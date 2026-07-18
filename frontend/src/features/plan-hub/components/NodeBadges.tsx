// Plan Hub v2 (24 H4 / PH18/19/23) — the node badge ROW: renders the pre-ordered, pre-capped
// decoration list from `orderNodeBadges` (the single precedence home) so ChapterNode/SceneNode/
// ArcRollupNode share one row treatment. Render-only: it receives an ordered `NodeBadge[]` and maps
// it; it decides no order and reads no overlay. Canon is a deep-link affordance when `onOpenRef` is
// wired, else a plain count chip (H4.1 fallback — never a dead button).
import { memo } from 'react';

import { cn } from '@/lib/utils';

import type { PlanOverlayRef } from '../types';
import { PacingSparkline } from './PacingSparkline';
import type { NodeBadge, PlanNodeData } from './nodePresentation';

interface NodeBadgesProps {
  nodeId: string;
  badges: NodeBadge[];
  onOpenRef?: PlanNodeData['onOpenRef'];
  /** Scene cards run quieter/denser than chapter cards. */
  compact?: boolean;
}

const chip = 'rounded px-1 text-[10px] leading-4';

// NB: the prop is `rule`, not `ref` — `ref` is a reserved React prop and would be swallowed.
function CanonBadge({ nodeId, count, rule, onOpenRef }: {
  nodeId: string;
  count: number;
  rule: PlanOverlayRef | null;
  onOpenRef?: PlanNodeData['onOpenRef'];
}) {
  const label = rule ? rule.line : `${count} canon issue${count === 1 ? '' : 's'}`;
  const cls = cn(chip, 'bg-destructive/15 font-medium text-destructive');
  // A wired handler + a resolvable rule ⇒ a real deep-link button; otherwise a static count chip.
  if (onOpenRef && rule) {
    return (
      <button
        type="button"
        data-testid={`plan-badge-canon-${nodeId}`}
        title={label}
        aria-label={label}
        onClick={(e) => {
          e.stopPropagation();
          onOpenRef(rule, nodeId);
        }}
        className={cn(cls, 'pointer-events-auto hover:bg-destructive/25')}
      >
        ⚠ {count}
      </button>
    );
  }
  return (
    <span data-testid={`plan-badge-canon-${nodeId}`} title={label} className={cls}>
      ⚠ {count}
    </span>
  );
}

function NodeBadgesInner({ nodeId, badges, onOpenRef, compact }: NodeBadgesProps) {
  if (badges.length === 0) return null;
  return (
    <div
      data-testid={`plan-node-badges-${nodeId}`}
      className={cn('flex items-center gap-1', compact ? 'mt-0.5' : 'mt-1 h-4')}
    >
      {badges.map((b) => {
        switch (b.kind) {
          case 'canon':
            return <CanonBadge key="canon" nodeId={nodeId} count={b.count} rule={b.ref} onOpenRef={onOpenRef} />;
          case 'dirty':
            return (
              <span
                key="dirty"
                data-testid={`plan-badge-dirty-${nodeId}`}
                title="conformance drift"
                className="h-2 w-2 shrink-0 rounded-full bg-amber-500"
              />
            );
          case 'threads':
            return (
              <span
                key="threads"
                data-testid={`plan-badge-threads-${nodeId}`}
                title={`${b.count} open thread${b.count === 1 ? '' : 's'}`}
                className={cn(chip, 'bg-muted text-muted-foreground')}
              >
                🧵{b.count}
              </span>
            );
          case 'tension':
            return <PacingSparkline key="tension" nodeId={nodeId} value={b.value} />;
          case 'cast': {
            // PH26's three states. `missing` is an ACCUSATION (this reference is broken) and is only
            // ever reachable when the entity-names map is COMPLETE — with a partial map, an absent id
            // means "not paged in yet", which renders neutrally. Never a silent blank.
            const r = b.resolution;
            const isMissing = r.state === 'missing';
            const label =
              r.state === 'resolved' ? r.name : isMissing ? 'missing entity' : '…';
            return (
              <span
                key={`cast-${b.entityId}`}
                data-testid={`plan-badge-cast-${nodeId}-${b.entityId}`}
                data-cast-state={r.state}
                title={
                  isMissing
                    ? `This scene references an entity that is not in the glossary (${b.entityId})`
                    : label
                }
                className={cn(
                  chip,
                  'max-w-[5rem] truncate',
                  isMissing
                    ? 'bg-red-100 text-red-900 dark:bg-red-950/50 dark:text-red-200'
                    : r.state === 'unknown'
                      ? 'bg-muted text-muted-foreground/60'
                      : 'bg-sky-100 text-sky-900 dark:bg-sky-950/50 dark:text-sky-200',
                )}
              >
                {isMissing && <span className="mr-0.5">⚠</span>}
                {label}
              </span>
            );
          }
          case 'motif':
            return (
              <span
                key={`motif-${b.chip.motif_id}`}
                data-testid={`plan-badge-motif-${nodeId}-${b.chip.motif_id}`}
                title={
                  b.stale
                    ? `${b.chip.title} · pin v${b.chip.pinned_version} → v${b.chip.live_version} (stale)`
                    : `${b.chip.title} · pin v${b.chip.pinned_version}`
                }
                className={cn(
                  chip,
                  'max-w-[6rem] truncate',
                  b.stale
                    ? 'bg-amber-100 text-amber-900 dark:bg-amber-950/50 dark:text-amber-200'
                    : 'bg-violet-100 text-violet-900 dark:bg-violet-950/50 dark:text-violet-200',
                )}
              >
                {b.chip.title}
                {b.stale && <span className="ml-0.5 font-semibold">↑</span>}
              </span>
            );
          case 'overflow':
            return (
              <span
                key={`overflow-${b.of}`}
                data-testid={`plan-badge-overflow-${b.of}-${nodeId}`}
                title={`${b.count} more ${b.of === 'cast' ? 'cast member' : 'motif'}${b.count === 1 ? '' : 's'}`}
                className={cn(chip, 'bg-muted text-muted-foreground')}
              >
                +{b.count}
              </span>
            );
        }
      })}
    </div>
  );
}

export const NodeBadges = memo(NodeBadgesInner);
