import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => useAuthMock() }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string) => k }),
}));

// vi.hoisted — the mock factory is hoisted, so a plain top-level `toast` const
// would be in the TDZ when `vi.mock('sonner', () => ({ toast }))` evaluates it.
const toast = vi.hoisted(() => ({ success: vi.fn(), warning: vi.fn(), info: vi.fn(), error: vi.fn() }));
vi.mock('sonner', () => ({ toast }));

const getJob = vi.fn();
const generateStubs = vi.fn();
const resumeJob = vi.fn();
const cancelJob = vi.fn();
vi.mock('../../api', () => ({
  wikiApi: {
    getJob: (...a: unknown[]) => getJob(...a),
    generateStubs: (...a: unknown[]) => generateStubs(...a),
    resumeJob: (...a: unknown[]) => resumeJob(...a),
    cancelJob: (...a: unknown[]) => cancelJob(...a),
  },
}));

import { useWikiGenJob } from '../useWikiGenJob';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuthMock.mockReturnValue({ accessToken: 'tok' });
});

describe('useWikiGenJob', () => {
  it('treats a 404 from getJob as "no job" (null, no throw)', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await waitFor(() => expect(getJob).toHaveBeenCalled());
    await waitFor(() => expect(result.current.job).toBeNull());
    expect(result.current.isActive).toBe(false);
  });

  it('exposes a running job as active', async () => {
    getJob.mockResolvedValue({ job_id: 'j1', status: 'running', items_total: 3, items_processed: 1, entity_count: 3 });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.isActive).toBe(true));
    expect(result.current.job?.status).toBe('running');
  });

  it('trigger with a model posts the delegate payload and toasts started', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    generateStubs.mockResolvedValue({ job_id: 'j9', status: 'pending' });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await act(async () => {
      await result.current.trigger({ model_ref: 'm1', max_spend_usd: 1.5, kind_codes: ['character'] });
    });
    expect(generateStubs).toHaveBeenCalledWith(
      'b1',
      { kind_codes: ['character'], model_ref: 'm1', model_source: 'user_model', max_spend_usd: 1.5 },
      'tok',
    );
    expect(toast.success).toHaveBeenCalledWith('gen.started');
  });

  it('warns startedTruncated when the genLimit dropped candidates (D-WIKI-M7B-GEN-LIMIT)', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    generateStubs.mockResolvedValue({ job_id: 'j1', status: 'pending', total_matched: 87, selected: 50 });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await act(async () => {
      await result.current.trigger({ model_ref: 'm1', kind_codes: ['character'] });
    });
    expect(toast.warning).toHaveBeenCalledWith('gen.startedTruncated');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('shows plain started (not truncated) when total_matched == selected', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    generateStubs.mockResolvedValue({ job_id: 'j2', status: 'pending', total_matched: 50, selected: 50 });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await act(async () => {
      await result.current.trigger({ model_ref: 'm1', kind_codes: ['character'] });
    });
    expect(toast.success).toHaveBeenCalledWith('gen.started');
    expect(toast.warning).not.toHaveBeenCalled();
  });

  it('trigger without a model runs deterministic stubs and invalidates the list', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    generateStubs.mockResolvedValue({ created: 2, articles: [] });
    const { Wrapper, invalidateSpy } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await act(async () => {
      await result.current.trigger({});
    });
    // no model fields in the payload
    expect(generateStubs).toHaveBeenCalledWith('b1', {}, 'tok');
    expect(toast.success).toHaveBeenCalledWith('generatedCount');
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['wiki-articles', 'b1'] });
  });

  it('surfaces a 409 active-job as an info toast (not a failure)', async () => {
    getJob.mockRejectedValue(Object.assign(new Error('no_job'), { status: 404 }));
    generateStubs.mockRejectedValue(Object.assign(new Error('active'), { status: 409 }));
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await act(async () => {
      await expect(result.current.trigger({ model_ref: 'm1' })).rejects.toBeTruthy();
    });
    expect(toast.info).toHaveBeenCalledWith('gen.alreadyRunning');
    expect(toast.error).not.toHaveBeenCalled();
  });

  it('resume and cancel call their endpoints for the current job', async () => {
    getJob.mockResolvedValue({ job_id: 'jX', status: 'paused', items_total: 3, items_processed: 1, entity_count: 3 });
    resumeJob.mockResolvedValue({ job_id: 'jX', status: 'pending' });
    cancelJob.mockResolvedValue({ job_id: 'jX', status: 'cancelled' });
    const { Wrapper } = wrapper();
    const { result } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await waitFor(() => expect(result.current.job?.job_id).toBe('jX'));
    await act(async () => { await result.current.resume(); });
    expect(resumeJob).toHaveBeenCalledWith('b1', 'jX', 'tok');
    await act(async () => { await result.current.cancel(); });
    expect(cancelJob).toHaveBeenCalledWith('b1', 'jX', 'tok');
  });

  it('invalidates the article list exactly once when a job completes (ref guard)', async () => {
    getJob.mockResolvedValue({ job_id: 'jDone', status: 'complete', items_total: 2, items_processed: 2, entity_count: 2 });
    const { Wrapper, invalidateSpy } = wrapper();
    const { rerender } = renderHook(() => useWikiGenJob('b1'), { wrapper: Wrapper });
    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['wiki-articles', 'b1'] }),
    );
    const callsForArticles = () =>
      invalidateSpy.mock.calls.filter(
        ([arg]) => JSON.stringify((arg as { queryKey?: unknown[] })?.queryKey) === JSON.stringify(['wiki-articles', 'b1']),
      ).length;
    const after = callsForArticles();
    // a re-render on the SAME completed job must not re-invalidate (the ref guard)
    rerender();
    rerender();
    expect(callsForArticles()).toBe(after);
  });
});
