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

import asyncio
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
from app.packer.sanitize import sanitize_lore

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


def _arc_position(story_order: int | None, span: dict[str, Any]) -> int | None:
    """The scene's pacing position within a node's DERIVED span (BA6/BPS-3): a
    0..100 percentage of `story_order` across [min_story_order, max_story_order]
    over the node's member chapters. None when unplaceable (no story_order, an
    empty/unplaced span). A single-chapter span (max<=min) reads as 0% (the scene
    IS the whole span — clamped, never a divide-by-zero)."""
    lo = span.get("min_story_order")
    hi = span.get("max_story_order")
    if story_order is None or lo is None or hi is None:
        return None
    if hi <= lo:
        return 0
    pct = round((story_order - lo) / (hi - lo) * 100)
    return max(0, min(100, pct))


async def gather_arc(
    structure_repo, structure_node_id: UUID, *,
    story_order: int | None, narrative_threads_repo=None,
    open_promises_cap: int = 8,
) -> str:
    """23 BA12 — the ARC lens: the durable spec layer (`structure_node`) reaching
    the prompt. This is the anti-write-only proof for the whole spec — a chapter
    assigned to an arc must STEER generation, and the D2 effect test asserts this
    frame CHANGES when the arc's `tracks` change.

    Renders (BA12) a compact structural frame the drafter reads FIRST:
      · the resolved arc CHAIN — saga→arc→sub-arc titles, root→leaf (`ancestor_chain`)
      · the merged `tracks` (`resolve_tracks` — the ONE cascade impl, BA7; never
        re-derived here) shadowed by `key`
      · the pacing POSITION of this scene within EACH ancestor's derived span
        (`span` + this scene's `story_order`) — the coexisting curves BA7 calls out
        ("~60% through arc 'Betrayal'; ~20% through saga 'Ascension'")
      · the merged `roster_bindings` (`resolve_roster_bindings`, shadow by role_key)
      · the open-promise rollup over the arc's chapter subtree (`open_promises`, BA15)

    Best-effort (the packer `_safe_*` posture): any repo failure degrades to '' — the
    arc frame THINS, never fails a pack. Every author-authored string (titles, goals,
    track labels, binding ids, promise summaries) is neutralised (SEC3) before
    assembly so a crafted title can't forge a block delimiter on re-injection."""
    try:
        chain, tracks, bindings = await asyncio.gather(
            structure_repo.ancestor_chain(structure_node_id),
            structure_repo.resolve_tracks(structure_node_id),
            structure_repo.resolve_roster_bindings(structure_node_id),
        )
    except Exception:  # noqa: BLE001 — the arc frame degrades; never fail a pack
        logger.warning("gather_arc resolve failed", exc_info=True)
        return ""
    if not chain:  # a dangling structure_node_id (deleted arc) → nothing to inject
        return ""

    def _title(n: Any) -> str:
        return sanitize_lore((getattr(n, "title", "") or "").strip()) or "(untitled)"

    lines: list[str] = []

    # 1. CHAIN — the saga→arc→sub-arc frame (root→leaf).
    lines.append("Arc chain: " + " → ".join(
        f'{getattr(n, "kind", "arc")} "{_title(n)}"' for n in chain))

    # the leaf (the arc this chapter is assigned to) intent
    goal = sanitize_lore((getattr(chain[-1], "goal", "") or "").strip())
    if goal:
        lines.append(f"Arc goal: {goal}")

    # 2. TRACKS — the merged parallel plotlines (BA7 cascade), shadow by key.
    track_parts: list[str] = []
    for t in tracks or []:
        key = sanitize_lore(str(t.get("key", "")).strip())
        label = sanitize_lore(str(t.get("label", "")).strip())
        piece = f"{key}: {label}" if key and label else (key or label)
        if piece:
            track_parts.append(piece)
    if track_parts:
        lines.append("Tracks: " + "; ".join(track_parts))

    # 3. PACING — this scene's position within each ancestor's derived span
    #    (coexisting curves, BA7). One span() per chain node (depth<=2), gathered
    #    concurrently; a per-node failure just drops that node's curve.
    spans = await asyncio.gather(
        *(structure_repo.span(getattr(n, "id")) for n in chain),
        return_exceptions=True,
    )
    pacing_parts: list[str] = []
    for n, sp in zip(chain, spans):
        if isinstance(sp, BaseException):
            continue
        pct = _arc_position(story_order, sp)
        if pct is not None:
            pacing_parts.append(f'~{pct}% through {getattr(n, "kind", "arc")} "{_title(n)}"')
    if pacing_parts:
        lines.append("Pacing: " + "; ".join(pacing_parts))

    # 4. CAST — the merged roster_bindings (role_key → glossary entity), shadow by
    #    role_key. The concrete cast the abstract roster slots resolve to.
    binding_parts: list[str] = []
    for role_key, entity_id in (bindings or {}).items():
        rk = sanitize_lore(str(role_key).strip())
        ev = sanitize_lore(str(entity_id).strip())
        if rk and ev:
            binding_parts.append(f"{rk} → {ev}")
    if binding_parts:
        lines.append("Cast bindings: " + "; ".join(binding_parts))

    # 5. OPEN PROMISES — the rollup over the arc's chapter subtree (BA15). Needs the
    #    promise-ledger repo's pool (open_promises borrows it); skip when unwired.
    if narrative_threads_repo is not None:
        try:
            promises = await structure_repo.open_promises(
                structure_node_id, narrative_threads_repo=narrative_threads_repo)
        except Exception:  # noqa: BLE001 — the rollup degrades; never fail a pack
            logger.warning("gather_arc open_promises failed", exc_info=True)
            promises = []
        promise_parts: list[str] = []
        for p in promises[:open_promises_cap]:
            summary = sanitize_lore((getattr(p, "summary", "") or "").strip())
            if summary:
                promise_parts.append(f'{getattr(p, "kind", "promise")}: {summary}')
        if promise_parts:
            lines.append("Open threads: " + "; ".join(promise_parts))

    return "\n".join(lines)


#: X-7 caps. The <motif> block rides OUTSIDE enforce_budget (like <arc>), so every
#: unbounded surface in it is a Context-Budget-Law hole. Two exist: the motif's `beats[]`
#: (listed as the scene's shape when no beat is bound — a motif may carry dozens) and the
#: free author text (`summary`, beat intents).
_MOTIF_BEAT_CAP = 3
_MOTIF_SUMMARY_CHARS = 240


def _clip(text: str, limit: int = _MOTIF_SUMMARY_CHARS) -> str:
    """Sanitize + truncate one author-authored string."""
    s = sanitize_lore((text or "").strip())
    return s if len(s) <= limit else s[:limit].rstrip() + "…"


async def gather_motif(
    applications_repo, motif_repo, project_id: UUID, node_id: UUID, *,
    user_id: UUID,
    beat_cap: int = _MOTIF_BEAT_CAP,
    summary_chars: int = _MOTIF_SUMMARY_CHARS,
) -> str:
    """X-7 == spec 30 BE-19 == spec 33 BE-M2 — the MOTIF lens: the narrative-craft layer
    (套路 / 爽点 / 打脸) finally reaching the prompt.

    This is the anti-write-only proof for the whole motif cluster. The author binds 打脸 to
    a scene, the Hub renders the chip, the binder writes `motif_application`, and the
    conformance engine GRADES the prose against it — and until this lens existed, `pack()`
    never told the drafter. A motif bound to a scene must STEER generation; the effect test
    asserts this frame CHANGES when the binding changes.

    Resolution — LAST-WINS, the one shipped rule:
      `by_nodes` is ORDER BY created_at ASC and the binder INSERTs a NEW row per re-bind
      (no upsert, no unique index), so a scene can carry N rows. They are SUPERSEDED
      VERSIONS, not N co-bound motifs — so we take the LAST, exactly as the shipped
      `plan.py:1196` does. Rendering the older rows would steer the drafter with a binding
      the author already replaced, which is worse than verbose.

    Degradation (no oracle): no binding → "". An archived motif (`motif_id` is SET NULL per
    models.py:545) or a foreign one (`get_visible` → None) → "", exactly as plan.py:1188
    degrades. Any repo failure → "" — the motif frame THINS, never fails a pack.

    SEC3: `sanitize_lore` EVERY author-authored string. Stricter than gather_arc's need, not
    looser — motifs can be MINED from imported third-party text (`source`/`imported_derived`,
    models.py:519-521), so the delimiter-forging surface is LARGER here.

    CAPPED: see _MOTIF_BEAT_CAP / _MOTIF_SUMMARY_CHARS above.
    """
    try:
        apps = await applications_repo.by_nodes(project_id, [node_id])
        if not apps:
            return ""
        app = apps[-1]  # last-wins on a re-bind (created_at ASC)
        if app.motif_id is None:  # the motif was archived → SET NULL
            return ""
        m = await motif_repo.get_visible(user_id, app.motif_id)
    except Exception:  # noqa: BLE001 — the motif frame degrades; never fail a pack
        logger.warning("gather_motif resolve failed", exc_info=True)
        return ""
    if m is None:  # archived / foreign motif — degrade silently (no existence oracle)
        return ""

    annotations = getattr(app, "annotations", None) or {}
    beats = list(getattr(m, "beats", None) or [])
    lines: list[str] = []

    # 1. THE MOTIF — what pattern this scene is executing.
    name = _clip(str(getattr(m, "name", "") or ""), summary_chars) or "(untitled)"
    kind = _clip(str(getattr(m, "kind", "") or "sequence"), 40)
    lines.append(f'Motif: "{name}" ({kind})')
    summary = _clip(str(getattr(m, "summary", "") or ""), summary_chars)
    if summary:
        lines.append(f"Motif intent: {summary}")

    # 2. THE BOUND BEAT — the scene's target shape within the motif.
    beat_key = annotations.get("beat_key")
    bound_beat: dict[str, Any] | None = None
    if beat_key:
        bound_beat = next(
            (b for b in beats if str(b.get("key")) == str(beat_key)), None)
    if bound_beat is not None:
        label = _clip(str(bound_beat.get("label") or ""), summary_chars)
        intent = _clip(str(bound_beat.get("intent") or ""), summary_chars)
        lines.append(f"Beat: {label} — {intent}" if intent else f"Beat: {label}")
        tension = bound_beat.get("tension_target")
        if tension is not None:
            lines.append(f"Tension target: {int(tension)}/5")
    elif beats:
        # No beat bound → give the drafter the motif's SHAPE (capped: a motif may carry
        # dozens of beats and this block is outside the budget).
        ordered = sorted(beats, key=lambda b: b.get("order") or 0)[:beat_cap]
        shape = "; ".join(
            _clip(str(b.get("label") or b.get("key") or ""), 60) for b in ordered
        )
        if shape:
            lines.append(f"Motif shape: {shape}")

    # 3. REVERSAL / ALLIANCE SHIFT — from the application, else the bound beat (§15.2).
    for key, label in (("reversal", "Reversal"), ("alliance_shift", "Alliance shift")):
        val = annotations.get(key) or (bound_beat or {}).get(key)
        if val:
            lines.append(f"{label}: {_clip(str(val), summary_chars)}")

    # 4. ROLES — role_key → entity, rendered exactly like gather_arc's "Cast bindings".
    #    An UNRESOLVED role (set_role_binding writes JSON null) is RENDERED, never dropped:
    #    silence would read to the drafter as "no such role" (fe-status-default-fallback).
    role_parts: list[str] = []
    for role_key, entity_id in (getattr(app, "role_bindings", None) or {}).items():
        rk = _clip(str(role_key), 60)
        if not rk:
            continue
        ev = _clip(str(entity_id), 80) if entity_id else ""
        role_parts.append(f"{rk} → {ev}" if ev else f"{rk} → (unresolved)")
    if role_parts:
        lines.append("Motif roles: " + "; ".join(role_parts))

    return "\n".join(lines)


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
