"""W10 — arc-template APPLY as a PURE, deterministic function (§12.5).

"Write a new arc from this template" = decompose (§3.1) **at arc scale**:
  1. reconcile `chapter_span` → the user's target chapter count — **R2.5 proportional
     placement-rescale**: each `layout[]` placement's `[span_start, span_end]` (in
     template chapter coordinates [1..source_span]) is scaled into the target range
     [1..target], endpoints anchored (chapter 1 → 1, chapter source_span → target),
     monotonic, clamped. This is the A3 "B≠C reconciliation" at arc scale.
  2. bind `arc_roster` **ONCE** to the new book's cast (the apply args' roster_bindings)
     and **propagate** the resolved bindings to EVERY placement's role_bindings (a role
     recurs across many placements — bind it once, §12.2/§12.5). Roster slots with no
     binding supplied are surfaced in `unbound_roster_keys` — NEVER silently half-bound.
  3. place each thread's motifs across the target chapters + interleave per chapter
     (`chapter_interleave`: chapter_no → active placement ords).
  4. when the target is SMALLER than the source span, two same-thread placements may
     collapse onto identical chapters — the later one is **merged** into the earlier
     survivor and the fold is recorded in `drop_merge_report`. §12.6: a motif lost to a
     scale-mismatch is **NEVER silent**.

SCOPE (deliberately bounded — W10 BACKEND): `build_apply_plan` is the placement MATH
only. It does NOT materialize `outline_node` rows, write a `motif_application` ledger,
or invoke the LLM planner. The router exposes it as an `apply`-preview that returns the
plan; nothing is persisted there. No DB / no provider call (pure function).

──────────────────────────────────────────────────────────────────────────────────────
23 A5 (BA3) — the DURABLE spec layer on top of the pure math above. Two explicit,
snapshot round-trip ops between an `arc_template` (the library REGISTRY) and a
`structure_node` (the per-book SPEC):

  • `arc_apply(template, structure_node, …)` — template → spec. Rescales the template's
    `chapter_span` onto the arc's MEMBER chapters (`StructureRepo.member_chapter_ids`),
    binds the roster ONCE, materializes scenes under those chapters, and writes a
    `motif_application` ledger row per scene (real `motif_id`, pinned `motif_version`,
    `outline_node_id`, plus `structure_node_id`/`motif_code`/`thread` folded into
    annotations — BA5's first-class column write rides a sibling `insert_many` change,
    see interface note). CRUCIAL (BA3): the template's `pacing` curve is written INTO the
    member scenes' `outline_node.tension` — `pacing` is NOT stored on `structure_node`,
    it is DERIVED from tension. Reads `arc_template.threads` (old column — the rename is
    Deploy 2) and writes `structure_node.tracks` + `roster` + resolved `roster_bindings`
    + provenance (`arc_template_id`/`template_version`).

  • `arc_extract_template(structure_node, …)` — spec → template ("save my plan as a
    template"). The exact inverse: the arc's `motif_application` rows → `layout`, the
    member scenes' `tension` → the template's `pacing` curve, resolved `tracks` → `threads`
    (old template column), resolved `roster` → `arc_roster`. Returns a ready
    `ArcTemplateCreateArgs`; the caller persists it via `ArcTemplateRepo.create`.

These two are ASYNC orchestrators (they call `StructureRepo`/`OutlineRepo`/
`MotifApplicationRepo`), not pure functions. The router/MCP tool is a thin seam that
resolves the template, the spec node, the book cast, and the motifs, then calls them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable
from uuid import UUID

from app.db.models import (
    ArcApplyArgs,
    ArcApplyPlan,
    ArcPlacement,
    ArcRosterEntry,
    ArcTemplate,
    ArcTemplateCreateArgs,
    ArcThread,
    DropMergeEntry,
    Motif,
    ResolvedPlacement,
    StructureNode,
)
from app.engine.arc_materialize import _resolve_roster as _resolve_cast_bindings
from app.engine.arc_materialize import build_materialize_spec
from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

if TYPE_CHECKING:  # repos are injected — typed for readers, not imported at runtime
    from app.db.repositories.motif_application import MotifApplicationRepo
    from app.db.repositories.outline import OutlineRepo
    from app.db.repositories.structure import StructureRepo


def _rescale_span(
    span_start: int, span_end: int, *, source_span: int, target: int,
) -> tuple[int, int]:
    """R2.5 proportional rescale of one placement span from the template's chapter
    coordinates [1..source_span] into the target range [1..target].

    Endpoints are anchored: chapter 1 → 1, chapter `source_span` → `target` (so the
    arc still opens on chapter 1 and closes on the last chapter regardless of scale).
    A chapter c in between maps to round(1 + (c-1) * (target-1)/(source_span-1)). The
    result is clamped to [1..target] and ordered (start <= end). A degenerate
    source_span <= 1 maps everything to chapter 1 (no division by zero)."""
    target = max(1, target)
    source_span = max(1, source_span)

    def _map(c: int) -> int:
        c = max(1, c)
        if source_span <= 1 or target <= 1:
            return 1
        scaled = 1 + round((c - 1) * (target - 1) / (source_span - 1))
        return min(target, max(1, scaled))

    s = _map(span_start)
    e = _map(span_end)
    if s > e:
        s, e = e, s
    return s, e


def _resolve_roster(
    arc: ArcTemplate, supplied: dict[str, object],
) -> tuple[dict[str, object], list[str]]:
    """Bind the arc_roster ONCE: keep only bindings for roster keys that actually
    exist on the template (a stray key can't be smuggled in), and report roster slots
    that received no binding (`unbound`). Both returns are deterministic-ordered by the
    template's roster declaration order (§12.5: bind once, never silently half-bound)."""
    roster_keys = [str(r.get("key")) for r in arc.arc_roster if r.get("key")]
    bound: dict[str, object] = {}
    unbound: list[str] = []
    for key in roster_keys:
        if key in supplied:
            bound[key] = supplied[key]
        else:
            unbound.append(key)
    return bound, unbound


def build_apply_plan(arc: ArcTemplate, args: ArcApplyArgs) -> ArcApplyPlan:
    """Produce the deterministic apply plan (preview) for `arc` at `target_chapters`.

    Pure function: same inputs → byte-identical plan. No DB, no LLM, no persistence."""
    target = max(1, args.target_chapters)
    # chapter_span is a HINT (§12.2); absent → identity rescale against the target.
    source_span = arc.chapter_span if arc.chapter_span and arc.chapter_span > 0 else target

    roster_bindings, unbound_roster_keys = _resolve_roster(arc, dict(args.roster_bindings))

    # Stable processing order: as authored, but ord-then-span keeps merges deterministic.
    raw = list(arc.layout)
    indexed = sorted(
        enumerate(raw),
        key=lambda iv: (
            int(iv[1].get("ord", 0) or 0),
            int(iv[1].get("span_start", 0) or 0),
            iv[0],
        ),
    )

    placements: list[ResolvedPlacement] = []
    report: list[DropMergeEntry] = []
    # survivor index keyed by (thread, rescaled-start, rescaled-end) → the placement a
    # collapse folds INTO (§12.6 merge, same thread only — parallel threads never merge).
    survivors: dict[tuple[str, int, int], ResolvedPlacement] = {}

    for _orig_idx, p in indexed:
        thread = str(p.get("thread", ""))
        src_s = int(p.get("span_start", 1) or 1)
        src_e = int(p.get("span_end", src_s) or src_s)
        if src_e < src_s:
            src_s, src_e = src_e, src_s
        new_s, new_e = _rescale_span(src_s, src_e, source_span=source_span, target=target)
        code = str(p.get("motif_code", ""))
        key = (thread, new_s, new_e)

        existing = survivors.get(key)
        if existing is not None:
            # collapse onto an identical same-thread span → MERGE into the survivor.
            existing.merged_codes.append(code)
            report.append(DropMergeEntry(
                kind="merged",
                motif_code=code,
                thread=thread,
                src_span_start=src_s,
                src_span_end=src_e,
                into_motif_code=existing.motif_code,
                reason=(
                    f"target {target} < source span {source_span}: this placement "
                    f"rescaled onto chapters {new_s}..{new_e} already held by "
                    f"'{existing.motif_code}' on thread '{thread}'"
                ),
            ))
            continue

        rp = ResolvedPlacement(
            motif_code=code,
            motif_id=p.get("motif_id"),
            thread=thread,
            ord=int(p.get("ord", 0) or 0),
            src_span_start=src_s,
            src_span_end=src_e,
            span_start=new_s,
            span_end=new_e,
            role_hints=dict(p.get("role_hints", {}) or {}),
            role_bindings=dict(roster_bindings),   # bound ONCE → propagated identically
            triggers=list(p.get("triggers", []) or []),
            merged_codes=[],
        )
        survivors[key] = rp
        placements.append(rp)

    # per-chapter interleave: chapter_no (1-based, str key for JSONB) → active ords.
    interleave: dict[str, list[int]] = {}
    for ch in range(1, target + 1):
        active = [p.ord for p in placements if p.span_start <= ch <= p.span_end]
        if active:
            interleave[str(ch)] = active

    return ArcApplyPlan(
        arc_template_id=arc.id,
        source_chapter_span=source_span,
        target_chapters=target,
        threads=list(arc.threads),
        placements=placements,
        roster_bindings=roster_bindings,
        unbound_roster_keys=unbound_roster_keys,
        drop_merge_report=report,
        chapter_interleave=interleave,
    )


# ══════════════════════════════════════════════════════════════════════════════════
# 23 A5 (BA3) — template ⇄ spec round-trip (arc_apply / arc_extract_template)
# ══════════════════════════════════════════════════════════════════════════════════

# A resolver injected by the router/MCP seam: it turns each rescaled placement into its
# concrete Motif (preferring the pinned motif_id, falling back to a tier-merged code
# lookup), parallel to `placements`, None where neither resolves. Kept as an injection so
# this engine never re-imports MotifRepo / re-introduces a `user_id` (motif visibility is
# the deps/-registry's concern, resolved at the seam — see routers/plan._resolve_plan_motifs).
MotifResolver = Callable[[list[ResolvedPlacement]], Awaitable[list[Motif | None]]]


class ArcApplyError(Exception):
    """A non-conflict apply failure the router maps to a clean 4xx (400): the arc has no
    member chapters, or no placement resolved to a motif with beats. NEVER a 500."""

    def __init__(self, message: str, *, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


class ArcApplyConflict(Exception):
    """A member chapter already carries active scenes and `replace` was not set — the
    router maps this to 409 (resend with replace=true). Mirrors decompose's
    AlreadyPlannedError shape (chapter_ids) so the two apply paths report identically."""

    def __init__(self, chapter_ids: list[str]) -> None:
        super().__init__("member chapters already have scenes")
        self.chapter_ids = chapter_ids


@dataclass
class ArcApplyResult:
    structure_node_id: str
    arc_template_id: str
    template_version: int | None
    member_chapter_node_ids: list[str]          # the arc's member chapter OUTLINE nodes (order)
    scene_ids: list[str]                        # freshly materialized scene node ids
    motif_applications: int                     # ledger rows written
    scenes_total: int
    beats_distributed: int
    pacing_written: int                         # scenes whose tension came FROM the template pacing curve
    tracks: list[dict[str, Any]] = field(default_factory=list)          # written onto the spec node
    roster: list[dict[str, Any]] = field(default_factory=list)
    roster_bindings: dict[str, Any] = field(default_factory=dict)       # resolved {role_key: entity_id}
    unbound_roster_keys: list[str] = field(default_factory=list)
    unresolved_placements: list[dict[str, Any]] = field(default_factory=list)
    drop_merge_report: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ArcTemplateExtract:
    args: ArcTemplateCreateArgs                 # ready for ArcTemplateRepo.create(caller_id, args)
    member_chapter_node_ids: list[str]
    layout_placements: int                      # how many placements the ledger reconstructed
    pacing_chapters: int                        # member chapters that contributed a pacing point


def _extract_pacing_values(pacing: list[Any] | None) -> list[float | None]:
    """Tolerantly read a per-chapter numeric curve from the freeform `arc_template.pacing`
    JSONB (a list of bare numbers or `{tension|value|t}` dicts). Preserves length + order;
    an entry with no recoverable number becomes None (that chapter keeps its motif tension)."""
    out: list[float | None] = []
    for entry in pacing or []:
        v: float | None = None
        if isinstance(entry, (int, float)):
            v = float(entry)
        elif isinstance(entry, dict):
            for k in ("tension", "value", "t"):
                if isinstance(entry.get(k), (int, float)):
                    v = float(entry[k])
                    break
        out.append(v)
    return out


def _rescale_pacing(values: list[float | None], target: int) -> list[int | None]:
    """Resample the template's pacing curve onto `target` member chapters, endpoints
    anchored (chapter 1 → pacing[0], chapter target → pacing[-1]) — the SAME anchoring as
    `_rescale_span`, so pacing and placements stay aligned under a scale change. Nearest
    sample (pacing is a coarse authored curve, not a signal to interpolate). Empty curve →
    all-None (scenes then keep their motif-beat tension)."""
    if target <= 0:
        return []
    if not values:
        return [None] * target
    n = len(values)
    out: list[int | None] = []
    for j in range(target):
        idx = 0 if target == 1 else round(j * (n - 1) / (target - 1))
        idx = min(n - 1, max(0, idx))
        v = values[idx]
        out.append(int(round(v)) if v is not None else None)
    return out


def _as_uuid(value: Any) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


async def arc_apply(
    template: ArcTemplate,
    structure_node: StructureNode,
    *,
    created_by: UUID,
    structure_repo: "StructureRepo",
    outline_repo: "OutlineRepo",
    applications_repo: "MotifApplicationRepo",
    resolve_motifs: MotifResolver,
    cast_index: dict[str, str],
    cast_names: dict[str, str],
    roster_bindings: dict[str, Any] | None = None,
    k_ceiling: int,
    high_threshold: int,
    min_scenes: int,
    max_scenes: int,
    replace: bool = False,
) -> ArcApplyResult:
    """Apply an arc `template` onto an existing spec `structure_node` (an arc) — the
    template → spec snapshot (BA3).

    The arc's MEMBER chapters (`StructureRepo.member_chapter_ids`, in reading order) are
    the target: `build_apply_plan` rescales the template's `chapter_span` onto them,
    `build_materialize_spec` distributes each motif's beats across its rescaled span, and
    this function then (in ONE transaction):
      • materializes a scene `outline_node` per distributed beat under its member chapter,
      • writes each scene's `tension` FROM the template's rescaled `pacing` curve (BA3 —
        pacing is derived-from-tension, never stored on the spec), falling back to the
        motif-beat tension only where the template declares no pacing,
      • writes a `motif_application` ledger row per scene (real `motif_id`, pinned
        `motif_version`, `outline_node_id`, `role_bindings`; `structure_node_id` +
        `motif_code` + `thread` folded into `annotations` — the extract reads them back).
    Then it stamps the spec node: `tracks` ← template `threads` (old column name), `roster`
    ← template `arc_roster`, `roster_bindings` ← the once-bound {role_key: entity_id}, and
    provenance (`arc_template_id` + `template_version`).

    Raises ArcApplyError (→400) when the arc has no member chapters or nothing resolved,
    ArcApplyConflict (→409) when a member chapter already has scenes and `replace` is False.
    """
    supplied = dict(roster_bindings or {})

    member_node_ids = await structure_repo.member_chapter_ids(structure_node.id)
    if not member_node_ids:
        raise ArcApplyError(
            "arc has no member chapters — assign chapters to the arc first",
            detail={"code": "NO_MEMBER_CHAPTERS"},
        )
    # The member chapters as full outline nodes, positioned 1..N in reading order. Position
    # j is the target chapter index build_apply_plan/build_materialize_spec rescale onto.
    index_to_node: dict[int, Any] = {}
    for j, cid in enumerate(member_node_ids, start=1):
        node = await outline_repo.get_node(cid)
        if node is not None:
            index_to_node[j] = node
    target = len(member_node_ids)

    plan = build_apply_plan(
        template, ArcApplyArgs(target_chapters=target, roster_bindings=supplied))
    resolved = await resolve_motifs(plan.placements)
    code_by_id: dict[str, str] = {
        str(m.id): m.code for m in resolved if m is not None
    }

    spec = build_materialize_spec(
        plan, resolved,
        cast_index=cast_index, cast_names=cast_names,
        roster_bindings=plan.roster_bindings, arc_template_id=str(template.id),
        k_ceiling=k_ceiling, high_threshold=high_threshold,
        min_scenes=min_scenes, max_scenes=max_scenes,
    )
    if not spec.chapters:
        raise ArcApplyError(
            "no placement resolved to a motif with beats — nothing to apply",
            detail={"code": "NO_MATERIALIZABLE_PLACEMENTS",
                    "unresolved_placements": spec.unresolved_placements},
        )

    pacing_curve = _rescale_pacing(_extract_pacing_values(template.pacing), target)

    created_scene_ids: list[str] = []
    applied = 0
    pacing_written = 0

    # ONE transaction over the composition pool (shared by every repo): scene creation +
    # ledger writes are atomic. A replace archives the prior scenes + drops their ledger
    # rows in the same tx (StructureRepo's open_promises sets the `_pool` access precedent).
    pool = outline_repo._pool
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Replace guard, per member chapter (in-tx → no TOCTOU): a chapter with active
            # scenes blocks unless replace, in which case its prior scenes + their ledger
            # rows are archived/dropped (prose on archived scenes is preserved, never read).
            conflict: list[str] = []
            for node in index_to_node.values():
                existing = await conn.fetch(
                    """
                    SELECT id FROM outline_node
                    WHERE project_id = $1 AND chapter_id = $2 AND kind = 'scene'
                      AND NOT is_archived
                    """,
                    node.project_id, node.chapter_id,
                )
                existing_ids = [r["id"] for r in existing]
                if not existing_ids:
                    continue
                if not replace:
                    conflict.append(str(node.chapter_id))
                    continue
                await conn.execute(
                    "UPDATE outline_node SET is_archived = true, updated_at = now() "
                    "WHERE id = ANY($1) AND kind = 'scene'",
                    existing_ids,
                )
                await applications_repo.delete_for_nodes(
                    node.project_id, existing_ids, conn=conn)
            if conflict:
                raise ArcApplyConflict(sorted(conflict))

            for mc in spec.chapters:
                node = index_to_node.get(mc.chapter_index)
                if node is None:
                    continue
                pacing_tension = (
                    pacing_curve[mc.chapter_index - 1]
                    if mc.chapter_index - 1 < len(pacing_curve) else None
                )
                base = (node.story_order if node.story_order is not None
                        else mc.chapter_index) * STORY_ORDER_CHAPTER_STRIDE
                rows: list[dict[str, Any]] = []
                for i, sc in enumerate(mc.scenes):
                    tension = pacing_tension if pacing_tension is not None else sc.tension
                    if pacing_tension is not None:
                        pacing_written += 1
                    present = [u for u in (_as_uuid(e) for e in sc.present_entity_ids)
                               if u is not None]
                    scene = await outline_repo.create_node(
                        node.project_id, created_by=created_by, kind="scene",
                        parent_id=node.id, chapter_id=node.chapter_id,
                        beat_role=node.beat_role, title=sc.title, synopsis=sc.synopsis,
                        tension=tension, present_entity_ids=present,
                        story_order=base + i, status="outline", conn=conn,
                    )
                    created_scene_ids.append(str(scene.id))
                    row = dict(sc.application_row)
                    ann = dict(row.get("annotations", {}))
                    # BA5: pin the arc this binding realizes as a FIRST-CLASS column so
                    # arc conformance can read `WHERE structure_node_id = $arc` (23-A4).
                    # It also rides `annotations` — arc_extract_template reads it back from
                    # there, and it is the bridge the migration backfills FROM (mirroring
                    # the legacy annotations->>'arc_template_id'/'thread' pattern).
                    # `motif_code` lets extract rebuild `layout` without re-resolving motifs.
                    ann["structure_node_id"] = str(structure_node.id)
                    mid = row.get("motif_id")
                    if mid is not None and str(mid) in code_by_id:
                        ann["motif_code"] = code_by_id[str(mid)]
                    row["annotations"] = ann
                    row["structure_node_id"] = str(structure_node.id)   # BA5 first-class
                    row["outline_node_id"] = str(scene.id)
                    rows.append(row)
                if rows:
                    inserted = await applications_repo.insert_many(
                        node.project_id, structure_node.book_id, rows,
                        created_by=created_by, conn=conn)
                    applied += len(inserted)

    # Stamp the spec node from the template (metadata — a separate write; the scenes above
    # are the load-bearing, atomic core). tracks ← threads (old col), roster ← arc_roster,
    # roster_bindings ← the once-bound {role_key: entity_id}, + provenance. expected_version
    # None: apply is a deliberate snapshot, not an OCC-guarded field edit.
    resolved_bindings = _resolve_cast_bindings(plan.roster_bindings, cast_index)
    tracks = [dict(t) for t in (template.threads or [])]
    roster = [dict(r) for r in (template.arc_roster or [])]
    await structure_repo.update(
        structure_node.id,
        {
            "tracks": tracks,
            "roster": roster,
            "roster_bindings": resolved_bindings,
            "arc_template_id": template.id,
            "template_version": template.version,
        },
        expected_version=None,
    )

    return ArcApplyResult(
        structure_node_id=str(structure_node.id),
        arc_template_id=str(template.id),
        template_version=template.version,
        member_chapter_node_ids=[str(c) for c in member_node_ids],
        scene_ids=created_scene_ids,
        motif_applications=applied,
        scenes_total=spec.scenes_total,
        beats_distributed=spec.beats_distributed,
        pacing_written=pacing_written,
        tracks=tracks,
        roster=roster,
        roster_bindings=resolved_bindings,
        unbound_roster_keys=list(plan.unbound_roster_keys),
        unresolved_placements=spec.unresolved_placements,
        drop_merge_report=[d.model_dump(mode="json") for d in plan.drop_merge_report],
    )


async def arc_extract_template(
    structure_node: StructureNode,
    *,
    code: str,
    name: str,
    summary: str = "",
    genre_tags: list[str] | None = None,
    language: str = "en",
    visibility: str = "private",
    structure_repo: "StructureRepo",
    outline_repo: "OutlineRepo",
    applications_repo: "MotifApplicationRepo",
) -> ArcTemplateExtract:
    """Extract an `arc_template` FROM a spec `structure_node` — the spec → template
    snapshot ("save my plan as a template", BA3). The exact inverse of `arc_apply`:

      • `tracks`  → `threads`     (resolved root→leaf via StructureRepo.resolve_tracks;
                                   the old template column name — the rename is Deploy 2)
      • `roster`  → `arc_roster`  (resolved via StructureRepo.resolve_roster; bindings are
                                   book-specific, so they are dropped — a template is
                                   book-independent)
      • member scenes' `tension` → `pacing`  (per member chapter, avg tension → one curve
                                   point — the derived curve read back out, BA3)
      • `motif_application` rows → `layout`  (each row's scene chapter position gives the
                                   placement span; grouped by motif_code × thread — BA5:
                                   the ledger IS the realized layout)

    Returns a ready `ArcTemplateCreateArgs`; the caller persists it via
    `ArcTemplateRepo.create(caller_id, args)`. Pure read — writes nothing.

    NOTE (honest, non-silent): `layout` reflects the REALIZED span — where motifs actually
    landed — which can be narrower than a template's declared span when a motif had fewer
    beats than its span width (some span chapters got no scene). This matches BA5 ("the
    ledger is the layout"); it is not a bug.
    """
    tracks = await structure_repo.resolve_tracks(structure_node.id)
    roster = await structure_repo.resolve_roster(structure_node.id)

    member_node_ids = await structure_repo.member_chapter_ids(structure_node.id)

    # Per member chapter (in reading order): its scenes → a pacing point (avg tension), and
    # a scene_id → chapter_index map for the layout reconstruction. Group scene ids by their
    # Work so the ledger read stays project-scoped (a book may hold >1 Work — dị bản).
    pacing: list[dict[str, Any]] = []
    scene_index: dict[UUID, int] = {}
    scene_ids_by_project: dict[UUID, list[UUID]] = {}
    for j, cid in enumerate(member_node_ids, start=1):
        chapter = await outline_repo.get_node(cid)
        if chapter is None or chapter.chapter_id is None:
            continue
        scenes = await outline_repo.scenes_for_chapter(
            chapter.project_id, chapter.chapter_id)
        tensions = [s.tension for s in scenes if s.tension is not None]
        if tensions:
            pacing.append({"chapter_index": j,
                           "tension": int(round(sum(tensions) / len(tensions)))})
        for s in scenes:
            scene_index[s.id] = j
            scene_ids_by_project.setdefault(chapter.project_id, []).append(s.id)

    apps = []
    for project_id, sids in scene_ids_by_project.items():
        apps.extend(await applications_repo.by_nodes(project_id, sids))

    # Reconstruct layout: group ledger rows by (motif_code, thread); the span is the
    # min/max member-chapter index the motif's scenes landed in (BA5 — realized layout).
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    for app in apps:
        idx = scene_index.get(app.outline_node_id) if app.outline_node_id else None
        if idx is None:
            continue
        ann = app.annotations or {}
        thread = str(ann.get("thread") or "")
        motif_code = str(ann.get("motif_code") or (app.motif_id or ""))
        key = (motif_code, thread)
        g = groups.get(key)
        if g is None:
            groups[key] = {
                "motif_code": motif_code,
                "motif_id": app.motif_id,
                "thread": thread,
                "span_start": idx,
                "span_end": idx,
            }
        else:
            g["span_start"] = min(g["span_start"], idx)
            g["span_end"] = max(g["span_end"], idx)

    ordered = sorted(groups.values(),
                     key=lambda g: (g["span_start"], g["thread"], g["motif_code"]))
    layout = [
        ArcPlacement(
            motif_code=g["motif_code"], motif_id=g["motif_id"], thread=g["thread"],
            span_start=g["span_start"], span_end=g["span_end"], ord=ord_i,
        )
        for ord_i, g in enumerate(ordered)
    ]

    threads = [ArcThread(key=str(t.get("key") or ""), label=str(t.get("label") or ""))
               for t in tracks if t.get("key")]
    arc_roster = [
        ArcRosterEntry(
            key=str(r.get("key") or ""), actant=r.get("actant"),
            label=str(r.get("label") or ""),
            constraints=list(r.get("constraints") or []),
        )
        for r in roster if r.get("key")
    ]

    args = ArcTemplateCreateArgs(
        code=code, name=name, language=language, summary=summary,
        genre_tags=list(genre_tags or []),
        chapter_span=len(member_node_ids) or None,
        threads=threads, layout=layout, pacing=pacing, arc_roster=arc_roster,
        visibility=visibility,
    )
    return ArcTemplateExtract(
        args=args,
        member_chapter_node_ids=[str(c) for c in member_node_ids],
        layout_placements=len(layout),
        pacing_chapters=len(pacing),
    )


async def extract_template_from_arc(
    pool: Any, *, arc_node: StructureNode, owner_user_id: UUID,
    code: str, name: str, language: str = "en", visibility: str = "private",
) -> dict[str, Any]:
    """MCP/REST seam for `composition_arc_extract_template` (23 B2): run the spec→template
    snapshot and PERSIST it as a USER-tier `arc_template` in the caller's library.

    Thin wrapper over `arc_extract_template` (the pure orchestrator) + `ArcTemplateRepo.create`
    (the docstring above says "the caller persists it"). Returns the new template id + the
    reconstruction stats. A duplicate (owner, code, language) raises asyncpg.UniqueViolationError,
    which the caller maps to a 409 — this seam does not swallow it."""
    from app.db.repositories.arc_template_repo import ArcTemplateRepo
    from app.db.repositories.motif_application import MotifApplicationRepo
    from app.db.repositories.outline import OutlineRepo
    from app.db.repositories.structure import StructureRepo

    extract = await arc_extract_template(
        arc_node, code=code, name=name, language=language, visibility=visibility,
        structure_repo=StructureRepo(pool), outline_repo=OutlineRepo(pool),
        applications_repo=MotifApplicationRepo(pool),
    )
    template = await ArcTemplateRepo(pool).create(owner_user_id, extract.args)
    return {
        "success": True,
        "outcome": "extracted",
        "template_id": str(template.id),
        "member_chapter_node_ids": extract.member_chapter_node_ids,
        "layout_placements": extract.layout_placements,
        "pacing_chapters": extract.pacing_chapters,
    }


async def _resolve_plan_motifs(motifs_repo: Any, user_id: UUID, placements: list) -> list[Any]:
    """Resolve each placement's Motif (parallel to `placements`): pinned `motif_id` first
    (get_visible), else a tier-merged code lookup, None when neither resolves (the engine
    surfaces it as unresolved — no silent drop). Mirrors plan._resolve_plan_motifs."""
    codes_needing = [p.motif_code for p in placements if p.motif_id is None and p.motif_code]
    by_code = await motifs_repo.get_by_codes(user_id, codes_needing) if codes_needing else {}
    by_id: dict[UUID, Any] = {}
    for p in placements:
        if p.motif_id is not None and p.motif_id not in by_id:
            by_id[p.motif_id] = await motifs_repo.get_visible(user_id, p.motif_id)
    out: list[Any] = []
    for p in placements:
        out.append(by_id.get(p.motif_id) if p.motif_id is not None else by_code.get(p.motif_code))
    return out


async def apply_arc_to_spec(
    pool: Any,
    *,
    book_id: UUID,
    project_id: UUID,
    arc_template: "ArcTemplate",
    roster_bindings: dict[str, Any],
    replace: bool,
    idempotency_key: str | None,
    created_by: UUID,
    book_client: Any,
    kal_client: Any,
    motifs_repo: Any,
    outline_repo: Any,
    bearer: str,
) -> dict[str, Any]:
    """23 A5 (BA3) — the BOOK-level apply: materialize an arc TEMPLATE onto a book's EXISTING
    chapters as a committed arc→chapter→scene outline + a motif_application ledger. DETERMINISTIC
    (no LLM). The SHARED engine behind BOTH the REST route (POST /works/{id}/arc/materialize) and
    the MCP tool (composition_arc_apply) — the CALLER resolves + visibility-gates the arc and the
    book (VIEW/EDIT); this does the pure orchestration: fetch chapters → build_apply_plan →
    resolve motifs → cast → build_materialize_spec → commit → ledger. Raises ArcApplyError (guard
    failures / book-service down) or ArcApplyConflict (already-planned); NEVER a 500. Was inline
    in plan.materialize_arc — D-W10 dedupe so the agent (MCP) and the GUI (REST) share one path."""
    import logging
    import asyncpg
    from app.config import settings
    from app.clients.book_client import BookClientError
    from app.db.models import ArcApplyArgs
    from app.db.repositories import AlreadyPlannedError, ReferenceViolationError
    from app.db.repositories.motif_application import MotifApplicationRepo
    from app.engine.arc_materialize import build_materialize_spec
    from app.engine.chapter_gen import STORY_ORDER_CHAPTER_STRIDE

    logger = logging.getLogger(__name__)

    # 1 · the book's EXISTING chapters (cross-service; the IDOR/validation guards depend on this
    #     list — a book-service outage is a 502, never a silent skip).
    try:
        book_chapters = await book_client.list_chapters(book_id, bearer)
    except BookClientError as exc:
        raise ArcApplyError("book-service unavailable",
                            detail={"code": "BOOK_SERVICE_UNAVAILABLE", "detail": str(exc)})
    if not book_chapters:
        raise ArcApplyError("no chapters",
                            detail={"code": "NO_CHAPTERS",
                                    "detail": "materialize maps onto existing chapters — create chapters first"})
    if len(book_chapters) > settings.plan_max_chapters:
        raise ArcApplyError("too many chapters",
                            detail={"code": "TOO_MANY_CHAPTERS", "count": len(book_chapters),
                                    "max": settings.plan_max_chapters})

    chapters_sorted = sorted(book_chapters, key=lambda c: c.get("sort_order") or 0)
    target = len(chapters_sorted)

    plan = build_apply_plan(arc_template, ArcApplyArgs(
        target_chapters=target, roster_bindings=dict(roster_bindings)))
    resolved = await _resolve_plan_motifs(motifs_repo, created_by, plan.placements)

    # cast roster through the KAL (bounded-per-page, complete-in-aggregate).
    cast = await kal_client.roster(book_id, user_id=created_by)
    cast_index = {c["name"].strip().casefold(): c["entity_id"] for c in cast if c.get("name")}
    cast_names = {c["entity_id"]: c["name"] for c in cast}

    spec = build_materialize_spec(
        plan, resolved,
        cast_index=cast_index, cast_names=cast_names,
        roster_bindings=dict(roster_bindings), arc_template_id=str(arc_template.id),
        k_ceiling=settings.compose_diverge_k, high_threshold=settings.plan_high_tension_threshold,
        min_scenes=settings.plan_min_scenes_per_chapter, max_scenes=settings.plan_max_scenes_per_chapter,
    )
    if not spec.chapters:
        raise ArcApplyError("nothing materializable",
                            detail={"code": "NO_MATERIALIZABLE_PLACEMENTS",
                                    "detail": "no placement resolved to a motif with beats — nothing to commit",
                                    "unresolved_placements": spec.unresolved_placements})

    # the A3 commit spec (chapter_index → real chapter_id + story_order) + flat, chapter-major
    # ledger payloads (parallel to the scene_ids the commit returns).
    commit_chapters: list[dict[str, Any]] = []
    flat_app_rows: list[dict[str, Any]] = []
    for mc in spec.chapters:
        ch = chapters_sorted[mc.chapter_index - 1]
        sort_order = ch.get("sort_order") or 0
        scenes_spec: list[dict[str, Any]] = []
        for i, sc in enumerate(mc.scenes):
            present = []
            for eid in sc.present_entity_ids:
                try:
                    present.append(UUID(str(eid)))
                except (ValueError, TypeError):
                    continue
            scenes_spec.append({
                "title": sc.title, "synopsis": sc.synopsis, "tension": sc.tension,
                "present_entity_ids": present,
                "story_order": sort_order * STORY_ORDER_CHAPTER_STRIDE + i,
            })
            flat_app_rows.append(sc.application_row)
        commit_chapters.append({
            "chapter_id": UUID(str(ch["chapter_id"])), "title": ch.get("title", ""),
            "intent": "", "beat_role": None, "scenes": scenes_spec,
        })

    try:
        created = await outline_repo.commit_decomposed_tree(
            project_id, book_id=book_id, created_by=created_by, arc_title=arc_template.name,
            chapters=commit_chapters, replace=replace, idempotency_key=idempotency_key,
        )
    except AlreadyPlannedError as exc:
        raise ArcApplyConflict(sorted(str(c) for c in exc.chapter_ids))
    except ReferenceViolationError as exc:
        raise ArcApplyError("bad reference", detail={"code": "BAD_REFERENCE", "detail": exc.message})

    # ledger the bindings (positional with the flat scene_ids). NOT atomic with the tree Tx,
    # FK-tolerant (archived motif → soft-skip), skipped on an idempotency replay.
    applied = 0
    if not created.get("replay") and flat_app_rows:
        scene_ids = [UUID(s) for s in created["scene_ids"]]
        ledger_rows = [{**row, "outline_node_id": str(node_id)}
                       for row, node_id in zip(flat_app_rows, scene_ids)]
        if ledger_rows:
            try:
                await MotifApplicationRepo(pool).insert_many(
                    project_id, book_id, ledger_rows, created_by=created_by)
                applied = len(ledger_rows)
            except asyncpg.ForeignKeyViolationError:  # archived motif → soft-skip
                logger.warning("arc materialize: motif_application FK violation — ledger skipped")

    return {
        "arc_id": str(created["arc_id"]),
        "arc_template_id": str(arc_template.id),
        "chapter_ids": [str(i) for i in created["chapter_ids"]],
        "scene_ids": [str(i) for i in created["scene_ids"]],
        "motif_applications": applied,
        "scenes_total": spec.scenes_total,
        "beats_distributed": spec.beats_distributed,
        "unresolved_placements": spec.unresolved_placements,
        "drop_merge_report": [d.model_dump(mode="json") for d in plan.drop_merge_report],
        "replay": bool(created.get("replay")),
    }
