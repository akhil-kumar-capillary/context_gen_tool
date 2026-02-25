"""Confluence Cloud API client — async wrapper around atlassian-python-api.

Uses Basic Auth (email + API token) for Confluence Cloud.
"""
from __future__ import annotations

import asyncio
from functools import partial
from typing import Optional

from atlassian import Confluence
from bs4 import BeautifulSoup
from markdownify import markdownify as md

from app.config import settings


class ConfluenceClient:
    """Thin async wrapper over the synchronous atlassian Confluence SDK."""

    def __init__(
        self,
        url: Optional[str] = None,
        email: Optional[str] = None,
        api_token: Optional[str] = None,
    ):
        self.url = (url or settings.confluence_url or "").rstrip("/")
        self.email = email or settings.confluence_email or ""
        self.api_token = api_token or settings.confluence_api_token or ""

        if not self.url or not self.email or not self.api_token:
            raise ValueError(
                "Confluence credentials missing. Set CONFLUENCE_URL, "
                "CONFLUENCE_EMAIL, and CONFLUENCE_API_TOKEN."
            )

        self._client = Confluence(
            url=self.url,
            username=self.email,
            password=self.api_token,
            cloud=True,
        )

    # ── helpers ──────────────────────────────────────────────────────

    async def _run(self, fn, *args, **kwargs):
        """Run a blocking atlassian-api call in a thread."""
        return await asyncio.to_thread(partial(fn, *args, **kwargs))

    @staticmethod
    def _html_to_markdown(html: str) -> str:
        """Convert Confluence storage-format HTML to clean Markdown."""
        if not html:
            return ""
        soup = BeautifulSoup(html, "html.parser")
        for macro in soup.find_all("ac:structured-macro"):
            macro.decompose()
        for tag in soup.find_all(["style", "script"]):
            tag.decompose()
        cleaned = str(soup)
        markdown = md(cleaned, heading_style="ATX", strip=["img"])
        # collapse excessive blank lines
        lines: list[str] = []
        prev_blank = False
        for line in markdown.splitlines():
            stripped = line.rstrip()
            if not stripped:
                if not prev_blank:
                    lines.append("")
                    prev_blank = True
            else:
                lines.append(stripped)
                prev_blank = False
        return "\n".join(lines).strip()

    # ── public API (all async) ───────────────────────────────────────

    async def test_connection(self) -> bool:
        """Return True if we can reach Confluence."""
        try:
            await self._run(self._client.get_all_spaces, start=0, limit=1)
            return True
        except Exception:
            return False

    async def list_spaces(self, limit: int = 50) -> list[dict]:
        """List available Confluence spaces."""
        raw = await self._run(
            self._client.get_all_spaces, start=0, limit=limit, expand="description.plain"
        )
        results = raw.get("results", []) if isinstance(raw, dict) else raw
        spaces = []
        for s in results:
            spaces.append(
                {
                    "key": s["key"],
                    "name": s["name"],
                    "type": s.get("type", "global"),
                    "url": f"{self.url}/wiki/spaces/{s['key']}",
                }
            )
        return spaces

    async def search_pages(
        self, query: str, space_key: Optional[str] = None, limit: int = 10
    ) -> list[dict]:
        """CQL full-text search for pages."""
        cql = f'type=page AND text ~ "{query}"'
        if space_key:
            cql += f' AND space="{space_key}"'

        raw = await self._run(self._client.cql, cql, limit=limit)
        results = raw.get("results", []) if isinstance(raw, dict) else []
        pages = []
        for r in results:
            content = r.get("content", r)
            excerpt_html = r.get("excerpt", "")
            excerpt = BeautifulSoup(excerpt_html, "html.parser").get_text()[:200] if excerpt_html else ""
            pages.append(
                {
                    "id": str(content.get("id", r.get("id", ""))),
                    "title": content.get("title", r.get("title", "")),
                    "space_key": content.get("space", {}).get("key", ""),
                    "excerpt": excerpt,
                    "url": f"{self.url}/wiki{content.get('_links', {}).get('webui', '')}",
                }
            )
        return pages

    async def get_page(self, page_id: str) -> dict:
        """Fetch a single page with its content as Markdown."""
        raw = await self._run(
            self._client.get_page_by_id,
            page_id,
            expand="body.storage,version,space",
        )
        storage_html = raw.get("body", {}).get("storage", {}).get("value", "")
        content_md = self._html_to_markdown(storage_html)
        space = raw.get("space", {})
        return {
            "id": str(raw.get("id", page_id)),
            "title": raw.get("title", ""),
            "space_key": space.get("key", ""),
            "space_name": space.get("name", ""),
            "content": content_md,
            "version": raw.get("version", {}).get("number", 0),
            "url": f"{self.url}/wiki{raw.get('_links', {}).get('webui', '')}",
        }

    async def get_child_pages(self, page_id: str, limit: int = 50) -> list[dict]:
        """Get child pages of a given page."""
        raw = await self._run(
            self._client.get_page_child_by_type,
            page_id,
            type="page",
            start=0,
            limit=limit,
        )
        return [{"id": str(p["id"]), "title": p["title"]} for p in raw]

    async def get_space_pages(self, space_key: str, limit: int = 50) -> list[dict]:
        """Get root-level pages of a space."""
        try:
            cql = f'type=page AND space="{space_key}" AND ancestor=null'
            raw = await self._run(self._client.cql, cql, limit=limit)
            results = raw.get("results", []) if isinstance(raw, dict) else []
            return [
                {"id": str(r.get("content", r).get("id", "")), "title": r.get("content", r).get("title", "")}
                for r in results
            ]
        except Exception:
            # Fallback
            raw = await self._run(
                self._client.get_all_pages_from_space,
                space_key,
                start=0,
                limit=limit,
                expand="version",
            )
            return [{"id": str(p["id"]), "title": p["title"]} for p in raw]
