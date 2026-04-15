"""
Async analysis pipeline orchestrator.

New file (no direct reference equivalent) — ties together:
  load SQLs → dedup → fingerprint → counters → clusters → classify → save.

Supports two SQL source modes:
  - "extraction": SQLs from extracted_sqls table (existing flow)
  - "table": SQLs from a Databricks SQL table via sql_query_client
"""

import logging
import re as re_module
import uuid
from typing import Optional, Callable, Awaitable

from app.services.databricks.storage import StorageService
from app.services.databricks.fingerprint_engine import (
    ingest_and_dedup,
    extract_all_fingerprints,
)
from app.services.databricks.frequency_counters import (
    build_counters,
    counters_to_serializable,
)
from app.services.databricks.cluster_builder import build_clusters, classify_filters

logger = logging.getLogger(__name__)

# Type alias for progress callback
ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


async def _run_analysis_pipeline(
    sql_records: list[dict],
    analysis_id: str,
    org_id: str,
    user_id: int,
    storage: StorageService,
    on_progress: Optional[ProgressCallback] = None,
    run_id: str | None = None,
    source_type: str = "extraction",
    source_table_name: str | None = None,
) -> dict:
    """Shared analysis pipeline: dedup → fingerprint → counters → clusters → save.

    Called by both run_analysis() and run_analysis_from_table().
    """
    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    # --- Step 1: Ingest & dedup ---
    corpus = await ingest_and_dedup(sql_records, on_progress=on_progress)

    if not corpus:
        await emit("error", 0, 0, "No SELECT/WITH queries after deduplication")
        return {
            "analysis_id": analysis_id,
            "error": "No SELECT/WITH queries after deduplication",
        }

    # --- Step 2: Extract fingerprints ---
    await emit(
        "fingerprint", 0, len(corpus),
        f"Fingerprinting {len(corpus)} unique queries...",
    )
    fingerprints, failures = await extract_all_fingerprints(
        corpus, on_progress=on_progress
    )

    if not fingerprints:
        await emit("error", 0, 0, "No fingerprints could be extracted")
        return {
            "analysis_id": analysis_id,
            "error": "No fingerprints could be extracted",
            "failure_count": len(failures),
        }

    # --- Step 3: Build counters ---
    await emit("counters", 0, 0, "Building frequency counters...")
    counters, literal_vals, alias_conv, total_weight = build_counters(fingerprints)
    counters_json = counters_to_serializable(counters, literal_vals, alias_conv)

    # --- Step 4: Build clusters ---
    await emit("clusters", 0, 0, "Building query clusters...")
    clusters = build_clusters(fingerprints)

    # --- Step 5: Classify filters ---
    await emit("filters", 0, 0, "Classifying WHERE conditions...")
    classified_filters = classify_filters(counters["where"], fingerprints, total_weight)

    # --- Step 6: Build fingerprints summary (top 20) ---
    fps_sorted = sorted(fingerprints, key=lambda f: f.frequency, reverse=True)
    fps_summary = [
        {
            "id": fp.id,
            "tables": fp.tables,
            "frequency": fp.frequency,
            "functions": fp.functions[:5],
            "join_count": len(fp.join_graph),
            "where_count": len(fp.where_conditions),
        }
        for fp in fps_sorted[:20]
    ]

    # --- Step 7: Persist to database ---
    await emit("saving", 0, 0, "Saving analysis results...")

    analysis_data = {
        "org_id": org_id,
        "counters": counters_json,
        "clusters": clusters,
        "classified_filters": classified_filters,
        "fingerprints_summary": fps_summary,
        "literal_vals": {
            col: [[v, n] for v, n in vc.items()]
            for col, vc in literal_vals.items()
        },
        "alias_conv": {
            t: [[a, n] for a, n in ac.items()]
            for t, ac in alias_conv.items()
        },
        "total_weight": total_weight,
    }

    version = await storage.save_analysis_run(
        analysis_id, run_id, user_id, analysis_data,
        source_type=source_type,
        source_table_name=source_table_name,
    )

    # Save individual fingerprints
    fp_dicts = [fp.to_dict() for fp in fingerprints]
    await storage.save_analysis_fingerprints(analysis_id, fp_dicts)

    # Link notebooks (only for extraction mode)
    if run_id:
        notebook_links = await _compute_notebook_links(sql_records, run_id, storage)
        if notebook_links:
            await storage.save_analysis_notebooks(analysis_id, notebook_links)

    await emit(
        "complete", 0, 0,
        f"Analysis complete: {len(fingerprints)} fingerprints, "
        f"{len(clusters)} clusters, version {version}",
    )

    return {
        "analysis_id": analysis_id,
        "run_id": run_id,
        "org_id": org_id,
        "source_type": source_type,
        "version": version,
        "fingerprint_count": len(fingerprints),
        "failure_count": len(failures),
        "cluster_count": len(clusters),
        "filter_count": len(classified_filters),
        "total_weight": total_weight,
    }


async def run_analysis(
    run_id: str,
    org_id: str,
    user_id: int,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """Run analysis pipeline from extracted SQLs (existing flow)."""
    analysis_id = str(uuid.uuid4())
    storage = StorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    try:
        await emit("loading", 0, 0, "Loading extracted SQLs...")
        sql_records = await storage.get_extracted_sqls(
            run_id, valid_only=True, org_id=org_id
        )

        if not sql_records:
            await emit("error", 0, 0, f"No valid SQLs found for org {org_id}")
            return {
                "analysis_id": analysis_id,
                "error": f"No valid SQLs found for org {org_id}",
            }

        await emit(
            "loading", len(sql_records), len(sql_records),
            f"Loaded {len(sql_records)} valid SQL records",
        )

        return await _run_analysis_pipeline(
            sql_records, analysis_id, org_id, user_id, storage,
            on_progress=on_progress, run_id=run_id,
            source_type="extraction",
        )

    except Exception as e:
        logger.exception(f"Analysis failed: {e}")
        await emit("error", 0, 0, f"Analysis failed: {str(e)}")
        raise


async def run_analysis_from_table(
    org_id: str,
    user_id: int,
    cluster_key: str,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """Run analysis pipeline from a Databricks SQL table.

    Queries the table configured in platform variable databricks/{cluster}_sql_table,
    filtered by org_id. Then feeds results through the same fingerprint/cluster pipeline.
    """
    from app.services.databricks.sql_query_client import (
        create_sql_client_for_cluster, get_platform_var,
    )

    analysis_id = str(uuid.uuid4())
    storage = StorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    try:
        # Step 1: Resolve table name from platform variable
        await emit("loading", 0, 0, "Resolving SQL table configuration...")
        table_var_key = f"databricks/{cluster_key.lower()}_sql_table"
        table_name = await get_platform_var(table_var_key)
        if not table_name:
            raise ValueError(
                f"Platform variable '{table_var_key}' not configured. "
                f"Set it in Admin → Platform Variables."
            )

        # Validate table name format (defense-in-depth — table names can't be parameterized)
        if not re_module.match(r'^[a-zA-Z0-9_\.]+$', table_name):
            raise ValueError(f"Invalid table name format: '{table_name}'")

        # Step 2: Query Databricks SQL table (org_id is parameterized, not interpolated)
        await emit("loading", 0, 0, f"Fetching SQLs from {table_name} for org {org_id}...")
        async with await create_sql_client_for_cluster(cluster_key) as client:
            query = f"SELECT sql FROM {table_name} WHERE org_id = %(org_id)s"
            rows = await client.query_all(query, {"org_id": str(org_id)})

        if not rows:
            await emit("error", 0, 0, f"No SQLs found in table for org {org_id}")
            return {
                "analysis_id": analysis_id,
                "error": f"No SQLs found for org {org_id} in {table_name}",
            }

        # Step 3: Convert to format expected by ingest_and_dedup
        sql_records = [
            {"cleaned_sql": row.get("sql") or row.get("SQL", ""), "is_valid": True}
            for row in rows
            if row.get("sql") or row.get("SQL")
        ]

        await emit(
            "loading", len(sql_records), len(sql_records),
            f"Loaded {len(sql_records)} SQLs from Databricks table",
        )

        return await _run_analysis_pipeline(
            sql_records, analysis_id, org_id, user_id, storage,
            on_progress=on_progress, run_id=None,
            source_type="table", source_table_name=table_name,
        )

    except Exception as e:
        logger.exception(f"Table-based analysis failed: {e}")
        await emit("error", 0, 0, f"Analysis failed: {str(e)}")
        raise


async def _compute_notebook_links(
    sql_records: list[dict], run_id: str, storage: StorageService
) -> list[dict]:
    """Compute notebook → SQL count linkage from SQL records.

    Resolves notebook_metadata IDs by matching notebook_path from the
    extracted SQL records against the notebook_metadata table for the run.
    """
    nb_counts: dict[str, int] = {}
    for r in sql_records:
        path = r.get("notebook_path") or r.get("NotebookPath", "")
        if path:
            nb_counts[path] = nb_counts.get(path, 0) + 1

    if not nb_counts:
        return []

    nb_id_map = await storage.get_notebook_id_map(run_id)

    links = []
    for path, count in nb_counts.items():
        if path in nb_id_map:
            links.append({
                "notebook_id": nb_id_map[path],
                "sql_count": count,
            })

    return links
