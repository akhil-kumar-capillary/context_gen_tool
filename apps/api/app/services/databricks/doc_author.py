"""
Async LLM document authoring — calls LLM to generate context documents.

Ported from reference: services/doc_author.py
Key changes: Uses existing call_llm from llm_service.py (async, cached clients),
all functions become async.
"""

import json
import logging
from typing import Optional, Callable, Awaitable

from app.config import settings
from app.services.llm_service import call_llm as _llm_call

logger = logging.getLogger(__name__)


# ── System prompts for each doc ──

SYSTEM_PROMPTS = {
    "01_MASTER": """Write the MASTER RULES document — the "constitution" of SQL generation rules.
This is the definitive rulebook the AI follows when writing SparkSQL.

Use numbered rules grouped by category. Every rule must be actionable
("ALWAYS do X", "NEVER do Y", "PREFER X over Y"). Include SparkSQL examples inline.

NEVER mention query counts, percentages, or how often something is used.
Write as authoritative rules, not statistical observations.

SECTIONS:
1. Dialect & Syntax Rules — SparkSQL-specific conventions, date functions, null handling
2. Structural Preferences — When to use CTEs vs subqueries, window functions, CASE WHEN
3. Naming Conventions — Table aliases, column aliases, output labels
4. Core Table Hierarchy — Identify the primary entity tables, lookup/reference tables,
   and how they relate. Group them by the business domains you discover in the data.
5. Output Formatting — SELECT column conventions, ORDER BY, LIMIT defaults
6. Conflict Resolution — What takes priority when rules overlap

Budget: {budget} tokens.""",

    "02_SCHEMA": """Write the SCHEMA REFERENCE — the complete data dictionary.
This tells the AI what tables exist, what each column means, and how tables connect.

NEVER mention query counts, percentages, or how often something is used.
Write as a definitive reference guide.

Identify ALL business domains present in the data from table/column names and group
tables accordingly. Do NOT skip any table or domain — be exhaustive. Every table in the
data must appear.

For each table include:
- 1-2 sentence business description (infer from table/column names)
- Key columns with inferred types and business meaning
- Common aliases
- JOIN relationships with exact ON syntax

SECTIONS:
1. Table Registry by Domain (group all tables under discovered domains)
2. Column Reference per Table
3. Join Graph — how tables connect with exact ON conditions
4. Data Type Conventions

Budget: {budget} tokens.""",

    "03_BUSINESS": """Write the BUSINESS MAPPINGS — the business knowledge layer.
This maps business terminology to SQL. An AI reading this should understand what every
code, KPI, dimension, and business rule means and how to express it in SparkSQL.

NEVER mention query counts, percentages, or how often something is used.
Write as a business knowledge guide with SQL translations.

Be EXHAUSTIVE across every business domain you find in the data.

SECTIONS:
1. Code Dictionaries — Every status code, type code, category code with its business meaning
2. KPI Definitions — Business metric name, exact SQL expression, typical GROUP BY dimensions
3. Business Dimensions — What analysts segment/group by, with SQL syntax
4. Derived Business Logic — CASE WHEN patterns that classify or transform data
5. Natural Language to SQL — Common business questions and their SQL translations

Budget: {budget} tokens.""",

    "04_FILTERS": """Write the DEFAULT FILTERS document.
This defines which WHERE conditions the AI must apply automatically and which are contextual.

NEVER mention query counts, percentages, or how often something is used.
Write as definitive filtering rules.

Every filter must include the EXACT SparkSQL syntax ready to copy-paste.

Categorize filters as:
- MANDATORY: Always apply these (e.g., org/tenant filters, active record flags, soft deletes)
- TABLE-DEFAULT: Apply whenever a specific table is used
- COMMON: Apply when contextually relevant

SECTIONS:
1. Mandatory Filters — Always apply, with exact syntax
2. Table-Specific Defaults — Per-table filters for every relevant table
3. Date Range Patterns — Standard time filtering conventions
4. Parameterized Filters — How to handle dynamic values
5. Filter Interaction Rules — Which filters combine, which are mutually exclusive

Budget: {budget} tokens.""",

    "05_PATTERNS": """Write the QUERY PATTERNS document — a complete cookbook of reusable SQL templates.
An AI should be able to pick the right template for any business question and adapt it.

NEVER mention query counts, percentages, or how often something is used.
Write as a practical cookbook with runnable examples.

Name every pattern by its BUSINESS PURPOSE, not by SQL structure.

Be EXHAUSTIVE. Cover templates for EVERY business domain discovered in the data.

For each pattern include:
- Business-friendly name and when to use it
- Complete, runnable SparkSQL example
- Simple variant and complex variant (with CTEs/windows) where relevant

SECTIONS:
1. Core Patterns — Essential everyday queries, grouped by business domain
2. Advanced Patterns — CTE-based, window function, multi-join templates
3. Cross-Domain Patterns — Queries that join across business domains
4. Few-Shot Examples — Natural language question paired with complete SQL

Budget: {budget} tokens.""",
}

DOC_NAMES = {
    "01_MASTER": "01_MASTER_RULES",
    "02_SCHEMA": "02_SCHEMA_REFERENCE",
    "03_BUSINESS": "03_BUSINESS_MAPPINGS",
    "04_FILTERS": "04_DEFAULT_FILTERS",
    "05_PATTERNS": "05_QUERY_PATTERNS",
}

TOKEN_BUDGETS = {
    "01_MASTER": settings.token_budget_01_master,
    "02_SCHEMA": settings.token_budget_02_schema,
    "03_BUSINESS": settings.token_budget_03_business,
    "04_FILTERS": settings.token_budget_04_filters,
    "05_PATTERNS": settings.token_budget_05_patterns,
}


def build_preamble(column_freq: list) -> str:
    """Build the shared preamble that precedes every doc's system prompt."""
    glossary = []
    for entry, _ in column_freq[:settings.top_glossary_cols]:
        entry_str = str(entry)
        if "." in entry_str:
            parts = entry_str.split(".")
            tbl, col = parts[0], ".".join(parts[1:])
        else:
            tbl, col = "?", entry_str
        glossary.append(f'      "{col.replace("_", " ")}" for column `{col}` in `{tbl}`')
    gloss_block = "\n".join(glossary) if glossary else "      (auto-populated)"

    return f"""You are authoring ONE document in a set of 5 context documents for an AI
system that generates SparkSQL queries from natural language.

All 5 docs will be loaded together into the AI's system prompt at query time.
The AI must use these docs to understand the brand's business, database, and
query conventions well enough to write correct SparkSQL from plain English.

THE 5 DOCUMENTS AND THEIR BOUNDARIES:
  01_MASTER_RULES     -> SQL generation rules, conventions, and structural guidance.
  02_SCHEMA_REFERENCE -> Tables, columns, joins, data types — the data dictionary.
  03_BUSINESS_MAPPINGS -> What business concepts mean in SQL — KPIs, codes, enums, logic.
  04_DEFAULT_FILTERS  -> Mandatory and default WHERE clauses with exact syntax.
  05_QUERY_PATTERNS   -> Complete reusable SQL templates for every business scenario.

CRITICAL WRITING RULES:
  - NEVER mention query counts, usage percentages, or frequency stats.
    Do NOT write "used in 90% of queries" or "appears 120 times".
    Write as authoritative documentation, not statistical analysis.
  - Identify ALL business domains present in the data and organize content around them.
    Do NOT skip any domain — every table, pattern, and business concept must be captured.
  - Be EXHAUSTIVE. If the data shows a pattern, document it.
  - Use these canonical terms:
{gloss_block}
  - Reference other docs instead of redefining their content.
  - Priority: 01_MASTER > 04_FILTERS > 02_SCHEMA > 03_BUSINESS > 05_PATTERNS
"""


def _cap_payload(payload: dict, max_chars: int = 0) -> str:
    """Serialize payload to JSON, truncate if too large."""
    if max_chars <= 0:
        max_chars = settings.max_payload_chars
    text = json.dumps(payload, indent=2, default=str)
    if len(text) <= max_chars:
        return text
    text = json.dumps(payload, separators=(",", ":"), default=str)
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n\n... (truncated — highest-frequency items shown above)"


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
    # Extract text from the response
    for block in result.get("content", []):
        if block.get("type") == "text":
            return block["text"]
    return ""


async def author_docs(
    payloads: dict,
    preamble: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-5-20250929",
    model_map: Optional[dict] = None,
    system_prompts: Optional[dict] = None,
    on_progress: Optional[Callable] = None,
) -> dict:
    """Generate 5 context documents via LLM (async). Returns {doc_key: text}."""
    prompts = system_prompts or SYSTEM_PROMPTS
    mm = model_map or {}
    docs = {}

    for key in ["01_MASTER", "02_SCHEMA", "03_BUSINESS", "04_FILTERS", "05_PATTERNS"]:
        name = DOC_NAMES[key]
        budget = TOKEN_BUDGETS.get(key, 1500)
        active_model = mm.get(key, model)

        sys_prompt = (
            preamble
            + f"\nYOUR DOC: {key} — {name}\n\n"
            + prompts[key].format(budget=budget)
        )
        payload_text = _cap_payload(payloads[key])
        user_msg = (
            f"Data payload for {name}. The numbers in the data are for your reference to "
            f"understand relative importance — do NOT include any counts, percentages, or "
            f"frequency stats in your output. Write as an authoritative business & database guide.\n\n"
            f"DATA:\n{payload_text}"
        )

        if on_progress:
            await on_progress({
                "type": "llm_progress", "phase": "authoring",
                "doc_key": key, "doc_name": name, "status": "started",
            })

        try:
            docs[key] = await _call_llm_async(
                provider, active_model, sys_prompt, user_msg, max_tokens=budget * 2
            )
            word_count = len(docs[key].split()) if docs[key] else 0
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
