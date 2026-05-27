import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { PendingFact } from '../types';

// K21-C (D8 / K21.7 sf4): the pending-facts review hook.
//
// When a project has `memory_remember_confirm` on, a `memory_remember`
// tool call queues a fact instead of writing it (knowledge-service
// design D6). The FE discovers those queued facts by polling
// `GET /v1/knowledge/pending-facts?session_id=` — NOT from the SSE
// stream (design D9) — so the confirmation flow is decoupled from the
// one-shot turn stream.
//
// This hook owns the query + the confirm/reject mutations. A
// confirm/reject mutation refetches the list on success so the card
// drops the resolved row. `refetch` is also exposed so ChatView can
// poll on chat-stream end (a turn may have just queued a fact).
//
// The hook is self-contained per CLAUDE.md MVC rules — it manages its
// own query state and cleanup; the consumer just renders the list and
// calls the actions.

export interface UsePendingFactsResult {
  /** Queued facts for this session, oldest-first. Empty when none. */
  pendingFacts: PendingFact[];
  isLoading: boolean;
  error: Error | null;
  /** Re-fetch the list. Wired to chat-stream end in ChatView. */
  refetch: () => void;
  /** Write the queued fact to the graph, then refetch. */
  confirm: (pendingFactId: string) => Promise<void>;
  /** Drop the queued fact, then refetch. */
  reject: (pendingFactId: string) => Promise<void>;
  /** True while a confirm or reject is in flight. */
  isMutating: boolean;
}

export function usePendingFacts(sessionId: string | null): UsePendingFactsResult {
  const { accessToken } = useAuth();

  const query = useQuery({
    queryKey: ['chat-pending-facts', sessionId] as const,
    queryFn: () => chatApi.listPendingFacts(accessToken!, sessionId!),
    // No session or no token → nothing to fetch. The card renders
    // nothing on an empty list, so a disabled query is a clean no-op.
    enabled: !!accessToken && !!sessionId,
  });

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const confirmMutation = useMutation({
    mutationFn: (pendingFactId: string) =>
      chatApi.confirmPendingFact(accessToken!, pendingFactId),
    // A resolved fact must leave the list — refetch rather than
    // optimistic-remove so the card stays in sync with the BE (a
    // concurrent confirm/reject on another device is reflected too).
    onSuccess: () => {
      void query.refetch();
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (pendingFactId: string) =>
      chatApi.rejectPendingFact(accessToken!, pendingFactId),
    onSuccess: () => {
      void query.refetch();
    },
  });

  const confirm = useCallback(
    async (pendingFactId: string) => {
      await confirmMutation.mutateAsync(pendingFactId);
    },
    [confirmMutation],
  );

  const reject = useCallback(
    async (pendingFactId: string) => {
      await rejectMutation.mutateAsync(pendingFactId);
    },
    [rejectMutation],
  );

  return {
    pendingFacts: query.data ?? [],
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
    refetch,
    confirm,
    reject,
    isMutating: confirmMutation.isPending || rejectMutation.isPending,
  };
}
