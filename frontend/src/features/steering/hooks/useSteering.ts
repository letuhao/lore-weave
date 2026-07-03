// MVC controller for the steering panel (react-query). Owns the list query + the
// create/update/delete mutations; invalidates the list on success so the view stays
// in lockstep with the server (SSOT = book-service). No JSX.
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { steeringApi } from '../api';
import type { SteeringEntry, SteeringInput } from '../types';
import { STEERING_LIMITS } from '../types';

/** A thrown apiJson error carries `.status`/`.code`. */
type ApiErr = Error & { status?: number; code?: string };

export type SteeringErrorKind = 'duplicate' | 'cap' | 'forbidden' | 'other' | null;

/** Map a mutation error to a UI-actionable kind: 409 → duplicate name, 422 →
 * cap/enum, 403 → no-permission (a VIEW-only collaborator: writes are EDIT-gated,
 * so a permission denial must NOT read as a transient "try again"). review-impl M1. */
export function classifySteeringError(err: unknown): SteeringErrorKind {
  if (!err) return null;
  const status = (err as ApiErr).status;
  if (status === 409) return 'duplicate';
  if (status === 422) return 'cap';
  if (status === 403) return 'forbidden';
  return 'other';
}

export function useSteering(bookId: string | null) {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';
  const qc = useQueryClient();
  const enabled = !!accessToken && !!bookId;
  const key = ['steering', userId, bookId] as const;

  const query = useQuery({
    queryKey: key,
    queryFn: () => steeringApi.list(accessToken!, bookId!),
    enabled,
    staleTime: 30_000,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: key });

  const createMutation = useMutation({
    mutationFn: (payload: SteeringInput) => steeringApi.create(accessToken!, bookId!, payload),
    onSuccess: invalidate,
  });

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; payload: SteeringInput }) =>
      steeringApi.update(accessToken!, bookId!, vars.id, vars.payload),
    onSuccess: invalidate,
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => steeringApi.remove(accessToken!, bookId!, id),
    onSuccess: invalidate,
  });

  const entries: SteeringEntry[] = query.data ?? [];

  return {
    entries,
    isLoading: query.isLoading && enabled,
    isError: query.isError,
    error: (query.error as Error | null) ?? null,
    /** True once the per-book row cap is reached — the view disables "Add". */
    atCap: entries.length >= STEERING_LIMITS.maxRows,
    createEntry: createMutation.mutateAsync,
    updateEntry: (id: string, payload: SteeringInput) => updateMutation.mutateAsync({ id, payload }),
    deleteEntry: deleteMutation.mutateAsync,
    isMutating: createMutation.isPending || updateMutation.isPending || deleteMutation.isPending,
    createError: createMutation.error,
    updateError: updateMutation.error,
  };
}
