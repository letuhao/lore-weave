// S-10 O6b — "Suggest an arc for this premise": type a premise → POST /arc-templates/suggest →
// ranked candidate rows (name, score, why-it-matched). No project ⇒ a guidance hint, not a dead form.
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { ArcSuggestView } from '../components/ArcSuggestView';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => apiJson.mockReset());

describe('ArcSuggestView (O6b)', () => {
  it('ranks templates for the typed premise and renders the candidates', async () => {
    apiJson.mockResolvedValue({
      candidates: [
        { arc_template: { id: 'T1', code: 'fall', name: 'Fall of a house', chapter_span: 12, genre_tags: ['tragedy'], mine: true }, score: 0.91, match_reason: 'premise mentions a fallen house' },
        { arc_template: { id: 'T2', code: 'heir', name: 'Reluctant heir', chapter_span: null, genre_tags: [], mine: false }, score: 0.7, match_reason: null },
      ],
      detail: 'summary',
      count: 2,
    });
    render(<ArcSuggestView projectId="proj-1" token="t" />, { wrapper: wrap() });

    fireEvent.change(screen.getByTestId('arc-suggest-premise'), { target: { value: 'a reluctant heir reclaims a fallen house' } });
    fireEvent.click(screen.getByTestId('arc-suggest-run'));

    await waitFor(() => expect(apiJson).toHaveBeenCalled());
    const [url, opts] = apiJson.mock.calls[0];
    expect(url).toBe('/v1/composition/arc-templates/suggest');
    const body = JSON.parse(opts.body);
    expect(body.project_id).toBe('proj-1');
    expect(body.premise).toContain('reluctant heir');
    expect(body.detail).toBe('summary');

    await waitFor(() => expect(screen.getByTestId('arc-suggest-results')).toBeInTheDocument());
    expect(screen.getByTestId('arc-suggest-row-T1')).toHaveTextContent('Fall of a house');
    expect(screen.getByTestId('arc-suggest-row-T1')).toHaveTextContent('91%');
    expect(screen.getByTestId('arc-suggest-row-T2')).toHaveTextContent('Reluctant heir');
  });

  it('shows an empty note when nothing fits (not a blank pane)', async () => {
    apiJson.mockResolvedValue({ candidates: [], detail: 'summary', count: 0 });
    render(<ArcSuggestView projectId="proj-1" token="t" />, { wrapper: wrap() });
    fireEvent.click(screen.getByTestId('arc-suggest-run'));
    await waitFor(() => expect(screen.getByTestId('arc-suggest-empty')).toBeInTheDocument());
  });

  it('guides the user when there is no Work project (no dead form)', () => {
    render(<ArcSuggestView projectId={null} token="t" />, { wrapper: wrap() });
    expect(screen.getByTestId('arc-suggest-noproject')).toBeInTheDocument();
    expect(screen.queryByTestId('arc-suggest-run')).toBeNull();
  });
});
