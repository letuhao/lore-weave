import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { PropsWithChildren } from 'react';

// The correction flywheel's FELT signal (S1 blackbox D-S1-FLYWHEEL-INVISIBLE): a genuine
// dissatisfaction capture (reject/regenerate/edit/pick_different) posts the correction AND now
// acknowledges it with one subtle toast, so the author knows their edits teach the co-writer.
const toastSuccess = vi.fn();
vi.mock('sonner', () => ({ toast: { success: (m: string) => toastSuccess(m) } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: { defaultValue?: string }) => o?.defaultValue ?? k }),
}));
const submitCorrection = vi.fn();
vi.mock('../../api', () => ({ compositionApi: { submitCorrection: (...a: unknown[]) => submitCorrection(...a) } }));

import { useCorrection } from '../useAutoGenerate';

function wrapper({ children }: PropsWithChildren) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false }, queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  toastSuccess.mockReset();
  submitCorrection.mockReset();
});

describe('useCorrection — flywheel felt-signal', () => {
  it('posts the correction AND fires one acknowledgement toast on success', async () => {
    submitCorrection.mockResolvedValue({});
    const { result } = renderHook(() => useCorrection('tok'), { wrapper });
    result.current.mutate({ jobId: 'job-1', body: { kind: 'reject' } });
    await waitFor(() => expect(submitCorrection).toHaveBeenCalledWith('job-1', { kind: 'reject' }, 'tok'));
    await waitFor(() => expect(toastSuccess).toHaveBeenCalledTimes(1));
  });

  it('does NOT toast when the correction POST fails (no false "learned" signal)', async () => {
    submitCorrection.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useCorrection('tok'), { wrapper });
    result.current.mutate({ jobId: 'job-2', body: { kind: 'regenerate' } });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(toastSuccess).not.toHaveBeenCalled();
  });
});
