"""Compose router — the unified async entry for the enrichment input modes.

Compose lets the author start enrichment *the way they want* (spec
``docs/specs/2026-06-03-enrichment-compose.md``), not only by filling a detected
gap. Slice 1 ships the **spine** + **mode D (draft expansion)**:

  * ``input_source='draft'`` — the author pastes their OWN draft for an entity
    (existing OR new) and it is expanded into the kind's dimensions via the
    ``compose_draft`` technique (own seeded generation, no corpus). H0-quarantined.
  * ``input_source='gap'`` — mode A reuse: enrich specific gap targets (the same
    targeted path ``auto-enrich`` already exposes), unified under one endpoint.

Slice 2 adds **mode C (paste-context)**:

  * ``input_source='context'`` — the author pastes reference text + a license
    assertion (default-deny: copyrighted/unknown refused). The text is ingested as
    a grounding corpus (the C2 ``ingest_corpus`` seam, synchronous) and a normal
    retrieval/recook job then grounds on it (the C2 grounding composer picks the
    corpus up by project_id — so NO worker/strategy change). H0-quarantined.

Slice 3 adds **mode F (files)** (`input_source='files'` — upload+extract+OCR via
/uploads, then ingest like context) and slice 4 adds **mode B (intent)**
(`input_source='intent'` — runs a confirmed target from /compose/resolve-intent).
All five input sources (gap/draft/context/files/intent) are now live.

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

import hashlib
import logging
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.api.gaps import coverages_from_rows
from app.api.principal import Principal, require_principal
from app.clients.glossary import GlossaryClient, GlossaryServiceError
from app.clients.knowledge import KnowledgeClient, KnowledgeServiceError
from app.config import settings
from app.db.book_profile import get_book_profile
from app.deps import get_db
from app.gaps.model import resolve_dimensions
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.jobs.job_request import save_job_request
from app.api.license_assert import resolve_asserted_license
from app.api.uploads import fetch_upload
from app.compose.compose_task import create_compose_task, enqueue_compose_task
from app.jobs.proposal_store import PgProposalStore
from app.retrieval.store import SourceCorpusStore
from app.strategies.base import Technique
from app.strategies.draft_expand import EXPAND_ADD_ONLY, EXPAND_REWRITE

logger = logging.getLogger("lore_enrichment.compose")

router = APIRouter(prefix="/v1/lore-enrichment/projects", tags=["compose"])

# All compose input sources (slices 1–4).
_SUPPORTED_SOURCES = {"gap", "draft", "context", "files", "intent"}
_FUTURE_SOURCES: set[str] = set()
_EXPAND_MODES = {EXPAND_ADD_ONLY, EXPAND_REWRITE}
# Cap the pasted text (draft AND context) so a huge paste can't blow up the LLM
# prompt / fan out into an unbounded synchronous embed in the request path. ~50 KB;
# larger material → mode F upload (async/poll). (D-COMPOSE-S1-DRAFT-CAP, spec §2.3.)
_MAX_DRAFT_CHARS = 50_000

# Mode C/F license default-deny → see app/api/license_assert.resolve_asserted_license.


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
    # Dimension picker (#1): when the author explicitly chooses WHICH dimensions to
    # enrich, the FE sends them here (ids or localized labels). None = "auto" — the
    # server derives present from coverage (existing) or enriches all (new), the prior
    # behavior. When set, present = the kind's full set MINUS requested, so the gap
    # builder's missing = exactly the requested dimensions.
    requested_dimensions: list[str] | None = None


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
    # mode C (context): the author's pasted reference text + their license assertion.
    # The text is ingested as a grounding corpus; a normal retrieval/recook job then
    # grounds on it. context_license is default-deny (copyrighted/unknown → refused).
    context_text: str | None = None
    context_license: str | None = None
    # mode C/F: keep the ingested corpus as a CURATED source (#7) instead of an
    # ephemeral paste the reaper GCs by TTL. Default false → ephemeral (prior behavior);
    # true → the corpus is untagged and surfaces under /sources for reuse.
    persist_corpus: bool = False
    # mode F (files): the uploaded files (from POST /uploads) to ingest as grounding.
    # Each upload carries its own validated license; the file's extracted text is
    # ingested as a corpus, then identical to mode C.
    upload_ids: list[UUID] | None = None
    # mode B (intent): present only for an audit trail when a confirmed target arrives
    # from /compose/resolve-intent; the run uses `target` (the FE confirms it first).
    intent_text: str | None = None
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


async def _resolve_target_present(
    pool: asyncpg.Pool, book_id: UUID, target: ComposeTargetInput
) -> list[str] | None:
    """Decide the ``present_dimensions`` override for a target (#1 dimension picker).

    * Author picked specific dims (``requested_dimensions``) → present = the kind's
      full (profile-localized) set MINUS the requested ids, so the gap builder's
      derived ``missing`` is exactly what the author chose. Accepts ids OR localized
      labels (maps both to the stable id), mirroring ``coverages_from_rows``.
    * Else an existing target with no present supplied → derive from glossary coverage
      (the prior best-effort behavior).
    * Else None → leave the target_dict default (new target enriches all).
    """
    if target.requested_dimensions is not None:
        profile = await get_book_profile(pool, book_id)
        table = resolve_dimensions(
            target.entity_kind, language=profile.language, overrides=profile.dimension_overrides
        )
        ids = {s.dimension for s in table}
        label_to_id = {s.label: s.dimension for s in table}
        requested = {d if d in ids else label_to_id.get(d, d) for d in target.requested_dimensions}
        return [s.dimension for s in table if s.dimension not in requested]
    if target.mode == "existing" and not target.present_dimensions:
        return await _resolve_present_dimensions(pool, book_id, target.canonical_name)
    return None


async def _ingest_context(
    *,
    pool: asyncpg.Pool,
    principal: Principal,
    project_id: UUID,
    book_id: UUID,
    text: str,
    embedding_model_ref: UUID,
    store_license: str,
    persist: bool = False,
) -> list[str]:
    """Ingest the pasted context as a grounding corpus SYNCHRONOUSLY, reusing the C2
    ingest seam (the ``/ground`` handler shape, F6): build the embed seam from a
    KnowledgeClient (BYOK, model_ref — NO model name) and call ``ingest_corpus``. The
    corpus name is content-hashed, so re-pasting identical text is idempotent (no
    duplicate chunks). Returns the corpus_id(s) for the request audit trail. The C2
    grounding composer picks the corpus up by project_id when the job runs — so no
    worker change is needed (spec §1).

    SCOPE (D-COMPOSE-CONTEXT-CORPUS-SCOPE): the corpus is PROJECT-scoped (same as
    every C2 corpus), not run/target-scoped — so a paste also grounds later
    enrichments in the project (similarity-ranking keeps off-target context low).
    That cross-run bleed is by design (a re-paste re-grounds idempotently). To stop
    the corpora ACCUMULATING forever, each compose paste/file ingest is tagged
    ``provenance_json.compose_ephemeral`` so the worker reaper garbage-collects it by
    TTL (``context_corpus_ttl_s``); the curated ``/sources`` library is untagged and
    never reaped. The ingest is idempotent (content-hashed name), and the query is
    re-embedded with the SAME model_ref the request persists, so the corpus vectors
    are comparable at search time (the grounding-alignment invariant)."""
    store = SourceCorpusStore(pool)
    client = KnowledgeClient(
        knowledge_base_url=settings.knowledge_service_url,
        provider_registry_base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
    )

    async def embed_fn(chunk_texts):
        result = await client.embed(
            user_id=principal.user_id, model_source="user_model",
            model_ref=str(embedding_model_ref), texts=list(chunk_texts),
        )
        return result.embeddings

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
    try:
        ingest = await store.ingest_corpus(
            user_id=principal.user_id, project_id=project_id,
            name=f"compose-context:{book_id}:{digest}", kind="other",
            license=store_license, text=text, embed_fn=embed_fn,
            model_ref=str(embedding_model_ref),
            # Tag ephemeral (reaper GCs it by TTL, D-COMPOSE-CONTEXT-CORPUS-SCOPE)
            # UNLESS the author chose to keep it as a curated source (#7, persist).
            provenance_json={"compose_ephemeral": not persist, "source": "compose", "book_id": str(book_id)},
        )
        # Persist is honest even on an idempotent re-ingest: upsert returns an existing
        # (possibly ephemeral) corpus untouched, so explicitly clear the flag (#7).
        if persist:
            await store.mark_corpus_persistent(corpus_id=ingest.corpus_id)
    finally:
        await client.aclose()
    return [str(ingest.corpus_id)]


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
                "(mode B / intent lands in compose slice 4)"
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

    # ── mode C — paste-context ───────────────────────────────────────────────────
    if source == "context":
        ctx_text = (body.context_text or "").strip()
        if not ctx_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="context input requires a non-empty context_text",
            )
        if len(ctx_text) > _MAX_DRAFT_CHARS:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=(
                    f"context_text is too large ({len(ctx_text)} chars > {_MAX_DRAFT_CHARS} cap) "
                    "— trim it or use a file upload (mode F, coming in a later slice)"
                ),
            )
        if body.target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="context input requires a target (existing or new)",
            )
        if body.embedding_model_ref is None:
            # The pasted text is chunked + embedded into a grounding corpus, so an
            # embedding model is required (unlike mode D, which does no retrieval).
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="context input requires embedding_model_ref (the text is embedded as grounding)",
            )
        # License default-deny: refuse copyrighted / unrecognised before any ingest.
        store_license = resolve_asserted_license(body.context_license)
        if store_license is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    "context_license must be one of public_domain | licensed | owned — "
                    "copyrighted material cannot be ingested (you must own, license, or "
                    "use public-domain text)"
                ),
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
        # Ingest the pasted text as a grounding corpus (synchronous). 502/503 mirror
        # the /ground handler so an embed outage is a clear upstream error, not a 500.
        try:
            corpus_ids = await _ingest_context(
                pool=pool,
                principal=principal,
                project_id=project_id,
                book_id=body.book_id,
                text=ctx_text,
                embedding_model_ref=body.embedding_model_ref,
                store_license=store_license,
                persist=body.persist_corpus,
            )
        except KnowledgeServiceError as exc:
            code = (
                status.HTTP_503_SERVICE_UNAVAILABLE
                if exc.retryable
                else status.HTTP_502_BAD_GATEWAY
            )
            raise HTTPException(status_code=code, detail=f"context embedding failed: {exc}")
        target_dict = _target_dict(body.target)
        # Present dims: an explicit dimension pick (#1) → enrich exactly those; else
        # (existing, no pick) derive from coverage so we fill only the missing ones.
        present = await _resolve_target_present(pool, body.book_id, body.target)
        if present is not None:
            target_dict["present_dimensions"] = present
        return await _create_and_enqueue(
            pool=pool,
            project_id=project_id,
            user_id=user_id,
            body=body,
            technique=technique.value,
            entity_kind=body.target.entity_kind,
            targets=[target_dict],
            extra_request={"context_corpus_ids": corpus_ids, "context_license": store_license},
        )

    # ── mode F — attach files ────────────────────────────────────────────────────
    if source == "files":
        if not body.upload_ids:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="files input requires upload_ids (from POST /uploads)",
            )
        if body.target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="files input requires a target (existing or new)",
            )
        if body.embedding_model_ref is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="files input requires embedding_model_ref (extracted text is embedded as grounding)",
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
        # Ingest each ready upload's extracted text as a grounding corpus (each file
        # carries its own license, validated + stored admissible at upload time).
        corpus_ids: list[str] = []
        for uid in body.upload_ids:
            up = await fetch_upload(pool, principal.user_id, uid)
            if up is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"upload {uid} not found")
            if up["status"] != "ready":
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"upload {uid} is not ready (status={up['status']}) — poll until ready",
                )
            text = (up["extracted_text"] or "").strip()
            if not text:
                continue  # an empty extraction (e.g. a blank scan) grounds nothing — skip
            try:
                ids = await _ingest_context(
                    pool=pool, principal=principal, project_id=project_id, book_id=body.book_id,
                    text=text, embedding_model_ref=body.embedding_model_ref,
                    store_license=up["license_asserted"], persist=body.persist_corpus,
                )
            except KnowledgeServiceError as exc:
                code = (
                    status.HTTP_503_SERVICE_UNAVAILABLE if exc.retryable else status.HTTP_502_BAD_GATEWAY
                )
                raise HTTPException(status_code=code, detail=f"file embedding failed: {exc}")
            corpus_ids.extend(ids)
        if not corpus_ids:
            raise HTTPException(
                status_code=422,
                detail="the uploaded files had no extractable text to ground on",
            )
        target_dict = _target_dict(body.target)
        present = await _resolve_target_present(pool, body.book_id, body.target)
        if present is not None:
            target_dict["present_dimensions"] = present
        return await _create_and_enqueue(
            pool=pool,
            project_id=project_id,
            user_id=user_id,
            body=body,
            technique=technique.value,
            entity_kind=body.target.entity_kind,
            targets=[target_dict],
            extra_request={
                "context_corpus_ids": corpus_ids,
                "upload_ids": [str(u) for u in body.upload_ids],
            },
        )

    # ── mode B — intent (the body arrives with a CONFIRMED target from resolve-intent) ──
    if source == "intent":
        if body.target is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="intent input requires a confirmed target — call /compose/resolve-intent first",
            )
        try:
            technique = Technique(body.technique or Technique.FABRICATION.value)
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
        # retrieval grounds on a corpus → needs an embed model; fabrication doesn't.
        if technique is Technique.RETRIEVAL and body.embedding_model_ref is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="intent input with technique=retrieval requires embedding_model_ref",
            )
        target_dict = _target_dict(body.target)
        present = await _resolve_target_present(pool, body.book_id, body.target)
        if present is not None:
            target_dict["present_dimensions"] = present
        return await _create_and_enqueue(
            pool=pool,
            project_id=project_id,
            user_id=user_id,
            body=body,
            technique=technique.value,
            entity_kind=body.target.entity_kind,
            targets=[target_dict],
            # Persist the original intent for the audit trail (review-impl #1 — the
            # FE sends it as audit; the run uses the confirmed target, not this).
            extra_request={"intent_resolved": True, "intent_text": body.intent_text},
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


class ResolveIntentBody(BaseModel):
    book_id: UUID
    intent_text: str = Field(min_length=1)
    generation_model_ref: UUID


@router.post("/{project_id}/compose/resolve-intent", status_code=status.HTTP_202_ACCEPTED)
async def compose_resolve_intent(
    project_id: UUID,
    body: ResolveIntentBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Mode B step 1 (F5): resolve a free-text intent → a PROPOSED target + dimensions
    + technique + rationale via ONE LLM call.

    Phase 3 M2 — OFF the request path: creates a 'pending' compose task + enqueues a
    resume-stream trigger, returns 202 + task_id. The resume worker runs the resolver
    (model by BYOK model_ref); GET /v1/lore-enrichment/compose-tasks/{task_id} polls.
    The FE shows the resolved result, lets the author edit/confirm, then POSTs a normal
    /compose with input_source='intent' + the confirmed target — so a mis-resolved
    target is never silently enriched. Unmetered (one resolver call, no cost cap)."""
    if principal.user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required")

    task_id = await create_compose_task(
        pool,
        kind="intent_resolve",
        user_id=str(principal.user_id),
        project_id=str(project_id),
        book_id=str(body.book_id),
        request={
            "user_id": str(principal.user_id),
            "project_id": str(project_id),
            "book_id": str(body.book_id),
            "intent_text": body.intent_text,
            "generation_model_ref": str(body.generation_model_ref),
        },
    )
    enqueued = await enqueue_compose_task(
        task_id=task_id, kind="intent_resolve",
        user_id=str(principal.user_id), project_id=str(project_id),
    )
    return {"task_id": task_id, "status": "pending",
            "enqueued": "ok" if enqueued else "retriggerable"}
