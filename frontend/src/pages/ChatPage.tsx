import { ChatSessionProvider, ChatStreamProvider, useChatSession } from '@/features/chat/providers';
import { SessionSidebar } from '@/features/chat/components/SessionSidebar';
import { ChatView } from '@/features/chat/components/ChatView';
import { NewChatDialog } from '@/features/chat/components/NewChatDialog';
import { ChatKeyboardShortcuts } from '@/features/chat/components/ChatKeyboardShortcuts';
import { ChatEmptyState } from '@/features/chat/components/ChatEmptyState';

export function ChatPage() {
  return (
    <ChatSessionProvider>
      <ChatStreamProvider>
        <ChatPageLayout />
      </ChatStreamProvider>
    </ChatSessionProvider>
  );
}

/** Inner layout — reads from context providers */
function ChatPageLayout() {
  const {
    activeSession,
    sessions,
    sessionsLoading,
    modelNameMap,
    selectSession,
    renameSession,
    archiveSession,
    deleteSession,
    togglePin,
    showNewDialog,
    setShowNewDialog,
    mobileSidebarOpen,
    setMobileSidebarOpen,
    createSession,
  } = useChatSession();

  return (
    <div className="flex h-full flex-col overflow-hidden bg-background">
      <ChatKeyboardShortcuts />

      <div className="flex min-h-0 flex-1 overflow-hidden">
        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSession?.session_id ?? null}
          isLoading={sessionsLoading}
          modelNameMap={modelNameMap}
          onSelect={selectSession}
          onCreate={() => { setShowNewDialog(true); setMobileSidebarOpen(false); }}
          onRename={renameSession}
          onArchive={archiveSession}
          onDelete={deleteSession}
          onTogglePin={(sessionId, pinned) => void togglePin(sessionId, pinned)}
          mobileOpen={mobileSidebarOpen}
          onMobileClose={() => setMobileSidebarOpen(false)}
        />

        <div className="flex flex-1 flex-col overflow-hidden">
          {/* ChatView always mounted — never unmounts voice/audio state */}
          <ChatView className={!activeSession ? 'hidden' : ''} />
          <ChatEmptyState className={activeSession ? 'hidden' : ''} />
        </div>
      </div>

      <NewChatDialog
        open={showNewDialog}
        onClose={() => setShowNewDialog(false)}
        onCreate={(modelRef, systemPrompt) => {
          void createSession({
            model_source: 'user_model',
            model_ref: modelRef,
            title: 'New Chat',
            system_prompt: systemPrompt,
          });
        }}
      />
    </div>
  );
}
