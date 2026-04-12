/**
 * PipelineIndicator — visual debug overlay showing voice pipeline state machine.
 * Shows each step with timing, current phase highlighted, errors marked.
 */
import { cn } from '@/lib/utils';
import type { PipelineSnapshot, PipelinePhase } from '@/lib/VoicePipelineState';

const PHASE_ICONS: Record<PipelinePhase, string> = {
  idle: '⏹',
  activating: '⏳',
  listening: '🎤',
  sending: '📤',
  transcribing: '📝',
  thinking: '🧠',
  speaking: '🔊',
  error: '❌',
};

const PHASE_COLORS: Record<PipelinePhase, string> = {
  idle: 'text-muted-foreground',
  activating: 'text-amber-400',
  listening: 'text-primary',
  sending: 'text-amber-400',
  transcribing: 'text-blue-400',
  thinking: 'text-purple-400',
  speaking: 'text-green-400',
  error: 'text-red-500',
};

interface PipelineIndicatorProps {
  snapshot: PipelineSnapshot;
}

export function PipelineIndicator({ snapshot }: PipelineIndicatorProps) {
  const { phase, steps, sttText, aiText, error, turnIndex } = snapshot;

  return (
    <div className="w-full rounded-lg border border-white/10 bg-black/40 px-3 py-2 font-mono text-[10px]">
      {/* Current phase */}
      <div className="flex items-center justify-between mb-1">
        <span className={cn('font-bold', PHASE_COLORS[phase])}>
          {PHASE_ICONS[phase]} {phase.toUpperCase()}
        </span>
        <span className="text-white/30">Turn #{turnIndex}</span>
      </div>

      {/* Step timeline */}
      {steps.length > 0 && (
        <div className="space-y-0.5 mb-1">
          {steps.map((step, i) => {
            const duration = step.completedAt && step.startedAt
              ? step.completedAt - step.startedAt
              : step.startedAt
                ? Date.now() - step.startedAt
                : 0;
            const isActive = i === steps.length - 1 && !step.completedAt;

            return (
              <div key={i} className="flex items-center gap-1.5">
                <span className={cn(
                  'w-1.5 h-1.5 rounded-full flex-shrink-0',
                  step.error ? 'bg-red-500' :
                  step.completedAt ? 'bg-emerald-400' :
                  isActive ? 'bg-amber-400 animate-pulse' : 'bg-white/20',
                )} />
                <span className={cn(
                  'flex-1',
                  isActive ? 'text-white/80' : 'text-white/40',
                )}>
                  {step.label}
                </span>
                <span className="text-white/30">
                  {duration > 0 ? `${duration}ms` : '...'}
                </span>
              </div>
            );
          })}
        </div>
      )}

      {/* Transcript preview */}
      {sttText && (
        <div className="text-white/50 truncate">
          You: {sttText}
        </div>
      )}
      {aiText && (
        <div className="text-white/40 truncate">
          AI: {aiText.slice(-80)}
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="text-red-400 mt-0.5">
          {error}
        </div>
      )}
    </div>
  );
}
