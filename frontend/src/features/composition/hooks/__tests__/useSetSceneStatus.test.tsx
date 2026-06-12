import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const patchNodeMock = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: { patchNode: (...a: unknown[]) => patchNodeMock(...a) },
}));

import { useSetSceneStatus } from '../useWork';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => patchNodeMock.mockReset());

describe('useSetSceneStatus (M9 — fixes the dead-gate)', () => {
  it("patches the node status and invalidates BOTH outline AND publish-gate", async () => {
    patchNodeMock.mockResolvedValue({ id: 'n1', status: 'done' });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useSetSceneStatus('p1', 'tok'), { wrapper: Wrapper });

    await act(async () => {
      await result.current.mutateAsync({ nodeId: 'n1', status: 'done' });
    });

    expect(patchNodeMock).toHaveBeenCalledWith('n1', { status: 'done' }, 'tok');
    await waitFor(() => {
      const keys = invalidateSpy.mock.calls.map((c) => JSON.stringify((c[0] as { queryKey: unknown[] }).queryKey));
      // MED#2: without the publish-gate invalidation the Publish affordance stays
      // stale after a scene is committed.
      expect(keys).toContain(JSON.stringify(['composition', 'outline', 'p1']));
      expect(keys).toContain(JSON.stringify(['composition', 'publish-gate', 'p1']));
    });
  });
});
