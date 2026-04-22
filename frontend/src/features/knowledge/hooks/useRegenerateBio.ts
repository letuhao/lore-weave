import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import {
  knowledgeApi,
  type RegenerateRequest,
  type RegenerateResponse,
} from '../api';

// useSummaries + useGlobalSummaryVersions keys, mirrored here so
// invalidation doesn't drift if they rename theirs.
const SUMMARIES_KEY = ['knowledge-summaries'] as const;
const VERSIONS_KEY = ['knowledge-summary-versions', 'global'] as const;

// K20α — mutation hook for the Global-tab Regenerate button.
// Consumes POST /v1/knowledge/me/summary/regenerate (L0 scope; project
// scope has its own endpoint which lands when the Project Memory tab
// grows a Regenerate button — not today).
//
// Error shape from the public edge:
//   409 `user_edit_lock`       → recent manual edit protected (≤30d).
//   409 `regen_concurrent_edit` → manual edit raced the regen mid-flight.
//   422 `regen_guardrail_failed` → LLM output failed quality gate.
//   502 `provider_error`        → user's BYOK provider errored out.
//
// On success (any of `regenerated` / `no_op_similarity` /
// `no_op_empty_source`) we invalidate the summaries list + versions
// list so GlobalBioTab's current content and VersionsPanel both
// refresh from the server.

export type RegenerateErrorCode =
  | 'user_edit_lock'
  | 'regen_concurrent_edit'
  | 'regen_guardrail_failed'
  | 'provider_error'
  | 'unknown';

export interface RegenerateError extends Error {
  status?: number;
  errorCode: RegenerateErrorCode;
  /** Server-supplied human-readable message if present. */
  detailMessage?: string;
}

/** Extract `{error_code, message}` from FastAPI's `detail: {...}`
 *  envelope, falling back to {unknown, raw message} for anything
 *  unexpected. Keeping this centralised means dialog-level `switch`
 *  statements stay on a closed set of codes. */
function parseRegenerateError(err: unknown): RegenerateError {
  const e = err as {
    message?: string;
    status?: number;
    body?: { detail?: { error_code?: string; message?: string } };
  };
  const detail = e.body?.detail;
  const code = (detail?.error_code ?? 'unknown') as RegenerateErrorCode;
  const out: RegenerateError = Object.assign(new Error(e.message || 'regen failed'), {
    status: e.status,
    errorCode: code,
    detailMessage: detail?.message,
  });
  return out;
}

export interface UseRegenerateBioOptions {
  onSuccess?: (resp: RegenerateResponse) => void;
  onError?: (err: RegenerateError) => void;
}

export function useRegenerateBio(opts: UseRegenerateBioOptions = {}) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  return useMutation<RegenerateResponse, RegenerateError, RegenerateRequest>({
    mutationFn: async (body: RegenerateRequest) => {
      if (!accessToken) {
        throw parseRegenerateError(new Error('not authenticated'));
      }
      try {
        return await knowledgeApi.regenerateGlobalBio(body, accessToken);
      } catch (err) {
        throw parseRegenerateError(err);
      }
    },
    onSuccess: async (resp) => {
      // Both the GET /summaries list (useSummaries) and the GET
      // /summaries/global/versions list (useGlobalSummaryVersions)
      // reflect the regen write. Keys are mirrored from the owning
      // hooks — if either renames their queryKey the mirror here
      // needs the same rename (TS won't catch it).
      await queryClient.invalidateQueries({ queryKey: SUMMARIES_KEY });
      await queryClient.invalidateQueries({ queryKey: VERSIONS_KEY });
      opts.onSuccess?.(resp);
    },
    onError: (err) => {
      opts.onError?.(err);
    },
  });
}
