import { useMemo, useState } from 'react';

export interface PagedList<T> {
  /** Current page, 0-based and clamped to [0, pageCount-1]. */
  page: number;
  /** Jump to a page (0-based); clamps out-of-range values. */
  setPage: (page: number) => void;
  /** Total pages (≥ 1, even for an empty list). */
  pageCount: number;
  /** Absolute index of the first item on the current page (for "1-based row #"). */
  start: number;
  /** The items on the current page. */
  pageItems: T[];
}

/**
 * Page-through pagination state for a client-side list — shared by the chapter
 * import review and the translator wizard (the deferred shared-chapter-browser
 * epic's pagination half). Pairs with <Pager/> for the controls. Page reset on a
 * data swap stays the caller's job (e.g. call setPage(0) when a modal reopens) —
 * the hook deliberately holds no opinion about when the underlying data changes.
 */
export function usePagedList<T>(items: T[], pageSize: number): PagedList<T> {
  const [page, setPageRaw] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const safePage = Math.min(Math.max(0, page), pageCount - 1);
  const start = safePage * pageSize;
  const pageItems = useMemo(() => items.slice(start, start + pageSize), [items, start, pageSize]);
  const setPage = (p: number) => setPageRaw(Math.min(pageCount - 1, Math.max(0, p)));
  return { page: safePage, setPage, pageCount, start, pageItems };
}
