import { useEffect, useCallback } from 'react';
import { X, Pause, Play, Settings2, Loader2, Volume2, Mic } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import type { VoicePhase } from '../hooks/useVoiceMode';
import { WaveformVisualizer } from './WaveformVisualizer';
import { cn } from '@/lib/utils';

interface VoiceModeOverlayProps {
  phase: VoicePhase;
  userTranscript: string;
  interimText: string;
  aiResponseText: string;
  error: string | null;
  onExit: () => void;
  onPause: () => void;
  onResume: () => void;
  onOpenSettings: () => void;
}

const PHASE_CONFIG: Record<VoicePhase, { icon: typeof Mic; label: string; color: string }> = {
  idle: { icon: Mic, label: 'voice.listening', color: 'text-muted-foreground' },
  listening: { icon: Mic, label: 'voice.listening', color: 'text-primary' },
  processing: { icon: Loader2, label: 'voice.processing', color: 'text-amber-400' },
  speaking: { icon: Volume2, label: 'voice.speaking', color: 'text-green-500' },
  paused: { icon: Pause, label: 'voice.paused', color: 'text-muted-foreground' },
};

export function VoiceModeOverlay({
  phase,
  userTranscript,
  interimText,
  aiResponseText,
  error,
  onExit,
  onPause,
  onResume,
  onOpenSettings,
}: VoiceModeOverlayProps) {
  const { t } = useTranslation('common');

  // Keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault();
        onExit();
      }
      if (e.key === ' ' && e.target === document.body) {
        e.preventDefault();
        if (phase === 'paused') onResume();
        else if (phase === 'listening') onPause();
      }
    },
    [phase, onExit, onPause, onResume],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  const config = PHASE_CONFIG[phase] || PHASE_CONFIG.idle;
  const PhaseIcon = config.icon;
  const isListening = phase === 'listening';
  const isPaused = phase === 'paused';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm">
      <div className="w-full max-w-lg mx-4 flex flex-col items-center gap-6">

        {/* Top controls */}
        <div className="w-full flex items-center justify-between">
          <button
            onClick={onOpenSettings}
            className="rounded-md p-2 text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors"
            title="Voice Settings"
          >
            <Settings2 className="h-4 w-4" />
          </button>
          <h2 className="text-sm font-medium text-white/80">{t('voice.voiceMode')}</h2>
          <button
            onClick={onExit}
            className="rounded-md p-2 text-muted-foreground hover:text-foreground hover:bg-white/10 transition-colors"
            title="Exit Voice Mode (Esc)"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        {/* Phase indicator */}
        <div className="flex flex-col items-center gap-3">
          <div className={cn(
            'flex items-center justify-center w-20 h-20 rounded-full border-2 transition-colors',
            isListening && 'border-primary bg-primary/10',
            phase === 'processing' && 'border-amber-400 bg-amber-400/10',
            phase === 'speaking' && 'border-green-500 bg-green-500/10',
            isPaused && 'border-border bg-border/10',
          )}>
            <PhaseIcon className={cn(
              'h-8 w-8',
              config.color,
              phase === 'processing' && 'animate-spin',
            )} />
          </div>

          {/* Waveform */}
          <WaveformVisualizer active={isListening} />

          {/* Phase label */}
          <p className={cn('text-sm font-medium', config.color)}>
            {t(config.label)}
          </p>
        </div>

        {/* Transcript area */}
        <div className="w-full rounded-lg border border-white/10 bg-white/5 p-4 min-h-[80px] max-h-[200px] overflow-y-auto">
          {/* User's speech */}
          {(userTranscript || interimText) && (
            <div className="mb-2">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">You</span>
              <p className="text-sm text-white mt-0.5">
                {userTranscript}
                {interimText && (
                  <span className="text-white/40 italic"> {interimText}</span>
                )}
              </p>
            </div>
          )}

          {/* AI response */}
          {aiResponseText && (
            <div>
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">AI</span>
              <p className="text-sm text-white/80 mt-0.5 whitespace-pre-wrap">
                {aiResponseText}
              </p>
            </div>
          )}

          {/* Empty state */}
          {!userTranscript && !interimText && !aiResponseText && (
            <p className="text-sm text-white/30 text-center">
              {isListening ? 'Start speaking...' : isPaused ? 'Paused' : ''}
            </p>
          )}
        </div>

        {/* Error */}
        {error && (
          <p className="text-xs text-red-400 bg-red-400/10 rounded-md px-3 py-1.5">{error}</p>
        )}

        {/* Bottom controls */}
        <div className="flex items-center gap-3">
          {/* Pause / Resume */}
          <button
            onClick={isPaused ? onResume : onPause}
            disabled={phase === 'processing' || phase === 'speaking'}
            className="inline-flex items-center gap-1.5 rounded-full border border-white/20 px-5 py-2.5 text-xs font-medium text-white/80 hover:bg-white/10 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
          >
            {isPaused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
            {t('voice.pauseResume')}
          </button>

          {/* Exit */}
          <button
            onClick={onExit}
            className="inline-flex items-center gap-1.5 rounded-full border border-red-500/30 bg-red-500/10 px-5 py-2.5 text-xs font-medium text-red-400 hover:bg-red-500/20 transition-colors"
          >
            <X className="h-3.5 w-3.5" />
            {t('voice.exitVoiceMode')}
          </button>
        </div>

        {/* Keyboard hints */}
        <p className="text-[10px] text-white/20">
          Esc to exit &middot; Space to pause/resume
        </p>
      </div>
    </div>
  );
}
