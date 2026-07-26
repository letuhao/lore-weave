import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { useProvenance } from '../useProvenance';
import type { TiptapEditorHandle } from '@/components/editor/TiptapEditor';

// A fake editor handle whose unreviewed count + visibility we can drive, to lock
// the host glue (badge derives from the doc; toggle persists + pushes to editor;
// mark-all calls the handle then refreshes the badge).
function fakeHandle(count = 0) {
  const calls = { setVisible: [] as boolean[], markAll: 0 };
  let unreviewed = count;
  const handle = {
    setProvenanceVisible: (v: boolean) => calls.setVisible.push(v),
    getUnreviewedProvenanceCount: () => unreviewed,
    markAllProvenanceReviewed: () => { calls.markAll += 1; const n = unreviewed; unreviewed = 0; return n; },
  } as unknown as TiptapEditorHandle;
  return { ref: { current: handle }, calls, setUnreviewed: (n: number) => { unreviewed = n; } };
}

beforeEach(() => localStorage.clear());

describe('useProvenance (T5.3)', () => {
  it('derives the unreviewed-span count from the editor on each doc change', () => {
    const f = fakeHandle(3);
    const { result, rerender } = renderHook(({ doc }) => useProvenance(f.ref, doc), {
      initialProps: { doc: { v: 1 } },
    });
    expect(result.current.unreviewedCount).toBe(3);
    f.setUnreviewed(1);
    rerender({ doc: { v: 2 } }); // a new doc → recompute
    expect(result.current.unreviewedCount).toBe(1);
  });

  it('defaults visible=true (always-on underlay) and pushes it to the editor', () => {
    const f = fakeHandle();
    const { result } = renderHook(() => useProvenance(f.ref, { v: 1 }));
    expect(result.current.visible).toBe(true);
    expect(f.calls.setVisible).toContain(true);
  });

  it('toggleVisible flips, persists to localStorage, and pushes to the editor', () => {
    const f = fakeHandle();
    const { result } = renderHook(() => useProvenance(f.ref, { v: 1 }));
    act(() => result.current.toggleVisible());
    expect(result.current.visible).toBe(false);
    expect(localStorage.getItem('lw-provenance-visible')).toBe('0');
    expect(f.calls.setVisible).toContain(false);
  });

  it('honours a persisted hidden preference on mount', () => {
    localStorage.setItem('lw-provenance-visible', '0');
    const f = fakeHandle();
    const { result } = renderHook(() => useProvenance(f.ref, { v: 1 }));
    expect(result.current.visible).toBe(false);
  });

  it('markAllReviewed calls the handle and refreshes the badge to 0', () => {
    const f = fakeHandle(4);
    const { result } = renderHook(() => useProvenance(f.ref, { v: 1 }));
    expect(result.current.unreviewedCount).toBe(4);
    let returned = -1;
    act(() => { returned = result.current.markAllReviewed(); });
    expect(returned).toBe(4);
    expect(f.calls.markAll).toBe(1);
    expect(result.current.unreviewedCount).toBe(0);
  });
});
