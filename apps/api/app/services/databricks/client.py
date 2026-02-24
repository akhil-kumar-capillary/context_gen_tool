"""
Async Databricks REST API client with retry logic.

Ported from reference: services/databricks_client.py
Key changes: httpx.Client → httpx.AsyncClient, all methods async,
tenacity retry with async support.
"""

import base64
import logging
from typing import Optional

import httpx
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class APIError(Exception):
    """Raised on retryable API errors (429, 500, 502, 503, 504)."""
    pass


class APIFatalError(Exception):
    """Raised on non-retryable API errors (401, 403)."""
    pass


class DatabricksClient:
    """Async Databricks REST API client."""

    def __init__(self, instance_url: str, access_token: str):
        self.base_url = instance_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        self.client = httpx.AsyncClient(
            headers=self.headers,
            timeout=60.0,
            follow_redirects=True,
        )
        self.failures: list[dict] = []
        logger.info(f"DatabricksClient initialized for {self.base_url}")

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    @retry(
        retry=retry_if_exception_type(APIError),
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=2, min=2, max=30),
        reraise=True,
    )
    async def _api_get(self, endpoint: str, params: dict) -> dict:
        url = f"{self.base_url}{endpoint}"
        response = await self.client.get(url, params=params)

        if response.status_code == 200:
            return response.json()

        if response.status_code in (429, 500, 502, 503, 504):
            raise APIError(f"HTTP {response.status_code} for {url}")

        if response.status_code in (401, 403):
            raise APIFatalError(
                f"Auth error {response.status_code}: check access token"
            )

        # Non-retryable error
        body_preview = response.text[:200] if response.text else "(empty)"
        logger.warning(
            f"HTTP {response.status_code} for {url} params={params}: {body_preview}"
        )
        raise Exception(f"HTTP {response.status_code} for {url}: {body_preview}")

    async def test_connection(self) -> dict:
        """Test connection by listing root workspace path."""
        try:
            await self._api_get("/api/2.0/workspace/list", {"path": "/Workspace"})
            return {"success": True, "message": "Connection successful"}
        except APIFatalError as e:
            return {"success": False, "message": str(e)}
        except Exception as e:
            return {"success": False, "message": f"Connection failed: {str(e)}"}

    async def list_workspace_path(self, path: str) -> list:
        """List objects in a workspace path."""
        try:
            data = await self._api_get("/api/2.0/workspace/list", {"path": path})
            objects = data.get("objects", [])
            logger.debug(f"Listed {path}: {len(objects)} objects")
            return objects
        except APIFatalError:
            raise
        except Exception as e:
            self.failures.append(
                {"path": path, "operation": "list", "error": str(e)}
            )
            logger.warning(f"Failed to list {path}: {e}")
            return []

    async def export_notebook(
        self, path: str
    ) -> tuple[Optional[str], Optional[str]]:
        """Export notebook content as SOURCE format. Returns (content, file_type)."""
        try:
            data = await self._api_get(
                "/api/2.0/workspace/export", {"path": path, "format": "SOURCE"}
            )
            content = data.get("content")
            file_type = data.get("file_type", "python")
            if content:
                return base64.b64decode(content).decode("utf-8"), file_type
            return None, None
        except APIFatalError:
            raise
        except Exception as e:
            self.failures.append(
                {"path": path, "operation": "export", "error": str(e)}
            )
            logger.warning(f"Failed to export {path}: {e}")
            return None, None

    async def get_notebook_metadata(self, path: str) -> dict:
        """Get metadata for a workspace object."""
        try:
            return await self._api_get(
                "/api/2.0/workspace/get-status", {"path": path}
            )
        except APIFatalError:
            raise
        except Exception as e:
            self.failures.append(
                {"path": path, "operation": "get-status", "error": str(e)}
            )
            logger.warning(f"Failed to get metadata for {path}: {e}")
            return {}

    async def get_all_jobs(self) -> list:
        """Fetch all jobs with pagination."""
        all_jobs: list = []
        has_more = True
        offset = 0
        limit = 25

        while has_more:
            try:
                data = await self._api_get(
                    "/api/2.1/jobs/list",
                    {"limit": limit, "offset": offset, "expand_tasks": "true"},
                )
                jobs = data.get("jobs", [])
                all_jobs.extend(jobs)
                has_more = data.get("has_more", False)
                offset += limit
            except Exception as e:
                self.failures.append(
                    {
                        "path": f"jobs/offset={offset}",
                        "operation": "list_jobs",
                        "error": str(e),
                    }
                )
                logger.warning(f"Failed to list jobs at offset={offset}: {e}")
                break

        logger.info(f"Fetched {len(all_jobs)} jobs total")
        return all_jobs

    async def get_job_runs(self, job_id: int, limit: int = 25) -> list:
        """Fetch recent runs for a specific job."""
        try:
            data = await self._api_get(
                "/api/2.1/jobs/runs/list", {"job_id": job_id, "limit": limit}
            )
            return data.get("runs", [])
        except Exception:
            return []
