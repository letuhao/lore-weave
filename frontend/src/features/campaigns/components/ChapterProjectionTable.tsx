import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useCampaignChapters } from '../hooks/useCampaignQueries';
import { useRerunFailed } from '../hooks/useCampaignMutations';
import type { CampaignChapter } from '../types';

const PAGE = 200;

function isFailed(c: CampaignChapter): boolean {
  return [c.knowledge_status, c.translation_status, c.eval_status].includes('failed');
}

const STATUS_TONE: Record<string, string> = {
  done: 'text-green-600 dark:text-green-400',
  failed: 'text-destructive',
  dispatched: 'text-blue-600 dark:text-blue-400',
  skipped: 'text-muted-foreground',
  pending: 'text-muted-foreground',
};

/** S6 (view) — per-chapter projection, SERVER-PAGINATED (D-S6-CHAPTER-PAGING). Defaults
 *  to the rows needing attention (failed + in-progress); a toggle shows all. Re-run
 *  controls (G2) appear when the campaign has failures (`hasFailures`, from the
 *  monitor's progress) — selection persists across pages. */
export function ChapterProjectionTable(
  { campaignId, active, hasFailures }: { campaignId: string; active: boolean; hasFailures: boolean },
) {
  const { t } = useTranslation('campaigns');
  const [showAll, setShowAll] = useState(false);
  const [offset, setOffset] = useState(0);
  const [sel, setSel] = useState<Set<string>>(new Set());

  const status = showAll ? 'all' : 'attention';
  const q = useCampaignChapters(campaignId, { status, limit: PAGE, offset, active });
  const items = q.data?.items ?? [];
  const total = q.data?.total ?? 0;

  const rerun = useRerunFailed({
    onSuccess: () => { setSel(new Set()); toast.success(t('monitor.rerunQueued', { defaultValue: 'Re-run queued.' })); },
    onError: (e) => toast.error(t('monitor.rerunFailed', { defaultValue: 'Re-run failed: {{error}}', error: e.message })),
  });

  const cell = (s: string) => <span className={STATUS_TONE[s] ?? ''}>{s}</span>;
  const toggle = (id: string) =>
    setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const setFilter = (all: boolean) => { setShowAll(all); setOffset(0); };

  const pageEnd = Math.min(offset + items.length, total);
  const lastPage = offset + PAGE >= total;
  const showRerun = hasFailures || sel.size > 0;
  const showSelect = useMemo(() => items.some(isFailed) || sel.size > 0, [items, sel]);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t('monitor.chapters', { defaultValue: 'Chapters' })}</span>
        <button type="button" onClick={() => setFilter(!showAll)}
          className="text-xs text-primary hover:underline">
          {showAll
            ? t('monitor.showAttention', { defaultValue: 'Show only failed / in-progress' })
            : t('monitor.showAll', { defaultValue: 'Show all' })}
        </button>
      </div>

      {showRerun && (
        <div className="flex items-center gap-3">
          <button type="button" disabled={rerun.isPending || !hasFailures}
            onClick={() => rerun.mutate({ campaignId, chapterIds: null })}
            className="rounded-md border border-primary/40 bg-primary/5 px-3 py-1 text-xs font-medium text-primary hover:bg-primary/10 disabled:opacity-40">
            {t('monitor.rerunAll', { defaultValue: 'Re-run all failed' })}
          </button>
          <button type="button" disabled={rerun.isPending || sel.size === 0}
            onClick={() => rerun.mutate({ campaignId, chapterIds: [...sel] })}
            className="rounded-md border px-3 py-1 text-xs hover:bg-accent disabled:opacity-40">
            {t('monitor.rerunSelected', { defaultValue: 'Re-run selected ({{n}})', n: sel.size })}
          </button>
        </div>
      )}

      {q.isLoading && !q.data ? (
        <p className="text-sm text-muted-foreground">{t('monitor.loading', { defaultValue: 'Loading…' })}</p>
      ) : total === 0 ? (
        <p className="text-sm text-muted-foreground">
          {showAll
            ? t('monitor.noChapters', { defaultValue: 'No chapters.' })
            : t('monitor.allDone', { defaultValue: 'All chapters are done.' })}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="text-muted-foreground">
              <tr className="border-b text-left">
                {showSelect && <th className="py-1 pr-2" />}
                <th className="py-1 pr-3">#</th>
                <th className="py-1 pr-3">{t('monitor.stage.knowledge', { defaultValue: 'Knowledge' })}</th>
                <th className="py-1 pr-3">{t('monitor.stage.translation', { defaultValue: 'Translation' })}</th>
                <th className="py-1 pr-3">{t('monitor.stage.eval', { defaultValue: 'Eval' })}</th>
                <th className="py-1 pr-3">{t('monitor.fidelity', { defaultValue: 'Fidelity' })}</th>
                <th className="py-1">{t('monitor.lastError', { defaultValue: 'Last error' })}</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr key={c.chapter_id} className={`border-b ${isFailed(c) ? 'bg-destructive/5' : ''}`}>
                  {showSelect && (
                    <td className="py-1 pr-2">
                      {isFailed(c) && (
                        <input type="checkbox" aria-label={`select chapter ${c.chapter_sort}`}
                          checked={sel.has(c.chapter_id)} onChange={() => toggle(c.chapter_id)} />
                      )}
                    </td>
                  )}
                  <td className="py-1 pr-3">{c.chapter_sort}</td>
                  <td className="py-1 pr-3">{cell(c.knowledge_status)}</td>
                  <td className="py-1 pr-3">{cell(c.translation_status)}</td>
                  <td className="py-1 pr-3">{cell(c.eval_status)}</td>
                  <td className="py-1 pr-3">{c.eval_fidelity_score ? Number(c.eval_fidelity_score).toFixed(2) : '—'}</td>
                  <td className="py-1 max-w-[20rem] truncate text-destructive" title={c.last_error ?? ''}>{c.last_error ?? ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="flex items-center justify-between pt-2 text-[11px] text-muted-foreground">
            <span>{t('monitor.pageRange', {
              defaultValue: '{{from}}–{{to}} of {{total}}', from: total === 0 ? 0 : offset + 1, to: pageEnd, total,
            })}</span>
            <span className="flex gap-2">
              <button type="button" disabled={offset === 0}
                onClick={() => setOffset((o) => Math.max(0, o - PAGE))}
                className="rounded border px-2 py-0.5 hover:bg-accent disabled:opacity-40">
                {t('monitor.prev', { defaultValue: 'Prev' })}
              </button>
              <button type="button" disabled={lastPage}
                onClick={() => setOffset((o) => o + PAGE)}
                className="rounded border px-2 py-0.5 hover:bg-accent disabled:opacity-40">
                {t('monitor.next', { defaultValue: 'Next' })}
              </button>
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
