// 24-H2.2 (PH14) — the lane-layout engine is the pillar's biggest custom surface, so it is
// pinned headless: every invariant PH14 states (rank-ordered depth-nested bands, global-story-order
// x with collapsed-run compression, BA6 contiguous-run segmentation, insert-shifts-never-reshuffles,
// the PH21 unplanned tray) is a test — the canvas only supplies pan/zoom over these numbers.
import { describe, expect, it } from 'vitest';
import {
  laneLayout, leafLaneAtY, chapterAtPoint, bandAtY, readingUnitBefore, DEFAULT_LAYOUT_OPTIONS as D,
  type ArcShellNode, type LaneBand, type NodePosition, type WindowNode,
} from '../laneLayout';

const arc = (o: Partial<ArcShellNode> & { id: string }): ArcShellNode => ({
  kind: 'arc', parent_id: null, rank: 'm', title: o.id, span: null,
  // A rollup sorts on the RAW axis (first_story_order) — the same one the chapter cards use; `span`
  // is the DISPLAY ordinal. Default the sort key from the span so the dense fixtures (where the two
  // units coincide) keep working; the strided suite below passes it explicitly.
  first_story_order: o.span ? o.span.from_order : null,
  is_contiguous: true, chapter_count: 0, ...o,
});
const ch = (id: string, structure_node_id: string | null, story_order: number, rank = 'm'): WindowNode =>
  ({ id, kind: 'chapter', parent_id: null, structure_node_id, chapter_id: id, story_order, rank });
const scene = (id: string, parent_id: string, story_order: number, rank = 'm'): WindowNode =>
  ({ id, kind: 'scene', parent_id, structure_node_id: null, chapter_id: null, story_order, rank });

const chapterNodes = (l: ReturnType<typeof laneLayout>) => l.nodes.filter((n) => n.shape === 'chapter');
const byId = (l: ReturnType<typeof laneLayout>, id: string) => l.nodes.find((n) => n.id === id);
const laneOf = (l: ReturnType<typeof laneLayout>, id: string) => l.lanes.find((b) => b.id === id);

describe('laneLayout — PH14 (24-H2.2)', () => {
  it('an empty shell yields empty lanes and nodes (the Hub paints nothing before load)', () => {
    const l = laneLayout([], []);
    expect(l.lanes).toEqual([]);
    expect(l.nodes).toEqual([]);
    expect(l.unassigned).toEqual([]);
    expect(l.unassignedY).toBeNull();
  });

  it('lane bands are rank-ordered and depth is recomputed from the tree, not trusted from the shell', () => {
    // Deliberately out-of-order input + a saga wrapping two arcs; the shell "depth" is absent.
    const shell = [
      arc({ id: 'A2', parent_id: 'S', rank: 'q', kind: 'arc' }),
      arc({ id: 'S', rank: 'a', kind: 'saga' }),
      arc({ id: 'A1', parent_id: 'S', rank: 'c', kind: 'arc' }),
    ];
    const l = laneLayout(shell, []);
    // Render order: saga first (root), then its arcs by rank (A1 'c' before A2 'q').
    expect(l.lanes.map((b) => b.id)).toEqual(['S', 'A1', 'A2']);
    expect(laneOf(l, 'S')!.depth).toBe(0);
    expect(laneOf(l, 'A1')!.depth).toBe(1);
    expect(laneOf(l, 'A2')!.depth).toBe(1);
    // The saga is a non-leaf header band; its arcs are leaf content lanes.
    expect(laneOf(l, 'S')!.isLeaf).toBe(false);
    expect(laneOf(l, 'A1')!.isLeaf).toBe(true);
  });

  it('a non-leaf band spans its children: header strip + stacked child bands + inter-child gap', () => {
    const shell = [
      arc({ id: 'S', rank: 'a', kind: 'saga' }),
      arc({ id: 'A1', parent_id: 'S', rank: 'a', kind: 'arc' }),
      arc({ id: 'A2', parent_id: 'S', rank: 'b', kind: 'arc' }),
    ];
    const l = laneLayout(shell, []);
    const S = laneOf(l, 'S')!, A1 = laneOf(l, 'A1')!, A2 = laneOf(l, 'A2')!;
    // A leaf band now reserves its OWN header strip too (so the title never overlaps the first card),
    // so its total height is the header strip + the content strip.
    const leafH = D.laneHeaderHeight + D.laneHeight + D.sceneRowHeight;
    expect(S.y).toBe(D.padY);
    expect(A1.y).toBe(D.padY + D.laneHeaderHeight); // A1 sits under the saga's header
    expect(A2.y).toBe(A1.y + leafH + D.laneGap); // A2 stacks under A1 with the sibling gap
    expect(S.height).toBe(D.laneHeaderHeight + leafH + D.laneGap + leafH); // wraps both children
  });

  it('chapter x is global story_order across lanes; scenes branch under their chapter', () => {
    const shell = [arc({ id: 'A1', rank: 'a', is_contiguous: true }), arc({ id: 'A2', rank: 'b' })];
    const windows = [ch('c1', 'A1', 1), ch('c2', 'A1', 2), ch('c3', 'A2', 3), scene('s1', 'c1', 1), scene('s2', 'c1', 2)];
    const l = laneLayout(shell, windows);
    expect(byId(l, 'c1')!.x).toBe(D.padX);
    expect(byId(l, 'c2')!.x).toBe(D.padX + D.cardPitch);
    expect(byId(l, 'c3')!.x).toBe(D.padX + 2 * D.cardPitch); // A2's chapter is right of A1's, by story_order
    // c1 and c3 sit on different lane bands (different y).
    expect(byId(l, 'c1')!.y).toBe(laneOf(l, 'A1')!.chapterY);
    expect(byId(l, 'c3')!.y).toBe(laneOf(l, 'A2')!.chapterY);
    // scenes branch from c1's x on the scene row, one scenePitch apart.
    const s1 = byId(l, 's1')!, s2 = byId(l, 's2')!;
    expect(s1.shape).toBe('scene');
    expect(s1.x).toBe(byId(l, 'c1')!.x);
    expect(s2.x).toBe(byId(l, 'c1')!.x + D.scenePitch);
    expect(s1.y).toBe(laneOf(l, 'A1')!.sceneY);
  });

  it('a collapsed arc compresses to ONE rollup slot; its chapters and scenes disappear', () => {
    const shell = [
      arc({ id: 'A1', rank: 'a', span: { from_order: 1, to_order: 2 }, chapter_count: 2 }),
      arc({ id: 'A2', rank: 'b' }),
    ];
    const windows = [ch('c1', 'A1', 1), ch('c2', 'A1', 2), ch('c3', 'A2', 3), scene('s1', 'c1', 1)];
    const l = laneLayout(shell, windows, { arcs: ['A1'] });
    // A1 folds to a single arc-rollup at its span start; its two chapters + scene are gone.
    expect(byId(l, 'c1')).toBeUndefined();
    expect(byId(l, 'c2')).toBeUndefined();
    expect(byId(l, 's1')).toBeUndefined();
    const rollup = byId(l, 'A1')!;
    expect(rollup.shape).toBe('arc-rollup');
    expect(rollup.rollupCount).toBe(2);
    expect(rollup.x).toBe(D.padX); // occupies the first slot (order 1)
    expect(byId(l, 'c3')!.x).toBe(D.padX + D.cardPitch); // A2's chapter takes the next slot — compression
    expect(laneOf(l, 'A1')!.collapsed).toBe(true);
  });

  it('collapsing a saga suppresses nested arcs — only the OUTERMOST rollup renders', () => {
    const shell = [
      arc({ id: 'S', rank: 'a', kind: 'saga', span: { from_order: 1, to_order: 4 }, chapter_count: 4 }),
      arc({ id: 'A1', parent_id: 'S', rank: 'a' }),
      arc({ id: 'A2', parent_id: 'S', rank: 'b' }),
    ];
    const windows = [ch('c1', 'A1', 1), ch('c2', 'A2', 2)];
    const l = laneLayout(shell, windows, { arcs: ['S', 'A1'] }); // A1 redundant under collapsed S
    const rollups = l.nodes.filter((n) => n.shape === 'arc-rollup');
    expect(rollups.map((r) => r.id)).toEqual(['S']); // only the saga rollup
    expect(byId(l, 'c1')).toBeUndefined();
    expect(byId(l, 'c2')).toBeUndefined();
  });

  it('a collapsed chapter keeps its own card but hides its scene branch', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const windows = [ch('c1', 'A1', 1), scene('s1', 'c1', 1), scene('s2', 'c1', 2)];
    const l = laneLayout(shell, windows, { chapters: ['c1'] });
    expect(byId(l, 'c1')!.collapsed).toBe(true);
    expect(byId(l, 's1')).toBeUndefined();
    expect(byId(l, 's2')).toBeUndefined();
  });

  it('BA6: a non-contiguous arc renders one SEGMENT per contiguous chapter run', () => {
    // A1 owns chapters at story_order 1 and 3; A2 owns 2 — so A1 is non-contiguous (a gap at 2).
    const shell = [arc({ id: 'A1', rank: 'a', is_contiguous: false }), arc({ id: 'A2', rank: 'b' })];
    const windows = [ch('c1', 'A1', 1), ch('c2', 'A2', 2), ch('c3', 'A1', 3)];
    const l = laneLayout(shell, windows);
    const A1 = laneOf(l, 'A1')!;
    expect(A1.contiguous).toBe(false);
    expect(A1.segments).toHaveLength(2); // {1..1} and {3..3}, spine-joined by the canvas
    expect(A1.segments[0].fromOrder).toBe(1);
    expect(A1.segments[1].fromOrder).toBe(3);
    // A single contiguous lane collapses to exactly one segment.
    expect(laneOf(l, 'A2')!.segments).toHaveLength(1);
  });

  it('insert SHIFTS downstream x by one pitch, never reshuffles lanes (PH14 stability law)', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const before = laneLayout(shell, [ch('c1', 'A1', 1), ch('c2', 'A1', 2), ch('c4', 'A1', 4)]);
    const after = laneLayout(shell, [ch('c1', 'A1', 1), ch('c2', 'A1', 2), ch('c3', 'A1', 3), ch('c4', 'A1', 4)]);
    // c1, c2 are pinned; c4 shifts right by exactly one card pitch; nothing else moved lanes.
    expect(byId(after, 'c1')!.x).toBe(byId(before, 'c1')!.x);
    expect(byId(after, 'c2')!.x).toBe(byId(before, 'c2')!.x);
    expect(byId(after, 'c4')!.x).toBe(byId(before, 'c4')!.x + D.cardPitch);
    expect(after.lanes.map((b) => [b.id, b.y])).toEqual(before.lanes.map((b) => [b.id, b.y]));
  });

  it('a chapter bound directly to a NON-leaf band reserves a content strip (no overlap with scenes or child bands)', () => {
    // review: a prologue bound to the saga S itself (S is non-leaf: it has arc A1). Its card + scene
    // branch must not collide with each other or overflow onto A1.
    const shell = [
      arc({ id: 'S', rank: 'a', kind: 'saga' }),
      arc({ id: 'A1', parent_id: 'S', rank: 'a' }),
    ];
    const l = laneLayout(shell, [ch('c0', 'S', 0), scene('s0', 'c0', 0), ch('c1', 'A1', 1)]);
    const S = laneOf(l, 'S')!, A1 = laneOf(l, 'A1')!;
    const c0 = byId(l, 'c0')!, s0 = byId(l, 's0')!;
    // the chapter sits below S's header; its scene sits below the chapter — distinct rows, no overlap.
    expect(c0.y).toBe(S.chapterY);
    expect(s0.y).toBe(S.sceneY);
    expect(s0.y).toBeGreaterThan(c0.y);
    // the chapter card (laneHeight tall) + its scene row are fully reserved ABOVE the child band A1.
    expect(A1.y).toBeGreaterThanOrEqual(S.sceneY + D.sceneRowHeight);
    expect(byId(l, 'c1')!.y).toBe(A1.chapterY);
  });

  it('is deterministic — same inputs, identical output (memoizable)', () => {
    const shell = [arc({ id: 'A1', rank: 'a' }), arc({ id: 'A2', rank: 'b' })];
    const windows = [ch('c2', 'A2', 2), ch('c1', 'A1', 1)];
    expect(laneLayout(shell, windows)).toEqual(laneLayout(shell, windows));
  });

  it('width covers scene branch cards that extend past the last chapter slot (no minimap clip)', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    // One chapter with many scenes — the last scene sits well right of the single chapter slot.
    const scenes = Array.from({ length: 5 }, (_, i) => scene(`s${i}`, 'c1', i + 1));
    const l = laneLayout(shell, [ch('c1', 'A1', 1), ...scenes]);
    const rightmostScene = Math.max(...l.nodes.filter((n) => n.shape === 'scene').map((n) => n.x + n.width));
    expect(l.width).toBeGreaterThanOrEqual(rightmostScene);
  });

  it('PH21: a chapter with no (or unknown) structure_node_id goes to the UNASSIGNED strip, not a lane', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const windows = [ch('c1', 'A1', 1), ch('u1', null, 2), ch('u2', 'GHOST', 3)];
    const l = laneLayout(shell, windows);
    expect(l.unassigned.map((n) => n.id)).toEqual(['u1', 'u2']);
    expect(l.unassigned.every((n) => n.laneId === null)).toBe(true);
    // only the arc-bound chapter is ON a lane…
    expect(chapterNodes(l).filter((n) => n.laneId !== null).map((n) => n.id)).toEqual(['c1']);
  });

  it('UNASSIGNED chapters are RENDERED (they are in `nodes`) — else you cannot see or fix them', () => {
    // They used to be computed into an array nothing drew, so an arc-less chapter was invisible on
    // the canvas: unseeable, and therefore un-draggable into a lane. Being in `nodes` is what makes
    // the ordinary Row-1 drag work on them.
    const l = laneLayout([arc({ id: 'A1', rank: 'a' })], [ch('c1', 'A1', 1), ch('u1', null, 2)]);
    expect(l.nodes.map((n) => n.id)).toContain('u1');
    expect(l.unassigned[0]).toBe(l.nodes.find((n) => n.id === 'u1')); // the SAME object, not a copy
  });

  it('the unassigned strip sits BELOW every lane band, and the canvas grows to hold it', () => {
    const l = laneLayout([arc({ id: 'A1', rank: 'a' })], [ch('c1', 'A1', 1), ch('u1', null, 2)]);
    const bandsBottom = Math.max(...l.lanes.map((b) => b.y + b.height));
    expect(l.unassignedY).not.toBeNull();
    expect(l.unassignedY!).toBeGreaterThanOrEqual(bandsBottom);
    expect(l.height).toBeGreaterThan(l.unassignedY!); // not clipped
  });

  it('no unassigned chapters ⇒ unassignedY is null (nothing to label)', () => {
    const l = laneLayout([arc({ id: 'A1', rank: 'a' })], [ch('c1', 'A1', 1)]);
    expect(l.unassigned).toEqual([]);
    expect(l.unassignedY).toBeNull();
  });
});

describe('leafLaneAtY — H5 drag drop-target (24-H5.1)', () => {
  // A saga band (non-leaf, y 0..300) containing two leaf arc lanes stacked inside it.
  const band = (o: Partial<LaneBand> & { id: string; y: number; height: number; isLeaf: boolean }): LaneBand => ({
    kind: 'arc', depth: 1, title: o.id, chapterY: o.y + 8, sceneY: o.y + 40,
    contiguous: true, segments: [], collapsed: false, ...o,
  });
  const lanes: LaneBand[] = [
    band({ id: 'saga', kind: 'saga', depth: 0, y: 0, height: 300, isLeaf: false }),
    band({ id: 'arc-a', y: 10, height: 130, isLeaf: true }),
    band({ id: 'arc-b', y: 150, height: 130, isLeaf: true }),
  ];

  it('returns the LEAF lane whose band contains y', () => {
    expect(leafLaneAtY(lanes, 40)?.id).toBe('arc-a');   // inside arc-a
    expect(leafLaneAtY(lanes, 200)?.id).toBe('arc-b');  // inside arc-b
  });
  it('never returns a non-leaf (saga) band even though it also contains y', () => {
    // y=5 is inside the saga band but outside both leaf arcs → no leaf target.
    expect(leafLaneAtY(lanes, 5)).toBeNull();
  });
  it('returns null for a y in no leaf band (a gap between lanes / off the canvas)', () => {
    expect(leafLaneAtY(lanes, 145)).toBeNull(); // gap between arc-a (ends 140) and arc-b (starts 150)
    expect(leafLaneAtY(lanes, 999)).toBeNull();
  });
  it('is half-open [y, y+height): the exact bottom edge belongs to the next lane', () => {
    expect(leafLaneAtY(lanes, 140)).toBeNull();        // arc-a bottom edge, not inside
    expect(leafLaneAtY(lanes, 150)?.id).toBe('arc-b'); // arc-b top edge, inside
  });
})

describe('chapterAtPoint — H5 Row-4 scene drop-target (24-H5.4)', () => {
  // Two chapter cards on one lane's chapter row (y=28), plus a scene on the scene row (y=112).
  const np = (o: Partial<NodePosition> & { id: string; shape: NodePosition['shape']; x: number; y: number }): NodePosition =>
    ({ laneId: 'arc-a', width: D.cardWidth, collapsed: false, storyOrder: 1, ...o });
  // Geometry-relative to the layout options (was hardcoded for cardWidth=128; broke when S4 widened
  // cards to 208). c1 spans [padX, padX+cardWidth); c2 sits one cardPitch over; the scene is on the
  // row below (chapterY + laneHeight). Using D.* keeps this correct under any future dimension change.
  const SCENE_Y = 28 + D.laneHeight;
  const nodes: NodePosition[] = [
    np({ id: 'c1', shape: 'chapter', x: D.padX, y: 28 }),
    np({ id: 'c2', shape: 'chapter', x: D.padX + D.cardPitch, y: 28 }),
    np({ id: 's1', shape: 'scene', x: D.padX, y: SCENE_Y + 2 }),
  ];

  it('returns the chapter whose card box contains the drop point', () => {
    expect(chapterAtPoint(nodes, D.padX + 40, 40)?.id).toBe('c1');
    expect(chapterAtPoint(nodes, D.padX + D.cardPitch + 40, 60)?.id).toBe('c2');
  });
  it('the hit box spans the chapter ROW strip (laneHeight), so a drop low on the card still lands', () => {
    expect(chapterAtPoint(nodes, D.padX + 40, 28 + D.laneHeight - 1)?.id).toBe('c1');
    expect(chapterAtPoint(nodes, D.padX + 40, 28 + D.laneHeight)).toBeNull(); // past the row → miss
  });
  it('a drop in the horizontal gap BETWEEN two chapter cards hits neither', () => {
    // c1 ends at padX+cardWidth; c2 starts at padX+cardPitch → the gutter is the middle of that gap.
    const gutter = D.padX + D.cardWidth + (D.cardPitch - D.cardWidth) / 2;
    expect(chapterAtPoint(nodes, gutter, 40)).toBeNull();
  });
  it('never returns a non-chapter node (a scene is not a re-parent target)', () => {
    expect(chapterAtPoint(nodes, D.padX + 40, SCENE_Y + 2)).toBeNull(); // over the scene row
  });
  it('returns null when the point is off every card', () => {
    expect(chapterAtPoint(nodes, 9999, 9999)).toBeNull();
  });
})

describe('bandAtY — H5 Row-2 arc-band drop target (24-H5.2)', () => {
  const band = (o: Partial<LaneBand> & { id: string; y: number; height: number; depth: number }): LaneBand => ({
    kind: 'arc', title: o.id, chapterY: o.y + 8, sceneY: o.y + 40, isLeaf: true,
    contiguous: true, segments: [], collapsed: false, ...o,
  });
  // A saga band (depth 0, y 0..300) WRAPPING two nested arc bands — the real nesting geometry.
  const lanes: LaneBand[] = [
    band({ id: 'saga', kind: 'saga', depth: 0, y: 0, height: 300, isLeaf: false }),
    band({ id: 'arc-a', depth: 1, y: 30, height: 120 }),
    band({ id: 'arc-b', depth: 1, y: 160, height: 120 }),
  ];

  it('returns the INNERMOST band containing y — a nested arc wins over its wrapping saga', () => {
    expect(bandAtY(lanes, 60)?.id).toBe('arc-a');
    expect(bandAtY(lanes, 200)?.id).toBe('arc-b');
  });
  it('falls back to the saga where only IT covers y (its header strip / the inter-arc gap)', () => {
    expect(bandAtY(lanes, 10)?.id).toBe('saga');  // above arc-a, inside the saga
    expect(bandAtY(lanes, 155)?.id).toBe('saga'); // the gap between arc-a and arc-b
  });
  it('returns null off every band', () => {
    expect(bandAtY(lanes, 999)).toBeNull();
  });
})

// ── The STRIDED reading axis (the production shape) ────────────────────────────────────────────
// A chapter's story_order is `chapter_sort * 1000` (the packer axis it shares with its scenes and
// with the canon-rule windows), so ADJACENT chapters differ by 1000, never by 1. The layout must
// therefore treat adjacency POSITIONALLY. A `prev + 1` test — which is what shipped — reports every
// arc as segmented the moment real (strided) data arrives, while passing on dense test fixtures.
const STRIDE = 1000;

describe('laneLayout — the strided story_order axis', () => {
  it('consecutive STRIDED chapters are ONE contiguous segment (not one per chapter)', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const windows = [ch('c1', 'A1', 1 * STRIDE), ch('c2', 'A1', 2 * STRIDE), ch('c3', 'A1', 3 * STRIDE)];
    const l = laneLayout(shell, windows);
    expect(laneOf(l, 'A1')!.segments).toHaveLength(1); // `+1` arithmetic would give 3
  });

  it('BA6 non-contiguity still detected on the strided axis (another lane interleaves)', () => {
    // A1 owns chapters 1 and 3; A2 owns 2. On the strided axis: 1000, 3000 vs 2000.
    const shell = [arc({ id: 'A1', rank: 'a', is_contiguous: false }), arc({ id: 'A2', rank: 'b' })];
    const windows = [ch('c1', 'A1', 1 * STRIDE), ch('c2', 'A2', 2 * STRIDE), ch('c3', 'A1', 3 * STRIDE)];
    const l = laneLayout(shell, windows);
    expect(laneOf(l, 'A1')!.segments).toHaveLength(2); // the hole at slot 2 is real
    expect(laneOf(l, 'A2')!.segments).toHaveLength(1);
  });

  it('x still follows reading order on the strided axis', () => {
    const shell = [arc({ id: 'A1', rank: 'a' }), arc({ id: 'A2', rank: 'b' })];
    const windows = [ch('c1', 'A1', 1 * STRIDE), ch('c2', 'A2', 2 * STRIDE), ch('c3', 'A1', 3 * STRIDE)];
    const l = laneLayout(shell, windows);
    expect(byId(l, 'c1')!.x).toBe(D.padX + 0 * D.cardPitch);
    expect(byId(l, 'c2')!.x).toBe(D.padX + 1 * D.cardPitch);
    expect(byId(l, 'c3')!.x).toBe(D.padX + 2 * D.cardPitch);
  });

  it('a chapter with an UNKNOWN position (null) sorts LAST — never silently first', () => {
    // The shipped bug coerced null → 0, which claimed an unordered chapter was the book's FIRST
    // (and, while chapter story_order was never written at all, tied EVERY chapter at 0).
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const windows = [
      { ...ch('c-unknown', 'A1', 0), story_order: null } as WindowNode,
      ch('c1', 'A1', 1 * STRIDE),
      ch('c2', 'A1', 2 * STRIDE),
    ];
    const l = laneLayout(shell, windows);
    expect(byId(l, 'c1')!.x).toBe(D.padX + 0 * D.cardPitch);
    expect(byId(l, 'c2')!.x).toBe(D.padX + 1 * D.cardPitch);
    expect(byId(l, 'c-unknown')!.x).toBe(D.padX + 2 * D.cardPitch); // last slot
    expect(byId(l, 'c-unknown')!.storyOrder).toBeNull();            // and it renders as unordered
  });
});

describe('laneLayout — a collapsed arc\'s rollup interleaves on the RAW axis', () => {
  it('places a rollup AFTER the loaded chapters that precede it in reading order', () => {
    // The live-caught bug: the rollup was sorted by `span.from_order` (a reading POSITION, e.g. 4)
    // while chapter cards sort by raw `story_order` (e.g. 1000). Mixing the two units put Arc Beta's
    // rollup at slot 0 — visually BEFORE chapters that actually precede it.
    const shell = [
      arc({ id: 'A1', rank: 'a', span: { from_order: 1, to_order: 3 }, first_story_order: 1 * STRIDE, chapter_count: 3 }),
      arc({ id: 'A2', rank: 'b', span: { from_order: 4, to_order: 4 }, first_story_order: 4 * STRIDE, chapter_count: 1 }),
    ];
    // A1 is expanded (3 loaded chapters); A2 is COLLAPSED ⇒ one rollup card.
    const windows = [ch('c1', 'A1', 1 * STRIDE), ch('c2', 'A1', 2 * STRIDE), ch('c3', 'A1', 3 * STRIDE)];
    const l = laneLayout(shell, windows, { arcs: ['A2'] });

    expect(byId(l, 'c1')!.x).toBe(D.padX + 0 * D.cardPitch);
    expect(byId(l, 'c2')!.x).toBe(D.padX + 1 * D.cardPitch);
    expect(byId(l, 'c3')!.x).toBe(D.padX + 2 * D.cardPitch);
    expect(byId(l, 'A2')!.x).toBe(D.padX + 3 * D.cardPitch); // the rollup lands LAST, not first
    expect(byId(l, 'A2')!.shape).toBe('arc-rollup');
  });

  it('an empty arc pins its rollup to the left column, and never steals a positioned arc\'s slot', () => {
    // null first_story_order ≠ story position 0: the empty arc must NOT sort ahead of a positioned
    // one. It ALSO must not cascade by slot index (the manual-create bug: N empty arcs marching
    // diagonally, the first overlapping its own lane header). It pins to the lane's first column,
    // in its OWN band row — so a stack of freshly-created empty arcs reads as a clean left column.
    const shell = [
      arc({ id: 'A1', rank: 'a', span: { from_order: 1, to_order: 1 }, first_story_order: 1 * STRIDE, chapter_count: 1 }),
      arc({ id: 'A2', rank: 'b', span: null, first_story_order: null, chapter_count: 0 }),
    ];
    const l = laneLayout(shell, [ch('c1', 'A1', 1 * STRIDE)], { arcs: ['A1', 'A2'] });
    const a1 = byId(l, 'A1')!, a2 = byId(l, 'A2')!;
    expect(a1.x).toBe(D.padX + 0 * D.cardPitch); // positioned arc keeps slot 0 — the empty one didn't displace it
    expect(a2.x).toBe(D.padX);                    // empty arc pinned left, NOT cascaded to padX + 1*pitch
    expect(a2.y).not.toBe(a1.y);                  // different bands ⇒ no overlap despite the shared x
  });

  it('multiple empty arcs stack in a left column, one per band — no diagonal cascade', () => {
    const shell = [
      arc({ id: 'E1', rank: 'a', span: null, first_story_order: null, chapter_count: 0 }),
      arc({ id: 'E2', rank: 'b', span: null, first_story_order: null, chapter_count: 0 }),
      arc({ id: 'E3', rank: 'c', span: null, first_story_order: null, chapter_count: 0 }),
    ];
    const l = laneLayout(shell, [], { arcs: ['E1', 'E2', 'E3'] });
    const xs = ['E1', 'E2', 'E3'].map((id) => byId(l, id)!.x);
    const ys = ['E1', 'E2', 'E3'].map((id) => byId(l, id)!.y);
    expect(new Set(xs)).toEqual(new Set([D.padX]));   // all at the left column, no cascade
    expect(new Set(ys).size).toBe(3);                 // each in its own band row
  });
});

describe('readingUnitBefore — the Row-3 reorder drop target', () => {
  const units: NodePosition[] = [
    { id: 'c1', shape: 'chapter', laneId: 'A1', x: 24, y: 0, width: 128, collapsed: false, storyOrder: 1000 },
    { id: 'A2', shape: 'arc-rollup', laneId: 'A2', x: 168, y: 50, width: 128, collapsed: true, storyOrder: 2000 },
    { id: 'c3', shape: 'chapter', laneId: 'A1', x: 312, y: 0, width: 128, collapsed: false, storyOrder: 3000 },
    { id: 's1', shape: 'scene', laneId: 'A1', x: 24, y: 90, width: 100, collapsed: false, storyOrder: 1000 },
  ];

  it('returns the last unit whose centre is left of the drop', () => {
    // c3 spans 312..440, so its centre is 376: a drop at 350 is still LEFT of that centre, and the
    // unit you landed after is A2 (centre 232). Only past 376 does c3 become the predecessor.
    expect(readingUnitBefore(units, 400, 'c1')!.id).toBe('c3');
    expect(readingUnitBefore(units, 350, 'c1')!.id).toBe('A2');
    expect(readingUnitBefore(units, 250, 'c1')!.id).toBe('A2');
  });

  it('a drop before everything returns null (⇒ becomes the first chapter)', () => {
    expect(readingUnitBefore(units, 10, 'c3')).toBeNull();
  });

  it('never returns the dragged chapter itself', () => {
    expect(readingUnitBefore(units, 350, 'c3')!.id).toBe('A2');
  });

  it('scenes are not reading-order units — only chapters and rollups occupy a slot', () => {
    const hit = readingUnitBefore(units, 200, 'c3');
    expect(hit!.id).toBe('c1'); // s1 shares c1's x but must never be the predecessor
    expect(hit!.shape).toBe('chapter');
  });

  it('REPORTS a collapsed arc rollup as the predecessor (the controller must see it and refuse)', () => {
    // Skipping the rollup and silently returning c1 would place the chapter BEFORE that arc's
    // hidden chapters — a manuscript move the user never asked for.
    const hit = readingUnitBefore(units, 300, 'c3');
    expect(hit!.id).toBe('A2');
    expect(hit!.shape).toBe('arc-rollup');
  });
});
