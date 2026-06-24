import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...args: unknown[]) => apiJson(...args) }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { useGenresAdmin } from './useGenresAdmin';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => apiJson.mockReset());
afterEach(() => vi.clearAllMocks());

describe('useGenresAdmin', () => {
  it('lists system genres (include_user=false, system tier only)', async () => {
    apiJson.mockResolvedValueOnce({
      items: [
        { genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: null, color: null, sort_order: 1, tier: 'system' },
        { genre_id: 'g2', code: 'mine', name: 'Mine', icon: null, color: null, sort_order: 2, tier: 'user' },
      ],
    });
    const { result } = renderHook(() => useGenresAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/genres?include_user=false', { token: 'tok' });
    expect(result.current.list.data).toHaveLength(1);
    expect(result.current.list.data?.[0].name).toBe('Fantasy');
  });

  it('create POSTs to /v1/glossary/system-genres with the body', async () => {
    apiJson.mockResolvedValueOnce({ items: [] });
    const { result } = renderHook(() => useGenresAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce({
      genre_id: 'g9', code: 'scifi', name: 'Sci-Fi', icon: null, color: null, sort_order: 3,
    });
    await act(async () => {
      await result.current.create.mutateAsync({ name: 'Sci-Fi' });
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-genres', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({ name: 'Sci-Fi' }),
    });
  });

  it('delete DELETEs to /v1/glossary/system-genres/{id}', async () => {
    apiJson.mockResolvedValueOnce({ items: [] });
    const { result } = renderHook(() => useGenresAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce(undefined);
    await act(async () => {
      await result.current.remove.mutateAsync('g1');
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-genres/g1', {
      method: 'DELETE',
      token: 'tok',
    });
  });

  it('surfaces an admin-session message on a 403 write', async () => {
    apiJson.mockResolvedValueOnce({ items: [] });
    const { result } = renderHook(() => useGenresAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    apiJson.mockRejectedValueOnce(Object.assign(new Error('Forbidden'), { status: 403 }));
    await act(async () => {
      await result.current.create.mutateAsync({ name: 'X' }).catch(() => {});
    });
    await waitFor(() => expect(result.current.status?.kind).toBe('err'));
    expect(result.current.status?.text).toMatch(/admin session required/i);
  });
});
