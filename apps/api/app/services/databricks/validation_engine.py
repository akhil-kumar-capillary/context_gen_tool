"""
Async cross-document validation and patching.

Ported from reference: services/validation_engine.py
Key changes: LLM calls are async via our call_llm service.
"""

import logging
import random
from typing import Optional, Callable, Awaitable

from app.services.databricks.doc_author import (
    _call_llm_async,
    DOC_NAMES,
    SYSTEM_PROMPTS,
    TOKEN_BUDGETS,
    _cap_payload,
)

logger = logging.getLogger(__name__)

VALIDATION_PROMPT = """Review 5 context documents for an AI that generates SparkSQL from natural language.
These docs are loaded together into the AI's system prompt. Find CROSS-DOCUMENT problems only:

1. TERMINOLOGY CONFLICTS — Same concept named differently across docs
2. CONTRADICTIONS — Conflicting rules or definitions
3. COVERAGE GAPS — Business domains, tables, or patterns present in one doc but missing
   from docs that should also cover them
4. REDUNDANCY — Same content fully duplicated instead of cross-referenced
5. SYNTAX INCONSISTENCY — Same SQL pattern written differently
6. STATISTICS LEAKAGE — Any mention of query counts, usage percentages, or frequency stats

For each issue: type, docs involved, exact text, suggested fix.
If none: "PASS — all 5 docs are consistent." """


async def validate_and_patch(
    docs: dict,
    payloads: dict,
    preamble: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    system_prompts: Optional[dict] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Validate cross-doc consistency; patch affected docs if issues found."""
    prompts = system_prompts or SYSTEM_PROMPTS

    combined = "\n\n".join(
        f"{'=' * 50}\n{DOC_NAMES[k]}\n{'=' * 50}\n\n{v}"
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
            provider, model, VALIDATION_PROMPT, combined, 2000
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
    keywords = {
        "01_MASTER": ["01_MASTER", "MASTER_RULES", "Doc 1"],
        "02_SCHEMA": ["02_SCHEMA", "SCHEMA_REFERENCE", "Doc 2"],
        "03_BUSINESS": ["03_BUSINESS", "BUSINESS_MAPPINGS", "Doc 3"],
        "04_FILTERS": ["04_FILTERS", "DEFAULT_FILTERS", "Doc 4"],
        "05_PATTERNS": ["05_PATTERNS", "QUERY_PATTERNS", "Doc 5"],
    }
    to_patch = [
        k for k, kws in keywords.items()
        if any(kw.lower() in report.lower() for kw in kws)
    ]

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
        name = DOC_NAMES[key]
        budget = TOKEN_BUDGETS.get(key, 1500)

        sys_prompt = (
            preamble
            + f"\nYOUR DOC: {key} — {name}\n\n"
            + prompts[key].format(budget=budget)
        )
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
            docs[key] = await _call_llm_async(
                provider, model, sys_prompt, user_msg, budget * 2
            )
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


def spot_check(fingerprints: list, docs: dict, n: int = 20) -> float:
    """Sample random fingerprints, check if their tables appear in docs."""
    all_text = " ".join(d for d in docs.values() if d).lower()
    sample = random.sample(fingerprints, min(n, len(fingerprints)))
    hits = 0
    for fp in sample:
        tables = fp.get("tables", []) if isinstance(fp, dict) else getattr(fp, "tables", [])
        if any(t.lower() in all_text for t in tables):
            hits += 1
    pct = hits / len(sample) * 100 if sample else 0
    return pct


def check_budgets(docs: dict) -> dict:
    """Estimate tokens per doc and check against budgets."""
    results = {}
    total = 0
    for key, text in sorted(docs.items()):
        if not text:
            continue
        est = int(len(text.split()) * 1.3)
        budget = TOKEN_BUDGETS.get(key, 1500)
        status = "OVER" if est > budget * 1.2 else "ok"
        results[key] = {"estimated_tokens": est, "budget": budget, "status": status}
        total += est
    results["_total"] = {
        "estimated_tokens": total, "max": 16000,
        "status": "OVER" if total > 16000 else "ok",
    }
    return results
