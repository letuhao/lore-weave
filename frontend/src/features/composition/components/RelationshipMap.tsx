// LOOM Composition (T2.2) — Relationship Map: an ego-network of entities + typed
// RELATES_TO relations. Pick a focus → its 1-hop; click a neighbour to re-focus;
// ⊞ a node to accrete its 1-hop (capped). Built on the shared <GraphCanvas> (T1.3).
// Drag positions persist per-device in localStorage. Render-only; logic in
// useRelationshipMap.
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GraphCanvas, type Pos } from './GraphCanvas';
import { GraphEntityNode, ENTITY_NODE_H, ENTITY_NODE_W } from './GraphEntityNode';
import { RelationEdge } from './RelationEdge';
import { buildGraph, radialLayout, useRelationshipMap, type GraphEdge } from '../hooks/useRelationshipMap';

function readPositions(key: string): Record<string, Pos> {
  try { return JSON.parse(localStorage.getItem(key) ?? '{}') as Record<string, Pos>; } catch { return {}; }
}
function writePositions(key: string, pos: Record<string, Pos>) {
  try { localStorage.setItem(key, JSON.stringify(pos)); } catch { /* quota / disabled — cosmetic, ignore */ }
}

export function RelationshipMap({ bookId, token }: { bookId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const rm = useRelationshipMap(bookId, token);
  const { nodes, edges, truncated } = useMemo(() => buildGraph(rm.details), [rm.details]);

  const storageKey = `loreweave.relmap.${bookId}`;
  const [local, setLocal] = useState<Record<string, Pos>>(() => readPositions(storageKey));
  const localRef = useRef<Record<string, Pos>>(local);
  const applyLocal = (next: Record<string, Pos>) => { localRef.current = next; setLocal(next); };
  const persist = (pos: Record<string, Pos>) => { localRef.current = pos; writePositions(storageKey, pos); };

  const auto = useMemo(() => radialLayout(nodes.map((n) => n.id), rm.focusId), [nodes, rm.focusId]);
  const positions = useMemo(() => {
    const acc: Record<string, Pos> = {};
    for (const n of nodes) acc[n.id] = local[n.id] ?? auto[n.id] ?? { x: 24, y: 24 };
    return acc;
  }, [nodes, local, auto]);
  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  // /review-impl MED-1: a controlled <select value={focusId}> needs focusId to be
  // an option, else it renders blank while the graph is focused. Re-focusing onto a
  // neighbour not in the (capped) entity list — or any out-of-list focus — would
  // desync the picker. Always surface the current focus as an option.
  const pickerOptions = useMemo(() => {
    const opts = rm.entities.map((e) => ({ id: e.id, name: e.name }));
    if (rm.focusId && !opts.some((o) => o.id === rm.focusId)) {
      opts.unshift({ id: rm.focusId, name: byId.get(rm.focusId)?.name ?? rm.focusId });
    }
    return opts;
  }, [rm.entities, rm.focusId, byId]);

  return (
    <div className="flex h-full flex-col" data-testid="composition-relmap">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('relations.title', { defaultValue: 'Relationship Map' })}</span>
        <label className="flex items-center gap-1">
          <span className="text-muted-foreground/70">{t('relations.focus', { defaultValue: 'Focus' })}</span>
          <select
            data-testid="relmap-focus-select"
            aria-label={t('relations.focus', { defaultValue: 'Focus entity' })}
            className="max-w-[10rem] rounded border bg-background px-1 py-0.5"
            value={rm.focusId ?? ''}
            onChange={(e) => rm.setFocus(e.target.value)}
          >
            {pickerOptions.map((en) => <option key={en.id} value={en.id}>{en.name}</option>)}
          </select>
        </label>
        {truncated && (
          <span data-testid="relmap-truncated" className="text-amber-600 dark:text-amber-400">
            {t('relations.truncated', { defaultValue: 'showing the first {{n}} nodes', n: nodes.length })}
          </span>
        )}
      </div>

      {rm.projectLoading || rm.entitiesLoading ? (
        <Hint>{t('relations.loading', { defaultValue: 'Loading relationship map…' })}</Hint>
      ) : !rm.projectId || rm.entities.length === 0 ? (
        <Hint>{t('relations.noProject', { defaultValue: 'No knowledge graph yet — extract this book to map relationships.' })}</Hint>
      ) : (
        <div className="relative flex min-h-0 flex-1 flex-col">
          {edges.length === 0 && !rm.detailsLoading && (
            <div data-testid="relmap-empty" className="border-b bg-muted/40 px-3 py-1 text-[10px] text-muted-foreground">
              {t('relations.noRelations', { defaultValue: 'This entity has no relations yet.' })}
            </div>
          )}
          <GraphCanvas<GraphEdge>
            testid="relmap-svg"
            positions={positions}
            nodeIds={nodes.map((n) => n.id)}
            edges={edges}
            edgeEndpoints={(e) => ({ from: e.from, to: e.to })}
            edgeKey={(e) => e.id}
            nodeSize={{ w: ENTITY_NODE_W, h: ENTITY_NODE_H }}
            onNodeClick={(id) => rm.setFocus(id)}
            onNodeDrag={(id, pos) => applyLocal({ ...localRef.current, [id]: pos })}
            onNodeDragEnd={() => persist(localRef.current)}
            defs={(
              <marker id="relmap-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
              </marker>
            )}
            renderEdge={(e, from, to) => <RelationEdge edge={e} from={from} to={to} />}
            renderNode={(id, h) => {
              const n = byId.get(id)!;
              return (
                <GraphEntityNode
                  node={n} pos={positions[id]} isFocus={id === rm.focusId} expanded={rm.expanded.includes(id)}
                  onPointerDown={h.onPointerDown} onActivate={() => rm.setFocus(id)} onExpand={() => rm.toggleExpand(id)}
                />
              );
            }}
          />
        </div>
      )}
    </div>
  );
}

const Hint = ({ children }: { children: React.ReactNode }) => (
  <div className="p-3 text-xs text-muted-foreground">{children}</div>
);
