// D-W10-ARC-CONFORMANCE-FE — the arc-conformance dashboard: coarse (thread coverage,
// pacing, structural succession, unmaterialized) from the scope=arc GET, plus the DEEP
// prose overlay via the Tier-W JOB (propose→confirm→poll over the FE→MCP-tool bridge).
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

const mcpExecute = vi.fn();
vi.mock('@/mcpBridge', () => ({ mcpExecute: (...a: unknown[]) => mcpExecute(...a) }));

// The deep tagging-model picker lives in features/campaigns and pulls in auth + the
// BYOK model list; stub it to a simple chooser so this test stays about the JOB flow.
vi.mock('@/features/campaigns/components/ModelRolePicker', () => ({
  ModelRolePicker: ({ value, onChange }: { value: string | null; onChange: (v: string | null) => void }) => (
    <button type="button" data-testid="mock-model-pick" onClick={() => onChange('m1')}>
      {value ?? 'pick a model'}
    </button>
  ),
}));

import { ArcConformancePanel } from '../components/ArcConformancePanel';
import type { ArcConformance, ArcDeep } from '../types';

const REPORT = (over: Partial<ArcConformance> = {}): ArcConformance => ({
  scope: 'arc', available: true, coarse: true, causal_verified: false,
  arc_template_id: 'a1', arc_name: 'Revenge Arc', chapter_count: 2,
  thread_progress: [
    { thread: 'revenge', label: 'Revenge', planned: 3, covered: 2, missing: [{ motif_code: 'exile', ord: 1 }] },
  ],
  pacing: { comparable: true, planned: [30, 90], realized: [
    { chapter_index: 1, avg_tension: 40, scenes: 2 }, { chapter_index: 2, avg_tension: 70, scenes: 1 },
  ], max_drift: 20 },
  succession: { causal_verified: false, threads: [
    { thread: 'revenge', label: 'Revenge', transitions: 1, legal: 1, unrelated: 0, violations: [] },
  ] },
  unmaterialized: [{ motif_code: 'exile', thread: 'revenge', ord: 1 }],
  ...over,
});

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

// Route apiJson by URL: the coarse conformance GET, the confirm POST (→ job_id), and the
// job poll (→ completed + result). `deep` is the report the completed job returns.
function mockFlow(deep: ArcDeep) {
  apiJson.mockImplementation((url: string, init?: { method?: string }) => {
    const u = String(url);
    if (u.includes('/actions/confirm')) {
      expect(init?.method).toBe('POST');
      expect(u).toContain('token=ct'); // token rides the QUERY, not the body
      return Promise.resolve({ outcome: 'action_accepted', job_id: 'j1', poll: 'composition_get_mine_job' });
    }
    if (u.includes('/jobs/j1')) {
      return Promise.resolve({ id: 'j1', status: 'completed', result: REPORT({ deep }) });
    }
    // the coarse scope=arc GET
    return Promise.resolve(REPORT());
  });
  mcpExecute.mockResolvedValue({ confirm_token: 'ct', estimate: { estimated_usd: 0.5 } });
}

// Drive the panel: pick a model → run → confirm the cost → (poll resolves) deep renders.
async function runDeep() {
  fireEvent.click(await screen.findByTestId('mock-model-pick'));
  fireEvent.click(await screen.findByTestId('arc-conf-run-deep-btn'));
  fireEvent.click(await screen.findByTestId('motif-cost-confirm-btn'));
}

beforeEach(() => {
  apiJson.mockReset();
  mcpExecute.mockReset();
  apiJson.mockImplementation(() => Promise.resolve(REPORT()));
});

describe('ArcConformancePanel', () => {
  it('renders the coarse badge + thread coverage + pacing + unmaterialized', async () => {
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    const thread = await screen.findByTestId('arc-conf-thread-revenge');
    expect(screen.getByTestId('arc-conf-coarse-badge')).toBeInTheDocument();
    expect(thread).toHaveTextContent('2/3');
    expect(screen.getByTestId('arc-conf-missing-revenge')).toHaveTextContent('exile');
    expect(screen.getByTestId('arc-conf-drift')).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-pacing')).toHaveTextContent('40');
    expect(screen.getByTestId('arc-conf-succession-ok')).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-unmaterialized')).toHaveTextContent('exile');
  });

  it('hits the scope=arc endpoint with the arc id', async () => {
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    const call = apiJson.mock.calls.find((c) => String(c[0]).includes('/conformance'));
    expect(String(call?.[0])).toContain('/works/p1/conformance');
    expect(String(call?.[0])).toContain('scope=arc');
    expect(String(call?.[0])).toContain('arc_id=a1');           // M-BUG-4: wire arg is arc_id, not arc_template_id
    expect(String(call?.[0])).not.toContain('arc_template_id');   // the old (dropped-by-FastAPI → 422) arg is gone
  });

  it('surfaces a succession violation when the realized order is reversed', async () => {
    apiJson.mockImplementation(() => Promise.resolve(REPORT({
      succession: { causal_verified: false, threads: [
        { thread: 'revenge', label: 'Revenge', transitions: 1, legal: 0, unrelated: 0,
          violations: [{ from_motif_id: 'm-slap', to_motif_id: 'm-humil' }] },
      ] },
    })));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    expect(await screen.findByTestId('arc-conf-violation-revenge')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-conf-succession-ok')).toBeNull();
  });

  it('shows the empty state when nothing is materialized', async () => {
    apiJson.mockImplementation(() => Promise.resolve(REPORT({ chapter_count: 0 })));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    expect(await screen.findByTestId('arc-conf-empty')).toBeInTheDocument();
  });

  it('without a projectId, prompts to materialize first (no fetch)', () => {
    render(<ArcConformancePanel projectId={null} arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    expect(screen.getByTestId('arc-conf-no-work')).toBeInTheDocument();
    expect(apiJson).not.toHaveBeenCalled();
    expect(mcpExecute).not.toHaveBeenCalled();
  });

  // ── DEEP overlay via the Tier-W JOB (propose → confirm → poll) ────────────────

  it('runs the deep JOB: propose mints a token, confirm spends, the poll renders prose drift', async () => {
    mockFlow({
      available: true, source: 'motif_beat_extractor',
      pacing: { comparable: true, planned: [{ chapter_index: 1, avg_tension: 50 }],
        realized: [{ chapter_index: 1, avg_tension: 100, events: 2 }], max_drift: 50, scale_note: 's' },
      thread_progression: { available: false, reason: 'untagged', threads: [], unplanned: [] },
      succession: { available: false, causal_verified: false, reason: 'untagged', transitions: 0, legal: 0, unrelated: 0, violations: [] },
    });
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    await runDeep();
    const deepSection = await screen.findByTestId('arc-conf-deep');
    expect(screen.getByTestId('arc-conf-deep-drift')).toBeInTheDocument();
    expect(deepSection).toHaveTextContent('100'); // realized prose tension rendered raw
    // PROPOSE went through the bridge with scope=arc + the chosen model.
    const [tool, callArgs] = mcpExecute.mock.calls[0];
    expect(tool).toBe('composition_conformance_run');
    // FastMCP nests the tool's single pydantic `args` param.
    expect(callArgs).toMatchObject({ args: { project_id: 'p1', scope: 'arc', arc_id: 'a1', model_ref: 'm1' } });  // M-BUG-4
  });

  it('deep overlay degrades honestly when no prose is extracted yet', async () => {
    mockFlow({
      available: false, source: 'motif_beat_extractor',
      pacing: { comparable: false, planned: [], realized: [], max_drift: null, scale_note: 's' },
      thread_progression: { available: false, reason: 'x', threads: [], unplanned: [] },
      succession: { available: false, causal_verified: false, reason: 'x', transitions: 0, legal: 0, unrelated: 0, violations: [] },
    });
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    await runDeep();
    expect(await screen.findByTestId('arc-conf-deep-empty')).toBeInTheDocument();
  });

  it('deep thread-progression: realized vs missing threads + unplanned (THREAD-TAG)', async () => {
    mockFlow({
      available: true, source: 'motif_beat_extractor',
      pacing: { comparable: false, planned: [], realized: [{ chapter_index: 1, avg_tension: 60, events: 1 }], max_drift: null, scale_note: 's' },
      thread_progression: { available: true, threads: [
        { thread: 'combat', label: 'Combat', realized: true, realized_chapters: 2 },
        { thread: 'romance', label: 'Romance', realized: false, realized_chapters: 0 },
      ], unplanned: ['intrigue'] },
      succession: { available: false, causal_verified: false, reason: 'x', transitions: 0, legal: 0, unrelated: 0, violations: [] },
    });
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    await runDeep();
    const threads = await screen.findByTestId('arc-conf-deep-threads');
    expect(threads).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-deep-thread-combat')).toHaveTextContent('2');
    expect(screen.getByTestId('arc-conf-deep-thread-romance')).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-deep-unplanned')).toHaveTextContent('intrigue');
  });

  it('deep succession: realized order vs the precedes graph + a violation (F1)', async () => {
    mockFlow({
      available: true, source: 'motif_beat_extractor',
      pacing: { comparable: false, planned: [], realized: [{ chapter_index: 1, avg_tension: 60, events: 1 }], max_drift: null, scale_note: 's' },
      thread_progression: { available: false, reason: 'x', threads: [], unplanned: [] },
      succession: { available: true, causal_verified: false, transitions: 2, legal: 1, unrelated: 0,
        violations: [{ from_motif_code: 'face_slap', to_motif_code: 'humiliation' }] },
    });
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    await runDeep();
    const succ = await screen.findByTestId('arc-conf-deep-succession');
    expect(succ).toHaveTextContent('1');
    expect(screen.getByTestId('arc-conf-deep-succ-violations')).toHaveTextContent('face_slap');
  });

  it('deep succession: causal + entailment counts (F2 + entailment judge)', async () => {
    mockFlow({
      available: true, source: 'motif_beat_extractor',
      pacing: { comparable: false, planned: [], realized: [{ chapter_index: 1, avg_tension: 60, events: 1 }], max_drift: null, scale_note: 's' },
      thread_progression: { available: false, reason: 'x', threads: [], unplanned: [] },
      succession: { available: true, causal_verified: true, transitions: 3, legal: 3, unrelated: 0, caused: 2, entailment_verified: true, entailed: 1, violations: [] },
    });
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    await runDeep();
    await screen.findByTestId('arc-conf-deep-succession');
    expect(screen.getByTestId('arc-conf-deep-succ-caused')).toHaveTextContent('2');
    expect(screen.getByTestId('arc-conf-deep-succ-entailed')).toHaveTextContent('1');
  });

  it('surfaces a propose error (e.g. EDIT-grant denial) without spending', async () => {
    mcpExecute.mockRejectedValue(Object.assign(new Error('EDIT grant required'), { status: 400 }));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    fireEvent.click(await screen.findByTestId('mock-model-pick'));
    fireEvent.click(await screen.findByTestId('arc-conf-run-deep-btn'));
    expect(await screen.findByTestId('arc-conf-deep-error')).toHaveTextContent('EDIT grant required');
    // no confirm card, no spend
    expect(screen.queryByTestId('motif-cost-confirm-btn')).toBeNull();
  });
});
