// Plan Hub v2 (24 H2.4) — the chapter card (render-only custom RF node). Title slot is a
// storyOrder placeholder until H4 enriches the node; the badge row is a minimal reserved
// slot reading only overlay scalars we already hold (canon/thread count + tension rollup).
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import {
  chapterTension,
  problemCount,
  unionDotClass,
  unionStateClass,
  type PlanNodeData,
} from './nodePresentation';

function ChapterNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, unionState, selected, onToggle } = data;
  const problems = problemCount(overlay, node.id);
  const tension = chapterTension(overlay, node.id);
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
      {/* Badge slot — canon/dirty/tension chips get their full wiring in H4; minimal now. */}
      <div
        data-testid={`plan-node-chapter-badges-${node.id}`}
        className="mt-1 flex h-4 items-center gap-1"
      >
        {tension != null && (
          <span className="rounded bg-muted px-1 text-[10px] text-muted-foreground">T{tension}</span>
        )}
        {problems > 0 && (
          <span className="rounded bg-destructive/15 px-1 text-[10px] text-destructive">{problems}</span>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

export const ChapterNode = memo(ChapterNodeInner);
