import { useState } from 'react';

export interface ServerPagedList {
  /** Current page, 0-based. The caller clamps against pageCount (which needs the
   *  server `total`) — see `pageInfo`. */
  page: number;
  /** Set the page (caller is expected to pass an in-range value; pair with pageInfo). */
  setPage: (page: number) => void;
  pageSize: number;
  /** Change page size; resets to page 0 (the old offset is meaningless at a new size). */
  setPageSize: (size: number) => void;
  /** Server offset for the current page (= page * pageSize) — the query INPUT. */
  offset: number;
  /** Server limit (= pageSize). */
  limit: number;
  /** Jump back to page 0 — call from filter/sort/search change handlers. */
  reset: () => void;
  /**
   * Derive the total-dependent view from the server `total` (the query OUTPUT).
   * Kept as a pure function rather than a hook input so `offset` never depends on
   * `total` — that would feed the query's own result back into its key.
   * `safePage` clamps the displayed page when `total` shrinks.
   */
  pageInfo: (total: number) => { pageCount: number; safePage: number; start: number; end: number };
}

/**
 * Server-side pagination state — the counterpart to {@link usePagedList} (which
 * slices a client-held array). The caller drives a server query with `offset` /
 * `limit`, then passes the response `total` to `pageInfo` for the page count and
 * the "X–Y of N" range. Reset to page 0 on filter/sort/search changes by calling
 * `reset()` from those handlers (not an effect — page-reset is an event reaction).
 */
export function useServerPagedList(initialPageSize = 50): ServerPagedList {
  const [pageSize, setPageSizeRaw] = useState(initialPageSize);
  const [page, setPage] = useState(0);

  const offset = page * pageSize;
  const setPageSize = (size: number) => {
    setPageSizeRaw(size);
    setPage(0);
  };
  const reset = () => setPage(0);

  const pageInfo = (total: number) => {
    const pageCount = Math.max(1, Math.ceil(total / pageSize));
    const safePage = Math.min(Math.max(0, page), pageCount - 1);
    const safeOffset = safePage * pageSize;
    return {
      pageCount,
      safePage,
      start: total === 0 ? 0 : safeOffset + 1,
      end: Math.min(safeOffset + pageSize, total),
    };
  };

  return { page, setPage, pageSize, setPageSize, offset, limit: pageSize, reset, pageInfo };
}
