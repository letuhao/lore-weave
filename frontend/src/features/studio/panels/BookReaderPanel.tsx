// 14_utility_panels.md Phase C4 — the `book-reader` dock panel: a hidden-from-palette,
// params-retargeting singleton (SkillEditorPanel / JsonEditorPanel precedent) that reads
// `{bookId, chapterId?}` from props.params (DOCK-7 F1) and renders the SAME reading chrome as
// the standalone `/books/:bookId/chapters/:chapterId/read` route via `useBookReaderContent`
// (C3) + the router-free TTS/reading-tracker hooks — all reused AS-IS (DOCK-2).
//
// This is a pure READ-only browse capability: opening book B here never touches the active
// book's studio/editor state (see 14_utility_panels.md Phase C design correction — no DOCK-7
// exception needed at all, this is an ordinary panel). In-panel chapter/TOC navigation updates
// the panel's OWN params via `props.api.updateParameters` — never a route push. The "edit this
// chapter" / "back to this book" links ReaderPage shows are deliberately OMITTED here: this
// panel only ever shows an OTHER book than the active studio's, so there is no "back to the
// (active) book" affordance that makes sense, and editing another book's chapter from inside a
// browse-then-read panel is out of scope (see spec's Phase C note on a future social/mutation
// layer not existing yet).
import { useCallback, useEffect, useMemo, useState } from 'react';
import type { IDockviewPanelProps } from 'dockview-react';
import { useTranslation } from 'react-i18next';
import { ChevronLeft, ChevronRight, Menu, Sun, Volume2 } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { ContentRenderer } from '@/components/reader/ContentRenderer';
import { TOCSidebar } from '@/components/reader/TOCSidebar';
import { ThemeCustomizer } from '@/components/reader/ThemeCustomizer';
import { TTSBar } from '@/components/reader/TTSBar';
import { TTSSettings } from '@/components/reader/TTSSettings';
import { useReaderTheme } from '@/providers/ThemeProvider';
import { useTTSState, useTTSControls } from '@/hooks/useTTS';
import { useReadingTracker } from '@/hooks/useReadingTracker';
import { extractSpeakableBlocks } from '@/lib/audio-utils';
import { useBookReaderContent, computeReadingStats } from '@/features/books/hooks/useBookReaderContent';
import { useStudioPanel } from './useStudioPanel';

interface BookReaderPanelParams {
  bookId?: string;
  chapterId?: string;
}

export function BookReaderPanel(props: IDockviewPanelProps) {
  useStudioPanel('book-reader', props.api);
  const { t } = useTranslation('reader');
  const { accessToken } = useAuth();
  const { cssVars: readerCssVars, theme: readerTheme } = useReaderTheme();

  // F1 — params seed on mount, then follow every updateParameters call (Settings/JobDetail
  // precedent: dockview fires onDidParametersChange on EVERY call, even a same-value repeat).
  const [params, setParams] = useState<BookReaderPanelParams>((props.params as BookReaderPanelParams | undefined) ?? {});
  useEffect(() => {
    const disp = props.api.onDidParametersChange?.((p: Record<string, unknown> | undefined) => {
      setParams((p as BookReaderPanelParams | undefined) ?? {});
    });
    return () => disp?.dispose?.();
  }, [props.api]);

  const bookId = params.bookId ?? '';
  const chapterId = params.chapterId ?? '';

  // UI-only toggle state — panel-local (Tier-1), mirrors ReaderPage's own local state.
  const [tocOpen, setTocOpen] = useState(false);
  const [themeOpen, setThemeOpen] = useState(false);
  const [ttsSettingsOpen, setTtsSettingsOpen] = useState(false);
  const [showIndices, setShowIndices] = useState(false);
  const [autoScrollTTS, setAutoScrollTTS] = useState(true);

  const sentinelRef = useReadingTracker({ bookId, chapterId, accessToken });
  const ttsState = useTTSState();
  const ttsControls = useTTSControls();

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

  // BooksBrowserPanel opens this panel with only {bookId} (a book row click doesn't know a
  // chapter yet). Resolve the first active chapter once, then retarget our own params — this
  // bootstrapping concern is deliberately kept OUT of useBookReaderContent (whose contract is a
  // concrete (bookId, chapterId) pair, matching ReaderPage's route-supplied args exactly).
  useEffect(() => {
    if (!accessToken || !bookId || chapterId) return;
    let cancelled = false;
    void booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }).then((res) => {
      if (cancelled || res.items.length === 0) return;
      const first = [...res.items].sort((a, b) => a.sort_order - b.sort_order)[0];
      props.api.updateParameters({ bookId, chapterId: first.chapter_id });
    }).catch(() => undefined);
    return () => { cancelled = true; };
  }, [accessToken, bookId, chapterId, props.api]);

  const goToChapter = useCallback((targetChapterId: string) => {
    props.api.updateParameters({ bookId, chapterId: targetChapterId });
  }, [props.api, bookId]);

  // Self-title beyond the generic "Reader" label once we know which book/chapter is open —
  // useStudioPanel already claims the base title; this refines it per DOCK-5's intent (a
  // meaningful dock-tab title), same pattern JobDetailPanel/SettingsPanel use for retargeting.
  useEffect(() => {
    if (book && chapter) {
      props.api.setTitle(`${book.title} — ${chapter.title || chapter.original_filename}`);
    } else if (book) {
      props.api.setTitle(book.title);
    }
  }, [props.api, book, chapter]);

  const handleStartTTS = useCallback(() => {
    if (ttsState.status !== 'idle') ttsControls.stop();
    else ttsControls.start(blocks);
  }, [blocks, ttsState.status, ttsControls]);

  const handleBlockClick = useCallback((blockId: string) => {
    if (ttsState.status !== 'idle') ttsControls.seekBlock(blockId);
  }, [ttsState.status, ttsControls]);

  const activeBlockText = useMemo(() => {
    if (!ttsState.activeBlockId) return '';
    const speakable = extractSpeakableBlocks(blocks);
    const active = speakable.find((b) => b.blockId === ttsState.activeBlockId);
    return active?.text || active?.subtitle || '';
  }, [blocks, ttsState.activeBlockId]);

  const chapterLang = chapter?.original_language;
  const stats = useMemo(() => computeReadingStats(blocks, chapterLang ?? undefined), [blocks, chapterLang]);

  if (!bookId) {
    return (
      <div data-testid="studio-book-reader-panel" className="p-4 text-xs text-muted-foreground">
        Open a book from the Books panel to read a chapter.
      </div>
    );
  }

  if (loading || !chapterId) {
    return (
      <div data-testid="studio-book-reader-panel" className="flex h-full items-center justify-center text-xs text-muted-foreground">
        {t('loading')}
      </div>
    );
  }

  return (
    <div data-testid="studio-book-reader-panel" className="relative flex h-full flex-col overflow-hidden" style={{ background: readerTheme.bg }}>
      {/* Progress bar */}
      <div className="absolute left-0 right-0 top-0 z-20 h-0.5 bg-secondary">
        <div className="h-full bg-primary transition-all" style={{ width: `${progress}%` }} />
      </div>

      {/* Top bar */}
      <div
        className="relative z-[19] flex h-12 flex-shrink-0 items-center justify-between border-b border-border/30 px-4"
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
          <button
            onClick={handleStartTTS}
            className={`rounded p-1.5 transition-colors ${ttsState.status !== 'idle' ? 'bg-purple-500/15 text-purple-400' : 'text-muted-foreground hover:bg-secondary'}`}
            title={ttsState.status !== 'idle' ? t('stop_reading') : t('read_aloud')}
          >
            <Volume2 className="h-4 w-4" />
          </button>
          <button onClick={() => { setThemeOpen((v) => !v); setTocOpen(false); }} className={`rounded p-1.5 transition-colors ${themeOpen ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary'}`} title={t('reading_theme')}>
            <Sun className="h-4 w-4" />
          </button>
        </div>
      </div>

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
        onNavigateChapter={goToChapter}
      />

      <ThemeCustomizer
        open={themeOpen}
        onClose={() => setThemeOpen(false)}
        showIndices={showIndices}
        onShowIndicesChange={setShowIndices}
        autoNext={false}
        onAutoNextChange={() => undefined}
        autoScrollTTS={autoScrollTTS}
        onAutoScrollTTSChange={setAutoScrollTTS}
      />

      <div className="flex flex-1 justify-center overflow-y-auto" style={{ padding: '32px 24px 96px', background: readerTheme.bg, color: readerTheme.fg, ...readerCssVars as React.CSSProperties }}>
        <article style={{ maxWidth: 'var(--reader-width, 680px)', width: '100%' }}>
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
            <p className="text-center font-serif text-muted-foreground italic">{t('empty_chapter')}</p>
          )}

          <div className="chapter-end">
            <p>{t('end_of_chapter', { n: currentIdx + 1 })}</p>
          </div>
          <div ref={sentinelRef} aria-hidden="true" />
        </article>
      </div>

      <TTSBar
        activeBlockText={activeBlockText}
        onOpenSettings={() => setTtsSettingsOpen(true)}
        autoScroll={autoScrollTTS}
        onToggleAutoScroll={() => setAutoScrollTTS((v) => !v)}
      />
      <TTSSettings open={ttsSettingsOpen} onClose={() => setTtsSettingsOpen(false)} />

      {/* Bottom nav — in-panel chapter switch via updateParameters, never a route push (DOCK-7) */}
      <div
        className="relative z-20 flex flex-shrink-0 items-center justify-between px-6 py-3"
        style={{ background: `linear-gradient(transparent, ${readerTheme.bg})` }}
      >
        {prevCh ? (
          <button
            type="button"
            onClick={() => goToChapter(prevCh.chapter_id)}
            data-testid="book-reader-prev-chapter"
            className="inline-flex items-center gap-2 rounded-lg border bg-card px-4 py-2 text-xs transition-colors hover:border-[hsl(var(--border-hover,25_6%_24%))] hover:bg-[hsl(var(--card-hover,25_7%_14%))]"
          >
            <ChevronLeft className="h-3.5 w-3.5" /> {prevCh.title || t('ch_short', { n: currentIdx })}
          </button>
        ) : <div />}
        <span className="text-[11px] text-muted-foreground">
          {t('progress', { current: currentIdx + 1, total: chapters.length, percent: Math.round(progress) })}
        </span>
        {nextCh ? (
          <button
            type="button"
            onClick={() => goToChapter(nextCh.chapter_id)}
            data-testid="book-reader-next-chapter"
            className="btn-glow inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-xs font-medium text-primary-foreground transition-all hover:bg-primary/90"
          >
            {nextCh.title || t('ch_short', { n: currentIdx + 2 })} <ChevronRight className="h-3.5 w-3.5" />
          </button>
        ) : <div />}
      </div>
    </div>
  );
}
