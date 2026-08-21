import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

/**
 * The consumer half of `kg_unchecked` (contracts/guard-signals.yaml → glossary.kg_sweep_coverage).
 *
 * The sweep already REPORTED its coverage; nothing read it, so a rescan run while
 * knowledge-service was down showed the same green "Rescan done — 0 new changes" as a book
 * with genuinely nothing stale. These tests pin the branch that separates them, and each one
 * would pass identically before the change if it only asserted the toast FIRED — so they
 * assert WHICH toast, and the coverage state that outlives it.
 */

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (k: string, o?: Record<string, unknown>) => (o?.count != null ? `${k}:${o.count}` : k),
  }),
}));

// vi.hoisted — the factory below is hoisted above a plain const (TDZ).
const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const listStaleness = vi.fn();
const sweepStaleness = vi.fn();
vi.mock('../../api', () => ({
  wikiApi: {
    listStaleness: (...a: unknown[]) => listStaleness(...a),
    sweepStaleness: (...a: unknown[]) => sweepStaleness(...a),
    dismissStaleness: vi.fn(),
    dismissStalenessBatch: vi.fn(),
  },
}));

import { useWikiStaleness } from '../useWikiStaleness';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return Wrapper;
}

/** A sweep response that found nothing. `kg` overrides the coverage triple. */
function sweep(kg: Partial<{ kg_status: string; kg_checked: number; kg_unchecked: number }>) {
  return {
    flagged: 0,
    kg_flagged: 0,
    recipe_swept: true,
    kg_status: 'checked',
    kg_checked: 12,
    kg_unchecked: 0,
    ...kg,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  listStaleness.mockResolvedValue({ items: [], total: 0 });
});

describe('useWikiStaleness — kg coverage', () => {
  it('a fully-compared sweep reports success and holds no coverage warning', async () => {
    sweepStaleness.mockResolvedValue(sweep({}));
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });

    expect(toast.success).toHaveBeenCalledWith('staleness.rescanDone:0');
    expect(toast.warning).not.toHaveBeenCalled();
    expect(result.current.coverage).toBeNull();
  });

  it('a response with NO coverage fields at all warns rather than reading as fully compared', async () => {
    // A glossary build older than guardstatus. The type says these fields are required; the
    // wire does not, and `undefined > 0` is false — the fail-open default in a required type.
    const { kg_status: _s, kg_checked: _c, kg_unchecked: _u, ...legacy } = sweep({});
    sweepStaleness.mockResolvedValue(legacy);
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });

    expect(toast.warning).toHaveBeenCalledWith('staleness.coverageUnknown');
    expect(toast.success).not.toHaveBeenCalled();
    expect(result.current.coverage).toEqual({ unchecked: null });
  });

  it('a sweep that could not compare some articles warns instead of succeeding, with the uncompared count', async () => {
    // The exact shape of the original defect: zero findings, because three articles were
    // never looked at. `found` is 0 in BOTH this test and the one above.
    sweepStaleness.mockResolvedValue(sweep({ kg_status: 'degraded', kg_checked: 9, kg_unchecked: 3 }));
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });

    expect(toast.warning).toHaveBeenCalledWith('staleness.rescanUnchecked:3');
    expect(toast.success).not.toHaveBeenCalled();
    expect(result.current.coverage).toEqual({ unchecked: 3 });
  });

  it('a degraded STATUS with a zero count is still a gap — the two fields are read independently', async () => {
    // Today the server cannot emit this (guardstatus.Over derives degraded FROM the count,
    // and the mid-sweep degradedSoFar report never reaches the wire). That is a coupling
    // across two files, not an invariant, so the UI must not depend on it.
    sweepStaleness.mockResolvedValue(sweep({ kg_status: 'degraded', kg_unchecked: 0 }));
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });

    expect(toast.warning).toHaveBeenCalledWith('staleness.rescanUnchecked:0');
    expect(result.current.coverage).toEqual({ unchecked: 0 });
  });

  it('a later clean sweep clears the standing warning', async () => {
    sweepStaleness.mockResolvedValue(sweep({ kg_status: 'degraded', kg_unchecked: 2 }));
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });
    expect(result.current.coverage).not.toBeNull();

    sweepStaleness.mockResolvedValue(sweep({}));
    await act(async () => { await result.current.rescan(); });
    await waitFor(() => expect(result.current.coverage).toBeNull());
  });

  it('a recipe-half skip is still reported as its own partial, not folded into the coverage gap', async () => {
    sweepStaleness.mockResolvedValue({ ...sweep({}), recipe_swept: false });
    const { result } = renderHook(() => useWikiStaleness('b1'), { wrapper: wrapper() });
    await act(async () => { await result.current.rescan(); });

    expect(toast.success).toHaveBeenCalledWith('staleness.rescanPartial:0');
    expect(result.current.coverage).toBeNull();
  });
});
