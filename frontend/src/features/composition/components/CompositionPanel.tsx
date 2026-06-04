// LOOM Composition (M8) — Power panel container (view).
//
// Resolves/creates the Work for the book, lets the author target a scene + a
// drafter model, then switches between Compose / Grounding / Canon sub-views.
// Render-only: all logic lives in the hooks.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { aiModelsApi } from '../../ai-models/api';
import { useChapterScenes, useCreateScene, useCreateWork, useWorkResolution } from '../hooks/useWork';
import type { Work } from '../types';
import { ComposeView } from './ComposeView';
import { GroundingPanel } from './GroundingPanel';
import { CanonRulesPanel } from './CanonRulesPanel';

type Props = {
  bookId: string;
  chapterId: string;
  token: string | null;
  onAccept: (text: string) => void; // insert accepted prose into the editor
};

type SubTab = 'compose' | 'grounding' | 'canon';

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

  return (
    <div className="flex h-full flex-col">
      {/* scene + model selectors */}
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-200 p-2 text-sm dark:border-neutral-700">
        <select
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={effectiveScene}
          onChange={(e) => setSceneId(e.target.value)}
          aria-label={t('scene', { defaultValue: 'Scene' })}
        >
          {(scenes.data ?? []).map((s) => (
            <option key={s.id} value={s.id}>{s.title || t('untitledScene', { defaultValue: 'Untitled scene' })}</option>
          ))}
          {!scenes.data?.length && <option value="">{t('noScenes', { defaultValue: 'No scenes' })}</option>}
        </select>
        <button
          className="rounded border border-neutral-300 px-2 py-1 text-xs dark:border-neutral-600"
          onClick={() => createScene.mutate({ chapter_id: chapterId, title: t('newScene', { defaultValue: 'New scene' }) })}
        >
          + {t('addScene', { defaultValue: 'Scene' })}
        </button>
        <select
          className="rounded border border-neutral-300 bg-transparent px-2 py-1 dark:border-neutral-600"
          value={modelRef}
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
        {(['compose', 'grounding', 'canon'] as SubTab[]).map((tb) => (
          <button
            key={tb}
            className={`rounded-t px-2 py-1 ${tab === tb ? 'bg-neutral-100 font-medium dark:bg-neutral-800' : 'text-neutral-500'}`}
            onClick={() => setTab(tb)}
          >
            {t(tb, { defaultValue: tb })}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'compose' && (
          <ComposeView
            projectId={work.project_id}
            sceneId={effectiveScene}
            modelRef={modelRef}
            token={token}
            onAccept={onAccept}
          />
        )}
        {tab === 'grounding' && (
          <GroundingPanel projectId={work.project_id} sceneId={effectiveScene} token={token} />
        )}
        {tab === 'canon' && <CanonRulesPanel projectId={work.project_id} token={token} />}
      </div>
    </div>
  );
}

function Hint({ children }: { children: React.ReactNode }) {
  return <div className="p-4 text-sm text-neutral-500">{children}</div>;
}
