"""
Document structure planner — decides if extra docs are needed beyond the core 4.

After core payloads are built, this module asks the LLM to evaluate whether
any domain is complex enough to warrant a dedicated document (split or new topic).

Replaces the old focus_doc_engine.py — extras are now planned upfront,
not assessed after generation.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Callable

from app.services.llm_service import call_llm as _llm_call
from app.services.databricks.doc_author import _cap_payload

logger = logging.getLogger(__name__)

PLAN_PROMPT = """You are a documentation architect for an AI SQL assistant.

You have 4 CORE context documents being generated:
  01_DATA_MODEL      — Custom table schemas, columns, joins
  02_FILTERS_GUARDS  — WHERE clause rules (mandatory, table-default, common)
  03_BUSINESS_LOGIC  — Metrics, code dictionaries, enums, CASE WHEN, dimensions
  04_QUERY_COOKBOOK   — Verified queries, SQL templates, patterns, conventions

Below is a SUMMARY of what each core document's payload contains (table counts, metric counts, etc.).

Your job: Decide if ANY of these conditions apply:
1. A core document's payload is so large that it should be SPLIT into domain-specific parts
   (e.g., DATA_MODEL → data_model_loyalty + data_model_analytics)
2. There is a cross-cutting business domain that needs its OWN standalone document
   (e.g., a loyalty state machine, campaign lifecycle, or scoring system that spans multiple core docs)

RULES:
- Only propose extra docs if genuinely needed. 4 docs is often sufficient.
- Each extra doc must have a clear, non-overlapping purpose.
- Extra docs should NOT duplicate content from core docs — they EXTEND or DECOMPOSE.
- Maximum 5 extra docs. Typical: 0-2.
- Each extra doc must specify which tables/topics it covers.

Respond with ONLY valid JSON:
{
  "extras_needed": true/false,
  "reason": "brief explanation",
  "extra_docs": [
    {
      "key": "05_LOYALTY_SYSTEM",
      "name": "Loyalty System Deep Dive",
      "layer": "business",
      "purpose": "End-to-end loyalty lifecycle: points, tiers, redemptions",
      "tables": ["loyalty_program", "points_*", "tier_*"],
      "data_sources": ["counters.table", "counters.column", "clusters", "classified_filters"]
    }
  ]
}

If no extras needed:
{"extras_needed": false, "reason": "4 core docs are sufficient for this data complexity"}
"""


@dataclass
class ExtraDocPlan:
    key: str
    name: str
    layer: str
    purpose: str
    tables: list[str] = field(default_factory=list)
    data_sources: list[str] = field(default_factory=list)


async def plan_extra_docs(
    payloads: dict,
    counters: dict,
    clusters: list,
    fingerprints: list,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-6",
    on_progress: Optional[Callable] = None,
) -> list[ExtraDocPlan]:
    """Ask the LLM if the data warrants extra documents beyond the core 4.

    Returns list of ExtraDocPlan (empty if 4 docs are sufficient).
    """
    if on_progress:
        await on_progress({
            "type": "llm_progress", "phase": "planning",
            "status": "started", "detail": "Evaluating document structure...",
        })

    # Build a compact summary of what's in each payload
    summary = {}
    for key, payload in payloads.items():
        stats = {}
        for k, v in payload.items():
            if isinstance(v, list):
                stats[k] = f"{len(v)} items"
            elif isinstance(v, dict):
                stats[k] = f"{len(v)} entries"
            elif isinstance(v, str):
                stats[k] = f"{len(v)} chars"
        summary[key] = stats

    # Add overall stats
    table_counter = counters.get("table", {})
    table_names = []
    if hasattr(table_counter, "most_common"):
        table_names = [str(t) for t, _ in table_counter.most_common(50)]
    elif isinstance(table_counter, dict):
        table_names = list(table_counter.keys())[:50]
    elif isinstance(table_counter, list):
        table_names = [str(t) for t, _ in table_counter[:50]]

    summary["_overview"] = {
        "total_tables": len(table_names),
        "top_tables": table_names[:30],
        "total_clusters": len(clusters),
        "total_fingerprints": len(fingerprints),
    }

    user_msg = (
        "Payload summary for the 4 core documents:\n\n"
        + json.dumps(summary, indent=2, default=str)
    )

    try:
        result = await _llm_call(
            provider=provider,
            model=model,
            system=PLAN_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
            max_tokens=2000,
        )

        response_text = ""
        for block in result.get("content", []):
            if block.get("type") == "text":
                response_text = block["text"]
                break

        # Parse JSON response
        # Strip markdown code fences if present
        clean = response_text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
            if clean.endswith("```"):
                clean = clean[:-3]
            clean = clean.strip()

        plan = json.loads(clean)

        if not plan.get("extras_needed", False):
            logger.info(f"[planner] No extra docs needed: {plan.get('reason', '')}")
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "planning",
                    "status": "done", "detail": "4 core docs are sufficient",
                })
            return []

        extras = []
        for doc in plan.get("extra_docs", []):
            extras.append(ExtraDocPlan(
                key=doc.get("key", ""),
                name=doc.get("name", ""),
                layer=doc.get("layer", ""),
                purpose=doc.get("purpose", ""),
                tables=doc.get("tables", []),
                data_sources=doc.get("data_sources", []),
            ))

        logger.info(f"[planner] {len(extras)} extra docs proposed: {[e.key for e in extras]}")
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "planning",
                "status": "done",
                "detail": f"{len(extras)} extra docs: {', '.join(e.name for e in extras)}",
            })
        return extras

    except Exception as e:
        logger.warning(f"[planner] Failed to plan extras (proceeding with core 4 only): {e}")
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "planning",
                "status": "done", "detail": "Planning failed, proceeding with core 4",
            })
        return []


def build_extra_payload(
    plan: ExtraDocPlan,
    counters: dict,
    alias_conv: dict,
    literal_vals: dict,
    fingerprints: list,
    clusters: list,
    classified_filters: list,
) -> dict:
    """Build a payload for an extra doc by filtering core data to its owned tables/topics."""
    owned_tables = set(plan.tables)

    # Filter to owned tables (prefix matching for patterns like "points_*")
    def _matches(table_name: str) -> bool:
        for pattern in owned_tables:
            if pattern.endswith("*"):
                if table_name.startswith(pattern[:-1]):
                    return True
            elif table_name == pattern:
                return True
        return False

    # Filter fingerprints to those touching owned tables
    relevant_fps = [
        fp for fp in fingerprints
        if any(_matches(t) for t in (
            fp.get("tables", []) if isinstance(fp, dict) else getattr(fp, "tables", [])
        ))
    ]

    # Filter clusters
    relevant_clusters = [
        cl for cl in clusters
        if any(_matches(t) for t in cl.get("sig", "").split("|"))
    ]

    # Filter classified_filters
    relevant_filters = [
        f for f in classified_filters
        if any(_matches(t) for t in f.get("table_pcts", {}).keys())
    ]

    return {
        "purpose": plan.purpose,
        "tables": plan.tables,
        "fingerprint_count": len(relevant_fps),
        "cluster_count": len(relevant_clusters),
        "filter_count": len(relevant_filters),
        "clusters": [
            {"sig": cl.get("sig", ""), "functions": cl.get("functions", []),
             "group_by": cl.get("group_by", [])}
            for cl in relevant_clusters[:50]
        ],
        "filters": [f.get("condition", "") for f in relevant_filters[:30]],
    }
