"""PDF text + embedded-image extraction for PDF book import.

Used by knowledge-service's `/internal/parse/pdf-chunk` endpoint (one call
per N-page chunk — see docs/specs/2026-07-06-pdf-book-import.md L6). Not
part of the heading-detecting StructuralTree dispatcher (dispatcher.py) —
PDF import bypasses that entirely per L3 (chunk boundary = chapter
boundary, no "Chapter N" regex dependency).

Uses PyMuPDF (`fitz`) for per-page text + embedded-image extraction (the
one library in this ecosystem that does both in one pass — pypdf, used by
lore-enrichment-service's `extract.py` for the separate grounding-corpus
path, has no embedded-image extraction). OCR fallback (pytesseract +
pdf2image) and image downscaling (Pillow) are import-guarded exactly like
`extract.py`'s discipline: a missing lib/binary degrades gracefully (text-
layer only / original-size image), it never crashes the caller. The OCR
language-pack mapping (`tesseract_lang_for`) is ported verbatim from
`extract.py` rather than imported cross-service — a future cleanup could
point `extract.py` at this shared module instead, but that's a separate,
lower-risk refactor of an already-working service, not required for PDF
book import to ship.

Known v1 limitation (locked in CLARIFY, not a bug): a vector-drawn chart
with no embedded raster image object isn't captured by
`page.get_images()` — only embedded raster images (photos, pasted PNGs/
JPEGs — the common case for a scanned figure or an exported chart image)
are extracted. Full-page rasterization as a fallback is a follow-up, not
v1 scope.
"""

from __future__ import annotations

import hashlib
import io
import logging
from dataclasses import dataclass, field

logger = logging.getLogger("loreweave_parse.pdf_walker")

#: A page with fewer than this many extracted text chars is treated as
#: "scanned" (image-only) and routed to OCR when OCR is available. Mirrors
#: lore-enrichment-service's extract.py:_PDF_OCR_MIN_CHARS_PER_PAGE.
_OCR_MIN_CHARS_PER_PAGE = 8

#: Default OCR language string (CJK + English) — used when no language
#: hint is given or it maps to an uninstalled pack. A safe superset.
_DEFAULT_OCR_LANG = "chi_sim+chi_tra+eng"

#: Tesseract language packs assumed installed in the knowledge-service
#: image (mirrors extract.py's _INSTALLED_OCR_LANGS — keep both lists in
#: sync with each Dockerfile's `apt-get install tesseract-ocr-*` lines).
_INSTALLED_OCR_LANGS = frozenset({"chi_sim", "chi_tra", "eng", "jpn", "vie"})

#: Book/chunk `language` hint (free text, lower-cased) → Tesseract lang
#: code(s). Ported verbatim from extract.py's _LANG_TO_TESS.
_LANG_TO_TESS = {
    "zh": "chi_sim+chi_tra", "cmn": "chi_sim+chi_tra", "chinese": "chi_sim+chi_tra",
    "zh-cn": "chi_sim", "zh-hans": "chi_sim", "zh_hans": "chi_sim",
    "zh-tw": "chi_tra", "zh-hant": "chi_tra", "zh_hant": "chi_tra", "zh-hk": "chi_tra",
    "en": "eng", "eng": "eng", "english": "eng",
    "ja": "jpn", "jpn": "jpn", "japanese": "jpn",
    "vi": "vie", "vie": "vie", "vietnamese": "vie",
}

#: Images with either dimension below this are treated as decorative
#: (tracking pixels, hairline rules, tiny bullet icons) and skipped —
#: never extracted, never sent to the vision op. (spec §6.3)
MIN_IMAGE_DIMENSION_PX = 64

#: Default longest-side cap for downscale_for_vision. Comfortably above
#: what a vision model's tiling needs while bounding request size/cost.
DEFAULT_VISION_MAX_DIMENSION_PX = 1536


def tesseract_lang_for(language: str | None) -> str:
    """Map a chunk's `language` hint to a Tesseract `lang` string,
    restricted to _INSTALLED_OCR_LANGS. Ported verbatim from
    lore-enrichment-service's extract.py:tesseract_lang_for (spec §6.9 —
    the language-resolution wrapper, not just the raw Tesseract
    invocation, must be part of the port)."""
    if not language:
        return _DEFAULT_OCR_LANG
    key = language.strip().lower()
    if key in ("", "auto"):
        return _DEFAULT_OCR_LANG
    tess = _LANG_TO_TESS.get(key) or _LANG_TO_TESS.get(key.split("-")[0].split("_")[0])
    if tess is None:
        return _DEFAULT_OCR_LANG
    parts = tess.split("+")
    if "eng" not in parts:
        parts.append("eng")
    installed = [p for p in parts if p in _INSTALLED_OCR_LANGS]
    return "+".join(installed) or _DEFAULT_OCR_LANG


class PdfOpenError(ValueError):
    """Raised when a PDF can't be usefully opened: corrupted/malformed, OR
    password-protected. fitz opens an encrypted PDF without raising — it
    just returns empty text from every page (doc.needs_pass stays True) —
    so this wraps BOTH failure modes into one typed, non-silent error.
    Callers (pdf-peek) must reject on this immediately rather than let an
    encrypted PDF silently produce an empty "completed" import (spec §6.2)."""


@dataclass(frozen=True)
class PageContent:
    """One page's extracted text. `page_number` is 1-indexed (matches the
    page_start/page_end convention used by the /internal/parse/pdf-chunk
    request contract)."""

    page_number: int
    text: str
    ocr_used: bool


@dataclass(frozen=True)
class ExtractedImage:
    """One embedded raster image, already deduped + size-filtered within
    the walked page range (spec §6.3)."""

    page_number: int  # first page it was seen on, 1-indexed
    data: bytes  # original bytes, as embedded in the PDF (no downscale)
    ext: str  # e.g. "png", "jpeg" — from fitz's extract_image
    content_hash: str  # sha256 hex — the dedup key


@dataclass(frozen=True)
class WalkResult:
    pages: list[PageContent] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)


def get_page_count(data: bytes) -> int:
    """Cheap open + page count. Raises PdfOpenError on a corrupted or
    password-protected PDF — used by the pdf-peek endpoint to reject
    early, before the user even reaches the chunking-configuration step
    (spec §6.2)."""
    doc = _open_pdf(data)
    try:
        return doc.page_count
    finally:
        doc.close()


def walk_pdf_pages(
    data: bytes,
    *,
    page_start: int,
    page_end: int,
    language: str | None = None,
) -> WalkResult:
    """Extract text + embedded images for pages [page_start, page_end]
    (1-indexed, inclusive — clamped to the PDF's actual page count).

    Raises PdfOpenError on a corrupted/encrypted PDF (callers should have
    already rejected this at pdf-peek time, but this function re-checks
    defensively since it can be called independently).
    """
    doc = _open_pdf(data)
    try:
        page_count = doc.page_count
        start = max(1, page_start)
        end = min(page_count, page_end)

        pages: list[PageContent] = []
        page_texts: dict[int, str] = {}
        scanned_page_indices: list[int] = []  # 0-indexed, whole-doc numbering
        seen_hashes: set[str] = set()
        images: list[ExtractedImage] = []

        for page_no in range(start, end + 1):
            page = doc[page_no - 1]
            text = (page.get_text() or "").strip()
            page_texts[page_no] = text
            if len(text) < _OCR_MIN_CHARS_PER_PAGE:
                scanned_page_indices.append(page_no - 1)

            for img in page.get_images(full=True):
                xref = img[0]
                try:
                    extracted = doc.extract_image(xref)
                except Exception:  # noqa: BLE001 — a malformed image xref → skip it, not fatal
                    continue
                img_bytes = extracted.get("image")
                if not img_bytes:
                    continue
                width, height = extracted.get("width", 0), extracted.get("height", 0)
                if width and height and (width < MIN_IMAGE_DIMENSION_PX or height < MIN_IMAGE_DIMENSION_PX):
                    continue  # decorative/tracking-pixel filter (spec §6.3)
                digest = hashlib.sha256(img_bytes).hexdigest()
                if digest in seen_hashes:
                    continue  # dedup — repeated logo/watermark captions once (spec §6.3)
                seen_hashes.add(digest)
                images.append(ExtractedImage(
                    page_number=page_no,
                    data=img_bytes,
                    ext=extracted.get("ext", "png"),
                    content_hash=digest,
                ))

        ocr_used_pages: set[int] = set()
        if scanned_page_indices:
            ocr_texts = _ocr_pdf_pages(data, scanned_page_indices, language=language)
            for idx, text in ocr_texts.items():
                if text.strip():
                    page_no = idx + 1
                    page_texts[page_no] = text.strip()
                    ocr_used_pages.add(page_no)

        for page_no in range(start, end + 1):
            pages.append(PageContent(
                page_number=page_no,
                text=page_texts.get(page_no, ""),
                ocr_used=page_no in ocr_used_pages,
            ))

        return WalkResult(pages=pages, images=images)
    finally:
        doc.close()


def downscale_for_vision(
    image_bytes: bytes, *, max_dimension: int = DEFAULT_VISION_MAX_DIMENSION_PX
) -> bytes:
    """Return a downscaled copy of image_bytes for the vision-caption call
    ONLY — the caller is responsible for uploading the ORIGINAL
    (un-downscaled) bytes to MinIO separately (spec §4.3/§6.3). Returns
    the input unchanged if Pillow is unavailable, the image is already
    small enough, or decoding fails for any reason — never raises."""
    try:
        from PIL import Image
    except Exception:  # noqa: BLE001 — Pillow missing → return original, no crash
        return image_bytes
    try:
        img = Image.open(io.BytesIO(image_bytes))
        width, height = img.size
        if max(width, height) <= max_dimension:
            return image_bytes
        scale = max_dimension / max(width, height)
        resized = img.resize((max(1, int(width * scale)), max(1, int(height * scale))))
        buf = io.BytesIO()
        resized.save(buf, format=img.format or "PNG")
        return buf.getvalue()
    except Exception:  # noqa: BLE001 — any decode/resize failure → return original, no crash
        logger.warning("downscale_for_vision failed — using original bytes", exc_info=True)
        return image_bytes


def _open_pdf(data: bytes):
    try:
        import fitz
    except Exception as exc:  # noqa: BLE001
        raise PdfOpenError(f"PyMuPDF unavailable: {exc}") from exc
    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001 — corrupted/malformed PDF
        raise PdfOpenError(f"failed to open PDF: {exc}") from exc
    if doc.needs_pass:
        doc.close()
        raise PdfOpenError("PDF is password-protected")
    return doc


def _ocr_pdf_pages(data: bytes, indices: list[int], *, language: str | None = None) -> dict[int, str]:
    """OCR the given 0-based page indices. Import-guarded: if
    pdf2image/pytesseract or the Tesseract binary is unavailable, returns
    {} (caller keeps the text layer, ocr_used stays False for those
    pages). Mirrors extract.py's _ocr_pdf_pages."""
    try:
        import pytesseract
        from pdf2image import convert_from_bytes
    except Exception:  # noqa: BLE001 — OCR libs not installed → skip OCR
        logger.info("OCR libraries unavailable — skipping OCR (text-layer only)")
        return {}
    ocr_lang = tesseract_lang_for(language)
    out: dict[int, str] = {}
    try:
        for i in indices:
            images = convert_from_bytes(data, first_page=i + 1, last_page=i + 1)
            if not images:
                continue
            out[i] = pytesseract.image_to_string(images[0], lang=ocr_lang)
    except Exception:  # noqa: BLE001 — Tesseract binary / poppler missing → skip
        logger.warning("OCR failed (Tesseract/poppler unavailable?) — text-layer only", exc_info=True)
        return {}
    return out


__all__ = [
    "DEFAULT_VISION_MAX_DIMENSION_PX",
    "MIN_IMAGE_DIMENSION_PX",
    "ExtractedImage",
    "PageContent",
    "PdfOpenError",
    "WalkResult",
    "downscale_for_vision",
    "get_page_count",
    "tesseract_lang_for",
    "walk_pdf_pages",
]
