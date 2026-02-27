"""
Async storage service for the Config APIs pipeline.

Mirrors the Databricks ``StorageService`` pattern:
short-lived async sessions, UUID conversion at boundaries.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import select, update, delete, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models.config_pipeline import ConfigExtractionRun, ConfigAnalysisRun
from app.models.context_doc import ContextDoc
from app.utils import utcnow as _utcnow

logger = logging.getLogger(__name__)


class ConfigStorageService:
    """Async PostgreSQL storage for Config APIs pipeline data."""

    # ------------------------------------------------------------------
    # Extraction Runs
    # ------------------------------------------------------------------

    async def create_extraction_run(
        self,
        run_id: str,
        user_id: int,
        org_id: int,
        host: str,
        categories: List[str],
        category_params: Optional[Dict[str, Any]] = None,
    ) -> str:
        async with async_session() as db:
            run = ConfigExtractionRun(
                id=uuid.UUID(run_id),
                user_id=user_id,
                org_id=org_id,
                host=host,
                categories=categories,
                category_params=category_params or {},
                status="running",
                started_at=_utcnow(),
            )
            db.add(run)
            await db.commit()
        return run_id

    async def update_extraction_run(self, run_id: str, **kwargs: Any) -> None:
        async with async_session() as db:
            stmt = (
                update(ConfigExtractionRun)
                .where(ConfigExtractionRun.id == uuid.UUID(run_id))
                .values(**kwargs)
            )
            await db.execute(stmt)
            await db.commit()

    async def complete_extraction_run(
        self,
        run_id: str,
        extracted_data: Dict[str, Any],
        stats: Dict[str, Any],
        api_call_log: Optional[Dict[str, Any]] = None,
    ) -> None:
        kwargs: Dict[str, Any] = {
            "extracted_data": extracted_data,
            "stats": stats,
            "status": "completed",
            "completed_at": _utcnow(),
        }
        if api_call_log is not None:
            kwargs["api_call_log"] = api_call_log
        await self.update_extraction_run(run_id, **kwargs)

    async def fail_extraction_run(self, run_id: str, error: str) -> None:
        await self.update_extraction_run(
            run_id,
            status="failed",
            error_message=error,
            completed_at=_utcnow(),
        )

    async def cancel_extraction_run(self, run_id: str) -> None:
        await self.update_extraction_run(
            run_id,
            status="cancelled",
            completed_at=_utcnow(),
        )

    async def get_extraction_runs(
        self, user_id: int, org_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        async with async_session() as db:
            stmt = (
                select(ConfigExtractionRun)
                .where(ConfigExtractionRun.user_id == user_id)
                .order_by(ConfigExtractionRun.created_at.desc())
            )
            if org_id is not None:
                stmt = stmt.where(ConfigExtractionRun.org_id == org_id)
            result = await db.execute(stmt)
            rows = result.scalars().all()
        return [_extraction_to_dict(r) for r in rows]

    async def get_extraction_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(ConfigExtractionRun).where(
                    ConfigExtractionRun.id == uuid.UUID(run_id)
                )
            )
            row = result.scalar_one_or_none()
        return _extraction_to_dict(row) if row else None

    async def delete_extraction_run(self, run_id: str) -> None:
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            # Delete child analysis runs first (CASCADE should handle, but be explicit)
            await db.execute(
                delete(ConfigAnalysisRun).where(ConfigAnalysisRun.run_id == uid)
            )
            await db.execute(
                delete(ConfigExtractionRun).where(ConfigExtractionRun.id == uid)
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Extraction Run — granular access
    # ------------------------------------------------------------------

    async def get_api_call_log(
        self, run_id: str, category: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get the api_call_log for a run, optionally filtered by category."""
        async with async_session() as db:
            result = await db.execute(
                select(ConfigExtractionRun.api_call_log).where(
                    ConfigExtractionRun.id == uuid.UUID(run_id)
                )
            )
            log = result.scalar_one_or_none()
        if log is None:
            return None
        if category:
            return {category: log.get(category, [])}
        return log

    async def get_raw_api_data(
        self, run_id: str, category: str, api_name: Optional[str] = None
    ) -> Optional[Any]:
        """Read a specific key from extracted_data JSONB without loading full blob.

        If api_name is provided, returns extracted_data[category][api_name].
        Otherwise returns extracted_data[category].
        """
        uid = uuid.UUID(run_id)
        async with async_session() as db:
            if api_name:
                # Use JSONB path operator to extract nested key
                stmt = text(
                    "SELECT extracted_data -> :cat -> :api "
                    "FROM config_extraction_runs WHERE id = :id"
                )
                result = await db.execute(
                    stmt, {"cat": category, "api": api_name, "id": str(uid)}
                )
            else:
                stmt = text(
                    "SELECT extracted_data -> :cat "
                    "FROM config_extraction_runs WHERE id = :id"
                )
                result = await db.execute(stmt, {"cat": category, "id": str(uid)})
            row = result.scalar_one_or_none()
        return row

    # ------------------------------------------------------------------
    # Analysis Runs
    # ------------------------------------------------------------------

    async def save_analysis_run(
        self,
        analysis_id: str,
        run_id: str,
        user_id: int,
        org_id: int,
        analysis_data: Dict[str, Any],
    ) -> str:
        async with async_session() as db:
            # Auto-increment version
            stmt = (
                select(ConfigAnalysisRun.version)
                .where(ConfigAnalysisRun.run_id == uuid.UUID(run_id))
                .order_by(ConfigAnalysisRun.version.desc())
                .limit(1)
            )
            result = await db.execute(stmt)
            prev_version = result.scalar_one_or_none()
            version = (prev_version or 0) + 1

            analysis = ConfigAnalysisRun(
                id=uuid.UUID(analysis_id),
                run_id=uuid.UUID(run_id),
                user_id=user_id,
                org_id=org_id,
                analysis_data=analysis_data,
                version=version,
                status="completed",
                completed_at=_utcnow(),
            )
            db.add(analysis)
            await db.commit()
        return analysis_id

    async def fail_analysis_run(
        self, analysis_id: str, error: str
    ) -> None:
        async with async_session() as db:
            stmt = (
                update(ConfigAnalysisRun)
                .where(ConfigAnalysisRun.id == uuid.UUID(analysis_id))
                .values(status="failed", error_message=error, completed_at=_utcnow())
            )
            await db.execute(stmt)
            await db.commit()

    async def get_analysis_run(
        self, analysis_id: str
    ) -> Optional[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(ConfigAnalysisRun).where(
                    ConfigAnalysisRun.id == uuid.UUID(analysis_id)
                )
            )
            row = result.scalar_one_or_none()
        return _analysis_to_dict(row) if row else None

    async def get_analysis_history(
        self, run_id: str
    ) -> List[Dict[str, Any]]:
        """Get analysis runs for a specific extraction, newest first."""
        async with async_session() as db:
            result = await db.execute(
                select(ConfigAnalysisRun)
                .where(ConfigAnalysisRun.run_id == uuid.UUID(run_id))
                .order_by(ConfigAnalysisRun.created_at.desc())
            )
            rows = result.scalars().all()
        return [_analysis_to_dict(r) for r in rows]

    async def delete_analysis_run(self, analysis_id: str) -> None:
        async with async_session() as db:
            await db.execute(
                delete(ConfigAnalysisRun).where(
                    ConfigAnalysisRun.id == uuid.UUID(analysis_id)
                )
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Context Docs (reuses existing ContextDoc model)
    # ------------------------------------------------------------------

    async def save_context_doc(
        self,
        analysis_id: str,
        user_id: int,
        org_id: int,
        doc_key: str,
        doc_name: str,
        doc_content: str,
        model_used: Optional[str] = None,
        provider_used: Optional[str] = None,
        system_prompt_used: Optional[str] = None,
        payload_sent: Optional[Dict[str, Any]] = None,
        token_count: Optional[int] = None,
    ) -> int:
        async with async_session() as db:
            doc = ContextDoc(
                source_type="config_apis",
                source_run_id=uuid.UUID(analysis_id),
                user_id=user_id,
                org_id=str(org_id),
                doc_key=doc_key,
                doc_name=doc_name,
                doc_content=doc_content,
                model_used=model_used,
                provider_used=provider_used,
                system_prompt_used=system_prompt_used,
                payload_sent=payload_sent,
                token_count=token_count,
            )
            db.add(doc)
            await db.commit()
            await db.refresh(doc)
            return doc.id

    async def get_context_docs(
        self, analysis_id: str
    ) -> List[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(ContextDoc)
                .where(
                    ContextDoc.source_run_id == uuid.UUID(analysis_id),
                    ContextDoc.source_type == "config_apis",
                )
                .order_by(ContextDoc.doc_key)
            )
            rows = result.scalars().all()
        return [_context_doc_to_dict(r) for r in rows]

    async def get_context_doc(self, doc_id: int) -> Optional[Dict[str, Any]]:
        async with async_session() as db:
            result = await db.execute(
                select(ContextDoc).where(ContextDoc.id == doc_id)
            )
            r = result.scalar_one_or_none()
        return _context_doc_to_dict(r) if r else None


# ---------------------------------------------------------------------------
# Private serialization helpers
# ---------------------------------------------------------------------------

def _extraction_to_dict(row: ConfigExtractionRun) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "user_id": row.user_id,
        "org_id": row.org_id,
        "host": row.host,
        "categories": row.categories,
        "category_params": row.category_params,
        "stats": row.stats,
        "api_call_log": row.api_call_log,
        "status": row.status,
        "error_message": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _analysis_to_dict(row: ConfigAnalysisRun) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "run_id": str(row.run_id) if row.run_id else None,
        "user_id": row.user_id,
        "org_id": row.org_id,
        "version": row.version,
        "status": row.status,
        "error_message": row.error_message,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
    }


def _context_doc_to_dict(row: ContextDoc) -> Dict[str, Any]:
    return {
        "id": row.id,
        "doc_key": row.doc_key,
        "doc_name": row.doc_name,
        "doc_content": row.doc_content,
        "model_used": row.model_used,
        "provider_used": row.provider_used,
        "token_count": row.token_count,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
