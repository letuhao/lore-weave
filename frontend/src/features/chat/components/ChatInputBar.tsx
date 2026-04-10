import { useState, useCallback } from 'react';
import { ArrowUp, Brain, Square, Zap, Mic, MicOff } from 'lucide-react';
import { useSpeechRecognition, SPEECH_RECOGNITION_SUPPORTED } from '@/hooks/useSpeechRecognition';
import TextareaAutosize from 'react-textarea-autosize';
import { ContextBar } from '../context/ContextBar';
import type { ContextItem } from '../context/types';
import { PromptTemplatePicker, type PromptTemplate } from './PromptTemplates';

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
}: ChatInputBarProps) {
  const [value, setValue] = useState('');
  const [thinkingMode, setThinkingMode] = useState(thinkingDefault ?? false);
  const [responseFormat, setResponseFormat] = useState<string>('Auto');
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateFilter, setTemplateFilter] = useState('');
  const [attachPickerOpen, setAttachPickerOpen] = useState(false);

  // Push-to-talk mic — inserts transcript into textarea (does NOT auto-send)
  const [micActive, setMicActive] = useState(false);
  const stt = useSpeechRecognition({
    continuous: false,
    interimResults: true,
    onFinalTranscript: useCallback((text: string) => {
      setValue((prev) => (prev ? prev + ' ' + text : text));
      setMicActive(false);
    }, []),
  });

  const toggleMic = useCallback(() => {
    if (micActive) {
      stt.stop();
      setMicActive(false);
    } else {
      stt.resetTranscript();
      stt.start();
      setMicActive(true);
    }
  }, [micActive, stt]);

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
    <div className="shrink-0 border-t border-border bg-card px-8 py-4">
      <div className="mx-auto max-w-full px-4 md:max-w-[720px] 2xl:max-w-[900px]">
        {/* Format pills */}
        <div className="mb-1.5 flex items-center gap-1.5">
          <span className="text-[10px] text-muted-foreground">Format:</span>
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
              {fmt}
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
            value={value}
            onChange={(e) => handleValueChange(e.target.value)}
            placeholder="Ask about your story, characters, world-building..."
            minRows={3}
            maxRows={8}
            disabled={disabled || isStreaming}
            onKeyDown={(e) => {
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
          <div className="flex items-center justify-between px-2 pb-2">
            <div className="flex items-center gap-2">
              {/* Attach context button */}
              <button
                type="button"
                onClick={() => setAttachPickerOpen(true)}
                className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                title="Attach context"
              >
                <svg className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24"><path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66l-9.2 9.19a2 2 0 01-2.83-2.83l8.49-8.48" /></svg>
              </button>
              {/* Push-to-talk mic button */}
              {SPEECH_RECOGNITION_SUPPORTED && (
                <button
                  type="button"
                  onClick={toggleMic}
                  className={`rounded-md p-1.5 transition-colors ${
                    micActive
                      ? 'bg-red-500/10 text-red-500 animate-pulse'
                      : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                  }`}
                  title={micActive ? 'Stop recording' : 'Voice input'}
                >
                  {micActive ? <MicOff className="h-4 w-4" /> : <Mic className="h-4 w-4" />}
                </button>
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
                    Think
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
                    Fast
                  </button>
                </div>
              )}
            </div>

            {/* Send / Stop button */}
            {isStreaming ? (
              <button
                type="button"
                onClick={onStop}
                title="Stop generating (Esc)"
                className="flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-destructive text-destructive-foreground transition-colors hover:bg-destructive/90"
              >
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => handleSubmit()}
                disabled={!value.trim() || disabled}
                title="Send (Enter)"
                className="flex h-[34px] w-[34px] items-center justify-center rounded-lg bg-primary text-primary-foreground transition-colors hover:brightness-110 disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
        </div>
        <p className="mt-1.5 text-center text-[10px] text-muted-foreground">
          {hasContext ? 'Context attached · ' : ''}
          {modelHint ? `${modelHint} · ` : ''}Enter to send &middot; Shift+Enter for new line
          {supportsThinking ? ' · Ctrl+Shift+Enter think · Ctrl+Enter fast' : ''}
        </p>
      </div>
    </div>
  );
}
