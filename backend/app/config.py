from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
DATASET_DIR = BACKEND_DIR / "dataset"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(BACKEND_DIR / ".env"), extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"
    max_repair_attempts: int = 2
    cors_origins: str = "http://localhost:5173"

    sales_csv: Path = DATASET_DIR / "sales_data.csv"
    targets_csv: Path = DATASET_DIR / "targets.csv"
    data_dictionary_json: Path = DATASET_DIR / "data_dictionary.json"
    nl_queries_json: Path = DATASET_DIR / "nl_queries.json"
    feedback_log_csv: Path = DATASET_DIR / "feedback_log.csv"

    max_result_rows: int = 500

    snowflake_account: str = ""
    snowflake_user: str = ""
    snowflake_password: str = ""
    snowflake_warehouse: str = "ANALYTICS_WH"
    snowflake_database: str = "ANALYTICS_QUERY_ENGINE"
    snowflake_schema: str = "PUBLIC"
    snowflake_role: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
