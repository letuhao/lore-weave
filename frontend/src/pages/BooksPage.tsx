import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { BookOpen, Plus, ChevronRight } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book } from '@/features/books/api';
import { translationApi } from '@/features/translation/api';
import { PageHeader } from '@/components/layout/PageHeader';
import { FilterToolbar, Pagination, EmptyState, FormDialog, StatusBadge, SkeletonCard } from '@/components/shared';
import { LanguageDisplay } from '@/components/shared/LanguageDisplay';

/** Generate a stable hue from a book ID for cover gradient */
function hashToHue(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) & 0xfff;
  return h % 360;
}

export function BooksPage() {
  const { t } = useTranslation('books');
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

  const handleCreate = async () => {
    if (!accessToken || !newTitle.trim()) return;
    setCreating(true);
    try {
      await booksApi.createBook(accessToken, {
        title: newTitle.trim(),
        description: newDesc || undefined,
        original_language: newLang || undefined,
      });
      setCreateOpen(false);
      setNewTitle('');
      setNewDesc('');
      setNewLang('');
      await load();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={t('workspace')}
        actions={
          <button
            onClick={() => setCreateOpen(true)}
            className="btn-glow inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground transition-all hover:bg-primary/90"
          >
            <Plus className="h-4 w-4" />
            {t('new_book')}
          </button>
        }
      />

      {error && (
        <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
          {error}
        </div>
      )}

      <FilterToolbar
        search={search}
        onSearchChange={setSearch}
        searchPlaceholder={t('search_placeholder')}
        trailing={
          <div className="flex items-center gap-3">
            {allLanguages.length > 1 && (
              <select
                value={langFilter}
                onChange={(e) => setLangFilter(e.target.value)}
                className="appearance-none rounded-md border bg-background px-3 py-2 pr-8 text-sm focus:outline-none focus:ring-2 focus:ring-ring/40"
              >
                <option value="">All languages</option>
                {allLanguages.map((l) => (
                  <option key={l} value={l}>{l}</option>
                ))}
              </select>
            )}
            <span className="text-xs text-muted-foreground">
              {filteredBooks.length} {filteredBooks.length === 1 ? 'book' : 'books'}
            </span>
          </div>
        }
      />

      {/* Loading */}
      {loading && (
        <div className="space-y-2">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      )}

      {/* Empty state */}
      {!loading && filteredBooks.length === 0 && (
        <EmptyState
          icon={BookOpen}
          title={t('empty.title')}
          description={t('empty.description')}
          variant="primary"
          action={
            <button
              onClick={() => setCreateOpen(true)}
              className="inline-flex items-center gap-2 rounded-md bg-primary px-3.5 py-2 text-sm font-medium text-primary-foreground"
            >
              <Plus className="h-4 w-4" />
              {t('new_book')}
            </button>
          }
        />
      )}

      {/* Book list */}
      {!loading && filteredBooks.length > 0 && (
        <div className="space-y-2">
          {filteredBooks.map((book) => (
            <Link
              key={book.book_id}
              to={`/books/${book.book_id}`}
              className="group flex items-center gap-4 rounded-lg border p-4 transition-all hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-card"
            >
              {/* Cover */}
              <div
                className="flex h-16 w-11 flex-shrink-0 items-end overflow-hidden rounded border border-[hsl(var(--border-hover,25_6%_24%))]"
                style={{
                  background: `linear-gradient(135deg, hsl(${hashToHue(book.book_id)} 30% 12%), hsl(${hashToHue(book.book_id)} 25% 16%))`,
                  boxShadow: 'inset 0 0 20px rgba(0,0,0,0.5)',
                }}
              >
                <span className="p-1 font-serif text-[6px] leading-tight" style={{ color: `hsl(${hashToHue(book.book_id)} 40% 75%)` }}>
                  {book.title.slice(0, 20)}
                </span>
              </div>

              {/* Info */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate font-serif font-medium">{book.title}</span>
                  {book.visibility && <StatusBadge variant={book.visibility} />}
                </div>
                <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                  {book.original_language ? (
                    <LanguageDisplay code={book.original_language} />
                  ) : (
                    <span>{t('card.no_language')}</span>
                  )}
                  <span className="text-border">·</span>
                  <span>{t('card.chapters', { count: book.chapter_count })}</span>
                  {book.updated_at && (
                    <>
                      <span className="text-border">·</span>
                      <span>{new Date(book.updated_at).toLocaleDateString()}</span>
                    </>
                  )}
                </div>
                {book.genre_tags && book.genre_tags.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {book.genre_tags.slice(0, 4).map((g) => (
                      <span key={g} className="rounded-full border border-border bg-secondary px-1.5 py-px text-[9px] font-medium text-muted-foreground">
                        {g}
                      </span>
                    ))}
                    {book.genre_tags.length > 4 && (
                      <span className="rounded-full border border-border bg-secondary px-1.5 py-px text-[9px] font-medium text-muted-foreground">
                        +{book.genre_tags.length - 4}
                      </span>
                    )}
                  </div>
                )}
              </div>

              {/* Translation language dots */}
              {bookLangs[book.book_id] && bookLangs[book.book_id].length > 0 && (
                <div className="flex items-center gap-1" title={`Translated to: ${bookLangs[book.book_id].join(', ')}`}>
                  {bookLangs[book.book_id].map((lang) => (
                    <span
                      key={lang}
                      className="h-2 w-2 rounded-full bg-success"
                      title={lang}
                    />
                  ))}
                </div>
              )}

              <ChevronRight className="h-4 w-4 text-muted-foreground/30 transition-colors group-hover:text-muted-foreground" />
            </Link>
          ))}
        </div>
      )}

      <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />

      {/* Create book dialog */}
      <FormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        title={t('create.title')}
        description={t('create.description')}
        footer={
          <>
            <button
              onClick={() => setCreateOpen(false)}
              className="rounded-md border px-4 py-2 text-sm font-medium transition-colors hover:bg-secondary"
            >
              {t('common.cancel', { ns: 'common' })}
            </button>
            <button
              onClick={() => void handleCreate()}
              disabled={creating || !newTitle.trim()}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:opacity-50"
            >
              {t('create.submit')}
            </button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.book_title')}</label>
            <input
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('create.book_title_placeholder')}
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.language')}</label>
            <input
              value={newLang}
              onChange={(e) => setNewLang(e.target.value)}
              placeholder="ja, en, vi, zh-TW..."
              className="w-full rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
          <div className="space-y-1.5">
            <label className="text-sm font-medium">{t('create.book_description')}</label>
            <textarea
              value={newDesc}
              onChange={(e) => setNewDesc(e.target.value)}
              placeholder={t('create.book_description_placeholder')}
              rows={3}
              className="w-full resize-none rounded-md border bg-background px-3 py-2 text-sm placeholder:text-muted-foreground/50 focus:outline-none focus:ring-2 focus:ring-ring/40"
            />
          </div>
        </div>
      </FormDialog>
    </div>
  );
}
