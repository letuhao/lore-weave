import { ReactNode } from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { renderHook, waitFor, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...args: unknown[]) => apiJson(...args) }));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

import { useKindsAdmin } from './useKindsAdmin';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => apiJson.mockReset());
afterEach(() => vi.clearAllMocks());

describe('useKindsAdmin', () => {
  it('lists system kinds from the bare-array endpoint', async () => {
    apiJson.mockResolvedValueOnce([
      { kind_id: 'k1', code: 'character', name: 'Character', description: null, icon: null, color: null, is_hidden: false, sort_order: 1 },
    ]);
    const { result } = renderHook(() => useKindsAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/kinds', { token: 'tok' });
    expect(result.current.list.data?.[0].name).toBe('Character');
  });

  it('create POSTs to /v1/glossary/system-kinds with the body', async () => {
    apiJson.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useKindsAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce({
      kind_id: 'k9', code: 'faction', name: 'Faction', description: null, icon: null, color: null, is_hidden: true, sort_order: 5,
    });
    // onSuccess invalidates the list → a refetch fires; keep it from hitting undefined.
    apiJson.mockResolvedValue([]);
    await act(async () => {
      await result.current.create.mutateAsync({ name: 'Faction', is_hidden: true });
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-kinds', {
      method: 'POST',
      token: 'tok',
      body: JSON.stringify({ name: 'Faction', is_hidden: true }),
    });
  });

  it('delete DELETEs to /v1/glossary/system-kinds/{id}', async () => {
    apiJson.mockResolvedValueOnce([]);
    const { result } = renderHook(() => useKindsAdmin(), { wrapper });
    await waitFor(() => expect(result.current.list.isSuccess).toBe(true));

    apiJson.mockResolvedValueOnce(undefined);
    apiJson.mockResolvedValue([]); // post-delete invalidate refetch
    await act(async () => {
      await result.current.remove.mutateAsync('k1');
    });
    expect(apiJson).toHaveBeenCalledWith('/v1/glossary/system-kinds/k1', {
      method: 'DELETE',
      token: 'tok',
    });
  });
});
