import { createContext, useContext, useEffect } from 'react';
import { useChatMessages } from '../hooks/useChatMessages';
import { useChatSession } from './ChatSessionContext';

// ── Types ──────────────────────────────────────────────────────────────────────

export type ChatStreamValue = ReturnType<typeof useChatMessages>;

const ChatStreamCtx = createContext<ChatStreamValue | null>(null);

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useChatStream() {
  const ctx = useContext(ChatStreamCtx);
  if (!ctx) throw new Error('useChatStream must be inside ChatStreamProvider');
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────────────────

export function ChatStreamProvider({ children }: { children: React.ReactNode }) {
  const { activeSession, refreshSessions, updateActiveSession } = useChatSession();
  const chat = useChatMessages(activeSession?.session_id ?? null);

  // Wire up onStreamEnd callback — explicit handler, not a useEffect chain.
  // Refreshes session list after streaming ends (picks up auto-generated title).
  useEffect(() => {
    chat.onStreamEndRef.current = () => {
      setTimeout(() => { void refreshSessions(); }, 2000);
    };
    return () => { chat.onStreamEndRef.current = null; };
  }, [chat.onStreamEndRef, refreshSessions]);

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

  return <ChatStreamCtx.Provider value={chat}>{children}</ChatStreamCtx.Provider>;
}
