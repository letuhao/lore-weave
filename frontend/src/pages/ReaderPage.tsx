import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { Menu, X, ChevronLeft, ChevronRight, Pencil, Volume2, Sun, BookOpen } from 'lucide-react';
import { useAuth } from '@/auth';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { TOCSidebar } from '@/components/reader/TOCSidebar';
import { ThemeCustomizer } from '@/components/reader/ThemeCustomizer';
import { TTSBar } from '@/components/reader/TTSBar';
import { TTSSettings } from '@/components/reader/TTSSettings';
import { useReaderTheme } from '@/providers/ThemeProvider';
import { useTTSState, useTTSControls } from '@/hooks/useTTS';
import { useReadingTracker } from '@/hooks/useReadingTracker';
import { useBlockScroll } from '@/hooks/useBlockScroll';
import { useTTSShortcuts } from '@/hooks/useTTSShortcuts';
import { extractSpeakableBlocks } from '@/lib/audio-utils';
import { BookAssistantDock } from '@/features/chat/BookAssistantDock';
import { LoreSeekerPanel } from '@/features/books/components/LoreSeekerPanel';
import { useBookReaderContent, computeReadingStats } from '@/features/books/hooks/useBookReaderContent';

export function ReaderPage() {
  const { t } = useTranslation('reader');
  const { bookId = '', chapterId = '' } = useParams();
  // raw-search jump-to-source: ?block=N scrolls to that block once content renders.
  const [searchParams] = useSearchParams();
  const jumpBlock = searchParams.get('block');
  const { accessToken, user } = useAuth();
  // GA4-style reading tracker — zero re-renders, flushes via sendBeacon
  const sentinelRef = useReadingTracker({ bookId, chapterId, accessToken });
  const navigate = useNavigate();
  const { cssVars: readerCssVars, theme: readerTheme } = useReaderTheme();

  // C3 — content-bootstrapping (book/chapters/chapter/blocks/languages/readProgress/loading)
  // extracted into useBookReaderContent() (docs/specs/2026-07-01-writing-studio/
  // 14_utility_panels.md Phase C3) so this page and the studio `book-reader` dock panel
  // (BookReaderPanel) share one fetch/state implementation instead of forking it.
  const {
    book,
    chapters,
    chapter,
    blocks,
    languages,
    activeLanguage,
    langLoading,
    readProgress,
    loading,
    handleLanguageChange,
    currentIdx,
    prevCh,
    nextCh,
    progress,
  } = useBookReaderContent(bookId, chapterId);

  // UI-only toggle state — stays page-local (Tier-1), not hoisted into the shared hook.
  const [tocOpen, setTocOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const [ttsSettingsOpen, setTtsSettingsOpen] = useState(false);
  const [showIndices, setShowIndices] = useState(() => localStorage.getItem('lw_reader_indices') === 'true');
  const [loreOpen, setLoreOpen] = useState(false); // W11 lore-seeker slide-over
  const [autoNextEnabled, setAutoNextEnabled] = useState(() => localStorage.getItem('lw_reader_auto_next') !== 'false');
  const [autoScrollTTS, setAutoScrollTTS] = useState(() => localStorage.getItem('lw_reader_tts_scroll') !== 'false');
  const [autoNextCountdown, setAutoNextCountdown] = useState<number | null>(null);
  const chapterEndRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  // TTS playback
  const ttsState = useTTSState();
  const ttsControls = useTTSControls();
  useBlockScroll(scrollRef, autoScrollTTS);
  useTTSShortcuts();

  // Raw-search jump-to-source: once the chapter content has rendered, scroll the
  // targeted block to centre (reuses ContentRenderer's `data-block-id="block-N"`,
  // the same hook TTS auto-scroll uses; the reader renders all blocks, no
  // virtualization). blockIndex matches the BE's lexical hit — both index the
  // top-level Tiptap content array. (A translation view that merges/splits blocks
  // could drift; `?.scrollIntoView` no-ops if the index isn't present.)
  useEffect(() => {
    if (!jumpBlock || loading || blocks.length === 0) return;
    const timer = window.setTimeout(() => {
      document
        .querySelector(`[data-block-id="block-${jumpBlock}"]`)
        ?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 150);
    return () => window.clearTimeout(timer);
  }, [jumpBlock, loading, blocks.length]);

  const handleStartTTS = useCallback(() => {
    if (ttsState.status !== 'idle') {
      ttsControls.stop();
    } else {
      ttsControls.start(blocks);
    }
  }, [blocks, ttsState.status, ttsControls]);

  const handleBlockClick = useCallback((blockId: string) => {
    if (ttsState.status !== 'idle') {
      ttsControls.seekBlock(blockId);
    }
  }, [ttsState.status, ttsControls]);

  // Get active block text for TTSBar preview
  const activeBlockText = useMemo(() => {
    if (!ttsState.activeBlockId) return '';
    const speakable = extractSpeakableBlocks(blocks);
    const active = speakable.find((b) => b.blockId === ttsState.activeBlockId);
    return active?.text || active?.subtitle || '';
  }, [blocks, ttsState.activeBlockId]);

  const chapterLang = chapter?.original_language;
  const stats = useMemo(() => computeReadingStats(blocks, chapterLang ?? undefined), [blocks, chapterLang]);

  const anyOverlayOpen = tocOpen || themeOpen;

  // Auto-load next chapter when reaching end
  useEffect(() => {
    if (!autoNextEnabled || !nextCh || !chapterEndRef.current || !scrollRef.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setAutoNextCountdown(5);
        } else {
          setAutoNextCountdown(null);
        }
      },
      { root: scrollRef.current, threshold: 0.5 },
    );
    observer.observe(chapterEndRef.current);
    return () => observer.disconnect();
  }, [autoNextEnabled, nextCh, loading]);

  // Reset countdown when chapter changes (prevents stale navigation)
  useEffect(() => {
    setAutoNextCountdown(null);
  }, [chapterId]);

  // Countdown timer for auto-next
  useEffect(() => {
    if (autoNextCountdown === null || !nextCh) return;
    if (autoNextCountdown <= 0) {
      navigate(`/books/${bookId}/chapters/${nextCh.chapter_id}/read`);
      return;
    }
    const timer = setTimeout(() => setAutoNextCountdown((c) => (c !== null ? c - 1 : null)), 1000);
    return () => clearTimeout(timer);
  }, [autoNextCountdown, nextCh, bookId, navigate]);

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      // Ignore when typing in inputs
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      switch (e.key) {
        case 'Escape':
          if (themeOpen) setThemeOpen(false);
          else if (tocOpen) setTocOpen(false);
          break;
        case 't':
        case 'T':
          if (themeOpen) setThemeOpen(false);
          setTocOpen((v) => !v);
          break;
        case 'ArrowLeft':
        case 'PageUp':
          if (!anyOverlayOpen && prevCh) navigate(`/books/${bookId}/chapters/${prevCh.chapter_id}/read`);
          break;
        case 'ArrowRight':
        case 'PageDown':
          if (!anyOverlayOpen && nextCh) navigate(`/books/${bookId}/chapters/${nextCh.chapter_id}/read`);
          break;
        case 'Home':
          if (!anyOverlayOpen) scrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' });
          break;
        case 'End':
          if (!anyOverlayOpen) scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
          break;
        default:
          return;
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [tocOpen, themeOpen, anyOverlayOpen, prevCh, nextCh, bookId, navigate]);

  if (loading) return <div className="flex h-screen items-center justify-center text-sm text-muted-foreground">{t('loading')}</div>;

  return (
    <div className="relative flex h-screen flex-col" style={{ background: readerTheme.bg }}>
      {/* Progress bar */}
      <div className="fixed left-0 right-0 top-0 z-20 h-0.5 bg-secondary">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      {/* Top bar — semi-opaque card bg for readability on any reader theme */}
      <div
        className="fixed left-0 right-0 top-0 z-[19] flex h-12 items-center justify-between border-b border-border/30 px-4"
        style={{ background: 'hsl(var(--card) / 0.85)', backdropFilter: 'blur(8px)' }}
      >
        <div className="flex items-center gap-3">
          <button onClick={() => { setTocOpen(true); setThemeOpen(false); }} className="rounded p-1.5 text-muted-foreground hover:bg-secondary">
            <Menu className="h-4 w-4" />
          </button>
          <span className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">{book?.title}</span>
            <span className="mx-1.5 text-border">/</span>
            {t('chapter_of', { current: currentIdx + 1, total: chapters.length })}
          </span>
        </div>
        <div className="flex gap-1">
          {/* TTS toggle */}
          <button
            onClick={handleStartTTS}
            className={`rounded p-1.5 transition-colors ${ttsState.status !== 'idle' ? 'bg-purple-500/15 text-purple-400' : 'text-muted-foreground hover:bg-secondary'}`}
            title={ttsState.status !== 'idle' ? t('stop_reading') : t('read_aloud')}
          >
            <Volume2 className="h-4 w-4" />
          </button>
          {/* W11 lore-seeker toggle — "the lore so far", spoiler-windowed to this chapter. */}
          <button
            onClick={() => { setLoreOpen((v) => !v); setThemeOpen(false); setTocOpen(false); }}
            data-testid="lore-toggle"
            className={`rounded p-1.5 transition-colors ${loreOpen ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary'}`}
            title={t('lore.heading', { defaultValue: 'Lore so far' })}
          >
            <BookOpen className="h-4 w-4" />
          </button>
          {/* Theme customizer toggle */}
          <button onClick={() => { setThemeOpen((v) => !v); setTocOpen(false); }} className={`rounded p-1.5 transition-colors ${themeOpen ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary'}`} title={t('reading_theme')}>
            <Sun className="h-4 w-4" />
          </button>
          {accessToken && user && book?.owner_user_id === user.user_id && (
            <Link to={`/books/${bookId}/chapters/${chapterId}/edit`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title={t('edit_chapter')}>
              <Pencil className="h-4 w-4" />
            </Link>
          )}
          <Link to={`/books/${bookId}`} className="rounded p-1.5 text-muted-foreground hover:bg-secondary" title={t('back_to_book')}>
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
        readProgress={readProgress}
      />

      {/* Theme customizer slide-over */}
      <ThemeCustomizer
        open={themeOpen}
        onClose={() => setThemeOpen(false)}
        showIndices={showIndices}
        onShowIndicesChange={(v) => { setShowIndices(v); localStorage.setItem('lw_reader_indices', String(v)); }}
        autoNext={autoNextEnabled}
        onAutoNextChange={(v) => {
          setAutoNextEnabled(v);
          localStorage.setItem('lw_reader_auto_next', String(v));
          if (!v) setAutoNextCountdown(null); // cancel any pending auto-advance
        }}
        autoScrollTTS={autoScrollTTS}
        onAutoScrollTTSChange={(v) => {
          setAutoScrollTTS(v);
          localStorage.setItem('lw_reader_tts_scroll', String(v));
        }}
      />

      {/* W11 lore-seeker slide-over — "the lore so far", spoiler-windowed to the current chapter. */}
      {loreOpen && bookId && (
        <>
          <div className="fixed inset-0 z-[19] bg-black/20" onClick={() => setLoreOpen(false)} />
          <aside
            className="fixed right-0 top-12 bottom-0 z-20 w-80 max-w-[90vw] overflow-y-auto border-l bg-card shadow-lg"
            data-testid="lore-seeker-panel"
          >
            <LoreSeekerPanel bookId={bookId} chapterId={chapterId} />
          </aside>
        </>
      )}

      {/* P5: the book-scoped glossary assistant (floating dock → embedded chat). */}
      {bookId && <BookAssistantDock bookId={bookId} />}

      {/* Reading area — reader theme applied here, chrome stays on app theme.
          D-READER-WIDTH-SCALE: see BookReaderPanel.tsx for why `cqw` (container-relative, not
          `vw`) and why `--reader-effective-width` is set ONCE here and consumed by both the
          article AND ContentRenderer's `.content-renderer` (reader.css) — same shared reader
          chrome, same fixed-width-wastes-space fix, kept consistent across both consumers
          (DOCK-2 no-fork). */}
      <div
        ref={scrollRef}
        className="flex flex-1 justify-center overflow-y-auto"
        style={{
          padding: '64px 24px 120px', background: readerTheme.bg, color: readerTheme.fg,
          containerType: 'inline-size',
          '--reader-effective-width': 'clamp(var(--reader-width, 680px), 85cqw, 1100px)',
          ...readerCssVars as React.CSSProperties,
        } as React.CSSProperties}
      >
        <article style={{ maxWidth: 'var(--reader-effective-width)', width: '100%' }}>

          {/* Chapter header */}
          <div className="chapter-header">
            <p className="ch-label">{t('chapter_label', { n: currentIdx + 1 })}</p>
            {(chapter?.title || chapter?.original_filename) && (
              <h1 className="ch-title">{chapter?.title || chapter?.original_filename}</h1>
            )}
            <div className="ch-divider" />
            <div className="ch-meta">
              <span>{stats.count} {t(stats.unit)}</span>
              <span style={{ color: 'var(--border)' }}>&middot;</span>
              <span>{t('min_read', { minutes: stats.minutes })}</span>
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
            <div className="mb-6 text-center text-xs text-muted-foreground animate-pulse">{t('loading_translation')}</div>
          )}
          {blocks.length > 0 ? (
            <ContentRenderer
              blocks={blocks}
              showIndices={showIndices}
              ttsActiveBlock={ttsState.activeBlockId ?? undefined}
              onBlockClick={ttsState.status !== 'idle' ? handleBlockClick : undefined}
              className={langLoading ? 'opacity-50 transition-opacity' : ''}
            />
          ) : (
            <p className="text-center font-serif text-muted-foreground italic">
              {t('empty_chapter')}
            </p>
          )}

          {/* End of chapter marker */}
          <div ref={chapterEndRef} className="chapter-end">
            <p>{t('end_of_chapter', { n: currentIdx + 1 })}</p>
            {autoNextCountdown !== null && nextCh && (
              <div className="mt-3 flex flex-col items-center gap-2">
                <p className="text-xs text-muted-foreground">
                  {t('next_in', { seconds: autoNextCountdown })}
                </p>
                <button
                  onClick={() => setAutoNextCountdown(null)}
                  className="rounded border px-3 py-1 text-[11px] text-muted-foreground hover:bg-secondary"
                >
                  {t('cancel')}
                </button>
              </div>
            )}
          </div>
          {/* Reading tracker sentinel — invisible, triggers scroll depth */}
          <div ref={sentinelRef} aria-hidden="true" />
        </article>
      </div>

      {/* TTS floating player */}
      <TTSBar
        activeBlockText={activeBlockText}
        onOpenSettings={() => setTtsSettingsOpen(true)}
        autoScroll={autoScrollTTS}
        onToggleAutoScroll={() => {
          setAutoScrollTTS((v) => {
            localStorage.setItem('lw_reader_tts_scroll', String(!v));
            return !v;
          });
        }}
      />

      {/* TTS settings slide-over */}
      <TTSSettings open={ttsSettingsOpen} onClose={() => setTtsSettingsOpen(false)} />

      {/* Bottom nav — gradient fade */}
      <div
        className="fixed bottom-0 left-0 right-0 z-20 flex items-center justify-between px-6 py-3"
        style={{ background: `linear-gradient(transparent, ${readerTheme.bg})` }}
      >
        {prevCh ? (
          <Link to={`/books/${bookId}/chapters/${prevCh.chapter_id}/read`} className="inline-flex items-center gap-2 rounded-lg border bg-card px-4 py-2 text-xs transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-[hsl(var(--card-hover,25_7%_14%))]">
            <ChevronLeft className="h-3.5 w-3.5" /> {prevCh.title || t('ch_short', { n: currentIdx })}
          </Link>
        ) : <div />}
        <span className="text-[11px] text-muted-foreground">
          {t('progress', { current: currentIdx + 1, total: chapters.length, percent: Math.round(progress) })}
        </span>
        {nextCh ? (
          <Link to={`/books/${bookId}/chapters/${nextCh.chapter_id}/read`} className="btn-glow inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-all hover:bg-primary/90">
            {nextCh.title || t('ch_short', { n: currentIdx + 2 })} <ChevronRight className="h-3.5 w-3.5" />
          </Link>
        ) : <div />}
      </div>
    </div>
  );
}
