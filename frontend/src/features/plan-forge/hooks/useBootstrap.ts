// Auto-bootstrap gate controller (M4) — owns propose/approve/reject/apply against the
// composition-service gate (docs/specs/2026-07-06-planforge-auto-bootstrap.md §6). Mirrors
// usePlanRun's shape (busy/error, explicit handlers, no useEffect-for-events): propose runs
// the diff ONCE; approve/reject/apply never call propose again.
import { useCallback, useState } from 'react';
import { planForgeApi } from '../api';
import type { BootstrapProposal } from '../types';

export interface UseBootstrap {
  proposal: BootstrapProposal | null;
  busy: boolean;
  error: string | null;
  propose: (runId: string) => Promise<void>;
  approve: () => Promise<void>;
  reject: () => Promise<void>;
  apply: () => Promise<void>;
  /** Back to "not proposed yet" — e.g. after a reject, so the writer can review a fresh
   * propose without the old (rejected) card lingering. Local UI state only. */
  reset: () => void;
}

// composition-service errors as FastAPI's default {"detail": "..."} shape, which this repo's
// shared apiJson/ApiError type ({code, message}) doesn't parse into `.message` — so `.message`
// falls back to a generic statusText ("Unprocessable Entity") for ANY composition-service
// HTTPException(detail=...) today, not just this gate's. Read the raw body's `detail` first so
// THIS panel's actionable messages (e.g. "adopt an ontology first") surface correctly; the
// shared-client fix is a separate, wider concern out of this gate's scope.
function errorMessage(e: unknown): string {
  const body = (e as { body?: { detail?: string } } | undefined)?.body;
  return body?.detail || (e as Error).message;
}

export function useBootstrap(bookId: string, token: string | null): UseBootstrap {
  const [proposal, setProposal] = useState<BootstrapProposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const propose = useCallback(async (runId: string) => {
    if (!token) return;
    setBusy(true);
    setError(null);
    try {
      const p = await planForgeApi.bootstrapPropose(bookId, runId, token);
      setProposal(p);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token]);

  const approve = useCallback(async () => {
    if (!token || !proposal) return;
    setBusy(true);
    setError(null);
    try {
      const p = await planForgeApi.bootstrapApprove(bookId, proposal.id, token);
      setProposal(p);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, proposal]);

  const reject = useCallback(async () => {
    if (!token || !proposal) return;
    setBusy(true);
    setError(null);
    try {
      const p = await planForgeApi.bootstrapReject(bookId, proposal.id, token);
      setProposal(p);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, proposal]);

  const apply = useCallback(async () => {
    if (!token || !proposal) return;
    setBusy(true);
    setError(null);
    try {
      const p = await planForgeApi.bootstrapApply(bookId, proposal.id, token);
      setProposal(p);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }, [bookId, token, proposal]);

  const reset = useCallback(() => {
    setProposal(null);
    setError(null);
  }, []);

  return { proposal, busy, error, propose, approve, reject, apply, reset };
}
