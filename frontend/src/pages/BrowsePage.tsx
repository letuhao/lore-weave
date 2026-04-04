import { useCallback, useEffect, useRef, useState } from 'react';
import { Search } from 'lucide-react';
import { toast } from 'sonner';
import { booksApi } from '@/features/books/api';
import { BookCard } from '@/features/browse/BookCard';
import { FilterBar } from '@/features/browse/FilterBar';
import { Pagination } from '@/components/shared/Pagination';

type CatalogBook = {
  book_id: string;
  title: string;
  description?: string | null;
  original_language?: string | null;
  summary_excerpt?: string | null;
  chapter_count?: number;
  has_cover?: boolean;
  cover_url?: string | null;
  created_at?: string | null;
};

export function BrowsePage() {
  const [books, setBooks] = useState<CatalogBook[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [language, setLanguage] = useState('');
  const [sort, setSort] = useState('recent');
  const [limit] = useState(12);
  const [offset, setOffset] = useState(0);
  const abortRef = useRef<AbortController | null>(null);

  const fetchBooks = useCallback(async () => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    try {
      const params: Record<string, string> = {};
      if (limit) params.limit = String(limit);
      if (offset) params.offset = String(offset);
      if (search.trim()) params.q = search.trim();
      if (language) params.language = language;
      if (sort) params.sort = sort;

      const qs = new URLSearchParams(params).toString();
      // Use the catalog API — no auth required
      const res = await fetch(`${import.meta.env.VITE_API_BASE || ''}/v1/catalog/books${qs ? `?${qs}` : ''}`);
      if (controller.signal.aborted) return;
      if (!res.ok) throw new Error('Failed to load catalog');
      const data = await res.json();
      setBooks(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch {
      if (controller.signal.aborted) return;
      setBooks([]);
      setTotal(0);
      toast.error('Failed to load catalog');
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [limit, offset, search, language, sort]);

  useEffect(() => {
    void fetchBooks();
    return () => { abortRef.current?.abort(); };
  }, [fetchBooks]);

  // Debounce search
  const [searchInput, setSearchInput] = useState('');
  useEffect(() => {
    const timer = setTimeout(() => {
      setSearch(searchInput);
      setOffset(0);
    }, 400);
    return () => clearTimeout(timer);
  }, [searchInput]);

  function handleLanguageChange(lang: string) {
    setLanguage(lang);
    setOffset(0);
  }

  function handleSortChange(s: string) {
    setSort(s);
    setOffset(0);
  }

  return (
    <div className="mx-auto max-w-[1100px] px-6 py-6">
      {/* Hero */}
      <div className="pb-6 pt-8 text-center">
        <h1 className="font-serif text-2xl font-semibold">Discover Stories</h1>
        <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
          Browse public novels from the LoreWeave community. Read, translate, and explore stories across languages.
        </p>
      </div>

      {/* Search */}
      <div className="mx-auto mb-6 max-w-[500px]">
        <div className="relative">
          <Search className="absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            placeholder="Search by title, author, or language..."
            aria-label="Search catalog"
            className="h-[42px] w-full rounded-[10px] border bg-background pl-10 pr-4 text-sm placeholder:text-muted-foreground/40 focus:border-ring focus:outline-none focus:ring-1 focus:ring-ring/30"
          />
        </div>
      </div>

      {/* Filters + sort */}
      <FilterBar
        language={language}
        sort={sort}
        total={total}
        onLanguageChange={handleLanguageChange}
        onSortChange={handleSortChange}
      />

      {/* Grid */}
      {loading && books.length === 0 ? (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="aspect-[2/3] animate-pulse rounded-[10px] border bg-card" />
          ))}
        </div>
      ) : books.length === 0 ? (
        <div className="py-16 text-center text-sm text-muted-foreground">
          No books found. Try a different search or filter.
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-4">
          {books.map((book) => (
            <BookCard key={book.book_id} book={book} />
          ))}
        </div>
      )}

      {/* Pagination */}
      <div className="flex justify-center py-8">
        <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />
      </div>
    </div>
  );
}
