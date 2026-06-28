// W6 §5.4 — the ARC-TIMELINE INTERACTION CONTRACT (design-only, frozen in P1; the
// edit-grid itself is P4/W10). The arc-template timeline (mockup 05/06-B) is a
// thread × chapter drag-grid — the audit's "undesigned drag-grid (0 mobile/touch, 0
// keyboard)". W6 FREEZES the interaction contract HERE so W10 builds the right thing.
// NO built grid UI ships in P1 — only this typed contract + the mobile-list skeleton
// (ArcTimelineMobileList.tsx).
//
// ── Desktop edit-grid (W10, dnd-kit — the studio already uses dnd-kit) ──────────
//   Keyboard model (MANDATORY — the dnd-kit KeyboardSensor pattern, same as DockRail):
//     • Tab to a placement (a focusable cell with aria-grabbed + aria-describedby
//       announcing e.g. "combat thread, chapters 2-3")
//     • Enter / Space  → "grab" the placement
//     • Arrow keys      → move across chapters
//     • Shift + Arrow   → resize the chapter span
//     • Enter           → drop
//     • Esc             → cancel the grab
//   The edit-grid is DESKTOP-ONLY (gated behind a breakpoint).
//
// ── Mobile / touch fallback (REQUIRED, not optional — a drag-grid is unusable on a
//   phone) ──────────────────────────────────────────────────────────────────────
//   A vertical, per-thread LIST: each thread is a section, each placement a row
//   (chapter range + motif name) with explicit "move" / "resize" stepper buttons +
//   a "+ place" affordance — NO dragging. Reads (viewing an arc) work on ALL sizes;
//   only the grid EDIT affordance is desktop-only, with a notice on mobile.
//
//   W10 implements ArcTimelineGrid (desktop) against THIS contract; the mobile
//   ArcTimelineMobileList skeleton (the sibling .tsx) is the frozen interface.

/** One motif placement on the (thread, chapter-span) grid. Mirrors the F0
 *  `ArcPlacement` shape (layout[] entry) the backend stores. */
export type ArcPlacement = {
  id: string;                 // stable id (for aria-grabbed / keyboard focus)
  motif_code: string;
  motif_id: string | null;    // resolved id (R1.4)
  motif_name: string;
  thread: string;             // the thread key this placement sits in
  span_start: number;         // first chapter (inclusive)
  span_end: number;           // last chapter (inclusive)
  ord: number;
  // OPAQUE passthrough of the backend ArcLayoutEntry fields the timeline UI does NOT
  // render but MUST preserve across an edit→save round-trip (§15.3 — per-placement role
  // overrides + chained-placement refs). Dropping these on save = silent data loss.
  role_hints?: Record<string, unknown>;
  triggers?: string[];
};

/** A parallel narrative track (a row/lane on the grid). */
export type ArcThread = {
  key: string;
  label: string;
  /** A named hue + a GLYPH (§2.2 — paired, never hue alone): ⚔ combat / ☯ cultivation
   *  / ♥ romance. W10 renders glyph + label, not color alone. */
  glyph?: string;
};

/** The frozen edit-action contract W10's grid + the mobile list BOTH drive. The
 *  desktop grid produces these via drag OR the keyboard model above; the mobile
 *  list produces the move/resize ones via stepper buttons. */
export type ArcTimelineEdit =
  | { type: 'place'; thread: string; motif_code: string; span_start: number; span_end: number }
  | { type: 'move'; placement_id: string; to_thread: string; delta_chapters: number }
  | { type: 'resize'; placement_id: string; edge: 'start' | 'end'; delta: number }
  | { type: 'remove'; placement_id: string };

/** The data + callbacks BOTH the desktop grid (W10) and the mobile list skeleton
 *  bind to — the single frozen interface so W10 builds against it. */
export type ArcTimelineContract = {
  threads: ArcThread[];
  placements: ArcPlacement[];
  chapterSpan: number;        // total chapters (the grid's column count)
  /** Edit affordances (desktop grid OR mobile stepper) emit edits through here.
   *  Read-only viewers pass `undefined` (the grid renders non-interactive). */
  onEdit?: (edit: ArcTimelineEdit) => void;
  /** True ⇒ desktop edit-grid is allowed; false ⇒ mobile shows the list + a notice
   *  ("The timeline grid is available on a larger screen — here's the list view"). */
  editGridEnabled: boolean;
};
