import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowRight, BookOpen, ChevronRight, Heart, Share2 } from 'lucide-react';
import { toast } from 'sonner';
import { booksApi } from '@/features/books/api';
import { Pagination } from '@/components/shared/Pagination';

// ── Types ───────────────────────────────────────────────────────────────────

type CatalogBook = {
  book_id: string;
  owner_user_id: string;
  title: string;
  description?: string | null;
  original_language?: string | null;
  summary_excerpt?: string | null;
  has_cover?: boolean;
  cover_url?: string | null;
  genre_tags?: string[];
  chapter_count: number;
  visibility: string;
  created_at?: string | null;
  available_languages?: Array<{ language: string; chapter_count: number }> | null;
};

type CatalogChapter = {
  chapter_id: string;
  title?: string | null;
  sort_order: number;
  original_language: string;
  word_count_estimate?: number;
  draft_updated_at?: string | null;
};

// ── Cover gradient (reused from BookCard) ────────────────────────────────────

const GRADIENTS = [
  'from-[#2d1740] to-[#1a1030]',
  'from-[#162824] to-[#0a1a14]',
  'from-[#302018] to-[#1a100c]',
  'from-[#1a1828] to-[#100e20]',
  'from-[#1c2830] to-[#0e1820]',
];

function hashGradient(id: string): string {
  let h = 0;
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0;
  return GRADIENTS[Math.abs(h) % GRADIENTS.length];
}

// ── Page ────────────────────────────────────────────────────────────────────

export function PublicBookDetailPage() {
  const { bookId = '' } = useParams();
  const [book, setBook] = useState<CatalogBook | null>(null);
  const [chapters, setChapters] = useState<CatalogChapter[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);

  // Fetch book detail
  useEffect(() => {
    if (!bookId) return;
    setError('');
    setLoading(true);
    let mounted = true;
    booksApi.getCatalogBook(bookId)
      .then((data) => { if (mounted) setBook(data as CatalogBook); })
      .catch((e) => { if (mounted) setError((e as Error).message || 'Book not found'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [bookId]);

  // Fetch chapters (paginated)
  useEffect(() => {
    if (!bookId) return;
    let mounted = true;
    booksApi.listCatalogChapters(bookId, { limit, offset })
      .then((res) => {
        if (mounted) { setChapters(res.items ?? []); setTotal(res.total ?? 0); }
      })
      .catch(() => { if (mounted) { setChapters([]); toast.error('Failed to load chapters'); } });
    return () => { mounted = false; };
  }, [bookId, limit, offset]);

  // ── Loading skeleton ──────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="mx-auto max-w-[1000px] px-8 py-8">
        <div className="flex gap-8">
          <div className="h-[300px] w-[200px] shrink-0 animate-pulse rounded-xl bg-card" />
          <div className="flex-1 space-y-4">
            <div className="h-6 w-48 animate-pulse rounded bg-card" />
            <div className="h-4 w-32 animate-pulse rounded bg-card" />
            <div className="h-20 w-full animate-pulse rounded bg-card" />
          </div>
        </div>
      </div>
    );
  }

  // ── Error / Not Found ─────────────────────────────────────────────────────

  if (error || !book) {
    return (
      <div className="mx-auto max-w-[1000px] px-8 py-16 text-center">
        <p className="text-sm text-destructive">{error || 'Book not found'}</p>
        <Link to="/browse" className="mt-4 inline-block text-sm text-accent hover:underline">
          Back to Browse
        </Link>
      </div>
    );
  }

  const firstChapterId = chapters.length > 0 ? chapters[0].chapter_id : null;
  const gradient = hashGradient(book.book_id);

  return (
    <div className="mx-auto max-w-[1000px] px-8 py-6">

      {/* Breadcrumb */}
      <nav className="mb-6 flex items-center gap-1.5 text-xs text-muted-foreground">
        <Link to="/browse" className="text-accent hover:underline">Browse</Link>
        <ChevronRight className="h-3 w-3" />
        <span className="text-foreground">{book.title}</span>
      </nav>

      {/* Hero: Cover + Info */}
      <div className="flex gap-8">
        {/* Cover */}
        <div className="shrink-0">
          <div className={`relative h-[300px] w-[200px] overflow-hidden rounded-xl border border-border bg-gradient-to-br ${gradient}`}>
            {book.has_cover && book.cover_url ? (
              <img src={book.cover_url} alt={book.title} className="absolute inset-0 h-full w-full object-cover" />
            ) : null}
            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/50 to-transparent" />
          </div>
        </div>

        {/* Info */}
        <div className="min-w-0 flex-1">
          {/* Badges */}
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-[#3dba6a] px-2 py-0.5 text-[10px] font-medium text-white">Public</span>
            {book.genre_tags && book.genre_tags.length > 0 && book.genre_tags.map((g) => (
              <span key={g} className="rounded-full border border-border bg-secondary px-2 py-0.5 text-[10px] font-medium text-muted-foreground">
                {g}
              </span>
            ))}
          </div>

          <h1 className="font-serif text-2xl font-semibold leading-tight">{book.title}</h1>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
            <span>{book.chapter_count} chapters</span>
            {book.original_language && (
              <>
                <span>&middot;</span>
                <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px]">{book.original_language}</span>
              </>
            )}
            {book.created_at && (
              <>
                <span>&middot;</span>
                <span>{new Date(book.created_at).toLocaleDateString()}</span>
              </>
            )}
          </div>

          {/* Description */}
          {(book.description || book.summary_excerpt) && (
            <p className="mt-4 text-sm leading-relaxed text-foreground/85">
              {book.description || book.summary_excerpt}
            </p>
          )}

          {/* Available languages */}
          {book.available_languages && book.available_languages.length > 0 && (
            <div className="mt-4">
              <p className="mb-1.5 text-[11px] font-medium text-muted-foreground">Available languages</p>
              <div className="flex flex-wrap gap-1.5">
                {book.original_language && (
                  <span className="rounded border border-accent/20 bg-accent/5 px-2 py-0.5 font-mono text-[10px] font-medium text-accent">
                    {book.original_language} &middot; Original
                  </span>
                )}
                {book.available_languages.map((l) => (
                  <span key={l.language} className="rounded border border-border bg-secondary px-2 py-0.5 font-mono text-[10px] text-muted-foreground">
                    {l.language} &middot; {l.chapter_count}/{book.chapter_count}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="mt-5 flex gap-2">
            {firstChapterId ? (
              <Link
                to={`/read/${book.book_id}/${firstChapterId}`}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:brightness-110"
              >
                <BookOpen className="h-4 w-4" />
                Start Reading
              </Link>
            ) : (
              <button disabled className="inline-flex items-center gap-1.5 rounded-lg bg-accent/50 px-4 py-2 text-sm font-medium text-white/60 cursor-not-allowed">
                <BookOpen className="h-4 w-4" />
                No chapters yet
              </button>
            )}
            <button
              onClick={() => { navigator.clipboard.writeText(window.location.href).then(() => toast.success('Link copied')).catch(() => toast.error('Failed to copy')); }}
              className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-sm text-foreground transition-colors hover:bg-secondary"
            >
              <Share2 className="h-3.5 w-3.5" />
              Share
            </button>
          </div>
        </div>
      </div>

      {/* Chapter List */}
      <div className="mt-8">
        <h2 className="mb-4 text-base font-semibold">Chapters</h2>

        {chapters.length === 0 ? (
          <div className="rounded-lg border border-border bg-card p-8 text-center text-sm text-muted-foreground">
            No chapters available.
          </div>
        ) : (
          <div className="overflow-hidden rounded-lg border border-border bg-card">
            {chapters.map((ch) => (
              <Link
                key={ch.chapter_id}
                to={`/read/${book.book_id}/${ch.chapter_id}`}
                className="flex items-center border-b border-border px-4 py-3 transition-colors last:border-b-0 hover:bg-secondary/30"
              >
                <span className="w-9 shrink-0 text-center text-xs font-medium text-muted-foreground">
                  {ch.sort_order}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13px] font-medium">{ch.title || 'Untitled'}</p>
                  {ch.word_count_estimate != null && ch.word_count_estimate > 0 && (
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {ch.word_count_estimate.toLocaleString()} words
                    </p>
                  )}
                </div>
                <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground/40" />
              </Link>
            ))}

            {/* Pagination footer */}
            {total > limit && (
              <div className="border-t border-border px-4 py-3">
                <p className="mb-2 text-center text-[11px] text-muted-foreground">
                  Showing {offset + 1}–{Math.min(offset + limit, total)} of {total} chapters
                </p>
                <div className="flex justify-center">
                  <Pagination total={total} limit={limit} offset={offset} onChange={setOffset} />
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Stats footer */}
      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Chapters</p>
          <p className="mt-1 font-mono text-lg font-semibold">{book.chapter_count}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Languages</p>
          <p className="mt-1 font-mono text-lg font-semibold">{(book.available_languages?.length ?? 0) + 1}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Original</p>
          <p className="mt-1 text-sm font-medium">{book.original_language || 'N/A'}</p>
        </div>
        <div className="rounded-lg border border-border bg-card p-3">
          <p className="text-[10px] uppercase tracking-wider text-muted-foreground">Published</p>
          <p className="mt-1 text-sm font-medium">
            {book.created_at ? new Date(book.created_at).toLocaleDateString() : 'N/A'}
          </p>
        </div>
      </div>
    </div>
  );
}
