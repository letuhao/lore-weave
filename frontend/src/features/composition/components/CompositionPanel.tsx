// LOOM Composition (M8) — Power panel container (view).
//
// Resolves/creates the Work for the book, lets the author target a scene + a
// drafter model, then switches between Compose / Grounding / Canon sub-views.
// Render-only: all logic lives in the hooks.
import { useCallback, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { AddModelCta } from '@/components/shared/AddModelCta';
import { aiModelsApi } from '../../ai-models/api';
import { compositionApi } from '../api';
import { useChapterScenes, useCreateScene, useCreateWork, usePendingWorkResolver, useSetSceneStatus, useWorkResolution } from '../hooks/useWork';
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
import { ReferencesPanel } from './ReferencesPanel';
import { DivergenceWizardButton } from './DivergenceWizardButton';
import { PromoteWhatIfButton } from './PromoteWhatIfButton';
import { DerivativeBanner } from './DerivativeBanner';
import { DerivativeGroundingLayers } from './DerivativeGroundingLayers';
import { useDerivativeContext } from '../hooks/useDerivativeContext';
import { CanonRulesPanel } from './CanonRulesPanel';
import { ThreadsPanel } from './ThreadsPanel';
import { QualityPanel } from './QualityPanel';
import { ProgressPanel } from './ProgressPanel';
import { StyleVoicePanel } from './StyleVoicePanel';
import { CompositionSettingsView } from './CompositionSettingsView';

type Props = {
  bookId: string;
  chapterId: string;
  token: string | null;
  // insert accepted prose into the editor; `meta.model` attributes the AI
  // provenance mark (T5.3) with the model that wrote it.
  onAccept: (text: string, meta?: { model?: string }) => void;
  /** T3.2: the active scene can be lifted to ChapterEditorPage so the editor's
   *  Selection Tools ground on it. Controlled-or-internal — omitted → own state. */
  sceneId?: string;
  onSceneChange?: (id: string) => void;
  /** T5.2: the in-prose mention-heatmap toggle, owned by ChapterEditorPage (it drives
   *  the editor decoration); the GroundingPanel renders the toggle control. */
  heatmapEnabled?: boolean;
  onToggleHeatmap?: () => void;
};

type SubTab = 'compose' | 'cowriter' | 'assemble' | 'planner' | 'beats' | 'graph' | 'cast' | 'relmap' | 'timeline' | 'arc' | 'worldmap' | 'grounding' | 'references' | 'style' | 'canon' | 'threads' | 'progress' | 'quality' | 'flywheel' | 'settings';

export function CompositionPanel({ bookId, chapterId, token, onAccept, sceneId: sceneIdProp, onSceneChange, heatmapEnabled, onToggleHeatmap }: Props) {
  const { t } = useTranslation('composition');
  const qc = useQueryClient();
  const resolution = useWorkResolution(bookId, token);
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
  // 'found' → the marked Work; 'candidates' (rare multi-marked) → the first,
  // so the panel doesn't loop on "set up" forever. A just-spawned dị bản overrides;
  // a `?work=` deep-link selects the named Work next.
  const work: Work | null =
    activeWorkOverride ??
    deepLinkWork ??
    (res?.status === 'found' ? res.work : res?.status === 'candidates' ? (res.candidates[0] ?? null) : null);
  const projectId = work?.project_id;

  // C24 (dị bản M0) — derivative-context controller. Surfaces the dị bản banner +
  // the 2-layer (INHERITED/OVERRIDDEN) grounding badges when the open Work is a
  // derivative (source_work_id set). No-ops for a greenfield Work.
  const derivativeCtx = useDerivativeContext(work);
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
  const models = useQuery({
    queryKey: ['composition', 'chat-models'],
    queryFn: () => aiModelsApi.listUserModels(token!, { capability: 'chat' }),
    enabled: !!token,
    select: (d) => d.items.filter((m) => m.is_active),
  });

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
    models: models.data ?? [],
    modelsLoading: models.isLoading,
    createScene: (payload) => createScene.mutate(payload),
    chapterId,
    newSceneTitle: guidedSceneTitle,
  });

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
  const defaultIsAvailable = !models.data || models.data.some((m) => m.user_model_id === defaultModelRef);
  // Precedence: an explicit session pick > the persisted per-Work default (if still
  // active) > the sole-registered model auto-pick. All DERIVED — no useEffect.
  const effectiveModelRef =
    modelRef || (defaultIsAvailable && defaultModelRef ? defaultModelRef : '') || (guided.soleModelId ?? '');
  // The selected model's metadata — hints for the server's auto-reasoning
  // strategy (adaptive pass-through vs our rule-based scorer).
  const selectedModel = models.data?.find((m) => m.user_model_id === effectiveModelRef);
  // T5.3 — attribute accepted AI prose with the selected model's name so the
  // provenance hover tag can show it. Stable so the no-unmount child views don't
  // churn on every render.
  const acceptProse = useCallback(
    (text: string) => onAccept(text, { model: selectedModel?.provider_model_name }),
    [onAccept, selectedModel?.provider_model_name],
  );
  // T0.1 — the plot-thread debt panel is opt-in: only surface its sub-tab when
  // the book has narrative-thread tracking on (same gate as the producer).
  const threadsEnabled = work.settings?.narrative_thread_enabled === true;

  // C15 (WG-1/WG-2) — writer readiness. A chat model is the writer's ONE true
  // prerequisite; knowledge/grounding is OPTIONAL and degrades gracefully. Derive
  // (no useEffect): once the list resolves empty → offer an in-flow register CTA;
  // once a chat model exists → surface a positive "Ready to draft" cue that frames
  // knowledge as optional, never a precondition wall.
  const hasChatModel = !!models.data?.length;
  const noChatModel = !models.isLoading && !hasChatModel;

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
          <select
            data-testid="composition-model-select"
            className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
            value={effectiveModelRef}
            onChange={(e) => setModelRef(e.target.value)}
            aria-label={t('model', { defaultValue: 'Model' })}
          >
            <option value="">{t('pickModel', { defaultValue: 'Pick a model…' })}</option>
            {(models.data ?? []).map((m) => (
              <option key={m.user_model_id} value={m.user_model_id}>{m.alias || m.provider_model_name}</option>
            ))}
          </select>
        )}
        {/* C24 (dị bản M0) — spawn a what-if derivative branching from this canon.
            The wizard mints a fresh Work + its own knowledge project (delta), persists
            the divergence_spec + entity overrides, then routes the writer into the new
            dị bản studio (re-resolved via the book's work query). */}
        <div className="ml-auto">
          <DivergenceWizardButton sourceWork={work} token={token} onDerived={onDerivedWork} />
        </div>
      </div>

      {/* C27 (dị bản M4) — what-if → derivative PROMOTION. Only on a CANON work
          (promoting always creates a NEW derivative from canon). The writer names an
          ephemeral what-if, then promotes it into a persistent dị bản through the C23
          derive path (fresh project_id + spec + overrides carried over). The full
          spec/overrides authoring is the C24 wizard; this is the explicit
          ephemeral→persistent seam for a quick what-if. */}
      {!derivativeCtx.isDerivative && (
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

      {/* sub-tabs — 16 tabs in a resizable (narrow-able) panel: the strip scrolls
          horizontally rather than overflowing the panel. Tabs don't shrink (labels
          stay readable) and the row never forces the panel wider than its width.
          D-080: TabScrollStrip adds the scroll-aware edge fade affordance. */}
      <TabScrollStrip
        testid="composition-subtabs"
        className="flex gap-1 overflow-x-auto border-b border-neutral-200 px-2 pt-1 text-sm dark:border-neutral-700"
      >
        {(['compose', 'cowriter', 'assemble', 'planner', 'beats', 'graph', 'cast', 'relmap', 'timeline', 'arc', 'worldmap', 'grounding', 'references', 'style', 'canon', ...(threadsEnabled ? ['threads' as const] : []), 'progress', 'quality', 'flywheel', 'settings'] as SubTab[]).map((tb) => (
          <button
            key={tb}
            data-testid={`composition-subtab-${tb}`}
            className={`shrink-0 whitespace-nowrap rounded-t px-2 py-1 ${tab === tb ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500'}`}
            onClick={() => setTab(tb)}
          >
            {t(tb, { defaultValue: tb })}
          </button>
        ))}
        {/* T5.5 — open the story-map views full-screen */}
        <button
          type="button"
          data-testid="composition-power-view-btn"
          className="ml-auto shrink-0 self-center whitespace-nowrap rounded px-2 py-0.5 text-xs text-neutral-500 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
          onClick={() => setPowerViewOpen(true)}
          title={t('view.power_view', { defaultValue: 'Power view' })}
        >
          ⛶ {t('view.power_view', { defaultValue: 'Power view' })}
        </button>
      </TabScrollStrip>

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
        <div className={tab === 'compose' ? '' : 'hidden'}>
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
          />
        </div>
        <div className={tab === 'cowriter' ? '' : 'hidden'}>
          <CoWriterChat
            bookId={bookId}
            onAccept={acceptProse}
            onUseAsGuide={(text) => { setComposeGuide(text); setTab('compose'); }}
          />
        </div>
        <div className={tab === 'assemble' ? '' : 'hidden'}>
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
        </div>
        <div className={tab === 'planner' ? '' : 'hidden'}>
          <PlannerView projectId={work.project_id} bookId={bookId} modelRef={effectiveModelRef} modelSource="user_model" models={models.data ?? []} token={token} />
        </div>
        <div className={tab === 'beats' ? '' : 'hidden'}>
          <BeatSheetView bookId={bookId} projectId={work.project_id} token={token} />
        </div>
        <div className={tab === 'graph' ? '' : 'hidden'}>
          <SceneGraphCanvas work={work} bookId={bookId} token={token} />
        </div>
        <div className={tab === 'cast' ? '' : 'hidden'}>
          <CastCodexPanel
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            onViewArc={(id) => { setArcEntityId(id); setTab('arc'); }}
            search={castSearch}
            onSearchChange={setCastSearch}
          />
        </div>
        <div className={tab === 'relmap' ? '' : 'hidden'}>
          <RelationshipMap bookId={bookId} token={token} />
        </div>
        <div className={tab === 'timeline' ? '' : 'hidden'}>
          <TimelineView bookId={bookId} chapterId={chapterId} token={token} />
        </div>
        <div className={tab === 'arc' ? '' : 'hidden'}>
          <CharacterArcView
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            entityId={arcEntityId}
            onEntityChange={setArcEntityId}
          />
        </div>
        <div className={tab === 'worldmap' ? '' : 'hidden'}>
          <WorldMap
            work={work}
            bookId={bookId}
            chapterId={chapterId}
            token={token}
            onViewCast={(name) => { setCastSearch(name); setTab('cast'); }}
          />
        </div>
        <div className={tab === 'grounding' ? '' : 'hidden'}>
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
            sceneId={effectiveScene}
            token={token}
            heatmapEnabled={heatmapEnabled}
            onToggleHeatmap={onToggleHeatmap}
          />
        </div>
        <div className={tab === 'references' ? '' : 'hidden'}>
          <ReferencesPanel
            projectId={work.project_id}
            sceneId={effectiveScene}
            token={token}
            models={models.data ?? []}
          />
        </div>
        <div className={tab === 'style' ? '' : 'hidden'}>
          <StyleVoicePanel
            projectId={work.project_id}
            chapterId={chapterId}
            sceneId={effectiveScene}
            token={token}
          />
        </div>
        <div className={tab === 'canon' ? '' : 'hidden'}>
          <CanonRulesPanel projectId={work.project_id} bookId={bookId} token={token} />
        </div>
        {threadsEnabled && (
          <div className={tab === 'threads' ? '' : 'hidden'}>
            <ThreadsPanel projectId={work.project_id} token={token} enabled={threadsEnabled} />
          </div>
        )}
        <div className={tab === 'progress' ? '' : 'hidden'}>
          <ProgressPanel projectId={work.project_id} bookId={bookId} settings={work.settings} token={token} />
        </div>
        <div className={tab === 'quality' ? '' : 'hidden'}>
          <QualityPanel projectId={work.project_id} token={token} />
        </div>
        <div className={tab === 'flywheel' ? '' : 'hidden'}>
          <FlywheelPanel
            projectId={work.project_id}
            token={token}
            onOpenCast={(name) => { if (name) setCastSearch(name); setTab('cast'); }}
            onOpenTimeline={() => setTab('timeline')}
            onOpenRelations={() => setTab('relmap')}
          />
        </div>
        <div className={tab === 'settings' ? '' : 'hidden'}>
          <CompositionSettingsView
            projectId={work.project_id}
            bookId={bookId}
            settings={work.settings}
            models={models.data ?? []}
            token={token}
          />
        </div>
      </div>
      {/* T5.5 — Story Map Power-view overlay (mount-on-open, fresh each open) */}
      {powerViewOpen && (
        <PowerViewOverlay
          work={work}
          bookId={bookId}
          chapterId={chapterId}
          token={token}
          onClose={() => setPowerViewOpen(false)}
          onViewCast={(name) => { setCastSearch(name); setTab('cast'); setPowerViewOpen(false); }}
        />
      )}
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
