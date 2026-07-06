import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

// useWorkResolution decides hasWork (Work → group by arc; none → hasWork:false). Same mocking
// shape as useManuscriptTree.test.tsx.
const work = vi.hoisted(() => ({ value: { data: { status: 'none' } as Record<string, unknown>, isLoading: false } }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => work.value }));

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 't' }) }));

const listOutlineChildren = vi.fn();
vi.mock('@/features/composition/api', () => ({
  compositionApi: { listOutlineChildren: (...a: unknown[]) => listOutlineChildren(...a) },
}));

import { useChapterBrowserGroups } from '../useChapterBrowserGroups';

beforeEach(() => {
  listOutlineChildren.mockReset();
  work.value = { data: { status: 'none' }, isLoading: false };
});

describe('useChapterBrowserGroups', () => {
  it('no Work → hasWork false, empty groups, arcIdForChapter always undefined', async () => {
    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasWork).toBe(false);
    expect(result.current.groups).toEqual([]);
    expect(result.current.arcIdForChapter('anything')).toBeUndefined();
    expect(listOutlineChildren).not.toHaveBeenCalled();
  });

  it('has Work → builds groups + arcIdForChapter from arc-then-children fetch', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockImplementation((_projectId: string, _token: string, opts: { parentId: string | null }) => {
      if (opts.parentId === null) {
        return Promise.resolve({
          items: [
            { id: 'arc1', kind: 'arc', title: 'The Crimson Court', chapter_id: null },
            { id: 'arc2', kind: 'arc', title: 'The Long Winter', chapter_id: null },
          ],
          next_cursor: null,
        });
      }
      if (opts.parentId === 'arc1') {
        return Promise.resolve({
          items: [
            { id: 'ch1', kind: 'chapter', title: 'Ch1', chapter_id: 'bc1' },
            { id: 'ch2', kind: 'chapter', title: 'Ch2', chapter_id: 'bc2' },
            { id: 'sc1', kind: 'scene', title: 'Scene', chapter_id: null }, // non-chapter kind, must be skipped
          ],
          next_cursor: null,
        });
      }
      if (opts.parentId === 'arc2') {
        return Promise.resolve({ items: [{ id: 'ch3', kind: 'chapter', title: 'Ch3', chapter_id: 'bc3' }], next_cursor: null });
      }
      return Promise.resolve({ items: [], next_cursor: null });
    });

    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    expect(result.current.hasWork).toBe(true);
    expect(result.current.groups).toHaveLength(2);
    expect(result.current.groups[0]).toMatchObject({
      arcId: 'arc1', label: 'The Crimson Court', romanNumeral: 'I', chapterCount: 2,
    });
    expect(result.current.groups[0].chapterIds.has('bc1')).toBe(true);
    expect(result.current.groups[0].chapterIds.has('bc2')).toBe(true);
    expect(result.current.groups[1]).toMatchObject({ arcId: 'arc2', romanNumeral: 'II', chapterCount: 1 });

    expect(result.current.arcIdForChapter('bc1')).toBe('arc1');
    expect(result.current.arcIdForChapter('bc2')).toBe('arc1');
    expect(result.current.arcIdForChapter('bc3')).toBe('arc2');
    expect(result.current.arcIdForChapter('unknown')).toBeUndefined();
  });

  it('cursor-follows a multi-page arc list AND a multi-page chapter list within one arc', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockImplementation((_projectId: string, _token: string, opts: { parentId: string | null; cursor?: string | null }) => {
      if (opts.parentId === null) {
        if (!opts.cursor) {
          return Promise.resolve({ items: [{ id: 'arc1', kind: 'arc', title: 'Arc One', chapter_id: null }], next_cursor: 'arcs-p2' });
        }
        return Promise.resolve({ items: [{ id: 'arc2', kind: 'arc', title: 'Arc Two', chapter_id: null }], next_cursor: null });
      }
      if (opts.parentId === 'arc1') {
        if (!opts.cursor) {
          return Promise.resolve({ items: [{ id: 'ch1', kind: 'chapter', title: 'Ch1', chapter_id: 'bc1' }], next_cursor: 'ch-p2' });
        }
        return Promise.resolve({ items: [{ id: 'ch2', kind: 'chapter', title: 'Ch2', chapter_id: 'bc2' }], next_cursor: null });
      }
      return Promise.resolve({ items: [], next_cursor: null }); // arc2 has 0 chapters
    });

    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));

    // Both arc pages resolved (2 groups, not just the first page's 1).
    expect(result.current.groups.map((g) => g.arcId)).toEqual(['arc1', 'arc2']);
    // Both chapter pages resolved for arc1 (2 chapters, not just the first page's 1).
    expect(result.current.groups[0].chapterCount).toBe(2);
    expect(result.current.arcIdForChapter('bc1')).toBe('arc1');
    expect(result.current.arcIdForChapter('bc2')).toBe('arc1');
    expect(result.current.groups[1].chapterCount).toBe(0);
  });

  it('a fetch failure degrades to empty groups rather than throwing', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasWork).toBe(true);
    expect(result.current.groups).toEqual([]);
  });

  it('re-fetches when the resolved project changes (book switch)', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockImplementation((projectId: string, _token: string, opts: { parentId: string | null }) => {
      if (opts.parentId === null) {
        return Promise.resolve({
          items: [{ id: `arc-${projectId}`, kind: 'arc', title: `Arc of ${projectId}`, chapter_id: null }],
          next_cursor: null,
        });
      }
      return Promise.resolve({ items: [], next_cursor: null });
    });

    const { result, rerender } = renderHook(
      ({ bookId }: { bookId: string }) => useChapterBrowserGroups(bookId),
      { initialProps: { bookId: 'b1' } },
    );
    await waitFor(() => expect(result.current.groups.length).toBe(1));
    expect(result.current.groups[0].arcId).toBe('arc-p1');

    work.value = { data: { status: 'found', work: { project_id: 'p2' } }, isLoading: false };
    rerender({ bookId: 'b2' });
    await waitFor(() => expect(result.current.groups[0]?.arcId).toBe('arc-p2'));
  });
});
