// 15_chapter_browser.md B1 — Title-mode: migrates + extends `ChapterListBrowser`'s server-paged/
// debounced-search/multi-select data layer (DOCK-2 — same `booksApi.listChapters` +
// `useServerPagedList` + `useDebouncedValue` primitives, not a forked fetch/pagination scheme)
// with the sort dropdown, filter chips, word-count column, group-by-arc toggle (CB8), and
// bulk-action bar the design draft calls for. `ChapterListBrowser` itself stays untouched and
// keeps serving its existing callers (extraction wizard picker, etc.) — this is a sibling, richer
// consumer of the same query shape, not a replacement.
//
// Two client-side-only filters (CB6/CB7 honesty requirement — see the spec): the BE has no
// word-count-range or updated-within-days query params yet, so both are applied to the CURRENTLY
// LOADED PAGE only, after the server fetch. This means a narrow range filter can show fewer rows
// than the page size, and the server-reported `total`/pagination range does NOT reflect these two
// filters (only the server-side ones — status/language/search — do). Documented here, not hidden.
import { useMemo, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { ChevronDown, Languages as LanguagesIcon, LayoutGrid, List as ListIcon, Search } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { useServerPagedList } from '@/components/pagination/useServerPagedList';
import { Pager } from '@/components/pagination/Pager';
import { useDebouncedValue } from '@/features/raw-search/hooks/useDebouncedValue';
import { LANGUAGE_NAMES } from '@/lib/languages';
import { cn } from '@/lib/utils';
import { useStudioHost } from '../host/StudioHostProvider';
import { useChapterBrowserGroups, type ChapterArcGroup } from '@/features/books/hooks/useChapterBrowserGroups';
import { TranslateModal } from '@/pages/book-tabs/TranslateModal';

type SortKey = 'sort_order' | 'updated_at' | 'word_count' | 'lifecycle_state';
type StatusFilter = 'all' | 'draft' | 'published' | 'trashed';
type ViewMode = 'flat' | 'grouped';

const SORT_OPTIONS: { value: SortKey; labelKey: string; defaultLabel: string }[] = [
  { value: 'sort_order', labelKey: 'panels.chapter-browser.sort_chapter_num', defaultLabel: 'Sort: Chapter #' },
  { value: 'updated_at', labelKey: 'panels.chapter-browser.sort_updated', defaultLabel: 'Sort: Last updated' },
  { value: 'word_count', labelKey: 'panels.chapter-browser.sort_word_count', defaultLabel: 'Sort: Word count' },
  { value: 'lifecycle_state', labelKey: 'panels.chapter-browser.sort_status', defaultLabel: 'Sort: Status' },
];

function chapterStatusVariant(c: Chapter): 'draft' | 'published' | 'trashed' {
  if (c.lifecycle_state === 'trashed') return 'trashed';
  return c.editorial_status === 'published' ? 'published' : 'draft';
}

function StatusPill({ status }: { status: 'draft' | 'published' | 'trashed' }) {
  const { t } = useTranslation('studio');
  const cls = {
    draft: 'bg-secondary text-muted-foreground',
    published: 'bg-success/10 text-success',
    trashed: 'bg-destructive/10 text-destructive',
  }[status];
  return (
    <span className={cn('inline-flex w-fit items-center rounded-full px-2 py-0.5 text-[10px] font-semibold', cls)}>
      {t(`panels.chapter-browser.status_${status}`, { defaultValue: status })}
    </span>
  );
}

// Client-side range/date filters (see file header — documented limitation, not silent).
function passesClientFilters(c: Chapter, wordMin: string, wordMax: string, updatedWithinDays: string): boolean {
  const wc = c.word_count;
  if (wordMin.trim() !== '') {
    const min = Number(wordMin);
    if (Number.isFinite(min) && (wc === undefined || wc < min)) return false;
  }
  if (wordMax.trim() !== '') {
    const max = Number(wordMax);
    if (Number.isFinite(max) && (wc === undefined || wc > max)) return false;
  }
  if (updatedWithinDays.trim() !== '') {
    const days = Number(updatedWithinDays);
    if (Number.isFinite(days) && days > 0) {
      if (!c.updated_at) return false;
      const ageMs = Date.now() - new Date(c.updated_at).getTime();
      if (ageMs > days * 24 * 60 * 60 * 1000) return false;
    }
  }
  return true;
}

function groupFor(groups: ChapterArcGroup[], arcId: string | undefined): ChapterArcGroup | undefined {
  return arcId ? groups.find((g) => g.arcId === arcId) : undefined;
}

export function ChapterBrowserTitleView({ bookId }: { bookId: string }) {
  const { t } = useTranslation('studio');
  const { t: tBooks } = useTranslation('books');
  const { accessToken } = useAuth();
  const host = useStudioHost();
  const queryClient = useQueryClient();
  const invalidate = () => queryClient.invalidateQueries({ queryKey: ['chapter-browser-title', bookId] });
  const paged = useServerPagedList(50);

  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebouncedValue(searchInput, 300);
  const [sortKey, setSortKey] = useState<SortKey>('sort_order');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [langFilter, setLangFilter] = useState('');
  const [wordMin, setWordMin] = useState('');
  const [wordMax, setWordMax] = useState('');
  const [updatedWithinDays, setUpdatedWithinDays] = useState('');
  const [viewMode, setViewMode] = useState<ViewMode>('flat');
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [translateOpen, setTranslateOpen] = useState(false);

  // Reset to page 0 on any filter/sort/search change — the guarded render-time reset
  // ChapterListBrowser already uses (an event reaction, not a useEffect-for-events).
  const filterKey = `${statusFilter}|${langFilter}|${sortKey}|${debouncedSearch}`;
  const [prevFilterKey, setPrevFilterKey] = useState(filterKey);
  if (filterKey !== prevFilterKey) {
    setPrevFilterKey(filterKey);
    paged.reset();
  }

  const lifecycle = statusFilter === 'trashed' ? 'trashed' : 'active';
  const editorialStatus = statusFilter === 'draft' || statusFilter === 'published' ? statusFilter : undefined;

  const listParams = {
    lifecycle_state: lifecycle,
    editorial_status: editorialStatus,
    original_language: langFilter || undefined,
    q: debouncedSearch || undefined,
    sort: sortKey,
    limit: paged.limit,
    offset: paged.offset,
  };

  const { data, isLoading } = useQuery({
    queryKey: ['chapter-browser-title', bookId, statusFilter, langFilter, sortKey, debouncedSearch, paged.offset, paged.limit],
    queryFn: () => booksApi.listChapters(accessToken!, bookId, listParams),
    enabled: !!accessToken && !!bookId,
    placeholderData: (prev) => prev,
  });

  const rawChapters = data?.items ?? [];
  const chapters = useMemo(
    () => rawChapters.filter((c) => passesClientFilters(c, wordMin, wordMax, updatedWithinDays)),
    [rawChapters, wordMin, wordMax, updatedWithinDays],
  );
  const total = data?.total ?? 0;
  const { pageCount, safePage, start, end } = paged.pageInfo(total);
  const clientFiltered = chapters.length !== rawChapters.length;

  // CB8 — arc grouping reuses useChapterBrowserGroups (wraps compositionApi.listOutlineChildren
  // as-is, no fork of the Navigator's tree hook). Grouping only makes sense for the natural
  // chapter-order sort; hidden entirely (not just disabled) when the book has no Composition
  // Work, mirroring ManuscriptNavigator's own no-Work fallback.
  const groupsResult = useChapterBrowserGroups(bookId);
  const canGroup = groupsResult.hasWork && sortKey === 'sort_order';
  const grouped = viewMode === 'grouped' && canGroup;

  const setSearch = (v: string) => { setSearchInput(v); paged.reset(); };
  const setSort = (v: SortKey) => setSortKey(v);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const pageAllSelected = chapters.length > 0 && chapters.every((c) => selected.has(c.chapter_id));
  const togglePageAll = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (pageAllSelected) chapters.forEach((c) => next.delete(c.chapter_id));
      else chapters.forEach((c) => next.add(c.chapter_id));
      return next;
    });
  };
  const clearSelection = () => setSelected(new Set());

  const openChapter = (c: Chapter) => host.focusManuscriptUnit(c.chapter_id);

  // Bulk actions — all 4 wired to real endpoints (Phase A landed):
  // Translate reuses the existing TranslateModal (zero new BE). Set status / Export / Trash
  // call the new per-id-outcome bulk-status (A3) / bulk-zip (A4) endpoints — never assume the
  // whole batch succeeded, report the real per-id result (CB5).
  const [bulkBusy, setBulkBusy] = useState(false);

  const reportBulkOutcome = (results: Array<{ chapter_id: string; ok: boolean; error?: string }>) => {
    const failed = results.filter((r) => !r.ok);
    if (failed.length === 0) {
      toast.success(t('panels.chapter-browser.bulk_status_ok', { count: results.length, defaultValue: '{{count}} chapter(s) updated' }));
    } else {
      toast.error(t('panels.chapter-browser.bulk_status_partial', {
        okCount: results.length - failed.length, failCount: failed.length,
        defaultValue: '{{okCount}} updated, {{failCount}} failed',
      }));
    }
    invalidate();
  };

  const bulkRestore = async () => {
    if (!accessToken || selected.size === 0 || bulkBusy) return;
    setBulkBusy(true);
    try {
      const { results } = await booksApi.bulkUpdateChapterStatus(accessToken, bookId, [...selected], 'active');
      reportBulkOutcome(results);
      clearSelection();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  const bulkTrash = async () => {
    if (!accessToken || selected.size === 0 || bulkBusy) return;
    // Destructive bulk action — a quick native confirm (not a full ConfirmDialog) for this
    // integration pass; upgrading to the shared ConfirmDialog is a reasonable follow-up, not
    // a correctness gap (the action itself is still gated, just via a plainer prompt).
    if (!window.confirm(t('panels.chapter-browser.trash_confirm', { count: selected.size, defaultValue: 'Move {{count}} chapter(s) to trash?' }))) return;
    setBulkBusy(true);
    try {
      const { results } = await booksApi.bulkUpdateChapterStatus(accessToken, bookId, [...selected], 'trashed');
      reportBulkOutcome(results);
      clearSelection();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  const bulkExport = async () => {
    if (!accessToken || selected.size === 0 || bulkBusy) return;
    setBulkBusy(true);
    try {
      const blob = await booksApi.bulkExportChaptersZip(accessToken, bookId, [...selected]);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'chapters-export.zip';
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBulkBusy(false);
    }
  };

  let lastArcId: string | undefined;

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Toolbar row 1: search + sort + view toggle */}
      <div className="flex flex-wrap items-center gap-2 border-b p-2">
        <div className="relative min-w-[220px] flex-1">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={tBooks('chapterBrowser.search', { defaultValue: 'Search chapters…' })}
            data-testid="chapter-browser-title-search"
            className="w-full rounded-md border bg-background py-1.5 pl-8 pr-3 text-xs focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        <div className="relative">
          <select
            value={sortKey}
            onChange={(e) => setSort(e.target.value as SortKey)}
            data-testid="chapter-browser-sort-select"
            className="appearance-none rounded-md border bg-background py-1.5 pl-2.5 pr-7 text-xs font-medium focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {SORT_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{t(opt.labelKey, { defaultValue: opt.defaultLabel })}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
        </div>

        <div className="flex items-center gap-0.5 rounded-md border p-0.5">
          <button
            type="button"
            onClick={() => setViewMode('flat')}
            title={t('panels.chapter-browser.view_flat', { defaultValue: 'Flat list' })}
            data-testid="chapter-browser-view-flat"
            className={cn('rounded p-1', viewMode === 'flat' ? 'bg-secondary text-foreground' : 'text-muted-foreground')}
          >
            <ListIcon className="h-3.5 w-3.5" />
          </button>
          {canGroup && (
            <button
              type="button"
              onClick={() => setViewMode('grouped')}
              title={t('panels.chapter-browser.view_grouped', { defaultValue: 'Group by arc' })}
              data-testid="chapter-browser-view-grouped"
              className={cn('rounded p-1', viewMode === 'grouped' ? 'bg-secondary text-foreground' : 'text-muted-foreground')}
            >
              <LayoutGrid className="h-3.5 w-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Toolbar row 2: filter chips */}
      <div className="flex flex-wrap items-center gap-1.5 border-b p-2 text-[11px]">
        {(['all', 'draft', 'published', 'trashed'] as StatusFilter[]).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => setStatusFilter(s)}
            data-testid={`chapter-browser-status-${s}`}
            className={cn(
              'rounded-full border px-2.5 py-1 font-medium',
              statusFilter === s ? 'border-primary/40 bg-primary/10 text-primary' : 'border-border text-muted-foreground hover:text-foreground',
            )}
          >
            {t(`panels.chapter-browser.status_${s}`, { defaultValue: s === 'all' ? 'Status: All' : s })}
          </button>
        ))}

        <div className="relative">
          <LanguagesIcon className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-muted-foreground" />
          <select
            value={langFilter}
            onChange={(e) => setLangFilter(e.target.value)}
            data-testid="chapter-browser-lang-select"
            className="appearance-none rounded-full border bg-background py-1 pl-6 pr-6 font-medium focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">{t('panels.chapter-browser.lang_all', { defaultValue: 'Lang: All' })}</option>
            {Object.entries(LANGUAGE_NAMES).map(([code, name]) => (
              <option key={code} value={code}>{name} ({code})</option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-muted-foreground">
          <span>{t('panels.chapter-browser.words_label', { defaultValue: 'Words' })}</span>
          <input
            type="number"
            value={wordMin}
            onChange={(e) => setWordMin(e.target.value)}
            placeholder={t('panels.chapter-browser.min', { defaultValue: 'min' })}
            data-testid="chapter-browser-word-min"
            className="w-12 border-b border-dashed bg-transparent text-center text-foreground outline-none"
          />
          <span>–</span>
          <input
            type="number"
            value={wordMax}
            onChange={(e) => setWordMax(e.target.value)}
            placeholder={t('panels.chapter-browser.max', { defaultValue: 'max' })}
            data-testid="chapter-browser-word-max"
            className="w-12 border-b border-dashed bg-transparent text-center text-foreground outline-none"
          />
        </div>

        {/* Client-computed only (no BE date-range param yet — see file header). */}
        <div className="flex items-center gap-1 rounded-full bg-secondary px-2.5 py-1 text-muted-foreground">
          <span>{t('panels.chapter-browser.updated_within', { defaultValue: 'Updated within' })}</span>
          <input
            type="number"
            value={updatedWithinDays}
            onChange={(e) => setUpdatedWithinDays(e.target.value)}
            data-testid="chapter-browser-updated-within"
            className="w-10 border-b border-dashed bg-transparent text-center text-foreground outline-none"
          />
          <span>{t('panels.chapter-browser.days', { defaultValue: 'days' })}</span>
        </div>
      </div>

      {/* Bulk-action bar */}
      {selected.size > 0 && (
        <div className="flex items-center justify-between gap-2 border-b bg-primary/5 px-3 py-1.5" data-testid="chapter-browser-bulk-bar">
          <span className="text-xs font-semibold text-primary">
            {t('panels.chapter-browser.n_selected', { count: selected.size, defaultValue: `${selected.size} selected` })}{' '}
            <button type="button" onClick={clearSelection} className="text-[11px] font-normal text-muted-foreground underline">
              {t('panels.chapter-browser.clear', { defaultValue: 'clear' })}
            </button>
          </span>
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => setTranslateOpen(true)}
              data-testid="chapter-browser-bulk-translate"
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-secondary"
            >
              {t('panels.chapter-browser.translate', { defaultValue: 'Translate…' })}
            </button>
            <button
              type="button"
              onClick={() => void bulkRestore()}
              disabled={bulkBusy}
              data-testid="chapter-browser-bulk-status"
              title={t('panels.chapter-browser.set_status_hint', { defaultValue: 'Restore selected chapters to active' })}
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-secondary disabled:opacity-50"
            >
              {t('panels.chapter-browser.set_status', { defaultValue: 'Set status…' })}
            </button>
            <button
              type="button"
              onClick={() => void bulkExport()}
              disabled={bulkBusy}
              data-testid="chapter-browser-bulk-export"
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium hover:bg-secondary disabled:opacity-50"
            >
              {t('panels.chapter-browser.export', { defaultValue: 'Export' })}
            </button>
            <button
              type="button"
              onClick={() => void bulkTrash()}
              disabled={bulkBusy}
              data-testid="chapter-browser-bulk-trash"
              className="rounded-md border bg-background px-2.5 py-1 text-xs font-medium text-destructive hover:bg-destructive/10 disabled:opacity-50"
            >
              {t('panels.chapter-browser.trash', { defaultValue: 'Trash' })}
            </button>
          </div>
        </div>
      )}

      {/* Table */}
      <div className="min-h-0 flex-1 overflow-auto">
        <div
          className="sticky top-0 z-10 grid grid-cols-[24px_44px_1fr_60px_84px_64px_88px] gap-2 border-b bg-background px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground"
        >
          <input type="checkbox" checked={pageAllSelected} onChange={togglePageAll} aria-label={tBooks('chapterBrowser.select_all', { defaultValue: 'Select all' })} className="accent-primary" />
          <span>#</span>
          <span>{t('panels.chapter-browser.col_title', { defaultValue: 'Title' })}</span>
          <span>{t('panels.chapter-browser.col_lang', { defaultValue: 'Lang' })}</span>
          <span>{t('panels.chapter-browser.col_status', { defaultValue: 'Status' })}</span>
          <span className="text-right">{t('panels.chapter-browser.col_words', { defaultValue: 'Words' })}</span>
          <span className="text-right">{t('panels.chapter-browser.col_updated', { defaultValue: 'Updated' })}</span>
        </div>

        {isLoading && chapters.length === 0 ? (
          <div className="space-y-1.5 p-3">
            {[1, 2, 3].map((i) => <div key={i} className="h-8 animate-pulse rounded bg-secondary" />)}
          </div>
        ) : chapters.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            {t('panels.chapter-browser.empty', { defaultValue: 'No chapters match these filters.' })}
          </div>
        ) : (
          chapters.map((c) => {
            const arcId = grouped ? groupsResult.arcIdForChapter(c.chapter_id) : undefined;
            const showHeader = grouped && arcId !== undefined && arcId !== lastArcId;
            if (grouped) lastArcId = arcId;
            const group = showHeader ? groupFor(groupsResult.groups, arcId) : undefined;
            const isSelected = selected.has(c.chapter_id);
            return (
              <div key={c.chapter_id}>
                {showHeader && group && (
                  <div
                    data-testid="chapter-browser-group-header"
                    className="flex items-center gap-2 border-b bg-secondary px-2 py-1.5 text-[11px] font-semibold text-accent-foreground"
                  >
                    <span className="font-mono text-[9px] text-accent">{group.romanNumeral}</span>
                    <span>{group.label}</span>
                    <span className="ml-auto font-mono text-[10px] font-normal text-muted-foreground">
                      {t('panels.chapter-browser.chapter_count', { count: group.chapterCount, defaultValue: `${group.chapterCount} chapters` })}
                    </span>
                  </div>
                )}
                <div
                  onClick={() => openChapter(c)}
                  data-testid="chapter-browser-row"
                  className={cn(
                    'grid cursor-pointer grid-cols-[24px_44px_1fr_60px_84px_64px_88px] items-center gap-2 border-b px-2 py-1.5 text-xs hover:bg-secondary',
                    isSelected && 'bg-primary/5',
                  )}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onClick={(e) => e.stopPropagation()}
                    onChange={() => toggle(c.chapter_id)}
                    aria-label={tBooks('chapterBrowser.select_row', { defaultValue: 'Select chapter' })}
                    className="accent-primary"
                  />
                  <span className="font-mono text-[10px] text-muted-foreground">#{c.sort_order}</span>
                  <span className="truncate font-medium">{c.title || c.original_filename || tBooks('chapterBrowser.untitled', { defaultValue: 'Untitled' })}</span>
                  <span className="font-mono text-[10px] text-muted-foreground">{c.original_language}</span>
                  <StatusPill status={chapterStatusVariant(c)} />
                  {/* CB3 — word_count may not exist on the API response yet; render gracefully. */}
                  <span className="text-right font-mono text-[11px] text-muted-foreground">{c.word_count ?? '—'}</span>
                  <span className="text-right text-[10px] text-muted-foreground">{c.updated_at ? new Date(c.updated_at).toLocaleDateString() : '—'}</span>
                </div>
              </div>
            );
          })
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between gap-2 border-t px-2.5 py-1.5 text-[10.5px] text-muted-foreground">
        <span data-testid="chapter-browser-range">
          {total > 0 ? tBooks('chapterBrowser.range', { start, end, total, defaultValue: `${start}–${end} of ${total}` }) : ''}
          {clientFiltered && ` · ${t('panels.chapter-browser.client_filtered_note', { defaultValue: 'word/date filters apply to this page only' })}`}
        </span>
        <Pager
          page={safePage}
          pageCount={pageCount}
          onPageChange={(p) => paged.setPage(Math.min(Math.max(0, p), pageCount - 1))}
          labels={{
            page: tBooks('chapterBrowser.page', { defaultValue: 'Page' }),
            prev: tBooks('chapterBrowser.prev', { defaultValue: 'Previous page' }),
            next: tBooks('chapterBrowser.next', { defaultValue: 'Next page' }),
          }}
        />
      </div>

      <TranslateModal
        open={translateOpen}
        onClose={() => setTranslateOpen(false)}
        bookId={bookId}
        onJobCreated={() => { setTranslateOpen(false); clearSelection(); }}
        preselectedChapterIds={[...selected]}
      />
    </div>
  );
}

