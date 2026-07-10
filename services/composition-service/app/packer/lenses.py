"""Lens gatherers (§2.1) — fetch each context source, degrade gracefully.

Each gatherer mirrors knowledge-service's `_safe_*` pattern: the network/repo
call is wrapped so a failure returns empty (the pack thins, never 500s), but the
IMPORTS stay at module top so a wiring error surfaces loud (verified `full.py`
lesson). Every knowledge/glossary gatherer takes `project_id`/`book_id` as a
REQUIRED arg (not Optional) so a None can't silently widen the read (A1).

Lens map: L0 canon (COMP DB) · L1a present = glossary bios + knowledge relations
· L1b timeline (in-world cutoff) · L2/L2′ structural (COMP DB) · L3 recent prose
(book draft tail — chapter-tail approximation until M8 SceneAnchor) · L4 lore
(knowledge drawers/search; spoiler-filtered in pack.py). L5 deferred.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from app.clients.book_client import BookClient, BookClientError
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.db.models import CanonRule
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo

logger = logging.getLogger(__name__)

_RECENT_PARAGRAPHS = 6  # L3 chapter-tail size
_SOURCE_SCENE_PARAGRAPHS = 12  # M1 adapt-from-source window (a fuller scene than the L3 tail)


@dataclass
class LensBundle:
    canon: list[CanonRule] = field(default_factory=list)
    present: list[dict[str, Any]] = field(default_factory=list)   # {entity_id, name, summary, relations}
    timeline: list[dict[str, Any]] = field(default_factory=list)  # raw events (cutoff at query)
    beat: dict[str, Any] = field(default_factory=dict)
    threads: list[dict[str, Any]] = field(default_factory=list)
    planned: list[dict[str, Any]] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)
    lore: list[dict[str, Any]] = field(default_factory=list)      # raw hits (spoiler-filtered in pack)
    knowledge_seen: bool = False  # True if any knowledge call returned data (C3a signal)
    # S2 — compressed re-injectable state summary (older story-so-far + spoiler-
    # filtered timeline + plan), set by pack() only when the raw "story so far"
    # exceeds budget; renders FIRST in the `recent` block (older→immediate order).
    state_summary: str = ""
    # FD-1 S3 — open promise/foreshadow/MICE threads re-injected so the model
    # carries + pays them (F2; spec §6 ground→…+open-promises). [{kind, summary}],
    # priority-ordered + capped. Empty unless the Work opts into narrative_thread.
    open_promises: list[dict[str, Any]] = field(default_factory=list)
    # C25 — added canon-rule text contributed by a derivative's entity overrides
    # (the M0 "added canon rule" override scope). Rendered in the <canon> block
    # alongside inherited canon. Empty for a non-derivative pack.
    extra_canon: list[str] = field(default_factory=list)
    # T3.6 — the author's semantically-retrieved reference passages (external
    # influences) for this scene. Each {id, title, author, source_url, content,
    # score}. composition-owned; pinned ones are protected in the budget.
    references: list[dict[str, Any]] = field(default_factory=list)
    # M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — the inherited SOURCE scene's prose
    # paragraphs for the `adapt_scene` op (gathered by gather_source_scene ONLY for
    # that op, spoiler-bounded ≤ the branch). Renders as the <source_scene> block
    # the adapt instruction points the model at. Empty for every other op / Work.
    source_scene: list[str] = field(default_factory=list)


def _applies_at(rule: CanonRule, story_order: int | None) -> bool:
    """A canon rule applies at the scene position if the position is within
    [from_order, until_order] (None bound = open).

    FAIL-CLOSED on unknown position (/review-impl M4 MED#1): when `story_order`
    is None we CANNOT place the scene, so we include ONLY ungated world rules
    (`from_order is None`). A `from_order`d rule is a reveal-gate — its text is a
    spoiler until that in-world moment — and must NOT leak into the canon block
    of a scene whose position we can't verify. (Consistent with gather_timeline,
    which returns [] for a None story_order.)"""
    if story_order is None:
        return rule.from_order is None
    if rule.from_order is not None and story_order < rule.from_order:
        return False
    if rule.until_order is not None and story_order > rule.until_order:
        return False
    return True


async def gather_canon(
    canon_repo: CanonRulesRepo, project_id: UUID, story_order: int | None,
) -> list[CanonRule]:
    """L0 — active canon rules applying at the scene's in-world position."""
    try:
        rules = await canon_repo.list_active(project_id)
    except Exception:  # noqa: BLE001 — repo failure degrades the lens
        logger.warning("gather_canon failed", exc_info=True)
        return []
    return [r for r in rules if _applies_at(r, story_order)]


async def gather_open_promises(
    repo, project_id: UUID, *, cap: int,
) -> list[dict[str, Any]]:
    """FD-1 S3 — the open promise/foreshadow set to re-inject (F2). Returns the
    top-`cap` open threads (list_open is priority DESC, created ASC) as
    {kind, summary}. Degrade-safe: any repo failure → [] (re-injection is
    advisory; it must never fail a pack).

    review-impl LOW#3 (accepted, → S4): the open set is NOT position-filtered, so
    an OUT-OF-ORDER regenerate (regen an earlier scene while a later scene's
    promise is open) could re-inject a later-position promise (a forward leak). In
    normal sequential generation, open promises are all ≤ the current position, so
    this is an edge case; the spoiler-axis filter (compare opened_at_node position
    to the scene's story_order) belongs with S4's debt/spoiler work."""
    try:
        threads = await repo.list_open(project_id, limit=cap)
    except Exception:  # noqa: BLE001 — repo failure degrades the lens
        logger.warning("gather_open_promises failed", exc_info=True)
        return []
    return [
        {"kind": t.kind, "summary": t.summary}
        for t in threads if (t.summary or "").strip()
    ]


async def gather_present(
    glossary: GlossaryClient, knowledge: KnowledgeClient, *,
    book_id: UUID, user_id: UUID, project_id: UUID, bearer: str, query: str,
    present_entity_ids: list[UUID], language: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """L1a — who is present + their state. Bios from glossary select-for-context
    (rich short_description); currently-valid relations from knowledge for the
    explicitly-cast entities. DI3: a soft-absent (renamed/trashed) id is SKIPPED,
    never crashes; we cache the STABLE glossary entity_id, not knowledge's
    rename-sensitive canonical_id. Returns (present, knowledge_seen)."""
    present: list[dict[str, Any]] = []
    seen = False
    # Bios: mui #4 — semantic-ranked entities from knowledge when the project
    # has embeddings (vector beats lexical, esp. for CJK); fall back to glossary
    # FTS select-for-context on empty/failure (AC4/AC5). Same item shape either
    # way (entity_id/cached_name/short_description), so the loop below is shared.
    bios = await knowledge.glossary_semantic(user_id, project_id=project_id, query=query)
    if not bios:
        bios = await glossary.select_for_context(book_id, user_id, query, language=language)
    for b in bios:
        eid = b.get("entity_id")
        if not eid:  # soft-absent / malformed → skip (DI3)
            continue
        present.append({
            "entity_id": eid,
            "name": b.get("cached_name") or "",
            "summary": b.get("short_description") or "",
            "relations": [],
        })
    # Knowledge relations for the explicitly-cast entities (best-effort).
    by_id = {p["entity_id"]: p for p in present}
    for ent_id in present_entity_ids:
        detail = await knowledge.get_entity(bearer, str(ent_id))
        if detail is None:  # soft-absent / unavailable → skip (DI3)
            continue
        seen = True
        rels = [
            f'{r.get("predicate", "")} {r.get("object_name", r.get("object_id", ""))}'.strip()
            for r in (detail.get("relations") or [])
        ]
        key = str(ent_id)
        if key in by_id:
            by_id[key]["relations"] = rels
        else:
            ent = detail.get("entity") or {}
            # Cache the glossary anchor id (stable), not the knowledge id.
            anchor = ent.get("glossary_entity_id") or key
            present.append({"entity_id": anchor, "name": ent.get("name", ""), "summary": "", "relations": rels})
    return present, seen


async def gather_timeline(
    knowledge: KnowledgeClient, bearer: str, project_id: UUID, at_order: int | None,
    after_order: int | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """L1b — in-world events strictly before the scene's chapter, on the DENSE
    reading-order axis (`event_order` = chapter sort_order × stride; CM4).

    Queries `before_order=at_order`, NOT the sparse date-derived
    `chronological_order`: extraction leaves most events dateless (esp. CJK) →
    `chronological_order` NULL → the date-axis query silently drops them, so prior
    chapters' plot never carried into a new chapter's pack (LOOM-32 Round-2 finding
    — the chapter-boundary re-establishment defect). `event_order` is always set
    when a chapter is published, so the dense axis carries ALL position-bound
    events.

    NEVER queried without a cutoff: `at_order=None` (scene's chapter unplaceable)
    → [] (a no-cutoff call would leak future events). Returns (events, seen)."""
    if at_order is None:
        return [], False
    events = await knowledge.timeline(bearer, project_id=project_id, before_order=at_order,
                                      after_order=after_order)
    return events, bool(events)


async def gather_structural(
    outline_repo: OutlineRepo, scene_links_repo: SceneLinksRepo, *,
    project_id: UUID, node: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    """L2 beat/goal/POV/synopsis + setup_payoff threads, and L2′ planned
    synopses of unwritten scenes at/before this position."""
    beat = {
        "beat_role": node.get("beat_role"), "goal": node.get("goal", ""),
        "pov_entity_id": node.get("pov_entity_id"), "synopsis": node.get("synopsis", ""),
        "title": node.get("title", ""),
    }
    threads: list[dict[str, Any]] = []
    planned: list[dict[str, Any]] = []
    node_id = node.get("id")
    try:
        links = await scene_links_repo.list_by_project(project_id)
        threads = [
            {"kind": l.kind, "label": l.label, "to": str(l.to_node_id)}
            for l in links if str(l.from_node_id) == str(node_id) or str(l.to_node_id) == str(node_id)
        ]
    except Exception:  # noqa: BLE001
        logger.warning("gather threads failed", exc_info=True)
    try:
        tree = await outline_repo.list_tree(project_id)
        my_order = node.get("story_order")
        for n in tree:
            if n.kind != "scene" or n.status == "done" or str(n.id) == str(node_id):
                continue
            if my_order is not None and n.story_order is not None and n.story_order > my_order:
                continue
            if n.synopsis:
                planned.append({"title": n.title, "synopsis": n.synopsis})
    except Exception:  # noqa: BLE001
        logger.warning("gather planned failed", exc_info=True)
    return beat, threads, planned


async def gather_recent(
    book: BookClient, book_id: UUID, chapter_id: UUID, bearer: str, *,
    k: int = _RECENT_PARAGRAPHS,
    jobs_repo: GenerationJobsRepo | None = None,
    project_id: UUID | None = None,
    story_order: int | None = None,
) -> list[str]:
    """L3 — the chapter's 'story so far'. PRIMARY source = the accepted chapter
    DRAFT (last K paragraphs — chapter-tail; M8 upgrades to precise SceneAnchor
    ranges).

    **S1 state-reinjection fallback** (D-COMP-LONGFORM-STATE-REINJECTION): when
    there is NO accepted draft yet (autonomous generation / not-yet-accepted —
    the case the A-EVAL/B concat eval exposed), fall back to the prior generated
    scene winners, **STRICTLY position-bounded** (`story_order < current`;
    spoiler-safe, /review-impl H1). Returns ALL prior prose as paragraphs — the
    budget ladder protects the immediate-preceding one (PRIO_RECENT_IMMEDIATE) and
    trims older ones (PRIO_RECENT_OLDER), so it never evicts canon/spoiler-safety."""
    try:
        draft = await book.get_draft(book_id, chapter_id, bearer)
        text = draft.get("text_content") or ""
    except BookClientError:
        text = ""
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if paras:
        return paras[-k:]  # primary: the accepted draft tail
    # Fallback: no accepted draft → prior generated scene winners (strictly prior).
    if jobs_repo is not None and project_id is not None and story_order is not None:
        try:
            prior = await jobs_repo.prior_scene_drafts(project_id, chapter_id, story_order)
        except Exception:  # noqa: BLE001
            logger.warning("gather_recent prior-scene fallback failed", exc_info=True)
            return []
        return [p.strip() for t in prior for p in t.split("\n") if p.strip()]
    return []


async def gather_source_scene(
    book: BookClient, book_id: UUID, source_chapter_id: UUID, bearer: str, *,
    branch_point: int | None = None, chapter_sort_order: int | None = None,
    k: int = _SOURCE_SCENE_PARAGRAPHS,
) -> list[str]:
    """M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — the inherited SOURCE scene's prose for
    the `adapt_scene` op. A derivative Work is COW: it shares the SOURCE `book_id`
    and chapter spine (works.py:315), so the source prose lives in the SAME chapter
    DRAFT the derivative scene maps to — read it on the shared `book_id`.

    Mirrors `gather_recent` (reads `book.get_draft`, returns the last K paragraphs
    under a paragraph budget so a long source chapter can't blow context), BUT
    spoiler-bounded on the chapter reading-order axis (`chapter_sort_order` is the
    source chapter's `sort_order`, the SAME axis `branch_point` lives on):

      **At/after the branch only.** A chapter STRICTLY BEFORE `branch_point` is
      inherited CANON, not adaptable — its prose must not seed an "adapt" ghost
      (the FE gates the action too; this is the server belt). chapter_sort_order
      < branch_point → [] (the "pre-branch scene = read-only" edge case). This is
      also the ≤-scene-position bound: for an inherited spine the adapted chapter
      IS the scene's own chapter, so reading at/after the branch never pulls prose
      past where the scene sits.

    The bound only fires when the position is PLACEABLE — a None on either side
    (sort-order outage / unplaceable) skips it rather than fail-empty, so a
    transient book-service hiccup doesn't kill a legitimate adapt the FE already
    offer-gated. Empty/absent source draft → [] (the caller surfaces "nothing to
    adapt"; the FE falls back to draft_scene). Best-effort: a book-service error
    degrades to []."""
    if (branch_point is not None and chapter_sort_order is not None
            and chapter_sort_order < branch_point):
        return []
    try:
        draft = await book.get_draft(book_id, source_chapter_id, bearer)
        text = draft.get("text_content") or ""
    except BookClientError:
        return []
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        return []
    return paras[-k:]  # last K paragraphs — the budgeted source-prose adapt window


async def gather_lore(
    knowledge: KnowledgeClient, bearer: str, project_id: UUID, query: str,
    language: str | None = None,
) -> tuple[list[dict[str, Any]], bool]:
    """L4 — semantic lore hits (RAW; pack.py applies the reading-order spoiler
    filter). `project_id` is required by the endpoint. Returns (hits, seen).

    KG-ML M7 (C6): `language` (author's reader-language) soft-orders in-language
    passages first so a vi author's lore lens surfaces vi passages (headline)."""
    if not query.strip():
        return [], False
    hits = await knowledge.search_drawers(
        bearer, project_id=project_id, query=query, language=language
    )
    return hits, bool(hits)


async def gather_references(
    refs_repo, embedder, *, user_id: UUID, project_id: UUID, query: str,
    model: tuple[str, str] | None, limit: int = 6,
) -> tuple[list[dict[str, Any]], bool]:
    """T3.6 — the author's reference shelf, semantically retrieved for this scene.
    Embeds the scene query via provider-registry and cosine-ranks the Work's
    references (composition-owned, brute-force top-K). Returns (hits, seen).

    Fully degrade-safe (the packer `_safe_*` posture): an unwired repo/embedder, an
    unset Work embed model, an empty query, an embed/provider failure, or a repo
    error all yield ([], False) — references THIN the pack, never fail it."""
    if refs_repo is None or embedder is None or model is None or not query.strip():
        return [], False
    model_source, model_ref = model
    try:
        result = await embedder.embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref, texts=[query])
        if not result.embeddings or not result.embeddings[0]:
            return [], False
        hits = await refs_repo.search(project_id, result.embeddings[0], limit=limit)
    except Exception:  # noqa: BLE001 — references are advisory; never fail a pack
        logger.warning("gather_references failed", exc_info=True)
        return [], False
    return hits, bool(hits)
