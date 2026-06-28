// W6 §7.1 — useAdoptFlow: adopt = clone into YOUR library (user-scoped). PROPOSE via
// the FE→MCP-tool bridge → confirm. A quota ceiling (now enforced at confirm, the
// spend) → the §4.4 explainer (not a silent fail).
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

const mcpExecute = vi.fn();
vi.mock('@/mcpBridge', () => ({ mcpExecute: (...a: unknown[]) => mcpExecute(...a) }));

import { useAdoptFlow } from '../hooks/useAdoptFlow';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  apiJson.mockReset();
  mcpExecute.mockReset();
});

describe('useAdoptFlow', () => {
  it('begin opens the flow', () => {
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    expect(result.current.isOpen).toBe(true);
    expect(result.current.estimate).toBeNull();
  });

  it('mint PROPOSEs via the bridge → a confirm token (no $ — adopt is quota-gated)', async () => {
    mcpExecute.mockResolvedValueOnce({ confirm_token: 'ct', preview: { will_clone: true } });
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    await act(async () => { await result.current.mint.mutateAsync(); });
    expect(mcpExecute).toHaveBeenCalledWith('composition_motif_adopt', { args: { motif_id: 'm1' } }, 'tok');
    expect(result.current.estimate?.confirm_token).toBe('ct');
    expect(result.current.estimate?.est_usd).toBe(0);
  });

  it('quota_exhausted on CONFIRM → the explainer is surfaced (not a silent fail)', async () => {
    mcpExecute.mockResolvedValueOnce({ confirm_token: 'ct' });
    // confirm hits POST /actions/confirm → 402 with the composition action-effect shape
    apiJson.mockRejectedValueOnce(
      Object.assign(new Error('quota'), { status: 402, body: { code: 'action_error', reason: 'quota_exhausted' } }),
    );
    const { result } = renderHook(() => useAdoptFlow('tok'), { wrapper: wrap() });
    act(() => result.current.begin('m1'));
    await act(async () => { await result.current.mint.mutateAsync(); });
    await act(async () => { await result.current.confirm.mutateAsync().catch(() => {}); });
    await waitFor(() => expect(result.current.quota).not.toBeNull());
    expect(result.current.quota).toMatchObject({ resource: 'adopt' });
  });
});
