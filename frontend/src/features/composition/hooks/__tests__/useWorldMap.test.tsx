import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi, type Mock } from 'vitest';
import { useWorldMap } from '../useWorldMap';
import { knowledgeApi } from '../../../knowledge/api';
import type { Work } from '../../types';

// /review-impl regression-lock for the two-writer clobber fix: positions and
// backdrop both replace the single `work.settings.world_map` blob, so each must
// preserve the other's sub-key. Mock the leaf deps; assert the merged PATCH.
const { setSettingsMutate, uploadMedia } = vi.hoisted(() => ({
  setSettingsMutate: vi.fn(),
  uploadMedia: vi.fn(),
}));
vi.mock('../useCast', async (orig) => ({
  ...(await orig<typeof import('../useCast')>()),
  useKnowledgeProjectId: () => ({ data: 'kp1', isLoading: false }),
}));
vi.mock('../useWork', () => ({ useSetWorkSettings: () => ({ mutate: setSettingsMutate }) }));
vi.mock('../../../knowledge/api', () => ({
  knowledgeApi: {
    listEntities: vi.fn().mockResolvedValue({ entities: [], total: 0 }),
    getEntityDetail: vi.fn().mockResolvedValue({ entity: null, relations: [], relations_truncated: false, total_relations: 0 }),
    archiveMyEntity: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock('../../../books/api', () => ({ booksApi: { uploadChapterMedia: uploadMedia } }));

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return ({ children }: { children: React.ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const work = {
  project_id: 'wp1', book_id: 'b',
  settings: { world_map: { positions: { old: { x: 0, y: 0 } }, backdrop_url: 'orig.png' } },
} as unknown as Work;

describe('useWorldMap persist (T2.5 /review-impl clobber lock)', () => {
  beforeEach(() => { setSettingsMutate.mockReset(); uploadMedia.mockReset(); });

  it('persisting positions KEEPS the existing backdrop_url', () => {
    const { result } = renderHook(() => useWorldMap(work, 'b', 'ch', 't'), { wrapper: makeWrapper() });
    act(() => result.current.persistPositions({ p1: { x: 1, y: 1 } }));
    expect(setSettingsMutate).toHaveBeenLastCalledWith(
      expect.objectContaining({
        patch: { world_map: { positions: { p1: { x: 1, y: 1 } }, backdrop_url: 'orig.png' } },
      }),
    );
  });

  it('uploading a backdrop KEEPS the freshly-dragged positions (no clobber)', async () => {
    uploadMedia.mockResolvedValue({ url: 'http://cdn/new.png' });
    const { result } = renderHook(() => useWorldMap(work, 'b', 'ch', 't'), { wrapper: makeWrapper() });
    // drag first → wmRef now holds the new positions...
    act(() => result.current.persistPositions({ p1: { x: 1, y: 1 } }));
    // ...then upload a backdrop (reads the SAME ref, not the stale `work` prop).
    await act(async () => { await result.current.uploadBackdrop.mutateAsync(new File([], 'm.png')); });
    await waitFor(() => {
      expect(setSettingsMutate).toHaveBeenLastCalledWith(
        expect.objectContaining({
          patch: { world_map: { positions: { p1: { x: 1, y: 1 } }, backdrop_url: 'http://cdn/new.png' } },
        }),
      );
    });
  });
});

describe('useWorldMap deletePlace (place-graph delete)', () => {
  beforeEach(() => {
    (knowledgeApi.listEntities as Mock).mockReset();
    (knowledgeApi.archiveMyEntity as Mock).mockReset().mockResolvedValue(undefined);
  });

  it('archives the location entity, then the node drops out on the invalidated refetch', async () => {
    const p = { id: 'a', name: 'Doomed Hold', kind: 'location' };
    (knowledgeApi.listEntities as Mock)
      .mockResolvedValueOnce({ entities: [p], total: 1 }) // initial load: one place
      .mockResolvedValue({ entities: [], total: 0 });     // after archive+invalidate: gone

    const { result } = renderHook(() => useWorldMap(work, 'b', 'ch', 't'), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.nodes.map((n) => n.id)).toEqual(['a']));

    await act(async () => { await result.current.deletePlace.mutateAsync('a'); });

    expect(knowledgeApi.archiveMyEntity).toHaveBeenCalledWith('a', 't');
    await waitFor(() => expect(result.current.nodes).toHaveLength(0));
  });

  it('treats a 404 (already gone / cross-user) as idempotent success, not a throw', async () => {
    (knowledgeApi.listEntities as Mock).mockResolvedValue({ entities: [], total: 0 });
    (knowledgeApi.archiveMyEntity as Mock).mockRejectedValue(Object.assign(new Error('nope'), { status: 404 }));

    const { result } = renderHook(() => useWorldMap(work, 'b', 'ch', 't'), { wrapper: makeWrapper() });
    await expect(
      act(async () => { await result.current.deletePlace.mutateAsync('gone'); }),
    ).resolves.toBeUndefined();
  });
});
