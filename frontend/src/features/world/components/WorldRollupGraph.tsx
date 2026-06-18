// W5 (G4) — the WORLD rollup graph canvas. Renders the W2
// `GET /worlds/{id}/subgraph` union: each member book's canon subgraph + the
// world-level (bible) project, as one explorable network. REUSES the same
// shared primitives as the C19 ProjectGraphView (GraphCanvas SVG + node-drag,
// GraphEntityNode, RelationEdge, radialLayout, EntityDetailPanel) rather than
// forking them — it just sources from the flat world union instead of a single
// project, and has NO expand-hop (the per-book islands are disconnected
// components by design; the endpoint has no `center`).
//
// Read-only: click a node → the existing EntityDetailPanel. The detail panel's
// book-scoped pin control is intentionally NOT wired here (a rollup node can be
// from any member book — passing one book's id would mis-scope the pin), so the
// canvas stays purely a read view.
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
import { EntityDetailPanel } from '@/features/knowledge/components/EntityDetailPanel';
import { useWorldSubgraph } from '../hooks/useWorldSubgraph';

interface WorldRollupGraphProps {
  worldId: string | undefined;
}

export function WorldRollupGraph({ worldId }: WorldRollupGraphProps) {
  const { t } = useTranslation('world');
  const sg = useWorldSubgraph(worldId);

  // Map the union projection onto the shared node/edge view shapes (reuse).
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
        pending: false,
        confidence: e.confidence,
      })),
    [sg.edges],
  );

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

  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (sg.isLoading) {
    return <Hint>{t('graph.loading', { defaultValue: 'Loading world graph…' })}</Hint>;
  }
  if (sg.error) {
    return (
      <div
        role="alert"
        className="rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
        data-testid="world-graph-error"
      >
        {t('graph.loadFailed', {
          defaultValue: 'Failed to load the world graph: {{error}}',
          error: sg.error.message,
        })}
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <Hint>
        {t('graph.empty', {
          defaultValue:
            'No world knowledge yet — build the bible or extract a member book to roll its graph up here.',
        })}
      </Hint>
    );
  }

  return (
    <div className="flex h-[70vh] flex-col rounded-md border" data-testid="world-rollup-graph">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="font-medium text-foreground">
          {t('graph.title', { defaultValue: 'World graph' })}
        </span>
        <span className="text-muted-foreground" data-testid="world-graph-counts">
          {t('graph.counts', {
            defaultValue: '{{nodes}} nodes · {{edges}} relations',
            nodes: nodes.length,
            edges: edges.length,
          })}
        </span>
        {/* Per-book island legend (decision ②): the rollup is a union of each
            book's canon graph as disconnected components, not one merged graph. */}
        <span
          className="rounded bg-secondary px-1.5 py-0.5 text-muted-foreground"
          data-testid="world-graph-sources"
        >
          {t('graph.sources', {
            defaultValue: 'rolled up from {{count}} book(s)',
            count: sg.sources.length,
          })}
        </span>
        {sg.truncated && (
          <span data-testid="world-graph-truncated" className="text-amber-600 dark:text-amber-400">
            {t('graph.truncated', {
              defaultValue: 'showing the top {{n}} — a large book can crowd a smaller one',
              n: nodes.length,
            })}
          </span>
        )}
        <span className="ml-auto text-muted-foreground/70">
          {t('graph.hint', {
            defaultValue: 'Scroll to zoom · drag empty space to pan · click a node for detail',
          })}
        </span>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col">
        <GraphCanvas<GraphEdge>
          testid="world-graph-svg"
          zoomable
          positions={positions}
          nodeIds={nodes.map((n) => n.id)}
          edges={edges}
          edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
          edgeKey={(e) => e.id}
          nodeSize={{ w: ENTITY_NODE_W, h: ENTITY_NODE_H }}
          onNodeClick={(id) => setSelectedId(id)}
          onNodeDrag={(id, pos) => applyLocal({ ...localRef.current, [id]: pos })}
          onBackgroundClick={() => { /* selection lives in the panel */ }}
          defs={(
            <marker id="world-graph-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
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
                expanded={false}
                onPointerDown={h.onPointerDown}
                onActivate={() => setSelectedId(id)}
                // No onExpand — the world rollup is a flat union (no ego-hop).
              />
            );
          }}
        />
      </div>

      {/* Read-only: click → existing detail slide-over. No bookId (a rollup
          node can be from any member book). */}
      <EntityDetailPanel
        open={!!selectedId}
        onOpenChange={(o) => { if (!o) setSelectedId(null); }}
        entityId={selectedId}
      />
    </div>
  );
}

// Pick the most-connected node as the radial centre (stable, cheap). Pure.
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
  <div className="rounded-md border border-dashed p-6 text-center text-xs text-muted-foreground" data-testid="world-graph-hint">
    {children}
  </div>
);
