import { useCallback, useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { versionsApi, translationApi, type LanguageVersionGroup, type BookTranslationSettings } from '@/features/translation/api';
import { VersionSidebar } from '@/features/translation/components/VersionSidebar';
import { TranslationViewer } from '@/features/translation/components/TranslationViewer';
import { SplitCompareView } from '@/features/translation/components/SplitCompareView';
import { TranslationErrorState } from '@/features/translation/components/TranslationErrorState';
import { TranslateModal } from '@/pages/book-tabs/TranslateModal';

interface Props {
  bookId: string;
  chapterId: string;
  /** Seed the selected language (e.g. deep-link `?lang=` from the translation matrix). */
  initialLang?: string | null;
  /** Seed the selected version id. */
  initialVersionId?: string | null;
  /** Show the book/chapter breadcrumb row (standalone page). Off when embedded in the editor. */
  showBreadcrumb?: boolean;
  className?: string;
  /** #16 Phase 3 DOCK-7 fix — see TranslationViewer's own doc comment. Omitted by every
   *  existing caller (classic page, legacy editor's Translate workmode) so their `navigate()`
   *  fallback is unchanged; only the new `translation-versions` Studio panel supplies it. */
  onReview?: (versionId: string) => void;
}

/**
 * The full per-chapter translation workspace — language/version picker, side-by-side
 * compare, per-block human edits, set-active, and re-translate jobs.
 *
 * Extracted from ChapterTranslationsPage so the SAME workspace mounts either as a
 * standalone route OR embedded as the editor's Translate workmode. Selection state is
 * LOCAL (not URL search params) so it composes cleanly inside the editor route; the
 * standalone page seeds it from `?lang=`/`?vid=` via the initial props. Selection is not
 * written back to the URL (a minor loss of deep-link refresh-persistence, acceptable for
 * the reuse win).
 */
export function ChapterTranslationsPanel({
  bookId,
  chapterId,
  initialLang = null,
  initialVersionId = null,
  showBreadcrumb = true,
  className,
  onReview,
}: Props) {
  const { t } = useTranslation('translation');
  const { accessToken } = useAuth();

  const [chapterTitle, setChapterTitle] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState<string | undefined>();
  const [wordCount, setWordCount] = useState<number | undefined>();
  const [languages, setLanguages] = useState<LanguageVersionGroup[]>([]);
  const [, setSettings] = useState<BookTranslationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  // T6: a versions/chapters load failure must show a typed error banner + Retry, not a
  // structurally-fine-but-empty workspace (blank title, `??` language) with the failure only
  // in a toast that is long gone by the time the user looks.
  const [loadError, setLoadError] = useState<unknown>(null);
  const [compareMode, setCompareMode] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

  const [selectedLang, setSelectedLang] = useState<string | null>(initialLang);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(initialVersionId);

  // Load all data
  const loadAll = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    setLoadError(null);
    try {
      const [chaptersRes, versionsRes, settingsRes] = await Promise.all([
        booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
        versionsApi.listChapterVersions(accessToken, chapterId),
        translationApi.getBookSettings(accessToken, bookId).catch(() => null),
      ]);

      const ch = chaptersRes.items?.find((c: any) => c.chapter_id === chapterId) as any;
      setChapterTitle(ch?.title || t('page.chapter_fallback', { n: ch?.sort_order ?? '?' }));
      setOriginalLanguage(ch?.original_language);
      setWordCount(ch?.word_count_estimate as number | undefined);
      setLanguages(versionsRes.languages);
      setSettings(settingsRes);

      // Auto-select the best-covered language if none is set yet.
      setSelectedLang((prev) => {
        if (prev) return prev;
        if (versionsRes.languages.length === 0) return prev;
        const best = versionsRes.languages.reduce((a, b) => (b.versions.length > a.versions.length ? b : a));
        return best.target_language;
      });
    } catch (e) {
      // T6: surface a persistent typed error state (below), not a transient toast over an
      // empty workspace.
      setLoadError(e);
    } finally {
      setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [accessToken, bookId, chapterId]);

  // #16 Phase 4 (LIVE-SYNC audit, 2026-07-05) — this component's multi-source loadAll() has no
  // direct react-query integration of its own (it's a plain useState/useEffect fetch), so the
  // Lane B reconciler (`translationEffects.ts`) has nothing to invalidate directly after an agent
  // cancels/pauses a translation job. This trivial sentinel query gives it a lever: its queryFn
  // does no network work, but react-query's own invalidation → refetch → dataUpdatedAt-changes
  // machinery is reused as a refresh signal, so loadAll() re-runs without restructuring the rest
  // of this component's local optimistic-update state (handleSetActive et al).
  const refreshSignal = useQuery({
    queryKey: ['translation', 'refresh', bookId, chapterId],
    queryFn: () => Date.now(),
    staleTime: Infinity,
    enabled: !!accessToken,
  });
  useEffect(() => {
    if (refreshSignal.dataUpdatedAt) void loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- loadAll is intentionally excluded:
    // it's recreated every render (new bookId/chapterId/accessToken identity is what matters, and
    // those already flow into loadAll's own deps + this query's key), only dataUpdatedAt should
    // re-trigger a fetch here.
  }, [refreshSignal.dataUpdatedAt]);

  // Auto-select a version when the language changes (active version, else first).
  useEffect(() => {
    if (!selectedLang) return;
    const group = languages.find((g) => g.target_language === selectedLang);
    if (!group || group.versions.length === 0) return;
    if (selectedVersionId && group.versions.some((v) => v.id === selectedVersionId)) return;
    const activeVer = group.versions.find((v) => v.is_active) ?? group.versions[0];
    setSelectedVersionId(activeVer.id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedLang, languages]);

  function handleLangChange(lang: string | null) {
    setCompareMode(false);
    if (lang === null) {
      setSelectedLang(null);
      setSelectedVersionId(null);
      return;
    }
    // Auto-select active version (or first) for the chosen language
    const group = languages.find((g) => g.target_language === lang);
    const activeVer = group?.versions.find((v) => v.is_active) ?? group?.versions[0];
    setSelectedLang(lang);
    setSelectedVersionId(activeVer ? activeVer.id : null);
  }

  function handleVersionSelect(id: string) {
    setSelectedVersionId(id);
  }

  function handleSetActive(versionId: string) {
    setLanguages((prev) =>
      prev.map((g) =>
        g.target_language === selectedLang
          ? { ...g, active_id: versionId, versions: g.versions.map((v) => ({ ...v, is_active: v.id === versionId })) }
          : g
      )
    );
  }

  const currentGroup = languages.find((g) => g.target_language === selectedLang);
  const currentVersion = currentGroup?.versions.find((v) => v.id === selectedVersionId) ?? currentGroup?.versions[0] ?? null;
  const isActive = currentVersion?.is_active ?? false;

  // Loading
  if (loading) {
    return (
      <div className={className ?? 'flex h-full'}>
        <div className="w-[240px] shrink-0 border-r border-border bg-card p-4 space-y-3">
          <div className="h-5 w-32 animate-pulse rounded bg-muted" />
          <div className="h-3 w-20 animate-pulse rounded bg-muted" />
          <div className="mt-4 space-y-2">
            {[1, 2, 3].map((i) => <div key={i} className="h-8 animate-pulse rounded bg-muted" />)}
          </div>
        </div>
        <div className="flex-1 p-6">
          <div className="h-4 w-48 animate-pulse rounded bg-muted" />
          <div className="mt-6 space-y-3">
            <div className="h-4 w-full animate-pulse rounded bg-muted" />
            <div className="h-4 w-5/6 animate-pulse rounded bg-muted" />
          </div>
        </div>
      </div>
    );
  }

  // T6: a load failure is surfaced as a persistent, typed banner with Retry — never a
  // structurally-fine, factually-empty workspace.
  if (loadError) {
    return (
      <div data-testid="chapter-translations-panel" className={className ?? 'flex h-full items-center justify-center p-6'}>
        <TranslationErrorState error={loadError} onRetry={loadAll} className="max-w-md" />
      </div>
    );
  }

  return (
    <div data-testid="chapter-translations-panel" className={className ?? 'flex h-full overflow-hidden'}>
      {/* Sidebar */}
      <VersionSidebar
        chapterTitle={chapterTitle}
        originalLanguage={originalLanguage}
        wordCount={wordCount}
        languages={languages}
        selectedLang={selectedLang}
        selectedVersionId={selectedVersionId}
        onLangChange={handleLangChange}
        onVersionSelect={handleVersionSelect}
        onRetranslate={() => setTranslateOpen(true)}
        onCompareToggle={() => setCompareMode(!compareMode)}
        compareMode={compareMode}
      />

      {/* Re-translate this chapter (the sidebar's action wires here). Scoped to the
          current chapter; on completion the version list reloads to show the new draft. */}
      <TranslateModal
        open={translateOpen}
        onClose={() => setTranslateOpen(false)}
        bookId={bookId}
        preselectedChapterIds={[chapterId]}
        onJobCreated={() => { setTranslateOpen(false); void loadAll(); }}
      />

      {/* Content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {showBreadcrumb && (
          <div className="flex items-center gap-1.5 border-b border-border px-5 py-2.5 text-xs text-muted-foreground shrink-0">
            <Link to={`/books/${bookId}`} className="text-accent hover:underline">{t('page.breadcrumb_book')}</Link>
            <span>&rsaquo;</span>
            <Link to={`/books/${bookId}`} className="text-accent hover:underline">{t('page.breadcrumb_chapters')}</Link>
            <span>&rsaquo;</span>
            <span className="text-foreground">{chapterTitle} &mdash; {t('page.translations')}</span>
          </div>
        )}

        {selectedLang === null ? (
          // Original view
          <OriginalViewer bookId={bookId} chapterId={chapterId} />
        ) : !currentVersion ? (
          // No versions for this language
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">{t('page.no_translations_yet')}</p>
              <button
                type="button"
                onClick={() => setTranslateOpen(true)}
                className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:brightness-110"
              >
                {t('page.translate_now')}
              </button>
            </div>
          </div>
        ) : compareMode ? (
          // Split compare view
          <SplitCompareView
            bookId={bookId}
            chapterId={chapterId}
            versionId={currentVersion.id}
            originalLanguage={originalLanguage}
            targetLanguage={selectedLang}
          />
        ) : (
          // Single translation viewer
          <TranslationViewer
            bookId={bookId}
            chapterId={chapterId}
            versionId={currentVersion.id}
            isActive={isActive}
            onSetActive={handleSetActive}
            onReview={onReview}
            // S4: a human edit creates a new version — reload so the sidebar's version list
            // reflects it instead of silently going stale.
            onSaved={() => void loadAll()}
          />
        )}
      </div>
    </div>
  );
}

// ── OriginalViewer ──────────────────────────────────────────────────────────

function OriginalViewer({ bookId, chapterId }: { bookId: string; chapterId: string }) {
  const { t } = useTranslation('translation');
  const { accessToken } = useAuth();
  const [body, setBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    booksApi.getDraft(accessToken, bookId, chapterId)
      .then((d) => { if (mounted) setBody(d.text_content || (typeof d.body === 'string' ? d.body : '')); })
      .catch((e) => { if (mounted) { setBody(null); toast.error(t('page.load_draft_failed', { error: (e as Error).message })); } })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [accessToken, bookId, chapterId]);

  if (loading) {
    return (
      <div className="flex-1 p-6">
        <div className="mx-auto max-w-[680px] space-y-3">
          <div className="h-4 w-full animate-pulse rounded bg-muted" />
          <div className="h-4 w-5/6 animate-pulse rounded bg-muted" />
          <div className="h-4 w-4/6 animate-pulse rounded bg-muted" />
        </div>
      </div>
    );
  }

  if (!body) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">
        {t('page.no_draft')}
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[680px]">
        <p className="mb-3 text-[11px] font-medium text-primary">{t('page.original_draft')}</p>
        <div className="whitespace-pre-wrap font-serif text-[15px] leading-[2.0] text-foreground/85">
          {body}
        </div>
      </div>
    </div>
  );
}
