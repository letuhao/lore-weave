"""Mode-F file text extraction (Compose slice 3).

`extract_text(filename, data)` → `ExtractResult(text, pages, ocr_used)` for the
supported formats (.txt .md .pdf .docx .epub). For a scanned PDF (no/low text
layer) it falls back to OCR (Tesseract chi_sim+chi_tra+eng via pytesseract over
pages rasterised by pdf2image).

DESIGN — graceful degradation: every heavy parser (pypdf, python-docx, ebooklib,
pytesseract/pdf2image) is imported LAZILY inside its branch. A missing library or
Tesseract binary does NOT crash the service — the PDF text layer is still
returned and `ocr_used` stays False (OCR simply doesn't run). This keeps the
module unit-testable without the OCR image and makes OCR a pure image-capability
upgrade. A genuinely unsupported extension raises `UnsupportedFileError` (→ 415).

This module is PURE (bytes → text); it does no I/O of its own and never raises on
an empty/whitespace document (returns empty text) — the caller decides what an
empty extraction means.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger("lore_enrichment.files.extract")

#: Accepted upload extensions (lower-case, with dot).
SUPPORTED_EXTENSIONS = frozenset({".txt", ".md", ".pdf", ".docx", ".epub"})

#: A page with fewer than this many extracted text chars is treated as "scanned"
#: (image-only) and routed to OCR when OCR is available.
_PDF_OCR_MIN_CHARS_PER_PAGE = 8


class UnsupportedFileError(ValueError):
    """Raised for a file extension outside SUPPORTED_EXTENSIONS (→ 415)."""


@dataclass(frozen=True)
class ExtractResult:
    text: str
    pages: int
    ocr_used: bool


def file_extension(filename: str) -> str:
    """Lower-cased extension (with dot), e.g. 'A.PDF' → '.pdf'."""
    return os.path.splitext(filename or "")[1].lower()


def extract_text(filename: str, data: bytes, *, max_pages: int = 300) -> ExtractResult:
    """Extract plain text from an uploaded file's bytes. Dispatches by extension;
    raises UnsupportedFileError for anything not in SUPPORTED_EXTENSIONS."""
    ext = file_extension(filename)
    if ext in (".txt", ".md"):
        return ExtractResult(text=_decode(data), pages=1, ocr_used=False)
    if ext == ".pdf":
        return _extract_pdf(data, max_pages=max_pages)
    if ext == ".docx":
        return _extract_docx(data)
    if ext == ".epub":
        return _extract_epub(data)
    raise UnsupportedFileError(f"unsupported file type {ext!r} (allowed: {sorted(SUPPORTED_EXTENSIONS)})")


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace").strip()


def _extract_pdf(data: bytes, *, max_pages: int) -> ExtractResult:
    """PDF text layer via pypdf; OCR fallback (page-by-page) for scanned pages."""
    try:
        from pypdf import PdfReader
    except Exception:  # noqa: BLE001 — pypdf missing → no PDF support, but don't crash
        logger.warning("pypdf unavailable — cannot extract PDF text")
        return ExtractResult(text="", pages=0, ocr_used=False)

    reader = PdfReader(io.BytesIO(data))
    all_pages = reader.pages
    # Page cap bounds the OCR fan-out. Truncation is intentional but must NOT be
    # silent (project rule) — log it so ops can see a doc was only partially read.
    if len(all_pages) > max_pages:
        logger.warning(
            "PDF has %d pages > cap %d — extracting the first %d only (rest skipped)",
            len(all_pages), max_pages, max_pages,
        )
    pages = all_pages[:max_pages]
    page_texts: list[str] = []
    scanned_idx: list[int] = []
    for i, page in enumerate(pages):
        try:
            t = (page.extract_text() or "").strip()
        except Exception:  # noqa: BLE001 — a malformed page → treat as empty/scanned
            t = ""
        page_texts.append(t)
        if len(t) < _PDF_OCR_MIN_CHARS_PER_PAGE:
            scanned_idx.append(i)

    ocr_used = False
    if scanned_idx:
        ocr_pages = _ocr_pdf_pages(data, scanned_idx, max_pages=max_pages)
        if ocr_pages:
            ocr_used = True
            for i, text in ocr_pages.items():
                if text.strip():
                    page_texts[i] = text.strip()

    return ExtractResult(text="\n\n".join(t for t in page_texts if t).strip(),
                         pages=len(pages), ocr_used=ocr_used)


def _ocr_pdf_pages(data: bytes, indices: list[int], *, max_pages: int) -> dict[int, str]:
    """OCR the given 0-based page indices. Import-guarded: if pdf2image/pytesseract
    or the Tesseract binary is unavailable, returns {} (caller keeps the text layer
    and ocr_used=False). Languages: Simplified + Traditional Chinese + English."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception:  # noqa: BLE001 — OCR libs not installed → skip OCR
        logger.info("OCR libraries unavailable — skipping OCR (text-layer only)")
        return {}
    out: dict[int, str] = {}
    try:
        for i in indices:
            if i >= max_pages:
                break
            images = convert_from_bytes(data, first_page=i + 1, last_page=i + 1)
            if not images:
                continue
            # NOTE (accepted): languages are fixed to CJK+English (the demo corpus).
            # A non-CJK book's scan OCRs sub-optimally — thread book profile.language
            # here later (D-COMPOSE-S3-OCR-LANG). Mixing extra langs slows Tesseract,
            # so we don't just add every pack.
            out[i] = pytesseract.image_to_string(images[0], lang="chi_sim+chi_tra+eng")
    except Exception:  # noqa: BLE001 — Tesseract binary missing / poppler missing → skip
        logger.warning("OCR failed (Tesseract/poppler unavailable?) — text-layer only", exc_info=True)
        return {}
    return out


def _extract_docx(data: bytes) -> ExtractResult:
    try:
        import docx  # python-docx
    except Exception:  # noqa: BLE001
        logger.warning("python-docx unavailable — cannot extract .docx")
        return ExtractResult(text="", pages=0, ocr_used=False)
    document = docx.Document(io.BytesIO(data))
    paras = [p.text for p in document.paragraphs if p.text and p.text.strip()]
    return ExtractResult(text="\n\n".join(paras).strip(), pages=1, ocr_used=False)


def _extract_epub(data: bytes) -> ExtractResult:
    try:
        import ebooklib
        from bs4 import BeautifulSoup
        from ebooklib import epub
    except Exception:  # noqa: BLE001
        logger.warning("ebooklib/beautifulsoup4 unavailable — cannot extract .epub")
        return ExtractResult(text="", pages=0, ocr_used=False)
    book = epub.read_epub(io.BytesIO(data))
    chunks: list[str] = []
    n = 0
    for item in book.get_items_of_type(ebooklib.ITEM_DOCUMENT):
        n += 1
        soup = BeautifulSoup(item.get_content(), "html.parser")
        text = soup.get_text(separator="\n").strip()
        if text:
            chunks.append(text)
    return ExtractResult(text="\n\n".join(chunks).strip(), pages=n, ocr_used=False)
