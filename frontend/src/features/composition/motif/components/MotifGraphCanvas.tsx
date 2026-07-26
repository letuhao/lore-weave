// Wave-4 (D-MOTIF-GRAPH-CANVAS) — the book-wide motif graph as a draggable reactflow (v11) canvas
// with PER-VIEWER persisted positions. Controlled nodes + onNodesChange (else a drag never moves the
// card under the cursor); nodeDragThreshold so a click isn't a 0px drag; drag-end → the hook's
// debounced persist. Positions seed from the stored layout, falling back to the bespoke layered
// auto-layout. Read-only (no EDIT) freezes edge tools but NOT the layout drag — positions are the
// viewer's own (they arrange their view of any graph they can see).
import { useEffect } from 'react';
import ReactFlow, {
  Background, Controls, ReactFlowProvider, useEdgesState, useNodesState,
  type Edge, type Node, type NodeDragHandler,
} from 'reactflow';
import 'reactflow/dist/style.css';
import { useTranslation } from 'react-i18next';
import { useMotifGraph } from '../hooks/useMotifGraph';
import { autoLayout } from '../motifGraphLayout';

const KIND_COLOR: Record<string, string> = {
  composed_of: '#8b5cf6', precedes: '#0ea5e9', variant_of: '#f59e0b',
};

type Props = { bookId: string | null; token: string | null; readOnly?: boolean };

function MotifGraphInner({ bookId, token, readOnly = false }: Props) {
  const { t } = useTranslation('composition');
  const graph = useMotifGraph(bookId, token);
  const [nodes, setNodes, onNodesChange] = useNodesState([] as Node[]);
  const [edges, setEdges] = useEdgesState([] as Edge[]);

  // Reset RF's controlled nodes from the source-of-truth whenever the graph (re)loads. Positions:
  // the stored per-viewer layout wins; an un-positioned node falls to its auto-layout slot.
  useEffect(() => {
    const d = graph.data;
    if (!d) return;
    const auto = autoLayout(d.nodes, d.edges);
    setNodes(d.nodes.map((n) => ({
      id: n.id,
      position: d.layout.positions[n.id] ?? auto[n.id] ?? { x: 24, y: 24 },
      data: { label: `${n.name}${n.mine ? '' : ' ·'}` },
      draggable: !readOnly,
      style: {
        fontSize: 11, borderRadius: 6, padding: '4px 8px', width: 150,
        border: n.mine ? '1px solid #8b5cf6' : '1px dashed #94a3b8',
      },
    })));
    setEdges(d.edges.map((e) => ({
      id: e.id, source: e.from_motif_id, target: e.to_motif_id, label: e.kind,
      style: { stroke: KIND_COLOR[e.kind] ?? '#94a3b8' }, labelStyle: { fontSize: 9 },
    })));
  }, [graph.data, readOnly, setNodes, setEdges]);

  const onNodeDragStop: NodeDragHandler = (_evt, node) => {
    if (readOnly) return;
    graph.savePosition(node.id, Math.round(node.position.x), Math.round(node.position.y));
  };

  if (graph.isLoading) {
    return <p data-testid="motif-graph-loading" className="p-4 text-center text-xs text-muted-foreground">{t('motif.graph.canvasLoading', { defaultValue: 'Loading the motif graph…' })}</p>;
  }
  if (graph.isError) {
    return (
      <p data-testid="motif-graph-error" className="p-4 text-center text-xs text-destructive">
        {t('motif.graph.error', { defaultValue: 'Could not load the motif graph.' })}
        <button type="button" className="ml-2 underline" onClick={() => graph.refetch()}>{t('motif.graph.retry', { defaultValue: 'Retry' })}</button>
      </p>
    );
  }
  if ((graph.data?.nodes.length ?? 0) === 0) {
    return <p data-testid="motif-graph-empty" className="p-4 text-center text-xs text-muted-foreground">{t('motif.graph.canvasEmpty', { defaultValue: 'No motifs to graph yet — create or adopt motifs, then link them.' })}</p>;
  }

  return (
    <div data-testid="motif-graph-canvas" className="relative h-full min-h-[240px] w-full">
      {graph.data?.truncated && (
        <p data-testid="motif-graph-truncated" className="absolute left-1 top-1 z-10 rounded bg-amber-100 px-2 py-0.5 text-[10px] text-amber-900 dark:bg-amber-950/60 dark:text-amber-200">
          {t('motif.graph.truncated', { cap: graph.data.node_cap, defaultValue: 'Showing the first {{cap}} motifs — narrow by tier or search to see more.' })}
        </p>
      )}
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onNodeDragStop={onNodeDragStop}
        nodesDraggable={!readOnly}
        nodesConnectable={false}
        nodeDragThreshold={5}
        fitView
        proOptions={{ hideAttribution: true }}
      >
        <Background />
        <Controls showInteractive={false} />
      </ReactFlow>
    </div>
  );
}

export function MotifGraphCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <MotifGraphInner {...props} />
    </ReactFlowProvider>
  );
}
