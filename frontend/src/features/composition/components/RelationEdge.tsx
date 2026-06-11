// LOOM Composition (T2.2) — one Relationship-Map edge: a directed RELATES_TO
// relation. Solid when confirmed, dashed when `pending_validation`. The predicate
// surfaces as a native hover tooltip (<title>); a fat transparent hit-line makes
// the thin edge easy to hover. Read-only (no select/delete) — navigation is via
// the nodes. Render-only.
import type { Pos } from './GraphCanvas';
import type { GraphEdge } from '../hooks/useRelationshipMap';
import { ENTITY_NODE_H, ENTITY_NODE_W } from './GraphEntityNode';

const center = (p: Pos) => ({ x: p.x + ENTITY_NODE_W / 2, y: p.y + ENTITY_NODE_H / 2 });

export function RelationEdge({ edge, from, to }: { edge: GraphEdge; from: Pos; to: Pos }) {
  const a = center(from);
  const b = center(to);
  const tip = edge.predicate + (edge.pending ? ' (unconfirmed)' : '');
  return (
    <g data-testid="relmap-edge" data-pending={edge.pending ? 'true' : 'false'} data-predicate={edge.predicate}>
      <line
        x1={a.x} y1={a.y} x2={b.x} y2={b.y}
        stroke={edge.pending ? '#cbd5e1' : '#94a3b8'} strokeWidth={1.5}
        strokeDasharray={edge.pending ? '5 4' : undefined}
        markerEnd="url(#relmap-arrow)" pointerEvents="none"
      >
        <title>{tip}</title>
      </line>
      {/* fat invisible hit line so the predicate tooltip is easy to reach */}
      <line x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke="transparent" strokeWidth={12} style={{ cursor: 'help' }}>
        <title>{tip}</title>
      </line>
    </g>
  );
}
