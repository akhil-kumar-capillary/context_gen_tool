"""Databricks SQL query client for table-mode analysis.

Uses databricks-sql-connector to execute SQL against all-purpose clusters.
Same pattern as cap-ai-readiness DatabricksClient.
"""

import asyncio
import logging
import re
from typing import Optional

from databricks import sql as databricks_sql

logger = logging.getLogger(__name__)

MAX_ROWS = 100_000
SOCKET_TIMEOUT = 300  # 5 minutes


class DatabricksSQLClient:
    """Async wrapper around databricks-sql-connector (sync library).

    Executes queries via asyncio.to_thread() to avoid blocking the event loop.
    """

    def __init__(self, server_hostname: str, cluster_id: str, access_token: str):
        if not re.match(r'^[a-zA-Z0-9\-]+$', cluster_id):
            raise ValueError(f"Invalid cluster ID format: {cluster_id}")
        self._hostname = server_hostname
        self._cluster_id = cluster_id
        self._token = access_token
        self._http_path = f"sql/protocolv1/o/0/{cluster_id}"
        self._connection = None

    def _connect(self):
        """Synchronous connect — runs in thread pool."""
        if self._connection is None:
            self._connection = databricks_sql.connect(
                server_hostname=self._hostname,
                http_path=self._http_path,
                access_token=self._token,
                _socket_timeout=SOCKET_TIMEOUT,
            )
        return self._connection

    def _query_sync(self, sql_query: str, parameters: dict | None = None) -> list[dict]:
        """Execute query synchronously, return list of dicts.

        Only SELECT/WITH queries are allowed. Enforces a hard row limit.

        Args:
            sql_query: SQL string. Use %(name)s for parameterized values.
            parameters: Dict of parameter values (e.g. {"org_id": "123"}).
        """
        # Defense-in-depth: only allow read queries
        stripped = sql_query.strip().upper()
        if not (stripped.startswith("SELECT") or stripped.startswith("WITH")):
            raise ValueError("Only SELECT and WITH queries are allowed")

        conn = self._connect()
        cursor = conn.cursor(arraysize=10000)
        try:
            cursor.execute(sql_query, parameters=parameters)
            if cursor.description is None:
                return []
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchmany(MAX_ROWS + 1)
            if len(rows) > MAX_ROWS:
                raise ValueError(
                    f"Query returned more than {MAX_ROWS:,} rows. "
                    f"Add a LIMIT clause or narrow the filter."
                )
            return [dict(zip(columns, row)) for row in rows]
        finally:
            cursor.close()

    def _close_sync(self):
        """Close connection synchronously."""
        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing Databricks connection: {e}")
            self._connection = None

    async def query_all(self, sql_query: str, parameters: dict | None = None) -> list[dict]:
        """Execute query asynchronously via thread pool."""
        return await asyncio.to_thread(self._query_sync, sql_query, parameters)

    async def close(self):
        """Close connection asynchronously."""
        await asyncio.to_thread(self._close_sync)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


async def get_platform_var(key: str) -> Optional[str]:
    """Read a platform variable value directly from the database."""
    from app.database import async_session
    from app.models.platform_variable import PlatformVariable
    from sqlalchemy import select

    async with async_session() as db:
        result = await db.execute(
            select(PlatformVariable.value, PlatformVariable.default_value)
            .where(PlatformVariable.key == key)
        )
        row = result.one_or_none()
        if row:
            return row[0] if row[0] is not None else row[1]
        return None


async def create_sql_client_for_cluster(cluster_key: str) -> DatabricksSQLClient:
    """Create a SQL client for the given cluster using config + env vars.

    Args:
        cluster_key: Canonical cluster key (e.g. "APAC2") or auth slug (e.g. "apac2").

    Returns:
        Configured DatabricksSQLClient ready for queries.

    Raises:
        ValueError: If cluster config or cluster_id is missing.
    """
    from app.config import get_databricks_cluster

    db_cluster = get_databricks_cluster(cluster_key)
    if not db_cluster:
        raise ValueError(f"No Databricks config for cluster {cluster_key}")

    if not db_cluster.cluster_id:
        raise ValueError(
            f"No cluster ID for {cluster_key}. "
            f"Set DATABRICKS_{db_cluster.key}_CLUSTER_ID env var."
        )

    hostname = db_cluster.instance.replace("https://", "").replace("http://", "")

    return DatabricksSQLClient(
        server_hostname=hostname,
        cluster_id=db_cluster.cluster_id,
        access_token=db_cluster.token,
    )
