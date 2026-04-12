import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import { useChatSession } from '../providers';
import { useChatStream } from '../providers';
import { ChatHeader } from './ChatHeader';
import { ChatInputBar } from './ChatInputBar';
import { MessageList } from './MessageList';
import { SessionSettingsPanel } from './SessionSettingsPanel';
import { VoiceChatOverlay } from './VoiceChatOverlay';
import { VoiceSettingsPanel } from './VoiceSettingsPanel';
import { useVoiceChat } from '../hooks/useVoiceChat';
import { useAutoTTS } from '../hooks/useAutoTTS';
import { usePanelState } from '../hooks/usePanelState';
import { loadVoicePrefs, saveVoicePrefs } from '../voicePrefs';

interface ChatViewProps {
  className?: string;
}

export function ChatView({ className }: ChatViewProps) {
  const { accessToken } = useAuth();
  const {
    activeSession,
    modelNameMap,
    promptRename,
    updateActiveSession,
    contextItems,
    attachContext,
    detachContext,
    clearContext,
    resolveAndSend,
    setMobileSidebarOpen,
  } = useChatSession();
  const chat = useChatStream();

  const { settingsOpen, setSettingsOpen, voiceSettingsOpen, setVoiceSettingsOpen } = usePanelState();
  const isArchived = activeSession?.status === 'archived';

  // Voice Assist mode — user toggle (persisted in prefs)
  const [voiceAssistOn, setVoiceAssistOn] = useState(() => loadVoicePrefs().voiceAssistEnabled);

  const toggleVoiceAssist = useCallback(() => {
    const prefs = loadVoicePrefs();
    // First-time: if enabling but models not configured, open settings instead
    if (!prefs.voiceAssistEnabled && (!prefs.ttsModelRef || !prefs.sttModelRef)) {
      setVoiceSettingsOpen(true);
      const missing = !prefs.sttModelRef && !prefs.ttsModelRef ? 'STT and TTS models'
        : !prefs.sttModelRef ? 'an STT model' : 'a TTS model';
      toast.info(`Configure ${missing} to enable Voice Assist`);
      return;
    }
    const next = !prefs.voiceAssistEnabled;
    saveVoicePrefs({ ...prefs, voiceAssistEnabled: next }, accessToken);
    setVoiceAssistOn(next);
  }, [accessToken, setVoiceSettingsOpen]);

  // Sync state when Voice Settings panel closes (user may have configured TTS model)
  useEffect(() => {
    if (!voiceSettingsOpen) {
      setVoiceAssistOn(loadVoicePrefs().voiceAssistEnabled);
    }
  }, [voiceSettingsOpen]);

  // Voice mode (full overlay)
  const voiceChat = useVoiceChat(activeSession?.session_id ?? null, chat.refresh);
  // Auto-TTS: fires when voice assist is ON (and voice mode overlay is not active)
  // onTTSComplete refreshes messages to pick up content_parts.voice_tts_sentences → shows replay button
  const autoTTS = useAutoTTS(chat.messages, chat.isStreaming, voiceChat.isActive, voiceAssistOn, chat.refresh);

  // Deactivate voice mode on session change
  useEffect(() => {
    voiceChat.deactivate();
  // eslint-disable-next-line react-hooks/exhaustive-deps -- only on session change
  }, [activeSession?.session_id]);

  // Loading state — shown inside ChatView, not by unmounting it
  if (!activeSession) {
    return <div className={className} />;
  }

  if (chat.isLoading && chat.messages.length === 0) {
    return (
      <div className={`flex flex-1 flex-col items-center justify-center ${className ?? ''}`}>
        <div className="space-y-3 text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-muted border-t-accent" />
          <p className="text-xs text-muted-foreground">Loading messages...</p>
        </div>
      </div>
    );
  }

  function handleSend(content: string, thinking?: boolean) {
    resolveAndSend(content, chat.send, thinking);
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
    chatApi.deleteMessage(accessToken, activeSession!.session_id, messageId)
      .then(() => { chat.refresh(); })
      .catch((err) => { toast.error(`Delete failed: ${(err as Error).message}`); });
  }

  return (
    <div className={`flex h-full flex-col overflow-hidden ${className ?? ''}`}>
      <ChatHeader
        session={activeSession}
        modelNameMap={modelNameMap}
        messageCount={chat.messages.length}
        onRename={promptRename}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenSidebar={() => setMobileSidebarOpen(true)}
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
        sessionId={activeSession.session_id}
        onSwitchBranch={(branchId) => {
          chat.refreshBranch(branchId);
        }}
      />

      <ChatInputBar
        onSend={handleSend}
        onStop={chat.stop}
        isStreaming={chat.isStreaming}
        disabled={!!isArchived}
        voiceModeActive={voiceChat.isActive}
        voiceAssistOn={voiceAssistOn}
        onToggleVoiceAssist={toggleVoiceAssist}
        ttsPlaying={autoTTS.isPlaying}
        onStopTTS={autoTTS.stop}
        supportsThinking={true}
        thinkingDefault={activeSession.generation_params?.thinking ?? false}
        onThinkingModeChange={(thinking) => {
          if (!accessToken) return;
          chatApi.patchSession(accessToken, activeSession.session_id, { generation_params: { thinking } })
            .then((updated) => updateActiveSession(updated))
            .catch(() => {});
        }}
        contextItems={contextItems}
        onAttachContext={attachContext}
        onDetachContext={detachContext}
        onClearContext={clearContext}
      />

      {settingsOpen && (
        <SessionSettingsPanel
          session={activeSession}
          onSessionUpdate={updateActiveSession}
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
