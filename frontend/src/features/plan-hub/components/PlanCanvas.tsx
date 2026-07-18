// Plan Hub v2 (24 H2.4 / PH14 / H5) — the React Flow canvas. It consumes the fixed PlanCanvasProps
// (the laneLayout result + decorations + callbacks) and maps them onto React Flow nodes/edges. It
// NEVER decides a RESTING position — every {x,y,width} comes from laneLayout (the one "where does a
// node go"); React Flow supplies mechanics only (pan/zoom/hit-test/drag).
//
// H5 made the node list CONTROLLED-WITH-DRAG, which has two React Flow v11 rules that are easy to
// get wrong (both shipped as live bugs once):
//   1. With a `nodes` prop and NO `onNodesChange`, RF's store is never updated by a drag — the card
//      does not move under the cursor at all (`hasDefaultNodes` is false, so triggerNodeChanges only
//      forwards to the absent callback). So we hold RF's node list in useNodesState and RESET it from
//      laneLayout whenever the layout changes. laneLayout stays the single source of resting
//      position; RF owns only the transient drag offset. Resetting at drag-stop IS the snap-back.
//   2. A per-node `draggable: true` does NOT override a global `nodesDraggable={false}` (it only
//      gates DOWN) — so the global flag must be on whenever ANY kind is draggable.
//
// The drop TARGET is resolved from the CURSOR (screenToFlowPosition), not from the dragged node's
// top-left corner. A corner-based hit-test is both asymmetric (a 13px nudge up crosses into the lane
// above while the card still looks 90% inside its own) and dangerous (a 1px drag could re-parent a
// scene under its neighbour). Cursor-based targeting is what the user means by "where I dropped it",
// and it is inherently no-op-safe: the cursor starts inside the dragged element's own region.
import { useCallback, useEffect, useMemo, useRef } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeDragHandler,
  type NodeMouseHandler,
  type OnConnect,
  type XYPosition,
} from 'reactflow';
import 'reactflow/dist/style.css';

import type { CameraFocusTarget, NodePosition, PlanCanvasProps } from '../types';
import { bandAtY, chapterAtPoint, leafLaneAtY, readingUnitBefore } from '../layout/laneLayout';
import { resolveEdges } from '../layout/edgeResolve';
import { ArcRollupNode } from './ArcRollupNode';
import { ChapterNode } from './ChapterNode';
import { buildLaneNodes, LaneBandNode, LANE_NODE_PREFIX } from './LaneBandLayer';
import { SceneNode } from './SceneNode';
import type { PlanNodeData } from './nodePresentation';

// Stable module-scope registry — a fresh object here makes React Flow warn + re-mount every node.
// Keys MUST equal NodeShape ('chapter'|'scene'|'arc-rollup') plus the band type.
const nodeTypes = {
  chapter: ChapterNode,
  scene: SceneNode,
  'arc-rollup': ArcRollupNode,
  'lane-band': LaneBandNode,
};

const CONTENT_Z = 10;
const FOCUS_ZOOM = 1;
/** Pixels the pointer must travel before a press becomes a DRAG. RF's default is 0, which turns
 *  every click — and every 1px twitch on a card — into a drag that fires a real structural write. */
const DRAG_THRESHOLD_PX = 5;

/**
 * Imperatively pans/zooms the viewport to a focused node (OQ-5). Rendered inside <ReactFlow>, so it
 * can call useReactFlow(). This is a legitimate useEffect: it SYNCHRONIZES an external imperative
 * API (React Flow's setCenter) with declarative state (focusTarget) — not event-handling. The `seq`
 * key means re-focusing the same node still pans. A node not in the current layout (collapsed away)
 * is a no-op — the pan is best-effort, never throws.
 */
function CameraController({
  focusTarget,
  nodes,
}: {
  focusTarget?: CameraFocusTarget | null;
  nodes: NodePosition[];
}) {
  const rf = useReactFlow();
  const seq = focusTarget?.seq ?? -1;
  // The seq we have already panned for. Focusing a node ALSO expands its ancestors, and that layout
  // change lands a render later — so the node usually does not exist on the frame the request was
  // made. We therefore watch `nodes` too and pan as soon as the target appears, but only ONCE per
  // request (without this latch, every unrelated layout change would re-pan the viewport).
  const pannedFor = useRef(-1);
  useEffect(() => {
    if (!focusTarget || pannedFor.current === seq) return;
    const n = nodes.find((p) => p.id === focusTarget.nodeId);
    if (!n) return; // not rendered yet (or at all) — retry on the next layout, never throw
    pannedFor.current = seq;
    rf.setCenter(n.x + n.width / 2, n.y + 20, { zoom: FOCUS_ZOOM, duration: 400 });
  }, [seq, nodes, focusTarget, rf]);
  return null;
}

/** PH15 "Fit" — re-frame the whole graph. Imperative RF API synchronised with a monotonic signal, so
 *  clicking Fit twice re-fits twice. Rendered inside <ReactFlow> so it can call useReactFlow(). */
function FitController({ signal }: { signal?: number }) {
  const rf = useReactFlow();
  const done = useRef(-1);
  useEffect(() => {
    if (signal === undefined || done.current === signal) return;
    done.current = signal;
    rf.fitView({ duration: 300 });
  }, [signal, rf]);
  return null;
}

/**
 * The drag's drop point in FLOW coordinates — i.e. where the CURSOR was released, projected into the
 * same space laneLayout emits. Returns null when the event carries no pointer coords (a synthetic or
 * keyboard-driven drag), so the caller can fall back to the node's own position.
 *
 * `screenToFlowPosition` is the v11.11 name; `project` is the older one. We accept either so the
 * canvas doesn't silently lose cursor targeting on a React Flow bump (it would fall back to the
 * corner probe and re-introduce the asymmetric hit-test).
 */
function cursorFlowPoint(
  event: unknown,
  rf: { screenToFlowPosition?: (p: XYPosition) => XYPosition; project?: (p: XYPosition) => XYPosition },
): XYPosition | null {
  const e = event as { clientX?: number; clientY?: number; changedTouches?: ArrayLike<Touch> };
  const touch = e?.changedTouches?.[0];
  const x = e?.clientX ?? touch?.clientX;
  const y = e?.clientY ?? touch?.clientY;
  if (typeof x !== 'number' || typeof y !== 'number') return null;
  const toFlow = rf.screenToFlowPosition ?? rf.project;
  return toFlow ? toFlow({ x, y }) : null;
}

function PlanCanvasInner(props: PlanCanvasProps) {
  const {
    layout,
    edges,
    overlay,
    conformance,
    unionState,
    nodeContent,
    selectedId,
    onSelect,
    onToggleArc,
    onToggleChapter,
    activeNodeId,
    focusTarget,
    onMoveChapter,
    onMoveScene,
    onMoveArc,
    onReorderChapter,
    arcPagination,
    onLoadMoreArc,
    onOpenRef,
    onLinkScenes,
    onUnlinkScenes,
    resolveEntity,
    fitSignal,
    matchedIds,
    busy,
  } = props;

  // H5: a node kind is draggable only when its move handler is wired (else the canvas is read-only).
  // A move already in flight freezes ALL dragging — the layout under the cursor is about to be
  // replaced by server truth, so a second drag would be aimed at stale lanes.
  const canDragChapter = (!!onMoveChapter || !!onReorderChapter) && !busy;
  const canDragScene = !!onMoveScene && !busy;
  const canDragArc = !!onMoveArc && !busy;
  // H5 Row-5: connecting is a WRITE, so it follows the same rule — offered only when its handler is
  // wired, and frozen while another write is in flight.
  const canConnect = !!onLinkScenes && !busy;
  const canDrag = canDragChapter || canDragScene || canDragArc;

  // PH13 — resolve each endpoint onto the RENDERED node set before React Flow ever sees it.
  //
  // The canvas used to map from/to straight through. An endpoint inside a collapsed arc is not in
  // the node list, so RF silently discarded the edge: the user saw a setup with no payoff, and no
  // hint that a payoff existed. `resolveEdges` walks each endpoint's server-supplied ancestry to the
  // nearest visible ancestor (scene → chapter card → arc rollup) and reports what it could NOT place,
  // so a collapsed card can badge the edges hiding inside it. Never a silent drop.
  const resolution = useMemo(() => resolveEdges(edges, layout.nodes), [edges, layout.nodes]);

  const rfNodes = useMemo<Node[]>(() => {
    const laneNodes = buildLaneNodes(
      layout.lanes, layout.width, onToggleArc, canDragArc, arcPagination, onLoadMoreArc,
    );
    const contentNodes: Node<PlanNodeData>[] = layout.nodes.map((n: NodePosition) => ({
      id: n.id,
      type: n.shape,
      position: { x: n.x, y: n.y },
      draggable:
        (n.shape === 'chapter' && canDragChapter) || (n.shape === 'scene' && canDragScene),
      zIndex: CONTENT_Z,
      style: { width: n.width },
      data: {
        node: n,
        content: nodeContent[n.id],
        overlay,
        conformance,
        unionState: unionState[n.id],
        selected: n.id === selectedId,
        isHere: activeNodeId != null && n.id === activeNodeId,
        // PH18 — every node card already READ `data.onOpenRef` and forwarded it to NodeBadges, and
        // NodeBadges already renders the canon badge as a deep-link button when it is present. The
        // canvas simply never put it in `data`, so the whole chain resolved to `undefined` and every
        // canon badge was a plain, unclickable chip. The seam existed; nothing fed it.
        onOpenRef,
        // PH13 — how many scene-links are folded INSIDE this card (both endpoints collapsed into
        // it, or its partner is off-screen). The card badges the number so the edge is accounted
        // for rather than vanishing.
        hiddenEdges: resolution.hiddenByNode[n.id] ?? 0,
        // PH26 — the name map, so a card can render its cast chips (and tell a BROKEN reference
        // from one merely not paged in). Absent ⇒ no cast chips, never a row of raw UUIDs.
        resolveEntity,
        // PH15 toolbar find — this node's title matches the query. A HIGHLIGHT, not a filter:
        // PH14 says an insert must shift, never reshuffle, and hiding non-matches would re-lay the
        // whole canvas out from under the user.
        matched: matchedIds ? matchedIds.has(n.id) : undefined,
        onToggle:
          n.shape === 'arc-rollup'
            ? () => onToggleArc(n.id)
            : n.shape === 'chapter'
              ? () => onToggleChapter(n.id)
              : undefined,
      },
    }));
    // Bands first (lower in the DOM / z), content on top.
    return [...laneNodes, ...contentNodes];
  }, [layout, overlay, conformance, unionState, nodeContent, selectedId, activeNodeId, canDragChapter, canDragScene, canDragArc, onToggleArc, onToggleChapter, arcPagination, onLoadMoreArc, onOpenRef, resolution, resolveEntity, matchedIds]);

  // RF's live node list. It exists ONLY so a drag can move the card under the cursor (see the header:
  // a controlled `nodes` prop with no onNodesChange never updates the store, so nothing moves). It is
  // reset from `rfNodes` — i.e. from laneLayout — on every layout change and at every drag stop, so
  // laneLayout remains the single source of resting position and RF can never invent one.
  const [nodes, setNodes, onNodesChange] = useNodesState([]);
  useEffect(() => {
    setNodes(rfNodes);
  }, [rfNodes, setNodes]);

  const rf = useReactFlow();

  const rfEdges = useMemo<Edge[]>(
    () =>
      resolution.edges.map(({ edge: e, source, target, stub }) => ({
        id: e.id,
        source,
        target,
        type: 'default',
        label: e.label ?? undefined,
        data: { kind: e.kind, stub },
        // setup_payoff = solid directional; custom = dashed (+ its label) (PH13). A STUB — one whose
        // endpoint is folded into a collapsed card — is dimmed and always dashed, so "this goes
        // somewhere you can't see" is visually distinct from a fully-drawn edge.
        style: stub
          ? { strokeDasharray: '2 3', opacity: 0.55 }
          : e.kind === 'custom'
            ? { strokeDasharray: '4 4' }
            : undefined,
        markerEnd: e.kind === 'setup_payoff' ? { type: MarkerType.ArrowClosed } : undefined,
      })),
    [resolution],
  );

  const onNodeClick = useCallback<NodeMouseHandler>(
    (_, node) => {
      // A band's header owns its own toggle; a click on the band body is not a selection.
      if (node.id.startsWith(LANE_NODE_PREFIX)) return;
      onSelect(node.id);
    },
    [onSelect],
  );

  const onPaneClick = useCallback(() => onSelect(null), [onSelect]);

  // H5 Row-5 (PH20) — DRAW an edge. The canvas reports only which two handles were joined; the
  // controller decides whether that is a legal link (both ends must be real SCENE nodes — an edge to
  // a stub connector's placeholder card is meaningless, because we don't know which hidden scene was
  // meant). Same two-layer law as every other H5 row.
  const onConnect = useCallback<OnConnect>(
    (c) => {
      if (!c.source || !c.target) return;
      onLinkScenes?.(c.source, c.target);
    },
    [onLinkScenes],
  );

  // H5 Row-5 — DELETE an edge. React Flow's own `deleteKeyCode` path is deliberately OFF: a stray
  // Backspace would destroy a link with no confirmation. An explicit click on the edge is the
  // gesture, and the controller owns the write.
  const onEdgeClick = useCallback(
    (_: unknown, rfEdge: Edge) => {
      // A STUB is not a real edge on screen — its other end is collapsed out of view. Deleting the
      // underlying link from a half-drawn line is a trap; expand the arc and delete it properly.
      if ((rfEdge.data as { stub?: boolean } | undefined)?.stub) return;
      // Hand back the WHOLE edge (kind + label), not just the id, so the controller's undo can
      // re-create it exactly. We hold it; the 204 doesn't carry it.
      const edge = edges.find((e) => e.id === rfEdge.id);
      if (edge) onUnlinkScenes?.(edge);
    },
    [onUnlinkScenes, edges],
  );

  // H5 drop routing. The drop point is the CURSOR in flow coordinates — see the file header for why
  // the dragged node's corner is the wrong probe. Routing by kind:
  //   • CHAPTER (Row-1) → the LEAF lane the cursor is over (leafLaneAtY). A DIFFERENT leaf arc
  //     rebinds it; its own lane / a non-leaf gap / off-canvas is a no-op.
  //   • SCENE (Row-4) → the CHAPTER card under the cursor (chapterAtPoint). The controller decides
  //     whether that's a real move (it owns the scene's parent + version for OCC).
  //   • ARC BAND (Row-2) → the band under the cursor (bandAtY, innermost). The controller decides
  //     nest-vs-sibling (it holds the shell's parent_id + rank). Its own band is a no-op.
  // Whatever we decide, the node list is RESET from laneLayout: on a no-op that's the snap-back, and
  // on a real move it holds the resting position until the refetch re-places the card for real.
  const onNodeDragStop = useCallback<NodeDragHandler>(
    (event, node) => {
      const drop = cursorFlowPoint(event, rf) ?? node.position;
      try {
        // Bands carry the `lane:` prefix and are NOT in layout.nodes (they're the background layer).
        if (node.id.startsWith(LANE_NODE_PREFIX)) {
          if (!onMoveArc) return;
          const arcId = node.id.slice(LANE_NODE_PREFIX.length);
          const target = bandAtY(layout.lanes, drop.y);
          if (target && target.id !== arcId) onMoveArc(arcId, target.id);
          return;
        }
        const np = layout.nodes.find((p) => p.id === node.id);
        if (!np) return;
        if (np.shape === 'chapter') {
          const target = leafLaneAtY(layout.lanes, drop.y);
          if (!target) return; // dropped off every lane
          if (target.id !== np.laneId) {
            // Row-1: a DIFFERENT lane ⇒ rebind the chapter's arc. Its reading position is untouched.
            onMoveChapter?.(node.id, target.id);
            return;
          }
          // Row-3: its OWN lane ⇒ the drag was horizontal, i.e. a move along the READING order.
          // The controller decides whether that's a real move (and refuses to jump a collapsed arc,
          // whose hidden chapters it cannot name to the server).
          onReorderChapter?.(node.id, readingUnitBefore(layout.nodes, drop.x, node.id));
          return;
        }
        if (np.shape === 'scene') {
          if (!onMoveScene) return;
          const target = chapterAtPoint(layout.nodes, drop.x, drop.y);
          if (target) onMoveScene(node.id, target.id);
        }
      } finally {
        setNodes(rfNodes); // snap back to laneLayout truth (RF only ever owned the drag offset)
      }
    },
    [onMoveChapter, onMoveScene, onMoveArc, onReorderChapter, layout, rf, rfNodes, setNodes],
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        // Without onNodesChange a controlled RF never applies a drag to its store — the card would
        // not move under the cursor at all (H5's live-caught bug #1). See the file header.
        onNodesChange={onNodesChange}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onPaneClick={onPaneClick}
        // React Flow v11: a per-node `draggable:true` does NOT override a global
        // `nodesDraggable={false}` (it only gates DOWN). So enable dragging globally when a move
        // handler is wired, and let the per-node `draggable` flag (chapters/scenes true, bands via
        // their header handle, rollups false) select WHAT drags. Read-only ⇒ nothing draggable.
        nodesDraggable={canDrag}
        // RF's default is 0 — every click would be a 0px "drag" and every twitch a structural write.
        nodeDragThreshold={DRAG_THRESHOLD_PX}
        // H5 Row-5 (PH20) — drag from a node's handle to another to CREATE a scene link.
        nodesConnectable={canConnect}
        onConnect={onConnect}
        onEdgeClick={onEdgeClick}
        // Deliberately NOT wiring RF's `onEdgesDelete`/`deleteKeyCode`: a stray Backspace would
        // destroy a link with no confirmation and no undo path. The click IS the gesture.
        deleteKeyCode={null}
        elementsSelectable={false}
        fitView
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
        <CameraController focusTarget={focusTarget} nodes={layout.nodes} />
        <FitController signal={fitSignal} />
      </ReactFlow>
    </div>
  );
}

/** The Plan Hub canvas. Parent MUST size it (fills h-full/w-full). */
export function PlanCanvas(props: PlanCanvasProps) {
  return (
    <ReactFlowProvider>
      <PlanCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
