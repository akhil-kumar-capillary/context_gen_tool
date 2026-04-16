"""Format-aware file → HTML conversion.

Each uploaded file is routed by magic-byte detection (with extension fallback)
to the right converter. The output is a sanitized HTML string with inline
base64-encoded images — safe to pass directly to Capillary's context API.
"""
from __future__ import annotations

import html as html_lib
import json
import logging
import re
from pathlib import Path
from typing import Optional

import bleach
import filetype

from app.utils import md_to_html

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Format registry
# ---------------------------------------------------------------------------

# Maps lowercase extension → logical format bucket
_EXT_FORMAT: dict[str, str] = {
    # Docling-handled
    "pdf": "docling",
    "docx": "docling",
    "pptx": "docling",
    "xlsx": "docling",
    "html": "docling",
    "htm": "docling",
    "png": "docling",
    "jpg": "docling",
    "jpeg": "docling",
    "tiff": "docling",
    "tif": "docling",
    "bmp": "docling",
    # Markdown
    "md": "markdown",
    "markdown": "markdown",
    "mdx": "markdown",
    # JSON
    "json": "json",
    # Plain text
    "txt": "text",
    "log": "text",
    "csv": "text",
    "tsv": "text",
    "yaml": "text",
    "yml": "text",
    "xml": "text",
}

SUPPORTED_EXTENSIONS: tuple[str, ...] = tuple(sorted(_EXT_FORMAT.keys()))


# Maps filetype-detected mime → logical format bucket (used when extension missing)
_MIME_FORMAT: dict[str, str] = {
    "application/pdf": "docling",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docling",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation": "docling",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "docling",
    "text/html": "docling",
    "image/png": "docling",
    "image/jpeg": "docling",
    "image/tiff": "docling",
    "image/bmp": "docling",
    "application/json": "json",
    "text/markdown": "markdown",
    "text/plain": "text",
    "text/csv": "text",
    "application/xml": "text",
}


class UnsupportedFormatError(ValueError):
    """Raised when a file's format cannot be converted."""


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def detect_format(file_path: Path, declared_name: str | None = None) -> str:
    """Return the logical format bucket for this file.

    Detection order:
      1. filetype magic-byte sniff (can't be spoofed by rename)
      2. Extension from declared_name or file_path

    Raises UnsupportedFormatError if no match.
    """
    # 1. Magic-byte sniff
    try:
        kind = filetype.guess(str(file_path))
        if kind is not None and kind.mime in _MIME_FORMAT:
            return _MIME_FORMAT[kind.mime]
    except Exception:
        # filetype may raise on empty/corrupt — fall through to extension check
        logger.debug("filetype sniff failed for %s", file_path, exc_info=True)

    # 2. Extension fallback
    name = declared_name or file_path.name
    ext = Path(name).suffix.lstrip(".").lower()
    if ext in _EXT_FORMAT:
        return _EXT_FORMAT[ext]

    raise UnsupportedFormatError(
        f"Unsupported format: '{name}' (no matching extension or magic signature). "
        f"Supported: {', '.join(SUPPORTED_EXTENSIONS)}"
    )


# ---------------------------------------------------------------------------
# Docling (lazy-loaded — models download on first use)
# ---------------------------------------------------------------------------

_docling_converter = None


class DoclingUnavailableError(RuntimeError):
    """Raised when Docling cannot be imported (usually a Python build issue).

    The most common cause on macOS + pyenv: Python was built before `xz` was
    installed, so the `_lzma` stdlib module is missing, which breaks
    torchvision → transformers → docling imports.

    Fix: `brew install xz && pyenv install --force <your-version>`.
    """


def _get_docling_converter():
    """Lazy-init the Docling converter with images embedded as base64."""
    global _docling_converter
    if _docling_converter is None:
        try:
            from docling.datamodel.base_models import InputFormat
            from docling.datamodel.pipeline_options import PdfPipelineOptions
            from docling.document_converter import DocumentConverter, PdfFormatOption
        except ModuleNotFoundError as e:
            # Most common case: _lzma missing because Python wasn't built with xz.
            hint = (
                "Docling import failed. This usually means Python was built without "
                "xz support (_lzma missing). Fix: `brew install xz && pyenv install "
                "--force <your-version>`, then recreate the venv."
            )
            raise DoclingUnavailableError(f"{hint} Underlying error: {e}") from e

        pdf_options = PdfPipelineOptions()
        # aiRA consumes contexts as text for an LLM — pictures are useless and
        # make payloads 10-100× larger. Skip extracting them to save compute.
        pdf_options.generate_picture_images = False
        pdf_options.do_ocr = True
        pdf_options.do_table_structure = True

        _docling_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=pdf_options),
            }
        )
        logger.info("Docling converter initialized (first use — models may download)")
    return _docling_converter


_BODY_RE = re.compile(r"<body\b[^>]*>(.*)</body>", re.DOTALL | re.IGNORECASE)
_STYLE_SCRIPT_RE = re.compile(
    r"<(style|script)\b[^>]*>.*?</\1\s*>", re.DOTALL | re.IGNORECASE
)
_HEAD_RE = re.compile(r"<head\b[^>]*>.*?</head>", re.DOTALL | re.IGNORECASE)
_DATA_IMG_RE = re.compile(
    r"""<img\b[^>]*\bsrc\s*=\s*["']data:[^"']*["'][^>]*/?\s*>""",
    re.IGNORECASE,
)
_EMPTY_FIGURE_RE = re.compile(
    r"<figure\b[^>]*>\s*</figure>", re.IGNORECASE | re.DOTALL
)


def _strip_embedded_images(html: str) -> str:
    """Remove <img> tags with data: URIs — aiRA is text-based; inline base64
    images bloat payloads 10-100× and have no semantic value for an LLM.

    Leaves external (http/https) <img> tags alone and keeps figure captions.
    Empty <figure></figure> shells (left after stripping the img) are removed.
    """
    html = _DATA_IMG_RE.sub("", html)
    html = _EMPTY_FIGURE_RE.sub("", html)
    return html


def _strip_standalone_chrome(html: str) -> str:
    """Drop <head>, <style>, <script> blocks and unwrap <html>/<body>.

    Docling's export_to_html() returns a full standalone HTML page with a big
    default stylesheet — useless for context docs (which go to an LLM, not a
    browser) and wasteful in tokens. We want just the semantic body content.
    """
    # Remove head + style + script with their contents (bleach's strip=True
    # would drop the tags but keep the inner CSS/JS as text).
    html = _HEAD_RE.sub("", html)
    html = _STYLE_SCRIPT_RE.sub("", html)
    # Extract just the body content if present
    m = _BODY_RE.search(html)
    if m:
        html = m.group(1)
    return html.strip()


def _convert_with_docling(file_path: Path) -> str:
    """Run Docling and return clean semantic HTML — body content only, no images."""
    converter = _get_docling_converter()  # may raise DoclingUnavailableError
    from docling_core.types.doc import ImageRefMode

    result = converter.convert(source=str(file_path))
    # PLACEHOLDER mode tells Docling not to embed base64 payloads for any
    # picture it did extract. Belt-and-suspenders with _strip_embedded_images.
    raw_html = result.document.export_to_html(image_mode=ImageRefMode.PLACEHOLDER)
    html = _strip_standalone_chrome(raw_html)
    html = _strip_embedded_images(html)
    return html


# ---------------------------------------------------------------------------
# Per-format converters
# ---------------------------------------------------------------------------


def _convert_markdown(file_path: Path) -> str:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    return md_to_html(text)


def _convert_json(file_path: Path) -> str:
    raw = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        parsed = json.loads(raw)
        pretty = json.dumps(parsed, indent=2, ensure_ascii=False)
    except json.JSONDecodeError:
        # Fall back to raw text if malformed — still show it to the user
        pretty = raw
    # Use md_to_html so the code fence renders as <pre><code class="language-json">
    md = f"```json\n{pretty}\n```\n"
    return md_to_html(md)


def _convert_text(file_path: Path) -> str:
    text = file_path.read_text(encoding="utf-8", errors="replace")
    # Auto-detect: if it looks like markdown (has #, -, *, or [] syntax), run md_to_html
    if _looks_like_markdown(text):
        return md_to_html(text)
    # Otherwise preserve whitespace with <pre>
    escaped = html_lib.escape(text)
    return f"<pre>{escaped}</pre>"


_MD_SIGNALS = ("\n# ", "\n## ", "\n- ", "\n* ", "\n1. ", "```", "[")


def _looks_like_markdown(text: str) -> bool:
    head = "\n" + text[:4000]
    return any(sig in head for sig in _MD_SIGNALS)


# ---------------------------------------------------------------------------
# HTML sanitization
# ---------------------------------------------------------------------------

_ALLOWED_TAGS = frozenset({
    # Block
    "p", "div", "section", "article", "header", "footer", "main", "aside",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "dl", "dt", "dd",
    "blockquote", "pre", "hr", "br",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
    "figure", "figcaption",
    # Inline
    "a", "span", "strong", "em", "b", "i", "u", "s", "strike", "del", "ins",
    "code", "kbd", "samp", "sub", "sup", "mark", "small",
    # Media — images embedded as data: URIs
    "img",
})

_ALLOWED_ATTRS = {
    # Intentionally excludes `style` — inline styles from converted docs often
    # fight the app's CSS and bleach warns without a CSS sanitizer configured.
    "*": ["class", "id", "title", "lang", "dir"],
    "a": ["href", "target", "rel"],
    "img": ["src", "alt", "width", "height"],
    "th": ["scope", "colspan", "rowspan"],
    "td": ["colspan", "rowspan"],
    "col": ["span", "width"],
    "colgroup": ["span"],
    "ol": ["start", "type"],
    "code": ["class"],
    "pre": ["class"],
}

# Allow data: for inline images (base64); https/http for external links
_ALLOWED_PROTOCOLS = ["http", "https", "mailto", "data"]


def sanitize_html(html: str) -> str:
    """Strip scripts/event handlers; allow inline base64 images and safe tags."""
    return bleach.clean(
        html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        protocols=_ALLOWED_PROTOCOLS,
        strip=True,
        strip_comments=True,
    )


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def convert_file(file_path: Path, declared_name: Optional[str] = None) -> str:
    """Convert a file to sanitized HTML.

    Args:
        file_path: Path to the file on local disk (temp file is fine).
        declared_name: Original filename from upload — used for extension fallback
            when magic-byte sniff is inconclusive.

    Returns:
        Sanitized HTML string with inline base64 images where applicable.

    Raises:
        UnsupportedFormatError: if the format can't be detected.
        Exception: converter-specific failures (bubbled for endpoint-level handling).
    """
    fmt = detect_format(file_path, declared_name)
    logger.info("Converting %s as format=%s", declared_name or file_path.name, fmt)

    if fmt == "docling":
        html = _convert_with_docling(file_path)
    elif fmt == "markdown":
        html = _convert_markdown(file_path)
    elif fmt == "json":
        html = _convert_json(file_path)
    elif fmt == "text":
        html = _convert_text(file_path)
    else:
        # Should be unreachable — detect_format raises on unknown
        raise UnsupportedFormatError(f"No converter for format '{fmt}'")

    return sanitize_html(html)
