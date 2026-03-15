"""Shared utility functions."""

from datetime import datetime, timezone

from markdown_it import MarkdownIt


def utcnow() -> datetime:
    """Return the current UTC datetime (timezone-aware)."""
    return datetime.now(timezone.utc)


_md = MarkdownIt("commonmark", {"html": True})


def md_to_html(content: str) -> str:
    """Convert markdown to HTML for Capillary upload. Passes through existing HTML tags."""
    return _md.render(content)
