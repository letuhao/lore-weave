// Plan Hub v2 (24 H4) — the chapter card (render-only custom RF node). Title slot falls back to a
// story-order label until the node's window loads; the badge row renders the ordered decorations
// (canon deep-link · thread debt · pacing sparkline · motif chips) from the single precedence home.
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { NodeBadges } from './NodeBadges';
import { orderNodeBadges, unionDotClass, unionStateClass, type PlanNodeData } from './nodePresentation';

function ChapterNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, unionState, selected, onToggle, onOpenRef } = data;
  // Chapters aren't in conformance.arcs ⇒ no drift badge (isArc:false); pacing IS chapter-keyed.
  const badges = orderNodeBadges({ overlay, nodeId: node.id, showTension: true });
  const title = content?.title || `Ch ${node.storyOrder ?? '—'}`;

  return (
    <div
      data-testid={`plan-node-chapter-${node.id}`}
      style={{ width: node.width }}
      className={cn(
        'select-none rounded-md border px-2 py-1.5 text-xs shadow-sm',
        unionStateClass(unionState),
        selected && 'ring-2 ring-primary',
      )}
    >
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1.5">
        <span className={cn('h-2 w-2 shrink-0 rounded-full', unionDotClass(unionState))} />
        {/* Real chapter title once the window loads; a story-order label until then. */}
        <span className="flex-1 truncate font-medium" title={title}>{title}</span>
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
