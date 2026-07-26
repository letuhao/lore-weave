import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// useWorkResolution supplies the OUTLINE presence (Work → outline); the unified /structure read
// supplies the PARTS presence. Mock both + the APIs. (P1.2 mode-by-content: parts render regardless
// of Work-mode.) The structure mock defaults to no-parts; a parts test flips kinds_present.parts.
const work = vi.hoisted(() => ({ value: { data: { status: 'none' } as Record<string, unknown>, isLoading: false } }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => work.value }));
const structure = vi.hoisted(() => ({ value: { data: { kinds_present: { parts: false, outline: false } } as Record<string, unknown>, isLoading: false } }));
vi.mock('../useBookStructure', () => ({ useBookStructure: () => structure.value }));
const invalidateQueries = vi.fn();
vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@tanstack/react-query')>();
  return { ...actual, useQueryClient: () => ({ invalidateQueries }) };
});

const listChaptersPage = vi.fn();
const listOutlineChildren = vi.fn();
const outlineStats = vi.fn(() => Promise.resolve({ arcs: 0, chapters: 0, scenes: 0 }));
vi.mock('@/features/books/api', () => ({ booksApi: { listChaptersPage: (...a: unknown[]) => listChaptersPage(...a) } }));
vi.mock('@/features/composition/api', () => ({ compositionApi: {
  listOutlineChildren: (...a: unknown[]) => listOutlineChildren(...a),
  outlineStats: (...a: unknown[]) => outlineStats(...a),
} }));
// S-02: default parts = none, so these tests exercise the FLAT chapters path (the grouped-tree
// path is covered by partsTree.test.ts + a dedicated case below). Keep groupChaptersByParts real
// (buildPartsTree depends on it). Individual tests can override listParts.
const listParts = vi.fn(() => Promise.resolve({ items: [] }));
const reorderParts = vi.fn(() => Promise.resolve({ items: [] }));
const restorePart = vi.fn(() => Promise.resolve({}));
vi.mock('../partsApi', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../partsApi')>();
  return { ...actual, partsApi: { ...actual.partsApi, list: (...a: unknown[]) => listParts(...a), reorder: (...a: unknown[]) => reorderParts(...a), restore: (...a: unknown[]) => restorePart(...a) } };
});

const mkAct = (id: string, sort: number, state: 'active' | 'trashed' = 'active') => ({ part_id: id, book_id: 'b1', title: id.toUpperCase(), path: id, sort_order: sort, lifecycle_state: state });

import { useManuscriptTree } from '../useManuscriptTree';
import type { ManuscriptRow } from '../types';

const isNode = (r: ManuscriptRow, id: string) => r.type === 'node' && r.node.id === id;

beforeEach(() => {
  listChaptersPage.mockReset();
  listOutlineChildren.mockReset();
  listParts.mockReset();
  reorderParts.mockReset();
  restorePart.mockReset();
  restorePart.mockResolvedValue({});
  reorderParts.mockResolvedValue({ items: [] });
  listParts.mockResolvedValue({ items: [] }); // default: flat mode
  work.value = { data: { status: 'none' }, isLoading: false };
  structure.value = { data: { kinds_present: { parts: false, outline: false } }, isLoading: false }; // default: no parts
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

  // F11 — a Work whose outline is EMPTY (chapters never decomposed) must NOT show "No chapters yet."
  // over a book that has chapters. Fall back to the flat book-service chapters.
  it('has Work but EMPTY outline → falls back to book-service chapters (F11: chapters do not vanish)', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    listOutlineChildren.mockResolvedValue({ items: [], next_cursor: null }); // un-decomposed Work
    listChaptersPage.mockResolvedValue({
      items: [{ chapter_id: 'c1', sort_order: 1, title: 'Chapter 1', original_filename: 'a.txt' }],
      next_cursor: null, total: 1,
    });
    listParts.mockResolvedValue({ items: [] });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.rows.some((r) => isNode(r, 'c1'))).toBe(true));
    expect(result.current.source).toBe('chapters'); // fell back
    expect(listChaptersPage).toHaveBeenCalled();     // the real chapters loaded
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

  it('S-02: a book WITH parts renders the grouped act tree (part header + nested chapter)', async () => {
    listParts.mockResolvedValue({
      items: [{ part_id: 'p1', book_id: 'b1', title: 'Act I', path: 'act-i', sort_order: 1, lifecycle_state: 'active' }],
    });
    structure.value = { data: { kinds_present: { parts: true, outline: false } }, isLoading: false };
    listChaptersPage.mockResolvedValue({
      items: [{ chapter_id: 'c1', sort_order: 1, title: 'Ch', original_filename: 'a.txt', part_id: 'p1' }],
      next_cursor: null, total: 1,
    });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.partsMode).toBe(true));
    await waitFor(() => expect(result.current.rows.some((r) => isNode(r, 'p1'))).toBe(true));
    const head = result.current.rows.find((r) => isNode(r, 'p1'));
    expect(head && head.type === 'node' && head.node.kind).toBe('part');
    // the act is expanded by default → its chapter is visible, nested one level deeper
    const chap = result.current.rows.find((r) => isNode(r, 'c1'));
    expect(chap && chap.type === 'node' && chap.depth).toBe(1);
    // no paging affordance in grouped mode (whole book loaded)
    expect(result.current.rows.some((r) => r.type === 'more')).toBe(false);
  });

  it('S-02b: moveAct swaps with a neighbour and reorders the FULL id set; boundary = no-op', async () => {
    listParts.mockResolvedValue({ items: [mkAct('p1', 1), mkAct('p2', 2), mkAct('p3', 3)] });
    structure.value = { data: { kinds_present: { parts: true, outline: false } }, isLoading: false };
    listChaptersPage.mockResolvedValue({ items: [], next_cursor: null, total: 0 });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.partsMode).toBe(true));

    // move p2 up → [p2, p1, p3]
    await act(async () => { await result.current.moveAct('p2', 'up'); });
    expect(reorderParts).toHaveBeenLastCalledWith('t', 'b1', ['p2', 'p1', 'p3']);

    // move p1 up when it's first → no-op (boundary), no new reorder call
    reorderParts.mockClear();
    await act(async () => { await result.current.moveAct('p1', 'up'); });
    expect(reorderParts).not.toHaveBeenCalled();
  });

  it('S-02b: splits include_trashed into active `parts` + `trashedActs`; restoreAct calls restore', async () => {
    listParts.mockResolvedValue({ items: [mkAct('p1', 1), mkAct('gone', 2, 'trashed')] });
    structure.value = { data: { kinds_present: { parts: true, outline: false } }, isLoading: false };
    listChaptersPage.mockResolvedValue({ items: [], next_cursor: null, total: 0 });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.partsMode).toBe(true));
    expect(result.current.parts.map((p) => p.part_id)).toEqual(['p1']);
    expect(result.current.trashedActs.map((p) => p.part_id)).toEqual(['gone']);
    // list was called WITH include_trashed
    expect(listParts).toHaveBeenCalledWith('t', 'b1', { includeTrashed: true });

    await act(async () => { await result.current.restoreAct('gone'); });
    expect(restorePart).toHaveBeenCalledWith('t', 'b1', 'gone');
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

  // P1.2 review-impl HIGH — a /structure OUTAGE (loaded, no data) must NOT brick the rail with a
  // permanent 'pending'/"Loading…"; it degrades to the flat path (parts merely unavailable).
  it('a /structure error degrades to a usable rail (no permanent pending)', async () => {
    structure.value = { data: undefined, isLoading: false }; // errored: not loading, no data
    listChaptersPage.mockResolvedValue({
      items: [{ chapter_id: 'c1', sort_order: 1, title: 'A', original_filename: 'a.txt' }],
      next_cursor: null, total: 1,
    });
    const { result } = renderHook(() => useManuscriptTree('b1', 't'));
    await waitFor(() => expect(result.current.source).not.toBe('pending'));
    expect(result.current.source).toBe('chapters'); // degraded to flat, NOT bricked
    await waitFor(() => expect(result.current.rows.some((r) => isNode(r, 'c1'))).toBe(true));
  });
});
