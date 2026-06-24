import { type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Zap } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Pager } from '@/components/pagination/Pager';
import { type ServerPagedList } from '@/components/pagination/useServerPagedList';

export interface EntityBrowserSortOption {
  value: string;
  label: string;
}

interface EntityListBrowserProps {
  // Search
  searchValue: string;
  onSearchChange: (value: string) => void;
  searchMode: 'simple' | 'raw';
  onToggleSearchMode: () => void;
  // Sort (options computed by the caller — e.g. include "relevance" only in raw mode)
  sort: string;
  onSortChange: (sort: string) => void;
  sortOptions: EntityBrowserSortOption[];
  // Filter — the caller owns the button + the expandable panel (glossary-specific)
  filterControl?: ReactNode;
  filterPanel?: ReactNode;
  // Pagination — server-paged state + the total-derived info
  total: number;
  paged: ServerPagedList;
  pageInfo: { pageCount: number; safePage: number; start: number; end: number };
  // The list body (rows + selection bar, or an empty/stale-page state)
  children: ReactNode;
}

/**
 * The reusable shell around a server-paged entity list: a search box (simple/raw
 * toggle) + sort dropdown + a filter slot on top, the caller's list as children,
 * and a "X–Y of N" + page-size + page-through footer at the bottom. The list rows
 * and selection stay with the caller (B1 lesson — extract the genuinely shared
 * shell, keep divergent bits as props/children; the Unknown/AiSuggestions/Merge
 * panels are NOT migrated here — see D-GLOSSARY-BROWSER-PANEL-REUSE).
 */
export function EntityListBrowser({
  searchValue,
  onSearchChange,
  searchMode,
  onToggleSearchMode,
  sort,
  onSortChange,
  sortOptions,
  filterControl,
  filterPanel,
  total,
  paged,
  pageInfo,
  children,
}: EntityListBrowserProps) {
  const { t } = useTranslation('books');
  const { pageCount, safePage, start, end } = pageInfo;

  return (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchValue}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={searchMode === 'raw' ? t('glossary.search_raw_placeholder') : t('glossary.search')}
            data-testid="glossary-search-input"
            className="w-full rounded-md border bg-background pl-9 pr-3 py-1.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
        <button
          onClick={onToggleSearchMode}
          data-testid="glossary-raw-toggle"
          title={t('glossary.search_raw_hint')}
          className={cn(
            'inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium transition-colors',
            searchMode === 'raw'
              ? 'border-amber-400/50 bg-amber-400/10 text-amber-500 hover:bg-amber-400/20'
              : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          <Zap className="h-3.5 w-3.5" />
          {t('glossary.search_raw')}
        </button>
        <select
          value={sort}
          onChange={(e) => onSortChange(e.target.value)}
          data-testid="glossary-sort"
          aria-label={t('glossary.sort_label')}
          className="h-8 rounded-md border bg-background px-2 text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
        >
          {sortOptions.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        {filterControl}
      </div>

      {filterPanel}

      {children}

      {/* Pagination footer */}
      {total > 0 && (
        <div className="flex items-center justify-between gap-2 flex-wrap text-[11px] text-muted-foreground">
          <div className="flex items-center gap-2">
            <span data-testid="glossary-range">{t('glossary.range', { start, end, total })}</span>
            <select
              value={paged.pageSize}
              onChange={(e) => paged.setPageSize(Number(e.target.value))}
              aria-label={t('glossary.page_size_label')}
              className="h-7 rounded-md border bg-background px-1.5 text-[11px] focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
            >
              {[10, 20, 50, 100, 200].map((n) => (
                <option key={n} value={n}>{t('glossary.page_size', { count: n })}</option>
              ))}
            </select>
          </div>
          <Pager
            page={safePage}
            pageCount={pageCount}
            onPageChange={(p) => paged.setPage(Math.min(Math.max(0, p), pageCount - 1))}
            labels={{ page: t('glossary.pager.page'), prev: t('glossary.pager.prev'), next: t('glossary.pager.next') }}
          />
        </div>
      )}
    </div>
  );
}
