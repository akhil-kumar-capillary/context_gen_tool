"""Shared utility functions."""

from datetime import datetime, timezone

from markdown_it import MarkdownIt


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


_md = (
    MarkdownIt("commonmark", {"html": True, "linkify": True})
    .enable("table")
    .enable("strikethrough")
)


def md_to_html(content: str) -> str:
    """Convert markdown to HTML for Capillary upload.

    Passes through existing HTML tags. GFM-style tables and strikethrough are
    enabled so content coming out of the rich-text editor, file ingest, and the
    refactor LLM all render with the same fidelity.
    """
    return _md.render(content)
