// LOOM Composition (M8) — Power panel container (view).
//
// Resolves/creates the Work for the book, lets the author target a scene + a
// drafter model, then switches between Compose / Grounding / Canon sub-views.
// Render-only: all logic lives in the hooks.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { aiModelsApi } from '../../ai-models/api';
import { useChapterScenes, useCreateScene, useCreateWork, useSetSceneStatus, useWorkResolution } from '../hooks/useWork';
import type { Work } from '../types';
import { ComposeView } from './ComposeView';
import { ChapterAssembleView } from './ChapterAssembleView';
import { PlannerView } from './PlannerView';
import { BeatSheetView } from './BeatSheetView';
import { SceneGraphCanvas } from './SceneGraphCanvas';
import { CastCodexPanel } from './CastCodexPanel';
import { GroundingPanel } from './GroundingPanel';
import { CanonRulesPanel } from './CanonRulesPanel';
import { ThreadsPanel } from './ThreadsPanel';
import { QualityPanel } from './QualityPanel';
import { CompositionSettingsView } from './CompositionSettingsView';

type Props = {
  bookId: string;
  chapterId: string;
  token: string | null;
  onAccept: (text: string) => void; // insert accepted prose into the editor
};

type SubTab = 'compose' | 'assemble' | 'planner' | 'beats' | 'graph' | 'cast' | 'grounding' | 'canon' | 'threads' | 'quality' | 'settings';

export function CompositionPanel({ bookId, chapterId, token, onAccept }: Props) {
  const { t } = useTranslation('composition');
  const resolution = useWorkResolution(bookId, token);
  const createWork = useCreateWork(bookId, token);
  const [tab, setTab] = useState<SubTab>('compose');
  const [sceneId, setSceneId] = useState<string>('');
  const [modelRef, setModelRef] = useState<string>('');

  const res = resolution.data;
  // 'found' → the marked Work; 'candidates' (rare multi-marked) → the first,
  // so the panel doesn't loop on "set up" forever.
  const work: Work | null =
    res?.status === 'found' ? res.work : res?.status === 'candidates' ? (res.candidates[0] ?? null) : null;
  const projectId = work?.project_id;

  const scenes = useChapterScenes(projectId, chapterId, token);
  const createScene = useCreateScene(projectId, token);
  const setSceneStatus = useSetSceneStatus(projectId, token);
  const models = useQuery({
    queryKey: ['composition', 'chat-models'],
    queryFn: () => aiModelsApi.listUserModels(token!, { capability: 'chat' }),
    enabled: !!token,
    select: (d) => d.items.filter((m) => m.is_active),
  });

  if (resolution.isLoading) return <Hint>{t('loading', { defaultValue: 'Loading co-writer…' })}</Hint>;
  if (res?.status === 'unavailable')
    return <Hint>{t('unavailable', { defaultValue: 'Grounding service unavailable.' })}</Hint>;

  // No Work yet → offer to set it up (POST /work).
  if (!work) {
    return (
      <div className="flex flex-col gap-3 p-4">
        <Hint>{t('noWork', { defaultValue: 'No co-writer Work for this book yet.' })}</Hint>
        <button
          data-testid="composition-setup-button"
          className="self-start rounded bg-indigo-600 px-3 py-1.5 text-sm text-white disabled:opacity-50"
          disabled={createWork.isPending}
          onClick={() => createWork.mutate()}
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
  const effectiveModelRef = modelRef || (defaultIsAvailable ? defaultModelRef : '');
  // The selected model's metadata — hints for the server's auto-reasoning
  // strategy (adaptive pass-through vs our rule-based scorer).
  const selectedModel = models.data?.find((m) => m.user_model_id === effectiveModelRef);
  // T0.1 — the plot-thread debt panel is opt-in: only surface its sub-tab when
  // the book has narrative-thread tracking on (same gate as the producer).
  const threadsEnabled = work.settings?.narrative_thread_enabled === true;

  return (
    <div className="flex h-full flex-col">
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
      </div>

      {/* sub-tabs */}
      <div className="flex gap-1 border-b border-neutral-200 px-2 pt-1 text-sm dark:border-neutral-700">
        {(['compose', 'assemble', 'planner', 'beats', 'graph', 'cast', 'grounding', 'canon', ...(threadsEnabled ? ['threads' as const] : []), 'quality', 'settings'] as SubTab[]).map((tb) => (
          <button
            key={tb}
            data-testid={`composition-subtab-${tb}`}
            className={`rounded-t px-2 py-1 ${tab === tb ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500'}`}
            onClick={() => setTab(tb)}
          >
            {t(tb, { defaultValue: tb })}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
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
            onAccept={onAccept}
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
            onAccept={onAccept}
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
          <CastCodexPanel bookId={bookId} chapterId={chapterId} token={token} />
        </div>
        <div className={tab === 'grounding' ? '' : 'hidden'}>
          <GroundingPanel projectId={work.project_id} sceneId={effectiveScene} token={token} />
        </div>
        <div className={tab === 'canon' ? '' : 'hidden'}>
          <CanonRulesPanel projectId={work.project_id} bookId={bookId} token={token} />
        </div>
        {threadsEnabled && (
          <div className={tab === 'threads' ? '' : 'hidden'}>
            <ThreadsPanel projectId={work.project_id} token={token} enabled={threadsEnabled} />
          </div>
        )}
        <div className={tab === 'quality' ? '' : 'hidden'}>
          <QualityPanel projectId={work.project_id} token={token} />
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
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
