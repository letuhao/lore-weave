import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, BookOpen } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';

/**
 * C4 (BL-3 / G6) — reusable book picker. Replaces raw-UUID `book_id` fields:
 * the book is the workspace anchor, so users pick it BY TITLE, never by pasting a
 * UUID. Searches the user's books (`booksApi.listBooks`, reused as-is) and emits
 * the selected `book_id`. An empty selection is a VALID state (book is optional
 * for a knowledge project / campaign).
 *
 * The list is loaded once and filtered client-side by title (the books endpoint
 * has no search param — Scope OUT forbids a new one); the input is debounced so
 * typing doesn't thrash render. Scales past a plain <select> because the matches
 * are filtered, not all rendered.
 */
interface Props {
  /** Selected book_id (UUID) or null. */
  value: string | null;
  onChange: (bookId: string | null) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Cap on books fetched for the picker. */
  limit?: number;
}

export function BookPicker({ value, onChange, disabled, placeholder, limit = 200 }: Props) {
  const { accessToken } = useAuth();
  const [books, setBooks] = useState<Book[] | null>(null);
  const [error, setError] = useState(false);
  const [total, setTotal] = useState(0);
  const [selectedBook, setSelectedBook] = useState<Book | null>(null);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Load the user's books once.
  useEffect(() => {
    if (!accessToken) {
      setBooks([]);
      return;
    }
    let cancelled = false;
    // The TITLE FILTER IS THE SERVER'S. It used to be a client-side
    // `includes()` over whatever this one call returned — and this call asks
    // for `limit: 200` while the endpoint clamps to 100, so the picker filtered
    // 100 rows in the belief it held every book. At 83 books that is invisible;
    // at 101 the picker starts omitting books with no symptom at all. That is
    // the same defect the library page shipped, one page further in.
    booksApi
      .listBooks(accessToken, { limit, ...(debounced.trim() ? { q: debounced.trim() } : {}) })
      .then((res) => {
        if (!cancelled) {
          setBooks(res.items);
          setTotal(res.total ?? res.items.length);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setBooks([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, limit, debounced]);

  // Debounce the title filter.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setDebounced(query), 180);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query]);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  // The selected book is REMEMBERED, not re-derived from the current page.
  // Deriving it worked only while the component held every book; now that the
  // list is a search result, the chosen book is usually absent from it, and
  // re-deriving would blank the picker's own label the moment you typed.
  useEffect(() => {
    if (!value) {
      setSelectedBook(null);
      return;
    }
    const hit = books?.find((b) => b.book_id === value);
    if (hit) setSelectedBook(hit);
  }, [books, value]);
  const selected = selectedBook;

  // The server has already applied the title filter; this only caps the render.
  const matches = useMemo(() => (books ?? []).slice(0, 50), [books]);

  // How many books the query matched but this page does not hold. Shown rather
  // than swallowed: a picker that quietly lists 100 of 140 is indistinguishable
  // from one whose user simply has 100 books.
  const notShown = Math.max(0, total - (books?.length ?? 0));

  function select(b: Book) {
    onChange(b.book_id);
    setOpen(false);
    setQuery('');
  }
  function clear() {
    onChange(null);
    setQuery('');
  }

  // When a book is selected, show its title + a clear affordance instead of the
  // search input (internal branching, not unmount — keeps the picker mounted).
  if (value) {
    return (
      <div ref={rootRef} className="flex items-center gap-2 rounded-md border bg-input px-3 py-2 text-sm">
        <BookOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate" data-testid="book-picker-selected">
          {selected ? selected.title : value}
        </span>
        {!disabled && (
          <button
            type="button"
            onClick={clear}
            aria-label="Clear selected book"
            className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-center gap-2 rounded-md border bg-input px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls="book-picker-list"
          value={query}
          disabled={disabled || books === null}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? 'Search your books by title…'}
          className="flex-1 bg-transparent text-sm outline-none disabled:opacity-60"
        />
      </div>
      {open && books !== null && (
        <ul
          id="book-picker-list"
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-card shadow-lg"
        >
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-[11px] text-muted-foreground">
              {error ? 'Failed to load books.' : books.length === 0 ? 'No books yet.' : 'No matching books.'}
            </li>
          ) : (
            matches.map((b) => (
              <li key={b.book_id} role="option" aria-selected={false}>
                <button
                  type="button"
                  onClick={() => select(b)}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-foreground/[0.04]',
                  )}
                >
                  <BookOpen className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{b.title}</span>
                  <span className="text-[10px] text-muted-foreground">{b.chapter_count} ch</span>
                </button>
              </li>
            ))
          )}
          {notShown > 0 && (
            <li
              className="border-t px-3 py-1.5 text-[10px] text-muted-foreground"
              data-testid="book-picker-truncated"
            >
              {notShown} more match{notShown === 1 ? '' : 'es'} not shown — keep typing to narrow.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
