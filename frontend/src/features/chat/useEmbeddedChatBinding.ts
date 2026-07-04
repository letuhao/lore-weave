import { useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';
import { chatApi } from './api';
import type { ChatSession } from './types';

interface BindingDeps {
  bookId?: string;
  sessions: ChatSession[];
  sessionsLoading: boolean;
  activeSession: ChatSession | null;
  selectSession: (s: ChatSession | null) => void;
  updateActiveSession: (s: ChatSession) => void;
}

interface BindingState {
  /** undefined = resolving, null = book has no project, string = the project id. */
  projectId: string | null | undefined;
  /** True when no book-scoped session exists yet → host should prompt to create. */
  needsNewSession: boolean;
}

/**
 * ARCH-1 C5 — the embedded chat binding logic, extracted from <Chat> so it can
 * be unit-tested without mounting the whole provider tree (CLAUDE.md MVC: logic
 * in hooks, not components).
 *
 * Sequence:
 *  1. Resolve the book's knowledge project via the by-book filter (Part A).
 *  2. Once resolved + sessions loaded, select the project-bound session, else
 *     signal that a new one is needed (needsNewSession).
 *  3. When a session becomes active that isn't yet bound to the project, patch
 *     it so memory/RAG is scoped to the book. Non-fatal on failure.
 */
export function useEmbeddedChatBinding({
  bookId,
  sessions,
  sessionsLoading,
  activeSession,
  selectSession,
  updateActiveSession,
}: BindingDeps): BindingState {
  const { accessToken } = useAuth();
  const [projectId, setProjectId] = useState<string | null | undefined>(undefined);
  const [needsNewSession, setNeedsNewSession] = useState(false);
  const boundRef = useRef(false);

  // 1. Resolve the book's project.
  useEffect(() => {
    if (!accessToken || !bookId) {
      setProjectId(null);
      return;
    }
    let cancelled = false;
    knowledgeApi
      .listProjects({ book_id: bookId, limit: 1 }, accessToken)
      .then((res) => {
        if (!cancelled) setProjectId(res.items[0]?.project_id ?? null);
      })
      .catch(() => {
        if (!cancelled) setProjectId(null); // degrade to no-project memory
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, bookId]);

  // 2. Select the book-scoped session, or signal a new one is needed.
  //
  // D-COMPOSE-SESSION-RESTORE: prefer a direct book_id match — it works even
  // when the book has no knowledge project yet (project_id stays null
  // forever in that case, so matching on it alone could never find a
  // session for such a book). Falls back to the pre-existing project_id
  // match for sessions created before book_id existed (never re-tagged).
  //
  // The local `sessions` array alone isn't reliable for this: it's ordered
  // by last_message_at DESC NULLS LAST, so a freshly-created 0-message
  // session sorts to the very bottom and can fall outside the loaded page
  // (the exact D-CHAT-URL-SESSION-ACTIVATION class of bug, hit again here).
  // When no local match is found and bookId is set, fall back to a direct
  // book_id-scoped fetch (the list endpoint's book_id filter) before giving
  // up and asking to start a new chat.
  const bookFetchInFlightRef = useRef(false);
  useEffect(() => {
    if (projectId === undefined || sessionsLoading || activeSession || boundRef.current) return;
    const localMatch = (bookId ? sessions.find((s) => s.book_id === bookId) : undefined)
      ?? (projectId ? sessions.find((s) => s.project_id === projectId) : undefined);
    if (localMatch) {
      boundRef.current = true;
      selectSession(localMatch);
      return;
    }
    if (!bookId) {
      boundRef.current = true;
      setNeedsNewSession(true);
      return;
    }
    if (!accessToken || bookFetchInFlightRef.current) return; // wait for auth, or a fetch already in flight
    bookFetchInFlightRef.current = true;
    let ignore = false;
    void chatApi
      .listSessions(accessToken, 'active', bookId)
      .then((res) => {
        if (ignore) return;
        boundRef.current = true;
        const found = res.items[0];
        if (found) {
          selectSession(found);
        } else {
          setNeedsNewSession(true);
        }
      })
      .catch(() => {
        if (ignore) return;
        boundRef.current = true;
        setNeedsNewSession(true);
      });
    return () => {
      ignore = true;
    };
  }, [bookId, projectId, sessions, sessionsLoading, activeSession, selectSession, accessToken]);

  // 3. Bind a newly-active session to the book's project.
  useEffect(() => {
    if (!accessToken || !activeSession || !projectId) return;
    if (activeSession.project_id === projectId) {
      if (needsNewSession) setNeedsNewSession(false);
      return;
    }
    chatApi
      .patchSession(accessToken, activeSession.session_id, { project_id: projectId })
      .then((updated) => updateActiveSession(updated))
      .catch(() => {
        // Non-fatal: chat still works, memory just isn't scoped to the book.
        // Surface it so the user understands why the assistant lacks book lore.
        toast.warning("Couldn't link this chat to the book's memory — replies may lack book context.");
      });
  }, [accessToken, activeSession, projectId, needsNewSession, updateActiveSession]);

  return { projectId, needsNewSession };
}
