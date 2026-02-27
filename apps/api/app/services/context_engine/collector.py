"""Context Collector — gathers ALL context documents from every source.

Sources:
  1. Databricks-generated context docs  (ContextDoc, source_type='databricks')
  2. Config APIs-generated context docs  (ContextDoc, source_type='config_apis')
  3. Live Capillary contexts              (via Capillary REST API)
"""
import base64
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


def _deduplicate(
    generated_docs: list[dict],
    capillary_docs: list[dict],
) -> list[dict]:
    """Remove Capillary contexts that duplicate generated docs (by name match).

    When we upload generated docs to Capillary, they appear in both sources.
    We prefer the generated version (has richer metadata) and skip the
    Capillary duplicate.
    """
    gen_names = {d["name"].lower().strip() for d in generated_docs}

    deduped_capillary = []
    for doc in capillary_docs:
        if doc["name"].lower().strip() not in gen_names:
            deduped_capillary.append(doc)
        else:
            logger.debug(f"Skipping Capillary duplicate: {doc['name']}")

    return deduped_capillary


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

    # Deduplicate: Capillary may contain previously-uploaded generated docs
    all_generated = databricks_docs + config_api_docs
    capillary_unique = _deduplicate(all_generated, capillary_docs)

    all_sources = databricks_docs + config_api_docs + capillary_unique

    # Skip contexts with empty content
    all_sources = [s for s in all_sources if s.get("content", "").strip()]

    input_sources = {
        "databricks": [d["doc_id"] for d in databricks_docs],
        "config_apis": [d["doc_id"] for d in config_api_docs],
        "capillary": [d.get("context_id", "") for d in capillary_unique],
    }

    summary = {
        "databricks": len(databricks_docs),
        "config_apis": len(config_api_docs),
        "capillary": len(capillary_unique),
        "total": len(all_sources),
    }

    logger.info(
        f"Collected {summary['total']} contexts for org {org_id}: "
        f"{summary['databricks']} databricks, {summary['config_apis']} config_apis, "
        f"{summary['capillary']} capillary"
    )

    return {
        "sources": all_sources,
        "input_sources": input_sources,
        "summary": summary,
    }
