"""Enrichment passes for Databricks context doc generation.

Ported from sparksql_context_pipeline notebook (Section 2C).
These functions mine additional intelligence from SQL fingerprints, counters,
and Thrift schema to produce richer context documents.

All functions are pure (no LLM calls, no DB access) — they operate on
in-memory data structures from the analysis pipeline.
"""

import logging
import re
from collections import Counter, defaultdict
from typing import Optional

from app.services.databricks.schema_client import ThriftSchema

logger = logging.getLogger(__name__)

# ── Importance Tier Thresholds ──
TIER_CRITICAL_PCT = 0.10   # top 10%
TIER_IMPORTANT_PCT = 0.40  # next 30%
MAX_ENUM_DISTINCT = 50     # max distinct values before treating as continuous


def _bt(s: str) -> str:
    """Strip backticks — not supported in this env."""
    return s.replace("`", "") if isinstance(s, str) else s


def _fp_get(fp, key: str, default=None):
    """Get attribute from fingerprint (handles both dict and object)."""
    if isinstance(fp, dict):
        return fp.get(key, default)
    return getattr(fp, key, default)


def compute_importance_tier(rank: int, total: int) -> str:
    """Assign importance tier based on rank position (0-indexed, sorted by frequency desc)."""
    if total == 0:
        return "supplementary"
    pct = rank / total
    if pct < TIER_CRITICAL_PCT:
        return "critical"
    elif pct < TIER_CRITICAL_PCT + TIER_IMPORTANT_PCT:
        return "important"
    return "supplementary"


# ── Helper ──

def _col_to_natural_name(col: str) -> str:
    """Convert snake_case column name to human-readable form."""
    return col.replace("_", " ").strip()


# ── Enriched Metrics ──

def build_enriched_metrics(counters: dict, fingerprints: list) -> list[dict]:
    """Build enriched metric definitions with full SQL expressions.

    Instead of just {"f": "SUM", "col": "bill_amount"}, extracts the actual SQL
    expression from the corpus (e.g., SUM(CASE WHEN ...), COUNT(DISTINCT ...)).
    """
    agg_counter = counters.get("agg_pattern", Counter())
    metrics = []
    seen = set()

    for (fn, col), _ in agg_counter.most_common():
        key = (fn, col)
        if key in seen:
            continue
        seen.add(key)

        # Find actual SQL expression from a fingerprint that uses this pattern
        example_expr = f"{fn}({col})"
        for fp in fingerprints:
            if fn in fp.get("functions", fp.functions if hasattr(fp, "functions") else []):
                qcols = fp.get("qualified_columns", getattr(fp, "qualified_columns", []))
                for qcol in qcols:
                    if len(qcol) >= 2 and qcol[1] == col:
                        canon = fp.get("canonical_sql", getattr(fp, "canonical_sql", ""))
                        # Look for full expression patterns
                        for pattern in [
                            f"{fn}(CASE", f"{fn}(DISTINCT", f"{fn}({col})",
                            f"{fn.lower()}(CASE", f"{fn.lower()}(DISTINCT", f"{fn.lower()}({col})",
                        ]:
                            idx = canon.upper().find(pattern.upper())
                            if idx >= 0:
                                # Extract full expression (match parentheses)
                                depth, end = 0, idx
                                for i in range(idx, len(canon)):
                                    if canon[i] == '(':
                                        depth += 1
                                    elif canon[i] == ')':
                                        depth -= 1
                                        if depth == 0:
                                            end = i + 1
                                            break
                                extracted = canon[idx:end].strip()
                                if len(extracted) > len(example_expr):
                                    example_expr = extracted
                                break
                        break

        natural = _col_to_natural_name(col)
        agg_prefix = {
            "SUM": "total", "COUNT": "count of", "AVG": "average",
            "MIN": "minimum", "MAX": "maximum",
        }.get(fn, fn)
        metrics.append({
            "metric": f"{fn}({col})",
            "full_expr": example_expr,
            "business_name": f"{agg_prefix} {natural}",
        })

    logger.info(f"[enrichment] built {len(metrics)} enriched metrics")
    return metrics


# ── Verified Queries ──

def build_verified_queries(fingerprints: list, clusters: list) -> list[dict]:
    """Extract verified NL→SQL pairs as a first-class artifact.

    Priority:
    1. Queries with actual NL questions from the corpus (highest confidence)
    2. Representative queries from popular clusters (inferred intent)
    """
    verified = []
    seen_sqls = set()

    # Tier 1: Actual NL→SQL pairs from corpus
    nl_fps = sorted(
        [fp for fp in fingerprints if _fp_get(fp, "nl_question")],
        key=lambda fp: _fp_get(fp, "frequency", 1),
        reverse=True,
    )
    for fp in nl_fps:
        sql_key = _bt(_fp_get(fp, "canonical_sql", "")).strip().upper()
        if sql_key and sql_key not in seen_sqls:
            verified.append({
                "question": _fp_get(fp, "nl_question", "").strip(),
                "sql": _bt(_fp_get(fp, "canonical_sql", "")),
                "tables": _fp_get(fp, "tables", []),
                "source": "corpus",
            })
            seen_sqls.add(sql_key)

    # Tier 2: Representative queries from top clusters
    fp_map = {_fp_get(fp, "id", i): fp for i, fp in enumerate(fingerprints)}
    for cl in clusters:
        rep_id = cl.get("rep_id")
        rep = fp_map.get(rep_id) if rep_id else None
        if not rep:
            continue
        sql_key = _bt(_fp_get(rep, "canonical_sql", "")).strip().upper()
        if sql_key in seen_sqls:
            continue
        verified.append({
            "question": None,
            "sql": _bt(_fp_get(rep, "canonical_sql", "")),
            "tables": _fp_get(rep, "tables", []),
            "source": "inferred_from_cluster",
        })
        seen_sqls.add(sql_key)

    corpus_count = sum(1 for v in verified if v["source"] == "corpus")
    inferred_count = sum(1 for v in verified if v["source"] == "inferred_from_cluster")
    logger.info(f"[enrichment] verified queries: {corpus_count} corpus, {inferred_count} inferred")
    return verified


# ── Synonym Map ──

_NL_STOPWORDS = frozenset({
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "her", "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "its", "may", "new", "now", "old", "see", "way", "who", "did",
    "let", "say", "she", "too", "use", "what", "where", "when", "which",
    "with", "from", "this", "that", "have", "been", "will", "each", "make",
    "like", "than", "them", "then", "into", "some", "could", "would",
    "there", "their", "about", "after", "other", "these", "those",
    "first", "also", "many", "most", "very", "just", "over", "such",
    "show", "give", "list", "find", "count", "total", "many", "much",
    "select", "query", "table", "column", "data", "number",
})


def build_synonym_map(
    fingerprints: list,
    counters: dict,
    enriched_metrics: list,
    thrift_schema: Optional[ThriftSchema] = None,
) -> dict[str, list[str]]:
    """Mine business synonyms from multiple sources.

    Sources:
    1. Thrift display_name → column_name (confirmed, highest confidence)
    2. NL questions → column mappings
    3. SELECT aliases → column mappings
    4. Metric business names → column mappings
    """
    synonyms: dict[str, set[str]] = defaultdict(set)

    # Source 0 (Thrift): display_name → column_name (confirmed synonyms)
    if thrift_schema:
        for table in thrift_schema.tables.values():
            for col in table.columns:
                if col.display_name and col.display_name != col.name:
                    synonyms[col.name].add(col.display_name.lower())

    # Source 1: NL questions → column mappings
    for fp in fingerprints:
        nl = getattr(fp, "nl_question", None)
        if not nl or not nl.strip():
            continue
        nl_lower = nl.lower()
        qcols = getattr(fp, "qualified_columns", [])
        for qcol in qcols:
            if len(qcol) < 2:
                continue
            col = qcol[1]
            col_lower = col.lower()
            natural = col_lower.replace("_", " ")
            nl_words = set(re.findall(r'\b[a-z]{3,}\b', nl_lower)) - _NL_STOPWORDS
            col_parts = set(col_lower.split("_")) - {"id", "at", "is", "no", "by", "of", "in", "to", "dt"}
            col_related = set()
            for word in nl_words:
                if word not in col_parts and word not in natural.split():
                    col_related.add(word)
            if 0 < len(col_related) <= 3:
                synonyms[col].update(col_related)

    # Source 2: SELECT aliases from canonical SQL
    alias_pattern = re.compile(
        r'(?:SUM|COUNT|AVG|MIN|MAX|COALESCE|NVL)\s*\([^)]*?\b(\w+)\b[^)]*\)\s+(?:AS\s+)?(\w+)',
        re.IGNORECASE,
    )
    for fp in fingerprints:
        canon = getattr(fp, "canonical_sql", "")
        for match in alias_pattern.finditer(canon):
            col_name, alias = match.group(1), match.group(2)
            if alias.lower() != col_name.lower() and len(alias) > 2:
                synonyms[col_name].add(alias.lower())

    # Source 3: Metric business names
    for m in enriched_metrics:
        metric_str = m.get("metric", "")
        bname = m.get("business_name", "")
        # Extract column from metric (e.g., "SUM(bill_amount)" → "bill_amount")
        col_match = re.search(r'\((\w+)\)', metric_str)
        if col_match and bname:
            col = col_match.group(1)
            synonyms[col].add(bname.lower())

    # Convert sets to sorted lists
    result = {col: sorted(syns) for col, syns in synonyms.items() if syns}
    logger.info(f"[enrichment] synonym map: {len(result)} columns with synonyms")
    return result


# ── Join Path Hints ──

def mine_join_path_hints(
    fingerprints: list,
    counters: dict,
    custom_tables: set[str],
    thrift_schema: Optional[ThriftSchema] = None,
) -> list[dict]:
    """Extract multi-hop join paths from query corpus.

    Thrift boost: Validate join conditions against real FK relationships.
    """
    path_counter: Counter = Counter()
    path_conditions: dict[tuple, list[str]] = {}

    for fp in fingerprints:
        join_graph = getattr(fp, "join_graph", [])
        if len(join_graph) < 2:
            # Also capture 2-table joins
            if len(join_graph) == 1:
                edge = join_graph[0]
                left = getattr(edge, "left", None)
                right = getattr(edge, "right", None)
                on_cond = getattr(edge, "on_condition", None)
                if left and right:
                    pair = (left, right)
                    freq = getattr(fp, "frequency", 1)
                    path_counter[pair] += freq
                    if pair not in path_conditions and on_cond:
                        path_conditions[pair] = [on_cond]
            continue

        chain = []
        conditions = []
        for edge in join_graph:
            left = getattr(edge, "left", None)
            right = getattr(edge, "right", None)
            on_cond = getattr(edge, "on_condition", None)
            if left and left not in chain:
                chain.append(left)
            if right and right not in chain:
                chain.append(right)
            if on_cond:
                conditions.append(on_cond)

        if len(chain) >= 3:
            chain_key = tuple(chain)
            path_counter[chain_key] += getattr(fp, "frequency", 1)
            if chain_key not in path_conditions:
                path_conditions[chain_key] = conditions

    result = []
    for path, freq in path_counter.most_common(30):
        involves_custom = any(t in custom_tables for t in path)
        hint = " → ".join(t.split(".")[-1] for t in path)

        # Thrift boost: check if FK relationships confirm this path
        fk_confirmed = False
        if thrift_schema and len(path) >= 2:
            for i in range(len(path) - 1):
                t = thrift_schema.get_table(path[i])
                if t:
                    for col in t.columns:
                        if col.foreign_key and path[i + 1] in col.foreign_key:
                            fk_confirmed = True
                            break

        result.append({
            "path": list(path),
            "conditions": path_conditions.get(path, []),
            "frequency": freq,
            "involves_custom_table": involves_custom,
            "fk_confirmed": fk_confirmed,
            "business_hint": hint,
        })

    multi_hop = sum(1 for r in result if len(r["path"]) >= 3)
    logger.info(f"[enrichment] {len(result)} join path patterns ({multi_hop} multi-hop)")
    return result


# ── Common Pitfalls ──

def mine_common_pitfalls(
    counters: dict,
    classified_filters: list,
    fingerprints: list,
    custom_tables: set[str],
    thrift_schema: Optional[ThriftSchema] = None,
) -> list[dict]:
    """Mine common query pitfalls from the corpus.

    Thrift boost: Flag queries that ignore FK relationships or standard filters.
    """
    pitfalls = []

    # 1. Ambiguous columns — same column name in multiple tables
    col_tables: dict[str, set[str]] = defaultdict(set)
    col_counter = counters.get("column", Counter())
    for (tbl, col), _ in col_counter.most_common():
        col_tables[col].add(tbl)

    for col, tables in col_tables.items():
        if len(tables) >= 2:
            custom_count = sum(1 for t in tables if t in custom_tables)
            if custom_count >= 1:
                tbl_list = ", ".join(sorted(tables)[:4])
                pitfalls.append({
                    "type": "ambiguous_column",
                    "warning": f"Column {col} exists in multiple tables ({tbl_list}). "
                               f"Always qualify with table name/alias.",
                    "severity": "high",
                })

    # 2. Mandatory filters easy to forget
    for f in classified_filters:
        if isinstance(f, dict) and f.get("tier") == "MANDATORY":
            pitfalls.append({
                "type": "mandatory_filter",
                "warning": f"ALWAYS include filter: {f.get('condition', '')}",
                "severity": "critical",
            })

    # 3. Tables co-occurring but never directly joined (need bridge table)
    cooccur: Counter = Counter()
    for fp in fingerprints:
        tbls = sorted(getattr(fp, "tables", []))
        for i, a in enumerate(tbls):
            for b in tbls[i + 1:]:
                cooccur[(a, b)] += getattr(fp, "frequency", 1)

    join_pair_counter = counters.get("join_pair", Counter())
    joined_pairs = set()
    for pair, _ in join_pair_counter.most_common():
        if len(pair) == 2:
            joined_pairs.add(tuple(sorted(pair)))

    for pair, freq in cooccur.most_common():
        if pair not in joined_pairs and freq >= 5:
            a, b = pair
            if a in custom_tables or b in custom_tables:
                pitfalls.append({
                    "type": "missing_direct_join",
                    "warning": f"Tables {a} and {b} co-occur in queries but are never "
                               f"directly joined. They likely need a bridge table.",
                    "severity": "medium",
                })

    # 4. Thrift boost: Standard filters from schema not appearing in corpus
    if thrift_schema:
        corpus_filters = set()
        for f in classified_filters:
            if isinstance(f, dict):
                corpus_filters.add(f.get("condition", "").lower())

        for table in thrift_schema.tables.values():
            for col in table.columns:
                if col.standard_filter:
                    filter_lower = col.standard_filter.lower()
                    if not any(filter_lower in cf for cf in corpus_filters):
                        pitfalls.append({
                            "type": "missing_standard_filter",
                            "warning": f"Table {table.name} has standard filter "
                                       f"{col.standard_filter} (from schema) but it's not "
                                       f"consistently used in the query corpus.",
                            "severity": "high",
                        })

    logger.info(f"[enrichment] {len(pitfalls)} pitfalls mined")
    return pitfalls


# ── Correctness Criteria ──

def generate_correctness_criteria(
    classified_filters: list,
    counters: dict,
    fingerprints: list,
    custom_tables: set[str],
    thrift_schema: Optional[ThriftSchema] = None,
) -> list[dict]:
    """Generate query correctness criteria from corpus patterns.

    Thrift boost: Include type-safety rules from real column types.
    """
    criteria = []

    # 1. Mandatory filter rules
    for f in classified_filters:
        if isinstance(f, dict) and f.get("tier") == "MANDATORY":
            criteria.append({
                "rule": f"Every query MUST include: {f['condition']}",
                "scope": "all_queries",
                "source": "mandatory_filter",
            })

    # 2. Table-default filter rules
    table_defaults: dict[str, list[str]] = defaultdict(list)
    for f in classified_filters:
        if isinstance(f, dict) and f.get("tier") == "TABLE-DEFAULT":
            for t, pct in f.get("table_pcts", {}).items():
                if pct >= 0.70:
                    table_defaults[t].append(f["condition"])

    for tbl, conditions in table_defaults.items():
        for cond in conditions[:3]:
            criteria.append({
                "rule": f"When querying {tbl}, include filter: {cond}",
                "scope": f"table:{tbl.split('.')[-1]}",
                "source": "table_default_filter",
            })

    # 3. Join correctness
    join_pair_counter = counters.get("join_pair", Counter())
    join_cond_counter = counters.get("join_cond", Counter())
    for pair, _ in join_pair_counter.most_common(20):
        if len(pair) < 2:
            continue
        conds = [on for (*p, on), _ in join_cond_counter.most_common()
                 if tuple(sorted(p)) == tuple(sorted(pair)) and on]
        if conds:
            criteria.append({
                "rule": f"Join {pair[0]} to {pair[1]} ON {conds[0]}",
                "scope": f"join:{pair[0]}|{pair[1]}",
                "source": "corpus_join_pattern",
            })

    # 4. Aggregation rules
    agg_counter = counters.get("agg_pattern", Counter())
    agg_cols: dict[str, Counter] = defaultdict(Counter)
    for (fn, col), cnt in agg_counter.most_common():
        agg_cols[col][fn] += cnt

    for col, fns in agg_cols.items():
        dominant_fn, dominant_cnt = fns.most_common(1)[0]
        total = sum(fns.values())
        if total >= 10 and dominant_cnt / total >= 0.80:
            criteria.append({
                "rule": f"Column {col} is typically aggregated with {dominant_fn}()",
                "scope": f"column:{col}",
                "source": "dominant_aggregation",
            })

    # 5. Thrift boost: Type-safety rules from real column types
    if thrift_schema:
        for table in thrift_schema.tables.values():
            for col in table.columns:
                if col.data_type and col.data_type.upper() in ("DATE", "TIMESTAMP"):
                    criteria.append({
                        "rule": f"{table.name}.{col.name} is {col.data_type} — "
                                f"use date functions, not string comparisons",
                        "scope": f"column:{table.name}.{col.name}",
                        "source": "thrift_schema_type",
                    })

    logger.info(f"[enrichment] {len(criteria)} correctness criteria generated")
    return criteria


# ── Business Evidence ──

def generate_business_evidence(
    counters: dict,
    literal_vals: dict,
    fingerprints: list,
    enriched_metrics: list,
    classified_filters: list,
    thrift_schema: Optional[ThriftSchema] = None,
) -> list[dict]:
    """Generate business logic evidence statements.

    Thrift boost: Use column descriptions as authoritative evidence.
    """
    evidence = []

    # 1. Metric definitions
    for m in enriched_metrics[:50]:
        bname = m.get("business_name", "")
        expr = m.get("metric", "")
        full = m.get("full_expr", "")
        if bname and expr:
            evidence.append({
                "evidence": f"'{bname}' = {full if full and full != expr else expr}",
                "type": "metric_definition",
                "confidence": "corpus_derived",
            })

    # 2. Mandatory filter rules
    for f in classified_filters:
        if isinstance(f, dict) and f.get("tier") == "MANDATORY":
            evidence.append({
                "evidence": f"Implicit rule: {f.get('condition', '')} is always required",
                "type": "implicit_filter",
                "confidence": "high",
            })

    # 3. Literal value patterns
    for col, vals in literal_vals.items():
        if isinstance(vals, dict):
            if len(vals) > MAX_ENUM_DISTINCT:
                continue
            top_vals = [str(v) for v in list(vals.keys())[:5]]
            if all(len(str(v)) == 2 and str(v).isupper() for v in list(vals.keys())[:10]):
                evidence.append({
                    "evidence": f"{col} values are 2-letter uppercase codes "
                                f"(e.g., {', '.join(top_vals[:3])})",
                    "type": "value_pattern",
                    "confidence": "corpus_derived",
                })

    # 4. Thrift boost: Column descriptions as authoritative evidence
    if thrift_schema:
        for table in thrift_schema.tables.values():
            for col in table.columns:
                if col.description and len(col.description) > 10:
                    evidence.append({
                        "evidence": f"{table.name}.{col.name}: {col.description}",
                        "type": "schema_description",
                        "confidence": "confirmed",
                    })

    logger.info(f"[enrichment] {len(evidence)} business evidence items")
    return evidence


# ── Master function ──

def run_all_enrichments(
    fingerprints: list,
    counters: dict,
    clusters: list,
    classified_filters: list,
    literal_vals: dict,
    thrift_schema: Optional[ThriftSchema] = None,
) -> dict:
    """Run all enrichment passes and return consolidated results.

    Returns dict with keys:
        enriched_metrics, verified_queries, synonyms, join_path_hints,
        pitfalls, correctness_criteria, business_evidence
    """
    # Determine custom tables (write_db tables)
    custom_tables = set()
    if thrift_schema:
        custom_tables = set(thrift_schema.custom_tables)

    enriched_metrics = build_enriched_metrics(counters, fingerprints)
    verified_queries = build_verified_queries(fingerprints, clusters)
    synonyms = build_synonym_map(fingerprints, counters, enriched_metrics, thrift_schema)
    join_path_hints = mine_join_path_hints(fingerprints, counters, custom_tables, thrift_schema)
    pitfalls = mine_common_pitfalls(
        counters, classified_filters, fingerprints, custom_tables, thrift_schema,
    )
    correctness_criteria = generate_correctness_criteria(
        classified_filters, counters, fingerprints, custom_tables, thrift_schema,
    )
    business_evidence = generate_business_evidence(
        counters, literal_vals, fingerprints, enriched_metrics, classified_filters, thrift_schema,
    )

    logger.info(
        f"[enrichment] all passes complete: "
        f"{len(enriched_metrics)} metrics, {len(verified_queries)} queries, "
        f"{len(synonyms)} synonym cols, {len(join_path_hints)} join paths, "
        f"{len(pitfalls)} pitfalls, {len(correctness_criteria)} criteria, "
        f"{len(business_evidence)} evidence"
    )

    return {
        "enriched_metrics": enriched_metrics,
        "verified_queries": verified_queries,
        "synonyms": synonyms,
        "join_path_hints": join_path_hints,
        "pitfalls": pitfalls,
        "correctness_criteria": correctness_criteria,
        "business_evidence": business_evidence,
    }
