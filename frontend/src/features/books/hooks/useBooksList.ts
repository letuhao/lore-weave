import { useEffect, useState } from 'react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type ImportJob } from '@/features/books/api';
import { translationApi } from '@/features/translation/api';

export type NewFB2ImportStage = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';

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
	const [newFB2File, setNewFB2File] = useState<File | null>(null);
  const [newFB2ImportStage, setNewFB2ImportStage] = useState<NewFB2ImportStage>('idle');
  const [newFB2ImportProgress, setNewFB2ImportProgress] = useState(0);
  const [newFB2ImportJob, setNewFB2ImportJob] = useState<ImportJob | null>(null);
  const [newFB2ImportError, setNewFB2ImportError] = useState('');
  const [langFilter, setLangFilter] = useState('');
  const [bookLangs, setBookLangs] = useState<Record<string, string[]>>({});

  // The search term the LAST fetch was made with. Kept separate from `search`
  // (which updates on every keystroke) so the debounce below has something to
  // compare against, and so `filteredBooks` never claims to have filtered a
  // term the server has not answered yet.
  const [appliedSearch, setAppliedSearch] = useState('');

  const load = async (q = appliedSearch) => {
    if (!accessToken) return;
    setLoading(true);
    try {
      // `q` goes to the SERVER. It used to be filtered here, in the browser,
      // over whatever listBooks happened to return — and listBooks was called
      // with no limit, so that was the endpoint's default of 20 rows. The page
      // then displayed `total` (the real count) beside a search that had only
      // ever seen the first page: 83 books shown, 20 searched, and a book at
      // rank 32 simply could not be found by name.
      // No search term => the call is byte-identical to what it always was.
      // Passing an explicit `undefined` would be equivalent to the API and NOT
      // equivalent to its callers' expectations, which is a needless break.
      const res = q
        ? await booksApi.listBooks(accessToken, { q })
        : await booksApi.listBooks(accessToken);
      setBooks(res.items);
      setTotal(res.total || res.items.length);
      setAppliedSearch(q);
      setError('');
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void load(); }, [accessToken]);

  // Refetch when the search term settles. A keystroke must not become a request.
  useEffect(() => {
    if (!accessToken) return;
    if (search === appliedSearch) return;
    const id = setTimeout(() => { void load(search); }, 300);
    return () => clearTimeout(id);
  }, [search, appliedSearch, accessToken]);

  useEffect(() => {
    if (!accessToken || !newFB2ImportJob || newFB2ImportStage !== 'processing') return;

    let cancelled = false;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;

    const poll = async () => {
      try {
        const updated = await booksApi.getImportJob(accessToken, newFB2ImportJob.book_id, newFB2ImportJob.id);
        if (cancelled) return;

        setNewFB2ImportJob(updated);
        if (updated.status === 'completed') {
          setNewFB2ImportStage('completed');
          void load();
          return;
        }
        if (updated.status === 'failed') {
          setNewFB2ImportStage('failed');
          setNewFB2ImportError(updated.error || 'The FB2 import failed while processing the file.');
          return;
        }
      } catch {
        // Keep reporting a running server-side job after a transient status-read failure.
      }

      if (!cancelled) pollTimer = setTimeout(() => { void poll(); }, 2_000);
    };

    void poll();
    return () => {
      cancelled = true;
      if (pollTimer) clearTimeout(pollTimer);
    };
  }, [accessToken, newFB2ImportJob?.book_id, newFB2ImportJob?.id, newFB2ImportStage]);

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

  // Title matching is the SERVER's job now (see load()). Only the language
  // facet is still local, and that one is honest: `bookLangs` is derived from
  // the rows in hand, so it can only ever narrow what the server returned.
  const filteredBooks = books.filter((b) => {
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

	// New-book FB2 imports intentionally have their own server-owned operation:
	// keep the dialog mounted so it can report the asynchronous job's real progress.
	const handleFB2Import = async (): Promise<void> => {
		if (!accessToken || !newFB2File) return;
		setCreating(true);
    setNewFB2ImportStage('uploading');
    setNewFB2ImportProgress(0);
    setNewFB2ImportJob(null);
    setNewFB2ImportError('');
		try {
			const job = await booksApi.startNewFB2Import(
        accessToken,
        newFB2File,
        newLang || undefined,
        setNewFB2ImportProgress,
      );
      setNewFB2ImportJob(job);
      setNewFB2ImportStage('processing');
		} catch (e) {
      setNewFB2ImportStage('failed');
      setNewFB2ImportError((e as Error).message);
		} finally {
			setCreating(false);
		}
	};

  const resetNewFB2Import = () => {
    setNewFB2File(null);
    setNewFB2ImportStage('idle');
    setNewFB2ImportProgress(0);
    setNewFB2ImportJob(null);
    setNewFB2ImportError('');
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
		newFB2File,
		setNewFB2File,
    newFB2ImportStage,
    newFB2ImportProgress,
    newFB2ImportJob,
    newFB2ImportError,
    langFilter,
    setLangFilter,
    bookLangs,
    filteredBooks,
    allLanguages,
    handleCreate,
		handleFB2Import,
    resetNewFB2Import,
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
