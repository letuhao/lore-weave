import {
  isBatchBody,
  parseRequestSteps,
  buildStepOutcomes,
  annotateBatchStepOutcomes,
} from '../src/scope/scope-filter.js';
import { domainScope } from '../src/scope/tool-policy.js';

// A knowledge-read key: may call kg_graph_query / memory_search, NOT book_get or a write.
const KNOWLEDGE_READ = ['read', domainScope('knowledge')];

// A two-step batch the agent might send: a kg read + a memory read (both in scope).
const batchBody = [
  { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
  { jsonrpc: '2.0', method: 'tools/call', params: { name: 'memory_search' }, id: 2 },
];

function upstreamBatch(entries: unknown[]): string {
  return JSON.stringify(entries);
}

describe('isBatchBody', () => {
  it('is true only for an array', () => {
    expect(isBatchBody(batchBody)).toBe(true);
    expect(isBatchBody({ jsonrpc: '2.0', method: 'tools/list', id: 1 })).toBe(false);
    expect(isBatchBody(undefined)).toBe(false);
    expect(isBatchBody(null)).toBe(false);
    expect(isBatchBody('x')).toBe(false);
  });
});

describe('parseRequestSteps', () => {
  it('returns one descriptor per batch element in wire order', () => {
    const steps = parseRequestSteps(batchBody);
    expect(steps).toEqual([
      { id: 1, name: 'kg_graph_query', isToolCall: true },
      { id: 2, name: 'memory_search', isToolCall: true },
    ]);
  });

  it('captures a non-call step by its method, and a missing id as null', () => {
    const steps = parseRequestSteps([
      { jsonrpc: '2.0', method: 'tools/list', id: 9 },
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' } }, // no id (notification)
    ]);
    expect(steps[0]).toEqual({ id: 9, name: 'tools/list', isToolCall: false });
    expect(steps[1]).toEqual({ id: null, name: 'kg_graph_query', isToolCall: true });
  });

  it('treats a single (non-array) body as a length-1 list', () => {
    expect(parseRequestSteps({ jsonrpc: '2.0', method: 'tools/call', params: { name: 'memory_search' }, id: 4 })).toEqual([
      { id: 4, name: 'memory_search', isToolCall: true },
    ]);
  });
});

describe('buildStepOutcomes', () => {
  it('marks all in-scope steps relayed when the upstream batch has no errors', () => {
    const upstream = upstreamBatch([
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
      { jsonrpc: '2.0', id: 2, result: { ok: true } },
    ]);
    expect(buildStepOutcomes(batchBody, KNOWLEDGE_READ, upstream)).toEqual([
      { id: 1, name: 'kg_graph_query', outcome: 'relayed' },
      { id: 2, name: 'memory_search', outcome: 'relayed' },
    ]);
  });

  it('marks a step FAILED when its upstream entry (matched by id) is an error — partial landing', () => {
    // Step 1 landed; step 2 errored at the domain (e.g. not found). The agent must see both.
    const upstream = upstreamBatch([
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
      { jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' } },
    ]);
    expect(buildStepOutcomes(batchBody, KNOWLEDGE_READ, upstream)).toEqual([
      { id: 1, name: 'kg_graph_query', outcome: 'relayed' },
      { id: 2, name: 'memory_search', outcome: 'failed' },
    ]);
  });

  it('matches by id, not position (upstream may reorder its batch response)', () => {
    const upstream = upstreamBatch([
      { jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' } },
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
    ]);
    expect(buildStepOutcomes(batchBody, KNOWLEDGE_READ, upstream)).toEqual([
      { id: 1, name: 'kg_graph_query', outcome: 'relayed' },
      { id: 2, name: 'memory_search', outcome: 'failed' },
    ]);
  });

  it('marks an out-of-scope step denied_scope from the EDGE decision (not the upstream)', () => {
    // book_get is outside a knowledge-read key. The edge is the source of truth.
    const mixed = [
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'kg_graph_query' }, id: 1 },
      { jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 2 },
    ];
    const upstream = upstreamBatch([{ jsonrpc: '2.0', id: 1, result: { ok: true } }]);
    expect(buildStepOutcomes(mixed, KNOWLEDGE_READ, upstream)).toEqual([
      { id: 1, name: 'kg_graph_query', outcome: 'relayed' },
      { id: 2, name: 'book_get', outcome: 'denied_scope' },
    ]);
  });

  it('never marks a step denied_scope for a wildcard key', () => {
    const mixed = [{ jsonrpc: '2.0', method: 'tools/call', params: { name: 'book_get' }, id: 1 }];
    const upstream = upstreamBatch([{ jsonrpc: '2.0', id: 1, result: { ok: true } }]);
    expect(buildStepOutcomes(mixed, ['*'], upstream)).toEqual([
      { id: 1, name: 'book_get', outcome: 'relayed' },
    ]);
  });

  it('does NOT fabricate failure when the upstream is not a parseable batch array', () => {
    // SSE / single-error / garbage upstream → relayed steps stay relayed (honest = no claim).
    expect(buildStepOutcomes(batchBody, KNOWLEDGE_READ, 'event: message\ndata: ...')).toEqual([
      { id: 1, name: 'kg_graph_query', outcome: 'relayed' },
      { id: 2, name: 'memory_search', outcome: 'relayed' },
    ]);
  });
});

describe('annotateBatchStepOutcomes (per-item _meta, bare array preserved)', () => {
  it('keeps the JSON-RPC array shape and tags each item with _meta.step_outcome', () => {
    const upstream = upstreamBatch([
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
      { jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' } },
    ]);
    const out = JSON.parse(annotateBatchStepOutcomes(batchBody, KNOWLEDGE_READ, upstream));
    // STILL a bare array (transport-transparent) — not wrapped in an object.
    expect(Array.isArray(out)).toBe(true);
    expect(out).toHaveLength(2);
    // Each item is the ORIGINAL item plus an additive _meta.step_outcome.
    expect(out[0]).toEqual({ jsonrpc: '2.0', id: 1, result: { ok: true }, _meta: { step_outcome: 'relayed' } });
    expect(out[1]).toEqual({ jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' }, _meta: { step_outcome: 'failed' } });
  });

  it('matches the verdict to the item by id (upstream may reorder)', () => {
    const upstream = upstreamBatch([
      { jsonrpc: '2.0', id: 2, error: { code: -32000, message: 'boom' } },
      { jsonrpc: '2.0', id: 1, result: { ok: true } },
    ]);
    const out = JSON.parse(annotateBatchStepOutcomes(batchBody, KNOWLEDGE_READ, upstream));
    const byId = Object.fromEntries(out.map((i: { id: number; _meta: { step_outcome: string } }) => [i.id, i._meta.step_outcome]));
    expect(byId).toEqual({ 1: 'relayed', 2: 'failed' });
  });

  it('preserves an existing item _meta (merges, does not clobber)', () => {
    const upstream = upstreamBatch([{ jsonrpc: '2.0', id: 1, result: { ok: true }, _meta: { undo_hint: 'x' } }, { jsonrpc: '2.0', id: 2, result: {} }]);
    const out = JSON.parse(annotateBatchStepOutcomes(batchBody, KNOWLEDGE_READ, upstream));
    expect(out[0]._meta).toEqual({ undo_hint: 'x', step_outcome: 'relayed' });
  });

  it('returns a SINGLE request response byte-for-byte unchanged', () => {
    const single = { jsonrpc: '2.0', method: 'tools/call', params: { name: 'memory_search' }, id: 4 };
    const upstream = '{"jsonrpc":"2.0","id":4,"result":{"ok":true}}';
    expect(annotateBatchStepOutcomes(single, KNOWLEDGE_READ, upstream)).toBe(upstream);
  });

  it('returns a non-array (object) upstream body for a batch unchanged', () => {
    const upstream = '{"jsonrpc":"2.0","error":{"code":-32600,"message":"bad"},"id":null}';
    expect(annotateBatchStepOutcomes(batchBody, KNOWLEDGE_READ, upstream)).toBe(upstream);
  });

  it('returns a non-JSON (SSE) upstream body unchanged', () => {
    const upstream = 'event: message\ndata: {"x":1}\n\n';
    expect(annotateBatchStepOutcomes(batchBody, KNOWLEDGE_READ, upstream)).toBe(upstream);
  });
});
