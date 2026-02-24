"""
QFP extraction engine — parses SQL queries into structured fingerprints.

Ported from reference: services/fingerprint_engine.py
Key changes: ProcessPoolExecutor → asyncio.to_thread() for CPU-bound parsing,
all orchestration functions become async.
Pure extraction logic (extract_fingerprint) remains synchronous.
"""

import asyncio
import logging
import os
import re
from typing import Optional, Callable, Awaitable

import sqlglot
from sqlglot import parse_one, exp
from sqlglot.optimizer.qualify import qualify

from app.config import settings
from app.services.databricks.qfp import QFP, JoinEdge

logger = logging.getLogger(__name__)

DIALECT = settings.dialect

# Cap workers — leave 1 core free for the event loop
_MAX_WORKERS = max(1, min(os.cpu_count() or 4, 8) - 1)


# --- Utility functions ---


def _norm(sql: str) -> str:
    """Normalize whitespace in SQL."""
    return " ".join(sql.split()).strip()


def _is_select(sql: str) -> bool:
    u = _norm(sql).upper()
    return u.startswith("SELECT") or u.startswith("WITH")


def _normalize_params(sql: str) -> str:
    """Replace dynamic placeholders with dummy literals for parsing."""
    sql = re.sub(r"\$\{(\w+)\}", r"'PARAM_\1'", sql)
    sql = re.sub(r"(?<!')\{(\w+)\}(?!')", r"'PARAM_\1'", sql)
    sql = re.sub(r":(\w+)", r"'PARAM_\1'", sql)
    sql = sql.replace("?", "'PLACEHOLDER'")
    sql = re.sub(r"@(\w+)", r"'PARAM_\1'", sql)
    return sql


def _split_and(expr) -> list[str]:
    if isinstance(expr, exp.And):
        return _split_and(expr.left) + _split_and(expr.right)
    return [expr.sql(dialect=DIALECT)]


_FUNC_MAP = {
    "SUM": "SUM", "COUNT": "COUNT", "AVG": "AVG", "MIN": "MIN", "MAX": "MAX",
    "COALESCE": "COALESCE", "IF": "IF", "CONCAT": "CONCAT",
    "DATEFORMAT": "DATE_FORMAT", "DATESUB": "DATE_SUB", "DATEADD": "DATE_ADD",
    "DATEDIFF": "DATEDIFF", "YEAR": "YEAR", "MONTH": "MONTH",
    "TRUNC": "TRUNC", "ROUND": "ROUND", "CAST": "CAST",
    "ROWNUMBER": "ROW_NUMBER", "RANK": "RANK", "DENSERANK": "DENSE_RANK",
    "LAG": "LAG", "LEAD": "LEAD",
}


# --- Ingest & Dedup ---


async def ingest_and_dedup(
    sql_records: list[dict],
    on_progress: Optional[Callable] = None,
) -> list[dict]:
    """
    Phase 0: Filter to SELECT/WITH queries, exact dedup, canonical dedup.

    CPU-bound canonical parsing is offloaded to thread pool via asyncio.to_thread().

    Input: list of dicts with keys: cleaned_sql (or CleanedSQL), is_valid, sql_hash, etc.
    Returns: deduplicated list of dicts with keys: sql, original_sql, nl_question, frequency.
    """
    corpus = []
    for r in sql_records:
        sql = r.get("cleaned_sql") or r.get("CleanedSQL") or ""
        if not sql or not sql.strip():
            continue
        sql = sql.strip()
        if not _is_select(sql):
            continue
        corpus.append({
            "sql": sql,
            "nl_question": r.get("nl_question"),
            "frequency": r.get("frequency", 1),
        })

    if not corpus:
        return []

    if on_progress:
        await on_progress(
            "dedup", 0, len(corpus),
            f"Filtering: {len(corpus)} SELECT/WITH queries from {len(sql_records)} total",
        )

    # Pass 1: exact dedup on normalized uppercase
    seen: dict[str, dict] = {}
    for e in corpus:
        key = _norm(e["sql"]).upper()
        if key in seen:
            seen[key]["frequency"] += e["frequency"]
            if not seen[key]["nl_question"] and e.get("nl_question"):
                seen[key]["nl_question"] = e["nl_question"]
        else:
            seen[key] = dict(e)
    p1 = list(seen.values())

    if on_progress:
        await on_progress(
            "dedup", 0, len(p1),
            f"Exact dedup: {len(corpus)} -> {len(p1)} unique queries. Running canonical dedup...",
        )

    # Pass 2: canonical dedup via sqlglot (offloaded to thread pool)
    def _canonical_parse_batch(sqls: list[str]) -> list[str]:
        """CPU-bound batch parsing — runs in thread pool."""
        results = []
        for sql in sqls:
            try:
                results.append(
                    parse_one(sql, dialect=DIALECT)
                    .sql(dialect=DIALECT, pretty=False)
                    .upper()
                )
            except Exception:
                results.append(_norm(sql).upper())
        return results

    sql_strings = [e["sql"] for e in p1]
    canonical_results = await asyncio.to_thread(_canonical_parse_batch, sql_strings)

    # Merge canonically
    seen2: dict[str, dict] = {}
    for i, e in enumerate(p1):
        canon = canonical_results[i]
        if canon in seen2:
            seen2[canon]["frequency"] += e["frequency"]
            if not seen2[canon]["nl_question"] and e.get("nl_question"):
                seen2[canon]["nl_question"] = e["nl_question"]
        else:
            seen2[canon] = e

    result = list(seen2.values())

    if on_progress:
        await on_progress(
            "dedup", len(p1), len(p1),
            f"Canonical dedup complete: {len(p1)} -> {len(result)} unique queries",
        )

    # Normalize parameters for parsing
    for e in result:
        e["original_sql"] = e["sql"]
        e["sql"] = _normalize_params(e["sql"])

    return result


# --- Fingerprint Extraction (synchronous — CPU bound) ---


def extract_fingerprint(
    qid: str, entry: dict
) -> tuple[Optional[QFP], Optional[dict]]:
    """Parse one SQL query -> (QFP, None) on success, (None, failure_dict) on error."""
    sql = entry["sql"]
    try:
        ast = parse_one(sql, dialect=DIALECT)
    except Exception as e:
        return None, {
            "id": qid,
            "raw_sql": entry.get("original_sql", sql),
            "error": str(e),
            "nl_question": entry.get("nl_question"),
        }

    fp = QFP(
        id=qid,
        raw_sql=entry.get("original_sql", sql),
        nl_question=entry.get("nl_question"),
        frequency=entry.get("frequency", 1),
    )

    # Tables + aliases
    for t in ast.find_all(exp.Table):
        name = t.name.lower()
        if name and name != "dual":
            fp.tables.append(name)
            if t.alias:
                fp.alias_map[t.alias.lower()] = name
    fp.tables = list(dict.fromkeys(fp.tables))

    # Qualified columns
    try:
        qast = qualify(ast, dialect=DIALECT)
    except Exception:
        qast = ast
    for c in qast.find_all(exp.Column):
        tbl = c.table.lower() if c.table else ""
        col = c.name.lower() if c.name else ""
        if col:
            fp.qualified_columns.append((tbl, col))

    # Functions
    for f in ast.find_all(exp.Func):
        fname = type(f).__name__.upper()
        if fname == "ANONYMOUS":
            mapped = f.sql_name() if hasattr(f, "sql_name") else "UNKNOWN"
        else:
            mapped = _FUNC_MAP.get(fname, fname)
        fp.functions.append(mapped)
    fp.functions = list(dict.fromkeys(fp.functions))

    # Joins
    for sel in ast.find_all(exp.Select):
        from_clause = sel.args.get("from")
        from_table = ""
        if from_clause:
            ft = from_clause.find(exp.Table)
            if ft and ft.name:
                from_table = ft.name.lower()

        prev_table = from_table
        joins = sel.args.get("joins") or []
        for j in joins:
            jtype = j.args.get("side") or j.args.get("kind") or "INNER"
            if hasattr(jtype, "upper"):
                jtype = jtype.upper()
            else:
                jtype = str(jtype).upper()
            jt = j.find(exp.Table)
            on = j.args.get("on")
            if jt and jt.name:
                right_table = jt.name.lower()
                fp.join_graph.append(
                    JoinEdge(
                        left=prev_table,
                        right=right_table,
                        join_type=jtype,
                        on_condition=on.sql(dialect=DIALECT) if on else "",
                    )
                )
                prev_table = right_table

    # WHERE
    for w in ast.find_all(exp.Where):
        fp.where_conditions.extend(_split_and(w.this))

    # GROUP BY
    for g in ast.find_all(exp.Group):
        for ge in g.expressions:
            fp.group_by.append(ge.sql(dialect=DIALECT))

    # HAVING
    for h in ast.find_all(exp.Having):
        fp.having_conditions.append(h.this.sql(dialect=DIALECT))
        fp.has_having = True

    # ORDER BY
    for o in ast.find_all(exp.Order):
        for oe in o.expressions:
            fp.order_by.append(oe.sql(dialect=DIALECT))
        fp.has_order_by = True

    # Literals in EQ (enum detection)
    for eq in ast.find_all(exp.EQ):
        if isinstance(eq.right, exp.Literal) and isinstance(eq.left, exp.Column):
            col = eq.left.name.lower() if eq.left.name else ""
            if col:
                fp.literals.setdefault(col, []).append(str(eq.right.this))

    # CASE WHEN
    for c in ast.find_all(exp.Case):
        fp.case_when_blocks.append(c.sql(dialect=DIALECT))
        fp.has_case = True

    # Window functions
    for w in ast.find_all(exp.Window):
        fp.window_exprs.append(w.sql(dialect=DIALECT))
        fp.has_window = True

    # Structural flags
    fp.has_cte = bool(list(ast.find_all(exp.CTE)))
    fp.has_subquery = bool(list(ast.find_all(exp.Subquery)))
    fp.has_union = bool(ast.find(exp.Union))

    sel = ast.find(exp.Select)
    if sel:
        fp.has_distinct = bool(sel.args.get("distinct"))
        fp.select_col_count = len(sel.expressions)

    lim = ast.find(exp.Limit)
    if lim:
        fp.has_limit = True
        try:
            fp.limit_value = int(lim.expression.this)
        except Exception:
            pass

    try:
        fp.canonical_sql = ast.sql(dialect=DIALECT, pretty=True)
    except Exception:
        fp.canonical_sql = sql

    return fp, None


# --- Batch extraction (async, offloaded to thread) ---


async def extract_all_fingerprints(
    corpus: list[dict],
    on_progress: Optional[Callable] = None,
) -> tuple[list[QFP], list[dict]]:
    """Extract fingerprints from all queries.

    CPU-bound sqlglot parsing is offloaded to a thread via asyncio.to_thread().
    """
    total = len(corpus)
    if total == 0:
        return [], []

    def _extract_batch() -> tuple[list[QFP], list[dict]]:
        """Synchronous batch extraction — runs in thread pool."""
        fingerprints: list[QFP] = []
        failures: list[dict] = []

        for i, entry in enumerate(corpus):
            qid = f"q_{i:05d}"
            fp, fail = extract_fingerprint(qid, entry)
            if fp:
                fingerprints.append(fp)
            elif fail:
                failures.append(fail)

        return fingerprints, failures

    # Run CPU-bound work in thread
    fingerprints, failures = await asyncio.to_thread(_extract_batch)

    if on_progress:
        await on_progress(
            "fingerprint", total, total,
            f"{len(fingerprints)} fingerprints extracted, {len(failures)} failures",
        )

    return fingerprints, failures
