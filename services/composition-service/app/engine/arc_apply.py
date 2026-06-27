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

SCOPE (deliberately bounded — W10 BACKEND): this is the placement MATH only. It does
NOT materialize `outline_node` rows, write a `motif_application` ledger, or invoke the
LLM planner — that deep planner integration is the W10 live-smoke / follow-up
(D-W10-APPLY-PLANNER-MATERIALIZE). The router exposes this as an `apply`-preview that
returns the plan; nothing is persisted here. No DB / no provider call (pure function).
"""

from __future__ import annotations

from app.db.models import (
    ArcApplyArgs,
    ArcApplyPlan,
    ArcTemplate,
    DropMergeEntry,
    ResolvedPlacement,
)


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
