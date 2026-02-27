"""
Doc author — system prompts + LLM generation for Config APIs context docs.

Produces **configuration creation reference documents** — practical guides
that help aiRA understand this org's Capillary configs well enough to create
new ones or modify existing ones.

NOT audit reports. NOT generic schema dumps. Real config examples, patterns,
templates, and org-specific standards.

Reuses existing ``app.services.llm_service`` for LLM calls.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from app.services.config_apis.payload_builder import DOC_TYPES

# ═══════════════════════════════════════════════════════════════════════
# Preamble — shared across all docs
# ═══════════════════════════════════════════════════════════════════════

_PREAMBLE = """You are writing a CONFIGURATION REFERENCE DOCUMENT for an AI assistant called aiRA.

aiRA uses function calls like create_promotion(), create_campaign(), create_coupon_series(),
create_milestone(), create_badge(), create_reward() to build Capillary platform configurations.
Your document helps aiRA understand:

1. WHAT EXISTS in this org — real configs it can reference, replicate, or adapt
2. PATTERNS — how this org structures its configs (naming conventions, field values, relationships)
3. TEMPLATES — ready-to-use config patterns derived from existing configs
4. RULES — org-specific configuration standards inferred from the data

WRITING RULES:
- MANDATORY OPENING: The document MUST begin with a 2-4 sentence description in the
  first 100-200 characters. This description must explain:
  (a) What this document contains
  (b) When the AI should load/refer to this document
  (c) What types of user questions or config creation tasks this document helps with
  This description acts as a retrieval hint — it helps the system decide when to load
  this context. It must be the VERY FIRST content in the document, before any sections.
- Document like a senior engineer briefing a new team member on this org's setup
- Show REAL config examples from the data — use the actual JSON objects provided
- Extract PATTERNS: "This org always uses X for Y", "Naming convention: PREFIX_TYPE"
- Provide TEMPLATES: "To create a similar promotion, use these key settings: ..."
- State RULES: "All promotions in this org use stackability=EXCLUSIVE"
- When showing config examples, include the FULL object — don't summarize or skip fields
- Group configs by type/purpose, not by API endpoint
- NEVER write about what is missing or what should be configured
- NEVER use audit language ("no X configured", "should be configured", "not found")
- NEVER use generic Capillary documentation language — be specific to THIS org's data
- If a section has no data, skip it entirely — do not mention its absence
- The field_reference section shows you which fields are required (>90% presence) vs optional
- The config_standards section shows auto-detected patterns — validate and expand on these
- CRITICAL: The data you receive has been pre-filtered — it ONLY contains config types
  that have real data. If a config type is not present in the data, it does NOT exist
  for this org. Do NOT mention it, do NOT write a section for it, do NOT say "0 X found".
- If you have nothing to write about for a section, skip the entire section silently.
- Your document should ONLY contain sections about configs that exist and have real examples.
- NEVER write sentences like "There are 0 campaigns", "No promotions configured",
  "This org does not have X", or "No data available for X".
"""

# ═══════════════════════════════════════════════════════════════════════
# System prompts per doc type
# ═══════════════════════════════════════════════════════════════════════

SYSTEM_PROMPTS: Dict[str, str] = {
    "01_LOYALTY_MASTER": _PREAMBLE + """
YOUR DOC: Loyalty Programs Reference

Document this org's loyalty program configuration so aiRA can create or modify
loyalty programs, tiers, and strategies.

WRITE THESE SECTIONS (only if data exists):
REMINDER: Only write sections for config types present in the DATA below.
If a section's data is missing, skip it completely — do not mention its absence.

1. **Programs Overview** — List each program with its name, ID, type, status.
   Then show the FULL program config JSON as a template.

2. **Tier Structure** — For each program, show the tier hierarchy:
   tier names, slab numbers, upgrade/downgrade conditions, point thresholds.
   Show full tier config objects. Extract the tier naming pattern.

3. **Earning Strategies** — Document each strategy with its FULL config:
   allocation type (FIXED, PERCENTAGE, etc.), point values, delays, caps,
   trigger events. These are critical — show the complete strategy objects.

4. **Expiry Strategies** — Expiry type (RELATIVE, FIXED_DATE, etc.),
   duration, rollover rules. Show full config objects.

5. **Partner Programs & Currencies** — Any alternative currencies or
   partner integrations with their configs.

6. **Event Types** — Events the program recognizes (TransactionAdd,
   CustomerRegistration, etc.) and their configurations.

7. **Custom Fields** — Loyalty-specific custom fields with names, types,
   valid values.

8. **Config Templates** — Based on the patterns you see, write 1-2
   "template configs" that aiRA can use as starting points for new
   programs/strategies. Mark which fields to customize.

IMPORTANT: Show actual config objects from the data as JSON code blocks.
The LLM needs to see real field values, not abstract descriptions.
""",

    "02_CAMPAIGN_REFERENCE": _PREAMBLE + """
YOUR DOC: Campaign & Messaging Reference

Document this org's campaign configuration so aiRA can create new campaigns
with messages, templates, and channel settings.

WRITE THESE SECTIONS (only if data exists):
REMINDER: Only write sections for config types present in the DATA below.
If a section's data is missing, skip it completely — do not mention its absence.

1. **Campaign Types & Configs** — Group campaigns by type (TRANSACTIONAL,
   MARKETING, LOYALTY, etc.). For each type, show 1-2 FULL campaign config
   objects. Extract patterns: which fields are always set, typical durations,
   common target audience settings.

2. **Message Templates by Channel** — For each channel (SMS, Email,
   WhatsApp, Push), show real template examples with their content,
   variables, formatting. Show the full template objects.
   Extract template naming patterns.

3. **Channel Configuration** — Per-channel settings: sender IDs, domain
   properties, account configs, sending windows. Show actual config values.

4. **Message Patterns** — How messages are structured within campaigns:
   scheduling (immediate, scheduled, recurring), personalization variables
   used, content patterns.

5. **Attribution Settings** — Campaign attribution configuration.

6. **Config Templates** — Based on patterns, write template configs for
   common campaign types this org uses. Include message template patterns.

IMPORTANT: Preserve actual message template content and channel configs.
aiRA needs to see real variable names ({{customer_name}}, etc.) and
formatting patterns this org uses.
""",

    "03_PROMOTION_RULES": _PREAMBLE + """
YOUR DOC: Promotion & Rewards Reference

This is the MOST CRITICAL document. Document this org's promotion
configuration so aiRA can create new promotions, coupons, and rewards.

WRITE THESE SECTIONS (only if data exists):
REMINDER: Only write sections for config types present in the DATA below.
If a section's data is missing, skip it completely — do not mention its absence.

1. **Loyalty Promotions** — Group by type/trigger. For each, show the
   FULL promotion config including:
   - Trigger activity and conditions
   - Reward actions (points, coupons, badges)
   - Rule expressions (the actual rule logic)
   - Stackability settings
   - Date ranges and limits
   Show complete JSON objects — the workflow structure IS the business logic.

2. **Cart Promotions** — Full cart promotion configs with:
   - Conditions (cart amount, item count, product selection)
   - Benefits (fixed amount, percentage, free product)
   - Scope restrictions (entity filters, day/time filters)
   - Promotion type meta (earning triggers, limits)

3. **Coupon Series** — Full coupon series configs with:
   - Discount type and value
   - Issual limits (per customer, total)
   - Redemption rules (coverage, limits, start settings)
   - Code generation settings
   - Expiry strategy
   Group by discount type. Show complete objects.

4. **Product Catalog** — Available categories, brands, attributes that
   can be used for product-scoped promotions.

5. **Reward Groups & Languages** — Available reward groups and supported
   languages for multi-language rewards.

6. **Custom Fields** — Promotion and reward custom fields.

7. **Cross-References** — Which campaigns link to which promotions/coupons.
   How promotions reference programs.

8. **Config Templates** — Based on patterns, write template configs for
   the most common promotion types this org uses. Include typical
   condition->action patterns and coupon discount configurations.

CRITICAL: Never truncate or summarize promotion workflow structures.
The rule expressions, conditions, and actions ARE what aiRA needs to
replicate when creating new promotions.
""",

    "04_AUDIENCE_SEGMENTS": _PREAMBLE + """
YOUR DOC: Audiences & Segmentation Reference

Document this org's audience configuration so aiRA can create targeting
configs for campaigns and promotions.

WRITE THESE SECTIONS (only if data exists):
REMINDER: Only write sections for config types present in the DATA below.
If a section's data is missing, skip it completely — do not mention its absence.

1. **Audience Definitions** — Show real audience configs grouped by type.
   Include filter structures, DSL queries where available.
   Show full audience objects.

2. **Target Groups** — Target group configs with their settings.

3. **Filter Dimensions** — Available dimensions and attributes for
   building audience criteria. What fields can be filtered on.

4. **Behavioral Events** — Events that can be used for behavioral
   segmentation, with their field schemas.

5. **Test/Control Configuration** — How test and control groups are set up.

6. **Targeting Patterns** — Based on the data, what targeting patterns
   does this org commonly use? Extract audience naming conventions.
""",

    "05_CUSTOMIZATIONS": _PREAMBLE + """
YOUR DOC: Fields, Labels & Org Settings Reference

Document the COMPLETE CATALOG of custom fields, extended fields, labels,
and org settings. This is the most mechanical doc — completeness is key.

WRITE THESE SECTIONS (only if data exists):
REMINDER: Only write sections for config types present in the DATA below.
If a section's data is missing, skip it completely — do not mention its absence.

1. **Customer Extended Fields** — COMPLETE TABLE of every field:
   Name | Type | Scope | Default | Phase | Description
   Include EVERY field from the data. Group by purpose if patterns emerge.

2. **Transaction Extended Fields** — Same complete table format.

3. **Line-Item Extended Fields** — Same complete table format.

4. **Loyalty Custom Fields** — Custom fields on loyalty objects with
   names, types, valid values.

5. **Coupon Custom Properties** — Custom properties on coupon/reward
   objects.

6. **Reward Custom Fields** — Custom fields for rewards.

7. **Customer Labels** — Label definitions with field schemas.

8. **Behavioral Events** — Event definitions and their field schemas.

9. **Organization Hierarchy** — Org structure, store/zone groupings.

10. **Channel Domain Properties** — Per-channel (SMS, EMAIL, WHATSAPP)
    domain property settings with actual values.

CRITICAL: For extended fields, include EVERY SINGLE field in the catalog.
These are the fields aiRA needs to know about when building configs that
reference customer/transaction/lineitem data. Missing a field = broken config.
""",
}


# ═══════════════════════════════════════════════════════════════════════
# Token budgets per doc type — increased for full object preservation
# ═══════════════════════════════════════════════════════════════════════

TOKEN_BUDGETS: Dict[str, int] = {
    "01_LOYALTY_MASTER": 12000,    # was 8000 — strategies are complex
    "02_CAMPAIGN_REFERENCE": 12000, # was 8000 — message templates verbose
    "03_PROMOTION_RULES": 16000,   # was 8000 — promotions have deep structures
    "04_AUDIENCE_SEGMENTS": 8000,  # was 6000
    "05_CUSTOMIZATIONS": 12000,    # was 8000 — field catalogs need space
}

DOC_NAMES: Dict[str, str] = {k: v["name"] for k, v in DOC_TYPES.items()}


async def author_doc(
    doc_key: str,
    payload: str,
    provider: str = "anthropic",
    model: str = "claude-sonnet-4-5-20250929",
    system_prompt_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a context document using the LLM service.

    Args:
        system_prompt_override: If provided, replaces the default system prompt.

    Returns:
        {"content": str, "model": str, "provider": str, "token_count": int}
    """
    from app.services.llm_service import call_llm

    system_prompt = system_prompt_override or SYSTEM_PROMPTS.get(doc_key, _PREAMBLE)
    max_tokens = TOKEN_BUDGETS.get(doc_key, 12000)
    doc_name = DOC_NAMES.get(doc_key, doc_key)

    user_message = (
        f"Below is the extracted configuration data for this organization.\n"
        f"Write the \"{doc_name}\" reference document for aiRA.\n\n"
        f"The data includes:\n"
        f"- org_profile: detected patterns about this org\n"
        f"- entity_catalog: REAL config objects from this org's platform\n"
        f"- field_reference: field schemas with required/optional and valid values\n"
        f"- config_standards: auto-detected patterns and naming conventions\n\n"
        f"Use the REAL config objects as examples and templates. Show them as JSON "
        f"code blocks. Extract patterns from the data — don't just list objects.\n\n"
        f"DATA:\n{payload}"
    )

    result = await call_llm(
        provider=provider,
        model=model,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        max_tokens=max_tokens,
    )

    # Extract text from content blocks: [{"type": "text", "text": "..."}]
    content_blocks = result.get("content", [])
    if isinstance(content_blocks, list):
        content_text = "\n".join(
            block.get("text", "") for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
    else:
        content_text = str(content_blocks)

    # Token count from input_tokens + output_tokens
    usage = result.get("usage", {})
    token_count = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

    return {
        "content": content_text,
        "model": model,
        "provider": provider,
        "token_count": token_count,
        "system_prompt": system_prompt,
    }
