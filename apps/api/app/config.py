import os
import logging
from dataclasses import dataclass
from pydantic_settings import BaseSettings
from pydantic import model_validator
from typing import Optional


logger = logging.getLogger(__name__)


def _env_or_dotenv(key: str, dotenv_path: str = ".env") -> Optional[str]:
    """Get a value from env var (if non-empty) or from .env file.

    Pydantic-settings prefers env vars over .env files. If the env var
    is set to an empty string, pydantic treats it as the actual value and
    ignores the .env file. This helper ensures that empty env vars fall
    through to the .env file value.
    """
    val = os.environ.get(key)
    if val:  # non-empty env var wins
        return val
    # Fall through to .env file
    try:
        from dotenv import dotenv_values
        vals = dotenv_values(dotenv_path)
        return vals.get(key) or None
    except ImportError:
        return None


# ---------------------------------------------------------------------------
# Intouch cluster → Databricks workspace mapping
# ---------------------------------------------------------------------------

# Canonical cluster keys (CAPS) → Databricks workspace URL
CLUSTER_DATABRICKS_MAP: dict[str, str] = {
    "APAC2": "https://capillary-notebook-asiacrm.cloud.databricks.com",
    "APAC":  "https://capillary-notebook-incrm.cloud.databricks.com",
    "EU":    "https://capillary-notebook-eucrm.cloud.databricks.com",
    "US":    "https://capillary-notebook-uscrm.cloud.databricks.com",
    "TATA":  "https://capillary-notebook-tata.cloud.databricks.com",
    "USHC":  "https://capillary-notebook-ushc.cloud.databricks.com",
    "SEA":   "https://capillary-notebook-seacrm-new.cloud.databricks.com",
}

# Canonical cluster keys (CAPS) → Intouch base URL
CLUSTER_INTOUCH_MAP: dict[str, str] = {
    "APAC2": "https://apac2.intouch.capillarytech.com",
    "APAC":  "https://apac.intouch.capillarytech.com",
    "EU":    "https://eu.intouch.capillarytech.com",
    "US":    "https://north-america.intouch.capillarytech.com",
    "TATA":  "https://tata.intouch.capillarytech.com",
    "USHC":  "https://ushc.intouch.capillarytech.com",
    "SEA":   "https://sea.intouch.capillarytech.com",
}

# Auth cluster slugs (lowercase, from login) → canonical CAPS key
# Most are just .upper(), but "north-america" maps to "US"
AUTH_CLUSTER_TO_KEY: dict[str, str] = {
    "apac2":         "APAC2",
    "apac":          "APAC",
    "eu":            "EU",
    "north-america": "US",
    "tata":          "TATA",
    "ushc":          "USHC",
    "sea":           "SEA",
}


@dataclass
class DatabricksCluster:
    """Resolved Databricks workspace config for a given Intouch cluster."""
    key: str        # canonical key, e.g. "APAC2"
    instance: str   # Databricks workspace URL
    token: str      # access token (never exposed to frontend)


def _resolve_databricks_token(cluster_key: str, dotenv_path: str = ".env") -> Optional[str]:
    """Resolve the Databricks access token for a cluster.

    Looks for env var: DATABRICKS_<CLUSTER_KEY>_TOKEN
    Falls back to .env file.
    """
    env_key = f"DATABRICKS_{cluster_key.upper()}_TOKEN"
    return _env_or_dotenv(env_key, dotenv_path)


def normalize_cluster_key(auth_cluster: str) -> str:
    """Convert an auth cluster slug to the canonical CAPS key.

    Args:
        auth_cluster: Cluster slug from JWT (e.g. "apac2", "north-america").

    Returns:
        Canonical key like "APAC2", "US", etc.
    """
    slug = auth_cluster.lower().strip()
    return AUTH_CLUSTER_TO_KEY.get(slug, slug.upper())


def get_databricks_cluster(cluster_key: str) -> Optional[DatabricksCluster]:
    """Resolve Databricks credentials for an Intouch cluster.

    Args:
        cluster_key: Intouch cluster identifier — can be an auth slug
                     (e.g. "apac2", "north-america") or a canonical key
                     (e.g. "APAC2", "US"). Handled case-insensitively.

    Returns:
        DatabricksCluster with instance URL + token, or None if not configured.
    """
    key = normalize_cluster_key(cluster_key)
    instance = CLUSTER_DATABRICKS_MAP.get(key)
    if not instance:
        return None

    token = _resolve_databricks_token(key)
    if not token:
        logger.warning(f"No Databricks token for cluster {key} (set DATABRICKS_{key}_TOKEN)")
        return None

    return DatabricksCluster(key=key, instance=instance, token=token)


def get_all_configured_clusters() -> list[dict]:
    """Return all clusters that have both a Databricks mapping and a token configured.

    Used by the /clusters endpoint to show which clusters are available.
    """
    result = []
    for key in CLUSTER_DATABRICKS_MAP:
        token = _resolve_databricks_token(key)
        if token:
            result.append({
                "key": key,
                "instance": CLUSTER_DATABRICKS_MAP[key],
            })
    return result


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

    # Confluence Cloud
    confluence_url: Optional[str] = None
    confluence_email: Optional[str] = None
    confluence_api_token: Optional[str] = None

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

    # Databricks pipeline settings
    filter_mandatory_pct: float = 0.50
    filter_table_default_pct: float = 0.30
    filter_common_pct: float = 0.10
    max_enum_distinct: int = 30
    top_tables_schema: int = 25
    top_join_pairs: int = 15
    top_clusters: int = 15
    top_glossary_cols: int = 20
    top_filter_tables: int = 20
    top_filters_per_table: int = 5
    dialect: str = "spark"

    # Sanitize/Refactoring
    sanitize_max_output_tokens: int = 64000
    chat_max_output_tokens: int = 8192
    chat_history_window: int = 20
    max_tool_rounds: int = 5

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    @model_validator(mode="after")
    def _resolve_empty_env_vars(self) -> "Settings":
        """Fix empty env vars overriding .env file values."""
        optional_keys = [
            "anthropic_api_key",
            "openai_api_key",
            "confluence_url",
            "confluence_email",
            "confluence_api_token",
        ]
        for key in optional_keys:
            if not getattr(self, key):
                val = _env_or_dotenv(key.upper())
                if val:
                    object.__setattr__(self, key, val)
        return self


settings = Settings()
