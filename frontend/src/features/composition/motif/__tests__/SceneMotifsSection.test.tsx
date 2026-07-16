// 3b §3.2a/§3.3 — the scene Motifs section: the ranked Suggest button (BE-M4) with a
// match_reason, replacing the flat unranked list (GG-1), plus the no-Work empty state.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { SceneMotifsSection } from '../components/SceneMotifsSection';
import { motifApi } from '../api';
import { compositionApi } from '../../api';

vi.mock('../api', () => ({ motifApi: { suggestForChapter: vi.fn(), list: vi.fn() } }));
vi.mock('../../api', () => ({ compositionApi: { getMotifBindings: vi.fn() } }));
vi.mock('@/api', () => ({ apiJson: vi.fn().mockResolvedValue({}) }));

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  vi.clearAllMocks();
  (compositionApi.getMotifBindings as ReturnType<typeof vi.fn>).mockResolvedValue({ bindings: {}, succession: {} });
  (motifApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: [] });
});

describe('SceneMotifsSection', () => {
  it('renders the no-Work state when there is no plan (projectId null)', () => {
    wrap(<SceneMotifsSection projectId={null} bookId="b" chapterId="c" sceneId="s" token="t" />);
    expect(screen.getByTestId('motif-no-work')).toBeInTheDocument();
    expect(motifApi.suggestForChapter).not.toHaveBeenCalled();
  });

  it('Suggest button fetches ranked candidates with score + match_reason (BE-M4)', async () => {
    (motifApi.suggestForChapter as ReturnType<typeof vi.fn>).mockResolvedValue({ candidates: [
      { motif: { id: 'm1', name: 'Face-slap', code: 'rev.slap' }, score: 0.82, match_reason: { tension: 1, genre: 1, degraded: false } },
    ] });
    wrap(<SceneMotifsSection projectId="p" bookId="b" chapterId="c" sceneId="s" token="t" />);
    fireEvent.click(await screen.findByTestId('motif-suggest-toggle'));
    const row = await screen.findByTestId('motif-suggest-row');
    expect(row.textContent).toMatch(/Face-slap/);
    expect(row.textContent).toMatch(/82%/);           // score surfaced
    expect(row.textContent).toMatch(/tension/);        // match_reason surfaced, degraded filtered out
    expect(motifApi.suggestForChapter).toHaveBeenCalledWith('p', 's', 't');
  });

  it('surfaces the suggest empty state (no motif fits)', async () => {
    (motifApi.suggestForChapter as ReturnType<typeof vi.fn>).mockResolvedValue({ candidates: [] });
    wrap(<SceneMotifsSection projectId="p" bookId="b" chapterId="c" sceneId="s" token="t" />);
    fireEvent.click(await screen.findByTestId('motif-suggest-toggle'));
    await waitFor(() => expect(screen.getByTestId('motif-suggest-empty')).toBeInTheDocument());
  });

  it('surfaces a suggest error (no silent fail)', async () => {
    (motifApi.suggestForChapter as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('boom'));
    wrap(<SceneMotifsSection projectId="p" bookId="b" chapterId="c" sceneId="s" token="t" />);
    fireEvent.click(await screen.findByTestId('motif-suggest-toggle'));
    await waitFor(() => expect(screen.getByTestId('motif-suggest-error')).toBeInTheDocument());
  });

  it('does not fetch suggestions until the button is clicked (lazy)', async () => {
    wrap(<SceneMotifsSection projectId="p" bookId="b" chapterId="c" sceneId="s" token="t" />);
    await screen.findByTestId('motif-suggest-toggle');
    expect(motifApi.suggestForChapter).not.toHaveBeenCalled();
  });
});
