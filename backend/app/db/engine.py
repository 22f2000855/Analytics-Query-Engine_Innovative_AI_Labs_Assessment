from urllib.parse import quote_plus

from sqlalchemy import create_engine

from app.config import settings


def _build_url() -> str:
    password = quote_plus(settings.snowflake_password)
    url = (
        f"snowflake://{settings.snowflake_user}:{password}"
        f"@{settings.snowflake_account}/{settings.snowflake_database}/{settings.snowflake_schema}"
        f"?warehouse={settings.snowflake_warehouse}"
    )
    if settings.snowflake_role:
        url += f"&role={settings.snowflake_role}"
    return url


# Scoped to ANALYTICS_QUERY_ENGINE.PUBLIC only — a dedicated database created
# for this project, entirely separate from any other database/schema in the
# same Snowflake account.
engine = create_engine(_build_url(), pool_pre_ping=True)
