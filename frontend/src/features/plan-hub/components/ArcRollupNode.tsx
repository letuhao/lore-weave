// Plan Hub v2 (24 H4 / PH11) — the collapsed-arc rollup card. A collapsed arc occupies ONE slot
// regardless of chapter_count and renders its summary from the shell (rollupCount) — never from
// loaded child nodes. Its badges roll up onto it too (overlay/conformance key on structure_node.id):
// the conformance drift badge (arcDirty) plus any canon/thread/motif chips, ordered by the single
// precedence home. Clicking the expand affordance re-expands the lane (onToggle→onToggleArc).
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { NodeBadges } from './NodeBadges';
import { orderNodeBadges, type PlanNodeData } from './nodePresentation';

function ArcRollupNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, conformance, selected, onToggle, onOpenRef, hiddenEdges } = data;
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
      {/* PH13 — a rollup is an EDGE ENDPOINT: an edge into a collapsed arc stubs onto this card. React
          Flow attaches an edge only to a node that has handles, so without these the stub connector
          resolves correctly and is then dropped anyway, one layer lower. (That is precisely how the
          original bug survived: every layer looked right on its own.) */}
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1.5">
        {/* The arc title (from the shell) is primary; the chapter count is the rollup's secondary
            line. Before the shell resolves for this node, the count alone still reads correctly. */}
        <span className="line-clamp-2 flex-1 break-words font-medium leading-tight" title={content?.title}>
          {content?.title || countLabel}
          {content?.title && (
            <span className="ml-1 font-normal text-muted-foreground">· {countLabel}</span>
          )}
        </span>
        {/* PH13 — scene-links folded INSIDE this collapsed arc (both endpoints inside it, so an edge
            would be a self-loop). They must be ACCOUNTED FOR, not dropped: without this the user sees
            a setup with no payoff and no hint the payoff exists. Expanding the arc draws them. */}
        {!!hiddenEdges && (
          <span
            data-testid={`plan-node-edges-${node.id}`}
            title={`${hiddenEdges} scene link(s) inside this arc — expand to see them`}
            className="rounded bg-sky-500/20 px-1 text-[10px] text-sky-700 dark:text-sky-300"
          >
            ⇄{hiddenEdges}
          </span>
        )}
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
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

export const ArcRollupNode = memo(ArcRollupNodeInner);
