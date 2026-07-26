// 32 arc-inspector controller — the OCC edit path + subject resolution. The critical regression:
// PATCH /arcs/{id} returns the BARE node (no resolved cascade); the hook MUST refetch the enriched
// detail after a successful edit, or the body's `d.resolved` blanks/crashes.
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

const api = vi.hoisted(() => ({
  getArcs: vi.fn(),
  getArc: vi.fn(),
  patchArc: vi.fn(),
  archiveArc: vi.fn(),
  restoreArc: vi.fn(),
}));
vi.mock('@/features/plan-hub/api', () => api);
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../host/StudioHostProvider', () => ({ useStudioBusSelector: () => undefined }));

import { useArcInspector } from '../useArcInspector';

const ENRICHED = {
  id: 'arc1', kind: 'arc', parent_id: 'saga1', depth: 1, rank: '0m', title: 'T', status: 'drafting',
  version: 7, span: { from_order: 1, to_order: 3 }, first_story_order: 1000, is_contiguous: true,
  chapter_count: 3, is_archived: false, tracks: [], roster: [],
  resolved: { tracks: [{ key: 'revenge', label: 'R' }], roster: [], roster_bindings: {} },
  open_promises: [],
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  Object.values(api).forEach((f) => f.mockReset());
  api.getArcs.mockResolvedValue({ arcs: [{ id: 'saga1', kind: 'saga', parent_id: null, depth: 0 }, { id: 'arc1', kind: 'arc', parent_id: 'saga1', depth: 1 }] });
  api.getArc.mockResolvedValue(ENRICHED);
});

describe('useArcInspector', () => {
  it('after a successful edit it REFETCHES the enriched detail (not the bare PATCH node)', async () => {
    // PATCH returns a bare node with NO `resolved` — if the hook seeded that, the body would crash.
    api.patchArc.mockResolvedValue({ id: 'arc1', version: 8, title: 'New' });
    api.getArc
      .mockResolvedValueOnce(ENRICHED)                               // initial load (v7)
      .mockResolvedValueOnce({ ...ENRICHED, version: 8, title: 'New' }); // post-edit refetch (v8, enriched)

    const { result } = renderHook(() => useArcInspector('book', 'arc1'), { wrapper });
    await waitFor(() => expect(result.current.detail?.version).toBe(7));

    await act(async () => { await result.current.edit({ title: 'New' }); });

    expect(api.patchArc).toHaveBeenCalledWith('arc1', { title: 'New' }, 7, 'tok');
    // getArc called AGAIN after patch → the detail is the ENRICHED refetch, resolved intact.
    expect(api.getArc).toHaveBeenCalledTimes(2);
    expect(result.current.detail?.version).toBe(8);
    expect(result.current.detail?.resolved.tracks).toHaveLength(1); // would be undefined on the bare node
    expect(result.current.writeError).toBeNull();
  });

  it('a 412 reseeds and surfaces "changed elsewhere", never a silent clobber', async () => {
    api.patchArc.mockRejectedValue(Object.assign(new Error('conflict'), { status: 412 }));
    const { result } = renderHook(() => useArcInspector('book', 'arc1'), { wrapper });
    await waitFor(() => expect(result.current.detail?.version).toBe(7));

    await act(async () => { await result.current.edit({ title: 'X' }); });
    expect(result.current.writeError).toContain('changed elsewhere');
  });

  it('derives the archive blast radius + breadcrumb from the shell', async () => {
    api.getArcs.mockResolvedValue({ arcs: [
      { id: 'saga1', kind: 'saga', parent_id: null, depth: 0 },
      { id: 'arc1', kind: 'arc', parent_id: 'saga1', depth: 1 },
      { id: 'sub1', kind: 'arc', parent_id: 'arc1', depth: 2 },
    ] });
    const { result } = renderHook(() => useArcInspector('book', 'arc1'), { wrapper });
    await waitFor(() => expect(result.current.shell.length).toBe(3));
    expect(result.current.blastRadius).toBe(1);           // sub1 under arc1
    expect(result.current.ancestors.map((a) => a.id)).toEqual(['saga1', 'arc1']);
  });
});
