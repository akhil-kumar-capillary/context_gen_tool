from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    # Database
    database_url: str = "postgresql+asyncpg://dev:dev@localhost:5432/context_gen"
    database_url_sync: str = "postgresql+psycopg://dev:dev@localhost:5432/context_gen"

    # Auth
    session_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expiry_hours: int = 24

    # LLM API Keys (server-side only)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None

    # Databricks (global default, can be overridden per-org)
    databricks_instance: Optional[str] = None
    databricks_token: Optional[str] = None

    # Confluence
    confluence_url: Optional[str] = None
    confluence_token: Optional[str] = None

    # App
    cors_origins: list[str] = ["http://localhost:3000"]
    debug: bool = False

    # Primary admin email
    primary_admin_email: str = "akhil.kumar@capillarytech.com"

    # Token budgets (Databricks 5-doc architecture)
    token_budget_01_master: int = 2000
    token_budget_02_schema: int = 3000
    token_budget_03_business: int = 3000
    token_budget_04_filters: int = 2000
    token_budget_05_patterns: int = 4000
    focus_token_budget: int = 3000
    max_focus_docs: int = 3
    max_payload_chars: int = 200000

    # Sanitize/Refactoring
    sanitize_max_output_tokens: int = 64000
    chat_max_output_tokens: int = 8192
    chat_history_window: int = 20
    max_tool_rounds: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
