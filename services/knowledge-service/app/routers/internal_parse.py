"""P1 — /internal/parse endpoint.

Stateless wrapper around the loreweave_parse SDK (structural decomposer
T1 of the hierarchical extraction ADR). No DB, no LLM, no embedding.

Callers (cross-service):
  - worker-infra import_processor.go (async path for EPUB/DOCX/MD)
  - book-service .txt import branch  (sync path for plain-text uploads)

Both POST the SAME contract; this endpoint never knows which.

Spec: docs/specs/2026-05-23-p1-structural-decomposer.md §D6.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from opentelemetry import trace
from pydantic import ValidationError

from app.config import settings
from app.middleware.internal_auth import require_internal_token
from loreweave_parse import ParseRequest, StructuralTree, parse

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

router = APIRouter(
    prefix="/internal",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.post(
    "/parse",
    response_model=StructuralTree,
    summary="Structural decomposer (P1)",
    description=(
        "Parse pandoc HTML, plain text, or a Tiptap JSON doc (26 IX-6 re-parse) "
        "into a StructuralTree (book -> part -> chapter -> scene). Stateless; no "
        f"persistence. Body cap: {settings.max_parse_body_bytes} bytes."
    ),
)
async def parse_endpoint(request: Request) -> StructuralTree:
    # Read body with explicit size cap (H3 fix). Starlette's default does
    # not enforce a ceiling; we must check explicitly.
    body_bytes = await request.body()
    if len(body_bytes) > settings.max_parse_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"body {len(body_bytes)} bytes exceeds cap "
                f"{settings.max_parse_body_bytes} bytes"
            ),
        )

    # Parse + validate the envelope. ValidationError -> 400 (caller bug).
    try:
        req = ParseRequest.model_validate_json(body_bytes)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"invalid request body: {e.errors()}",
        ) from e
    except ValueError as e:  # bad JSON
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"malformed JSON: {e}",
        ) from e

    # L4 fix: empty/whitespace-only content -> 422.
    if not req.content or not req.content.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="content is empty or whitespace-only",
        )

    with tracer.start_as_current_span("parse.structural_decomposition") as span:
        span.set_attribute("source_format", req.source_format)
        span.set_attribute("body_bytes", len(body_bytes))
        if req.language:
            span.set_attribute("language", req.language)

        try:
            tree = parse(
                req.source_format,
                req.content,
                language=req.language,
                filename=req.filename,
                options=req.options,
            )
        except ValueError as e:
            # Unknown source_format from the dispatcher — caller bug.
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            ) from e

        span.set_attribute("part_count", len(tree.parts))
        chapter_count = sum(len(p.chapters) for p in tree.parts)
        scene_count = sum(
            len(c.scenes) for p in tree.parts for c in p.chapters
        )
        span.set_attribute("chapter_count", chapter_count)
        span.set_attribute("scene_count", scene_count)
        span.set_attribute("walker_path", tree.walker_path)
        # L2 fix (spec D6): leaf_max_chars for downstream sizing telemetry.
        leaf_max = max(
            (len(s.leaf_text) for p in tree.parts for c in p.chapters for s in c.scenes),
            default=0,
        )
        span.set_attribute("leaf_max_chars", leaf_max)
        if tree.detected_language:
            span.set_attribute("detected_language", tree.detected_language)

        return tree
