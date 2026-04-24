import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

// C12b-b — tests for useRunBenchmark. Mirrors the useRegenerateBio
// error-parser + invalidation pattern. Covers the 5 typed error_codes
// from the C12b-a BE + the unknown-fallback for network/malformed
// errors.

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const runBenchmarkMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      runBenchmark: (...args: unknown[]) => runBenchmarkMock(...args),
    },
  };
});

import { useRunBenchmark } from '../useRunBenchmark';

const PROJECT_ID = '11111111-1111-1111-1111-111111111111';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

function makeSuccessResponse(overrides: Partial<Record<string, unknown>> = {}) {
  return {
    run_id: 'benchmark-20260424T120000Z',
    embedding_model: 'bge-m3',
    passed: true,
    recall_at_3: 0.82,
    mrr: 0.71,
    avg_score_positive: 0.66,
    negative_control_max_score: 0.3,
    stddev_recall: 0.02,
    stddev_mrr: 0.03,
    runs: 3,
    ...overrides,
  };
}

describe('useRunBenchmark', () => {
  beforeEach(() => {
    runBenchmarkMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: {
        user_id: 'u1',
        email: 'a@b',
        display_name: null,
        avatar_url: null,
      },
    });
  });

  it('invalidates benchmark-status prefix on success and calls onSuccess', async () => {
    runBenchmarkMock.mockResolvedValue(makeSuccessResponse());
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID, { onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({ runs: 3 });
    });

    expect(runBenchmarkMock).toHaveBeenCalledWith(PROJECT_ID, 3, 'tok-test');
    expect(onSuccess).toHaveBeenCalledTimes(1);
    const invalidatedKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    // Prefix invalidate covers every [..., projectId, <model>] variant.
    expect(invalidatedKeys).toContainEqual([
      'knowledge',
      'benchmark-status',
      PROJECT_ID,
    ]);
  });

  it('forwards undefined runs when input omitted', async () => {
    runBenchmarkMock.mockResolvedValue(makeSuccessResponse());
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID), {
      wrapper: Wrapper,
    });
    await act(async () => {
      await result.current.mutateAsync();
    });
    expect(runBenchmarkMock).toHaveBeenCalledWith(PROJECT_ID, undefined, 'tok-test');
  });

  it('passes runs=null straight through (BE will 422)', async () => {
    // /review-impl LOW #3 — TypeScript narrows the input to
    // `{ runs?: number } | void`, so a null gets here only via a
    // type-unsafe caller. Pinning the pass-through behaviour so a
    // future edit that silently coerces null → undefined doesn't
    // mask a real validation bug at the BE boundary.
    runBenchmarkMock.mockRejectedValue(
      Object.assign(new Error('invalid runs'), {
        status: 422,
        body: { detail: { error_code: 'unprocessable' } },
      }),
    );
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID), {
      wrapper: Wrapper,
    });
    // Cast: we deliberately hand in a TS-unsafe value.
    const input = { runs: null } as unknown as { runs?: number };
    await expect(result.current.mutateAsync(input)).rejects.toBeTruthy();
    expect(runBenchmarkMock).toHaveBeenCalledWith(PROJECT_ID, null, 'tok-test');
  });

  it.each([
    ['no_embedding_model', 409],
    ['unknown_embedding_model', 409],
    ['not_benchmark_project', 409],
    ['benchmark_already_running', 409],
    ['embedding_provider_flake', 502],
  ] as const)('parses %s error_code (status %i) into errorCode', async (code, status) => {
    const boom = Object.assign(new Error(code), {
      status,
      body: { detail: { error_code: code, message: 'server said' } },
    });
    runBenchmarkMock.mockRejectedValue(boom);
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useRunBenchmark(PROJECT_ID, { onError }),
      { wrapper: Wrapper },
    );

    await expect(result.current.mutateAsync({ runs: 3 })).rejects.toMatchObject({
      errorCode: code,
      detailMessage: 'server said',
      status,
    });
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('falls back to unknown errorCode when body is missing detail', async () => {
    runBenchmarkMock.mockRejectedValue(new Error('network boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID), {
      wrapper: Wrapper,
    });
    await expect(result.current.mutateAsync({ runs: 3 })).rejects.toMatchObject({
      errorCode: 'unknown',
    });
  });

  it('throws unknown error when accessToken is missing', async () => {
    useAuthMock.mockReturnValueOnce({
      accessToken: null,
      user: null,
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID), {
      wrapper: Wrapper,
    });
    await expect(result.current.mutateAsync({ runs: 3 })).rejects.toMatchObject({
      errorCode: 'unknown',
    });
    expect(runBenchmarkMock).not.toHaveBeenCalled();
  });

  it('throws unknown error when projectId is undefined', async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(undefined), {
      wrapper: Wrapper,
    });
    await expect(result.current.mutateAsync({ runs: 3 })).rejects.toMatchObject({
      errorCode: 'unknown',
    });
    expect(runBenchmarkMock).not.toHaveBeenCalled();
  });

  it('does NOT invalidate benchmark-status when mutation rejects', async () => {
    runBenchmarkMock.mockRejectedValue(
      Object.assign(new Error('nope'), {
        status: 409,
        body: { detail: { error_code: 'not_benchmark_project' } },
      }),
    );
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRunBenchmark(PROJECT_ID), {
      wrapper: Wrapper,
    });
    await expect(result.current.mutateAsync({ runs: 3 })).rejects.toBeTruthy();
    // Invalidation MUST NOT run on error — otherwise a failed run would
    // evict fresh status data from the cache and re-fetch for no gain.
    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
