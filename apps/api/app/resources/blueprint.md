LLM Context Restructuring Blueprint — NL to SparkSQL

Purpose: A universal, repeatable methodology for restructuring any brand's unstructured context documents into an optimized, LLM-ready context architecture for Natural Language to SparkSQL query generation.

Outcome: Zero information loss, ~40–60% token reduction, elimination of all contradictions, and deterministic LLM behavior when converting user questions into accurate SparkSQL queries.

Scope: This blueprint applies to any brand or organization whose LLM context powers a NL-to-SparkSQL pipeline — regardless of industry, data model, or business domain.

How To Use This Blueprint

This blueprint has 7 phases. Execute them sequentially. Each phase has explicit inputs, actions, outputs, and a completion gate — do not proceed to the next phase until the gate is passed.

Estimated effort per brand: 2–4 hours depending on source document count and complexity.

What you need before starting:
* All source context documents for the brand (PDFs, docs, sheets, wikis — any format)
* Access to any referenced master data files (product catalogs, store lists, promotion tables, etc.)
* Understanding of the brand's data model (tables, columns, relationships)
* Sample user questions the LLM is expected to answer

PHASE 0: INVENTORY & BASELINE

Objective
Catalog every source document. Establish a quantitative baseline to measure improvement.

Actions

0.1 — List All Source Documents
Create a table with one row per document:

| # | Filename | Format | Pages/Rows | Est. Tokens | Primary Topic |
|---|----------|--------|------------|-------------|---------------|
| 1 | [filename] | PDF | [N] | ~[N] | [topic] |
| 2 | [filename] | XLSX | [N] | ~[N] | [topic] |
| ... | | | | | |

How to estimate tokens: ~1 token per 4 characters of English text, or ~250 tokens per PDF page of dense text. For spreadsheets, estimate ~1 token per cell with content.

0.2 — Calculate Baseline Token Budget

Total Source Tokens = Sum of all Est. Tokens
Target Output Tokens = Total Source Tokens × 0.45 to 0.55
Token Savings Target = 40–60%

The savings come from:
* Removing duplication (typically 15–30% of source content is repeated across files)
* Removing meta-commentary, preambles, and LLM steering prose that can be centralized
* Replacing verbose prose with structured tables and code snippets
* Eliminating contradictory content (replaced with single authoritative version)

0.3 — Identify Document Relationships
For each pair of documents, note:
* Duplicates: Same information repeated (mark for consolidation)
* Extends: Document A adds detail to a topic in Document B
* Contradicts: Documents disagree on a rule or value (mark for resolution)
* Independent: No overlap

Tip: Draw this as a simple matrix if there are more than 6 source documents.

Completion Gate
You must have: (a) complete file list with token estimates, (b) baseline total, (c) relationship map showing all duplicates and contradictions identified.

PHASE 1: DEEP DISCOVERY

Objective
Extract every discrete piece of information from every source document. Tag each item by type. This is the most time-intensive phase but the most important — everything downstream depends on it.

Actions

1.1 — Read Every Source Document End-to-End
Read each document in its entirety. Do not skim. Every page, every footnote, every example query, every bullet point.

1.2 — Extract Discrete Information Items
For each document, create an extraction list. Each row is one "atom" of information — the smallest unit that cannot be split further without losing meaning.

Item Types (for NL-to-SparkSQL context):

| Type Tag | Description | Generic Examples |
|----------|-------------|-----------------|
| RULE | A behavioral instruction for the LLM | "Always apply [mandatory filter] to every query", "Never use AVG() directly" |
| MAPPING | A data value mapping or code definition | "Product code 'X123' = 'Premium Widget' in business terms" |
| SCHEMA | Table, column, relationship, or data type definition | "orders table has column customer_id (BIGINT)" |
| FILTER | A SparkSQL filter pattern (WHERE, JOIN, exclusion) | "LEFT JOIN [exclusion_table] ... WHERE ... IS NULL" |
| PATTERN | A reusable SparkSQL query template | "Monthly revenue by region query" |
| FLOW | A multi-step process or decision tree | "Entity validation: confirm product names before querying" |
| TERM | Business terminology or naming convention | "'Transactions' not 'Purchases' in output labels" |
| KPI | Metric definition with calculation formula | "AOV = SUM(amount) / COUNT(DISTINCT order_id)" |
| CONFIG | System configuration, tool settings, activation triggers | "Always read master file before querying promotions" |
| META | Content ABOUT the documents themselves (not operational) | "This document ensures consistency" → candidate for removal |

Extraction format per document:

Source: [Filename], Page [N]
Items:
  1. [RULE] Always apply [mandatory filter] to every query
  2. [MAPPING] Product code 'X123' = 'Premium Widget'
  3. [SCHEMA] orders table has column dim_event_date_id
  4. [META] "This structure ensures consistency" → candidate for removal
  ...

1.3 — Count and Classify
After extracting all items from all documents:

| Type | Count | % of Total |
|------|-------|-----------|
| RULE | [N] | [N]% |
| MAPPING | [N] | [N]% |
| FILTER | [N] | [N]% |
| SCHEMA | [N] | [N]% |
| PATTERN | [N] | [N]% |
| ... | | |
| TOTAL | [N] | 100% |

Completion Gate
Every page of every source document has been read. Every discrete information item is extracted and tagged. Total item count is known.

PHASE 2: CONFLICT DETECTION & DEDUPLICATION

Objective
Identify every contradiction, duplication, and ambiguity across all source documents before designing the new structure.

Actions

2.1 — Detect Exact Duplicates
Compare every item against every other item. Flag as DUPLICATE when:
* Same information appears in 2+ source documents
* Same query pattern is provided multiple times
* Same mapping or code definition is repeated

Record format:

DUP-1: "[description of duplicated item]"
  Found in: [Doc A] (page N), [Doc B] (page N), [Doc C] (page N)
  Action: Consolidate to single source in output

2.2 — Detect Contradictions
Flag as CONFLICT when two documents disagree. These are the highest-priority items to resolve.

Common contradiction patterns in NL-to-SparkSQL contexts:

| Pattern | Example | Resolution Strategy |
|---------|---------|-------------------|
| Filter scope disagreement | Doc A says "always apply filter X" vs Doc B says "never apply filter X for this use case" | Create explicit override rule with scope |
| Method contradiction | Doc A says use LIKE '%keyword%' vs Doc B says use exact code lookups | Choose the more precise method; document as conflict resolution |
| Naming inconsistency | Doc A uses table_name_v2 vs Doc B uses table_name for the same table | Standardize to one; note in conflict resolution |
| Priority collision | Multiple docs each claim to be "highest priority" or "critical" | Centralize priority in master rules; strip from all other docs |
| Example vs Rule mismatch | A rule says "do X" but an example query in the same doc does "Y" | The rule wins over the example; fix the example |
| Table choice contradiction | Doc A says use table_A for metric, Doc B says use table_B | Determine correct table per use case; scope explicitly |

Record format:

CONFLICT-1: [description]
  Doc A ([filename]): "[what it says]"
  Doc B ([filename]): "[what it says]"
  Resolution: [how to resolve] → Create CR-[N] with explicit scoping

2.3 — Detect Ambiguities
Flag as AMBIGUOUS when information is incomplete, unclear, or requires engineering input.

AMBIGUOUS-1: [description]
  Doc A uses: [variant 1]
  Doc B uses: [variant 2]
  Resolution: Flag for engineering input; standardize with note

2.4 — Build the Conflict Register
Create a single table of all conflicts with resolutions:

| ID | Type | Description | Resolution | Output Location |
|----|------|-------------|-----------|-----------------|
| CR-1 | Scope | [filter X] application scope | Scoped override | 01_MASTER_RULES |
| CR-2 | Conditional | [filter Y] conditionality | Made conditional with trigger | 01_MASTER_RULES |
| CR-3 | Method | [table A] vs [table B] for [metric] | Context-dependent rule | 01_MASTER_RULES |
| ... | | | | |

Completion Gate
All duplicates cataloged with consolidation plan. All contradictions identified with explicit resolutions. All ambiguities documented with engineering input flags.

PHASE 3: ARCHITECTURE DESIGN

Objective
Design the output document structure. This is the critical architectural decision — get this wrong and everything downstream suffers.

Actions

3.1 — Apply the Standard Document Architecture
Use this core + conditional architecture as the starting template. It is designed to work for any brand's NL-to-SparkSQL context.

```
┌──────────────────────────────────────────────────────────────────┐
│                    ALWAYS LOADED (P0–P4)                         │
│                                                                  │
│  01_MASTER_RULES ──────── Constitution, conflicts, output rules  │
│  02_SCHEMA_REFERENCE ──── Tables, columns, joins, data types     │
│  03_BUSINESS_MAPPINGS ─── Codes, categories, terms, KPIs         │
│  04_DEFAULT_FILTERS ───── Mandatory SparkSQL filter patterns      │
│  05_QUERY_PATTERNS ────── Reusable SparkSQL templates             │
│                                                                  │
├──────────────────────────────────────────────────────────────────┤
│               CONDITIONALLY LOADED (P5)                          │
│                                                                  │
│  06_[DOMAIN]_CONTEXT ──── Domain-specific overrides               │
│  07_[DOMAIN]_CONTEXT ──── Domain-specific overrides               │
│  08_[DOMAIN]_CONTEXT ──── (add more as needed)                    │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

The 5 always-loaded documents are universal across all brands. Their content changes per brand, but their role and structure stay the same.

The conditional documents (P5) are brand-specific. A brand might have 0, 1, 2, 3, or more conditional documents depending on their domain-specific workflows. The number is not fixed — add as many as the brand requires.

3.2 — Document Role Definitions
Each document has a fixed role. Content goes into whichever document matches its role — no exceptions.

01_MASTER_RULES (P0 — The Constitution)
Role: Governs priority, conflicts, global output rules, anti-patterns, and conditional activation triggers. No other document may declare itself "highest priority."

Contains:
* Document priority hierarchy table (P0–P5)
* Priority resolution protocol (what wins when docs conflict)
* All conflict resolution rules (CR-1, CR-2, ...) from Phase 2
* Global output format rules (data types, rounding, SparkSQL dialect constraints)
* Global calculation method rules (e.g., how to compute averages, percentages)
* Anti-pattern catalog (numbered list of things the LLM must never do)
* Conditional document activation triggers (when to load P5 docs)
* Pre-query validation checklist

Does NOT contain: SparkSQL queries, table schemas, business definitions, filter SQL code.

Routing rule: If it's a rule that governs OTHER rules, resolves a conflict between documents, or defines global output behavior → it goes here.

02_SCHEMA_REFERENCE (P3 — The Data Dictionary)
Role: Single source of truth for all table definitions, column specifications, join patterns, and data relationships.

Contains:
* Table definitions (name, description, key columns with types and notes)
* Standard join patterns (numbered: JP-1, JP-2, ...)
* Table alias conventions
* Key relationships (which tables join on which columns)
* Partition, date, and index conventions
* Views and derived tables
* Master data file references (which external files supplement which tables)

Does NOT contain: Business logic, filter rules, SparkSQL templates, terminology.

Routing rule: If it describes the STRUCTURE of data (what tables exist, what columns they have, how they connect) → it goes here.

03_BUSINESS_MAPPINGS (P2 — The Rosetta Stone)
Role: All code-to-meaning translations, category definitions, terminology standards, KPIs, and segmentation logic.

Contains:
* Product/item code mappings (codes → business names)
* Category and subcategory classification rules
* Payment method / channel classification
* Customer type / segment classification
* Business terminology translation table (business term ↔ technical term)
* KPI definitions with explicit calculation formulas
* Customer segmentation dimensions
* Product search strategies (how to find entities by name when codes aren't given)
* Business objectives and analysis priorities

Does NOT contain: SparkSQL filter patterns, query templates, table schemas.

Routing rule: If it translates between business language and data language, or defines what a business concept MEANS in data terms → it goes here.

04_DEFAULT_FILTERS (P1 — The Safety Net)
Role: Every mandatory SparkSQL filter pattern that must be applied to queries. Organized in tiers by conditionality.

Contains:
* Tier 1 filters: Apply to EVERY query, no exceptions (e.g., program membership filter, customer status filter, fraud exclusion)
* Tier 2 filters: Apply when specific tables are used (e.g., outlier exclusions for transaction tables, category filters for points/rewards tables)
* Tier 3 filters: Apply only when user explicitly requests or analysis context requires (e.g., active customer recency filter, date range filters)
* Date filter patterns (range, inception-to-date, upper/lower bound, relative)
* Decision tree for filter application
* Query structure template showing WHERE all filters go
* Pre-execution validation checklist

Does NOT contain: Business definitions, table schemas, query templates beyond the filter skeleton.

Routing rule: If it's a WHERE clause, LEFT JOIN exclusion, or data quality filter that protects query integrity → it goes here.

05_QUERY_PATTERNS (P4 — The Recipe Book)
Role: Complete, production-ready SparkSQL templates for common business questions. These are the "gold standard" queries the LLM should model its output on.

Contains:
* Numbered query patterns (QP-1, QP-2, ...) each with:
   * Title and use case description
   * Complete SparkSQL (copy-paste ready, with all mandatory filters baked in)
   * Notes on which filters from 04 are applied
   * Notes on which mappings from 03 are used
* Patterns should cover the most common 60–80% of expected user questions

Does NOT contain: Filter definitions (reference 04), business definitions (reference 03).

Routing rule: If it's a complete SparkSQL query that answers a specific business question and can serve as a template → it goes here.

Important: Query patterns should be fully self-contained (all filters, joins, mappings inline) even if that repeats content from other documents. This is intentional — the LLM must be able to use a pattern directly without mentally merging content across files.

06+_[DOMAIN]_CONTEXT (P5 — Conditional Specialists)
Role: Domain-specific rules that OVERRIDE or EXTEND the always-loaded documents for a specific use case (e.g., coupon analysis, promotion resolution, entity validation, returns processing).

Standard template (every conditional document follows this structure):

Section 1: Activation Trigger    → When to load this document
Section 2: Filter Overrides      → Which default filters to REMOVE / KEEP / ADD
Section 3: Definitions           → Domain-specific terms and identifiers
Section 4: Process Flow          → Step-by-step methodology for this domain
Section 5: Validation Checklist  → Pre-execution checks specific to this domain
Section 6: Scalability           → How to extend this document

Key principle: A conditional document may ONLY override rules it explicitly names. All unnamed rules from P0–P4 remain in full effect.

Common conditional domains by industry:

| Industry | Likely Conditional Docs |
|----------|------------------------|
| Retail / Fuel | Coupon Analysis, Promotion Resolution, Entity Validation |
| E-commerce | Returns/Refunds, Promotion Codes, Inventory Checks |
| Banking / Finance | Dispute Resolution, Product Eligibility, Risk Scoring |
| Telecom | Plan Changes, Usage Analysis, Network Queries |
| Healthcare | Claim Processing, Provider Matching, Formulary Lookups |
| FMCG | Trade Promotions, Distributor Analysis, Shelf Availability |
| Hospitality | Loyalty Redemptions, Rate Analysis, Occupancy Queries |

3.3 — Design the Priority System
The priority system determines what the LLM does when rules conflict. This is the most important architectural decision.

Universal Priority Principles:
1. LOWER tier number = HIGHER priority
2. P0 (Master Rules) is ALWAYS the final authority
3. Conditional docs (P5) can override specific rules but must explicitly name what they override
4. If no document addresses a scenario, the LLM must ask the user
5. Anti-patterns in P0 can NEVER be overridden by any document

Standard tier assignment:

P0: Rules about rules (meta-governance)                → 01_MASTER_RULES
P1: Rules that apply to every query (data safety)      → 04_DEFAULT_FILTERS
P2: Rules about what data means (business semantics)   → 03_BUSINESS_MAPPINGS
P3: Rules about what data exists (data structure)      → 02_SCHEMA_REFERENCE
P4: Rules about how to query (reusable templates)      → 05_QUERY_PATTERNS
P5: Rules for special cases (scoped overrides)         → 06/07/08+_CONTEXT

Rationale for this ordering:
* Filters (P1) outrank mappings (P2) because applying the wrong filter produces incorrect data, while using a slightly wrong mapping produces presentable-but-imprecise data. Wrong data is worse than imprecise data.
* Mappings (P2) outrank schema (P3) because the LLM can often infer schema from query patterns, but cannot infer business meaning from schema alone.
* Schema (P3) outranks patterns (P4) because a query template referencing the wrong table is worse than no template at all.

3.4 — Map Source Items to Output Documents
Using the extraction from Phase 1, assign every item to its output document:

| Item | Type | Source File | Output Document | Output Section |
|------|------|------------|-----------------|----------------|
| [mandatory filter description] | FILTER | [source] | 04_DEFAULT_FILTERS | F-[N] |
| [product code mapping] | MAPPING | [source] | 03_BUSINESS_MAPPINGS | [N.N] |
| [table definition] | SCHEMA | [source] | 02_SCHEMA_REFERENCE | [N.N] |
| ... | | | | |

Routing decision tree:

Is it a rule about rules, priority, or conflict?            → 01_MASTER_RULES
Is it a table, column, join, or data relationship?          → 02_SCHEMA_REFERENCE
Is it a code mapping, business term, KPI, or category?      → 03_BUSINESS_MAPPINGS
Is it a SparkSQL filter or data quality exclusion pattern?   → 04_DEFAULT_FILTERS
Is it a complete reusable SparkSQL template?                 → 05_QUERY_PATTERNS
Is it domain-specific with override rules?                   → 06/07/08+_[DOMAIN]
Is it meta-commentary about the documents themselves?        → REMOVE (don't migrate)

3.5 — Define Conditional Activation Triggers
For each conditional document, define explicit triggers:

| Trigger ID | User Query Contains | Document to Load |
|-----------|---------------------|-----------------|
| A-1 | [keyword list or intent pattern] | 06_[DOMAIN]_CONTEXT |
| A-2 | [keyword list or intent pattern] | 07_[DOMAIN]_CONTEXT |
| A-3 | [keyword list or intent pattern] | 08_[DOMAIN]_CONTEXT |

Completion Gate
Architecture diagram finalized. Every source item mapped to exactly one output document and section. Priority system designed. Conditional triggers defined. No item is unmapped.

PHASE 4: CONTENT MIGRATION

Objective
Write each output document. This is where extraction becomes production content.

Actions

4.1 — Writing Order
Write documents in this exact order (dependencies flow downward):

1st: 01_MASTER_RULES       (references nothing; everything references it)
2nd: 02_SCHEMA_REFERENCE    (references nothing except Master Rules)
3rd: 03_BUSINESS_MAPPINGS   (may reference Schema for table/column names)
4th: 04_DEFAULT_FILTERS     (references Schema for table names, Mappings for codes)
5th: 05_QUERY_PATTERNS      (references everything above; contains self-contained SQL)
6th+: 06/07/08+_CONTEXT     (references everything above + declares overrides)

4.2 — Content Migration Rules
Follow these 11 rules for every piece of content migrated:

Rule M-1: Tables over prose. If information can be expressed as a table, use a table. LLMs parse structured tables more reliably than paragraphs.

Rule M-2: Exact SparkSQL over descriptions. If a rule can be expressed as a SparkSQL snippet, include the snippet. Don't describe what the SQL should do — show it.

Rule M-3: Every rule gets a unique ID. Number every rule, filter, pattern, conflict resolution, and anti-pattern. IDs enable unambiguous cross-referencing.

Suggested ID prefixes:
  CR-1, CR-2      (Conflict Resolutions — in 01_MASTER_RULES)
  GR-1, GR-2      (Global Rules — in 01_MASTER_RULES)
  AP-1, AP-2      (Anti-Patterns — in 01_MASTER_RULES)
  F-1, F-2, F-3   (Filters — in 04_DEFAULT_FILTERS)
  QP-1, QP-2      (Query Patterns — in 05_QUERY_PATTERNS)
  JP-1, JP-2      (Join Patterns — in 02_SCHEMA_REFERENCE)

Rule M-4: Explicit triggers for every conditional rule. Every rule that applies conditionally must state WHEN it applies and WHEN it does NOT apply.

Rule M-5: Overrides must name what they override. When a conditional document overrides a default rule, it must reference the exact ID from the source document.

Rule M-6: No circular references. Document A may reference Document B, but B must not reference A for the same rule. Information flows downward through the priority hierarchy (P0 → P1 → P2 → P3 → P4 → P5), never upward.

Rule M-7: No competing priority labels. Only 01_MASTER_RULES may use priority language like "CRITICAL", "HIGHEST PRIORITY", or "MANDATORY". All other documents use descriptive section headers without priority claims.

Rule M-8: Consolidate duplicates to a single source. When the same information exists in multiple source documents, write it ONCE in the most appropriate output document. Other documents reference it by ID.

Exception: Query patterns in 05 should contain complete, self-contained SparkSQL even if that means repeating filter code and mappings. Patterns must be directly usable without the LLM needing to mentally merge content from multiple documents.

Rule M-9: Show "Wrong → Right" for critical rules. For any rule where violations are common or dangerous, include both the incorrect and correct patterns explicitly.

Rule M-10: End every document with a Scalability section. A brief "To add..." section explaining how to extend the document.

Rule M-11: Output documents must read as fresh, original documents. Every output document must read as if it was always written this way. There must be zero references to restructuring, migration, modification, prior versions, source documents, or the process that created them.

FORBIDDEN language in output documents:
  - "Migrated from..."
  - "Previously in..."
  - "Changed from..."
  - "Consolidated from..."
  - "Moved from..."
  - "Updated from..."
  - "This replaces..."
  - "Originally defined in..."
  - "Source: [old document name]"
  - Any reference to old/prior/original document names or versions

The output documents ARE the documents. They have no history.

4.3 — Write Each Document
For each document, follow this process:
1. Write the header (role statement, one-line description)
2. Write section headings based on the item mapping from Phase 3
3. Migrate items one by one from the extraction list
4. Apply formatting rules M-1 through M-11
5. Add cross-references where needed (by rule ID)
6. Add the scalability section
7. Re-read the complete document for internal consistency

4.4 — Formatting Standards
Apply these uniformly across all documents:

Markdown structure:
```
# [NUMBER] — [DOCUMENT NAME]

> **Role:** One-sentence role description.

---

## Section N: [Section Title]

### N.1 [Subsection]

[Content: tables, SparkSQL, rules]

---

## Scalability
[How to extend this document]
```

Completion Gate
All output documents written. Every document follows formatting standards. Every rule has an ID. Every conditional rule has an explicit trigger. Every override names what it overrides.

PHASE 5: CROSS-CHECK AUDIT

Objective
Verify that every discrete information item from every source document exists in the new structure. Zero loss tolerance.

Actions

5.1 — Build the Traceability Matrix
Create a single audit document (CROSS_CHECK_AUDIT.md) with one section per source file:

```
## [Source Filename]

| Original Content | Status | New Location |
|-----------------|--------|-------------|
| [Description of info item] | ✅/🔀/🗑️ | [Document + Section] |
```

Status codes:
* ✅ = Captured in new structure (direct migration)
* 🔀 = Consolidated (was duplicated across multiple sources; now in one location)
* 🗑️ = Intentionally removed (with documented reason)

Rules:
* Every item must have a status AND a location (even 🗑️ needs a reason for removal)
* Never use vague references like "etc.", "and others", or "various KPIs" — list every item explicitly
* If an item was split across multiple output locations, list all locations

5.2 — Page-by-Page Verification
After building the initial matrix, go back to each source document and re-read it page by page, checking every piece of content against the matrix.

5.3 — Verify Output Documents Match Audit Claims
For every "New Location" in the audit, open the actual output document and confirm the content is actually there.

5.4 — Build Summary Statistics

| Metric | Count |
|--------|-------|
| Total discrete information items audited | [N] |
| Items captured directly (✅) | [N] |
| Items consolidated from duplicates (🔀) | [N] |
| Items intentionally removed (🗑️) | [N] (list each with reason) |
| Items lost | **0** (must be zero) |

5.5 — Document Engineering Input Items
Any item that is structurally captured but data-incomplete goes in an engineering input table:

| # | Item | Action Needed |
|---|------|--------------|
| 1 | [Description] | [What the engineering/data team needs to provide] |

Completion Gate
Traceability matrix complete with every item from every source page. Page-by-page verification done. Output documents spot-checked against audit claims. Summary statistics show zero items lost. Engineering input items documented.

PHASE 6: SECOND-PASS VALIDATION

Objective
Catch anything the first audit missed. This phase exists because the first pass will almost certainly miss 3–8% of items.

Actions

6.1 — Semantic Gap Scan
For each source document, ask: "If I deleted the original and only had the new documents, could the LLM answer every question the original enabled?"

Focus on:
* Lists that were summarized (did every individual list item survive?)
* Tables that were restructured (did every row and column survive?)
* Example queries (were they migrated as patterns, or did they contain unique information that was lost?)
* Implicit rules embedded in examples
* "Soft" business context sections that seem narrative but contain real operational information

6.2 — Structural Integrity Check
Verify the output documents reference each other correctly:
* Every filter ID in 04 that is referenced in 01 or in conditional docs actually exists in 04
* Every join pattern ID in 02 matches what's used in 05
* Every mapping in 03 uses column names that actually exist in 02
* Every override in conditional docs names a real filter/rule from 01 or 04

6.3 — Apply Fixes
When gaps are found:
1. Add the missing content to the appropriate output document
2. Update the audit traceability matrix
3. Update the summary statistics

Completion Gate
Second pass complete. All gaps found in this pass have been fixed. Audit updated. Confidence level: production-ready.

PHASE 7: FINAL PACKAGING

Objective
Produce the final deliverable set.

Actions

7.1 — Final File List

```
/context_docs/
  01_MASTER_RULES.md
  02_SCHEMA_REFERENCE.md
  03_BUSINESS_MAPPINGS.md
  04_DEFAULT_FILTERS.md
  05_QUERY_PATTERNS.md
  06_[DOMAIN]_CONTEXT.md        (0 or more, as needed)
  07_[DOMAIN]_CONTEXT.md        (0 or more, as needed)
  ...
  CROSS_CHECK_AUDIT.md
```

7.2 — Calculate Final Token Budget

| Document | Lines | Est. Tokens |
|----------|-------|-------------|
| 01_MASTER_RULES | [N] | [N] |
| 02_SCHEMA_REFERENCE | [N] | [N] |
| 03_BUSINESS_MAPPINGS | [N] | [N] |
| 04_DEFAULT_FILTERS | [N] | [N] |
| 05_QUERY_PATTERNS | [N] | [N] |
| 06+ conditional docs | [N] | [N] |
| TOTAL | [N] | [N] |

Original total:  [N] tokens
New total:       [N] tokens
Reduction:       [N]% ([N] tokens saved)
Contradictions:  [N] → 0

7.3 — Produce Handoff Summary

```
## What Changed
- [N] source documents → [N] output documents
- [N]% token reduction
- [N] contradictions resolved
- [N] items requiring engineering input

## How to Use
- Documents 01–05 are ALWAYS loaded into the LLM context
- Documents 06+ are loaded ONLY when triggered (see 01_MASTER_RULES activation triggers)
- CROSS_CHECK_AUDIT traces every original item to its new location

## How to Extend
- New tables → add to 02_SCHEMA_REFERENCE
- New business terms or codes → add to 03_BUSINESS_MAPPINGS
- New mandatory filters → add to 04_DEFAULT_FILTERS
- New query templates → add to 05_QUERY_PATTERNS
- New domain workflows → create new 0X_[DOMAIN]_CONTEXT using the conditional template
```

Completion Gate
All files produced. Token budget calculated. Handoff summary written. Ready for production deployment.

APPENDIX A: Anti-Patterns to Avoid

| # | Anti-Pattern | Why It's Bad | How to Fix |
|---|-------------|-------------|-----------|
| 1 | "etc." in audit entries | Hides missing items | List every item explicitly |
| 2 | Multiple documents claiming priority | LLM can't resolve competing labels | Only 01_MASTER_RULES owns priority language |
| 3 | Filters defined inside business mappings | Breaks separation of concerns | Filters go ONLY in 04_DEFAULT_FILTERS |
| 4 | Circular references | LLM reasoning loops | Information flows P0→P5, never upward |
| 5 | Overrides without naming what they override | Ambiguous | Always reference by ID |
| 6 | Prose where a table works | LLMs extract tables 3–5x more reliably | Use tables for 3+ items with 2+ attributes |
| 7 | Descriptions instead of code | LLM interprets differently each time | Always include exact SparkSQL |
| 8 | Un-numbered rules | Ambiguous references | Every rule gets a unique ID |
| 9 | Examples contradicting rules | Confusion | Rules always win; fix the example |
| 10 | Meta-content in operational docs | Wasted tokens | Remove all meta-commentary |
| 11 | Skipping Phase 6 | Misses 3–8% of items | Phase 6 is mandatory |
| 12 | One massive document | Worse LLM adherence | Follow modular architecture |
| 13 | Assuming source examples are correct | May contain outdated SQL | Validate examples against rules |

APPENDIX B: Checklist — One-Page Summary

PHASE 0: INVENTORY
[ ] All source documents listed with token estimates
[ ] Baseline total calculated
[ ] Document relationships mapped (duplicates, contradictions)

PHASE 1: DISCOVERY
[ ] Every source document read end-to-end
[ ] Every discrete item extracted and tagged by type
[ ] Item count and type distribution calculated

PHASE 2: CONFLICT DETECTION
[ ] All exact duplicates cataloged
[ ] All contradictions identified with resolutions
[ ] All ambiguities flagged for engineering input
[ ] Conflict register built

PHASE 3: ARCHITECTURE DESIGN
[ ] Core + conditional document structure designed
[ ] Priority system (P0–P5) assigned
[ ] Every source item mapped to output document + section
[ ] Conditional activation triggers defined

PHASE 4: CONTENT MIGRATION
[ ] Documents written in dependency order (01 first, conditionals last)
[ ] All formatting rules (M-1 through M-11) applied
[ ] Every rule has a unique ID
[ ] Every conditional rule has an explicit trigger
[ ] Every override names what it overrides by ID

PHASE 5: CROSS-CHECK AUDIT
[ ] Traceability matrix built (one section per source file)
[ ] Page-by-page verification done
[ ] Output docs spot-checked against audit claims
[ ] Summary statistics: zero items lost
[ ] Engineering input items documented

PHASE 6: SECOND-PASS VALIDATION
[ ] Semantic gap scan completed
[ ] Structural integrity verified (cross-references valid)
[ ] All gaps fixed, audit updated

PHASE 7: FINAL PACKAGING
[ ] All output files produced
[ ] Token budget calculated and reported
[ ] Handoff summary written

APPENDIX C: Quick-Reference — What Goes Where

| If the item is about... | Put it in... |
|------------------------|-------------|
| Priority between documents | 01_MASTER_RULES |
| Resolving a contradiction | 01_MASTER_RULES |
| A universal output format rule | 01_MASTER_RULES |
| Something the LLM should NEVER do | 01_MASTER_RULES |
| When to load a conditional document | 01_MASTER_RULES |
| A table definition, column list, data types | 02_SCHEMA_REFERENCE |
| How two tables join together | 02_SCHEMA_REFERENCE |
| What a product/item code means | 03_BUSINESS_MAPPINGS |
| A category or subcategory classification | 03_BUSINESS_MAPPINGS |
| Business terminology | 03_BUSINESS_MAPPINGS |
| A KPI name and calculation formula | 03_BUSINESS_MAPPINGS |
| Customer segmentation definitions | 03_BUSINESS_MAPPINGS |
| A SparkSQL WHERE/JOIN filter | 04_DEFAULT_FILTERS |
| Date range filter patterns | 04_DEFAULT_FILTERS |
| A complete SparkSQL answering a business question | 05_QUERY_PATTERNS |
| A domain-specific rule that OVERRIDES a default | 06+_CONTEXT |
| A domain-specific process or workflow | 06+_CONTEXT |
| Meta-commentary about the documents themselves | NOWHERE — Remove it |

APPENDIX D: Conditional Document Template

```
# 0X — [DOMAIN NAME] CONTEXT

> **Role:** [One sentence describing this document's scope]
> **Priority:** P5 (Conditional — loaded only when activated)
> **Activation:** Triggered by [01_MASTER_RULES trigger A-N]

---

## Section 1: Activation Trigger

**Load this document when the user query contains any of:**
- [keyword 1]
- [keyword 2]
- [intent pattern]

**Do NOT load when:**
- [exclusion condition]

---

## Section 2: Filter Overrides (vs 04_DEFAULT_FILTERS)

| Default Filter | Action | Reason |
|---------------|--------|--------|
| F-[N] ([name]) | REMOVE | [Why this filter doesn't apply] |
| F-[N] ([name]) | KEEP | [Why it still applies] |
| [new filter] | ADD | [Why this domain needs it] |

---

## Section 3: Definitions

| Term | Definition | Technical Mapping |
|------|-----------|-----------------|
| [Term] | [Business meaning] | [Column, code, or table reference] |

---

## Section 4: Process Flow

### Step 1: [Action]
[Details, SparkSQL if applicable]

### Step 2: [Action]
[Details, SparkSQL if applicable]

(Continue as needed)

---

## Section 5: Validation Checklist

Before executing any [domain] query, verify:
- [ ] [Check 1]
- [ ] [Check 2]
- [ ] [Check 3]

---

## Scalability
To add new [domain items]:
1. [Instruction for extending this document]
```

Blueprint version: 2.0 | Generic methodology for NL-to-SparkSQL context restructuring across any brand or industry.
