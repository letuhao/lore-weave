// Studio Quality tab — `quality-canon`: book-wide itemized canon issues. NEW
// component (no old-workspace precedent) merging TWO backend sources that were
// each real but never itemized/book-wide before this feature (see the plan
// doc's reality map):
//   - composition-service: confirmed contradictions from a scene's latest
//     auto-generation (`GET /works/{id}/canon-issues`).
//   - knowledge-service: confirmed contradictions flagged during KG extraction
//     (`GET /extraction/projects/{id}/canon-flags`) — closes D-KG-CANON-FLAG-
//     REVIEW-UI (previously only visible interleaved in raw job logs).
// Clicking a row that resolves to a chapter jumps there via the existing
// `focusManuscriptUnit` host action (no new bus event needed).
import type { IDockviewPanelProps } from 'dockview-react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { Skeleton } from '@/components/shared';
import { compositionApi } from '@/features/composition/api';
import { useWorkResolution } from '@/features/composition/hooks/useWork';
import type { CanonIssue } from '@/features/composition/types';
import { knowledgeApi, type CanonFlag } from '@/features/knowledge/api';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';
import { useStudioHost } from '../host/StudioHostProvider';
import { useStudioPanel } from './useStudioPanel';

export function QualityCanonPanel(props: IDockviewPanelProps) {
  useStudioPanel('quality-canon', props.api);
  const { t } = useTranslation('studio');
  const host = useStudioHost();
  const { accessToken } = useAuth();

  const work = useWorkResolution(host.bookId, accessToken);
  const compositionProjectId = work.data?.status === 'found' ? work.data.work?.project_id ?? null : null;
  const compositionIssuesQ = useQuery({
    queryKey: ['studio', 'quality-canon', 'composition', compositionProjectId],
    queryFn: () => compositionApi.getCanonIssues(compositionProjectId!, accessToken!),
    enabled: !!compositionProjectId && !!accessToken,
  });

  const { projectId: knowledgeProjectId, isLoading: knowledgeProjectLoading } = useBookKnowledgeProject(host.bookId);
  const canonFlagsQ = useQuery({
    queryKey: ['studio', 'quality-canon', 'knowledge', knowledgeProjectId],
    queryFn: () => knowledgeApi.listCanonFlags(knowledgeProjectId!, accessToken!),
    enabled: !!knowledgeProjectId && !!accessToken,
  });

  const loading = work.isLoading || knowledgeProjectLoading
    || (!!compositionProjectId && compositionIssuesQ.isLoading)
    || (!!knowledgeProjectId && canonFlagsQ.isLoading);

  if (loading) {
    return (
      <div data-testid="quality-canon-loading" className="space-y-3 p-4">
        <Skeleton className="h-6 w-48" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  const compositionIssues = compositionIssuesQ.data?.items ?? [];
  const canonFlags = canonFlagsQ.data?.flags ?? [];
  // /review-impl: a fetch error must never render as "no issues" — that's a false-negative
  // (the checker didn't run, it isn't clean) — so `empty` is gated on neither source having
  // errored, and each error gets its own visible banner instead of silently vanishing.
  const hasError = compositionIssuesQ.isError || canonFlagsQ.isError;
  const empty = !hasError && compositionIssues.length === 0 && canonFlags.length === 0;

  const jumpToChapter = (chapterId: string | null | undefined) => {
    if (chapterId) host.focusManuscriptUnit(chapterId);
  };

  return (
    <div data-testid="studio-quality-canon-panel" className="flex h-full min-h-0 flex-col gap-3 overflow-auto p-3 text-sm">
      <p className="text-[11px] text-neutral-400">
        {t('quality.canonIntro', {
          defaultValue: 'Advisory — confirmed contradictions with content marked gone/changed earlier in the book. Nothing here is applied automatically.',
        })}
      </p>

      {compositionIssuesQ.isError && (
        <div data-testid="quality-canon-composition-error" className="rounded bg-amber-50 p-2 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300">
          {t('quality.canonCompositionError', { defaultValue: 'Could not load canon issues from generation — try again.' })}
        </div>
      )}
      {canonFlagsQ.isError && (
        <div data-testid="quality-canon-extraction-error" className="rounded bg-amber-50 p-2 text-[11px] text-amber-700 dark:bg-amber-950 dark:text-amber-300">
          {t('quality.canonExtractionError', { defaultValue: 'Could not load canon flags from knowledge extraction — try again.' })}
        </div>
      )}

      {empty && (
        <div data-testid="quality-canon-empty" className="p-4 text-center text-neutral-500">
          {t('quality.canonEmpty', { defaultValue: 'No canon issues found.' })}
        </div>
      )}

      {compositionIssues.length > 0 && (
        <section data-testid="quality-canon-composition-section" className="flex flex-col gap-1">
          <h3 className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
            {t('quality.canonFromGeneration', { defaultValue: 'From generation ({{n}})', n: compositionIssues.length })}
          </h3>
          <ul className="flex flex-col gap-1">
            {compositionIssues.map((issue: CanonIssue) => (
              <li
                key={issue.scene_id}
                data-testid="quality-canon-composition-item"
                className="flex items-start justify-between gap-2 rounded border border-rose-200 bg-rose-50 p-2 text-[11px] dark:border-rose-900 dark:bg-rose-950/40"
              >
                <div className="flex flex-col gap-0.5">
                  <span className="font-medium text-rose-700 dark:text-rose-300">{issue.scene_title || t('quality.untitledScene', { defaultValue: 'Untitled scene' })}</span>
                  {issue.violations.map((v, i) => (
                    <span key={i} className="text-rose-600 dark:text-rose-400">⚠ {v.why || v.name}</span>
                  ))}
                </div>
                {issue.chapter_id && (
                  <button
                    type="button"
                    data-testid="quality-canon-jump"
                    className="shrink-0 rounded bg-rose-600 px-2 py-0.5 text-white"
                    onClick={() => jumpToChapter(issue.chapter_id)}
                  >
                    {t('quality.jumpToChapter', { defaultValue: 'Open chapter' })}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      {canonFlags.length > 0 && (
        <section data-testid="quality-canon-extraction-section" className="flex flex-col gap-1">
          <h3 className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
            {t('quality.canonFromExtraction', { defaultValue: 'From knowledge extraction ({{n}})', n: canonFlags.length })}
          </h3>
          <ul className="flex flex-col gap-1">
            {canonFlags.map((flag: CanonFlag) => {
              const chapterId = flag.context.source_type === 'chapter' ? String(flag.context.source_id ?? '') : null;
              return (
                <li
                  key={flag.log_id}
                  data-testid="quality-canon-extraction-item"
                  className="flex items-start justify-between gap-2 rounded border border-amber-200 bg-amber-50 p-2 text-[11px] dark:border-amber-900 dark:bg-amber-950/40"
                >
                  <span className="text-amber-700 dark:text-amber-300">⚠ {flag.message}</span>
                  {chapterId && (
                    <button
                      type="button"
                      data-testid="quality-canon-jump"
                      className="shrink-0 rounded bg-amber-600 px-2 py-0.5 text-white"
                      onClick={() => jumpToChapter(chapterId)}
                    >
                      {t('quality.jumpToChapter', { defaultValue: 'Open chapter' })}
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
