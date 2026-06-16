import { useTranslation } from 'react-i18next';

const PAGE_SIZES = [25, 50, 100];

/** History pager — page-size selector + "X–Y of N" + prev/next, matching the
 *  glossary/chapter list pattern. `page` is 0-based. Disables prev/next at the
 *  ends; renders nothing when there's nothing to page. */
export function HistoryPager({
  page,
  pageSize,
  total,
  shown,
  onPage,
  onPageSize,
}: {
  page: number;
  pageSize: number;
  total: number;
  /** Rows on the current page (for an accurate "X–Y" when the last page is short). */
  shown: number;
  onPage: (next: number) => void;
  onPageSize: (next: number) => void;
}) {
  const { t } = useTranslation('jobs');
  if (total <= 0) return null;
  const from = page * pageSize + 1;
  const to = page * pageSize + shown;
  const hasPrev = page > 0;
  const hasNext = to < total;

  const pg = 'inline-flex h-7 min-w-[28px] items-center justify-center rounded-md border px-2 text-xs disabled:opacity-40';

  return (
    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
      <div className="flex items-center gap-3">
        <span className="tabular-nums">
          {t('pager.range', { defaultValue: '{{from}}–{{to}} of {{total}}', from, to, total })}
        </span>
        <select
          className="rounded-md border bg-input px-2 py-1 text-xs outline-none focus:border-ring"
          value={pageSize}
          onChange={(e) => onPageSize(Number(e.target.value))}
          aria-label={t('pager.pageSize', { defaultValue: 'Page size' })}
        >
          {PAGE_SIZES.map((s) => (
            <option key={s} value={s}>
              {t('pager.perPage', { defaultValue: '{{n}} / page', n: s })}
            </option>
          ))}
        </select>
      </div>
      <div className="flex items-center gap-1">
        <button
          type="button"
          className={pg}
          onClick={() => onPage(page - 1)}
          disabled={!hasPrev}
          aria-label={t('pager.prev', { defaultValue: 'Previous page' })}
        >
          ‹
        </button>
        <span className="px-1 tabular-nums">{t('pager.page', { defaultValue: 'Page {{n}}', n: page + 1 })}</span>
        <button
          type="button"
          className={pg}
          onClick={() => onPage(page + 1)}
          disabled={!hasNext}
          aria-label={t('pager.next', { defaultValue: 'Next page' })}
        >
          ›
        </button>
      </div>
    </div>
  );
}
