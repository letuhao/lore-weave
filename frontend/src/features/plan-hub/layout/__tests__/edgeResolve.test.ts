// 24 PH13 — "an edge whose other endpoint is not loaded/collapsed renders as a stub connector into
// the collapsed node, which carries an edge-count badge — NEVER silently dropped."
//
// The shipped canvas mapped from/to straight into React Flow. An endpoint inside a collapsed arc is
// not in the node list, so RF discarded the edge without a word: a setup with no payoff, and nothing
// saying a payoff existed. These tests pin every branch of the resolution.
import { describe, expect, it } from 'vitest';
import { resolveEdges } from '../edgeResolve';
import type { NodePosition, SceneLinkEdge } from '../../types';

const node = (id: string, shape: NodePosition['shape'] = 'scene'): NodePosition => ({
  id,
  shape,
  laneId: 'arc-1',
  x: 0,
  y: 0,
  width: 128,
  collapsed: false,
  storyOrder: 1,
});

const edge = (o: Partial<SceneLinkEdge> = {}): SceneLinkEdge => ({
  id: 'e1',
  from_node_id: 's1',
  to_node_id: 's2',
  kind: 'setup_payoff',
  label: null,
  from_chapter_node_id: 'ch-1',
  to_chapter_node_id: 'ch-2',
  from_arc_id: 'arc-1',
  to_arc_id: 'arc-2',
  ...o,
});

describe('resolveEdges (PH13)', () => {
  it('both scenes rendered ⇒ a normal, non-stub edge', () => {
    const r = resolveEdges([edge()], [node('s1'), node('s2')]);
    expect(r.edges).toHaveLength(1);
    expect(r.edges[0]).toMatchObject({ source: 's1', target: 's2', stub: false });
    expect(r.hiddenByNode).toEqual({});
  });

  it('a scene inside a COLLAPSED CHAPTER stubs into the chapter card', () => {
    // s2 is not rendered, but its chapter card is on screen.
    const r = resolveEdges([edge()], [node('s1'), node('ch-2', 'chapter')]);
    expect(r.edges[0]).toMatchObject({ source: 's1', target: 'ch-2', stub: true });
  });

  it('a scene inside a COLLAPSED ARC stubs into the arc rollup', () => {
    // neither s2 nor its chapter is loaded — only the rollup (whose id IS the arc id) is rendered.
    const r = resolveEdges([edge()], [node('s1'), node('arc-2', 'arc-rollup')]);
    expect(r.edges[0]).toMatchObject({ source: 's1', target: 'arc-2', stub: true });
  });

  it('prefers the most SPECIFIC visible ancestor (chapter over arc)', () => {
    const r = resolveEdges(
      [edge()],
      [node('s1'), node('ch-2', 'chapter'), node('arc-2', 'arc-rollup')],
    );
    expect(r.edges[0].target).toBe('ch-2'); // not the rollup
  });

  it('BOTH ends folded into the same card ⇒ no self-loop, but the card BADGES it', () => {
    // a setup and its payoff both inside one collapsed arc. Drawing a circle onto itself is noise;
    // dropping it silently is the bug. So: count it on the card.
    const r = resolveEdges(
      [edge({ from_arc_id: 'arc-1', to_arc_id: 'arc-1' })],
      [node('arc-1', 'arc-rollup')],
    );
    expect(r.edges).toHaveLength(0);
    expect(r.hiddenByNode).toEqual({ 'arc-1': 1 });
  });

  it('one end unresolvable ⇒ the RESOLVED end still carries the count', () => {
    // s2's arc is collapsed AND its rollup isn't rendered either (nested under another collapsed
    // arc). We can't draw the edge, but s1 can still say "you have a link going somewhere".
    const r = resolveEdges([edge({ to_arc_id: null, to_chapter_node_id: null })], [node('s1')]);
    expect(r.edges).toHaveLength(0);
    expect(r.hiddenByNode).toEqual({ s1: 1 });
    expect(r.unresolvable).toBe(0);
  });

  it('NEITHER end resolvable ⇒ counted as unresolvable, never silently forgotten', () => {
    const r = resolveEdges([edge()], []);
    expect(r.edges).toHaveLength(0);
    expect(r.hiddenByNode).toEqual({});
    expect(r.unresolvable).toBe(1); // nothing on screen can carry the badge — but we KNOW
  });

  it('counts accumulate per node across several edges', () => {
    const edges = [
      edge({ id: 'e1', from_arc_id: 'arc-1', to_arc_id: 'arc-1' }),
      edge({ id: 'e2', from_arc_id: 'arc-1', to_arc_id: 'arc-1' }),
    ];
    const r = resolveEdges(edges, [node('arc-1', 'arc-rollup')]);
    expect(r.hiddenByNode['arc-1']).toBe(2);
  });

  it('a null ancestry endpoint does not crash and does not fake a lane', () => {
    const r = resolveEdges(
      [edge({ from_chapter_node_id: null, from_arc_id: null })],
      [node('s2')],
    );
    expect(r.edges).toHaveLength(0);
    expect(r.hiddenByNode).toEqual({ s2: 1 }); // the end we DO have still reports it
  });
});
