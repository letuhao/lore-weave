import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// useWorkResolution decides the source (Work → outline; none → chapters). Mock it + the two APIs.
const work = vi.hoisted(() => ({ value: { data: { status: 'none' } as Record<string, unknown>, isLoading: false } }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => work.value }));

const listChaptersPage = vi.fn();
const listOutlineChildren = vi.fn();
const outlineStats = vi.fn(() => Promise.resolve({ arcs: 0, chapters: 0, scenes: 0 }));
vi.mock('@/features/books/api', () => ({ booksApi: { listChaptersPage: (...a: unknown[]) => listChaptersPage(...a) } }));
vi.mock('@/features/composition/api', () => ({ compositionApi: {
  listOutlineChildren: (...a: unknown[]) => listOutlineChildren(...a),
  outlineStats: (...a: unknown[]) => outlineStats(...a),
} }));

import { useManuscriptTree } from '../useManuscriptTree';
import type { ManuscriptRow } from '../types';

const isNode = (r: ManuscriptRow, id: string) => r.type === 'node' && r.node.id === id;

beforeEach(() => {
  listChaptersPage.mockReset();
  listOutlineChildren.mockReset();
  work.value = { data: { status: 'none' }, isLoading: false };
});

describe('useManuscriptTree', () => {
  it('no Work → chapters source: loads the first page (node + more row) and the total', async () => {
    listChaptersPage.mockResolvedValue({
      items: [{ chapter_id: 'c1', sort_order: 1, title: 'A', original_filename: 'a.txt' }],
      next_cursor: 'cur', total: 10,
    });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.rows.length).toBeGreaterThan(0));
    expect(result.current.source).toBe('chapters');
    expect(result.current.total).toBe(10);
    expect(result.current.rows.some((r) => isNode(r, 'c1'))).toBe(true);
    expect(result.current.rows.some((r) => r.type === 'more')).toBe(true); // next_cursor → paging affordance
  });

  it('has Work → outline source: loads top-level arcs with parentId null', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockResolvedValue({
      items: [{ id: 'arc1', kind: 'arc', title: 'Arc I', chapter_id: null, status: 'outline' }],
      next_cursor: null,
    });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.rows.length).toBeGreaterThan(0));
    expect(result.current.source).toBe('outline');
    expect(listOutlineChildren).toHaveBeenCalledWith('p1', 't', expect.objectContaining({ parentId: null }));
    expect(isNode(result.current.rows[0], 'arc1')).toBe(true);
  });

  it('toggleExpand lazy-loads a node’s children (parentId = the node)', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren
      .mockResolvedValueOnce({ items: [{ id: 'arc1', kind: 'arc', title: 'Arc', chapter_id: null, status: null }], next_cursor: null })
      .mockResolvedValueOnce({ items: [{ id: 'ch1', kind: 'chapter', title: 'Ch', chapter_id: 'bc1', status: null }], next_cursor: null });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.rows.length).toBe(1)); // arc only
    act(() => result.current.toggleExpand('arc1'));
    await waitFor(() => expect(result.current.rows.some((r) => isNode(r, 'ch1'))).toBe(true));
    expect(listOutlineChildren).toHaveBeenLastCalledWith('p1', 't', expect.objectContaining({ parentId: 'arc1' }));
  });

  it('drops a STALE page that resolves after a book switch (M1 guard)', async () => {
    // b1's first page is deferred; b2's resolves immediately. We switch to b2, then resolve
    // b1 late — its rows must NOT leak into b2's tree.
    let resolveB1!: (v: unknown) => void;
    const b1Page = new Promise((r) => { resolveB1 = r; });
    listChaptersPage.mockImplementation((_t: unknown, bId: string) =>
      bId === 'b1'
        ? b1Page
        : Promise.resolve({ items: [{ chapter_id: 'c-b2', sort_order: 1, title: 'B2', original_filename: 'b2' }], next_cursor: null, total: 1 }),
    );
    const { result, rerender } = renderHook(({ bookId }) => useManuscriptTree(bookId, 't'), { initialProps: { bookId: 'b1' } });
    rerender({ bookId: 'b2' }); // switch before b1 resolves
    await waitFor(() => expect(result.current.rows.some((r) => isNode(r, 'c-b2'))).toBe(true));
    // now the stale b1 page arrives
    await act(async () => {
      resolveB1({ items: [{ chapter_id: 'c-b1', sort_order: 1, title: 'B1', original_filename: 'b1' }], next_cursor: null, total: 1 });
      await Promise.resolve();
    });
    expect(result.current.rows.some((r) => isNode(r, 'c-b1'))).toBe(false); // no leak
    expect(result.current.rows.some((r) => isNode(r, 'c-b2'))).toBe(true);
  });

  it('filters structural `beat` nodes out of the outline', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockResolvedValue({
      items: [
        { id: 'arc1', kind: 'arc', title: 'Arc', chapter_id: null, status: null },
        { id: 'b1', kind: 'beat', title: 'Beat', chapter_id: null, status: null },
      ],
      next_cursor: null,
    });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.rows.length).toBeGreaterThan(0));
    expect(result.current.rows.some((r) => isNode(r, 'arc1'))).toBe(true);
    expect(result.current.rows.some((r) => isNode(r, 'b1'))).toBe(false); // beat dropped
  });
});
