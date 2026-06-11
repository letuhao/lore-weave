import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useWorldMap } from '../useWorldMap';
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
    getEntityDetail: vi.fn(),
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
