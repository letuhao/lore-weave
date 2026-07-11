// 24-H2.2 (PH14) — the lane-layout engine is the pillar's biggest custom surface, so it is
// pinned headless: every invariant PH14 states (rank-ordered depth-nested bands, global-story-order
// x with collapsed-run compression, BA6 contiguous-run segmentation, insert-shifts-never-reshuffles,
// the PH21 unplanned tray) is a test — the canvas only supplies pan/zoom over these numbers.
import { describe, expect, it } from 'vitest';
import {
  laneLayout, leafLaneAtY, chapterAtPoint, bandAtY, DEFAULT_LAYOUT_OPTIONS as D,
  type ArcShellNode, type LaneBand, type NodePosition, type WindowNode,
} from '../laneLayout';

const arc = (o: Partial<ArcShellNode> & { id: string }): ArcShellNode => ({
  kind: 'arc', parent_id: null, rank: 'm', title: o.id, span: null,
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
    expect(l.unplanned).toEqual([]);
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
    const leafH = D.laneHeight + D.sceneRowHeight;
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

  it('PH21: a chapter with no (or unknown) structure_node_id lands in the unplanned tray, off the lanes', () => {
    const shell = [arc({ id: 'A1', rank: 'a' })];
    const windows = [ch('c1', 'A1', 1), ch('u1', null, 2), ch('u2', 'GHOST', 3)];
    const l = laneLayout(shell, windows);
    expect(chapterNodes(l).map((n) => n.id)).toEqual(['c1']); // only the planned chapter is on a lane
    expect(l.unplanned.map((n) => n.id)).toEqual(['u1', 'u2']);
    expect(l.unplanned.every((n) => n.laneId === null)).toBe(true);
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
  const nodes: NodePosition[] = [
    np({ id: 'c1', shape: 'chapter', x: 24, y: 28 }),
    np({ id: 'c2', shape: 'chapter', x: 200, y: 28 }),
    np({ id: 's1', shape: 'scene', x: 24, y: 112 }),
  ];

  it('returns the chapter whose card box contains the drop point', () => {
    expect(chapterAtPoint(nodes, 60, 40)?.id).toBe('c1');
    expect(chapterAtPoint(nodes, 240, 60)?.id).toBe('c2');
  });
  it('the hit box spans the chapter ROW strip (laneHeight), so a drop low on the card still lands', () => {
    expect(chapterAtPoint(nodes, 60, 28 + D.laneHeight - 1)?.id).toBe('c1');
    expect(chapterAtPoint(nodes, 60, 28 + D.laneHeight)).toBeNull(); // past the row → miss
  });
  it('a drop in the horizontal gap BETWEEN two chapter cards hits neither', () => {
    // c1 ends at 24+128=152; c2 starts at 200 → 170 is the gutter.
    expect(chapterAtPoint(nodes, 170, 40)).toBeNull();
  });
  it('never returns a non-chapter node (a scene is not a re-parent target)', () => {
    expect(chapterAtPoint(nodes, 60, 112)).toBeNull(); // over the scene row
  });
  it('returns null when the point is off every card', () => {
    expect(chapterAtPoint(nodes, 999, 999)).toBeNull();
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
