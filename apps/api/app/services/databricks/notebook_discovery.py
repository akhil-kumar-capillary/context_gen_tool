"""
Async BFS notebook discovery + parallel metadata fetching.

Ported from reference: services/notebook_discovery.py
Key changes: ThreadPoolExecutor → asyncio.gather() + Semaphore,
sync client calls → async client calls.
"""

import asyncio
import logging
from collections import deque
from typing import Optional, Callable, Awaitable

from app.services.databricks.client import DatabricksClient
from app.services.databricks.sql_extractor import epoch_ms_to_str

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


async def find_all_notebooks(
    client: DatabricksClient,
    root_path: str,
    limit: Optional[int] = None,
    max_workers: int = 8,
    on_progress: Optional[ProgressCallback] = None,
) -> list[dict]:
    """
    Recursively discover notebooks using BFS.
    Fetches metadata in parallel using asyncio.gather + Semaphore.

    Args:
        client: Async Databricks API client.
        root_path: Workspace path to start discovery from.
        limit: Maximum number of notebooks to discover.
        max_workers: Concurrency limit for parallel metadata fetching.
        on_progress: async callback(phase, completed, total, detail).
    """
    notebook_paths: list[str] = []
    queue: deque[str] = deque([root_path])
    dirs_scanned = 0

    logger.info(f"Discovering notebooks under: {root_path}")

    # Phase 1: BFS discovery (sequential — each dir listing depends on queue state)
    while queue:
        current_path = queue.popleft()
        items = await client.list_workspace_path(current_path)
        dirs_scanned += 1

        if items:
            logger.info(
                f"  [{dirs_scanned}] {current_path}: {len(items)} items "
                f"({len(notebook_paths)} notebooks found, {len(queue)} dirs queued)"
            )
        else:
            logger.warning(
                f"  [{dirs_scanned}] {current_path}: 0 items (empty or failed)"
            )

        # Report progress every 5 dirs
        if dirs_scanned % 5 == 0 and on_progress:
            failures = len(client.failures)
            detail = (
                f"{dirs_scanned} dirs scanned, {len(notebook_paths)} notebooks, "
                f"{len(queue)} queued"
            )
            if failures > 0:
                detail += f", {failures} failures"
            await on_progress("discovery", len(notebook_paths), 0, detail)

        for item in items:
            item_type = item.get("object_type")
            item_path = item.get("path")

            if item_type == "NOTEBOOK":
                notebook_paths.append(item_path)
                if limit and len(notebook_paths) >= limit:
                    logger.info(f"Reached notebook limit: {limit}")
                    break
            elif item_type in ("DIRECTORY", "FOLDER", "REPO"):
                queue.append(item_path)

        if limit and len(notebook_paths) >= limit:
            break

    failures = len(client.failures)
    logger.info(
        f"Discovery complete: {len(notebook_paths)} notebooks found, "
        f"{dirs_scanned} dirs scanned, {failures} API failures"
    )

    if on_progress:
        detail = f"Discovery complete — {dirs_scanned} dirs scanned"
        if failures > 0:
            detail += f", {failures} API failures"
        await on_progress(
            "discovery", len(notebook_paths), len(notebook_paths), detail
        )

    # Phase 2: Parallel metadata fetching
    total = len(notebook_paths)
    if total == 0:
        return []

    notebooks: list[dict] = [None] * total  # type: ignore[list-item]
    completed = 0
    semaphore = asyncio.Semaphore(max_workers)
    log_interval = max(1, total // 20)

    async def fetch_metadata(idx: int, path: str):
        nonlocal completed
        async with semaphore:
            try:
                meta = await client.get_notebook_metadata(path)
                notebooks[idx] = {
                    "path": path,
                    "object_id": str(meta.get("object_id")) if meta.get("object_id") is not None else None,
                    "language": meta.get("language"),
                    "created_at": meta.get("created_at"),
                    "modified_at": meta.get("modified_at"),
                    "created_at_str": epoch_ms_to_str(meta.get("created_at")),
                    "modified_at_str": epoch_ms_to_str(meta.get("modified_at")),
                }
            except Exception as e:
                client.failures.append(
                    {"path": path, "operation": "metadata", "error": str(e)}
                )
                notebooks[idx] = {
                    "path": path,
                    "object_id": None,
                    "language": None,
                    "created_at": None,
                    "modified_at": None,
                    "created_at_str": None,
                    "modified_at_str": None,
                }

            completed += 1
            if (completed % log_interval == 0 or completed == total) and on_progress:
                pct = (completed / total) * 100
                await on_progress("metadata", completed, total, f"{pct:.0f}%")

    await asyncio.gather(
        *(fetch_metadata(i, path) for i, path in enumerate(notebook_paths))
    )

    return [nb for nb in notebooks if nb is not None]


def filter_notebooks_by_modified_date(
    notebooks: list[dict], since_epoch_ms: int
) -> tuple[list[dict], list[dict]]:
    """
    Filter notebooks to only those modified on or after the threshold date.
    Notebooks with missing metadata (modified_at = None) are included by default.
    """
    valid: list[dict] = []
    skipped: list[dict] = []

    for nb in notebooks:
        modified_at = nb.get("modified_at")
        if modified_at is None:
            valid.append(nb)
        elif modified_at >= since_epoch_ms:
            valid.append(nb)
        else:
            skipped.append(nb)

    return valid, skipped
