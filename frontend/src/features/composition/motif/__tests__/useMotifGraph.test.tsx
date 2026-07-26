// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the persistence controller. Proves the spec §6.5 edge cases:
// the pending-MAP never coalesces two nodes into one write (E1), the debounced flush batches,
// if_version is read from the ref (E3), and a 412 reseeds + retries (E4).
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import { useMotifGraph } from '../hooks/useMotifGraph';
import { motifApi } from '../api';

vi.mock('../api', () => ({ motifApi: { motifGraph: vi.fn(), patchGraphLayout: vi.fn() } }));

const GRAPH = {
  nodes: [{ id: 'm1', code: 'a', name: 'A', kind: 'scheme', mine: true, book_shared: false }],
  edges: [], layout: { positions: {}, version: 4 }, truncated: false, node_cap: 300,
};

function wrap() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.useFakeTimers();
  (motifApi.motifGraph as ReturnType<typeof vi.fn>).mockResolvedValue(GRAPH);
  (motifApi.patchGraphLayout as ReturnType<typeof vi.fn>).mockReset();
});
afterEach(() => { vi.useRealTimers(); });

async function loaded() {
  const h = renderHook(() => useMotifGraph('book1', 'tok'), { wrapper: wrap() });
  await vi.waitFor(() => expect(h.result.current.data).toBeTruthy());
  return h;
}

describe('useMotifGraph — persistence', () => {
  it('batches TWO different nodes into ONE flush (pending-map never drops a node)', async () => {
    (motifApi.patchGraphLayout as ReturnType<typeof vi.fn>).mockResolvedValue({ positions: {}, version: 5 });
    const h = await loaded();
    act(() => { h.result.current.savePosition('m1', 1, 2); h.result.current.savePosition('m2', 3, 4); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    expect(motifApi.patchGraphLayout).toHaveBeenCalledTimes(1);
    const [, moves, ifVersion] = (motifApi.patchGraphLayout as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(moves).toEqual(expect.arrayContaining([
      { motif_id: 'm1', x: 1, y: 2 }, { motif_id: 'm2', x: 3, y: 4 },
    ]));
    expect(ifVersion).toBe(4); // seeded from the loaded layout version
  });

  it('on a 412 conflict, reseeds the version and RETRIES the flush', async () => {
    const conflict = Object.assign(new Error('stale'), {
      status: 412, body: { detail: { current: { positions: { z: { x: 0, y: 0 } }, version: 9 } } },
    });
    (motifApi.patchGraphLayout as ReturnType<typeof vi.fn>)
      .mockRejectedValueOnce(conflict)
      .mockResolvedValueOnce({ positions: {}, version: 10 });
    const h = await loaded();
    act(() => { h.result.current.savePosition('m1', 7, 8); });
    await act(async () => { await vi.advanceTimersByTimeAsync(500); });
    // first call used the stale version 4; the retry used the reseeded version 9
    const calls = (motifApi.patchGraphLayout as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls.length).toBe(2);
    expect(calls[0][2]).toBe(4);
    expect(calls[1][2]).toBe(9);
  });
});
