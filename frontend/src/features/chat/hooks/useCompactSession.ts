import { useCallback, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import { useChatSession } from '../providers';

// W3 — the "Compact now" controller (MVC: this hook owns the logic/state; the
// ContextBreakdownPanel only renders what it's handed). Calls the persisted
// manual-compact endpoint with the user's optional preservation instructions,
// toasts the before→after estimate, and refreshes the active session so the
// "compacted through message N" marker (and every later turn) reflects it.
// The compacted history itself is server-side state — the next turn's loader
// splices the summary without any FE participation.
export interface CompactControls {
  pending: boolean;
  /** null = never manually compacted. */
  compactedBeforeSeq: number | null;
  onCompact: (instructions: string) => void;
  /** Clears the stored compact (summary + marker) — the panel shows the
   *  action only while compactedBeforeSeq is set. */
  onClearCompact: () => void;
}

export function useCompactSession(): CompactControls {
  const { t } = useTranslation('chat');
  const { accessToken } = useAuth();
  const { activeSession, updateActiveSession } = useChatSession();
  const [pending, setPending] = useState(false);

  const onCompact = useCallback((instructions: string) => {
    if (!accessToken || !activeSession || pending) return;
    const sessionId = activeSession.session_id;
    setPending(true);
    void (async () => {
      try {
        const trimmed = instructions.trim();
        const result = await chatApi.compactSession(
          accessToken,
          sessionId,
          trimmed ? { instructions: trimmed } : {},
        );
        toast.success(t('context_panel.compact.success', {
          before: result.tokens_before_estimate.toLocaleString(),
          after: result.tokens_after_estimate.toLocaleString(),
        }));
        // Refresh from the server (marker + message_count etc. all current) so
        // the panel indicator and any other session consumer see the compact.
        try {
          const fresh = await chatApi.getSession(accessToken, sessionId);
          updateActiveSession(fresh);
        } catch {
          // GET hiccup after a successful compact — patch the marker locally.
          updateActiveSession({
            ...activeSession,
            compacted_before_seq: result.compacted_before_seq,
          });
        }
      } catch (err) {
        toast.error(t('context_panel.compact.failed', { error: (err as Error).message }));
      } finally {
        setPending(false);
      }
    })();
  }, [accessToken, activeSession, pending, t, updateActiveSession]);

  const onClearCompact = useCallback(() => {
    if (!accessToken || !activeSession || pending) return;
    const sessionId = activeSession.session_id;
    setPending(true);
    void (async () => {
      try {
        await chatApi.compactSession(accessToken, sessionId, { clear: true });
        toast.success(t('context_panel.compact.cleared'));
        try {
          const fresh = await chatApi.getSession(accessToken, sessionId);
          updateActiveSession(fresh);
        } catch {
          // GET hiccup after a successful clear — drop the marker locally.
          updateActiveSession({ ...activeSession, compacted_before_seq: null });
        }
      } catch (err) {
        toast.error(t('context_panel.compact.failed', { error: (err as Error).message }));
      } finally {
        setPending(false);
      }
    })();
  }, [accessToken, activeSession, pending, t, updateActiveSession]);

  return {
    pending,
    compactedBeforeSeq: activeSession?.compacted_before_seq ?? null,
    onCompact,
    onClearCompact,
  };
}
