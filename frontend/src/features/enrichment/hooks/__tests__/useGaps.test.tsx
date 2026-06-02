import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const detectGapsMock = vi.fn();
const autoEnrichMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      detectGaps: (...a: unknown[]) => detectGapsMock(...a),
      autoEnrich: (...a: unknown[]) => autoEnrichMock(...a),
    },
  };
});

import { useGaps } from '../useGaps';
import type { Gap, DetectGapsResponse, AutoEnrichResponse } from '../../types';

const BOOK = 'book-1';

const G = (over: Partial<Gap> = {}): Gap =>
  ({
    rank: 1,
    score: 0.9,
    canonical_name: '玉虛宮',
    entity_kind: 'location',
    mention_count: 3,
    present_dimensions: ['appearance'],
    missing_dimensions: ['history'],
    ...over,
  } as Gap);

const ENRICH_BODY = {
  embedding_model_ref: 'm-embed',
  generation_model_ref: 'm-gen',
};

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => {
  [detectGapsMock, autoEnrichMock].forEach((m) => m.mockReset());
  Object.values(toastMocks).forEach((m) => m.mockReset());
});

describe('useGaps', () => {
  it('starts with gaps=null, detecting=false, enriching=false', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });
    expect(result.current.gaps).toBeNull();
    expect(result.current.detecting).toBe(false);
    expect(result.current.enriching).toBe(false);
  });

  it('detect calls detectGaps(bookId, token), sets gaps to r.gaps, returns the response', async () => {
    const resp = {
      project_id: 'proj-9',
      book_id: BOOK,
      entities_scanned: 5,
      gap_count: 1,
      gaps: [G()],
    } as DetectGapsResponse;
    detectGapsMock.mockResolvedValue(resp);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.detect();
    });

    expect(detectGapsMock).toHaveBeenCalledWith(BOOK, 'tok');
    expect(out).toBe(resp);
    expect(result.current.gaps).toEqual([G()]);
  });

  it('detect toggles detecting back to false after success', async () => {
    detectGapsMock.mockResolvedValue({
      project_id: 'proj-9',
      book_id: BOOK,
      entities_scanned: 0,
      gap_count: 0,
      gaps: [],
    } as DetectGapsResponse);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.detect();
    });
    expect(result.current.detecting).toBe(false);
  });

  it('detect on throw: toasts the error message, leaves gaps null, returns null', async () => {
    detectGapsMock.mockRejectedValue(new Error('detect boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.detect();
    });

    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('detect boom');
    expect(result.current.gaps).toBeNull();
    expect(result.current.detecting).toBe(false);
  });

  it('autoEnrich calls autoEnrich(bookId, body, token), toasts success, invalidates jobs + proposals', async () => {
    const resp = {
      project_id: 'proj-9',
      entities_scanned: 5,
      detected: 2,
      enqueued_gaps: 2,
      enqueued: true,
    } as AutoEnrichResponse;
    autoEnrichMock.mockResolvedValue(resp);
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.autoEnrich(ENRICH_BODY);
    });

    expect(autoEnrichMock).toHaveBeenCalledWith(BOOK, ENRICH_BODY, 'tok');
    expect(out).toBe(resp);
    expect(toastMocks.success).toHaveBeenCalledWith('gaps.enqueued');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['enrichment-jobs', BOOK]);
    expect(keys).toContainEqual(['enrichment-proposals', BOOK]);
    expect(result.current.enriching).toBe(false);
  });

  it('autoEnrich on throw: toasts the error, returns null, does NOT invalidate', async () => {
    autoEnrichMock.mockRejectedValue(new Error('enrich boom'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useGaps(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.autoEnrich(ENRICH_BODY);
    });

    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('enrich boom');
    expect(toastMocks.success).not.toHaveBeenCalled();
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).not.toContainEqual(['enrichment-jobs', BOOK]);
    expect(keys).not.toContainEqual(['enrichment-proposals', BOOK]);
    expect(result.current.enriching).toBe(false);
  });
});
