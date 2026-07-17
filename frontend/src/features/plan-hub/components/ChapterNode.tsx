// Plan Hub v2 (24 H4) — the chapter card (render-only custom RF node). Title slot falls back to a
// story-order label until the node's window loads; the badge row renders the ordered decorations
// (canon deep-link · thread debt · pacing sparkline · motif chips) from the single precedence home.
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { NodeBadges } from './NodeBadges';
import { orderNodeBadges, unionDotClass, unionStateClass, type PlanNodeData } from './nodePresentation';

function ChapterNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, unionState, selected, isHere, onToggle, onOpenRef, hiddenEdges, resolveEntity , matched } =
    data;
  // Chapters aren't in conformance.arcs ⇒ no drift badge (isArc:false); pacing IS chapter-keyed.
  const badges = orderNodeBadges({ overlay, nodeId: node.id, showTension: true, content, resolveEntity });
  const title = content?.title || `Ch ${node.storyOrder ?? '—'}`;

  return (
    <div
      data-testid={`plan-node-chapter-${node.id}`}
      data-here={isHere ? 'true' : undefined}
      style={{ width: node.width }}
      className={cn(
        'select-none rounded-md border px-2 py-1.5 text-xs shadow-sm',
        unionStateClass(unionState),
        selected && 'ring-2 ring-primary',
        // PH15 find — a match is RINGED, not isolated. Non-matches stay exactly where they were.
        matched && 'ring-2 ring-yellow-500',
        // "You are here" — a distinct sky outline that composes with the selection ring (both can hold).
        isHere && 'outline outline-2 outline-offset-2 outline-sky-500',
      )}
    >
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1.5">
        <span className={cn('h-2 w-2 shrink-0 rounded-full', unionDotClass(unionState))} />
        {/* Real chapter title once the window loads; a story-order label until then. */}
        <span className="line-clamp-2 flex-1 break-words font-medium leading-tight" title={title}>{title}</span>
        {/* PH13 — scene-links whose other end is hidden (inside this collapsed chapter, or off in a
            collapsed arc). Counted here so the edge is accounted for rather than silently dropped. */}
        {!!hiddenEdges && (
          <span
            data-testid={`plan-node-edges-${node.id}`}
            title={`${hiddenEdges} scene link(s) not drawn — the other end is collapsed`}
            className="rounded bg-sky-500/20 px-1 text-[10px] text-sky-700 dark:text-sky-300"
          >
            ⇄{hiddenEdges}
          </span>
        )}
        <button
          type="button"
          data-testid={`plan-node-chapter-toggle-${node.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggle?.();
          }}
          className="pointer-events-auto text-muted-foreground hover:text-foreground"
          aria-label={node.collapsed ? 'Expand scenes' : 'Collapse scenes'}
        >
          {node.collapsed ? '▸' : '▾'}
        </button>
      </div>
      <NodeBadges nodeId={node.id} badges={badges} onOpenRef={onOpenRef} />
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

export const ChapterNode = memo(ChapterNodeInner);
