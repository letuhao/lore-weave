// View: the roleplay scorecard overlay. Render only — receives the Scorecard
// and two callbacks (close → back to the conversation, restart → new persona).

import { Check, X, RotateCcw, ArrowLeft } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Scorecard } from '../types';

interface ScorecardViewProps {
  card: Scorecard;
  onClose: () => void;
  onRestart: () => void;
}

function Dimension({ label, value }: { label: string; value: string | null }) {
  if (!value) return null;
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="text-sm">{value}</span>
    </div>
  );
}

export function ScorecardView({ card, onClose, onRestart }: ScorecardViewProps) {
  const covered = card.checklist.filter((c) => c.covered).length;
  return (
    <div className="absolute inset-0 z-40 flex flex-col overflow-y-auto bg-background/95 p-6 backdrop-blur">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-5">
        <header className="flex items-center justify-between">
          <h2 className="font-serif text-lg font-semibold">Scorecard</h2>
          <div className="flex items-center gap-2">
            <button type="button" onClick={onClose} className="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs hover:bg-accent">
              <ArrowLeft className="h-3.5 w-3.5" /> Back
            </button>
            <button type="button" onClick={onRestart} className="flex items-center gap-1 rounded-md border px-2.5 py-1.5 text-xs hover:bg-accent">
              <RotateCcw className="h-3.5 w-3.5" /> New session
            </button>
          </div>
        </header>

        <div className="flex items-center gap-4">
          {card.overall_score != null && (
            <div className="flex h-16 w-16 shrink-0 flex-col items-center justify-center rounded-full border-2 border-primary">
              <span className="text-lg font-semibold">{card.overall_score}</span>
              <span className="text-[10px] text-muted-foreground">/100</span>
            </div>
          )}
          <div className="flex flex-col gap-1">
            {card.partial && (
              <span className="w-fit rounded bg-amber-500/15 px-2 py-0.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                Partial — session not fully completed
              </span>
            )}
            {card.summary && <p className="text-sm">{card.summary}</p>}
          </div>
        </div>

        <section className="flex flex-col gap-2">
          <span className="text-xs font-medium text-muted-foreground">Checklist ({covered}/{card.checklist.length})</span>
          <ul className="flex flex-col gap-1.5">
            {card.checklist.map((c) => (
              <li key={c.item} className="flex items-start gap-2 text-sm">
                <span className={cn('mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full', c.covered ? 'bg-green-500/20 text-green-600' : 'bg-muted text-muted-foreground')}>
                  {c.covered ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
                </span>
                <span className="flex flex-col">
                  <span className={cn(!c.covered && 'text-muted-foreground')}>{c.item}</span>
                  {c.note && <span className="text-xs text-muted-foreground">{c.note}</span>}
                </span>
              </li>
            ))}
          </ul>
        </section>

        <section className="grid gap-3 sm:grid-cols-3">
          <Dimension label="STAR" value={card.star_coverage} />
          <Dimension label="Clarity" value={card.clarity} />
          <Dimension label="Focus" value={card.filler} />
        </section>

        {card.strengths.length > 0 && (
          <section className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Strengths</span>
            <ul className="list-disc pl-5 text-sm">{card.strengths.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </section>
        )}
        {card.improvements.length > 0 && (
          <section className="flex flex-col gap-1">
            <span className="text-xs font-medium text-muted-foreground">Improvements</span>
            <ul className="list-disc pl-5 text-sm">{card.improvements.map((s, i) => <li key={i}>{s}</li>)}</ul>
          </section>
        )}
      </div>
    </div>
  );
}
