"""
Payload builders for the 5 context documents.

Ported from reference: services/payload_builder.py
Pure logic — no I/O changes needed.
"""

from collections import defaultdict
from typing import Optional

from app.config import settings


def _pct(n: int, total: int) -> float:
    return round(n / max(total, 1) * 100, 1)


# Keys that are purely statistical / not useful to the LLM
_STAT_KEYS = {"n", "pct", "count", "unique"}


def strip_stats(obj):
    """Recursively strip count/pct/n fields from payload structures."""
    if isinstance(obj, dict):
        non_stat_keys = [k for k in obj if k not in _STAT_KEYS]
        if not non_stat_keys and obj:
            return True
        return {k: strip_stats(v) for k, v in obj.items() if k not in _STAT_KEYS}
    if isinstance(obj, list):
        return [strip_stats(item) for item in obj]
    return obj


def build_payload_01(
    counters: dict, alias_conv: dict, fingerprints: list,
    total_weight: int, inclusions: Optional[dict] = None,
) -> dict:
    """Master rules payload."""
    inc = inclusions or {}
    structural_counter = dict(counters.get("structural", []))
    ss = {
        k: {"count": v, "pct": _pct(v, total_weight)}
        for k, v in structural_counter.items()
        if not inc or inc.get("structural", {}).get(k, True)
    }
    select_cols = dict(counters.get("select_cols", []))
    total_sel = sum(select_cols.values()) or 1
    avg_sel = sum(k * v for k, v in select_cols.items()) / total_sel

    spark_fns_ref = {
        "DATE_FORMAT", "DATE_SUB", "DATE_ADD", "DATEDIFF", "TRUNC",
        "COLLECT_LIST", "COLLECT_SET", "EXPLODE", "POSEXPLODE",
        "ARRAY_CONTAINS", "NVL", "NVL2", "COALESCE", "CONCAT_WS",
        "REGEXP_EXTRACT", "REGEXP_REPLACE", "TO_DATE", "TO_TIMESTAMP",
        "UNIX_TIMESTAMP", "FROM_UNIXTIME",
    }
    function_counter = dict(counters.get("function", []))
    spark_fns = [
        f for f in function_counter if f in spark_fns_ref
        and (not inc.get("spark_functions") or inc["spark_functions"].get(f, True))
    ]

    func_items = counters.get("function", [])
    if inc.get("functions"):
        func_items = [(f, n) for f, n in func_items if inc["functions"].get(str(f), True)]
    top_fns = [{"f": f, "n": n, "pct": _pct(n, total_weight)} for f, n in func_items]

    ac = {}
    for t, aliases in alias_conv.items():
        if inc.get("aliases") and not inc["aliases"].get(t, True):
            continue
        if isinstance(aliases, list):
            ac[t] = [a for a, _ in aliases[:3]]
        elif isinstance(aliases, dict):
            ac[t] = list(aliases.keys())[:3]
        else:
            ac[t] = []

    table_items = counters.get("table", [])
    if inc.get("tables"):
        table_items = [(t, n) for t, n in table_items if inc["tables"].get(str(t), True)]
    core_tables = [{"t": t, "n": n, "pct": _pct(n, total_weight)} for t, n in table_items]

    limit_items = counters.get("limit_val", [])
    output_items = {
        "avg_select_cols": round(avg_sel, 1),
        "order_by_pct": _pct(structural_counter.get("has_order_by", 0), total_weight),
        "limit_pct": _pct(structural_counter.get("has_limit", 0), total_weight),
        "common_limits": [{"v": v, "n": n} for v, n in limit_items[:5]],
    }
    if inc.get("output"):
        output_items = {k: v for k, v in output_items.items() if inc["output"].get(k, True)}

    return {
        "total_queries": total_weight,
        "unique_queries": len(fingerprints),
        "structural_stats": ss,
        "top_functions": top_fns,
        "alias_conventions": ac,
        "output": output_items,
        "spark_functions": spark_fns,
        "core_tables": core_tables,
    }


def build_payload_02(
    counters: dict, alias_conv: dict, total_weight: int,
    inclusions: Optional[dict] = None,
) -> dict:
    """Schema reference payload."""
    inc = inclusions or {}
    table_items = counters.get("table", [])
    column_items = counters.get("column", [])
    join_pair_items = counters.get("join_pair", [])
    join_cond_items = counters.get("join_cond", [])

    tables = []
    for t, tc in table_items:
        if inc.get("tables") and not inc["tables"].get(str(t), True):
            continue
        cols = []
        for entry, n in column_items:
            entry_str = str(entry)
            if "." in entry_str:
                parts = entry_str.split(".")
                tb, col = parts[0], ".".join(parts[1:])
            elif isinstance(entry, (list, tuple)) and len(entry) >= 2:
                tb, col = str(entry[0]), str(entry[1])
            else:
                continue
            if tb != str(t):
                continue
            if inc.get("columns", {}).get(str(t)) and not inc["columns"][str(t)].get(col, True):
                continue
            cols.append({"col": col, "n": n, "pct": _pct(n, tc)})

        t_str = str(t)
        raw_aliases = alias_conv.get(t_str, [])
        if isinstance(raw_aliases, list):
            aliases = [a for a, _ in raw_aliases[:3]]
        elif isinstance(raw_aliases, dict):
            aliases = list(raw_aliases.keys())[:3]
        else:
            aliases = []
        tables.append({
            "table": t_str, "n": tc, "pct": _pct(tc, total_weight),
            "aliases": aliases, "columns": cols,
        })

    joins = []
    for pair, n in join_pair_items:
        if isinstance(pair, (list, tuple)):
            parts = [str(p) for p in pair]
        else:
            parts = str(pair).split("|") if "|" in str(pair) else [str(pair)]
        if len(parts) < 2:
            continue
        left, right = parts[0], parts[1]
        pair_key = f"{left}|{right}"
        if inc.get("joins") and not inc["joins"].get(pair_key, True):
            continue
        conds = []
        for cond_entry, c in join_cond_items:
            if isinstance(cond_entry, (list, tuple)) and len(cond_entry) >= 3:
                cl, cr, con = str(cond_entry[0]), str(cond_entry[1]), str(cond_entry[2])
                if (cl == left and cr == right) or (cl == right and cr == left):
                    conds.append({"on": con, "n": c})
                    if len(conds) >= 5:
                        break
            else:
                cond_str = str(cond_entry)
                if left in cond_str and right in cond_str:
                    conds.append({"on": cond_str, "n": c})
                    if len(conds) >= 5:
                        break
        joins.append({"a": left, "b": right, "n": n, "pct": _pct(n, total_weight), "on": conds})

    type_heuristics = {
        "_id": "BIGINT/STRING", "_date": "DATE/TIMESTAMP",
        "_at": "TIMESTAMP", "_amount": "DECIMAL/DOUBLE",
        "_name": "STRING", "_code": "STRING(enum)", "_flag": "BOOLEAN",
        "is_": "BOOLEAN", "has_": "BOOLEAN",
    }
    if inc.get("type_heuristics"):
        type_heuristics = {k: v for k, v in type_heuristics.items() if inc["type_heuristics"].get(k, True)}

    return {"tables": tables, "join_patterns": joins, "type_heuristics": type_heuristics}


def build_payload_03(
    counters: dict, literal_vals: dict, fingerprints: list,
    total_weight: int, inclusions: Optional[dict] = None,
) -> dict:
    """Business mappings payload."""
    inc = inclusions or {}
    enums = {}
    for col, vc in literal_vals.items():
        if inc.get("enums") and not inc["enums"].get(col, True):
            continue
        if isinstance(vc, list):
            if len(vc) <= settings.max_enum_distinct:
                enums[col] = [{"v": v, "n": n} for v, n in vc[:30]]
        elif isinstance(vc, dict):
            if len(vc) <= settings.max_enum_distinct:
                safe_items = [(v, n) for v, n in vc.items() if isinstance(n, (int, float))]
                enums[col] = [{"v": v, "n": n} for v, n in sorted(safe_items, key=lambda x: -x[1])[:30]]

    agg_items = counters.get("agg_pattern", [])
    kpis = [{"f": str(f), "n": n, "pct": _pct(n, total_weight)} for f, n in agg_items]

    group_items = counters.get("group_by", [])
    if inc.get("dimensions"):
        group_items = [(e, n) for e, n in group_items if inc["dimensions"].get(str(e), True)]
    dims = [{"expr": str(e), "n": n, "pct": _pct(n, total_weight)} for e, n in group_items]

    cw_counter: dict = {}
    for fp in fingerprints:
        case_blocks = fp.get("case_when_blocks", []) if isinstance(fp, dict) else getattr(fp, "case_when_blocks", [])
        freq = fp.get("frequency", 1) if isinstance(fp, dict) else getattr(fp, "frequency", 1)
        for cw in case_blocks:
            normed = cw.strip().upper()[:200]
            cw_counter[normed] = cw_counter.get(normed, 0) + freq
    case_whens = [{"sql": s, "n": n} for s, n in sorted(cw_counter.items(), key=lambda x: -x[1])]
    if inc.get("case_whens"):
        case_whens = [cw for cw in case_whens if inc["case_whens"].get(cw["sql"], True)]

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
    if inc.get("nl_pairs"):
        nl_pairs = [p for p in nl_pairs if inc["nl_pairs"].get(p["nl"], True)]

    return {"enums": enums, "kpis": kpis, "dimensions": dims,
            "case_whens": case_whens, "nl_pairs": nl_pairs}


def build_payload_04(
    classified_filters: list, total_weight: int, table_freq: dict,
    inclusions: Optional[dict] = None,
) -> dict:
    """Default filters payload."""
    inc = inclusions or {}
    mandatory = []
    for f in classified_filters:
        if f.get("tier") != "MANDATORY":
            continue
        cond = f["condition"]
        if inc.get("mandatory") and not inc["mandatory"].get(cond, True):
            continue
        mandatory.append({"cond": cond, "pct": round(f["global_pct"] * 100, 1), "n": f["count"]})

    tbl_groups: dict = defaultdict(list)
    for f in sorted(classified_filters, key=lambda x: -x["count"]):
        if f.get("tier") != "TABLE-DEFAULT":
            continue
        for t, p in f.get("table_pcts", {}).items():
            if p >= 0.30:
                if inc.get("table_defaults", {}).get(t) and not inc["table_defaults"][t].get(f["condition"], True):
                    continue
                tbl_groups[t].append({"cond": f["condition"], "pct": round(p * 100, 1), "n": f["count"]})

    top_tables = sorted(tbl_groups.items(), key=lambda x: -table_freq.get(x[0], 0))
    tbl_def = {t: filters for t, filters in top_tables}

    common = []
    for f in classified_filters:
        if f.get("tier") != "COMMON":
            continue
        cond = f["condition"]
        if inc.get("common") and not inc["common"].get(cond, True):
            continue
        common.append({"cond": cond, "pct": round(f["global_pct"] * 100, 1), "n": f["count"]})

    date_kw = (
        "DATE_SUB", "DATE_ADD", "DATEDIFF", "DATE_FORMAT", "TO_DATE",
        "CURRENT_DATE", "CURRENT_TIMESTAMP", "INTERVAL", "_date", "_at", "_ts",
    )
    date_pats = []
    for f in classified_filters:
        if any(k.lower() in f["condition"].lower() for k in date_kw):
            date_pats.append({"cond": f["condition"], "tier": f["tier"], "pct": round(f["global_pct"] * 100, 1)})
    if inc.get("date_patterns"):
        date_pats = [dp for dp in date_pats if inc["date_patterns"].get(dp["cond"], True)]

    return {"total": total_weight, "mandatory": mandatory, "table_defaults": tbl_def,
            "common": common, "date_patterns": date_pats}


def build_payload_05(
    clusters: list, fingerprints: list, inclusions: Optional[dict] = None,
) -> dict:
    """Query patterns payload."""
    inc = inclusions or {}
    fp_map = {}
    for fp in fingerprints:
        fp_id = fp.get("id") if isinstance(fp, dict) else getattr(fp, "id", None)
        if fp_id:
            fp_map[fp_id] = fp

    cdata = []
    for cl in clusters:
        sig = cl.get("sig", "")
        if inc.get("clusters") and not inc["clusters"].get(sig, True):
            continue
        rep_id = cl.get("rep_id")
        cpx_id = cl.get("cpx_id")
        rep = fp_map.get(rep_id)
        cpx = fp_map.get(cpx_id)

        def _get(obj, key, default=""):
            if obj is None:
                return default
            return obj.get(key, default) if isinstance(obj, dict) else getattr(obj, key, default)

        entry = {
            "sig": sig,
            "count": cl.get("count", 0),
            "unique": cl.get("n_unique", 0),
            "functions": cl.get("functions", []),
            "group_by": cl.get("group_by", []),
            "where": cl.get("where", []),
            "rep_sql": (_get(rep, "canonical_sql", "") or "")[:800],
            "cpx_sql": (_get(cpx, "canonical_sql", "") or "")[:1200],
        }
        rep_nl = _get(rep, "nl_question")
        cpx_nl = _get(cpx, "nl_question")
        if rep_nl:
            entry["rep_nl"] = rep_nl
        if cpx_nl:
            entry["cpx_nl"] = cpx_nl
        cdata.append(entry)

    templates = {}
    checks = {
        "CTE": "has_cte", "Window": "has_window", "CASE WHEN": "has_case",
        "UNION": "has_union", "Subquery": "has_subquery",
    }
    for name, attr in checks.items():
        if inc.get("templates") and not inc["templates"].get(name, True):
            continue
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

    nl = []
    for fp in fingerprints:
        nl_q = fp.get("nl_question") if isinstance(fp, dict) else getattr(fp, "nl_question", None)
        canon = fp.get("canonical_sql", "") if isinstance(fp, dict) else getattr(fp, "canonical_sql", "")
        if nl_q and nl_q.strip():
            nl.append({"nl": nl_q, "sql": canon[:600]})
    if inc.get("nl_pairs"):
        nl = [p for p in nl if inc["nl_pairs"].get(p["nl"], True)]

    return {"clusters": cdata, "templates": templates, "nl_pairs": nl}


def build_all_payloads(
    counters: dict, alias_conv: dict, literal_vals: dict,
    fingerprints: list, clusters: list, classified_filters: list,
    total_weight: int, inclusions: Optional[dict] = None,
) -> dict:
    """Build all 5 payloads at once."""
    inc = inclusions or {}
    table_freq = dict(counters.get("table", []))
    return {
        "01_MASTER": build_payload_01(counters, alias_conv, fingerprints, total_weight, inc.get("01_MASTER")),
        "02_SCHEMA": build_payload_02(counters, alias_conv, total_weight, inc.get("02_SCHEMA")),
        "03_BUSINESS": build_payload_03(counters, literal_vals, fingerprints, total_weight, inc.get("03_BUSINESS")),
        "04_FILTERS": build_payload_04(classified_filters, total_weight, table_freq, inc.get("04_FILTERS")),
        "05_PATTERNS": build_payload_05(clusters, fingerprints, inc.get("05_PATTERNS")),
    }
