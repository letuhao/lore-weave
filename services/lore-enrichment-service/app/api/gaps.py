"""D1 — gap auto-detection read endpoint.

Wires the C7 gap-detection engine (previously library-only — QC F-C7-1) to a
production path: read the project's per-entity enrichment coverage from the
glossary SSOT, build EntityCoverage, and return the engine's RANKED gaps for
the author to triage. READ-ONLY — it surfaces under-described entities; it does
NOT kick off enrichment (the auto-enrich job mode is a deferred follow-up).

Coverage source (PO-approved 2026-05-31): glossary `enrichment-coverage`
(entities + mention_count + PROMOTED-enrichment dimensions). `present_dimensions`
= those promoted dims; the rest of the kind's frozen dimension table is the gap.
Over-detection on a fresh project is fine — this is a ranked candidate list.
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.principal import Principal, require_principal
from app.clients.glossary import (
    EntityCoverageRow,
    GlossaryClient,
    GlossaryServiceError,
)
from app.config import settings
from app.deps import get_db
from app.db.book_profile import NEUTRAL_PROFILE, BookProfile, get_book_profile
from app.gaps.engine import EntityCoverage, detect_ranked_gaps
from app.gaps.model import GENERIC_KIND, resolve_dimensions
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.jobs.job_request import save_job_request
from app.jobs.proposal_store import PgProposalStore
from app.strategies.base import Technique

logger = logging.getLogger("lore_enrichment.gaps")

router = APIRouter(prefix="/v1/lore-enrichment/projects", tags=["gaps"])


class DetectGapsBody(BaseModel):
    book_id: UUID
    limit: int = Field(default=200, ge=1, le=1000)


class AutoEnrichTarget(BaseModel):
    """One specific gap to enrich (LE-064 per-row "enrich →"). Mirrors the jobs
    router's GapTarget; the FE supplies a gap it already got from detect-gaps."""

    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None
    entity_kind: str = "location"
    mention_count: int = Field(default=1, ge=0)
    present_dimensions: list[str] = Field(default_factory=list)


class AutoEnrichBody(BaseModel):
    book_id: UUID
    embedding_model_ref: UUID
    generation_model_ref: UUID
    technique: str = "retrieval"
    max_gaps: int = Field(default=10, ge=1, le=100)        # top-N ranked gaps to enrich
    coverage_limit: int = Field(default=200, ge=1, le=1000)  # entities scanned for gaps
    max_spend_usd: float | None = Field(default=None, ge=0.0)
    eval_reserve_fraction: float = Field(default=0.15, ge=0.0, lt=1.0)
    top_k: int = Field(default=5, ge=1, le=20)
    # LE-064 — when set, enrich exactly these targets (the per-row "enrich →"),
    # bypassing detection + top-N ranking. Each target is a gap the FE already
    # received from detect-gaps, so it is trusted (the runner re-derives missing
    # dimensions per the C7 engine and skips a fully-described entity). Same async
    # worker path as a normal auto-enrich; max_gaps/coverage_limit are ignored.
    targets: list[AutoEnrichTarget] | None = None


def coverages_from_rows(
    rows: list[EntityCoverageRow], profile: BookProfile = NEUTRAL_PROFILE
) -> list[EntityCoverage]:
    """Map glossary coverage rows → engine EntityCoverage (de-bias C1, KB3 + KB-A).

    Multi-kind: ANY entity-kind is modeled — a kind with no built-in table falls
    back to GENERIC (never raises), so non-location entities are NEVER skipped.

    KB-A round-trip: the dimension table is resolved through the book ``profile``
    (``resolve_dimensions`` — localized labels + overrides), the SAME resolution
    generation/storage uses, so detect's labels match the stored labels per book
    (an English book detects "History" against stored "History", not static 历史).
    A 'present dimension' may be a stable ``id`` or a (localized) ``label`` — both
    map to the stable id; unknown dims drop (no drift). Empty name is the only skip.
    (Residual: a mid-life language change re-labels → re-detect; documented.)"""
    out: list[EntityCoverage] = []
    for r in rows:
        name = (r.canonical_name or "").strip()
        if not name:
            continue
        kind = (r.kind or "").strip() or GENERIC_KIND
        table = resolve_dimensions(
            kind, language=profile.language, overrides=profile.dimension_overrides
        )
        ids = {s.dimension for s in table}
        label_to_id = {s.label: s.dimension for s in table}
        present = tuple(
            d if d in ids else label_to_id[d]
            for d in r.dimensions
            if d in ids or d in label_to_id
        )
        out.append(
            EntityCoverage(
                entity_kind=kind,
                canonical_name=name,
                target_ref=r.canonical_name,
                mention_count=r.mention_count,
                present_dimensions=present,
            )
        )
    return out


@router.post("/{project_id}/detect-gaps")
async def detect_gaps(
    project_id: UUID,
    body: DetectGapsBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Detect + rank under-described entities in the book's glossary coverage.

    Returns ranked gaps (descending score) for author triage. The author then
    enriches chosen gaps via the existing job path (POST /v1/lore-enrichment/jobs
    with targets). READ-ONLY — no enrichment is started here."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")

    client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
    )
    try:
        rows = await client.list_enrichment_coverage(book_id=body.book_id, limit=body.limit)
    except GlossaryServiceError as exc:
        code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=code, detail=str(exc))
    finally:
        await client.aclose()

    # KB-A: localize the dimension tables via the book profile so detect matches
    # what generation/storage uses (per-book round-trip consistency).
    profile = await get_book_profile(pool, body.book_id)
    rankings = detect_ranked_gaps(coverages_from_rows(rows, profile))
    return {
        "project_id": str(project_id),
        "book_id": str(body.book_id),
        "entities_scanned": len(rows),
        # de-bias C2 T7: a book with NO extracted entities isn't enrichable yet —
        # signal "extract first" explicitly rather than returning a bare empty list
        # (the FE surfaces it; enrichment is downstream of knowledge extraction).
        "needs_extraction": len(rows) == 0,
        "gap_count": len(rankings),
        "gaps": [
            {
                "rank": gr.rank,
                "score": gr.score,
                "canonical_name": gr.gap.canonical_name,
                "entity_kind": gr.gap.entity_kind,
                "mention_count": gr.gap.mention_count,
                "present_dimensions": list(gr.gap.present_dimensions),
                "missing_dimensions": list(gr.gap.missing_dimensions),
            }
            for gr in rankings
        ],
    }


@router.post("/{project_id}/auto-enrich", status_code=status.HTTP_202_ACCEPTED)
async def auto_enrich(
    project_id: UUID,
    body: AutoEnrichBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Detect under-described entities and ENQUEUE an enrichment job over the
    top-N (the deferred D1 half). Composes detect-gaps + the job runner:

      detect (glossary coverage) → top max_gaps → create job + persist request
      (targets = the detected gaps) → enqueue → the background worker re-drives
      run_job (the SAME consumer as resume; a fresh job has no done gaps, so it
      enriches all selected). Non-blocking — returns 202 with the job_id.

    H0 unchanged: the job only ever produces QUARANTINED proposals. Spend is
    bounded by max_gaps + the per-job cost-cap (a breach pauses; resume continues)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    try:
        technique = Technique(body.technique)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown technique {body.technique!r}",
        )

    if body.targets:
        # LE-064 — targeted enrich: the FE passes specific gaps it already got from
        # detect-gaps. Trust them (the runner re-derives missing dimensions + skips a
        # fully-described entity), skip glossary detection + top-N ranking entirely.
        targets = [
            {
                "canonical_name": t.canonical_name,
                "target_ref": t.target_ref or t.canonical_name,
                "entity_kind": t.entity_kind,
                "mention_count": t.mention_count,
                "present_dimensions": t.present_dimensions,
            }
            for t in body.targets
        ]
        entities_scanned = len(targets)
        detected_total = len(targets)
    else:
        client = GlossaryClient(
            base_url=settings.glossary_service_url,
            internal_token=settings.internal_service_token,
        )
        try:
            rows = await client.list_enrichment_coverage(
                book_id=body.book_id, limit=body.coverage_limit
            )
        except GlossaryServiceError as exc:
            code = status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
            raise HTTPException(status_code=code, detail=str(exc))
        finally:
            await client.aclose()

        profile = await get_book_profile(pool, body.book_id)
        rankings = detect_ranked_gaps(coverages_from_rows(rows, profile))
        selected = rankings[: body.max_gaps]
        if not selected:
            # de-bias C2 T7: distinguish "nothing under-described" from "book not
            # extracted yet" (no entities at all) — the latter is the real prereq.
            needs_extraction = len(rows) == 0
            return {
                "project_id": str(project_id),
                "entities_scanned": len(rows),
                "detected": 0,
                "enqueued": False,
                "needs_extraction": needs_extraction,
                "message": (
                    "extract this book first — no entities found "
                    "(enrichment is downstream of knowledge extraction)"
                    if needs_extraction
                    else "no under-described entities to enrich"
                ),
            }

        # The detected gaps become the job's targets (so the worker re-drives them,
        # and a later resume can re-load the same request).
        targets = [
            {
                "canonical_name": gr.gap.canonical_name,
                "target_ref": gr.gap.target_ref,
                "entity_kind": gr.gap.entity_kind,
                "mention_count": gr.gap.mention_count,
                "present_dimensions": list(gr.gap.present_dimensions),
            }
            for gr in selected
        ]
        entities_scanned = len(rows)
        detected_total = len(rankings)

    store = PgProposalStore(pool)
    db_job_id = await store.create_job(
        user_id=str(principal.user_id),
        project_id=str(project_id),
        book_id=str(body.book_id),
        technique=technique.value,
        entity_kind="location",
        max_spend=body.max_spend_usd,
        estimated_cost=0.0,
    )
    await save_job_request(
        pool=pool,
        job_id=UUID(db_job_id),
        request={
            "project_id": str(project_id),
            "embedding_model_ref": str(body.embedding_model_ref),
            "generation_model_ref": str(body.generation_model_ref),
            "technique": technique.value,
            "top_k": body.top_k,
            "eval_reserve_fraction": body.eval_reserve_fraction,
            "max_spend_usd": body.max_spend_usd,
            "entity_kind": "location",
            "targets": targets,
            "user_id": str(principal.user_id),
            # C3/F-C12-1: persist the book scope so the worker-driven runner reads
            # authored glossary canon for the contradiction check (auto-reject).
            "book_id": str(body.book_id),
        },
    )

    producer = make_redis_producer(settings.redis_url)
    try:
        await producer.xadd(
            LORE_ENRICHMENT_RESUME_STREAM,
            {"job_id": db_job_id, "project_id": str(project_id), "user_id": str(principal.user_id)},
            maxlen=10000,
        )
        enqueued = True
    except Exception:  # noqa: BLE001 — the job + request persist; re-triggerable
        logger.warning("auto-enrich enqueue failed for job %s (re-triggerable)", db_job_id, exc_info=True)
        enqueued = False
    finally:
        await producer.aclose()

    return {
        "project_id": str(project_id),
        "job_id": db_job_id,
        "entities_scanned": entities_scanned,
        "detected": detected_total,
        "enqueued_gaps": len(targets),
        "enqueued": enqueued,
    }
