from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import inspect, text

from app.db.engine import engine

ALLOWED_TABLES = {"sales_data", "targets"}

# Columns whose distinct values are worth checking a generated SQL's WHERE
# literals against, to catch hallucinated entity names (typo'd country, etc.)
ENTITY_COLUMNS = {
    "sales_data": [
        "region",
        "country",
        "city",
        "customer_segment",
        "product_category",
        "product_subcategory",
        "product_name",
    ],
    "targets": ["region"],
}


@dataclass
class LoadedDataset:
    reference_date: date
    schema_description: str
    allowed_columns: dict[str, list[str]] = field(default_factory=dict)
    entity_values: dict[str, set[str]] = field(default_factory=dict)


_loaded: LoadedDataset | None = None


def _describe_columns(table: str) -> list[tuple[str, str]]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"DESCRIBE TABLE {table}")).fetchall()
    # DESCRIBE TABLE columns: name, type, kind, null?, default, ...
    return [(row[0].lower(), row[1]) for row in rows]


def load_dataset() -> LoadedDataset:
    """Introspect the sales_data/targets tables already loaded into Snowflake
    (via scripts/setup_snowflake.py) — this app never writes to those tables,
    only reads. Idempotent; call once at startup."""
    global _loaded

    sales_columns = _describe_columns("sales_data")
    targets_columns = _describe_columns("targets")

    allowed_columns = {
        "sales_data": [name for name, _ in sales_columns],
        "targets": [name for name, _ in targets_columns],
    }

    with engine.connect() as conn:
        reference_date = conn.execute(text("SELECT MAX(order_date) FROM sales_data")).scalar()

        entity_values: dict[str, set[str]] = {}
        for col in ENTITY_COLUMNS["sales_data"]:
            rows = conn.execute(text(f"SELECT DISTINCT {col} FROM sales_data")).fetchall()
            entity_values[col] = {str(r[0]) for r in rows}
        for col in ENTITY_COLUMNS["targets"]:
            rows = conn.execute(text(f"SELECT DISTINCT {col} FROM targets")).fetchall()
            entity_values[col] = entity_values.get(col, set()) | {str(r[0]) for r in rows}

    schema_lines = ["TABLE sales_data ("]
    for name, sql_type in sales_columns:
        schema_lines.append(f"  {name} {sql_type},")
    schema_lines.append(")")
    schema_lines.append("TABLE targets (")
    for name, sql_type in targets_columns:
        schema_lines.append(f"  {name} {sql_type},")
    schema_lines.append(")")
    schema_lines.append("")
    schema_lines.append("NOTES:")
    schema_lines.append("- sales_data.order_date is a native DATE column.")
    schema_lines.append("- targets.month is stored as TEXT in 'YYYY-MM' format.")
    schema_lines.append(
        "- revenue is NOT a stored column; it must always be computed as "
        "quantity * unit_price * (1 - discount)."
    )
    schema_lines.append("- profit IS a stored column in sales_data (already net of costs).")
    schema_lines.append("- targets.region values use 'NA' for North America (not null).")

    _loaded = LoadedDataset(
        reference_date=reference_date,
        schema_description="\n".join(schema_lines),
        allowed_columns=allowed_columns,
        entity_values=entity_values,
    )
    return _loaded


def get_loaded_dataset() -> LoadedDataset:
    if _loaded is None:
        raise RuntimeError("Dataset not loaded yet; call load_dataset() at startup first.")
    return _loaded


def tables_exist() -> bool:
    inspector = inspect(engine)
    names = {n.lower() for n in inspector.get_table_names()}
    return ALLOWED_TABLES.issubset(names)
