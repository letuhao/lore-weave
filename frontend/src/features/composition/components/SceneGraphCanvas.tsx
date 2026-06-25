// LOOM Composition (T1.3) — Scene Graph: scenes as a 2-D graph of typed causal
// edges (setup→payoff / custom) the linear outline can't show. Auto-laid-out by
// story_order, with drag-to-reposition persisted to work.settings (shared across
// devices). Link-create is pick-two-nodes + a button (a11y/testable): click scene
// A then B (both ring), choose kind/label, "+ link" → POST (409 dup → toast). An
// edge click selects it → ✕ delete. The open (↗) button jumps to the scene.
// View; all data logic in useOutline/useSceneLinks + useSetWorkSettings.
import { useEffect, useMemo, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { aiModelsApi } from '../../ai-models/api';
import { useOutline, useOutlineMutations, useSceneLinks } from '../hooks/useOutline';
import { useSetWorkSettings } from '../hooks/useWork';
import { useSceneWhatIf, whatIfAltPositions, whatIfAltEdges, type WhatIfEdge } from '../hooks/useSceneWhatIf';
import { useWhatIfTakes } from '../hooks/useWhatIfTakes';
import type { OutlineNode, SceneLink, SceneLinkKind, Work } from '../types';
import { SceneNode } from './SceneNode';
import { SceneEdge } from './SceneEdge';
import { WhatIfAltNode } from './WhatIfAltNode';
import { GraphCanvas } from './GraphCanvas';
import { autoLayout, NODE_H, NODE_W, PAD, type Pos } from './sceneGraphLayout';

type GraphEdge = SceneLink | WhatIfEdge;
const isWhatIfEdge = (e: GraphEdge): e is WhatIfEdge => 'wi' in e;

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
  // WS-B3 M1 — the ephemeral on-canvas what-if branch (dashed, beside canon; nothing
  // persisted until a future Promote step). Discard leaves zero residue.
  const whatIf = useSceneWhatIf();
  // M2 — self-contained model picker for take generation (SelectionToolbar precedent;
  // SceneGraphCanvas has no shared model ref). + the generate/judge orchestration.
  const [whatIfModelRef, setWhatIfModelRef] = useState('');
  const whatIfModels = useQuery({
    queryKey: ['composition', 'chat-models'],
    queryFn: () => aiModelsApi.listUserModels(token!, { capability: 'chat' }),
    enabled: !!token && whatIf.active,
    select: (d) => d.items.filter((mm) => mm.is_active),
  });
  const whatIfModelList = whatIfModels.data ?? [];
  const effectiveWhatIfModel = whatIfModelRef || whatIfModelList[0]?.user_model_id || '';
  const selectedWhatIfModel = whatIfModelList.find((mm) => mm.user_model_id === effectiveWhatIfModel);
  const takes = useWhatIfTakes({ projectId, token, updateAlt: whatIf.updateAlt });
  const [previewAltId, setPreviewAltId] = useState<string | null>(null);
  const generateTake = (altId: string) => {
    if (!whatIf.branch) return;
    takes.generateTake(altId, whatIf.branch.anchorSceneId, {
      modelRef: effectiveWhatIfModel,
      modelKind: selectedWhatIfModel?.provider_kind,
      modelName: selectedWhatIfModel?.provider_model_name,
    });
  };

  const persist = (positions: Record<string, Pos>) => {
    const sg = (work.settings.scene_graph as Record<string, unknown> | undefined) ?? {};
    setSettings.mutate({ projectId, currentSettings: work.settings, patch: { scene_graph: { ...sg, positions } } });
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
  const byId = useMemo(() => new Map(scenes.map((s) => [s.id, s])), [scenes]);
  const positions: Record<string, Pos> = Object.fromEntries(scenes.map((s) => [s.id, posOf(s.id)]));

  // WS-B3 M1 — merge the ephemeral what-if branch (dashed alt nodes + edges) into the
  // graph passed to GraphCanvas. Empty when no branch is open (canon graph unchanged).
  const branch = whatIf.branch;
  // Auto-discard the branch if its anchor scene is deleted out from under it (a legit
  // synchronization effect): a what-if is meaningless without its anchor, and a stale
  // anchorSceneId would later derive a branch_point from a non-existent scene (M3).
  useEffect(() => {
    if (branch && !scenes.some((s) => s.id === branch.anchorSceneId)) whatIf.discard();
  }, [branch, scenes, whatIf.discard]);
  const altById = useMemo(() => new Map((branch?.alts ?? []).map((a) => [a.id, a])), [branch]);
  const altPositions = branch ? whatIfAltPositions(branch, posOf(branch.anchorSceneId)) : {};
  const allPositions: Record<string, Pos> = { ...positions, ...altPositions };
  const allNodeIds = [...scenes.map((s) => s.id), ...(branch?.alts ?? []).map((a) => a.id)];
  const allEdges: GraphEdge[] = branch ? [...links, ...whatIfAltEdges(branch)] : links;
  const previewAlt = branch?.alts.find((a) => a.id === previewAltId) ?? null;

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

        {/* WS-B3 M1 — what-if controls. Entry: exactly one scene selected + no branch
            yet → branch from it. Active: add another alternate / discard (zero residue). */}
        {!whatIf.active && selected.length === 1 && (
          <button
            type="button" data-testid="scenegraph-whatif-start"
            className="ml-auto rounded border border-purple-300 px-2 py-0.5 text-purple-700 hover:bg-purple-50 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-950/30"
            onClick={() => { whatIf.start(selected[0]); setSelected([]); }}
          >
            ⑂ {t('whatif.start', { defaultValue: 'What-if from here' })}
          </button>
        )}
        {whatIf.active && (
          <div className="ml-auto flex items-center gap-1" data-testid="scenegraph-whatif-bar">
            <span className="text-purple-700/80 dark:text-purple-300/80">{t('whatif.active', { defaultValue: 'What-if branch (unsaved)' })}</span>
            <select
              data-testid="scenegraph-whatif-model"
              aria-label={t('whatif.model', { defaultValue: 'Take model' })}
              className="rounded border bg-background px-1 py-0.5"
              value={effectiveWhatIfModel}
              onChange={(e) => setWhatIfModelRef(e.target.value)}
            >
              {whatIfModelList.length === 0 && <option value="">{t('whatif.noModel', { defaultValue: 'No model' })}</option>}
              {whatIfModelList.map((mm) => <option key={mm.user_model_id} value={mm.user_model_id}>{mm.alias || mm.provider_model_name}</option>)}
            </select>
            <button
              type="button" data-testid="scenegraph-whatif-add"
              className="rounded border border-purple-300 px-2 py-0.5 text-purple-700 hover:bg-purple-50 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-950/30"
              onClick={whatIf.addAlt}
            >
              + {t('whatif.addAlt', { defaultValue: 'alternate' })}
            </button>
            <button
              type="button" data-testid="scenegraph-whatif-discard"
              className="rounded px-2 py-0.5 text-muted-foreground hover:text-foreground"
              onClick={whatIf.discard}
            >
              {t('whatif.discard', { defaultValue: 'Discard what-if' })}
            </button>
          </div>
        )}
      </div>

      {scenes.length === 0 ? (
        <div data-testid="scenegraph-empty" className="p-3 text-xs text-muted-foreground">
          {t('scenegraph.empty', { defaultValue: 'No scenes yet — plan some scenes in the outline to see the graph.' })}
        </div>
      ) : (
        <GraphCanvas<GraphEdge>
          testid="scenegraph-svg"
          positions={allPositions}
          nodeIds={allNodeIds}
          edges={allEdges}
          edgeEndpoints={(l) => ({ from: l.from_node_id, to: l.to_node_id })}
          edgeKey={(l) => l.id}
          nodeSize={{ w: NODE_W, h: NODE_H }}
          onNodeClick={(id) => { if (!altById.has(id)) toggleSelect(id); }}
          onNodeDrag={(id, pos) => applyLocal({ ...localRef.current, [id]: pos })}
          onNodeDragEnd={() => persist(localRef.current)}
          onBackgroundClick={clearSelection}
          defs={(
            <marker id="scene-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
              <path d="M0,0 L10,5 L0,10 z" fill="#94a3b8" />
            </marker>
          )}
          renderEdge={(l, from, to) =>
            isWhatIfEdge(l) ? (
              // dashed branch edge anchor → alternate (purple, no arrow/selection)
              <line
                key={l.id} data-testid={`whatif-edge-${l.id}`}
                x1={from.x + NODE_W} y1={from.y + NODE_H / 2} x2={to.x} y2={to.y + NODE_H / 2}
                stroke="#a855f7" strokeWidth={1.5} strokeDasharray="4 3"
              />
            ) : (
              <SceneEdge
                link={l} from={from} to={to}
                selected={selectedEdge === l.id}
                onSelect={() => { setSelected([]); setSelectedEdge(l.id); }}
                onDelete={() => deleteEdge(l.id)}
              />
            )
          }
          renderNode={(id, h) => {
            const alt = altById.get(id);
            if (alt) {
              return (
                <WhatIfAltNode
                  alt={alt} pos={allPositions[id]}
                  onRemove={() => { whatIf.removeAlt(id); if (previewAltId === id) setPreviewAltId(null); }}
                  onGenerate={() => generateTake(id)}
                  onView={() => setPreviewAltId(id)}
                />
              );
            }
            const n = byId.get(id)!;
            return (
              <SceneNode
                node={n} pos={allPositions[id]} selected={selected.includes(id)}
                onPointerDown={h.onPointerDown} onSelect={() => toggleSelect(id)} onOpen={() => openScene(n)}
              />
            );
          }}
        />
      )}

      {/* M2 — the take preview strip: the selected alternate's ghost prose + full judge
          dims. Read-only preview (no auto-insert); accept-into-draft / promote is M3. */}
      {previewAlt?.take && (
        <div data-testid="whatif-preview" className="flex max-h-48 shrink-0 flex-col gap-1 border-t border-purple-200 bg-purple-50/40 p-2 text-[11px] dark:border-purple-800 dark:bg-purple-950/30">
          <div className="flex items-center gap-2">
            <span className="font-medium text-purple-800 dark:text-purple-200">⑂ {previewAlt.title}</span>
            {previewAlt.take.judge && (
              <span className="font-mono text-[10px] text-purple-700/80 dark:text-purple-300/80">
                C{previewAlt.take.judge.coherence ?? '–'} · V{previewAlt.take.judge.voice_match ?? '–'} · P{previewAlt.take.judge.pacing ?? '–'} · K{previewAlt.take.judge.canon_consistency ?? '–'}
              </span>
            )}
            <button
              type="button" data-testid="whatif-preview-close"
              className="ml-auto rounded px-1 text-muted-foreground hover:text-foreground"
              onClick={() => setPreviewAltId(null)}
            >
              {t('whatif.closePreview', { defaultValue: 'Close' })}
            </button>
          </div>
          <p className="overflow-y-auto whitespace-pre-wrap text-purple-900/90 dark:text-purple-100/90">{previewAlt.take.ghost}</p>
        </div>
      )}
    </div>
  );
}
