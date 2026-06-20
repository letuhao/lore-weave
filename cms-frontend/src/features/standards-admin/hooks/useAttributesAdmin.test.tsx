import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...args: unknown[]) => apiJson(...args) }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { useAttributesAdmin } from './useAttributesAdmin';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

// kinds, genres, then (when selected) attributes are fetched in turn.
function mockReads() {
  apiJson
    .mockResolvedValueOnce([
      { kind_id: 'k1', code: 'character', name: 'Character', description: null, icon: null, color: null, is_hidden: false, sort_order: 1 },
    ]) // kinds
    .mockResolvedValueOnce({
      items: [
        { genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: null, color: null, sort_order: 1, tier: 'system' },
      ],
    }) // genres
    .mockResolvedValueOnce({
      items: [
        { attr_id: 'a1', kind_id: 'k1', genre_id: 'g1', code: 'rank', name: 'Rank', description: null, field_type: 'text', is_required: false, sort_order: 1, options: null },
      ],
    }); // attributes
}

beforeEach(() => apiJson.mockReset());
afterEach(() => vi.clearAllMocks());

describe('useAttributesAdmin', () => {
  it('lists attributes for the selected kind × genre with both ids in the query', async () => {
    mockReads();
    const { result } = renderHook(() => useAttributesAdmin('k1', 'g1'), { wrapper });
    await waitFor(() => expect(result.current.attributes.isSuccess).toBe(true));
    expect(apiJson).toHaveBeenCalledWith(
      '/v1/glossary/system-attributes?kind_id=k1&genre_id=g1',
      { token: 'tok' },
    );
    expect(result.current.attributes.data?.[0].name).toBe('Rank');
  });

  it('does NOT fetch attributes until both kind and genre are chosen', async () => {
    apiJson
      .mockResolvedValueOnce([]) // kinds
      .mockResolvedValueOnce({ items: [] }); // genres
    const { result } = renderHook(() => useAttributesAdmin('', ''), { wrapper });
    await waitFor(() => expect(result.current.kinds.isSuccess).toBe(true));
    expect(result.current.selected).toBe(false);
    expect(
      apiJson.mock.calls.some(([p]) => String(p).includes('system-attributes')),
    ).toBe(false);
  });

  it('create POSTs to system-attributes-admin with kind_id + genre_id + body', async () => {
    mockReads();
    const { result } = renderHook(() => useAttributesAdmin('k1', 'g1'), { wrapper });
    await waitFor(() => expect(result.current.attributes.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce({
      attr_id: 'a9', kind_id: 'k1', genre_id: 'g1', code: 'role', name: 'Role', description: null, field_type: 'select', is_required: true, sort_order: 2, options: ['hero', 'villain'],
    });
    await act(async () => {
      await result.current.create.mutateAsync({
        kind_id: 'k1',
        genre_id: 'g1',
        name: 'Role',
        field_type: 'select',
        is_required: true,
        options: ['hero', 'villain'],
      });
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-attributes-admin', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({
        kind_id: 'k1',
        genre_id: 'g1',
        name: 'Role',
        field_type: 'select',
        is_required: true,
        options: ['hero', 'villain'],
      }),
    });
  });

  it('delete DELETEs to system-attributes-admin/{id}', async () => {
    mockReads();
    const { result } = renderHook(() => useAttributesAdmin('k1', 'g1'), { wrapper });
    await waitFor(() => expect(result.current.attributes.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce(undefined);
    await act(async () => {
      await result.current.remove.mutateAsync('a1');
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-attributes-admin/a1', {
      method: 'DELETE',
      token: 'tok',
    });
  });
});
