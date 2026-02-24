"""
Query clustering + filter classification.

Ported from reference: services/cluster_builder.py
Pure logic — no I/O changes needed.
"""

from collections import Counter, defaultdict

from app.config import settings
from app.services.databricks.qfp import QFP
from app.services.databricks.fingerprint_engine import _norm


def build_clusters(fps: list[QFP]) -> list[dict]:
    """Group queries by table signature, pick representative + complex per cluster."""
    clusters: dict[str, dict] = {}
    fp_map = {fp.id: fp for fp in fps}

    for fp in fps:
        sig = "|".join(sorted(set(fp.tables))) or "__NONE__"
        clusters.setdefault(sig, {"ids": [], "count": 0})
        clusters[sig]["ids"].append(fp.id)
        clusters[sig]["count"] += fp.frequency

    result = []
    for sig, info in sorted(clusters.items(), key=lambda x: -x[1]["count"]):
        members = [fp_map[i] for i in info["ids"] if i in fp_map]
        if not members:
            continue
        shortest = min(members, key=lambda f: len(f.raw_sql))
        longest = max(members, key=lambda f: len(f.raw_sql))

        fc, gc, wc = Counter(), Counter(), Counter()
        for m in members:
            for fn in m.functions:
                fc[fn] += m.frequency
            for g in m.group_by:
                gc[g] += m.frequency
            for w in m.where_conditions:
                wc[_norm(w)] += m.frequency

        result.append(
            {
                "sig": sig,
                "count": info["count"],
                "n_unique": len(info["ids"]),
                "rep_id": shortest.id,
                "cpx_id": longest.id,
                "rep_sql": (
                    shortest.canonical_sql[:800]
                    if shortest.canonical_sql
                    else shortest.raw_sql[:800]
                ),
                "cpx_sql": (
                    longest.canonical_sql[:1200]
                    if longest.canonical_sql
                    else longest.raw_sql[:1200]
                ),
                "functions": [f for f, _ in fc.most_common(8)],
                "group_by": [g for g, _ in gc.most_common(5)],
                "where": [w for w, _ in wc.most_common(5)],
                "tables": sig.split("|") if sig != "__NONE__" else [],
            }
        )

    return result


def classify_filters(
    where_freq: Counter,
    fps: list[QFP],
    total_w: int,
) -> list[dict]:
    """Classify WHERE conditions into MANDATORY / TABLE-DEFAULT / COMMON / SITUATIONAL."""
    if total_w == 0:
        return []

    tbl_totals: Counter = Counter()
    tbl_cond: dict = defaultdict(Counter)
    for fp in fps:
        for t in fp.tables:
            tbl_totals[t] += fp.frequency
        for c in fp.where_conditions:
            nc = _norm(c)
            for t in fp.tables:
                tbl_cond[t][nc] += fp.frequency

    result = []
    for cond, cnt in where_freq.most_common():
        gpct = cnt / total_w
        tpcts: dict[str, float] = {}
        for t, tt in tbl_totals.items():
            tc = tbl_cond[t].get(cond, 0)
            if tc > 0:
                tpcts[t] = tc / tt
        max_tpct = max(tpcts.values()) if tpcts else 0

        if gpct >= settings.filter_mandatory_pct:
            tier = "MANDATORY"
        elif max_tpct >= settings.filter_table_default_pct:
            tier = "TABLE-DEFAULT"
        elif max_tpct >= settings.filter_common_pct:
            tier = "COMMON"
        else:
            tier = "SITUATIONAL"

        result.append(
            {
                "condition": cond,
                "tier": tier,
                "global_pct": round(gpct, 4),
                "table_pcts": {t: round(p, 4) for t, p in tpcts.items()},
                "count": cnt,
            }
        )

    return result
