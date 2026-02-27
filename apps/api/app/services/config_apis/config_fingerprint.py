"""
Config Fingerprint model — the Config API analog of Databricks' QFP.

Decomposes each config object (program, campaign, promotion, etc.) into
typed structural components for frequency analysis and template selection.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


# ═══════════════════════════════════════════════════════════════════════
# Keywords that indicate rule / condition / workflow structures
# ═══════════════════════════════════════════════════════════════════════

_RULE_KEYWORDS = frozenset({
    "rule", "rules", "ruleExpression", "ruleSetCondition",
    "ruleExpression", "earningRule", "expiryRule", "burnRule",
    "promotionRule", "conditionExpression", "expression",
})

_CONDITION_KEYWORDS = frozenset({
    "condition", "conditions", "conditionExpression", "filter",
    "filters", "criteria", "whereClause", "constraintType",
    "limitConstraints", "scopeConstraints",
})

_WORKFLOW_KEYWORDS = frozenset({
    "workflow", "workflows", "actions", "action", "steps",
    "eventActions", "allocation", "allocationActions",
    "messageBody", "schedule", "scheduleCron",
})

# Fields commonly holding a "type" or "subtype" value
_TYPE_FIELDS = (
    "type", "campaignType", "promotionType", "seriesType",
    "discountType", "audienceType", "targetType", "entityType",
    "fieldType", "dataType", "module", "scope", "status",
)

# Fields commonly holding a name
_NAME_FIELDS = (
    "name", "programName", "campaignName", "seriesName",
    "promotionName", "audienceName", "groupName", "label",
    "displayName", "title", "description",
)

# Fields commonly holding an ID
_ID_FIELDS = (
    "id", "programId", "campaignId", "seriesId", "promotionId",
    "audienceId", "groupId", "entityId",
)

# Fields with categorical / enum-like values (low cardinality)
_CATEGORICAL_FIELDS = frozenset({
    "type", "status", "module", "scope", "channel", "medium",
    "campaignType", "promotionType", "discountType", "seriesType",
    "audienceType", "targetType", "entityType", "fieldType",
    "dataType", "targetType", "isActive", "isEnabled", "isDeleted",
    "allocationType", "allocatePointsOn", "pointsExpiryType",
    "ownerType", "owned_by", "ownedBy",
})


@dataclass
class ConfigFingerprint:
    """Fingerprint of one config object (program, campaign, promotion, etc.)."""

    # ── Identity ──
    id: str                                         # e.g. "loyalty__program__0"
    category: str                                   # extraction category
    entity_type: str                                # e.g. "program", "campaign"
    entity_subtype: str = ""                        # e.g. "TRANSACTIONAL"
    entity_name: str = ""                           # human-readable name
    entity_id: Any = None                           # numeric/string ID

    # ── Structural decomposition ──
    field_names: List[str] = field(default_factory=list)
    nested_objects: List[str] = field(default_factory=list)
    field_types: Dict[str, str] = field(default_factory=dict)
    field_values: Dict[str, Any] = field(default_factory=dict)

    # ── Complexity metrics ──
    depth: int = 0
    total_fields: int = 0
    has_rules: bool = False
    has_conditions: bool = False
    has_workflow: bool = False

    # ── Raw config object (strings capped) ──
    raw_object: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "category": self.category,
            "entity_type": self.entity_type,
            "entity_subtype": self.entity_subtype,
            "entity_name": self.entity_name,
            "entity_id": self.entity_id,
            "field_names": self.field_names,
            "nested_objects": self.nested_objects,
            "field_types": self.field_types,
            "field_values": self.field_values,
            "depth": self.depth,
            "total_fields": self.total_fields,
            "has_rules": self.has_rules,
            "has_conditions": self.has_conditions,
            "has_workflow": self.has_workflow,
            "raw_object": self.raw_object,
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "ConfigFingerprint":
        return ConfigFingerprint(
            id=d["id"],
            category=d["category"],
            entity_type=d["entity_type"],
            entity_subtype=d.get("entity_subtype", ""),
            entity_name=d.get("entity_name", ""),
            entity_id=d.get("entity_id"),
            field_names=d.get("field_names", []),
            nested_objects=d.get("nested_objects", []),
            field_types=d.get("field_types", {}),
            field_values=d.get("field_values", {}),
            depth=d.get("depth", 0),
            total_fields=d.get("total_fields", 0),
            has_rules=d.get("has_rules", False),
            has_conditions=d.get("has_conditions", False),
            has_workflow=d.get("has_workflow", False),
            raw_object=d.get("raw_object", {}),
        )
