"""Content versioning service — create, query, diff, and restore versions."""

import difflib
import logging
from typing import Any

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.content_version import ContentVersion
from app.utils import utcnow

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

async def create_version(
    db: AsyncSession,
    *,
    entity_type: str,
    entity_id: str,
    org_id: int,
    snapshot: dict,
    previous_snapshot: dict | None = None,
    change_type: str,
    change_summary: str | None = None,
    changed_fields: list[str] | None = None,
    user_id: int | None = None,
) -> ContentVersion:
    """Create a new version record.  Must be called inside an open transaction.

    Uses the unique constraint (entity_type, entity_id, version_number) as
    the concurrency guard.  If two transactions race, the loser hits a unique
    violation and the caller should retry or let it bubble up.
    """

    # Compute next version number.
    # PostgreSQL doesn't allow FOR UPDATE with aggregates, so we rely on
    # the uq_entity_version unique constraint to prevent duplicates.
    result = await db.execute(
        select(func.coalesce(func.max(ContentVersion.version_number), 0))
        .where(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == str(entity_id),
        )
    )
    next_version = result.scalar_one() + 1

    version = ContentVersion(
        entity_type=entity_type,
        entity_id=str(entity_id),
        version_number=next_version,
        snapshot=snapshot,
        previous_snapshot=previous_snapshot,
        change_type=change_type,
        change_summary=change_summary,
        changed_fields=changed_fields,
        changed_by_user_id=user_id,
        org_id=org_id,
        created_at=utcnow(),
    )
    db.add(version)
    return version


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

async def get_version_history(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    org_id: int,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[ContentVersion], int]:
    """Return paginated version metadata (newest first) and total count."""

    base_filter = [
        ContentVersion.entity_type == entity_type,
        ContentVersion.entity_id == str(entity_id),
        ContentVersion.org_id == org_id,
    ]

    count_result = await db.execute(
        select(func.count()).select_from(ContentVersion).where(*base_filter)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(ContentVersion)
        .where(*base_filter)
        .order_by(ContentVersion.version_number.desc())
        .offset(offset)
        .limit(limit)
    )
    versions = list(result.scalars().all())
    return versions, total


async def get_version_detail(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    version_number: int,
    org_id: int,
) -> ContentVersion | None:
    """Return a single version with full snapshot."""
    result = await db.execute(
        select(ContentVersion).where(
            ContentVersion.entity_type == entity_type,
            ContentVersion.entity_id == str(entity_id),
            ContentVersion.version_number == version_number,
            ContentVersion.org_id == org_id,
        )
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------

def _diff_aira_context(old: dict, new: dict) -> tuple[list[dict], str]:
    """Diff two capillary context snapshots. Returns (field_changes, summary)."""
    changes: list[dict] = []
    changed_names: list[str] = []

    for field in ("name", "content", "scope"):
        old_val = old.get(field, "")
        new_val = new.get(field, "")
        if old_val != new_val:
            change: dict[str, Any] = {"field": field}
            if field == "content":
                # Produce unified text diff for content
                old_lines = str(old_val).splitlines(keepends=True)
                new_lines = str(new_val).splitlines(keepends=True)
                diff_lines = list(difflib.unified_diff(
                    old_lines, new_lines, fromfile="before", tofile="after", lineterm="",
                ))
                change["old_value"] = str(old_val)[:500]  # truncate for summary
                change["new_value"] = str(new_val)[:500]
                change["diff"] = "".join(diff_lines)
            else:
                change["old_value"] = str(old_val) if old_val else None
                change["new_value"] = str(new_val) if new_val else None
            changes.append(change)
            changed_names.append(field)

    summary = f"Changed: {', '.join(changed_names)}" if changed_names else "No changes"
    return changes, summary


def _collect_nodes(tree: dict) -> dict[str, dict]:
    """Flatten tree into {node_id: node_dict} map."""
    nodes: dict[str, dict] = {}
    stack = [tree] if tree else []
    while stack:
        node = stack.pop()
        nid = node.get("id")
        if nid:
            nodes[nid] = node
        for child in node.get("children", []):
            stack.append(child)
    return nodes


def _diff_context_tree(old: dict, new: dict) -> tuple[list[dict], str]:
    """Diff two context tree snapshots. Returns (tree_changes, summary)."""
    old_nodes = _collect_nodes(old)
    new_nodes = _collect_nodes(new)

    old_ids = set(old_nodes.keys())
    new_ids = set(new_nodes.keys())

    changes: list[dict] = []
    added = new_ids - old_ids
    removed = old_ids - new_ids
    common = old_ids & new_ids

    for nid in added:
        n = new_nodes[nid]
        changes.append({
            "node_id": nid,
            "node_name": n.get("name", ""),
            "change_type": "added",
            "field_changes": None,
        })

    for nid in removed:
        n = old_nodes[nid]
        changes.append({
            "node_id": nid,
            "node_name": n.get("name", ""),
            "change_type": "removed",
            "field_changes": None,
        })

    compare_fields = ("name", "desc", "visibility", "health", "type", "summary")
    for nid in common:
        o, n = old_nodes[nid], new_nodes[nid]
        field_changes = []
        for f in compare_fields:
            ov, nv = o.get(f), n.get(f)
            if ov != nv:
                field_changes.append({
                    "field": f,
                    "old_value": str(ov) if ov is not None else None,
                    "new_value": str(nv) if nv is not None else None,
                })
        if field_changes:
            changes.append({
                "node_id": nid,
                "node_name": n.get("name", o.get("name", "")),
                "change_type": "modified",
                "field_changes": field_changes,
            })

    parts = []
    if added:
        parts.append(f"{len(added)} added")
    if removed:
        parts.append(f"{len(removed)} removed")
    modified_count = sum(1 for c in changes if c["change_type"] == "modified")
    if modified_count:
        parts.append(f"{modified_count} modified")
    summary = f"Nodes: {', '.join(parts)}" if parts else "No changes"

    return changes, summary


async def compare_versions(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    from_version: int,
    to_version: int,
    org_id: int,
) -> dict:
    """Compare two versions and return a structured diff."""
    v_from = await get_version_detail(db, entity_type, entity_id, from_version, org_id)
    v_to = await get_version_detail(db, entity_type, entity_id, to_version, org_id)

    if not v_from or not v_to:
        return {
            "entity_type": entity_type,
            "from_version": from_version,
            "to_version": to_version,
            "field_changes": [],
            "tree_changes": None,
            "summary": "Version not found",
        }

    if entity_type == "aira_context":
        field_changes, summary = _diff_aira_context(v_from.snapshot, v_to.snapshot)
        return {
            "entity_type": entity_type,
            "from_version": from_version,
            "to_version": to_version,
            "field_changes": field_changes,
            "tree_changes": None,
            "summary": summary,
        }
    else:  # context_tree
        tree_changes, summary = _diff_context_tree(v_from.snapshot, v_to.snapshot)
        return {
            "entity_type": entity_type,
            "from_version": from_version,
            "to_version": to_version,
            "field_changes": [],
            "tree_changes": tree_changes,
            "summary": summary,
        }


# ---------------------------------------------------------------------------
# Restore helper
# ---------------------------------------------------------------------------

async def get_restore_snapshot(
    db: AsyncSession,
    entity_type: str,
    entity_id: str,
    version_number: int,
    org_id: int,
) -> dict | None:
    """Return the snapshot for a given version, or None if not found."""
    ver = await get_version_detail(db, entity_type, entity_id, version_number, org_id)
    return ver.snapshot if ver else None
