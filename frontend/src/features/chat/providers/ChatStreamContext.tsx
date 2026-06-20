import { createContext, useContext, useEffect } from 'react';
import { useChatMessages } from '../hooks/useChatMessages';
import { usePendingFacts } from '../hooks/usePendingFacts';
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
  composeMode,
  bookContext,
}: {
  children: React.ReactNode;
  // ARCH-1 C6: editor panel context — enables the write-back frontend tool +
  // carries the chapter the assistant is editing. Undefined for the chat page.
  editorContext?: { book_id: string; chapter_id: string };
  // Editor "Compose" mode — when true, turns advertise no tools (prose-only).
  composeMode?: boolean;
  // Glossary-assistant P3: book-scoped (non-editor) chat → enables the glossary
  // edit-existing frontend tool. Undefined for the global chat page.
  bookContext?: { book_id: string };
}) {
  const { activeSession, refreshSessions, updateActiveSession } = useChatSession();
  const chat = useChatMessages(activeSession?.session_id ?? null, editorContext, composeMode, bookContext);
  // K21-C (D8): pending-facts review for the active session. A turn
  // may have queued a fact (knowledge-service design D6); the FE
  // discovers it by polling, so we refetch on stream-end below.
  const pendingFacts = usePendingFacts(activeSession?.session_id ?? null);

  // Wire up onStreamEnd callback — explicit handler, not a useEffect chain.
  // Fires after streaming ends: refreshes the session list (picks up
  // the auto-generated title) AND refetches pending facts (the turn may
  // have queued a `memory_remember` fact — K21-C D8). The ref has a
  // single writer, so both behaviors must live in this one callback.
  useEffect(() => {
    chat.onStreamEndRef.current = () => {
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

  return (
    <ChatStreamCtx.Provider value={{ ...chat, pendingFacts }}>
      {children}
    </ChatStreamCtx.Provider>
  );
}
