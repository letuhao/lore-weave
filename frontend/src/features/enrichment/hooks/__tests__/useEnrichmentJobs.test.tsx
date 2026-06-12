import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const listJobsMock = vi.fn();
const resumeJobMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    enrichmentApi: {
      listJobs: (...a: unknown[]) => listJobsMock(...a),
      resumeJob: (...a: unknown[]) => resumeJobMock(...a),
    },
  };
});

import { useEnrichmentJobs } from '../useEnrichmentJobs';
import type { Job } from '../../types';

const BOOK = 'book-1';

const J = (over: Partial<Job> = {}): Job =>
  ({
    job_id: 'job-1',
    project_id: 'proj-9',
    status: 'completed',
    technique: 'recook',
    entity_kind: null,
    book_id: BOOK,
    proposals_total: 0,
    estimated_cost: 0,
    actual_cost: 0,
    max_spend: null,
    error_message: null,
    created_at: '2026-01-01T00:00:00Z',
    ...over,
  } as Job);

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => {
  listJobsMock.mockReset();
  resumeJobMock.mockReset();
  Object.values(toastMocks).forEach((m) => m.mockReset());
});

describe('useEnrichmentJobs', () => {
  it('exposes items/total from the query data', async () => {
    const job = J({ status: 'completed' });
    listJobsMock.mockResolvedValue({ items: [job], total: 1, limit: 50, offset: 0 });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.total).toBe(1));
    expect(result.current.items).toEqual([job]);
    expect(listJobsMock).toHaveBeenCalledWith(BOOK, 'tok');
  });

  it('defaults items to [] and total to 0 before data resolves', () => {
    listJobsMock.mockReturnValue(new Promise(() => {})); // never resolves
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

    expect(result.current.items).toEqual([]);
    expect(result.current.total).toBe(0);
  });

  it('resume calls resumeJob(job_id, project_id, token), toasts success, invalidates jobs + proposals', async () => {
    listJobsMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    resumeJobMock.mockResolvedValue({ job_id: 'job-1', status: 'running' });
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

    await act(async () => {
      await result.current.resume(J({ job_id: 'job-1', project_id: 'proj-9' }));
    });

    expect(resumeJobMock).toHaveBeenCalledWith('job-1', 'proj-9', 'tok');
    expect(toastMocks.success).toHaveBeenCalledWith('jobs.resumed');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['enrichment-jobs', BOOK]);
    expect(keys).toContainEqual(['enrichment-proposals', BOOK]);
  });

  it('resume on API error toasts the error message and does NOT invalidate', async () => {
    listJobsMock.mockResolvedValue({ items: [], total: 0, limit: 50, offset: 0 });
    resumeJobMock.mockRejectedValue(new Error('cost cap hit'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

    await act(async () => {
      await result.current.resume(J());
    });

    expect(toastMocks.error).toHaveBeenCalledWith('cost cap hit');
    expect(toastMocks.success).not.toHaveBeenCalled();
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).not.toContainEqual(['enrichment-jobs', BOOK]);
    expect(keys).not.toContainEqual(['enrichment-proposals', BOOK]);
  });

  it('polls (refetches) while a job is active', async () => {
    vi.useFakeTimers();
    try {
      listJobsMock.mockResolvedValue({
        items: [J({ status: 'running' })],
        total: 1,
        limit: 50,
        offset: 0,
      });
      const { Wrapper } = makeWrapper();
      renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

      // initial fetch
      await vi.waitFor(() => expect(listJobsMock).toHaveBeenCalledTimes(1));

      // refetchInterval === 4000 for an active job → next poll fires
      await act(async () => {
        await vi.advanceTimersByTimeAsync(4000);
      });
      expect(listJobsMock).toHaveBeenCalledTimes(2);
    } finally {
      vi.useRealTimers();
    }
  });

  it('does NOT poll when all jobs are terminal', async () => {
    vi.useFakeTimers();
    try {
      listJobsMock.mockResolvedValue({
        items: [J({ status: 'completed' }), J({ job_id: 'job-2', status: 'failed' })],
        total: 2,
        limit: 50,
        offset: 0,
      });
      const { Wrapper } = makeWrapper();
      renderHook(() => useEnrichmentJobs(BOOK), { wrapper: Wrapper });

      await vi.waitFor(() => expect(listJobsMock).toHaveBeenCalledTimes(1));

      // refetchInterval === false for all-terminal → no further fetch
      await act(async () => {
        await vi.advanceTimersByTimeAsync(8000);
      });
      expect(listJobsMock).toHaveBeenCalledTimes(1);
    } finally {
      vi.useRealTimers();
    }
  });
});
