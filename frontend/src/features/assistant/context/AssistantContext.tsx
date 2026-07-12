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
  const inFlight = useRef(false);

  // Provisioning is a SYNCHRONIZATION with the server (get-or-create on open), which is exactly
  // what useEffect is for — not an event reaction. Re-runs on token / explicit reprovision.
  useEffect(() => {
    if (!accessToken || inFlight.current) return;
    inFlight.current = true;
    setLoading(true);
    setError(null);
    let cancelled = false;
    assistantApi
      .provision(accessToken)
      .then((res) => {
        if (cancelled) return;
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
        if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to reach the assistant.');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
        inFlight.current = false;
      });
    return () => {
      cancelled = true;
    };
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
