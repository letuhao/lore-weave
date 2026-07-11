// Plan Hub v2 (24 H2.4 / PH14) — the React Flow canvas. RENDER-ONLY: it consumes the fixed
// PlanCanvasProps (the laneLayout result + decorations + callbacks) and maps them onto React
// Flow nodes/edges. It NEVER decides a position — every {x,y,width} comes from laneLayout
// (the one "where does a node go"); React Flow supplies mechanics only (pan/zoom/hit-test).
// Fully controlled + read-only: no drag (H5, later), no internal selection (we own it via
// data.selected), no useEffect (nodes/edges are pure useMemo of props).
import { useCallback, useMemo } from 'react';
import ReactFlow, {
  Background,
  Controls,
  MarkerType,
  ReactFlowProvider,
  type Edge,
  type Node,
  type NodeMouseHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';

import type { NodePosition, PlanCanvasProps } from '../types';
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

function PlanCanvasInner(props: PlanCanvasProps) {
  const {
    layout,
    edges,
    overlay,
    conformance,
    unionState,
    selectedId,
    onSelect,
    onToggleArc,
    onToggleChapter,
  } = props;

  const rfNodes = useMemo<Node[]>(() => {
    const laneNodes = buildLaneNodes(layout.lanes, layout.width, onToggleArc);
    const contentNodes: Node<PlanNodeData>[] = layout.nodes.map((n: NodePosition) => ({
      id: n.id,
      type: n.shape,
      position: { x: n.x, y: n.y },
      draggable: false,
      zIndex: CONTENT_Z,
      style: { width: n.width },
      data: {
        node: n,
        overlay,
        conformance,
        unionState: unionState[n.id],
        selected: n.id === selectedId,
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
  }, [layout, overlay, conformance, unionState, selectedId, onToggleArc, onToggleChapter]);

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

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        fitView
        minZoom={0.1}
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
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
