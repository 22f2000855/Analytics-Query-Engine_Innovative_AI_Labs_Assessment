"""One-time setup: creates the Snowflake warehouse, database, schema, and
sales_data/targets tables, then loads dataset/sales_data.csv and
dataset/targets.csv into them.

Safe to re-run: every CREATE uses IF NOT EXISTS, and tables are truncated
before reload so re-running doesn't duplicate rows.

Usage (from backend/): python -m scripts.setup_snowflake
Requires SNOWFLAKE_* variables in backend/.env.
"""
from __future__ import annotations

import pandas as pd
import snowflake.connector

from app.config import settings

CREATE_WAREHOUSE = f"""
CREATE WAREHOUSE IF NOT EXISTS {settings.snowflake_warehouse}
  WAREHOUSE_SIZE = 'XSMALL'
  AUTO_SUSPEND = 60
  AUTO_RESUME = TRUE
  INITIALLY_SUSPENDED = TRUE
"""

CREATE_DATABASE = f"CREATE DATABASE IF NOT EXISTS {settings.snowflake_database}"

CREATE_SCHEMA = f"CREATE SCHEMA IF NOT EXISTS {settings.snowflake_database}.{settings.snowflake_schema}"

CREATE_SALES_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.snowflake_database}.{settings.snowflake_schema}.sales_data (
  order_id INTEGER,
  order_date DATE,
  region VARCHAR,
  country VARCHAR,
  city VARCHAR,
  customer_id VARCHAR,
  customer_segment VARCHAR,
  product_category VARCHAR,
  product_subcategory VARCHAR,
  product_name VARCHAR,
  quantity INTEGER,
  unit_price FLOAT,
  discount FLOAT,
  shipping_cost FLOAT,
  profit FLOAT
)
"""

CREATE_TARGETS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {settings.snowflake_database}.{settings.snowflake_schema}.targets (
  region VARCHAR,
  month VARCHAR,
  target_revenue FLOAT
)
"""


def _connect() -> snowflake.connector.SnowflakeConnection:
    return snowflake.connector.connect(
        account=settings.snowflake_account,
        user=settings.snowflake_user,
        password=settings.snowflake_password,
        role=settings.snowflake_role or None,
    )


def _load_sales_rows() -> list[tuple]:
    df = pd.read_csv(settings.sales_csv, keep_default_na=False, na_values=[])
    df["order_date"] = pd.to_datetime(df["order_date"], format="%d-%m-%Y").dt.strftime("%Y-%m-%d")
    return list(df.itertuples(index=False, name=None))


def _load_target_rows() -> list[tuple]:
    df = pd.read_csv(settings.targets_csv, keep_default_na=False, na_values=[])
    return list(df.itertuples(index=False, name=None))


def main() -> None:
    missing = [
        name
        for name in ("snowflake_account", "snowflake_user", "snowflake_password")
        if not getattr(settings, name)
    ]
    if missing:
        print(f"Missing required settings in backend/.env: {', '.join(missing)}. Aborting.")
        return

    print(f"Connecting to Snowflake account {settings.snowflake_account}...")
    conn = _connect()
    cur = conn.cursor()
    try:
        print(f"Creating warehouse {settings.snowflake_warehouse} (XSMALL, auto-suspend 60s)...")
        cur.execute(CREATE_WAREHOUSE)

        print(f"Creating database {settings.snowflake_database}...")
        cur.execute(CREATE_DATABASE)

        print(f"Creating schema {settings.snowflake_schema}...")
        cur.execute(CREATE_SCHEMA)

        cur.execute(f"USE WAREHOUSE {settings.snowflake_warehouse}")
        cur.execute(f"USE DATABASE {settings.snowflake_database}")
        cur.execute(f"USE SCHEMA {settings.snowflake_schema}")

        print("Creating sales_data table...")
        cur.execute(CREATE_SALES_TABLE)

        print("Creating targets table...")
        cur.execute(CREATE_TARGETS_TABLE)

        print("Loading sales_data rows (truncate + insert)...")
        cur.execute("TRUNCATE TABLE sales_data")
        sales_rows = _load_sales_rows()
        cur.executemany(
            "INSERT INTO sales_data VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            sales_rows,
        )
        print(f"  inserted {len(sales_rows)} rows")

        print("Loading targets rows (truncate + insert)...")
        cur.execute("TRUNCATE TABLE targets")
        target_rows = _load_target_rows()
        cur.executemany("INSERT INTO targets VALUES (%s,%s,%s)", target_rows)
        print(f"  inserted {len(target_rows)} rows")

        conn.commit()

        cur.execute("SELECT COUNT(*) FROM sales_data")
        sales_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM targets")
        targets_count = cur.fetchone()[0]
        print(f"\nVerified: sales_data has {sales_count} rows, targets has {targets_count} rows.")
        print(
            f"Fully-qualified table names: "
            f"{settings.snowflake_database}.{settings.snowflake_schema}.sales_data, "
            f"{settings.snowflake_database}.{settings.snowflake_schema}.targets"
        )
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
