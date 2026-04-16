"""
Async document generation orchestrator — 10-step pipeline.

Replaces the old 5-doc pipeline with:
  load → Thrift schema → enrichment → payloads → plan extras →
  author all docs → index → validate → save.

4 core docs (DATA_MODEL, FILTERS_GUARDS, BUSINESS_LOGIC, QUERY_COOKBOOK)
+ LLM-planned extra docs when data complexity warrants it.
"""

import logging
from typing import Optional, Callable, Awaitable
from collections import Counter

from app.services.databricks.storage import StorageService
from app.services.databricks.schema_client import fetch_thrift_schema, ThriftSchema
from app.services.databricks.enrichment import run_all_enrichments
from app.services.databricks.payload_builder import build_all_payloads
from app.services.databricks.doc_author import (
    author_docs, build_preamble, build_index_document,
    DOC_NAMES, SYSTEM_PROMPTS, CORE_DOC_KEYS, _cap_payload,
)
from app.services.databricks.doc_planner import plan_extra_docs, build_extra_payload
from app.services.databricks.validation_engine import (
    run_completeness_check, run_schema_validation,
    run_self_evaluation, validate_and_patch,
    spot_check, check_budgets,
)

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[dict], Awaitable[None]]


def _reconstruct_counters(counters_json: dict) -> dict:
    """Reconstruct Counter objects from the stored JSON format.

    The analysis orchestrator stores counters via counters_to_serializable(),
    which converts Counter → list of [key, count] pairs.
    """
    counters = {}
    for key, val in counters_json.items():
        if isinstance(val, list):
            c = Counter()
            for item in val:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    k, n = item
                    if isinstance(k, list):
                        k = tuple(k)
                    c[k] = n
            counters[key] = c
        elif isinstance(val, dict):
            counters[key] = Counter(val)
        else:
            counters[key] = val
    return counters


async def run_generation(
    analysis_id: str,
    user_id: int,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    model_map: Optional[dict] = None,
    system_prompts: Optional[dict] = None,
    skip_validation: bool = False,
    capillary_token: Optional[str] = None,
    base_url: Optional[str] = None,
    org_id_for_schema: Optional[str] = None,
    on_progress: Optional[ProgressCallback] = None,
) -> dict:
    """Run the full 10-step document generation pipeline.

    Args:
        analysis_id: Analysis run UUID.
        user_id: User running the generation.
        provider: LLM provider.
        model: Default LLM model.
        model_map: Optional per-doc model overrides.
        system_prompts: Optional custom system prompts.
        skip_validation: Skip validation passes.
        capillary_token: Capillary auth token for Thrift API (from JWT).
        base_url: Capillary Intouch base URL (from JWT/config).
        org_id_for_schema: Org ID for Thrift schema fetch.
        on_progress: Async callback for progress events.
    """
    storage = StorageService()

    async def emit(event: dict):
        if on_progress:
            await on_progress(event)

    try:
        # ══════════════════════════════════════════════════════
        # Step 1: Load analysis data
        # ══════════════════════════════════════════════════════
        await emit({"type": "llm_progress", "phase": "loading", "status": "started"})

        analysis = await storage.get_analysis_run(analysis_id)
        if not analysis:
            raise ValueError(f"Analysis run not found: {analysis_id}")

        org_id = analysis.get("org_id")
        run_id = analysis.get("run_id")

        counters_json = analysis.get("counters", {})
        clusters = analysis.get("clusters", [])
        classified_filters = analysis.get("classified_filters", {})
        literal_vals_raw = analysis.get("literal_vals", {})
        alias_conv_raw = analysis.get("alias_conv", {})
        total_weight = analysis.get("total_weight", 0)

        counters = _reconstruct_counters(counters_json)

        # Reconstruct literal_vals
        literal_vals = {}
        for col, pairs in literal_vals_raw.items():
            if isinstance(pairs, list):
                literal_vals[col] = {str(v): n for v, n in pairs}
            elif isinstance(pairs, dict):
                literal_vals[col] = pairs
            else:
                literal_vals[col] = {}

        # Reconstruct alias_conv
        alias_conv = {}
        for tbl, pairs in alias_conv_raw.items():
            if isinstance(pairs, list):
                alias_conv[tbl] = {str(a): n for a, n in pairs}
            elif isinstance(pairs, dict):
                alias_conv[tbl] = pairs
            else:
                alias_conv[tbl] = {}

        # Load fingerprints
        fingerprints, total_fp = await storage.get_analysis_fingerprints(
            analysis_id, limit=5000, offset=0,
        )

        # Ensure classified_filters is a list
        if isinstance(classified_filters, dict):
            classified_filters = []

        await emit({
            "type": "llm_progress", "phase": "loading", "status": "done",
            "fingerprint_count": len(fingerprints),
            "cluster_count": len(clusters),
            "total_weight": total_weight,
        })

        # ══════════════════════════════════════════════════════
        # Step 2: Fetch Thrift schema (ground truth)
        # ══════════════════════════════════════════════════════
        thrift_schema: Optional[ThriftSchema] = None
        schema_org = org_id_for_schema or org_id

        if capillary_token and base_url and schema_org:
            await emit({
                "type": "llm_progress", "phase": "schema",
                "status": "started", "detail": f"Fetching schema for org {schema_org}...",
            })
            try:
                thrift_schema = await fetch_thrift_schema(base_url, capillary_token, schema_org)
                await emit({
                    "type": "llm_progress", "phase": "schema", "status": "done",
                    "detail": f"{thrift_schema.table_count} tables, {thrift_schema.column_count} columns",
                })
            except Exception as e:
                logger.warning(f"Thrift schema fetch failed (proceeding without): {e}")
                await emit({
                    "type": "llm_progress", "phase": "schema",
                    "status": "skipped", "detail": f"Schema fetch failed: {e}",
                })
        else:
            await emit({
                "type": "llm_progress", "phase": "schema",
                "status": "skipped", "detail": "No Capillary credentials for schema fetch",
            })

        # ══════════════════════════════════════════════════════
        # Step 3: Run enrichment passes
        # ══════════════════════════════════════════════════════
        await emit({
            "type": "llm_progress", "phase": "enrichment", "status": "started",
        })

        enrichment_data = run_all_enrichments(
            fingerprints=fingerprints,
            counters=counters,
            clusters=clusters,
            classified_filters=classified_filters,
            literal_vals=literal_vals,
            thrift_schema=thrift_schema,
        )

        await emit({
            "type": "llm_progress", "phase": "enrichment", "status": "done",
            "detail": (
                f"{len(enrichment_data.get('enriched_metrics', []))} metrics, "
                f"{len(enrichment_data.get('verified_queries', []))} queries, "
                f"{len(enrichment_data.get('synonyms', {}))} synonyms, "
                f"{len(enrichment_data.get('pitfalls', []))} pitfalls"
            ),
        })

        # ══════════════════════════════════════════════════════
        # Step 4: Build 4 core payloads
        # ══════════════════════════════════════════════════════
        await emit({"type": "llm_progress", "phase": "payloads", "status": "started"})

        payloads = build_all_payloads(
            counters=counters,
            alias_conv=alias_conv,
            literal_vals=literal_vals,
            fingerprints=fingerprints,
            clusters=clusters,
            classified_filters=classified_filters,
            total_weight=total_weight,
            thrift_schema=thrift_schema,
            enrichment_data=enrichment_data,
        )

        await emit({"type": "llm_progress", "phase": "payloads", "status": "done"})

        # ══════════════════════════════════════════════════════
        # Step 5: Structure planning pass
        # ══════════════════════════════════════════════════════
        extra_plans = await plan_extra_docs(
            payloads=payloads,
            counters=counters,
            clusters=clusters,
            fingerprints=fingerprints,
            provider=provider,
            model=model_map.get("planning", "claude-sonnet-4-6") if model_map else "claude-sonnet-4-6",
            on_progress=on_progress,
        )

        # ══════════════════════════════════════════════════════
        # Step 6: Build extra doc payloads (if any)
        # ══════════════════════════════════════════════════════
        # Local copy to avoid mutating global DOC_NAMES
        doc_names = dict(DOC_NAMES)
        for plan in extra_plans:
            extra_payload = build_extra_payload(
                plan, counters, alias_conv, literal_vals,
                fingerprints, clusters, classified_filters,
            )
            payloads[plan.key] = extra_payload
            doc_names[plan.key] = plan.name

        # ══════════════════════════════════════════════════════
        # Step 7: Author all docs (core 4 + extras)
        # ══════════════════════════════════════════════════════
        column_freq = counters.get("column", Counter()).most_common() if isinstance(counters.get("column"), Counter) else counters.get("column", [])
        preamble = build_preamble(column_freq)

        docs = await author_docs(
            payloads=payloads,
            preamble=preamble,
            provider=provider,
            model=model,
            model_map=model_map,
            system_prompts=system_prompts,
            on_progress=on_progress,
        )

        # ══════════════════════════════════════════════════════
        # Step 8: Generate 00_INDEX document
        # ══════════════════════════════════════════════════════
        index_doc = build_index_document(docs, payloads)
        docs["00_INDEX"] = index_doc
        doc_names["00_INDEX"] = "00_INDEX"

        # ══════════════════════════════════════════════════════
        # Step 9: Validation (4 passes)
        # ══════════════════════════════════════════════════════
        validation_results = {}

        if not skip_validation:
            # Pass 1: Completeness
            await emit({"type": "llm_progress", "phase": "validation", "status": "completeness"})
            completeness = run_completeness_check(docs, payloads)
            validation_results["completeness"] = completeness

            # Pass 2: Schema validation
            schema_check = run_schema_validation(docs, thrift_schema)
            validation_results["schema"] = schema_check

            # Pass 3: Self-evaluation (anti-hallucination)
            await emit({"type": "llm_progress", "phase": "validation", "status": "self_eval"})
            self_eval = await run_self_evaluation(
                docs, payloads,
                provider=provider,
                model=model_map.get("validation", "claude-sonnet-4-6") if model_map else "claude-sonnet-4-6",
                on_progress=on_progress,
            )
            validation_results["self_eval"] = self_eval

            # Pass 4: Cross-doc validation + patching
            await emit({"type": "llm_progress", "phase": "validation", "status": "cross_doc"})
            docs = await validate_and_patch(
                docs, payloads, preamble,
                provider=provider,
                model=model_map.get("validation", model) if model_map else model,
                system_prompts=system_prompts,
                on_progress=on_progress,
            )

        # Quality checks
        spot_pct = spot_check(fingerprints, docs) if fingerprints else 0
        budget_check = check_budgets(docs, payloads)

        # ══════════════════════════════════════════════════════
        # Step 10: Save all docs
        # ══════════════════════════════════════════════════════
        await emit({"type": "llm_progress", "phase": "saving", "status": "started"})

        saved_docs = []
        for key, text in docs.items():
            if not text:
                continue

            source_run_id = run_id if run_id else analysis_id
            doc_id = await storage.save_context_doc(
                source_type="databricks",
                source_run_id=source_run_id,
                user_id=user_id,
                org_id=org_id,
                doc_key=key,
                doc_name=doc_names.get(key, key),
                doc_content=text,
                model_used=model_map.get(key, model) if model_map else model,
                provider_used=provider,
                system_prompt_used=SYSTEM_PROMPTS.get(key, "")[:500],
                payload_sent=payloads.get(key),
                inclusions_used=None,
                token_count=int(len(text.split()) * 1.3),
            )
            saved_docs.append({
                "id": doc_id, "key": key, "name": doc_names.get(key, key),
                "word_count": len(text.split()),
            })

        await emit({
            "type": "llm_progress", "phase": "saving", "status": "done",
            "doc_count": len(saved_docs),
        })

        core_count = sum(1 for d in saved_docs if d["key"] in CORE_DOC_KEYS or d["key"] == "00_INDEX")
        extra_count = len(saved_docs) - core_count

        return {
            "analysis_id": analysis_id,
            "doc_count": len(saved_docs),
            "core_doc_count": core_count,
            "extra_doc_count": extra_count,
            "docs": saved_docs,
            "validation": validation_results,
            "spot_check_pct": round(spot_pct, 1),
            "budget_check": budget_check,
            "thrift_schema_available": thrift_schema is not None,
        }

    except Exception as e:
        logger.exception(f"Document generation failed: {e}")
        await emit({
            "type": "llm_progress", "phase": "error",
            "status": "failed", "error": str(e),
        })
        raise


async def preview_payloads(
    analysis_id: str,
    capillary_token: Optional[str] = None,
    base_url: Optional[str] = None,
    org_id_for_schema: Optional[str] = None,
) -> dict:
    """Build payloads without calling LLM — for preview/debugging."""
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
    literal_vals = {col: ({str(v): n for v, n in pairs} if isinstance(pairs, list) else pairs if isinstance(pairs, dict) else {}) for col, pairs in literal_vals_raw.items()}
    alias_conv = {tbl: ({str(a): n for a, n in pairs} if isinstance(pairs, list) else pairs if isinstance(pairs, dict) else {}) for tbl, pairs in alias_conv_raw.items()}

    fingerprints, _ = await storage.get_analysis_fingerprints(analysis_id, limit=5000, offset=0)

    if isinstance(classified_filters, dict):
        classified_filters = []

    # Thrift schema
    thrift_schema = None
    schema_org = org_id_for_schema or analysis.get("org_id")
    if capillary_token and base_url and schema_org:
        try:
            thrift_schema = await fetch_thrift_schema(base_url, capillary_token, schema_org)
        except Exception:
            pass

    # Enrichment
    enrichment_data = run_all_enrichments(
        fingerprints=fingerprints, counters=counters, clusters=clusters,
        classified_filters=classified_filters, literal_vals=literal_vals,
        thrift_schema=thrift_schema,
    )

    # Payloads
    payloads = build_all_payloads(
        counters=counters, alias_conv=alias_conv, literal_vals=literal_vals,
        fingerprints=fingerprints, clusters=clusters,
        classified_filters=classified_filters, total_weight=total_weight,
        thrift_schema=thrift_schema, enrichment_data=enrichment_data,
    )

    return {
        "payloads": {k: {"item_count": sum(len(v) if isinstance(v, list) else len(v) if isinstance(v, dict) else 0 for v in p.values()), "keys": list(p.keys())} for k, p in payloads.items()},
        "enrichment_summary": {
            "metrics": len(enrichment_data.get("enriched_metrics", [])),
            "verified_queries": len(enrichment_data.get("verified_queries", [])),
            "synonyms": len(enrichment_data.get("synonyms", {})),
            "pitfalls": len(enrichment_data.get("pitfalls", [])),
            "correctness_criteria": len(enrichment_data.get("correctness_criteria", [])),
            "business_evidence": len(enrichment_data.get("business_evidence", [])),
        },
        "thrift_schema_available": thrift_schema is not None,
        "thrift_tables": thrift_schema.table_count if thrift_schema else 0,
    }
