import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, ArrowRight, BookOpen, ChevronRight, Share2, X } from 'lucide-react';
import { toast } from 'sonner';
import { booksApi } from '@/features/books/api';
import { Pagination } from '@/components/shared/Pagination';

// ── Types ───────────────────────────────────────────────────────────────────

type SharedBook = {
  book_id: string;
  title: string;
  description?: string | null;
  original_language?: string | null;
  summary_excerpt?: string | null;
  has_cover?: boolean;
  cover_url?: string | null;
  chapter_count?: number;
  visibility?: string;
};

type SharedChapter = {
  chapter_id: string;
  title?: string | null;
  sort_order: number;
  original_language: string;
  word_count_estimate?: number;
};

// ── Cover gradient ──────────────────────────────────────────────────────────

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

export function SharedBookPage() {
  const { accessToken = '' } = useParams();
  const [book, setBook] = useState<SharedBook | null>(null);
  const [chapters, setChapters] = useState<SharedChapter[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [limit] = useState(10);
  const [offset, setOffset] = useState(0);

  // Inline reader state
  const [readingChapter, setReadingChapter] = useState<{ chapter_id: string; title: string; body: string } | null>(null);
  const [loadingChapter, setLoadingChapter] = useState(false);

  // Fetch book
  useEffect(() => {
    if (!accessToken) return;
    setError('');
    setLoading(true);
    let mounted = true;
    booksApi.getUnlisted(accessToken)
      .then((data) => { if (mounted) setBook(data as SharedBook); })
      .catch((e) => { if (mounted) setError((e as Error).message || 'Shared link not found or expired'); })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [accessToken]);

  // Fetch chapters
  useEffect(() => {
    if (!accessToken) return;
    // Close inline reader when pagination changes — chapter list is different
    setReadingChapter(null);
    let mounted = true;
    booksApi.listUnlistedChapters(accessToken, { limit, offset })
      .then((res) => {
        if (mounted) { setChapters(res.items ?? []); setTotal(res.total ?? 0); }
      })
      .catch(() => { if (mounted) setChapters([]); });
    return () => { mounted = false; };
  }, [accessToken, limit, offset]);

  // Read a chapter inline
  function handleReadChapter(ch: SharedChapter) {
    setLoadingChapter(true);
    booksApi.getUnlistedChapter(accessToken, ch.chapter_id)
      .then((data) => {
        const content = data.text_content || (typeof data.body === 'string' ? data.body : JSON.stringify(data.body));
        setReadingChapter({ chapter_id: ch.chapter_id, title: ch.title || 'Untitled', body: content });
      })
      .catch((e) => {
        toast.error(`Failed to load chapter: ${(e as Error).message}`);
        setReadingChapter(null);
      })
      .finally(() => setLoadingChapter(false));
  }

  // ── Loading ───────────────────────────────────────────────────────────────

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

  // ── Error ─────────────────────────────────────────────────────────────────

  if (error || !book) {
    return (
      <div className="mx-auto max-w-[1000px] px-8 py-16 text-center">
        <p className="text-sm text-destructive">{error || 'This shared link is invalid or has expired.'}</p>
        <Link to="/browse" className="mt-4 inline-block text-sm text-accent hover:underline">
          Browse public books instead
        </Link>
      </div>
    );
  }

  const firstChapterId = chapters.length > 0 ? chapters[0].chapter_id : null;
  const gradient = hashGradient(book.book_id);

  // ── Inline Reader ─────────────────────────────────────────────────────────

  if (readingChapter) {
    // Find current index for prev/next navigation (may be -1 if chapter not on current page)
    const currentIdx = chapters.findIndex((c) => c.chapter_id === readingChapter.chapter_id);
    const prevCh = currentIdx > 0 ? chapters[currentIdx - 1] : null;
    const nextCh = currentIdx >= 0 && currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;

    return (
      <div className="mx-auto max-w-[800px] px-8 py-6">
        {/* Reader header */}
        <div className="mb-6 flex items-center justify-between">
          <button
            onClick={() => setReadingChapter(null)}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            <ArrowLeft className="h-4 w-4" />
            Back to chapters
          </button>
          <span className="text-xs text-muted-foreground">{book.title}</span>
        </div>

        {/* Chapter title */}
        <h1 className="font-serif text-2xl font-semibold mb-6">{readingChapter.title}</h1>

        {/* Chapter content */}
        <div className="prose prose-sm prose-invert max-w-none whitespace-pre-wrap font-serif text-[15px] leading-[1.9] text-foreground/90">
          {readingChapter.body}
        </div>

        {/* Prev / Next navigation */}
        <div className="mt-10 flex items-center justify-between border-t border-border pt-6">
          {prevCh ? (
            <button
              onClick={() => handleReadChapter(prevCh)}
              disabled={loadingChapter}
              className="flex items-center gap-1.5 text-sm text-accent hover:underline disabled:opacity-50"
            >
              <ArrowLeft className="h-3.5 w-3.5" />
              {prevCh.title || `Ch. ${prevCh.sort_order}`}
            </button>
          ) : <div />}
          {nextCh ? (
            <button
              onClick={() => handleReadChapter(nextCh)}
              disabled={loadingChapter}
              className="flex items-center gap-1.5 text-sm text-accent hover:underline disabled:opacity-50"
            >
              {nextCh.title || `Ch. ${nextCh.sort_order}`}
              <ArrowRight className="h-3.5 w-3.5" />
            </button>
          ) : <div />}
        </div>
      </div>
    );
  }

  // ── Book Detail (same layout as PublicBookDetailPage) ─────────────────────

  return (
    <div className="mx-auto max-w-[1000px] px-8 py-6">

      {/* Shared link indicator */}
      <div className="mb-6 flex items-center gap-2 rounded-lg border border-accent/20 bg-accent/5 px-4 py-2.5">
        <Share2 className="h-4 w-4 text-accent" />
        <p className="text-sm text-accent">
          You're viewing a shared link. This book is not publicly listed.
        </p>
      </div>

      {/* Hero: Cover + Info */}
      <div className="flex gap-8">
        <div className="shrink-0">
          <div className={`relative h-[300px] w-[200px] overflow-hidden rounded-xl border border-border bg-gradient-to-br ${gradient}`}>
            {book.has_cover && book.cover_url ? (
              <img src={book.cover_url} alt={book.title} className="absolute inset-0 h-full w-full object-cover" />
            ) : null}
            <div className="absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/50 to-transparent" />
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-accent/20 px-2 py-0.5 text-[10px] font-medium text-accent">Unlisted</span>
          </div>

          <h1 className="font-serif text-2xl font-semibold leading-tight">{book.title}</h1>

          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-muted-foreground">
            <span>{book.chapter_count ?? 0} chapters</span>
            {book.original_language && (
              <>
                <span>&middot;</span>
                <span className="rounded bg-secondary px-1.5 py-0.5 font-mono text-[11px]">{book.original_language}</span>
              </>
            )}
          </div>

          {(book.description || book.summary_excerpt) && (
            <p className="mt-4 text-sm leading-relaxed text-foreground/85">
              {book.description || book.summary_excerpt}
            </p>
          )}

          <div className="mt-5 flex gap-2">
            {firstChapterId ? (
              <button
                onClick={() => handleReadChapter(chapters[0])}
                disabled={loadingChapter}
                className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-4 py-2 text-sm font-medium text-white transition-colors hover:brightness-110 disabled:opacity-50"
              >
                <BookOpen className="h-4 w-4" />
                {loadingChapter ? 'Loading...' : 'Start Reading'}
              </button>
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
              Copy Link
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
              <button
                key={ch.chapter_id}
                onClick={() => handleReadChapter(ch)}
                disabled={loadingChapter}
                className="flex w-full items-center border-b border-border px-4 py-3 text-left transition-colors last:border-b-0 hover:bg-secondary/30 disabled:opacity-50"
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
              </button>
            ))}

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
    </div>
  );
}
