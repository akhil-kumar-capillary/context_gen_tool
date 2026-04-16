"""File ingestion — converts uploaded documents to HTML for context storage.

Supported formats:
  - PDF, DOCX, PPTX, XLSX, HTML, images (PNG/JPEG/TIFF)  → via Docling
  - Markdown (.md, .markdown)                            → via markdown-it-py
  - JSON                                                 → pretty-printed code fence
  - Plain text (.txt, .log, .csv-ish)                    → wrapped in <pre>

Output is always sanitized HTML (allowlist via bleach) with inline base64 images.
"""
from app.services.file_ingest.converter import (
    SUPPORTED_EXTENSIONS,
    UnsupportedFormatError,
    convert_file,
    detect_format,
)
from app.services.file_ingest.refactor import refactor_document

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "UnsupportedFormatError",
    "convert_file",
    "detect_format",
    "refactor_document",
]
