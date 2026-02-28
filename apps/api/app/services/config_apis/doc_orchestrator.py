"""
Doc generation orchestrator for Config APIs.

End-to-end: load analysis → build payloads → author docs → validate → save.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any, Callable, Awaitable, Dict, List, Optional

from app.services.config_apis.storage import ConfigStorageService
from app.services.config_apis.payload_builder import (
    build_payloads,
    build_payloads_from_clusters,
    strip_stats,
    DOC_TYPES,
)
from app.services.config_apis.doc_author import author_doc, DOC_NAMES

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int, str], Awaitable[None]]


# ═══════════════════════════════════════════════════════════════════════
# Post-generation validation
# ═══════════════════════════════════════════════════════════════════════

_AUDIT_PHRASES = [
    "no .* configured",
    "not configured",
    "should be configured",
    "no active",
    "not found",
    "no .* available",
    "0 programs",
    "0 campaigns",
    "0 promotions",
    "0 audiences",
    "0 coupons",
    "recommend",
    "future configuration",
    "zero .*",
    "none .* configured",
    "not currently",
    "no data",
    "does not have",
    "has not been",
    "no .* found",
    "no .* exist",
]

_AUDIT_PATTERN = re.compile(
    "|".join(f"({p})" for p in _AUDIT_PHRASES),
    re.IGNORECASE,
)


def _validate_doc(
    doc_key: str, content: str, analysis_data: Dict[str, Any]
) -> List[str]:
    """Validate generated doc against source data. Returns list of warnings."""
    warnings: List[str] = []

    # 1. Minimum content length (too short = likely empty/error)
    if len(content.strip()) < 200:
        warnings.append("Document is very short (<200 chars) — may be incomplete")

    # 2. Check for audit language
    audit_matches = _AUDIT_PATTERN.findall(content)
    if audit_matches:
        flat = [m for group in audit_matches for m in group if m]
        if flat:
            warnings.append(
                f"Contains audit language ({len(flat)} matches) — "
                f"should focus on what exists, not what's missing"
            )

    # 3. Check for JSON code blocks (docs should contain real examples)
    json_blocks = content.count("```json") + content.count("```")
    if json_blocks < 1 and doc_key != "05_CUSTOMIZATIONS":
        warnings.append("No JSON code blocks found — doc may lack real config examples")

    # 4. Check that doc mentions actual entity names from data
    doc_sections = DOC_TYPES.get(doc_key, {}).get("sections", [])
    for section_key in doc_sections:
        section_data = analysis_data.get(section_key, {})
        if not isinstance(section_data, dict):
            continue
        # Look for entity objects with 'name' fields
        for entity_key, entity_data in section_data.items():
            if not isinstance(entity_data, dict):
                continue
            objects = entity_data.get("objects") or entity_data.get("examples") or []
            if isinstance(objects, list) and objects:
                first = objects[0]
                if isinstance(first, dict):
                    name = first.get("name") or first.get("programName") or first.get("campaignName")
                    if isinstance(name, str) and len(name) > 2 and name not in content:
                        warnings.append(
                            f"Entity name '{name}' from {entity_key} not found in doc"
                        )
                        break  # Only report one missing name per section

    return warnings


async def run_generation(
    *,
    analysis_id: str,
    user_id: int,
    org_id: int,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    inclusions: Optional[Dict[str, Dict[str, bool]]] = None,
    system_prompts: Optional[Dict[str, str]] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> Dict[str, Any]:
    """Generate context documents from analysis data.

    Args:
        analysis_id: Analysis run UUID.
        user_id: User running the generation.
        org_id: Organization ID.
        provider: LLM provider.
        model: LLM model.
        inclusions: {doc_key: {entity_path: bool}} — toggle items.
        system_prompts: {doc_key: custom_prompt_str} — override defaults.
        on_progress: async callback(phase, completed, total, detail).

    Returns:
        dict with doc_count, docs generated
    """
    storage = ConfigStorageService()

    async def emit(phase: str, completed: int, total: int, detail: str):
        if on_progress:
            await on_progress(phase, completed, total, detail)

    # Load analysis data
    await emit("loading", 0, 0, "Loading analysis data...")

    # Need the full analysis_data from DB
    from app.database import async_session
    from app.models.config_pipeline import ConfigAnalysisRun
    from sqlalchemy import select
    import uuid

    async with async_session() as db:
        result = await db.execute(
            select(ConfigAnalysisRun).where(
                ConfigAnalysisRun.id == uuid.UUID(analysis_id)
            )
        )
        row = result.scalar_one_or_none()
        if not row or not row.analysis_data:
            raise ValueError("Analysis run not found or has no data")
        analysis_data = row.analysis_data

    # Build payloads (prefer cluster-based if available)
    await emit("building_payloads", 0, 0, "Building LLM payloads...")
    if analysis_data.get("clusters"):
        payloads = build_payloads_from_clusters(
            analysis_data,
            inclusions=inclusions,
            include_stats=False,  # strip stats for LLM
        )
    else:
        payloads = build_payloads(analysis_data)

    if not payloads:
        await emit("complete", 0, 0, "No payloads to generate (no analysis data)")
        return {"doc_count": 0, "docs": []}

    total = len(payloads)
    docs_generated = []

    await emit("generating", 0, total, f"Generating {total} documents...")

    for i, (doc_key, payload_data) in enumerate(payloads.items()):
        doc_name = payload_data["doc_name"]
        await emit("generating", i, total, f"Generating: {doc_name}...")

        # Pre-generation quality gate: skip docs with too-small payloads
        payload_text = payload_data.get("payload", "")
        if len(payload_text) < 100:
            logger.info(f"Skipping {doc_key}: payload too small ({len(payload_text)} chars)")
            await emit("doc_skipped", i + 1, total, f"{doc_name}: skipped (no data)")
            continue

        try:
            # Use custom system prompt if provided for this doc
            custom_prompt = (system_prompts or {}).get(doc_key)
            result = await author_doc(
                doc_key=doc_key,
                payload=payload_data["payload"],
                provider=provider,
                model=model,
                system_prompt_override=custom_prompt,
            )

            # Validate generated content
            doc_warnings = _validate_doc(doc_key, result["content"], analysis_data)
            if doc_warnings:
                logger.warning(
                    f"Doc {doc_key} validation warnings: {doc_warnings}"
                )

            # Save to DB
            doc_id = await storage.save_context_doc(
                analysis_id=analysis_id,
                user_id=user_id,
                org_id=org_id,
                doc_key=doc_key,
                doc_name=doc_name,
                doc_content=result["content"],
                model_used=result["model"],
                provider_used=result["provider"],
                system_prompt_used=result.get("system_prompt"),
                token_count=result.get("token_count"),
            )

            docs_generated.append({
                "doc_id": doc_id,
                "doc_key": doc_key,
                "doc_name": doc_name,
                "token_count": result.get("token_count", 0),
                "warnings": doc_warnings if doc_warnings else None,
            })

            warn_msg = f" ({len(doc_warnings)} warnings)" if doc_warnings else ""
            await emit(
                "doc_complete", i + 1, total,
                f"{doc_name}: {result.get('token_count', 0)} tokens{warn_msg}"
            )

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception(f"Failed to generate {doc_key}")
            await emit("doc_error", i + 1, total, f"{doc_name}: FAILED — {e}")

    await emit("complete", total, total, f"Generated {len(docs_generated)}/{total} documents")

    return {
        "doc_count": len(docs_generated),
        "docs": docs_generated,
    }
