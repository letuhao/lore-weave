import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import { Menu, X, ChevronLeft, ChevronRight, Pencil, Volume2, Sun } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import { versionsApi } from '@/features/translation/api';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { TOCSidebar, type LanguageOption } from '@/components/reader/TOCSidebar';
import type { JSONContent } from '@tiptap/react';
import { extractText } from '@/lib/tiptap-utils';

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
  const { accessToken, user } = useAuth();
  const navigate = useNavigate();
  const [originalBlocks, setOriginalBlocks] = useState<JSONContent[]>([]);
  const [blocks, setBlocks] = useState<JSONContent[]>([]);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [chapters, setChapters] = useState<Chapter[]>([]);
  const [book, setBook] = useState<Book | null>(null);
  const [tocOpen, setTocOpen] = useState(false);
  const [loading, setLoading] = useState(true);

  // Language state
  const [languages, setLanguages] = useState<LanguageOption[]>([]);
  const [activeLanguage, setActiveLanguage] = useState('');
  // Map: language code → active translation version ID
  const [langVersionMap, setLangVersionMap] = useState<Record<string, string>>({});
  const [langLoading, setLangLoading] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!accessToken) return;
    setLoading(true);
    Promise.all([
      booksApi.getBook(accessToken, bookId),
      booksApi.getDraft(accessToken, bookId, chapterId),
      booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
      versionsApi.listChapterVersions(accessToken, chapterId).catch(() => null),
    ]).then(([b, d, chs, versions]) => {
      setBook(b);
      const body = d.body as JSONContent | null;
      const origBlocks = body?.content ?? [];
      setOriginalBlocks(origBlocks);
      setBlocks(origBlocks);
      setChapter(chs.items.find((c) => c.chapter_id === chapterId) ?? null);
      setChapters(chs.items);

      // Build language options
      const origLang = b.original_language ?? 'original';
      const langs: LanguageOption[] = [{ code: origLang, isOriginal: true }];
      const versionMap: Record<string, string> = {};
      if (versions?.languages) {
        for (const g of versions.languages) {
          if (g.target_language !== origLang) {
            langs.push({ code: g.target_language, isOriginal: false });
          }
          if (g.active_id) {
            versionMap[g.target_language] = g.active_id;
          }
        }
      }
      setLanguages(langs);
      setLangVersionMap(versionMap);
      setActiveLanguage(origLang);
    }).catch(() => {}).finally(() => setLoading(false));
  }, [accessToken, bookId, chapterId]);

  /** Convert flat translated text to paragraph blocks for ContentRenderer */
  const textToBlocks = useCallback((text: string): JSONContent[] => {
    return text.split(/\n\n+/).filter(Boolean).map((p) => ({
      type: 'paragraph',
      content: [{ type: 'text', text: p }],
    }));
  }, []);

  /** Switch reading language */
  const handleLanguageChange = useCallback(async (lang: string) => {
    setActiveLanguage(lang);
    const origLang = book?.original_language ?? 'original';
    if (lang === origLang) {
      setBlocks(originalBlocks);
      return;
    }
    const versionId = langVersionMap[lang];
    if (!versionId || !accessToken) return;
    setLangLoading(true);
    try {
      const version = await versionsApi.getChapterVersion(accessToken, chapterId, versionId);
      if (version.translated_body) {
        setBlocks(textToBlocks(version.translated_body));
      }
    } catch {
      setBlocks(originalBlocks);
      setActiveLanguage(origLang);
    } finally {
      setLangLoading(false);
    }
  }, [book, originalBlocks, langVersionMap, accessToken, chapterId, textToBlocks]);

  const currentIdx = chapters.findIndex((c) => c.chapter_id === chapterId);
  const prevCh = currentIdx > 0 ? chapters[currentIdx - 1] : null;
  const nextCh = currentIdx < chapters.length - 1 ? chapters[currentIdx + 1] : null;
  const progress = chapters.length > 0 ? ((currentIdx + 1) / chapters.length) * 100 : 0;
  const chapterLang = chapter?.original_language;
  const stats = useMemo(() => computeReadingStats(blocks, chapterLang ?? undefined), [blocks, chapterLang]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.key) {
        case 'Escape':
          if (tocOpen) setTocOpen(false);
          break;
        case 't':
        case 'T':
          setTocOpen((v) => !v);
          break;
        case 'ArrowLeft':
        case 'PageUp':
          if (!tocOpen && prevCh) navigate(`/books/${bookId}/chapters/${prevCh.chapter_id}/read`);
          break;
        case 'ArrowRight':
        case 'PageDown':
          if (!tocOpen && nextCh) navigate(`/books/${bookId}/chapters/${nextCh.chapter_id}/read`);
          break;
        case 'Home':
          if (!tocOpen) scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
          break;
        case 'End':
          if (!tocOpen) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
          break;
        default:
          return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [tocOpen, prevCh, nextCh, bookId, navigate]);

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
          {accessToken && user && book?.owner_user_id === user.user_id && (
            <Link to={`/books/${bookId}/chapters/${chapterId}/edit`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Edit this chapter">
              <Pencil className="h-4 w-4" />
            </Link>
          )}
          <Link to={`/books/${bookId}`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title="Back to book">
            <X className="h-4 w-4" />
          </Link>
        </div>
      </div>

      {/* TOC sidebar */}
      <TOCSidebar
        open={tocOpen}
        onClose={() => setTocOpen(false)}
        book={book}
        chapters={chapters}
        currentChapterId={chapterId}
        currentIdx={currentIdx}
        progress={progress}
        bookId={bookId}
        languages={languages}
        activeLanguage={activeLanguage}
        onLanguageChange={handleLanguageChange}
      />

      {/* Reading area */}
      <div ref={scrollRef} className="flex flex-1 justify-center overflow-y-auto" style={{ padding: '64px 24px 120px' }}>
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
          {langLoading && (
            <div className="mb-6 text-center text-xs text-muted-foreground animate-pulse">Loading translation...</div>
          )}
          {blocks.length > 0 ? (
            <ContentRenderer blocks={blocks} className={langLoading ? 'opacity-50 transition-opacity' : ''} />
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
