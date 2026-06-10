import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { CampaignChapter } from '../types';

const DONE = new Set(['done', 'skipped']);
const MAX_ROWS = 200;

function isFailed(c: CampaignChapter): boolean {
  return [c.knowledge_status, c.translation_status, c.eval_status].includes('failed');
}
function isDone(c: CampaignChapter): boolean {
  return DONE.has(c.knowledge_status) && DONE.has(c.translation_status) && DONE.has(c.eval_status);
}

const STATUS_TONE: Record<string, string> = {
  done: 'text-green-600 dark:text-green-400',
  failed: 'text-destructive',
  dispatched: 'text-blue-600 dark:text-blue-400',
  skipped: 'text-muted-foreground',
  pending: 'text-muted-foreground',
};

/** S6 (view) — per-chapter projection. Defaults to the rows that need attention
 *  (failed + in-progress); a toggle reveals all. Capped at MAX_ROWS (D-S6-CHAPTER-PAGING). */
export function ChapterProjectionTable({ chapters }: { chapters: CampaignChapter[] }) {
  const { t } = useTranslation('campaigns');
  const [showAll, setShowAll] = useState(false);

  const filtered = useMemo(
    () => (showAll ? chapters : chapters.filter((c) => !isDone(c))),
    [chapters, showAll],
  );
  const rows = filtered.slice(0, MAX_ROWS);

  const cell = (s: string) => <span className={STATUS_TONE[s] ?? ''}>{s}</span>;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{t('monitor.chapters', { defaultValue: 'Chapters' })}</span>
        <button type="button" onClick={() => setShowAll((v) => !v)}
          className="text-xs text-primary hover:underline">
          {showAll
            ? t('monitor.showAttention', { defaultValue: 'Show only failed / in-progress' })
            : t('monitor.showAll', { defaultValue: 'Show all' })}
        </button>
      </div>
      {filtered.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          {t('monitor.allDone', { defaultValue: 'All chapters are done.' })}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[12px]">
            <thead className="text-muted-foreground">
              <tr className="border-b text-left">
                <th className="py-1 pr-3">#</th>
                <th className="py-1 pr-3">{t('monitor.stage.knowledge', { defaultValue: 'Knowledge' })}</th>
                <th className="py-1 pr-3">{t('monitor.stage.translation', { defaultValue: 'Translation' })}</th>
                <th className="py-1 pr-3">{t('monitor.stage.eval', { defaultValue: 'Eval' })}</th>
                <th className="py-1 pr-3">{t('monitor.fidelity', { defaultValue: 'Fidelity' })}</th>
                <th className="py-1">{t('monitor.lastError', { defaultValue: 'Last error' })}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <tr key={c.chapter_id} className={`border-b ${isFailed(c) ? 'bg-destructive/5' : ''}`}>
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
          {filtered.length > MAX_ROWS && (
            <p className="pt-1 text-[11px] text-muted-foreground">
              {t('monitor.truncated', {
                defaultValue: 'Showing {{shown}} of {{total}} — refine by completing or cancelling.',
                shown: MAX_ROWS, total: filtered.length,
              })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
