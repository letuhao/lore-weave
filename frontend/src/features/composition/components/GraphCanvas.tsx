// LOOM Composition (T2.2) — generic, controlled graph SVG canvas. Owns ONLY the
// shared mechanics two graph views need (T1.3 Scene Graph + T2.2 Relationship Map,
// later T2.5 World Map): the <svg>, the pointer-drag gesture (5px threshold splits
// drag from click), canvas extent, a background-click-to-clear target, and a `defs`
// slot. Everything consumer-specific — what a node/edge looks like, click/persist
// semantics, layout — is a prop, so the consumer keeps its own state (positions,
// selection, persistence target). The consumer's node/edge components self-position
// (they receive a Pos); GraphCanvas does NOT transform them, so SceneNode/SceneEdge
// stay unchanged across the extraction.
import { Fragment, useEffect, useRef, useState } from 'react';
import { useIsMobile } from '@/hooks/useIsMobile';

export type Pos = { x: number; y: number };

export const GRAPH_PAD = 24;
const DRAG_THRESHOLD = 5; // px of pointer travel before a press counts as a drag
const ZOOM_MIN = 0.3;
const ZOOM_MAX = 2.5;
const ZOOM_STEP = 0.0015; // wheel-delta → scale factor

type DragState = { id: string; startX: number; startY: number; origX: number; origY: number; moved: boolean };
// C19 — a pan gesture (empty-space drag) for the zoomable project canvas. Distinct
// from node DragState: it translates the viewport, not a node.
type PanState = { startX: number; startY: number; origX: number; origY: number };

export function GraphCanvas<E>({
  positions, nodeIds, edges, edgeEndpoints, edgeKey, renderNode, renderEdge, nodeSize,
  onNodeClick, onNodeDrag, onNodeDragEnd, onBackgroundClick, defs, background,
  minWidth = 360, minHeight = 220, testid = 'graph-canvas', zoomable = false, autoFit = false,
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
  /** Optional layer painted BEHIND edges/nodes (T2.5 World Map backdrop). It sits
   *  under the transparent background-click rect, so it must be `pointer-events:none`
   *  to let background clicks through. Default: nothing (T1.3/T2.2 unaffected). */
  background?: React.ReactNode;
  minWidth?: number;
  minHeight?: number;
  testid?: string;
  /** C19 (G5) — opt-in pan/zoom for the project graph canvas. When true the SVG
   *  contents sit inside a zoom/pan `<g transform>`: mouse-wheel zooms (toward the
   *  cursor), an empty-space drag pans, and a Reset control re-centres. OFF by
   *  default so the T2.2 RelationshipMap (which uses node-drag + a small canvas)
   *  is byte-for-byte unaffected. The node-drag gesture stays intact in both modes. */
  zoomable?: boolean;
  /** Opt-in fit-to-content on desktop too (default: mobile-only). The KG schema
   *  canvas uses it so the type-graph is centred + scaled to the viewport instead
   *  of rendering at raw layout coords in a corner. Requires `zoomable`. */
  autoFit?: boolean;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const drag = useRef<DragState | null>(null);
  // C19 — viewport transform for the zoomable mode. Identity when !zoomable.
  const [view, setView] = useState<{ x: number; y: number; k: number }>({ x: 0, y: 0, k: 1 });
  const pan = useRef<PanState | null>(null);
  // M5b — on a ≤767px viewport EVERY heavy canvas becomes pan/zoom/pinch-able (the
  // desktop overflow-auto scroller is unusable on touch). Desktop is byte-unchanged:
  // `effectiveZoomable` collapses to the passed `zoomable` off-mobile.
  const isMobile = useIsMobile();
  const effectiveZoomable = zoomable || isMobile;
  // M5b — pinch-zoom: track active pointers; ≥2 → a pinch gesture (suppresses node-drag
  // / pan, zooms toward the gesture midpoint). Touch single-finger pan already works via
  // the pointer-event pan path; this adds the two-finger case the wheel can't cover.
  const pointers = useRef<Map<number, { x: number; y: number }>>(new Map());
  const pinch = useRef<{ dist: number; cx: number; cy: number; k: number; vx: number; vy: number } | null>(null);
  const fitted = useRef(false);

  const posOf = (id: string): Pos => positions[id] ?? { x: GRAPH_PAD, y: GRAPH_PAD };

  const startDrag = (id: string) => (e: React.PointerEvent) => {
    const p = posOf(id);
    drag.current = { id, startX: e.clientX, startY: e.clientY, origX: p.x, origY: p.y, moved: false };
    try { svgRef.current?.setPointerCapture?.(e.pointerId); } catch { /* jsdom no-op */ }
  };
  const clampK = (k: number) => Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, k));
  // M5b — register every pointer (bubbles up from nodes + the bg rect). The 2nd
  // pointer starts a pinch and cancels any in-flight node-drag / pan.
  const trackDown = (e: React.PointerEvent) => {
    pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (effectiveZoomable && pointers.current.size === 2) {
      drag.current = null;
      pan.current = null;
      const [a, b] = [...pointers.current.values()];
      const rect = svgRef.current?.getBoundingClientRect();
      pinch.current = {
        dist: Math.hypot(a.x - b.x, a.y - b.y) || 1,
        cx: (a.x + b.x) / 2 - (rect?.left ?? 0),
        cy: (a.y + b.y) / 2 - (rect?.top ?? 0),
        k: view.k, vx: view.x, vy: view.y,
      };
    }
  };
  const trackUp = (e: React.PointerEvent) => {
    pointers.current.delete(e.pointerId);
    if (pointers.current.size < 2) pinch.current = null;
  };

  const onPointerMove = (e: React.PointerEvent) => {
    if (pointers.current.has(e.pointerId)) pointers.current.set(e.pointerId, { x: e.clientX, y: e.clientY });
    // M5b — a live pinch zooms toward the gesture's start midpoint (keeps that point fixed).
    const pz = pinch.current;
    if (pz && pointers.current.size >= 2) {
      const [a, b] = [...pointers.current.values()];
      const k = clampK(pz.k * (Math.hypot(a.x - b.x, a.y - b.y) / pz.dist));
      const ratio = k / pz.k;
      setView({ k, x: pz.cx - (pz.cx - pz.vx) * ratio, y: pz.cy - (pz.cy - pz.vy) * ratio });
      return;
    }
    const d = drag.current;
    if (d) {
      const dx = e.clientX - d.startX;
      const dy = e.clientY - d.startY;
      if (!d.moved && Math.abs(dx) + Math.abs(dy) > DRAG_THRESHOLD) d.moved = true;
      // In zoomable mode the pointer travel is in screen px; divide by the zoom
      // factor so a node tracks the cursor 1:1 regardless of scale.
      if (d.moved) onNodeDrag(d.id, { x: Math.max(0, d.origX + dx / view.k), y: Math.max(0, d.origY + dy / view.k) });
      return;
    }
    const p = pan.current;
    if (p) setView((v) => ({ ...v, x: p.origX + (e.clientX - p.startX), y: p.origY + (e.clientY - p.startY) }));
  };
  const onPointerUp = (e: React.PointerEvent) => {
    trackUp(e);
    pan.current = null;
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.moved) onNodeDragEnd?.(d.id, posOf(d.id)); // consumer may read its own ref instead
    else onNodeClick?.(d.id);                        // a press without travel = a click
  };

  // C19 — empty-space press starts a pan (zoomable mode) AND clears selection.
  const onBackgroundDown = (e: React.PointerEvent) => {
    onBackgroundClick?.();
    if (effectiveZoomable) {
      pan.current = { startX: e.clientX, startY: e.clientY, origX: view.x, origY: view.y };
      try { svgRef.current?.setPointerCapture?.(e.pointerId); } catch { /* jsdom no-op */ }
    }
  };
  // C19 — mouse-wheel zoom toward the cursor (keeps the point under the cursor fixed).
  const onWheel = (e: React.WheelEvent) => {
    if (!effectiveZoomable) return;
    const rect = svgRef.current?.getBoundingClientRect();
    const cx = rect ? e.clientX - rect.left : 0;
    const cy = rect ? e.clientY - rect.top : 0;
    setView((v) => {
      const k = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, v.k * (1 - e.deltaY * ZOOM_STEP)));
      if (k === v.k) return v;
      const ratio = k / v.k;
      return { k, x: cx - (cx - v.x) * ratio, y: cy - (cy - v.y) * ratio };
    });
  };
  const resetView = () => setView({ x: 0, y: 0, k: 1 });

  const w = Math.max(minWidth, ...nodeIds.map((id) => posOf(id).x + nodeSize.w + GRAPH_PAD));
  const h = Math.max(minHeight, ...nodeIds.map((id) => posOf(id).y + nodeSize.h + GRAPH_PAD));

  // M5b — fit-to-screen on mount (MOBILE always; desktop only when `autoFit` is
  // opted-in — otherwise desktop zoomable keeps its identity start, byte-unchanged).
  // Fires once, once the graph has content + a measurable viewport, so the content
  // is centred + scaled to the viewport instead of rendering at raw coords.
  useEffect(() => {
    if ((!isMobile && !autoFit) || fitted.current || nodeIds.length === 0) return;
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || rect.height === 0) return;
    fitted.current = true;
    // fit to the smaller axis, centred. `autoFit` allows a modest upscale so a
    // sparse 2-node graph isn't a speck in a wide viewport; mobile stays cap-1.
    const cap = autoFit ? 1.6 : 1;
    const k = Math.min(rect.width / w, rect.height / h, cap);
    setView({ k, x: (rect.width - w * k) / 2, y: (rect.height - h * k) / 2 });
  }, [isMobile, autoFit, nodeIds.length, w, h]);

  const content = (
    <>
      {/* optional backdrop layer, painted behind everything (under the click rect) */}
      {background}
      {/* background: a press on empty space clears selection (+ starts a pan when zoomable) */}
      <rect data-testid={`${testid}-bg`} width={w} height={h} fill="transparent" onPointerDown={onBackgroundDown} />
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
    </>
  );

  // Non-zoomable (T2.2 desktop): the SVG grows to the node extent inside an
  // overflow-auto scroller — byte-identical to the pre-C19 behaviour.
  if (!effectiveZoomable) {
    return (
      <div className="min-h-0 flex-1 overflow-auto">
        <svg ref={svgRef} width={w} height={h} data-testid={testid} onPointerMove={onPointerMove} onPointerUp={onPointerUp}>
          {defs && <defs>{defs}</defs>}
          {content}
        </svg>
      </div>
    );
  }

  // Zoomable (C19): a fixed-size viewport SVG; the graph lives inside a pan/zoom
  // <g transform>. Wheel zooms, empty-space drag pans, Reset re-centres.
  return (
    <div className="relative min-h-0 flex-1 overflow-hidden" data-testid={`${testid}-viewport`}>
      <svg
        ref={svgRef}
        className="h-full w-full touch-none select-none"
        data-testid={testid}
        data-zoom={view.k.toFixed(3)}
        onPointerDown={trackDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={trackUp}
        onWheel={onWheel}
      >
        {defs && <defs>{defs}</defs>}
        {/* a full-bleed pan-catcher so empty viewport space (beyond the node
            extent) still starts a pan / clears selection. */}
        <rect data-testid={`${testid}-pan-catcher`} x={0} y={0} width="100%" height="100%" fill="transparent" onPointerDown={onBackgroundDown} />
        <g data-testid={`${testid}-transform`} transform={`translate(${view.x}, ${view.y}) scale(${view.k})`}>
          {content}
        </g>
      </svg>
      <button
        type="button"
        onClick={resetView}
        data-testid={`${testid}-reset`}
        className="absolute bottom-2 right-2 rounded-md border bg-card/90 px-2 py-1 text-[11px] text-muted-foreground shadow-sm hover:text-foreground"
      >
        ⤢ Reset view
      </button>
    </div>
  );
}
