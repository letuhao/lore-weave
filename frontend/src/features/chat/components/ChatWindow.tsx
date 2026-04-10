import { useState, useCallback } from 'react';
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
import { VoiceModeOverlay } from './VoiceModeOverlay';
import { VoiceSettingsPanel } from './VoiceSettingsPanel';
import { useVoiceMode } from '../hooks/useVoiceMode';

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
}: ChatWindowProps) {
  const { accessToken } = useAuth();
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [voiceSettingsOpen, setVoiceSettingsOpen] = useState(false);
  const isArchived = session.status === 'archived';

  // Voice mode
  const sendForVoice = useCallback(
    (content: string) => chat.send(content),
    [chat],
  );
  const voiceMode = useVoiceMode({
    sendMessage: sendForVoice,
    streamStatus: chat.streamStatus,
    streamingText: chat.streamingText,
  });

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
        isVoiceModeActive={voiceMode.isActive}
        onToggleVoiceMode={() => {
          if (voiceMode.isActive) voiceMode.deactivate();
          else voiceMode.activate();
        }}
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

      {voiceMode.isActive && (
        <VoiceModeOverlay
          phase={voiceMode.phase}
          userTranscript={voiceMode.userTranscript}
          interimText={voiceMode.interimText}
          aiResponseText={voiceMode.aiResponseText}
          error={voiceMode.error}
          onExit={voiceMode.deactivate}
          onPause={voiceMode.pause}
          onResume={voiceMode.resume}
          onOpenSettings={() => setVoiceSettingsOpen(true)}
        />
      )}

      <VoiceSettingsPanel
        open={voiceSettingsOpen}
        onClose={() => {
          setVoiceSettingsOpen(false);
          voiceMode.reloadPrefs();
        }}
      />
    </div>
  );
}
