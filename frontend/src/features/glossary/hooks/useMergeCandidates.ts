import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { MergeCandidate, MergeResult } from '../types';

/**
 * Controller for the "Merge Candidates" inbox (glossary AI-pipeline v2, mui #1c).
 *
 * Lists coreference clusters knowledge-service's detector proposed (likely the
 * same entity under different names: 姜子牙 / 太公望 / 子牙) and owns the review
 * actions:
 *   - confirm(candidate, winnerId) → R5 merge: folds the other members into the
 *     chosen winner (destructive, journaled + reversible). Returns the merge
 *     journal ids so the caller can offer an Undo.
 *   - dismiss(candidate) → marks the cluster dismissed (a future detection pass
 *     won't re-propose the same set).
 *   - undo(journalId) → reverts a merge by replaying its journal.
 *
 * Every action invalidates the inbox query (the cluster left the proposed set)
 * and the main entity list (members were merged/soft-deleted).
 */
export function useMergeCandidates(bookId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['glossary-merge-candidates', bookId],
    queryFn: () => glossaryApi.listMergeCandidates(bookId, accessToken!),
    enabled: !!accessToken,
  });

  const candidates: MergeCandidate[] = data?.candidates ?? [];
  const total = candidates.length;

  const invalidate = () => {
    void queryClient.invalidateQueries({ queryKey: ['glossary-merge-candidates', bookId] });
    void queryClient.invalidateQueries({ queryKey: ['glossary-entities', bookId] });
  };

  /** Fold every member except `winnerId` into the winner. Returns journal ids. */
  const confirm = async (candidate: MergeCandidate, winnerId: string): Promise<string[]> => {
    const loserIds = candidate.members
      .map((m) => m.entity_id)
      .filter((id) => id !== winnerId);
    const result: MergeResult = await glossaryApi.confirmMerge(bookId, winnerId, loserIds, accessToken!);
    invalidate();
    return result.results
      .filter((r) => r.status === 'merged' && r.journal_id)
      .map((r) => r.journal_id as string);
  };

  const dismiss = async (candidate: MergeCandidate) => {
    await glossaryApi.dismissMergeCandidate(bookId, candidate.candidate_id, accessToken!);
    invalidate();
  };

  const undo = async (journalId: string) => {
    await glossaryApi.revertMerge(bookId, journalId, accessToken!);
    invalidate();
  };

  return { candidates, total, isLoading, error, refetch, confirm, dismiss, undo };
}
