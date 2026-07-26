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
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useEffectiveModel } from '@/features/chat-ai-settings/context/ChatAiSettingsContext';
import { booksApi } from '../../books/api';
import { useOutline, useOutlineMutations, useSceneLinks } from '../hooks/useOutline';
import { useSetWorkSettings } from '../hooks/useWork';
import { useSceneWhatIf, whatIfAltPositions, whatIfAltEdges, type WhatIfEdge } from '../hooks/useSceneWhatIf';
import { useWhatIfTakes } from '../hooks/useWhatIfTakes';
import { useWhatIfPromotion } from '../hooks/useWhatIfPromotion';
import { useVsCanonDelta } from '../hooks/useVsCanonDelta';
import { compositionApi } from '../api';
import type { OutlineNode, SceneLink, SceneLinkKind, Work } from '../types';
import { SceneNode } from './SceneNode';
import { SceneEdge } from './SceneEdge';
import { WhatIfAltNode } from './WhatIfAltNode';
import { WhatIfJudgeBadge } from './WhatIfJudgeBadge';
import { CanonAtChapterPanel } from './CanonAtChapterPanel';
import { GraphCanvas } from './GraphCanvas';
import { autoLayout, NODE_H, NODE_W, PAD, type Pos } from './sceneGraphLayout';

type GraphEdge = SceneLink | WhatIfEdge;
const isWhatIfEdge = (e: GraphEdge): e is WhatIfEdge => 'wi' in e;

export function SceneGraphCanvas({ work, bookId, token, onPromoted }: {
  work: Work; bookId: string; token: string | null;
  /** WS-B3 M3 — called with the freshly-materialized derivative Work after a what-if
   *  is promoted, so the studio can switch to it. Optional (no-op if not wired). */
  onPromoted?: (derivative: Work) => void;
}) {
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
  // W5: the shared useUserModels fetch (active-only, capability=chat), gated on the
  // what-if branch being open like the old lazy query.
  const [whatIfModelRef, setWhatIfModelRef] = useState('');
  const whatIfModels = useUserModels({ capability: 'chat', enabled: whatIf.active });
  const whatIfModelList = whatIfModels.models ?? [];
  // Inherit the shared cascade model (spec §8) before list[0].
  const inheritedWhatIfModel = useEffectiveModel('chat');
  const effectiveWhatIfModel = whatIfModelRef || inheritedWhatIfModel || whatIfModelList[0]?.user_model_id || '';
  const selectedWhatIfModel = whatIfModelList.find((mm) => mm.user_model_id === effectiveWhatIfModel);
  const takes = useWhatIfTakes({ projectId, token, updateAlt: whatIf.updateAlt });
  const [previewAltId, setPreviewAltId] = useState<string | null>(null);
  // M6 — the canon-at-branch-point inspector (what canon knows right before the
  // divergence). Toggled from the what-if bar; the headline use of CanonAtChapterPanel.
  const [showBranchCanon, setShowBranchCanon] = useState(false);

  // M3 — promote the ephemeral branch into a persistent derivative Work (the SAME
  // path the Divergence Wizard uses), then seed each generated take as a scene node
  // in the derivative (defer persisting take-prose-as-draft, per the M3 contract).
  const wb = whatIf.branch;
  const anchorScene = wb ? scenes.find((s) => s.id === wb.anchorSceneId) : undefined;
  // branch_point is a CHAPTER sort_order (the Divergence Wizard picks a chapter), NOT a
  // scene story_order — so map the anchor scene's chapter → its sort_order. (/review-impl)
  const chaptersQ = useQuery({
    queryKey: ['composition', 'whatif-chapters', bookId],
    queryFn: () => booksApi.listChapters(token!, bookId, { lifecycle_state: 'active', limit: 500, offset: 0 }),
    enabled: !!bookId && !!token && whatIf.active,
    select: (d) => d.items,
  });
  const anchorChapterSort = anchorScene && chaptersQ.data
    ? (chaptersQ.data.find((c) => c.chapter_id === anchorScene.chapter_id)?.sort_order ?? null)
    : null;
  const whatIfDraft = useMemo(() => ({
    branchPoint: anchorChapterSort,
    taxonomy: 'au' as const,
    povAnchor: null,
    canonRules: [] as string[],
    overrides: {} as Record<string, Record<string, unknown>>,
    name: anchorScene ? `What-if from "${anchorScene.title || 'scene'}"` : 'What-if',
  }), [anchorScene, anchorChapterSort]);
  const promotion = useWhatIfPromotion({
    sourceWork: work,
    draft: whatIfDraft,
    token,
    onPromoted: (derivative) => {
      // Seed the READY takes as scene nodes in the derivative project, then persist each
      // take's ghost PROSE into the derivative's scene store (M3), THEN switch the studio
      // — so the derivative's outline already has the seeded scenes + their prose when it
      // mounts (switching first would open an empty outline).
      const ready = whatIf.branch?.alts.filter((a) => a.status === 'ready') ?? [];
      const finish = () => {
        // local cleanup BEFORE the (possibly unmounting) studio switch.
        whatIf.discard();
        setPreviewAltId(null);
        onPromoted?.(derivative);
      };
      if (derivative.project_id && token && ready.length) {
        const proj = derivative.project_id;
        // A scene REQUIRES a chapter (DB CHECK `outline_chapter_required` — caught by a
        // live smoke). The take is an alternate of the anchor scene, so it belongs to the
        // anchor's chapter (a book chapter, shared by the COW derivative).
        const chapterId = anchorScene?.chapter_id ?? null;
        let proseFailed = 0;
        void Promise.allSettled(
          ready.map(async (a, idx) => {
            // story_order is REQUIRED for the prose to be read back: prior_scene_drafts /
            // chapter_scene_drafts / gather_recent's fallback all filter `story_order IS
            // NOT NULL` (/review-impl HIGH — without it the persisted prose is write-only).
            // The derivative outline is created EMPTY (create_derivative copies no nodes),
            // so a dense 0..n-1 index by ready-order is collision-free + reading-ordered.
            const node = await compositionApi.createNode(proj, { kind: 'scene', title: a.title, chapter_id: chapterId, story_order: idx }, token);
            // M3 — best-effort persist the take's ghost prose into the new derivative
            // scene (synthetic-job store; server-side source-clobber guard). A blank
            // ghost is skipped (BE would 422 EMPTY_SCENE_PROSE). A persist failure does
            // NOT fail the scene-add — the scene exists; prose is re-promotable — so we
            // surface a SOFT count rather than rejecting the chain.
            const ghost = a.take?.ghost?.trim();
            if (ghost) {
              try {
                await compositionApi.persistScenePromoteProse(proj, node.id, ghost, token, { anchorNodeId: anchorScene?.id ?? undefined });
              } catch {
                proseFailed += 1;
              }
            }
          }),
        ).then((results) => {
          const failed = results.filter((r) => r.status === 'rejected').length;
          if (failed) toast.error(t('whatif.promotedPartial', { defaultValue: 'Promoted, but {{n}} take(s) couldn’t be added.', n: failed }));
          else if (proseFailed) toast.warning(t('whatif.promotedProsePartial', { defaultValue: 'Promoted, but {{n}} take(s)’ prose couldn’t be saved — re-promote to retry.', n: proseFailed }));
          else toast.success(t('whatif.promoted', { defaultValue: 'Promoted to a what-if derivative.' }));
          finish();
        });
      } else {
        toast.success(t('whatif.promoted', { defaultValue: 'Promoted to a what-if derivative.' }));
        finish();
      }
    },
  });
  // Gate Promote on the chapters query having loaded too, so branch_point (the anchor's
  // CHAPTER sort_order) is resolved — a fast click before it loads would branch at null.
  const canPromote = !!wb && wb.alts.some((a) => a.status === 'ready') && !promotion.isPromoting && !!chaptersQ.data;
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

  // M4 — judge the canon baseline (the anchor scene's chapter draft) so the preview
  // badge can show each dim RELATIVE to canon, not just the take's own score. Only
  // fires while a take with a judge is previewed; memoized by (chapter_id, version).
  const vsCanon = useVsCanonDelta({
    bookId,
    token,
    chapterId: anchorScene?.chapter_id ?? null,
    jobId: previewAlt?.take?.jobId ?? null,
    enabled: !!previewAlt?.take?.judge,
  });

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
            {/* W5 — shared ModelPicker (compact) replaces the bespoke <select>. */}
            <div data-testid="scenegraph-whatif-model" className="w-44">
              <ModelPicker
                capability="chat"
                compact
                value={effectiveWhatIfModel || null}
                onChange={(id) => setWhatIfModelRef(id ?? '')}
                ariaLabel={t('whatif.model', { defaultValue: 'Take model' })}
                placeholder={t('whatif.noModel', { defaultValue: 'No model' })}
              />
            </div>
            <button
              type="button" data-testid="scenegraph-whatif-add"
              className="rounded border border-purple-300 px-2 py-0.5 text-purple-700 hover:bg-purple-50 dark:border-purple-700 dark:text-purple-300 dark:hover:bg-purple-950/30"
              onClick={whatIf.addAlt}
            >
              + {t('whatif.addAlt', { defaultValue: 'alternate' })}
            </button>
            <button
              type="button" data-testid="scenegraph-whatif-promote"
              className="rounded bg-purple-600 px-2 py-0.5 text-white disabled:opacity-50"
              disabled={!canPromote}
              title={canPromote ? undefined : t('whatif.promoteHint', { defaultValue: 'Generate at least one take to promote' })}
              onClick={() => promotion.promote()}
            >
              {promotion.isPromoting ? t('whatif.promoting', { defaultValue: 'Promoting…' }) : t('whatif.promote', { defaultValue: 'Promote' })}
            </button>
            <button
              type="button" data-testid="scenegraph-whatif-canon"
              className={`rounded border px-2 py-0.5 ${showBranchCanon ? 'border-indigo-400 bg-indigo-50 text-indigo-700 dark:border-indigo-600 dark:bg-indigo-950/30 dark:text-indigo-300' : 'border-transparent text-muted-foreground hover:text-foreground'}`}
              title={t('canonview.branchHint', { defaultValue: 'What canon knows right before this branch' })}
              onClick={() => setShowBranchCanon((v) => !v)}
            >
              ⊙ {t('canonview.branchToggle', { defaultValue: 'Canon at branch' })}
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

      {/* M6 — canon-at-branch-point inspector: what canon establishes/knows right
          before the divergence chapter. Windowed to the anchor scene's chapter (with
          its sort_order → established-by-N). Source = the canon project (pre-promote). */}
      {whatIf.active && showBranchCanon && anchorScene?.chapter_id && (
        <div data-testid="scenegraph-branch-canon" className="max-h-64 shrink-0 overflow-y-auto border-b border-indigo-200 bg-indigo-50/30 dark:border-indigo-900 dark:bg-indigo-950/20">
          <CanonAtChapterPanel
            bookId={bookId}
            chapterId={anchorScene.chapter_id}
            chapterIndex={anchorChapterSort}
            chapterLabel={anchorChapterSort != null ? t('canonview.chapterN', { defaultValue: 'chapter {{n}}', n: anchorChapterSort + 1 }) : undefined}
            token={token}
            enabled={showBranchCanon}
          />
        </div>
      )}

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
          // D-S5-SCENEGRAPH-VIRTUALIZE — cull to the viewport at book scale; always keep
          // the selected scenes (link-create), the what-if alt nodes + their anchor (the
          // branch overlay must never be culled).
          virtualize
          alwaysRenderIds={[...selected, ...(branch?.alts ?? []).map((a) => a.id), ...(branch ? [branch.anchorSceneId] : [])]}
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
              <WhatIfJudgeBadge
                judge={previewAlt.take.judge}
                canon={vsCanon.canon}
                baselineAvailable={vsCanon.baselineAvailable}
                judging={vsCanon.judging}
              />
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
