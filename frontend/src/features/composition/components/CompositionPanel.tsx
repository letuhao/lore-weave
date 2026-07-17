// LOOM Composition (M8) — Power panel container (view).
//
// Resolves/creates the Work for the book, lets the author target a scene + a
// drafter model, then switches between Compose / Grounding / Canon sub-views.
// Render-only: all logic lives in the hooks.
import { useCallback, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQueryClient } from '@tanstack/react-query';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { ModelPicker, useUserModels } from '@/components/model-picker';
import { useEffectiveModel } from '@/features/chat-ai-settings/context/ChatAiSettingsContext';
import { compositionApi } from '../api';
import { useChapterScenes, useCreateScene, useCreateWork, usePendingWorkResolver, useSetSceneStatus, useWorkResolution } from '../hooks/useWork';
import { useActiveWorkId } from '../hooks/useActiveWork';
import { resolveActiveWork } from '../workSelect';
import { useGuidedFirstRun } from '../hooks/useGuidedFirstRun';
import type { Work } from '../types';
import { ComposeView } from './ComposeView';
import { TabScrollStrip } from './TabScrollStrip';
import { CoWriterChat } from './CoWriterChat';
import { ChapterAssembleView } from './ChapterAssembleView';
import { PlannerView } from './PlannerView';
import { BeatSheetView } from './BeatSheetView';
import { SceneGraphCanvas } from './SceneGraphCanvas';
import { CastCodexPanel } from './CastCodexPanel';
import { RelationshipMap } from './RelationshipMap';
import { FlywheelPanel } from './FlywheelPanel';
import { PowerViewOverlay } from './PowerViewOverlay';
import { TimelineView } from './TimelineView';
import { CharacterArcView } from './CharacterArcView';
import { WorldMap } from './WorldMap';
import { GroundingPanel } from './GroundingPanel';
import { CanonAtChapterPanel } from './CanonAtChapterPanel';
import { ReferencesPanel } from './ReferencesPanel';
import { DockRail } from './workspace/DockRail';
import { DockSlot } from './workspace/DockSlot';
import { PopoutBridge } from './workspace/PopoutBridge';
import { MobilePanelSwitcher } from './MobilePanelSwitcher';
import { useIsMobile } from '@/hooks/useIsMobile';
import { useWorkspaceLayoutOptional } from '../context/WorkspaceLayoutContext';
import { visibleDockIds, hiddenDockIds, floatingDockIds, popoutDockIds, nextActiveAfterHide, defaultFloatRect } from '../workspace/dock';
import type { Rect, WorkspacePanelId } from '../workspace/types';
import { DivergenceWizardButton } from './DivergenceWizardButton';
import { PromoteWhatIfButton } from './PromoteWhatIfButton';
import { DerivativeBanner } from './DerivativeBanner';
import { DerivativeGroundingLayers } from './DerivativeGroundingLayers';
import { useDerivativeContext } from '../hooks/useDerivativeContext';
import { useAdaptFromSource } from '../hooks/useAdaptFromSource';
import { CanonRulesPanel } from './CanonRulesPanel';
import { CriticPanel } from './CriticPanel';
import { ThreadsPanel } from './ThreadsPanel';
import { QualityPanel } from './QualityPanel';
import { PolishPanel } from './PolishPanel';
import { ProgressPanel } from './ProgressPanel';
import { StyleVoicePanel } from './StyleVoicePanel';
import { CompositionSettingsView } from './CompositionSettingsView';
// W6 (motif library) — additive dock panels. The motif subtree is W6-owned; these
// two registrations are the only studio-shell touches (master §4 W6 / 00-RECONCILE §2).
import { MotifLibraryView } from '../motif/components/MotifLibraryView';
import { ConformanceTraceView } from '../motif/components/ConformanceTraceView';
import { MotifPanelBoundary } from '../motif/components/MotifPanelBoundary';
import { MotifSimpleModeProvider } from '../motif/context/MotifSimpleModeContext';

type Props = {
  bookId: string;
  chapterId: string;
  token: string | null;
  // insert accepted prose into the editor; `meta.model` attributes the AI
  // provenance mark (T5.3) with the model that wrote it. Returns TRUE only when the prose actually
  // landed — the compose/assemble views clear their draft ONLY on true, so a failed insert (e.g. no
  // editor open on this chapter in the studio dock) never loses the draft. Legacy ChapterEditorPage
  // co-mounts the editor and always succeeds synchronously → returns true.
  onAccept: (text: string, meta?: { model?: string }) => boolean;
  /** M6 Polish — replace the chapter doc with the self-heal-accepted text. Owned by
   *  ChapterEditorPage (it holds the Tiptap editor ref). Omitted ⇒ Apply is a no-op. */
  onApplyPolish?: (healedText: string) => void;
  /** T3.2: the active scene can be lifted to ChapterEditorPage so the editor's
   *  Selection Tools ground on it. Controlled-or-internal — omitted → own state. */
  sceneId?: string;
  onSceneChange?: (id: string) => void;
  /** T5.2: the in-prose mention-heatmap toggle, owned by ChapterEditorPage (it drives
   *  the editor decoration); the GroundingPanel renders the toggle control. */
  heatmapEnabled?: boolean;
  onToggleHeatmap?: () => void;
  /** T5.4 M4 — popout/solo mode: when set, render ONLY this panel (no dock rail, no
   *  windowing chrome) — used by the /composition/popout route so a popped-out panel
   *  shows just itself in its own OS window. Omitted ⇒ the full studio (default). */
  soloPanel?: WorkspacePanelId;
};

type SubTab = 'compose' | 'cowriter' | 'assemble' | 'planner' | 'beats' | 'graph' | 'cast' | 'relmap' | 'timeline' | 'arc' | 'worldmap' | 'grounding' | 'canonview' | 'references' | 'style' | 'canon' | 'critic' | 'threads' | 'progress' | 'quality' | 'polish' | 'flywheel' | 'motifs' | 'conformance' | 'settings';

export function CompositionPanel({ bookId, chapterId, token, onAccept, onApplyPolish, sceneId: sceneIdProp, onSceneChange, heatmapEnabled, onToggleHeatmap, soloPanel }: Props) {
  const solo = soloPanel != null;
  const { t } = useTranslation('composition');
  const qc = useQueryClient();
  const resolution = useWorkResolution(bookId, token);
  const { data: activeWorkId } = useActiveWorkId(bookId, token);
  const createWork = useCreateWork(bookId, token);
  // D-C16: a Work created during a knowledge-service outage comes back pending
  // (null project_id) and is invisible to the resolution query; this resolver
  // polls resolve-project on its surrogate id until it's backfilled.
  const pendingResolver = usePendingWorkResolver(bookId, token);
  const [tab, setTab] = useState<SubTab>('compose');
  const [localSceneId, setLocalSceneId] = useState<string>('');
  const sceneId = sceneIdProp ?? localSceneId;
  const setSceneId = onSceneChange ?? setLocalSceneId;
  const [modelRef, setModelRef] = useState<string>('');
  // C27 (dị bản M4) — ephemeral what-if draft. A lightweight in-memory exploration
  // (just a name here; the full spec/overrides come from the C24 wizard) the writer
  // can PROMOTE to a persistent derivative via the C23 derive path. Held transient
  // (no localStorage) until promoted, then the derive response is the persisted truth.
  const [whatIfName, setWhatIfName] = useState<string>('');
  // T2.4: the character whose arc is shown — lifted here so the Cast codex (T2.1)
  // can launch the arc tab with a character preselected; the arc's own picker also
  // writes back through setArcEntityId.
  const [arcEntityId, setArcEntityId] = useState<string | null>(null);
  // T2.5: the Cast search is lifted here so the World Map can "open a place in the
  // codex" by prefilling its name + switching to the cast tab.
  const [castSearch, setCastSearch] = useState('');
  // T5.5 — the Story Map Power-view overlay (mount-on-open, fresh each time).
  const [powerViewOpen, setPowerViewOpen] = useState(false);
  // T3.1: the compose guide is lifted here so the co-writer chat's "Use as guide"
  // can pre-fill it (then switch to the compose tab).
  const [composeGuide, setComposeGuide] = useState('');
  // T5.4 M3 — floating-window z-order (focus stack, most-recent last). Ephemeral
  // per-device-session UI state (NOT persisted — z-order across reload is immaterial);
  // a window click moves it to the top. The placement + geometry ARE persisted (layout).
  const [floatFocus, setFloatFocus] = useState<WorkspacePanelId[]>([]);

  // C24 (dị bản M0) — when the wizard spawns a derivative, the studio switches to
  // edit THAT Work so the writer lands in the dị bản (banner + 2-layer badges). The
  // derivative is a fresh candidate on the same book; rather than guess which
  // candidate it is from the resolution, we hold the just-spawned Work explicitly.
  // NOTE: this override is intentionally NOT reset on chapter change — it's safe
  // because the panel is mounted with `key={bookId}` (ChapterEditorPage), so it
  // remounts (clearing this state) whenever the book changes; a derivative is
  // per-book so it must persist across chapter navigation within the same book.
  const [activeWorkOverride, setActiveWorkOverride] = useState<Work | null>(null);
  const res = resolution.data;
  // C28 (dị bản M6) — the living-world tree deep-links into a SPECIFIC Work via
  // `?work=<surrogate id>` (a canon + its dị bản share one book_id under COW, so
  // the param disambiguates which one to open). DERIVED inline from the
  // resolution (no useEffect-for-events): match the param against the resolved
  // work/candidates by surrogate id. The wizard's just-spawned override still
  // wins; an absent/stale param falls back to the default selection.
  const [searchParams] = useSearchParams();
  const deepLinkWorkId = searchParams.get('work');
  const allResolved: Work[] = res
    ? [...(res.work ? [res.work] : []), ...(res.candidates ?? [])]
    : [];
  const deepLinkWork = deepLinkWorkId
    ? allResolved.find((w) => (w.id ?? w.project_id) === deepLinkWorkId) ?? null
    : null;
  // 'found' → the marked Work; 'candidates' → the ACTIVE Work (EC-3d: the per-book
  // pref, else canonical) so the panel follows a "Switch to". A just-spawned dị bản
  // overrides; a `?work=` deep-link selects the named Work next.
  const work: Work | null =
    activeWorkOverride ??
    deepLinkWork ??
    resolveActiveWork(res, activeWorkId);
  const projectId = work?.project_id;

  // C24 (dị bản M0) — derivative-context controller. Surfaces the dị bản banner +
  // the 2-layer (INHERITED/OVERRIDDEN) grounding badges when the open Work is a
  // derivative (source_work_id set). No-ops for a greenfield Work.
  const derivativeCtx = useDerivativeContext(work, token);
  // M1 (D-DERIVATIVE-ADAPT-FROM-SOURCE) — whether the active chapter's scenes can be
  // adapted from inherited source prose (derivative + at/after branch + source has
  // prose). No-ops (no fetch) on a greenfield Work. Drives ComposeView's adapt action.
  const adaptability = useAdaptFromSource(bookId, chapterId, derivativeCtx, token);
  // EXPLICIT handler from the wizard's onDerived (NOT a useEffect-for-events): switch
  // the studio to the new derivative + refresh the resolution cache so a later
  // re-resolve also sees it.
  const onDerivedWork = (derivative: Work) => {
    setActiveWorkOverride(derivative);
    qc.invalidateQueries({ queryKey: ['composition', 'work', bookId] });
  };

  const scenes = useChapterScenes(projectId, chapterId, token);
  const createScene = useCreateScene(projectId, token);
  const setSceneStatus = useSetSceneStatus(projectId, token);
  // W5 — THE shared user-models fetch (active-only, capability=chat, server-side
  // filter + 15s dedupe cache shared with the ModelPicker below and sibling panels).
  const modelsQ = useUserModels({ capability: 'chat' });
  const modelList = modelsQ.models;
  // Chat & AI settings — the inherited Account-tier chat model (spec §8). Called
  // before the early returns (rules-of-hooks); null outside the studio provider.
  const inheritedChatModel = useEffectiveModel('chat');

  const guidedSceneTitle = t('firstSceneTitle', { defaultValue: 'Opening scene' });
  // C17 (WG-4) — guided first-run controller. Called BEFORE the early returns
  // (rules-of-hooks); it no-ops until the Work resolves (workReady=!!work). Auto-pick
  // the chat model ONLY when EXACTLY ONE is registered (hook returns undefined for
  // 0/≥2 — never guess), derive whether a first scene is needed, and expose an
  // explicit runGuided() that creates that one scene (no useEffect-for-events).
  const guided = useGuidedFirstRun({
    workReady: !!work,
    scenes: scenes.data ?? [],
    scenesLoading: scenes.isLoading,
    models: modelList ?? [],
    modelsLoading: modelsQ.loading,
    createScene: (payload) => createScene.mutate(payload),
    chapterId,
    newSceneTitle: guidedSceneTitle,
  });

  // T5.3 — attribute accepted AI prose with the selected model's name (for the
  // provenance hover tag). HOISTED above the early returns (rules-of-hooks): a hook
  // below the `if (resolution.isLoading) return` was masked in the opener (its query
  // cache is pre-warmed by ChapterEditorPage) but CRASHED the pop-out, whose separate
  // React root has a COLD query cache → first render early-returns with fewer hooks,
  // then the resolved render runs this one → "rendered more hooks". The model name is
  // read via a ref (assigned below, after the Work resolves) so the deps stay stable.
  const modelNameRef = useRef<string | undefined>(undefined);
  const acceptProse = useCallback(
    (text: string): boolean => onAccept(text, { model: modelNameRef.current }),
    [onAccept],
  );
  // T5.4 — the windowing layout/flag (null without a provider, e.g. unit tests / the
  // flag-OFF path). HOISTED above the early returns for the same rules-of-hooks reason
  // as acceptProse: a cold-cache first render (the pop-out's separate root) early-returns
  // before this line, then the resolved render reaches it → "rendered more hooks".
  const ws = useWorkspaceLayoutOptional();
  // M5a — mobile studio: one panel at a time via the MobilePanelSwitcher; the dock
  // rail / float / popout / picker are never rendered (≤767px). Unconditional hook
  // (above the early returns) like `ws`.
  const isMobile = useIsMobile();

  if (resolution.isLoading) return <Hint>{t('loading', { defaultValue: 'Loading co-writer…' })}</Hint>;
  if (res?.status === 'unavailable')
    return <Hint>{t('unavailable', { defaultValue: 'Grounding service unavailable.' })}</Hint>;

  // No Work yet → offer to set it up (POST /work). C17 (WG-4) guided first-run:
  // the SAME click chains the first scene so a fresh book reaches a primed Generate
  // in ≤2 clicks (setup → Generate). The chain is a DIRECT side-effect of the
  // explicit click via the mutation's onSuccess (the action origin) — NOT a
  // useEffect reacting to the Work appearing. project_id can be null when the
  // knowledge-service is down (C16 resilience, D-C16-NULL-WORK-ROUTE) — guard it:
  // the writer still gets a Work, just not the auto-scene until backfill.
  if (!work) {
    // D-C16: a pending null-project Work is backfilling — surface a transient
    // "finishing setup" state (and a retry if knowledge stays down) instead of
    // looping back to the setup button (the resolution query can't see it yet).
    if (pendingResolver.state === 'resolving') {
      return (
        <div className="flex flex-col gap-3 p-4">
          <Hint>{t('resolvingWork', { defaultValue: 'Finishing setup… the knowledge service was briefly unavailable.' })}</Hint>
        </div>
      );
    }
    if (pendingResolver.state === 'failed') {
      return (
        <div className="flex flex-col gap-3 p-4">
          <Hint>{t('resolveWorkFailed', { defaultValue: 'Knowledge service unavailable — couldn’t finish setting up grounding.' })}</Hint>
          <button
            data-testid="composition-resolve-retry"
            className="self-start rounded bg-indigo-600 px-3 py-1.5 text-sm text-white"
            onClick={() => pendingResolver.retry()}
          >
            {t('retry', { defaultValue: 'Retry' })}
          </button>
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-3 p-4">
        <Hint>{t('noWork', { defaultValue: 'No co-writer Work for this book yet.' })}</Hint>
        <button
          data-testid="composition-setup-button"
          className="self-start rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={createWork.isPending}
          onClick={() =>
            createWork.mutate(undefined, {
              onSuccess: (created) => {
                if (!created) return;
                // C16: knowledge was down → a pending null-project Work. Hand its
                // surrogate id to the resolver to poll for backfill (the resolution
                // query excludes pending works, so we can't rely on a refetch).
                if (!created.project_id) {
                  if (created.id) pendingResolver.start(created.id);
                  return;
                }
                if (!token) return;
                // Claim the guided one-shot guard BEFORE the async scene create so
                // the cue's "Start writing" button (briefly live until the outline
                // refetch lands) can't create a SECOND scene — single first-scene
                // per chapter across both origins (adversary C17 MAJOR fix).
                guided.markFired();
                void compositionApi
                  .createNode(created.project_id, { kind: 'scene', chapter_id: chapterId, title: guidedSceneTitle }, token)
                  .then(() => qc.invalidateQueries({ queryKey: ['composition', 'outline', created.project_id] }))
                  .catch(() => { /* scene auto-create is best-effort; the writer can +Scene */ });
              },
            })
          }
        >
          {t('setup', { defaultValue: 'Set up co-writer' })}
        </button>
      </div>
    );
  }

  const effectiveScene = sceneId || scenes.data?.[0]?.id || '';
  const selectedScene = scenes.data?.find((s) => s.id === effectiveScene);
  const sceneDone = selectedScene?.status === 'done';
  // Stitch (B3) is the publishable artifact → gated on every scene being done.
  const scenesAllDone = !!scenes.data?.length && scenes.data.every((s) => s.status === 'done');
  // Session model pick OVERRIDES the persisted per-Work default (Settings tab);
  // derive (like effectiveScene) so the default applies without a useEffect. Guard
  // a STALE default that points at a now-deactivated model (initialValues-respect-
  // dynamic-gates): only honor it while models are still loading or it's in the
  // active list — else fall back to '' so the selector doesn't show a phantom value
  // and no hidden stale model_ref reaches generation.
  const defaultModelRef = typeof work.settings?.default_model_ref === 'string' ? work.settings.default_model_ref : '';
  const defaultIsAvailable = !modelList || modelList.some((m) => m.user_model_id === defaultModelRef);
  // Precedence (the settings cascade, spec §3): an explicit session pick > the
  // persisted per-Work default (Book tier, if still active) > the inherited
  // Account-tier chat model > the sole-registered model auto-pick. All DERIVED —
  // no useEffect. Every studio tool inherits through this hub.
  const effectiveModelRef =
    modelRef
    || (defaultIsAvailable && defaultModelRef ? defaultModelRef : '')
    || (inheritedChatModel ?? '')
    || (guided.soleModelId ?? '');
  // The selected model's metadata — hints for the server's auto-reasoning
  // strategy (adaptive pass-through vs our rule-based scorer).
  const selectedModel = modelList?.find((m) => m.user_model_id === effectiveModelRef);
  // Feed the hoisted acceptProse the current model name via its ref (plain assignment,
  // not a hook — safe after the early returns).
  modelNameRef.current = selectedModel?.provider_model_name;
  // T0.1 — the plot-thread debt panel is opt-in: only surface its sub-tab when
  // the book has narrative-thread tracking on (same gate as the producer).
  const threadsEnabled = work.settings?.narrative_thread_enabled === true;

  // C15 (WG-1/WG-2) — writer readiness. A chat model is the writer's ONE true
  // prerequisite; knowledge/grounding is OPTIONAL and degrades gracefully. Derive
  // (no useEffect): once the list resolves empty → offer an in-flow register CTA;
  // once a chat model exists → surface a positive "Ready to draft" cue that frames
  // knowledge as optional, never a precondition wall.
  const hasChatModel = !!modelList?.length;
  const noChatModel = !modelsQ.loading && !hasChatModel;

  // T5.4 M2 — dock windowing. When the WorkspaceShell flag is ON, the fixed strip is
  // replaced by a reorderable DockRail and the active panel is driven by the (per-
  // device) layout; OFF (or no provider — unit tests) keeps the local `tab` state +
  // fixed strip UNCHANGED. The 19 content divs stay MOUNTED either way (no remount).
  // `ws` is the hoisted hook value (read above the early returns); the derivations below
  // use it only after the Work resolves.
  const dockOn = !!ws?.enabled;
  const dockVisible = dockOn ? visibleDockIds(ws!.layout, threadsEnabled) : [];
  // CLAMP the active panel to a VISIBLE one (/review-impl MED): a persisted active
  // that is now hidden or gated-out (e.g. 'threads' saved while enabled, now disabled)
  // would otherwise blank the content pane — no matching div renders + no rail tab.
  const activeTab: SubTab = dockOn
    ? ((dockVisible as string[]).includes(ws!.layout.active)
        ? (ws!.layout.active as SubTab)
        : ((dockVisible[0] as SubTab) ?? 'compose'))
    : tab;
  const selectTab = (id: SubTab) => {
    if (dockOn && ws) {
      // a deep-link to a hidden panel un-hides it so it shows in the rail (not just
      // active-but-tabless). /review-impl LOW.
      if (ws.layout.panels[id as WorkspacePanelId]?.hidden) {
        ws.dispatch({ type: 'toggle-hidden', id: id as WorkspacePanelId });
      }
      ws.dispatch({ type: 'set-active', id: id as WorkspacePanelId });
    } else setTab(id);
  };
  const hideDockPanel = (id: WorkspacePanelId) => {
    if (!ws) return;
    if (activeTab === id) {
      const next = nextActiveAfterHide(dockVisible, id);
      if (next) ws.dispatch({ type: 'set-active', id: next });
    }
    ws.dispatch({ type: 'toggle-hidden', id });
  };
  // T5.4 M3 — in-app floating windows. A floated panel leaves the rail (placement
  // filters exclude it) and renders as a FloatingWindow via DockSlot; its content is
  // the SAME element (re-parented, not duplicated) so the M1-hoisted co-writer stream
  // survives the move. dock↔float reuses the persisted rect so a window reopens where
  // it last sat.
  const dockFloating = dockOn ? floatingDockIds(ws!.layout, threadsEnabled) : [];
  const focusFloat = (id: WorkspacePanelId) =>
    setFloatFocus((prev) => [...prev.filter((x) => x !== id), id]);
  // zIndex stays below the Power-view overlay (z-50): base 40 + focus position, capped.
  const floatZ = (id: WorkspacePanelId) => 40 + Math.min(Math.max(floatFocus.indexOf(id), 0), 9);
  const floatPanel = (id: WorkspacePanelId) => {
    if (!ws) return;
    const rect = ws.layout.panels[id]?.rect ?? defaultFloatRect(dockFloating.length);
    ws.dispatch({ type: 'set-placement', id, placement: 'float', rect });
    focusFloat(id);
    // if the panel being floated was the active dock tab, advance focus so the dock
    // content pane doesn't go blank (the rail no longer lists it).
    if (activeTab === id) {
      const next = nextActiveAfterHide(dockVisible, id);
      if (next) ws.dispatch({ type: 'set-active', id: next });
    }
  };
  const dockPanel = (id: WorkspacePanelId) => {
    if (!ws) return;
    ws.dispatch({ type: 'set-placement', id, placement: 'dock' }); // rect preserved for re-float
    setFloatFocus((prev) => prev.filter((x) => x !== id));
  };
  // T5.4 M4 — OS pop-out. A popped panel leaves the rail AND the opener content area
  // (it runs in its OWN window via PopoutBridge → the /composition/popout route); only
  // its bridge stays mounted here, owning that window's lifecycle. Closing the window
  // (or its Dock button) re-docks it (dockPanel, via the bridge's close-poll).
  const dockPopped = dockOn ? popoutDockIds(ws!.layout, threadsEnabled) : [];
  const popoutPanel = (id: WorkspacePanelId) => {
    if (!ws) return;
    ws.dispatch({ type: 'set-placement', id, placement: 'popout' });
    if (activeTab === id) {
      const next = nextActiveAfterHide(dockVisible, id);
      if (next) ws.dispatch({ type: 'set-active', id: next });
    }
  };
  // Per-panel placement-aware host props (shared by every DockSlot). When the flag is
  // OFF / there's no provider, `floated` is always false ⇒ DockSlot renders the M2
  // visible/hidden div, byte-identical to before. In SOLO mode (the popout shell) only
  // `soloPanel` is mounted, forced visible, never floated/popped (it IS the window).
  const slot = (id: WorkspacePanelId) => ({
    id,
    active: solo ? id === soloPanel : activeTab === id,
    // M5a — mobile forces every panel DOCKED + MOUNTED (placement ignored): no
    // FloatingWindow, no popout, just the active panel's CSS-visible DockSlot.
    floated: !solo && !isMobile && dockOn && ws?.layout.panels[id]?.placement === 'float',
    // Not mounted here when: a non-solo panel in the popout shell, OR (in the opener)
    // a panel that's popped out to its own window. On mobile everything is mounted+docked.
    mounted: solo ? id === soloPanel : isMobile ? true : ws?.layout.panels[id]?.placement !== 'popout',
    rect: ws?.layout.panels[id]?.rect ?? defaultFloatRect(0),
    title: t(id, { defaultValue: id }),
    zIndex: floatZ(id),
    onMove: (rect: Rect) => ws?.dispatch({ type: 'set-rect', id, rect }),
    onResize: (rect: Rect) => ws?.dispatch({ type: 'set-rect', id, rect }),
    onDock: () => dockPanel(id),
    onFocus: () => focusFloat(id),
  });
  // T5.5 — open the story-map views full-screen. Shared by both the dock rail and the
  // fixed strip (the DockRail rightSlot), so the affordance survives flag ON.
  const powerViewBtn = (
    <button
      type="button"
      data-testid="composition-power-view-btn"
      className="ml-auto shrink-0 self-center whitespace-nowrap rounded px-2 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
      onClick={() => setPowerViewOpen(true)}
      title={t('view.power_view', { defaultValue: 'Power view' })}
    >
      ⛶ {t('view.power_view', { defaultValue: 'Power view' })}
    </button>
  );

  // The fixed sub-tab order (the `threads` gate applied) — shared by the flag-OFF
  // TabScrollStrip and the mobile switcher's flag-OFF list.
  const stripIds: SubTab[] = ['compose', 'cowriter', 'assemble', 'planner', 'beats', 'graph', 'cast', 'relmap', 'timeline', 'arc', 'worldmap', 'grounding', 'canonview', 'references', 'style', 'canon', 'critic', ...(threadsEnabled ? ['threads' as const] : []), 'progress', 'quality', 'polish', 'flywheel', 'motifs', 'conformance', 'settings'];
  // M5a — the mobile switcher's panel list: the dock's visible ids when the windowing
  // flag is ON (respects hide + reorder + the threads gate), else the fixed strip order.
  const mobileIds: SubTab[] = dockOn ? (dockVisible as SubTab[]) : stripIds;

  return (
    <div className="flex h-full min-w-0 flex-col overflow-hidden">
      {/* C24 (dị bản M0) — persistent derivative-context banner (no-ops unless this
          Work is a derivative). Tells the writer they're adapting from read-only canon. */}
      <DerivativeBanner ctx={derivativeCtx} />
      {/* scene + model selectors */}
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-200 p-2 text-sm dark:border-neutral-700">
        <select
          data-testid="composition-scene-select"
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={effectiveScene}
          onChange={(e) => setSceneId(e.target.value)}
          aria-label={t('scene', { defaultValue: 'Scene' })}
        >
          {(scenes.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>
              {s.status === 'done' ? '✓ ' : ''}{s.title || t('untitledScene', { defaultValue: 'Untitled scene' })}
            </option>
          ))}
          {!scenes.data?.length && <option value="">{t('noScenes', { defaultValue: 'No scenes' })}</option>}
        </select>
        <button
          data-testid="composition-add-scene"
          className="rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600"
          onClick={() => createScene.mutate({ chapter_id: chapterId, title: t('newScene', { defaultValue: 'New scene' }) })}
        >
          + {t('addScene', { defaultValue: 'Scene' })}
        </button>
        {/* M9: commit/reopen the selected scene — marking 'done' satisfies the
            chapter-gate (and emits scene_committed). Without this the gate could
            never be satisfied from the UI. */}
        {selectedScene && (
          <button
            data-testid="composition-mark-done"
            className={
              'rounded px-2 py-1 text-xs disabled:opacity-50 ' +
              (sceneDone
                ? 'border border-emerald-300 text-emerald-700 dark:border-emerald-700 dark:text-emerald-400'
                : 'bg-emerald-600 text-white')
            }
            disabled={setSceneStatus.isPending}
            title={sceneDone
              ? t('reopenSceneHint', { defaultValue: 'Reopen this scene (back to drafting)' })
              : t('markDoneHint', { defaultValue: 'Mark this scene done — required before the chapter can be published' })}
            onClick={() =>
              setSceneStatus.mutate({ nodeId: effectiveScene, status: sceneDone ? 'drafting' : 'done' })
            }
          >
            {sceneDone
              ? t('reopenScene', { defaultValue: '✓ Done — Reopen' })
              : t('markDone', { defaultValue: 'Mark done' })}
          </button>
        )}
        {/* C15 (WG-1) — when there's no active chat model, the picker is a dead end
            (empty select + disabled Generate). Replace it with an in-flow register
            CTA that deep-links to model registration AND returns here. The chat model
            is the writer's ONE hard need; this is the only setup the writer must do. */}
        {noChatModel ? (
          <span data-testid="composition-add-chat-model" className="self-center">
            <AddModelCta
              capability="chat"
              label={t('addChatModel', { defaultValue: 'Add a model to start writing' })}
              variant="link"
            />
          </span>
        ) : (
          // W5 — the shared ModelPicker replaces the bespoke <select>. Choosing the
          // "Pick a model…" (none) row emits null → modelRef '' → the effective ref
          // falls back to the persisted default / sole-model auto-pick, exactly like
          // the old empty <option>.
          <div data-testid="composition-model-select" className="min-w-44">
            <ModelPicker
              capability="chat"
              compact
              value={effectiveModelRef || null}
              onChange={(id) => setModelRef(id ?? '')}
              allowNone
              noneLabel={t('pickModel', { defaultValue: 'Pick a model…' })}
              ariaLabel={t('model', { defaultValue: 'Model' })}
            />
          </div>
        )}
        {/* C24 (dị bản M0) — spawn a what-if derivative branching from this canon.
            The wizard mints a fresh Work + its own knowledge project (delta), persists
            the divergence_spec + entity overrides, then routes the writer into the new
            dị bản studio (re-resolved via the book's work query).
            D-S1-COMPOSE-ASSEMBLE-VISUAL-SAMENESS: the chapter-assemble solo panel stitches DONE
            scenes into a chapter — what-if exploration is a scene-drafting concern, not an assembly
            one — so its what-if chrome (this Spawn button + the promote row below) is hidden there,
            which also gives assemble a distinct identity from scene-compose. */}
        {soloPanel !== 'assemble' && (
          <div className="ml-auto">
            <DivergenceWizardButton sourceWork={work} token={token} onDerived={onDerivedWork} />
          </div>
        )}
      </div>

      {/* C27 (dị bản M4) — what-if → derivative PROMOTION. Only on a CANON work
          (promoting always creates a NEW derivative from canon). The writer names an
          ephemeral what-if, then promotes it into a persistent dị bản through the C23
          derive path (fresh project_id + spec + overrides carried over). The full
          spec/overrides authoring is the C24 wizard; this is the explicit
          ephemeral→persistent seam for a quick what-if. */}
      {!derivativeCtx.isDerivative && soloPanel !== 'assemble' && (
        <div
          data-testid="composition-whatif-promote"
          className="flex flex-wrap items-center gap-2 border-b border-neutral-200 px-2 py-1.5 dark:border-neutral-700"
        >
          <input
            data-testid="composition-whatif-name"
            className="rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
            placeholder={t('promote.namePlaceholder', { defaultValue: 'Name a what-if…' })}
            value={whatIfName}
            onChange={(e) => setWhatIfName(e.target.value)}
            aria-label={t('promote.nameLabel', { defaultValue: 'What-if name' })}
          />
          <PromoteWhatIfButton
            sourceWork={work}
            token={token}
            draft={{
              branchPoint: null,
              taxonomy: 'au',
              povAnchor: null,
              canonRules: [],
              overrides: {},
              name: whatIfName,
            }}
            onPromoted={(d) => {
              setWhatIfName('');
              onDerivedWork(d);
            }}
          />
        </div>
      )}

      {/* C15 (WG-2) — positive readiness cue. Nothing in the writer flow told the
          author that writing is READY once a chat model exists; they wrongly believed
          they had to build a knowledge graph first. Surface it here, framing knowledge
          as OPTIONAL enrichment — never present embedding/extraction as a writing gate. */}
      {hasChatModel && (
        <div
          data-testid="composition-ready-to-draft"
          className="flex items-center gap-1.5 border-b border-neutral-200 bg-emerald-50/60 px-2 py-1 text-xs text-emerald-800 dark:border-neutral-700 dark:bg-emerald-950/30 dark:text-emerald-300"
        >
          <span className="inline-block h-2 w-2 rounded-full bg-emerald-500" />
          <span className="font-medium">{t('readyToDraft', { defaultValue: 'Ready to draft' })}</span>
          <span className="text-emerald-700/80 dark:text-emerald-400/80">
            {t('readyToDraftHint', {
              defaultValue: 'Grounding gets richer after you build a knowledge graph, but it is optional — you can write now.',
            })}
          </span>
        </div>
      )}

      {/* C17 (WG-4) — guided first-run cue. Once primed (a chat model is resolvable
          and a scene exists or can be created) tell the writer exactly what to do
          next, turning empty dropdowns into a primed Generate. When the Work has no
          scene yet, the cue carries a prominent EXPLICIT "Start writing" action that
          creates the first scene (direct handler → runGuided, no useEffect-for-events). */}
      {guided.guidedCue && (
        <div
          data-testid="composition-guided-cue"
          className="flex flex-wrap items-center gap-2 border-b border-neutral-200 px-2 py-1.5 text-xs text-neutral-600 dark:border-neutral-700 dark:text-neutral-300"
        >
          <span>
            {guided.needsFirstScene
              ? t('guidedCueStart', { defaultValue: 'Create your first scene, then write your opening and Generate — or Continue from your cursor in the editor.' })
              : t('guidedCueReady', { defaultValue: 'Write your opening, then Generate — or Continue from your cursor in the editor.' })}
          </span>
          {guided.needsFirstScene && !guided.sceneFired && (
            <button
              data-testid="composition-guided-start"
              className="rounded bg-indigo-600 px-2 py-1 text-xs text-white disabled:opacity-50"
              disabled={createScene.isPending}
              onClick={guided.runGuided}
            >
              {t('guidedStart', { defaultValue: 'Start writing' })}
            </button>
          )}
        </div>
      )}

      {/* T5.4 M4 — opener-side OS pop-out bridges (render nothing; own each popped
          panel's window). Never in SOLO mode (the popout shell IS a window) nor on
          mobile (M5a — no popout; a popped panel is shown docked instead). */}
      {!solo && !isMobile && dockPopped.map((id) => (
        <PopoutBridge
          key={id}
          id={id}
          bookId={bookId}
          chapterId={chapterId}
          sceneId={effectiveScene}
          onClosed={() => dockPanel(id)}
        />
      ))}

      {/* sub-tabs strip — DockRail (reorderable) when the windowing flag is ON, else
          the fixed TabScrollStrip. Both keep the Power-view trigger (shared rightSlot)
          and the 19 content divs below stay MOUNTED either way (no remount). SOLO mode
          (the popout shell) shows no strip — the window IS the single panel. */}
      {solo ? null : isMobile ? (
        // M5a — mobile: replace the rail/strip with a single Studio panel picker (Sheet).
        <MobilePanelSwitcher
          ids={mobileIds}
          active={activeTab}
          onSelect={(id) => selectTab(id as SubTab)}
          label={(id) => t(id, { defaultValue: id })}
        />
      ) : dockOn && ws ? (
        <DockRail
          visibleIds={dockVisible}
          hiddenIds={hiddenDockIds(ws.layout, threadsEnabled)}
          active={activeTab as WorkspacePanelId}
          onSelect={(id) => selectTab(id as SubTab)}
          onReorder={(ids) => ws.dispatch({ type: 'reorder', ids })}
          onHide={hideDockPanel}
          onShow={(id) => ws.dispatch({ type: 'toggle-hidden', id })}
          onFloat={floatPanel}
          onPopout={popoutPanel}
          rightSlot={powerViewBtn}
        />
      ) : (
        <TabScrollStrip
          testid="composition-subtabs"
          className="flex gap-1 overflow-x-auto border-b border-neutral-200 px-2 pt-1 text-sm dark:border-neutral-700"
        >
          {stripIds.map((tb) => (
            <button
              key={tb}
              data-testid={`composition-subtab-${tb}`}
              className={`shrink-0 whitespace-nowrap rounded-t px-2 py-1 ${tab === tb ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500'}`}
              onClick={() => setTab(tb)}
            >
              {t(tb, { defaultValue: tb })}
            </button>
          ))}
          {powerViewBtn}
        </TabScrollStrip>
      )}

      <div data-testid="composition-content" className="min-h-0 min-w-0 flex-1 overflow-auto [overflow-wrap:anywhere]">
        {/* All sub-panels stay MOUNTED, toggled with CSS `hidden`, so in-progress
            generation/edit state (a co-write draft, a chapter/stitch preview)
            survives a tab switch — CLAUDE.md "never conditionally unmount stateful
            components". A ternary here would destroy ComposeView/ChapterAssembleView
            hook state on every tab change.
            Trade-off (PO: holistic): the read-only panels now fetch eagerly even if
            never opened — QualityPanel (correction-stats) + CanonRulesPanel (list).
            Both are bounded + react-query-cached; GroundingPanel self-guards on an
            empty sceneId (no eager query). Accepted for uniform state-preservation. */}
        <DockSlot {...slot('compose')}>
          <ComposeView
            projectId={work.project_id}
            sceneId={effectiveScene}
            modelRef={effectiveModelRef}
            modelKind={selectedModel?.provider_kind}
            modelName={selectedModel?.provider_model_name}
            token={token}
            onAccept={acceptProse}
            guide={composeGuide}
            onGuideChange={setComposeGuide}
            canAdapt={adaptability.canAdapt}
            adaptSourceEmpty={adaptability.sourceEmpty}
          />
        </DockSlot>
        <DockSlot {...slot('cowriter')}>
          <CoWriterChat
            bookId={bookId}
            onAccept={acceptProse}
            onUseAsGuide={(text) => { setComposeGuide(text); selectTab('compose'); }}
            // M2 (D-T5.4-CHAT-HOIST): engage the chat SharedWorker when the panel can
            // float/pop-out — opener (dock on) or the solo pop-out window — so an
            // in-flight chat turn survives the panel re-parenting / opener close.
            windowingEnabled={dockOn}
            forceShared={solo}
          />
        </DockSlot>
        <DockSlot {...slot('assemble')}>
          <ChapterAssembleView
            projectId={work.project_id}
            bookId={bookId}
            chapterId={chapterId}
            modelRef={effectiveModelRef}
            modelKind={selectedModel?.provider_kind}
            modelName={selectedModel?.provider_model_name}
            settings={work.settings}
            scenesAllDone={scenesAllDone}
            token={token}
            onAccept={acceptProse}
          />
        </DockSlot>
        <DockSlot {...slot('planner')}>
          <PlannerView projectId={work.project_id} bookId={bookId} modelRef={effectiveModelRef} modelSource="user_model" token={token} />
        </DockSlot>
        <DockSlot {...slot('beats')}>
          <BeatSheetView bookId={bookId} projectId={work.project_id} token={token} />
        </DockSlot>
        <DockSlot {...slot('graph')}>
          <SceneGraphCanvas work={work} bookId={bookId} token={token} onPromoted={onDerivedWork} />
        </DockSlot>
        <DockSlot {...slot('cast')}>
          <CastCodexPanel
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            onViewArc={(id) => { setArcEntityId(id); selectTab('arc'); }}
            search={castSearch}
            onSearchChange={setCastSearch}
          />
        </DockSlot>
        <DockSlot {...slot('relmap')}>
          <RelationshipMap bookId={bookId} token={token} />
        </DockSlot>
        <DockSlot {...slot('timeline')}>
          <TimelineView bookId={bookId} chapterId={chapterId} token={token} />
        </DockSlot>
        <DockSlot {...slot('arc')}>
          <CharacterArcView
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            entityId={arcEntityId}
            onEntityChange={setArcEntityId}
          />
        </DockSlot>
        <DockSlot {...slot('worldmap')}>
          <WorldMap
            work={work}
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            onViewCast={(name) => { setCastSearch(name); selectTab('cast'); }}
          />
        </DockSlot>
        <DockSlot {...slot('grounding')}>
          {/* C24 (dị bản M0) — on a derivative Work, decorate the grounding tab with
              the 2-layer (INHERITED/OVERRIDDEN) canon view + read-only reference
              spine. No-ops on a greenfield Work. */}
          {derivativeCtx.isDerivative && derivativeCtx.sourceProjectId && (
            <DerivativeGroundingLayers
              ctx={derivativeCtx}
              sourceProjectId={derivativeCtx.sourceProjectId}
              bookId={bookId}
              token={token}
            />
          )}
          <GroundingPanel
            projectId={work.project_id}
            bookId={bookId}
            chapterId={selectedScene?.chapter_id ?? chapterId}
            sceneId={effectiveScene}
            token={token}
            heatmapEnabled={heatmapEnabled}
            onToggleHeatmap={onToggleHeatmap}
          />
        </DockSlot>
        <DockSlot {...slot('canonview')}>
          {/* M6 — "Canon as of chapter N" for the active scene's chapter. On a
              derivative, window against the SOURCE project (the derivative's own is
              empty pre-promote). Fetches only when this tab is active (4 windowed
              cross-service reads). */}
          {/* Knowledge project is resolved by book_id inside the hook (distinct from
              work.project_id); a derivative shares book_id → source canon's graph. */}
          <CanonAtChapterPanel
            bookId={bookId}
            chapterId={selectedScene?.chapter_id ?? chapterId}
            token={token}
            enabled={activeTab === 'canonview'}
          />
        </DockSlot>
        <DockSlot {...slot('references')}>
          <ReferencesPanel
            projectId={work.project_id}
            sceneId={effectiveScene}
            token={token}
            models={modelList ?? []}
          />
        </DockSlot>
        <DockSlot {...slot('style')}>
          <StyleVoicePanel
            projectId={work.project_id}
            chapterId={chapterId}
            sceneId={effectiveScene}
            token={token}
          />
        </DockSlot>
        <DockSlot {...slot('canon')}>
          <CanonRulesPanel projectId={work.project_id} bookId={bookId} token={token} />
        </DockSlot>
        <DockSlot {...slot('critic')}>
          <CriticPanel token={token} />
        </DockSlot>
        {threadsEnabled && (
          <DockSlot {...slot('threads')}>
            <ThreadsPanel projectId={work.project_id} token={token} enabled={threadsEnabled} />
          </DockSlot>
        )}
        <DockSlot {...slot('progress')}>
          <ProgressPanel projectId={work.project_id} bookId={bookId} token={token} />
        </DockSlot>
        <DockSlot {...slot('quality')}>
          <QualityPanel projectId={work.project_id} token={token} modelRef={effectiveModelRef} />
        </DockSlot>
        <DockSlot {...slot('polish')}>
          {/* keyed by chapterId so proposals (offsets into THIS chapter's text) reset on a
              chapter switch — else stale Ch-A edits would Apply onto Ch-B (corruption). */}
          <PolishPanel
            key={chapterId}
            projectId={work.project_id}
            chapterId={chapterId}
            token={token}
            modelRef={effectiveModelRef}
            onApply={onApplyPolish ?? (() => {})}
          />
        </DockSlot>
        <DockSlot {...slot('flywheel')}>
          <FlywheelPanel
            projectId={work.project_id}
            token={token}
            onOpenCast={(name) => { if (name) setCastSearch(name); selectTab('cast'); }}
            onOpenTimeline={() => selectTab('timeline')}
            onOpenRelations={() => selectTab('relmap')}
          />
        </DockSlot>
        {/* W6 — motif library + conformance dock panels. The MotifSimpleModeProvider
            wraps BOTH so the simple/expert toggle is shared across them (one stable
            per-device preference). */}
        <DockSlot {...slot('motifs')}>
          <MotifPanelBoundary label="motifs">
            <MotifSimpleModeProvider token={token}>
              <MotifLibraryView token={token} projectId={work.project_id} />
            </MotifSimpleModeProvider>
          </MotifPanelBoundary>
        </DockSlot>
        <DockSlot {...slot('conformance')}>
          <MotifPanelBoundary label="conformance">
            <MotifSimpleModeProvider token={token}>
              <ConformanceTraceView projectId={work.project_id} chapterId={chapterId} token={token} />
            </MotifSimpleModeProvider>
          </MotifPanelBoundary>
        </DockSlot>
        <DockSlot {...slot('settings')}>
          <CompositionSettingsView
            projectId={work.project_id}
            bookId={bookId}
            settings={work.settings}
            models={modelList ?? []}
            token={token}
          />
        </DockSlot>
      </div>
      {/* T5.5 — Story Map Power-view overlay (mount-on-open, fresh each open) */}
      {powerViewOpen && (
        <PowerViewOverlay
          work={work}
          bookId={bookId}
          chapterId={chapterId}
          token={token}
          onClose={() => setPowerViewOpen(false)}
          onViewCast={(name) => { setCastSearch(name); selectTab('cast'); setPowerViewOpen(false); }}
          onPromoted={(d) => { onDerivedWork(d); setPowerViewOpen(false); }}
        />
      )}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
