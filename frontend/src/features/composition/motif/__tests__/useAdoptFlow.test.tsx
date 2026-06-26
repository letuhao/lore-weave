// W6 §7.1 — useAdoptFlow: target picker (User | book); quota_exceeded → the
// explainer (not a silent fail); mint → estimate.
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { useAdoptFlow } from '../hooks/useAdoptFlow';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => apiJson.mockReset());

describe('useAdoptFlow', () => {
  it('begin opens the flow with a default User target', () => {
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    expect(result.current.isOpen).toBe(true);
    expect(result.current.target).toEqual({ kind: 'user' });
  });

  it('mint resolves a cost estimate', async () => {
    apiJson.mockResolvedValueOnce({ confirm_token: 'tok', descriptor: 'composition.motif_mine', est_usd: 0.01, est_tokens: 100, quota_remaining: 5 });
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    await act(async () => { await result.current.mint.mutateAsync(); });
    expect(result.current.estimate?.confirm_token).toBe('tok');
  });

  it('quota_exceeded on mint → the explainer is surfaced (not a silent fail)', async () => {
    apiJson.mockRejectedValueOnce(Object.assign(new Error('quota'), { code: 'quota_exceeded', body: { code: 'quota_exceeded', resource: 'adopt', limit: 50, used: 50 } }));
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    await act(async () => { await result.current.mint.mutateAsync().catch(() => {}); });
    await waitFor(() => expect(result.current.quota).not.toBeNull());
    expect(result.current.quota).toMatchObject({ resource: 'adopt', limit: 50, used: 50 });
  });
});
