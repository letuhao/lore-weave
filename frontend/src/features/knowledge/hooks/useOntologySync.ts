import { useCallback, useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type {
  SyncChange,
  SyncChoice,
  SyncDecision,
} from '../types/ontology';

// ─────────────────────────────────────────────────────────────────────────────
// useOntologySync — controller for the tree-granular sync flow.
//
// Reads /sync/available (per-node added/modified/removed_upstream diff), holds
// the user's per-node keep_mine/take_theirs decisions, and POSTs /sync/apply
// with the optimistic-concurrency `base_source_hash`. The SyncDiff view renders
// off `changes` + `decisions`; it calls `setDecision` / `keepAllMine` /
// `takeAllTheirs` (explicit handlers, no useEffect) then `apply`.
//
// Decision key = `${node_type}:${parent_code ?? ''}:${code}` so a vocab_value
// keyed under its set never collides with an edge_type of the same code.
// `removed_upstream` changes don't apply a remote value — keep_mine (the
// default) preserves boundary independence; take_theirs there is a no-op the BE
// ignores, so we only send decisions the user explicitly set.
// ─────────────────────────────────────────────────────────────────────────────

export function changeKey(c: Pick<SyncChange, 'node_type' | 'parent_code' | 'code'>): string {
  return `${c.node_type}:${c.parent_code ?? ''}:${c.code}`;
}

export function useOntologySync(projectId: string) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  // key → choice. Absent key = undecided (UI defaults to keep_mine until set).
  const [decisions, setDecisions] = useState<Record<string, SyncChoice>>({});

  const query = useQuery({
    queryKey: ['kg-sync-available', projectId],
    queryFn: () => ontologyApi.syncAvailable(projectId, accessToken!),
    enabled: !!accessToken && !!projectId,
  });

  const diff = query.data ?? null;
  const changes = useMemo<SyncChange[]>(() => diff?.changes ?? [], [diff]);

  const setDecision = useCallback(
    (change: SyncChange, choice: SyncChoice) => {
      setDecisions((prev) => ({ ...prev, [changeKey(change)]: choice }));
    },
    [],
  );

  const setAll = useCallback(
    (choice: SyncChoice) => {
      setDecisions(() => {
        const next: Record<string, SyncChoice> = {};
        for (const c of changes) next[changeKey(c)] = choice;
        return next;
      });
    },
    [changes],
  );

  const keepAllMine = useCallback(() => setAll('keep_mine'), [setAll]);
  const takeAllTheirs = useCallback(() => setAll('take_theirs'), [setAll]);

  const getChoice = useCallback(
    (change: SyncChange): SyncChoice => decisions[changeKey(change)] ?? 'keep_mine',
    [decisions],
  );

  // Only the user's explicit take_theirs decisions carry weight; keep_mine is the
  // no-op default. We still pass keep_mine entries the user set so the apply is
  // an exact record of intent.
  const pendingDecisions = useMemo<SyncDecision[]>(
    () =>
      changes
        .filter((c) => decisions[changeKey(c)] !== undefined)
        .map((c) => ({
          node_type: c.node_type,
          parent_code: c.parent_code ?? null,
          code: c.code,
          choice: decisions[changeKey(c)],
        })),
    [changes, decisions],
  );

  const applyMutation = useMutation({
    mutationFn: () => {
      // base_source_hash is the optimistic-concurrency token from /available.
      // Empty string falls back gracefully if upstream omitted it.
      const base = diff?.source_hash_current ?? '';
      return ontologyApi.syncApply(
        projectId,
        { base_source_hash: base, decisions: pendingDecisions },
        accessToken!,
      );
    },
    onSuccess: () => {
      setDecisions({});
      queryClient.invalidateQueries({
        queryKey: ['kg-sync-available', projectId],
      });
      queryClient.invalidateQueries({ queryKey: ['kg-graph-schemas'] });
      queryClient.invalidateQueries({
        queryKey: ['kg-resolved-schema', projectId],
      });
    },
  });

  const decidedCount = pendingDecisions.length;

  return {
    diff,
    changes,
    hasUpdates: diff?.has_updates ?? false,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    // per-node decision state
    getChoice,
    setDecision,
    keepAllMine,
    takeAllTheirs,
    decisions,
    decidedCount,
    pendingDecisions,
    // apply
    apply: applyMutation.mutateAsync,
    isApplying: applyMutation.isPending,
    applyError: applyMutation.error,
    applyResult: applyMutation.data ?? null,
  };
}
