import { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { versionsApi, type LanguageVersionGroup, type VersionSummary } from '@/features/translation/versionsApi';
import { translationApi, type BookTranslationSettings } from '@/features/translation/api';
import { useJobEvents, type JobEvent } from '@/hooks/useJobEvents';
import { VersionSidebar } from '@/components/translation/VersionSidebar';
import { TranslationViewer } from '@/components/translation/TranslationViewer';
import { SplitCompareView } from '@/components/translation/SplitCompareView';
import { TranslateModal } from '@/components/translation/TranslateModal';
import { Skeleton } from '@/components/ui/skeleton';

export default function ChapterTranslationsPage() {
  const { bookId = '', chapterId = '' } = useParams<{ bookId: string; chapterId: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const { accessToken } = useAuth();
  const token = accessToken!;

  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [languages, setLanguages] = useState<LanguageVersionGroup[]>([]);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [loading, setLoading] = useState(true);

  // Derived selection state from URL
  const selectedLang = searchParams.get('lang') || null;
  const selectedVersionId = searchParams.get('vid') || null;

  const [compareMode, setCompareMode] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

  // Load chapter metadata + versions + book settings on mount
  const loadAll = useCallback(async () => {
    setLoading(true);
    try {
      const [chapters, versionsResp, settingsResp] = await Promise.all([
        booksApi.listChapters(token, bookId, { lifecycle_state: 'active', limit: 100 }),
        versionsApi.listChapterVersions(token, chapterId),
        translationApi.getBookSettings(token, bookId),
      ]);
      const ch = chapters.items.find((c) => c.chapter_id === chapterId) ?? null;
      setChapter(ch);
      setLanguages(versionsResp.languages);
      setSettings(settingsResp);

      // If URL has no lang set, auto-select the language with the most versions
      if (!searchParams.get('lang') && versionsResp.languages.length > 0) {
        const bestLang = versionsResp.languages.reduce((a, b) =>
          b.versions.length > a.versions.length ? b : a
        );
        setSearchParams((p) => { p.set('lang', bestLang.target_language); return p; }, { replace: true });
      }
    } finally {
      setLoading(false);
    }
  }, [token, bookId, chapterId]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  // Refresh versions when a translation job completes for this chapter
  const handleJobEvent = useCallback((e: JobEvent) => {
    if (e.job_type !== 'translation') return;
    if (e.event === 'job.chapter_done') {
      const payload = e.payload as { chapter_id?: string };
      if (payload.chapter_id === chapterId) {
        versionsApi.listChapterVersions(token, chapterId)
          .then((r) => setLanguages(r.languages))
          .catch(() => {});
      }
    }
  }, [token, chapterId]);

  const handleReconnect = useCallback(() => {
    versionsApi.listChapterVersions(token, chapterId)
      .then((r) => setLanguages(r.languages))
      .catch(() => {});
  }, [token, chapterId]);

  useJobEvents({ onEvent: handleJobEvent, onReconnect: handleReconnect });

  // Auto-select active version (or latest) when language changes
  useEffect(() => {
    if (!selectedLang) return;
    const group = languages.find((g) => g.target_language === selectedLang);
    if (!group || group.versions.length === 0) return;
    const currentVid = searchParams.get('vid');
    if (currentVid && group.versions.some((v) => v.id === currentVid)) return; // already valid
    const activeVer = group.versions.find((v) => v.is_active) ?? group.versions[0];
    setSearchParams((p) => { p.set('vid', activeVer.id); return p; }, { replace: true });
  }, [selectedLang, languages]);

  function handleLangChange(lang: string | null) {
    setCompareMode(false);
    if (lang === null) {
      setSearchParams((p) => { p.delete('lang'); p.delete('vid'); return p; }, { replace: true });
    } else {
      setSearchParams((p) => { p.set('lang', lang); p.delete('vid'); return p; }, { replace: true });
    }
  }

  function handleVersionSelect(id: string) {
    setSearchParams((p) => { p.set('vid', id); return p; }, { replace: true });
  }

  function handleSetActive(versionId: string) {
    // Optimistically update is_active flags in state
    setLanguages((prev) =>
      prev.map((g) =>
        g.target_language === selectedLang
          ? {
              ...g,
              active_id: versionId,
              versions: g.versions.map((v) => ({ ...v, is_active: v.id === versionId })),
            }
          : g
      )
    );
  }

  const currentGroup = languages.find((g) => g.target_language === selectedLang) ?? null;
  const currentVersion: VersionSummary | null =
    currentGroup?.versions.find((v) => v.id === selectedVersionId) ??
    currentGroup?.versions[0] ??
    null;

  const isActiveVersion = currentVersion?.is_active ?? false;

  const title = chapter?.title || `Chapter ${chapter?.sort_order ?? chapterId.slice(0, 8)}`;

  return (
    <div className="flex h-full flex-col gap-4">
      {/* Page header */}
      <div className="flex items-center gap-3">
        <Link to={`/books/${bookId}`} className="text-sm text-muted-foreground hover:underline">
          ← Back to book
        </Link>
        <span className="text-muted-foreground">/</span>
        {loading ? (
          <Skeleton className="h-5 w-48" />
        ) : (
          <h1 className="text-lg font-semibold">{title} — Translations</h1>
        )}
      </div>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-56" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : (
        <div className="flex flex-1 gap-4 overflow-hidden">
          {/* Left: version sidebar */}
          <div className="w-52 shrink-0">
            <VersionSidebar
              languages={languages}
              selectedLang={selectedLang}
              onLangChange={handleLangChange}
              selectedVersionId={selectedVersionId}
              onVersionSelect={handleVersionSelect}
              onRetranslate={() => setTranslateOpen(true)}
              originalLanguage={chapter?.original_language}
            />
          </div>

          {/* Right: content */}
          <div className="flex-1 overflow-auto">
            {selectedLang === null || currentVersion === null ? (
              /* Original view — show the draft body */
              <OriginalViewer token={token} bookId={bookId} chapterId={chapterId} />
            ) : compareMode ? (
              <SplitCompareView
                token={token}
                bookId={bookId}
                chapterId={chapterId}
                version={currentVersion}
                originalLanguage={chapter?.original_language}
              />
            ) : (
              <TranslationViewer
                token={token}
                chapterId={chapterId}
                version={currentVersion}
                isActiveVersion={isActiveVersion}
                onSetActive={handleSetActive}
                onToggleCompare={() => setCompareMode(true)}
                compareMode={false}
              />
            )}
            {compareMode && (
              <div className="mt-2">
                <button
                  onClick={() => setCompareMode(false)}
                  className="text-sm text-muted-foreground hover:underline"
                >
                  Exit compare
                </button>
              </div>
            )}
          </div>
        </div>
      )}

      {translateOpen && settings && (
        <TranslateModal
          token={token}
          bookId={bookId}
          chapterIds={[chapterId]}
          settings={settings}
          onClose={() => setTranslateOpen(false)}
          onJobCreated={() => { setTranslateOpen(false); void loadAll(); }}
        />
      )}
    </div>
  );
}

// Shows the original draft body — used when selectedLang is null
function OriginalViewer({
  token,
  bookId,
  chapterId,
}: {
  token: string;
  bookId: string;
  chapterId: string;
}) {
  const [body, setBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    booksApi.getDraft(token, bookId, chapterId)
      .then((d) => setBody(d.body))
      .catch(() => setBody(null))
      .finally(() => setLoading(false));
  }, [token, bookId, chapterId]);

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!body) return <p className="text-sm text-muted-foreground">No draft content available.</p>;

  return (
    <div className="whitespace-pre-wrap rounded border bg-muted p-4 text-sm leading-relaxed">
      {body}
    </div>
  );
}
