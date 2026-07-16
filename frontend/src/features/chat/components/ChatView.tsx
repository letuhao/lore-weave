import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { chatApi } from '../api';
import { useChatSession } from '../providers';
import { useChatStream } from '../providers';
import { ChatHeader } from './ChatHeader';
import { ChatInputBar, effortLevelFromGenerationParams, reasoningEffortForLevel, type EffortLevel } from './ChatInputBar';
import { MessageList } from './MessageList';
import { PendingFactsCard } from './PendingFactsCard';
import { SessionSettingsPanel } from './SessionSettingsPanel';
import { VoiceChatOverlay } from './VoiceChatOverlay';
import { useVoiceChat } from '../hooks/useVoiceChat';
import { useAutoTTS } from '../hooks/useAutoTTS';
import { useUiToolExecutor } from '../hooks/useUiToolExecutor';
import { useCompactSession } from '../hooks/useCompactSession';
import { usePanelState } from '../hooks/usePanelState';
import { AgentContextRack } from './AgentContextRack';
import { AgentRuntimeInspector } from './AgentRuntimeInspector';
import { loadVoicePrefs, saveVoicePrefs } from '../voicePrefs';

interface ChatViewProps {
  className?: string;
  /** Editor compose mode — hides tool rack (disable_tools). */
  composeMode?: boolean;
  /** Optional host-supplied slot rendered between the message list and the input
   *  bar (inside the chat providers, so it can read useChatStream/useChatSession).
   *  T3.1 mounts the co-writer Insert/Use-as-guide bar + starter chips here. */
  footerSlot?: React.ReactNode;
  /** Optional host-supplied header slot (bug #17): the embedded chat passes a
   *  SessionSwitcher here so the workspace can switch/create sessions. */
  headerSlot?: React.ReactNode;
}

export function ChatView({ className, composeMode, footerSlot, headerSlot }: ChatViewProps) {
  const { t } = useTranslation('chat');
  const navigate = useNavigate();
  const { accessToken } = useAuth();
  // Embedded surfaces (editor/studio) pass a headerSlot; there, opening the
  // standalone inspector would navigate away and tear down the host, so the
  // header inspector affordance is offered only on the full chat page.
  const embedded = !!headerSlot;
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
  const rackHidden = !!composeMode;
  const rack = chat.rack;

  const { settingsOpen, setSettingsOpen, voiceSettingsOpen, setVoiceSettingsOpen } = usePanelState();
  // W3 — the "Compact now" controller for the context breakdown panel.
  const compactControls = useCompactSession();
  const isArchived = activeSession?.status === 'archived';
  // WS-4.5 — voice affordance gate. A voice turn in an assistant session does NOT
  // fire canon capture yet (the WS-4.1 gap), so capturing the user's spoken diary
  // would silently drop it. Hide ALL voice controls for assistant sessions until
  // WS-4.1 lands; ordinary chat sessions keep voice.
  const voiceEnabled = activeSession?.session_kind !== 'assistant';
  // W2: the context breakdown panel's tool rows open the rack's add modal.
  const [rackAddOpen, setRackAddOpen] = useState(false);
  // W6: the rack's summary chip opens the header's context breakdown panel.
  const [breakdownOpen, setBreakdownOpen] = useState(false);

  // MCP fan-out (C-NAV): resolve any suspended `ui_*` nav tool the agent calls —
  // perform the router action + POST the resolve immediately (no human gate).
  // Mounted here (inside the providers, under the router) so it runs for both
  // the chat page and the embedded dock/editor surfaces.
  useUiToolExecutor();

  // Voice Assist mode — user toggle (persisted in prefs)
  const [voiceAssistOn, setVoiceAssistOn] = useState(() => loadVoicePrefs().voiceAssistEnabled);

  const toggleVoiceAssist = useCallback(() => {
    const prefs = loadVoicePrefs();
    // First-time: if enabling but models not configured, open settings instead
    if (!prefs.voiceAssistEnabled && (!prefs.ttsModelRef || !prefs.sttModelRef)) {
      setVoiceSettingsOpen(true);
      const missing = !prefs.sttModelRef && !prefs.ttsModelRef ? t('view.missing_both')
        : !prefs.sttModelRef ? t('view.missing_stt') : t('view.missing_tts');
      toast.info(t('view.configure_voice', { missing }));
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
          <p className="text-xs text-muted-foreground">{t('view.loading_messages')}</p>
        </div>
      </div>
    );
  }

  function handleSend(content: string, thinking?: boolean, reasoningEffort?: EffortLevel) {
    resolveAndSend(content, chat.send, thinking, reasoningEffort);
  }

  function handleEdit(content: string, sequenceNum: number) {
    chat.edit(content, sequenceNum).catch((err) => {
      toast.error(t('view.edit_failed', { error: (err as Error).message }));
    });
  }

  function handleRegenerate(userContent: string, userSequenceNum: number) {
    chat.regenerate(userContent, userSequenceNum).catch((err) => {
      toast.error(t('view.regenerate_failed', { error: (err as Error).message }));
    });
  }

  function handleDeleteMessage(messageId: string) {
    if (!accessToken) return;
    if (!confirm(t('view.delete_confirm'))) return;
    chatApi.deleteMessage(accessToken, activeSession!.session_id, messageId)
      .then(() => { chat.refresh(); })
      .catch((err) => { toast.error(t('view.delete_failed', { error: (err as Error).message })); });
  }

  return (
    <div className={`flex h-full flex-col overflow-hidden ${className ?? ''}`}>
      <ChatHeader
        session={activeSession}
        modelNameMap={modelNameMap}
        messageCount={chat.messages.length}
        contextBudget={chat.contextBudget}
        onManageContextTools={!rackHidden ? () => setRackAddOpen(true) : undefined}
        compactControls={!isArchived ? compactControls : undefined}
        breakdownOpen={breakdownOpen}
        onBreakdownClose={() => setBreakdownOpen(false)}
        onOpenInspector={
          !embedded
            ? () => navigate(`/context-inspector?session=${activeSession.session_id}`)
            : undefined
        }
        sessionSwitcher={headerSlot}
        onRename={promptRename}
        onOpenSettings={() => setSettingsOpen(true)}
        onOpenSidebar={() => setMobileSidebarOpen(true)}
        isVoiceModeActive={voiceChat.isActive}
        onToggleVoiceMode={voiceEnabled ? () => {
          if (voiceChat.isActive) voiceChat.deactivate();
          else voiceChat.activate();
        } : undefined}
        onOpenVoiceSettings={voiceEnabled ? () => setVoiceSettingsOpen(true) : undefined}
      />

      {!rackHidden && (
        <AgentRuntimeInspector
          state={chat.agentSurface.state}
          expanded={chat.agentSurface.expanded}
          onToggle={chat.agentSurface.toggleExpanded}
          isStreaming={chat.isStreaming}
          trail={chat.agentSurface.trail}
        />
      )}

      <MessageList
        messages={chat.messages}
        streamingText={chat.streamingText}
        streamingReasoning={chat.streamingReasoning}
        streamPhase={chat.streamPhase}
        thinkingElapsed={chat.thinkingElapsed}
        isStreaming={chat.isStreaming}
        isComposing={chat.isComposing}
        onEditMessage={!isArchived ? handleEdit : undefined}
        onRegenerateMessage={!isArchived ? handleRegenerate : undefined}
        onDeleteMessage={!isArchived ? handleDeleteMessage : undefined}
        disabled={isArchived || chat.isStreaming}
        sessionId={activeSession.session_id}
        onSwitchBranch={(branchId) => {
          chat.refreshBranch(branchId);
        }}
      />

      {/* K21-C (D8): facts the AI's memory_remember tool queued for
          confirmation. Renders nothing when the queue is empty. The
          hook (in ChatStreamContext) refetches on chat-stream end. */}
      <PendingFactsCard
        pendingFacts={chat.pendingFacts.pendingFacts}
        onConfirm={chat.pendingFacts.confirm}
        onReject={chat.pendingFacts.reject}
      />

      {footerSlot}

      {!rackHidden && (
        <AgentContextRack
          enabledTools={rack.enabledTools}
          enabledSkills={rack.enabledSkills}
          activatedTools={rack.activatedTools}
          pinnedLegacyTools={rack.pinnedLegacyTools}
          surface={chat.agentSurface.state}
          onOpenBreakdown={chat.contextBudget ? () => setBreakdownOpen(true) : undefined}
          token={accessToken}
          onAddTool={rack.addTool}
          onAddSkill={rack.addSkill}
          onRemoveTool={rack.removeTool}
          onRemoveSkill={rack.removeSkill}
          onAddLegacyTool={rack.addPinnedLegacyTool}
          onRemoveLegacyTool={rack.removePinnedLegacyTool}
          onClearDiscovered={rack.clearDiscovered}
          disabled={!!isArchived || chat.isStreaming}
          externalAddOpen={rackAddOpen}
          onExternalAddClose={() => setRackAddOpen(false)}
        />
      )}

      <ChatInputBar
        onSend={handleSend}
        onStop={chat.stop}
        isStreaming={chat.isStreaming}
        disabled={!!isArchived}
        placeholder={activeSession.session_kind === 'assistant' ? t('input.assistant_placeholder') : undefined}
        voiceModeActive={voiceChat.isActive}
        voiceEnabled={voiceEnabled}
        voiceAssistOn={voiceAssistOn}
        onToggleVoiceAssist={voiceEnabled ? toggleVoiceAssist : undefined}
        ttsPlaying={autoTTS.isPlaying}
        onStopTTS={autoTTS.stop}
        permissionMode={chat.permissionMode}
        onPermissionModeChange={chat.setPermissionMode}
        supportsThinking={true}
        effortDefault={effortLevelFromGenerationParams(activeSession.generation_params)}
        onEffortChange={(level) => {
          if (!accessToken) return;
          // Persist the GRANULAR knob + clear the legacy boolean — the same
          // {reasoning_effort, thinking:null} contract SessionSettingsPanel
          // writes, so a stale reasoning_effort can never shadow the dropdown
          // (and Deep survives a reload instead of downgrading to Standard).
          chatApi.patchSession(accessToken, activeSession.session_id, {
            generation_params: { reasoning_effort: reasoningEffortForLevel(level), thinking: null },
          })
            .then((updated) => updateActiveSession(updated))
            .catch(() => {});
        }}
        contextItems={contextItems}
        onAttachContext={attachContext}
        onDetachContext={detachContext}
        onClearContext={clearContext}
      />

      {/* ONE session settings surface (spec §8). Voice is a section inside it, not a
          rival slide-over: the mic button deep-links to that section instead of opening
          a second panel that fought this one for the right edge. */}
      {(settingsOpen || voiceSettingsOpen) && (
        <SessionSettingsPanel
          session={activeSession}
          onSessionUpdate={updateActiveSession}
          initialSection={voiceSettingsOpen ? 'voice' : undefined}
          onClose={() => { setSettingsOpen(false); setVoiceSettingsOpen(false); }}
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
            <h3 className="text-sm font-semibold text-foreground">{t('view.consent_title')}</h3>
            <p className="mt-2 text-xs text-muted-foreground leading-relaxed">
              {t('view.consent_desc')}
            </p>
            <div className="mt-4 flex gap-2 justify-end">
              <button
                onClick={voiceChat.dismissConsent}
                className="rounded-md border px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground"
              >
                {t('view.cancel')}
              </button>
              <button
                onClick={voiceChat.acceptConsent}
                className="rounded-md bg-accent px-3 py-1.5 text-xs font-medium text-accent-foreground hover:brightness-110"
              >
                {t('view.continue')}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
