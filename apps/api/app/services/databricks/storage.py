"""
Async storage service — PostgreSQL implementation via SQLAlchemy async ORM.

Ported from reference: services/storage_client.py
Key changes: sqlite3 → SQLAlchemy async, json.dumps() → native JSONB,
individual booleans → structural_flags JSONB, short-lived sessions.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select, func, delete, update, and_, exists, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.extraction import ExtractionRun, ExtractedSQL, NotebookMetadata
from app.models.analysis import AnalysisRun, AnalysisFingerprint, AnalysisNotebook
from app.models.context_doc import ContextDoc

logger = logging.getLogger(__name__)


def _utcnow():
    return datetime.now(timezone.utc)


class StorageService:
    """Async PostgreSQL storage for all Databricks pipeline data.

    Each method creates a short-lived async session from the pool.
    No long-lived connections are held open.
    """

    # ------------------------------------------------------------------
    # Extraction Runs
    # ------------------------------------------------------------------

    async def create_extraction_run(
        self,
        run_id: str,
        user_id: int,
        databricks_instance: str,
        root_path: str,
        modified_since: Optional[str] = None,
    ) -> str:
        # Parse modified_since string to datetime if provided
        modified_since_dt = None
        if modified_since:
            from datetime import datetime as _dt
            try:
                modified_since_dt = _dt.strptime(modified_since, "%Y-%m-%d")
            except ValueError:
                try:
                    modified_since_dt = _dt.fromisoformat(modified_since)
                except ValueError:
                    pass  # Leave as None if unparseable

        async with async_session() as db:
            run = ExtractionRun(
                id=uuid.UUID(run_id),
                user_id=user_id,
                databricks_instance=databricks_instance,
                root_path=root_path,
                modified_since=modified_since_dt,
                status="running",
                started_at=_utcnow(),
            )
            db.add(run)
            await db.commit()
        return run_id

    async def update_extraction_run(self, run_id: str, **kwargs):
        """Update any fields on an extraction run."""
        async with async_session() as db:
            stmt = (
                update(ExtractionRun)
                .where(ExtractionRun.id == uuid.UUID(run_id))
                .values(**kwargs)
            )
            await db.execute(stmt)
            await db.commit()

    async def complete_extraction_run(self, run_id: str, summary: dict):
        async with async_session() as db:
            stmt = (
                update(ExtractionRun)
                .where(ExtractionRun.id == uuid.UUID(run_id))
                .values(
                    total_notebooks=summary["total_notebooks"],
                    processed_notebooks=summary["processed_notebooks"],
                    skipped_notebooks=summary["skipped_notebooks"],
                    total_sqls_extracted=summary["total_cells"],
                    valid_sqls=summary["valid_sqls"],
                    unique_hashes=summary["unique_hashes"],
                    api_failures=summary["api_failures"],
                    status="completed",
                    completed_at=_utcnow(),
                )
            )
            await db.execute(stmt)
            await db.commit()

    async def fail_extraction_run(self, run_id: str, error: str):
        await self.update_extraction_run(
            run_id, status="failed", completed_at=_utcnow()
        )

    async def get_extraction_runs(self) -> list[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(ExtractionRun).order_by(ExtractionRun.started_at.desc())
            )
            runs = result.scalars().all()
            return [self._run_to_dict(r) for r in runs]

    async def get_extraction_run(self, run_id: str) -> Optional[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(ExtractionRun).where(
                    ExtractionRun.id == uuid.UUID(run_id)
                )
            )
            run = result.scalar_one_or_none()
            return self._run_to_dict(run) if run else None

    async def delete_extraction_run(self, run_id: str):
        """Delete an extraction run and all cascaded data.

        PostgreSQL ON DELETE CASCADE handles analysis_fingerprints,
        analysis_notebooks, extracted_sqls, and notebook_metadata.
        Context docs need manual deletion as they use source_run_id (not FK cascade).
        """
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            # Get analysis IDs for this run
            result = await db.execute(
                select(AnalysisRun.id).where(AnalysisRun.run_id == uid)
            )
            analysis_ids = [row[0] for row in result.all()]

            # Delete context docs linked to these analyses
            for aid in analysis_ids:
                await db.execute(
                    delete(ContextDoc).where(ContextDoc.source_run_id == aid)
                )

            # Delete analysis runs (cascades to fingerprints + notebooks)
            await db.execute(
                delete(AnalysisRun).where(AnalysisRun.run_id == uid)
            )

            # Delete extraction-level data (CASCADE handles these, but explicit for safety)
            await db.execute(
                delete(NotebookMetadata).where(NotebookMetadata.run_id == uid)
            )
            await db.execute(
                delete(ExtractedSQL).where(ExtractedSQL.run_id == uid)
            )

            # Delete the extraction run itself
            await db.execute(
                delete(ExtractionRun).where(ExtractionRun.id == uid)
            )
            await db.commit()

    def _run_to_dict(self, run: ExtractionRun) -> dict:
        return {
            "id": str(run.id),
            "user_id": run.user_id,
            "org_id": run.org_id,
            "databricks_instance": run.databricks_instance,
            "root_path": run.root_path,
            "modified_since": str(run.modified_since) if run.modified_since else None,
            "total_notebooks": run.total_notebooks,
            "processed_notebooks": run.processed_notebooks,
            "skipped_notebooks": run.skipped_notebooks,
            "total_sqls_extracted": run.total_sqls_extracted,
            "valid_sqls": run.valid_sqls,
            "unique_hashes": run.unique_hashes,
            "api_failures": run.api_failures,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }

    # ------------------------------------------------------------------
    # Extracted SQLs
    # ------------------------------------------------------------------

    async def save_extracted_sqls(self, run_id: str, sql_results: list[dict]):
        """Bulk insert extracted SQL records."""
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            objects = [
                ExtractedSQL(
                    run_id=uid,
                    org_id=r.get("OrgID"),
                    org_id_source=r.get("OrgID_Source"),
                    notebook_path=r["NotebookPath"],
                    notebook_name=r["NotebookName"],
                    user_name=r.get("User"),
                    object_id=r.get("ObjectID"),
                    language=r.get("Language"),
                    created_at=r.get("CreatedAt"),
                    modified_at=r.get("ModifiedAt"),
                    cell_number=r.get("CellNumber"),
                    file_type=r.get("FileType"),
                    cleaned_sql=r.get("CleanedSQL"),
                    sql_hash=r.get("SQLHash"),
                    is_valid=bool(r.get("IsValidSQL")),
                    original_snippet=r.get("OriginalSnippet"),
                    extracted_at=r.get("ExtractedAt"),
                )
                for r in sql_results
            ]
            db.add_all(objects)
            await db.commit()

    async def get_extracted_sqls(
        self,
        run_id: str,
        valid_only: bool = False,
        org_id: Optional[str] = None,
    ) -> list[dict]:
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            stmt = select(ExtractedSQL).where(ExtractedSQL.run_id == uid)
            if valid_only:
                stmt = stmt.where(ExtractedSQL.is_valid == True)  # noqa: E712
            if org_id:
                stmt = stmt.where(ExtractedSQL.org_id == org_id)
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [self._sql_to_dict(r) for r in rows]

    async def get_valid_sql_count(
        self, run_id: str, org_id: Optional[str] = None
    ) -> int:
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            stmt = (
                select(func.count())
                .select_from(ExtractedSQL)
                .where(
                    and_(ExtractedSQL.run_id == uid, ExtractedSQL.is_valid == True)  # noqa: E712
                )
            )
            if org_id:
                stmt = stmt.where(ExtractedSQL.org_id == org_id)
            result = await db.execute(stmt)
            return result.scalar() or 0

    async def get_distinct_org_ids(self, run_id: str) -> list[dict]:
        """Return distinct org_ids for a run with SQL counts."""
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            stmt = (
                select(
                    ExtractedSQL.org_id,
                    func.count().label("total_sqls"),
                    func.sum(
                        func.cast(ExtractedSQL.is_valid, type_=func.coalesce.type)
                    ).label("valid_sqls_raw"),
                )
                .where(
                    and_(
                        ExtractedSQL.run_id == uid,
                        ExtractedSQL.org_id.isnot(None),
                        ExtractedSQL.org_id != "",
                    )
                )
                .group_by(ExtractedSQL.org_id)
                .order_by(text("total_sqls DESC"))
            )
            # Use raw SQL for the SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) pattern
            stmt = text("""
                SELECT org_id,
                       COUNT(*) as total_sqls,
                       SUM(CASE WHEN is_valid THEN 1 ELSE 0 END) as valid_sqls
                FROM extracted_sqls
                WHERE run_id = :run_id AND org_id IS NOT NULL AND org_id != ''
                GROUP BY org_id
                ORDER BY valid_sqls DESC
            """)
            result = await db.execute(stmt, {"run_id": uid})
            return [
                {"org_id": row.org_id, "total_sqls": row.total_sqls, "valid_sqls": row.valid_sqls}
                for row in result.all()
            ]

    def _sql_to_dict(self, sql: ExtractedSQL) -> dict:
        return {
            "id": sql.id,
            "run_id": str(sql.run_id),
            "org_id": sql.org_id,
            "org_id_source": sql.org_id_source,
            "notebook_path": sql.notebook_path,
            "notebook_name": sql.notebook_name,
            "user_name": sql.user_name,
            "object_id": sql.object_id,
            "language": sql.language,
            "cell_number": sql.cell_number,
            "file_type": sql.file_type,
            "cleaned_sql": sql.cleaned_sql,
            "sql_hash": sql.sql_hash,
            "is_valid": sql.is_valid,
            "original_snippet": sql.original_snippet,
            "extracted_at": sql.extracted_at.isoformat() if sql.extracted_at else None,
        }

    # ------------------------------------------------------------------
    # Notebook Metadata
    # ------------------------------------------------------------------

    async def save_notebook_metadata(self, run_id: str, notebook_data: list[dict]):
        """Bulk insert notebook metadata records."""
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            objects = [
                NotebookMetadata(
                    run_id=uid,
                    notebook_path=r["NotebookPath"],
                    notebook_name=r.get("NotebookName"),
                    user_name=r.get("User"),
                    object_id=r.get("ObjectID"),
                    language=r.get("Language"),
                    created_at=r.get("CreatedAt"),
                    modified_at=r.get("ModifiedAt"),
                    has_content=bool(r.get("HasContent")),
                    file_type=r.get("FileType"),
                    status=r.get("Status", "Processed"),
                    is_attached_to_jobs=r.get("Is_Attached_to_Jobs", "No"),
                    job_id=r.get("JobID"),
                    job_name=r.get("JobName"),
                    cont_success_run_count=r.get("Cont_Success_Run_Count"),
                    earliest_run_date=r.get("Earliest_Run_Date"),
                    trigger_type=r.get("Trigger_Type"),
                    extracted_at=r.get("ExtractedAt"),
                )
                for r in notebook_data
            ]
            db.add_all(objects)
            await db.commit()

    async def get_notebook_metadata(
        self, run_id: str, org_id: Optional[str] = None
    ) -> list[dict]:
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            if org_id:
                # Only notebooks with at least one SQL matching this org_id
                subq = (
                    select(ExtractedSQL.notebook_path)
                    .where(
                        and_(
                            ExtractedSQL.run_id == uid,
                            ExtractedSQL.org_id == org_id,
                        )
                    )
                    .distinct()
                    .scalar_subquery()
                )
                stmt = select(NotebookMetadata).where(
                    and_(
                        NotebookMetadata.run_id == uid,
                        NotebookMetadata.notebook_path.in_(
                            select(ExtractedSQL.notebook_path)
                            .where(
                                and_(
                                    ExtractedSQL.run_id == uid,
                                    ExtractedSQL.org_id == org_id,
                                )
                            )
                            .distinct()
                        ),
                    )
                )
            else:
                stmt = select(NotebookMetadata).where(
                    NotebookMetadata.run_id == uid
                )
            result = await db.execute(stmt)
            rows = result.scalars().all()
            return [self._nb_to_dict(r) for r in rows]

    def _nb_to_dict(self, nb: NotebookMetadata) -> dict:
        return {
            "id": nb.id,
            "run_id": str(nb.run_id),
            "notebook_path": nb.notebook_path,
            "notebook_name": nb.notebook_name,
            "user_name": nb.user_name,
            "object_id": nb.object_id,
            "language": nb.language,
            "has_content": nb.has_content,
            "file_type": nb.file_type,
            "status": nb.status,
            "is_attached_to_jobs": nb.is_attached_to_jobs,
            "job_id": nb.job_id,
            "job_name": nb.job_name,
            "cont_success_run_count": nb.cont_success_run_count,
            "trigger_type": nb.trigger_type,
        }

    # ------------------------------------------------------------------
    # Analysis Runs
    # ------------------------------------------------------------------

    async def save_analysis_run(
        self,
        analysis_id: str,
        run_id: str,
        user_id: int,
        data: dict,
    ) -> int:
        """Save analysis results. Auto-increments version per run_id. Returns version."""
        uid_analysis = uuid.UUID(analysis_id)
        uid_run = uuid.UUID(run_id)

        async with async_session() as db:
            # Compute next version
            result = await db.execute(
                select(func.max(AnalysisRun.version)).where(
                    AnalysisRun.run_id == uid_run
                )
            )
            max_v = result.scalar()
            version = (max_v or 0) + 1

            run = AnalysisRun(
                id=uid_analysis,
                run_id=uid_run,
                user_id=user_id,
                org_id=data.get("org_id"),
                counters=data.get("counters", {}),
                clusters=data.get("clusters", []),
                classified_filters=data.get("classified_filters", {}),
                fingerprints_summary=data.get("fingerprints_summary", []),
                literal_vals=data.get("literal_vals", {}),
                alias_conv=data.get("alias_conv", {}),
                total_weight=data.get("total_weight", 0),
                version=version,
                status="completed",
                created_at=_utcnow(),
            )
            db.add(run)
            await db.commit()
        return version

    async def get_analysis_run(self, analysis_id: str) -> Optional[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(AnalysisRun).where(
                    AnalysisRun.id == uuid.UUID(analysis_id)
                )
            )
            run = result.scalar_one_or_none()
            return self._analysis_to_dict(run) if run else None

    async def get_analysis_runs_for_extraction(self, run_id: str) -> list[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(AnalysisRun)
                .where(AnalysisRun.run_id == uuid.UUID(run_id))
                .order_by(AnalysisRun.created_at.desc())
            )
            return [self._analysis_to_dict(r) for r in result.scalars().all()]

    async def get_analysis_history(self) -> list[dict]:
        """Return lightweight metadata for all analysis runs."""
        async with async_session() as db:
            stmt = text("""
                SELECT
                    a.id, a.run_id, a.org_id, a.version, a.total_weight,
                    a.status, a.created_at,
                    e.databricks_instance, e.root_path, e.valid_sqls, e.total_notebooks,
                    (SELECT COUNT(*) FROM analysis_fingerprints af WHERE af.analysis_id = a.id) AS fingerprint_count,
                    (SELECT COUNT(*) FROM analysis_notebooks an WHERE an.analysis_id = a.id) AS notebook_count
                FROM analysis_runs a
                LEFT JOIN extraction_runs e ON e.id = a.run_id
                ORDER BY a.created_at DESC
            """)
            result = await db.execute(stmt)
            return [dict(row._mapping) for row in result.all()]

    async def get_analysis_history_for_run(self, run_id: str) -> list[dict]:
        async with async_session() as db:
            stmt = text("""
                SELECT
                    a.id, a.run_id, a.org_id, a.version, a.total_weight,
                    a.status, a.created_at,
                    (SELECT COUNT(*) FROM analysis_fingerprints af WHERE af.analysis_id = a.id) AS fingerprint_count,
                    (SELECT COUNT(*) FROM analysis_notebooks an WHERE an.analysis_id = a.id) AS notebook_count
                FROM analysis_runs a
                WHERE a.run_id = :run_id
                ORDER BY a.created_at DESC
            """)
            result = await db.execute(stmt, {"run_id": uuid.UUID(run_id)})
            return [dict(row._mapping) for row in result.all()]

    async def delete_analysis_run(self, analysis_id: str):
        """Delete analysis run and cascaded data."""
        uid = uuid.UUID(analysis_id)
        async with async_session() as db:
            # Delete context docs linked to this analysis
            await db.execute(
                delete(ContextDoc).where(ContextDoc.source_run_id == uid)
            )
            # Delete analysis notebooks + fingerprints (CASCADE handles this)
            await db.execute(
                delete(AnalysisNotebook).where(AnalysisNotebook.analysis_id == uid)
            )
            await db.execute(
                delete(AnalysisFingerprint).where(AnalysisFingerprint.analysis_id == uid)
            )
            await db.execute(
                delete(AnalysisRun).where(AnalysisRun.id == uid)
            )
            await db.commit()

    def _analysis_to_dict(self, run: AnalysisRun) -> dict:
        return {
            "id": str(run.id),
            "run_id": str(run.run_id),
            "user_id": run.user_id,
            "org_id": run.org_id,
            "counters": run.counters or {},
            "clusters": run.clusters or [],
            "classified_filters": run.classified_filters or {},
            "fingerprints_summary": run.fingerprints_summary or [],
            "literal_vals": run.literal_vals or {},
            "alias_conv": run.alias_conv or {},
            "total_weight": run.total_weight,
            "version": run.version,
            "status": run.status,
            "created_at": run.created_at.isoformat() if run.created_at else None,
        }

    # ------------------------------------------------------------------
    # Analysis Fingerprints (individual QFP rows)
    # ------------------------------------------------------------------

    async def save_analysis_fingerprints(
        self, analysis_id: str, fingerprints: list[dict]
    ):
        """Bulk insert individual fingerprint records for an analysis run."""
        uid = uuid.UUID(analysis_id)
        async with async_session() as db:
            objects = [
                AnalysisFingerprint(
                    analysis_id=uid,
                    qfp_id=fp.get("id", ""),
                    raw_sql=fp.get("raw_sql", ""),
                    canonical_sql=fp.get("canonical_sql", ""),
                    nl_question=fp.get("nl_question"),
                    frequency=fp.get("frequency", 1),
                    tables_json=fp.get("tables", []),
                    columns_json=fp.get("qualified_columns", []),
                    functions_json=fp.get("functions", []),
                    join_graph_json=fp.get("join_graph", []),
                    where_json=fp.get("where_conditions", []),
                    group_by_json=fp.get("group_by", []),
                    having_json=fp.get("having_conditions", []),
                    order_by_json=fp.get("order_by", []),
                    literals_json=fp.get("literals", {}),
                    case_when_json=fp.get("case_when_blocks", []),
                    window_json=fp.get("window_exprs", []),
                    structural_flags={
                        "has_cte": bool(fp.get("has_cte")),
                        "has_window": bool(fp.get("has_window")),
                        "has_union": bool(fp.get("has_union")),
                        "has_case": bool(fp.get("has_case")),
                        "has_subquery": bool(fp.get("has_subquery")),
                        "has_having": bool(fp.get("has_having")),
                        "has_order_by": bool(fp.get("has_order_by")),
                        "has_distinct": bool(fp.get("has_distinct")),
                        "has_limit": bool(fp.get("has_limit")),
                        "limit_value": fp.get("limit_value"),
                    },
                    select_col_count=fp.get("select_col_count", 0),
                    alias_map_json=fp.get("alias_map", {}),
                    created_at=_utcnow(),
                )
                for fp in fingerprints
            ]
            db.add_all(objects)
            await db.commit()

    async def get_analysis_fingerprints(
        self, analysis_id: str, limit: int = 100, offset: int = 0
    ) -> tuple[list[dict], int]:
        """Get paginated fingerprints. Returns (fingerprints, total_count)."""
        uid = uuid.UUID(analysis_id)
        async with async_session() as db:
            # Total count
            count_result = await db.execute(
                select(func.count())
                .select_from(AnalysisFingerprint)
                .where(AnalysisFingerprint.analysis_id == uid)
            )
            total = count_result.scalar() or 0

            # Paginated results
            result = await db.execute(
                select(AnalysisFingerprint)
                .where(AnalysisFingerprint.analysis_id == uid)
                .order_by(AnalysisFingerprint.frequency.desc())
                .limit(limit)
                .offset(offset)
            )
            rows = result.scalars().all()

            results = []
            for fp in rows:
                flags = fp.structural_flags or {}
                results.append({
                    "id": fp.qfp_id,
                    "raw_sql": fp.raw_sql,
                    "canonical_sql": fp.canonical_sql,
                    "nl_question": fp.nl_question,
                    "frequency": fp.frequency,
                    "tables": fp.tables_json or [],
                    "qualified_columns": fp.columns_json or [],
                    "functions": fp.functions_json or [],
                    "join_graph": fp.join_graph_json or [],
                    "where_conditions": fp.where_json or [],
                    "group_by": fp.group_by_json or [],
                    "having_conditions": fp.having_json or [],
                    "order_by": fp.order_by_json or [],
                    "literals": fp.literals_json or {},
                    "case_when_blocks": fp.case_when_json or [],
                    "window_exprs": fp.window_json or [],
                    "has_cte": flags.get("has_cte", False),
                    "has_window": flags.get("has_window", False),
                    "has_union": flags.get("has_union", False),
                    "has_case": flags.get("has_case", False),
                    "has_subquery": flags.get("has_subquery", False),
                    "has_having": flags.get("has_having", False),
                    "has_order_by": flags.get("has_order_by", False),
                    "has_distinct": flags.get("has_distinct", False),
                    "has_limit": flags.get("has_limit", False),
                    "limit_value": flags.get("limit_value"),
                    "select_col_count": fp.select_col_count,
                    "alias_map": fp.alias_map_json or {},
                })

            return results, total

    # ------------------------------------------------------------------
    # Analysis-Notebook Linkage
    # ------------------------------------------------------------------

    async def save_analysis_notebooks(
        self, analysis_id: str, notebook_links: list[dict]
    ):
        """Link notebooks to an analysis run with SQL counts."""
        uid = uuid.UUID(analysis_id)
        async with async_session() as db:
            objects = [
                AnalysisNotebook(
                    analysis_id=uid,
                    notebook_id=link["notebook_id"],
                    sql_count=link.get("sql_count", 0),
                    created_at=_utcnow(),
                )
                for link in notebook_links
            ]
            db.add_all(objects)
            await db.commit()

    async def get_analysis_notebooks(self, analysis_id: str) -> list[dict]:
        """Get notebooks linked to an analysis run with metadata."""
        uid = uuid.UUID(analysis_id)
        async with async_session() as db:
            stmt = text("""
                SELECT an.id, an.analysis_id, an.notebook_id, an.sql_count,
                       an.created_at,
                       nm.notebook_path, nm.notebook_name, nm.user_name,
                       nm.language, nm.status, nm.is_attached_to_jobs,
                       nm.job_id, nm.job_name
                FROM analysis_notebooks an
                JOIN notebook_metadata nm ON an.notebook_id = nm.id
                WHERE an.analysis_id = :analysis_id
                ORDER BY an.sql_count DESC
            """)
            result = await db.execute(stmt, {"analysis_id": uid})
            return [dict(row._mapping) for row in result.all()]

    # ------------------------------------------------------------------
    # Context Documents
    # ------------------------------------------------------------------

    async def save_context_doc(
        self,
        analysis_id: str,
        org_id: Optional[str],
        user_id: int,
        doc: dict,
    ):
        """Save a generated context document."""
        async with async_session() as db:
            doc_obj = ContextDoc(
                source_type="databricks",
                source_run_id=uuid.UUID(analysis_id),
                user_id=user_id,
                org_id=org_id or doc.get("org_id"),
                doc_key=doc["doc_key"],
                doc_name=doc.get("doc_name"),
                doc_content=doc.get("doc_content"),
                model_used=doc.get("model_used"),
                provider_used=doc.get("provider_used"),
                system_prompt_used=doc.get("system_prompt_used"),
                payload_sent=doc.get("payload_sent", {}),
                inclusions_used=doc.get("inclusions_used", {}),
                token_count=doc.get("token_count"),
                status="active",
                created_at=_utcnow(),
            )
            db.add(doc_obj)
            await db.commit()

    async def get_context_docs(self, analysis_id: str) -> list[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(ContextDoc)
                .where(ContextDoc.source_run_id == uuid.UUID(analysis_id))
                .order_by(ContextDoc.doc_key)
            )
            docs = result.scalars().all()
            return [self._doc_to_dict(d) for d in docs]

    async def get_context_doc(self, doc_id: int) -> Optional[dict]:
        async with async_session() as db:
            result = await db.execute(
                select(ContextDoc).where(ContextDoc.id == doc_id)
            )
            doc = result.scalar_one_or_none()
            return self._doc_to_dict(doc) if doc else None

    def _doc_to_dict(self, doc: ContextDoc) -> dict:
        return {
            "id": doc.id,
            "source_type": doc.source_type,
            "source_run_id": str(doc.source_run_id) if doc.source_run_id else None,
            "user_id": doc.user_id,
            "org_id": doc.org_id,
            "doc_key": doc.doc_key,
            "doc_name": doc.doc_name,
            "doc_content": doc.doc_content,
            "model_used": doc.model_used,
            "provider_used": doc.provider_used,
            "system_prompt_used": doc.system_prompt_used,
            "payload_sent": doc.payload_sent or {},
            "inclusions_used": doc.inclusions_used or {},
            "token_count": doc.token_count,
            "status": doc.status,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }

    # ------------------------------------------------------------------
    # Storage Stats
    # ------------------------------------------------------------------

    async def get_storage_stats(self) -> dict:
        """Return row counts for all pipeline tables."""
        tables = [
            ("extraction_runs", ExtractionRun),
            ("extracted_sqls", ExtractedSQL),
            ("notebook_metadata", NotebookMetadata),
            ("analysis_runs", AnalysisRun),
            ("analysis_fingerprints", AnalysisFingerprint),
            ("analysis_notebooks", AnalysisNotebook),
            ("context_docs", ContextDoc),
        ]
        stats = {}
        async with async_session() as db:
            for name, model in tables:
                result = await db.execute(select(func.count()).select_from(model))
                stats[name] = result.scalar() or 0
        return stats
