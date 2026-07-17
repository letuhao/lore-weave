// Plan Hub v2 (24 H4) — the scene card (render-only custom RF node). Compact by design: a scene
// branches under its chapter, so it stays smaller/quieter than a chapter card. Its badge row is the
// same ordered precedence as the chapter's but denser and WITHOUT the pacing sparkline — tension
// rolls up per chapter (PH17), not per scene, so a scene shows only problems + motif chips.
import { memo } from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import { NodeBadges } from './NodeBadges';
import { orderNodeBadges, unionDotClass, unionStateClass, type PlanNodeData } from './nodePresentation';

function SceneNodeInner({ data }: NodeProps<PlanNodeData>) {
  const { node, content, overlay, unionState, selected, isHere, onOpenRef, resolveEntity , matched } = data;
  // PH26 — a scene's cast is the whole point of the chips: `present_entity_ids` is a SCENE field.
  const badges = orderNodeBadges({
    overlay, nodeId: node.id, showTension: false, content, resolveEntity,
  });
  const title = content?.title || `Sc ${node.storyOrder ?? '—'}`;

  return (
    <div
      data-testid={`plan-node-scene-${node.id}`}
      data-here={isHere ? 'true' : undefined}
      style={{ width: node.width }}
      className={cn(
        'select-none rounded border px-1.5 py-1 text-[11px] shadow-sm',
        unionStateClass(unionState),
        selected && 'ring-2 ring-primary',
        // PH15 find — a match is RINGED, not isolated. Non-matches stay exactly where they were.
        matched && 'ring-2 ring-yellow-500',
        isHere && 'outline outline-2 outline-offset-2 outline-sky-500',
      )}
    >
      <Handle type="target" position={Position.Left} className="!border-0 !bg-transparent" />
      <div className="flex items-center gap-1">
        <span className={cn('h-1.5 w-1.5 shrink-0 rounded-full', unionDotClass(unionState))} />
        {/* Real scene title once its window loads; a story-order label until then. */}
        <span className="line-clamp-2 flex-1 break-words leading-tight" title={title}>{title}</span>
      </div>
      <NodeBadges nodeId={node.id} badges={badges} onOpenRef={onOpenRef} compact />
      <Handle type="source" position={Position.Right} className="!border-0 !bg-transparent" />
    </div>
  );
}

export const SceneNode = memo(SceneNodeInner);
