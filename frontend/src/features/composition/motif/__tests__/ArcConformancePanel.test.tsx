// D-W10-ARC-CONFORMANCE-FE — the coarse arc-conformance dashboard: renders thread
// coverage, the realized pacing curve, structural succession flags, and unmaterialized
// (folded-away) placements from the scope=arc report. Logic lives in useArcConformance.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcConformancePanel } from '../components/ArcConformancePanel';
import type { ArcConformance } from '../types';

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

beforeEach(() => {
  apiJson.mockReset();
  apiJson.mockImplementation(() => Promise.resolve(REPORT()));
});

describe('ArcConformancePanel', () => {
  it('renders the coarse badge + thread coverage + pacing + unmaterialized', async () => {
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    // thread coverage only appears once the query resolves (the wrapper renders eagerly).
    const thread = await screen.findByTestId('arc-conf-thread-revenge');
    // honest coarse stamp (causal_verified=false).
    expect(screen.getByTestId('arc-conf-coarse-badge')).toBeInTheDocument();
    // thread coverage 2/3 + the missing motif surfaced.
    expect(thread).toHaveTextContent('2/3');
    expect(screen.getByTestId('arc-conf-missing-revenge')).toHaveTextContent('exile');
    // pacing drift + a realized point.
    expect(screen.getByTestId('arc-conf-drift')).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-pacing')).toHaveTextContent('40');
    // no violations → the OK row.
    expect(screen.getByTestId('arc-conf-succession-ok')).toBeInTheDocument();
    // folded-away placement surfaced (§12.6 honesty).
    expect(screen.getByTestId('arc-conf-unmaterialized')).toHaveTextContent('exile');
  });

  it('hits the scope=arc endpoint with the arc id', async () => {
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    await screen.findByTestId('arc-conformance-panel');
    const call = apiJson.mock.calls.find((c) => String(c[0]).includes('/conformance'));
    expect(String(call?.[0])).toContain('/works/p1/conformance');
    expect(String(call?.[0])).toContain('scope=arc');
    expect(String(call?.[0])).toContain('arc_template_id=a1');
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
  });

  it('"Check prose drift" refetches with deep=true and shows the prose-pacing overlay', async () => {
    // coarse first; deep=true adds the realized-from-prose pacing overlay.
    apiJson.mockImplementation((url: string) => Promise.resolve(
      String(url).includes('deep=true')
        ? REPORT({ deep: {
            available: true, source: 'motif_beat_extractor',
            pacing: { comparable: true, planned: [{ chapter_index: 1, avg_tension: 50 }],
              realized: [{ chapter_index: 1, avg_tension: 100, events: 2 }], max_drift: 50,
              scale_note: 's' },
            thread_progression: { available: false, reason: 'P4+', threads: [], unplanned: [] },
            succession: { available: false, causal_verified: false, reason: 'P4+', transitions: 0, legal: 0, unrelated: 0, violations: [] },
          } })
        : REPORT(),
    ));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('arc-conf-deep-btn'));
    // the deep section + the drift readout appear once the deep fetch resolves.
    const deepSection = await screen.findByTestId('arc-conf-deep');
    expect(screen.getByTestId('arc-conf-deep-drift')).toBeInTheDocument();
    // the realized prose tension (100) is rendered raw (not via i18n) → a real data check.
    expect(deepSection).toHaveTextContent('100');
    await waitFor(() => {
      const deepCall = apiJson.mock.calls.find((c) => String(c[0]).includes('deep=true'));
      expect(deepCall?.[0]).toContain('scope=arc');
    });
  });

  it('deep overlay degrades honestly when no prose is extracted yet', async () => {
    apiJson.mockImplementation((url: string) => Promise.resolve(
      String(url).includes('deep=true')
        ? REPORT({ deep: {
            available: false, source: 'motif_beat_extractor',
            pacing: { comparable: false, planned: [], realized: [], max_drift: null, scale_note: 's' },
            thread_progression: { available: false, reason: 'P4+', threads: [], unplanned: [] },
            succession: { available: false, causal_verified: false, reason: 'P4+', transitions: 0, legal: 0, unrelated: 0, violations: [] },
          } })
        : REPORT(),
    ));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('arc-conf-deep-btn'));
    expect(await screen.findByTestId('arc-conf-deep-empty')).toBeInTheDocument();
  });

  it('deep thread-progression: realized vs missing threads + unplanned (THREAD-TAG)', async () => {
    apiJson.mockImplementation((url: string) => Promise.resolve(
      String(url).includes('deep=true')
        ? REPORT({ deep: {
            available: true, source: 'motif_beat_extractor',
            pacing: { comparable: false, planned: [], realized: [{ chapter_index: 1, avg_tension: 60, events: 1 }], max_drift: null, scale_note: 's' },
            thread_progression: { available: true, threads: [
              { thread: 'combat', label: 'Combat', realized: true, realized_chapters: 2 },
              { thread: 'romance', label: 'Romance', realized: false, realized_chapters: 0 },
            ], unplanned: ['intrigue'] },
            succession: { available: false, causal_verified: false, reason: 'P4+', transitions: 0, legal: 0, unrelated: 0, violations: [] },
          } })
        : REPORT(),
    ));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" modelRef="m1" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('arc-conf-deep-btn'));
    const threads = await screen.findByTestId('arc-conf-deep-threads');
    expect(threads).toBeInTheDocument();
    expect(screen.getByTestId('arc-conf-deep-thread-combat')).toHaveTextContent('2');     // realized in 2 ch
    expect(screen.getByTestId('arc-conf-deep-thread-romance')).toBeInTheDocument();         // planned, not in prose
    expect(screen.getByTestId('arc-conf-deep-unplanned')).toHaveTextContent('intrigue');
    // modelRef threaded → the deep fetch opts into tagging (model_ref on the URL).
    await waitFor(() => {
      const call = apiJson.mock.calls.find((c) => String(c[0]).includes('deep=true'));
      expect(String(call?.[0])).toContain('model_ref=m1');
    });
  });

  it('deep succession: realized motif order vs the precedes graph + a violation (F1)', async () => {
    apiJson.mockImplementation((url: string) => Promise.resolve(
      String(url).includes('deep=true')
        ? REPORT({ deep: {
            available: true, source: 'motif_beat_extractor',
            pacing: { comparable: false, planned: [], realized: [{ chapter_index: 1, avg_tension: 60, events: 1 }], max_drift: null, scale_note: 's' },
            thread_progression: { available: false, reason: 'x', threads: [], unplanned: [] },
            succession: { available: true, causal_verified: false, transitions: 2, legal: 1, unrelated: 0,
              violations: [{ from_motif_code: 'face_slap', to_motif_code: 'humiliation' }] },
          } })
        : REPORT(),
    ));
    render(<ArcConformancePanel projectId="p1" arcTemplateId="a1" token="tok" modelRef="m1" />, { wrapper: wrap() });
    fireEvent.click(await screen.findByTestId('arc-conf-deep-btn'));
    const succ = await screen.findByTestId('arc-conf-deep-succession');
    expect(succ).toHaveTextContent('1');                                   // 1/2 legal (raw count)
    expect(screen.getByTestId('arc-conf-deep-succ-violations')).toHaveTextContent('face_slap');
  });
});
