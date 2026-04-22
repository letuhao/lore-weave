import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const updateEntityMock = vi.fn();
const mergeEntityIntoMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateEntity: (...args: unknown[]) => updateEntityMock(...args),
      mergeEntityInto: (...args: unknown[]) => mergeEntityIntoMock(...args),
    },
  };
});

import { useUpdateEntity, useMergeEntity } from '../useEntityMutations';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const removeSpy = vi.spyOn(qc, 'removeQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy, removeSpy };
}

const ENTITY = {
  id: 'ent-1',
  user_id: 'u1',
  project_id: null,
  name: 'Kai',
  canonical_name: 'kai',
  kind: 'character',
  aliases: ['Kai'],
  canonical_version: 1,
  source_types: ['chat_turn'],
  confidence: 0.9,
  archived_at: null,
  archive_reason: null,
  evidence_count: 0,
  mention_count: 0,
  created_at: null,
  updated_at: null,
};

describe('useUpdateEntity', () => {
  beforeEach(() => {
    updateEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('calls onSuccess + invalidates list and detail', async () => {
    updateEntityMock.mockResolvedValue(ENTITY);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateEntity({ onSuccess }), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.update({
        entityId: 'ent-1',
        payload: { name: 'Kai' },
      });
    });
    expect(updateEntityMock).toHaveBeenCalledWith('ent-1', { name: 'Kai' }, 'tok');
    expect(onSuccess).toHaveBeenCalledWith(ENTITY);
    const invalidated = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidated).toContainEqual(['knowledge-entities', 'u1']);
    expect(invalidated).toContainEqual([
      'knowledge-entity-detail',
      'u1',
      'ent-1',
    ]);
  });

  it('surfaces errors via onError', async () => {
    updateEntityMock.mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.update({ entityId: 'ent-1', payload: { name: 'X' } }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

describe('useMergeEntity', () => {
  beforeEach(() => {
    mergeEntityIntoMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('parses 409 glossary_conflict into structured errorCode', async () => {
    mergeEntityIntoMock.mockRejectedValue(
      Object.assign(new Error('conflict'), {
        status: 409,
        body: {
          detail: {
            error_code: 'glossary_conflict',
            message: 'distinct anchors',
          },
        },
      }),
    );
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.merge({ sourceId: 'a', targetId: 'b' }),
    ).rejects.toMatchObject({
      errorCode: 'glossary_conflict',
      detailMessage: 'distinct anchors',
    });
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('invalidates list + target detail and evicts source detail on success', async () => {
    mergeEntityIntoMock.mockResolvedValue({
      target: { ...ENTITY, id: 'target-id', name: 'Phoenix' },
    });
    const { Wrapper, invalidateSpy, removeSpy } = makeWrapper();
    const { result } = renderHook(() => useMergeEntity(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.merge({
        sourceId: 'source-id',
        targetId: 'target-id',
      });
    });
    const invalidated = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidated).toContainEqual(['knowledge-entities', 'u1']);
    expect(invalidated).toContainEqual([
      'knowledge-entity-detail',
      'u1',
      'target-id',
    ]);
    const removed = removeSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(removed).toContainEqual([
      'knowledge-entity-detail',
      'u1',
      'source-id',
    ]);
  });

  it('falls back to unknown errorCode when body lacks detail', async () => {
    mergeEntityIntoMock.mockRejectedValue(new Error('network'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMergeEntity(), { wrapper: Wrapper });
    await expect(
      result.current.merge({ sourceId: 'a', targetId: 'b' }),
    ).rejects.toMatchObject({ errorCode: 'unknown' });
  });
});
