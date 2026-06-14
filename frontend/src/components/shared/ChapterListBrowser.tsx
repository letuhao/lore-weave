import { type ReactNode, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Search } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { useServerPagedList } from '@/components/pagination/useServerPagedList';
import { Pager } from '@/components/pagination/Pager';
import { useDebouncedValue } from '@/features/raw-search/hooks/useDebouncedValue';
import { cn } from '@/lib/utils';

export type ChapterSelectionMode = 'none' | 'single' | 'multi';

interface ChapterListBrowserProps {
  bookId: string;
  /** none = read-only/navigation, single = click-to-pick, multi = checkboxes. */
  selectionMode?: ChapterSelectionMode;
  /** Controlled selection (multi). Persists across pages — a Set of chapter_id. */
  selectedIds?: Set<string>;
  onSelectionChange?: (ids: Set<string>) => void;
  /** Row click (single-pick / navigation). */
  onRowClick?: (chapter: Chapter) => void;
  /** Highlight the current chapter (editor / reader). */
  activeChapterId?: string;
  /** Server filters. */
  lifecycle?: 'active' | 'trashed';
  editorialStatus?: 'draft' | 'published';
  /** UI toggles. */
  enableSearch?: boolean;
  enableSelectAll?: boolean; // multi: "select all N matching" loop-fetch
  pageSize?: number;
  selectAllCap?: number;
  /** Per-row slots. */
  rowMeta?: (c: Chapter) => ReactNode;
  rowActions?: (c: Chapter) => ReactNode;
  className?: string;
}

const SELECT_ALL_CAP = 5000;

/**
 * The single server-paged chapter browser that replaces the per-screen ad-hoc
 * lists (each previously full-loaded, capped at 20/100 by the limit bug). Owns
 * its query + pagination (useServerPagedList) + debounced search + selection
 * (Set persists across pages, with a Gmail-style "select all N matching"
 * loop-fetch). Selection/filters are props so each call site picks the mode it
 * needs (reader TOC = none, editor nav = single, extraction/translation/campaign
 * = multi). See docs/specs/2026-06-14-shared-chapter-list-browser-epic.md.
 */
export function ChapterListBrowser({
  bookId,
  selectionMode = 'none',
  selectedIds,
  onSelectionChange,
  onRowClick,
  activeChapterId,
  lifecycle = 'active',
  editorialStatus,
  enableSearch = true,
  enableSelectAll = true,
  pageSize = 50,
  selectAllCap = SELECT_ALL_CAP,
  rowMeta,
  rowActions,
  className,
}: ChapterListBrowserProps) {
  const { t } = useTranslation('books');
  const { accessToken } = useAuth();
  const paged = useServerPagedList(pageSize);
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput, 300);

  const listParams = {
    lifecycle_state: lifecycle,
    editorial_status: editorialStatus,
    q: debouncedSearch || undefined,
    limit: paged.limit,
    offset: paged.offset,
  };

  const { data, isLoading } = useQuery({
    queryKey: ['chapter-browser', bookId, lifecycle, editorialStatus, debouncedSearch, paged.offset, paged.limit],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, listParams),
    enabled: !!accessToken && !!bookId,
    placeholderData: (prev) => prev,
  });

  const chapters = data?.items ?? [];
  const total = data?.total ?? 0;
  const { pageCount, safePage, start, end } = paged.pageInfo(total);
  const sel = selectedIds ?? EMPTY_SET;

  const setSearch = (v: string) => { setSearchInput(v); paged.reset(); };

  const toggle = (id: string) => {
    if (!onSelectionChange) return;
    const next = new Set(sel);
    if (selectionMode === 'single') {
      next.clear();
      if (!sel.has(id)) next.add(id);
    } else {
      if (next.has(id)) next.delete(id); else next.add(id);
    }
    onSelectionChange(next);
  };

  const pageAllSelected = chapters.length > 0 && chapters.every((c) => sel.has(c.chapter_id));
  const togglePageAll = () => {
    if (!onSelectionChange) return;
    const next = new Set(sel);
    if (pageAllSelected) chapters.forEach((c) => next.delete(c.chapter_id));
    else chapters.forEach((c) => next.add(c.chapter_id));
    onSelectionChange(next);
  };

  // Loop-fetch every matching chapter id across all pages (honors filters/search).
  const selectAllMatching = async () => {
    if (!onSelectionChange || !accessToken) return;
    const ids = new Set<string>();
    const fetchSize = 100;
    for (let offset = 0; offset < total && ids.size < selectAllCap; offset += fetchSize) {
      const page = await booksApi.listChapters(accessToken, bookId, { ...listParams, limit: fetchSize, offset });
      if (page.items.length === 0) break;
      for (const c of page.items) { if (ids.size >= selectAllCap) break; ids.add(c.chapter_id); }
    }
    onSelectionChange(ids);
  };

  return (
    <div className={cn('flex flex-col gap-2', className)}>
      {enableSearch && (
        <div className="relative">
          <Search className="absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('chapterBrowser.search', { defaultValue: 'Search chapters…' })}
            data-testid="chapter-browser-search"
            className="w-full rounded-md border bg-background pl-9 pr-3 py-1.5 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>
      )}

      {selectionMode === 'multi' && chapters.length > 0 && (
        <div className="flex items-center gap-2 px-1 text-[11px] text-muted-foreground">
          <input
            type="checkbox"
            checked={pageAllSelected}
            onChange={togglePageAll}
            aria-label={t('chapterBrowser.select_all', { defaultValue: 'Select all' })}
            className="h-3.5 w-3.5 rounded border-border accent-primary cursor-pointer"
          />
          <span>{sel.size > 0 ? t('chapterBrowser.selected', { count: sel.size, defaultValue: '{{count}} selected' }) : t('chapterBrowser.select_all', { defaultValue: 'Select all' })}</span>
          {enableSelectAll && pageAllSelected && total > chapters.length && sel.size < total && (
            <button onClick={() => void selectAllMatching()} className="text-primary hover:underline">
              {t('chapterBrowser.select_all_matching', { count: total, defaultValue: 'Select all {{count}}' })}
            </button>
          )}
        </div>
      )}

      <div className="rounded-lg border divide-y" data-testid="chapter-browser-list">
        {isLoading && chapters.length === 0 ? (
          <div className="p-4 space-y-2">{[1, 2, 3].map((i) => <div key={i} className="h-9 animate-pulse rounded bg-secondary" />)}</div>
        ) : chapters.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            {t('chapterBrowser.empty', { defaultValue: 'No chapters' })}
          </div>
        ) : (
          chapters.map((c) => {
            const selected = sel.has(c.chapter_id);
            return (
              <div
                key={c.chapter_id}
                onClick={() => { if (selectionMode === 'single') toggle(c.chapter_id); onRowClick?.(c); }}
                data-testid="chapter-browser-row"
                className={cn(
                  'flex items-center gap-3 px-3 py-2 text-sm transition-colors group',
                  (onRowClick || selectionMode === 'single') && 'cursor-pointer hover:bg-card/50',
                  (selected || activeChapterId === c.chapter_id) && 'bg-primary/5 border-l-2 border-l-primary',
                )}
              >
                {selectionMode === 'multi' && (
                  <input
                    type="checkbox"
                    checked={selected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggle(c.chapter_id)}
                    aria-label={t('chapterBrowser.select_row', { defaultValue: 'Select chapter' })}
                    className="h-3.5 w-3.5 shrink-0 rounded border-border accent-primary cursor-pointer"
                  />
                )}
                <span className="w-10 shrink-0 text-[10px] tabular-nums text-muted-foreground">#{c.sort_order}</span>
                <span className="flex-1 min-w-0 truncate">{c.title || c.original_filename || t('chapterBrowser.untitled', { defaultValue: 'Untitled' })}</span>
                {rowMeta?.(c)}
                {rowActions && <span onClick={(e) => e.stopPropagation()}>{rowActions(c)}</span>}
              </div>
            );
          })
        )}
      </div>

      {total > 0 && (
        <div className="flex items-center justify-between gap-2 flex-wrap text-[11px] text-muted-foreground">
          <span data-testid="chapter-browser-range">
            {t('chapterBrowser.range', { start, end, total, defaultValue: '{{start}}–{{end}} of {{total}}' })}
          </span>
          <Pager
            page={safePage}
            pageCount={pageCount}
            onPageChange={(p) => paged.setPage(Math.min(Math.max(0, p), pageCount - 1))}
            labels={{
              page: t('chapterBrowser.page', { defaultValue: 'Page' }),
              prev: t('chapterBrowser.prev', { defaultValue: 'Previous page' }),
              next: t('chapterBrowser.next', { defaultValue: 'Next page' }),
            }}
          />
        </div>
      )}
    </div>
  );
}

// A stable empty set so an uncontrolled browser doesn't churn identity each render.
const EMPTY_SET: Set<string> = new Set();
