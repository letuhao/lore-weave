// Plan Hub v2 (spec 24) — the canvas data contract, FE side. Types mirror the H1
// backend read surfaces (24 §113 read-surfaces table); the LANE-LAYOUT inputs
// (ArcShellNode / WindowNode / CollapseState) are OWNED by layout/laneLayout.ts and
// re-exported here so a consumer imports one place. Prose never reaches the canvas
// (PH10) — the `detail=summary` projection is scalars + L1 refs only.
import type { EntityResolution } from './hooks/useEntityNames';
import type { PlanNodeWrites } from './hooks/usePlanNodeWrites';
import type { BookChapter } from './hooks/useBookChapters';
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
import type { LaneArc, LaneChapter } from './layout/laneTree';

/** The FE authorship CODING — the sealed redesign's type/colour semantic: `authored` (a human wrote
 *  it → Lora serif + amber) vs `mined` (a machine produced it → JetBrains Mono + teal). This is a
 *  2-value DISPLAY coding, distinct from the wire's richer `source` enum. */
export type NodeSource = 'authored' | 'mined';

/** Normalise the wire's `source` (`outline_node.source` / `structure_node.source`) to the 2-value FE
 *  coding. The human value is exactly `'authored'`; EVERY other value the backend uses — `'planforge'`,
 *  `'decompiled'`, `'mined'`, `'imported'`, `'adopted'` — is machine-produced and gets the AI (teal +
 *  mono) treatment. Recognising only `'mined'` (the old bug) rendered planner/import content as if the
 *  writer had authored it, so the authorship coding was invisible on real books. */
export function normalizeSource(s: string | undefined | null): NodeSource {
  return !s || s === 'authored' ? 'authored' : 'mined';
}

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
export type { LaneArc, LaneChapter, LaneScene } from './layout/laneTree';

/** Read surface #1 — `GET /v1/composition/books/{book_id}/arcs` (composition_arc_list,
 *  23 B1). The whole structure shell + the derived block the Hub requires (OQ-2). Extra
 *  spec fields (goal/tracks/roster/roster_bindings/…) ride along for the drawer; the
 *  canvas + laneLayout only read the ArcShellNode subset. */
/** One cascade entry (a track or a roster slot). `key` is the shadow key (server-enforced
 *  non-empty + unique within a node — BE D-ARC-TRACKS-ROSTER-SCHEMA); other fields ride along. */
export interface ArcEntry {
  key: string;
  label?: string;
  actant?: string | null;
  constraints?: string[];
  [k: string]: unknown;
}

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
  /** AUTHORSHIP (redesign) — the RAW wire value (`'authored'|'planforge'|'decompiled'|'mined'|
   *  'imported'|…`). Rides the arc-list wire via `model_dump`. Normalise with `normalizeSource`. */
  source?: string;
  // 32 §3.6 — widened to the full StructureNode shape so PlanDrawer's `as ArcListNode &
  // { tracks?: unknown }` cast (the type lying about the wire) can go. The inspector reads the
  // node's OWN arrays; the resolved cascade comes from the ArcDetail fetch.
  book_id?: string;
  created_by?: string;
  tracks?: ArcEntry[];
  roster?: ArcEntry[];
  roster_bindings?: Record<string, string>;
  is_archived?: boolean;
  created_at?: string;
  updated_at?: string;
  // derived block (BA6) — the Hub's requirement on B1's response (24 OQ-2).
  // `span` is the human READING-POSITION range ("chapters 1–3"), for display.
  // `first_story_order` is the RAW-axis sort key the rollup card is placed by — a different unit,
  // deliberately a different field (one field, one job).
  span: { from_order: number; to_order: number } | null;
  first_story_order: number | null;
  is_contiguous: boolean;
  chapter_count: number;
}

/** One open-promise rollup entry (32 §3.4 — read-only, deep-links to quality-promises). */
export interface ArcOpenPromise {
  id: string;
  kind: string;
  severity?: number | null;
  text?: string;
  chapter_id?: string | null;
}

/** `GET /v1/composition/arcs/{node_id}` (composition_arc_get) — the arc-inspector detail (32 §4).
 *  The node's OWN fields + the root→leaf RESOLVED cascade + the BE-A1 dense-ranked derived block
 *  (span/chapter_count/is_contiguous, NULL for an archived node) + the open-promise rollup. */
export interface ArcDetail extends ArcListNode {
  resolved: {
    tracks: ArcEntry[];
    roster: ArcEntry[];
    roster_bindings: Record<string, string>;
  };
  open_promises: ArcOpenPromise[];
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
  /** AUTHORSHIP (redesign) — the RAW wire value (`'authored'|'planforge'|'decompiled'|…`). Now on the
   *  summary wire (`outline.py _summary_projection`). Normalise with `normalizeSource`. */
  source?: string;
  /** SC11 amendment — "is there prose behind this node?", MAINTAINED server-side
   *  (`outline_node.written_scene_id`, reconciled from book-service's `scenes.source_scene_id`).
   *  It replaces the client-side two-truths join entirely: no scene-index page-walk, no per-chapter
   *  completeness guard, no generation guard. Independent of `status`, which is the AUTHOR'S INTENT
   *  (PH16's two chips: desired vs actual). */
  written: boolean;
}

/** The children route envelope (keyset). `next_cursor` null ⇒ last page. */
export interface ChildrenPage {
  items: SummaryNode[];
  next_cursor: string | null;
}

/** Read surface #4 — `GET .../scene-links` (PH13). Sparse, whole-book, one call.
 *  `kind` MIRRORS the server's closed set — SoT: `LinkKind` in composition-service
 *  `app/db/models.py` (the REST schema and the MCP tool both derive from it). Adding a kind
 *  server-side without adding it here renders as the `custom` dashed style, silently. */
export interface SceneLinkEdge {
  id: string;
  from_node_id: string;
  to_node_id: string;
  kind: 'setup_payoff' | 'custom';
  label: string | null;
  /**
   * Each endpoint's ANCESTRY — its parent chapter node and its arc lane (PH13). The client cannot
   * derive these: a COLLAPSED arc never loads its chapter window, so its scenes never arrive, and an
   * unloaded endpoint's lane is simply unknowable here. Without them the canvas hands React Flow an
   * edge naming a node that doesn't exist and RF drops it in silence — the exact failure PH13 names.
   * null ⇒ the endpoint node is gone or unparented; the edge then has no lane to stub into.
   */
  from_chapter_node_id: string | null;
  to_chapter_node_id: string | null;
  from_arc_id: string | null;
  to_arc_id: string | null;
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
/** PH11 — how much of an arc's chapter window is actually loaded. The children route pages at 100,
 *  so a 340-chapter arc shows 100 cards. Without surfacing this, the other 240 are invisible AND
 *  un-draggable, with nothing on screen admitting they exist — a silent truncation (OUT-5). */
export interface ArcPagination {
  loaded: number;
  /** The arc's TRUE chapter count, from the shell (`chapter_count`) — never the loaded length. */
  total: number;
  hasMore: boolean;
  loading: boolean;
}

/** A MANUSCRIPT chapter with no spec node (PH21). It has no canvas node — that is the whole
 *  point — so it is addressed by its book-service `chapter_id`, not an outline-node id. */
export interface UnplannedChapter {
  chapter_id: string;
  title: string;
  sort_order: number;
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
  /** PH21 tray — the shared server-side coverage diff (28 OQ-4/NC-1: ONE computation,
   *  also feeding `composition_diagnostics`). **OPTIONAL on purpose**: when the
   *  manuscript spine is unreadable the server OMITS the key and sends `warnings`
   *  instead. `[]` means "nothing unplanned"; `undefined` means "we don't know" — do
   *  NOT collapse the two (absent ≠ zero). */
  unplanned_chapters?: UnplannedChapter[];
  /** EXACT, even when the list above is capped at 200. */
  unplanned_count?: number;
  unplanned_capped?: boolean;
  /** Present ⇒ some part of the payload is degraded (today: the tray only). */
  warnings?: string[];
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


/** PH12 — the three node states from the two-truths join (spec vs manuscript). */
export type NodeUnionState = 'planned-only' | 'written' | 'imported-unplanned';

/** Display scalars a canvas node needs but `NodePosition` (layout-only) lacks — title/status/etc.
 *  Keyed by node id in `PlanHubView.nodeContent`: arc/saga entries come from the shell (ArcListNode),
 *  chapter/scene entries from the loaded summary windows (SummaryNode). `chapterId` feeds the bus
 *  (node → active-chapter event) + the H3 drawer. Prose (goal/synopsis) is NOT here (PH10). */
export interface NodeContent {
  title: string;
  status: string;
  kind: string;
  tension: number | null;
  beatRole: string | null;
  chapterId: string | null;
  /** PH23/PH26 — the cast, SERVER-capped to 3 (exactly what a card may render). It has been on the
   *  wire since H1.1 (`SummaryNode.present_entity_ids`); the NodeContent map simply dropped it, so
   *  the cast chips had no data source and could not be built. */
  castIds: string[];
  /** EXACT roster size — drives the `+N` overflow. Never the length of the capped list. */
  castCount: number;
  /** AUTHORSHIP (redesign) — 'authored' (human) vs 'mined' (decompiler). Drives the Lora+amber vs
   *  Mono+teal type/colour coding on every card. Defaults to 'authored' when the wire omits it. */
  source: NodeSource;
}

/** The controller ↔ canvas contract (H2). `usePlanHub` PRODUCES this; `PlanCanvas` and
 *  `PlanHubPanel` CONSUME it. Fixed here so the hooks slice and the components slice can be
 *  built in parallel against one interface (`css-var-duplicated-across-two-consumers-drifts`). */
export interface PlanHubView {
  /** The positioned lanes/nodes for the current shell + loaded windows + collapse state
   *  (the ONE laneLayout() call — never a second "where does a node go" in the canvas). */
  layout: LaneLayout;
  /** The arc → chapter → scene TREE for the lane-flow Advanced view (the sealed redesign). A
   *  projection of the SAME shell + loaded windows the `layout` uses — the flow view renders a
   *  document tree (stacked lanes, wrapping chapters), not the graph's absolute positions. */
  laneTree: LaneArc[];
  /** Arc-less chapters (post-decompile) for the flow view's "Unassigned" group — visible + fileable. */
  laneUnassigned: LaneChapter[];
  /** Flattened arc pick-list for the "move to arc" control (id, title, depth for indentation). */
  arcOptions: { id: string; title: string; depth: number }[];
  edges: SceneLinkEdge[];
  /** null until the overlay resolves; the canvas renders no problem badge while null. */
  overlay: PlanOverlay | null;
  /** null = NOT computed (26 absent / never_run) — absent ≠ zero, render no drift badge. */
  conformance: ConformanceStatus | null;
  /** PH12 union state per node id (spec vs manuscript), for the three-state node styling. */
  unionState: Record<string, NodeUnionState>;
  /** Display scalars (title/status/…) per node id — arc titles from the shell, chapter/scene
   *  titles from the loaded windows. Absent id ⇒ the card falls back to a story-order label. */
  nodeContent: Record<string, NodeContent>;
  /**
   * PH21 — the book has NO spec at all (no arcs, no chapter nodes), so the Hub shows the empty
   * state with its two CTAs instead of a blank canvas. `false` while we are still finding out:
   * we must never claim "no plan" over an unfinished read (absent ≠ empty). The Hub NEVER
   * synthesises a graph from chapters — inferring structure is the decompiler's explicit job.
   */
  specEmpty: boolean;
  /**
   * PH21 tray — MANUSCRIPT chapters with no spec node (the shared server-side coverage diff).
   * THREE states, and collapsing any two of them is a bug:
   *   `undefined` ⇒ still loading — render nothing (NOT "unknown", or every cold open flashes the
   *                 degradation alarm while the overlay, the slowest read, is in flight)
   *   `null`      ⇒ the server ANSWERED and omitted the key — render "unknown", never an empty tray
   *   `[]`        ⇒ nothing is unplanned
   * Distinct from `layout.unassigned`, which is spec chapters with no ARC.
   */
  unplanned: UnplannedChapter[] | null | undefined;
  /** EXACT count even when the tray list is server-capped at 200. */
  unplannedCount: number;
  /** Book-wide problem total, from the EXACT per-node counts — never the capped refs list (the
   *  server caps refs at 50 while keeping counts exact, so summing refs would report "50" for a
   *  book with 300 problems). */
  problemTotal: number;
  /** PH11 — per-arc window state (loaded / total / hasMore / loading) for the lane header counter. */
  arcPagination: Record<string, ArcPagination>;
  /** PH11 — page in the next 100 chapters of an expanded arc. */
  loadMoreArc: (arcId: string) => void;
  /** H5 Row-5 (PH20) — draw a scene-link edge between two scene nodes. */
  linkScenes: (fromNodeId: string, toNodeId: string) => void;
  /** H5 Row-5 (PH20) — delete a scene-link edge (undoable: the edge carries its kind + label). */
  unlinkScenes: (edge: SceneLinkEdge) => void;
  /** PH26 — the entity-names map (read surface #6): resolve a cast id to a name, or say honestly
   *  whether it is MISSING (map complete) or merely UNKNOWN (map incomplete). */
  resolveEntity: (entityId: string) => EntityResolution;
  /** PH20 — the drawer's writes (edit / archive / restore), OCC'd on the node version. */
  nodeWrites: PlanNodeWrites;
  /** The book's chapter spine — the ⚓ re-anchor picker's options (BPS-13). Loaded ONLY once a node
   *  is selected (the walk is ~100 requests on a big book; firing it at mount was a budget bug). */
  chapters: BookChapter[];
  /** The spine read FAILED. With `[]` the anchor picker would show "— not anchored —" for an
   *  ANCHORED node — a confident lie about its state. The drawer says so instead. */
  chaptersError: boolean;
  /** PH21 CTA — run the SC6 decompiler (`materialize-scenes`) on this book. */
  extract: {
    run: () => void;
    extracting: boolean;
    result: { scenes_total: number; created: number; chapters: number; detail: string | null } | null;
    error: string | null;
  };
  /**
   * Every partial truth the canvas is currently rendering — the manuscript join being dead, refs
   * being capped, the coverage diff being uncomputable. The Hub degrades in several ways and each
   * used to do so SILENTLY: it just showed less, and looked exactly like a healthy canvas showing
   * less. Empty ⇒ what you see is the whole truth.
   */
  notices: string[];
  loading: boolean;
  error: string | null;
  selectedId: string | null;
  select: (id: string | null) => void;
  /** Collapse/expand an arc lane to/from a single rollup card (PH11). */
  toggleArc: (arcId: string) => void;
  /** Idempotently OPEN a set of arcs (never collapses one already closed by the user). The lane-flow
   *  view uses it for bounded auto-expand on open — showing the hierarchy by default (mockup "root
   *  fix 2") without a per-arc window fetch on a huge book. */
  expandArcs: (arcIds: string[]) => void;
  /** Hide/show a chapter's scene branch (loads the scene window on expand). */
  toggleChapter: (chapterId: string) => void;
  /** OQ-5 — open an arc's ancestors so the arc becomes a RENDERED node. A nested arc under a
   *  collapsed ancestor isn't drawn at all, so there is nothing for the camera to pan to. */
  expandAncestorsOf: (nodeId: string) => void;
  /** H5 Row-1 (PH20): rebind a chapter to another arc (drag into its lane). Refetches on success. */
  moveChapterToArc: (chapterId: string, arcId: string) => void;
  /** H5 Row-4 (PH20): re-parent a scene under another chapter (drag onto its card). OCC'd on the
   *  scene's version (If-Match → 412 reload). A drop on its OWN chapter is a no-op. */
  moveSceneToChapter: (sceneId: string, chapterId: string) => void;
  /** H5 Row-2 (PH20): move an ARC in the structure tree by dropping its band on another band —
   *  nest under a saga/parent arc, or become a leaf arc's next sibling. Cycle/depth are the
   *  server's rules (clean 4xx → moveError). */
  moveArcTo: (arcId: string, targetId: string) => void;
  /** H5 Row-3 (PH20): move a chapter along the READING order (drag it within its own lane) — the one
   *  gesture that mutates the MANUSCRIPT, since the x-axis is book-service's chapter order. `afterUnit`
   *  is the reading-order unit it should follow (null ⇒ becomes chapter 1); a collapsed arc's rollup
   *  is refused (its hidden chapters can't be named to the server). */
  reorderChapter: (chapterNodeId: string, afterUnit: NodePosition | null) => void;
  /** A move is in flight (disable further drags / show a subtle busy state). */
  moving: boolean;
  /** The last move's failure (incl. the 412 "changed elsewhere — reloaded" recovery); null when ok. */
  moveError: string | null;
  /** H5: the last successful move's INVERSE (one level), or null. Its arguments were captured before
   *  the write — the server's answer no longer knows where the node came from. */
  undo: { label: string; run: () => void } | null;
}

/** A camera pan request (H2.6/OQ-5). `seq` increments per request so re-focusing the SAME node
 *  still pans (a bare id wouldn't change ⇒ the effect wouldn't re-run). null ⇒ no pan pending. */
export interface CameraFocusTarget {
  nodeId: string;
  seq: number;
}

/** Props the React Flow canvas takes — a strict subset of PlanHubView (render-only) + the H2.6
 *  camera/here inputs. */
export interface PlanCanvasProps {
  layout: LaneLayout;
  edges: SceneLinkEdge[];
  overlay: PlanOverlay | null;
  conformance: ConformanceStatus | null;
  unionState: Record<string, NodeUnionState>;
  nodeContent: Record<string, NodeContent>;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onToggleArc: (arcId: string) => void;
  onToggleChapter: (chapterId: string) => void;
  /** H2.6 "you are here": the node whose chapter is open in the editor (from the bus active-chapter
   *  signal). Rendered with a distinct highlight, NOT the selection ring. undefined ⇒ none. */
  activeNodeId?: string | null;
  /** OQ-5 camera: when this changes (by `seq`), pan/zoom the canvas to center `nodeId`. */
  focusTarget?: CameraFocusTarget | null;
  /** H5 Row-1: a chapter card was dragged into another arc's lane — rebind it (structure_node_id).
   *  Omitted ⇒ chapters aren't draggable (read-only canvas). */
  onMoveChapter?: (chapterId: string, arcId: string) => void;
  /** H5 Row-4: a scene card was dropped onto a chapter card — re-parent it under that chapter.
   *  The canvas only resolves the TARGET; the controller decides whether it's a real move (it owns
   *  the scene's current parent + version). Omitted ⇒ scenes aren't draggable. */
  onMoveScene?: (sceneId: string, chapterId: string) => void;
  /** H5 Row-2: an ARC band was dragged (by its header) onto another band. The canvas reports only
   *  which band was hit; the controller decides nest-vs-sibling (it holds parent_id + rank).
   *  Omitted ⇒ bands aren't draggable. Saga bands never drag (a saga cannot be parented). */
  onMoveArc?: (arcId: string, targetId: string) => void;
  /** H5 Row-3: a chapter card was dragged WITHIN its own lane — i.e. along the reading order. The
   *  canvas reports the unit it landed after (null ⇒ before everything); the controller decides
   *  whether that's a real move and whether it can be named to the server. */
  onReorderChapter?: (chapterNodeId: string, afterUnit: NodePosition | null) => void;
  /** PH11 — per-arc window pagination (loaded/total/hasMore), rendered in the lane header. */
  arcPagination?: Record<string, ArcPagination>;
  /** PH11 — fetch the next chapter page of an expanded arc. Without a caller, an arc's 101st
   *  chapter is unreachable: invisible on the canvas AND undraggable. */
  onLoadMoreArc?: (arcId: string) => void;
  /** PH18 — open a problem ref in its owning lens (canon → `quality-canon`, thread →
   *  `quality-promises`). Reaches the node cards through `PlanNodeData.onOpenRef`, which they
   *  already forward to NodeBadges. Omitted ⇒ badges stay plain chips, never dead links.
   *  The NODE id rides along because the canon lens cannot filter by rule id — see PlanHubPanel. */
  onOpenRef?: (ref: PlanOverlayRef, nodeId: string) => void;
  /** H5 Row-5 (PH20) — two handles were joined. The canvas reports only WHICH; the controller decides
   *  whether it's a legal link (both ends must be real scene nodes). Omitted ⇒ not connectable. */
  onLinkScenes?: (fromNodeId: string, toNodeId: string) => void;
  /** H5 Row-5 (PH20) — an edge was clicked; delete that scene link. Passes the WHOLE edge so the undo
   *  can re-create it with its kind + label. A STUB edge is never deletable (its other end is
   *  collapsed out of view — deleting from a half-drawn line is a trap). */
  onUnlinkScenes?: (edge: SceneLinkEdge) => void;
  /** PH26 — resolve a cast entity id (read surface #6). Omitted ⇒ no cast chips. */
  resolveEntity?: (entityId: string) => EntityResolution;
  /** PH15 — bump to re-frame the whole graph ("Fit"). Monotonic, so two clicks fit twice. */
  fitSignal?: number;
  /** PH15 — nodes matching the toolbar's find query. HIGHLIGHTED, never filtered (PH14: an insert
   *  must shift, never reshuffle — hiding non-matches would re-lay the canvas out under the user). */
  matchedIds?: Set<string>;
  /** H5: a move is in flight ⇒ freeze dragging. The lanes under the cursor are about to be replaced
   *  by the server's answer, so a second drag would be aimed at a layout that no longer holds. */
  busy?: boolean;
}
