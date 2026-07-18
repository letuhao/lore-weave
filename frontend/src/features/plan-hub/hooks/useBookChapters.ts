// 24 BPS-13 — the book's chapter spine, for the drawer's ⚓ re-anchor picker.
//
// It must NOT fire at cold open. `enabled` is gated on `active` — i.e. on a node actually being
// SELECTED — because this walks the whole spine (up to 200 sequential `GET /chapters` pages on a
// 10k-chapter book). Shipped once as an unconditional `useQuery` in usePlanHub, which re-introduced
// the exact PH9 budget violation A11 had removed from `useActualState` ONE COMMIT EARLIER: ~100
// serial requests on panel open, for a control nobody had opened yet. The cold-open budget test
// missed it because it only summed the five NAMED apis and never asserted that nothing ELSE fired —
// a budget assertion that enumerates the allowed calls but not the forbidden ones is half a test.
//
// It pages in FULL — book-service CLAMPS `limit` to 100 (server.go parseLimitOffset), so asking for
// more silently returns 100 and a >100-chapter book's tail would simply be missing from the picker,
// with no signal. That exact trap already produced one manuscript-corrupting bug in this feature
// (Row-3's undo, `749805ca6`); do not re-lay it.
import { useQuery } from '@tanstack/react-query';
import { booksApi } from '@/features/books/api';

const PAGE = 100;
const MAX_PAGES = 200; // 20k chapters

export interface BookChapter {
  chapter_id: string;
  title: string;
  sort_order: number;
}

export interface BookChaptersResult {
  chapters: BookChapter[];
  /** The read FAILED. Load-bearing: with `[]` the anchor picker shows "— not anchored —" as the
   *  selected option for an ANCHORED node, silently misreporting its state. The caller must say so
   *  rather than render a confident lie. */
  error: boolean;
}

export function useBookChapters(
  bookId: string,
  token: string | null,
  /** Only fetch when the picker can actually be seen (a node is selected). See the header. */
  active: boolean,
): BookChaptersResult {
  const { data, isError } = useQuery({
    queryKey: ['plan-hub', 'book-chapters', bookId],
    enabled: !!token && !!bookId && active,
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
  return { chapters: data ?? [], error: isError };
}
