"""
Query Fingerprint (QFP) dataclass and JoinEdge.

Ported from reference: models/qfp.py
Pure dataclasses — no I/O dependencies.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class JoinEdge:
    left: str
    right: str
    join_type: str
    on_condition: str


@dataclass
class QFP:
    """Query fingerprint — structured metadata from one parsed SQL query."""

    id: str
    raw_sql: str
    nl_question: Optional[str] = None
    frequency: int = 1

    tables: list = field(default_factory=list)
    qualified_columns: list = field(default_factory=list)
    functions: list = field(default_factory=list)
    join_graph: list = field(default_factory=list)
    where_conditions: list = field(default_factory=list)
    group_by: list = field(default_factory=list)
    having_conditions: list = field(default_factory=list)
    order_by: list = field(default_factory=list)
    literals: dict = field(default_factory=dict)
    case_when_blocks: list = field(default_factory=list)
    window_exprs: list = field(default_factory=list)

    canonical_sql: str = ""

    has_cte: bool = False
    has_window: bool = False
    has_union: bool = False
    has_case: bool = False
    has_subquery: bool = False
    has_having: bool = False
    has_order_by: bool = False
    has_distinct: bool = False
    has_limit: bool = False
    limit_value: Optional[int] = None
    select_col_count: int = 0
    alias_map: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Serialize to dict for JSON transport."""
        return {
            "id": self.id,
            "raw_sql": self.raw_sql,
            "nl_question": self.nl_question,
            "frequency": self.frequency,
            "tables": self.tables,
            "qualified_columns": self.qualified_columns,
            "functions": self.functions,
            "join_graph": [
                {
                    "left": e.left,
                    "right": e.right,
                    "join_type": e.join_type,
                    "on_condition": e.on_condition,
                }
                for e in self.join_graph
            ],
            "where_conditions": self.where_conditions,
            "group_by": self.group_by,
            "having_conditions": self.having_conditions,
            "order_by": self.order_by,
            "literals": self.literals,
            "case_when_blocks": self.case_when_blocks,
            "window_exprs": self.window_exprs,
            "canonical_sql": self.canonical_sql,
            "has_cte": self.has_cte,
            "has_window": self.has_window,
            "has_union": self.has_union,
            "has_case": self.has_case,
            "has_subquery": self.has_subquery,
            "has_having": self.has_having,
            "has_order_by": self.has_order_by,
            "has_distinct": self.has_distinct,
            "has_limit": self.has_limit,
            "limit_value": self.limit_value,
            "select_col_count": self.select_col_count,
            "alias_map": self.alias_map,
        }
