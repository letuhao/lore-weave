"""Compose router — the unified async entry for the enrichment input modes.

Compose lets the author start enrichment *the way they want* (spec
``docs/specs/2026-06-03-enrichment-compose.md``), not only by filling a detected
gap. Slice 1 ships the **spine** + **mode D (draft expansion)**:

  * ``input_source='draft'`` — the author pastes their OWN draft for an entity
    (existing OR new) and it is expanded into the kind's dimensions via the
    ``compose_draft`` technique (own seeded generation, no corpus). H0-quarantined.
  * ``input_source='gap'`` — mode A reuse: enrich specific gap targets (the same
    targeted path ``auto-enrich`` already exposes), unified under one endpoint.

Modes C (paste-context), F (files), B (intent) arrive in slices 2–4 — this
handler refuses them with a clear 400 so a premature FE call fails loudly.

Async like auto-enrich: create the job + persist the request (additive JSONB
fields: ``input_source`` / ``seed_text`` / ``expand_mode``) + enqueue the resume
trigger → 202 + job_id. The background worker re-drives ``run_job`` (the SAME
consumer as resume) which selects the ``compose_draft`` pipeline and threads
``seed_text`` / ``expand_mode`` into the StrategyContext.

H0 (LOCKED): a compose job ONLY ever produces QUARANTINED proposals
(origin='enrichment', confidence<1.0, review_status='proposed'). A **new** target
(``target.mode='new'``) writes NOTHING to glossary at compose time — the proposal
carries ``target_ref=None`` + the canonical_name, and the glossary anchor is minted
only at the author's ④ promote (the writeback resolve-or-create seam). So a rejected
new-target proposal leaves glossary untouched. No model NAMES (model_ref only).
"""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.gaps import coverages_from_rows
from app.api.principal import Principal, require_principal
from app.clients.glossary import GlossaryClient, GlossaryServiceError
from app.config import settings
from app.db.book_profile import get_book_profile
from app.deps import get_db
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.jobs.job_request import save_job_request
from app.jobs.proposal_store import PgProposalStore
from app.strategies.base import Technique
from app.strategies.draft_expand import EXPAND_ADD_ONLY, EXPAND_REWRITE

logger = logging.getLogger("lore_enrichment.compose")

router = APIRouter(prefix="/v1/lore-enrichment/projects", tags=["compose"])

# Slice 1 supports these input sources; the rest land in slices 2–4.
_SUPPORTED_SOURCES = {"gap", "draft"}
_FUTURE_SOURCES = {"context", "files", "intent"}
_EXPAND_MODES = {EXPAND_ADD_ONLY, EXPAND_REWRITE}
# Cap the pasted draft so it can't blow up the LLM prompt. ~50 KB ≈ the spec's
# mode-C context cap (D-COMPOSE-S1-DRAFT-CAP; mode C/F will reuse this constant).
_MAX_DRAFT_CHARS = 50_000


class ComposeTargetInput(BaseModel):
    """The entity a compose run targets — existing canon OR a new entity.

    ``mode='existing'`` → enrich a known glossary entity (``target_ref`` set, plus
    any ``present_dimensions`` the FE already knows). ``mode='new'`` → create from
    the input: ``target_ref`` MUST be None so the proposal is tagged new; the
    glossary anchor is minted only at PROMOTE (H0-clean). ``entity_kind`` is any
    C1-modeled kind or ``generic`` (the freeform fallback)."""

    # Constrained to the contract enum (openapi: [existing, new]) so a typo'd mode
    # can't silently mis-route a new-entity request onto the existing path (422).
    mode: Literal["existing", "new"] = "existing"
    canonical_name: str = Field(min_length=1)
    entity_kind: str = "location"
    target_ref: str | None = None
    present_dimensions: list[str] = Field(default_factory=list)


class ComposeBody(BaseModel):
    book_id: UUID
    input_source: str
    # Optional: mode D (draft) does NO retrieval/embed, so it needs no embedding
    # model (D-COMPOSE-S1-EMBED-REF). The gap path still requires it (validated in
    # the handler). build_live_runner ignores it regardless (the embed seam resolves
    # the model from the StrategyContext), so a missing ref never breaks a draft job.
    embedding_model_ref: UUID | None = None
    generation_model_ref: UUID
    # mode D (draft): the author's draft + how to expand it.
    target: ComposeTargetInput | None = None
    draft_text: str | None = None
    expand_mode: str = EXPAND_REWRITE
    # mode A (gap): the specific gap targets to enrich (LE-064 per-row shape).
    gap_targets: list[ComposeTargetInput] | None = None
    # output config (shared with auto-enrich). draft FORCES compose_draft; gap may
    # pick retrieval/fabrication/recook (gate-enforced downstream).
    technique: str | None = None
    max_spend_usd: float | None = Field(default=None, ge=0.0)
    eval_reserve_fraction: float = Field(default=0.15, ge=0.0, lt=1.0)
    top_k: int = Field(default=5, ge=1, le=20)


def _target_dict(t: ComposeTargetInput) -> dict:
    """Project a target onto the persisted ``targets`` shape the worker re-drives
    (mirrors auto-enrich). For a NEW target ``target_ref`` stays None so the
    proposal is tagged new (anchor minted at promote); for an existing target it
    falls back to the canonical_name when the FE omits a ref."""
    is_new = t.mode == "new"
    return {
        "canonical_name": t.canonical_name,
        "target_ref": None if is_new else (t.target_ref or t.canonical_name),
        "entity_kind": t.entity_kind,
        "mention_count": 1,
        "present_dimensions": [] if is_new else list(t.present_dimensions),
    }


async def _resolve_present_dimensions(
    pool: asyncpg.Pool, book_id: UUID, canonical_name: str
) -> list[str] | None:
    """Best-effort: read an EXISTING entity's already-covered dimensions from the
    glossary so an ``add_only`` draft ADDS only the genuinely-missing dims (review #1)
    — the FE composer has no coverage info, so without this an add_only draft on a
    covered entity would regenerate dims the entity already has. Returns None on any
    failure / a never-seen name → the caller degrades to ``present=[]`` (generate all),
    never hard-failing the compose. The glossary stays the SSOT (this only READS)."""
    client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
    )
    try:
        rows = await client.list_enrichment_coverage(book_id=book_id, limit=500)
    except (GlossaryServiceError, Exception):  # noqa: BLE001 — best-effort; degrade
        return None
    finally:
        await client.aclose()
    profile = await get_book_profile(pool, book_id)
    for cov in coverages_from_rows(rows, profile):
        if cov.canonical_name == canonical_name:
            return list(cov.present_dimensions)
    return None  # entity not found in coverage → no known present dims


async def _create_and_enqueue(
    *,
    pool: asyncpg.Pool,
    project_id: UUID,
    user_id: str,
    body: ComposeBody,
    technique: str,
    entity_kind: str,
    targets: list[dict],
    extra_request: dict | None = None,
) -> dict:
    """Create the job row, persist the re-drive request (+ any compose-specific
    fields), and enqueue the resume trigger. Returns the 202 response body. Mirrors
    the auto-enrich create/persist/enqueue sequence so the worker path is identical."""
    store = PgProposalStore(pool)
    db_job_id = await store.create_job(
        user_id=user_id,
        project_id=str(project_id),
        book_id=str(body.book_id),
        technique=technique,
        entity_kind=entity_kind,
        max_spend=body.max_spend_usd,
        estimated_cost=0.0,
    )
    request: dict = {
        "project_id": str(project_id),
        # Optional for draft (D-COMPOSE-S1-EMBED-REF) — None when the author didn't
        # pick an embed model; the worker passes it through and build_live_runner
        # ignores it (the embed seam resolves the model from the StrategyContext).
        "embedding_model_ref": str(body.embedding_model_ref) if body.embedding_model_ref else None,
        "generation_model_ref": str(body.generation_model_ref),
        "technique": technique,
        "top_k": body.top_k,
        "eval_reserve_fraction": body.eval_reserve_fraction,
        "max_spend_usd": body.max_spend_usd,
        "entity_kind": entity_kind,
        "targets": targets,
        "user_id": user_id,
        "book_id": str(body.book_id),
        "input_source": body.input_source,
    }
    if extra_request:
        request.update(extra_request)
    await save_job_request(pool=pool, job_id=UUID(db_job_id), request=request)

    producer = make_redis_producer(settings.redis_url)
    try:
        await producer.xadd(
            LORE_ENRICHMENT_RESUME_STREAM,
            {"job_id": db_job_id, "project_id": str(project_id), "user_id": user_id},
            maxlen=10000,
        )
        enqueued = True
    except Exception:  # noqa: BLE001 — the job + request persist; re-triggerable
        logger.warning("compose enqueue failed for job %s (re-triggerable)", db_job_id, exc_info=True)
        enqueued = False
    finally:
        await producer.aclose()

    return {
        "project_id": str(project_id),
        "job_id": db_job_id,
        "input_source": body.input_source,
        "technique": technique,
        "enqueued_targets": len(targets),
        "enqueued": enqueued,
    }


@router.post("/{project_id}/compose", status_code=status.HTTP_202_ACCEPTED)
async def compose(
    project_id: UUID,
    body: ComposeBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Start a compose enrichment job (async, 202 + job_id). Slice 1: gap | draft.

    H0 unchanged: the job only ever produces QUARANTINED proposals; a new target's
    glossary anchor is minted only at PROMOTE (nothing enters glossary here)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")
    user_id = str(principal.user_id)

    source = body.input_source
    if source in _FUTURE_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"input_source {source!r} is not available yet "
                "(modes C/F/B land in compose slices 2–4)"
            ),
        )
    if source not in _SUPPORTED_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown input_source {source!r}",
        )

    # ── mode D — draft expansion ────────────────────────────────────────────────
    if source == "draft":
        draft = (body.draft_text or "").strip()
        if not draft:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="draft input requires a non-empty draft_text",
            )
        if len(draft) > _MAX_DRAFT_CHARS:
            # D-COMPOSE-S1-DRAFT-CAP: bound the prompt — a huge paste should use a
            # file upload (mode F, async) rather than the synchronous draft path.
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"draft_text is too large ({len(draft)} chars > {_MAX_DRAFT_CHARS} cap) "
                    "— trim it or use a file upload (mode F, coming in a later slice)"
                ),
            )
        if body.target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="draft input requires a target (existing or new)",
            )
        if body.expand_mode not in _EXPAND_MODES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"unknown expand_mode {body.expand_mode!r} (add_only|rewrite)",
            )
        target_dict = _target_dict(body.target)
        if body.expand_mode == EXPAND_REWRITE:
            # /review-impl MED: rewrite expands ALL dimensions (the author wants a full
            # rewrite, per spec §2.5), NOT just the missing ones. Clear present_dimensions
            # so _gap_from_target never drops a well-covered entity to a SILENT no-op
            # (it returns None when nothing is "missing").
            target_dict["present_dimensions"] = []
        elif body.target.mode == "existing" and not body.target.present_dimensions:
            # /review-impl #1: add_only "only adds the missing dims" — but the FE composer
            # doesn't know which the entity already covers. Derive them server-side from
            # the glossary (best-effort; degrades to present=[] = generate all). Skipped
            # for a new entity (nothing covered) or when the FE supplied present explicitly.
            present = await _resolve_present_dimensions(
                pool, body.book_id, body.target.canonical_name
            )
            if present is not None:
                target_dict["present_dimensions"] = present
        return await _create_and_enqueue(
            pool=pool,
            project_id=project_id,
            user_id=user_id,
            body=body,
            technique=Technique.COMPOSE_DRAFT.value,  # forced — mode D is its own path
            entity_kind=body.target.entity_kind,
            targets=[target_dict],
            extra_request={"seed_text": draft, "expand_mode": body.expand_mode},
        )

    # ── mode A — gap-fill (targeted) ─────────────────────────────────────────────
    if not body.gap_targets:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="gap input requires gap_targets",
        )
    if body.embedding_model_ref is None:
        # The gap path keeps the auto-enrich contract (an embed model is expected);
        # only mode D relaxes it (D-COMPOSE-S1-EMBED-REF).
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="gap input requires embedding_model_ref",
        )
    try:
        technique = Technique(body.technique or Technique.RETRIEVAL.value)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown technique {body.technique!r}",
        )
    if technique is Technique.COMPOSE_DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="compose_draft is the draft input's technique — use input_source='draft'",
        )
    targets = [_target_dict(t) for t in body.gap_targets]
    return await _create_and_enqueue(
        pool=pool,
        project_id=project_id,
        user_id=user_id,
        body=body,
        technique=technique.value,
        entity_kind=body.gap_targets[0].entity_kind,
        targets=targets,
    )
