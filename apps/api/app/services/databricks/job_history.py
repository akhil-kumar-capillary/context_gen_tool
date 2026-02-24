"""
Async job association and run history.

Ported from reference: services/job_history.py
Key changes: ThreadPoolExecutor → asyncio.gather() + Semaphore.
"""

import asyncio
import logging
from typing import Optional, Callable, Awaitable

from app.services.databricks.client import DatabricksClient
from app.services.databricks.sql_extractor import epoch_ms_to_str

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


def build_job_notebook_map(jobs: list[dict]) -> dict[str, list[dict]]:
    """
    Build mapping: notebook_path → [{job_id, job_name, has_schedule}].
    Handles both single notebook_task and multi-task jobs.
    Pure function — no I/O.
    """
    nb_to_jobs: dict[str, list[dict]] = {}

    for job in jobs:
        job_id = job.get("job_id")
        job_name = job.get("settings", {}).get("name", "unnamed")
        has_schedule = bool(job.get("settings", {}).get("schedule"))

        # Single task job
        nb_task = job.get("settings", {}).get("notebook_task")
        if nb_task:
            path = nb_task.get("notebook_path")
            if path:
                nb_to_jobs.setdefault(path, []).append(
                    {"job_id": job_id, "job_name": job_name, "has_schedule": has_schedule}
                )

        # Multi-task job
        for task in job.get("settings", {}).get("tasks", []):
            nb_task = task.get("notebook_task")
            if nb_task:
                path = nb_task.get("notebook_path")
                if path:
                    nb_to_jobs.setdefault(path, []).append(
                        {"job_id": job_id, "job_name": job_name, "has_schedule": has_schedule}
                    )

    return nb_to_jobs


async def fetch_run_history_for_notebooks(
    client: DatabricksClient,
    nb_to_jobs: dict[str, list[dict]],
    max_workers: int = 8,
    max_runs: int = 25,
    on_progress: Optional[ProgressCallback] = None,
) -> dict[str, list[dict]]:
    """
    Fetch run history for all notebooks that have jobs.
    De-duplicates API calls by unique job_id.
    Returns: dict of {notebook_path: [run_records]}
    """
    # Collect unique job_ids and which notebooks they serve
    job_to_notebooks: dict[int, set[str]] = {}
    for nb_path, entries in nb_to_jobs.items():
        for entry in entries:
            jid = entry["job_id"]
            job_to_notebooks.setdefault(jid, set()).add(nb_path)

    unique_job_ids = list(job_to_notebooks.keys())
    total = len(unique_job_ids)
    if total == 0:
        return {}

    # Parallel fetch
    job_runs_map: dict[int, list] = {}
    completed = 0
    semaphore = asyncio.Semaphore(max_workers)
    log_interval = max(1, total // 20)
    lock = asyncio.Lock()

    async def fetch_one(jid: int):
        nonlocal completed
        async with semaphore:
            try:
                runs = await client.get_job_runs(jid, max_runs)
            except Exception:
                runs = []

        async with lock:
            job_runs_map[jid] = runs
            completed += 1
            if (completed % log_interval == 0 or completed == total) and on_progress:
                pct = (completed / total) * 100
                await on_progress("jobs", completed, total, f"{pct:.0f}%")

    await asyncio.gather(*(fetch_one(jid) for jid in unique_job_ids))

    # Map runs back to notebook paths
    nb_runs: dict[str, list[dict]] = {}
    for jid, runs in job_runs_map.items():
        for nb_path in job_to_notebooks.get(jid, set()):
            for run in runs:
                start_ms = run.get("start_time")
                state = run.get("state", {}).get("result_state")
                trigger = run.get("trigger")
                nb_runs.setdefault(nb_path, []).append(
                    {
                        "start_time_str": epoch_ms_to_str(start_ms) if start_ms else None,
                        "start_time_ms": start_ms,
                        "state": state,
                        "trigger": trigger,
                    }
                )

    return nb_runs


def compute_notebook_job_info(
    notebook_path: str,
    nb_to_jobs: dict[str, list[dict]],
    nb_runs: dict[str, list[dict]],
) -> dict:
    """Compute aggregated job columns for a single notebook. Pure function."""
    job_entries = nb_to_jobs.get(notebook_path)

    if not job_entries:
        return {
            "Is_Attached_to_Jobs": "No",
            "JobID": None,
            "JobName": None,
            "Cont_Success_Run_Count": None,
            "Earliest_Run_Date": None,
            "Trigger_Type": None,
        }

    # Deduplicate job_ids
    seen_ids: set[int] = set()
    unique_ids: list[str] = []
    unique_names: list[str] = []
    any_periodic = False

    for e in job_entries:
        if e["job_id"] not in seen_ids:
            seen_ids.add(e["job_id"])
            unique_ids.append(str(e["job_id"]))
            unique_names.append(e["job_name"])
        if e["has_schedule"]:
            any_periodic = True

    # Get runs for this notebook
    runs = nb_runs.get(notebook_path, [])

    # Earliest_Run_Date
    start_times = [r["start_time_str"] for r in runs if r.get("start_time_str")]
    earliest = min(start_times) if start_times else None

    # Cont_Success_Run_Count: sort newest first, count consecutive SUCCESS
    sorted_runs = sorted(
        runs, key=lambda r: r.get("start_time_ms") or 0, reverse=True
    )
    streak = 0
    for r in sorted_runs:
        if r.get("state") == "SUCCESS":
            streak += 1
        else:
            break

    # Trigger_Type
    run_triggers = set(r.get("trigger") for r in runs if r.get("trigger"))
    if any_periodic or "PERIODIC" in run_triggers:
        trigger_type = "PERIODIC"
    elif run_triggers:
        trigger_type = "ONE_TIME"
    else:
        trigger_type = None

    return {
        "Is_Attached_to_Jobs": "Yes",
        "JobID": ", ".join(unique_ids),
        "JobName": ", ".join(unique_names),
        "Cont_Success_Run_Count": streak,
        "Earliest_Run_Date": earliest,
        "Trigger_Type": trigger_type,
    }
