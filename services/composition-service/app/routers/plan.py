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
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.db.repositories import AlreadyPlannedError, ReferenceViolationError
from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.pool import get_pool
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_retrieve import MotifRetriever
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_generation_jobs_repo, get_glossary_client_dep,
    get_llm_client_dep, get_outline_repo, get_structure_templates_repo, get_works_repo,
)
from app.engine.motif_select import (
    MotifBinding, MotifSwapError, SelectedMotif, apply_motif_swap,
    bind_motif, undo_motif_swap,
)
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE
from app.engine.plan import ChapterPlan, decompose
from app.middleware.jwt_auth import get_bearer_token, get_current_user
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


async def _require_work(works: WorksRepo, user_id: UUID, project_id: UUID):
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    return work


async def _book_chapter_ids(book: BookClient, book_id: UUID, bearer: str) -> list[dict]:
    """Active chapters for the book, or 502 if book-service can't be reached (the
    IDOR/validation guards depend on this list — never silently skip it)."""
    try:
        return await book.list_chapters(book_id, bearer)
    except BookClientError as exc:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE",
                                                     "detail": str(exc)}) from exc


async def _cast_roster(glossary: GlossaryClient, book_id: UUID) -> list[dict]:
    """The book's glossary entities as `{entity_id, name}`. Empty on outage (the
    planner just gets no roster; commit-time entity validation degrades to skip —
    present_entity_ids are non-FK display hints, packer-tolerant)."""
    resp = await glossary.list_entities(book_id)
    if not resp:
        return []
    return [{"entity_id": str(i["entity_id"]), "name": i["name"]}
            for i in resp.get("items", []) if i.get("name") and i.get("entity_id")]


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
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    llm: LLMClient = Depends(get_llm_client_dep),
    templates: StructureTemplatesRepo = Depends(get_structure_templates_repo),
):
    """Run the planner; return the proposed tree (NOT persisted).

    Phase 3 M4 — when COMPOSITION_WORKER_ENABLED, the bearer-authenticated context
    (book chapters, cast) is resolved HERE, persisted in the job's input, and the
    LLM compute runs OFF the request path: returns 202 + job_id; GET /jobs/{id}
    polls for the proposed tree. Default (flag off) → inline behavior verbatim."""
    work = await _require_work(works, user_id, project_id)
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

    cast = await _cast_roster(glossary, work.book_id)
    profile = from_settings(work.settings)
    chapters_in = [
        ChapterPlan(chapter_id=str(c["chapter_id"]), title=c["title"],
                    sort_order=c["sort_order"], beat_role=None, intent="")
        for c in chapters_raw
    ]

    # W2 motif select+bind context (only resolved when the toggle is on — default
    # OFF in P1, so the inline/worker paths are byte-identical to today when off).
    motif_genres: list[str] = []
    motif_applied_counts: dict[str, int] = {}
    if body.motifs_enabled:
        motif_genres = await _book_genre_tags(book, work.book_id, bearer)
        motif_applied_counts = await MotifApplicationRepo(get_pool()).count_by_motif_for_book(
            user_id, work.book_id,
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
            # W2 — persisted so the worker can bind motifs off-request once
            # operations.run_decompose is wired (worker-path motif binding is a
            # cross-track follow-up; default-OFF in P1 means the worker ignores these
            # until then). book_id/project_id let the worker resolve the retriever.
            "motifs_enabled": body.motifs_enabled,
            "motif_genre_tags": motif_genres,
            "book_id": str(work.book_id),
        }
        job, _created = await jobs.create(
            user_id, project_id, operation="decompose_preview",
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
        motifs_enabled=body.motifs_enabled,
        retriever=MotifRetriever(get_pool()) if body.motifs_enabled else None,
        book_id=work.book_id if body.motifs_enabled else None,
        project_id=project_id if body.motifs_enabled else None,
        genre_tags=motif_genres,
        motif_min_score=settings.motif_min_score,
        motif_max_reapply=settings.motif_max_reapply,
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
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
):
    """Persist the accepted tree (arc→chapter→scene) atomically. Validates every
    chapter_id belongs to the book (IDOR) + every present_entity_id is a real
    glossary id; refuses to re-plan a chapter that already has scenes unless
    `replace=true`."""
    work = await _require_work(works, user_id, project_id)
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

    # present_entity validation against the glossary cast. Best-effort: on a
    # glossary outage (empty roster) we SKIP rather than false-reject valid ids
    # (present_entity_ids are non-FK, packer-tolerant). Only validate when we have
    # a roster to validate against.
    cast = await _cast_roster(glossary, work.book_id)
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
        "scenes": [{"title": sc.title, "synopsis": sc.synopsis, "tension": sc.tension,
                    "present_entity_ids": sc.present_entity_ids,
                    "story_order": sort_by_chapter[str(ch.chapter_id)] * STORY_ORDER_CHAPTER_STRIDE + i}
                   for i, sc in enumerate(ch.scenes)],
    } for ch in body.chapters]
    try:
        created = await outline.commit_decomposed_tree(
            user_id, project_id, arc_title=body.arc_title, chapters=spec,
            replace=body.replace or body.force, idempotency_key=body.idempotency_key,
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
                    user_id, project_id, work.book_id, ledger_rows,
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


@router.patch("/works/{project_id}/outline/{node_id}/motif")
async def swap_chapter_motif(
    project_id: UUID,
    node_id: UUID,
    body: MotifSwapRequest,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    outline: OutlineRepo = Depends(get_outline_repo),
):
    """Swap (or clear) a CHAPTER's bound motif after its scenes may already have
    prose. Archives the old scenes (prose preserved — never deleted), instantiates
    the new motif's scenes, flags orphaned narrative_thread promises (surfaced, not
    closed), and returns an undo_token. `undo_token` in the body runs the inverse
    (restore prior binding + prose). The JWT-gated HTTP twin of W4's MCP
    `composition_motif_bind` — ONE engine (motif_select), two entries."""
    work = await _require_work(works, user_id, project_id)
    apps = MotifApplicationRepo(get_pool())
    pool = get_pool()

    # UNDO mode — restore the prior binding (the honored Tier-A undo).
    if body.undo_token is not None:
        async with pool.acquire() as c:
            async with c.transaction():
                res = await undo_motif_swap(outline, apps, user_id, project_id,
                                            body.undo_token, conn=c)
        return {"undone": True, **res}

    # APPLY mode — resolve + bind the new motif (or clear when motif_id is None).
    new_sel: SelectedMotif | None = None
    binding: MotifBinding | None = None
    cast_names: dict[str, str] = {}
    if body.motif_id is not None:
        from app.db.repositories.motif_repo import MotifRepo
        motif = await MotifRepo(pool).get_visible(user_id, body.motif_id)
        if motif is None:
            # H13 uniform — no existence oracle for a foreign/missing motif.
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})
        cast = await _cast_roster(glossary, work.book_id)
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
                    outline, apps, user_id, project_id, work.book_id, node_id,
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
