import { useCallback, useEffect, useRef, useState } from 'react';
import { Menu, MessageSquareText } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { syncPrefsToServer, loadPrefFromServer } from '@/lib/syncPrefs';


import { providerApi, type UserModel } from '@/features/settings/api';
import { booksApi } from '@/features/books/api';
import { glossaryApi } from '@/features/glossary/api';
import { useSessions } from '@/features/chat/hooks/useSessions';
import { useChatMessages } from '@/features/chat/hooks/useChatMessages';
import { SessionSidebar } from '@/features/chat/components/SessionSidebar';
import { ChatWindow } from '@/features/chat/components/ChatWindow';
import { NewChatDialog } from '@/features/chat/components/NewChatDialog';
import { buildContextBlock } from '@/features/chat/context/formatContext';
import { onSendToChat } from '@/features/chat/context/sendToChat';
import type { ContextItem } from '@/features/chat/context/types';
import type { ChatSession } from '@/features/chat/types';

export function ChatPage() {
  const { accessToken } = useAuth();
  const {
    sessions,
    isLoading: sessionsLoading,
    createSession,
    renameSession,
    archiveSession,
    deleteSession,
    togglePin,
  } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);
  const [mobileSidebarOpen, setMobileSidebarOpen] = useState(false);
  const restoredRef = useRef(false);

  // Restore last active session from server preferences on mount
  useEffect(() => {
    if (!accessToken || restoredRef.current || sessions.length === 0) return;
    restoredRef.current = true;
    loadPrefFromServer<string>('last_active_chat_session', accessToken).then((savedId) => {
      if (savedId) {
        const match = sessions.find((s) => s.session_id === savedId);
        if (match) setActiveSession(match);
      }
    });
  }, [accessToken, sessions]);

  // Persist active session to server on change
  const handleSelectSession = useCallback((session: ChatSession | null) => {
    setActiveSession(session);
    if (session && accessToken) {
      syncPrefsToServer('last_active_chat_session', session.session_id, accessToken);
    }
  }, [accessToken]);

  // Model name resolver: model_ref UUID → display name
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

  const chat = useChatMessages(activeSession?.session_id ?? null);

  // ── Context management ────────────────────────────────────────────────────

  function handleAttachContext(item: ContextItem) {
    setContextItems((prev) => {
      if (prev.some((p) => p.id === item.id)) return prev;
      return [...prev, item];
    });
  }

  function handleDetachContext(id: string) {
    setContextItems((prev) => prev.filter((p) => p.id !== id));
  }

  function handleClearContext() {
    setContextItems([]);
  }

  // ── Send with context ─────────────────────────────────────────────────────

  const handleSendWithContext = useCallback(
    async (content: string, thinking?: boolean) => {
      if (!accessToken) return;

      let finalContent = content;

      // Resolve context data and build context block
      if (contextItems.length > 0) {
        const resolvedData = new Map<string, { book?: any; chapterBody?: string; entity?: any }>();

        for (const item of contextItems) {
          try {
            if (item.type === 'book') {
              const book = await booksApi.getBook(accessToken, item.id);
              resolvedData.set(item.id, { book });
            } else if (item.type === 'chapter' && item.bookId && item.chapterId) {
              const draft = await booksApi.getDraft(accessToken, item.bookId, item.chapterId);
              resolvedData.set(item.id, { chapterBody: draft.body ?? '' });
            } else if (item.type === 'glossary' && item.bookId) {
              const entity = await glossaryApi.getEntity(item.bookId!, item.id, accessToken);
              resolvedData.set(item.id, { entity });
            }
          } catch {
            toast.warning(`Could not load context for "${item.label}" — sending without it`);
          }
        }

        const contextBlock = buildContextBlock(contextItems, resolvedData);
        if (contextBlock) {
          finalContent = contextBlock + content;
        }

        // Clear context after sending
        setContextItems([]);
      }

      chat.send(finalContent, thinking).catch((err) => {
        toast.error(`Chat error: ${(err as Error).message}`);
      });
    },
    [accessToken, contextItems, chat],
  );

  // ── Global keyboard shortcuts ──────────────────────────────────────────────

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Ctrl+N: new chat
      if (e.ctrlKey && e.key === 'n') {
        e.preventDefault();
        setShowNewDialog(true);
      }
      // Escape: stop streaming
      if (e.key === 'Escape' && chat.isStreaming) {
        chat.stop();
      }
    }
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [chat.isStreaming, chat.stop]);

  // ── Listen for "Send to Chat" from editor ─────────────────────────────────

  useEffect(() => {
    return onSendToChat((detail) => {
      // Attach chapter as context
      handleAttachContext({
        id: detail.chapterId,
        type: 'chapter',
        label: detail.chapterTitle,
        bookId: detail.bookId,
        chapterId: detail.chapterId,
      });
      toast.info(`"${detail.chapterTitle}" attached as context`);
    });
  }, []);

  // ── Session CRUD handlers ─────────────────────────────────────────────────

  async function handleCreate(modelRef: string, systemPrompt?: string) {
    try {
      const session = await createSession({
        model_source: 'user_model',
        model_ref: modelRef,
        title: 'New Chat',
        system_prompt: systemPrompt,
      });
      handleSelectSession(session);
      setShowNewDialog(false);
      setContextItems([]);
    } catch (err) {
      toast.error(`Failed to create chat: ${(err as Error).message}`);
    }
  }

  async function handleRename(sessionId: string, title: string) {
    try {
      await renameSession(sessionId, title);
      if (activeSession?.session_id === sessionId) {
        setActiveSession((prev) => (prev ? { ...prev, title } : prev));
      }
    } catch (err) {
      toast.error(`Rename failed: ${(err as Error).message}`);
    }
  }

  async function handleArchive(sessionId: string) {
    try {
      await archiveSession(sessionId);
      if (activeSession?.session_id === sessionId) setActiveSession(null);
    } catch (err) {
      toast.error(`Archive failed: ${(err as Error).message}`);
    }
  }

  async function handleDelete(sessionId: string) {
    try {
      await deleteSession(sessionId);
      if (activeSession?.session_id === sessionId) setActiveSession(null);
    } catch (err) {
      toast.error(`Delete failed: ${(err as Error).message}`);
    }
  }

  function handleHeaderRename() {
    if (!activeSession) return;
    const title = prompt('Rename chat:', activeSession.title);
    if (title?.trim()) {
      void handleRename(activeSession.session_id, title.trim());
    }
  }

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <div className="flex min-h-0 flex-1 overflow-hidden">
        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSession?.session_id ?? null}
          isLoading={sessionsLoading}
          modelNameMap={modelNameMap}
          onSelect={handleSelectSession}
          onCreate={() => { setShowNewDialog(true); setMobileSidebarOpen(false); }}
          onRename={handleRename}
          onArchive={handleArchive}
          onDelete={handleDelete}
          onTogglePin={(sessionId, pinned) => void togglePin(sessionId, pinned)}
          mobileOpen={mobileSidebarOpen}
          onMobileClose={() => setMobileSidebarOpen(false)}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          {activeSession && chat.isLoading ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="space-y-3 text-center">
                <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-accent" />
                <p className="text-xs text-muted-foreground">Loading messages...</p>
              </div>
            </div>
          ) : activeSession ? (
            <ChatWindow
              session={activeSession}
              chat={chat}
              modelNameMap={modelNameMap}
              onRename={handleHeaderRename}
              onSessionUpdate={(updated) => setActiveSession(updated)}
              contextItems={contextItems}
              onAttachContext={handleAttachContext}
              onDetachContext={handleDetachContext}
              onClearContext={handleClearContext}
              onSendWithContext={(content, thinking) => void handleSendWithContext(content, thinking)}
              onOpenSidebar={() => setMobileSidebarOpen(true)}
            />
          ) : (
            <div className="relative flex flex-1 flex-col items-center justify-center gap-4 text-center">
              <button
                type="button"
                onClick={() => setMobileSidebarOpen(true)}
                className="absolute left-3 top-3 rounded-md p-2 text-muted-foreground hover:bg-muted md:hidden"
                aria-label="Open conversations"
              >
                <Menu className="h-5 w-5" />
              </button>
              <MessageSquareText className="h-12 w-12 text-muted-foreground/30" />
              <div>
                <p className="text-sm font-medium text-foreground">No chat selected</p>
                <p className="mt-1 text-xs text-muted-foreground">
                  Select a conversation from the sidebar or start a new one.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowNewDialog(true)}
                className="flex items-center gap-1.5 rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-white hover:brightness-110"
              >
                Start New Chat
              </button>
            </div>
          )}
        </div>
      </div>

      <NewChatDialog
        open={showNewDialog}
        onClose={() => setShowNewDialog(false)}
        onCreate={handleCreate}
      />
    </div>
  );
}
