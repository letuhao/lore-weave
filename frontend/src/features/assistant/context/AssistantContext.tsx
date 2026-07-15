// WS-1.10 — the Assistant "service": shared control-plane state (provisioning + consent) across the
// home strip's views. CLAUDE.md MVC: shared state lives in context, logic in this provider's
// callbacks (no business logic in the view components that consume it).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';
import { assistantApi } from '../api';
import { useEndOfDay } from '../hooks/useEndOfDay';
import type { ProvisionStatus } from '../types';

interface AssistantState {
  loading: boolean;
  /** A hard failure (auth / network / trashed diary) — the durable core isn't ready. */
  error: string | null;
  provisioned: boolean;
  bookId: string | null;
  projectId: string | null;
  provisionStatus: ProvisionStatus | null;
  /** Work-capture consent (A2). Fail-closed: starts false; reflects the server after a toggle. */
  consentEnabled: boolean;
  consentSaving: boolean;
  setConsent: (enabled: boolean) => void;
  reprovision: () => void;
  /** End-of-day flow (distill → poll → keep). Lifted into context so its in-flight state (a
   *  running distill) SURVIVES the mobile↔desktop chrome swap — a rotate mid-distill must not
   *  reset the button to idle and invite a duplicate, costly re-enqueue (cold-review MED). */
  endOfDay: ReturnType<typeof useEndOfDay>;
}

const AssistantCtx = createContext<AssistantState | null>(null);

export function AssistantProvider({ children }: { children: ReactNode }) {
  const { accessToken } = useAuth();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [provisioned, setProvisioned] = useState(false);
  const [bookId, setBookId] = useState<string | null>(null);
  const [projectId, setProjectId] = useState<string | null>(null);
  const [provisionStatus, setProvisionStatus] = useState<ProvisionStatus | null>(null);
  const [consentEnabled, setConsentEnabled] = useState(false);
  const [consentSaving, setConsentSaving] = useState(false);
  // Bump to re-drive provisioning (e.g. after the user restores a trashed diary).
  const [attempt, setAttempt] = useState(0);
  // Dedupe key = the ATTEMPT number ONLY — deliberately NOT the access token. `accessToken` rotates on
  // every silent 401-refresh (auth.tsx), and provisioning is idempotent + book/project don't change for
  // the same user, so a token refresh must NOT re-provision. Keying on the token made a refresh re-enter
  // this effect, flip `loading` true, and unmount <Chat>/<HomeStrip> mid-turn (audit HIGH #1). Keying on
  // `attempt` fires provisioning exactly once per mount (+ once per explicit reprovision) and survives
  // React 18 StrictMode's dev double-invoke without discarding the first run's result. The effect still
  // depends on `accessToken` so it runs once the token is first available, but a later rotation is a
  // no-op (same key → early return).
  const provisionedKeyRef = useRef<string>('');

  // Provisioning is a SYNCHRONIZATION with the server (get-or-create on open) — what useEffect is for.
  useEffect(() => {
    if (!accessToken) return;
    const key = String(attempt);
    if (provisionedKeyRef.current === key) return; // already provisioning/provisioned this attempt
    provisionedKeyRef.current = key;
    setLoading(true);
    setError(null);
    assistantApi
      .provision(accessToken)
      .then((res) => {
        setProvisioned(res.provisioned);
        setBookId(res.book_id ?? null);
        setProjectId(res.project_id ?? null);
        setProvisionStatus(res.provision_status);
        if (!res.provisioned) {
          setError(
            res.provision_status.diary_book === 'trashed'
              ? 'Your diary is in the trash — restore it to continue.'
              : 'The assistant could not finish setting up. Reopen to retry.',
          );
          return;
        }
        // Seed the REAL consent state from the assistant project (audit MED #2): the toggle must show
        // the persisted `canon_capture_enabled`, not a hard-coded false — otherwise a reload shows
        // "off" while capture is running server-side, and (since the toggle only ever offers "turn on")
        // the user can't turn it off. Best-effort: a failed read leaves the fail-closed false.
        if (res.book_id) {
          knowledgeApi
            .listProjects({ book_id: res.book_id, limit: 1 }, accessToken)
            .then((r) => {
              const p = r.items[0];
              if (p) setConsentEnabled(!!p.canon_capture_enabled);
            })
            .catch(() => {});
        }
      })
      .catch((e) => {
        // Allow a retry of this attempt after a hard failure (network/auth), so Retry re-drives.
        provisionedKeyRef.current = '';
        setError(e instanceof Error ? e.message : 'Failed to reach the assistant.');
      })
      .finally(() => setLoading(false));
  }, [accessToken, attempt]);

  const setConsent = useCallback(
    (enabled: boolean) => {
      if (!accessToken || !projectId) return;
      setConsentSaving(true);
      assistantApi
        .setCaptureConsent(accessToken, projectId, enabled)
        .then((res) => {
          setConsentEnabled(res.canon_capture_enabled);
          toast.success(res.canon_capture_enabled ? 'Capturing your work notes' : 'Capture paused');
        })
        .catch(() => toast.error('Could not update capture consent'))
        .finally(() => setConsentSaving(false));
    },
    [accessToken, projectId],
  );

  const reprovision = useCallback(() => setAttempt((a) => a + 1), []);

  // Bound HERE (in the provider, not a view) so the distill/poll state persists across the
  // strip↔dock swap on a viewport change — the provider is not remounted on resize.
  const endOfDay = useEndOfDay(bookId);

  return (
    <AssistantCtx.Provider
      value={{
        loading,
        error,
        provisioned,
        bookId,
        projectId,
        provisionStatus,
        consentEnabled,
        consentSaving,
        setConsent,
        reprovision,
        endOfDay,
      }}
    >
      {children}
    </AssistantCtx.Provider>
  );
}

export function useAssistant(): AssistantState {
  const ctx = useContext(AssistantCtx);
  if (!ctx) throw new Error('useAssistant must be used within an AssistantProvider');
  return ctx;
}
