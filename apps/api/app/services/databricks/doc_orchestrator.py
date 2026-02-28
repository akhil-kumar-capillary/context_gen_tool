"""
Async document generation orchestrator.

New file (no direct reference equivalent) — ties together:
  load analysis → build payloads → author 5 docs → validate → focus docs → save.
"""

import logging
from typing import Optional, Callable, Awaitable

from app.services.databricks.storage import StorageService
from app.services.databricks.payload_builder import build_all_payloads
from app.services.databricks.doc_author import (
    author_docs,
    build_preamble,
    DOC_NAMES,
    SYSTEM_PROMPTS,
    TOKEN_BUDGETS,
    _cap_payload,
)
from app.services.databricks.validation_engine import (
    validate_and_patch,
    spot_check,
    check_budgets,
)
from app.services.databricks.focus_doc_engine import assess_and_author_focus_docs

logger = logging.getLogger(__name__)

# Type alias for progress callback (dict-based for flexible event shapes)
ProgressCallback = Callable[[dict], Awaitable[None]]


async def run_generation(
    analysis_id: str,
    user_id: int,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    model_map: Optional[dict] = None,
    system_prompts: Optional[dict] = None,
    inclusions: Optional[dict] = None,
    focus_domains: Optional[list] = None,
    skip_validation: bool = False,
    skip_focus_docs: bool = False,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """
    Run the full document generation pipeline for a completed analysis.

    Args:
        analysis_id: Analysis run UUID.
        user_id: User running the generation.
        provider: LLM provider ("anthropic" or "openai").
        model: Default model name.
        model_map: Optional per-doc model override {doc_key: model_name}.
        system_prompts: Optional custom system prompts per doc.
        inclusions: Optional inclusion overrides per doc (controls what data appears in payloads).
        focus_domains: Optional filter for focus doc topic selection.
        skip_validation: Skip cross-doc validation + patching step.
        skip_focus_docs: Skip focus doc assessment + generation.
        on_progress: async callback(event_dict) for real-time progress updates.

    Returns:
        dict with: doc_count, focus_doc_count, validation_status, budget_check,
                   spot_check_pct, docs (list of doc metadata)
    """
    storage = StorageService()

    async def emit(event: dict):
        if on_progress:
            await on_progress(event)

    try:
        # ── Step 1: Load analysis data ──
        await emit({"type": "llm_progress", "phase": "loading", "status": "started"})

        analysis = await storage.get_analysis_run(analysis_id)
        if not analysis:
            raise ValueError(f"Analysis run not found: {analysis_id}")

        org_id = analysis.get("org_id")
        run_id = analysis.get("run_id")

        # Load stored analysis artifacts
        counters_json = analysis.get("counters", {})
        clusters = analysis.get("clusters", [])
        classified_filters = analysis.get("classified_filters", {})
        literal_vals_raw = analysis.get("literal_vals", {})
        alias_conv_raw = analysis.get("alias_conv", {})
        total_weight = analysis.get("total_weight", 0)

        # Reconstruct counters from stored JSON format
        # The analysis orchestrator stores counters via counters_to_serializable(),
        # which converts Counter → list of [key, count] pairs.
        counters = _reconstruct_counters(counters_json)

        # Reconstruct literal_vals: stored as {col: [[v, n], ...]} → {col: {v: n, ...}}
        literal_vals = {}
        for col, pairs in literal_vals_raw.items():
            if isinstance(pairs, list):
                literal_vals[col] = {str(v): n for v, n in pairs}
            elif isinstance(pairs, dict):
                literal_vals[col] = pairs
            else:
                literal_vals[col] = {}

        # Reconstruct alias_conv: stored as {table: [[alias, n], ...]} → {table: {alias: n, ...}}
        alias_conv = {}
        for tbl, pairs in alias_conv_raw.items():
            if isinstance(pairs, list):
                alias_conv[tbl] = {str(a): n for a, n in pairs}
            elif isinstance(pairs, dict):
                alias_conv[tbl] = pairs
            else:
                alias_conv[tbl] = {}

        # Load fingerprints from the analysis (we need them for payload building)
        fingerprints, total_fp = await storage.get_analysis_fingerprints(
            analysis_id, limit=5000, offset=0
        )

        await emit({
            "type": "llm_progress", "phase": "loading", "status": "done",
            "fingerprint_count": len(fingerprints),
            "cluster_count": len(clusters),
            "total_weight": total_weight,
        })

        # ── Step 2: Build payloads ──
        await emit({"type": "llm_progress", "phase": "payloads", "status": "started"})

        payloads = build_all_payloads(
            counters=counters,
            alias_conv=alias_conv,
            literal_vals=literal_vals,
            fingerprints=fingerprints,
            clusters=clusters,
            classified_filters=classified_filters if isinstance(classified_filters, list) else [],
            total_weight=total_weight,
            inclusions=inclusions,
        )

        await emit({"type": "llm_progress", "phase": "payloads", "status": "done"})

        # ── Step 3: Build preamble ──
        column_freq = counters.get("column", [])
        preamble = build_preamble(column_freq)

        # ── Step 4: Author 5 core documents via LLM ──
        docs = await author_docs(
            payloads=payloads,
            preamble=preamble,
            provider=provider,
            model=model,
            model_map=model_map,
            system_prompts=system_prompts,
            on_progress=on_progress,
        )

        authored_count = sum(1 for v in docs.values() if v)
        if authored_count == 0:
            raise RuntimeError("All 5 documents failed to generate")

        # ── Step 5: Cross-document validation + patching ──
        validation_status = "skipped"
        if not skip_validation and authored_count == 5:
            docs = await validate_and_patch(
                docs=docs,
                payloads=payloads,
                preamble=preamble,
                provider=provider,
                model=model,
                system_prompts=system_prompts,
                on_progress=on_progress,
            )
            validation_status = "done"

        # ── Step 6: Focus docs ──
        focus_docs = {}
        if not skip_focus_docs and authored_count >= 3:
            focus_docs = await assess_and_author_focus_docs(
                docs=docs,
                fingerprints=fingerprints,
                counters=counters,
                clusters=clusters,
                literal_vals=literal_vals,
                classified_filters=classified_filters if isinstance(classified_filters, list) else [],
                alias_conv=alias_conv,
                preamble=preamble,
                provider=provider,
                model=model,
                focus_domains=focus_domains,
                on_progress=on_progress,
            )

        # ── Step 7: Quality checks ──
        spot_pct = spot_check(fingerprints, docs) if fingerprints else 0.0
        budgets = check_budgets(docs)

        # Merge focus docs into main docs dict
        all_docs = {**docs, **focus_docs}

        # ── Step 8: Save to database ──
        await emit({"type": "llm_progress", "phase": "saving", "status": "started"})

        saved_docs = []
        for doc_key, content in sorted(all_docs.items()):
            if not content:
                continue

            is_focus = doc_key.startswith("06_") or doc_key.startswith("07_") or doc_key.startswith("08_")
            doc_name = DOC_NAMES.get(doc_key, doc_key)
            est_tokens = int(len(content.split()) * 1.3)

            doc_record = {
                "doc_key": doc_key,
                "doc_name": doc_name,
                "doc_content": content,
                "model_used": (model_map or {}).get(doc_key, model),
                "provider_used": provider,
                "system_prompt_used": (system_prompts or SYSTEM_PROMPTS).get(doc_key, ""),
                "payload_sent": payloads.get(doc_key, {}),
                "inclusions_used": (inclusions or {}).get(doc_key, {}),
                "token_count": est_tokens,
            }

            await storage.save_context_doc(analysis_id, org_id, user_id, doc_record)
            saved_docs.append({
                "doc_key": doc_key,
                "doc_name": doc_name,
                "word_count": len(content.split()),
                "est_tokens": est_tokens,
                "is_focus": is_focus,
            })

        await emit({
            "type": "llm_progress", "phase": "saving", "status": "done",
            "doc_count": len(saved_docs),
        })

        await emit({
            "type": "llm_progress", "phase": "complete", "status": "done",
            "doc_count": len(saved_docs),
            "focus_doc_count": len(focus_docs),
        })

        return {
            "analysis_id": analysis_id,
            "org_id": org_id,
            "doc_count": authored_count,
            "focus_doc_count": len(focus_docs),
            "validation_status": validation_status,
            "spot_check_pct": round(spot_pct, 1),
            "budget_check": budgets,
            "docs": saved_docs,
        }

    except Exception as e:
        logger.exception(f"Document generation failed: {e}")
        await emit({
            "type": "llm_progress", "phase": "generation",
            "status": "failed", "error": str(e),
        })
        raise


def _reconstruct_counters(counters_json: dict) -> dict:
    """Reconstruct counters from the serialized JSON stored in the database.

    The analysis orchestrator saves counters via `counters_to_serializable()`,
    which converts each Counter to a list of [key, count] tuples.
    The payload builders expect dicts with lists of (key, count) tuples (Counter.most_common() format).

    NOTE: counters_to_serializable() also embeds "literal_vals" and "alias_conv"
    as nested dicts — those are handled separately in run_generation() and must
    be skipped here (their values are dicts-of-lists, not flat [key, count] pairs).
    """
    # Keys that have nested structure and are handled separately
    _NESTED_KEYS = {"literal_vals", "alias_conv"}

    result = {}
    for counter_name, entries in counters_json.items():
        if counter_name in _NESTED_KEYS:
            continue
        if isinstance(entries, list):
            # Already in [[key, count], ...] format — convert to list of tuples
            result[counter_name] = [(item[0], item[1]) for item in entries if len(item) >= 2]
        elif isinstance(entries, dict):
            # Dict format — convert to sorted list of tuples
            # Ensure values are numeric before negating for sort
            result[counter_name] = sorted(
                ((k, v) for k, v in entries.items() if isinstance(v, (int, float))),
                key=lambda x: -x[1],
            )
        else:
            result[counter_name] = []
    return result


async def preview_payloads(
    analysis_id: str,
    inclusions: Optional[dict] = None,
) -> dict:
    """Build and return payloads without calling LLM. Useful for preview/inspection."""
    storage = StorageService()

    analysis = await storage.get_analysis_run(analysis_id)
    if not analysis:
        raise ValueError(f"Analysis run not found: {analysis_id}")

    counters_json = analysis.get("counters", {})
    clusters = analysis.get("clusters", [])
    classified_filters = analysis.get("classified_filters", {})
    literal_vals_raw = analysis.get("literal_vals", {})
    alias_conv_raw = analysis.get("alias_conv", {})
    total_weight = analysis.get("total_weight", 0)

    counters = _reconstruct_counters(counters_json)

    literal_vals = {}
    for col, pairs in literal_vals_raw.items():
        if isinstance(pairs, list):
            literal_vals[col] = {str(v): n for v, n in pairs}
        elif isinstance(pairs, dict):
            literal_vals[col] = pairs
        else:
            literal_vals[col] = {}

    alias_conv = {}
    for tbl, pairs in alias_conv_raw.items():
        if isinstance(pairs, list):
            alias_conv[tbl] = {str(a): n for a, n in pairs}
        elif isinstance(pairs, dict):
            alias_conv[tbl] = pairs
        else:
            alias_conv[tbl] = {}

    fingerprints, _ = await storage.get_analysis_fingerprints(
        analysis_id, limit=5000, offset=0
    )

    payloads = build_all_payloads(
        counters=counters,
        alias_conv=alias_conv,
        literal_vals=literal_vals,
        fingerprints=fingerprints,
        clusters=clusters,
        classified_filters=classified_filters if isinstance(classified_filters, list) else [],
        total_weight=total_weight,
        inclusions=inclusions,
    )

    # Include preamble preview
    column_freq = counters.get("column", [])
    preamble = build_preamble(column_freq)

    # Estimate payload sizes
    sizes = {}
    for key, payload in payloads.items():
        text = _cap_payload(payload)
        sizes[key] = {"chars": len(text), "est_tokens": int(len(text.split()) * 1.3)}

    return {
        "payloads": payloads,
        "preamble": preamble,
        "payload_sizes": sizes,
        "total_weight": total_weight,
        "fingerprint_count": len(fingerprints),
    }
