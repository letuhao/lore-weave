// ACP A4.3 — the Practice session header: "Question N of T" + a time countdown, mirroring the
// server's wrap enforcement (the server actually closes the interview; this is the honest display
// so the user sees the structure). View only — the progress math lives in practiceProgress.
import { Flag, Timer } from 'lucide-react';
import { cn } from '@/lib/utils';
import { practiceProgress } from '../lib/practiceProgress';
import type { Script } from '../types';

export interface PracticeProgressHeaderProps {
  messageCount: number;
  startedAt: string | null;
  script: Script | undefined;
}

export function PracticeProgressHeader({ messageCount, startedAt, script }: PracticeProgressHeaderProps) {
  const p = practiceProgress(messageCount, startedAt, script);
  // Freeform practice (no target and no budget) has no structure to show.
  if (p.target == null && p.budgetMin == null) return null;

  const current = p.target != null ? Math.min(p.questionCount + 1, p.target) : null;

  return (
    <div
      data-testid="practice-progress"
      className={cn(
        'flex items-center justify-between gap-3 border-b border-border bg-card px-3 py-2 text-sm',
        p.wrapping && 'bg-primary/10',
      )}
    >
      {current != null && (
        <span data-testid="practice-qcount" className="flex items-center gap-1.5 font-medium">
          <Flag className="h-4 w-4 text-primary" aria-hidden="true" />
          Question {current} of {p.target}
        </span>
      )}
      <span className="flex items-center gap-3 text-xs text-muted-foreground tabular-nums">
        {p.budgetMin != null && (
          <span data-testid="practice-timer" className="flex items-center gap-1">
            <Timer className="h-3.5 w-3.5" aria-hidden="true" />
            {p.elapsedMin ?? 0}/{p.budgetMin} min
          </span>
        )}
        {p.wrapping && (
          <span data-testid="practice-wrapping" className="font-medium text-primary">
            Wrapping up…
          </span>
        )}
      </span>
    </div>
  );
}
