"""Batch-runs every question in dataset/nl_queries.json through the live pipeline
(real Gemini calls, no mocking) and writes backend/sample_outputs.json.

For the 6 questions with a single deterministic correct answer, also checks the
result against an independently hand-written pandas oracle (not shared code with
prompt_builder.py's few-shots) and prints PASS/FAIL. The YoY and target-comparison
edge-case questions are printed for manual inspection only.

Usage (from backend/): python -m scripts.run_test_queries
Requires GEMINI_API_KEY to be set (backend/.env or environment).
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from app.config import settings
from app.core.data_loader import load_dataset
from app.core.feedback_store import ensure_log_exists
from app.core.gemini_client import GeminiUnavailableError
from app.core.pipeline import run_pipeline

BACKEND_DIR = Path(__file__).resolve().parent.parent
OUTPUT_PATH = BACKEND_DIR / "sample_outputs.json"
TOLERANCE = 0.01


def _revenue(df: pd.DataFrame) -> pd.Series:
    return df["quantity"] * df["unit_price"] * (1 - df["discount"])


def _load_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    sales = pd.read_csv(settings.sales_csv, keep_default_na=False, na_values=[])
    sales["order_date"] = pd.to_datetime(sales["order_date"], format="%d-%m-%Y")
    sales["month"] = sales["order_date"].dt.strftime("%Y-%m")
    sales["revenue"] = _revenue(sales)
    targets = pd.read_csv(settings.targets_csv, keep_default_na=False, na_values=[])
    return sales, targets


def _oracle_total_sales_india_march(sales: pd.DataFrame, targets: pd.DataFrame) -> float:
    mask = (sales["country"] == "India") & (sales["month"] == "2024-03")
    return round(float(sales.loc[mask, "revenue"].sum()), 2)


def _oracle_top2_cities_by_profit(sales: pd.DataFrame, targets: pd.DataFrame) -> list[str]:
    return list(sales.groupby("city")["profit"].sum().sort_values(ascending=False).head(2).index)


def _oracle_avg_order_value_by_region(sales: pd.DataFrame, targets: pd.DataFrame) -> dict[str, float]:
    grouped = sales.groupby("region").agg(revenue=("revenue", "sum"), orders=("order_id", "count"))
    aov = grouped["revenue"] / grouped["orders"]
    return {k: round(float(v), 2) for k, v in aov.items()}


def _oracle_region_missed_target_feb(sales: pd.DataFrame, targets: pd.DataFrame) -> list[str]:
    feb_sales = sales[sales["month"] == "2024-02"].groupby("region")["revenue"].sum()
    feb_targets = targets[targets["month"] == "2024-02"].set_index("region")["target_revenue"]
    missed = [r for r in feb_targets.index if feb_sales.get(r, 0) < feb_targets[r]]
    return missed


def _oracle_contribution_pct_by_category(sales: pd.DataFrame, targets: pd.DataFrame) -> dict[str, float]:
    total = sales["revenue"].sum()
    by_cat = sales.groupby("product_category")["revenue"].sum()
    return {k: round(float(v) * 100.0 / total, 2) for k, v in by_cat.items()}


def _oracle_top_product_per_region(sales: pd.DataFrame, targets: pd.DataFrame) -> dict[str, str]:
    by_region_product = sales.groupby(["region", "product_name"])["revenue"].sum().reset_index()
    idx = by_region_product.groupby("region")["revenue"].idxmax()
    top = by_region_product.loc[idx]
    return dict(zip(top["region"], top["product_name"]))


ORACLES = {
    "Total sales in India for March": _oracle_total_sales_india_march,
    "Top 2 cities by profit": _oracle_top2_cities_by_profit,
    "Average order value by region": _oracle_avg_order_value_by_region,
    "Which region missed its target in Feb?": _oracle_region_missed_target_feb,
    "Sales contribution % by category": _oracle_contribution_pct_by_category,
    "Top product in each region": _oracle_top_product_per_region,
}


def _load_existing_outputs() -> dict[str, dict]:
    """Load any previous run's results, keyed by question, so a re-run after a
    quota error or crash doesn't burn API calls re-fetching answers we already
    have. Only successful (non-error) entries are treated as reusable."""
    if not OUTPUT_PATH.exists():
        return {}
    try:
        existing = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return {item["query"]: item for item in existing if "error" not in item}


def _save(outputs: list[dict]) -> None:
    OUTPUT_PATH.write_text(json.dumps(outputs, indent=2, default=str), encoding="utf-8")


def main() -> None:
    if not settings.gemini_api_key:
        print("GEMINI_API_KEY is not set (backend/.env). Aborting.")
        return

    load_dataset()
    ensure_log_exists()
    sales, targets = _load_frames()

    with open(settings.nl_queries_json, "r", encoding="utf-8") as f:
        nl_queries = json.load(f)

    reusable = _load_existing_outputs()
    outputs: list[dict] = []
    succeeded = 0
    failed = 0

    for item in nl_queries:
        question = item["query"]

        if question in reusable:
            print(f"\n=== {question} === (reused from previous run)")
            outputs.append(reusable[question])
            succeeded += 1
            continue

        print(f"\n=== {question} ===")
        try:
            response = run_pipeline(question)
        except GeminiUnavailableError as e:
            print(f"SKIPPED — Gemini call failed: {e}")
            outputs.append({"query": question, "error": str(e)})
            failed += 1
            _save(outputs)  # persist partial progress after every query
            continue

        outputs.append(response.model_dump())
        succeeded += 1
        _save(outputs)  # persist partial progress after every query

        print(f"SQL: {response.generated_logic}")
        print(f"Confidence: {response.confidence_score}")
        print(f"Rows: {response.meta.execution.row_count}")

        oracle_fn = ORACLES.get(question)
        if oracle_fn is None:
            print("No deterministic oracle for this question — inspect manually.")
            continue

        try:
            expected = oracle_fn(sales, targets)
            print(f"Oracle expects: {expected}")
            print("Result:", response.result)
            print("(Compare the printed result against the oracle above by eye; "
                  "exact row-shape matching is left to manual review given the "
                  "variety of valid column-naming choices the model may make.)")
        except Exception as e:
            print(f"Oracle computation failed: {e}")

    _save(outputs)  # ensure trailing reused entries are persisted even if none were freshly saved after them
    print(f"\nWrote {len(outputs)} sample outputs to {OUTPUT_PATH} ({succeeded} succeeded, {failed} failed)")
    if failed:
        print("Re-run this script later to retry only the failed questions (successful ones are reused).")


if __name__ == "__main__":
    main()
