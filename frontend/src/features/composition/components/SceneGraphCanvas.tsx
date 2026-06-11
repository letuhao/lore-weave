// LOOM Composition (T1.3) — Scene Graph: scenes as a 2-D graph of typed causal
// edges (setup→payoff / custom) the linear outline can't show. Auto-laid-out by
// story_order, with drag-to-reposition persisted to work.settings (shared across
// devices). Link-create is pick-two-nodes + a button (a11y/testable): click scene
// A then B (both ring), choose kind/label, "+ link" → POST (409 dup → toast). An
// edge click selects it → ✕ delete. The open (↗) button jumps to the scene.
// View; all data logic in useOutline/useSceneLinks + useSetWorkSettings.
import { useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { useOutline, useOutlineMutations, useSceneLinks } from '../hooks/useOutline';
import { useSetWorkSettings } from '../hooks/useWork';
import type { OutlineNode, SceneLinkKind, Work } from '../types';
import { SceneNode } from './SceneNode';
import { SceneEdge } from './SceneEdge';
import { autoLayout, NODE_H, NODE_W, PAD, type Pos } from './sceneGraphLayout';

type DragState = { id: string; startX: number; startY: number; origX: number; origY: number; moved: boolean };

export function SceneGraphCanvas({ work, bookId, token }: { work: Work; bookId: string; token: string | null }) {
  const { t } = useTranslation('composition');
  const navigate = useNavigate();
  const projectId = work.project_id;
  const q = useOutline(projectId, token);
  const linksQ = useSceneLinks(projectId, token);
  const m = useOutlineMutations(projectId, token);
  const setSettings = useSetWorkSettings(bookId, token);

  const scenes = useMemo<OutlineNode[]>(
    () => (q.data ?? []).filter((n) => n.kind === 'scene' && !n.is_archived),
    [q.data],
  );
  const auto = useMemo(() => autoLayout(scenes), [scenes]);
  // Persisted drag overrides, seeded once from work.settings (last-write-wins,
  // cosmetic). New scenes with no override fall back to the auto-layout.
  const seed = (work.settings.scene_graph as { positions?: Record<string, Pos> } | undefined)?.positions ?? {};
  const [local, setLocal] = useState<Record<string, Pos>>(seed);
  // Ref mirror of `local` so the drag-end persist reads the latest positions
  // WITHOUT a side-effect inside a setState updater (StrictMode double-fire).
  const localRef = useRef<Record<string, Pos>>(seed);
  const applyLocal = (next: Record<string, Pos>) => { localRef.current = next; setLocal(next); };
  const posOf = (id: string): Pos => local[id] ?? auto[id] ?? { x: PAD, y: PAD };

  const [selected, setSelected] = useState<string[]>([]);
  const [selectedEdge, setSelectedEdge] = useState<string | null>(null);
  const [kind, setKind] = useState<SceneLinkKind>('setup_payoff');
  const [label, setLabel] = useState('');
  const drag = useRef<DragState | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const persist = (positions: Record<string, Pos>) => {
    const sg = (work.settings.scene_graph as Record<string, unknown> | undefined) ?? {};
    setSettings.mutate({ projectId, currentSettings: work.settings, patch: { scene_graph: { ...sg, positions } } });
  };

  const onNodePointerDown = (id: string) => (e: React.PointerEvent) => {
    const p = posOf(id);
    drag.current = { id, startX: e.clientX, startY: e.clientY, origX: p.x, origY: p.y, moved: false };
    try { svgRef.current?.setPointerCapture?.(e.pointerId); } catch { /* jsdom no-op */ }
  };
  const onPointerMove = (e: React.PointerEvent) => {
    const d = drag.current;
    if (!d) return;
    const dx = e.clientX - d.startX;
    const dy = e.clientY - d.startY;
    if (!d.moved && Math.abs(dx) + Math.abs(dy) > 5) d.moved = true; // 5px = drag, else click
    if (d.moved) applyLocal({ ...localRef.current, [d.id]: { x: Math.max(0, d.origX + dx), y: Math.max(0, d.origY + dy) } });
  };
  const onPointerUp = () => {
    const d = drag.current;
    drag.current = null;
    if (!d) return;
    if (d.moved) persist(localRef.current); // commit the dragged position (shared via work.settings)
    else toggleSelect(d.id);               // a click, not a drag → (de)select for link-create
  };

  const toggleSelect = (id: string) => {
    setSelectedEdge(null);
    setSelected((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id].slice(-2)); // keep last 2
  };
  const clearSelection = () => { setSelected([]); setSelectedEdge(null); };

  const addLink = () => {
    if (selected.length !== 2) return;
    m.createSceneLink.mutate(
      { from_node_id: selected[0], to_node_id: selected[1], kind, label: label.trim() },
      {
        onSuccess: () => { setSelected([]); setLabel(''); },
        onError: (e) => {
          const status = (e as { status?: number }).status;
          toast.error(status === 409
            ? t('scenegraph.linkExists', { defaultValue: 'A link of that kind already exists between these scenes.' })
            : t('scenegraph.linkFailed', { defaultValue: 'Could not create the link.' }));
        },
      },
    );
  };
  const deleteEdge = (linkId: string) =>
    m.deleteSceneLink.mutate(linkId, { onSuccess: () => setSelectedEdge(null) });
  const openScene = (n: OutlineNode) => { if (n.chapter_id) navigate(`/books/${bookId}/chapters/${n.chapter_id}/edit`); };

  // Canvas extent from the laid-out nodes (so the scroll area fits everything).
  // Links are drawn only between two visible scenes (/review-impl LOW-2: this UI
  // only ever creates scene→scene links, so a link to an archived/non-scene node
  // would render nowhere — acceptable since no other surface authors such links).
  const inGraph = new Set(scenes.map((s) => s.id));
  const links = (linksQ.data ?? []).filter((l) => inGraph.has(l.from_node_id) && inGraph.has(l.to_node_id));
  const w = Math.max(360, ...scenes.map((s) => posOf(s.id).x + NODE_W + PAD));
  const h = Math.max(220, ...scenes.map((s) => posOf(s.id).y + NODE_H + PAD));

  return (
    <div className="flex h-full flex-col" data-testid="composition-graph">
      <div className="flex flex-shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2 text-[11px]">
        <span className="text-muted-foreground">{t('scenegraph.title', { defaultValue: 'Scene Graph' })}</span>
        {selected.length < 2 ? (
          <span className="text-muted-foreground/70">
            {t('scenegraph.selectTwo', { defaultValue: 'Click two scenes to link them ({{n}}/2)', n: selected.length })}
          </span>
        ) : (
          <div className="flex items-center gap-1" data-testid="scenegraph-linkbar">
            <select
              data-testid="scenegraph-kind" aria-label={t('scenegraph.linkKind', { defaultValue: 'Link kind' })}
              className="rounded border bg-background px-1 py-0.5" value={kind}
              onChange={(e) => setKind(e.target.value as SceneLinkKind)}
            >
              <option value="setup_payoff">{t('scenegraph.kind_setup_payoff', { defaultValue: 'setup → payoff' })}</option>
              <option value="custom">{t('scenegraph.kind_custom', { defaultValue: 'custom' })}</option>
            </select>
            <input
              data-testid="scenegraph-label" aria-label={t('scenegraph.label', { defaultValue: 'Link label (optional)' })}
              className="w-28 rounded border bg-background px-1 py-0.5" placeholder={t('scenegraph.label', { defaultValue: 'label (optional)' })}
              value={label} onChange={(e) => setLabel(e.target.value)}
            />
            <button
              type="button" data-testid="scenegraph-add"
              className="rounded bg-primary px-2 py-0.5 text-primary-foreground disabled:opacity-50"
              disabled={m.createSceneLink.isPending} onClick={addLink}
            >
              + {t('scenegraph.addLink', { defaultValue: 'link' })}
            </button>
            <button type="button" data-testid="scenegraph-cancel" className="rounded px-2 py-0.5 text-muted-foreground" onClick={clearSelection}>
              {t('scenegraph.cancel', { defaultValue: 'Cancel' })}
            </button>
          </div>
        )}
      </div>

      {scenes.length === 0 ? (
        <div data-testid="scenegraph-empty" className="p-3 text-xs text-muted-foreground">
          {t('scenegraph.empty', { defaultValue: 'No scenes yet — plan some scenes in the outline to see the graph.' })}
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-auto">
          <svg
            ref={svgRef} width={w} height={h} data-testid="scenegraph-svg"
            onPointerMove={onPointerMove} onPointerUp={onPointerUp}
          >
            <defs>
              <marker id="scene-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
                <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
              </marker>
            </defs>
            {/* background: clicking empty space clears any selection */}
            <rect data-testid="scenegraph-bg" width={w} height={h} fill="transparent" onPointerDown={clearSelection} />
            {links.map((l) => (
              <SceneEdge
                key={l.id} link={l} from={posOf(l.from_node_id)} to={posOf(l.to_node_id)}
                selected={selectedEdge === l.id}
                onSelect={() => { setSelected([]); setSelectedEdge(l.id); }}
                onDelete={() => deleteEdge(l.id)}
              />
            ))}
            {scenes.map((n) => (
              <SceneNode
                key={n.id} node={n} pos={posOf(n.id)} selected={selected.includes(n.id)}
                onPointerDown={onNodePointerDown(n.id)} onSelect={() => toggleSelect(n.id)} onOpen={() => openScene(n)}
              />
            ))}
          </svg>
        </div>
      )}
    </div>
  );
}
