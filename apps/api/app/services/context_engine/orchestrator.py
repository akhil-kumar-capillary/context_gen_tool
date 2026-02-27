"""Tree Orchestrator — background task that runs the full tree generation pipeline.

Pipeline: collect contexts → build tree via LLM → validate → save to DB.
Progress is streamed to the user via WebSocket.
"""
import asyncio
import logging
import uuid as uuid_mod
from datetime import timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import select, update

from app.core.websocket import WebSocketManager
from app.database import async_session
from app.models.context_tree import ContextTreeRun
from app.services.context_engine.collector import collect_all_contexts
from app.services.context_engine.tree_builder import build_tree
from app.utils import utcnow

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, str], Awaitable[None]]


def _make_progress_callback(
    ws_manager: WebSocketManager,
    user_id: int,
    run_id: str,
) -> ProgressCallback:
    """Create a progress callback that emits WebSocket events."""
    async def _emit(phase: str, detail: str, status: str):
        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_progress",
            "run_id": run_id,
            "phase": phase,
            "detail": detail,
            "status": status,
        })
    return _emit


async def _save_progress(run_id: str, progress_entries: list[dict]):
    """Persist progress entries to the DB."""
    async with async_session() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid_mod.UUID(run_id))
            .values(progress_data=progress_entries)
        )
        await db.commit()


async def _save_completion(
    run_id: str,
    tree_data: dict,
    input_sources: dict,
    input_count: int,
    model_used: str,
    provider_used: str,
    token_usage: dict,
    system_prompt_used: str,
    progress_entries: list[dict],
):
    """Save final tree result and mark run as completed."""
    async with async_session() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid_mod.UUID(run_id))
            .values(
                tree_data=tree_data,
                input_sources=input_sources,
                input_context_count=input_count,
                model_used=model_used,
                provider_used=provider_used,
                token_usage=token_usage,
                system_prompt_used=system_prompt_used,
                progress_data=progress_entries,
                status="completed",
                completed_at=utcnow(),
            )
        )
        await db.commit()


async def _save_failure(run_id: str, error_message: str, progress_entries: list[dict]):
    """Mark run as failed with error message."""
    async with async_session() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid_mod.UUID(run_id))
            .values(
                status="failed",
                error_message=error_message,
                progress_data=progress_entries,
                completed_at=utcnow(),
            )
        )
        await db.commit()


async def run_tree_generation(
    run_id: str,
    user: dict,
    org_id: int,
    ws_manager: WebSocketManager,
    user_id: int,
    cancel_event: asyncio.Event | None = None,
):
    """Background task: collect contexts -> build tree -> save results.

    Args:
        run_id: UUID string for this tree run.
        user: User dict with capillary_token, base_url, etc.
        org_id: Organization ID.
        ws_manager: WebSocket manager for progress events.
        user_id: User who triggered generation.
        cancel_event: Event to cancel the pipeline.
    """
    progress_entries: list[dict] = []
    emit = _make_progress_callback(ws_manager, user_id, run_id)

    async def track(phase: str, detail: str, status: str):
        """Track progress both in WS and in the progress list."""
        entry = {"phase": phase, "detail": detail, "status": status}
        progress_entries.append(entry)
        await emit(phase, detail, status)

    try:
        # ─── Phase 1: Collecting ───────────────────────────────────
        await track("collecting", "Fetching contexts from all sources...", "running")

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        base_url = user.get("base_url", "")
        capillary_headers = {
            "Authorization": f"Bearer {user.get('capillary_token', '')}",
            "x-cap-api-auth-org-id": str(org_id),
        }

        async with async_session() as db:
            collected = await collect_all_contexts(
                db=db,
                org_id=org_id,
                base_url=base_url,
                capillary_headers=capillary_headers,
            )

        summary = collected["summary"]
        await track(
            "collecting",
            f"Collected {summary['total']} contexts "
            f"({summary['databricks']} databricks, "
            f"{summary['config_apis']} config_apis, "
            f"{summary['capillary']} capillary)",
            "done",
        )

        if not collected["sources"]:
            await track("collecting", "No contexts found — cannot build tree", "failed")
            await _save_failure(run_id, "No contexts found for this organization", progress_entries)
            await ws_manager.send_to_user(user_id, {
                "type": "context_engine_failed",
                "run_id": run_id,
                "error": "No contexts found for this organization",
            })
            return

        # ─── Phase 2: Analyzing (LLM tree building) ───────────────
        await track("analyzing", f"Sending {summary['total']} contexts to LLM...", "running")

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        async def builder_progress(phase: str, detail: str, status: str):
            await track(phase, detail, status)

        result = await build_tree(
            contexts=collected["sources"],
            org_id=org_id,
            progress_cb=builder_progress,
            cancel_event=cancel_event,
        )

        await track("analyzing", "Tree structure generated successfully", "done")

        # ─── Phase 3: Enriching ─────────────────────────────────
        await track("enriching", "Scanning for secrets...", "running")

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        # 3a: Secret scanning
        try:
            from app.services.context_engine.secret_scanner import scan_tree_secrets
            secret_count = scan_tree_secrets(result["tree_data"])
            if secret_count > 0:
                await track("enriching", f"Detected {secret_count} secret(s) — masked and extracted", "done")
            else:
                await track("enriching", "No secrets detected", "done")
        except Exception as e:
            logger.warning(f"Secret scanning failed (non-fatal): {e}")
            await track("enriching", f"Secret scanning skipped: {e}", "done")

        # 3b: Conflict detection
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        await track("enriching", "Detecting conflicts between contexts...", "running")
        try:
            from app.services.context_engine.conflict_detector import detect_conflicts
            conflict_count = await detect_conflicts(result["tree_data"])
            if conflict_count > 0:
                await track("enriching", f"Found {conflict_count} conflict(s)", "done")
            else:
                await track("enriching", "No conflicts detected", "done")
        except Exception as e:
            logger.warning(f"Conflict detection failed (non-fatal): {e}")
            await track("enriching", f"Conflict detection skipped: {e}", "done")

        # 3c: Redundancy detection
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        await track("enriching", "Detecting redundancy between contexts...", "running")
        try:
            from app.services.context_engine.redundancy_detector import detect_redundancy
            redundancy_count = await detect_redundancy(result["tree_data"])
            if redundancy_count > 0:
                await track("enriching", f"Found {redundancy_count} redundant overlap(s)", "done")
            else:
                await track("enriching", "No significant redundancy detected", "done")
        except Exception as e:
            logger.warning(f"Redundancy detection failed (non-fatal): {e}")
            await track("enriching", f"Redundancy detection skipped: {e}", "done")

        # 3d: Health scoring (runs last since it uses conflict/redundancy results)
        await track("enriching", "Computing health scores...", "running")
        try:
            from app.services.context_engine.health_scorer import score_tree_health
            score_tree_health(result["tree_data"])
            await track("enriching", "Health scores computed", "done")
        except Exception as e:
            logger.warning(f"Health scoring failed (non-fatal): {e}")
            await track("enriching", f"Health scoring skipped: {e}", "done")

        # ─── Phase 4: Saving ──────────────────────────────────────
        await track("saving", "Persisting tree to database...", "running")

        await _save_completion(
            run_id=run_id,
            tree_data=result["tree_data"],
            input_sources=collected["input_sources"],
            input_count=summary["total"],
            model_used=result["model_used"],
            provider_used=result["provider_used"],
            token_usage=result["token_usage"],
            system_prompt_used=result["system_prompt_used"],
            progress_entries=progress_entries,
        )

        await track("saving", "Tree saved to database", "done")

        # ─── Phase 4: Complete ────────────────────────────────────
        await track("complete", f"Tree generated with {summary['total']} contexts", "done")

        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_complete",
            "run_id": run_id,
            "input_context_count": summary["total"],
        })

    except asyncio.CancelledError:
        await track("cancelled", "Tree generation was cancelled", "failed")
        await _save_failure(run_id, "Cancelled by user", progress_entries)
        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_cancelled",
            "run_id": run_id,
        })

    except Exception as e:
        logger.exception(f"Tree generation failed for run {run_id}")
        error_msg = str(e)
        await track("error", f"Failed: {error_msg}", "failed")
        await _save_failure(run_id, error_msg, progress_entries)
        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_failed",
            "run_id": run_id,
            "error": error_msg,
        })
