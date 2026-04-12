import { createContext, useContext, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { providerApi } from '@/features/settings/api';
import { booksApi, type Book } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import type { GlossaryEntity } from '@/features/glossary/types';
import { useSessions } from '../hooks/useSessions';
import { buildContextBlock } from '../context/formatContext';
import { onSendToChat } from '../context/sendToChat';
import type { ContextItem } from '../context/types';
import type { ChatSession, CreateSessionPayload } from '../types';

// ── Types ──────────────────────────────────────────────────────────────────────

interface ChatSessionContextValue {
  // Session
  activeSession: ChatSession | null;
  selectSession: (session: ChatSession | null) => void;

  // Session list
  sessions: ChatSession[];
  sessionsLoading: boolean;
  refreshSessions: () => Promise<void>;

  // Session CRUD
  createSession: (payload: CreateSessionPayload) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;
  archiveSession: (sessionId: string) => Promise<void>;
  deleteSession: (sessionId: string) => Promise<void>;
  togglePin: (sessionId: string, pinned: boolean) => Promise<void>;
  promptRename: () => void;
  updateActiveSession: (updated: ChatSession) => void;

  // Model names
  modelNameMap: Map<string, string>;

  // Context attachment
  contextItems: ContextItem[];
  attachContext: (item: ContextItem) => void;
  detachContext: (id: string) => void;
  clearContext: () => void;

  // UI
  showNewDialog: boolean;
  setShowNewDialog: (v: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (v: boolean) => void;

  // Send with context resolution
  resolveAndSend: (content: string, sendFn: (content: string, thinking?: boolean) => Promise<string>, thinking?: boolean) => void;
}

const ChatSessionCtx = createContext<ChatSessionContextValue | null>(null);

// ── Hook ───────────────────────────────────────────────────────────────────────

export function useChatSession() {
  const ctx = useContext(ChatSessionCtx);
  if (!ctx) throw new Error('useChatSession must be inside ChatSessionProvider');
  return ctx;
}

// ── Provider ───────────────────────────────────────────────────────────────────

export function ChatSessionProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();

  // ── Sessions ───────────────────────────────────────────────────────────────

  const sessionsHook = useSessions();
  const {
    sessions,
    isLoading: sessionsLoading,
    refresh: refreshSessions,
    createSession: createSessionApi,
    renameSession: renameSessionApi,
    archiveSession: archiveSessionApi,
    deleteSession: deleteSessionApi,
    togglePin: togglePinApi,
  } = sessionsHook;

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);

  // Restore session from URL param
  useEffect(() => {
    if (!urlSessionId || sessions.length === 0) return;
    const match = sessions.find((s) => s.session_id === urlSessionId);
    if (match && match.session_id !== activeSession?.session_id) {
      setActiveSession(match);
    }
  }, [urlSessionId, sessions]);

  const selectSession = useCallback((session: ChatSession | null) => {
    setActiveSession(session);
    if (session) {
      navigate(`/chat/${session.session_id}`, { replace: true });
    } else {
      navigate('/chat', { replace: true });
    }
  }, [navigate]);

  // ── Session CRUD ───────────────────────────────────────────────────────────

  const createSession = useCallback(async (payload: CreateSessionPayload) => {
    try {
      const session = await createSessionApi(payload);
      selectSession(session);
      setShowNewDialog(false);
      setContextItems([]);
    } catch (err) {
      toast.error(`Failed to create chat: ${(err as Error).message}`);
    }
  }, [createSessionApi, selectSession]);

  const renameSession = useCallback(async (sessionId: string, title: string) => {
    try {
      await renameSessionApi(sessionId, title);
      if (activeSession?.session_id === sessionId) {
        setActiveSession((prev) => (prev ? { ...prev, title } : prev));
      }
    } catch (err) {
      toast.error(`Rename failed: ${(err as Error).message}`);
    }
  }, [renameSessionApi, activeSession?.session_id]);

  const archiveSession = useCallback(async (sessionId: string) => {
    try {
      await archiveSessionApi(sessionId);
      if (activeSession?.session_id === sessionId) selectSession(null);
    } catch (err) {
      toast.error(`Archive failed: ${(err as Error).message}`);
    }
  }, [archiveSessionApi, activeSession?.session_id, selectSession]);

  const deleteSession = useCallback(async (sessionId: string) => {
    try {
      await deleteSessionApi(sessionId);
      if (activeSession?.session_id === sessionId) selectSession(null);
    } catch (err) {
      toast.error(`Delete failed: ${(err as Error).message}`);
    }
  }, [deleteSessionApi, activeSession?.session_id, selectSession]);

  const togglePin = useCallback(async (sessionId: string, pinned: boolean) => {
    await togglePinApi(sessionId, pinned);
  }, [togglePinApi]);

  const promptRename = useCallback(() => {
    if (!activeSession) return;
    const title = prompt('Rename chat:', activeSession.title);
    if (title?.trim()) {
      void renameSession(activeSession.session_id, title.trim());
    }
  }, [activeSession, renameSession]);

  const updateActiveSession = useCallback((updated: ChatSession) => {
    setActiveSession(updated);
  }, []);

  // ── Model names ────────────────────────────────────────────────────────────

  const [modelNameMap, setModelNameMap] = useState<Map<string, string>>(new Map());
  useEffect(() => {
    if (!accessToken) return;
    let cancelled = false;
    providerApi.listUserModels(accessToken).then((res) => {
      if (cancelled) return;
      const map = new Map<string, string>();
      for (const m of res.items ?? []) {
        map.set(m.user_model_id, m.alias || m.provider_model_name);
      }
      setModelNameMap(map);
    }).catch(() => {});
    return () => { cancelled = true; };
  }, [accessToken]);

  // ── Context attachment ─────────────────────────────────────────────────────

  const [contextItems, setContextItems] = useState<ContextItem[]>([]);

  const attachContext = useCallback((item: ContextItem) => {
    setContextItems((prev) => {
      if (prev.some((p) => p.id === item.id)) return prev;
      return [...prev, item];
    });
  }, []);

  const detachContext = useCallback((id: string) => {
    setContextItems((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const clearContext = useCallback(() => {
    setContextItems([]);
  }, []);

  // Listen for "Send to Chat" from editor
  useEffect(() => {
    return onSendToChat((detail) => {
      attachContext({
        id: detail.chapterId,
        type: 'chapter',
        label: detail.chapterTitle,
        bookId: detail.bookId,
        chapterId: detail.chapterId,
      });
      toast.info(`"${detail.chapterTitle}" attached as context`);
    });
  }, [attachContext]);

  // ── Send with context resolution ───────────────────────────────────────────

  const contextItemsRef = useRef(contextItems);
  contextItemsRef.current = contextItems;

  const resolveAndSend = useCallback(
    (content: string, sendFn: (content: string, thinking?: boolean) => Promise<string>, thinking?: boolean) => {
      const items = contextItemsRef.current;
      if (items.length === 0) {
        sendFn(content, thinking).catch((err) => {
          toast.error(`Chat error: ${(err as Error).message}`);
        });
        return;
      }

      // Clear immediately, then resolve async
      setContextItems([]);

      (async () => {
        if (!accessToken) return;
        const resolvedData = new Map<string, { book?: Book; chapterBody?: string; entity?: GlossaryEntity }>();

        for (const item of items) {
          try {
            if (item.type === 'book') {
              const book = await booksApi.getBook(accessToken, item.id);
              resolvedData.set(item.id, { book });
            } else if (item.type === 'chapter' && item.bookId && item.chapterId) {
              const draft = await booksApi.getDraft(accessToken, item.bookId, item.chapterId);
              resolvedData.set(item.id, { chapterBody: draft.body ?? '' });
            } else if (item.type === 'glossary' && item.bookId) {
              const entity = await glossaryApi.getEntity(item.bookId, item.id, accessToken);
              resolvedData.set(item.id, { entity });
            }
          } catch {
            toast.warning(`Could not load context for "${item.label}" — sending without it`);
          }
        }

        const contextBlock = buildContextBlock(items, resolvedData);
        const finalContent = contextBlock ? contextBlock + content : content;

        sendFn(finalContent, thinking).catch((err) => {
          toast.error(`Chat error: ${(err as Error).message}`);
        });
      })();
    },
    [accessToken],
  );

  // ── UI state ───────────────────────────────────────────────────────────────

  const [showNewDialog, setShowNewDialog] = useState(false);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);

  // ── Context value (memoized) ───────────────────────────────────────────────

  const value = useMemo<ChatSessionContextValue>(() => ({
    activeSession,
    selectSession,
    sessions,
    sessionsLoading,
    refreshSessions,
    createSession,
    renameSession,
    archiveSession,
    deleteSession,
    togglePin,
    promptRename,
    updateActiveSession,
    modelNameMap,
    contextItems,
    attachContext,
    detachContext,
    clearContext,
    showNewDialog,
    setShowNewDialog,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    resolveAndSend,
  }), [
    activeSession, selectSession,
    sessions, sessionsLoading, refreshSessions,
    createSession, renameSession, archiveSession, deleteSession, togglePin,
    promptRename, updateActiveSession,
    modelNameMap,
    contextItems, attachContext, detachContext, clearContext,
    showNewDialog, mobileSidebarOpen,
    resolveAndSend,
  ]);

  return <ChatSessionCtx.Provider value={value}>{children}</ChatSessionCtx.Provider>;
}
