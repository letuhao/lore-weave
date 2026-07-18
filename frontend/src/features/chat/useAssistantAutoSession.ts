import { useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { defaultModelsApi, CHAT_CAPABILITY } from '@/features/settings/api';
import type { CreateSessionPayload } from './types';

interface Opts {
  /** True for the diary assistant surface (sessionKind === 'assistant'). */
  enabled: boolean;
  needsNewSession: boolean;
  hasActiveSession: boolean;
  bookId?: string;
  createSession: (payload: CreateSessionPayload) => Promise<void>;
}

/**
 * F-QC-1 (WS-1.10) — the diary assistant must be READY on open, not greet the user with the GENERIC
 * new-chat dialog (a model picker + Novelist/Translator/Worldbuilder/... personas that belong to the
 * novel-writing product, not a journal). When the assistant has no session yet, auto-create ONE — bound to
 * the diary book, stamped `session_kind='assistant'`, using the user's DEFAULT chat model — so `/assistant`
 * lands straight in the journal. Falls back to the manual dialog ONLY when no default model is set (then the
 * user genuinely must pick one). Runs at most once per mount (a ref guards the create).
 */
export function useAssistantAutoSession({
  enabled,
  needsNewSession,
  hasActiveSession,
  bookId,
  createSession,
}: Opts): { suppressGenericDialog: boolean } {
  const { accessToken } = useAuth();
  const [noDefaultModel, setNoDefaultModel] = useState(false);
  const triedRef = useRef(false);

  useEffect(() => {
    if (!enabled || !needsNewSession || hasActiveSession || triedRef.current || !accessToken) return;
    triedRef.current = true;
    void defaultModelsApi
      .get(accessToken)
      .then(({ defaults }) => {
        const modelRef = defaults?.[CHAT_CAPABILITY];
        if (!modelRef) {
          setNoDefaultModel(true); // no default → the manual dialog is the correct fallback (user picks)
          return;
        }
        return createSession({
          model_source: 'user_model',
          model_ref: modelRef,
          title: 'Work Assistant',
          book_id: bookId,
          session_kind: 'assistant',
        });
      })
      .catch(() => setNoDefaultModel(true)); // resolution/create failed → fall back to manual, never a dead surface
  }, [enabled, needsNewSession, hasActiveSession, accessToken, bookId, createSession]);

  // The assistant OWNS its session-create; suppress the generic dialog for it — unless there's genuinely no
  // default model to auto-use, in which case the manual picker is the right fallback.
  return { suppressGenericDialog: enabled && !noDefaultModel };
}
