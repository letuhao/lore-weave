import { useCallback } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
import type { DiaryPendingFact } from '../types';

// WS-2.5 — the diary FACT-INBOX controller.
//
// The distiller diverts each day's facts into the human-gated pending-facts inbox (WS-2.3). This hook
// owns the list + the confirm/reject actions so the user can review them. Unlike the chat memory card
// (usePendingFacts), the diary facts are SESSION-LESS, so we list without a session_id filter — the
// server returns every pending fact the caller owns, JWT-scoped.
//
// Self-contained per the MVC rule: it manages its own query state + refetch-on-mutate; the view just
// renders the list and calls confirm/reject. A confirm/reject refetches so the row drops (and a
// concurrent action on another device is reflected).

export interface UseDiaryFactInboxResult {
  facts: DiaryPendingFact[];
  isLoading: boolean;
  error: Error | null;
  refetch: () => void;
  confirm: (pendingFactId: string) => Promise<void>;
  reject: (pendingFactId: string) => Promise<void>;
  /** id currently being confirmed/rejected (for per-row disabled state), or null. */
  pendingId: string | null;
}

export function useDiaryFactInbox(): UseDiaryFactInboxResult {
  const { accessToken } = useAuth();

  const query = useQuery({
    queryKey: ['diary-fact-inbox'] as const,
    queryFn: () => assistantApi.listDiaryFacts(accessToken!),
    enabled: !!accessToken,
  });

  const refetch = useCallback(() => {
    void query.refetch();
  }, [query]);

  const confirmMutation = useMutation({
    mutationFn: (pendingFactId: string) => assistantApi.confirmDiaryFact(accessToken!, pendingFactId),
    onSuccess: () => {
      void query.refetch();
    },
  });

  const rejectMutation = useMutation({
    mutationFn: (pendingFactId: string) => assistantApi.rejectDiaryFact(accessToken!, pendingFactId),
    onSuccess: () => {
      void query.refetch();
    },
  });

  const confirm = useCallback(
    async (id: string) => {
      await confirmMutation.mutateAsync(id);
    },
    [confirmMutation],
  );

  const reject = useCallback(
    async (id: string) => {
      await rejectMutation.mutateAsync(id);
    },
    [rejectMutation],
  );

  return {
    facts: query.data ?? [],
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
    refetch,
    confirm,
    reject,
    pendingId:
      (confirmMutation.isPending ? confirmMutation.variables : null) ??
      (rejectMutation.isPending ? rejectMutation.variables : null) ??
      null,
  };
}
