// S-05 Part B — controller hook for the KG triage queue panel. Drives the
// COMPLETE-but-uncalled public routes (routers/public/triage.py): listTriage
// (grouped by signature), resolveTriage (batch over a signature), and dismiss
// (as a `dismiss` resolve action — the grouped view has no per-item triage_id,
// so a group is dismissed by resolving the signature with action='dismiss').
//
// Read key `['kg-triage', userId, projectId]` is in knowledgeEffects.ts's
// invalidation list, so an AGENT resolving a triage item refreshes THIS panel
// (the spec's Lane-B "triageEffects" — folded into the one /^kg_/ handler, never
// a second one, per the no-double-fire rule).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { ontologyApi } from '../api/ontology';
import type {
  TriageAction,
  TriageGroup,
  TriageItem,
  TriageResolveResult,
} from '../types/ontology';

export interface UseTriageQueueResult {
  groups: TriageGroup[];
  isLoading: boolean;
  error: Error | null;
  resolve: (args: {
    signature: string;
    action: TriageAction;
    params?: Record<string, unknown>;
  }) => Promise<TriageResolveResult>;
  isResolving: boolean;
  /** S-05 — dismiss ONE item of a signature (kills the whole-group blast). */
  dismissItem: (triageId: string) => Promise<void>;
  isDismissing: boolean;
}

export function useTriageQueue(projectId: string | null): UseTriageQueueResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const queryClient = useQueryClient();
  const queryKey = ['kg-triage', userId, projectId] as const;

  const query = useQuery({
    queryKey,
    queryFn: () =>
      ontologyApi.listTriage(projectId!, { status: 'pending' }, accessToken!),
    enabled: !!accessToken && !!projectId,
    staleTime: 10_000,
  });

  const resolveMutation = useMutation({
    mutationFn: ({
      signature,
      action,
      params,
    }: {
      signature: string;
      action: TriageAction;
      params?: Record<string, unknown>;
    }) =>
      ontologyApi.resolveTriage(
        projectId!,
        signature,
        { action, params: params ?? {} },
        accessToken!,
      ),
    onSuccess: () => queryClient.invalidateQueries({ queryKey }),
  });

  const dismissMutation = useMutation({
    mutationFn: (triageId: string) =>
      ontologyApi.dismissTriageItem(projectId!, triageId, accessToken!),
    onSuccess: () => {
      // refetch the groups (a count may drop / a group may vanish) AND any open
      // per-signature item drill-in.
      queryClient.invalidateQueries({ queryKey });
      queryClient.invalidateQueries({ queryKey: ['kg-triage-items', userId, projectId] });
    },
  });

  return {
    groups: query.data?.groups ?? [],
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
    resolve: resolveMutation.mutateAsync,
    isResolving: resolveMutation.isPending,
    dismissItem: dismissMutation.mutateAsync,
    isDismissing: dismissMutation.isPending,
  };
}

/** S-05 — lazy per-signature item drill-in (loads only when a group is expanded). */
export function useTriageItems(
  projectId: string | null,
  signature: string | null,
  enabled: boolean,
): { items: TriageItem[]; isLoading: boolean } {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const query = useQuery({
    queryKey: ['kg-triage-items', userId, projectId, signature] as const,
    queryFn: () => ontologyApi.listTriageItems(projectId!, signature!, accessToken!),
    enabled: !!accessToken && !!projectId && !!signature && enabled,
    staleTime: 10_000,
  });
  return { items: query.data?.items ?? [], isLoading: query.isLoading };
}
