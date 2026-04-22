import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const regenerateGlobalBioMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      regenerateGlobalBio: (...args: unknown[]) =>
        regenerateGlobalBioMock(...args),
    },
  };
});

import { useRegenerateBio } from '../useRegenerateBio';

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const invalidateSpy = vi.spyOn(qc, 'invalidateQueries');
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return { Wrapper, invalidateSpy };
}

describe('useRegenerateBio', () => {
  beforeEach(() => {
    regenerateGlobalBioMock.mockReset();
    useAuthMock.mockReset();
    useAuthMock.mockReturnValue({
      accessToken: 'tok-test',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
  });

  it('invalidates summaries + versions on success and calls onSuccess', async () => {
    regenerateGlobalBioMock.mockResolvedValue({
      status: 'regenerated',
      summary: {
        summary_id: 's1',
        user_id: 'u1',
        scope_type: 'global',
        scope_id: null,
        content: 'new bio',
        token_count: 10,
        version: 2,
        created_at: '2026-04-22T00:00:00Z',
        updated_at: '2026-04-22T00:00:00Z',
      },
      skipped_reason: null,
    });
    const onSuccess = vi.fn();
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBio({ onSuccess }), {
      wrapper: Wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        model_source: 'user_model',
        model_ref: 'gpt-4o-mini',
      });
    });

    expect(regenerateGlobalBioMock).toHaveBeenCalledWith(
      { model_source: 'user_model', model_ref: 'gpt-4o-mini' },
      'tok-test',
    );
    expect(onSuccess).toHaveBeenCalledTimes(1);
    // Prefix-match invalidation on both keys.
    const invalidatedKeys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(invalidatedKeys).toContainEqual(['knowledge-summaries']);
    expect(invalidatedKeys).toContainEqual([
      'knowledge-summary-versions',
      'global',
    ]);
  });

  it('parses 409 user_edit_lock into errorCode for onError', async () => {
    const boom = Object.assign(new Error('recent edit'), {
      status: 409,
      body: {
        detail: { error_code: 'user_edit_lock', message: 'recent manual edit' },
      },
    });
    regenerateGlobalBioMock.mockRejectedValue(boom);
    const onError = vi.fn();
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBio({ onError }), {
      wrapper: Wrapper,
    });

    await expect(
      result.current.mutateAsync({
        model_source: 'user_model',
        model_ref: 'gpt-4o-mini',
      }),
    ).rejects.toMatchObject({
      errorCode: 'user_edit_lock',
      detailMessage: 'recent manual edit',
      status: 409,
    });
    expect(onError).toHaveBeenCalledTimes(1);
  });

  it('maps 422 regen_guardrail_failed onto errorCode', async () => {
    const boom = Object.assign(new Error('guardrail'), {
      status: 422,
      body: {
        detail: { error_code: 'regen_guardrail_failed', message: 'empty output' },
      },
    });
    regenerateGlobalBioMock.mockRejectedValue(boom);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBio(), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.mutateAsync({
        model_source: 'user_model',
        model_ref: 'gpt-4o-mini',
      }),
    ).rejects.toMatchObject({ errorCode: 'regen_guardrail_failed' });
  });

  it('falls back to unknown errorCode when body is missing detail', async () => {
    regenerateGlobalBioMock.mockRejectedValue(new Error('network boom'));
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBio(), {
      wrapper: Wrapper,
    });
    await expect(
      result.current.mutateAsync({
        model_source: 'user_model',
        model_ref: 'gpt-4o-mini',
      }),
    ).rejects.toMatchObject({ errorCode: 'unknown' });
  });

  it('returns 200 no_op_similarity payload without error', async () => {
    regenerateGlobalBioMock.mockResolvedValue({
      status: 'no_op_similarity',
      summary: null,
      skipped_reason: 'content identical',
    });
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBio(), {
      wrapper: Wrapper,
    });
    const resp = await result.current.mutateAsync({
      model_source: 'user_model',
      model_ref: 'gpt-4o-mini',
    });
    expect(resp.status).toBe('no_op_similarity');
  });
});
