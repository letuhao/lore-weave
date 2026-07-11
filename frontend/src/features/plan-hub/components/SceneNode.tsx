// Plan Hub v2 (24 H2.4) — the scene card (render-only custom RF node). Compact by design:
// a scene branches under its chapter, so it stays smaller and quieter than a chapter card.
// Scene tension lives on the SummaryNode (not on the canvas NodePosition contract yet), so
// it is intentionally NOT shown here — it arrives with node enrichment in H4.
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { unionDotClass, unionStateClass, type PlanNodeData } from './nodePresentation';

function SceneNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, unionState, selected } = data;

  return (
    <div
      data-testid={`plan-node-scene-${node.id}`}
      style={{ width: node.width }}
      className={cn(
        'select-none rounded border px-1.5 py-1 text-[11px] shadow-sm',
        unionStateClass(unionState),
        selected && 'ring-2 ring-primary',
      )}
    >
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1">
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', unionDotClass(unionState))} />
        {/* Title + tension arrive with node enrichment (H4); storyOrder is the placeholder. */}
        <span className="flex-1 truncate">Sc {node.storyOrder ?? '—'}</span>
      </div>
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

export const SceneNode = memo(SceneNodeInner);
