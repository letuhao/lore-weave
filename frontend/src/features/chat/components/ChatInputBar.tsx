import { useState, useCallback, useRef, useEffect } from 'react';
import { ArrowUp, Brain, Square, Zap, Mic, MicOff, Loader2 } from 'lucide-react';
import { useSpeechRecognition, SPEECH_RECOGNITION_SUPPORTED } from '@/hooks/useSpeechRecognition';
import { MEDIA_RECORDER_SUPPORTED } from '@/hooks/useBackendSTT';
import { useAuth } from '@/auth';
import { loadVoicePrefs } from '../voicePrefs';
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
  /** When true, disable push-to-talk mic (voice mode owns STT) */
  voiceModeActive?: boolean;
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
}: ChatInputBarProps) {
  const [value, setValue] = useState('');
  const [thinkingMode, setThinkingMode] = useState(thinkingDefault ?? false);
  const [responseFormat, setResponseFormat] = useState<string>('Auto');
  const [showTemplates, setShowTemplates] = useState(false);
  const [templateFilter, setTemplateFilter] = useState('');
  const [attachPickerOpen, setAttachPickerOpen] = useState(false);

  // Push-to-talk mic — inserts transcript into textarea (does NOT auto-send)
  // Supports both browser Web Speech API and backend STT via provider-registry
  const { accessToken } = useAuth();
  const [micState, setMicState] = useState<'idle' | 'recording' | 'transcribing' | 'error'>('idle');
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const stt = useSpeechRecognition({
    continuous: false,
    interimResults: true,
    onFinalTranscript: useCallback((text: string) => {
      setValue((prev) => (prev ? prev + ' ' + text : text));
      setMicState('idle');
    }, []),
  });

  const toggleMic = useCallback(async () => {
    if (micState === 'recording' || micState === 'transcribing') {
      // Stop
      stt.stop();
      mediaRecorderRef.current?.stop();
      setMicState('idle');
      return;
    }

    const prefs = loadVoicePrefs();
    if (prefs.sttSource === 'ai_model' && prefs.sttModelRef && MEDIA_RECORDER_SUPPORTED) {
      // Backend STT via provider-registry proxy
      setMicState('recording');
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        // Choose supported MIME type (Safari doesn't support webm)
        const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm'
          : MediaRecorder.isTypeSupported('audio/mp4') ? 'audio/mp4' : '';
        const recorder = mimeType
          ? new MediaRecorder(stream, { mimeType })
          : new MediaRecorder(stream);
        const ext = mimeType.includes('mp4') ? 'mp4' : 'webm';
        mediaRecorderRef.current = recorder;
        const chunks: Blob[] = [];
        recorder.ondataavailable = (e) => { if (e.data.size > 0) chunks.push(e.data); };
        recorder.onstop = async () => {
          stream.getTracks().forEach((t) => t.stop());
          mediaRecorderRef.current = null;
          if (chunks.length === 0) { setMicState('idle'); return; }
          setMicState('transcribing');
          try {
            const blob = new Blob(chunks, { type: mimeType || 'audio/webm' });
            const apiBase = import.meta.env.VITE_API_BASE || '';
            const params = new URLSearchParams({
              model_source: 'user_model',
              model_ref: prefs.sttModelRef,
            });
            const formData = new FormData();
            formData.append('file', blob, `audio.${ext}`);
            const resp = await fetch(
              `${apiBase}/v1/model-registry/proxy/v1/audio/transcriptions?${params}`,
              { method: 'POST', headers: { Authorization: `Bearer ${accessToken}` }, body: formData },
            );
            if (resp.ok) {
              const result = await resp.json();
              const text = result.text || '';
              if (text.trim()) setValue((prev) => (prev ? prev + ' ' + text : text));
            } else {
              setMicState('error');
              setTimeout(() => setMicState('idle'), 2000);
              return;
            }
          } catch {
            setMicState('error');
            setTimeout(() => setMicState('idle'), 2000);
            return;
          }
          setMicState('idle');
        };
        recorder.start();
        // Auto-stop after 30s
        setTimeout(() => { if (recorder.state === 'recording') recorder.stop(); }, 30000);
      } catch {
        setMicState('error');
        setTimeout(() => setMicState('idle'), 2000);
      }
    } else if (SPEECH_RECOGNITION_SUPPORTED) {
      // Browser Web Speech API
      stt.resetTranscript();
      stt.start();
      setMicState('recording');
    }
  }, [micState, stt, accessToken]);

  // Cleanup mic on unmount
  useEffect(() => {
    return () => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === 'recording') {
        mediaRecorderRef.current.stop();
      }
    };
  }, []);

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
        <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
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
              {/* Push-to-talk mic button — 4 states (hidden when voice mode owns STT) */}
              {(SPEECH_RECOGNITION_SUPPORTED || MEDIA_RECORDER_SUPPORTED) && !voiceModeActive && (
                <button
                  type="button"
                  onClick={toggleMic}
                  disabled={micState === 'transcribing'}
                  className={`rounded-md p-1.5 transition-colors ${
                    micState === 'recording'
                      ? 'bg-red-500/10 text-red-500 animate-pulse'
                      : micState === 'transcribing'
                        ? 'text-amber-400'
                        : micState === 'error'
                          ? 'text-red-500'
                          : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
                  }`}
                  title={
                    micState === 'recording' ? 'Stop recording' :
                    micState === 'transcribing' ? 'Transcribing...' :
                    micState === 'error' ? 'Microphone error' : 'Voice input'
                  }
                  aria-label={micState === 'recording' ? 'Stop recording' : 'Voice input'}
                >
                  {micState === 'recording' ? <MicOff className="h-4 w-4" /> :
                   micState === 'transcribing' ? <Loader2 className="h-4 w-4 animate-spin" /> :
                   <Mic className="h-4 w-4" />}
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
