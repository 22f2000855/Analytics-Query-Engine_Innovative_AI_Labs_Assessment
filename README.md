# Intelligent Analytics Query Engine

Converts natural-language questions about a sales dataset into executable SQL, runs them, and returns a structured result with a confidence score and an explanation of what was understood and how the answer was produced.

Stack: **React (Vite)** frontend, **FastAPI** backend, **Google Gemini** for NL→SQL generation, **Snowflake** as the query engine.

## Architecture

```
frontend (React)  ──HTTP──>  backend (FastAPI)
                                 │
                                 ├─ prompt_builder.py  (schema + data dictionary + reference-date facts + few-shots + past corrections)
                                 ├─ gemini_client.py   (Gemini, structured JSON output, retry-with-backoff + clean failure surface)
                                 ├─ sql_validator.py   (sqlglot AST allow-list: SELECT-only, known tables, Snowflake dialect)
                                 ├─ sql_executor.py    (runs SQL against Snowflake via SQLAlchemy)
                                 ├─ confidence.py      (blends LLM confidence + repair/empty/entity signals)
                                 ├─ explanation.py     (turns structured fields into plain text)
                                 └─ feedback_store.py  (feedback_log.csv, folds corrections back into prompts)
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

## NL → SQL approach

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

**Backend**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows; source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
copy .env.example .env        # then fill in GEMINI_API_KEY and SNOWFLAKE_*
python -m scripts.setup_snowflake   # one-time: creates the warehouse/database/schema/tables and loads the CSVs
uvicorn app.main:app --reload
```
`setup_snowflake.py` is safe to re-run — it truncates and reloads rather than duplicating rows, and it only ever creates/touches its own dedicated database (`SNOWFLAKE_DATABASE` in `.env`, default `ANALYTICS_QUERY_ENGINE`), never any other database already in your account.

**Frontend**
```bash
cd frontend
npm install
copy .env.example .env
npm run dev
```

Then open http://localhost:5173.

**Batch test / sample outputs**
```bash
cd backend
python -m scripts.run_test_queries
```
Runs all 8 questions in `dataset/nl_queries.json` against the live pipeline and writes `backend/sample_outputs.json`, saving incrementally after each question. For the 6 questions with a single deterministic answer, an independently hand-written pandas oracle is printed alongside the model's result for comparison. If a question fails (e.g. a quota error), it's recorded as `{"query": ..., "error": ...}` and the run continues — re-running the script later reuses every already-succeeded result and only retries the ones that failed, so a rate limit never costs you progress already made.

## Sample outputs

The three results below were captured against the live Gemini API and checked against an independent pandas oracle (`backend/scripts/run_test_queries.py`) — all exact matches. They were generated before the Snowflake rewrite, so `generated_logic` shows SQLite syntax (`strftime`); the current system generates equivalent Snowflake syntax (`TO_CHAR`) instead, per the **Reliability**/**Why this stack** sections above. The Snowflake execution path itself — schema introspection, the validator's Snowflake dialect (including `QUALIFY`), and query execution — has been independently re-verified with real Snowflake queries producing these same numbers (108.0 for this exact question, matching top-product-per-region results, etc.); what hasn't been re-run yet is the full live-Gemini pipeline against Snowflake, blocked by the same free-tier daily cap discussed above.

```json
{
  "query": "Total sales in India for March",
  "generated_logic": "SELECT SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data WHERE country = 'India' AND strftime('%Y-%m', order_date) = '2024-03';",
  "result": [{"revenue": 108.0}],
  "confidence_score": 1.0,
  "explanation": "Understood: the user wants total revenue for India in March 2024. How generated: revenue computed as quantity * unit_price * (1 - discount), filtered by country and the reference-date-resolved month. Execution: returned 1 row(s)."
}
```
```json
{
  "query": "Top 2 cities by profit",
  "generated_logic": "SELECT city, SUM(profit) AS total_profit FROM sales_data GROUP BY city ORDER BY total_profit DESC LIMIT 2;",
  "result": [{"city": "New York", "total_profit": 200}, {"city": "San Francisco", "total_profit": 180}],
  "confidence_score": 1.0,
  "explanation": "Understood: the two cities with the highest total profit. How generated: SUM(profit) grouped by city, ordered descending, limited to 2. Execution: returned 2 row(s)."
}
```
```json
{
  "query": "Average order value by region",
  "generated_logic": "SELECT region, SUM(quantity * unit_price * (1 - discount)) / COUNT(order_id) AS avg_order_value FROM sales_data GROUP BY region;",
  "result": [{"region": "APAC", "avg_order_value": 118.5}, {"region": "EMEA", "avg_order_value": 799.33}, {"region": "NA", "avg_order_value": 1087.47}],
  "confidence_score": 1.0,
  "explanation": "Understood: average order value per region. How generated: revenue summed per region divided by order count per region. Execution: returned 3 row(s)."
}
```

The remaining 5 questions (target comparison, contribution %, window-function ranking, YoY, nested top-3-per-region) are implemented and covered by the few-shot prompt design and the validator/executor pipeline, but weren't re-verified against live Gemini output in this run — testing hit the **Gemini free-tier daily cap (20 requests/day)** partway through, which the system surfaced as a clean error rather than a crash (see **Reliability** above). Run `python -m scripts.run_test_queries` yourself with a fresh quota window to generate the full 8-entry `sample_outputs.json`; it will reuse the 3 results above and only spend quota on the rest.

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
