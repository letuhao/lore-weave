// Plan Hub v2 (24 H4 / PH11) — the collapsed-arc rollup card. A collapsed arc occupies ONE slot
// regardless of chapter_count and renders its summary from the shell (rollupCount) — never from
// loaded child nodes. Its badges roll up onto it too (overlay/conformance key on structure_node.id):
// the conformance drift badge (arcDirty) plus any canon/thread/motif chips, ordered by the single
// precedence home. Clicking the expand affordance re-expands the lane (onToggle→onToggleArc).
import { memo } from 'react';
import type { NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { NodeBadges } from './NodeBadges';
import { orderNodeBadges, type PlanNodeData } from './nodePresentation';

function ArcRollupNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, conformance, selected, onToggle, onOpenRef } = data;
  // isArc ⇒ the drift badge is eligible; the arc lane is not chapter-keyed ⇒ no pacing slot.
  const badges = orderNodeBadges({ overlay, conformance, nodeId: node.id, isArc: true });
  const count = node.rollupCount ?? 0;
  const countLabel = `${count} ${count === 1 ? 'chapter' : 'chapters'}`;

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
        {/* The arc title (from the shell) is primary; the chapter count is the rollup's secondary
            line. Before the shell resolves for this node, the count alone still reads correctly. */}
        <span className="flex-1 truncate font-medium" title={content?.title}>
          {content?.title || countLabel}
          {content?.title && (
            <span className="ml-1 font-normal text-muted-foreground">· {countLabel}</span>
          )}
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
      <NodeBadges nodeId={node.id} badges={badges} onOpenRef={onOpenRef} />
    </div>
  );
}

export const ArcRollupNode = memo(ArcRollupNodeInner);
