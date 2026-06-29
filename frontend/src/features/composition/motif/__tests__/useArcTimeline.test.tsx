// W10 arc-timeline — useArcTimeline: seeds the working copy from the fetched arc,
// applies edits optimistically, persists the layout with a DEBOUNCED If-Match PATCH,
// adopts the server's new version for the next save, and gates editing to the owner.
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

const apiJson = vi.fn();
vi.mock('@/api', () => ({ apiJson: (...a: unknown[]) => apiJson(...a), apiBase: () => '' }));

import { useArcTimeline } from '../hooks/useArcTimeline';
import type { ArcTemplate } from '../arcTypes';

const OWNER = 'user-1';

const ARC = (over: Partial<ArcTemplate> = {}): ArcTemplate => ({
  id: 'A1', owner_user_id: OWNER, code: 'rev', language: 'en', visibility: 'private',
  name: 'Revenge', summary: '', genre_tags: [], chapter_span: 10,
  threads: [{ key: 'combat', label: 'Combat', glyph: '⚔' }],
  layout: [{ motif_code: 'duel', motif_id: 'm1', thread: 'combat', span_start: 2, span_end: 3, ord: 0 }],
  pacing: [], arc_roster: [], source: 'authored', imported_derived: false,
  source_version: null, status: 'active', version: 1, ...over,
});

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { qc, wrapper };
}

beforeEach(() => {
  apiJson.mockReset();
  localStorage.setItem('lw_user', JSON.stringify({ user_id: OWNER }));
});
afterEach(() => { localStorage.clear(); vi.useRealTimers(); });

describe('useArcTimeline', () => {
  it('seeds placements from the fetched layout and reports the owner can edit', async () => {
    apiJson.mockResolvedValueOnce(ARC());
    const { wrapper } = wrap();
    const { result } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await waitFor(() => expect(result.current.placements).toHaveLength(1));
    expect(result.current.placements[0]).toMatchObject({ id: 'p0', motif_code: 'duel', span_start: 2 });
    expect(result.current.threads[0]).toMatchObject({ key: 'combat', glyph: '⚔' });
    expect(result.current.chapterSpan).toBe(10);
    expect(result.current.canEdit).toBe(true);
  });

  it('a foreign / system arc is read-only (canEdit false)', async () => {
    apiJson.mockResolvedValueOnce(ARC({ owner_user_id: 'someone-else' }));
    const { wrapper } = wrap();
    const { result } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await waitFor(() => expect(result.current.arc).toBeDefined());
    expect(result.current.canEdit).toBe(false);
  });

  it('an edit persists a debounced If-Match PATCH of the layout, then adopts the new version', async () => {
    vi.useFakeTimers();
    apiJson
      .mockResolvedValueOnce(ARC())                       // GET
      .mockResolvedValueOnce(ARC({ version: 2 }))         // 1st PATCH → version 2
      .mockResolvedValueOnce(ARC({ version: 3 }));        // 2nd PATCH → version 3
    const { wrapper } = wrap();
    const { result } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    expect(result.current.placements).toHaveLength(1);

    act(() => {
      result.current.onEdit({ type: 'place', thread: 'combat', motif_code: 'ambush', span_start: 4, span_end: 5 });
    });
    expect(result.current.placements).toHaveLength(2);     // optimistic, before debounce

    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    const patch1 = apiJson.mock.calls.find((c) => (c[1] as { method?: string })?.method === 'PATCH');
    expect(patch1?.[0]).toBe('/v1/composition/arc-templates/A1');
    expect((patch1?.[1] as { headers: Record<string, string> }).headers['If-Match']).toBe('1');
    const body1 = JSON.parse((patch1?.[1] as { body: string }).body);
    expect(body1.layout).toHaveLength(2);                  // the placed motif is persisted

    // a SECOND edit must use the server's new version (2) as the If-Match.
    act(() => { result.current.onEdit({ type: 'remove', placement_id: 'p1' }); });
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    const patches = apiJson.mock.calls.filter((c) => (c[1] as { method?: string })?.method === 'PATCH');
    expect((patches[1][1] as { headers: Record<string, string> }).headers['If-Match']).toBe('2');
  });

  it('flushes a pending edit on unmount (a last edit is not lost)', async () => {
    vi.useFakeTimers();
    apiJson.mockResolvedValueOnce(ARC()).mockResolvedValueOnce(ARC({ version: 2 }));
    const { wrapper } = wrap();
    const { result, unmount } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.onEdit({ type: 'remove', placement_id: 'p0' }); });
    // unmount BEFORE the debounce fires → cleanup flushes the pending persist.
    await act(async () => { unmount(); await vi.advanceTimersByTimeAsync(0); });
    const patches = apiJson.mock.calls.filter((c) => (c[1] as { method?: string })?.method === 'PATCH');
    expect(patches).toHaveLength(1);
  });

  it('does NOT double-persist when unmount follows an already-fired debounce', async () => {
    vi.useFakeTimers();
    apiJson.mockResolvedValueOnce(ARC()).mockResolvedValueOnce(ARC({ version: 2 }));
    const { wrapper } = wrap();
    const { result, unmount } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.onEdit({ type: 'remove', placement_id: 'p0' }); });
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });   // debounce fires → 1 PATCH
    await act(async () => { unmount(); await vi.advanceTimersByTimeAsync(0); });
    const patches = apiJson.mock.calls.filter((c) => (c[1] as { method?: string })?.method === 'PATCH');
    expect(patches).toHaveLength(1);   // NOT 2 — the fired timer nulled its ref
  });

  it('surfaces a 412 conflict on a stale write', async () => {
    vi.useFakeTimers();
    apiJson
      .mockResolvedValueOnce(ARC())
      .mockRejectedValueOnce(Object.assign(new Error('conflict'), { status: 412 }))
      .mockResolvedValueOnce(ARC({ version: 2 }));        // the invalidate-triggered reconcile refetch
    const { wrapper } = wrap();
    const { result } = renderHook(() => useArcTimeline('A1', 'tok'), { wrapper });
    await act(async () => { await vi.advanceTimersByTimeAsync(0); });
    act(() => { result.current.onEdit({ type: 'remove', placement_id: 'p0' }); });
    await act(async () => { await vi.advanceTimersByTimeAsync(700); });
    expect(result.current.saveError).toBe('conflict');
  });
});
