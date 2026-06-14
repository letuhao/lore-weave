// C19 (G5) — Project Graph canvas: the whole-project knowledge subgraph as
// an explorable visual network. GENERALIZES the T2.2 RelationshipMap
// ego-network pattern into a project-subgraph renderer — it REUSES the same
// shared primitives (GraphCanvas SVG layer + node-drag, GraphEntityNode,
// RelationEdge, radialLayout) instead of forking them, and sources its data
// from C18's `GET /projects/{id}/subgraph` (a real project-wide graph)
// rather than client-side ego-accretion.
//
// Read-only: click a node → the existing EntityDetailPanel (whose own edit /
// merge dialogs are the only edit surface; the canvas never mutates). ⊞ a
// node → expand-hop (re-query C18 `center`, MERGE — no full reload), fired
// from the click handler (never a useEffect-for-events). Pan/zoom via the
// canvas's opt-in `zoomable` mode. The node cap is honoured (the hook bounds
// the accreted union) so a runaway expand can't collapse the SVG. All
// fetch/cache/merge logic lives in useProjectSubgraph (FE MVC).
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GraphCanvas, type Pos } from '@/features/composition/components/GraphCanvas';
import {
  GraphEntityNode,
  ENTITY_NODE_H,
  ENTITY_NODE_W,
} from '@/features/composition/components/GraphEntityNode';
import { RelationEdge } from '@/features/composition/components/RelationEdge';
import {
  radialLayout,
  type GraphNode,
  type GraphEdge,
} from '@/features/composition/hooks/useRelationshipMap';
import { useProjectSubgraph } from '../hooks/useProjectSubgraph';
import { EntityDetailPanel } from './EntityDetailPanel';

export interface ProjectGraphViewProps {
  /** Route-scoped project (G6). */
  projectId: string | undefined;
  /** The project's linked book — threaded into the detail panel for the
   *  book-scoped glossary pin control (read-only canvas otherwise). */
  bookId?: string | null;
}

export function ProjectGraphView({ projectId, bookId }: ProjectGraphViewProps) {
  const { t } = useTranslation('knowledge');
  const sg = useProjectSubgraph(projectId);

  // Map the C18 projection onto the shared node/edge view shapes (reuse).
  const nodes: GraphNode[] = useMemo(
    () => sg.nodes.map((n) => ({ id: n.id, name: n.name, kind: n.kind })),
    [sg.nodes],
  );
  const edges: GraphEdge[] = useMemo(
    () =>
      sg.edges.map((e) => ({
        id: e.id,
        from: e.source,
        to: e.target,
        predicate: e.predicate,
        pending: false, // subgraph returns only active edges (C18)
        confidence: e.confidence,
      })),
    [sg.edges],
  );

  // Hand-rolled radial layout (reused from the ego-network), seeded from the
  // highest-degree node so the densest hub anchors the centre. Per-device
  // drag overrides are held locally (no server layout).
  const center = useMemo(() => mostConnected(nodes, edges), [nodes, edges]);
  const auto = useMemo(() => radialLayout(nodes.map((n) => n.id), center), [nodes, center]);
  const [local, setLocal] = useState<Record<string, Pos>>({});
  const localRef = useRef<Record<string, Pos>>(local);
  const applyLocal = (next: Record<string, Pos>) => { localRef.current = next; setLocal(next); };
  const positions = useMemo(() => {
    const acc: Record<string, Pos> = {};
    for (const n of nodes) acc[n.id] = local[n.id] ?? auto[n.id] ?? { x: 24, y: 24 };
    return acc;
  }, [nodes, local, auto]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  // Read-only selection → reuse the existing entity detail slide-over.
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (sg.isLoading) {
    return <Hint>{t('graph.loading', { defaultValue: 'Loading graph…' })}</Hint>;
  }
  if (sg.error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="project-graph-error"
      >
        {t('graph.loadFailed', { defaultValue: 'Failed to load graph: {{error}}', error: sg.error.message })}
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <Hint>
        {t('graph.empty', { defaultValue: 'No knowledge graph yet — build this project to explore its network.' })}
      </Hint>
    );
  }

  return (
    <div className="flex h-[70vh] flex-col rounded-md border" data-testid="project-graph-view">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="font-medium text-foreground">
          {t('graph.title', { defaultValue: 'Knowledge graph' })}
        </span>
        <span className="text-muted-foreground" data-testid="project-graph-counts">
          {t('graph.counts', {
            defaultValue: '{{nodes}} nodes · {{edges}} relations',
            nodes: nodes.length,
            edges: edges.length,
          })}
        </span>
        {sg.truncated && (
          <span data-testid="project-graph-truncated" className="text-amber-600 dark:text-amber-400">
            {t('graph.truncated', { defaultValue: 'showing the top {{n}} — expand a node to load more', n: nodes.length })}
          </span>
        )}
        {sg.expandingId && (
          <span data-testid="project-graph-expanding" className="text-primary">
            {t('graph.expanding', { defaultValue: 'expanding…' })}
          </span>
        )}
        <span className="ml-auto text-muted-foreground/70">
          {t('graph.hint', { defaultValue: 'Scroll to zoom · drag empty space to pan · click a node for detail · ⊞ to expand' })}
        </span>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        <GraphCanvas<GraphEdge>
          testid="project-graph-svg"
          zoomable
          positions={positions}
          nodeIds={nodes.map((n) => n.id)}
          edges={edges}
          edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
          edgeKey={(e) => e.id}
          nodeSize={{ w: ENTITY_NODE_W, h: ENTITY_NODE_H }}
          onNodeClick={(id) => setSelectedId(id)}
          onNodeDrag={(id, pos) => applyLocal({ ...localRef.current, [id]: pos })}
          onBackgroundClick={() => { /* selection lives in the panel; nothing to clear */ }}
          defs={(
            <marker id="project-graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
            </marker>
          )}
          renderEdge={(e, from, to) => <RelationEdge edge={e} from={from} to={to} />}
          renderNode={(id, h) => {
            const n = byId.get(id)!;
            return (
              <GraphEntityNode
                node={n}
                pos={positions[id]}
                isFocus={id === selectedId}
                expanded={sg.expandedIds.includes(id)}
                onPointerDown={h.onPointerDown}
                onActivate={() => setSelectedId(id)}
                // Expand-hop fired DIRECTLY from the click handler (FE event
                // rule: never a useEffect reacting to state).
                onExpand={() => void sg.expand(id)}
              />
            );
          }}
        />
      </div>

      {/* Read-only: click → existing detail slide-over. Editing happens via
          that panel's own dialogs, never on the canvas. */}
      <EntityDetailPanel
        open={!!selectedId}
        onOpenChange={(o) => { if (!o) setSelectedId(null); }}
        entityId={selectedId}
        bookId={bookId}
      />
    </div>
  );
}

// Pick the node with the most incident edges as the radial centre (a stable,
// cheap heuristic — the hub of the densest cluster). Falls back to the first
// node. Pure (no exported test needed; covered via the component render).
function mostConnected(nodes: GraphNode[], edges: GraphEdge[]): string | null {
  if (nodes.length === 0) return null;
  const deg = new Map<string, number>();
  for (const e of edges) {
    deg.set(e.from, (deg.get(e.from) ?? 0) + 1);
    deg.set(e.to, (deg.get(e.to) ?? 0) + 1);
  }
  let best = nodes[0].id;
  let bestDeg = -1;
  for (const n of nodes) {
    const d = deg.get(n.id) ?? 0;
    if (d > bestDeg) { bestDeg = d; best = n.id; }
  }
  return best;
}

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground" data-testid="project-graph-hint">
    {children}
  </div>
);
