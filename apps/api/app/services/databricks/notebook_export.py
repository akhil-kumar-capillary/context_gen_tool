"""
Async parallel notebook export.

Ported from reference: services/notebook_export.py
Key changes: ThreadPoolExecutor → asyncio.gather() + Semaphore.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from app.services.databricks.client import DatabricksClient

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


async def export_notebooks_parallel(
    client: DatabricksClient,
    notebooks: list[dict],
    max_workers: int = 8,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, tuple[Optional[str], Optional[str]]]:
    """
    Export notebook contents in parallel using asyncio.gather + Semaphore.

    Args:
        client: Async Databricks API client.
        notebooks: List of notebook dicts (must have "path" key).
        max_workers: Concurrency limit.
        on_progress: async callback(phase, completed, total, detail).

    Returns:
        dict of {path: (content, file_type)}
    """
    exports: dict[str, tuple[Optional[str], Optional[str]]] = {}
    total = len(notebooks)
    if total == 0:
        return exports

    completed = 0
    semaphore = asyncio.Semaphore(max_workers)
    log_interval = max(1, total // 20)
    lock = asyncio.Lock()

    async def export_one(nb: dict):
        nonlocal completed
        path = nb["path"]
        async with semaphore:
            try:
                content, file_type = await client.export_notebook(path)
            except Exception as e:
                client.failures.append(
                    {"path": path, "operation": "export_parallel", "error": str(e)}
                )
                content, file_type = None, None

        async with lock:
            exports[path] = (content, file_type)
            completed += 1
            if (completed % log_interval == 0 or completed == total) and on_progress:
                pct = (completed / total) * 100
                await on_progress("export", completed, total, f"{pct:.0f}%")

    await asyncio.gather(*(export_one(nb) for nb in notebooks))

    return exports
