// Plan Hub v2 (24 H2.4 / PH14) — the swimlane band layer. Bands are rendered as low-z, non-
// interactive React Flow nodes (NOT an absolute HTML overlay) so they pan/zoom in lockstep with
// the content nodes under the same viewport transform. A band spans the full canvas width; its
// header carries the arc title + a collapse/expand affordance (→ onToggleArc) + the BA6 warn chip
// on a non-contiguous arc. The band BODY is pointer-transparent so it never steals a node click;
// only the header strip is interactive.
import { memo } from 'react';
import type { Node, NodeProps } from 'reactflow';

import { cn } from '@/lib/utils';

import type { LaneBand } from '../types';
import type { LaneBandData } from './nodePresentation';

/** RF node id namespace for bands — a band's id is a structure_node id, which also names the
 *  arc-rollup CONTENT node of a collapsed arc; prefixing keeps RF node ids unique. */
export const LANE_NODE_PREFIX = 'lane:';

function LaneBandInner({ data }: NodeProps<LaneBandData>) {
  const { band, onToggleArc } = data;

  return (
    <div
      data-testid={`plan-lane-${band.id}`}
      className={cn(
        'pointer-events-none h-full w-full rounded-md border border-border/50',
        band.isLeaf ? 'bg-muted/20' : 'bg-muted/10',
        band.collapsed && 'opacity-70',
      )}
    >
      <div className="pointer-events-auto flex w-max max-w-full items-center gap-1 rounded-br-md rounded-tl-md border-b border-r border-border/50 bg-background/80 px-2 py-0.5 text-[11px] font-medium">
        <button
          type="button"
          data-testid={`plan-lane-toggle-${band.id}`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleArc(band.id);
          }}
          className="text-muted-foreground hover:text-foreground"
          aria-label={band.collapsed ? 'Expand lane' : 'Collapse lane'}
        >
          {band.collapsed ? '▸' : '▾'}
        </button>
        <span className="truncate">{band.title}</span>
        {!band.contiguous && (
          <span
            data-testid={`plan-lane-warn-${band.id}`}
            className="rounded bg-amber-500/20 px-1 text-amber-700 dark:text-amber-300"
            title="non-contiguous arc"
          >
            ⚠
          </span>
        )}
      </div>
    </div>
  );
}

export const LaneBandNode = memo(LaneBandInner);

/**
 * Build the background band nodes for a laneLayout. Full-width, positioned at each band's y,
 * low z-index (by depth so a nested band draws over its parent) and non-interactive except the
 * header. Kept out of PlanCanvas so the canvas stays a thin mapper.
 */
export function buildLaneNodes(
  lanes: LaneBand[],
  width: number,
  onToggleArc: (arcId: string) => void,
): Node<LaneBandData>[] {
  return lanes.map((band) => ({
    id: `${LANE_NODE_PREFIX}${band.id}`,
    type: 'lane-band',
    position: { x: 0, y: band.y },
    data: { band, onToggleArc },
    draggable: false,
    selectable: false,
    connectable: false,
    deletable: false,
    focusable: false,
    zIndex: band.depth,
    style: { width, height: band.height, pointerEvents: 'none' },
  }));
}
