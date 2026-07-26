// W0-S16 — the global mutation error handler is the safety net for every mutation
// that declares no onError of its own, and it must NOT clobber the ones that do.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MutationObserver } from '@tanstack/react-query';
import { queryClient } from '@/lib/queryClient';

const toastError = vi.fn();
vi.mock('sonner', () => ({ toast: { error: (m: string) => toastError(m) } }));

async function runFailingMutation(opts: { onError?: () => void } = {}) {
  const observer = new MutationObserver(queryClient, {
    mutationFn: async () => {
      throw Object.assign(new Error('Bad Gateway'), { body: { detail: 'the real reason' } });
    },
    ...opts,
  });
  await observer.mutate().catch(() => {});
}

describe('W0-S16 global MutationCache.onError', () => {
  beforeEach(() => toastError.mockClear());

  it('toasts the backend reason when a mutation declares NO onError (the ~44 silent ones)', async () => {
    await runFailingMutation();
    expect(toastError).toHaveBeenCalledWith('the real reason');
  });

  it('stays SILENT when a mutation owns its failure UX (slice-local onError wins)', async () => {
    const local = vi.fn();
    await runFailingMutation({ onError: local });
    expect(local).toHaveBeenCalled();
    expect(toastError).not.toHaveBeenCalled();
  });
});
