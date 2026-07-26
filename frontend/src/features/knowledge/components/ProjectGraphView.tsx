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
import type { TFunction } from 'i18next';
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
import { useProjectGraphSlice } from '../hooks/useProjectGraphSlice';
import { useGraphViews } from '../hooks/useGraphViews';
import type { GraphView } from '../types/ontology';
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

  // S-09 W3 (F-12) — the "lens": a saved view + an as-of-chapter cut. When
  // EITHER is set the panel reads the view-aware `/graph` reader (whole
  // filtered slice, no expand-hop); with neither it keeps the C18 `/subgraph`
  // top-N + click-to-expand behaviour. The two data hooks are both always
  // called (hooks can't be conditional) but each is `enabled` only for its
  // mode, so they never double-fetch.
  const views = useGraphViews(projectId ?? '');
  const [viewCode, setViewCode] = useState<string>('');
  const [asOfText, setAsOfText] = useState<string>('');
  const asOfChapter = useMemo(() => {
    const n = parseInt(asOfText, 10);
    return Number.isFinite(n) && n >= 0 ? n : null;
  }, [asOfText]);
  const lensActive = viewCode !== '' || asOfChapter != null;

  const sg = useProjectSubgraph(projectId, !lensActive);
  const slice = useProjectGraphSlice(projectId, viewCode || null, asOfChapter, lensActive);
  const graph = lensActive ? slice : sg;

  // Map the projection onto the shared node/edge view shapes (reuse).
  const nodes: GraphNode[] = useMemo(
    () => graph.nodes.map((n) => ({ id: n.id, name: n.name, kind: n.kind })),
    [graph.nodes],
  );
  const edges: GraphEdge[] = useMemo(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        from: e.source,
        to: e.target,
        predicate: e.predicate,
        pending: false, // both readers return only active edges
        confidence: e.confidence,
      })),
    [graph.edges],
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

  // The lens toolbar renders in EVERY non-fatal state (loading / empty /
  // populated) so a user can always change or clear the lens — an empty
  // as-of-chapter slice must not trap them behind a bare "no graph" hint.
  const toolbar = (
    <LensToolbar
      t={t}
      views={views.views}
      viewCode={viewCode}
      onViewCode={setViewCode}
      asOfText={asOfText}
      onAsOfText={setAsOfText}
      active={lensActive}
      onClear={() => { setViewCode(''); setAsOfText(''); }}
    />
  );

  if (graph.isLoading) {
    return (
      <div className="flex h-[70vh] flex-col rounded-md border" data-testid="project-graph-view">
        {toolbar}
        <Hint>{t('graph.loading', { defaultValue: 'Loading graph…' })}</Hint>
      </div>
    );
  }
  if (graph.error) {
    return (
      <div className="flex flex-col rounded-md border" data-testid="project-graph-view">
        {toolbar}
        <div
          role="alert"
          className="m-3 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-[12px] text-destructive"
          data-testid="project-graph-error"
        >
          {t('graph.loadFailed', { defaultValue: 'Failed to load graph: {{error}}', error: graph.error.message })}
        </div>
      </div>
    );
  }
  if (nodes.length === 0) {
    return (
      <div className="flex flex-col rounded-md border" data-testid="project-graph-view">
        {toolbar}
        <Hint>
          {lensActive
            ? t('graph.emptyLens', { defaultValue: 'No relations match this lens — try another view or an earlier chapter, or clear the lens.' })
            : t('graph.empty', { defaultValue: 'No knowledge graph yet — build this project to explore its network.' })}
        </Hint>
      </div>
    );
  }

  return (
    <div className="flex h-[70vh] flex-col rounded-md border" data-testid="project-graph-view">
      {toolbar}
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
        {graph.truncated && (
          <span data-testid="project-graph-truncated" className="text-amber-600 dark:text-amber-400">
            {lensActive
              ? t('graph.truncatedLens', { defaultValue: 'showing the first {{n}} relations of this lens', n: edges.length })
              : t('graph.truncated', { defaultValue: 'showing the top {{n}} — expand a node to load more', n: nodes.length })}
          </span>
        )}
        {!lensActive && sg.expandingId && (
          <span data-testid="project-graph-expanding" className="text-primary">
            {t('graph.expanding', { defaultValue: 'expanding…' })}
          </span>
        )}
        <span className="ml-auto text-muted-foreground/70">
          {lensActive
            ? t('graph.hintLens', { defaultValue: 'Scroll to zoom · drag to pan · click a node for detail' })
            : t('graph.hint', { defaultValue: 'Scroll to zoom · drag empty space to pan · click a node for detail · ⊞ to expand' })}
        </span>
      </div>
      {lensActive && slice.warnings.length > 0 && (
        <div
          data-testid="project-graph-warnings"
          className="flex-shrink-0 border-b bg-amber-50 px-3 py-1.5 text-[11px] text-amber-700 dark:bg-amber-950/30 dark:text-amber-400"
        >
          {slice.warnings.join(' · ')}
        </div>
      )}

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
                expanded={!lensActive && sg.expandedIds.includes(id)}
                onPointerDown={h.onPointerDown}
                onActivate={() => setSelectedId(id)}
                // Expand-hop fired DIRECTLY from the click handler (FE event
                // rule: never a useEffect reacting to state). Undefined in lens
                // mode (the lens is the whole scope) → GraphEntityNode hides ⊞.
                onExpand={lensActive ? undefined : () => void sg.expand(id)}
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

// S-09 W3 — the lens controls: pick a saved view (the lenses ViewBuilder
// authors) + scrub an as-of-chapter cut. Empty view + empty chapter = the
// default `/subgraph` mode. A "Clear" button escapes the lens (so an empty
// filtered slice is never a dead end). Pure presentational — all state lives
// in the parent (FE MVC).
function LensToolbar({
  t,
  views,
  viewCode,
  onViewCode,
  asOfText,
  onAsOfText,
  active,
  onClear,
}: {
  t: TFunction<'knowledge'>;
  views: GraphView[];
  viewCode: string;
  onViewCode: (code: string) => void;
  asOfText: string;
  onAsOfText: (text: string) => void;
  active: boolean;
  onClear: () => void;
}) {
  return (
    <div
      data-testid="project-graph-lens"
      className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2 text-[11px]"
    >
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">{t('graph.lens.view', { defaultValue: 'View' })}</span>
        <select
          data-testid="project-graph-view-select"
          value={viewCode}
          onChange={(e) => onViewCode(e.target.value)}
          className="rounded border bg-background px-1.5 py-1 text-[11px]"
        >
          <option value="">{t('graph.lens.noView', { defaultValue: 'All relations' })}</option>
          {views.map((v) => (
            <option key={v.code} value={v.code}>{v.name}</option>
          ))}
        </select>
      </label>
      <label className="flex items-center gap-1.5">
        <span className="text-muted-foreground">{t('graph.lens.asOf', { defaultValue: 'As of chapter' })}</span>
        <input
          type="number"
          min={0}
          inputMode="numeric"
          data-testid="project-graph-asof-input"
          value={asOfText}
          onChange={(e) => onAsOfText(e.target.value)}
          placeholder={t('graph.lens.latest', { defaultValue: 'latest' })}
          className="w-20 rounded border bg-background px-1.5 py-1 text-[11px]"
        />
      </label>
      {active && (
        <button
          type="button"
          data-testid="project-graph-lens-clear"
          onClick={onClear}
          className="rounded border px-2 py-1 text-[11px] text-muted-foreground hover:bg-secondary hover:text-foreground"
        >
          {t('graph.lens.clear', { defaultValue: 'Clear lens' })}
        </button>
      )}
    </div>
  );
}
