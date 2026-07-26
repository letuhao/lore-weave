import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok', user: { user_id: 'u1' } }),
}));

const updateEntityMock = vi.fn();
const createEntityMock = vi.fn();
const createRelationMock = vi.fn();
const archiveMyEntityMock = vi.fn();
vi.mock('../../../knowledge/api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../../knowledge/api');
  return {
    ...actual,
    knowledgeApi: {
      updateEntity: (...a: unknown[]) => updateEntityMock(...a),
      createEntity: (...a: unknown[]) => createEntityMock(...a),
      createRelation: (...a: unknown[]) => createRelationMock(...a),
      archiveMyEntity: (...a: unknown[]) => archiveMyEntityMock(...a),
    },
  };
});

import { useCastEdit } from '../useCastEdit';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

describe('useCastEdit', () => {
  beforeEach(() => {
    updateEntityMock.mockReset();
    createEntityMock.mockReset();
    createRelationMock.mockReset();
    archiveMyEntityMock.mockReset();
  });

  it('rename sends If-Match version and invalidates composition + knowledge caches', async () => {
    updateEntityMock.mockResolvedValue({ id: 'e1', name: 'New' });
    const onRenamed = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCastEdit({ onRenamed }), { wrapper: Wrapper });
    await act(async () => {
      await result.current.rename({ entityId: 'e1', name: 'New', version: 4 });
    });
    expect(updateEntityMock).toHaveBeenCalledWith('e1', { name: 'New' }, 4, 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['composition', 'cast']);
    expect(keys).toContainEqual(['composition', 'arc']);
    expect(keys).toContainEqual(['knowledge-entities']);
    expect(onRenamed).toHaveBeenCalled();
  });

  it('rename 412 fires onRenameConflict (reseed, no clobber) not onError', async () => {
    updateEntityMock.mockRejectedValue(
      Object.assign(new Error('stale'), { status: 412 }),
    );
    const onRenameConflict = vi.fn();
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useCastEdit({ onRenameConflict, onError }),
      { wrapper: Wrapper },
    );
    await act(async () => {
      await result.current
        .rename({ entityId: 'e1', name: 'X', version: 1 })
        .catch(() => {});
    });
    expect(onRenameConflict).toHaveBeenCalledTimes(1);
    expect(onError).not.toHaveBeenCalled();
  });

  it('archive treats 404 as success (idempotent hide)', async () => {
    archiveMyEntityMock.mockRejectedValue(
      Object.assign(new Error('nf'), { status: 404 }),
    );
    const onArchived = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCastEdit({ onArchived }), { wrapper: Wrapper });
    await act(async () => {
      await result.current.archive({ entityId: 'e1' });
    });
    expect(onArchived).toHaveBeenCalledTimes(1);
  });
});
