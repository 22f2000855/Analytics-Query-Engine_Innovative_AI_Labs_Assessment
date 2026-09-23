from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text

from app.config import settings
from app.db.engine import engine


@dataclass
class ExecutionResult:
    success: bool
    rows: list[dict[str, Any]]
    row_count: int
    truncated: bool
    duration_ms: float
    error: str | None = None


def execute_sql(sql: str) -> ExecutionResult:
    sql = sql.strip().rstrip(";")
    start = time.perf_counter()
    try:
        with engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            fetched = result.fetchmany(settings.max_result_rows + 1)
            rows = [dict(zip(columns, row)) for row in fetched]
    except Exception as e:
        duration_ms = (time.perf_counter() - start) * 1000
        return ExecutionResult(
            success=False, rows=[], row_count=0, truncated=False, duration_ms=duration_ms, error=str(e)
        )

    duration_ms = (time.perf_counter() - start) * 1000
    truncated = len(rows) > settings.max_result_rows
    if truncated:
        rows = rows[: settings.max_result_rows]

    return ExecutionResult(
        success=True,
        rows=rows,
        row_count=len(rows),
        truncated=truncated,
        duration_ms=duration_ms,
        error=None,
    )
