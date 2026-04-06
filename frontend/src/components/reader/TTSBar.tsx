import { useTTSState, useTTSControls, type AudioSource } from '@/hooks/useTTS';
import { Play, Pause, SkipBack, SkipForward, X } from 'lucide-react';
import { cn } from '@/lib/utils';

const SOURCE_COLORS: Record<AudioSource, string> = {
  attached: '#8b5cf6',
  ai: '#5496e8',
  browser: '#9e9488',
  inline: '#8b5cf6',
};

const SOURCE_LABELS: Record<AudioSource, string> = {
  attached: 'Attached',
  ai: 'AI TTS',
  browser: 'Browser',
  inline: 'Audio',
};

const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 2];

function formatTime(ms: number): string {
  const totalSec = Math.round(ms / 1000);
  const m = Math.floor(totalSec / 60);
  const s = totalSec % 60;
  return `${m}:${s.toString().padStart(2, '0')}`;
}

interface TTSBarProps {
  /** Text preview of the currently active block */
  activeBlockText?: string;
}

export function TTSBar({ activeBlockText }: TTSBarProps) {
  const state = useTTSState();
  const controls = useTTSControls();

  if (state.status === 'idle') return null;

  const sourceColor = SOURCE_COLORS[state.source || 'browser'];
  const sourceLabel = SOURCE_LABELS[state.source || 'browser'];
  const isPlaying = state.status === 'playing';
  const hasProgress = state.durationMs > 0;
  const progressPct = hasProgress ? Math.min(100, (state.currentMs / state.durationMs) * 100) : 0;

  const cycleSpeed = () => {
    const idx = SPEEDS.indexOf(state.speed);
    const next = SPEEDS[(idx + 1) % SPEEDS.length];
    controls.setSpeed(next);
  };

  return (
    <div
      className="fixed bottom-12 left-1/2 z-30 flex w-[min(520px,calc(100vw-32px))] -translate-x-1/2 items-center gap-2 rounded-xl border px-3 py-2 shadow-lg"
      style={{
        background: 'hsl(var(--card) / 0.95)',
        backdropFilter: 'blur(12px)',
        borderColor: `${sourceColor}40`,
      }}
    >
      {/* Source color indicator line */}
      <div
        className="absolute left-3 right-3 top-0 h-[2px] rounded-full"
        style={{ background: sourceColor }}
      />

      {/* Prev block */}
      <button
        type="button"
        onClick={controls.prevBlock}
        className="rounded p-1 text-muted-foreground transition hover:text-foreground"
        title="Previous block (Shift+Left)"
      >
        <SkipBack className="h-3.5 w-3.5" />
      </button>

      {/* Play/Pause */}
      <button
        type="button"
        onClick={isPlaying ? controls.pause : controls.play}
        className="flex h-8 w-8 items-center justify-center rounded-full text-white transition"
        style={{ background: sourceColor }}
        title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
      >
        {isPlaying ? <Pause className="h-4 w-4" /> : <Play className="ml-0.5 h-4 w-4" />}
      </button>

      {/* Next block */}
      <button
        type="button"
        onClick={controls.nextBlock}
        className="rounded p-1 text-muted-foreground transition hover:text-foreground"
        title="Next block (Shift+Right)"
      >
        <SkipForward className="h-3.5 w-3.5" />
      </button>

      {/* Block text preview + progress */}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[11px] text-foreground">
          {activeBlockText || '\u00A0'}
        </div>
        {/* Scrubber */}
        <div className="mt-1 flex items-center gap-2">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-border">
            <div
              className="h-full rounded-full transition-[width] duration-200"
              style={{ width: `${progressPct}%`, background: sourceColor }}
            />
          </div>
          {hasProgress && (
            <span className="flex-shrink-0 text-[9px] text-muted-foreground">
              {formatTime(state.currentMs)} / {formatTime(state.durationMs)}
            </span>
          )}
        </div>
      </div>

      {/* Source badge */}
      <span
        className="flex-shrink-0 rounded-full px-2 py-0.5 text-[9px] font-medium"
        style={{ background: `${sourceColor}18`, color: sourceColor }}
      >
        {sourceLabel}
      </span>

      {/* Speed */}
      <button
        type="button"
        onClick={cycleSpeed}
        className="flex-shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground transition hover:bg-secondary hover:text-foreground"
        title="Cycle speed"
      >
        {state.speed}x
      </button>

      {/* Close */}
      <button
        type="button"
        onClick={controls.stop}
        className="rounded p-1 text-muted-foreground transition hover:text-destructive"
        title="Stop (Escape)"
      >
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}
