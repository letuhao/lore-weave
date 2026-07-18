// Simple mode's data: the book's chapters, WINDOWED. Deliberately NOT useBookChapters (which walks up
// to 200 sequential pages — a cold-open budget violation its own header warns shipped once). Simple
// mode is the DEFAULT view, so it must load like the manuscript navigator does: keyset page of 100,
// `total` on the first page, `+ more` to page. Scales to 10k chapters without a request storm.
import { useCallback, useState } from 'react';
import { useInfiniteQuery } from '@tanstack/react-query';
import { booksApi } from '@/features/books/api';
import type { NodeSource } from '../types';

export interface SimpleChapter {
  chapter_id: string;
  title: string;
  sort_order: number;
  word_count: number | null;
  /** editorial_status from book-service: 'draft' | 'published'. Undefined on older BE. */
  published: boolean;
  /** Authorship — 'authored' (the writer's) vs 'mined' (an AI-proposed chapter). Book chapters are
   *  the writer's prose units, so this is 'authored' today; the field + the "AI idea" row styling
   *  exist so an AI-proposed chapter renders correctly (Mono + teal) the moment such a flow lands. */
  source: NodeSource;
}

export interface SimpleChaptersResult {
  chapters: SimpleChapter[];
  total: number | null;
  loading: boolean;
  error: boolean;
  hasMore: boolean;
  loadMore: () => void;
  loadingMore: boolean;
}

const PAGE = 100;

export function useSimpleChapters(bookId: string, token: string | null, enabled: boolean): SimpleChaptersResult {
  const [total, setTotal] = useState<number | null>(null);
  const q = useInfiniteQuery({
    queryKey: ['plan-hub', 'simple-chapters', bookId],
    enabled: !!token && !!bookId && enabled,
    initialPageParam: null as string | null,
    queryFn: async ({ pageParam }) => {
      const res = await booksApi.listChaptersPage(token!, bookId, { cursor: pageParam, limit: PAGE, sort: 'sort_order' });
      if (res.total != null) setTotal(res.total); // total rides only the first (cursorless) page
      return res;
    },
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });

  const chapters: SimpleChapter[] = (q.data?.pages ?? []).flatMap((p) =>
    p.items.map((c) => ({
      chapter_id: c.chapter_id,
      title: c.title ?? '',
      sort_order: c.sort_order,
      word_count: c.word_count ?? null,
      published: c.editorial_status === 'published',
      // Book chapters are the writer's prose units → authored. (No book-service authorship flag; an
      // AI-proposed chapter, when that flow exists, would set this to 'mined'.)
      source: 'authored',
    })),
  );

  return {
    chapters,
    total,
    loading: q.isLoading,
    error: q.isError,
    hasMore: q.hasNextPage,
    loadMore: useCallback(() => { if (q.hasNextPage && !q.isFetchingNextPage) void q.fetchNextPage(); }, [q]),
    loadingMore: q.isFetchingNextPage,
  };
}
