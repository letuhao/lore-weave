// LOOM Composition (T2.5) — one World Map place: a location node. The body is the
// drag handle (via GraphCanvas) AND the click target (→ open in the Cast codex).
// When the link tool is picking endpoints it shows a selection ring. Render-only;
// self-positions (GraphCanvas does not transform).
import type { Pos } from './GraphCanvas';
import type { GraphNode } from '../hooks/useRelationshipMap';

export const PLACE_NODE_W = 150;
export const PLACE_NODE_H = 40;

export function PlaceNode({
  node, pos, selected, onPointerDown, onActivate, onDelete, deleteLabel,
}: {
  node: GraphNode;
  pos: Pos;
  selected: boolean;
  onPointerDown: (e: React.PointerEvent) => void;
  onActivate: () => void;
  /** Remove this place (archive the location entity). Rendered as a small ×
   *  affordance; its pointer/click is isolated from the drag handle + open-codex. */
  onDelete?: () => void;
  deleteLabel?: string;
}) {
  return (
    <g transform={`translate(${pos.x}, ${pos.y})`} data-testid="worldmap-node" data-place={node.id} data-selected={selected ? 'true' : 'false'}>
      <foreignObject width={PLACE_NODE_W} height={PLACE_NODE_H} style={{ overflow: 'visible' }}>
        <div
          data-testid="worldmap-node-body"
          role="button"
          tabIndex={0}
          aria-label={node.name}
          onPointerDown={onPointerDown}
          onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onActivate(); } }}
          className={
            'group flex h-full cursor-grab select-none items-center gap-1.5 rounded-md border bg-card px-2 text-[11px] shadow-sm outline-none focus-visible:ring-2 focus-visible:ring-primary active:cursor-grabbing ' +
            (selected ? 'border-primary ring-2 ring-primary/50 ' : 'border-border ')
          }
        >
          <span aria-hidden className="shrink-0 text-[12px]">📍</span>
          <span className="min-w-0 flex-1 truncate font-medium">{node.name}</span>
          {onDelete && (
            <button
              type="button"
              data-testid="worldmap-node-delete"
              aria-label={deleteLabel}
              title={deleteLabel}
              // Isolate from the drag handle (onPointerDown) AND the open-in-codex
              // click on the body — this button owns its own gesture.
              onPointerDown={(e) => e.stopPropagation()}
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
              className="shrink-0 rounded px-1 leading-none text-muted-foreground opacity-60 hover:bg-destructive/10 hover:text-destructive hover:opacity-100 focus-visible:opacity-100"
            >
              ×
            </button>
          )}
        </div>
      </foreignObject>
    </g>
  );
}
