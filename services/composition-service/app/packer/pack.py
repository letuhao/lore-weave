"""Packer orchestrator (§2.5) — gather → spoiler → budget → assemble.

Flow: A1 chokepoint (project_id) → SEC2 chokepoint (owns_book BEFORE any internal
read) → resolve the scene's reading position → parallel `_safe_*` lens gather →
two-axis spoiler filter (L1b in-world, L4 reading-order with conservative-drop +
LOG) → priority-ladder budget trim → assemble structured blocks. Returns a
PackedContext that the grounding endpoint (and M6 engine) consume.

C3a: when no knowledge lens returned data, `grounding_available=False` + a
warning — surface "grounding thin/unavailable", never silently ship thin.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.clients.book_client import BookClient
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.packer import assemble
from app.packer import budget as B
from app.packer import profile as profile_mod
from app.packer import spoiler
from app.packer.lenses import (
    LensBundle, gather_canon, gather_lore, gather_present, gather_recent,
    gather_structural, gather_timeline,
)

logger = logging.getLogger(__name__)


class OwnershipError(Exception):
    """Caller does not own the book — raised by the SEC2 chokepoint so the
    router maps it to 404 (don't leak existence)."""


@dataclass
class PackRequest:
    user_id: UUID
    project_id: UUID
    book_id: UUID
    node: dict[str, Any]   # the outline_node (id, chapter_id, story_order, present_entity_ids, pov_entity_id, beat_role, goal, synopsis, title)
    bearer: str
    guide: str = ""
    settings: dict[str, Any] | None = None  # composition_work.settings → BookProfile


@dataclass
class PackedContext:
    blocks: dict[str, str]
    prompt: str
    profile: profile_mod.BookProfile
    token_count: int
    dropped_count: int
    l4_dropped_no_position: int
    grounding_available: bool
    over_budget: bool
    # A2-S3b — the scene's chapter reading-order (book sort_order), the canon
    # guard's position axis (× stride = the event_order cutoff). None when the
    # node has no resolved chapter → the guard skips (advisory).
    scene_sort_order: int | None = None
    warnings: list[str] = field(default_factory=list)


def _as_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def pack(
    req: PackRequest, *,
    book: BookClient, glossary: GlossaryClient, knowledge: KnowledgeClient,
    canon_repo: CanonRulesRepo, outline_repo: OutlineRepo, scene_links_repo: SceneLinksRepo,
    budget_tokens: int, counter: B.TokenCounter | None = None,
) -> PackedContext:
    # A1: never pack unscoped (knowledge timeline/entities widen cross-project).
    assemble.assert_project_scoped(req.project_id)
    # SEC2: verify book ownership BEFORE any internal (token-trust) read.
    if not await book.owns_book(req.book_id, req.bearer):
        raise OwnershipError("caller does not own the book")

    profile = profile_mod.from_settings(req.settings)
    node = req.node
    story_order = node.get("story_order")
    chapter_id = _as_uuid(node.get("chapter_id"))
    query = " ".join(
        str(x) for x in [node.get("goal"), node.get("synopsis"), node.get("beat_role"), node.get("title")] if x
    )
    present_ids = [u for u in (
        [_as_uuid(node.get("pov_entity_id"))] + [_as_uuid(e) for e in (node.get("present_entity_ids") or [])]
    ) if u is not None]

    canon, (present, seen_p), (timeline, seen_t), (beat, threads, planned), recent, (lore, seen_l) = (
        await asyncio.gather(
            gather_canon(canon_repo, req.user_id, req.project_id, story_order),
            gather_present(glossary, knowledge, book_id=req.book_id, user_id=req.user_id,
                           project_id=req.project_id, bearer=req.bearer, query=query,
                           present_entity_ids=present_ids),
            gather_timeline(knowledge, req.bearer, req.project_id, story_order),
            gather_structural(outline_repo, scene_links_repo, user_id=req.user_id,
                              project_id=req.project_id, node=node),
            gather_recent(book, req.book_id, chapter_id, req.bearer) if chapter_id else _empty_list(),
            gather_lore(knowledge, req.bearer, req.project_id, query),
        )
    )

    # Resolve reading positions in ONE batch: the scene's chapter + any lore hit
    # whose chapter_index is None (best-effort ingest left it unset).
    to_resolve: list[UUID] = []
    if chapter_id is not None:
        to_resolve.append(chapter_id)
    for h in lore:
        if h.get("chapter_index") is None:
            sid = _as_uuid(h.get("source_id"))
            if sid is not None:
                to_resolve.append(sid)
    sort_map = await book.get_chapter_sort_orders(to_resolve) if to_resolve else {}
    scene_sort_order = sort_map.get(str(chapter_id)) if chapter_id is not None else None

    # Spoiler — two axes.
    tl_kept, tl_dropped = spoiler.filter_inworld_events(timeline, story_order)

    def position_for(h: dict[str, Any]) -> int | None:
        ci = h.get("chapter_index")
        if isinstance(ci, int):
            return ci
        return sort_map.get(str(h.get("source_id")))

    l4 = spoiler.filter_reading_order(lore, scene_sort_order, position_for)
    if l4.dropped_no_position:
        logger.info(
            "l4_dropped_no_position=%d (project=%s node=%s)",
            l4.dropped_no_position, req.project_id, node.get("id"),
        )

    bundle = LensBundle(
        canon=canon, present=present, timeline=tl_kept, beat=beat, threads=threads,
        planned=planned, recent=recent, lore=l4.kept,
        knowledge_seen=bool(seen_p or seen_t or seen_l),
    )
    segs = assemble.build_segments(bundle, guide=req.guide)
    bres = B.enforce_budget(segs, budget_tokens, counter or B.default_counter())
    blocks = assemble.segments_to_blocks(bres.kept)

    warnings: list[str] = []
    if not bundle.knowledge_seen:
        warnings.append("grounding_unavailable: no knowledge-graph data for this scene/project (C3a)")
    if l4.dropped_no_position:
        warnings.append(f"l4_dropped_no_position={l4.dropped_no_position}")
    if bres.over_budget:
        warnings.append("over_budget: protected context exceeds the token target")

    return PackedContext(
        blocks=blocks, prompt=assemble.render(blocks), profile=profile,
        token_count=bres.total_tokens, dropped_count=bres.dropped_count,
        l4_dropped_no_position=l4.dropped_no_position,
        grounding_available=bundle.knowledge_seen, over_budget=bres.over_budget,
        scene_sort_order=scene_sort_order,
        warnings=warnings,
    )


async def _empty_list() -> list[Any]:
    """gather() placeholder for the L3 lens when the scene has no chapter_id."""
    return []
