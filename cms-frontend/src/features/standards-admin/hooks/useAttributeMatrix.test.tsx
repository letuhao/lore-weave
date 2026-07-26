import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...args: unknown[]) => apiJson(...args) }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { useAttributeMatrix } from './useAttributeMatrix';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => apiJson.mockReset());
afterEach(() => vi.clearAllMocks());

describe('useAttributeMatrix', () => {
  it('fans out one system-attributes read per active genre and merges the result', async () => {
    // genres read (system tier)
    apiJson.mockImplementation((rawPath: unknown) => {
      const path = String(rawPath ?? '');
      if (path.startsWith('/v1/glossary/genres')) {
        return Promise.resolve({
          items: [
            { genre_id: 'g1', code: 'fantasy', name: 'Fantasy', icon: null, color: null, sort_order: 1, tier: 'system' },
            { genre_id: 'g2', code: 'scifi', name: 'Sci-Fi', icon: null, color: null, sort_order: 2, tier: 'system' },
          ],
        });
      }
      if (path.includes('genre_id=g1')) {
        return Promise.resolve({
          items: [
            { attr_id: 'a1', kind_id: 'k1', genre_id: 'g1', code: 'rank', name: 'Rank', description: null, field_type: 'text', is_required: false, sort_order: 1, options: null },
          ],
        });
      }
      if (path.includes('genre_id=g2')) {
        return Promise.resolve({
          items: [
            { attr_id: 'a2', kind_id: 'k1', genre_id: 'g2', code: 'rank', name: 'Rank', description: null, field_type: 'text', is_required: false, sort_order: 1, options: null },
          ],
        });
      }
      return Promise.resolve({ items: [] });
    });

    const { result } = renderHook(() => useAttributeMatrix('k1'), { wrapper });
    await waitFor(() => expect(result.current.attributes).toHaveLength(2));

    // Exactly two system-attributes calls — one per active genre.
    const attrCalls = apiJson.mock.calls.filter(([p]) =>
      String(p).includes('system-attributes'),
    );
    expect(attrCalls).toHaveLength(2);
    expect(attrCalls.some(([p]) => String(p).includes('kind_id=k1&genre_id=g1'))).toBe(true);
    expect(attrCalls.some(([p]) => String(p).includes('kind_id=k1&genre_id=g2'))).toBe(true);

    expect(result.current.activeGenres).toHaveLength(2);
    // 'rank' appears in both genres → a keep-both conflict (caller flags span=2).
    const ranks = result.current.attributes.filter((a) => a.code === 'rank');
    expect(ranks).toHaveLength(2);
    expect(new Set(ranks.map((a) => a.genre_id))).toEqual(new Set(['g1', 'g2']));
  });

  it('does NOT fetch attributes until a kind is chosen', async () => {
    apiJson.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useAttributeMatrix(''), { wrapper });
    await waitFor(() => expect(result.current.genres.isSuccess).toBe(true));
    expect(
      apiJson.mock.calls.some(([p]) => String(p).includes('system-attributes')),
    ).toBe(false);
  });
});
