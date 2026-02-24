"""
Async extraction pipeline orchestrator.

Ported from reference: services/extraction_orchestrator.py
Key changes: All I/O is async, uses DatabricksClient (async), storage via StorageService.

Pipeline: discovery → job info → freshness filter → export → cell extraction → save.
"""

import logging
import re
import uuid
from datetime import datetime
from typing import Optional, Callable, Awaitable

from app.services.databricks.client import DatabricksClient
from app.services.databricks.notebook_discovery import (
    find_all_notebooks,
    filter_notebooks_by_modified_date,
)
from app.services.databricks.notebook_export import export_notebooks_parallel
from app.services.databricks.job_history import (
    build_job_notebook_map,
    fetch_run_history_for_notebooks,
    compute_notebook_job_info,
)
from app.services.databricks.sql_extractor import (
    extract_user_from_path,
    extract_sql_from_cell,
    extract_notebook_default_org_id,
    get_org_id_for_sql,
    sha256_hash,
)
from app.services.databricks.storage import StorageService

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


async def run_extraction(
    *,
    run_id: Optional[str] = None,
    credentials: Optional[dict] = None,
    config: Optional[dict] = None,
    instance_url: Optional[str] = None,
    access_token: Optional[str] = None,
    user_id: int,
    root_path: str = "/Workspace/Users",
    notebook_limit: Optional[int] = None,
    modified_since: Optional[str] = None,
    max_workers: int = 8,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """
    Run the full extraction pipeline (async).

    Accepts either:
      - credentials dict {"instance", "token"} + config dict {"root_path", ...}
      - or individual kwargs (instance_url, access_token, root_path, ...)

    Args:
        run_id: Pre-generated run ID (optional, auto-generated if missing).
        credentials: {"instance": str, "token": str}.
        config: {"root_path": str, "modified_since": str|None, "max_workers": int, ...}.
        instance_url: Databricks workspace URL (alternative to credentials).
        access_token: Databricks access token (alternative to credentials).
        user_id: User running the extraction.
        root_path: Workspace path to scan.
        notebook_limit: Max notebooks to discover (None = unlimited).
        modified_since: ISO date string for freshness filter.
        max_workers: Concurrency limit for parallel API calls.
        on_progress: async callback(phase, completed, total, detail).

    Returns:
        dict with: run_id, sql_results, notebook_data, summary
    """
    # Resolve credentials
    if credentials:
        instance_url = credentials.get("instance", instance_url)
        access_token = credentials.get("token", access_token)
    if not instance_url or not access_token:
        raise ValueError("Databricks instance URL and access token are required")

    # Resolve config overrides
    if config:
        root_path = config.get("root_path", root_path)
        modified_since = config.get("modified_since", modified_since)
        max_workers = config.get("max_workers", max_workers)
        notebook_limit = config.get("notebook_limit", notebook_limit)

    run_id = run_id or str(uuid.uuid4())
    storage = StorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    # Create extraction run record
    await storage.create_extraction_run(
        run_id=run_id,
        user_id=user_id,
        databricks_instance=instance_url,
        root_path=root_path,
        modified_since=modified_since,
    )

    async with DatabricksClient(instance_url, access_token) as client:
        try:
            # --- Step 1: Discover notebooks + fetch metadata ---
            await emit("discovery", 0, 0, "Discovering notebooks...")
            all_notebooks = await find_all_notebooks(
                client,
                root_path,
                limit=notebook_limit,
                max_workers=max_workers,
                on_progress=on_progress,
            )

            if not all_notebooks:
                summary = _build_summary(0, 0, 0, 0, 0, 0, len(client.failures))
                await storage.complete_extraction_run(run_id, summary)
                if on_progress:
                    await on_progress({
                        "phase": "complete", "completed": 0, "total": 0,
                        "detail": "No notebooks found", "status": "done", **summary,
                    })
                return {
                    "run_id": run_id,
                    "sql_results": [],
                    "notebook_data": [],
                    "summary": summary,
                }

            # --- Step 2: Fetch job info ---
            await emit("jobs", 0, 0, "Fetching job associations...")
            all_jobs = await client.get_all_jobs()
            nb_to_jobs = build_job_notebook_map(all_jobs)

            # Fetch run history for notebooks with jobs
            all_paths = [nb["path"] for nb in all_notebooks]
            matched_paths = [p for p in all_paths if p in nb_to_jobs]

            if matched_paths:
                nb_runs = await fetch_run_history_for_notebooks(
                    client,
                    nb_to_jobs,
                    max_workers=max_workers,
                    max_runs=25,
                    on_progress=on_progress,
                )
            else:
                nb_runs = {}

            # --- Step 3: Apply freshness filter ---
            skipped_notebooks: list[dict] = []
            modified_since_epoch_ms: Optional[int] = None

            if modified_since:
                try:
                    dt = datetime.strptime(modified_since, "%Y-%m-%d")
                    modified_since_epoch_ms = int(dt.timestamp() * 1000)
                except ValueError:
                    pass

            if modified_since_epoch_ms:
                notebooks, skipped_notebooks = filter_notebooks_by_modified_date(
                    all_notebooks, modified_since_epoch_ms
                )
                if not notebooks:
                    notebook_data = _build_metadata_for_notebooks(
                        all_notebooks, nb_to_jobs, nb_runs, status="Skipped_Stale"
                    )
                    summary = _build_summary(
                        len(all_notebooks), 0, len(all_notebooks), 0, 0, 0,
                        len(client.failures),
                    )
                    await storage.save_notebook_metadata(run_id, notebook_data)
                    await storage.complete_extraction_run(run_id, summary)
                    if on_progress:
                        await on_progress({
                            "phase": "complete", "completed": 0, "total": 0,
                            "detail": "No notebooks pass freshness filter", "status": "done",
                            **summary,
                        })
                    return {
                        "run_id": run_id,
                        "sql_results": [],
                        "notebook_data": notebook_data,
                        "summary": summary,
                    }
            else:
                notebooks = all_notebooks

            # --- Step 4: Parallel export ---
            await emit("export", 0, len(notebooks), "Exporting notebooks...")
            exports = await export_notebooks_parallel(
                client,
                notebooks,
                max_workers=max_workers,
                on_progress=on_progress,
            )

            # --- Step 5: Process each notebook — extract SQL from cells ---
            sql_results: list[dict] = []
            notebook_data: list[dict] = []
            total_nb = len(notebooks)
            log_interval = max(1, total_nb // 20)

            for nb_idx, nb in enumerate(notebooks, 1):
                notebook_path = nb["path"]
                content, file_type = exports.get(notebook_path, (None, None))
                user = extract_user_from_path(notebook_path)
                notebook_name = notebook_path.split("/")[-1]
                job_info = compute_notebook_job_info(
                    notebook_path, nb_to_jobs, nb_runs
                )

                notebook_data.append(
                    {
                        "NotebookPath": notebook_path,
                        "NotebookName": notebook_name,
                        "User": user,
                        "ObjectID": nb["object_id"],
                        "Language": nb["language"],
                        "CreatedAt": nb["created_at_str"],
                        "ModifiedAt": nb["modified_at_str"],
                        "HasContent": content is not None,
                        "FileType": file_type,
                        "Status": "Processed",
                        "Is_Attached_to_Jobs": job_info["Is_Attached_to_Jobs"],
                        "JobID": job_info["JobID"],
                        "JobName": job_info["JobName"],
                        "Cont_Success_Run_Count": job_info["Cont_Success_Run_Count"],
                        "Earliest_Run_Date": job_info["Earliest_Run_Date"],
                        "Trigger_Type": job_info["Trigger_Type"],
                        "ExtractedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

                if not content:
                    continue

                notebook_default_org = extract_notebook_default_org_id(content)

                # Split into cells
                if file_type and file_type.lower() == "sql":
                    cells = re.split(r"-- COMMAND ----------", content)
                else:
                    cells = re.split(r"# COMMAND ----------", content)

                for idx, cell in enumerate(cells):
                    cell_content = cell.strip()
                    if not cell_content:
                        continue

                    cleaned_sql, is_valid = extract_sql_from_cell(
                        cell_content, file_type or "python"
                    )
                    org_id, org_source = get_org_id_for_sql(
                        cleaned_sql, notebook_default_org
                    )

                    sql_results.append(
                        {
                            "User": user,
                            "NotebookPath": notebook_path,
                            "NotebookName": notebook_name,
                            "ObjectID": nb["object_id"],
                            "Language": nb["language"],
                            "CreatedAt": nb["created_at_str"],
                            "ModifiedAt": nb["modified_at_str"],
                            "CellNumber": idx + 1,
                            "FileType": file_type,
                            "CleanedSQL": cleaned_sql,
                            "SQLHash": sha256_hash(cleaned_sql),
                            "IsValidSQL": is_valid,
                            "OrgID": org_id,
                            "OrgID_Source": org_source,
                            "OriginalSnippet": cell_content[:4000],
                            "ExtractedAt": datetime.now().strftime(
                                "%Y-%m-%d %H:%M:%S"
                            ),
                        }
                    )

                if nb_idx % log_interval == 0 or nb_idx == total_nb:
                    pct = (nb_idx / total_nb) * 100
                    await emit(
                        "extraction",
                        nb_idx,
                        total_nb,
                        f"{len(sql_results)} cells extracted",
                    )

            # --- Step 6: Add skipped notebooks to metadata ---
            for nb in skipped_notebooks:
                job_info = compute_notebook_job_info(
                    nb["path"], nb_to_jobs, nb_runs
                )
                notebook_data.append(
                    {
                        "NotebookPath": nb["path"],
                        "NotebookName": nb["path"].split("/")[-1],
                        "User": extract_user_from_path(nb["path"]),
                        "ObjectID": nb["object_id"],
                        "Language": nb["language"],
                        "CreatedAt": nb["created_at_str"],
                        "ModifiedAt": nb["modified_at_str"],
                        "HasContent": False,
                        "FileType": None,
                        "Status": "Skipped_Stale",
                        "Is_Attached_to_Jobs": job_info["Is_Attached_to_Jobs"],
                        "JobID": job_info["JobID"],
                        "JobName": job_info["JobName"],
                        "Cont_Success_Run_Count": job_info["Cont_Success_Run_Count"],
                        "Earliest_Run_Date": job_info["Earliest_Run_Date"],
                        "Trigger_Type": job_info["Trigger_Type"],
                        "ExtractedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
                )

            # --- Step 7: Compute summary + persist ---
            valid_sqls = [r for r in sql_results if r["IsValidSQL"]]
            unique_hashes = len(
                set(r["SQLHash"] for r in valid_sqls if r["SQLHash"])
            )

            summary = _build_summary(
                total_notebooks=len(all_notebooks),
                processed_notebooks=len(notebooks),
                skipped_notebooks=len(skipped_notebooks),
                total_cells=len(sql_results),
                valid_sqls=len(valid_sqls),
                unique_hashes=unique_hashes,
                api_failures=len(client.failures),
            )

            # Persist to database
            await storage.save_extracted_sqls(run_id, sql_results)
            await storage.save_notebook_metadata(run_id, notebook_data)
            await storage.complete_extraction_run(run_id, summary)

            # Emit complete with summary stats so the frontend can display them
            if on_progress:
                await on_progress({
                    "phase": "complete",
                    "completed": len(notebooks),
                    "total": len(all_notebooks),
                    "detail": "Extraction complete",
                    "status": "done",
                    **summary,
                })

            return {
                "run_id": run_id,
                "sql_results": sql_results,
                "notebook_data": notebook_data,
                "summary": summary,
            }

        except Exception as e:
            logger.exception(f"Extraction failed: {e}")
            await storage.fail_extraction_run(run_id, str(e))
            await emit("error", 0, 0, f"Extraction failed: {str(e)}")
            raise


def _build_metadata_for_notebooks(
    notebooks: list[dict],
    nb_to_jobs: dict,
    nb_runs: dict,
    status: str = "Processed",
) -> list[dict]:
    """Build metadata records for a list of notebooks."""
    data = []
    for nb in notebooks:
        job_info = compute_notebook_job_info(nb["path"], nb_to_jobs, nb_runs)
        data.append(
            {
                "NotebookPath": nb["path"],
                "NotebookName": nb["path"].split("/")[-1],
                "User": extract_user_from_path(nb["path"]),
                "ObjectID": nb["object_id"],
                "Language": nb["language"],
                "CreatedAt": nb["created_at_str"],
                "ModifiedAt": nb["modified_at_str"],
                "HasContent": False,
                "FileType": None,
                "Status": status,
                "Is_Attached_to_Jobs": job_info["Is_Attached_to_Jobs"],
                "JobID": job_info["JobID"],
                "JobName": job_info["JobName"],
                "Cont_Success_Run_Count": job_info["Cont_Success_Run_Count"],
                "Earliest_Run_Date": job_info["Earliest_Run_Date"],
                "Trigger_Type": job_info["Trigger_Type"],
                "ExtractedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        )
    return data


def _build_summary(
    total_notebooks: int,
    processed_notebooks: int,
    skipped_notebooks: int,
    total_cells: int,
    valid_sqls: int,
    unique_hashes: int,
    api_failures: int,
) -> dict:
    return {
        "total_notebooks": total_notebooks,
        "processed_notebooks": processed_notebooks,
        "skipped_notebooks": skipped_notebooks,
        "total_cells": total_cells,
        "valid_sqls": valid_sqls,
        "unique_hashes": unique_hashes,
        "api_failures": api_failures,
    }
