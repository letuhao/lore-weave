import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { translationApi } from '@/features/translation/api';

/**
 * List/search/language-filter/create/coverage-batch logic extracted from `BooksPage.tsx`
 * (14_utility_panels.md Phase C1, docs/standards/dockable-gui.md DOCK-2) so the standalone
 * `/books` route AND the studio `books` dock panel (`BooksBrowserPanel`) share ONE
 * implementation instead of forking it. Simple page-local filter-UI state (search/langFilter/
 * create-dialog fields) stays in this hook too — the goal is reuse, not a state-ownership
 * ideology (C1 brief explicitly allows this).
 *
 * Byte-preserving extraction: every effect/fetch/derivation below is copied verbatim from
 * BooksPage's original inline `useState`s — including the pre-existing quirk that `load()`
 * fetches ALL books unpaginated (no limit/offset sent to the API) while `offset` only drives
 * the <Pagination> display, not a refetch. Not fixed here — out of scope for a reuse extraction.
 */
export function useBooksList() {
  const { accessToken } = useAuth();
  const [books, setBooks] = useState<Book[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [search, setSearch] = useState('');
  const [offset, setOffset] = useState(0);
  const limit = 20;

  // Create dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [creating, setCreating] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newLang, setNewLang] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [bookLangs, setBookLangs] = useState<Record<string, string[]>>({});

  const load = async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const res = await booksApi.listBooks(accessToken);
      setBooks(res.items);
      setTotal(res.total || res.items.length);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [accessToken]);

  // Fetch translation coverage per book (batched 10 at a time, fire-and-forget)
  const bookIds = books.map((b) => b.book_id).join(',');
  useEffect(() => {
    if (!accessToken || books.length === 0) return;
    let cancelled = false;
    const fetchCoverage = async () => {
      const results: Record<string, string[]> = {};
      // Batch requests in groups of 10 to avoid overwhelming the server
      for (let i = 0; i < books.length; i += 10) {
        if (cancelled) break;
        const batch = books.slice(i, i + 10);
        await Promise.allSettled(
          batch.map(async (book) => {
            try {
              const cov = await translationApi.getBookCoverage(accessToken, book.book_id);
              if (cov.known_languages?.length > 0) {
                results[book.book_id] = cov.known_languages;
              }
            } catch {}
          }),
        );
      }
      if (!cancelled) setBookLangs(results);
    };
    void fetchCoverage();
    return () => { cancelled = true; };
  }, [accessToken, bookIds]);

  const filteredBooks = books.filter((b) => {
    if (search && !b.title.toLowerCase().includes(search.toLowerCase())) return false;
    if (langFilter && b.original_language !== langFilter) return false;
    return true;
  });

  const allLanguages = [...new Set(books.map((b) => b.original_language).filter(Boolean))] as string[];

  // D-BOOKS-CREATE-TO-STUDIO: returns the new book's id so a caller that wants
  // to navigate straight into it (BooksPage → /studio) can; BooksBrowserPanel
  // (browsing OTHER books from inside an already-open studio) ignores the
  // return value on purpose — auto-navigating there would unmount the active
  // book's studio out from under the user.
  const handleCreate = async (): Promise<string | undefined> => {
    // F16 — language is REQUIRED: a language-less book breaks downstream (chapters
    // require original_language, which they inherit from the book). The submit button
    // is disabled without it too; this guards the programmatic path.
    if (!accessToken || !newTitle.trim() || !newLang) return undefined;
    setCreating(true);
    try {
      const created = await booksApi.createBook(accessToken, {
        title: newTitle.trim(),
        description: newDesc || undefined,
        original_language: newLang || undefined,
      });
      setCreateOpen(false);
      setNewTitle('');
      setNewDesc('');
      setNewLang('');
      await load();
      return created.book_id;
    } catch (e) {
      setError((e as Error).message);
      return undefined;
    } finally {
      setCreating(false);
    }
  };

  return {
    books,
    total,
    loading,
    error,
    search,
    setSearch,
    offset,
    setOffset,
    limit,
    createOpen,
    setCreateOpen,
    creating,
    newTitle,
    setNewTitle,
    newDesc,
    setNewDesc,
    newLang,
    setNewLang,
    langFilter,
    setLangFilter,
    bookLangs,
    filteredBooks,
    allLanguages,
    handleCreate,
    load,
  };
}

export type UseBooksListResult = ReturnType<typeof useBooksList>;

/** Generate a stable hue from a book ID for cover gradient — shared by BooksPage AND
 *  BooksBrowserPanel so the cover-gradient rendering isn't a second copy (DOCK-2). */
export function hashToHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xfff;
  return h % 360;
}
