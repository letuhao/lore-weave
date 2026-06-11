// LOOM Composition (T2.2) — generic, controlled graph SVG canvas. Owns ONLY the
// shared mechanics two graph views need (T1.3 Scene Graph + T2.2 Relationship Map,
// later T2.5 World Map): the <svg>, the pointer-drag gesture (5px threshold splits
// drag from click), canvas extent, a background-click-to-clear target, and a `defs`
// slot. Everything consumer-specific — what a node/edge looks like, click/persist
// semantics, layout — is a prop, so the consumer keeps its own state (positions,
// selection, persistence target). The consumer's node/edge components self-position
// (they receive a Pos); GraphCanvas does NOT transform them, so SceneNode/SceneEdge
// stay unchanged across the extraction.
import { Fragment, useRef } from 'react';

export type Pos = { x: number; y: number };

export const GRAPH_PAD = 24;
const DRAG_THRESHOLD = 5; // px of pointer travel before a press counts as a drag

type DragState = { id: string; startX: number; startY: number; origX: number; origY: number; moved: boolean };

export function GraphCanvas<E>({
  positions, nodeIds, edges, edgeEndpoints, edgeKey, renderNode, renderEdge, nodeSize,
  onNodeClick, onNodeDrag, onNodeDragEnd, onBackgroundClick, defs,
  minWidth = 360, minHeight = 220, testid = 'graph-canvas',
}: {
  positions: Record<string, Pos>;
  nodeIds: string[];
  edges: E[];
  edgeEndpoints: (e: E) => { from: string; to: string };
  edgeKey?: (e: E) => string;
  renderNode: (id: string, handlers: { onPointerDown: (e: React.PointerEvent) => void }) => React.ReactNode;
  renderEdge: (edge: E, from: Pos, to: Pos) => React.ReactNode;
  nodeSize: { w: number; h: number };
  onNodeClick?: (id: string) => void;
  onNodeDrag: (id: string, pos: Pos) => void;
  onNodeDragEnd?: (id: string, pos: Pos) => void;
  onBackgroundClick?: () => void;
  defs?: React.ReactNode;
  minWidth?: number;
  minHeight?: number;
  testid?: string;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<DragState | null>(null);

  const posOf = (id: string): Pos => positions[id] ?? { x: GRAPH_PAD, y: GRAPH_PAD };

  const startDrag = (id: string) => (e: React.PointerEvent) => {
    const p = posOf(id);
    drag.current = { id, startX: e.clientX, startY: e.clientY, origX: p.x, origY: p.y, moved: false };
    try { svgRef.current?.setPointerCapture?.(e.pointerId); } catch { /* jsdom no-op */ }
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (!d.moved && Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) d.moved = true;
    if (d.moved) onNodeDrag(d.id, { x: Math.max(0, d.origX + dx), y: Math.max(0, d.origY + dy) });
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.moved) onNodeDragEnd?.(d.id, posOf(d.id)); // consumer may read its own ref instead
    else onNodeClick?.(d.id);                        // a press without travel = a click
  };

  const w = Math.max(minWidth, ...nodeIds.map((id) => posOf(id).x + nodeSize.w + GRAPH_PAD));
  const h = Math.max(minHeight, ...nodeIds.map((id) => posOf(id).y + nodeSize.h + GRAPH_PAD));

  return (
    <div className="min-h-0 flex-1 overflow-auto">
      <svg ref={svgRef} width={w} height={h} data-testid={testid} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
        {defs && <defs>{defs}</defs>}
        {/* background: a press on empty space clears the consumer's selection */}
        <rect data-testid={`${testid}-bg`} width={w} height={h} fill="transparent" onPointerDown={onBackgroundClick} />
        {edges.map((e, i) => {
          const { from, to } = edgeEndpoints(e);
          const pf = positions[from];
          const pt = positions[to];
          if (!pf || !pt) return null; // skip an edge to an off-graph node
          return <Fragment key={edgeKey ? edgeKey(e) : i}>{renderEdge(e, pf, pt)}</Fragment>;
        })}
        {nodeIds.map((id) => (
          <Fragment key={id}>{renderNode(id, { onPointerDown: startDrag(id) })}</Fragment>
        ))}
      </svg>
    </div>
  );
}
