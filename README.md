# Intelligent Analytics Query Engine

Converts natural-language questions about a sales dataset into executable SQL, runs them, and returns a structured result with a confidence score and an explanation of what was understood and how the answer was produced.

Stack: **React (Vite)** frontend, **FastAPI** backend, **Google Gemini** for NL→SQL generation, **Snowflake** as the query engine.

## Architecture

```
frontend (React, Vite)  ──HTTP (fetch)──>  backend (FastAPI, app/main.py)
                                                │
                                      app/api/*.py  — HTTP route handlers
                                        ├─ routes_query.py     POST /api/query
                                        ├─ routes_feedback.py  POST /api/feedback
                                        └─ routes_meta.py      GET  /api/examples
                                                │
                                app/core/pipeline.py  — orchestrates every /api/query request
                                                │
        ┌───────────────┬───────────────┬───────┴────────┬────────────────┬─────────────────┐
        │               │               │                │                │                 │
data_loader.py   dictionary.py   prompt_builder.py  gemini_client.py  sql_validator.py  sql_executor.py
schema + entity   data dict +     assembles the      Gemini call,      sqlglot AST       runs SQL via
introspection     reference-date  system prompt      retry-with-       allow-list        SQLAlchemy on
at startup        facts                              backoff           (SELECT-only,     Snowflake
                                                                        known tables)
        │                                                                        │
        └───────────────────────────────┬─────────────────────────────────────────┘
                                         │
                    confidence.py + explanation.py — blends signals into a score + plain-text explanation
                                         │
                    feedback_store.py — feedback_log.csv, folds past corrections back into the next prompt

Supporting layers used throughout the above:
  app/db/engine.py       SQLAlchemy engine/connection to Snowflake
  app/models/schemas.py  Pydantic request/response contracts (also the Gemini structured-output schema)
  app/config.py          env-driven settings (pydantic-settings, reads backend/.env)
```

The dataset lives in a **dedicated Snowflake database** (`ANALYTICS_QUERY_ENGINE.PUBLIC`, created and loaded once via `scripts/setup_snowflake.py` from `sales_data.csv`/`targets.csv`) — a database created specifically for this project, isolated from anything else already in the same Snowflake account. The backend never writes to it; it only connects, introspects the schema at startup (`data_loader.py`), and runs read-only `SELECT` queries. Because it's real Snowflake SQL rather than a constrained DSL, Gemini can generate genuine joins, `GROUP BY`, and window functions (including Snowflake's `QUALIFY` clause) — that's what makes top-N-per-group, contribution %, and nested ranking queries possible without hand-written special cases per query type.

## Why this stack

- **Snowflake over an ad-hoc local database**: real SQL semantics (window functions, joins, `QUALIFY`) map directly onto what a language model is already good at generating, it's far easier to validate/sandbox a SQL string than arbitrary pandas code, and it's the same class of system a business's actual data warehouse would already be — this isn't just a demo database, it's the target of a realistic integration.
- **`google-genai` SDK with `response_schema`**: Gemini validates its own output against a Pydantic schema (`GenerationOutput`: `understood`, `sql`, `reasoning`, `assumptions`, `confidence`) server-side, so the backend never regex-scrapes JSON out of prose.
- **sqlglot AST validation, not regex**: parses the generated SQL into a real syntax tree (Snowflake dialect) and walks it — rejects anything that isn't a single `SELECT` statement and checks every referenced table against an allow-list (`sales_data`, `targets`). A regex keyword scan (`DROP`, `INSERT`, etc.) sits alongside it as a second, cheap layer. Note this is an application-level allow-list, not a Snowflake-side permission boundary — the connecting user's actual Snowflake role privileges are whatever they were granted outside this app, so the allow-list is the real safety net here, not database-level isolation.

## Reliability

Gemini calls go through a retry layer (`gemini_client.py`), not a bare API call:
- **Retryable** failures — rate limits (429), server errors (5xx), network timeouts/drops — get up to 3 attempts with exponential backoff (1s, 2s).
- **Non-retryable** failures — a bad API key, a malformed request — fail immediately instead of wasting time retrying something that can't succeed.
- If Gemini is still unreachable after retries, or returns output that doesn't parse even with a forced schema, the API returns a clean `502` with an actionable message (`"Unable to reach the Gemini API right now..."`) instead of a raw `500` stack trace. The frontend's existing error banner displays this as-is.

This was validated against a real failure, not just a mock: the batch test script below hit Gemini's free-tier daily cap (20 requests/day) mid-run, and the system degraded exactly as designed — clean error, no crash, no fabricated result.

## Approach

1. **Schema grounding** — the exact column names/types and `data_dictionary.json` (metrics, synonyms, dimensions) are serialized straight into the system prompt; nothing is hand-duplicated.
2. **Reference-date facts, not wall-clock time** — this dataset only spans 2024-01 to 2024-03. Using real "today" for phrases like "last month" would resolve to a period with zero data. Instead, `REFERENCE_DATE = max(order_date)` (2024-03-10) is computed at startup, and "this month" / "last month" / "this quarter" / "last year" etc. are resolved against *that* and injected into the prompt as concrete facts. When a resolved period has no data in this dataset, the model is instructed to still write correct SQL, but record it as an assumption and lower its confidence — never invent numbers.
3. **Few-shot examples** cover every complexity class the assignment requires: simple filter+aggregate, top-N by group, group averages, a target-comparison join, contribution %, a `RANK() OVER (PARTITION BY ...)` query, and a nested top-N-then-aggregate query.
4. **Self-repair loop** (`pipeline.py`, max 1 retry) — if the generated SQL fails validation or execution, the exact SQL and exact error are sent back to Gemini for one correction attempt before giving up.

## Confidence score

```python
score = llm_confidence                 # Gemini's own self-reported 0-1 confidence
score *= 0.7 ** repair_count           # each repair round is evidence the first attempt was wrong
if row_count == 0: score *= 0.85       # ran clean but zero rows is often an over-narrow filter
if unresolved_entities: score *= 0.8   # filtered on a value not present in the loaded data
# hard 0 if execution never succeeded
```

`unresolved_entities` is checked by extracting string literals from the validated SQL's `WHERE` clause (via the same sqlglot AST) and comparing them against the actual distinct region/country/city/segment/category/product values in the dataset — catching a hallucinated or typo'd filter value before it silently returns an empty result. All four components are returned in `meta.confidence_breakdown` for transparency (shown as a tooltip on the confidence badge in the UI).

## Explanation

Built entirely from structured fields (no extra LLM call): Gemini's own `understood` (plain-language restatement) and `reasoning` (which tables/joins/aggregations were used), plus any `assumptions`, whether a repair round was needed and why, and the execution outcome (row count / error).

## Feedback loop

`POST /api/feedback` appends `{timestamp, query, generated_sql, rating, corrected_sql, notes}` to `backend/dataset/feedback_log.csv`. On every new question, past 👎 corrections are ranked by Jaccard keyword-overlap with the new question (plus recency as a tiebreaker) and the top ~5 are injected into the prompt as a "learn from past corrections" few-shot block — no vector DB needed at this dataset's scale.

## Running it

These are complete, copy-pasteable instructions to get the app running locally from a fresh clone/zip.

> **Credentials**: this repo intentionally does not commit real API keys or database passwords (GitHub's push protection blocks it, and it's bad practice regardless). The actual working `GEMINI_API_KEY` and Snowflake credentials have been shared directly with the evaluator through a separate channel. Paste those values into the `backend/.env` file below in place of the placeholders.

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Create `backend/.env` (copy `backend/.env.example` and fill in the real values you were given):

```env
GEMINI_API_KEY=your-gemini-api-key-here
GEMINI_MODEL=gemini-3.6-flash
MAX_REPAIR_ATTEMPTS=2
CORS_ORIGINS=http://localhost:5173

SNOWFLAKE_ACCOUNT=your-account-identifier
SNOWFLAKE_USER=your-username
SNOWFLAKE_PASSWORD=your-password
SNOWFLAKE_WAREHOUSE=ANALYTICS_WH
SNOWFLAKE_DATABASE=ANALYTICS_QUERY_ENGINE
SNOWFLAKE_SCHEMA=PUBLIC
SNOWFLAKE_ROLE=
```

Then, one-time only, load the dataset into Snowflake and start the server:

```bash
python -m scripts.setup_snowflake   # creates the warehouse/database/schema/tables and loads the CSVs
uvicorn app.main:app --reload       # serves on http://localhost:8000
```

`setup_snowflake.py` is safe to re-run — it truncates and reloads rather than duplicating rows, and it only ever creates/touches its own dedicated database (`ANALYTICS_QUERY_ENGINE`), never any other database in the account.

Verify the backend is up: open **http://localhost:8000/docs** (interactive Swagger UI).

### 2. Frontend

```bash
cd frontend
npm install
```

Create `frontend/.env` with exactly this content:

```env
VITE_API_BASE_URL=http://localhost:8000
```

```bash
npm run dev
```

Then open **http://localhost:5173** in a browser — that's the app.

### 3. Troubleshooting

- **Gemini quota errors** ("Unable to reach the Gemini API right now"): free-tier Gemini keys are capped at **20 requests/day per project**. If it's exhausted, either wait for the daily reset or swap in a key from a different Google Cloud project/account in `backend/.env`, then restart the backend.
- **Port 8000 already in use / fails to bind on Windows**: some Windows setups (Hyper-V/WSL networking) reserve a range of ports including 8000 at the OS level, causing `uvicorn` to fail with `WinError 10048` even with nothing visibly running on it. If that happens, run the backend on a different port and point the frontend at it:
  ```bash
  uvicorn app.main:app --reload --port 8001
  ```
  and set `VITE_API_BASE_URL=http://localhost:8001` in `frontend/.env` (restart both after changing).
- **`.env` changes not taking effect**: `uvicorn --reload` only watches `.py` files, not `.env`. After editing `backend/.env`, stop and restart the `uvicorn` process manually.

### 4. Batch test / regenerate sample outputs

```bash
cd backend
python -m scripts.run_test_queries
```
Runs all 8 questions in `dataset/nl_queries.json` against the live pipeline and writes `backend/sample_outputs.json`, saving incrementally after each question. For the 6 questions with a single deterministic answer, an independently hand-written pandas oracle is printed alongside the model's result for comparison. If a question fails (e.g. a quota error), it's recorded as `{"query": ..., "error": ...}` and the run continues — re-running the script later reuses every already-succeeded result and only retries the ones that failed, so a rate limit never costs you progress already made.

## Sample outputs

All 9 queries below were run against the **live Gemini API and live Snowflake** (not mocked). The full structured JSON for every one — including `meta.confidence_breakdown`, execution timing, and repair info — is in [`backend/sample_outputs.json`](backend/sample_outputs.json). The 6 rows marked ✅ were additionally checked against an independently hand-written pandas oracle (`backend/scripts/run_test_queries.py`) with an exact match; the other 3 have no single deterministic answer to check against (nested/compound logic, or genuinely un-computable given the dataset), so they're included for inspection instead.

| # | Query | Result | Confidence | Oracle match |
|---|-------|--------|------------|:---:|
| 1 | Total sales in India for March | `108.0` | 1.0 | ✅ |
| 2 | Top 2 cities by profit | New York (200), San Francisco (180) | 1.0 | ✅ |
| 3 | Average order value by region | APAC 118.5, EMEA 799.33, NA 1087.47 | 1.0 | ✅ |
| 4 | Which region missed its target in Feb? | APAC, EMEA, NA (all 3 missed) | 0.8 | ✅ |
| 5 | Sales contribution % by category | Technology 88.06%, Furniture 9.44%, Office Supplies 2.50% | 1.0 | ✅ |
| 6 | Top product in each region | APAC: Ergo Chair, EMEA: Samsung Galaxy, NA: Dell XPS | 1.0 | ✅ |
| 7 | YoY growth in revenue | Only one year (2024) present; growth % correctly not fabricated | 0.5 | — |
| 8 | Revenue of top 3 customers per region | APAC 474.0, EMEA 2398.0, NA 3262.4 | 1.0 | — |
| 9 | What is the highest sale in the world and in India? | World: 2068.0, India: 216.0 | 0.9 | — |

Three representative full outputs, showing a join-with-target comparison, a window-function top-N, and a nested subquery:

```json
{
  "query": "Which region missed its target in Feb?",
  "generated_logic": "SELECT s.region, SUM(s.quantity * s.unit_price * (1 - s.discount)) AS revenue, t.target_revenue FROM sales_data s JOIN targets t ON s.region = t.region AND TO_CHAR(s.order_date, 'YYYY-MM') = t.month WHERE t.month = '2024-02' GROUP BY s.region, t.target_revenue HAVING revenue < t.target_revenue",
  "result": [
    {"region": "APAC", "revenue": 75.0, "target_revenue": 6000.0},
    {"region": "EMEA", "revenue": 255.0, "target_revenue": 7500.0},
    {"region": "NA", "revenue": 1116.0, "target_revenue": 9500.0}
  ],
  "confidence_score": 0.8,
  "explanation": "Understood: Identify the regions that generated less revenue than their target revenue in February 2024. How generated: Joined sales_data with targets on region and month (2024-02), calculated actual revenue using quantity * unit_price * (1 - discount), grouped by region and target_revenue, and filtered for regions where total revenue was strictly less than target_revenue."
}
```
```json
{
  "query": "Top product in each region",
  "generated_logic": "SELECT region, product_name, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY region, product_name QUALIFY RANK() OVER (PARTITION BY region ORDER BY SUM(quantity * unit_price * (1 - discount)) DESC) = 1",
  "result": [
    {"region": "APAC", "product_name": "Ergo Chair", "revenue": 324.0},
    {"region": "EMEA", "product_name": "Samsung Galaxy", "revenue": 1288.0},
    {"region": "NA", "product_name": "Dell XPS", "revenue": 2068.0}
  ],
  "confidence_score": 1.0,
  "explanation": "Understood: Find the top product by total revenue in each region.\nHow generated: Grouped sales_data by region and product_name, computed total revenue as quantity * unit_price * (1 - discount), and used Snowflake's QUALIFY clause with RANK() to filter for the top product per region."
}
```
```json
{
  "query": "Revenue of top 3 customers per region",
  "generated_logic": "SELECT region, SUM(revenue) AS top3_revenue FROM (SELECT region, customer_id, SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data GROUP BY region, customer_id QUALIFY RANK() OVER (PARTITION BY region ORDER BY SUM(quantity * unit_price * (1 - discount)) DESC) <= 3) GROUP BY region;",
  "result": [
    {"region": "APAC", "top3_revenue": 474.0},
    {"region": "EMEA", "top3_revenue": 2398.0},
    {"region": "NA", "top3_revenue": 3262.4}
  ],
  "confidence_score": 1.0,
  "explanation": "Understood: Calculate the combined revenue from the top 3 customers in each region based on total customer revenue.\nHow generated: A subquery aggregates revenue by region and customer_id, filtering for the top 3 customers per region using RANK() and QUALIFY. The outer query then sums the revenue of these top 3 customers for each region."
}
```

Note: entries #1–6 in `sample_outputs.json` were captured earlier in development and retain an older, more verbose `explanation` phrasing (an explicit "Assumptions made: ..." / "Execution: ..." sentence); entries #7–9 reflect the current, tightened format (two-line "Understood" / "How generated" only, no separate assumptions/execution sentences — see **Explanation** section above). The underlying SQL and results are unaffected either way; only the wording of the explanation text differs. Run `python -m scripts.run_test_queries` after deleting `sample_outputs.json` to regenerate all 8 nl_queries.json entries in the current format if a fully consistent set is needed.

## Tradeoffs

- **Single repair round, not a full agent loop** — bounded latency/cost over chasing every possible failure mode. A second failure surfaces `confidence_score = 0` with the execution error rather than retrying indefinitely.
- **sqlglot AST validation over a full sandboxed executor** — sufficient here because this app's Snowflake database only ever contains two read-only tables (`sales_data`, `targets`) that it never writes to; even a validator bypass can only read data, never mutate it. This is an application-level guarantee, not a Snowflake permission boundary (see **Why this stack**).
- **Snowflake over an in-memory database** — trades the near-zero latency of SQLite-in-memory (sub-millisecond) for real network round-trips and warehouse spin-up time (typically 100–400ms per query in testing here), in exchange for querying a real, persistent, production-shaped data source instead of re-loading CSVs into memory on every restart. For this dataset's tiny size the tradeoff is purely about realism, not necessity — but it's the choice that generalizes to an actual business's existing warehouse.
- **No vector DB for feedback retrieval** — Jaccard keyword overlap is enough at this dataset's scale (a handful of feedback rows); would need revisiting with a much larger corrections log.
- **Honesty over YoY / "last quarter"** — this dataset has only one calendar year of data, so a true year-over-year percentage or a prior-quarter comparison can't be computed. The system says so via `assumptions` and a lowered confidence score rather than fabricating a number.
- **Bounded retries against a hard quota, not unlimited backoff** — the retry layer is designed for transient failures (rate limits, brief outages), not for waiting out a daily quota reset (Gemini free tier: 20 requests/day). Retrying 3 times against a hard daily cap wastes a few calls before failing cleanly; a production deployment would use a paid tier or an application-level daily budget tracker instead of relying on retry alone.

## Future improvements

- Multi-year dataset to make YoY/quarter-over-quarter comparisons meaningful.
- Streaming responses (SSE) so the UI can show "generating → validating → executing" progress instead of one blocking request.
- Fuzzy entity matching (e.g. Levenshtein) to auto-suggest the closest valid value when a filter references an unrecognized entity, instead of just penalizing confidence.
- Query result caching for repeated identical questions.
- Auth + per-user feedback logs if this moved beyond a single-user assignment context.
