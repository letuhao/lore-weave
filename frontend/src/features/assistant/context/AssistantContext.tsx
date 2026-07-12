// WS-1.10 — the Assistant "service": shared control-plane state (provisioning + consent) across the
// home strip's views. CLAUDE.md MVC: shared state lives in context, logic in this provider's
// callbacks (no business logic in the view components that consume it).
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { assistantApi } from '../api';
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
  // Dedupe key = (token, attempt). This makes provisioning fire EXACTLY once per key and — crucially —
  // survives React 18 StrictMode's dev double-invoke WITHOUT discarding the first run's result. (A
  // per-run `cancelled` closure would be set true by the first invoke's cleanup, then the resolved
  // provision would skip its setState → the page hangs on "Setting up…" forever. The live smoke caught
  // exactly that.) Changing token or attempt changes the key, so reprovision still works.
  const provisionedKeyRef = useRef<string>('');

  // Provisioning is a SYNCHRONIZATION with the server (get-or-create on open) — what useEffect is for.
  useEffect(() => {
    if (!accessToken) return;
    const key = `${accessToken}:${attempt}`;
    if (provisionedKeyRef.current === key) return; // already provisioning/provisioned this key
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
        }
      })
      .catch((e) => {
        // Allow a retry of this key after a hard failure (network/auth), so Retry re-drives.
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
