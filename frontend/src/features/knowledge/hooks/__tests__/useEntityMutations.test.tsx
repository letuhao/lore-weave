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
const unlockEntityMock = vi.fn();
const promoteEntityMock = vi.fn();
const setGlossaryEntityPinnedMock = vi.fn();
const createEntityMock = vi.fn();
const createRelationMock = vi.fn();
const archiveMyEntityMock = vi.fn();
const restoreMyEntityMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      updateEntity: (...args: unknown[]) => updateEntityMock(...args),
      mergeEntityInto: (...args: unknown[]) => mergeEntityIntoMock(...args),
      unlockEntity: (...args: unknown[]) => unlockEntityMock(...args),
      promoteEntity: (...args: unknown[]) => promoteEntityMock(...args),
      setGlossaryEntityPinned: (...args: unknown[]) =>
        setGlossaryEntityPinnedMock(...args),
      createEntity: (...args: unknown[]) => createEntityMock(...args),
      createRelation: (...args: unknown[]) => createRelationMock(...args),
      archiveMyEntity: (...args: unknown[]) => archiveMyEntityMock(...args),
      restoreMyEntity: (...args: unknown[]) => restoreMyEntityMock(...args),
    },
  };
});

import {
  useMergeEntity,
  useUnlockEntity,
  useUpdateEntity,
  usePromoteEntity,
  useToggleGlossaryPin,
  useCreateEntity,
  useCreateRelation,
  useArchiveEntity,
  useRestoreEntity,
} from '../useEntityMutations';

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

  it('calls onSuccess + invalidates list and detail + forwards If-Match version', async () => {
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
        ifMatchVersion: 3,
      });
    });
    // C9: ifMatchVersion threaded as 3rd positional arg before token.
    expect(updateEntityMock).toHaveBeenCalledWith(
      'ent-1', { name: 'Kai' }, 3, 'tok',
    );
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
      result.current.update({
        entityId: 'ent-1',
        payload: { name: 'X' },
        ifMatchVersion: 1,
      }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('C9: on 412 conflict, invalidates detail cache so baseline refreshes', async () => {
    updateEntityMock.mockRejectedValue(
      Object.assign(new Error('version mismatch'), { status: 412 }),
    );
    const onError = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUpdateEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.update({
        entityId: 'ent-1',
        payload: { name: 'X' },
        ifMatchVersion: 1,
      }),
    ).rejects.toThrow();
    // onError fires with the 412 error (consumer toast owns it).
    expect(onError).toHaveBeenCalledTimes(1);
    // Detail cache invalidated so next open sees fresh baseline.
    const invalidated = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidated).toContainEqual([
      'knowledge-entity-detail',
      'u1',
      'ent-1',
    ]);
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


// ── C9 — useUnlockEntity ─────────────────────────────────────────────

describe('useUnlockEntity', () => {
  beforeEach(() => {
    unlockEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('calls the API and invalidates list + detail on success', async () => {
    unlockEntityMock.mockResolvedValue(ENTITY);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useUnlockEntity({ onSuccess }), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.unlock({ entityId: 'ent-1' });
    });
    expect(unlockEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    expect(onSuccess).toHaveBeenCalledWith(ENTITY);
    const invalidated = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidated).toContainEqual(['knowledge-entities', 'u1']);
    expect(invalidated).toContainEqual([
      'knowledge-entity-detail', 'u1', 'ent-1',
    ]);
  });

  it('surfaces errors via onError', async () => {
    unlockEntityMock.mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUnlockEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.unlock({ entityId: 'ent-1' }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

// ── C9 (C9-promote-flow) ──────────────────────────────────────────────

describe('usePromoteEntity', () => {
  beforeEach(() => {
    promoteEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('calls promoteEntity + invalidates list and detail on success', async () => {
    const anchored = { ...ENTITY, glossary_entity_id: 'g-9', anchor_score: 1 };
    promoteEntityMock.mockResolvedValue(anchored);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => usePromoteEntity({ onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.promote({ entityId: 'ent-1' });
    });

    await waitFor(() => {
      expect(promoteEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['knowledge-entities', 'u1'],
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['knowledge-entity-detail', 'u1', 'ent-1'],
    });
    expect(onSuccess).toHaveBeenCalledTimes(1);
  });

  it('forwards the error to onError', async () => {
    promoteEntityMock.mockRejectedValue(new Error('glossary_draft_failed'));
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePromoteEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.promote({ entityId: 'ent-1' }),
    ).rejects.toThrow('glossary_draft_failed');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

describe('useToggleGlossaryPin', () => {
  beforeEach(() => {
    setGlossaryEntityPinnedMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('toggles is_pinned_for_context (pinned=false) on the glossary entity', async () => {
    setGlossaryEntityPinnedMock.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useToggleGlossaryPin({ onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.toggle({
        entityId: 'ent-1',
        bookId: 'b-1',
        glossaryEntityId: 'g-1',
        pinned: false,
      });
    });

    // setGlossaryEntityPinned(bookId, glossaryEntityId, pinned, token)
    expect(setGlossaryEntityPinnedMock).toHaveBeenCalledWith(
      'b-1',
      'g-1',
      false,
      'tok',
    );
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ['knowledge-entity-detail', 'u1', 'ent-1'],
    });
    expect(onSuccess).toHaveBeenCalledWith(false);
  });
});

// ── S7-1 — create entity / relation, archive ──────────────────────────

describe('useCreateEntity', () => {
  beforeEach(() => {
    createEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('posts the payload + invalidates list, subgraph, and composition cast', async () => {
    createEntityMock.mockResolvedValue({ ...ENTITY, id: 'ent-new' });
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCreateEntity({ onSuccess }), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.create({
        project_id: 'p1',
        name: 'Kai',
        kind: 'character',
      });
    });
    expect(createEntityMock).toHaveBeenCalledWith(
      { project_id: 'p1', name: 'Kai', kind: 'character' },
      'tok',
    );
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['knowledge-entities', 'u1']);
    expect(keys).toContainEqual(['knowledge-subgraph', 'u1']);
    expect(keys).toContainEqual(['composition', 'cast']);
    expect(onSuccess).toHaveBeenCalled();
  });

  it('surfaces errors via onError', async () => {
    createEntityMock.mockRejectedValue(new Error('boom'));
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCreateEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.create({ project_id: 'p1', name: 'X', kind: 'item' }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

describe('useCreateRelation', () => {
  beforeEach(() => {
    createRelationMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('invalidates subgraph, both endpoints detail, and composition arc', async () => {
    createRelationMock.mockResolvedValue({ id: 'rel-1' });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCreateRelation(), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.createRelation({
        subject_id: 's1',
        object_id: 'o1',
        predicate: 'ally_of',
      });
    });
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['knowledge-subgraph', 'u1']);
    expect(keys).toContainEqual(['knowledge-entity-detail', 'u1', 's1']);
    expect(keys).toContainEqual(['knowledge-entity-detail', 'u1', 'o1']);
    expect(keys).toContainEqual(['composition', 'arc']);
  });

  it('surfaces a 409 (endpoint not yours) via onError', async () => {
    createRelationMock.mockRejectedValue(
      Object.assign(new Error('conflict'), { status: 409 }),
    );
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCreateRelation({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.createRelation({
        subject_id: 's1',
        object_id: 'x',
        predicate: 'owns',
      }),
    ).rejects.toMatchObject({ status: 409 });
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

describe('useArchiveEntity', () => {
  beforeEach(() => {
    archiveMyEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('archives + invalidates list, detail, subgraph, composition cast', async () => {
    archiveMyEntityMock.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useArchiveEntity({ onSuccess }), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.archive({ entityId: 'ent-1' });
    });
    expect(archiveMyEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['knowledge-entities', 'u1']);
    expect(keys).toContainEqual(['knowledge-entity-detail', 'u1', 'ent-1']);
    expect(keys).toContainEqual(['composition', 'cast']);
    expect(onSuccess).toHaveBeenCalled();
  });

  it('treats a 404 as success (idempotent: already gone == hidden)', async () => {
    archiveMyEntityMock.mockRejectedValue(
      Object.assign(new Error('not found'), { status: 404 }),
    );
    const onSuccess = vi.fn();
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useArchiveEntity({ onSuccess, onError }),
      { wrapper: Wrapper },
    );
    await act(async () => {
      await result.current.archive({ entityId: 'ent-1' });
    });
    expect(onSuccess).toHaveBeenCalled();
    expect(onError).not.toHaveBeenCalled();
  });

  it('surfaces a non-404 error via onError', async () => {
    archiveMyEntityMock.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useArchiveEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.archive({ entityId: 'ent-1' }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});

// D-KG-ENTITY-RESTORE (S7) — the Undo leg of the archive toast. The round-trip
// (archive → Undo → restore) is the operable inverse; without coverage the
// restore hook is a wired-but-unproven path.
describe('useRestoreEntity', () => {
  beforeEach(() => {
    restoreMyEntityMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('restores + invalidates list, detail, subgraph, composition cast', async () => {
    restoreMyEntityMock.mockResolvedValue(undefined);
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRestoreEntity({ onSuccess }), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.restore({ entityId: 'ent-1' });
    });
    expect(restoreMyEntityMock).toHaveBeenCalledWith('ent-1', 'tok');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['knowledge-entities', 'u1']);
    expect(keys).toContainEqual(['knowledge-entity-detail', 'u1', 'ent-1']);
    expect(keys).toContainEqual(['knowledge-subgraph', 'u1']);
    expect(keys).toContainEqual(['composition', 'cast']);
    expect(onSuccess).toHaveBeenCalled();
  });

  it('surfaces a restore failure via onError', async () => {
    restoreMyEntityMock.mockRejectedValue(
      Object.assign(new Error('boom'), { status: 500 }),
    );
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRestoreEntity({ onError }), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.restore({ entityId: 'ent-1' }),
    ).rejects.toThrow('boom');
    expect(onError).toHaveBeenCalledTimes(1);
  });
});
