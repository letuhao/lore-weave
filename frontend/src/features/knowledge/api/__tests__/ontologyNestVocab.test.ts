import { describe, it, expect, vi, beforeEach } from 'vitest';

// The schema endpoints return vocab VALUES separately (`vocab_values`, keyed by
// set code) — ontologyApi must nest them into vocab_sets[].values so SchemaEditor
// (which reads vs.values) shows them. Guards the contract-drift fix (#28 review).
const apiJson = vi.hoisted(() => vi.fn());
vi.mock('../../../../api', () => ({ apiJson }));

import { ontologyApi } from '../ontology';

beforeEach(() => apiJson.mockReset());

describe('ontologyApi vocab-value nesting', () => {
  it('nests resolved-schema vocab_values into the matching set', async () => {
    apiJson.mockResolvedValue({
      project_id: 'p1',
      schema_version: 3,
      allow_free_edges: false,
      vocab_sets: [{ code: 'status', label: 'Status', closed: true }],
      vocab_values: { status: [{ code: 'alive', label: 'Alive' }] },
    });
    const out = await ontologyApi.getResolvedSchema('p1', 'tok');
    expect(out.vocab_sets?.[0].values).toEqual([{ code: 'alive', label: 'Alive' }]);
  });

  it('leaves a set with no matching values as an empty list (not undefined)', async () => {
    apiJson.mockResolvedValue({
      schema_id: 's1', scope: 'project', code: 'c', name: 'n', schema_version: 1, allow_free_edges: true,
      vocab_sets: [{ code: 'empty', label: 'Empty', closed: false }],
      vocab_values: {},
    });
    const out = await ontologyApi.getSchema('s1', 'tok');
    expect(out.vocab_sets?.[0].values).toEqual([]);
  });

  it('is a no-op when the payload carries no vocab_values key', async () => {
    apiJson.mockResolvedValue({
      project_id: 'p1', schema_version: 1, allow_free_edges: true,
      vocab_sets: [{ code: 'status', label: 'Status', closed: false, values: [{ code: 'x', label: 'X' }] }],
    });
    const out = await ontologyApi.getResolvedSchema('p1', 'tok');
    // pre-existing nested values are preserved untouched.
    expect(out.vocab_sets?.[0].values).toEqual([{ code: 'x', label: 'X' }]);
  });
});
