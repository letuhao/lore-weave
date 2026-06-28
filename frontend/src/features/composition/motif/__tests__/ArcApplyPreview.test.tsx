// W10 §12.5 — the apply-preview: target chapters + roster bind → POST …/apply → render
// the deterministic plan (rescaled placements, unbound roles, the §12.6 drop/merge
// report). The call is pure (nothing persisted); the surface is preview-only.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcApplyPreview } from '../components/ArcApplyPreview';
import type { ArcTemplate } from '../arcTypes';

const ARC: ArcTemplate = {
  id: 'A1', owner_user_id: 'u1', code: 'rev', language: 'en', visibility: 'private',
  name: 'Revenge', summary: '', genre_tags: [], chapter_span: 5,
  threads: [], layout: [], pacing: [],
  arc_roster: [{ key: 'protagonist', label: 'Hero' }],
  source: 'authored', imported_derived: false, source_version: null, status: 'active', version: 1,
};

const PLAN = {
  arc_template_id: 'A1', source_chapter_span: 5, target_chapters: 20,
  threads: [],
  placements: [
    { motif_code: 'duel', motif_id: null, thread: 'combat', ord: 0, src_span_start: 1, src_span_end: 1, span_start: 1, span_end: 4, role_hints: {}, role_bindings: {}, triggers: [], merged_codes: ['skirmish'] },
  ],
  roster_bindings: { protagonist: 'Lin' },
  unbound_roster_keys: ['mentor'],
  drop_merge_report: [
    { kind: 'merged', motif_code: 'skirmish', thread: 'combat', src_span_start: 2, src_span_end: 2, into_motif_code: 'duel', reason: 'collapsed onto chapters 1..4' },
  ],
  chapter_interleave: { '1': [0] },
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('ArcApplyPreview', () => {
  it('POSTs the chosen target + roster bindings and renders the plan', async () => {
    apiJson.mockResolvedValueOnce(PLAN);
    render(<ArcApplyPreview arc={ARC} token="tok" />, { wrapper: wrap() });

    fireEvent.change(screen.getByTestId('arc-apply-target'), { target: { value: '20' } });
    fireEvent.change(screen.getByTestId('arc-apply-roster-protagonist'), { target: { value: 'Lin' } });
    fireEvent.click(screen.getByTestId('arc-apply-run'));

    await waitFor(() => expect(screen.getByTestId('arc-apply-plan')).toBeInTheDocument());
    const call = apiJson.mock.calls[0];
    expect(call[0]).toBe('/v1/composition/arc-templates/A1/apply');
    const body = JSON.parse((call[1] as { body: string }).body);
    expect(body).toEqual({ target_chapters: 20, roster_bindings: { protagonist: 'Lin' } });

    // the plan surfaces placements, the merge badge, the unbound role, and the drop/merge report.
    expect(screen.getByTestId('arc-apply-placement')).toBeInTheDocument();
    expect(screen.getByTestId('arc-apply-merged')).toHaveTextContent('+1');
    expect(screen.getByTestId('arc-apply-unbound')).toBeInTheDocument();
    expect(screen.getByTestId('arc-apply-dropmerge')).toBeInTheDocument();
  });

  it('an empty roster binding is omitted from the request', async () => {
    apiJson.mockResolvedValueOnce(PLAN);
    render(<ArcApplyPreview arc={ARC} token="tok" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-apply-run'));
    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    const body = JSON.parse((apiJson.mock.calls[0][1] as { body: string }).body);
    expect(body.roster_bindings).toEqual({});   // blank input not sent
  });
});
