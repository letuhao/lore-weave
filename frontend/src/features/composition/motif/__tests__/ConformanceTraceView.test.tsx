// Regression (D-MOTIF-CONFORMANCE-CONTRACT) — the chapter conformance reader
// (GET …/conformance) returns {scope, chapter_id, calibrated, scenes} and does NOT
// emit `conform_count`. The panel is ALWAYS mounted (CSS-hidden) by CompositionPanel,
// so an unguarded `conf.conform_count[0]` white-screened the entire studio. Assert
// the view tolerates the real BE shape and only renders the count when present.
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ConformanceTraceView } from '../components/ConformanceTraceView';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('ConformanceTraceView — missing conform_count must not crash', () => {
  it('renders the real BE shape (no conform_count) without throwing; count span omitted', async () => {
    apiJson.mockResolvedValue({ scope: 'chapter', chapter_id: 'c1', calibrated: false, scenes: [] });
    render(<ConformanceTraceView projectId="p1" chapterId="c1" token="tok" />, { wrapper: wrap() });
    // the panel mounts (no white-screen) and resolves to the empty state.
    expect(await screen.findByTestId('conformance-trace-view')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('conformance-empty')).toBeInTheDocument());
    // no "N/M" count is shown when the field is absent.
    expect(screen.queryByText(/^\d+\/\d+$/)).toBeNull();
  });

  it('derives the [conforming/judged] count from the nested scene verdicts', async () => {
    const sc = (id: string, beat: boolean | null, band: boolean | null) => ({
      outline_node_id: id, title: id, beat_role: 'rising',
      planned: { motif_id: 'm1', motif_version: 1, beat_key: 'b', tension: 40, role_bindings: {} },
      realized: { job_id: 'j', has_prose: true },
      conformance: beat === null ? null : { beat_realized: beat, tension_band_match: band, calibrated: true },
    });
    // 3 judged scenes, 2 conforming; +1 unjudged (null verdict) is excluded from the denominator.
    apiJson.mockResolvedValue({
      scope: 'chapter', chapter_id: 'c1', calibrated: true,
      scenes: [sc('a', true, true), sc('b', true, true), sc('c', false, true), sc('d', null, null)],
    });
    render(<ConformanceTraceView projectId="p1" chapterId="c1" token="tok" />, { wrapper: wrap() });
    expect(await screen.findByTestId('conformance-count')).toHaveTextContent('2/3');
  });
});
