import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GraphCanvas, type Pos } from '@/features/composition/components/GraphCanvas';
import type { GraphSchemaTree } from '../../types/ontology';

// M2 — visual type-graph canvas: node KINDS are draggable boxes, edge TYPES are
// labeled arrows between them (source_kind → target_kind). Reuses the composition
// GraphCanvas (drag-arrange, pan/zoom). "Draw an edge" = click a node's ⇢ handle,
// then click a target node → an inline new-edge popover (code+label) → create.
// Detailed attribute editing stays in the List view (the Canvas/List toggle).

const NODE = { w: 132, h: 44 };
const R = 190; // circle-layout radius

function circleLayout(codes: string[]): Record<string, Pos> {
  const cx = R + NODE.w, cy = R + NODE.h;
  const out: Record<string, Pos> = {};
  codes.forEach((c, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, codes.length) - Math.PI / 2;
    out[c] = { x: Math.round(cx + R * Math.cos(a)), y: Math.round(cy + R * Math.sin(a)) };
  });
  return out;
}

interface Arrow { key: string; code: string; from: string; to: string }

interface Props {
  schema: GraphSchemaTree;
  disabled?: boolean;
  onAddKind: (code: string) => void;
  onAddEdge: (code: string, label: string, from: string, to: string) => void;
}

export function SchemaCanvas({ schema, disabled, onAddKind, onAddEdge }: Props) {
  const { t } = useTranslation('kgOntology');
  const kinds = useMemo(() => (schema.node_kinds ?? []).map((k) => k.kind_code), [schema.node_kinds]);
  const strengthOf = useMemo(
    () => Object.fromEntries((schema.node_kinds ?? []).map((k) => [k.kind_code, k.strength])),
    [schema.node_kinds],
  );

  const defined = useMemo(() => new Set(kinds), [kinds]);

  const [positions, setPositions] = useState<Record<string, Pos>>(() => circleLayout(kinds));
  // keep positions when kinds are added/removed. review-impl #3: place each NEW
  // kind on a golden-angle spiral from the centre (not all at one point) so a bulk
  // add (AI-generate while on Canvas) doesn't stack them.
  useEffect(() => {
    setPositions((p) => {
      const next = { ...p };
      let changed = false;
      let placed = Object.keys(next).length;
      for (const c of kinds)
        if (!next[c]) {
          const a = placed * 2.399963; // golden angle
          const r = 40 + 26 * Math.sqrt(placed);
          next[c] = { x: Math.round(R + NODE.w + r * Math.cos(a)), y: Math.round(R + NODE.h + r * Math.sin(a)) };
          placed++;
          changed = true;
        }
      for (const c of Object.keys(next)) if (!kinds.includes(c)) { delete next[c]; changed = true; }
      return changed ? next : p;
    });
  }, [kinds]);

  // Arrows only for pairs where BOTH endpoint kinds are defined (an arrow to an
  // undefined kind can't be positioned anyway).
  const arrows: Arrow[] = useMemo(
    () =>
      (schema.edge_types ?? []).flatMap((et) =>
        (et.source_node_kinds ?? []).filter((s) => defined.has(s)).flatMap((s) =>
          (et.target_node_kinds ?? []).filter((tg) => defined.has(tg)).map((tg) => ({ key: `${et.code}:${s}:${tg}`, code: et.code, from: s, to: tg })),
        ),
      ),
    [schema.edge_types, defined],
  );
  // review-impl #2: an edge with NO renderable arrow (empty endpoints OR an endpoint
  // that isn't a defined kind) would otherwise be invisible — surface it in the tray.
  const looseEdges = useMemo(
    () =>
      (schema.edge_types ?? []).filter(
        (e) =>
          !(e.source_node_kinds ?? []).some((s) => defined.has(s)) ||
          !(e.target_node_kinds ?? []).some((tg) => defined.has(tg)),
      ),
    [schema.edge_types, defined],
  );

  const [connectFrom, setConnectFrom] = useState<string | null>(null);
  const [pending, setPending] = useState<{ from: string; to: string } | null>(null);
  const [newCode, setNewCode] = useState('');
  const [newLabel, setNewLabel] = useState('');
  const [addingKind, setAddingKind] = useState('');

  const nodeClick = (id: string) => {
    if (connectFrom && connectFrom !== id) {
      setPending({ from: connectFrom, to: id });
      setConnectFrom(null);
    } else {
      setConnectFrom(null);
    }
  };

  const createEdge = () => {
    if (!pending || !newCode.trim()) return;
    onAddEdge(newCode.trim(), newLabel.trim() || newCode.trim(), pending.from, pending.to);
    setPending(null);
    setNewCode('');
    setNewLabel('');
  };

  return (
    <div className="space-y-2" data-testid="schema-canvas">
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex items-center gap-1">
          <input value={addingKind} onChange={(e) => setAddingKind(e.target.value)} placeholder={t('canvas.newKindPlaceholder')}
            className="w-32 rounded-md border bg-input px-2 py-1 text-[12px]" data-testid="canvas-new-kind" />
          <button type="button" disabled={disabled || !addingKind.trim()}
            onClick={() => { onAddKind(addingKind.trim()); setAddingKind(''); }}
            className="rounded-md border px-2 py-1 text-[12px] disabled:opacity-50" data-testid="canvas-add-kind">
            {t('canvas.addKind')}
          </button>
        </div>
        <span className="text-[11px] text-muted-foreground">
          {connectFrom ? t('canvas.connectingFrom', { code: connectFrom }) : t('canvas.hint')}
        </span>
      </div>

      <div className="relative flex h-[min(70vh,640px)] min-h-[420px] flex-col rounded-lg border bg-card/40">
        <GraphCanvas<Arrow>
          zoomable
          autoFit
          testid="schema-graph"
          positions={positions}
          nodeIds={kinds}
          edges={arrows}
          edgeEndpoints={(a) => ({ from: a.from, to: a.to })}
          edgeKey={(a) => a.key}
          nodeSize={NODE}
          onNodeClick={nodeClick}
          onNodeDrag={(id, pos) => setPositions((p) => ({ ...p, [id]: pos }))}
          onBackgroundClick={() => setConnectFrom(null)}
          defs={
            <marker id="kg-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" className="fill-muted-foreground" />
            </marker>
          }
          renderEdge={(a, from, to) => {
            const mx = (from.x + to.x) / 2 + NODE.w / 2;
            const my = (from.y + to.y) / 2 + NODE.h / 2;
            return (
              <g data-testid={`canvas-edge-${a.key}`}>
                <line x1={from.x + NODE.w / 2} y1={from.y + NODE.h / 2} x2={to.x + NODE.w / 2} y2={to.y + NODE.h / 2}
                  className="stroke-muted-foreground/60" strokeWidth={1.5} markerEnd="url(#kg-arrow)" />
                <text x={mx} y={my} textAnchor="middle" className="fill-muted-foreground text-[9px]">{a.code}</text>
              </g>
            );
          }}
          renderNode={(id, h) => {
            const p = positions[id] ?? { x: 0, y: 0 };
            return (
              <foreignObject x={p.x} y={p.y} width={NODE.w} height={NODE.h} data-testid={`canvas-node-${id}`}>
                <div
                  onPointerDown={h.onPointerDown}
                  className={`flex h-full cursor-move items-center justify-between gap-1 rounded-md border px-2 text-[12px] shadow-sm ${
                    connectFrom === id ? 'border-primary bg-primary/10' : 'border-border bg-card'
                  }`}
                >
                  <span className="truncate">
                    {id}
                    <span className="ml-1 text-[9px] text-muted-foreground">{strengthOf[id]}</span>
                  </span>
                  <button
                    type="button"
                    disabled={disabled}
                    onPointerDown={(e) => { e.stopPropagation(); }}
                    onClick={(e) => { e.stopPropagation(); setConnectFrom(id); }}
                    className="rounded border px-1 text-[11px] text-primary hover:bg-primary/10"
                    data-testid={`canvas-connect-${id}`}
                    title={t('canvas.connect')}
                  >⇢</button>
                </div>
              </foreignObject>
            );
          }}
        />

        {/* inline new-edge popover after a connect */}
        {pending && (
          <div className="absolute left-1/2 top-2 z-10 -translate-x-1/2 space-y-1.5 rounded-md border bg-card p-2 shadow-lg"
            data-testid="canvas-new-edge">
            <p className="text-[11px] text-muted-foreground">{pending.from} → {pending.to}</p>
            <div className="flex items-center gap-1">
              <input value={newCode} onChange={(e) => setNewCode(e.target.value)} placeholder="MENTOR_OF" autoFocus
                className="w-28 rounded-md border bg-input px-1.5 py-0.5 text-[11px]" data-testid="canvas-edge-code" />
              <input value={newLabel} onChange={(e) => setNewLabel(e.target.value)} placeholder={t('schema.label')}
                className="w-28 rounded-md border bg-input px-1.5 py-0.5 text-[11px]" data-testid="canvas-edge-label" />
              <button type="button" onClick={createEdge} disabled={disabled || !newCode.trim()}
                className="rounded-md bg-primary px-2 py-0.5 text-[11px] text-primary-foreground disabled:opacity-50"
                data-testid="canvas-edge-create">{t('schema.addButton')}</button>
              <button type="button" onClick={() => setPending(null)}
                className="rounded-md border px-2 py-0.5 text-[11px]">{t('common.cancel')}</button>
            </div>
          </div>
        )}

        {kinds.length === 0 && (
          <p className="absolute inset-0 flex items-center justify-center text-[12px] text-muted-foreground">
            {t('canvas.empty')}
          </p>
        )}
      </div>

      {looseEdges.length > 0 && (
        <p className="text-[11px] text-muted-foreground" data-testid="canvas-loose-edges">
          {t('canvas.looseEdges')}: {looseEdges.map((e) => e.code).join(', ')}
        </p>
      )}
    </div>
  );
}
