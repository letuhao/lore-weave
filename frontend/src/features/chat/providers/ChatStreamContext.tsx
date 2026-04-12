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
  const { activeSession, refreshSessions } = useChatSession();
  const chat = useChatMessages(activeSession?.session_id ?? null);

  // Wire up onStreamEnd callback — explicit handler, not a useEffect chain.
  // Refreshes session list after streaming ends (picks up auto-generated title).
  useEffect(() => {
    chat.onStreamEndRef.current = () => {
      setTimeout(() => { void refreshSessions(); }, 2000);
    };
    return () => { chat.onStreamEndRef.current = null; };
  }, [chat.onStreamEndRef, refreshSessions]);

  return <ChatStreamCtx.Provider value={chat}>{children}</ChatStreamCtx.Provider>;
}
