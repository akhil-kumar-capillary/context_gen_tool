"""Tree Orchestrator — background task that runs the full tree generation pipeline.

Pipeline: collect contexts → build tree via LLM → (optional) sanitize content
          → enrich (secrets, conflicts, redundancy, health) → save to DB.
Progress is streamed to the user via WebSocket.
"""
import asyncio
import logging
import uuid as uuid_mod
from datetime import timezone
from typing import Any, Callable, Awaitable

from sqlalchemy import select, update

from app.config import settings
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
    org_id: int | None = None,
) -> ProgressCallback:
    """Create a progress callback that emits WebSocket events."""
    async def _emit(phase: str, detail: str, status: str):
        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_progress",
            "run_id": run_id,
            "phase": phase,
            "detail": detail,
            "status": status,
        }, org_id=org_id)
    return _emit


async def _save_progress(run_id: str, progress_entries: list[dict]):
    """Persist progress entries to the DB."""
    async with async_session() as db:
        await db.execute(
            update(ContextTreeRun)
            .where(ContextTreeRun.id == uuid_mod.UUID(run_id))
            .values(progress_data=progress_entries, updated_at=utcnow())
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
    org_id: int,
    user_id: int | None = None,
):
    """Save final tree result and mark run as completed.

    Retries once on transient DB errors so a successful generation isn't
    lost due to a momentary connection hiccup.  Also creates version 1
    (the initial snapshot) for the auto-versioning system.
    """
    from app.services.versioning import create_version

    max_attempts = 2
    for attempt in range(max_attempts):
        try:
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
                        updated_at=utcnow(),
                        completed_at=utcnow(),
                    )
                )

                # Create initial version (v1) for the tree
                await create_version(
                    db,
                    entity_type="context_tree",
                    entity_id=str(run_id),
                    org_id=org_id,
                    snapshot=tree_data,
                    previous_snapshot=None,
                    change_type="create",
                    change_summary="Initial tree generation",
                    changed_fields=["tree_data"],
                    user_id=user_id,
                )

                await db.commit()
                return  # success
        except Exception:
            if attempt < max_attempts - 1:
                logger.warning(
                    "DB commit failed for run %s (attempt %d), retrying...",
                    run_id, attempt + 1,
                )
                await asyncio.sleep(1)
            else:
                logger.exception("DB commit failed for run %s after %d attempts", run_id, max_attempts)
                raise


async def _save_failure(run_id: str, error_message: str, progress_entries: list[dict]):
    """Mark run as failed with error message.

    Guards against overwriting an already-completed run — if the run was
    successfully saved but a later step raised, we must not downgrade it.
    """
    try:
        async with async_session() as db:
            # Only overwrite if the run is still "running" — never downgrade
            # a "completed" run to "failed".
            result = await db.execute(
                update(ContextTreeRun)
                .where(
                    ContextTreeRun.id == uuid_mod.UUID(run_id),
                    ContextTreeRun.status == "running",
                )
                .values(
                    status="failed",
                    error_message=error_message,
                    progress_data=progress_entries,
                    completed_at=utcnow(),
                )
            )
            await db.commit()
            if result.rowcount == 0:
                logger.info(
                    "Run %s not marked as failed — already has terminal status", run_id
                )
    except Exception:
        logger.exception("Failed to save failure status for run %s", run_id)


async def run_tree_generation(
    run_id: str,
    user: dict,
    org_id: int,
    ws_manager: WebSocketManager,
    user_id: int,
    cancel_event: asyncio.Event | None = None,
    sanitize: bool = False,
    blueprint_text: str | None = None,
):
    """Background task: collect contexts -> build tree -> (optionally sanitize) -> save results.

    Args:
        run_id: UUID string for this tree run.
        user: User dict with capillary_token, base_url, etc.
        org_id: Organization ID.
        ws_manager: WebSocket manager for progress events.
        user_id: User who triggered generation.
        cancel_event: Event to cancel the pipeline.
        sanitize: If True, run content sanitization via blueprint after tree building.
        blueprint_text: Custom blueprint text for sanitization (optional).
    """
    progress_entries: list[dict] = []
    emit = _make_progress_callback(ws_manager, user_id, run_id, org_id=org_id)

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
        dedup_msg = ""
        if summary.get("duplicates_removed", 0) > 0:
            dedup_msg = f", {summary['duplicates_removed']} duplicates removed"
        await track(
            "collecting",
            f"Collected {summary['total']} contexts "
            f"({summary['databricks']} databricks, "
            f"{summary['config_apis']} config_apis, "
            f"{summary['capillary']} capillary{dedup_msg})",
            "done",
        )

        if not collected["sources"]:
            await track("collecting", "No contexts found — cannot build tree", "failed")
            await _save_failure(run_id, "No contexts found for this organization", progress_entries)
            await ws_manager.send_to_user(user_id, {
                "type": "context_engine_failed",
                "run_id": run_id,
                "error": "No contexts found for this organization",
            }, org_id=org_id)
            return

        # Reusable progress callback for sub-services
        async def builder_progress(phase: str, detail: str, status: str):
            await track(phase, detail, status)

        # ─── Phase 1b: Conflict Detection ─────────────────────────
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        await track("conflicts", "Checking for contradictions between contexts...", "running")

        try:
            from app.services.context_engine.conflict_resolver import detect_conflicts as find_conflicts

            conflicts = await find_conflicts(
                collected["sources"],
                progress_cb=builder_progress,
            )

            if conflicts:
                await track(
                    "conflicts",
                    f"Found {len(conflicts)} contradiction(s) — review recommended",
                    "done",
                )
                # Send conflicts to frontend for visibility
                await ws_manager.send_to_user(user_id, {
                    "type": "context_engine_conflicts",
                    "run_id": run_id,
                    "conflicts": [c.to_dict() for c in conflicts],
                    "count": len(conflicts),
                }, org_id=org_id)
            else:
                await track("conflicts", "No contradictions detected", "done")
        except Exception as e:
            logger.warning("Conflict detection failed (non-fatal): %s", e)
            await track("conflicts", f"Conflict detection skipped: {e}", "done")

        # ─── Phase 2: Analyzing (LLM tree building) ───────────────
        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        if sanitize:
            # Unified approach: blueprint restructuring + tree building in one LLM call.
            # The LLM has full liberty to merge, deduplicate, and optimize contexts.
            await track("analyzing", f"Optimizing {summary['total']} contexts via blueprint + tree building...", "running")

            try:
                from app.services.context_engine.optimized_builder import build_optimized_tree

                result = await build_optimized_tree(
                    contexts=collected["sources"],
                    org_id=org_id,
                    progress_cb=builder_progress,
                    cancel_event=cancel_event,
                    blueprint_text=blueprint_text,
                    max_tokens=settings.sanitize_max_output_tokens,
                )

                await track("analyzing", "Optimized tree generated successfully", "done")

            except asyncio.CancelledError:
                raise
            except Exception as e:
                # Fallback: use standard two-stage flow if unified builder fails
                logger.warning(f"Optimized builder failed, falling back to standard flow: {e}")
                await track(
                    "analyzing",
                    f"Optimized build failed — falling back to standard tree building...",
                    "running",
                )

                result = await build_tree(
                    contexts=collected["sources"],
                    org_id=org_id,
                    progress_cb=builder_progress,
                    cancel_event=cancel_event,
                )

                await track("analyzing", "Tree structure generated successfully (fallback)", "done")
        else:
            # Standard flow: tree structure only, attach original content
            await track("analyzing", f"Sending {summary['total']} contexts to LLM...", "running")

            result = await build_tree(
                contexts=collected["sources"],
                org_id=org_id,
                progress_cb=builder_progress,
                cancel_event=cancel_event,
            )

            await track("analyzing", "Tree structure generated successfully", "done")

        # ─── Phase 3: Sanitizing (handled during Phase 2 for optimized flow) ──
        if sanitize:
            await track("sanitizing", "Content optimization completed during tree building", "done")

        # ─── Phase 4: Enriching ─────────────────────────────────
        await track("enriching", "Scanning for secrets...", "running")

        if cancel_event and cancel_event.is_set():
            raise asyncio.CancelledError()

        # 4a: Secret scanning
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

        # 4b: Conflict detection
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

        # 4c: Redundancy detection
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

        # 4d: Health scoring (runs last since it uses conflict/redundancy results)
        await track("enriching", "Computing health scores...", "running")
        try:
            from app.services.context_engine.health_scorer import score_tree_health
            score_tree_health(result["tree_data"])
            await track("enriching", "Health scores computed", "done")
        except Exception as e:
            logger.warning(f"Health scoring failed (non-fatal): {e}")
            await track("enriching", f"Health scoring skipped: {e}", "done")

        # ─── Phase 5: Saving ──────────────────────────────────────
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
            org_id=org_id,
            user_id=user_id,
        )

        await track("saving", "Tree saved to database", "done")

        # Log LLM usage for cost tracking
        logger.info(
            "LLM call completed",
            extra={
                "event": "llm_call",
                "provider": result.get("provider_used"),
                "model": result.get("model_used"),
                "input_tokens": result.get("token_usage", {}).get("input_tokens", 0),
                "output_tokens": result.get("token_usage", {}).get("output_tokens", 0),
                "user_id": user_id,
                "org_id": org_id,
                "run_id": run_id,
            },
        )

        # ─── Complete ────────────────────────────────────────────
        await track("complete", f"Tree generated with {summary['total']} contexts", "done")

        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_complete",
            "run_id": run_id,
            "input_context_count": summary["total"],
        }, org_id=org_id)

    except asyncio.CancelledError:
        await track("cancelled", "Tree generation was cancelled", "failed")
        await _save_failure(run_id, "Cancelled by user", progress_entries)
        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_cancelled",
            "run_id": run_id,
        }, org_id=org_id)

    except Exception as e:
        logger.exception(f"Tree generation failed for run {run_id}")
        error_msg = str(e)
        await track("error", f"Failed: {error_msg}", "failed")
        await _save_failure(run_id, error_msg, progress_entries)

        # Graceful degradation: check if a previous successful tree exists
        # so the frontend can still show useful data.
        has_fallback = False
        try:
            async with async_session() as db:
                prev = await db.execute(
                    select(ContextTreeRun.id)
                    .where(
                        ContextTreeRun.org_id == org_id,
                        ContextTreeRun.status == "completed",
                    )
                    .limit(1)
                )
                has_fallback = prev.scalar_one_or_none() is not None
        except Exception:
            pass

        await ws_manager.send_to_user(user_id, {
            "type": "context_engine_failed",
            "run_id": run_id,
            "error": error_msg,
            "has_previous_tree": has_fallback,
        }, org_id=org_id)
