import { useEffect, useState } from 'react';
import { Bot, ChevronRight } from 'lucide-react';
import { useAuth } from '@/auth';
import { Button } from '@/components/ui/button';
import {
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Select } from '@/components/ui/select';
import { aiModelsApi } from '@/features/ai-models/api';
import { SessionSidebar } from '@/features/chat/components/SessionSidebar';
import { ChatWindow } from '@/features/chat/components/ChatWindow';
import { useSessions } from '@/features/chat/hooks/useSessions';
import type { ChatSession } from '@/features/chat/types';

type UserModelItem = {
  user_model_id: string;
  alias?: string | null;
  provider_model_name: string;
  provider_kind: string;
};

export default function ChatPage() {
  const { accessToken } = useAuth();
  const { sessions, createSession, renameSession, archiveSession, deleteSession } =
    useSessions();

  const [activeSession, setActiveSession] = useState<ChatSession | null>(null);
  const [showNewDialog, setShowNewDialog] = useState(false);
  const [userModels, setUserModels] = useState<UserModelItem[]>([]);
  const [selectedModel, setSelectedModel] = useState<string>('');

  useEffect(() => {
    if (!showNewDialog || !accessToken) return;
    void aiModelsApi
      .listUserModels(accessToken, { include_inactive: false })
      .then((res) => {
        setUserModels(res.items as UserModelItem[]);
        if (res.items.length > 0) setSelectedModel((res.items[0] as UserModelItem).user_model_id);
      })
      .catch(() => {});
  }, [showNewDialog, accessToken]);

  async function handleConfirmCreate() {
    if (!selectedModel) return;
    const session = await createSession({
      model_source: 'user_model',
      model_ref: selectedModel,
      title: 'New Chat',
    });
    setActiveSession(session);
    setShowNewDialog(false);
  }

  async function handleRename(sessionId: string, title: string) {
    await renameSession(sessionId, title);
    if (activeSession?.session_id === sessionId) {
      setActiveSession((prev) => (prev ? { ...prev, title } : prev));
    }
  }

  async function handleArchive(sessionId: string) {
    await archiveSession(sessionId);
    if (activeSession?.session_id === sessionId) setActiveSession(null);
  }

  async function handleDelete(sessionId: string) {
    await deleteSession(sessionId);
    if (activeSession?.session_id === sessionId) setActiveSession(null);
  }

  return (
    <div className="flex h-full overflow-hidden">
      <SessionSidebar
        sessions={sessions}
        activeSessionId={activeSession?.session_id ?? null}
        onSelect={setActiveSession}
        onCreate={() => setShowNewDialog(true)}
        onRename={handleRename}
        onArchive={handleArchive}
        onDelete={handleDelete}
      />

      <div className="flex flex-1 flex-col overflow-hidden">
        {activeSession ? (
          <ChatWindow session={activeSession} />
        ) : (
          <div className="flex flex-1 flex-col items-center justify-center gap-4 text-center">
            <Bot className="h-10 w-10 text-muted-foreground/40" />
            <div>
              <p className="text-sm font-medium">No chat selected</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Select a chat from the sidebar or start a new one.
              </p>
            </div>
            <Button size="sm" onClick={() => setShowNewDialog(true)} className="gap-1.5">
              <ChevronRight className="h-3.5 w-3.5" />
              Start New Chat
            </Button>
          </div>
        )}
      </div>

      {/* New chat dialog */}
      {showNewDialog && (
        <DialogContent className="max-w-sm" onClose={() => setShowNewDialog(false)}>
          <DialogHeader>
            <DialogTitle>Start New Chat</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">Model</label>
              {userModels.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  No active models. Add one in Settings → Providers.
                </p>
              ) : (
                <Select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
                  className="h-8 text-sm"
                >
                  {userModels.map((m) => (
                    <option key={m.user_model_id} value={m.user_model_id}>
                      {m.alias ?? m.provider_model_name} ({m.provider_kind})
                    </option>
                  ))}
                </Select>
              )}
            </div>
            <Button
              className="w-full"
              disabled={!selectedModel}
              onClick={() => void handleConfirmCreate()}
            >
              Start Chat
            </Button>
          </div>
        </DialogContent>
      )}
    </div>
  );
}
