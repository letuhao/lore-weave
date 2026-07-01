import { useTranslation } from 'react-i18next';
import { Gauge } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ContextBudget } from '../types';

// RAID Wave A3 — the chat header context-budget meter (industry-standard
// "context used %" indicator). Pure render component: the event→state wiring
// lives in useChatMessages / the stream hub; this only renders the snapshot.
//
// Tiered warning bands (pct = used / effective_limit):
//   < 0.70  → normal  (muted)
//   0.70–0.85 → amber (warning)
//   > 0.85  → red     (danger / destructive)
// When pct is null (the model has no registered context_length) → render "—"
// so an unknown budget never crashes or shows a bogus %.

/** Band selector — exported so the unit test asserts the boundary logic directly. */
export type ContextBand = 'normal' | 'warning' | 'danger';

export function contextBand(pct: number): ContextBand {
  if (pct > 0.85) return 'danger';
  if (pct >= 0.7) return 'warning';
  return 'normal';
}

interface Props {
  budget: ContextBudget | null;
  /** Narrow host: render the gauge icon + % without extra chrome. */
  compact?: boolean;
}

export function ContextMeter({ budget, compact }: Props) {
  const { t } = useTranslation('chat');

  // No snapshot yet (before the first turn finishes) → render nothing rather
  // than a placeholder chip that would just be visual noise.
  if (!budget) return null;

  const known = budget.pct != null && Number.isFinite(budget.pct);
  const pct = known ? (budget.pct as number) : null;
  const band = pct != null ? contextBand(pct) : 'normal';

  const label = known ? `${Math.round((pct as number) * 100)}%` : '—';

  const title = known
    ? t('header.context_meter.tokens', {
        used: budget.used_tokens,
        limit: budget.effective_limit ?? budget.context_length ?? '?',
      })
    : t('header.context_meter.unknown');

  return (
    <div className="relative min-w-0">
      <div
        title={title}
        aria-label={t('header.context_meter.label')}
        data-testid="context-meter"
        data-band={band}
        className={cn(
          'flex min-w-0 items-center gap-1 rounded-md border px-2 py-1 text-[11px] font-medium tabular-nums transition-colors',
          !known
            ? 'border-border bg-secondary/40 text-muted-foreground'
            : band === 'danger'
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : band === 'warning'
                ? 'border-warning/40 bg-warning/10 text-warning'
                : 'border-border bg-secondary/40 text-muted-foreground',
        )}
      >
        <Gauge className="h-3 w-3 shrink-0" />
        {!compact && <span className="tabular-nums">{label}</span>}
      </div>
    </div>
  );
}
