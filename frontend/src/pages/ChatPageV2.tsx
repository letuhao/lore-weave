import { useState } from 'react';
import { MessageSquareText } from 'lucide-react';
import { toast } from 'sonner';
import { AppNav } from '@/components/layout/AppNav';
import { Button } from '@/components/ui/button';
import { useSessions } from '@/features/chat-v2/hooks/useSessions';
import { useChatMessages } from '@/features/chat-v2/hooks/useChatMessages';
import { SessionSidebar } from '@/features/chat-v2/components/SessionSidebar';
import { ChatWindow } from '@/features/chat-v2/components/ChatWindow';
import { NewChatDialog } from '@/features/chat-v2/components/NewChatDialog';
import type { ChatSession } from '@/features/chat-v2/types';

export default function ChatPageV2() {
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

  const chat = useChatMessages(activeSession?.session_id ?? null);

  // ── Session CRUD handlers ───────────────────────────────────────────────────

  async function handleCreate(modelRef: string) {
    try {
      const session = await createSession({
        model_source: 'user_model',
        model_ref: modelRef,
        title: 'New Chat',
      });
      setActiveSession(session);
      setShowNewDialog(false);
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

  // ── Inline rename from header ─────────────────────────────────────────────────

  function handleHeaderRename() {
    if (!activeSession) return;
    const title = prompt('Rename chat:', activeSession.title);
    if (title?.trim()) {
      void handleRename(activeSession.session_id, title.trim());
    }
  }

  return (
    <div className="flex h-screen flex-col overflow-hidden bg-background">
      {/* Top nav — consistent with rest of app */}
      <div className="shrink-0 px-4 pt-3 sm:px-6 lg:px-8">
        <AppNav />
      </div>

      {/* Main chat area */}
      <div className="flex min-h-0 flex-1 overflow-hidden">
        {/* Session sidebar */}
        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSession?.session_id ?? null}
          isLoading={sessionsLoading}
          onSelect={setActiveSession}
          onCreate={() => setShowNewDialog(true)}
          onRename={handleRename}
          onArchive={handleArchive}
          onDelete={handleDelete}
        />

        {/* Chat area or empty state */}
        <div className="flex flex-1 flex-col overflow-hidden">
          {activeSession ? (
            <ChatWindow
              session={activeSession}
              chat={chat}
              onRename={handleHeaderRename}
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
              <Button
                size="sm"
                onClick={() => setShowNewDialog(true)}
                className="gap-1.5 bg-accent text-accent-foreground hover:bg-accent/90"
              >
                Start New Chat
              </Button>
            </div>
          )}
        </div>
      </div>

      {/* New chat dialog */}
      <NewChatDialog
        open={showNewDialog}
        onClose={() => setShowNewDialog(false)}
        onCreate={handleCreate}
      />
    </div>
  );
}
