import { useState, useCallback, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowUp, Brain, Eye, ListTodo, Pencil, Square, Zap, Mic, MicOff, Loader2, Volume2, VolumeX } from 'lucide-react';
import { loadVoicePrefs } from '../voicePrefs';
import { useVoiceAssistMic } from '../hooks/useVoiceAssistMic';
import { useMentionPicker } from '../hooks/useMentionPicker';
import TextareaAutosize from 'react-textarea-autosize';
import { ContextBar } from '../context/ContextBar';
import type { ContextItem } from '../context/types';
import { PromptTemplatePicker, type PromptTemplate } from './PromptTemplates';
import { MentionPopover } from './MentionPopover';

interface ChatInputBarProps {
  onSend: (content: string, thinking?: boolean) => void;
  onStop: () => void;
  isStreaming: boolean;
  disabled?: boolean;
  modelHint?: string;
  /** Whether the active model supports thinking mode */
  supportsThinking?: boolean;
  /** Session-level default thinking mode */
  thinkingDefault?: boolean;
  /** Called when user switches Think/Fast to persist to session */
  onThinkingModeChange?: (thinking: boolean) => void;
  /** Context items attached to the next message */
  contextItems: ContextItem[];
  onAttachContext: (item: ContextItem) => void;
  onDetachContext: (id: string) => void;
  onClearContext: () => void;
  /** When true, disable push-to-talk mic (voice mode owns STT) */
  voiceModeActive?: boolean;
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
  thinkingDefault,
  onThinkingModeChange,
  contextItems,
  onAttachContext,
  onDetachContext,
  onClearContext,
  voiceModeActive,
  voiceAssistOn,
  onToggleVoiceAssist,
  ttsPlaying,
  onStopTTS,
  permissionMode,
  onPermissionModeChange,
}: ChatInputBarProps) {
  const { t } = useTranslation('chat');
  const [value, setValue] = useState('');
  const [thinkingMode, setThinkingMode] = useState(thinkingDefault ?? false);
  const [responseFormat, setResponseFormat] = useState<string>('Auto');
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateFilter, setTemplateFilter] = useState('');
  const [attachPickerOpen, setAttachPickerOpen] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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
    const thinking = supportsThinking ? (forceThinking ?? thinkingMode) : undefined;
    const formatSuffix = FORMAT_INSTRUCTIONS[responseFormat] ?? '';
    onSend(text + formatSuffix, thinking);
  }

  const hasContext = contextItems.length > 0;

  return (
    <div className="shrink-0 border-t border-border bg-card px-4 py-3">
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
                onClick={() => setAttachPickerOpen(true)}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                title={t('input.attach_context')}
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" /></svg>
              </button>
              {/* Voice Assist toggle + Push-to-talk mic (hidden when voice mode overlay owns STT) */}
              {!voiceModeActive && (
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
              {/* RAID C2/B2 — Ask/Plan/Write permission-mode toggle. Ask =
                  read-only research surface; Plan = reads + PlanForge plan_*
                  tools (plan artifacts, no prose); Write = full surface + the
                  Tier-A approval prompt. Sent per message POST. */}
              {permissionMode !== undefined && onPermissionModeChange && (
                <div className="inline-flex rounded-md bg-secondary p-0.5 gap-0.5" data-testid="permission-mode-toggle">
                  <button
                    type="button"
                    onClick={() => onPermissionModeChange('ask')}
                    aria-pressed={permissionMode === 'ask'}
                    title={t('input.mode_ask_hint')}
                    className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      permissionMode === 'ask'
                        ? 'bg-sky-500/10 text-sky-400 border border-sky-500/30'
                        : 'text-muted-foreground'
                    }`}
                  >
                    <Eye className="h-2.5 w-2.5" />
                    {t('input.mode_ask')}
                  </button>
                  <button
                    type="button"
                    onClick={() => onPermissionModeChange('plan')}
                    aria-pressed={permissionMode === 'plan'}
                    title={t('input.mode_plan_hint')}
                    className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      permissionMode === 'plan'
                        ? 'bg-violet-500/10 text-violet-400 border border-violet-500/30'
                        : 'text-muted-foreground'
                    }`}
                  >
                    <ListTodo className="h-2.5 w-2.5" />
                    {t('input.mode_plan')}
                  </button>
                  <button
                    type="button"
                    onClick={() => onPermissionModeChange('write')}
                    aria-pressed={permissionMode === 'write'}
                    title={t('input.mode_write_hint')}
                    className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      permissionMode === 'write'
                        ? 'bg-accent/10 text-accent border border-accent/30'
                        : 'text-muted-foreground'
                    }`}
                  >
                    <Pencil className="h-2.5 w-2.5" />
                    {t('input.mode_write')}
                  </button>
                </div>
              )}
              {/* Think/Fast toggle */}
              {supportsThinking && (
                <div className="inline-flex rounded-md bg-secondary p-0.5 gap-0.5">
                  <button
                    type="button"
                    onClick={() => { setThinkingMode(true); onThinkingModeChange?.(true); }}
                    className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      thinkingMode
                        ? 'bg-[#1e1633] text-[#a78bfa] border border-[#3b2d6b]'
                        : 'text-muted-foreground'
                    }`}
                  >
                    <Brain className="h-2.5 w-2.5" />
                    {t('input.think')}
                  </button>
                  <button
                    type="button"
                    onClick={() => { setThinkingMode(false); onThinkingModeChange?.(false); }}
                    className={`flex items-center gap-1 rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                      !thinkingMode
                        ? 'bg-accent/10 text-accent border border-accent/30'
                        : 'text-muted-foreground'
                    }`}
                  >
                    <Zap className="h-2.5 w-2.5" />
                    {t('input.fast')}
                  </button>
                </div>
              )}
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
