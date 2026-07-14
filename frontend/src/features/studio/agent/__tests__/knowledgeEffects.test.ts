// 14_kg_panels.md A4 — Lane B effect handler for kg_* MCP writes.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { clearEffectHandlers, runEffectHandlers, matchEffectHandlers, type EffectContext } from '../effectRegistry';
import type { StudioHost } from '../../host/StudioHostProvider';

import {
  knowledgeEffect, registerKnowledgeEffectHandlers, KNOWLEDGE_WRITE_PATTERN, _resetKnowledgeEffectHandlers,
} from '../handlers/knowledgeEffects';

beforeEach(() => {
  clearEffectHandlers();
  _resetKnowledgeEffectHandlers();
});

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'kg_propose_fact',
  result: { fact_id: 'f1' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  ...over,
});

describe('knowledgeEffect (Lane B handler)', () => {
  it('invalidates every KG panel query key', () => {
    const c = ctx();
    knowledgeEffect(c);
    const keys = (c.queryClient.invalidateQueries as ReturnType<typeof vi.fn>).mock.calls.map((call) => call[0].queryKey);
    expect(keys).toContainEqual(['knowledge-projects']);
    expect(keys).toContainEqual(['knowledge-entities']);
    expect(keys).toContainEqual(['knowledge-entity-detail']);
    expect(keys).toContainEqual(['knowledge-entity-facts']);
    expect(keys).toContainEqual(['knowledge-timeline']);
    expect(keys).toContainEqual(['knowledge-gaps']);
    expect(keys).toContainEqual(['knowledge-jobs']);
    expect(keys).toContainEqual(['knowledge-subgraph']);
    expect(keys).toContainEqual(['knowledge-proposals-inbox']);
    expect(keys).toContainEqual(['knowledge-summaries']);
    expect(keys).toContainEqual(['knowledge-summary-versions']);
    expect(keys).toContainEqual(['kg-views']);
    expect(keys).toContainEqual(['kg-sync-available']);
    expect(keys).toContainEqual(['kg-graph-schemas']);
    expect(keys).toContainEqual(['kg-graph-schema']);
    expect(keys).toContainEqual(['kg-resolved-schema']);
    expect(keys).toContainEqual(['kg-schema-usage']);
    expect(keys).toContainEqual(['kg-schema-observed']);
    expect(keys).toContainEqual(['kg-adopt-preview']);
  });
});

describe('KNOWLEDGE_WRITE_PATTERN (write vs read tool names)', () => {
  it.each([
    'kg_project_create', 'kg_build_graph', 'kg_build_wiki', 'kg_run_benchmark',
    'kg_propose_fact', 'kg_propose_edge', 'kg_view_upsert', 'kg_view_delete',
    'kg_triage_resolve', 'kg_triage_place_edge', 'kg_triage_schema_write',
    'kg_schema_edit', 'kg_adopt_template', 'kg_sync_apply',
    // W0-S4 / X-4d — PINNED. Plan 30's X-4 listed kg_create_node as having "no handler"; it already
    // has one, because KNOWLEDGE_WRITE_PATTERN is a NEGATIVE-lookahead (allow-by-default over kg_*,
    // minus the reads) and kg_create_node is not in the lookahead. Wave 0's job is to VERIFY, not to
    // ADD: a second handler would DOUBLE-FIRE (effectCoverage.contract.test.ts's <=1 assertion reds).
    // This explicit positive case keeps the truth true, so Wave 8a finds a green assertion instead of
    // re-deriving the lookahead at 3am.
    'kg_create_node',
  ])('matches %s (a write)', (tool) => {
    expect(KNOWLEDGE_WRITE_PATTERN.test(tool)).toBe(true);
  });

  it('X-4d — kg_create_node routes through the REGISTERED handler (not just the pattern)', () => {
    registerKnowledgeEffectHandlers();
    expect(matchEffectHandlers('kg_create_node')).toEqual([knowledgeEffect]);
  });

  it.each([
    'kg_project_list', 'kg_graph_query', 'kg_world_query', 'kg_multi_query',
    'kg_entity_edge_timeline', 'kg_schema_read', 'kg_list_templates',
    'kg_sync_available', 'kg_view_read', 'kg_triage_list',
  ])('does NOT match %s (a read) — avoids thrashing the cache on a chatty read loop', (tool) => {
    expect(KNOWLEDGE_WRITE_PATTERN.test(tool)).toBe(false);
  });

  it('does not match a non-kg tool', () => {
    expect(KNOWLEDGE_WRITE_PATTERN.test('glossary_propose_new_entity')).toBe(false);
  });
});

describe('registerKnowledgeEffectHandlers wiring', () => {
  it('routes a real write tool through the registry', async () => {
    registerKnowledgeEffectHandlers();
    expect(matchEffectHandlers('kg_propose_fact')).toContain(knowledgeEffect);
    await runEffectHandlers(ctx({ tool: 'kg_propose_fact' }));
    expect(ctx().queryClient.invalidateQueries).toBeDefined();
  });

  it('does not double-register on a second call (idempotent)', () => {
    registerKnowledgeEffectHandlers();
    registerKnowledgeEffectHandlers();
    expect(matchEffectHandlers('kg_propose_fact')).toEqual([knowledgeEffect]);
  });
});
