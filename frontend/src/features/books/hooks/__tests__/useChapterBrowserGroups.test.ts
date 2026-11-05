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

// #271 — the grouping binds chapters to arcs via outline_node.structure_node_id (23 BA2)
// and reads the arc shells from the structure route the Plan Hub already uses
// (GET /books/{id}/arcs), NOT from outline nodes: outline nodes are chapter/scene only
// (#263), so the old `kind === 'arc'` outline filter matched nothing, ever.
const getArcs = vi.fn();
vi.mock('@/features/plan-hub/api', () => ({ getArcs: (...a: unknown[]) => getArcs(...a) }));

import { useChapterBrowserGroups } from '../useChapterBrowserGroups';

beforeEach(() => {
  listOutlineChildren.mockReset();
  getArcs.mockReset();
  work.value = { data: { status: 'none' }, isLoading: false };
});

// Real-shaped root page: outline nodes are chapter/scene only; a chapter binds to its
// arc through structure_node_id. No `kind: 'arc'` outline node can exist (#263).
function chapter(id: string, chapterId: string, structureNodeId: string | null) {
  return { id, kind: 'chapter', title: id, chapter_id: chapterId, structure_node_id: structureNodeId };
}

describe('useChapterBrowserGroups', () => {
  it('no Work → hasWork false, empty groups, arcIdForChapter always undefined', async () => {
    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasWork).toBe(false);
    expect(result.current.groups).toEqual([]);
    expect(result.current.arcIdForChapter('anything')).toBeUndefined();
    expect(listOutlineChildren).not.toHaveBeenCalled();
    expect(getArcs).not.toHaveBeenCalled();
  });

  it('has Work → binds chapters to arcs via structure_node_id and orders groups by the arc shells', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    getArcs.mockResolvedValue({
      arcs: [
        { id: 'arc1', kind: 'arc', title: 'The Crimson Court' },
        { id: 'arc2', kind: 'arc', title: 'The Long Winter' },
      ],
    });
    listOutlineChildren.mockResolvedValue({
      items: [
        chapter('ch1', 'bc1', 'arc1'),
        chapter('ch2', 'bc2', 'arc1'),
        { id: 'sc1', kind: 'scene', title: 'Scene', chapter_id: null, structure_node_id: null }, // non-chapter kind, must be skipped
        chapter('ch3', 'bc3', 'arc2'),
        chapter('ch4', 'bc4', null), // bound to no arc (PH21 unassigned) → ungrouped
      ],
      next_cursor: null,
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
    expect(result.current.arcIdForChapter('bc4')).toBeUndefined(); // unassigned chapter
    expect(result.current.arcIdForChapter('unknown')).toBeUndefined();
  });

  it('an arc shell with no bound chapters still yields its (empty) group', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    getArcs.mockResolvedValue({
      arcs: [
        { id: 'arc1', kind: 'arc', title: 'Arc One' },
        { id: 'arc2', kind: 'arc', title: 'Arc Two' },
      ],
    });
    listOutlineChildren.mockResolvedValue({
      items: [chapter('ch1', 'bc1', 'arc1')],
      next_cursor: null,
    });

    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups.map((g) => g.arcId)).toEqual(['arc1', 'arc2']);
    expect(result.current.groups[0].chapterCount).toBe(1);
    expect(result.current.groups[1].chapterCount).toBe(0);
  });

  it('cursor-follows a multi-page root chapter list', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    getArcs.mockResolvedValue({ arcs: [{ id: 'arc1', kind: 'arc', title: 'Arc One' }] });
    listOutlineChildren.mockImplementation((_p: string, _t: string, opts: { parentId: string | null; cursor?: string | null }) => {
      if (opts.parentId === null && !opts.cursor) {
        return Promise.resolve({ items: [chapter('ch1', 'bc1', 'arc1')], next_cursor: 'ch-p2' });
      }
      if (opts.parentId === null) {
        return Promise.resolve({ items: [chapter('ch2', 'bc2', 'arc1')], next_cursor: null });
      }
      return Promise.resolve({ items: [], next_cursor: null });
    });

    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.groups[0].chapterCount).toBe(2);
    expect(result.current.arcIdForChapter('bc1')).toBe('arc1');
    expect(result.current.arcIdForChapter('bc2')).toBe('arc1');
  });

  it('a fetch failure degrades to empty groups rather than throwing', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    getArcs.mockRejectedValue(new Error('network down'));
    const { result } = renderHook(() => useChapterBrowserGroups('b1'));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.hasWork).toBe(true);
    expect(result.current.groups).toEqual([]);
  });

  it('re-fetches when the resolved project changes (book switch)', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    getArcs.mockImplementation((_bookId: string) => Promise.resolve({ arcs: [{ id: 'arc-shell', kind: 'arc', title: 'Shell' }] }));
    listOutlineChildren.mockImplementation((projectId: string, _t: string, opts: { parentId: string | null }) => {
      if (opts.parentId === null) {
        return Promise.resolve({
          items: [{ id: `ch-${projectId}`, kind: 'chapter', title: 'Ch', chapter_id: `bc-${projectId}`, structure_node_id: 'arc-shell' }],
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
    expect(result.current.arcIdForChapter('bc-p1')).toBe('arc-shell');

    work.value = { data: { status: 'found', work: { project_id: 'p2' } }, isLoading: false };
    rerender({ bookId: 'b2' });
    await waitFor(() => expect(result.current.arcIdForChapter('bc-p2')).toBe('arc-shell'));
    expect(result.current.arcIdForChapter('bc-p1')).toBeUndefined(); // prior book's binding dropped
  });
});
