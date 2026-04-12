/**
 * VoiceChatOverlay — V2 voice pipeline overlay UI.
 * Simpler than V1 overlay: states driven by server pipeline, no client-side phase management.
 *
 * Design ref: VOICE_PIPELINE_V2.md §8.2
 */
import { useEffect, useCallback } from 'react';
import { X, Mic, Loader2, Send } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { WaveformVisualizer } from './WaveformVisualizer';
import { cn } from '@/lib/utils';
import type { VoiceChatState } from '../hooks/useVoiceChat';

interface VoiceChatOverlayProps {
  state: VoiceChatState;
  sttText: string;
  aiText: string;
  error: string | null;
  onExit: () => void;
  onCancel: () => void;
}

const STATE_CONFIG: Record<VoiceChatState, { icon: typeof Mic; label: string; color: string }> = {
  inactive:  { icon: Mic,     label: 'voice.inactive',  color: 'text-muted-foreground' },
  listening: { icon: Mic,     label: 'voice.listening',  color: 'text-primary' },
  sending:   { icon: Send,    label: 'voice.sending',    color: 'text-amber-400' },
  receiving: { icon: Loader2, label: 'voice.receiving',  color: 'text-green-500' },
  error:     { icon: X,       label: 'voice.error',      color: 'text-destructive' },
};

export function VoiceChatOverlay({
  state,
  sttText,
  aiText,
  error,
  onExit,
  onCancel,
}: VoiceChatOverlayProps) {
  const { t } = useTranslation('voice');
  const config = STATE_CONFIG[state] || STATE_CONFIG.inactive;
  const Icon = config.icon;

  // Keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') onExit();
      if (e.key === ' ' && state === 'receiving') {
        e.preventDefault();
        onCancel();
      }
    },
    [state, onExit, onCancel],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="flex w-full max-w-md flex-col items-center gap-4 px-6">
        {/* Header */}
        <div className="flex w-full items-center justify-between">
          <div className="flex items-center gap-2">
            <Mic className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-white">
              {t('voice.voiceMode', 'Voice Mode')}
            </span>
          </div>
          <button
            onClick={onExit}
            className="rounded-full p-2 text-white/60 hover:bg-white/10 hover:text-white"
            aria-label="Exit voice mode"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Status indicator */}
        <div className="flex flex-col items-center gap-3">
          <div className={cn('rounded-full bg-white/5 p-4', config.color)}>
            <Icon className={cn('h-8 w-8', state === 'receiving' && 'animate-spin')} />
          </div>

          {/* Waveform — tap to cancel during receiving */}
          <div
            onClick={state === 'receiving' ? onCancel : undefined}
            className={state === 'receiving' ? 'cursor-pointer' : ''}
            role={state === 'receiving' ? 'button' : undefined}
            aria-label={state === 'receiving' ? 'Tap to stop' : undefined}
          >
            <WaveformVisualizer active={state === 'listening'} />
            {state === 'receiving' && (
              <p className="mt-1 text-center text-[10px] text-white/30 md:hidden">
                {t('voice.tapToStop', 'Tap to stop')}
              </p>
            )}
          </div>

          {/* State label */}
          <p className={cn('text-sm font-medium', config.color)}>
            {t(config.label, state)}
          </p>
        </div>

        {/* Transcript area */}
        <div className="w-full rounded-lg border border-white/10 bg-white/5 p-4 min-h-[80px] max-h-[200px] overflow-y-auto">
          {sttText && (
            <div className="mb-2">
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {t('voice.you', 'You')}
              </span>
              <p className="mt-0.5 text-sm text-white">{sttText}</p>
            </div>
          )}

          {aiText && (
            <div>
              <span className="text-[10px] uppercase tracking-wider text-muted-foreground">
                {t('voice.ai', 'AI')}
              </span>
              <p className="mt-0.5 text-sm text-white/80">{aiText}</p>
            </div>
          )}

          {!sttText && !aiText && (
            <p className="text-center text-sm text-white/30">
              {state === 'listening'
                ? t('voice.startSpeaking', 'Start speaking...')
                : ''}
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="rounded-md bg-red-400/10 px-3 py-1.5 text-xs text-red-400">
            {error}
          </p>
        )}

        {/* Controls */}
        <div className="flex items-center gap-3">
          {state === 'receiving' && (
            <button
              onClick={onCancel}
              className="inline-flex items-center gap-1.5 rounded-full border border-white/20 px-5 py-2.5 text-xs font-medium text-white/80 hover:bg-white/10 transition-colors"
            >
              {t('voice.cancel', 'Cancel')}
            </button>
          )}
          <button
            onClick={onExit}
            className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-5 py-2.5 text-xs font-medium text-red-400 hover:bg-red-500/20 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
            {t('voice.exitVoiceMode', 'Exit Voice Mode')}
          </button>
        </div>

        {/* Keyboard hints (desktop only) */}
        <p className="hidden text-[10px] text-white/20 md:block">
          Esc to exit &middot; Space to cancel
        </p>
      </div>
    </div>
  );
}
