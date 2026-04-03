import { useCallback, useEffect, useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';


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
  } = useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [contextItems, setContextItems] = useState<ContextItem[]>([]);

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
    async (content: string) => {
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
            // Skip failed resolutions — still send the message
          }
        }

        const contextBlock = buildContextBlock(contextItems, resolvedData);
        if (contextBlock) {
          finalContent = contextBlock + content;
        }

        // Clear context after sending
        setContextItems([]);
      }

      chat.send(finalContent).catch((err) => {
        toast.error(`Chat error: ${(err as Error).message}`);
      });
    },
    [accessToken, contextItems, chat],
  );

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

  async function handleCreate(modelRef: string) {
    try {
      const session = await createSession({
        model_source: 'user_model',
        model_ref: modelRef,
        title: 'New Chat',
      });
      setActiveSession(session);
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
          onSelect={setActiveSession}
          onCreate={() => setShowNewDialog(true)}
          onRename={handleRename}
          onArchive={handleArchive}
          onDelete={handleDelete}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          {activeSession ? (
            <ChatWindow
              session={activeSession}
              chat={chat}
              modelNameMap={modelNameMap}
              onRename={handleHeaderRename}
              contextItems={contextItems}
              onAttachContext={handleAttachContext}
              onDetachContext={handleDetachContext}
              onClearContext={handleClearContext}
              onSendWithContext={(content) => void handleSendWithContext(content)}
            />
          ) : (
            <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
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
