// 22-C2 review — the controller had ZERO tests (the panel test fully mocks it). These pin the
// review-fixed behaviors: identity survives an intent-side failure; workless ≠ unavailable; the
// empty-flash `ready` gate; and spec_only suppression while the index is still paging.
import { renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Scene } from '@/features/books/api';
import type { OutlineNode, WorkResolution } from '@/features/composition/types';

const listScenes = vi.fn();
const getOutline = vi.fn();
let workData: WorkResolution;
let workLoading = false;

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('@/features/composition/hooks/useWork', () => ({
  useWorkResolution: () => ({ data: workData, isLoading: workLoading }),
}));
vi.mock('@/features/books/api', () => ({ booksApi: { listScenes: (...a: unknown[]) => listScenes(...a) } }));
vi.mock('@/features/composition/api', () => ({ compositionApi: { getOutline: (...a: unknown[]) => getOutline(...a) } }));

import { useSceneBrowser } from '../useSceneBrowser';

const scene = (o: Partial<Scene>): Scene => ({
  scene_id: 's', book_id: 'b', chapter_id: 'c', sort_order: 0, title: null, path: '/0', leaf_text: '',
  content_hash: 'h', source_scene_id: null, parse_version: 1, lifecycle_state: 'active', ...o,
});
const node = (o: Partial<OutlineNode>): OutlineNode => ({
  id: 'n', project_id: 'p', parent_id: null, kind: 'scene', rank: 'a', title: '', chapter_id: 'c',
  story_order: 0, status: 'outline', synopsis: '', version: 1, is_archived: false, beat_role: null, ...o,
});
const found = (pid: string): WorkResolution => ({
  status: 'found', work: { project_id: pid } as WorkResolution['work'], candidates: [],
  book_project_id: pid, book_project_ids: [pid],
});

beforeEach(() => {
  listScenes.mockReset(); getOutline.mockReset(); workLoading = false;
});

describe('useSceneBrowser — review fixes', () => {
  it('keeps the book-service identity rows when the intent (getOutline) call fails', async () => {
    workData = found('proj-1');
    listScenes.mockResolvedValue({ items: [scene({ scene_id: 's1', source_scene_id: null })], next_cursor: null, total: 1 });
    getOutline.mockRejectedValue(new Error('composition down'));

    const { result } = renderHook(() => useSceneBrowser('book-1'));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.error).toBeNull();          // NOT a blocking error
    expect(result.current.intentUnavailable).toBe(true);
    expect(result.current.rows).toHaveLength(1);       // identity row survived
    expect(result.current.rows[0].shape).toBe('index_only');
  });

  it('a blocking identity failure sets error and no rows', async () => {
    workData = found('proj-1');
    listScenes.mockRejectedValue(new Error('book-service 502'));
    getOutline.mockResolvedValue({ nodes: [], scene_links: [] });

    const { result } = renderHook(() => useSceneBrowser('book-1'));
    await waitFor(() => expect(result.current.ready).toBe(true));
    expect(result.current.error).toMatch(/502/);
    expect(result.current.rows).toHaveLength(0);
  });

  it('distinguishes a Work-less book (workless) from a transient outage (unavailable)', async () => {
    listScenes.mockResolvedValue({ items: [], next_cursor: null, total: 0 });
    getOutline.mockResolvedValue({ nodes: [], scene_links: [] });

    workData = { status: 'none', work: null, candidates: [], book_project_id: null, book_project_ids: [] };
    const none = renderHook(() => useSceneBrowser('book-1'));
    await waitFor(() => expect(none.result.current.ready).toBe(true));
    expect(none.result.current.workless).toBe(true);

    workData = { status: 'unavailable', work: null, candidates: [], book_project_id: null, book_project_ids: [] };
    const unavail = renderHook(() => useSceneBrowser('book-2'));
    await waitFor(() => expect(unavail.result.current.ready).toBe(true));
    expect(unavail.result.current.workless).toBe(false); // NOT shown the create-plan CTA
  });

  it('MID-PAGE, the server decides spec_only — no waiting for the whole index (SC11)', async () => {
    // This used to assert the `specComplete` SUPPRESSION: while more index pages remained, an
    // unclaimed spec was hidden, because "unclaimed" might only mean "its page hasn't loaded".
    //
    // The server now answers that outright (`written_scene_id`, maintained from
    // scenes.source_scene_id), so mid-page is not a special case at all:
    //   n2 — prose EXISTS, its index row is on page 2  -> NOT spec_only (correct, and it was before)
    //   n3 — no prose at all                           -> spec_only IMMEDIATELY (which the old gate
    //                                                     could not say until the whole index loaded)
    workData = found('proj-1');
    listScenes.mockResolvedValueOnce({
      items: [scene({ scene_id: 's1', source_scene_id: 'n1' })], next_cursor: 'c2', total: 3,
    });
    getOutline.mockResolvedValue({
      nodes: [
        node({ id: 'n1', written_scene_id: 's1' }),
        node({ id: 'n2', story_order: 1, written_scene_id: 's2' }),   // written; page 2
        node({ id: 'n3', story_order: 2, written_scene_id: null }),   // genuinely unwritten
      ],
      scene_links: [],
    });

    const { result } = renderHook(() => useSceneBrowser('book-1'));
    await waitFor(() => expect(result.current.ready).toBe(true));

    expect(result.current.hasMore).toBe(true);      // still paging…
    const specOnly = result.current.rows.filter((r) => r.shape === 'spec_only');
    expect(specOnly.map((r) => r.key)).toEqual(['n3']);   // …and the verdict is already correct
    expect(result.current.rows.filter((r) => r.shape === 'linked')).toHaveLength(1);
  });

  it('does not flash empty while work resolution is loading (ready=false)', async () => {
    workLoading = true;
    workData = undefined as unknown as WorkResolution;
    const { result } = renderHook(() => useSceneBrowser('book-1'));
    expect(result.current.ready).toBe(false);
    expect(listScenes).not.toHaveBeenCalled(); // no fetch until resolution settles
  });
});
