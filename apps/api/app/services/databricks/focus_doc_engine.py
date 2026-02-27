"""
Async focus doc assessment and generation.

Ported from reference: services/focus_doc_engine.py
Key changes: LLM calls are async via our call_llm service.
"""

import json
import logging
from typing import Optional, Callable, Awaitable

from app.config import settings
from app.services.databricks.doc_author import (
    _call_llm_async,
    DOC_NAMES,
    _cap_payload,
)

logger = logging.getLogger(__name__)


FOCUS_ASSESSMENT_PROMPT_TEMPLATE = """You have just reviewed 5 context documents created from a SQL query corpus.
Your job is to decide if any ADDITIONAL standalone documents are needed.

The 5 core docs already cover: SQL rules, table schemas, business mappings, default filters,
and query patterns. Most topics belong in one of these.

A focus doc is ONLY needed when a topic is:
- Too complex to fit in a section
- Cross-cutting in a way the 5 docs can't capture
- Structurally unique (e.g., a scoring/simulation system, a state machine)

A focus doc is NOT needed for:
- A domain that just has many tables — the core docs handle that
- Simple deep-dives that are just "more detail on X"
- Topics already well-covered across the 5 docs

Review the core docs below and the data summary. Respond with ONLY valid JSON:

If NO focus docs needed:
{{"focus_docs": []}}

If focus docs ARE needed (max {max_focus_docs}):
{{"focus_docs": [
  {{"title": "Short descriptive title",
    "reason": "One sentence on why this can't fit in the 5 core docs",
    "tables": ["table1", "table2"],
    "key_concepts": ["concept1", "concept2"]}}
]}}

Respond ONLY with JSON, no other text."""


FOCUS_DOC_PROMPT = """Write a standalone context document about: "{title}"

This document exists because this topic is too complex or cross-cutting to be
adequately covered within the 5 core context documents.

Reason this doc was created: {reason}

MANDATORY OPENING: The document MUST begin with a 2-4 sentence description in the
first 100-200 characters. This description must explain:
(a) What this document contains
(b) When the AI should load/refer to this document
(c) What types of user questions this document helps answer
This description acts as a retrieval hint — it helps the system decide when to load
this context. It must be the VERY FIRST content in the document, before any sections.

NEVER mention query counts, percentages, or how often something is used.
Write as an authoritative, self-contained guide.

Focus specifically on:
- How this system/process/concept WORKS end-to-end
- The tables involved and how they connect for THIS specific purpose
- The business logic, state transitions, or workflows specific to this topic
- Complete SQL templates for key scenarios within this topic
- Filters and conditions specific to this context
- Edge cases and gotchas an AI would need to know

SECTIONS:
1. Overview — What this is and why it needs dedicated documentation
2. How It Works — End-to-end explanation
3. Data Model — Tables, columns, and joins specific to this topic
4. Business Logic — Codes, statuses, CASE WHEN, state transitions
5. Query Templates — Complete runnable SparkSQL for key scenarios
6. Cross-References — How this connects to concepts in the core docs

Budget: {budget} tokens."""


def _build_assessment_input(
    docs: dict, counters: dict, literal_vals: dict, clusters: list,
) -> str:
    """Build a compact summary of core docs + data highlights."""
    doc_summary = "\n\n".join(
        f"--- {k} ---\n{v[:500]}..." for k, v in sorted(docs.items()) if v
    )

    table_items = counters.get("table", [])
    top_tables = [str(t) for t, _ in table_items[:30]]

    complex_clusters = [
        cl for cl in clusters
        if cl.get("n_unique", 0) >= 5 and len(cl.get("sig", "").split("|")) >= 3
    ][:10]

    enum_cols = [
        col for col, vc in literal_vals.items()
        if (isinstance(vc, list) and 5 <= len(vc) <= settings.max_enum_distinct)
        or (isinstance(vc, dict) and 5 <= len(vc) <= settings.max_enum_distinct)
    ]

    structural = dict(counters.get("structural", []))

    highlights = {
        "all_tables": top_tables,
        "complex_multi_table_patterns": [
            {"tables": cl.get("sig", ""), "query_count": cl.get("count", 0)}
            for cl in complex_clusters
        ],
        "enum_columns": enum_cols[:20],
        "structural_features": structural,
    }

    return (
        f"CORE DOCS (summaries):\n{doc_summary}\n\n"
        f"DATA HIGHLIGHTS:\n{json.dumps(highlights, indent=2, default=str)}"
    )


def _build_focus_payload(
    topic: dict, fingerprints: list, counters: dict, clusters: list,
    literal_vals: dict, classified_filters: list, alias_conv: dict,
) -> dict:
    """Build a focused payload for one topic."""
    tables = set(topic.get("tables", []))

    for cl in clusters:
        cl_tables = set(cl.get("sig", "").split("|"))
        if cl_tables.intersection(tables) and len(cl_tables) <= 6:
            tables.update(cl_tables)

    column_items = counters.get("column", [])
    join_pair_items = counters.get("join_pair", [])
    join_cond_items = counters.get("join_cond", [])
    table_counter = dict(counters.get("table", []))

    schema = []
    for t in sorted(tables):
        tc = table_counter.get(t, 0)
        if tc == 0:
            continue
        cols = []
        for entry, n in column_items:
            entry_str = str(entry)
            tb = entry_str.split(".", 1)[0] if "." in entry_str else "?"
            if tb == t:
                col = entry_str.split(".", 1)[-1] if "." in entry_str else entry_str
                cols.append({"col": col, "n": n})
                if len(cols) >= 25:
                    break
        raw_aliases = alias_conv.get(t, [])
        if isinstance(raw_aliases, list):
            aliases = [a for a, _ in raw_aliases[:3]]
        elif isinstance(raw_aliases, dict):
            aliases = list(raw_aliases.keys())[:3]
        else:
            aliases = []
        schema.append({"table": t, "columns": cols, "aliases": aliases})

    joins = []
    for pair, n in join_pair_items:
        pair_str = str(pair)
        parts = pair_str.split("|") if "|" in pair_str else [pair_str]
        if len(parts) < 2:
            continue
        if parts[0] in tables or parts[1] in tables:
            conds = []
            for cond_entry, c in join_cond_items:
                cond_str = str(cond_entry)
                if parts[0] in cond_str and parts[1] in cond_str:
                    conds.append({"on": cond_str, "n": c})
                    if len(conds) >= 3:
                        break
            joins.append({"a": parts[0], "b": parts[1], "on": conds})
            if len(joins) >= 15:
                break

    patterns = []
    for cl in clusters:
        cl_tables = set(cl.get("sig", "").split("|"))
        if not cl_tables.intersection(tables):
            continue
        patterns.append({
            "sig": cl.get("sig", ""),
            "count": cl.get("count", 0),
            "functions": cl.get("functions", []),
            "group_by": cl.get("group_by", []),
            "rep_sql": cl.get("rep_sql", "")[:800],
            "cpx_sql": cl.get("cpx_sql", "")[:1200],
        })
        if len(patterns) >= 20:
            break

    filters = []
    for f in classified_filters:
        if any(t in f.get("table_pcts", {}) for t in tables):
            filters.append({"cond": f["condition"], "tier": f["tier"]})
            if len(filters) >= 25:
                break

    enums = {}
    for col, vc in literal_vals.items():
        vals = vc if isinstance(vc, list) else list(vc.items()) if isinstance(vc, dict) else []
        if len(vals) <= settings.max_enum_distinct:
            if isinstance(vc, list):
                enums[col] = [{"v": v, "n": n} for v, n in vc[:20]]
            elif isinstance(vc, dict):
                safe_items = [(v, n) for v, n in vc.items() if isinstance(n, (int, float))]
                enums[col] = [{"v": v, "n": n} for v, n in sorted(safe_items, key=lambda x: -x[1])[:20]]

    case_whens = []
    for fp in fingerprints:
        fp_tables = fp.get("tables", []) if isinstance(fp, dict) else getattr(fp, "tables", [])
        if not set(fp_tables).intersection(tables):
            continue
        blocks = fp.get("case_when_blocks", []) if isinstance(fp, dict) else getattr(fp, "case_when_blocks", [])
        for cw in blocks:
            case_whens.append(cw.strip().upper()[:200])
            if len(case_whens) >= 15:
                break
        if len(case_whens) >= 15:
            break

    return {
        "title": topic["title"],
        "reason": topic.get("reason", ""),
        "key_concepts": topic.get("key_concepts", []),
        "tables": sorted(tables),
        "schema": schema,
        "joins": joins,
        "patterns": patterns,
        "filters": filters,
        "enums": enums,
        "case_whens": list(dict.fromkeys(case_whens))[:10],
    }


async def assess_and_author_focus_docs(
    docs: dict,
    fingerprints: list,
    counters: dict,
    clusters: list,
    literal_vals: dict,
    classified_filters: list,
    alias_conv: dict,
    preamble: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-5-20250929",
    focus_domains: Optional[list] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Assess if focus docs are needed and author them (async)."""
    if not any(docs.values()):
        return {}

    assessment_input = _build_assessment_input(docs, counters, literal_vals, clusters)
    prompt = FOCUS_ASSESSMENT_PROMPT_TEMPLATE.format(max_focus_docs=settings.max_focus_docs)

    if on_progress:
        await on_progress({
            "type": "llm_progress", "phase": "focus_assessment", "status": "started",
        })

    try:
        resp = await _call_llm_async(provider, model, prompt, assessment_input, 1500)
        cleaned = resp.strip().strip("`").lstrip("json\n")
        result = json.loads(cleaned)
    except Exception as e:
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "focus_assessment",
                "status": "failed", "error": str(e),
            })
        return {}

    topics = result.get("focus_docs", [])
    if not topics:
        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "focus_assessment",
                "status": "done", "count": 0,
            })
        return {}

    if focus_domains:
        topics = [
            t for t in topics
            if any(
                fd.lower() in t.get("title", "").lower()
                or fd.lower() in " ".join(t.get("key_concepts", [])).lower()
                for fd in focus_domains
            )
        ]

    topics = topics[:settings.max_focus_docs]

    if on_progress:
        await on_progress({
            "type": "llm_progress", "phase": "focus_assessment",
            "status": "done", "count": len(topics),
        })

    focus_docs = {}
    for i, topic in enumerate(topics):
        doc_num = 6 + i
        doc_key = f"{doc_num:02d}_FOCUS_{topic['title'].upper().replace(' ', '_')[:30]}"

        payload = _build_focus_payload(
            topic, fingerprints, counters, clusters,
            literal_vals, classified_filters, alias_conv,
        )

        sys_prompt = (
            preamble
            + f"\nYOUR DOC: {doc_key}\n\n"
            + FOCUS_DOC_PROMPT.format(
                title=topic["title"],
                reason=topic.get("reason", "Complex topic requiring dedicated documentation"),
                budget=settings.focus_token_budget,
            )
        )
        payload_text = _cap_payload(payload)
        user_msg = (
            f"Data for focus doc: {topic['title']}. Numbers are for reference only — "
            f"do NOT include counts or percentages.\n\nDATA:\n{payload_text}"
        )

        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "focus_authoring",
                "doc_key": doc_key, "status": "started",
            })

        try:
            focus_docs[doc_key] = await _call_llm_async(
                provider, model, sys_prompt, user_msg,
                max_tokens=settings.focus_token_budget * 2,
            )
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "focus_authoring",
                    "doc_key": doc_key, "status": "done",
                    "word_count": len(focus_docs[doc_key].split()) if focus_docs[doc_key] else 0,
                })
        except Exception as e:
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "focus_authoring",
                    "doc_key": doc_key, "status": "failed", "error": str(e),
                })

    return focus_docs
