// MOTIF-I18N — the affordance guard.
//
// The translation layer is only worth anything if a CALLER asks for it. This repo's most
// repeated bug shape is "capability wired at one layer, dead at the next, with green tests
// in between": the backend resolves display languages perfectly, every unit test passes,
// and a Vietnamese reader still sees English because nothing ever sends the parameter.
// These tests assert the wire, not the mechanism.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMotifLibrary } from '../hooks/useMotifLibrary';
import { motifApi } from '../api';

const language = { current: 'vi' };
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ i18n: { get language() { return language.current; } } }),
}));

vi.mock('../api', () => ({
  motifApi: { list: vi.fn(), catalog: vi.fn(), book: vi.fn() },
}));

function wrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity, gcTime: Infinity } },
  });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  language.current = 'vi';
  vi.clearAllMocks();
  (motifApi.list as ReturnType<typeof vi.fn>).mockResolvedValue({ motifs: [] });
  (motifApi.catalog as ReturnType<typeof vi.fn>).mockResolvedValue({ items: [] });
});

describe('useMotifLibrary — display language reaches the wire', () => {
  it('sends the UI language on the library list', async () => {
    renderHook(() => useMotifLibrary('t', { initialScope: 'my' }), { wrapper: wrapper() });
    await waitFor(() => expect(motifApi.list).toHaveBeenCalled());
    expect((motifApi.list as ReturnType<typeof vi.fn>).mock.calls[0][0]).toMatchObject({
      display_language: 'vi',
    });
  });

  it('sends it on the public catalog too', async () => {
    renderHook(() => useMotifLibrary('t', { initialScope: 'catalog' }), { wrapper: wrapper() });
    await waitFor(() => expect(motifApi.catalog).toHaveBeenCalled());
    expect((motifApi.catalog as ReturnType<typeof vi.fn>).mock.calls[0][0]).toMatchObject({
      display_language: 'vi',
    });
  });

  it('re-fetches when the UI language changes instead of serving cached rows', async () => {
    // The language is part of the query key. Without that, switching to Vietnamese would
    // re-render the ENGLISH rows already in the react-query cache under the same key —
    // a stale-cache bug that looks exactly like "the translation did not work".
    const { rerender } = renderHook(
      () => useMotifLibrary('t', { initialScope: 'my' }), { wrapper: wrapper() },
    );
    await waitFor(() => expect(motifApi.list).toHaveBeenCalledTimes(1));

    language.current = 'ja';
    rerender();

    await waitFor(() => expect(motifApi.list).toHaveBeenCalledTimes(2));
    expect((motifApi.list as ReturnType<typeof vi.fn>).mock.calls[1][0]).toMatchObject({
      display_language: 'ja',
    });
  });
});
