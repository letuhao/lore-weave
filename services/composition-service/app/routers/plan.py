"""A3 decompose-planner router (§5 / Phase-A A3).

Two endpoints, composition-only, preview→commit (the controlled-auto human gate):

  POST /works/{project_id}/outline/decompose        — run the planner, return the
                                                       proposed arc→chapter→scene
                                                       tree WITHOUT persisting.
  POST /works/{project_id}/outline/decompose/commit  — persist the accepted (and
                                                       possibly author-edited) tree.

decompose maps a structure template's beats onto the book's EXISTING chapters and
LLM-decomposes each into scenes with tension + cast; it NEVER mints book chapters
(commit reuses the existing `chapter_id`s). See engine/plan.py for the planner.
"""

from __future__ import annotations

import dataclasses
import logging
from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.db.repositories import AlreadyPlannedError, ReferenceViolationError
from app.clients.kal_client import KalClient, RosterIncomplete
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.pool import get_pool
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_generation_jobs_repo, get_kal_client_dep,
    get_llm_client_dep, get_outline_repo, get_structure_templates_repo, get_works_repo,
)
from app.engine.motif_select import (
    MotifBinding, MotifSwapError, SelectedMotif, apply_motif_swap,
    bind_motif, undo_motif_swap,
)
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE
from app.engine.plan import ChapterPlan, decompose
from app.engine.arc_apply import build_apply_plan
from app.engine.arc_materialize import build_materialize_spec
from app.db.models import ArcApplyArgs
from app.db.repositories.arc_template_repo import ArcTemplateRepo
from app.db.repositories.motif_repo import MotifRepo
from app.deps import get_arc_template_repo, get_grant_client_dep, get_motif_repo
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from app.engine.heal_canon import convention_for, render_canon
from app.engine.prose_doc import tiptap_doc_to_text
from app.packer.profile import from_settings
from app.worker.events import enqueue_job
from fastapi import status as http_status

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition")


class DecomposeRequest(BaseModel):
    structure_template_id: UUID
    premise: str = Field(min_length=1, max_length=4000)
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    # W2 motif select+bind. Default OFF in P1 (MD-7) — the eval-gate compares arms
    # cleanly and A3's default behavior is unchanged until A≥B is proven. Genres for
    # retrieval come from the book object; language from the work's source profile.
    motifs_enabled: bool = False
    # Phase-0 slice-2 — cross-chapter sequential threading. Default OFF ⇒ today's
    # concurrent per-chapter decompose. ON ⇒ chapters are decomposed in order, each
    # conditioned on the prior chapters' typed exit-state so they don't repeat the arc.
    thread_state: bool = False
    # Planning-pipeline — when true, run the multi-step planner (cast → motifs → tension →
    # char-arcs/intros → grounded decompose → plan self-heal) instead of the one-shot
    # decompose. Default OFF (opt-in rollout). Long-running ⇒ always via the worker when
    # COMPOSITION_WORKER_ENABLED. NOTE: this SEEDS the proposed cast into the glossary.
    pipeline: bool = False


class CommitScene(BaseModel):
    title: str = ""
    synopsis: str = Field(default="", max_length=4000)
    # 0..100 (the outline_node.tension convention) — bounded here so an
    # author-edited commit can't overflow the SMALLINT column into a 500.
    tension: int | None = Field(default=None, ge=0, le=100)
    present_entity_ids: list[UUID] = []


class CommitMotifApplication(BaseModel):
    # one entry per bound scene (positional with the chapter's scenes); echoed from
    # the preview's per-chapter motif.application_rows. owner/book/project are NEVER
    # client fields (the router stamps them) — the binder ledger is server-scoped.
    motif_id: UUID
    motif_version: int | None = None
    role_bindings: dict = {}
    annotations: dict = {}


class CommitChapter(BaseModel):
    chapter_id: UUID
    title: str = ""
    intent: str = ""
    beat_role: str | None = None
    scenes: list[CommitScene] = []
    # W2 — the motif binding ledger for THIS chapter's scenes (positional with
    # `scenes`). Empty on an invented/unbound chapter (back-compat: omitted by old
    # callers). Persisted as motif_application rows after the tree commits.
    motif_application_rows: list[CommitMotifApplication] = []


class CommitRequest(BaseModel):
    arc_title: str = "Arc"
    chapters: list[CommitChapter] = Field(min_length=1)
    # `replace=true` archives the target chapters' EXISTING scenes (a true replace
    # — D-A3-COMMIT-TRUE-REPLACE), scoped to ONLY those chapters; default false =
    # refuse to double-plan (409 CHAPTER_ALREADY_PLANNED). `force` kept as a
    # deprecated alias for back-compat (old callers); `replace` wins if both set.
    replace: bool = False
    force: bool = False
    # Client idempotency key — a double-submit / retry with the same key replays
    # the original commit instead of persisting a second tree (exactly-once,
    # D-A3-COMMIT-IDEMPOTENCY). Optional (older callers omit it).
    idempotency_key: str | None = None


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
    need: GrantLevel = GrantLevel.EDIT,
):
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8: access is decided HERE, never in the
    repos). Default EDIT — every planner route below mutates the spec tree or
    spends LLM via a generation_job; the one read (motif-bindings) passes VIEW.
    none→404 (no oracle), under-tier→403."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    return work


async def _book_chapter_ids(book: BookClient, book_id: UUID, bearer: str) -> list[dict]:
    """Active chapters for the book, or 502 if book-service can't be reached (the
    IDOR/validation guards depend on this list — never silently skip it)."""
    try:
        return await book.list_chapters(book_id, bearer)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE",
                                                     "detail": str(exc)}) from exc


async def _cast_roster(
    kal: KalClient, book_id: UUID, user_id: UUID, *, strict: bool = False
) -> list[dict]:
    """The book's full cast as `{entity_id, name}`, read through the KAL (INV-KAL).

    Drains the KAL `roster` keyset cursor to completion (D4 / §12.5.2): the prior
    glossary `list_entities` path read only the first page and ignored `next_cursor`,
    silently truncating the cast at ~100 — so a deep book's planner saw an incomplete
    roster. The KAL roster is bounded-per-page, COMPLETE-in-aggregate; the client
    follows `next_cursor` until null.

    Default (non-strict): empty/partial on outage (the packer just gets a thin/no roster).
    `strict=True` raises `RosterIncomplete` on a truncated drain so a caller that treats the
    cast as AUTHORITATIVE (commit-time entity validation) can skip instead of false-rejecting
    a valid id in a dropped page. `user_id` is forwarded as the KAL tenancy identity."""
    return await kal.roster(book_id, user_id=user_id, strict=strict)


class SelfHealProposeRequest(BaseModel):
    chapter_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    # Optional canon override — a caller (e.g. the planner) can pass the PipelineResult.canon
    # bible directly; otherwise the endpoint best-effort renders it from the cast roster +
    # a genre/language convention (the dominant xưng-hô grounding).
    canon: str | None = Field(default=None, max_length=20000)
    prefilter: bool = True
    # OPT-IN comparative re-ranker — one extra LLM call per semantic edit to pre-check the ones
    # it approves (it never drops). Default OFF (cost); the FE exposes a toggle.
    rerank: bool = False


@router.post("/works/{project_id}/self-heal/propose")
async def self_heal_propose_endpoint(
    project_id: UUID,
    body: SelfHealProposeRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """M6 Polish — PROPOSE self-heal edits for a chapter draft (the review-gate). Resolves the
    draft text (Tiptap→prose) + a canon (override via `body.canon`, else best-effort from the
    cast roster + genre/language convention), runs the cheap-stack in PROPOSE mode, and returns
    EditProposals — NOT applied. The human accepts a subset; the accepted edits are spliced +
    saved by the caller (composition_write_prose). Worker when enabled (202 + job_id), else
    inline. Never auto-writes (do-no-harm: the imperfect pass is gated by the human)."""
    work = await _require_work(works, grant, user_id, project_id)
    try:
        draft = await book.get_draft(work.book_id, body.chapter_id, bearer)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE",
                                                     "detail": str(exc)}) from exc
    text = tiptap_doc_to_text(draft.get("body") or draft.get("doc") or draft.get("content"))
    if not text.strip():
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_DRAFT", "detail": "chapter draft has no prose to heal"})

    profile = from_settings(work.settings)
    canon = body.canon
    if not canon:
        genre_tags = await _book_genre_tags(book, work.book_id, bearer)
        roster = await _cast_roster(kal, work.book_id, user_id)
        canon = render_canon(roster, convention=convention_for(genre_tags, profile.source_language))

    heal_input = {
        "worker_op": "self_heal_propose", "chapter_text": text, "canon": canon,
        "chapter_id": str(body.chapter_id), "draft_version": draft.get("draft_version"),
        "book_id": str(work.book_id), "project_id": str(project_id),
        "model_source": str(body.model_source), "model_ref": str(body.model_ref),
        "source_language": profile.source_language,
        "prefilter": body.prefilter, "rerank": body.rerank,
    }
    if settings.composition_worker_enabled:
        jobs = await get_generation_jobs_repo()
        job, _created = await jobs.create(
            project_id, created_by=user_id, operation="self_heal_propose", mode="auto",
            status="pending", input=heal_input)
        enqueued = await enqueue_job(settings.redis_url, job_id=str(job.id),
                                     user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "enqueued": "ok" if enqueued else "retriggerable"})
    # inline (worker-off / tests) — blocks for the full propose pass.
    from app.worker.operations import run_self_heal_propose
    return await run_self_heal_propose(llm, user_id=str(user_id), input=heal_input)


class QualityReportRequest(BaseModel):
    chapter_id: UUID
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)
    # Optional canon override (same as self-heal) — grounds the critic's canon dimension.
    canon: str | None = Field(default=None, max_length=20000)


@router.post("/works/{project_id}/quality-report")
async def quality_report_endpoint(
    project_id: UUID,
    body: QualityReportRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Q1+Q2 Quality Report — surface the planner's advisory judges for a chapter draft as a
    READ-ONLY report (M6 Polish gate). Resolves the draft text (Tiptap→prose) + a canon (override
    else best-effort from the cast roster), then runs the 4-dim critic + the promise audit. Unlike
    self-heal this produces NO applyable edits — it is diagnostic (the author reads it and decides).
    Worker when enabled (202 + job_id), else inline."""
    work = await _require_work(works, grant, user_id, project_id)
    try:
        draft = await book.get_draft(work.book_id, body.chapter_id, bearer)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE",
                                                     "detail": str(exc)}) from exc
    text = tiptap_doc_to_text(draft.get("body") or draft.get("doc") or draft.get("content"))
    if not text.strip():
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_DRAFT", "detail": "chapter draft has no prose to analyze"})

    profile = from_settings(work.settings)
    canon = body.canon
    if not canon:
        genre_tags = await _book_genre_tags(book, work.book_id, bearer)
        roster = await _cast_roster(kal, work.book_id, user_id)
        canon = render_canon(roster, convention=convention_for(genre_tags, profile.source_language))

    qr_input = {
        "worker_op": "quality_report", "chapter_text": text, "canon": canon,
        "chapter_id": str(body.chapter_id), "draft_version": draft.get("draft_version"),
        "book_id": str(work.book_id), "project_id": str(project_id),
        "model_source": str(body.model_source), "model_ref": str(body.model_ref),
        "source_language": profile.source_language,
    }
    if settings.composition_worker_enabled:
        jobs = await get_generation_jobs_repo()
        job, _created = await jobs.create(
            project_id, created_by=user_id, operation="quality_report", mode="auto",
            status="pending", input=qr_input)
        enqueued = await enqueue_job(settings.redis_url, job_id=str(job.id),
                                     user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "enqueued": "ok" if enqueued else "retriggerable"})
    # inline (worker-off / tests)
    from app.worker.operations import run_quality_report
    return await run_quality_report(llm, user_id=str(user_id), input=qr_input)


def _render_outline_plan(nodes: list[Any]) -> str:
    """Render the outline tree into a compact plan_text — the SPEC the promise set is
    derived from: each chapter header followed by ITS scenes, in reading order.

    `list_tree` returns a FLAT list ordered by (parent_id, rank), so the scene groups
    are ordered by their parent chapter's UUID — NOT reading order. Iterating the flat
    list would emit every chapter header first, then scene clusters in arbitrary order,
    detached from their chapters. So we WALK the tree (arc → chapters → scenes) via a
    parent→children map; children within a parent stay rank-ordered (list_tree's order),
    which is the correct sibling order."""
    by_parent: dict[Any, list[Any]] = {}
    for n in nodes:
        by_parent.setdefault(n.parent_id, []).append(n)
    lines: list[str] = []

    def walk(parent_id: Any) -> None:
        for n in by_parent.get(parent_id, []):
            if n.kind == "chapter":
                head = (n.title or "").strip() or "(chapter)"
                if n.beat_role:
                    head += f" [{n.beat_role}]"
                if (n.goal or "").strip():
                    head += f": {n.goal.strip()}"
                lines.append(f"## {head}")
            elif n.kind == "scene":
                body = (n.synopsis or "").strip() or (n.title or "").strip()
                if body:
                    lines.append(f"- {body}")
            walk(n.id)  # descend: arc → chapters, chapter → scenes (tree order)

    walk(None)
    return "\n".join(lines)


class PromiseCoverageRequest(BaseModel):
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)


@router.post("/works/{project_id}/promise-coverage")
async def promise_coverage_endpoint(
    project_id: UUID,
    body: PromiseCoverageRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    llm: LLMClient = Depends(get_llm_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Q3 Book-level promise coverage — does the finished book pay off what the outline
    promised? Renders the outline tree as the plan spec, assembles every ACTIVE chapter's
    prose, derives a STABLE tracked-promise set from the spec, and scores the book against it
    (paid/progressing/abandoned/absent + rates). READ-ONLY (book-scoped; no per-chapter edits).
    Worker when enabled (202 + job_id), else inline."""
    work = await _require_work(works, grant, user_id, project_id)
    nodes = await outline.list_tree(project_id)
    plan_text = _render_outline_plan(nodes)

    # Assemble every active chapter's prose in reading order (skip empty/failed — degrade).
    chapters = await _book_chapter_ids(book, work.book_id, bearer)
    parts: list[str] = []
    n_ok = 0
    for ch in chapters:
        cid = ch.get("chapter_id")
        if not cid:
            continue
        try:
            draft = await book.get_draft(work.book_id, UUID(str(cid)), bearer)
        except BookClientError:
            continue
        txt = tiptap_doc_to_text(draft.get("body") or draft.get("doc") or draft.get("content"))
        if txt.strip():
            parts.append(txt.strip())
            n_ok += 1
    book_text = "\n\n".join(parts)
    if not book_text.strip():
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_BOOK", "detail": "no chapter prose to analyze"})

    profile = from_settings(work.settings)
    cov_input = {
        "worker_op": "promise_coverage", "premise": "", "plan_text": plan_text,
        "book_text": book_text, "chapters": n_ok,
        "book_id": str(work.book_id), "project_id": str(project_id),
        "model_source": str(body.model_source), "model_ref": str(body.model_ref),
        "source_language": profile.source_language,
    }
    if settings.composition_worker_enabled:
        jobs = await get_generation_jobs_repo()
        job, _created = await jobs.create(
            project_id, created_by=user_id, operation="promise_coverage", mode="auto",
            status="pending", input=cov_input)
        enqueued = await enqueue_job(settings.redis_url, job_id=str(job.id),
                                     user_id=str(user_id), project_id=str(project_id))
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "enqueued": "ok" if enqueued else "retriggerable"})
    # inline (worker-off / tests)
    from app.worker.operations import run_promise_coverage
    return await run_promise_coverage(llm, user_id=str(user_id), input=cov_input)


def _decompose_response(result) -> dict:
    """Serialize a DecomposeResult for the preview. Plain dataclasses.asdict can't
    serialize the SelectedMotif/MotifBinding (they hold a Pydantic Motif), so the
    motif fields are folded in explicitly: per bound chapter we surface
    motif_id/motif_name/role_bindings/match_reason/source + the application_rows the
    commit will persist; plus the book-level motif_coverage + the post-bind diverge
    budget (the cost the author sees before a /generate auto)."""
    from app.engine.motif_select import estimate_diverge_budget

    out = {
        "arc_title": result.arc_title,
        "unmapped_beats": list(result.unmapped_beats),
        "motif_coverage": result.motif_coverage,
        "diverge_budget": estimate_diverge_budget(result.chapters),
        "chapters": [],
    }
    for cs in result.chapters:
        ch: dict = {
            "chapter": dataclasses.asdict(cs.chapter),
            "scenes": [dataclasses.asdict(s) for s in cs.scenes],
            "warning": cs.warning,
            "motif": None,
            # Phase-0 slice-2 — surface the threaded exit-state so the inline preview
            # matches the worker path's asdict shape (None when threading is off).
            "exit_state": dataclasses.asdict(cs.exit_state) if cs.exit_state else None,
        }
        if cs.motif is not None:
            sel: SelectedMotif = cs.motif
            binding: MotifBinding = cs.binding
            ch["motif"] = {
                "motif_id": str(sel.motif.id),
                "motif_name": sel.motif.name,
                "motif_source": sel.motif.source,
                "score": sel.score,
                "match_reason": sel.match_reason,
                "role_bindings": binding.role_bindings,
                "unresolved_roles": binding.unresolved_roles,
                "application_rows": cs.application_rows,
            }
        out["chapters"].append(ch)
    return out


async def _book_genre_tags(book: BookClient, book_id: UUID, bearer: str) -> list[str]:
    """The book's genre tags for motif retrieval (best-effort — an empty list just
    means the retriever's genre ∩ pre-filter matches nothing, so no motif binds; the
    planner degrades to invent cleanly). Reads the `genres`/`genre_tags` field off the
    book object if present."""
    try:
        b = await book.get_book(book_id, bearer)
    except BookClientError:
        return []
    if not b:
        return []
    raw = b.get("genres") or b.get("genre_tags") or []
    return [str(g) for g in raw if isinstance(g, (str,)) and g.strip()]


@router.post("/works/{project_id}/outline/decompose")
async def decompose_preview(
    project_id: UUID,
    body: DecomposeRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Run the planner; return the proposed tree (NOT persisted).

    Phase 3 M4 — when COMPOSITION_WORKER_ENABLED, the bearer-authenticated context
    (book chapters, cast) is resolved HERE, persisted in the job's input, and the
    LLM compute runs OFF the request path: returns 202 + job_id; GET /jobs/{id}
    polls for the proposed tree. Default (flag off) → inline behavior verbatim."""
    work = await _require_work(works, grant, user_id, project_id)
    tmpl = await templates.get(user_id, body.structure_template_id)
    if tmpl is None:
        raise HTTPException(status_code=404, detail="structure template not found")

    chapters_raw = await _book_chapter_ids(book, work.book_id, bearer)
    if not chapters_raw:
        raise HTTPException(status_code=400, detail={
            "code": "NO_CHAPTERS",
            "detail": "decompose maps onto existing chapters — create chapters first"})
    if len(chapters_raw) > settings.plan_max_chapters:
        raise HTTPException(status_code=400, detail={
            "code": "TOO_MANY_CHAPTERS", "count": len(chapters_raw),
            "max": settings.plan_max_chapters})

    cast = await _cast_roster(kal, work.book_id, user_id)
    profile = from_settings(work.settings)
    chapters_in = [
        ChapterPlan(chapter_id=str(c["chapter_id"]), title=c["title"],
                    sort_order=c["sort_order"], beat_role=None, intent="")
        for c in chapters_raw
    ]

    # ── Planning pipeline (multi-step) — opt-in via `pipeline=true`. Long-running ⇒ worker
    # when enabled (202 + job_id); else inline (tests / worker-off). Seeds the cast glossary.
    if body.pipeline:
        genre_tags = await _book_genre_tags(book, work.book_id, bearer)
        pipe_input = {
            "model_source": str(body.model_source), "model_ref": str(body.model_ref),
            "worker_op": "plan_pipeline", "premise": body.premise, "beats": tmpl.beats,
            "chapters": [dataclasses.asdict(c) for c in chapters_in],
            "genre_tags": genre_tags, "book_id": str(work.book_id), "project_id": str(project_id),
            "k_ceiling": settings.compose_diverge_k,
            "high_threshold": settings.plan_high_tension_threshold,
            "min_scenes": settings.plan_min_scenes_per_chapter,
            "max_scenes": settings.plan_max_scenes_per_chapter,
            "source_language": profile.source_language, "self_heal": True,
        }
        if settings.composition_worker_enabled:
            jobs = await get_generation_jobs_repo()
            job, _created = await jobs.create(
                project_id, created_by=user_id, operation="plan_pipeline", mode="auto",
                status="pending", input=pipe_input)
            enqueued = await enqueue_job(
                settings.redis_url, job_id=str(job.id),
                user_id=str(user_id), project_id=str(project_id))
            return JSONResponse(
                status_code=http_status.HTTP_202_ACCEPTED,
                content={"job_id": str(job.id), "status": "pending",
                         "enqueued": "ok" if enqueued else "retriggerable"})
        # inline (worker-off / tests) — blocks for the full pipeline.
        from app.clients.glossary_client import get_glossary_client
        from app.engine.planning_pipeline import run_planning_pipeline
        res = await run_planning_pipeline(
            llm, MotifRetriever(get_pool()), get_glossary_client(), kal,
            user_id=str(user_id), book_id=work.book_id, project_id=project_id,
            premise=body.premise, beats=tmpl.beats, chapters=chapters_in, genre_tags=genre_tags,
            model_source=body.model_source, model_ref=body.model_ref,
            k_ceiling=settings.compose_diverge_k, high_threshold=settings.plan_high_tension_threshold,
            min_scenes=settings.plan_min_scenes_per_chapter,
            max_scenes=settings.plan_max_scenes_per_chapter,
            source_language=profile.source_language, self_heal=True)
        return JSONResponse(content=dataclasses.asdict(res))

    # W2 motif select+bind context (only resolved when the toggle is on — default
    # OFF in P1, so the inline/worker paths are byte-identical to today when off).
    motif_genres: list[str] = []
    motif_applied_counts: dict[str, int] = {}
    if body.motifs_enabled:
        motif_genres = await _book_genre_tags(book, work.book_id, bearer)
        motif_applied_counts = await MotifApplicationRepo(get_pool()).count_by_motif_for_book(
            work.book_id,
        )

    if settings.composition_worker_enabled:
        # Persist the FULLY-RESOLVED decompose args (the worker has no bearer to
        # re-fetch book/cast) → enqueue → 202. GET /jobs/{id} polls result.
        # The repo is built lazily HERE (not a top-level Depends) so the default
        # inline path never touches the pool — keeps the flag-off contract + tests
        # unchanged.
        jobs = await get_generation_jobs_repo()
        job_input = {
            "model_source": str(body.model_source),
            "model_ref": str(body.model_ref),
            "worker_op": "decompose_preview",
            "premise": body.premise,
            "arc_title": tmpl.name,
            "beats": tmpl.beats,
            "chapters": [dataclasses.asdict(c) for c in chapters_in],
            "cast": cast,
            "k_ceiling": settings.compose_diverge_k,
            "high_threshold": settings.plan_high_tension_threshold,
            "min_scenes": settings.plan_min_scenes_per_chapter,
            "max_scenes": settings.plan_max_scenes_per_chapter,
            "source_language": profile.source_language,
            "thread_state": body.thread_state,  # Phase-0 slice-2 (worker reads via input.get)
            # W2 — persisted so the worker can bind motifs off-request once
            # operations.run_decompose is wired (worker-path motif binding is a
            # cross-track follow-up; default-OFF in P1 means the worker ignores these
            # until then). book_id/project_id let the worker resolve the retriever.
            "motifs_enabled": body.motifs_enabled,
            "motif_genre_tags": motif_genres,
            "book_id": str(work.book_id),
        }
        job, _created = await jobs.create(
            project_id, created_by=user_id, operation="decompose_preview",
            mode="auto", status="pending", input=job_input,
        )
        enqueued = await enqueue_job(
            settings.redis_url, job_id=str(job.id),
            user_id=str(user_id), project_id=str(project_id),
        )
        return JSONResponse(
            status_code=http_status.HTTP_202_ACCEPTED,
            content={"job_id": str(job.id), "status": "pending",
                     "enqueued": "ok" if enqueued else "retriggerable"},
        )

    result = await decompose(
        llm, user_id=str(user_id), model_source=body.model_source, model_ref=body.model_ref,
        premise=body.premise, arc_title=tmpl.name, beats=tmpl.beats,
        chapters=chapters_in, cast=cast,
        k_ceiling=settings.compose_diverge_k, high_threshold=settings.plan_high_tension_threshold,
        min_scenes=settings.plan_min_scenes_per_chapter,
        max_scenes=settings.plan_max_scenes_per_chapter,
        source_language=profile.source_language,
        thread_state=body.thread_state,
        motifs_enabled=body.motifs_enabled,
        retriever=MotifRetriever(get_pool()) if body.motifs_enabled else None,
        book_id=work.book_id if body.motifs_enabled else None,
        project_id=project_id if body.motifs_enabled else None,
        genre_tags=motif_genres,
        motif_min_score=settings.motif_min_score,
        motif_max_reapply=settings.motif_max_reapply,
        motif_connective_floor_margin=settings.motif_connective_floor_margin,
        motif_applied_counts=motif_applied_counts,
    )
    return _decompose_response(result)


@router.post("/works/{project_id}/outline/decompose/commit", status_code=201)
async def decompose_commit(
    project_id: UUID,
    body: CommitRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Persist the accepted tree (arc→chapter→scene) atomically. Validates every
    chapter_id belongs to the book (IDOR) + every present_entity_id is a real
    glossary id; refuses to re-plan a chapter that already has scenes unless
    `replace=true`."""
    work = await _require_work(works, grant, user_id, project_id)
    req_chapter_ids = [ch.chapter_id for ch in body.chapters]

    # IDOR: every committed chapter_id must be one of THIS book's chapters
    # (list_chapters is JWT-scoped → only the user's book). 502 if unverifiable.
    # Also keep each chapter's reading-order sort_order to assign scene story_order.
    book_chapters = await _book_chapter_ids(book, work.book_id, bearer)
    sort_by_chapter = {str(c["chapter_id"]): (c.get("sort_order") or 0) for c in book_chapters}
    bad = [str(cid) for cid in req_chapter_ids if str(cid) not in sort_by_chapter]
    if bad:
        raise HTTPException(status_code=400, detail={"code": "BAD_CHAPTER", "chapter_ids": bad})

    # Robustness (LOOM-73): refuse to commit an ALL-EMPTY plan — a decompose that
    # produced no scenes for ANY (valid) chapter, i.e. the planner LLM degraded
    # (the pre-LOOM-71 reasoning_effort 400, or any future model/parse failure).
    # Without this guard the empty commit succeeds silently and the author hits a
    # mysterious NO_CHAPTER_PLAN only later at generate-time. Fail fast with an
    # actionable code (the per-chapter `warning`s in the preview say WHY). Placed
    # AFTER the IDOR check so a bad-chapter body still reports BAD_CHAPTER first.
    if not any(ch.scenes for ch in body.chapters):
        raise HTTPException(status_code=400, detail={
            "code": "EMPTY_DECOMPOSE_PLAN",
            "detail": "the plan has no scenes for any chapter — the planner likely "
                      "degraded (try again, or use a different model). Nothing was committed."})

    # present_entity validation against the glossary cast. Best-effort: on a glossary outage
    # OR an INCOMPLETE drain we SKIP rather than false-reject valid ids (present_entity_ids are
    # non-FK, packer-tolerant). strict=True ⇒ a truncated cast raises RosterIncomplete, so we
    # only validate against a COMPLETE cast — never against a partial set that would 400 a valid
    # entity whose roster page failed to load.
    try:
        cast = await _cast_roster(kal, work.book_id, user_id, strict=True)
    except RosterIncomplete as exc:
        logger.warning("cast roster incomplete (%s) — skipping present_entity validation", exc)
        cast = []
    if cast:
        cast_ids = {c["entity_id"] for c in cast}
        bad_ents = sorted({
            str(eid) for ch in body.chapters for sc in ch.scenes
            for eid in sc.present_entity_ids if str(eid) not in cast_ids
        })
        if bad_ents:
            raise HTTPException(status_code=400, detail={"code": "BAD_ENTITY", "entity_ids": bad_ents})

    # The already-planned guard now runs INSIDE commit_decomposed_tree's
    # transaction (closes the TOCTOU race a pre-Tx check left open). `replace=true`
    # archives the target chapters' existing scenes; an idempotency_key dedups a
    # double-submit. `force` is the deprecated alias for `replace`.

    # Assign each scene a reading-order story_order = chapter.sort_order*STRIDE + idx.
    # This is the position axis the packer + S1 state-reinjection key on (prior =
    # lower story_order); WITHOUT it scenes are story_order=None and both the
    # spoiler-windowed lenses AND S1's prior-scene fallback no-op. Chapter-major,
    # scene-minor, stable + collision-free (≤STRIDE scenes/chapter). The stride is
    # shared with B2 chapter-mode (build_chapter_pack_node) so the two never drift.
    spec = [{
        "chapter_id": ch.chapter_id, "title": ch.title, "intent": ch.intent,
        "beat_role": ch.beat_role,
        # The CHAPTER's own position on the same axis (= its scene 0). It was missing, so every
        # persisted chapter node carried story_order NULL — see _insert_decomposed_tree.
        "story_order": sort_by_chapter[str(ch.chapter_id)] * STORY_ORDER_CHAPTER_STRIDE,
        "scenes": [{"title": sc.title, "synopsis": sc.synopsis, "tension": sc.tension,
                    "present_entity_ids": sc.present_entity_ids,
                    "story_order": sort_by_chapter[str(ch.chapter_id)] * STORY_ORDER_CHAPTER_STRIDE + i}
                   for i, sc in enumerate(ch.scenes)],
    } for ch in body.chapters]
    try:
        created = await outline.commit_decomposed_tree(
            project_id, book_id=work.book_id, created_by=user_id, arc_title=body.arc_title,
            chapters=spec, replace=body.replace or body.force, idempotency_key=body.idempotency_key,
        )
    except AlreadyPlannedError as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CHAPTER_ALREADY_PLANNED",
            "chapter_ids": sorted(str(c) for c in exc.chapter_ids),
            "detail": "chapters already have scenes — resend with replace=true to "
                      "archive the existing scenes and replace them"}) from exc
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400,
                            detail={"code": "BAD_REFERENCE", "detail": exc.message}) from exc
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(status_code=400,
                            detail={"code": "CONSTRAINT", "detail": str(exc)}) from exc

    # W2 — persist the motif_application binding ledger (one row per bound scene).
    # The created scene_ids are flat, chapter-major + within-chapter ordered (the
    # same order as `spec`), so we map each chapter's application rows positionally to
    # its scene nodes. Skipped on an idempotency replay (the prior commit already
    # wrote them). NOT atomic with the tree Tx — commit_decomposed_tree owns + closes
    # its own Tx (an A3-track file we don't edit); a failure here leaves a planned
    # tree with no ledger rows (degraded, re-runnable), never a corrupt tree. (The
    # "atomic with the tree" ideal needs an outline.py change → F0/A3 follow-up.)
    applied = 0
    if not created.get("replay") and any(ch.motif_application_rows for ch in body.chapters):
        flat_scene_ids = [UUID(s) for s in created["scene_ids"]]
        ledger_rows: list[dict] = []
        cursor = 0
        for ch in body.chapters:
            n = len(ch.scenes)
            chapter_scene_ids = flat_scene_ids[cursor:cursor + n]
            cursor += n
            for app, node_id in zip(ch.motif_application_rows, chapter_scene_ids):
                ledger_rows.append({
                    "motif_id": str(app.motif_id),
                    "motif_version": app.motif_version,
                    "outline_node_id": str(node_id),
                    "role_bindings": app.role_bindings,
                    "annotations": app.annotations,
                })
        if ledger_rows:
            try:
                await MotifApplicationRepo(get_pool()).insert_many(
                    project_id, work.book_id, ledger_rows, created_by=user_id,
                )
                applied = len(ledger_rows)
            except asyncpg.ForeignKeyViolationError:
                # a motif_id that no longer exists (archived/deleted between preview
                # and commit) — the tree is committed + valid; the binding ledger is
                # advisory, so we surface a soft signal instead of failing the commit.
                logger.warning("motif_application FK violation on commit — ledger skipped")

    return {"arc_id": str(created["arc_id"]),
            "chapter_ids": [str(i) for i in created["chapter_ids"]],
            "scene_ids": [str(i) for i in created["scene_ids"]],
            "motif_applications": applied,
            "replay": bool(created.get("replay"))}


# ── swap-motif-after-generation (§R2.6 / audit H-4) ─────────────────────

class MotifSwapRequest(BaseModel):
    # apply mode: bind a new motif (motif_id set) or CLEAR (motif_id null) onto the
    # chapter's scenes. undo mode: pass `undo_token` (from a prior swap response) to
    # restore the prior binding+prose. Exactly one mode per call.
    motif_id: UUID | None = None
    undo_token: dict | None = None


async def _bind_scene_motif(
    *, pool: Any, apps: MotifApplicationRepo, kal: KalClient,
    user_id: UUID, project_id: UUID, book_id: UUID, node_id: UUID,
    motif_id: UUID | None, bound_via: str = "manual_scene",
) -> dict[str, Any]:
    """Per-SCENE motif bind/swap/clear (D-MOTIF-FE-SWAP-NODE-GRANULARITY).

    Unlike the chapter swap (`apply_motif_swap` regenerates a chapter's scenes FROM a
    motif's beats), a scene bind is a lightweight ledger write: record "this ONE scene
    realizes motif M" as a single `motif_application` (motif-level — `beat_key` null),
    atomically REPLACING any prior binding on the node. No scene is archived or
    instantiated. `motif_id=None` clears the node's binding (→ free-form). `bound_via`
    stamps the provenance in annotations (`manual_scene` for a hand-bind, `chain` for a
    legal-succession pre-seed). `user_id` is the ACTOR (created_by stamp +
    motif-registry visibility + KAL identity) — never a row filter (25 law)."""
    if motif_id is None:
        async with pool.acquire() as c:
            async with c.transaction():
                removed = await apps.delete_for_nodes(project_id, [node_id], conn=c)
        return {"node_id": str(node_id), "cleared": True, "removed": removed}

    from app.db.repositories.motif_repo import MotifRepo
    motif = await MotifRepo(pool).get_visible(user_id, motif_id)
    if motif is None:
        # H13 uniform — no existence oracle for a foreign/missing motif.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    cast = await _cast_roster(kal, book_id, user_id)
    cast_index = {e["name"].strip().casefold(): e["entity_id"] for e in cast}
    sel = SelectedMotif(motif=motif, score=1.0, match_reason={})
    # bind_motif ignores its ChapterPlan arg (only resolves roles→cast) → throwaway.
    binding = bind_motif(sel, cast_index, ChapterPlan(
        chapter_id=str(node_id), title="", sort_order=0, beat_role=None, intent=""))
    row = {
        "motif_id": str(motif.id),
        "motif_version": motif.version,
        "outline_node_id": str(node_id),
        "role_bindings": binding.role_bindings,
        # motif-level (no beat_key); a manual scene bind isn't a plan-time match.
        "annotations": {**binding.annotations, "bound_via": bound_via},
    }
    async with pool.acquire() as c:
        async with c.transaction():
            await apps.delete_for_nodes(project_id, [node_id], conn=c)
            await apps.insert_many(project_id, book_id, [row], created_by=user_id, conn=c)
    return {
        "node_id": str(node_id),
        "motif_id": str(motif.id),
        "motif_name": motif.name,
        "bound": True,
        "unresolved_roles": binding.unresolved_roles,
        "warning": binding.warning,
    }


@router.patch("/works/{project_id}/outline/{node_id}/motif")
async def swap_node_motif(
    project_id: UUID,
    node_id: UUID,
    body: MotifSwapRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Bind / swap / clear a node's motif — NODE-KIND-AWARE (one URL, the FE's seam):
    - a **chapter** node → the heavy CHAPTER swap (`apply_motif_swap`): archives the
      old scenes (prose preserved), instantiates the new motif's beats as scenes,
      flags orphaned threads, returns an `undo_token`. `undo_token` in the body runs
      the inverse. The JWT-gated HTTP twin of W4's MCP `composition_motif_bind`.
    - a **scene** node → the lightweight per-SCENE ledger bind (`_bind_scene_motif`):
      one motif_application replacing the node's prior binding, no scene regeneration.
    `motif_id=null` clears (→ free-form) in both modes."""
    work = await _require_work(works, grant, user_id, project_id)
    apps = MotifApplicationRepo(get_pool())
    pool = get_pool()

    # UNDO mode — restore the prior binding (the honored Tier-A undo; chapter-only).
    if body.undo_token is not None:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await undo_motif_swap(outline, apps, project_id,
                                            body.undo_token, conn=c)
        return {"undone": True, **res}

    node = await outline.get_node(node_id)
    if node is None or node.project_id != project_id:
        # H13 uniform — no existence oracle for a foreign/missing node.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    # SCENE node → the lightweight per-scene ledger bind (no scene regeneration).
    if node.kind == "scene":
        return await _bind_scene_motif(
            pool=pool, apps=apps, kal=kal, user_id=user_id,
            project_id=project_id, book_id=work.book_id, node_id=node_id,
            motif_id=body.motif_id,
        )

    # CHAPTER node → APPLY mode: resolve + bind the new motif (or clear when None).
    new_sel: SelectedMotif | None = None
    binding: MotifBinding | None = None
    cast_names: dict[str, str] = {}
    if body.motif_id is not None:
        from app.db.repositories.motif_repo import MotifRepo
        motif = await MotifRepo(pool).get_visible(user_id, body.motif_id)
        if motif is None:
            # H13 uniform — no existence oracle for a foreign/missing motif.
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        cast = await _cast_roster(kal, work.book_id, user_id)
        cast_index = {e["name"].strip().casefold(): e["entity_id"] for e in cast}
        cast_names = {e["entity_id"]: e["name"] for e in cast}
        new_sel = SelectedMotif(motif=motif, score=1.0, match_reason={})
        # the swap binds onto the chapter node; ChapterPlan beat_role comes from the
        # node inside apply_motif_swap, so a throwaway ChapterPlan suffices for bind.
        binding = bind_motif(new_sel, cast_index,
                             ChapterPlan(chapter_id=str(node_id), title="", sort_order=0,
                                         beat_role=None, intent=""))

    try:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await apply_motif_swap(
                    outline, apps, project_id, work.book_id, node_id,
                    created_by=user_id,
                    new_motif=new_sel, binding=binding, cast_names=cast_names,
                    k_ceiling=settings.compose_diverge_k,
                    high_threshold=settings.plan_high_tension_threshold,
                    min_scenes=settings.plan_min_scenes_per_chapter,
                    max_scenes=settings.plan_max_scenes_per_chapter, conn=c,
                )
    except MotifSwapError as exc:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"}) from exc

    return {
        "chapter_node_id": res.chapter_node_id,
        "archived_scene_ids": res.archived_scene_ids,
        "new_scene_ids": res.new_scene_ids,
        "orphaned_thread_ids": res.orphaned_thread_ids,
        "new_motif_id": res.new_motif_id,
        "undo_token": res.undo_token,
    }


@router.delete("/works/{project_id}/outline/{node_id}/motif")
async def clear_node_motif(
    project_id: UUID,
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Clear a node's bound motif → free-form. NODE-KIND-AWARE: a **scene** drops its
    single ledger row (`delete_for_nodes`); a **chapter** runs the heavy clear
    (`apply_motif_swap` with no motif → archives the motif's scenes, prose preserved).
    The DELETE twin of the PATCH `motif_id=null` clear (the FE's `clearMotif`)."""
    work = await _require_work(works, grant, user_id, project_id)
    apps = MotifApplicationRepo(get_pool())
    pool = get_pool()

    node = await outline.get_node(node_id)
    if node is None or node.project_id != project_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    if node.kind == "scene":
        async with pool.acquire() as c:
            async with c.transaction():
                removed = await apps.delete_for_nodes(project_id, [node_id], conn=c)
        return {"node_id": str(node_id), "cleared": True, "removed": removed}

    # chapter clear → the heavy archive-scenes path (motif-less apply_motif_swap).
    try:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await apply_motif_swap(
                    outline, apps, project_id, work.book_id, node_id,
                    created_by=user_id,
                    new_motif=None, binding=None, cast_names={},
                    k_ceiling=settings.compose_diverge_k,
                    high_threshold=settings.plan_high_tension_threshold,
                    min_scenes=settings.plan_min_scenes_per_chapter,
                    max_scenes=settings.plan_max_scenes_per_chapter, conn=c,
                )
    except MotifSwapError as exc:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"}) from exc
    return {
        "chapter_node_id": res.chapter_node_id,
        "archived_scene_ids": res.archived_scene_ids,
        "cleared": True,
    }


# ── per-scene role-rebind + legal-succession chain (D-MOTIF-SCENE-REBIND-CHAIN) ──

class RoleRebindRequest(BaseModel):
    # rebind ONE role of the node's bound motif to a cast entity, or null = unresolve.
    role_key: str
    entity_id: UUID | None = None


class MotifChainRequest(BaseModel):
    # the legal-succession motif to pre-seed onto this (the NEXT) node, resolved BY CODE.
    to_motif_code: str


@router.patch("/works/{project_id}/outline/{node_id}/motif/role")
async def rebind_node_motif_role(
    project_id: UUID,
    node_id: UUID,
    body: RoleRebindRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    kal: KalClient = Depends(get_kal_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Rebind ONE role of a node's bound motif → a cast entity (or null = unresolve) —
    the FE ``RoleBindingRow`` → ``useMotifBinding.rebindRole`` seam (`PATCH …/motif/role`).
    Targets the single ``role_bindings[role_key]`` key in place, leaving the other
    resolved roles + motif lineage untouched. H13 uniform 404 (no existence oracle) on:
    a foreign/missing node, a node with NO bound motif (nothing to rebind), a ``role_key``
    the binding doesn't have, or an ``entity_id`` not in THIS book's cast (tenant-scoped —
    a rebind can only point at the book's own glossary entities)."""
    work = await _require_work(works, grant, user_id, project_id)
    node = await outline.get_node(node_id)
    if node is None or node.project_id != project_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    apps = MotifApplicationRepo(get_pool())
    bound = await apps.by_nodes(project_id, [node_id])
    app = bound[0] if bound else None
    if app is None or app.motif_id is None:
        # nothing bound on the node → no role to rebind.
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    # only a role the binding actually has may be rebound (no arbitrary jsonb-key write).
    if body.role_key not in (app.role_bindings or {}):
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
    # the target entity must be in the book's own cast (tenant-scoped; no foreign entity).
    if body.entity_id is not None:
        cast = await _cast_roster(kal, work.book_id, user_id)
        if str(body.entity_id) not in {e["entity_id"] for e in cast}:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    pool = get_pool()
    async with pool.acquire() as c:
        async with c.transaction():
            updated = await apps.set_role_binding(
                project_id, node_id, body.role_key, body.entity_id, conn=c)
    return {
        "node_id": str(node_id),
        "role_key": body.role_key,
        "entity_id": str(body.entity_id) if body.entity_id is not None else None,
        "rebound": updated > 0,
    }


@router.post("/works/{project_id}/outline/{node_id}/motif/chain")
async def chain_node_motif(
    project_id: UUID,
    node_id: UUID,
    body: MotifChainRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    kal: KalClient = Depends(get_kal_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Pre-seed a node with a legal-succession motif resolved BY CODE — the FE
    ``ChainItHint`` → ``useMotifBinding.chainIt`` seam (`POST …/motif/chain`, where
    ``for_node_id`` is the NEXT scene). Resolves ``to_motif_code`` under the visible
    tier-merge (the caller's own row shadows system), then writes a lightweight per-node
    ledger binding (``bound_via='chain'``, no scene regeneration) reusing
    ``_bind_scene_motif``. H13 uniform 404 (no oracle) on a foreign/missing node or an
    unresolvable/foreign code."""
    work = await _require_work(works, grant, user_id, project_id)
    node = await outline.get_node(node_id)
    if node is None or node.project_id != project_id:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    resolved = await MotifRepo(get_pool()).get_by_codes(user_id, [body.to_motif_code])
    motif = resolved.get(body.to_motif_code)
    if motif is None:
        # no visible active motif with that code → uniform not-found (no oracle).
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

    apps = MotifApplicationRepo(get_pool())
    out = await _bind_scene_motif(
        pool=get_pool(), apps=apps, kal=kal, user_id=user_id,
        project_id=project_id, book_id=work.book_id, node_id=node_id,
        motif_id=motif.id, bound_via="chain",
    )
    return {**out, "chained": True, "motif_code": motif.code}


def _assemble_motif_bindings(
    *, scenes: list, apps_by_node: dict, motif_by_id: dict, cast_names: dict[str, str],
) -> dict[str, Any]:
    """PURE in-memory join → ``{node_id: BoundMotif | null}`` (no DB, no glossary —
    the join-correctness surface, mirrors conformance._assemble_conformance).

    Every committed scene appears (null = free-form / cleared / archived-motif, the A3
    invent path — NOT an error), so the FE renders a card per scene without guessing
    which nodes exist. A bound scene → the ``BoundMotif`` shape the FE
    ``MotifBindingCard`` consumes: role_bindings resolved to {entity_id, entity_name}
    via the book cast, the persisted plan-time ``match_reason``, the scene ``beat_key``."""
    bindings: dict[str, Any] = {}
    for s in scenes:
        app = apps_by_node.get(s.id)
        motif = motif_by_id.get(app.motif_id) if (app and app.motif_id) else None
        if app is None or app.motif_id is None or motif is None:
            bindings[str(s.id)] = None
            continue
        role_bindings = {
            rk: {"entity_id": str(eid), "entity_name": cast_names.get(str(eid), "")}
            for rk, eid in (app.role_bindings or {}).items()
        }
        ann = app.annotations or {}
        bindings[str(s.id)] = {
            "motif_id": str(app.motif_id),
            "motif_name": motif.name,
            "motif_source": motif.source,
            "role_bindings": role_bindings,
            "match_reason": ann.get("match_reason") or {},
            "beat_key": ann.get("beat_key"),
        }
    return bindings


def _assemble_succession(
    *, scenes: list, apps_by_node: dict, motif_by_id: dict,
    successors: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """PURE in-memory join → ``{node_id: SuccessionHint | null}`` for the FE ChainIt
    affordance (D-MOTIF-CHAIN-SUCCESSION-HINT).

    A hint is emitted on scene[i]'s card when ALL hold: scene[i] has a bound motif M whose
    `precedes` chain has a successor S, AND scene[i+1] exists and is currently FREE-FORM
    (unbound). The hint pre-seeds that empty next scene — we never suggest chaining OVER an
    already-bound next scene (that would clobber a deliberate binding). ``for_node_id`` is
    the NEXT scene node (where the FE POSTs the chain); the hint shape mirrors the FE
    ``SuccessionHint`` (``from_motif_id``/``to_motif_code``/``to_motif_name``/``for_node_id``)."""
    hints: dict[str, Any] = {}
    for i, s in enumerate(scenes):
        hints[str(s.id)] = None
        app = apps_by_node.get(s.id)
        if app is None or app.motif_id is None or app.motif_id not in motif_by_id:
            continue
        succ = successors.get(str(app.motif_id)) or []
        if not succ:
            continue
        nxt = scenes[i + 1] if i + 1 < len(scenes) else None
        if nxt is None:
            continue
        nxt_app = apps_by_node.get(nxt.id)
        if nxt_app is not None and nxt_app.motif_id is not None:
            continue  # next scene already bound — don't suggest clobbering it
        hints[str(s.id)] = {
            "from_motif_id": str(app.motif_id),
            "to_motif_code": succ[0]["code"],
            "to_motif_name": succ[0]["name"],
            "for_node_id": str(nxt.id),
        }
    return hints


@router.get("/works/{project_id}/outline/motif-bindings")
async def get_motif_bindings(
    project_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    kal: KalClient = Depends(get_kal_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — the POST-commit per-scene motif
    binding for a chapter's committed scene nodes, so the FE renders
    ``MotifBindingCard`` per scene wired to ``useMotifBinding(node_id)``.

    Returns ``{chapter_id, bindings: {node_id: BoundMotif | null}}``. READ-only over
    W2's ``motif_application``; project-scoped on BOTH the application AND the scene
    (the kinds-bug rule — ``by_nodes`` + ``scenes_for_chapter`` both filter project).
    A foreign/missing motif (get_visible → None) degrades that scene to null (no oracle)."""
    from app.db.repositories.motif_repo import MotifRepo

    work = await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    scenes = await outline.scenes_for_chapter(project_id, chapter_id)
    apps = await MotifApplicationRepo(get_pool()).by_nodes(
        project_id, [s.id for s in scenes])

    # latest application per node (by_nodes is created_at ASC → last wins on a re-bind).
    apps_by_node: dict[UUID, Any] = {
        a.outline_node_id: a for a in apps if a.outline_node_id is not None}

    # resolve the distinct bound motifs (name/source) + the book cast (entity → name),
    # both ONCE, only when something is actually bound.
    motif_by_id: dict[UUID, Any] = {}
    cast_names: dict[str, str] = {}
    successors: dict[str, list[dict[str, Any]]] = {}
    bound_ids = {a.motif_id for a in apps_by_node.values() if a.motif_id is not None}
    if bound_ids:
        mrepo = MotifRepo(get_pool())
        for mid in bound_ids:
            m = await mrepo.get_visible(user_id, mid)
            if m is not None:
                motif_by_id[mid] = m
        cast = await _cast_roster(kal, work.book_id, user_id)
        cast_names = {e["entity_id"]: e["name"] for e in cast}
        # the legal-succession edges for the bound motifs → the ChainIt hints.
        successors = await mrepo.successors_by_ids(list(bound_ids))

    bindings = _assemble_motif_bindings(
        scenes=scenes, apps_by_node=apps_by_node,
        motif_by_id=motif_by_id, cast_names=cast_names,
    )
    succession = _assemble_succession(
        scenes=scenes, apps_by_node=apps_by_node,
        motif_by_id=motif_by_id, successors=successors,
    )
    return {"chapter_id": str(chapter_id), "bindings": bindings, "succession": succession}


# ── W10 arc materialize (D-W10-APPLY-PLANNER-MATERIALIZE) ───────────────────────

class ArcMaterializeRequest(BaseModel):
    arc_template_id: UUID
    # arc roster bind {role_key: cast_NAME} — bound once for the whole arc, resolved to
    # entity ids via the book cast; a name matching no cast member is dropped (surfaced).
    roster_bindings: dict[str, Any] = {}
    replace: bool = False
    idempotency_key: str | None = None


async def _resolve_plan_motifs(
    mrepo: MotifRepo, user_id: UUID, placements: list,
) -> list[Any]:
    """Resolve each placement's Motif (parallel to `placements`). Prefer the pinned
    `motif_id` (get_visible); fall back to a tier-merged code lookup; None when neither
    resolves (the engine surfaces it as an unresolved placement — no silent drop)."""
    codes_needing = [p.motif_code for p in placements if p.motif_id is None and p.motif_code]
    by_code = await mrepo.get_by_codes(user_id, codes_needing) if codes_needing else {}
    by_id: dict[UUID, Any] = {}
    for p in placements:
        if p.motif_id is not None and p.motif_id not in by_id:
            by_id[p.motif_id] = await mrepo.get_visible(user_id, p.motif_id)
    out: list[Any] = []
    for p in placements:
        if p.motif_id is not None:
            out.append(by_id.get(p.motif_id))
        else:
            out.append(by_code.get(p.motif_code))
    return out


@router.post("/works/{project_id}/arc/materialize", status_code=201)
async def materialize_arc(
    project_id: UUID,
    body: ArcMaterializeRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    kal: KalClient = Depends(get_kal_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
    arcs: ArcTemplateRepo = Depends(get_arc_template_repo),
    motifs: MotifRepo = Depends(get_motif_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
):
    """Materialize an arc template onto THIS work's book — turn the rescaled placements
    into a committed arc→chapter→scene outline + a motif_application ledger
    (D-W10-APPLY-PLANNER-MATERIALIZE). DETERMINISTIC (no LLM — `scenes_from_motif`).

    Maps the arc onto the book's EXISTING chapters (never mints book chapters, like
    decompose): target_chapters = the book's chapter count; `build_apply_plan` rescales,
    then `build_materialize_spec` distributes each motif's beats across its chapter span.
    Reuses the A3 commit primitives (atomic + idempotent + replace). A not-visible arc →
    H13 404; an all-empty plan (nothing resolved) → 400 with the unresolved report."""
    work = await _require_work(works, grant, user_id, project_id)
    arc = await arcs.get_visible(user_id, body.arc_template_id)
    if arc is None:
        raise HTTPException(status_code=404, detail={
            "code": "ARC_TEMPLATE_NOT_FOUND",
            "message": "arc template not found or not accessible"})

    # The orchestration (chapters→plan→resolve→spec→commit→ledger) is the SHARED engine
    # `apply_arc_to_spec` — the SAME path the MCP tool `composition_arc_apply` runs (D-W10 dedupe:
    # one apply for the GUI and the agent). This route resolves + EDIT-gates the Work above; the
    # engine does the deterministic work and raises typed failures we map to HTTP.
    from app.engine.arc_apply import apply_arc_to_spec, ArcApplyError, ArcApplyConflict
    _STATUS = {"BOOK_SERVICE_UNAVAILABLE": 502}  # the rest are 400 client errors
    try:
        return await apply_arc_to_spec(
            get_pool(), book_id=work.book_id, project_id=project_id, arc_template=arc,
            roster_bindings=dict(body.roster_bindings), replace=body.replace,
            idempotency_key=body.idempotency_key, created_by=user_id,
            book_client=book, kal_client=kal, motifs_repo=motifs, outline_repo=outline, bearer=bearer,
        )
    except ArcApplyConflict as exc:
        raise HTTPException(status_code=409, detail={
            "code": "CHAPTER_ALREADY_PLANNED", "chapter_ids": exc.chapter_ids,
            "detail": "chapters already have scenes — resend with replace=true"}) from exc
    except ArcApplyError as exc:
        raise HTTPException(status_code=_STATUS.get(exc.detail.get("code"), 400),
                            detail=exc.detail) from exc
