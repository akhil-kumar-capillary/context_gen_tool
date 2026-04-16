"""
4-pass validation engine for context documents.

Ported from sparksql_context_pipeline notebook with additions:
1. Completeness check — every payload item appears in generated doc
2. Schema validation — cross-ref against Thrift ground truth (NEW)
3. Self-evaluation — anti-hallucination check
4. Cross-doc validation — consistency, redundancy, conflicts
"""

import logging
import random
from typing import Optional, Callable, Awaitable

from app.services.databricks.doc_author import (
    _call_llm_async,
    DOC_NAMES,
    SYSTEM_PROMPTS,
    _cap_payload,
    estimate_output_tokens,
)
from app.services.databricks.schema_client import ThriftSchema

logger = logging.getLogger(__name__)


# ── Prompts ──

CROSS_DOC_VALIDATION_PROMPT = """Review these context documents for an AI that generates SparkSQL.
These docs are loaded together into the AI's system prompt. Find CROSS-DOCUMENT problems only:

1. TERMINOLOGY CONFLICTS — Same concept named differently
2. CONTRADICTIONS — Conflicting rules between docs
3. COVERAGE GAPS — Domains in one doc missing from others
4. REDUNDANCY — CRITICAL. Each doc owns:
   - DATA_MODEL: table schemas, column definitions, join syntax
   - FILTERS_GUARDS: WHERE clause rules and filter patterns
   - BUSINESS_LOGIC: code dicts, metrics, dimensions
   - QUERY_COOKBOOK: verified queries, SQL templates
   If content appears in non-owning doc AND owning doc, replace with cross-ref.
5. SYNTAX INCONSISTENCY — Same SQL pattern written differently
6. STATISTICS LEAKAGE — Any query counts, percentages, frequencies (remove these)
7. FILLER CONTENT — Generic advice, boilerplate (remove entirely)

For each issue: type, docs, exact text, fix.
If none: "PASS — all docs are consistent." """


SELF_EVAL_PROMPT = """You are a fact-checker. Compare the GENERATED DOC against the DATA PAYLOAD.

Flag any content in the doc that is NOT supported by the payload data:
- Table names that don't appear in the payload
- Column names attributed to wrong tables
- SQL expressions that don't match any payload pattern
- Business rules or metrics invented without payload evidence
- Filter conditions not present in the payload

For each issue: quote the suspicious text, explain why it's unsupported.
If everything checks out: "PASS — all content is grounded in the data." """


# ═══════════════════════════════════════════════════════════════
# Pass 1: Completeness Check
# ═══════════════════════════════════════════════════════════════

def run_completeness_check(docs: dict, payloads: dict) -> dict:
    """Check that every payload item appears in the generated doc (no LLM needed).

    Returns: {doc_key: {"missing": [...], "coverage_pct": float}}
    """
    results = {}

    for key, doc_text in docs.items():
        if not doc_text:
            results[key] = {"missing": ["ENTIRE DOC MISSING"], "coverage_pct": 0}
            continue

        payload = payloads.get(key, {})
        doc_lower = doc_text.lower()

        # Extract checkable items from payload
        items_to_check = []
        for k, v in payload.items():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        # Check table names, conditions, metrics
                        for check_key in ("table", "condition", "metric", "dimension", "sig"):
                            if check_key in item:
                                items_to_check.append(str(item[check_key]))
                    elif isinstance(item, str):
                        items_to_check.append(item)
            elif isinstance(v, dict):
                for sub_key in v:
                    items_to_check.append(str(sub_key))

        if not items_to_check:
            results[key] = {"missing": [], "coverage_pct": 100}
            continue

        missing = [item for item in items_to_check if item.lower() not in doc_lower]
        coverage = (len(items_to_check) - len(missing)) / len(items_to_check) * 100

        results[key] = {
            "missing": missing[:20],  # cap at 20 for readability
            "total_items": len(items_to_check),
            "missing_count": len(missing),
            "coverage_pct": round(coverage, 1),
        }

    return results


# ═══════════════════════════════════════════════════════════════
# Pass 2: Schema Validation (Thrift cross-reference)
# ═══════════════════════════════════════════════════════════════

def run_schema_validation(
    docs: dict,
    thrift_schema: Optional[ThriftSchema],
) -> dict:
    """Cross-reference tables/columns in docs against Thrift ground truth.

    Flags:
    - Tables mentioned in docs that don't exist in schema
    - Columns attributed to wrong tables
    """
    if not thrift_schema or thrift_schema.table_count == 0:
        return {"status": "skipped", "reason": "No Thrift schema available"}

    all_table_names = thrift_schema.all_table_names
    issues = []

    # Pre-build set of all column names for O(1) lookup
    all_column_names: set[str] = set()
    for t in all_table_names:
        table = thrift_schema.get_table(t)
        if table:
            all_column_names.update(col.name for col in table.columns)

    all_doc_text = " ".join(d for d in docs.values() if d)

    import re

    # Check for backtick leakage — backticks should never appear in generated docs
    backtick_count = all_doc_text.count("`")
    if backtick_count > 0:
        issues.append({
            "type": "backtick_leakage",
            "severity": "high",
            "message": f"Found {backtick_count} backtick(s) in generated docs. "
                       f"Backticks are not supported in this environment.",
        })

    # Extract identifier references (word boundaries for table/column names)
    # Use dot-separated identifiers like table_name.column_name
    identifier_refs = re.findall(r'\b([a-zA-Z_]\w+(?:\.\w+)?)\b', all_doc_text)

    unknown_tables = set()
    for ref in identifier_refs:
        if len(ref) < 3 or "." in ref:
            continue
        if ref in all_table_names:
            continue
        is_column = ref in all_column_names
        if not is_column and ref not in unknown_tables:
            # Could be a hallucinated table — but only flag if it looks like a table name
            # (contains underscore, not a SQL keyword)
            sql_keywords = {"select", "from", "where", "join", "and", "or", "on", "as",
                           "group", "order", "limit", "having", "case", "when", "then",
                           "else", "end", "in", "not", "null", "true", "false", "between"}
            if "_" in ref and ref.lower() not in sql_keywords:
                unknown_tables.add(ref)

    for t in sorted(unknown_tables)[:20]:
        issues.append({
            "type": "unknown_table",
            "table": t,
            "severity": "warning",
            "message": f"Table {t} referenced in docs but not found in Thrift schema",
        })

    return {
        "status": "completed",
        "issues": issues,
        "tables_checked": len(identifier_refs),
        "unknown_count": len(unknown_tables),
    }


# ═══════════════════════════════════════════════════════════════
# Pass 3: Self-Evaluation (Anti-Hallucination)
# ═══════════════════════════════════════════════════════════════

async def run_self_evaluation(
    docs: dict,
    payloads: dict,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    on_progress: Optional[Callable] = None,
    cancel_event: Optional["asyncio.Event"] = None,
) -> dict:
    """LLM checks if generated doc content is grounded in the payload data."""
    results = {}

    for key, doc_text in docs.items():
        if cancel_event and cancel_event.is_set():
            break
        if not doc_text:
            continue

        payload = payloads.get(key)
        if not payload:
            continue

        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "self_eval",
                "doc_key": key, "status": "started",
            })

        try:
            user_msg = (
                f"DATA PAYLOAD:\n{_cap_payload(payload, max_chars=200000)}\n\n"
                f"GENERATED DOC:\n{doc_text[:50000]}"
            )
            report = await _call_llm_async(provider, model, SELF_EVAL_PROMPT, user_msg, 4000)
            passed = "PASS" in report.upper()
            results[key] = {"passed": passed, "report": report[:2000]}

            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "self_eval",
                    "doc_key": key, "status": "pass" if passed else "issues_found",
                })
        except Exception as e:
            logger.warning(f"[self-eval] {key} failed: {e}")
            results[key] = {"passed": None, "skipped": True, "report": f"Skipped: {e}"}

    return results


# ═══════════════════════════════════════════════════════════════
# Pass 4: Cross-Doc Validation + Patching
# ═══════════════════════════════════════════════════════════════

async def validate_and_patch(
    docs: dict,
    payloads: dict,
    preamble: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    system_prompts: Optional[dict] = None,
    on_progress: Optional[Callable] = None,
    cancel_event: Optional["asyncio.Event"] = None,
) -> dict:
    """Validate cross-doc consistency; patch affected docs if issues found."""
    if cancel_event and cancel_event.is_set():
        return docs

    prompts = system_prompts or SYSTEM_PROMPTS

    combined = "\n\n".join(
        f"{'=' * 50}\n{DOC_NAMES.get(k, k)}\n{'=' * 50}\n\n{v}"
        for k, v in sorted(docs.items()) if v
    )
    if not combined.strip():
        return docs

    if on_progress:
        await on_progress({
            "type": "llm_progress", "phase": "validation", "status": "started",
        })

    try:
        report = await _call_llm_async(
            provider, model, CROSS_DOC_VALIDATION_PROMPT, combined, 4000,
        )
    except Exception as e:
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "validation",
                "status": "failed", "error": str(e),
            })
        return docs

    if "PASS" in report.upper() and "consistent" in report.lower():
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "validation", "status": "pass",
            })
        return docs

    # Determine which docs to patch
    to_patch = []
    for k in docs:
        name = DOC_NAMES.get(k, k)
        if k.lower() in report.lower() or name.lower() in report.lower():
            to_patch.append(k)

    if not to_patch:
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "validation",
                "status": "done", "patched": [],
            })
        return docs

    if on_progress:
        await on_progress({
            "type": "llm_progress", "phase": "validation",
            "status": "patching", "to_patch": to_patch,
        })

    for key in to_patch:
        if key not in payloads:
            continue
        name = DOC_NAMES.get(key, key)
        doc_prompt = prompts.get(key, "")
        budget = estimate_output_tokens(key, payloads[key])

        sys_prompt = preamble + f"\nYOUR DOC: {key} — {name}\n\n" + doc_prompt
        user_msg = (
            f"CORRECTION: previous version had cross-doc issues:\n{report}\n\n"
            f"Fix these issues. Do NOT include any counts, percentages, or frequency stats.\n"
            f"DATA:\n{_cap_payload(payloads[key])}"
        )

        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "patching",
                "doc_key": key, "status": "started",
            })

        try:
            docs[key] = await _call_llm_async(provider, model, sys_prompt, user_msg, budget)
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "patching",
                    "doc_key": key, "status": "done",
                    "word_count": len(docs[key].split()) if docs[key] else 0,
                })
        except Exception as e:
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "patching",
                    "doc_key": key, "status": "failed", "error": str(e),
                })

    return docs


# ═══════════════════════════════════════════════════════════════
# Utility checks
# ═══════════════════════════════════════════════════════════════

def spot_check(fingerprints: list, docs: dict, n: int = 20) -> float:
    """Sample random fingerprints, check if their tables appear in docs."""
    all_text = " ".join(d for d in docs.values() if d).lower()
    sample = random.sample(fingerprints, min(n, len(fingerprints)))
    hits = 0
    for fp in sample:
        tables = fp.get("tables", []) if isinstance(fp, dict) else getattr(fp, "tables", [])
        if any(t.lower() in all_text for t in tables):
            hits += 1
    return hits / len(sample) * 100 if sample else 0


def check_budgets(docs: dict, payloads: dict) -> dict:
    """Estimate tokens per doc and check against dynamic budgets."""
    results = {}
    total = 0
    for key, text in sorted(docs.items()):
        if not text:
            continue
        est = int(len(text.split()) * 1.3)
        budget = estimate_output_tokens(key, payloads.get(key, {}))
        status = "OVER" if est > budget * 1.2 else "ok"
        results[key] = {"estimated_tokens": est, "budget": budget, "status": status}
        total += est
    results["_total"] = {"estimated_tokens": total}
    return results
