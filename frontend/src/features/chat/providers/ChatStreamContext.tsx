import { createContext, useContext, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { useChatMessages } from '../hooks/useChatMessages';
import { usePendingFacts } from '../hooks/usePendingFacts';
import { useAgentSurface } from '../hooks/useAgentSurface';
import { useContextRack } from '../hooks/useContextRack';
import { useChatSession } from './ChatSessionContext';

// ── Types ──────────────────────────────────────────────────────────────────────

// K21-C (D8): the stream context also surfaces the pending-facts
// review state. usePendingFacts lives here — not in ChatView —
// because `onStreamEndRef` is a single mutable ref with exactly one
// writer (this provider). Owning the hook here lets the one
// stream-end callback fan out to BOTH the session refresh and the
// pending-facts refetch without clobbering.
export type ChatStreamValue = ReturnType<typeof useChatMessages> & {
  pendingFacts: ReturnType<typeof usePendingFacts>;
  agentSurface: ReturnType<typeof useAgentSurface>;
  rack: ReturnType<typeof useContextRack>;
};

const ChatStreamCtx = createContext<ChatStreamValue | null>(null);

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useChatStream() {
  const ctx = useContext(ChatStreamCtx);
  if (!ctx) throw new Error('useChatStream must be inside ChatStreamProvider');
  return ctx;
}

/** Non-throwing variant — returns null outside a ChatStreamProvider. Used by
 *  leaf renderers (e.g. the activity Undo action) that must call a hook
 *  unconditionally yet may be rendered in isolation (tests, storybook) without
 *  the provider. */
export function useChatStreamOptional() {
  return useContext(ChatStreamCtx);
}

// ── Provider ───────────────────────────────────────────────────────────────────

export function ChatStreamProvider({
  children,
  editorContext,
  studioContext,
  composeMode,
  bookContext,
  displayLanguage,
}: {
  children: React.ReactNode;
  // ARCH-1 C6: editor panel context — enables the write-back frontend tool +
  // carries the chapter the assistant is editing. Undefined for the chat page.
  editorContext?: { book_id: string; chapter_id: string };
  // #09 Lane A: Writing Studio compose panel → enables the studio dock-nav frontend tools.
  studioContext?: { book_id?: string; project_id?: string; active_chapter_id?: string; active_panel_ids?: string[]; context_revision?: number };
  // Editor "Compose" mode — when true, turns advertise no tools (prose-only).
  composeMode?: boolean;
  // Glossary-assistant P3: book-scoped (non-editor) chat → enables the glossary
  // edit-existing frontend tool. Undefined for the global chat page.
  bookContext?: { book_id: string };
  // S6: the user's per-book display language (the glossary `apiDisplayLanguage`,
  // set only when viewing a translation). Forwarded so knowledge composes entity
  // aliases in it. Undefined → source-language aliases.
  displayLanguage?: string;
}) {
  const { accessToken } = useAuth();
  const { t } = useTranslation('chat');
  const { activeSession, refreshSessions, updateActiveSession } = useChatSession();
  const agentSurface = useAgentSurface(activeSession);
  const rack = useContextRack({
    session: activeSession,
    accessToken,
    onSessionUpdate: updateActiveSession,
    hidden: !!composeMode,
  });
  const chat = useChatMessages(
    activeSession?.session_id ?? null,
    editorContext,
    composeMode,
    bookContext,
    displayLanguage,
    activeSession?.enabled_tools,
    activeSession?.enabled_skills,
    rack.streamPinsRef,
    studioContext,
  );
  // K21-C (D8): pending-facts review for the active session. A turn
  // may have queued a fact (knowledge-service design D6); the FE
  // discovers it by polling, so we refetch on stream-end below.
  const pendingFacts = usePendingFacts(activeSession?.session_id ?? null);

  // Wire up onStreamEnd callback — explicit handler, not a useEffect chain.
  // Fires after streaming ends: refreshes the session list (picks up
  // the auto-generated title) AND refetches pending facts (the turn may
  // have queued a `memory_remember` fact — K21-C D8). The ref has a
  // single writer, so both behaviors must live in this one callback.
  // Inline-path compaction dedupe: in-loop compaction can emit several
  // `compaction` frames in ONE turn (the worker path dedupes upstream on
  // turnId; the inline path has no turnId) — toast at most once per turn,
  // reset at stream end.
  const compactionToastedRef = useRef(false);

  useEffect(() => {
    chat.onStreamEndRef.current = () => {
      compactionToastedRef.current = false;
      setTimeout(() => { void refreshSessions(); }, 2000);
      pendingFacts.refetch();
    };
    return () => { chat.onStreamEndRef.current = null; };
  }, [chat.onStreamEndRef, refreshSessions, pendingFacts]);

  // K-CLEAN-5 (D-K8-04): wire up the per-turn memory-mode SSE event
  // so the chat header MemoryIndicator can flip to a degraded badge
  // as soon as chat-service signals the knowledge call fell back.
  // The ref is reset to a stable closure that captures the current
  // activeSession via the function-form setter, so we don't have to
  // re-subscribe on every session change.
  useEffect(() => {
    chat.onMemoryModeRef.current = (mode) => {
      // Only update if the mode actually changed — saves a render.
      if (activeSession && activeSession.memory_mode !== mode) {
        updateActiveSession({ ...activeSession, memory_mode: mode });
      }
    };
    return () => { chat.onMemoryModeRef.current = null; };
  }, [chat.onMemoryModeRef, activeSession, updateActiveSession]);

  useEffect(() => {
    chat.onAgentSurfaceRef.current = agentSurface.applyEvent;
    return () => { chat.onAgentSurfaceRef.current = null; };
  }, [chat.onAgentSurfaceRef, agentSurface.applyEvent]);

  // W2: the per-turn `compaction` CUSTOM frame → a small toast so the user
  // knows earlier turns were summarized/trimmed (and it wasn't silent context
  // loss). Warn variant when the summarizer failed or the prompt still
  // overflowed after compaction — the model genuinely lost detail then.
  useEffect(() => {
    chat.onCompactionRef.current = (event) => {
      // At most one compaction toast per turn (see compactionToastedRef above).
      if (compactionToastedRef.current) return;
      compactionToastedRef.current = true;
      const msg = t('compaction.toast', {
        before: event.tokens_before.toLocaleString(),
        after: event.tokens_after.toLocaleString(),
      });
      if (event.summarize_failed || event.overflowed) {
        toast.warning(msg, {
          description: t(event.overflowed ? 'compaction.overflowed' : 'compaction.summarize_failed'),
        });
      } else {
        toast.info(msg);
      }
    };
    return () => { chat.onCompactionRef.current = null; };
  }, [chat.onCompactionRef, t]);

  return (
    <ChatStreamCtx.Provider value={{ ...chat, pendingFacts, agentSurface, rack }}>
      {children}
    </ChatStreamCtx.Provider>
  );
}
