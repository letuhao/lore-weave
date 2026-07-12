// 24 BPS-13 — the book's chapter spine, for the drawer's ⚓ re-anchor picker.
//
// This is NOT a cold-open read: it loads on demand for a control the user only sees with the drawer
// open, so it stays outside PH9's ≤5 budget. It pages in FULL — book-service CLAMPS `limit` to 100
// (server.go parseLimitOffset), so asking for more silently returns 100 and a >100-chapter book's
// tail would simply be missing from the picker, with no signal. That exact trap already produced one
// manuscript-corrupting bug in this feature (Row-3's undo, `749805ca6`); do not re-lay it.
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '@/features/books/api';

const PAGE = 100;
const MAX_PAGES = 200; // 20k chapters

export interface BookChapter {
  chapter_id: string;
  title: string;
  sort_order: number;
}

export function useBookChapters(bookId: string, token: string | null): BookChapter[] {
  const { data } = useQuery({
    queryKey: ['plan-hub', 'book-chapters', bookId],
    enabled: !!token && !!bookId,
    staleTime: 60_000,
    queryFn: async () => {
      const rows: BookChapter[] = [];
      for (let page = 0; page < MAX_PAGES; page++) {
        const res = await booksApi.listChapters(token!, bookId, {
          limit: PAGE,
          offset: page * PAGE,
        });
        rows.push(
          ...res.items.map((c) => ({
            chapter_id: c.chapter_id,
            title: c.title ?? '',
            sort_order: c.sort_order,
          })),
        );
        if (res.items.length < PAGE) break;
      }
      return rows.sort((a, b) => a.sort_order - b.sort_order);
    },
  });
  return data ?? [];
}
