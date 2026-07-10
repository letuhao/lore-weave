"""W2 — the ONE motif select + bind/swap/undo engine (Narrative Motif Library).

This module is the SOLE owner of the bind/swap/undo logic. W4's MCP tool
`composition_motif_bind` IMPORTS `apply_motif_swap`/`undo_motif_swap` from here and
adapts the envelope to it — it never re-implements the bind logic (00-RECONCILE §2,
"one engine, two entries"). W2's HTTP `PATCH …/outline/{node}/motif` is the second
entry. Both call the SAME functions frozen here.

Pipeline (W2 doc §2): retrieve → select(adaptive-K aware) → bind(role→cast) →
scenes_from_motif(beats → ScenePlan, NO LLM) → motif_application rows (the binding
ledger; W2 is the sole writer — W5's conformance trace JOINs on these rows per
scene `outline_node_id`, reading motif_id/motif_version/role_bindings + beat_key
folded into `annotations`).

`MotifRetriever.retrieve` is IMPLEMENTED (W3 landed — SQL pre-filter → platform-embed
query → cosine → match_reason → degrade, in `db/repositories/motif_retrieve.py`). This
engine consumes only the FROZEN F0 signature, so it is agnostic to that implementation.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import UUID

import asyncpg

from app.db.models import Motif, MotifCandidate
from app.engine.adaptive_k import (
    HIGH_WEIGHT_BEATS,
    adaptive_k,
    motif_tension_to_scale,
)

if TYPE_CHECKING:  # avoid an import cycle through plan.py at module load
    from app.engine.plan import ChapterPlan, ChapterScenes, ScenePlan


class MotifSwapError(Exception):
    """A swap target was not accessible (wrong project / not a chapter node / not
    found). The HTTP router + MCP tool map this to a uniform 'not found or not
    accessible' (H13 — no enumeration oracle). Kept framework-agnostic so both
    entries (W2 HTTP, W4 MCP) translate it to their own error shape."""

logger = logging.getLogger(__name__)

# Default connective-beat floor margin: a non-high-weight (connective) beat must
# clear `min_score + this` to earn a motif, so the library does not carpet-bomb
# every transition with a trope (W2 doc §2.2 / MD-3; config.motif_connective_floor_margin).
_DEFAULT_CONNECTIVE_FLOOR_MARGIN = 0.08

# {role_key} placeholder in a beat intent → substituted with the bound cast member's
# display name (or the role label when unbound).
_ROLE_TOKEN_RE = re.compile(r"\{([a-zA-Z0-9_]+)\}")


class MotifRetrieverError(Exception):
    """Infra failure raised by W3's retrieve() (distinct from an empty result []).
    W2 catches it and falls back to the invent path with a distinct warning token so
    an outage doesn't look like an empty library (W2 doc §2.4)."""


@dataclass(frozen=True)
class SelectedMotif:
    motif: Motif
    score: float
    match_reason: dict[str, Any]   # {tension, genre, precond, cosine}


@dataclass(frozen=True)
class MotifBinding:
    role_bindings: dict[str, str]        # {role_key: glossary_entity_id}
    unresolved_roles: list[str]          # role_keys whose hint matched no cast member
    annotations: dict[str, Any]          # bound info_asymmetry / reversal / alliance_shift
    warning: str | None                  # 'partial_role_bind' when unresolved, else None


# ── SELECT ──────────────────────────────────────────────────────────────

def _chapter_intent_tension(beat_role: str | None, high_threshold: int) -> int | None:
    """A coarse chapter-level tension to feed retrieve()'s tension arg, derived from
    the beat_role weight (no per-scene tension yet — scenes don't exist until bind).
    HIGH_WEIGHT_BEATS → high (clears the gate so retrieve prefers high-tension
    motifs); else mid. None when no beat_role (selection is gated on beat_role
    anyway). This proxy is DISCARDED after selection — only the bound motif's
    per-beat tensions become scene tensions (W2 doc §3.3, no double-counting)."""
    if beat_role is None:
        return None
    return high_threshold + 15 if beat_role.strip().lower() in HIGH_WEIGHT_BEATS \
        else high_threshold // 2


def _pick_top1(cands: list[MotifCandidate]) -> MotifCandidate:
    """Deterministic top-1 over the retrieve()-ranked list (W2 doc §5 — audit
    reproducibility). Total order: score desc, mining_support desc, judge_score desc,
    code asc. `code` is unique-within-tier + stable, so it is the always-unique
    backstop that guarantees a total order even when score/support/judge all tie (a
    clone shares its source's content) — never rely on list/DB order."""
    return min(cands, key=lambda c: (
        -c.score,
        -(c.motif.mining_support or 0),
        -float(c.motif.judge_score or 0),
        c.motif.code,
    ))


async def select_motif_for_chapter(
    ch: "ChapterPlan", retriever: Any, *,
    book_id: UUID, project_id: UUID, caller_id: UUID,
    genre_tags: list[str], language: str,
    prev_effects: list[str],
    min_score: float,
    high_threshold: int,
    connective_floor_margin: float = _DEFAULT_CONNECTIVE_FLOOR_MARGIN,
    applied_counts: dict[str, int] | None = None,
    max_reapply: int = 0,
) -> SelectedMotif | None:
    """RETRIEVE then SELECT one motif (top-1) for a chapter, or None to fall back.

    SELECT is adaptive-K-aware (W2 doc §2.2): a HIGH-tension beat WANTS a motif (it
    is exactly where invent fails); a CONNECTIVE beat must clear a higher bar (a weak
    fit on a connective beat → stay free-form: invent reads better than a forced
    cliché). Anti-repetition (§7.6): a motif already applied >= max_reapply times in
    THIS book is dropped (deprioritized below the floor) so one trope doesn't carpet
    the book.

    Returns None on: retrieve empty ([]), retrieve errored (MotifRetrieverError),
    top score < floor, or the chosen motif over the anti-repetition cap. The caller
    (plan.py) maps each None to the matching fallback warning token (§2.4)."""
    chapter_tension = _chapter_intent_tension(ch.beat_role, high_threshold)

    try:
        cands = await retriever.retrieve(
            caller_id, book_id=book_id, project_id=project_id,
            genre_tags=genre_tags, language=language,
            beat_role=ch.beat_role, tension=chapter_tension, prev_effects=prev_effects,
        )
    except MotifRetrieverError as exc:
        logger.warning("motif retrieve errored for chapter %s → invent fallback: %s",
                       ch.chapter_id, exc)
        return None
    # Defense-in-depth over W3's SQL status filter: never bind a non-active motif
    # (a draft awaiting review must not auto-bind into a plan — W2 doc §5.2).
    cands = [c for c in (cands or []) if c.motif.status == "active"]
    if not cands:
        return None

    top = _pick_top1(cands)

    # Anti-repetition cap (§7.6): drop a motif already at/over the per-book cap.
    if max_reapply > 0 and applied_counts:
        if applied_counts.get(str(top.motif.id), 0) >= max_reapply:
            logger.info("motif %s at anti-repetition cap (%d) for book → fallback",
                        top.motif.code, max_reapply)
            return None

    is_high = (ch.beat_role or "").strip().lower() in HIGH_WEIGHT_BEATS
    floor = min_score if is_high else max(min_score, min_score + connective_floor_margin)
    if top.score < floor:
        return None
    return SelectedMotif(motif=top.motif, score=top.score, match_reason=top.match_reason)


# ── BIND ────────────────────────────────────────────────────────────────

def _resolve_role(hints: list[str], cast_index: dict[str, str]) -> str | None:
    """First cast id whose folded name matches one of the role's name hints, else
    None (unbound → surfaced, never invented — the no-silent-inference rule)."""
    for h in hints:
        if not isinstance(h, str) or not h.strip():
            continue
        eid = cast_index.get(h.strip().casefold())
        if eid is not None:
            return eid
    return None


def _bind_annotations(motif: Motif, role_bindings: dict[str, str]) -> dict[str, Any]:
    """Resolve the motif's scheme annotations (§15) to bound entity ids where the
    annotation references role keys. info_asymmetry {knows,deceived,gap}: role keys
    in knows/deceived are mapped to their bound entity id (an unbound key is left as
    the abstract key). reversal/alliance_shift live per-beat and are folded per scene
    in build_application_rows; here we only lift the motif-level info_asymmetry."""
    out: dict[str, Any] = {}
    info = motif.info_asymmetry
    if isinstance(info, dict) and info:
        out["info_asymmetry"] = {
            "knows": [role_bindings.get(k, k) for k in (info.get("knows") or [])],
            "deceived": [role_bindings.get(k, k) for k in (info.get("deceived") or [])],
            "gap": info.get("gap", ""),
        }
    return out


def bind_motif(sel: SelectedMotif, cast_index: dict[str, str], ch: "ChapterPlan") -> MotifBinding:
    """Bind each motif role to a book cast entity by NAME HINT (label + constraints),
    via the same folded-name resolution present-entities use. An unbound role is
    SURFACED (unresolved_roles), never invented as an id. A partial bind is NOT a
    failure (W2 doc §2.3): the chapter still binds, flagged 'partial_role_bind'."""
    role_bindings: dict[str, str] = {}
    unresolved: list[str] = []
    for role in sel.motif.roles:
        key = role.get("key")
        if not key:
            continue
        hints = [h for h in (role.get("label"), *(role.get("constraints") or []))
                 if isinstance(h, str)]
        eid = _resolve_role(hints, cast_index)
        if eid is not None:
            role_bindings[key] = eid
        else:
            unresolved.append(key)
    annotations = _bind_annotations(sel.motif, role_bindings)
    warning = "partial_role_bind" if unresolved else None
    return MotifBinding(role_bindings=role_bindings, unresolved_roles=unresolved,
                        annotations=annotations, warning=warning)


# ── SCENES (beats → ScenePlan, no LLM) ──────────────────────────────────

def _role_label(motif: Motif, key: str) -> str:
    for role in motif.roles:
        if role.get("key") == key:
            return role.get("label") or key
    return key


def _render_beat_synopsis(
    beat: dict[str, Any], motif: Motif, binding: MotifBinding,
    cast_names: dict[str, str],
) -> str:
    """Substitute {role_key} tokens in the beat intent with the bound cast member's
    display NAME (resolved from the entity id) when bound, else the role's abstract
    label (graceful — matches the partial-bind flag). cast_names maps entity_id →
    display name."""
    intent = beat.get("intent") or beat.get("label") or ""

    def repl(m: "re.Match[str]") -> str:
        key = m.group(1)
        eid = binding.role_bindings.get(key)
        if eid is not None and eid in cast_names:
            return cast_names[eid]
        return _role_label(motif, key)

    return _ROLE_TOKEN_RE.sub(repl, intent)


def scenes_from_motif(
    sel: SelectedMotif, binding: MotifBinding, ch: "ChapterPlan", *,
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
    cast_names: dict[str, str] | None = None,
) -> list["ScenePlan"]:
    """One ScenePlan per motif beat (ordered), clamped to max_scenes. tension is the
    beat's tension_target reconciled 1..5 → 0..100; suggested_k uses the SAME
    adaptive_k as invent on that reconciled tension + the chapter beat_role. NO LLM —
    a bound chapter is O(1) DB-shaped work, not a generation (the latency/cost win).
    Under-fill (beats < min_scenes) is NOT padded — the motif IS the structure."""
    from app.engine.plan import ScenePlan  # local: avoid the import cycle

    cast_names = cast_names or {}
    beats = sorted(sel.motif.beats, key=lambda b: b.get("order", 0))[:max(0, max_scenes)]
    present_ids = list(binding.role_bindings.values())
    out: list[ScenePlan] = []
    for b in beats:
        tens5 = b.get("tension_target")
        tension = motif_tension_to_scale(tens5, fallback=sel.motif.tension_target)
        out.append(ScenePlan(
            title=(b.get("label") or b.get("intent") or "")[:60],
            synopsis=_render_beat_synopsis(b, sel.motif, binding, cast_names),
            tension=tension if tension is not None else 50,  # A3 neutral default
            present_entity_ids=present_ids,
            present_entity_names_unresolved=[],
            suggested_k=adaptive_k(ch.beat_role, tension, k_ceiling=k_ceiling,
                                   high_threshold=high_threshold),
        ))
    return out


# ── motif_application rows (W2 is the sole writer) ──────────────────────

def build_application_rows(
    sel: SelectedMotif, binding: MotifBinding, scenes: list["ScenePlan"],
) -> list[dict[str, Any]]:
    """Build one persistable motif_application payload PER bound scene (W5's trace
    JOINs `motif_application` on the scene `outline_node_id`). Each row pins the
    motif_version (the trace shows what was bound, not live — edge-F3), carries the
    role_bindings, and folds the bound `beat_key` + any per-beat reversal/
    alliance_shift into `annotations` (no F0 schema column needed — W5 MD-3 reads
    beat_key from annotations, degrading to motif-level when absent).

    The scene→beat correspondence is positional: scenes_from_motif emits one scene
    per ordered beat, so scene[i] ↔ ordered-beat[i]. `outline_node_id` is filled by
    the commit/swap caller once the scene nodes exist (preview is non-persisted)."""
    ordered_beats = sorted(sel.motif.beats, key=lambda b: b.get("order", 0))[:len(scenes)]
    rows: list[dict[str, Any]] = []
    for beat in ordered_beats:
        ann = dict(binding.annotations)
        ann["beat_key"] = beat.get("key")
        # D-MOTIF-FE-PLANNERVIEW-WIRING (GAP-1): persist the plan-time match_reason
        # ({tension,genre,precond,cosine}) so a POST-commit binding read can render the
        # MatchReasonChip — without it the chip degrades to empty on a re-read. Additive
        # JSONB key; existing readers (W5 trace reads beat_key) ignore it.
        if sel.match_reason:
            ann["match_reason"] = dict(sel.match_reason)
        if beat.get("reversal") is not None:
            ann["reversal"] = beat["reversal"]
        if beat.get("alliance_shift") is not None:
            ann["alliance_shift"] = beat["alliance_shift"]
        rows.append({
            "motif_id": str(sel.motif.id),
            "motif_version": sel.motif.version,
            "role_bindings": dict(binding.role_bindings),
            "annotations": ann,
        })
    return rows


# ── cost aggregate (post-bind K distribution, for the confirm card) ─────

def estimate_diverge_budget(chapters: list["ChapterScenes"]) -> dict[str, int]:
    """Σ suggested_k over all scenes (the diverge candidate count = the cost driver),
    split bound vs invented, so the generate confirm card reflects the POST-BIND K
    (W2 doc §3.4). Pure — no I/O. A chapter is 'bound' iff it carries a motif."""
    bound_k = invent_k = scene_count = 0
    for cs in chapters:
        is_bound = getattr(cs, "motif", None) is not None
        for sc in cs.scenes:
            scene_count += 1
            if is_bound:
                bound_k += sc.suggested_k
            else:
                invent_k += sc.suggested_k
    return {
        "total_k": bound_k + invent_k,
        "bound_k": bound_k,
        "invent_k": invent_k,
        "scene_count": scene_count,
    }


# ── SWAP / UNDO (the honored Tier-A undo; §R2.6 / audit H-4) ────────────

@dataclass
class SwapResult:
    chapter_node_id: str
    archived_scene_ids: list[str]            # the prior scenes (now archived — prose preserved)
    new_scene_ids: list[str]                 # the freshly created scenes for the new motif
    orphaned_thread_ids: list[str]           # open threads anchored at an archived scene (SURFACED, not closed)
    new_motif_id: str | None                 # None on a clear-motif (swap to nothing)
    undo_token: dict[str, Any]               # bundles exactly what undo needs (idempotent inverse)


async def _scene_ids_for_chapter(
    conn: asyncpg.Connection, project_id: UUID, chapter_id: UUID,
    *, archived: bool,
) -> list[UUID]:
    """Active (or archived) scene-node ids for a chapter (by the shared chapter_id
    key — the replace-path shape), scoped to the project (access is gated on the
    book BEFORE this — 25 PM-8)."""
    rows = await conn.fetch(
        f"""
        SELECT id FROM outline_node
        WHERE project_id = $1 AND kind = 'scene'
          AND chapter_id = $2 AND is_archived = {'true' if archived else 'false'}
        """,
        project_id, chapter_id,
    )
    return [r["id"] for r in rows]


async def _set_scenes_archived(
    conn: asyncpg.Connection, project_id: UUID,
    scene_ids: list[UUID], *, archived: bool,
) -> None:
    """Flip is_archived on a scene id-set (symmetric archive/restore). Scoped to
    project + kind='scene'. The scenes' generation_job rows are NEVER deleted —
    archiving the node keeps the prose attached (FK is ON DELETE SET NULL but we
    never delete), so an un-archive restores the prose-bearing scenes losslessly."""
    if not scene_ids:
        return
    await conn.execute(
        """
        UPDATE outline_node SET is_archived = $3, updated_at = now()
        WHERE project_id = $1 AND kind = 'scene' AND id = ANY($2)
        """,
        project_id, scene_ids, archived,
    )


async def _open_threads_anchored_at(
    conn: asyncpg.Connection, project_id: UUID, scene_ids: list[UUID],
) -> list[UUID]:
    """Open/progressing narrative_thread ids whose promise (opened_at_node) is in the
    archived scene set — SURFACED for author review, NEVER auto-closed (§R2.6). A
    read-only SELECT (does not edit narrative_thread)."""
    if not scene_ids:
        return []
    rows = await conn.fetch(
        """
        SELECT id FROM narrative_thread
        WHERE project_id = $1 AND NOT is_archived
          AND status IN ('open', 'progressing')
          AND opened_at_node = ANY($2)
        """,
        project_id, scene_ids,
    )
    return [r["id"] for r in rows]


async def plan_swap(
    outline: Any, project_id: UUID, chapter_node_id: UUID,
    *, conn: asyncpg.Connection,
) -> dict[str, Any]:
    """Read-only preview of what a swap would archive + which threads it would orphan
    (for the confirm/undo UX). Does NOT mutate. Raises MotifSwapError if the node is
    not a chapter node in this project (H13)."""
    target = await outline.get_node(chapter_node_id, conn=conn)
    if target is None or target.project_id != project_id or target.kind != "chapter":
        raise MotifSwapError("chapter node not found or not accessible")
    scene_ids = await _scene_ids_for_chapter(conn, project_id, target.chapter_id,
                                             archived=False)
    orphaned = await _open_threads_anchored_at(conn, project_id, scene_ids)
    return {
        "chapter_node_id": str(chapter_node_id),
        "scene_ids_to_archive": [str(s) for s in scene_ids],
        "orphaned_thread_ids": [str(t) for t in orphaned],
    }


async def apply_motif_swap(
    outline: Any, applications: Any,
    project_id: UUID, book_id: UUID, chapter_node_id: UUID,
    *, created_by: UUID, new_motif: SelectedMotif | None, binding: MotifBinding | None,
    cast_names: dict[str, str] | None = None,
    k_ceiling: int, high_threshold: int, min_scenes: int, max_scenes: int,
    conn: asyncpg.Connection,
) -> SwapResult:
    """Swap a chapter's bound motif AFTER scenes may already have prose (§R2.6 / H-4).
    ONE transaction (the caller owns `conn`'s Tx):

      1. PROJECT-SCOPE the chapter node (get_node → assert project + kind) — IDOR guard
         (the same pattern mcp/server.py uses before archive_node).
      2. ARCHIVE the chapter's current SCENES (keep the chapter node) via the
         replace-path shape (kind='scene' AND chapter_id=…). Capture the ids FIRST
         (for undo + orphan-thread detection). The scenes' generation_job rows are
         UNTOUCHED → prose preserved, restorable.
      3. Drop the superseded binding-ledger rows for those scenes (history of the
         binding lives in the swap's undo_token; the prose stays on the archived
         nodes). The motif row itself is untouched.
      4. INSTANTIATE the new motif's scenes (scenes_from_motif) as FRESH scene nodes
         under the chapter; write the new motif_application rows. (clear-motif:
         new_motif=None → no new scenes, the chapter reverts to unplanned.)
      5. FLAG orphaned narrative_thread promises (open thread anchored at an archived
         scene) — SURFACED, never auto-closed.

    Returns a SwapResult whose undo_token makes undo_motif_swap an exact, idempotent
    inverse."""
    from app.engine.plan import ChapterPlan  # local: avoid the import cycle

    target = await outline.get_node(chapter_node_id, conn=conn)
    if target is None or target.project_id != project_id or target.kind != "chapter":
        raise MotifSwapError("chapter node not found or not accessible")

    archived_ids = await _scene_ids_for_chapter(conn, project_id,
                                                target.chapter_id, archived=False)
    orphaned = await _open_threads_anchored_at(conn, project_id, archived_ids)
    await _set_scenes_archived(conn, project_id, archived_ids, archived=True)
    await applications.delete_for_nodes(project_id, archived_ids, conn=conn)

    new_scene_ids: list[UUID] = []
    if new_motif is not None and binding is not None:
        ch = ChapterPlan(chapter_id=str(target.chapter_id), title=target.title or "",
                         sort_order=0, beat_role=target.beat_role, intent=target.goal or "")
        scenes = scenes_from_motif(
            new_motif, binding, ch, k_ceiling=k_ceiling, high_threshold=high_threshold,
            min_scenes=min_scenes, max_scenes=max_scenes, cast_names=cast_names or {},
        )
        rows = build_application_rows(new_motif, binding, scenes)
        for sc, row in zip(scenes, rows):
            node = await outline.create_node(
                project_id, created_by=created_by, kind="scene", parent_id=target.id,
                chapter_id=target.chapter_id, beat_role=target.beat_role,
                title=sc.title, synopsis=sc.synopsis, tension=sc.tension,
                present_entity_ids=[UUID(e) for e in sc.present_entity_ids],
                status="outline", conn=conn,
            )
            new_scene_ids.append(node.id)
            row["outline_node_id"] = str(node.id)
        await applications.insert_many(project_id, book_id, rows,
                                       created_by=created_by, conn=conn)

    undo_token = {
        "chapter_node_id": str(chapter_node_id),
        "archived_scene_ids": [str(s) for s in archived_ids],
        "new_scene_ids": [str(s) for s in new_scene_ids],
    }
    return SwapResult(
        chapter_node_id=str(chapter_node_id),
        archived_scene_ids=[str(s) for s in archived_ids],
        new_scene_ids=[str(s) for s in new_scene_ids],
        orphaned_thread_ids=[str(t) for t in orphaned],
        new_motif_id=str(new_motif.motif.id) if new_motif is not None else None,
        undo_token=undo_token,
    )


async def undo_motif_swap(
    outline: Any, applications: Any,
    project_id: UUID, undo_token: dict[str, Any],
    *, conn: asyncpg.Connection,
) -> dict[str, Any]:
    """Inverse of apply_motif_swap (the Tier-A _bind undo hint, made real — clears
    the MCP-R2 'unhonored undo' finding). undo_token = {chapter_node_id,
    archived_scene_ids, new_scene_ids}:
      1. ARCHIVE the swap's new scene nodes (+ drop their ledger rows).
      2. RESTORE the previously-archived scenes (un-archive the id-set → re-attaches
         the scenes AND their still-linked generation_job prose, never deleted).
    Net: the chapter is back to its pre-swap motif + prose, exactly. Idempotent —
    re-running with the same token archives already-archived new scenes (no-op) and
    restores already-active scenes (no-op)."""
    new_ids = [UUID(s) for s in undo_token.get("new_scene_ids", [])]
    archived_ids = [UUID(s) for s in undo_token.get("archived_scene_ids", [])]
    await _set_scenes_archived(conn, project_id, new_ids, archived=True)
    await applications.delete_for_nodes(project_id, new_ids, conn=conn)
    await _set_scenes_archived(conn, project_id, archived_ids, archived=False)
    return {
        "chapter_node_id": undo_token.get("chapter_node_id"),
        "restored_scene_ids": [str(s) for s in archived_ids],
        "removed_scene_ids": [str(s) for s in new_ids],
    }
