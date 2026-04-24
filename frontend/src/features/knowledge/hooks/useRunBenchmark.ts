import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '../api';
import type { BenchmarkRunResponse } from '../types';

// C12b-b — mutation hook for the Run-benchmark button inside
// EmbeddingModelPicker (which composes into BuildGraphDialog,
// ChangeModelDialog, and ProjectFormModal). Consumes the C12b-a BE
// endpoint POST /v1/knowledge/projects/{id}/benchmark-run.
//
// On success: prefix-invalidate ['knowledge', 'benchmark-status',
// projectId] so the badge renders the fresh pass/fail across ALL
// model scopes for this project. The picker's queryKey shape is
// ['knowledge', 'benchmark-status', projectId, value] — a prefix
// invalidate covers every model the user might have tabbed through.
//
// Error shape from the public edge (C12b-a):
//   404 (missing / cross-user, no error_code — just status)
//   409 `no_embedding_model`        — project has no embedding_model set
//   409 `unknown_embedding_model`   — model not in EMBEDDING_MODEL_TO_DIM
//                                     OR dim not in SUPPORTED_PASSAGE_DIMS
//   409 `not_benchmark_project`     — project has real chapter/chat/glossary
//                                     passages; dedicated project required
//   409 `benchmark_already_running` — sentinel held for this (user, project)
//   502 `embedding_provider_flake`  — fixture load incomplete (partial
//                                     embed); BE refuses to persist
//
// /review-impl LOW #4 — unmount during in-flight mutation: the BE
// synchronous runtime is 15-60s. If the hosting dialog closes before
// the mutation settles (user clicks Cancel on BuildGraphDialog while
// the benchmark is running), the component unmounts and the
// `onSuccess` / `onError` callbacks never fire — react-query cleans
// up the per-instance listeners on the `useMutation` hook. The BE
// request itself completes and the row persists to
// `project_embedding_benchmark_runs`; `queryClient.invalidateQueries`
// still runs because the queryClient outlives the component. Next
// time the user opens any dialog with the picker, the fresh badge
// appears — they just don't get a toast confirmation for the
// closed-dialog run. Matches useRegenerateBio's pattern. Fixing
// would require a global mutation-observer via
// `queryClient.getMutationCache()`, which is overkill for this UX.

const BENCHMARK_STATUS_PREFIX = ['knowledge', 'benchmark-status'] as const;

export type RunBenchmarkErrorCode =
  | 'no_embedding_model'
  | 'unknown_embedding_model'
  | 'not_benchmark_project'
  | 'benchmark_already_running'
  | 'embedding_provider_flake'
  | 'unknown';

export interface RunBenchmarkError extends Error {
  status?: number;
  errorCode: RunBenchmarkErrorCode;
  /** Server-supplied human-readable message if present. */
  detailMessage?: string;
}

/** Extract `{error_code, message}` from FastAPI's `detail: {...}`
 *  envelope, falling back to {unknown, raw message} for anything
 *  unexpected (network error, 404, malformed body). Centralised so
 *  the component's `switch` stays on a closed set of codes. */
function parseRunBenchmarkError(err: unknown): RunBenchmarkError {
  const e = err as {
    message?: string;
    status?: number;
    body?: { detail?: { error_code?: string; message?: string } };
  };
  const detail = e.body?.detail;
  const code = (detail?.error_code ?? 'unknown') as RunBenchmarkErrorCode;
  const out: RunBenchmarkError = Object.assign(
    new Error(e.message || 'benchmark run failed'),
    {
      status: e.status,
      errorCode: code,
      detailMessage: detail?.message,
    },
  );
  return out;
}

export interface UseRunBenchmarkOptions {
  onSuccess?: (resp: BenchmarkRunResponse) => void;
  onError?: (err: RunBenchmarkError) => void;
}

export interface RunBenchmarkInput {
  /** Defaults to BE's `runs=3` when omitted. Caller pins at 3 today
   *  (CLI + L-CH-09 methodology); BE validates 1..5. */
  runs?: number;
}

/**
 * Hook wiring POST /benchmark-run for a specific project.
 *
 * `projectId === undefined` makes the mutation throw on first call —
 * this mirrors the callsite guard in `EmbeddingModelPicker` where the
 * Run button only renders when `projectId && value` are both set.
 * A defensive throw keeps the hook honest against a future caller
 * that forgets the guard.
 */
export function useRunBenchmark(
  projectId: string | undefined,
  opts: UseRunBenchmarkOptions = {},
) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<BenchmarkRunResponse, RunBenchmarkError, RunBenchmarkInput | void>({
    mutationFn: async (input) => {
      if (!accessToken || !projectId) {
        throw parseRunBenchmarkError(
          new Error('not authenticated or missing project'),
        );
      }
      try {
        return await knowledgeApi.runBenchmark(
          projectId,
          input?.runs,
          accessToken,
        );
      } catch (err) {
        throw parseRunBenchmarkError(err);
      }
    },
    onSuccess: async (resp) => {
      if (projectId) {
        // Prefix-match: invalidates every ['knowledge',
        // 'benchmark-status', projectId, <model>] variant so the
        // badge flips to the new state regardless of which model
        // the user had the picker focused on at POST time.
        await queryClient.invalidateQueries({
          queryKey: [...BENCHMARK_STATUS_PREFIX, projectId],
        });
      }
      opts.onSuccess?.(resp);
    },
    onError: (err) => {
      opts.onError?.(err);
    },
  });
}
