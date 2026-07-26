// 24 PH26 — the entity-names map's COMPLETENESS is the load-bearing field, not the names.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';

const glossary = vi.hoisted(() => ({ listEntityNamesWithMeta: vi.fn() }));
vi.mock('@/features/glossary/api', () => ({ glossaryApi: glossary }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { useEntityNames } from '../useEntityNames';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => vi.clearAllMocks());

describe('useEntityNames (PH26)', () => {
  it('resolves a known id to its display name', async () => {
    glossary.listEntityNamesWithMeta.mockResolvedValue({
      items: [{ entity_id: 'e1', display_name: 'Hà' }],
      complete: true,
    });
    const { result } = renderHook(() => useEntityNames('book-1'), { wrapper });
    await waitFor(() => expect(result.current.complete).toBe(true));
    expect(result.current.resolve('e1')).toEqual({ state: 'resolved', name: 'Hà' });
  });

  it('COMPLETE map + absent id ⇒ missing', async () => {
    glossary.listEntityNamesWithMeta.mockResolvedValue({ items: [], complete: true });
    const { result } = renderHook(() => useEntityNames('book-1'), { wrapper });
    await waitFor(() => expect(result.current.complete).toBe(true));
    expect(result.current.resolve('ghost')).toEqual({ state: 'missing' });
  });

  it('INCOMPLETE map + absent id ⇒ unknown', async () => {
    glossary.listEntityNamesWithMeta.mockResolvedValue({ items: [], complete: false });
    const { result } = renderHook(() => useEntityNames('book-1'), { wrapper });
    await waitFor(() => expect(glossary.listEntityNamesWithMeta).toHaveBeenCalled());
    expect(result.current.resolve('ghost')).toEqual({ state: 'unknown' });
  });

  it('a FAILED read is not a complete map — it must not accuse every entity of being missing', async () => {
    // Defaulting `complete` to true on error would turn every cast id on the canvas into a red
    // "missing entity" warning the moment glossary hiccups. Absence must prove nothing here.
    glossary.listEntityNamesWithMeta.mockRejectedValue(new Error('glossary down'));
    const { result } = renderHook(() => useEntityNames('book-1'), { wrapper });
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.complete).toBe(false);
    expect(result.current.resolve('anything')).toEqual({ state: 'unknown' });
  });
});
