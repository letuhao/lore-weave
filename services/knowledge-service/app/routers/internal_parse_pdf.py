"""PDF-import vision op — /internal/parse/pdf-chunk endpoint.

Processes exactly ONE page-range chunk of a PDF per call (L6 — per-chunk,
not per-book, to bound each HTTP call's duration/payload size; see
docs/specs/2026-07-06-pdf-book-import.md §6.1/§6.5/§6.8). Caller (worker-
infra's ImportProcessor) loops chunks itself, one call per N-page window.

Separate from POST /internal/parse (internal_parse.py) — that endpoint's
`ParseRequest.content: str` single-text-blob contract stays untouched;
both of its existing callers (worker-infra's html path, book-service's
txt path) are unaffected by this addition.

Bypasses the heading-detecting StructuralTree dispatcher entirely (L3):
a chunk always becomes exactly one Chapter, titled "Pages {start}-{end}"
(+ a best-effort heading-line guess when one looks plausible — spec
§6.10 — never depended on downstream, the page-range title is always
present).
"""

from __future__ import annotations

import base64
import hashlib
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from opentelemetry import trace
from pydantic import BaseModel, Field

from app.clients.llm_client import get_llm_client
from app.config import settings
from app.middleware.internal_auth import require_internal_token
from loreweave_parse import (
    Chapter,
    PdfOpenError,
    Scene,
    downscale_for_vision,
    get_page_count,
    walk_pdf_pages,
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

#: Instruction sent to the vision op for every extracted image. Kept short
#: and data-focused since the caption is inlined into chapter text that
#: downstream glossary/KG extraction reads — a rambling caption pollutes
#: that signal.
_CAPTION_PROMPT = (
    "Describe this chart or image in 1-2 sentences, focusing on any data, "
    "labels, or text it contains."
)

#: Output token cap for a caption. The CAPTION ITSELF is short by design
#: (see _CAPTION_PROMPT), but a reasoning-capable local vision model
#: (e.g. LM Studio's google/gemma-4-26b-a4b-qat) burns a large share of
#: this budget on a `reasoning_content` scratchpad BEFORE writing the
#: actual answer into `content` — /review-impl 2026-07-06 live-caught
#: this at max_tokens=150: the model correctly read the test chart in
#: its reasoning (147 reasoning tokens) but got truncated
#: (finish_reason="length") before ever emitting real `content`, so the
#: caption came back empty. Confirmed live at max_tokens=600 the SAME
#: model completes reasoning (~440 tokens) and emits a correct one-
#: sentence caption. Sized with headroom above that measured case, not
#: just the caption's own length.
_CAPTION_MAX_TOKENS = 700

#: A first non-empty page line at or under this length, with no terminal
#: sentence punctuation, is treated as a plausible heading (spec §6.10).
#: Purely cosmetic — the page-range title is always present regardless.
_HEADING_GUESS_MAX_CHARS = 80

_EXT_TO_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}


class ParsePdfPeekRequest(BaseModel):
    """Request body for POST /internal/parse/pdf-peek."""

    pdf_bytes_b64: str = Field(..., min_length=1)


class ParsePdfPeekResponse(BaseModel):
    page_count: int


@router.post(
    "/parse/pdf-peek",
    response_model=ParsePdfPeekResponse,
    summary="PDF-import: cheap page-count peek",
    description=(
        "Opens a PDF just far enough to return its page count, rejecting "
        "encrypted/corrupted PDFs immediately (422) rather than letting "
        "the frontend proceed to chunk-configuration on an unusable file "
        "(spec §6.2). Called by book-service's POST "
        ".../import/pdf-peek, which this backs."
    ),
)
async def parse_pdf_peek_endpoint(req: ParsePdfPeekRequest) -> ParsePdfPeekResponse:
    try:
        pdf_bytes = base64.b64decode(req.pdf_bytes_b64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"pdf_bytes_b64 is not valid base64: {exc}",
        ) from exc
    if len(pdf_bytes) > settings.max_parse_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"decoded PDF {len(pdf_bytes)} bytes exceeds cap {settings.max_parse_body_bytes} bytes",
        )
    try:
        page_count = get_page_count(pdf_bytes)
    except PdfOpenError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"cannot open PDF: {exc}",
        ) from exc
    return ParsePdfPeekResponse(page_count=page_count)


class ParsePdfChunkRequest(BaseModel):
    """Request body for POST /internal/parse/pdf-chunk."""

    book_id: str
    pdf_bytes_b64: str = Field(..., min_length=1)
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    chunk_index: int = Field(..., ge=0)
    caption_images: bool = False
    language: str | None = None
    # BYOK — required only when caption_images=True; the vision op has no
    # platform default (Provider gateway invariant: explicit model_ref,
    # never a hardcoded model name).
    user_id: str | None = None
    model_source: str | None = None
    model_ref: str | None = None


class ChunkImage(BaseModel):
    """One extracted image from this chunk, already deduped + size-
    filtered by pdf_walker. `caption` is None when caption_images=False
    (L7) or the vision call failed/degraded (never fails the chunk)."""

    page_number: int
    image_bytes_b64: str
    ext: str
    caption: str | None = None
    model_ref: str | None = None


class ParsePdfChunkResponse(BaseModel):
    chapter: Chapter
    images: list[ChunkImage]


#: Terminal punctuation that marks a line as a sentence fragment rather
#: than a heading — ASCII + full-width CJK variants (per this repo's
#: Multilingual standard, docs/standards/multilingual.md: no ASCII-only
#: punctuation checks). /review-impl 2026-07-06: the original check was
#: ASCII-only (".,;:"), silently never treating a CJK-punctuated line as
#: non-heading-like even when it plainly was one.
_SENTENCE_TERMINAL_PUNCTUATION = ".,;:。，；：！？、"


def _guess_heading(first_page_text: str) -> str | None:
    """Best-effort heading-line guess (spec §6.10) — purely cosmetic,
    never required. Returns None when no line looks plausible."""
    for line in first_page_text.splitlines():
        candidate = line.strip()
        if not candidate or len(candidate) > _HEADING_GUESS_MAX_CHARS:
            continue
        if candidate[-1:] in _SENTENCE_TERMINAL_PUNCTUATION:
            continue
        return candidate
    return None


async def _caption_image(
    image_bytes: bytes, ext: str, *, user_id: str, model_source: str, model_ref: str,
) -> str | None:
    """Caption one image via the vision op. NEVER raises — a guardrail
    rejection, upstream error, or non-completed job degrades to None
    (spec §6.4/§6.7's advisory discipline, same as thread_tag.py's
    classify loop)."""
    try:
        vision_bytes = downscale_for_vision(image_bytes)
        mime = _EXT_TO_MIME.get(ext.lower(), "image/png")
        llm = get_llm_client()
        job = await llm.submit_and_wait(
            user_id=user_id,
            operation="vision",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "image_b64": base64.b64encode(vision_bytes).decode("ascii"),
                "mime_type": mime,
                "prompt": _CAPTION_PROMPT,
                "max_tokens": _CAPTION_MAX_TOKENS,
            },
            job_meta={"extractor": "pdf_import_vision"},
        )
    except Exception as exc:  # noqa: BLE001 — advisory: an LLM outage never fails the chunk
        logger.warning("pdf-import vision caption failed: %r", exc)
        return None
    if getattr(job, "status", None) != "completed":
        logger.warning("pdf-import vision job not completed: %s", getattr(job, "status", "?"))
        return None
    result = getattr(job, "result", None) or {}
    caption = result.get("caption")
    return caption.strip() if isinstance(caption, str) and caption.strip() else None


@router.post(
    "/parse/pdf-chunk",
    response_model=ParsePdfChunkResponse,
    summary="PDF-import: parse one page-range chunk into one chapter",
    description=(
        "Extracts text + embedded images for pages [page_start, page_end] "
        "of a PDF, optionally captioning images via the vision op, and "
        "returns exactly one Chapter (no heading detection — chunk "
        "boundary = chapter boundary). One call per chunk (L6); the "
        f"caller loops chunks. Body cap: {settings.max_parse_body_bytes} bytes."
    ),
)
async def parse_pdf_chunk_endpoint(req: ParsePdfChunkRequest) -> ParsePdfChunkResponse:
    try:
        pdf_bytes = base64.b64decode(req.pdf_bytes_b64, validate=True)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"pdf_bytes_b64 is not valid base64: {exc}",
        ) from exc
    if len(pdf_bytes) > settings.max_parse_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"decoded PDF {len(pdf_bytes)} bytes exceeds cap {settings.max_parse_body_bytes} bytes",
        )
    if req.page_end < req.page_start:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"page_end ({req.page_end}) must be >= page_start ({req.page_start})",
        )
    if req.caption_images and not (req.user_id and req.model_source and req.model_ref):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="caption_images=true requires user_id, model_source, and model_ref",
        )

    with tracer.start_as_current_span("parse.pdf_chunk") as span:
        span.set_attribute("book_id", req.book_id)
        span.set_attribute("chunk_index", req.chunk_index)
        span.set_attribute("page_start", req.page_start)
        span.set_attribute("page_end", req.page_end)
        span.set_attribute("caption_images", req.caption_images)

        try:
            walk = walk_pdf_pages(
                pdf_bytes, page_start=req.page_start, page_end=req.page_end, language=req.language,
            )
        except PdfOpenError as exc:
            # Corrupted/encrypted — should already have been rejected at
            # pdf-peek time, but this endpoint re-checks defensively for
            # any caller that skips peek.
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"cannot open PDF: {exc}",
            ) from exc

        if not walk.pages:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"no pages in range [{req.page_start}, {req.page_end}]",
            )

        span.set_attribute("ocr_used", any(p.ocr_used for p in walk.pages))
        span.set_attribute("image_count", len(walk.images))

        chunk_images: list[ChunkImage] = []
        caption_by_hash: dict[str, str | None] = {}
        for img in walk.images:
            caption: str | None = None
            if req.caption_images:
                # Defensive re-dedup by hash — pdf_walker already dedupes
                # within its own walk, but this keeps the contract honest
                # if that ever changes upstream (never re-caption the same
                # image bytes twice within one chunk response).
                digest = hashlib.sha256(img.data).hexdigest()
                if digest in caption_by_hash:
                    caption = caption_by_hash[digest]
                else:
                    caption = await _caption_image(
                        img.data, img.ext,
                        user_id=req.user_id, model_source=req.model_source, model_ref=req.model_ref,
                    )
                    caption_by_hash[digest] = caption
            chunk_images.append(ChunkImage(
                page_number=img.page_number,
                image_bytes_b64=base64.b64encode(img.data).decode("ascii"),
                ext=img.ext,
                caption=caption,
                model_ref=req.model_ref if caption else None,
            ))

        page_texts = [p.text for p in walk.pages if p.text]
        body_text = "\n\n".join(page_texts)
        image_notes = "\n\n".join(
            f"[Image (page {img.page_number}): {img.caption}]"
            for img in chunk_images if img.caption
        )
        leaf_text = f"{body_text}\n\n{image_notes}".strip() if image_notes else body_text

        title = f"Pages {req.page_start}-{req.page_end}"
        heading = _guess_heading(walk.pages[0].text) if walk.pages[0].text else None
        if heading:
            title = f"{title}: {heading}"

        path = f"chunk-{req.chunk_index}"
        content_hash = hashlib.sha256(leaf_text.encode("utf-8")).hexdigest()
        chapter = Chapter(
            sort_order=1,  # placeholder — worker-infra assigns the real book-global sort_order
            title=title,
            path=path,
            html="",
            scenes=[Scene(sort_order=1, path=f"{path}/scene-1", leaf_text=leaf_text, content_hash=content_hash)],
        )

        return ParsePdfChunkResponse(chapter=chapter, images=chunk_images)
