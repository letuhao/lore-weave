import { describe, expect, it } from 'vitest';
import { normalizeSlice } from '../useProjectGraphSlice';
import type { GraphSlice } from '../../types/ontology';

// S-09 W3 (F-12) — the pure reader→canvas normalization. The view-aware graph
// reader returns GraphNode {id,kind,name,*_label} + GraphEdge {edge_type,
// source_id,target_id,*_label} with NO edge id; normalizeSlice maps them onto
// the canvas {id,name,kind} node + {id,source,target,predicate,confidence} edge,
// preferring localized labels and synthesizing a stable, unique edge key.

describe('normalizeSlice', () => {
  it('maps reader nodes/edges onto the canvas view shapes', () => {
    const slice: GraphSlice = {
      nodes: [{ id: 'kael', kind: 'character', name: 'Kael', glossary_entity_id: 'g1' }],
      edges: [{ edge_type: 'ally', source_id: 'kael', target_id: 'mira' }],
    };
    const { nodes, edges } = normalizeSlice(slice);
    expect(nodes[0]).toMatchObject({ id: 'kael', name: 'Kael', kind: 'character', glossary_entity_id: 'g1' });
    expect(edges[0]).toMatchObject({ source: 'kael', target: 'mira', predicate: 'ally', confidence: 1 });
    expect(edges[0].id).toContain('kael');
  });

  it('prefers the localized labels when present (C7)', () => {
    const slice: GraphSlice = {
      nodes: [{ id: 'k', kind: 'character', name: 'Kael', kind_label: 'Nhân vật', name_label: 'Kael-vi' }],
      edges: [{ edge_type: 'ally', source_id: 'k', target_id: 'm', edge_type_label: 'đồng minh' }],
    };
    const { nodes, edges } = normalizeSlice(slice);
    expect(nodes[0].name).toBe('Kael-vi');
    expect(nodes[0].kind).toBe('Nhân vật');
    expect(edges[0].predicate).toBe('đồng minh');
  });

  it('synthesizes UNIQUE edge ids even for parallel same-predicate edges', () => {
    const slice: GraphSlice = {
      nodes: [],
      edges: [
        { edge_type: 'ally', source_id: 'a', target_id: 'b' },
        { edge_type: 'ally', source_id: 'a', target_id: 'b' },
      ],
    };
    const { edges } = normalizeSlice(slice);
    expect(edges[0].id).not.toBe(edges[1].id);
  });

  it('falls back to canonical labels when localized ones are null', () => {
    const slice: GraphSlice = {
      nodes: [{ id: 'k', kind: 'character', name: 'Kael', kind_label: null, name_label: null }],
      edges: [{ edge_type: 'ally', source_id: 'k', target_id: 'm', edge_type_label: null }],
    };
    const { nodes, edges } = normalizeSlice(slice);
    expect(nodes[0].name).toBe('Kael');
    expect(edges[0].predicate).toBe('ally');
  });
});
