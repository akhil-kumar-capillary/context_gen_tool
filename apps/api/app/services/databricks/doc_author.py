"""
Async LLM document authoring — 4-doc architecture with adaptive extras.

Ported from sparksql_context_pipeline notebook with:
- 4 core docs: DATA_MODEL, FILTERS_GUARDS, BUSINESS_LOGIC, QUERY_COOKBOOK
- Cross-reference guidance (each doc owns specific content)
- Importance-based space allocation (critical > important > supplementary)
- Dynamic token budgets based on payload size
- Chunked generation for large payloads (>300 items)
"""

import json
import logging
from typing import Optional, Callable, Awaitable

from app.config import settings
from app.services.llm_service import call_llm as _llm_call

logger = logging.getLogger(__name__)


# ── Token budget estimation ──

TOKEN_BUDGET_MIN = 64000
TOKEN_BUDGET_MAX = 128000
CHUNK_COMPLEXITY_THRESHOLD = 300  # items above this → chunked generation


def estimate_output_tokens(key: str, payload: dict) -> int:
    """Estimate required output tokens from actual payload size."""
    payload_chars = len(json.dumps(payload, default=str))
    payload_tokens = payload_chars // 4
    EXPANSION_FACTOR = 1.8
    OVERHEAD = 8000
    est = int(payload_tokens * EXPANSION_FACTOR) + OVERHEAD
    return max(min(est, TOKEN_BUDGET_MAX), TOKEN_BUDGET_MIN)


def _estimate_payload_complexity(key: str, payload: dict) -> int:
    """Estimate item count for chunking decision."""
    count = 0
    for v in payload.values():
        if isinstance(v, list):
            count += len(v)
        elif isinstance(v, dict):
            count += len(v)
    return count


# ── Guidance blocks ──

_CROSS_REF_GUIDANCE = """
CROSS-REFERENCE RULES (these docs are loaded together):
- Do NOT repeat information that belongs in another document.
- Instead, write: "See [DOC_NAME] for details on [topic]." Saves context.
- DATA_MODEL owns: table schemas, column definitions, join syntax.
- FILTERS_GUARDS owns: WHERE clause rules, mandatory/default/common filters, date patterns.
- BUSINESS_LOGIC owns: code dictionaries, metric definitions, CASE WHEN mappings, dimensions.
- QUERY_COOKBOOK owns: verified queries, SQL templates, patterns, conventions.
- If you need to mention a concept from another doc's domain (e.g., a filter in BUSINESS_LOGIC),
  give a one-line reference, NOT a full explanation.
"""

_IMPORTANCE_GUIDANCE = """
IMPORTANCE-BASED SPACE ALLOCATION:
- Each payload item has an "importance" field: "critical", "important", or "supplementary".
- CRITICAL items: Document in full detail. Every critical item MUST appear. Non-negotiable.
- IMPORTANT items: Document with moderate detail (name, expression, brief explanation).
- SUPPLEMENTARY items: Document concisely (name + expression sufficient). If low on space,
  supplementary items may be listed in compact format (bullet list).
- NEVER skip critical items to make room for supplementary content.
"""

_MATURITY_GUIDANCE = """
WRITING QUALITY:
- Write as an expert data engineer would for a production system prompt. Precise, specific.
- Every sentence must be grounded in the actual data payload — no filler.
- Do NOT write introductory paragraphs, motivational statements, or general advice.
- Do NOT explain what SQL is, what a JOIN does, or other basics. The reader is an AI.
- Jump straight to the specific tables, columns, filters, metrics, and queries.
- Use exact identifiers from the data — never paraphrase.
- NEVER use backticks (`) to quote identifiers. This environment does NOT support backtick quoting.
  Write table and column names unquoted: table_name.column_name, NOT `table_name`.`column_name`.
  This applies to ALL SQL examples, filter conditions, join syntax, and identifier references.
"""


# ── System prompts (ported from notebook) ──

SYSTEM_PROMPTS = {
    "01_DATA_MODEL": """Write the DATA MODEL document for this brand's CUSTOM TABLES only.

This brand has two types of tables:
- STANDARD TABLES (read_api databases): Their full schema, columns, data types, and
  relationships are documented in db_schema/ prefix docs in RAG. Do NOT re-document them.
- CUSTOM TABLES (write_db databases): These are brand-specific derived/aggregated tables
  NOT covered by db_schema/. This document must fully describe them.

The data payload contains:
- "custom_tables": Full detail for each custom table (columns, joins)
- "standard_tables": Names of standard tables (schema in db_schema/)
- "custom_joins": Joins involving custom tables (document these fully)

SECTIONS:
1. Schema Source Guide — State clearly standard vs custom
2. Custom Table Registry — For EACH custom table: business description, columns, joins
3. Custom Table Joins — All join relationships involving custom tables
4. Common Join Paths — If "join_path_hints" exists, document multi-table chains

COMPLETENESS RULES:
- Document EVERY custom table and column in the payload. Missing items = failure.
- Do NOT re-document standard table schemas — just list their names and point to db_schema/.
- Do NOT summarize or abbreviate — each item gets its own entry.
- The doc should be exactly as long as the data demands — no shorter, no longer.""",

    "02_FILTERS_GUARDS": """Write the FILTERS & GUARDS document — the complete reference for every
WHERE clause pattern the AI must apply when writing SparkSQL.

SECTIONS:
1. Mandatory Filters — filters that MUST appear in EVERY query
2. Table-Default Filters — filters that must always apply when querying a SPECIFIC table
3. Common Contextual Filters — filters that appear frequently but are not mandatory
4. Date Filter Patterns — specific patterns for date ranges, relative dates, date truncation
5. Situational Filters — less common filters that apply in specific business contexts
6. Common Pitfalls — If "common_pitfalls" exists, document EACH as a WARNING
7. Query Correctness Criteria — If "correctness_criteria" exists, document as a CHECKLIST

COMPLETENESS RULES:
- Document EVERY filter condition present in the DATA payload.
- Do NOT summarize or abbreviate — each item gets its own entry.
- When the data is fully covered, STOP. Do not add generic filler.""",

    "03_BUSINESS_LOGIC": """Write the BUSINESS LOGIC document — the business knowledge layer.
This maps business terminology to SQL.

Be EXHAUSTIVE across every business domain found in the data.

SECTIONS:
1. Code Dictionaries — For numeric codes, ONLY document value-to-meaning mapping
   if CASE WHEN blocks explicitly define it. If no CASE WHEN exists, list values WITHOUT
   assigning meanings.
2. Metric Definitions — For EACH metric: business name, exact SQL expression, full expression
   if CASE WHEN/DISTINCT/multi-column, typical GROUP BY dimensions, accompanying filters
3. Business Dimensions — What analysts segment/group by, with SQL syntax
4. Derived Business Logic — CASE WHEN patterns with structured mappings
5. Natural Language to SQL — Common business questions and SQL translations
6. Business Synonyms — If "synonyms" exists, document each column's business synonyms
7. Business Evidence — If "business_evidence" exists, document as AUTHORITATIVE FACTS

FOR ENUM/CODE VALUES: Data payload marks values as "confirmed_labels" or "unconfirmed".
For unconfirmed, list as "values observed: 2, 4 — meanings not confirmed". NEVER guess.

COMPLETENESS RULES: Document EVERY metric, enum, dimension, and business concept.
Missing items = failure. No filler beyond what data demands.""",

    "04_QUERY_COOKBOOK": """Write the QUERY COOKBOOK — a complete collection of reusable SQL templates.

VERIFIED QUERIES are the highest-priority section. Document NL→SQL pairs exactly.

Name every pattern by its BUSINESS PURPOSE (e.g., "Customer Lifetime Value").

Be EXHAUSTIVE. Cover templates for EVERY business domain discovered.

SECTIONS:
1. Conventions — Output formatting, alias style, SparkSQL function preferences
2. Verified Query Repository — NL→SQL pairs grouped by business domain
3. Examples by SQL Pattern — Organize by STRUCTURE (simple SELECT, aggregation, window, CTE, etc.)
4. Core Patterns — Essential queries grouped by business domain
5. Advanced Patterns — CTE-based, window function, multi-join templates
6. Cross-Domain Patterns — Queries joining across business domains

COMPLETENESS RULES: Document EVERY pattern, template, and query example.
Missing items = failure. No filler beyond what data demands.""",
}

DOC_NAMES = {
    "01_DATA_MODEL": "01_DATA_MODEL",
    "02_FILTERS_GUARDS": "02_FILTERS_GUARDS",
    "03_BUSINESS_LOGIC": "03_BUSINESS_LOGIC",
    "04_QUERY_COOKBOOK": "04_QUERY_COOKBOOK",
}

CORE_DOC_KEYS = ["01_DATA_MODEL", "02_FILTERS_GUARDS", "03_BUSINESS_LOGIC", "04_QUERY_COOKBOOK"]


# ── Preamble builder ──

def build_preamble(column_freq: list) -> str:
    """Build the shared preamble that precedes every doc's system prompt."""
    top_n = getattr(settings, "top_glossary_cols", 20)
    glossary = []
    for entry, _ in column_freq[:top_n]:
        entry_str = str(entry)
        if "." in entry_str:
            parts = entry_str.split(".")
            tbl, col = parts[0], ".".join(parts[1:])
        else:
            tbl, col = "?", entry_str
        glossary.append(f'      "{col.replace("_", " ")}" for column {col} in {tbl}')
    gloss_block = "\n".join(glossary) if glossary else "      (auto-populated)"

    doc_list = "\n".join(f"  {k} -> {DOC_NAMES[k]}" for k in CORE_DOC_KEYS)

    return f"""You are authoring ONE document in a set of context documents for an AI
system that generates SparkSQL queries from natural language.

All docs will be loaded together into the AI's system prompt at query time.
Standard tables (read_api databases) have their schema in db_schema/ prefix docs in RAG.
NEVER re-document standard table schemas — always reference db_schema/ for them.

THE CORE DOCUMENTS AND THEIR BOUNDARIES:
{doc_list}

{_CROSS_REF_GUIDANCE}
{_IMPORTANCE_GUIDANCE}
{_MATURITY_GUIDANCE}

CRITICAL WRITING RULES:
  - MANDATORY OPENING: Begin with a 2-4 sentence description (100-200 chars) explaining:
    (a) What this document contains, (b) When to load it, (c) What questions it answers.
  - NEVER mention query counts, usage percentages, or frequency stats.
  - NEVER use backticks (`) to quote identifiers. Write unquoted: table_name.column_name.
  - Be EXHAUSTIVE — every table, pattern, and business concept must be captured.
  - Use these canonical terms:
{gloss_block}
"""


# ── Payload serialization ──

def _cap_payload(payload: dict, max_chars: int = 0) -> str:
    """Serialize payload to JSON, truncate if too large."""
    if max_chars <= 0:
        max_chars = getattr(settings, "max_payload_chars", 600000)
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    text = json.dumps(payload, separators=(",", ":"), default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n... (truncated — highest-importance items shown above)"


# ── LLM call wrapper ──

async def _call_llm_async(
    provider: str, model: str, system_prompt: str,
    user_content: str, max_tokens: int = 4096,
) -> str:
    """Call LLM using our existing llm_service (async, cached clients)."""
    result = await _llm_call(
        provider=provider,
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        max_tokens=max_tokens,
    )
    for block in result.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


# ── Core authoring ──

async def author_docs(
    payloads: dict,
    preamble: str,
    provider: str = "anthropic",
    model: str = "claude-opus-4-6",
    model_map: Optional[dict] = None,
    system_prompts: Optional[dict] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Generate context documents via LLM.

    Handles both core 4 docs and any extra docs (from doc_planner).
    Uses dynamic token budgets and chunked generation for large payloads.
    """
    prompts = system_prompts or SYSTEM_PROMPTS
    mm = model_map or {}
    docs = {}

    for key in payloads:
        name = DOC_NAMES.get(key, key)
        payload = payloads[key]
        active_model = mm.get(key, model)

        # Get prompt — core docs from SYSTEM_PROMPTS, extras may have custom prompts
        doc_prompt = prompts.get(key, "")
        if not doc_prompt:
            # Extra doc — generate a generic prompt from its metadata
            doc_prompt = f"Write a comprehensive document for: {name}. Be exhaustive."

        complexity = _estimate_payload_complexity(key, payload)
        budget = estimate_output_tokens(key, payload)

        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "authoring",
                "doc_key": key, "doc_name": name, "status": "started",
            })

        try:
            if complexity > CHUNK_COMPLEXITY_THRESHOLD:
                docs[key] = await _author_doc_chunked(
                    key, payload, preamble, doc_prompt,
                    provider, active_model, budget,
                )
            else:
                sys_prompt = preamble + f"\nYOUR DOC: {key} — {name}\n\n" + doc_prompt
                payload_text = _cap_payload(payload)
                user_msg = (
                    f"Data payload for {name}. Items are sorted by prevalence (most common first). "
                    f"The 'importance' field indicates relative priority: 'critical' items must be "
                    f"documented thoroughly, 'important' items need solid coverage, 'supplementary' "
                    f"items need at minimum a mention with key details.\n"
                    f"Do NOT include any counts, percentages, or frequency stats in your output.\n\n"
                    f"DATA:\n{payload_text}"
                )
                docs[key] = await _call_llm_async(
                    provider, active_model, sys_prompt, user_msg, max_tokens=budget,
                )

            word_count = len(docs[key].split()) if docs[key] else 0
            logger.info(f"[author] {name} done — {word_count} words")

            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "authoring",
                    "doc_key": key, "doc_name": name, "status": "done",
                    "word_count": word_count,
                })

        except Exception as e:
            logger.exception(f"Failed to author {key}: {e}")
            docs[key] = None
            if on_progress:
                await on_progress({
                    "type": "llm_progress", "phase": "authoring",
                    "doc_key": key, "doc_name": name, "status": "failed",
                    "error": str(e),
                })

    return docs


async def _author_doc_chunked(
    key: str, payload: dict, preamble: str, doc_prompt: str,
    provider: str, model: str, total_budget: int,
) -> str:
    """Split large payload into chunks, generate separately, stitch together."""
    chunks = _split_payload_into_chunks(key, payload)
    sections = []

    for i, chunk in enumerate(chunks):
        chunk_label = chunk.get("label", f"Part {i + 1}")
        chunk_data = chunk["data"]
        chunk_budget = estimate_output_tokens(key, chunk_data)
        name = DOC_NAMES.get(key, key)

        sys_prompt = (
            preamble
            + f"\nYOUR DOC: {key} — {name}\n\n"
            + doc_prompt
            + f"\n\nIMPORTANT: You are writing PART {i + 1} of {len(chunks)}."
        )
        if i > 0:
            sys_prompt += "\nDo NOT include a document header — this continues from part 1."
        if i < len(chunks) - 1:
            sys_prompt += "\nDo NOT include a conclusion — more parts follow."

        payload_text = _cap_payload(chunk_data)
        user_msg = (
            f"Data payload for {name} — Part {i + 1}/{len(chunks)}: {chunk_label}\n"
            f"Document EVERY item. Importance tiers guide depth.\n\n"
            f"DATA:\n{payload_text}"
        )

        section = await _call_llm_async(provider, model, sys_prompt, user_msg, max_tokens=chunk_budget)
        if section:
            sections.append(section)

    logger.info(f"[author] {key} chunked into {len(chunks)} parts → {len(sections)} sections generated")
    return "\n\n".join(sections)


def _split_payload_into_chunks(key: str, payload: dict) -> list[dict]:
    """Split payload into 2 chunks for large payloads."""
    # Find the largest list in the payload
    largest_key = None
    largest_len = 0
    for k, v in payload.items():
        if isinstance(v, list) and len(v) > largest_len:
            largest_key = k
            largest_len = len(v)

    if not largest_key or largest_len <= CHUNK_COMPLEXITY_THRESHOLD:
        return [{"label": "Full", "data": payload}]

    # Split the largest list in half
    midpoint = largest_len // 2
    chunk1_data = {**payload, largest_key: payload[largest_key][:midpoint]}
    chunk2_data = {**payload, largest_key: payload[largest_key][midpoint:]}

    # Split other large lists proportionally between chunks
    for k, v in payload.items():
        if k != largest_key and isinstance(v, list) and len(v) > 50:
            mid = len(v) // 2
            chunk1_data[k] = v[:mid]
            chunk2_data[k] = v[mid:]

    return [
        {"label": f"{largest_key} (top half)", "data": chunk1_data},
        {"label": f"{largest_key} (bottom half)", "data": chunk2_data},
    ]


# ── Index document generator ──

def build_index_document(docs: dict, payloads: dict) -> str:
    """Auto-generate the 00_INDEX document listing all context docs."""
    lines = [
        "# Context Document Index",
        "",
        "Load this first to understand what context documents are available.",
        "",
        "| Key | Name | Purpose | Est. Words |",
        "|-----|------|---------|------------|",
    ]

    for key in sorted(docs.keys()):
        if not docs[key]:
            continue
        name = DOC_NAMES.get(key, key)
        word_count = len(docs[key].split())
        # Extract purpose from first 200 chars of the doc
        first_line = docs[key].strip().split("\n")[0][:150] if docs[key] else ""
        lines.append(f"| {key} | {name} | {first_line} | ~{word_count} |")

    lines.append("")
    lines.append("Standard table schemas are in db_schema/ prefix docs (loaded separately).")

    return "\n".join(lines)
