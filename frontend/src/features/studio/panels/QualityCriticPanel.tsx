// Studio Quality tab — `quality-critic`: the 4-dim critic (coherence / voice /
// pacing / canon) + per-chapter thread audit. DOCK-2 — thin wrapper over
// QualityReportSection + useWorkResolution, reused AS-IS. Per-chapter and
// on-demand (no book-wide critic aggregation exists yet — see the plan doc's
// reality map), so this adds a chapter picker (booksApi.listChapters, the same
// source the manuscript tree reads) + the shared ModelPicker.
import { useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { ModelPicker } from '@/components/model-picker';
import { Skeleton } from '@/components/shared';
import { booksApi } from '@/features/books/api';
import { QualityReportSection } from '@/features/composition/components/QualityReportSection';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';
import { QualityNoWorkState } from './QualityNoWorkState';

const CHAPTER_PICKER_LIMIT = 500;

export function QualityCriticPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-critic', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();
  const resolution = useWorkResolution(host.bookId, accessToken);
  const [modelRef, setModelRef] = useState('');
  const [chapterId, setChapterId] = useState('');

  const chaptersQ = useQuery({
    queryKey: ['studio', 'quality-critic', 'chapters', host.bookId],
    queryFn: () => booksApi.listChapters(accessToken!, host.bookId, { sort: 'sort_order', limit: CHAPTER_PICKER_LIMIT }),
    enabled: !!accessToken,
  });

  if (resolution.isLoading) {
    return (
      <div data-testid="quality-critic-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const projectId = resolution.data?.status === 'found' ? resolution.data.work?.project_id : null;
  if (!projectId) {
    return <QualityNoWorkState testId="quality-critic-no-work" />;
  }

  const chapters = chaptersQ.data?.items ?? [];

  return (
    <div data-testid="studio-quality-critic-panel" className="flex h-full min-h-0 flex-col gap-2 overflow-auto p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <select
          data-testid="quality-critic-chapter-picker"
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
        {/* /review-impl: no silent cap — a book past CHAPTER_PICKER_LIMIT would otherwise
            hide its later chapters from this picker with zero indication. */}
        {typeof chaptersQ.data?.total === 'number' && chaptersQ.data.total > chapters.length && (
          <span data-testid="quality-critic-chapters-truncated" className="text-[10px] text-neutral-400">
            {t('quality.chaptersTruncated', {
              defaultValue: 'showing first {{shown}} of {{total}} chapters',
              shown: chapters.length,
              total: chaptersQ.data.total,
            })}
          </span>
        )}
        <ModelPicker
          capability="chat"
          value={modelRef || null}
          onChange={(id) => setModelRef(id ?? '')}
          placeholder={t('quality.pickModel', { defaultValue: 'Pick a model to analyze with…' })}
          compact
        />
      </div>
      {chapterId ? (
        <QualityReportSection projectId={projectId} chapterId={chapterId} token={accessToken} modelRef={modelRef} />
      ) : (
        <div data-testid="quality-critic-no-chapter" className="p-4 text-center text-neutral-500">
          {t('quality.pickChapterHint', { defaultValue: 'Pick a chapter above to analyze its quality.' })}
        </div>
      )}
    </div>
  );
}
