"""Single-document LLM refactor — polish structure and remove noise.

Different from `services/context_engine/sanitizer.py` which works on a tree of
many documents. This is a single-shot cleanup for one uploaded file.

Takes HTML in, returns HTML out — no markdown intermediate, so complex tables,
merged cells, figure captions, and nested structure survive the round-trip.
"""
from __future__ import annotations

import logging
import re

from app.config import settings
from app.services.file_ingest.converter import sanitize_html
from app.services.llm_service import call_llm

logger = logging.getLogger(__name__)


_REFACTOR_SYSTEM = """You are a documentation cleanup assistant.

The user will paste the HTML contents of a document that was converted from PDF, DOCX, or similar. Your job is to clean and restructure it for use as an AI context document.

## HARD RULES (non-negotiable)

1. **PRESERVE ALL FACTUAL CONTENT.** Every number, every row of every table, every bullet, every code snippet must survive. Never summarize. Never drop data. Never say "[table omitted]" or similar.

2. **NEVER FLATTEN TABLES.** If the input has a `<table>`, the output MUST have a `<table>` — with every row and every cell intact. Use `<thead>`, `<tbody>`, `<tr>`, `<th>`, `<td>`. Preserve `colspan`/`rowspan` when present. Do NOT convert tables into bullet lists, key-value pairs, or paragraphs.

3. **OUTPUT HTML, NOT MARKDOWN.** No ``` fences. No `#` headings. Use `<h1>`–`<h6>`, `<p>`, `<ul>`, `<ol>`, `<li>`, `<table>`, `<pre><code>`, `<strong>`, `<em>`, etc.

## WHAT TO CLEAN UP

- Drop repeated page headers/footers, page numbers, navigation breadcrumbs.
- Join paragraphs that were split mid-sentence by page breaks.
- Fix broken hyphenation across lines (e.g. "reten-\ntion" → "retention").
- Drop OCR garbage and stray single-letter artifacts.
- Normalize heading hierarchy (single logical outline — one h1, nested h2/h3).
- Remove Docling's structural wrapper classes like `<div class="page">` or `<span class="inline-group">` — keep the content, drop the wrapper.

## WHAT NOT TO DO

- Do NOT add commentary, preamble, or a closing summary.
- Do NOT wrap your answer in ```html fences.
- Do NOT add content that wasn't in the source.
- Do NOT reorder sections.

Your entire response must be the cleaned HTML fragment — nothing else, no preamble, no explanation."""


def _strip_codefence(text: str) -> str:
    """Strip a leading/trailing ``` fence if the LLM added one despite instructions."""
    t = text.strip()
    t = re.sub(r"^```(?:html|markdown|md)?\s*\n?", "", t)
    t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


async def refactor_document(
    html_content: str,
    document_name: str | None = None,
) -> tuple[str, dict]:
    """Run a single-document refactor pass via LLM.

    Args:
        html_content: Sanitized HTML from the converter (images already stripped).
        document_name: Optional hint so the LLM knows the source document's title.

    Returns:
        (refactored_html, token_usage) — HTML in, HTML out, no markdown round-trip.
        Falls back to the original `html_content` on any failure.
    """
    if not html_content.strip():
        return html_content, {"input_tokens": 0, "output_tokens": 0}

    user_prompt = (
        (f"Document name: {document_name}\n\n" if document_name else "")
        + "HTML to clean up (remember: preserve all tables as <table>, preserve all data):\n\n"
        + html_content
    )

    try:
        result = await call_llm(
            provider=settings.refactor_provider,
            model=settings.refactor_model,
            system=_REFACTOR_SYSTEM,
            messages=[{"role": "user", "content": user_prompt}],
            max_tokens=settings.sanitize_max_output_tokens,
        )
    except Exception:
        logger.exception("Refactor LLM call failed; keeping original content")
        return html_content, {"input_tokens": 0, "output_tokens": 0}

    blocks = result.get("content", [])
    text_parts = [b.get("text", "") for b in blocks if b.get("type") == "text"]
    refactored_html = "".join(text_parts).strip()

    if not refactored_html:
        logger.warning("Refactor produced empty output for '%s'; keeping original", document_name)
        return html_content, result.get("usage", {})

    refactored_html = _strip_codefence(refactored_html)
    # Defense-in-depth: the LLM could theoretically emit <script>, event
    # handlers, or javascript: URLs even though the input was clean, so
    # re-apply the same allowlist sanitizer used for the initial conversion.
    refactored_html = sanitize_html(refactored_html)

    # Safety check: if the LLM somehow returned much less content, keep original.
    # Threshold is generous (30% of input size) to allow legitimate cleanup while
    # catching catastrophic truncation.
    if len(refactored_html) < max(200, int(len(html_content) * 0.3)):
        logger.warning(
            "Refactor output for '%s' is suspiciously short (%d → %d chars); "
            "keeping original to avoid data loss",
            document_name, len(html_content), len(refactored_html),
        )
        return html_content, result.get("usage", {})

    return refactored_html, result.get("usage", {})
