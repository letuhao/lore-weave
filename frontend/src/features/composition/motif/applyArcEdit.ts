// W10 arc-timeline — the PURE edit reducer + layout↔placement mapping. Both the
// desktop drag-grid AND the mobile stepper-list emit the frozen `ArcTimelineEdit`
// actions; this single deterministic function applies them, so the two surfaces can
// never diverge. No React, no IO — fully unit-testable in isolation (mirrors the
// backend's pure `arc_apply.build_apply_plan`).
import type { ArcPlacement, ArcThread, ArcTimelineEdit } from './arcTimelineContract';
import type { ArcLayoutEntry, ArcThreadEntry } from './arcTypes';

/** Clamp n into [lo, hi] (hi assumed ≥ lo). */
function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/** Read a backend `layout[]` into the contract's ArcPlacement[]. The backend stores
 *  no stable id (a layout entry is positional) — we synthesize one from the ORIGINAL
 *  index (`p${i}`) so it stays stable across in-session edits regardless of how the
 *  placement's thread/span later move. `motif_name` isn't persisted on a layout entry,
 *  so it falls back to the code for display. */
export function layoutToPlacements(layout: ArcLayoutEntry[]): ArcPlacement[] {
  return layout.map((e, i) => ({
    id: `p${i}`,
    motif_code: e.motif_code,
    motif_id: e.motif_id ?? null,
    motif_name: e.motif_code || '—',
    thread: e.thread,
    span_start: e.span_start,
    span_end: e.span_end,
    ord: e.ord ?? i,
  }));
}

/** Strip the contract placements back to the canonical backend `layout[]` shape (drop
 *  the synthetic id + display name; the backend ArcPlacement carries neither). Ord is
 *  renumbered per-thread by span order so the persisted layout stays canonical. */
export function placementsToLayout(placements: ArcPlacement[]): ArcLayoutEntry[] {
  const perThreadCount: Record<string, number> = {};
  const ordered = [...placements].sort(
    (a, b) => a.thread.localeCompare(b.thread) || a.span_start - b.span_start || a.ord - b.ord,
  );
  return ordered.map((p) => {
    const n = perThreadCount[p.thread] ?? 0;
    perThreadCount[p.thread] = n + 1;
    return {
      motif_code: p.motif_code,
      motif_id: p.motif_id,
      thread: p.thread,
      span_start: p.span_start,
      span_end: p.span_end,
      ord: n,
    };
  });
}

export function threadsToContract(threads: ArcThreadEntry[]): ArcThread[] {
  return threads.map((t) => ({ key: t.key, label: t.label || t.key, glyph: t.glyph }));
}

/** Generate a fresh placement id not colliding with the existing set. Deterministic
 *  given the set (uses the max numeric suffix + 1) so tests need no clock/random. */
function nextId(placements: ArcPlacement[]): string {
  let max = -1;
  for (const p of placements) {
    const m = /^p(\d+)$/.exec(p.id);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return `p${max + 1}`;
}

/** Translate a pointer drag-end into a `move` edit (or null for a no-op). The chapter
 *  delta is the horizontal drag distance measured in chapter-columns (rounded); the
 *  target thread is the row dropped onto. Pure so the geometry is unit-testable without
 *  simulating dnd-kit pointer events in jsdom. */
export function dragEndToMoveEdit(args: {
  placementId: string;
  fromThread: string;
  deltaX: number;
  trackWidth: number;
  cols: number;
  overThread: string | null;
}): ArcTimelineEdit | null {
  const { placementId, fromThread, deltaX, trackWidth, cols, overThread } = args;
  const chapterPx = trackWidth > 0 && cols > 0 ? trackWidth / cols : 0;
  const delta = chapterPx > 0 ? Math.round(deltaX / chapterPx) : 0;
  const toThread = overThread ?? fromThread;
  if (delta === 0 && toThread === fromThread) return null;   // no-op drag
  return { type: 'move', placement_id: placementId, to_thread: toThread, delta_chapters: delta };
}

/** Apply ONE frozen edit to the placement set, returning a NEW array (never mutates).
 *  All spans are clamped into [1..chapterSpan] and kept ordered (start ≤ end, width ≥ 1).
 *  Unknown placement ids are a no-op (the surface may emit stale ids mid-drag). */
export function applyArcEdit(
  placements: ArcPlacement[],
  edit: ArcTimelineEdit,
  chapterSpan: number,
): ArcPlacement[] {
  const hi = Math.max(1, chapterSpan);
  switch (edit.type) {
    case 'place': {
      const start = clamp(edit.span_start, 1, hi);
      const end = clamp(Math.max(edit.span_end, start), start, hi);
      const ordsInThread = placements.filter((p) => p.thread === edit.thread).map((p) => p.ord);
      const ord = ordsInThread.length ? Math.max(...ordsInThread) + 1 : 0;
      const created: ArcPlacement = {
        id: nextId(placements),
        motif_code: edit.motif_code,
        motif_id: null,
        motif_name: edit.motif_code || '—',
        thread: edit.thread,
        span_start: start,
        span_end: end,
        ord,
      };
      return [...placements, created];
    }
    case 'move': {
      return placements.map((p) => {
        if (p.id !== edit.placement_id) return p;
        const width = p.span_end - p.span_start;
        // width-preserving shift, then clamp the WHOLE span back inside the grid.
        let start = p.span_start + edit.delta_chapters;
        if (start < 1) start = 1;
        if (start + width > hi) start = hi - width;
        start = Math.max(1, start);
        return { ...p, thread: edit.to_thread, span_start: start, span_end: start + width };
      });
    }
    case 'resize': {
      return placements.map((p) => {
        if (p.id !== edit.placement_id) return p;
        if (edit.edge === 'end') {
          const end = clamp(p.span_end + edit.delta, p.span_start, hi);
          return { ...p, span_end: end };
        }
        const start = clamp(p.span_start + edit.delta, 1, p.span_end);
        return { ...p, span_start: start };
      });
    }
    case 'remove':
      return placements.filter((p) => p.id !== edit.placement_id);
    default:
      return placements;
  }
}
