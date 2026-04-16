"""
Payload builders for the 4 context documents.

Ported from sparksql_context_pipeline notebook with:
- Importance tiers (critical/important/supplementary) on every item
- Gradual degradation (full → abbreviated → metadata-only)
- Thrift schema integration for ground-truth column types
- Transparent drop logging
"""

import logging
import re
from collections import Counter, defaultdict
from typing import Optional

from app.services.databricks.enrichment import compute_importance_tier
from app.services.databricks.schema_client import ThriftSchema

logger = logging.getLogger(__name__)


# ── Compression Thresholds ──
# Business Logic
BL_FULL_METRICS = 200     # top N metrics: metric + business_name + full_expr
BL_ABBREV_METRICS = 100   # next N: metric + business_name (no full_expr)
BL_CASE_WHEN_MAX_CHARS = 800

# Filters & Guards
FG_MAX_TABLE_DEFAULTS = 150
FG_MAX_COMMON = 150
FG_MAX_DATE_PATTERNS = 75
FG_MAX_SITUATIONAL = 50
FG_FILTER_MAX_CHARS = 600

# Query Cookbook
QC_FULL_SQL_CLUSTERS = 150
QC_ABBREV_SQL_CLUSTERS = 100
QC_FULL_VERIFIED = 150
QC_ABBREV_VERIFIED = 100
QC_MAX_CLUSTERS = 300
QC_MAX_VERIFIED = 300
QC_SQL_PREVIEW_CHARS = 800
QC_MAX_SQL_CHARS = 3000

MAX_ENUM_DISTINCT = 50


def _cap_sql(sql: str, max_chars: int) -> str:
    return sql[:max_chars] + "..." if len(sql) > max_chars else sql


def _abbrev(cond: str) -> str:
    return cond[:FG_FILTER_MAX_CHARS] + "..." if len(cond) > FG_FILTER_MAX_CHARS else cond


def _norm(s: str) -> str:
    return s.strip().upper()[:BL_CASE_WHEN_MAX_CHARS]


# ── CASE WHEN mapping extraction ──

_CASE_WHEN_PATTERN = re.compile(
    r"WHEN\s+(\w+)\s*=\s*['\"]?(\w+)['\"]?\s+THEN\s+'([^']+)'",
    re.IGNORECASE,
)


def _extract_case_when_mappings(case_whens: list[str]) -> tuple[dict, list[dict]]:
    """Extract structured value→label mappings from CASE WHEN blocks.

    Returns: (confirmed_mappings: {col: {val: label}}, structured_case_whens: list)
    """
    confirmed_mappings: dict[str, dict] = defaultdict(dict)
    structured = []

    for cw in case_whens:
        matches = _CASE_WHEN_PATTERN.findall(cw)
        if matches:
            cols_in_cw = set()
            for col, val, label in matches:
                confirmed_mappings[col][val] = label
                cols_in_cw.add(col)
            structured.append({
                "sql": cw[:BL_CASE_WHEN_MAX_CHARS],
                "columns": list(cols_in_cw),
                "mappings": {col: {val: label for c, val, label in matches if c == col}
                             for col in cols_in_cw},
            })
        else:
            structured.append({"sql": cw[:BL_CASE_WHEN_MAX_CHARS]})

    return dict(confirmed_mappings), structured


# ═══════════════════════════════════════════════════════════════
# 01_DATA_MODEL
# ═══════════════════════════════════════════════════════════════

def build_payload_data_model(
    counters: dict,
    alias_conv: dict,
    thrift_schema: Optional[ThriftSchema] = None,
    join_path_hints: Optional[list] = None,
) -> dict:
    """DATA_MODEL: Full schema for custom tables, names for standard tables.

    Thrift schema provides ground-truth columns, types, FKs, display names.
    """
    custom_tables_set = set(thrift_schema.custom_tables) if thrift_schema else set()
    table_counter = counters.get("table", Counter())
    column_counter = counters.get("column", Counter())
    join_pair_counter = counters.get("join_pair", Counter())
    join_cond_counter = counters.get("join_cond", Counter())

    table_items = table_counter.most_common() if isinstance(table_counter, Counter) else list(table_counter.items()) if isinstance(table_counter, dict) else table_counter
    total_tables = len(table_items)

    custom_table_details = []
    standard_table_refs = []

    for rank, (t, _) in enumerate(table_items):
        tier = compute_importance_tier(rank, total_tables)
        t_str = str(t)

        if t_str in custom_tables_set:
            # Custom tables: full column detail
            cols_from_counter = [col for (tb, col), _ in (column_counter.most_common() if isinstance(column_counter, Counter) else column_counter) if str(tb) == t_str]

            # Enrich with Thrift data if available
            thrift_cols = []
            if thrift_schema:
                tt = thrift_schema.get_table(t_str)
                if tt:
                    for tc in tt.columns:
                        thrift_cols.append({
                            "name": tc.name,
                            "data_type": tc.data_type,
                            "display_name": tc.display_name,
                            "description": tc.description,
                        })

            entry = {
                "table": t_str,
                "source": "write_db (custom)",
                "importance": tier,
                "columns": cols_from_counter,
            }
            if thrift_cols:
                entry["schema_columns"] = thrift_cols
            custom_table_details.append(entry)
        else:
            # Standard tables: name + importance only
            entry = {"table": t_str, "importance": tier}
            # Add Thrift column count for reference
            if thrift_schema:
                tt = thrift_schema.get_table(t_str)
                if tt:
                    entry["column_count"] = len(tt.columns)
                    entry["type"] = tt.table_type
            standard_table_refs.append(entry)

    # Join graph — custom joins get full detail
    custom_joins = []
    standard_joins_count = 0
    for pair, _ in (join_pair_counter.most_common() if isinstance(join_pair_counter, Counter) else join_pair_counter):
        if isinstance(pair, (list, tuple)) and len(pair) >= 2:
            a, b = str(pair[0]), str(pair[1])
        else:
            parts = str(pair).split("|")
            if len(parts) < 2:
                continue
            a, b = parts[0], parts[1]

        conds = []
        for cond_entry, _ in (join_cond_counter.most_common() if isinstance(join_cond_counter, Counter) else join_cond_counter):
            if isinstance(cond_entry, (list, tuple)) and len(cond_entry) >= 3:
                cl, cr, on = str(cond_entry[0]), str(cond_entry[1]), str(cond_entry[2])
                if (cl == a and cr == b) or (cl == b and cr == a):
                    conds.append(on)
                    if len(conds) >= 3:
                        break

        if a in custom_tables_set or b in custom_tables_set:
            custom_joins.append({"a": a, "b": b, "on": conds})
        else:
            standard_joins_count += 1

    result = {
        "custom_tables": custom_table_details,
        "standard_tables": standard_table_refs,
        "custom_joins": custom_joins,
        "standard_joins_summary": f"{standard_joins_count} joins between standard tables (see db_schema/ for details)",
    }

    if join_path_hints:
        result["join_path_hints"] = join_path_hints

    logger.info(
        f"[payload] DATA_MODEL: {len(custom_table_details)} custom, "
        f"{len(standard_table_refs)} standard tables"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 02_FILTERS_GUARDS
# ═══════════════════════════════════════════════════════════════

def build_payload_filters_guards(
    classified_filters: list,
    pitfalls: Optional[list] = None,
    correctness_criteria: Optional[list] = None,
    thrift_schema: Optional[ThriftSchema] = None,
) -> dict:
    """FILTERS_GUARDS: mandatory, table-default, common, date, situational filters.

    Thrift boost: Merge standard_filter fields from schema.
    """
    # Table-default filters
    table_defaults: dict[str, list[str]] = defaultdict(list)
    for f in sorted(classified_filters, key=lambda x: -x.get("count", 0)):
        if f.get("tier") == "TABLE-DEFAULT":
            for t, p in f.get("table_pcts", {}).items():
                if p >= 0.30:
                    table_defaults[t].append(_abbrev(f["condition"]))

    table_default_list = [
        {"table": t, "filters": filters}
        for t, filters in sorted(table_defaults.items(), key=lambda x: -len(x[1]))
    ][:FG_MAX_TABLE_DEFAULTS]

    # Mandatory filters
    mandatory = [_abbrev(f["condition"]) for f in classified_filters if f.get("tier") == "MANDATORY"]

    # Thrift boost: add standard filters from schema
    if thrift_schema:
        existing_mandatory = set(m.lower() for m in mandatory)
        for table in thrift_schema.tables.values():
            for col in table.columns:
                if col.standard_filter and col.standard_filter.lower() not in existing_mandatory:
                    mandatory.append(f"[schema] {col.standard_filter}")

    # Common filters with importance tiers
    common_all = [f for f in classified_filters if f.get("tier") == "COMMON"]
    common = []
    for rank, f in enumerate(common_all[:FG_MAX_COMMON]):
        tier = compute_importance_tier(rank, min(len(common_all), FG_MAX_COMMON))
        common.append({"condition": _abbrev(f["condition"]), "importance": tier})

    # Date patterns
    date_kw = (
        "DATE_SUB", "DATE_ADD", "DATEDIFF", "DATE_FORMAT", "TO_DATE",
        "CURRENT_DATE", "CURRENT_TIMESTAMP", "INTERVAL", "_date", "_at", "_ts",
    )
    date_pats = [
        {"cond": _abbrev(f["condition"]), "tier": f["tier"]}
        for f in classified_filters
        if any(k.lower() in f.get("condition", "").lower() for k in date_kw)
    ][:FG_MAX_DATE_PATTERNS]

    result: dict = {
        "mandatory_filters": mandatory,
        "table_default_filters": table_default_list,
        "common_filters": common,
        "date_filter_patterns": date_pats,
    }

    # Situational filters
    situational = [f for f in classified_filters if f.get("tier") == "SITUATIONAL"]
    if FG_MAX_SITUATIONAL > 0 and situational:
        result["situational_filters"] = [_abbrev(f["condition"]) for f in situational[:FG_MAX_SITUATIONAL]]

    if pitfalls:
        result["common_pitfalls"] = pitfalls
    if correctness_criteria:
        result["correctness_criteria"] = correctness_criteria

    logger.info(
        f"[payload] FILTERS_GUARDS: {len(mandatory)} mandatory, "
        f"{len(table_default_list)} table defaults, {len(common)} common"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 03_BUSINESS_LOGIC
# ═══════════════════════════════════════════════════════════════

def build_payload_business_logic(
    counters: dict,
    literal_vals: dict,
    fingerprints: list,
    enriched_metrics: list,
    synonyms: Optional[dict] = None,
    business_evidence: Optional[list] = None,
) -> dict:
    """BUSINESS_LOGIC: metrics, codes, enums, CASE WHEN, dimensions, NL→SQL.

    With importance tiers and gradual degradation for metrics.
    """
    # Collect CASE WHEN blocks
    cw_counter: Counter = Counter()
    for fp in fingerprints:
        case_blocks = fp.get("case_when_blocks", []) if isinstance(fp, dict) else getattr(fp, "case_when_blocks", [])
        freq = fp.get("frequency", 1) if isinstance(fp, dict) else getattr(fp, "frequency", 1)
        for cw in case_blocks:
            cw_counter[_norm(cw)] += freq
    case_whens = [s for s, _ in cw_counter.most_common()]

    # Extract structured CASE WHEN mappings
    confirmed_mappings, structured_case_whens = _extract_case_when_mappings(case_whens)

    # Build enums enriched with confirmed labels
    enums = {}
    for col, vc in literal_vals.items():
        if isinstance(vc, dict):
            if len(vc) > MAX_ENUM_DISTINCT:
                continue
            values = list(vc.keys())
        elif isinstance(vc, list):
            if len(vc) > MAX_ENUM_DISTINCT:
                continue
            values = [v for v, _ in vc]
        else:
            continue

        col_mappings = confirmed_mappings.get(col, {})
        if col_mappings:
            enums[col] = {
                "values": values,
                "confirmed_labels": {str(v): col_mappings[str(v)] for v in values if str(v) in col_mappings},
                "unconfirmed": [v for v in values if str(v) not in col_mappings],
            }
        else:
            enums[col] = {"values": values, "confirmed_labels": {}, "unconfirmed": values}

    # Metrics with gradual degradation
    metrics_trimmed = []
    total_metrics = len(enriched_metrics)
    for i, m in enumerate(enriched_metrics):
        tier = compute_importance_tier(i, total_metrics)
        if i < BL_FULL_METRICS:
            metrics_trimmed.append({**m, "importance": tier})
        elif i < BL_FULL_METRICS + BL_ABBREV_METRICS:
            metrics_trimmed.append({
                "metric": m["metric"],
                "business_name": m.get("business_name", ""),
                "importance": tier,
            })
        else:
            metrics_trimmed.append({"metric": m["metric"], "importance": tier})

    # Dimensions with tiers
    group_by_counter = counters.get("group_by", Counter())
    dims_raw = group_by_counter.most_common() if isinstance(group_by_counter, Counter) else list(group_by_counter.items()) if isinstance(group_by_counter, dict) else group_by_counter
    dims = []
    for rank, (e, _) in enumerate(dims_raw):
        tier = compute_importance_tier(rank, len(dims_raw))
        dims.append({"dimension": str(e), "importance": tier})

    # NL→SQL pairs
    nl_pairs = []
    seen_sigs = set()
    for fp in fingerprints:
        tables = fp.get("tables", []) if isinstance(fp, dict) else getattr(fp, "tables", [])
        nl_q = fp.get("nl_question") if isinstance(fp, dict) else getattr(fp, "nl_question", None)
        canon = fp.get("canonical_sql", "") if isinstance(fp, dict) else getattr(fp, "canonical_sql", "")
        if nl_q and nl_q.strip():
            sig = "|".join(sorted(tables))
            if sig not in seen_sigs:
                nl_pairs.append({"nl": nl_q, "sql": canon[:500], "tables": tables})
                seen_sigs.add(sig)

    result: dict = {
        "enums": enums,
        "metrics": metrics_trimmed,
        "dimensions": dims,
        "case_whens": structured_case_whens,
        "nl_pairs": nl_pairs,
    }
    if synonyms:
        result["synonyms"] = synonyms
    if business_evidence:
        result["business_evidence"] = business_evidence

    logger.info(
        f"[payload] BUSINESS_LOGIC: {len(metrics_trimmed)} metrics, "
        f"{len(enums)} enums, {len(dims)} dims"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# 04_QUERY_COOKBOOK
# ═══════════════════════════════════════════════════════════════

def build_payload_query_cookbook(
    counters: dict,
    alias_conv: dict,
    clusters: list,
    fingerprints: list,
    verified_queries: Optional[list] = None,
) -> dict:
    """QUERY_COOKBOOK: verified queries, templates, clusters, conventions.

    With importance tiers and gradual degradation (full → abbreviated → metadata-only).
    """
    fp_map = {}
    for fp in fingerprints:
        fp_id = fp.get("id") if isinstance(fp, dict) else getattr(fp, "id", None)
        if fp_id:
            fp_map[fp_id] = fp

    # Clusters with gradual degradation
    cdata = []
    total_clusters_for_tier = min(len(clusters), QC_MAX_CLUSTERS)
    for i, cl in enumerate(clusters[:QC_MAX_CLUSTERS]):
        rep = fp_map.get(cl.get("rep_id"))
        cpx = fp_map.get(cl.get("cpx_id"))
        tier = compute_importance_tier(i, total_clusters_for_tier)

        def _get(obj, key, default=""):
            if obj is None:
                return default
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        if i < QC_FULL_SQL_CLUSTERS:
            entry = {
                "sig": cl.get("sig", ""),
                "functions": cl.get("functions", []),
                "group_by": cl.get("group_by", []),
                "importance": tier,
                "rep_sql": _cap_sql(_get(rep, "canonical_sql", ""), QC_MAX_SQL_CHARS),
                "cpx_sql": _cap_sql(_get(cpx, "canonical_sql", ""), QC_MAX_SQL_CHARS),
            }
            rep_nl = _get(rep, "nl_question")
            cpx_nl = _get(cpx, "nl_question")
            if rep_nl:
                entry["rep_nl"] = rep_nl
            if cpx_nl:
                entry["cpx_nl"] = cpx_nl
        elif i < QC_FULL_SQL_CLUSTERS + QC_ABBREV_SQL_CLUSTERS:
            entry = {
                "sig": cl.get("sig", ""),
                "functions": cl.get("functions", []),
                "group_by": cl.get("group_by", []),
                "importance": tier,
                "rep_sql": _cap_sql(_get(rep, "canonical_sql", ""), QC_SQL_PREVIEW_CHARS),
            }
            rep_nl = _get(rep, "nl_question")
            if rep_nl:
                entry["rep_nl"] = rep_nl
        else:
            entry = {
                "sig": cl.get("sig", ""),
                "functions": cl.get("functions", []),
                "group_by": cl.get("group_by", []),
                "importance": tier,
            }
        cdata.append(entry)

    # Verified queries with gradual degradation
    vq_trimmed = []
    if verified_queries:
        total_vq = min(len(verified_queries), QC_MAX_VERIFIED)
        for i, vq in enumerate(verified_queries[:QC_MAX_VERIFIED]):
            tier = compute_importance_tier(i, total_vq)
            if i < QC_FULL_VERIFIED:
                vq_trimmed.append({
                    **vq,
                    "sql": _cap_sql(vq.get("sql", ""), QC_MAX_SQL_CHARS),
                    "importance": tier,
                })
            elif i < QC_FULL_VERIFIED + QC_ABBREV_VERIFIED:
                vq_trimmed.append({
                    **vq,
                    "sql": _cap_sql(vq.get("sql", ""), QC_SQL_PREVIEW_CHARS),
                    "importance": tier,
                })
            else:
                vq_trimmed.append({
                    "question": vq.get("question"),
                    "tables": vq.get("tables", []),
                    "source": vq.get("source", ""),
                    "importance": tier,
                })

    # Structural templates
    templates = {}
    checks = {
        "CTE": "has_cte", "Window": "has_window", "CASE WHEN": "has_case",
        "UNION": "has_union", "Subquery": "has_subquery",
    }
    for name, attr in checks.items():
        cands = [
            fp for fp in fingerprints
            if (fp.get(attr) if isinstance(fp, dict) else getattr(fp, attr, False))
        ]
        if cands:
            def _sql(f):
                return f.get("canonical_sql", "") if isinstance(f, dict) else getattr(f, "canonical_sql", "")
            ideal = [fp for fp in cands if 200 <= len(_sql(fp)) <= 800]
            c = ideal[0] if ideal else min(cands, key=lambda f: len(_sql(f)))
            tables = c.get("tables", []) if isinstance(c, dict) else getattr(c, "tables", [])
            templates[name] = {"sql": _sql(c)[:1000], "tables": tables}

    # Conventions
    conventions = {}
    ac = {}
    for t, aliases in alias_conv.items():
        if isinstance(aliases, list):
            ac[t] = [a for a, _ in aliases[:3]]
        elif isinstance(aliases, dict):
            ac[t] = list(aliases.keys())[:3]
    if ac:
        conventions["alias_style"] = ac

    result: dict = {
        "clusters": cdata,
        "verified_queries": vq_trimmed,
        "templates": templates,
    }
    if conventions:
        result["conventions"] = conventions

    logger.info(
        f"[payload] QUERY_COOKBOOK: {len(cdata)} clusters, "
        f"{len(vq_trimmed)} verified queries, {len(templates)} templates"
    )
    return result


# ═══════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════

def build_all_payloads(
    counters: dict,
    alias_conv: dict,
    literal_vals: dict,
    fingerprints: list,
    clusters: list,
    classified_filters: list,
    total_weight: int,
    thrift_schema: Optional[ThriftSchema] = None,
    enrichment_data: Optional[dict] = None,
) -> dict:
    """Build all 4 payloads at once.

    Args:
        enrichment_data: Output from run_all_enrichments() containing
            enriched_metrics, verified_queries, synonyms, join_path_hints,
            pitfalls, correctness_criteria, business_evidence.
    """
    enr = enrichment_data or {}

    return {
        "01_DATA_MODEL": build_payload_data_model(
            counters, alias_conv, thrift_schema,
            join_path_hints=enr.get("join_path_hints"),
        ),
        "02_FILTERS_GUARDS": build_payload_filters_guards(
            classified_filters,
            pitfalls=enr.get("pitfalls"),
            correctness_criteria=enr.get("correctness_criteria"),
            thrift_schema=thrift_schema,
        ),
        "03_BUSINESS_LOGIC": build_payload_business_logic(
            counters, literal_vals, fingerprints,
            enriched_metrics=enr.get("enriched_metrics", []),
            synonyms=enr.get("synonyms"),
            business_evidence=enr.get("business_evidence"),
        ),
        "04_QUERY_COOKBOOK": build_payload_query_cookbook(
            counters, alias_conv, clusters, fingerprints,
            verified_queries=enr.get("verified_queries"),
        ),
    }
