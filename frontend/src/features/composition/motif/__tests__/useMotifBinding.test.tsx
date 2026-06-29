// W6 §7.1 — useMotifBinding: swap invalidates the decompose-preview query; clear →
// free-form (DELETE); commitAndGenerate returns the route contract; a failed swap
// keeps the prior binding (the mutation rejects, no local state mutated).
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { useMotifBinding } from '../hooks/useMotifBinding';

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const spy = vi.spyOn(qc, 'invalidateQueries');
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, spy, wrapper };
}

beforeEach(() => apiJson.mockReset());

describe('useMotifBinding', () => {
  it('swap → PATCH …/motif then invalidates the decompose-preview query', async () => {
    apiJson.mockResolvedValueOnce({ ok: true });
    const { spy, wrapper } = wrap();
    const { result } = renderHook(() => useMotifBinding({ projectId: 'p1', bookId: 'b1', nodeId: 'n1', token: 'tok' }), { wrapper });
    await act(async () => { await result.current.swap.mutateAsync('m2'); });
    expect(apiJson.mock.calls[0][0]).toContain('/works/p1/outline/n1/motif');
    expect(spy).toHaveBeenCalledWith({ queryKey: ['composition', 'decompose', 'p1'] });
  });

  it('clearMotif → DELETE (free-form fallback)', async () => {
    apiJson.mockResolvedValueOnce(undefined);
    const { wrapper } = wrap();
    const { result } = renderHook(() => useMotifBinding({ projectId: 'p1', bookId: 'b1', nodeId: 'n1', token: 'tok' }), { wrapper });
    await act(async () => { await result.current.clearMotif.mutateAsync(); });
    expect(apiJson.mock.calls[0][1]).toMatchObject({ method: 'DELETE' });
  });

  it('a failed swap rejects + leaves no invalidation (no destructive optimism)', async () => {
    apiJson.mockRejectedValueOnce(new Error('boom'));
    const { spy, wrapper } = wrap();
    const { result } = renderHook(() => useMotifBinding({ projectId: 'p1', bookId: 'b1', nodeId: 'n1', token: 'tok' }), { wrapper });
    await act(async () => { await result.current.swap.mutateAsync('m2').catch(() => {}); });
    await waitFor(() => expect(result.current.swap.isError).toBe(true));
    expect(spy).not.toHaveBeenCalled();   // onSuccess (invalidate) never ran
  });

  it('commitAndGenerate returns the route contract (W2 wires it)', () => {
    const { wrapper } = wrap();
    const { result } = renderHook(() => useMotifBinding({ projectId: 'p1', bookId: 'b1', nodeId: 'n1', token: 'tok' }), { wrapper });
    expect(result.current.commitAndGenerate('s9')).toEqual({ tab: 'compose', sceneId: 's9' });
  });
});
