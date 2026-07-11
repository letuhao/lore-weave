// Plan Hub v2 (24 H2.4 / PH11) — the collapsed-arc rollup card. A collapsed arc occupies ONE
// slot regardless of chapter_count and renders its summary from the shell (rollupCount) — never
// from loaded child nodes. Clicking the expand affordance re-expands the lane (onToggle→onToggleArc).
import { memo } from 'react';
import type { NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { arcDirty, type PlanNodeData } from './nodePresentation';

function ArcRollupNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, conformance, selected, onToggle } = data;
  const dirty = arcDirty(conformance, node.id);
  const count = node.rollupCount ?? 0;

  return (
    <div
      data-testid={`plan-node-arc-rollup-${node.id}`}
      style={{ width: node.width }}
      className={cn(
        'select-none rounded-md border border-dashed bg-muted/40 px-2 py-1.5 text-xs shadow-sm',
        selected && 'ring-2 ring-primary',
      )}
    >
      <div className="flex items-center gap-1.5">
        {dirty && (
          <span
            data-testid={`plan-node-arc-rollup-dirty-${node.id}`}
            className="h-2 w-2 shrink-0 rounded-full bg-amber-500"
            title="conformance drift"
          />
        )}
        <span className="flex-1 truncate font-medium">
          {count} {count === 1 ? 'chapter' : 'chapters'}
        </span>
        <button
          type="button"
          data-testid={`plan-node-arc-rollup-toggle-${node.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          className="pointer-events-auto text-muted-foreground hover:text-foreground"
          aria-label="Expand arc"
        >
          ▸
        </button>
      </div>
    </div>
  );
}

export const ArcRollupNode = memo(ArcRollupNodeInner);
