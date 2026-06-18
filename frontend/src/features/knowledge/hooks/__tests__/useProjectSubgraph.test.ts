import { describe, expect, it } from 'vitest';
import { mergeSubgraph, type MergedSubgraph } from '../useProjectSubgraph';
import type { SubgraphResponse, SubgraphNode, SubgraphEdge } from '../../api';

// C19 — pure merge logic for the project graph hook (expand-hop accretion).
// The component never merges; this proves the hook's contract.

function node(id: string, over: Partial<SubgraphNode> = {}): SubgraphNode {
  return { id, name: id.toUpperCase(), kind: 'character', anchor_score: 0, mention_count: 1, glossary_entity_id: null, ...over };
}
function edge(id: string, source: string, target: string): SubgraphEdge {
  return { id, source, target, predicate: 'knows', confidence: 0.9 };
}
function payload(nodes: SubgraphNode[], edges: SubgraphEdge[], cap = false): SubgraphResponse {
  return { nodes, edges, node_cap_hit: cap };
}

const empty: MergedSubgraph = { nodes: [], edges: [], truncated: false };

describe('mergeSubgraph (C19)', () => {
  it('accretes new nodes and edges, deduped by id (incoming wins)', () => {
    const base = mergeSubgraph(empty, payload([node('a'), node('b')], [edge('e1', 'a', 'b')]));
    // expand 'b' → pulls in c + a fresh projection of b + a new edge
    const merged = mergeSubgraph(base, payload([node('b', { mention_count: 99 }), node('c')], [edge('e2', 'b', 'c')]));
    expect(merged.nodes.map((n) => n.id).sort()).toEqual(['a', 'b', 'c']);
    expect(merged.edges.map((e) => e.id).sort()).toEqual(['e1', 'e2']);
    // incoming projection of 'b' wins (fresher).
    expect(merged.nodes.find((n) => n.id === 'b')!.mention_count).toBe(99);
  });

  it('respects the node cap — trims the union and flags truncation', () => {
    const many = Array.from({ length: 10 }, (_, i) => node(`n${i}`));
    const base = mergeSubgraph(empty, payload(many.slice(0, 5), []), 5);
    const merged = mergeSubgraph(base, payload(many.slice(5), []), 5); // cap=5
    expect(merged.nodes.length).toBe(5);
    expect(merged.truncated).toBe(true);
    // existing-first: the original 5 are kept, not the new arrivals.
    expect(merged.nodes.map((n) => n.id)).toEqual(['n0', 'n1', 'n2', 'n3', 'n4']);
  });

  it('prunes edges whose endpoints were dropped by the cap', () => {
    const base = mergeSubgraph(empty, payload([node('a'), node('b')], [edge('e1', 'a', 'b')]), 2);
    // incoming 'c' would exceed cap=2 → dropped; its edge to 'a' must be pruned.
    const merged = mergeSubgraph(base, payload([node('c')], [edge('e2', 'a', 'c')]), 2);
    expect(merged.nodes.map((n) => n.id).sort()).toEqual(['a', 'b']);
    expect(merged.edges.map((e) => e.id)).toEqual(['e1']); // e2 pruned (c dropped)
  });

  it('propagates a base node_cap_hit into truncated', () => {
    const base = mergeSubgraph(empty, payload([node('a')], [], true));
    expect(base.truncated).toBe(true);
  });
});
