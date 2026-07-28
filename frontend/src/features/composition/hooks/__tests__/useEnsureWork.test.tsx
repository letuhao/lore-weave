// Onboarding — the Studio ensures a book has its composition Work silently.
//
// The hole this closes was dogfooded on a real book: the Studio offered "Chapter"/"Part" and
// nothing else, so an author could write for a long time with plan / beats / scenes / quality
// switched off (composition_work=0, outline_node=0, plan_run=0) and nothing on screen saying so.
// The only affordance that created a Work lived on gated panels a new author never opens.
//
// The two cases that matter here are the ones that are NOT "absent → create": provisioning while
// the answer is still unknown would fire on every mount, and retrying a failure in a loop would
// hammer a service that is already down.
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

const resolveWork = vi.fn();
const createWork = vi.fn();
vi.mock('../../api', () => ({
  compositionApi: {
    resolveWork: (...a: unknown[]) => resolveWork(...a),
    createWork: (...a: unknown[]) => createWork(...a),
  },
}));

import { useEnsureWork } from '../useWork';

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  resolveWork.mockReset();
  createWork.mockReset();
  createWork.mockResolvedValue({ id: 'w1', project_id: 'p1' });
});

describe('useEnsureWork', () => {
  it('provisions when the book has NO Work', async () => {
    resolveWork.mockResolvedValue({ status: 'none' });
    renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await waitFor(() => expect(createWork).toHaveBeenCalledWith('b1', 't'));
  });

  it('provisions when resolveWork reports a PENDING work as absent', async () => {
    // resolveWork deliberately EXCLUDES pending (null-project) works, so the row the
    // `book.created` consumer created reads as absent here. The create call is an idempotent
    // get-or-create — it BACKFILLS that same row with the knowledge project, which the consumer
    // could not do itself (minting a project is JWT-only).
    resolveWork.mockResolvedValue({ status: 'none' });
    renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await waitFor(() => expect(createWork).toHaveBeenCalledTimes(1));
  });

  it('does NOT provision while the answer is still unknown', async () => {
    let settle!: (v: unknown) => void;
    resolveWork.mockImplementation(() => new Promise((r) => { settle = r; }));
    renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(createWork).not.toHaveBeenCalled();   // loading ≠ absent
    settle({ status: 'found', work: { project_id: 'p1' } });
    await new Promise((r) => setTimeout(r, 20));
    expect(createWork).not.toHaveBeenCalled();   // and it really had one
  });

  it('does NOT provision on a resolve ERROR — an outage is not an absent Work', async () => {
    resolveWork.mockRejectedValue(new Error('composition down'));
    renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await new Promise((r) => setTimeout(r, 40));
    expect(createWork).not.toHaveBeenCalled();
  });

  it('leaves an existing Work alone', async () => {
    resolveWork.mockResolvedValue({ status: 'found', work: { project_id: 'p1' } });
    renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await new Promise((r) => setTimeout(r, 40));
    expect(createWork).not.toHaveBeenCalled();
  });

  it('tries at most ONCE per mount, even when the create fails', async () => {
    resolveWork.mockResolvedValue({ status: 'none' });
    createWork.mockRejectedValue(new Error('nope'));
    const { rerender } = renderHook(() => useEnsureWork('b1', 't'), { wrapper });
    await waitFor(() => expect(createWork).toHaveBeenCalledTimes(1));
    rerender();
    rerender();
    await new Promise((r) => setTimeout(r, 40));
    // A failure that re-fired would hammer a service that is already down.
    expect(createWork).toHaveBeenCalledTimes(1);
  });

  it('does nothing without a token', async () => {
    renderHook(() => useEnsureWork('b1', null), { wrapper });
    await new Promise((r) => setTimeout(r, 20));
    expect(resolveWork).not.toHaveBeenCalled();
    expect(createWork).not.toHaveBeenCalled();
  });
});
