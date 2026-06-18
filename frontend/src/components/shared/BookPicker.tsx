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
    booksApi
      .listBooks(accessToken, { limit })
      .then((res) => {
        if (!cancelled) setBooks(res.items);
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
  }, [accessToken, limit]);

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

  const selected = useMemo(
    () => (value ? books?.find((b) => b.book_id === value) ?? null : null),
    [books, value],
  );

  const matches = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    const list = books ?? [];
    if (!q) return list.slice(0, 50);
    return list.filter((b) => b.title.toLowerCase().includes(q)).slice(0, 50);
  }, [books, debounced]);

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
        </ul>
      )}
    </div>
  );
}
