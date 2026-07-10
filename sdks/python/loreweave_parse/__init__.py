"""LoreWeave structural decomposer (hierarchical extraction T1).

Pure Python — no LLM, no embedding, no HTTP. Parses pandoc-HTML or plain
text into a StructuralTree (book → part → chapter → scene).

Top-level exports:
- ``parse`` — format dispatcher entry point.
- ``StructuralTree`` / ``Part`` / ``Chapter`` / ``Scene`` — output schema.
- ``ParseOptions`` / ``ParseRequest`` — input envelopes (D6 HTTP contract).
- ``detect_language`` — plaintext language detector.
- ``html_to_leaf_text`` — locked HTML→text helper (D4).

Spec: docs/specs/2026-05-23-p1-structural-decomposer.md
Parent ADR: docs/03_planning/KNOWLEDGE_SERVICE_HIERARCHICAL_EXTRACTION_ADR.md
"""

from loreweave_parse._text_strip import html_to_leaf_text
from loreweave_parse._types import (
    Chapter,
    ParseOptions,
    ParseRequest,
    Part,
    Scene,
    SourceFormat,
    StructuralTree,
    WalkerPath,
)
from loreweave_parse.dispatcher import parse
from loreweave_parse.html_walker import parse_html
from loreweave_parse.pdf_walker import (
    ExtractedImage,
    PageContent,
    PdfOpenError,
    WalkResult,
    downscale_for_vision,
    get_page_count,
    tesseract_lang_for,
    walk_pdf_pages,
)
from loreweave_parse.plaintext_parser import detect_language, parse_plain
from loreweave_parse.tiptap_walker import parse_tiptap

__version__ = "0.1.0"

__all__ = [
    "Chapter",
    "ExtractedImage",
    "PageContent",
    "ParseOptions",
    "ParseRequest",
    "Part",
    "PdfOpenError",
    "Scene",
    "SourceFormat",
    "StructuralTree",
    "WalkResult",
    "WalkerPath",
    "__version__",
    "detect_language",
    "downscale_for_vision",
    "get_page_count",
    "html_to_leaf_text",
    "parse",
    "parse_html",
    "parse_plain",
    "parse_tiptap",
    "tesseract_lang_for",
    "walk_pdf_pages",
]
