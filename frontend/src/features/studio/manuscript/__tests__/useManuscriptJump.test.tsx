import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';

// Source resolution + the two search APIs are mocked; the hook owns debounce + stale-guard.
const work = vi.hoisted(() => ({ value: { data: { status: 'none' } as Record<string, unknown>, isLoading: false } }));
vi.mock('@/features/composition/hooks/useWork', () => ({ useWorkResolution: () => work.value }));

const searchOutline = vi.fn();
const listChaptersPage = vi.fn();
vi.mock('@/features/books/api', () => ({ booksApi: { listChaptersPage: (...a: unknown[]) => listChaptersPage(...a) } }));
vi.mock('@/features/composition/api', () => ({ compositionApi: { searchOutline: (...a: unknown[]) => searchOutline(...a) } }));

import { useManuscriptJump } from '../useManuscriptJump';

// Advance past the debounce AND flush the fetch microtasks (no waitFor — it polls on real
// timers, which deadlocks under fake timers).
async function settle() {
  await act(async () => { await vi.advanceTimersByTimeAsync(200); });
}

beforeEach(() => {
  vi.useFakeTimers();
  searchOutline.mockReset();
  listChaptersPage.mockReset();
  work.value = { data: { status: 'none' }, isLoading: false };
});
afterEach(() => { vi.useRealTimers(); });

describe('useManuscriptJump', () => {
  it('no Work → chapters source: searches book-service with q, maps hits', async () => {
    listChaptersPage.mockResolvedValue({ items: [{ chapter_id: 'c1', sort_order: 3, title: 'Huyết chiến', original_filename: 'x' }], next_cursor: null });
    const { result } = renderHook(() => useManuscriptJump('b1', 't'));
    act(() => result.current.setQuery('huyết'));
    await settle();
    expect(listChaptersPage).toHaveBeenCalledWith('t', 'b1', expect.objectContaining({ q: 'huyết' }));
    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0]).toMatchObject({ id: 'c1', kind: 'chapter', title: 'Huyết chiến', number: 3, path: [] });
  });

  it('has Work → outline source: searches composition, maps kind + breadcrumb path', async () => {
    work.value = { data: { status: 'found', work: { project_id: 'p1' } }, isLoading: false };
    searchOutline.mockResolvedValue({ items: [{ id: 's9', kind: 'scene', title: 'Bị phản bội', chapter_id: 'bc3', status: 'done', story_order: 1, path: ['Arc I', 'Ch 0003'] }] });
    const { result } = renderHook(() => useManuscriptJump('b1', 't'));
    act(() => result.current.setQuery('phản'));
    await settle();
    expect(searchOutline).toHaveBeenCalledWith('p1', 't', expect.objectContaining({ q: 'phản' }));
    expect(result.current.results).toHaveLength(1);
    expect(result.current.results[0]).toMatchObject({ id: 's9', kind: 'scene', chapterId: 'bc3', path: ['Arc I', 'Ch 0003'] });
  });

  it('empty query short-circuits — no request, empty results, not active', async () => {
    const { result } = renderHook(() => useManuscriptJump('b1', 't'));
    act(() => result.current.setQuery('   '));
    await settle();
    expect(listChaptersPage).not.toHaveBeenCalled();
    expect(result.current.results).toEqual([]);
    expect(result.current.active).toBe(false);
  });

  it('debounces: a superseded query never fires its request', async () => {
    listChaptersPage.mockResolvedValue({ items: [], next_cursor: null });
    const { result } = renderHook(() => useManuscriptJump('b1', 't'));
    act(() => result.current.setQuery('drag'));
    await act(async () => { await vi.advanceTimersByTimeAsync(100); }); // < debounce
    act(() => result.current.setQuery('dragon'));                       // supersedes before it fired
    await settle();
    expect(listChaptersPage).toHaveBeenCalledTimes(1);
    expect(listChaptersPage).toHaveBeenCalledWith('t', 'b1', expect.objectContaining({ q: 'dragon' }));
  });

  it('stale-guard: a late response for an OLD query does not overwrite newer results', async () => {
    // 'a' resolves slowly, 'b' fast. The slow 'a' must not clobber 'b'.
    let resolveA!: (v: unknown) => void;
    const slow = new Promise((r) => { resolveA = r; });
    listChaptersPage.mockImplementation((_t: unknown, _b: unknown, o: { q: string }) =>
      o.q === 'a' ? slow : Promise.resolve({ items: [{ chapter_id: 'cb', sort_order: 2, title: 'B', original_filename: 'b' }], next_cursor: null }));
    const { result } = renderHook(() => useManuscriptJump('b1', 't'));
    act(() => result.current.setQuery('a'));
    await settle();                                   // 'a' fired, pending
    act(() => result.current.setQuery('b'));
    await settle();                                   // 'b' fired + resolved
    expect(result.current.results.some((r) => r.id === 'cb')).toBe(true);
    // now 'a' resolves late — must be dropped
    await act(async () => { resolveA({ items: [{ chapter_id: 'ca', sort_order: 1, title: 'A', original_filename: 'a' }], next_cursor: null }); await Promise.resolve(); });
    expect(result.current.results.some((r) => r.id === 'ca')).toBe(false);
    expect(result.current.results.some((r) => r.id === 'cb')).toBe(true);
  });
});
