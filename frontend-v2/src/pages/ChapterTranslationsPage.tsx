import { useCallback, useEffect, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { versionsApi, translationApi, type LanguageVersionGroup, type BookTranslationSettings } from '@/features/translation/api';
import { VersionSidebar } from '@/features/translation/components/VersionSidebar';
import { TranslationViewer } from '@/features/translation/components/TranslationViewer';
import { SplitCompareView } from '@/features/translation/components/SplitCompareView';

export function ChapterTranslationsPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { accessToken } = useAuth();

  const [chapterTitle, setChapterTitle] = useState('');
  const [originalLanguage, setOriginalLanguage] = useState<string | undefined>();
  const [wordCount, setWordCount] = useState<number | undefined>();
  const [languages, setLanguages] = useState<LanguageVersionGroup[]>([]);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [compareMode, setCompareMode] = useState(false);
  const [translateOpen, setTranslateOpen] = useState(false);

  const selectedLang = searchParams.get('lang') || null;
  const selectedVersionId = searchParams.get('vid') || null;

  // Load all data
  const loadAll = useCallback(async () => {
    if (!accessToken) return;
    setLoading(true);
    try {
      const [chaptersRes, versionsRes, settingsRes] = await Promise.all([
        booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 100 }),
        versionsApi.listChapterVersions(accessToken, chapterId),
        translationApi.getBookSettings(accessToken, bookId).catch(() => null),
      ]);

      const ch = chaptersRes.items?.find((c: any) => c.chapter_id === chapterId) as any;
      setChapterTitle(ch?.title || `Chapter ${ch?.sort_order ?? '?'}`);
      setOriginalLanguage(ch?.original_language);
      setWordCount(ch?.word_count_estimate as number | undefined);
      setLanguages(versionsRes.languages);
      setSettings(settingsRes);

      // Auto-select language if not set
      if (!searchParams.get('lang') && versionsRes.languages.length > 0) {
        const best = versionsRes.languages.reduce((a, b) =>
          b.versions.length > a.versions.length ? b : a
        );
        setSearchParams((p) => { p.set('lang', best.target_language); return p; }, { replace: true });
      }
    } catch (e) {
      toast.error(`Failed to load: ${(e as Error).message}`);
    } finally {
      setLoading(false);
    }
  }, [accessToken, bookId, chapterId]);

  useEffect(() => { void loadAll(); }, [loadAll]);

  // Auto-select version when language changes
  useEffect(() => {
    if (!selectedLang) return;
    const group = languages.find((g) => g.target_language === selectedLang);
    if (!group || group.versions.length === 0) return;
    const currentVid = searchParams.get('vid');
    if (currentVid && group.versions.some((v) => v.id === currentVid)) return;
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
      <div className="flex h-full">
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

  return (
    <div className="flex h-full overflow-hidden">
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

      {/* Content area */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Breadcrumb */}
        <div className="flex items-center gap-1.5 border-b border-border px-5 py-2.5 text-xs text-muted-foreground shrink-0">
          <Link to={`/books/${bookId}`} className="text-accent hover:underline">Book</Link>
          <span>&rsaquo;</span>
          <Link to={`/books/${bookId}`} className="text-accent hover:underline">Chapters</Link>
          <span>&rsaquo;</span>
          <span className="text-foreground">{chapterTitle} &mdash; Translations</span>
        </div>

        {selectedLang === null ? (
          // Original view
          <OriginalViewer bookId={bookId} chapterId={chapterId} />
        ) : !currentVersion ? (
          // No versions for this language
          <div className="flex flex-1 items-center justify-center">
            <div className="text-center">
              <p className="text-sm text-muted-foreground">No translations for this language yet.</p>
              <button
                type="button"
                onClick={() => setTranslateOpen(true)}
                className="mt-3 rounded-md bg-accent px-4 py-2 text-sm font-medium text-white hover:brightness-110"
              >
                Translate Now
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
            chapterId={chapterId}
            versionId={currentVersion.id}
            isActive={isActive}
            onSetActive={handleSetActive}
          />
        )}
      </div>
    </div>
  );
}

// ── OriginalViewer ──────────────────────────────────────────────────────────

function OriginalViewer({ bookId, chapterId }: { bookId: string; chapterId: string }) {
  const { accessToken } = useAuth();
  const [body, setBody] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!accessToken) return;
    let mounted = true;
    booksApi.getDraft(accessToken, bookId, chapterId)
      .then((d) => { if (mounted) setBody(d.text_content || (typeof d.body === 'string' ? d.body : '')); })
      .catch(() => { if (mounted) setBody(null); })
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
        No draft content available.
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-6">
      <div className="mx-auto max-w-[680px]">
        <p className="mb-3 text-[11px] font-medium text-primary">Original Draft</p>
        <div className="whitespace-pre-wrap font-serif text-[15px] leading-[2.0] text-foreground/85">
          {body}
        </div>
      </div>
    </div>
  );
}
