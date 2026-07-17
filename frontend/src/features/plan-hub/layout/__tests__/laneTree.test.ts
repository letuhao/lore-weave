// Plan Hub redesign — the lane-flow tree projection (buildLaneTree). Pure, headless.
import { describe, expect, it } from 'vitest';
import { autoExpandArcIds, buildLaneTree } from '../laneTree';
import type { ArcListNode, SummaryNode } from '../../types';

function arc(o: Partial<ArcListNode> & { id: string }): ArcListNode {
  return {
    kind: 'arc',
    parent_id: null,
    depth: 0,
    rank: 'a0',
    title: 'Arc',
    status: 'outline',
    version: 1,
    span: null,
    first_story_order: null,
    is_contiguous: true,
    chapter_count: 0,
    ...o,
  };
}

function chap(o: Partial<SummaryNode> & { id: string; structure_node_id: string }): SummaryNode {
  return {
    kind: 'chapter',
    parent_id: null,
    chapter_id: `book-${o.id}`,
    title: 'Chapter',
    status: 'drafting',
    version: 1,
    story_order: 0,
    rank: 'a0',
    beat_role: null,
    tension: null,
    pov_entity_id: null,
    present_entity_ids: [],
    present_entity_count: 0,
    written: false,
    ...o,
  } as SummaryNode;
}

function scene(o: Partial<SummaryNode> & { id: string; parent_id: string }): SummaryNode {
  return { ...chap({ ...o, id: o.id, structure_node_id: '' }), kind: 'scene', ...o } as SummaryNode;
}

function contentOf(...nodes: SummaryNode[]): Record<string, SummaryNode> {
  return Object.fromEntries(nodes.map((n) => [n.id, n]));
}

describe('buildLaneTree', () => {
  it('nests sub-arcs under their parent by rank, recomputing depth', () => {
    const arcs = [
      arc({ id: 'root', rank: 'a0' }),
      arc({ id: 'sub-b', parent_id: 'root', rank: 'b0', title: 'Sub B' }),
      arc({ id: 'sub-a', parent_id: 'root', rank: 'a0', title: 'Sub A' }),
    ];
    const tree = buildLaneTree(arcs, {}, new Set(['root']), new Set());
    expect(tree).toHaveLength(1);
    expect(tree[0].id).toBe('root');
    expect(tree[0].depth).toBe(0);
    expect(tree[0].subArcs.map((s) => s.id)).toEqual(['sub-a', 'sub-b']); // rank order
    expect(tree[0].subArcs[0].depth).toBe(1);
  });

  it('a COLLAPSED arc shows no chapters even when the window is loaded', () => {
    const arcs = [arc({ id: 'arc1', chapter_count: 2 })];
    const content = contentOf(
      chap({ id: 'c1', structure_node_id: 'arc1', story_order: 0 }),
      chap({ id: 'c2', structure_node_id: 'arc1', story_order: 1000 }),
    );
    const collapsed = buildLaneTree(arcs, content, new Set(), new Set());
    expect(collapsed[0].collapsed).toBe(true);
    expect(collapsed[0].chapters).toHaveLength(0);

    const open = buildLaneTree(arcs, content, new Set(['arc1']), new Set());
    expect(open[0].collapsed).toBe(false);
    expect(open[0].chapters.map((c) => c.id)).toEqual(['c1', 'c2']); // story order
  });

  it('scenes appear only under an EXPANDED chapter', () => {
    const arcs = [arc({ id: 'arc1' })];
    const content = contentOf(
      chap({ id: 'c1', structure_node_id: 'arc1' }),
      scene({ id: 's1', parent_id: 'c1', story_order: 1, title: 'Scene 1' }),
    );
    const chapterClosed = buildLaneTree(arcs, content, new Set(['arc1']), new Set());
    expect(chapterClosed[0].chapters[0].scenesExpanded).toBe(false);
    expect(chapterClosed[0].chapters[0].scenes).toHaveLength(0);

    const chapterOpen = buildLaneTree(arcs, content, new Set(['arc1']), new Set(['c1']));
    expect(chapterOpen[0].chapters[0].scenes.map((s) => s.id)).toEqual(['s1']);
  });

  it('carries the authorship source (default authored) for arc/chapter/scene', () => {
    const arcs = [arc({ id: 'arc1', source: 'mined' })];
    const content = contentOf(
      chap({ id: 'c1', structure_node_id: 'arc1', source: 'mined' }),
      chap({ id: 'c2', structure_node_id: 'arc1' }), // no source → authored
      scene({ id: 's1', parent_id: 'c1', source: 'mined' }),
    );
    const tree = buildLaneTree(arcs, content, new Set(['arc1']), new Set(['c1']));
    expect(tree[0].source).toBe('mined');
    expect(tree[0].chapters.find((c) => c.id === 'c1')!.source).toBe('mined');
    expect(tree[0].chapters.find((c) => c.id === 'c2')!.source).toBe('authored');
    expect(tree[0].chapters.find((c) => c.id === 'c1')!.scenes[0].source).toBe('mined');
  });
});

describe('autoExpandArcIds', () => {
  it('returns the first N ROOT arcs (never a sub-arc) in rank order', () => {
    const arcs = [
      arc({ id: 'r2', rank: 'b0' }),
      arc({ id: 'r1', rank: 'a0' }),
      arc({ id: 'sub', parent_id: 'r1', rank: 'a0' }),
      arc({ id: 'r3', rank: 'c0' }),
    ];
    expect(autoExpandArcIds(arcs, 2)).toEqual(['r1', 'r2']);
    expect(autoExpandArcIds(arcs, 10)).toEqual(['r1', 'r2', 'r3']); // sub excluded
  });
});
