import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const approveMock = vi.fn();
const rejectMock = vi.fn();
const editMock = vi.fn();
const promoteMock = vi.fn();
const retractMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      approve: (...a: unknown[]) => approveMock(...a),
      reject: (...a: unknown[]) => rejectMock(...a),
      edit: (...a: unknown[]) => editMock(...a),
      promote: (...a: unknown[]) => promoteMock(...a),
      retract: (...a: unknown[]) => retractMock(...a),
    },
  };
});

import { useProposalActions } from '../useProposalActions';
import type { Proposal } from '../../types';

const BOOK = 'book-1';
const P = (over: Partial<Proposal> = {}): Proposal =>
  ({
    proposal_id: 'p-1',
    project_id: 'proj-9',
    review_status: 'proposed',
    canonical_name: '玉虛宮',
    technique: 'recook',
    content: '...',
    confidence: 0.3,
    origin: 'enrichment',
    provenance_json: {},
    source_refs_json: [],
    ...over,
  } as Proposal);

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => {
  [approveMock, rejectMock, editMock, promoteMock, retractMock].forEach((m) => m.mockReset());
  Object.values(toastMocks).forEach((m) => m.mockReset());
});

describe('useProposalActions', () => {
  it('approve calls the API with the proposal project_id, toasts, invalidates the list', async () => {
    approveMock.mockResolvedValue(P({ review_status: 'approved' }));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.approve(P());
    });
    expect(approveMock).toHaveBeenCalledWith('p-1', 'proj-9', 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('actions.approved');
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).toContainEqual([
      'enrichment-proposals',
      BOOK,
    ]);
  });

  it('reject forwards the reason argument', async () => {
    rejectMock.mockResolvedValue(P({ review_status: 'rejected' }));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.reject(P(), 'not in canon');
    });
    expect(rejectMock).toHaveBeenCalledWith('p-1', 'proj-9', 'not in canon', 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('actions.rejected');
  });

  it('reject with no reason passes undefined', async () => {
    rejectMock.mockResolvedValue(P());
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.reject(P());
    });
    expect(rejectMock).toHaveBeenCalledWith('p-1', 'proj-9', undefined, 'tok');
  });

  it('edit calls the API with the content and toasts', async () => {
    editMock.mockResolvedValue(P());
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.edit(P(), 'new text');
    });
    expect(editMock).toHaveBeenCalledWith('p-1', 'proj-9', 'new text', 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('actions.edited');
  });

  it('promote on an APPROVED proposal promotes directly (no prior approve)', async () => {
    promoteMock.mockResolvedValue({ review_status: 'promoted' });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.promote(P({ review_status: 'approved' }));
    });
    expect(approveMock).not.toHaveBeenCalled();
    expect(promoteMock).toHaveBeenCalledWith('p-1', 'proj-9', BOOK, 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('actions.promoted');
  });

  it('promote on a PROPOSED proposal approves first, then promotes with the book anchor', async () => {
    approveMock.mockResolvedValue(P({ review_status: 'approved' }));
    promoteMock.mockResolvedValue({ review_status: 'promoted' });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.promote(P({ review_status: 'proposed' }));
    });
    expect(approveMock).toHaveBeenCalledWith('p-1', 'proj-9', 'tok');
    expect(promoteMock).toHaveBeenCalledWith('p-1', 'proj-9', BOOK, 'tok');
    expect(approveMock.mock.invocationCallOrder[0]).toBeLessThan(
      promoteMock.mock.invocationCallOrder[0],
    );
  });

  it('retract calls the API with the book anchor and toasts', async () => {
    retractMock.mockResolvedValue({});
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    await act(async () => {
      await result.current.retract(P({ review_status: 'promoted' }));
    });
    expect(retractMock).toHaveBeenCalledWith('p-1', 'proj-9', BOOK, 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('actions.retracted');
  });

  it('on API error: toasts the error, returns null, does NOT invalidate', async () => {
    approveMock.mockRejectedValue(new Error('boom'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useProposalActions(BOOK), { wrapper: Wrapper });
    let out: unknown;
    await act(async () => {
      out = await result.current.approve(P());
    });
    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('boom');
    expect(invalidateSpy.mock.calls.map((c) => c[0]?.queryKey)).not.toContainEqual([
      'enrichment-proposals',
      BOOK,
    ]);
  });
});
