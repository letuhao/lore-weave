import { cn } from '@/lib/utils';
import type { ExtractionJobStatus } from '../types/projectState';

// K19b.4 — reusable job-progress visual. Renders a status-coloured bar
// plus a compact metrics row (items processed, cost spent).
//
// Separate from `state_cards/shared.ProgressBar` because this bar is
// status-aware (colour + indeterminate state + 100% on complete) and
// meant for the K19b Jobs tab where many jobs of different statuses
// render side-by-side. The K19a state cards use the simpler shared
// bar because they only ever render for *one* currently-active state.

interface Props {
  status: ExtractionJobStatus;
  itemsProcessed: number;
  itemsTotal: number | null;
  costSpentUsd: string;
  /** null = unlimited budget (BE omits max_spend_usd). */
  maxSpendUsd: string | null;
  className?: string;
}

const BAR_COLOR: Record<ExtractionJobStatus, string> = {
  pending: 'bg-primary/70',
  running: 'bg-primary',
  paused: 'bg-amber-500',
  complete: 'bg-emerald-500',
  failed: 'bg-destructive',
  cancelled: 'bg-muted-foreground/40',
};

function computePct(
  status: ExtractionJobStatus,
  processed: number,
  total: number | null,
): number {
  if (status === 'complete') return 100;
  if (total == null || total <= 0) return 0;
  return Math.min(100, Math.max(0, Math.round((processed / total) * 100)));
}

// review-impl L4: BE ships Decimal fields as strings ("1234.56", "0.00"
// or "5"). Format once for display so `$5 / $100` / `$1,234.56 / $10`
// / `$0.00` all render consistently. Intl.NumberFormat handles
// locale-default grouping without pulling in i18n — currency-label
// localisation lands with K19b.7.
const USD_FORMATTER = new Intl.NumberFormat(undefined, {
  style: 'currency',
  currency: 'USD',
  minimumFractionDigits: 2,
  maximumFractionDigits: 4,
});

function formatCost(raw: string): string {
  const n = Number(raw);
  return Number.isFinite(n) ? USD_FORMATTER.format(n) : `$${raw}`;
}

export function JobProgressBar({
  status,
  itemsProcessed,
  itemsTotal,
  costSpentUsd,
  maxSpendUsd,
  className,
}: Props) {
  const pct = computePct(status, itemsProcessed, itemsTotal);
  const isIndeterminate =
    itemsTotal == null && (status === 'running' || status === 'pending');
  const totalLabel = itemsTotal == null ? '—' : String(itemsTotal);
  const spentFormatted = formatCost(costSpentUsd);
  const costLabel =
    maxSpendUsd != null
      ? `${spentFormatted} / ${formatCost(maxSpendUsd)}`
      : spentFormatted;

  // review-impl L5: richer aria-label so the screen-reader announcement
  // captures status + progress in one pass, not just the status word.
  // K19b.7 will swap the English verb out for a localised template.
  const ariaLabel = isIndeterminate
    ? `Job ${status}, progress unknown`
    : `Job ${status}, ${pct}% complete`;

  return (
    <div className={cn('space-y-1', className)}>
      <div
        className="relative h-1.5 w-full overflow-hidden rounded-full bg-muted"
        role="progressbar"
        aria-valuenow={isIndeterminate ? undefined : pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={ariaLabel}
        data-testid="job-progress-bar"
        data-status={status}
      >
        {isIndeterminate ? (
          <div
            className={cn(
              'absolute inset-y-0 w-1/3 animate-pulse rounded-full',
              BAR_COLOR[status],
            )}
            data-testid="job-progress-indeterminate"
          />
        ) : (
          <div
            className={cn('h-full transition-all', BAR_COLOR[status])}
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
      <div className="flex justify-between text-[11px] text-muted-foreground">
        <span data-testid="job-progress-items">
          {itemsProcessed} / {totalLabel}
        </span>
        <span data-testid="job-progress-cost">{costLabel}</span>
      </div>
    </div>
  );
}
