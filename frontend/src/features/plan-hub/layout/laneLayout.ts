// 24-H2.2 (PH14) — the deterministic lane-layout engine. ONE pure function,
// (shell, windows, collapse, options) → positions, consumed by BOTH the Hub canvas
// AND the Plan navigator (24:346 / PH25 — never a second "where does a node go" impl;
// the navigator renders ORDER, the canvas renders POSITIONS, from this one source).
//
// PH14's law (24:97):
//   • y = lane band derived from the `structure_node` tree (depth-nested sub-bands, rank-ordered)
//   • x = position of `story_order` within the loaded window, with collapsed-run compression
//   • a non-contiguous arc renders one band SEGMENT per contiguous chapter run, joined by a spine
//   • NO force/stock layout (dagre/elk) — an insert must SHIFT, never reshuffle.
//
// Deterministic (lane, order) → (x, y): memoizable, stable under insert/reorder, browser-free.
// React Flow supplies mechanics only (pan/zoom/hit-test); it never decides a position.

/** structure_node kinds — depth 0..2 (saga ← arc ← sub_arc), per 23:362. */
export type StructureKind = 'saga' | 'arc' | 'sub_arc';

/** Read surface #1 (`composition_arc_list`) — the whole structure shell in one call (24:119). */
export interface ArcShellNode {
  id: string;
  kind: StructureKind;
  parent_id: string | null; // parent structure node; null at a root
  rank: string; // lexrank among siblings (the within-parent order)
  title: string;
  /** BA6 derived span over the arc's chapters, as READING POSITIONS (1..N — "chapters 1–3"), for
   *  DISPLAY. null ⇒ the arc holds no chapters. Never a sort key: see first_story_order. */
  span: { from_order: number; to_order: number } | null;
  /** The arc's first chapter on the RAW story_order axis — the SORT key for a collapsed arc's
   *  rollup card, which has to interleave with loaded chapter cards (whose axis is raw
   *  story_order). Sorting the rollup by `span.from_order` instead mixes two units: an ordinal 4
   *  sorts ahead of a chapter at 1000, and the rollup lands at the wrong x. null ⇒ no chapters
   *  (or none positioned) ⇒ the rollup sorts LAST. */
  first_story_order: number | null;
  /** BA6 — false ⇒ the arc's chapters are non-contiguous ⇒ segmented lane + warn chip. */
  is_contiguous: boolean;
  chapter_count: number;
}

/** Read surface #2 (keyset children window) — a loaded chapter or scene (24:120). */
export interface WindowNode {
  id: string;
  kind: 'chapter' | 'scene';
  parent_id: string | null; // a scene's chapter node id; a chapter's parent is null post-migration
  structure_node_id: string | null; // the arc lane a CHAPTER is bound to (null on scenes / unplanned)
  chapter_id: string | null;
  /** Reading position on the book's STRIDED axis (a chapter sits at `chapter_sort * 1000`, its
   *  scenes at `+0..+n`). Adjacent chapters therefore differ by the STRIDE, never by 1 — nothing
   *  here may do `prev + 1` arithmetic on it; adjacency is positional (see the segment pass).
   *  `null` ⇒ genuinely unknown (a chapter with no scenes predating the backfill): it sorts LAST
   *  and is never silently treated as position 0 (absent ≠ zero). */
  story_order: number | null;
  rank: string;
  /** SC11 amendment — the server-maintained written verdict. It rides the node payload, so the
   *  canvas never joins against book-service's scene index to learn it. */
  written: boolean;
}

/** Sort key for a possibly-unordered node: an unknown position sorts LAST (mirrors the server's
 *  `ORDER BY story_order NULLS LAST`), never first. */
function orderKey(story_order: number | null): number {
  return story_order ?? Number.POSITIVE_INFINITY;
}

/**
 * What the user has collapsed. `arcs` collapses a lane to one rollup card (children suppressed);
 * `chapters` hides a chapter's scene branch cards. Iterables (not just Set) so callers can pass
 * arrays; we normalize once.
 */
export interface CollapseState {
  arcs?: Iterable<string>;
  chapters?: Iterable<string>;
}

export interface LaneLayoutOptions {
  laneHeight: number; // content-strip height of a leaf lane (the chapter row)
  sceneRowHeight: number; // the scene branch row beneath the chapter row on a leaf lane
  laneHeaderHeight: number; // header strip reserved above EVERY band's cards (leaf + non-leaf) so the title/toggle never overlaps the first card
  laneGap: number; // vertical gap between sibling bands
  cardWidth: number;
  cardPitch: number; // x distance between adjacent chapter slots (cardWidth + h-gap)
  scenePitch: number; // x distance between adjacent scene branch cards
  padX: number;
  padY: number;
}

export const DEFAULT_LAYOUT_OPTIONS: LaneLayoutOptions = {
  // Cards were 128px wide with truncated titles — a user panel's #1 complaint was "text bị ăn mất,
  // tên arc chỉ vài ký tự" (the title showed ~10 chars). Widened to 208 and the node titles now WRAP
  // to 2 lines (line-clamp) instead of hard-truncating, so a real chapter/arc name is legible. Pitch
  // and lane height grow to match (pitch = width + 16 gap; a 2-line title + badges needs the height).
  laneHeight: 92,
  sceneRowHeight: 44,
  laneHeaderHeight: 28,
  laneGap: 12,
  cardWidth: 208,
  cardPitch: 224,
  scenePitch: 96,
  padX: 24,
  padY: 16,
};

export interface LaneSegment {
  fromOrder: number;
  toOrder: number;
  x: number;
  width: number;
}

export interface LaneBand {
  id: string; // structure_node id
  kind: StructureKind;
  depth: number; // recomputed from the tree — the shell's depth is never trusted
  title: string;
  y: number; // band top
  height: number; // full band height (nested children included)
  /** y at which THIS band's directly-bound chapter cards sit. */
  chapterY: number;
  /** y at which THIS band's scene branch cards sit (leaf lanes). */
  sceneY: number;
  isLeaf: boolean; // no structure children → a content lane that carries chapters
  contiguous: boolean; // BA6 warn flag (false ⇒ segmented rendering)
  /** One per contiguous run of the lane's LOADED chapters; [] until chapters load / when collapsed. */
  segments: LaneSegment[];
  collapsed: boolean;
}

export type NodeShape = 'chapter' | 'scene' | 'arc-rollup';

export interface NodePosition {
  id: string;
  shape: NodeShape;
  laneId: string | null;
  x: number;
  y: number;
  width: number;
  collapsed: boolean; // a chapter whose scene branch is hidden
  rollupCount?: number; // arc-rollup: the shell's chapter_count
  storyOrder: number | null;
}

export interface LaneLayout {
  lanes: LaneBand[];
  /** Every drawn node — lane chapters + scenes + arc rollups AND the unassigned strip below. */
  nodes: NodePosition[];
  /**
   * SPEC chapter nodes bound to no arc lane (`structure_node_id` null, or naming an arc the shell
   * doesn't have). They ARE part of `nodes` — this is a labelled VIEW of the same objects, so the
   * strip can be titled and counted without a second render pass.
   *
   * NOT the PH21 tray. That tray is the other direction — MANUSCRIPT chapters with no spec node at
   * all, which by definition have no canvas node to draw; it rides `overlay.unplanned_chapters`
   * (the shared coverage diff). Two different sets: this one is "planned but un-filed", that one is
   * "written but unplanned". They were both called `unplanned` once, which is exactly the one-name-
   * two-concepts drift DA-10 bans.
   */
  unassigned: NodePosition[];
  /** Top of the unassigned strip (for its label), or null when nothing is unassigned. */
  unassignedY: number | null;
  width: number;
  height: number;
}

/** Compare two lexranks (then id) — the same (rank, id) order the keyset routes page by (24:120). */
function byRank<T extends { rank: string; id: string }>(a: T, b: T): number {
  if (a.rank < b.rank) return -1;
  if (a.rank > b.rank) return 1;
  return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
}

interface VBand {
  node: ArcShellNode;
  depth: number;
  children: VBand[];
  isLeaf: boolean;
}

/** Build the rank-ordered structure forest and recompute each node's depth from the tree. */
function buildForest(shell: ArcShellNode[]): VBand[] {
  const byId = new Map(shell.map((n) => [n.id, n]));
  const childrenOf = new Map<string | null, ArcShellNode[]>();
  for (const n of shell) {
    // A parent_id pointing outside the shell is treated as a root (defensive — a partial shell
    // should never happen since arc_list is one whole-book call, but never orphan-drop a lane).
    const key = n.parent_id && byId.has(n.parent_id) ? n.parent_id : null;
    (childrenOf.get(key) ?? childrenOf.set(key, []).get(key)!).push(n);
  }
  const build = (node: ArcShellNode, depth: number): VBand => {
    const kids = (childrenOf.get(node.id) ?? []).slice().sort(byRank);
    return {
      node,
      depth,
      isLeaf: kids.length === 0,
      children: kids.map((k) => build(k, depth + 1)),
    };
  };
  return (childrenOf.get(null) ?? []).slice().sort(byRank).map((r) => build(r, 0));
}

/**
 * Vertical pass: stack the forest into bands with (y, height). Post-order so a parent is sized
 * from its children. A leaf lane reserves a chapter strip + a scene strip so the layout is stable
 * regardless of whether scenes are loaded yet (no reflow on lazy scene load). A NON-leaf band that
 * ALSO carries directly-bound chapters (a prologue on a saga, an interstitial on an arc that later
 * grew sub-arcs — the schema/write-path allow a chapter to bind to any structure_node) reserves the
 * SAME chapter+scene strip under its header, so its chapter card and scene branch never overlap each
 * other or the child bands below (review: non-leaf-with-direct-chapters overlap).
 */
function layoutBands(forest: VBand[], carriers: Set<string>, opts: LaneLayoutOptions): LaneBand[] {
  const out: LaneBand[] = [];
  const contentStrip = opts.laneHeight + opts.sceneRowHeight;
  let cursor = opts.padY;

  const place = (vb: VBand): number => {
    const top = cursor;
    if (vb.isLeaf) {
      // A leaf band renders a header (title + collapse toggle) too, so it needs its OWN header strip
      // — same as the non-leaf branch below. Without it, chapterY === top put the first card (and an
      // empty arc's rollup) directly under the floating header, so the header title and the card
      // title overlapped (the bug the manual-create feature made unmissable: an empty arc IS just a
      // header + its rollup, stacked on the same pixels). Reserve laneHeaderHeight so cards clear it.
      const leafHeight = opts.laneHeaderHeight + contentStrip;
      out.push({
        id: vb.node.id, kind: vb.node.kind, depth: vb.depth, title: vb.node.title,
        y: top, height: leafHeight,
        chapterY: top + opts.laneHeaderHeight,
        sceneY: top + opts.laneHeaderHeight + opts.laneHeight,
        isLeaf: true, contiguous: vb.node.is_contiguous, segments: [], collapsed: false,
      });
      cursor = top + leafHeight;
      return leafHeight;
    }
    // Non-leaf: a header strip; if it carries its own chapters, ALSO a content strip; then children.
    const carries = carriers.has(vb.node.id);
    const chapterY = top + opts.laneHeaderHeight;
    const bandEntry: LaneBand = {
      id: vb.node.id, kind: vb.node.kind, depth: vb.depth, title: vb.node.title,
      y: top, height: 0, chapterY, sceneY: chapterY + opts.laneHeight,
      isLeaf: false, contiguous: vb.node.is_contiguous, segments: [], collapsed: false,
    };
    out.push(bandEntry);
    cursor = top + opts.laneHeaderHeight + (carries ? contentStrip : 0);
    vb.children.forEach((child, i) => {
      if (i > 0) cursor += opts.laneGap;
      place(child);
    });
    bandEntry.height = cursor - top;
    return bandEntry.height;
  };

  forest.forEach((root, i) => {
    if (i > 0) cursor += opts.laneGap;
    place(root);
  });
  return out;
}

/** Set of the OUTERMOST collapsed arcs (a collapsed child under a collapsed ancestor is redundant). */
function outermostCollapsed(bands: LaneBand[], forest: VBand[], collapsedArcs: Set<string>): Set<string> {
  const parentOf = new Map<string, string | null>();
  const walk = (vb: VBand, parent: string | null) => {
    parentOf.set(vb.node.id, parent);
    vb.children.forEach((c) => walk(c, vb.node.id));
  };
  forest.forEach((r) => walk(r, null));
  const out = new Set<string>();
  for (const id of collapsedArcs) {
    let p = parentOf.get(id) ?? null;
    let coveredByAncestor = false;
    while (p) {
      if (collapsedArcs.has(p)) { coveredByAncestor = true; break; }
      p = parentOf.get(p) ?? null;
    }
    if (!coveredByAncestor) out.add(id);
  }
  return out;
}

/** All structure ids at or under `arcId` (a collapsed arc suppresses every descendant chapter). */
function descendantArcs(forest: VBand[], arcId: string): Set<string> {
  const out = new Set<string>();
  const collect = (vb: VBand) => { out.add(vb.node.id); vb.children.forEach(collect); };
  const find = (vb: VBand): VBand | null => {
    if (vb.node.id === arcId) return vb;
    for (const c of vb.children) { const f = find(c); if (f) return f; }
    return null;
  };
  for (const r of forest) { const hit = find(r); if (hit) { collect(hit); break; } }
  return out;
}

/**
 * 24-H2.2 / PH14 — lay the loaded package out deterministically.
 *
 * @param shell   the whole structure_node forest (read surface #1)
 * @param windows the loaded chapter/scene nodes (read surface #2 windows)
 * @param collapse collapsed arcs (→ rollup) and chapters (→ scenes hidden)
 */
export function laneLayout(
  shell: ArcShellNode[],
  windows: WindowNode[],
  collapse: CollapseState = {},
  options: Partial<LaneLayoutOptions> = {},
): LaneLayout {
  const opts = { ...DEFAULT_LAYOUT_OPTIONS, ...options };
  const forest = buildForest(shell);
  const shellIds = new Set(shell.map((s) => s.id));
  const chapters = windows.filter((n) => n.kind === 'chapter');
  // Structure nodes that own >=1 loaded chapter — a NON-leaf one among these needs a content strip
  // reserved (else a directly-bound chapter + its scenes overlap the header and the child bands).
  const chapterCarriers = new Set(
    chapters.map((c) => c.structure_node_id).filter((id): id is string => !!id && shellIds.has(id)),
  );
  const bands = layoutBands(forest, chapterCarriers, opts);
  const bandById = new Map(bands.map((b) => [b.id, b]));

  const collapsedArcsRaw = new Set(collapse.arcs ?? []);
  const collapsedChapters = new Set(collapse.chapters ?? []);
  const rollupArcs = outermostCollapsed(bands, forest, collapsedArcsRaw);
  // Every arc suppressed because it (or an ancestor) is collapsed.
  const suppressed = new Set<string>();
  for (const a of rollupArcs) for (const d of descendantArcs(forest, a)) suppressed.add(d);

  const scenesByChapter = new Map<string, WindowNode[]>();
  for (const n of windows) {
    if (n.kind !== 'scene' || !n.parent_id) continue;
    (scenesByChapter.get(n.parent_id) ?? scenesByChapter.set(n.parent_id, []).get(n.parent_id)!).push(n);
  }

  // ---- x-axis: build placement UNITS in global story_order, with collapsed-run compression ----
  type Unit =
    | { order: number; tie: string; kind: 'chapter'; node: WindowNode }
    | { order: number; tie: string; kind: 'rollup'; arc: ArcShellNode };
  const units: Unit[] = [];
  const placedChapters: WindowNode[] = [];
  for (const ch of chapters) {
    const laneId = ch.structure_node_id;
    if (!laneId || !bandById.has(laneId)) continue; // no arc lane → the unassigned strip, below
    if (suppressed.has(laneId)) continue; // under a collapsed arc → folded into its rollup
    units.push({ order: orderKey(ch.story_order), tie: ch.id, kind: 'chapter', node: ch });
    placedChapters.push(ch);
  }
  for (const arcId of rollupArcs) {
    const node = shell.find((s) => s.id === arcId);
    if (!node) continue;
    // Sort on the RAW axis — the same one the loaded chapter cards use. `span` is the display
    // ordinal and would put this rollup at the wrong x (see ArcShellNode.first_story_order).
    units.push({ order: orderKey(node.first_story_order), tie: arcId, kind: 'rollup', arc: node });
  }
  // Deterministic global order: story_order, then kind (chapters before a rollup at the same
  // order), then id. A collapsed arc occupies exactly ONE slot regardless of chapter_count.
  units.sort((a, b) =>
    a.order - b.order || a.kind.localeCompare(b.kind) || (a.tie < b.tie ? -1 : a.tie > b.tie ? 1 : 0),
  );

  const nodes: NodePosition[] = [];
  const xOf = new Map<string, number>(); // chapter id → x (scenes branch from it)
  const slotOf = new Map<string, number>(); // node id → its SLOT in the global reading order
  units.forEach((u, i) => {
    const x = opts.padX + i * opts.cardPitch;
    slotOf.set(u.kind === 'chapter' ? u.node.id : u.arc.id, i);
    if (u.kind === 'chapter') {
      const band = bandById.get(u.node.structure_node_id!)!;
      const collapsedCh = collapsedChapters.has(u.node.id);
      nodes.push({
        id: u.node.id, shape: 'chapter', laneId: band.id, x, y: band.chapterY,
        width: opts.cardWidth, collapsed: collapsedCh, storyOrder: u.node.story_order,
      });
      xOf.set(u.node.id, x);
    } else {
      const band = bandById.get(u.arc.id)!;
      // An EMPTY arc (no chapters) has no story position: orderKey() sorts it at +Infinity, so the
      // slot index `i` would march every empty arc one column right and one band down — the diagonal
      // cascade the manual-create feature exposed (before it, arcs were only born from the decompiler
      // WITH chapters, so they always had a real first_story_order). Anchor an unpositioned rollup at
      // the lane's first column instead: empty arcs then form a clean left-aligned stack, one per
      // band row (distinct y), never overlapping each other. A POSITIONED arc's rollup keeps its
      // story-order slot (it must interleave with real chapter cards) — only the null case is pinned.
      const rollupX = u.arc.first_story_order === null ? opts.padX : x;
      nodes.push({
        id: u.arc.id, shape: 'arc-rollup', laneId: band.id, x: rollupX, y: band.chapterY,
        width: opts.cardWidth, collapsed: true, rollupCount: u.arc.chapter_count,
        storyOrder: u.arc.span ? u.arc.span.from_order : null,
      });
    }
  });

  // ---- scene branch cards: only under an expanded, placed, non-collapsed chapter ----
  for (const ch of placedChapters) {
    if (collapsedChapters.has(ch.id)) continue;
    const kids = (scenesByChapter.get(ch.id) ?? []).slice().sort(
      (a, b) => orderKey(a.story_order) - orderKey(b.story_order) || byRank(a, b),
    );
    if (kids.length === 0) continue;
    const band = bandById.get(ch.structure_node_id!)!;
    const baseX = xOf.get(ch.id)!;
    kids.forEach((sc, i) => {
      nodes.push({
        id: sc.id, shape: 'scene', laneId: band.id, x: baseX + i * opts.scenePitch,
        y: band.sceneY, width: opts.cardWidth, collapsed: false, storyOrder: sc.story_order,
      });
    });
  }

  // ---- lane segments (BA6): contiguous runs of a lane's loaded chapters, joined by a spine ----
  const chaptersByLane = new Map<string, NodePosition[]>();
  for (const n of nodes) {
    if (n.shape !== 'chapter' || !n.laneId) continue;
    (chaptersByLane.get(n.laneId) ?? chaptersByLane.set(n.laneId, []).get(n.laneId)!).push(n);
  }
  for (const band of bands) {
    const chs = (chaptersByLane.get(band.id) ?? []).slice().sort(
      (a, b) => (slotOf.get(a.id) ?? 0) - (slotOf.get(b.id) ?? 0),
    );
    if (chs.length === 0) continue;
    const segs: LaneSegment[] = [];
    let run: NodePosition[] = [chs[0]];
    const flush = () => {
      const first = run[0], last = run[run.length - 1];
      segs.push({
        fromOrder: first.storyOrder ?? 0, toOrder: last.storyOrder ?? 0,
        x: first.x, width: last.x - first.x + opts.cardWidth,
      });
    };
    for (let i = 1; i < chs.length; i++) {
      const prev = chs[i - 1], cur = chs[i];
      // A run breaks when the two chapters are NOT adjacent in the global reading order — i.e.
      // some other lane's chapter (or a collapsed arc's rollup) occupies the slot between them.
      // That is BA6 non-contiguity, and it is what the eye sees: a hole in the band.
      //
      // This is POSITIONAL (slot i vs i+1), never `story_order + 1` arithmetic: story_order is the
      // strided packer axis, so consecutive chapters differ by the STRIDE (1000), and a `+1` test
      // would report EVERY arc as segmented. Positional adjacency is also stride-agnostic — it
      // survives any future change to the axis.
      const adjacent = (slotOf.get(cur.id) ?? 0) === (slotOf.get(prev.id) ?? 0) + 1;
      if (adjacent) run.push(cur);
      else { flush(); run = [cur]; }
    }
    flush();
    band.segments = segs;
  }
  for (const arcId of rollupArcs) { const b = bandById.get(arcId); if (b) b.collapsed = true; }

  // ---- UNASSIGNED chapters: spec nodes bound to no arc lane, in a strip BELOW every band ----
  //
  // These used to be computed into a `unplanned` array that nothing ever rendered — so a chapter with
  // no arc was INVISIBLE on the canvas: the user could not see it, and therefore could not drag it
  // into a lane to fix it. (It is also the normal post-decompile state: materialize-scenes mints
  // chapter+scene nodes with no arc until the arc analysis runs.) They now render in their own strip,
  // which makes them draggable into a real lane through the ordinary Row-1 path.
  //
  // The strip is deliberately NOT a LaneBand: `leafLaneAtY`/`bandAtY` only see real arcs, so a drop
  // into the strip finds no lane and no-ops (snap-back). You can drag OUT of unassigned, never INTO
  // it — un-filing a chapter is not an interaction the spec has.
  const bandsBottom = bands.length ? Math.max(...bands.map((b) => b.y + b.height)) : opts.padY;
  const unassignedY = chapters.some((ch) => !ch.structure_node_id || !bandById.has(ch.structure_node_id))
    ? bandsBottom + opts.laneGap
    : null;
  const unassigned: NodePosition[] = chapters
    .filter((ch) => !ch.structure_node_id || !bandById.has(ch.structure_node_id))
    .sort((a, b) => orderKey(a.story_order) - orderKey(b.story_order) || byRank(a, b))
    .map((ch, i) => ({
      id: ch.id,
      shape: 'chapter',
      laneId: null,
      x: opts.padX + i * opts.cardPitch,
      // Same in-band geometry a lane card uses (band top + header), so the strip reads as a lane.
      y: (unassignedY ?? 0) + opts.laneHeaderHeight,
      width: opts.cardWidth,
      collapsed: collapsedChapters.has(ch.id),
      storyOrder: ch.story_order,
    }));
  // ONE list for the canvas — the strip's cards are ordinary nodes (that is what makes them
  // draggable + hit-testable); `unassigned` above is a labelled view of the same objects.
  nodes.push(...unassigned);

  // Width/height are the true content extent so React Flow's viewport + minimap never clip a card.
  // Scenes branch PAST the last chapter slot (baseX + i·scenePitch), so width must measure the
  // rightmost NODE edge, not just the chapter/rollup slot count.
  const rightmost = nodes.reduce((m, n) => Math.max(m, n.x + n.width), 0);
  const width = (rightmost || opts.padX) + opts.padX;
  const bottom = unassignedY === null ? bandsBottom : unassignedY + opts.laneHeight;
  const height = bottom + opts.padY;
  return { lanes: bands, nodes, unassigned, unassignedY, width, height };
}

/**
 * 24 H5.1 — drag drop-target resolution. The LEAF lane whose vertical band contains `y` (flow
 * coordinates): the arc a chapter dropped at `y` would bind to. Only LEAF lanes carry chapters (a
 * saga/parent can't own a chapter directly), so a drop over a non-leaf-only region returns null.
 * Leaf bands never overlap each other (they stack), so there is at most one hit. Pure + headless —
 * the whole drag hit-test is unit-testable without React Flow.
 *
 * A COLLAPSED lane (or one under a collapsed ancestor) is deliberately still a valid target: binding
 * a chapter to a collapsed arc is a legitimate move, and the card correctly folds into that arc's
 * rollup — the count on the rollup is where it went. Refusing the drop would break the common
 * "file this chapter into that (collapsed) arc" gesture.
 */
export function leafLaneAtY(lanes: LaneBand[], y: number): LaneBand | null {
  for (const lane of lanes) {
    if (lane.isLeaf && y >= lane.y && y < lane.y + lane.height) return lane;
  }
  return null;
}

/**
 * 24 H5.4 — the scene-drag drop target. The CHAPTER card whose hit box contains the point (flow
 * coords): the chapter a scene dropped there would re-parent under. The box is the card's x-extent
 * by the lane's chapter-row strip (`laneHeight`) — generous vertically so a drop anywhere on the
 * card's row lands, which matters because a dragged card's reported position is its top-left.
 * Chapters never overlap in x within a lane, so at most one hit. Pure + headless.
 */
export function chapterAtPoint(
  nodes: NodePosition[],
  x: number,
  y: number,
  hitHeight: number = DEFAULT_LAYOUT_OPTIONS.laneHeight,
): NodePosition | null {
  for (const n of nodes) {
    if (n.shape !== 'chapter') continue;
    if (x >= n.x && x < n.x + n.width && y >= n.y && y < n.y + hitHeight) return n;
  }
  return null;
}

/**
 * 24 H5.3 — the chapter-REORDER drop target: the reading-order unit the drop lands AFTER.
 *
 * The x-axis is the book's reading order, and a "unit" is one slot on it — a chapter card OR a
 * collapsed arc's rollup (which occupies exactly one slot no matter how many chapters it hides).
 * Returns the last unit whose CENTRE is left of `x`, i.e. the one the dragged chapter would follow;
 * null ⇒ dropped before everything ⇒ it becomes the first chapter.
 *
 * Returning the rollup rather than skipping it is deliberate: the controller must be able to SEE
 * that the predecessor is a collapsed arc and refuse, because "after that arc" cannot be named to
 * the server (the API takes an `after_chapter_id`, and the arc's chapters aren't loaded). Silently
 * choosing the last loaded chapter instead would place the chapter BEFORE the collapsed arc's
 * chapters — a move the user did not ask for, on the actual manuscript.
 */
export function readingUnitBefore(
  nodes: NodePosition[],
  x: number,
  excludeId: string,
): NodePosition | null {
  let best: NodePosition | null = null;
  for (const n of nodes) {
    if (n.id === excludeId) continue;
    if (n.shape !== 'chapter' && n.shape !== 'arc-rollup') continue;
    if (n.x + n.width / 2 >= x) continue;
    if (!best || n.x > best.x) best = n;
  }
  return best;
}

/**
 * 24 H5.2 — the arc-band drag drop target. The INNERMOST band whose vertical range contains `y`.
 * Bands NEST (a saga's band wraps its arcs'), so the deepest hit is the most specific target: a drop
 * over a nested arc targets that arc, not its saga. Returns null off every band. Pure + headless —
 * the canvas reports only WHICH band was hit; the controller (which holds the shell's parent_id /
 * rank) decides whether that means "nest under it" or "become its next sibling".
 */
export function bandAtY(lanes: LaneBand[], y: number): LaneBand | null {
  let hit: LaneBand | null = null;
  for (const b of lanes) {
    if (y >= b.y && y < b.y + b.height && (!hit || b.depth > hit.depth)) hit = b;
  }
  return hit;
}
