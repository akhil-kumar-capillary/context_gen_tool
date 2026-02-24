"""
Frequency counters — builds 12 counters from QFP list.

Ported from reference: services/frequency_counters.py
Pure logic — no I/O changes needed.
"""

from collections import Counter, defaultdict

from app.services.databricks.qfp import QFP
from app.services.databricks.fingerprint_engine import _norm


def build_counters(fps: list[QFP]) -> tuple[dict, dict, dict, int]:
    """
    Build all frequency counters from fingerprints.
    Returns: (counters_dict, literal_vals, alias_conv, total_weight)
    """
    C = {
        "table": Counter(),
        "column": Counter(),
        "function": Counter(),
        "join_pair": Counter(),
        "join_cond": Counter(),
        "where": Counter(),
        "group_by": Counter(),
        "agg_pattern": Counter(),
        "order_by": Counter(),
        "structural": Counter(),
        "limit_val": Counter(),
        "select_cols": Counter(),
    }
    literal_vals: dict = defaultdict(Counter)
    alias_conv: dict = defaultdict(Counter)
    total_w = 0

    for fp in fps:
        w = fp.frequency
        total_w += w

        for t in fp.tables:
            C["table"][t] += w
        for ta, col in fp.qualified_columns:
            resolved = fp.alias_map.get(ta, ta)
            C["column"][(resolved, col)] += w
            for fn in fp.functions:
                if fn in ("SUM", "COUNT", "AVG", "MIN", "MAX"):
                    C["agg_pattern"][(fn, col)] += w
        for fn in fp.functions:
            C["function"][fn] += w
        for e in fp.join_graph:
            if e.left:
                pair = tuple(sorted([e.left, e.right]))
                C["join_pair"][pair] += w
                C["join_cond"][(*pair, e.on_condition)] += w
            else:
                C["join_pair"][(e.right,)] += w
        for cond in fp.where_conditions:
            C["where"][_norm(cond)] += w
        for g in fp.group_by:
            C["group_by"][g] += w
        for col, vals in fp.literals.items():
            for v in vals:
                literal_vals[col][v] += w
        for flag in (
            "has_cte", "has_window", "has_union", "has_case",
            "has_subquery", "has_having", "has_order_by", "has_distinct", "has_limit",
        ):
            if getattr(fp, flag):
                C["structural"][flag] += w
        for a, t in fp.alias_map.items():
            alias_conv[t][a] += w
        for o in fp.order_by:
            C["order_by"][o] += w
        if fp.limit_value is not None:
            C["limit_val"][fp.limit_value] += w
        C["select_cols"][fp.select_col_count] += w

    return C, dict(literal_vals), dict(alias_conv), total_w


def counters_to_serializable(
    C: dict, literal_vals: dict, alias_conv: dict
) -> dict:
    """Convert Counters to JSON-serializable dicts for storage and frontend."""

    def _counter_to_list(counter: Counter, limit: int = 500) -> list:
        """Convert counter to sorted list of [key, count] pairs."""
        return [
            [k if isinstance(k, (str, int, float)) else list(k), v]
            for k, v in counter.most_common(limit)
        ]

    return {
        "table": _counter_to_list(C["table"]),
        "column": _counter_to_list(C["column"]),
        "function": _counter_to_list(C["function"]),
        "join_pair": _counter_to_list(C["join_pair"]),
        "join_cond": _counter_to_list(C["join_cond"], 200),
        "where": _counter_to_list(C["where"], 300),
        "group_by": _counter_to_list(C["group_by"], 200),
        "agg_pattern": _counter_to_list(C["agg_pattern"], 200),
        "order_by": _counter_to_list(C["order_by"], 200),
        "structural": _counter_to_list(C["structural"]),
        "limit_val": _counter_to_list(C["limit_val"]),
        "select_cols": _counter_to_list(C["select_cols"]),
        "literal_vals": {
            col: [[v, n] for v, n in vc.most_common(30)]
            for col, vc in literal_vals.items()
        },
        "alias_conv": {
            t: [[a, n] for a, n in ac.most_common(5)]
            for t, ac in alias_conv.items()
        },
    }
