// Plan Hub v2 (24 H2.4 / PH14) — the React Flow canvas. RENDER-ONLY: it consumes the fixed
// PlanCanvasProps (the laneLayout result + decorations + callbacks) and maps them onto React
// Flow nodes/edges. It NEVER decides a position — every {x,y,width} comes from laneLayout
// (the one "where does a node go"); React Flow supplies mechanics only (pan/zoom/hit-test).
// Fully controlled + read-only: no drag (H5, later), no internal selection (we own it via
// data.selected), no useEffect (nodes/edges are pure useMemo of props).
import { useCallback, useEffect, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  ReactFlowProvider,
  useReactFlow,
  type Edge,
  type Node,
  type NodeDragHandler,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';

import type { CameraFocusTarget, NodePosition, PlanCanvasProps } from '../types';
import { bandAtY, chapterAtPoint, leafLaneAtY } from '../layout/laneLayout';
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
  useEffect(() => {
    if (!focusTarget) return;
    const n = nodes.find((p) => p.id === focusTarget.nodeId);
    if (!n) return; // not currently rendered (arc collapsed) — best-effort, no throw
    rf.setCenter(n.x + n.width / 2, n.y + 20, { zoom: FOCUS_ZOOM, duration: 400 });
    // eslint-disable-next-line react-hooks/exhaustive-deps -- pan is keyed on the focus REQUEST (seq),
    // not on every nodes/rf identity change (which would re-pan on unrelated re-renders).
  }, [seq]);
  return null;
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
  } = props;

  // H5: a node kind is draggable only when its move handler is wired (else the canvas is read-only).
  const canDragChapter = !!onMoveChapter;
  const canDragScene = !!onMoveScene;
  const canDragArc = !!onMoveArc;
  const canDrag = canDragChapter || canDragScene || canDragArc;

  const rfNodes = useMemo<Node[]>(() => {
    const laneNodes = buildLaneNodes(layout.lanes, layout.width, onToggleArc, canDragArc);
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
  }, [layout, overlay, conformance, unionState, nodeContent, selectedId, activeNodeId, canDragChapter, canDragScene, canDragArc, onToggleArc, onToggleChapter]);

  const rfEdges = useMemo<Edge[]>(
    () =>
      edges.map((e) => ({
        id: e.id,
        source: e.from_node_id,
        target: e.to_node_id,
        type: 'default',
        label: e.label ?? undefined,
        data: { kind: e.kind },
        // setup_payoff = solid directional; custom = dashed (+ its label). (PH13)
        style: e.kind === 'custom' ? { strokeDasharray: '4 4' } : undefined,
        markerEnd: e.kind === 'setup_payoff' ? { type: MarkerType.ArrowClosed } : undefined,
      })),
    [edges],
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

  // H5 drop routing (pure hit-tests; React Flow snaps the card back on the next controlled render
  // whenever the drop is a no-op):
  //   • CHAPTER (Row-1) → the LEAF lane it landed in (leafLaneAtY). A DIFFERENT leaf arc rebinds it;
  //     its own lane / a non-leaf gap / the tray is a no-op.
  //   • SCENE (Row-4) → the CHAPTER card it landed on (chapterAtPoint). The controller decides
  //     whether that's a real move (it owns the scene's current parent + version for OCC); a drop on
  //     no chapter is a no-op.
  //   • ARC BAND (Row-2) → the band it landed on (bandAtY, innermost). The controller decides
  //     nest-vs-sibling (it holds the shell's parent_id + rank). Dropping on itself is a no-op.
  const onNodeDragStop = useCallback<NodeDragHandler>(
    (_, node) => {
      // Bands carry the `lane:` prefix and are NOT in layout.nodes (they're the background layer).
      if (node.id.startsWith(LANE_NODE_PREFIX)) {
        if (!onMoveArc) return;
        const arcId = node.id.slice(LANE_NODE_PREFIX.length);
        const target = bandAtY(layout.lanes, node.position.y);
        if (target && target.id !== arcId) onMoveArc(arcId, target.id);
        return;
      }
      const np = layout.nodes.find((p) => p.id === node.id);
      if (!np) return;
      const { x, y } = node.position;
      if (np.shape === 'chapter') {
        if (!onMoveChapter) return;
        const target = leafLaneAtY(layout.lanes, y);
        if (target && target.id !== np.laneId) onMoveChapter(node.id, target.id);
        return;
      }
      if (np.shape === 'scene') {
        if (!onMoveScene) return;
        const target = chapterAtPoint(layout.nodes, x, y);
        if (target) onMoveScene(node.id, target.id);
      }
    },
    [onMoveChapter, onMoveScene, onMoveArc, layout],
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onNodeDragStop={onNodeDragStop}
        onPaneClick={onPaneClick}
        // React Flow v11: a per-node `draggable:true` does NOT override a global
        // `nodesDraggable={false}` (it only gates DOWN). So enable dragging globally when a move
        // handler is wired, and let the per-node `draggable` flag (chapters true, bands/scenes/
        // rollups false) select WHAT drags. Read-only canvas ⇒ canDrag false ⇒ nothing draggable.
        nodesDraggable={canDrag}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
        <CameraController focusTarget={focusTarget} nodes={layout.nodes} />
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
