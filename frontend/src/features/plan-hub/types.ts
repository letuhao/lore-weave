// Plan Hub v2 (spec 24) — the canvas data contract, FE side. Types mirror the H1
// backend read surfaces (24 §113 read-surfaces table); the LANE-LAYOUT inputs
// (ArcShellNode / WindowNode / CollapseState) are OWNED by layout/laneLayout.ts and
// re-exported here so a consumer imports one place. Prose never reaches the canvas
// (PH10) — the `detail=summary` projection is scalars + L1 refs only.
import type {
  ArcShellNode,
  WindowNode,
  CollapseState,
  StructureKind,
  NodePosition,
  NodeShape,
  LaneBand,
  LaneLayout,
} from './layout/laneLayout';

// Re-export the laneLayout-owned types so a consumer imports one place.
export type {
  ArcShellNode,
  WindowNode,
  CollapseState,
  StructureKind,
  NodePosition,
  NodeShape,
  LaneBand,
  LaneLayout,
};

/** Read surface #1 — `GET /v1/composition/books/{book_id}/arcs` (composition_arc_list,
 *  23 B1). The whole structure shell + the derived block the Hub requires (OQ-2). Extra
 *  spec fields (goal/tracks/roster/roster_bindings/…) ride along for the drawer; the
 *  canvas + laneLayout only read the ArcShellNode subset. */
export interface ArcListNode {
  id: string;
  kind: 'saga' | 'arc';
  parent_id: string | null;
  depth: number;
  rank: string;
  title: string;
  status: string;
  summary?: string;
  goal?: string;
  arc_template_id?: string | null;
  template_version?: number | null;
  version: number;
  // derived block (BA6) — the Hub's requirement on B1's response (24 OQ-2)
  span: { from_order: number; to_order: number } | null;
  is_contiguous: boolean;
  chapter_count: number;
}

/** Read surface #2 — one node of the `detail=summary` children window (24:120 / PH10).
 *  `present_entity_ids` is server-capped to 3; `present_entity_count` stays exact. */
export interface SummaryNode {
  id: string;
  kind: 'chapter' | 'scene';
  parent_id: string | null;
  structure_node_id: string | null;
  chapter_id: string | null;
  title: string;
  status: string;
  version: number;
  story_order: number | null;
  rank: string;
  beat_role: string | null;
  tension: number | null;
  pov_entity_id: string | null;
  present_entity_ids: string[];
  present_entity_count: number;
}

/** The children route envelope (keyset). `next_cursor` null ⇒ last page. */
export interface ChildrenPage {
  items: SummaryNode[];
  next_cursor: string | null;
}

/** Read surface #4 — `GET .../scene-links` (PH13). Sparse, whole-book, one call. */
export interface SceneLinkEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  kind: 'setup_payoff' | 'custom';
  label: string | null;
}

/** Read surface #3 — `GET .../plan-overlay` (PH18/17/19/21). Decorations, bounded +
 *  partiality-flagged (drift/staleness is NOT here — that rides surface #7). */
export interface PlanOverlayRef {
  kind: 'canon' | 'thread';
  id: string;
  line: string;
}
export interface PlanOverlayProblemNode {
  canon: number;
  threads_open: number;
  refs: PlanOverlayRef[];
}
export interface PlanOverlay {
  problems: {
    by_node: Record<string, PlanOverlayProblemNode>;
    refs_capped: boolean;
  };
  tension_rollup: { chapter_node_id: string; story_order: number; tension: number }[];
  motif_chips: {
    node_ref: string;
    motif_id: string;
    title: string;
    pinned_version: number;
    live_version: number;
  }[];
  unplanned_chapters: { chapter_id: string; title: string; sort_order: number }[];
}

/** Read surface #7 — `GET .../conformance/status` (26 IX-14, PH18). Per-arc dirty
 *  badges + stale rollup. A `never_run` arc arrives `computed_at: null, dirty: true`
 *  and renders as such — never defaulted to a green 0
 *  (`fe-status-default-fallback-signals-backend-field-omission`). */
export interface ConformanceArc {
  structure_node_id: string;
  dirty: boolean;
  dirty_reasons: string[];
  stale_chapters: number;
  computed_at: string | null;
  summary: string | null;
}
export interface ConformanceStatus {
  arcs: ConformanceArc[];
  index: { stale_chapter_count: number };
}

/** Read surface #5 — the ACTUAL-state half (book-service `GET /v1/books/{book_id}/scenes`
 *  + the chapter spine, 22). Client-side join on chapter_id / source_scene_id (SC11 —
 *  PH12). Minimal shape the two-truths join needs. */
export interface ActualScene {
  scene_id: string;
  chapter_id: string;
  source_scene_id: string | null; // links a manuscript scene back to its spec node
  index: number;
}

/** PH12 — the three node states from the two-truths join (spec vs manuscript). */
export type NodeUnionState = 'planned-only' | 'written' | 'imported-unplanned';

/** The controller ↔ canvas contract (H2). `usePlanHub` PRODUCES this; `PlanCanvas` and
 *  `PlanHubPanel` CONSUME it. Fixed here so the hooks slice and the components slice can be
 *  built in parallel against one interface (`css-var-duplicated-across-two-consumers-drifts`). */
export interface PlanHubView {
  /** The positioned lanes/nodes for the current shell + loaded windows + collapse state
   *  (the ONE laneLayout() call — never a second "where does a node go" in the canvas). */
  layout: LaneLayout;
  edges: SceneLinkEdge[];
  /** null until the overlay resolves; the canvas renders no problem badge while null. */
  overlay: PlanOverlay | null;
  /** null = NOT computed (26 absent / never_run) — absent ≠ zero, render no drift badge. */
  conformance: ConformanceStatus | null;
  /** PH12 union state per node id (spec vs manuscript), for the three-state node styling. */
  unionState: Record<string, NodeUnionState>;
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  select: (id: string | null) => void;
  /** Collapse/expand an arc lane to/from a single rollup card (PH11). */
  toggleArc: (arcId: string) => void;
  /** Hide/show a chapter's scene branch (loads the scene window on expand). */
  toggleChapter: (chapterId: string) => void;
}

/** Props the React Flow canvas takes — a strict subset of PlanHubView (render-only). */
export interface PlanCanvasProps {
  layout: LaneLayout;
  edges: SceneLinkEdge[];
  overlay: PlanOverlay | null;
  conformance: ConformanceStatus | null;
  unionState: Record<string, NodeUnionState>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onToggleArc: (arcId: string) => void;
  onToggleChapter: (chapterId: string) => void;
}
