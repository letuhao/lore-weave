// Plan Hub v2 (24 H4.3 / PH17) — the per-chapter pacing indicator. A single inline tension bar
// (NOT a chart lib): the overlay's tension_rollup is one scalar per chapter, so the "sparkline" is a
// magnitude bar tinted by band (calm → tense). Clicking a point focuses the scene is a drawer/edit
// affordance (PH17) that lands with H5's node rail; here it is read-only, so the bar is inert.
import { memo } from 'react';

import { cn } from '@/lib/utils';

/** Tension is a 0..100 scalar (SC8). Clamp defensively — a backend that widens the range must not
 *  overflow the bar. Band thresholds are the same three the drawer will reuse (one visual language). */
function bandTone(pct: number): string {
  if (pct >= 66) return 'bg-rose-500';
  if (pct >= 33) return 'bg-amber-500';
  return 'bg-emerald-500';
}

function PacingSparklineInner({ value, nodeId }: { value: number; nodeId: string }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <span
      data-testid={`plan-pacing-${nodeId}`}
      title={`Tension ${value}`}
      aria-label={`Tension ${value}`}
      className="inline-flex h-2 w-8 shrink-0 items-stretch overflow-hidden rounded-sm bg-muted"
    >
      <span className={cn('h-full', bandTone(pct))} style={{ width: `${pct}%` }} />
    </span>
  );
}

export const PacingSparkline = memo(PacingSparklineInner);
