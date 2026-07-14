// W0-S4 / X-4b — Lane B effect handler for composition_authoring_run_* MCP writes.
// The reconciler's header used to claim "authoring_run has no MCP tools at all, REST-only, no Studio
// consumer to go stale". BOTH halves were false: server.py registers 11 composition_authoring_run_*
// tools (from :1616) and the shipped `agent-mode` panel (catalog.ts:258) is exactly the consumer that
// went stale — an agent accept_unit/pause left Mission Control showing the PREVIOUS state.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import {
  clearEffectHandlers, matchEffectHandlers, runEffectHandlers, type EffectContext,
} from '../../effectRegistry';
import type { StudioHost } from '../../../host/StudioHostProvider';
import {
  authoringRunEffect, registerAuthoringRunEffectHandlers, _resetAuthoringRunEffectHandlers,
} from '../authoringRunEffects';

beforeEach(() => {
  clearEffectHandlers();
  _resetAuthoringRunEffectHandlers();
});

const ctx = (over: Partial<EffectContext> = {}): EffectContext => ({
  tool: 'composition_authoring_run_pause',
  result: { success: true, status: 'paused' },
  bookId: 'b1',
  host: { publish: vi.fn() } as unknown as StudioHost,
  queryClient: { invalidateQueries: vi.fn() } as unknown as EffectContext['queryClient'],
  ...over,
});

// The 11 REAL tool names, from services/composition-service/app/mcp/server.py (grep
// 'name="composition_authoring_run_'). Testing the real names — not a pattern — is what catches the
// string-vs-RegExp silent no-op that a pattern-only test cannot see.
const TOOLS = [
  'composition_authoring_run_list', 'composition_authoring_run_get',
  'composition_authoring_run_create', 'composition_authoring_run_gate',
  'composition_authoring_run_start', 'composition_authoring_run_resume',
  'composition_authoring_run_pause', 'composition_authoring_run_close',
  'composition_authoring_run_accept_unit', 'composition_authoring_run_reject_unit',
  'composition_authoring_run_revert_all',
];

// The 7 keys Mission Control actually reads. Each was verified in source; a PARTIAL invalidation is a
// partially-stale panel, which is the bug with extra steps.
//   ['authoring-runs']              composition/authoringRuns/hooks.ts:21
//   ['authoring-run']               hooks.ts:38
//   ['authoring-run-report']        hooks.ts:48
//   ['authoring-unit-diff']         studio/panels/agentMode/DiffReviewPanel.tsx:55
//   ['plan-runs-for-authoring']     studio/panels/agentMode/useNewRunForm.ts:20
//   ['plan-run-for-authoring-gate'] studio/panels/agentMode/useMissionControl.ts:46
//   ['book-toc-for-authoring']      studio/panels/agentMode/useMissionControl.ts:31
const KEYS = [
  ['authoring-runs'], ['authoring-run'], ['authoring-run-report'], ['authoring-unit-diff'],
  ['plan-runs-for-authoring'], ['plan-run-for-authoring-gate'], ['book-toc-for-authoring'],
];

describe('authoringRunEffect (Lane B handler)', () => {
  it('invalidates every Mission Control query key', () => {
    const c = ctx();
    authoringRunEffect(c);
    const keys = (c.queryClient.invalidateQueries as ReturnType<typeof vi.fn>)
      .mock.calls.map((call) => call[0].queryKey);
    for (const k of KEYS) expect(keys).toContainEqual(k);
  });

  // ⚠ accept_unit/reject_unit return {success, unit_index, status} (server.py:1924, :1981) — NO run_id,
  // NO book_id. A handler that tried to read run_id from the result would extract null and silently
  // no-op (the fe-status-default-fallback class). It must invalidate BY PREFIX, unconditionally.
  it('invalidates even when the result carries NO ids (accept_unit/reject_unit shape)', () => {
    const c = ctx({ tool: 'composition_authoring_run_accept_unit', result: { success: true, unit_index: 2, status: 'accepted' } });
    authoringRunEffect(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledTimes(KEYS.length);
  });

  it('does not hijack the editor (never publishes on the bus)', () => {
    const c = ctx();
    authoringRunEffect(c);
    expect(c.host.publish).not.toHaveBeenCalled();
  });
});

describe('registerAuthoringRunEffectHandlers wiring', () => {
  it.each(TOOLS)('routes the REAL tool %s through the registry', (tool) => {
    registerAuthoringRunEffectHandlers();
    expect(matchEffectHandlers(tool)).toContain(authoringRunEffect);
  });

  it('runs the handler end-to-end through runEffectHandlers', async () => {
    registerAuthoringRunEffectHandlers();
    const c = ctx({ tool: 'composition_authoring_run_pause' });
    await runEffectHandlers(c);
    expect(c.queryClient.invalidateQueries).toHaveBeenCalledTimes(KEYS.length);
  });

  it('does not double-register on a second call (idempotent)', () => {
    registerAuthoringRunEffectHandlers();
    registerAuthoringRunEffectHandlers();
    expect(matchEffectHandlers('composition_authoring_run_pause')).toEqual([authoringRunEffect]);
  });

  // The registration must be DISJOINT from every existing pattern — matchEffectHandlers returns EVERY
  // match and runEffectHandlers awaits ALL of them, so an overlap DOUBLE-FIRES (it does not shadow).
  it('does not match a non-authoring-run composition tool (no over-broad pattern)', () => {
    registerAuthoringRunEffectHandlers();
    expect(matchEffectHandlers('composition_outline_node_update')).toHaveLength(0);
    expect(matchEffectHandlers('composition_publish')).toHaveLength(0);
  });
});
