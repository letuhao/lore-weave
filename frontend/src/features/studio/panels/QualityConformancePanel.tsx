// S4 · 3c — `quality-conformance`: the beat-by-beat "did the prose realize the plan?"
// trace (DOCK-8 sibling of quality-critic/coverage/canon). The Studio's answer was only a
// red/green dot (useConformanceStatus rollup); the full per-scene trace was legacy-only.
// Thin wrapper over ConformanceTraceView, mirroring QualityCriticPanel: a chapter picker +
// the shared ModelPicker (the Tier-W re-run is BYOK; regenerate + read need no model).
// This panel answers spec-vs-PROSE; arc_template_drift (spec-vs-template) is Wave 4's.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { ModelPicker } from '@/components/model-picker';
import { booksApi } from '@/features/books/api';
import { ConformanceTraceView } from '@/features/composition/motif/components/ConformanceTraceView';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityWorkGate } from './QualityNoWorkState';
import { useQualityWork } from './useQualityWork';

const CHAPTER_PICKER_LIMIT = 500;

export function QualityConformancePanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-conformance', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const work = useQualityWork(host.bookId, accessToken);
  const [modelRef, setModelRef] = useState('');
  const [chapterId, setChapterId] = useState('');

  const chaptersQ = useQuery({
    queryKey: ['studio', 'quality-conformance', 'chapters', host.bookId],
    queryFn: () => booksApi.listChapters(accessToken!, host.bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT }),
    enabled: !!accessToken,
  });

  if (work.kind !== 'ready') return <QualityWorkGate state={work} testIdPrefix="quality-conformance" bookId={host.bookId} token={accessToken} />;

  const chapters = chaptersQ.data?.items ?? [];

  return (
    <div data-testid="studio-quality-conformance-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <select
          data-testid="quality-conformance-chapter-picker"
          aria-label={t('quality.pickChapter', { defaultValue: 'Pick a chapter' })}
          className="min-w-[10rem] rounded border border-neutral-300 bg-white px-2 py-1 text-xs dark:border-neutral-700 dark:bg-neutral-900"
          value={chapterId}
          onChange={(e) => setChapterId(e.target.value)}
        >
          <option value="">{t('quality.pickChapter', { defaultValue: 'Pick a chapter' })}</option>
          {chapters.map((c) => (
            <option key={c.chapter_id} value={c.chapter_id}>
              {c.title || c.original_filename || `#${c.sort_order}`}
            </option>
          ))}
        </select>
        {/* no silent cap — a book past the picker limit shows the count so later chapters aren't hidden */}
        {typeof chaptersQ.data?.total === 'number' && chaptersQ.data.total > chapters.length && (
          <span data-testid="quality-conformance-chapters-truncated" className="text-[10px] text-neutral-400">
            {t('quality.chaptersTruncated', { defaultValue: 'showing first {{shown}} of {{total}} chapters', shown: chapters.length, total: chaptersQ.data.total })}
          </span>
        )}
        <ModelPicker
          capability="chat"
          value={modelRef || null}
          onChange={(id) => setModelRef(id ?? '')}
          placeholder={t('quality.pickModelRerun', { defaultValue: 'Pick a model to re-run with…' })}
          compact
        />
      </div>
      {chapterId ? (
        <div className="min-h-0 flex-1">
          <ConformanceTraceView
            projectId={work.projectId}
            chapterId={chapterId}
            token={accessToken}
            modelRef={modelRef || null}
            onOpenScene={(sceneId, chId) => {
              // §2#6 loop-connect — publish the selection + open the scene surface (the SceneBrowser pattern).
              if (sceneId) {
                host.publish({ type: 'scene', sceneId, chapterId: chId });
                host.openPanel('scene-inspector', { focus: true });
              } else {
                // empty state: no specific scene yet → land on the scene-browser to pick one to bind.
                host.publish({ type: 'chapter', chapterId: chId, bookId: host.bookId });
                host.openPanel('scene-browser', { focus: true });
              }
            }}
          />
        </div>
      ) : (
        <div data-testid="quality-conformance-no-chapter" className="p-4 text-center text-neutral-500">
          {t('quality.pickChapterConformanceHint', { defaultValue: 'Pick a chapter above to trace how its prose realized the plan.' })}
        </div>
      )}
    </div>
  );
}
