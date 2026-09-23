from __future__ import annotations

import json

from app.core.data_loader import LoadedDataset
from app.core.dictionary import TimeFacts, format_time_facts_block
from app.core.feedback_store import FeedbackRow, format_corrections_block

FEW_SHOT_EXAMPLES = """
EXAMPLES (Snowflake SQL dialect, this schema):

Q: "Total sales in India for March"
SQL: SELECT SUM(quantity * unit_price * (1 - discount)) AS revenue FROM sales_data WHERE country = 'India' AND TO_CHAR(order_date, 'YYYY-MM') = '2024-03';

Q: "Top 2 cities by profit"
SQL: SELECT city, SUM(profit) AS total_profit FROM sales_data GROUP BY city ORDER BY total_profit DESC LIMIT 2;

Q: "Average order value by region"
SQL: SELECT region, SUM(quantity * unit_price * (1 - discount)) / COUNT(order_id) AS avg_order_value FROM sales_data GROUP BY region;

Q: "Which region missed its target in Feb?"
SQL: SELECT s.region, SUM(s.quantity * s.unit_price * (1 - s.discount)) AS revenue, t.target_revenue
     FROM sales_data s JOIN targets t ON s.region = t.region AND TO_CHAR(s.order_date, 'YYYY-MM') = t.month
     WHERE t.month = '2024-02'
     GROUP BY s.region, t.target_revenue
     HAVING revenue < t.target_revenue;

Q: "Sales contribution % by category"
SQL: SELECT product_category,
            SUM(quantity * unit_price * (1 - discount)) * 100.0 / (SELECT SUM(quantity * unit_price * (1 - discount)) FROM sales_data) AS contribution_pct
     FROM sales_data GROUP BY product_category;

Q: "Top product in each region"
SQL: SELECT region, product_name, SUM(quantity * unit_price * (1 - discount)) AS revenue
     FROM sales_data
     GROUP BY region, product_name
     QUALIFY RANK() OVER (PARTITION BY region ORDER BY SUM(quantity * unit_price * (1 - discount)) DESC) = 1;

Q: "Revenue of top 3 customers per region"
SQL: SELECT region, SUM(revenue) AS top3_revenue FROM (
       SELECT region, customer_id, SUM(quantity * unit_price * (1 - discount)) AS revenue
       FROM sales_data
       GROUP BY region, customer_id
       QUALIFY RANK() OVER (PARTITION BY region ORDER BY SUM(quantity * unit_price * (1 - discount)) DESC) <= 3
     )
     GROUP BY region;

Q: "YoY growth in revenue"
SQL: SELECT TO_CHAR(order_date, 'YYYY') AS year, SUM(quantity * unit_price * (1 - discount)) AS revenue
     FROM sales_data GROUP BY year;
     -- NOTE: this dataset only has one calendar year of data. A true YoY growth
     -- percentage cannot be computed without a prior year. State this explicitly
     -- as an assumption and lower confidence rather than inventing a number.
""".strip()

RULES_BLOCK = """
RULES:
- Output Snowflake SQL dialect only. A single SELECT statement (QUALIFY and
  window functions are allowed; do not use SQLite functions like strftime).
- Never invent tables or columns. Only use sales_data and targets exactly as
  described, unqualified (no database/schema prefix needed — the connection
  is already scoped to the right database and schema).
- "revenue" / "sales" / "income" is NEVER a stored column: always compute it as
  quantity * unit_price * (1 - discount).
- "profit" IS a stored column in sales_data; do not recompute it.
- "earnings" means profit. "aov" means avg_order_value = revenue / orders.
- Use TO_CHAR(order_date, 'YYYY-MM') or TO_CHAR(order_date, 'YYYY') to extract
  month/year from order_date (a native DATE column). Use QUALIFY for
  "top N per group" ranking instead of a CTE + WHERE on a window function.
- Always answer, even if the question is ambiguous or references a time period
  with no data: make a reasonable assumption, record it in `assumptions`, and
  lower `confidence` accordingly. Never refuse and never fabricate numbers.
- Keep `assumptions` minimal: do NOT record an assumption for anything already
  resolved by the data dictionary, synonyms, or rules above (e.g. mapping
  "sales"/"income" to revenue, or "earnings" to profit is a known definition,
  not an assumption). Only record a genuine ambiguity — one the dictionary
  and rules don't already settle — such as an unresolved relative time phrase
  or a filter value that doesn't clearly map to the data.
- `confidence` must reflect how sure you are the SQL correctly answers the
  question as asked (1.0 = fully confident, lower for ambiguity/assumptions).
""".strip()


def build_system_prompt(
    dataset: LoadedDataset,
    dictionary: dict,
    time_facts: TimeFacts,
    corrections: list[FeedbackRow],
) -> str:
    parts = [
        "You are the SQL-generation engine of a natural-language analytics tool. "
        "Given a business question, produce a single Snowflake SQL SELECT statement "
        "that answers it against the schema below, plus a structured explanation.",
        "",
        "SCHEMA:",
        dataset.schema_description,
        "",
        "DATA DICTIONARY (metrics, dimensions, synonyms):",
        json.dumps(dictionary, indent=2),
        "",
        "REFERENCE DATE FACTS (use these to resolve relative time phrases; do not "
        "use wall-clock time):",
        format_time_facts_block(time_facts),
        "",
        FEW_SHOT_EXAMPLES,
        "",
        RULES_BLOCK,
    ]

    corrections_block = format_corrections_block(corrections)
    if corrections_block:
        parts += ["", corrections_block]

    return "\n".join(parts)


def build_repair_prompt(question: str, previous_sql: str, error: str) -> str:
    return (
        f'The previous SQL you generated for the question "{question}" failed.\n\n'
        f"Previous SQL:\n{previous_sql}\n\n"
        f"Error:\n{error}\n\n"
        "Generate a corrected SQL statement that fixes this specific error. "
        "Lower your `confidence` to reflect that a correction was needed."
    )
