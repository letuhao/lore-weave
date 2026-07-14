import { useState, useCallback, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp, ChevronDown, Eye, ListTodo, Pencil, Square, Mic, MicOff, Loader2, Volume2, VolumeX } from 'lucide-react';
import { loadVoicePrefs } from '../voicePrefs';
import { useVoiceAssistMic } from '../hooks/useVoiceAssistMic';
import { useMentionPicker } from '../hooks/useMentionPicker';
import TextareaAutosize from 'react-textarea-autosize';
import { ContextBar } from '../context/ContextBar';
import type { ContextItem } from '../context/types';
import { PromptTemplatePicker, type PromptTemplate } from './PromptTemplates';
import { type SlashCommandItem } from '../hooks/useSlashCommands';
import { MentionPopover } from './MentionPopover';

// W4 — the effort types/helpers moved to the shared AI-Task Standard module
// (@/components/ai-task/effort) so the chat composer and the one-shot generate
// dialogs share ONE mapping. Re-exported here so existing importers
// (useChatMessages, ChatView, runChatStream, the effort test) are unchanged.
import type { EffortLevel } from '@/components/ai-task/effort';
import { thinkingForLevel } from '@/components/ai-task/effort';
import { EffortSelect } from '@/components/ai-task';
export type { EffortLevel } from '@/components/ai-task/effort';
export { effortLevelFromGenerationParams, reasoningEffortForLevel } from '@/components/ai-task/effort';

interface ChatInputBarProps {
  onSend: (content: string, thinking?: boolean, reasoningEffort?: EffortLevel) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  modelHint?: string;
  /** Whether the active model supports thinking mode */
  supportsThinking?: boolean;
  /** Session-level default effort (derive via effortLevelFromGenerationParams). */
  effortDefault?: EffortLevel;
  /** Called when the user picks an effort level — the parent persists it on
   *  the session as {reasoning_effort, thinking:null} (reasoningEffortForLevel). */
  onEffortChange?: (level: EffortLevel) => void;
  /** Context items attached to the next message */
  contextItems: ContextItem[];
  onAttachContext: (item: ContextItem) => void;
  onDetachContext: (id: string) => void;
  onClearContext: () => void;
  /** When true, disable push-to-talk mic (voice mode owns STT) */
  voiceModeActive?: boolean;
  /** WS-4.5 — voice affordance gate. False hides ALL voice controls (push-to-talk
   *  + voice-assist) for session kinds where a voice turn wouldn't be captured/
   *  billed correctly yet (assistant sessions, until WS-4.1 lands). Defaults on. */
  voiceEnabled?: boolean;
  /** Voice Assist mode ON — mic highlighted, auto-TTS active */
  voiceAssistOn?: boolean;
  onToggleVoiceAssist?: () => void;
  /** Auto-TTS is playing — show stop button */
  ttsPlaying?: boolean;
  onStopTTS?: () => void;
  /** RAID C2/B2 — HITL permission mode (Ask = read-only tools, Plan = reads +
   *  PlanForge plan_* tools, Write = full). Rendered only when both are
   *  provided (embedded surfaces may omit). */
  permissionMode?: 'ask' | 'plan' | 'write';
  onPermissionModeChange?: (mode: 'ask' | 'plan' | 'write') => void;
}

export function ChatInputBar({
  onSend,
  onStop,
  isStreaming,
  disabled,
  modelHint,
  supportsThinking,
  effortDefault,
  onEffortChange,
  contextItems,
  onAttachContext,
  onDetachContext,
  onClearContext,
  voiceModeActive,
  voiceEnabled = true,
  voiceAssistOn,
  onToggleVoiceAssist,
  ttsPlaying,
  onStopTTS,
  permissionMode,
  onPermissionModeChange,
}: ChatInputBarProps) {
  const { t } = useTranslation('chat');
  const [value, setValue] = useState('');
  // W4 — the effort dropdown state (replaces the Think/Fast boolean pill).
  // 'fast' ≙ thinking:false, 'standard' ≙ thinking:true, 'deep' additionally
  // sends reasoning_effort:"deep". Initialized from the session default and
  // re-synced when it changes (session switch / settings-panel edit) — the
  // "previous default" render-time pattern, not a useEffect.
  const [effort, setEffort] = useState<EffortLevel>(effortDefault ?? 'off');
  const [prevEffortDefault, setPrevEffortDefault] = useState(effortDefault);
  if (effortDefault !== prevEffortDefault) {
    setPrevEffortDefault(effortDefault);
    setEffort(effortDefault ?? 'off');
  }
  const [responseFormat, setResponseFormat] = useState<string>('Auto');
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateFilter, setTemplateFilter] = useState('');
  const [attachPickerOpen, setAttachPickerOpen] = useState(false);
  // Which composer dropdown is open (the effort dropdown moved to the shared
  // EffortSelect, which self-manages; only the mode dropdown uses this now).
  const [openMenu, setOpenMenu] = useState<'mode' | null>(null);
  const menusRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Close the effort/mode dropdown on outside click (same pattern as the
  // message "more" dropdown).
  useEffect(() => {
    if (!openMenu) return;
    function handleClick(e: MouseEvent) {
      if (menusRef.current && !menusRef.current.contains(e.target as Node)) setOpenMenu(null);
    }
    window.addEventListener('mousedown', handleClick);
    return () => window.removeEventListener('mousedown', handleClick);
  }, [openMenu]);

  // Inline @-mention context attach — reuses the ContextPicker's attach seam.
  const mention = useMentionPicker({
    value,
    onAttach: onAttachContext,
    onValueChange: setValue,
    textareaRef,
  });

  // Push-to-talk mic — uses same VAD + backend STT pipeline as Voice Mode.
  // Captures speech via Silero VAD → WAV → backend STT → inserts transcript into textarea.
  const { micState, toggleMic } = useVoiceAssistMic(
    useCallback((text: string) => {
      const append = loadVoicePrefs().voiceAssistAppend;
      setValue((prev) => (append && prev) ? prev + ' ' + text : text);
    }, []),
  );

  function handleTemplateSelect(template: PromptTemplate) {
    setValue(template.prompt);
    setShowTemplates(false);
    setTemplateFilter('');
  }

  // D-REG-P4 — a registry command COMPLETES the `/name ` token (the server expands it
  // on send); unlike a template, it doesn't replace the input with a prompt body.
  function handleCommandSelect(cmd: SlashCommandItem) {
    setValue(`/${cmd.name} `);
    setShowTemplates(false);
    setTemplateFilter('');
    textareaRef.current?.focus();
  }

  function handleValueChange(newValue: string) {
    setValue(newValue);
    // "/" at start of input triggers template picker
    if (newValue.startsWith('/')) {
      setShowTemplates(true);
      setTemplateFilter(newValue.slice(1));
    } else {
      setShowTemplates(false);
      setTemplateFilter('');
    }
  }

  const FORMAT_INSTRUCTIONS: Record<string, string> = {
    Auto: '',
    Concise: '\n\n[Respond concisely in 2-3 sentences maximum.]',
    Detailed: '\n\n[Provide a detailed, thorough response with examples.]',
    Bullets: '\n\n[Format your response as bullet points.]',
    Table: '\n\n[Format your response as a markdown table where applicable.]',
  };

  function handleSubmit(forceThinking?: boolean) {
    const text = value.trim();
    if (!text || isStreaming) return;
    setValue('');
    // The keyboard force-shortcuts (Ctrl+Shift+Enter think / Ctrl+Enter fast)
    // override the dropdown for this one send, mapping onto medium/off (never the
    // max 'high' — that stays an explicit dropdown pick). The unified 5-level
    // effort rides the wire directly (reasoning_effort); chat-service maps it.
    const effectiveEffort: EffortLevel | undefined = !supportsThinking
      ? undefined
      : forceThinking != null
        ? (forceThinking ? 'medium' : 'off')
        : effort;
    const thinking = effectiveEffort != null ? thinkingForLevel(effectiveEffort) : undefined;
    const formatSuffix = FORMAT_INSTRUCTIONS[responseFormat] ?? '';
    onSend(text + formatSuffix, thinking, effectiveEffort);
  }

  // W4: mode selection + Ctrl+. cycling (Claude Code shift-tab pattern —
  // documented in the dropdown footer). Order: ask → plan → write → ask.
  const MODE_ORDER: Array<'ask' | 'plan' | 'write'> = ['ask', 'plan', 'write'];
  const cycleMode = useCallback(() => {
    if (permissionMode === undefined || !onPermissionModeChange) return;
    const idx = MODE_ORDER.indexOf(permissionMode);
    onPermissionModeChange(MODE_ORDER[(idx + 1) % MODE_ORDER.length]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [permissionMode, onPermissionModeChange]);

  function handleBarKeyDown(e: React.KeyboardEvent) {
    if (e.ctrlKey && !e.shiftKey && !e.altKey && e.key === '.') {
      e.preventDefault();
      cycleMode();
    }
  }

  const hasContext = contextItems.length > 0;

  return (
    // W4: Ctrl+. cycles the permission mode from anywhere inside the input bar
    // (keydown bubbles here from the textarea and the dropdowns).
    <div className="shrink-0 border-t border-border bg-card px-4 py-3" onKeyDown={handleBarKeyDown}>
      <div className="mx-auto min-w-0 max-w-full md:max-w-[720px] 2xl:max-w-[900px]">
        {/* Format pills */}
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] text-muted-foreground">{t('input.format')}</span>
          {['Auto', 'Concise', 'Detailed', 'Bullets', 'Table'].map((fmt) => (
            <button
              key={fmt}
              type="button"
              onClick={() => setResponseFormat(fmt)}
              className={`rounded-full border px-2.5 py-0.5 text-[10px] transition-colors ${
                responseFormat === fmt
                  ? 'border-accent/50 bg-accent/10 text-accent'
                  : 'border-border text-muted-foreground hover:border-border hover:text-foreground'
              }`}
            >
              {t(`input.format_opt.${fmt.toLowerCase()}`)}
            </button>
          ))}
        </div>

        <div className="relative overflow-visible rounded-[10px] border border-border bg-background focus-within:border-ring focus-within:shadow-[0_0_0_3px_rgba(212,149,42,0.2)]">
          {/* Prompt template picker (triggered by "/") */}
          <PromptTemplatePicker
            open={showTemplates}
            filter={templateFilter}
            onSelectCommand={handleCommandSelect}
            onSelect={handleTemplateSelect}
            onClose={() => { setShowTemplates(false); setTemplateFilter(''); }}
          />

          {/* Inline @-mention context popover (triggered by "@") */}
          <MentionPopover
            open={mention.open}
            items={mention.filtered}
            selectedIndex={mention.selectedIndex}
            onSelect={mention.attachCandidate}
            onHighlight={mention.setSelectedIndex}
          />

          {/* Context bar (pills + attach button) */}
          <ContextBar
            items={contextItems}
            onAttach={onAttachContext}
            onDetach={onDetachContext}
            onClearAll={onClearContext}
            externalPickerOpen={attachPickerOpen}
            onExternalPickerClose={() => setAttachPickerOpen(false)}
          />

          {/* Textarea */}
          <TextareaAutosize
            data-testid="chat-input-textarea"
            ref={textareaRef}
            value={value}
            onChange={(e) => { handleValueChange(e.target.value); mention.syncFromInput(e.target); }}
            onSelect={(e) => mention.syncFromInput(e.currentTarget)}
            placeholder={t('input.placeholder')}
            minRows={3}
            maxRows={8}
            disabled={disabled || isStreaming || voiceModeActive}
            onKeyDown={(e) => {
              // @-mention popover consumes navigation/attach keys (Enter must NOT send)
              if (mention.handleKeyDown(e)) return;
              if (e.key === 'Enter' && !e.shiftKey && !e.ctrlKey) {
                e.preventDefault();
                handleSubmit();
              }
              // Ctrl+Shift+Enter = force Think mode
              if (e.key === 'Enter' && e.ctrlKey && e.shiftKey && supportsThinking) {
                e.preventDefault();
                handleSubmit(true);
              }
              // Ctrl+Enter = force Fast mode
              if (e.key === 'Enter' && e.ctrlKey && !e.shiftKey) {
                e.preventDefault();
                handleSubmit(false);
              }
            }}
            className="w-full resize-none border-none bg-transparent px-3.5 py-3 text-sm leading-relaxed text-foreground placeholder:text-muted-foreground/50 focus:outline-none disabled:opacity-50"
          />

          {/* Bottom row: attach + mode toggle + send */}
          <div className="flex flex-wrap items-center justify-between gap-y-1.5 px-2 pb-2">
            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
              {/* Attach context button */}
              <button
                type="button"
                data-testid="chat-attach-context"
                onClick={() => setAttachPickerOpen(true)}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                title={t('input.attach_context')}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" /></svg>
              </button>
              {/* Voice Assist toggle + Push-to-talk mic (hidden when voice mode overlay
                  owns STT, or when voice is gated off for this session kind — WS-4.5) */}
              {!voiceModeActive && voiceEnabled && (
                <div className="flex items-center gap-0.5">
                  {/* Voice Assist ON/OFF toggle */}
                  {onToggleVoiceAssist && (
                    <button
                      type="button"
                      onClick={onToggleVoiceAssist}
                      className={`rounded-md px-2 py-1 text-[10px] font-medium transition-colors ${
                        voiceAssistOn
                          ? 'bg-primary/15 text-primary'
                          : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                      }`}
                      title={voiceAssistOn ? t('input.voice_assist_on') : t('input.voice_assist_off')}
                      aria-label={t('input.toggle_voice_assist')}
                      aria-pressed={!!voiceAssistOn}
                    >
                      {voiceAssistOn
                        ? <><Volume2 className="mr-1 inline h-3 w-3" />{t('input.assist')}</>
                        : <><VolumeX className="mr-1 inline h-3 w-3" />{t('input.assist')}</>}
                    </button>
                  )}
                  {/* Push-to-talk mic — VAD + backend STT (same pipeline as Voice Mode) */}
                  <button
                    type="button"
                    onClick={toggleMic}
                    disabled={micState === 'transcribing' || micState === 'activating'}
                    className={`rounded-md p-1.5 transition-colors ${
                      micState === 'listening'
                        ? 'bg-red-500/10 text-red-500 animate-pulse'
                        : micState === 'activating'
                          ? 'text-amber-400'
                          : micState === 'transcribing'
                            ? 'text-amber-400'
                            : micState === 'error'
                              ? 'text-red-500'
                              : voiceAssistOn
                                ? 'bg-primary/10 text-primary hover:bg-primary/20'
                                : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                    }`}
                    title={
                      micState === 'activating' ? t('input.mic_starting') :
                      micState === 'listening' ? t('input.mic_listening') :
                      micState === 'transcribing' ? t('input.mic_transcribing') :
                      micState === 'error' ? t('input.mic_error') :
                      voiceAssistOn ? t('input.mic_speak') : t('input.mic_input')
                    }
                    aria-label={micState === 'listening' ? t('input.stop_recording') : t('input.mic_input')}
                  >
                    {micState === 'listening' ? <MicOff className="h-4 w-4" /> :
                     micState === 'activating' || micState === 'transcribing' ? <Loader2 className="h-4 w-4 animate-spin" /> :
                     <Mic className="h-4 w-4" />}
                  </button>
                </div>
              )}
              {/* Stop TTS button (Voice Assist auto-TTS) */}
              {ttsPlaying && onStopTTS && (
                <button
                  type="button"
                  onClick={onStopTTS}
                  className="rounded-md bg-red-500/10 px-2 py-1 text-[10px] font-medium text-red-400 hover:bg-red-500/20 transition-colors"
                >
                  {t('input.stop_audio')}
                </button>
              )}
              {/* W4 — the two compact composer dropdowns (replace the two
                  segmented pills; saves the input-bar row). One shared ref
                  container so outside-click closes either menu. */}
              <div ref={menusRef} className="flex items-center gap-1.5">
                {/* RAID C2/B2 — Ask/Plan/Write permission mode, now ONE dropdown.
                    Trigger = persistent colored icon + one-word label (Claude
                    Code pattern); menu lists the 3 modes with hint lines;
                    Ctrl+. cycles (documented in the menu footer). */}
                {permissionMode !== undefined && onPermissionModeChange && (
                  <div className="relative">
                    <button
                      type="button"
                      data-testid="permission-mode-toggle"
                      onClick={() => setOpenMenu((m) => (m === 'mode' ? null : 'mode'))}
                      aria-haspopup="menu"
                      aria-expanded={openMenu === 'mode'}
                      title={t(`input.mode_${permissionMode}_hint`)}
                      className={`flex items-center gap-1 rounded-md border px-2.5 py-1 text-[11px] font-medium transition-colors ${
                        permissionMode === 'ask'
                          ? 'border-sky-500/30 bg-sky-500/10 text-sky-400'
                          : permissionMode === 'plan'
                            ? 'border-violet-500/30 bg-violet-500/10 text-violet-400'
                            : 'border-accent/30 bg-accent/10 text-accent'
                      }`}
                    >
                      {permissionMode === 'ask' ? <Eye className="h-2.5 w-2.5" /> : permissionMode === 'plan' ? <ListTodo className="h-2.5 w-2.5" /> : <Pencil className="h-2.5 w-2.5" />}
                      {t(`input.mode_${permissionMode}`)}
                      <ChevronDown className="h-2.5 w-2.5 opacity-60" />
                    </button>
                    {openMenu === 'mode' && (
                      <div role="menu" data-testid="permission-mode-menu" className="absolute bottom-full left-0 z-20 mb-1 w-64 rounded-md border border-border bg-card py-1 shadow-lg">
                        {([
                          { mode: 'ask' as const, Icon: Eye, color: 'text-sky-400' },
                          { mode: 'plan' as const, Icon: ListTodo, color: 'text-violet-400' },
                          { mode: 'write' as const, Icon: Pencil, color: 'text-accent' },
                        ]).map(({ mode, Icon, color }) => (
                          <button
                            key={mode}
                            type="button"
                            role="menuitemradio"
                            aria-checked={permissionMode === mode}
                            data-testid={`mode-opt-${mode}`}
                            onClick={() => { onPermissionModeChange(mode); setOpenMenu(null); }}
                            className={`flex w-full items-start gap-2 px-3 py-1.5 text-left hover:bg-secondary ${
                              permissionMode === mode ? 'bg-secondary/60' : ''
                            }`}
                          >
                            <Icon className={`mt-0.5 h-3 w-3 shrink-0 ${color}`} />
                            <span className="min-w-0">
                              <span className={`block text-[11px] font-medium ${color}`}>{t(`input.mode_${mode}`)}</span>
                              <span className="block text-[10px] leading-snug text-muted-foreground">{t(`input.mode_${mode}_hint`)}</span>
                            </span>
                          </button>
                        ))}
                        <p className="mt-1 border-t border-border px-3 pt-1 text-[9px] text-muted-foreground/70">
                          {t('input.mode_cycle_hint')}
                        </p>
                      </div>
                    )}
                  </div>
                )}
                {/* Effort/reasoning — the shared AI-task EffortSelect (unified
                    5-level vocab). Hidden when the model can't think, exactly like
                    the old pill — never forces thinking. */}
                {supportsThinking && (
                  <EffortSelect
                    value={effort}
                    onChange={(level) => { setEffort(level); onEffortChange?.(level); }}
                  />
                )}
              </div>
            </div>

            {/* Send / Stop button */}
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                title={t('input.stop_generating')}
                className="flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-destructive text-destructive-foreground transition-colors hover:bg-destructive/90"
              >
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                data-testid="chat-send-button"
                onClick={() => handleSubmit()}
                disabled={!value.trim() || disabled}
                title={t('input.send')}
                className="flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          {hasContext ? t('input.context_attached') : ''}
          {modelHint ? `${modelHint} · ` : ''}{t('input.hint')}
          {supportsThinking ? t('input.hint_thinking') : ''}
        </p>
      </div>
    </div>
  );
}
