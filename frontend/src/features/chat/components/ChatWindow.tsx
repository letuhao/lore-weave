import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import type { ChatSession } from '../types';
import type { useChatMessages } from '../hooks/useChatMessages';
import type { ContextItem } from '../context/types';
import { ChatHeader } from './ChatHeader';
import { ChatInputBar } from './ChatInputBar';
import { MessageList } from './MessageList';
import { SessionSettingsPanel } from './SessionSettingsPanel';
import { VoiceChatOverlay } from './VoiceChatOverlay';
import { VoiceSettingsPanel } from './VoiceSettingsPanel';
import { useVoiceChat } from '../hooks/useVoiceChat';
import { useAutoTTS } from '../hooks/useAutoTTS';

interface ChatWindowProps {
  session: ChatSession;
  chat: ReturnType<typeof useChatMessages>;
  modelNameMap?: Map<string, string>;
  onRename?: () => void;
  onSessionUpdate?: (updated: ChatSession) => void;
  contextItems: ContextItem[];
  onAttachContext: (item: ContextItem) => void;
  onDetachContext: (id: string) => void;
  onClearContext: () => void;
  onSendWithContext: (content: string, thinking?: boolean) => void;
  onOpenSidebar?: () => void;
}

export function ChatWindow({
  session,
  chat,
  modelNameMap,
  onRename,
  onSessionUpdate,
  contextItems,
  onAttachContext,
  onDetachContext,
  onClearContext,
  onSendWithContext,
  onOpenSidebar,
}: ChatWindowProps) {
  const { accessToken } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [voiceSettingsOpen, setVoiceSettingsOpen] = useState(false);
  const isArchived = session.status === 'archived';

  // Voice mode
  // #15: depend on chat.send directly (stable ref) not the chat object
  const voiceChat = useVoiceChat(session.session_id, chat.refresh);
  const autoTTS = useAutoTTS(chat.messages, chat.isStreaming, voiceChat.isActive);

  // Deactivate voice mode on session change
  useEffect(() => {
    voiceChat.deactivate();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- only on session change
  }, [session.session_id]);

  function handleSend(content: string, thinking?: boolean) {
    onSendWithContext(content, thinking);
  }

  function handleEdit(content: string, sequenceNum: number) {
    chat.edit(content, sequenceNum).catch((err) => {
      toast.error(`Edit failed: ${(err as Error).message}`);
    });
  }

  function handleRegenerate(userContent: string, userSequenceNum: number) {
    chat.regenerate(userContent, userSequenceNum).catch((err) => {
      toast.error(`Regenerate failed: ${(err as Error).message}`);
    });
  }

  function handleDeleteMessage(messageId: string) {
    if (!accessToken) return;
    if (!confirm('Delete this message? This cannot be undone.')) return;
    chatApi.deleteMessage(accessToken, session.session_id, messageId)
      .then(() => { chat.refresh(); })
      .catch((err) => { toast.error(`Delete failed: ${(err as Error).message}`); });
  }

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <ChatHeader
        session={session}
        modelNameMap={modelNameMap}
        messageCount={chat.messages.length}
        onRename={onRename}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenSidebar={onOpenSidebar}
        isVoiceModeActive={voiceChat.isActive}
        onToggleVoiceMode={() => {
          if (voiceChat.isActive) voiceChat.deactivate();
          else voiceChat.activate();
        }}
        onOpenVoiceSettings={() => setVoiceSettingsOpen(true)}
      />

      <MessageList
        messages={chat.messages}
        streamingText={chat.streamingText}
        streamingReasoning={chat.streamingReasoning}
        streamPhase={chat.streamPhase}
        thinkingElapsed={chat.thinkingElapsed}
        isStreaming={chat.isStreaming}
        onEditMessage={!isArchived ? handleEdit : undefined}
        onRegenerateMessage={!isArchived ? handleRegenerate : undefined}
        onDeleteMessage={!isArchived ? handleDeleteMessage : undefined}
        disabled={isArchived || chat.isStreaming}
        sessionId={session.session_id}
        onSwitchBranch={(branchId) => {
          chat.refreshBranch(branchId);
        }}
      />

      <ChatInputBar
        onSend={handleSend}
        onStop={chat.stop}
        isStreaming={chat.isStreaming}
        disabled={isArchived}
        voiceModeActive={voiceChat.isActive}
        ttsPlaying={autoTTS.isPlaying}
        onStopTTS={autoTTS.stop}
        supportsThinking={true}
        thinkingDefault={session.generation_params?.thinking ?? false}
        onThinkingModeChange={(thinking) => {
          if (!accessToken) return;
          chatApi.patchSession(accessToken, session.session_id, { generation_params: { thinking } })
            .then((updated) => onSessionUpdate?.(updated))
            .catch(() => {});
        }}
        contextItems={contextItems}
        onAttachContext={onAttachContext}
        onDetachContext={onDetachContext}
        onClearContext={onClearContext}
      />

      {settingsOpen && (
        <SessionSettingsPanel
          session={session}
          onSessionUpdate={(updated) => onSessionUpdate?.(updated)}
          onClose={() => setSettingsOpen(false)}
        />
      )}

      {voiceChat.isActive && (
        <VoiceChatOverlay
          state={voiceChat.state}
          sttText={voiceChat.sttText}
          aiText={voiceChat.aiText}
          error={voiceChat.error}
          onExit={voiceChat.deactivate}
          onCancel={voiceChat.cancel}
          pipelineSnapshot={voiceChat.pipelineSnapshot}
        />
      )}

      {/* Voice consent dialog — shown on first activation */}
      {voiceChat.showConsent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="mx-4 max-w-sm rounded-lg border border-border bg-card p-6 shadow-xl">
            <h3 className="text-sm font-semibold text-foreground">Enable Voice Mode</h3>
            <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
              Voice mode will use your microphone for speech recognition.
              Audio may be stored for up to 48 hours to enable replay.
              You can delete all voice data anytime from Settings.
            </p>
            <div className="mt-4 flex gap-2 justify-end">
              <button
                onClick={voiceChat.dismissConsent}
                className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
              <button
                onClick={voiceChat.acceptConsent}
                className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:brightness-110"
              >
                Continue
              </button>
            </div>
          </div>
        </div>
      )}

      <VoiceSettingsPanel
        open={voiceSettingsOpen}
        onClose={() => setVoiceSettingsOpen(false)}
      />
    </div>
  );
}
