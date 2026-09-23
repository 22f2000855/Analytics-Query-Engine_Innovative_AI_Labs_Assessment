from __future__ import annotations

import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp

from app.core.data_loader import ALLOWED_TABLES

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|TRUNCATE|ATTACH|DETACH|"
    r"PRAGMA|VACUUM|GRANT|REVOKE|EXEC|REINDEX|ANALYZE)\b",
    re.IGNORECASE,
)
COMMENT_PATTERN = re.compile(r"(--|/\*)")


@dataclass
class ValidationResult:
    ok: bool
    error: str | None = None
    where_literals: list[str] | None = None


def validate_sql(sql: str) -> ValidationResult:
    sql = sql.strip().rstrip(";")

    if not sql:
        return ValidationResult(ok=False, error="Empty SQL statement.")

    if FORBIDDEN_KEYWORDS.search(sql):
        return ValidationResult(ok=False, error="Statement contains a forbidden keyword (only SELECT is allowed).")
    if COMMENT_PATTERN.search(sql):
        return ValidationResult(ok=False, error="SQL comments are not allowed.")

    try:
        statements = sqlglot.parse(sql, read="snowflake")
    except Exception as e:  # sqlglot raises its own ParseError subclasses
        return ValidationResult(ok=False, error=f"SQL failed to parse: {e}")

    if len(statements) != 1 or statements[0] is None:
        return ValidationResult(ok=False, error="Exactly one SQL statement is required.")

    root = statements[0]

    if not isinstance(root, (exp.Select, exp.Union)):
        return ValidationResult(ok=False, error=f"Only SELECT statements are allowed, got {type(root).__name__}.")

    cte_names = {cte.alias_or_name.lower() for cte in root.find_all(exp.CTE)}

    for table in root.find_all(exp.Table):
        name = table.name.lower()
        if name in cte_names:
            continue
        if name not in {t.lower() for t in ALLOWED_TABLES}:
            return ValidationResult(ok=False, error=f"Reference to disallowed table '{table.name}'.")

    where_literals = _collect_entity_literals(root)

    return ValidationResult(ok=True, where_literals=where_literals)


def _collect_entity_literals(root: exp.Expression) -> list[str]:
    """Collect string literals that are directly compared against a bare column
    (e.g. country = 'India', region IN ('APAC', 'EMEA')) — these are the only
    literals that represent an entity filter value worth checking against the
    dataset's known values. Deliberately excludes literals nested inside
    function calls (e.g. strftime('%Y-%m', order_date) = '2024-03'), which are
    derived/format values, not raw entity filters.
    """
    literals: list[str] = []

    for cmp in root.find_all((exp.EQ, exp.NEQ)):
        left, right = cmp.this, cmp.expression
        if isinstance(left, exp.Column) and isinstance(right, exp.Literal) and right.is_string:
            literals.append(right.this)
        elif isinstance(right, exp.Column) and isinstance(left, exp.Literal) and left.is_string:
            literals.append(left.this)

    for in_expr in root.find_all(exp.In):
        if isinstance(in_expr.this, exp.Column):
            for lit in in_expr.expressions:
                if isinstance(lit, exp.Literal) and lit.is_string:
                    literals.append(lit.this)

    return literals
