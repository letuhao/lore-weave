import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));

const toastMocks = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn() }));
vi.mock('sonner', () => ({ toast: toastMocks }));

const composeMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return { ...actual, enrichmentApi: { compose: (...a: unknown[]) => composeMock(...a) } };
});

import { useCompose } from '../useCompose';
import type { ComposeBody, ComposeResult } from '../../types';

const BOOK = 'book-1';
const BODY: ComposeBody = {
  input_source: 'draft',
  embedding_model_ref: 'm-embed',
  generation_model_ref: 'm-gen',
  draft_text: '碧遊宮乃通天教主道場。',
  expand_mode: 'rewrite',
  target: { mode: 'existing', canonical_name: '碧遊宮', entity_kind: 'location', target_ref: '碧遊宮' },
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
  composeMock.mockReset();
  Object.values(toastMocks).forEach((m) => m.mockReset());
});

describe('useCompose', () => {
  it('starts with composing=false', () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCompose(BOOK), { wrapper: Wrapper });
    expect(result.current.composing).toBe(false);
  });

  it('compose calls api.compose(bookId, body, token), toasts success, invalidates jobs + proposals', async () => {
    const resp = {
      project_id: 'proj-9', job_id: 'job-1', input_source: 'draft',
      technique: 'compose_draft', enqueued_targets: 1, enqueued: true,
    } as ComposeResult;
    composeMock.mockResolvedValue(resp);
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCompose(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.compose(BODY);
    });

    expect(composeMock).toHaveBeenCalledWith(BOOK, BODY, 'tok');
    expect(out).toBe(resp);
    expect(toastMocks.success).toHaveBeenCalledWith('compose.enqueued');
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).toContainEqual(['enrichment-jobs', BOOK]);
    expect(keys).toContainEqual(['enrichment-proposals', BOOK]);
    expect(result.current.composing).toBe(false);
  });

  it('compose on throw: toasts the error, returns null, does NOT invalidate', async () => {
    composeMock.mockRejectedValue(new Error('compose boom'));
    const { Wrapper, invalidateSpy } = makeWrapper();
    const { result } = renderHook(() => useCompose(BOOK), { wrapper: Wrapper });

    let out: unknown;
    await act(async () => {
      out = await result.current.compose(BODY);
    });

    expect(out).toBeNull();
    expect(toastMocks.error).toHaveBeenCalledWith('compose boom');
    expect(toastMocks.success).not.toHaveBeenCalled();
    const keys = invalidateSpy.mock.calls.map((c) => c[0]?.queryKey);
    expect(keys).not.toContainEqual(['enrichment-jobs', BOOK]);
    expect(result.current.composing).toBe(false);
  });
});
