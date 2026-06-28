"""W10 — materialize an arc-apply PLAN into a committable arc→chapter→scene spec
(D-W10-APPLY-PLANNER-MATERIALIZE). The PURE/deterministic counterpart to `arc_apply`:
where `build_apply_plan` rescales placements into the target chapter range (preview),
this turns those placements into the actual outline the A3 commit-path persists.

DETERMINISTIC — NO LLM. It reuses the frozen W2 bound-chapter engine
(`scenes_from_motif`/`build_application_rows`/`bind_motif`, all no-LLM: "the motif IS
the structure"). The richer per-scene prose is the EXISTING downstream generate path.

Beat → chapter distribution (the one design choice): a placement spans chapters [s..e]
and its motif has beats [b0..b(n-1)]. EVERY beat is distributed across the span (no beat
lost, §12.6 spirit) — beat j lands in chapter `s + floor(j*w/n)` (w = e-s+1), grouped per
chapter. Degenerate: w=1 → all beats in one chapter (== decompose); n≤w → ≤1 beat/chapter.

The router resolves each placement's Motif (by id/code) via the DB and passes them in
parallel to `plan.placements`; this module never touches the DB. Output is CHAPTER-INDEX
based (1-based) — the router maps indices → the book's real chapter_ids + story_order.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.db.models import ArcApplyPlan, Motif


@dataclass
class MaterializeScene:
    title: str
    synopsis: str
    tension: int
    present_entity_ids: list[str]
    application_row: dict[str, Any]          # the motif_application ledger payload (no node id yet)


@dataclass
class MaterializeChapter:
    chapter_index: int                       # 1-based target chapter (→ book chapter by the router)
    scenes: list[MaterializeScene]


@dataclass
class MaterializeSpec:
    chapters: list[MaterializeChapter] = field(default_factory=list)
    # placements that produced NO scenes — NEVER silently dropped (§11/§12.6).
    unresolved_placements: list[dict[str, Any]] = field(default_factory=list)
    scenes_total: int = 0
    beats_distributed: int = 0


def _distribute_beats(n_beats: int, span_start: int, span_end: int) -> dict[int, list[int]]:
    """Map every beat index [0..n_beats-1] to a 1-based chapter in [span_start..span_end],
    grouped per chapter. beat j → span_start + floor(j*w/n) (w = span width). Returns
    {chapter_index: [beat_index,…]} preserving beat order within a chapter."""
    s = min(span_start, span_end)
    e = max(span_start, span_end)
    w = e - s + 1
    out: dict[int, list[int]] = {}
    if n_beats <= 0 or w <= 0:
        return out
    for j in range(n_beats):
        offset = (j * w) // n_beats          # floor; j<n ⇒ offset ≤ w-1
        if offset >= w:
            offset = w - 1
        out.setdefault(s + offset, []).append(j)
    return out


def _resolve_roster(
    roster_bindings: dict[str, Any], cast_index: dict[str, str],
) -> dict[str, str]:
    """Arc roster {role_key: cast_NAME} → {role_key: entity_id} via the book's folded
    cast index. A name that matches no cast member is dropped (the role stays bound by
    the motif's own name-hint resolution, or surfaces unresolved) — never invented."""
    out: dict[str, str] = {}
    for key, val in roster_bindings.items():
        if isinstance(val, str) and val.strip():
            eid = cast_index.get(val.strip().casefold())
            if eid is not None:
                out[str(key)] = eid
    return out


def build_materialize_spec(
    plan: ArcApplyPlan,
    resolved_motifs: list[Motif | None],
    *,
    cast_index: dict[str, str],
    cast_names: dict[str, str],
    roster_bindings: dict[str, Any],
    arc_template_id: str,
    k_ceiling: int,
    high_threshold: int,
    min_scenes: int,
    max_scenes: int,
) -> MaterializeSpec:
    """Assemble the deterministic materialize spec. `resolved_motifs[i]` is the Motif for
    `plan.placements[i]` (or None when the router couldn't resolve it). Pure — same inputs
    → byte-identical spec."""
    from app.engine.motif_select import (
        MotifBinding, SelectedMotif, bind_motif, build_application_rows, scenes_from_motif,
    )
    from app.engine.plan import ChapterPlan

    roster_resolved = _resolve_roster(roster_bindings, cast_index)
    # accumulate scenes per 1-based chapter index, in placement order (thread/ord stable).
    per_chapter: dict[int, list[MaterializeScene]] = {}
    spec = MaterializeSpec()

    # placements ordered as the plan emitted them (ord-then-span, deterministic).
    for placement, motif in zip(plan.placements, resolved_motifs):
        code = placement.motif_code
        thread = placement.thread
        if motif is None:
            spec.unresolved_placements.append(
                {"motif_code": code, "thread": thread, "reason": "motif_not_visible"})
            continue
        beats = sorted(motif.beats, key=lambda b: b.get("order", 0))
        if not beats:
            spec.unresolved_placements.append(
                {"motif_code": code, "thread": thread, "reason": "motif_has_no_beats"})
            continue

        # bind the motif's roles to the book cast (name-hints), then let the arc roster
        # (bound once, by name) OVERRIDE any motif role key it covers (§12.5).
        ch_full = ChapterPlan(chapter_id="", title="", sort_order=0, beat_role=None, intent="")
        base = bind_motif(SelectedMotif(motif=motif, score=1.0, match_reason={}),
                          cast_index, ch_full)
        motif_role_keys = {r.get("key") for r in motif.roles if r.get("key")}
        merged_role_bindings = dict(base.role_bindings)
        for key, eid in roster_resolved.items():
            if key in motif_role_keys:
                merged_role_bindings[key] = eid
        binding = MotifBinding(
            role_bindings=merged_role_bindings,
            unresolved_roles=[k for k in base.unresolved_roles if k not in roster_resolved],
            annotations=dict(base.annotations),
            warning=base.warning,
        )

        distribution = _distribute_beats(len(beats), placement.span_start, placement.span_end)
        for chapter_index, beat_idxs in sorted(distribution.items()):
            subset = [beats[j] for j in beat_idxs]
            spec.beats_distributed += len(subset)
            sub_motif = motif.model_copy(update={"beats": subset})
            sel = SelectedMotif(motif=sub_motif, score=1.0, match_reason={})
            ch = ChapterPlan(chapter_id=str(chapter_index), title="", sort_order=chapter_index,
                             beat_role=None, intent="")
            scenes = scenes_from_motif(
                sel, binding, ch, k_ceiling=k_ceiling, high_threshold=high_threshold,
                min_scenes=min_scenes, max_scenes=max_scenes, cast_names=cast_names)
            rows = build_application_rows(sel, binding, scenes)
            bucket = per_chapter.setdefault(chapter_index, [])
            for sc, row in zip(scenes, rows):
                row_ann = dict(row.get("annotations", {}))
                row_ann["arc_template_id"] = arc_template_id
                row_ann["thread"] = thread
                row = {**row, "annotations": row_ann}
                bucket.append(MaterializeScene(
                    title=sc.title, synopsis=sc.synopsis, tension=sc.tension,
                    present_entity_ids=list(sc.present_entity_ids), application_row=row))

    for chapter_index in sorted(per_chapter):
        scenes = per_chapter[chapter_index]
        spec.scenes_total += len(scenes)
        spec.chapters.append(MaterializeChapter(chapter_index=chapter_index, scenes=scenes))
    return spec
