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
from pydantic import BaseModel, Field

from app.clients.book_client import BookClient, BookClientError
from app.db.repositories import ReferenceViolationError
from app.clients.glossary_client import GlossaryClient
from app.clients.llm_client import LLMClient
from app.config import settings
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.structure_templates import StructureTemplatesRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_glossary_client_dep, get_llm_client_dep,
    get_outline_repo, get_structure_templates_repo, get_works_repo,
)
from app.engine.plan import ChapterPlan, decompose
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.profile import from_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/composition")


class DecomposeRequest(BaseModel):
    structure_template_id: UUID
    premise: str = Field(min_length=1, max_length=4000)
    model_source: str = Field(min_length=1, max_length=50)
    model_ref: str = Field(min_length=1, max_length=200)


class CommitScene(BaseModel):
    title: str = ""
    synopsis: str = Field(default="", max_length=4000)
    # 0..100 (the outline_node.tension convention) — bounded here so an
    # author-edited commit can't overflow the SMALLINT column into a 500.
    tension: int | None = Field(default=None, ge=0, le=100)
    present_entity_ids: list[UUID] = []


class CommitChapter(BaseModel):
    chapter_id: UUID
    title: str = ""
    intent: str = ""
    beat_role: str | None = None
    scenes: list[CommitScene] = []


class CommitRequest(BaseModel):
    arc_title: str = "Arc"
    chapters: list[CommitChapter] = Field(min_length=1)
    # `force` is honest: it does NOT replace a chapter's existing scenes, it adds
    # the new tree ALONGSIDE them (bypassing the already-planned guard). True
    # replace (archive the prior decomposed subtree) is a deferred follow-up
    # (D-A3-COMMIT-TRUE-REPLACE) — its archival scope (manual vs prior-decompose
    # scenes) needs its own design. Default false = refuse to double-plan.
    force: bool = False


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
    """Run the planner; return the proposed tree (NOT persisted)."""
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
    result = await decompose(
        llm, user_id=str(user_id), model_source=body.model_source, model_ref=body.model_ref,
        premise=body.premise, arc_title=tmpl.name, beats=tmpl.beats,
        chapters=chapters_in, cast=cast,
        k_ceiling=settings.compose_diverge_k, high_threshold=settings.plan_high_tension_threshold,
        min_scenes=settings.plan_min_scenes_per_chapter,
        max_scenes=settings.plan_max_scenes_per_chapter,
        source_language=profile.source_language,
    )
    return dataclasses.asdict(result)


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
    book_ids = {str(c["chapter_id"]) for c in await _book_chapter_ids(book, work.book_id, bearer)}
    bad = [str(cid) for cid in req_chapter_ids if str(cid) not in book_ids]
    if bad:
        raise HTTPException(status_code=400, detail={"code": "BAD_CHAPTER", "chapter_ids": bad})

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

    # already-planned guard: don't silently double-plan a chapter that already
    # has scenes. `force=true` adds the new tree ALONGSIDE the old scenes (it does
    # NOT replace them — see CommitRequest.force).
    existing = await outline.existing_scene_chapter_ids(user_id, project_id, req_chapter_ids)
    if existing and not body.force:
        raise HTTPException(status_code=409, detail={
            "code": "CHAPTER_ALREADY_PLANNED",
            "chapter_ids": sorted(str(c) for c in existing),
            "detail": "chapters already have scenes — resend with force=true to add "
                      "these scenes IN ADDITION (existing scenes are NOT removed)"})

    spec = [{
        "chapter_id": ch.chapter_id, "title": ch.title, "intent": ch.intent,
        "beat_role": ch.beat_role,
        "scenes": [{"title": sc.title, "synopsis": sc.synopsis, "tension": sc.tension,
                    "present_entity_ids": sc.present_entity_ids} for sc in ch.scenes],
    } for ch in body.chapters]
    try:
        created = await outline.create_decomposed_tree(
            user_id, project_id, arc_title=body.arc_title, chapters=spec,
        )
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400,
                            detail={"code": "BAD_REFERENCE", "detail": exc.message}) from exc
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(status_code=400,
                            detail={"code": "CONSTRAINT", "detail": str(exc)}) from exc
    return {"arc_id": str(created["arc_id"]),
            "chapter_ids": [str(i) for i in created["chapter_ids"]],
            "scene_ids": [str(i) for i in created["scene_ids"]]}
