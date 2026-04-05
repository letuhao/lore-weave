import { useEffect, useState } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { Menu, X, ChevronLeft, ChevronRight, Pencil, Volume2, Sun } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { cn } from '@/lib/utils';
import type { JSONContent } from '@tiptap/react';
import { extractText } from '@/components/editor/TiptapEditor';

/** CJK Unicode ranges: CJK Unified Ideographs, Hiragana, Katakana, Hangul */
const CJK_REGEX = /[\u3000-\u9fff\uac00-\ud7af\uff00-\uffef]/;

function computeReadingStats(blocks: JSONContent[], language?: string) {
  const text = blocks.map((b) => extractText(b)).join(' ');
  const isCJK = CJK_REGEX.test(text) || ['ja', 'zh', 'ko'].includes(language ?? '');

  if (isCJK) {
    // CJK: count characters (excluding spaces/punctuation), ~400 chars/min
    const chars = text.replace(/[\s\p{P}]/gu, '').length;
    const minutes = Math.max(1, Math.round(chars / 400));
    return { count: chars.toLocaleString(), unit: 'chars', minutes };
  }

  // Latin: count words, ~230 wpm
  const words = text.trim() ? text.trim().split(/\s+/).length : 0;
  const minutes = Math.max(1, Math.round(words / 230));
  return { count: words.toLocaleString(), unit: 'words', minutes };
}

export function ReaderPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const navigate = useNavigate();
  const [blocks, setBlocks] = useState<JSONContent[]>([]);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [book, setBook] = useState<Book | null>(null);
  const [tocOpen, setTocOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    Promise.all([
      booksApi.getBook(accessToken, bookId),
      booksApi.getDraft(accessToken, bookId, chapterId),
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
    ]).then(([b, d, chs]) => {
      setBook(b);
      // Extract blocks from Tiptap JSON body
      const body = d.body as JSONContent | null;
      setBlocks(body?.content ?? []);
      setChapter(chs.items.find((c) => c.chapter_id === chapterId) ?? null);
      setChapters(chs.items);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  const currentIdx = chapters.findIndex((c) => c.chapter_id === chapterId);
  const prevCh = currentIdx > 0 ? chapters[currentIdx - 1] : null;
  const nextCh = currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;
  const progress = chapters.length > 0 ? ((currentIdx + 1) / chapters.length) * 100 : 0;
  const chapterLang = chapter?.original_language;
  const stats = computeReadingStats(blocks, chapterLang ?? undefined);

  if (loading) return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">Loading...</div>;

  return (
    <div className="relative flex h-screen flex-col bg-background">
      {/* Progress bar */}
      <div className="fixed left-0 right-0 top-0 z-20 h-0.5 bg-secondary">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      {/* Top bar — gradient fade */}
      <div
        className="fixed left-0 right-0 top-0 z-[19] flex h-12 items-center justify-between px-4"
        style={{ background: 'linear-gradient(hsl(var(--background)), transparent)' }}
      >
        <div className="flex items-center gap-3">
          <button onClick={() => setTocOpen(true)} className="rounded p-1.5 text-muted-foreground hover:bg-secondary">
            <Menu className="h-4 w-4" />
          </button>
          <span className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{book?.title}</span>
            <span className="mx-1.5 text-border">/</span>
            Chapter {currentIdx + 1} of {chapters.length}
          </span>
        </div>
        <div className="flex gap-1">
          {/* TTS placeholder — wired in Phase 8D */}
          <button className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Read aloud (coming soon)" disabled>
            <Volume2 className="h-4 w-4" />
          </button>
          {/* Theme placeholder — wired in Phase 8B */}
          <button className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Reading theme (coming soon)" disabled>
            <Sun className="h-4 w-4" />
          </button>
          {accessToken && (
            <Link to={`/books/${bookId}/chapters/${chapterId}/edit`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Edit this chapter">
              <Pencil className="h-4 w-4" />
            </Link>
          )}
          <Link to={`/books/${bookId}`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Back to book">
            <X className="h-4 w-4" />
          </Link>
        </div>
      </div>

      {/* TOC overlay */}
      {tocOpen && (
        <>
          <div className="fixed inset-0 z-30 bg-black/50" onClick={() => setTocOpen(false)} />
          <div className="fixed bottom-0 left-0 top-0 z-[31] w-80 border-r bg-card shadow-xl flex flex-col">
            {/* TOC header */}
            <div className="flex items-center justify-between border-b p-4">
              <div>
                <h2 className="font-serif text-sm font-semibold">{book?.title}</h2>
                <p className="text-[11px] text-muted-foreground">
                  {book?.original_language && <>{book.original_language} &middot; </>}
                  {chapters.length} chapters
                </p>
              </div>
              <button onClick={() => setTocOpen(false)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Reading progress bar */}
            <div className="flex items-center gap-2.5 border-b px-4 py-3">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-secondary">
                <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${progress}%` }} />
              </div>
              <span className="flex-shrink-0 font-mono text-[10px] text-muted-foreground">{currentIdx + 1} / {chapters.length}</span>
            </div>

            {/* Chapter list */}
            <div className="flex-1 overflow-y-auto">
              {chapters.map((ch, i) => {
                const isCurrent = ch.chapter_id === chapterId;
                const isRead = i < currentIdx;
                return (
                  <button
                    key={ch.chapter_id}
                    onClick={() => { navigate(`/books/${bookId}/chapters/${ch.chapter_id}/read`); setTocOpen(false); }}
                    className={cn(
                      'flex w-full items-center gap-3 border-b px-4 py-2.5 text-left text-xs transition-colors',
                      isCurrent
                        ? 'border-l-2 border-l-primary bg-primary/10 text-primary font-medium'
                        : 'border-l-2 border-l-transparent text-muted-foreground hover:bg-card hover:text-foreground',
                    )}
                  >
                    <span className="w-5 flex-shrink-0 text-right font-mono text-[11px]">{i + 1}</span>
                    <span className="flex-1">{ch.title || ch.original_filename}</span>
                    {isCurrent && <span className="text-[9px] text-primary">reading</span>}
                    {isRead && (
                      <svg className="h-3 w-3 flex-shrink-0 text-success" fill="none" stroke="currentColor" strokeWidth={2.5} viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" /></svg>
                    )}
                  </button>
                );
              })}
            </div>
          </div>
        </>
      )}

      {/* Reading area */}
      <div className="flex flex-1 justify-center overflow-y-auto" style={{ padding: '64px 24px 120px' }}>
        <article style={{ maxWidth: 'var(--reader-width, 680px)', width: '100%' }}>

          {/* Chapter header */}
          <div className="chapter-header">
            <p className="ch-label">Chapter {currentIdx + 1}</p>
            {(chapter?.title || chapter?.original_filename) && (
              <h1 className="ch-title">{chapter?.title || chapter?.original_filename}</h1>
            )}
            <div className="ch-divider" />
            <div className="ch-meta">
              <span>{stats.count} {stats.unit}</span>
              <span style={{ color: 'var(--border)' }}>&middot;</span>
              <span>~{stats.minutes} min read</span>
              {chapterLang && (
                <>
                  <span style={{ color: 'var(--border)' }}>&middot;</span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: 3 }}>
                    <span className="lang-badge">{chapterLang}</span>
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Chapter content — ContentRenderer */}
          {blocks.length > 0 ? (
            <ContentRenderer blocks={blocks} />
          ) : (
            <p className="text-center font-serif text-muted-foreground italic">
              Empty chapter — nothing written yet.
            </p>
          )}

          {/* End of chapter marker */}
          <div className="chapter-end">
            <p>End of Chapter {currentIdx + 1}</p>
          </div>
        </article>
      </div>

      {/* Bottom nav — gradient fade */}
      <div
        className="fixed bottom-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-3"
        style={{ background: 'linear-gradient(transparent, hsl(var(--background)))' }}
      >
        {prevCh ? (
          <Link to={`/books/${bookId}/chapters/${prevCh.chapter_id}/read`} className="inline-flex items-center gap-2 rounded-lg border bg-card px-4 py-2 text-xs transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-[hsl(var(--card-hover,25_7%_14%))]">
            <ChevronLeft className="h-3.5 w-3.5" /> {prevCh.title || `Ch. ${currentIdx}`}
          </Link>
        ) : <div />}
        <span className="text-[11px] text-muted-foreground">
          Chapter {currentIdx + 1} of {chapters.length} &middot; {Math.round(progress)}% complete
        </span>
        {nextCh ? (
          <Link to={`/books/${bookId}/chapters/${nextCh.chapter_id}/read`} className="btn-glow inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-all hover:bg-primary/90">
            {nextCh.title || `Ch. ${currentIdx + 2}`} <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        ) : <div />}
      </div>
    </div>
  );
}
