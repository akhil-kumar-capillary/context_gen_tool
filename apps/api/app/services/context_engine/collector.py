"""Context Collector — gathers ALL context documents from every source.

Sources:
  1. Databricks-generated context docs  (ContextDoc, source_type='databricks')
  2. Config APIs-generated context docs  (ContextDoc, source_type='config_apis')
  3. Live aiRA contexts                  (via Capillary REST API)
"""
import base64
import hashlib
import logging
from typing import Any

import httpx
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.context_doc import ContextDoc

logger = logging.getLogger(__name__)


async def _fetch_generated_docs(
    db: AsyncSession,
    org_id: int,
    source_type: str,
) -> list[dict]:
    """Fetch latest active generated docs for a source type."""
    stmt = (
        select(ContextDoc)
        .where(
            ContextDoc.org_id == str(org_id),
            ContextDoc.source_type == source_type,
            ContextDoc.status == "active",
        )
        .order_by(desc(ContextDoc.created_at))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    docs = []
    for doc in rows:
        docs.append({
            "source": source_type,
            "doc_id": doc.id,
            "name": doc.doc_name or doc.doc_key,
            "doc_key": doc.doc_key,
            "content": doc.doc_content or "",
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        })
    return docs


async def _fetch_capillary_contexts(
    base_url: str,
    headers: dict,
) -> list[dict]:
    """Fetch live contexts from Capillary's context API."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                f"{base_url}/ask-aira/context/list",
                params={"is_active": "true"},
                headers=headers,
            )
            if resp.status_code != 200:
                logger.warning(f"Capillary context list failed: HTTP {resp.status_code}")
                return []

            data = resp.json()
    except Exception as e:
        logger.warning(f"Failed to fetch Capillary contexts: {e}")
        return []

    raw_list = data if isinstance(data, list) else data.get("data", data.get("contexts", []))

    # Safety filter: only include active contexts (exclude archived)
    raw_list = [
        item for item in raw_list
        if item.get("is_active") is not False
    ]

    docs = []
    for item in raw_list:
        name = item.get("name", "Unnamed")
        ctx_id = item.get("id", item.get("contextId", ""))
        scope = item.get("scope", "org")
        raw_content = item.get("content", item.get("context", ""))

        # Try base64 decode (Capillary stores content base64-encoded)
        if raw_content:
            try:
                raw_content = base64.b64decode(raw_content).decode("utf-8")
            except Exception:
                pass  # Already plain text

        docs.append({
            "source": "capillary",
            "context_id": str(ctx_id),
            "name": name,
            "content": raw_content,
            "scope": scope,
        })
    return docs


def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace."""
    return " ".join(text.lower().split())


def _content_hash(content: str) -> str:
    """SHA-256 hash of normalized full content for exact dedup."""
    return hashlib.sha256(_normalize_text(content).encode()).hexdigest()


def _short_hash(content: str) -> str:
    """MD5 hash of first 500 normalized chars for near-dedup."""
    return hashlib.md5(_normalize_text(content[:500]).encode()).hexdigest()


def _deduplicate_all(docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Three-tier deduplication across ALL sources.

    Tiers:
      1. Exact content match (SHA-256 of full normalized text)
      2. Near-content match (MD5 of first 500 normalized chars)
      3. Name match (case-insensitive, stripped)

    When a duplicate is found, the FIRST occurrence is kept (generated docs
    are listed before Capillary docs, so they win priority).

    Returns: (kept_docs, dropped_docs)
    """
    seen_exact: dict[str, dict] = {}
    seen_near: dict[str, dict] = {}
    seen_names: dict[str, dict] = {}

    kept: list[dict] = []
    dropped: list[dict] = []

    for doc in docs:
        content = doc.get("content", "")
        name = doc.get("name", "").lower().strip()

        # Tier 1: Exact content match
        eh = _content_hash(content) if content else ""
        if eh and eh in seen_exact:
            dropped.append({
                **doc,
                "_dedup_reason": "exact_content",
                "_duplicate_of": seen_exact[eh].get("name", "?"),
            })
            continue

        # Tier 2: Near-content match (first 500 chars)
        sh = _short_hash(content) if content else ""
        if sh and sh in seen_near:
            dropped.append({
                **doc,
                "_dedup_reason": "near_content",
                "_duplicate_of": seen_near[sh].get("name", "?"),
            })
            continue

        # Tier 3: Name match
        if name and name in seen_names:
            dropped.append({
                **doc,
                "_dedup_reason": "name_match",
                "_duplicate_of": seen_names[name].get("name", "?"),
            })
            continue

        # Keep this doc
        if eh:
            seen_exact[eh] = doc
        if sh:
            seen_near[sh] = doc
        if name:
            seen_names[name] = doc
        kept.append(doc)

    if dropped:
        logger.info(
            "Deduplication removed %d/%d docs: %s",
            len(dropped),
            len(docs),
            [(d["name"], d["_dedup_reason"]) for d in dropped[:5]],
        )

    return kept, dropped


async def collect_all_contexts(
    db: AsyncSession,
    org_id: int,
    base_url: str,
    capillary_headers: dict,
) -> dict[str, Any]:
    """Collect contexts from all sources for an organization.

    Returns:
        {
            "sources": [
                {"source": "databricks", "doc_id": 123, "name": "...", "content": "...", ...},
                {"source": "config_apis", "doc_id": 456, "name": "...", "content": "...", ...},
                {"source": "capillary", "context_id": "abc", "name": "...", "content": "...", ...},
            ],
            "input_sources": {
                "databricks": [doc_id, ...],
                "config_apis": [doc_id, ...],
                "capillary": [context_id, ...],
            },
            "summary": {"databricks": N, "config_apis": N, "capillary": N, "total": N}
        }
    """
    # Fetch from all three sources
    databricks_docs = await _fetch_generated_docs(db, org_id, "databricks")
    config_api_docs = await _fetch_generated_docs(db, org_id, "config_apis")
    capillary_docs = await _fetch_capillary_contexts(base_url, capillary_headers)

    # Combine all sources (generated docs first — they win priority in dedup)
    all_raw = databricks_docs + config_api_docs + capillary_docs

    # Skip contexts with empty content before dedup
    all_raw = [s for s in all_raw if s.get("content", "").strip()]

    # Three-tier deduplication across ALL sources
    all_sources, dropped_docs = _deduplicate_all(all_raw)

    # Recount after dedup (capillary count may have changed)
    db_count = sum(1 for d in all_sources if d.get("source") == "databricks")
    ca_count = sum(1 for d in all_sources if d.get("source") == "config_apis")
    cap_count = sum(1 for d in all_sources if d.get("source") == "capillary")

    input_sources = {
        "databricks": [d["doc_id"] for d in all_sources if d.get("source") == "databricks"],
        "config_apis": [d["doc_id"] for d in all_sources if d.get("source") == "config_apis"],
        "capillary": [d.get("context_id", "") for d in all_sources if d.get("source") == "capillary"],
    }

    summary = {
        "databricks": db_count,
        "config_apis": ca_count,
        "capillary": cap_count,
        "total": len(all_sources),
        "duplicates_removed": len(dropped_docs),
    }

    logger.info(
        "Collected %d contexts for org %s (%d databricks, %d config_apis, %d capillary, %d duplicates removed)",
        summary["total"], org_id, db_count, ca_count, cap_count, len(dropped_docs),
    )

    return {
        "sources": all_sources,
        "dropped": dropped_docs,
        "input_sources": input_sources,
        "summary": summary,
    }
