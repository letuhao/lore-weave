import { FormEvent, useCallback, useEffect, useRef, useState } from 'react';
import { Link, useLocation, useParams, useSearchParams } from 'react-router-dom';
import { ChevronRight, Download, Languages, RotateCcw, Save } from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Book, type Chapter } from '@/features/books/api';
import {
  versionsApi,
  type LanguageVersionGroup,
  type VersionSummary,
} from '@/features/translation/versionsApi';
import {
  translationApi,
  type BookTranslationSettings,
  type TranslationJob,
} from '@/features/translation/api';
import { useJobEvents, type JobEvent } from '@/hooks/useJobEvents';
import { LexicalComposer } from '@lexical/react/LexicalComposer';
import { PlainTextPlugin } from '@lexical/react/LexicalPlainTextPlugin';
import { ContentEditable } from '@lexical/react/LexicalContentEditable';
import { HistoryPlugin } from '@lexical/react/LexicalHistoryPlugin';
import { OnChangePlugin } from '@lexical/react/LexicalOnChangePlugin';
import { $createParagraphNode, $createTextNode, $getRoot, type EditorState } from 'lexical';
import { VersionSidebar } from '@/components/translation/VersionSidebar';
import { TranslationViewer } from '@/components/translation/TranslationViewer';
import { SplitCompareView } from '@/components/translation/SplitCompareView';
import { TranslateModal } from '@/components/translation/TranslateModal';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';

// ─────────────────────────────────────────────────────────────────────────────
// Main page component
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Unified chapter workspace — Draft editor, Translations viewer, and Revision
 * history are consolidated into one tabbed page.
 *
 * Routes:
 *   /books/:bookId/chapters/:chapterId/edit          → default tab: draft
 *   /books/:bookId/chapters/:chapterId/translations  → default tab: translations
 */
export function ChapterEditorPageV2() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();

  // Page-level meta
  const [book, setBook] = useState<Book | null>(null);
  const [chapter, setChapter] = useState<Chapter | null>(null);
  const [settings, setSettings] = useState<BookTranslationSettings | null>(null);
  const [metaLoading, setMetaLoading] = useState(true);

  // Download
  const [downloadBusy, setDownloadBusy] = useState(false);

  // Translate modal — controlled at page level so header button can open it
  const [translateOpen, setTranslateOpen] = useState(false);

  // Active tab — URL-driven; default inferred from route path
  const defaultTab = location.pathname.endsWith('/translations') ? 'translations' : 'draft';
  const activeTab = searchParams.get('tab') ?? defaultTab;
  const setTab = (tab: string) =>
    setSearchParams((p) => { p.set('tab', tab); return p; }, { replace: true });

  // Load book + chapter + translation settings on mount
  useEffect(() => {
    if (!accessToken || !bookId || !chapterId) return;
    void (async () => {
      try {
        const [b, chList, s] = await Promise.all([
          booksApi.getBook(accessToken, bookId),
          booksApi.listChapters(accessToken, bookId, { limit: 200 }),
          translationApi.getBookSettings(accessToken, bookId).catch(() => null),
        ]);
        setBook(b);
        setChapter(chList.items.find((c) => c.chapter_id === chapterId) ?? null);
        setSettings(s);
      } finally {
        setMetaLoading(false);
      }
    })();
  }, [accessToken, bookId, chapterId]);

  const handleDownload = async () => {
    if (!accessToken) return;
    setDownloadBusy(true);
    try {
      const blob = await booksApi.downloadRaw(accessToken, bookId, chapterId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = chapter?.title
        ? `${chapter.title}.txt`
        : `chapter-${chapterId.slice(0, 8)}.txt`;
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setDownloadBusy(false);
    }
  };

  const chapterLabel = chapter?.title ?? (chapter ? `Chapter ${chapter.sort_order}` : '…');

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between border-b px-4 py-2.5">
        {/* Breadcrumb */}
        <div className="flex min-w-0 items-center gap-1.5 text-sm">
          <Link
            to={`/books/${bookId}`}
            className="shrink-0 text-muted-foreground hover:text-foreground hover:underline"
          >
            {metaLoading ? <Skeleton className="inline-block h-4 w-20" /> : (book?.title ?? 'Book')}
          </Link>
          <ChevronRight className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          {metaLoading ? (
            <Skeleton className="inline-block h-4 w-32" />
          ) : (
            <span className="truncate font-medium">{chapterLabel}</span>
          )}
          {chapter?.original_language && (
            <Badge variant="muted" className="shrink-0 text-[10px]">
              {chapter.original_language}
            </Badge>
          )}
        </div>

        {/* Actions */}
        <div className="flex shrink-0 items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => void handleDownload()}
            disabled={downloadBusy}
          >
            <Download className="mr-1.5 h-3.5 w-3.5" />
            {downloadBusy ? 'Downloading…' : 'Download'}
          </Button>
          <Button
            size="sm"
            disabled={!settings}
            onClick={() => {
              setTab('translations');
              setTranslateOpen(true);
            }}
          >
            <Languages className="mr-1.5 h-3.5 w-3.5" />
            Translate
          </Button>
        </div>
      </div>

      {/* ── Tabs ────────────────────────────────────────────────────────────── */}
      <Tabs
        value={activeTab}
        onValueChange={setTab}
        className="flex flex-1 flex-col overflow-hidden"
      >
        <TabsList className="mx-4 mt-3 w-auto shrink-0 self-start">
          <TabsTrigger value="draft">Draft</TabsTrigger>
          <TabsTrigger value="translations">Translations</TabsTrigger>
          <TabsTrigger value="revisions">History</TabsTrigger>
        </TabsList>

        <TabsContent value="draft" className="mt-0 flex-1 overflow-hidden">
          <DraftTab token={accessToken!} bookId={bookId} chapterId={chapterId} />
        </TabsContent>

        <TabsContent value="translations" className="mt-0 flex-1 overflow-hidden">
          <TranslationsTab
            token={accessToken!}
            bookId={bookId}
            chapterId={chapterId}
            chapter={chapter}
            translateOpen={translateOpen}
            onTranslateClose={() => setTranslateOpen(false)}
            settings={settings}
            onTranslateJobCreated={() => setTranslateOpen(false)}
          />
        </TabsContent>

        <TabsContent value="revisions" className="mt-0 flex-1 overflow-hidden">
          <RevisionsTab token={accessToken!} bookId={bookId} chapterId={chapterId} />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Draft tab
// ─────────────────────────────────────────────────────────────────────────────

function DraftTab({
  token,
  bookId,
  chapterId,
}: {
  token: string;
  bookId: string;
  chapterId: string;
}) {
  const [body, setBody] = useState('');
  const [editorKey, setEditorKey] = useState(0);
  const [version, setVersion] = useState<number | undefined>(undefined);
  const [commitMsg, setCommitMsg] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isDirty, setIsDirty] = useState(false);
  const [savedOk, setSavedOk] = useState(false);
  const [error, setError] = useState('');
  const savedBodyRef = useRef('');

  useEffect(() => {
    setIsLoading(true);
    booksApi
      .getDraft(token, bookId, chapterId)
      .then((d) => {
        setBody(d.body);
        savedBodyRef.current = d.body;
        setVersion(d.draft_version);
        setEditorKey((k) => k + 1);
        setIsDirty(false);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setIsLoading(false));
  }, [token, bookId, chapterId]);

  const handleChange = (newBody: string) => {
    setBody(newBody);
    setIsDirty(newBody !== savedBodyRef.current);
  };

  const save = async (e: FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setError('');
    try {
      await booksApi.patchDraft(token, bookId, chapterId, {
        body,
        commit_message: commitMsg || undefined,
        expected_draft_version: version,
      });
      savedBodyRef.current = body;
      setCommitMsg('');
      setIsDirty(false);
      setSavedOk(true);
      setTimeout(() => setSavedOk(false), 2500);
      // Refresh version number
      const d = await booksApi.getDraft(token, bookId, chapterId);
      setVersion(d.draft_version);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex h-full flex-col gap-3 p-4">
        <Skeleton className="flex-1 w-full rounded-md" />
        <Skeleton className="h-9 w-full rounded-md" />
      </div>
    );
  }

  return (
    <form onSubmit={(e) => void save(e)} className="flex h-full flex-col">
      {/* Editor area */}
      <div className="flex-1 overflow-auto p-4">
        <LexicalPlainEditor key={editorKey} initialValue={body} onChange={handleChange} />
      </div>

      {/* Footer bar */}
      <div className="flex shrink-0 items-center gap-2 border-t bg-background px-4 py-2">
        {isDirty && (
          <span className="text-xs text-amber-500 dark:text-amber-400">Unsaved changes</span>
        )}
        <input
          className="flex-1 rounded-md border border-input bg-background px-3 py-1.5 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
          placeholder="Commit message (optional)"
          value={commitMsg}
          onChange={(e) => setCommitMsg(e.target.value)}
        />
        <Button type="submit" size="sm" disabled={isSaving || (!isDirty && !commitMsg)}>
          <Save className="mr-1.5 h-3.5 w-3.5" />
          {isSaving ? 'Saving…' : savedOk ? 'Saved!' : 'Save draft'}
        </Button>
        {error && <p className="text-xs text-destructive">{error}</p>}
      </div>
    </form>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Translations tab
// ─────────────────────────────────────────────────────────────────────────────

function TranslationsTab({
  token,
  bookId,
  chapterId,
  chapter,
  translateOpen,
  onTranslateClose,
  settings,
  onTranslateJobCreated,
}: {
  token: string;
  bookId: string;
  chapterId: string;
  chapter: Chapter | null;
  translateOpen: boolean;
  onTranslateClose: () => void;
  settings: BookTranslationSettings | null;
  onTranslateJobCreated: (job: TranslationJob) => void;
}) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [languages, setLanguages] = useState<LanguageVersionGroup[]>([]);
  const [loading, setLoading] = useState(true);
  const [compareMode, setCompareMode] = useState(false);
  const [localTranslateOpen, setLocalTranslateOpen] = useState(false);

  const selectedLang = searchParams.get('lang') ?? null;
  const selectedVersionId = searchParams.get('vid') ?? null;

  const loadVersions = useCallback(async () => {
    setLoading(true);
    try {
      const resp = await versionsApi.listChapterVersions(token, chapterId);
      setLanguages(resp.languages);
      // Auto-select best language if none selected
      if (!searchParams.get('lang') && resp.languages.length > 0) {
        const best = resp.languages.reduce((a, b) =>
          b.versions.length > a.versions.length ? b : a,
        );
        setSearchParams(
          (p) => { p.set('lang', best.target_language); return p; },
          { replace: true },
        );
      }
    } finally {
      setLoading(false);
    }
  }, [token, chapterId]);

  useEffect(() => { void loadVersions(); }, [loadVersions]);

  // Auto-select active version when language changes
  useEffect(() => {
    if (!selectedLang) return;
    const group = languages.find((g) => g.target_language === selectedLang);
    if (!group || group.versions.length === 0) return;
    const currentVid = searchParams.get('vid');
    if (currentVid && group.versions.some((v) => v.id === currentVid)) return;
    const activeVer = group.versions.find((v) => v.is_active) ?? group.versions[0];
    setSearchParams((p) => { p.set('vid', activeVer.id); return p; }, { replace: true });
  }, [selectedLang, languages]);

  // Refresh on job completion
  const handleJobEvent = useCallback((e: JobEvent) => {
    if (e.job_type !== 'translation' || e.event !== 'job.chapter_done') return;
    const payload = e.payload as { chapter_id?: string };
    if (payload.chapter_id === chapterId) {
      versionsApi.listChapterVersions(token, chapterId)
        .then((r) => setLanguages(r.languages))
        .catch(() => {});
    }
  }, [token, chapterId]);

  const handleReconnect = useCallback(() => {
    versionsApi.listChapterVersions(token, chapterId)
      .then((r) => setLanguages(r.languages))
      .catch(() => {});
  }, [token, chapterId]);

  useJobEvents({ onEvent: handleJobEvent, onReconnect: handleReconnect });

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
          ? {
              ...g,
              active_id: versionId,
              versions: g.versions.map((v) => ({ ...v, is_active: v.id === versionId })),
            }
          : g,
      ),
    );
  }

  const currentGroup = languages.find((g) => g.target_language === selectedLang) ?? null;
  const currentVersion: VersionSummary | null =
    currentGroup?.versions.find((v) => v.id === selectedVersionId) ??
    currentGroup?.versions[0] ??
    null;
  const isActiveVersion = currentVersion?.is_active ?? false;

  const openTranslate = () => setLocalTranslateOpen(true);
  const showTranslateModal = (translateOpen || localTranslateOpen) && settings;

  if (loading) {
    return (
      <div className="flex h-full gap-4 p-4">
        <Skeleton className="h-full w-52 shrink-0 rounded-md" />
        <Skeleton className="h-full flex-1 rounded-md" />
      </div>
    );
  }

  return (
    <div className="flex h-full gap-4 overflow-hidden p-4">
      {/* Sidebar */}
      <div className="w-52 shrink-0 overflow-y-auto">
        <VersionSidebar
          languages={languages}
          selectedLang={selectedLang}
          onLangChange={handleLangChange}
          selectedVersionId={selectedVersionId}
          onVersionSelect={handleVersionSelect}
          onRetranslate={openTranslate}
          originalLanguage={chapter?.original_language}
        />
      </div>

      {/* Content area */}
      <div className="flex flex-1 flex-col overflow-auto">
        {selectedLang === null || currentVersion === null ? (
          <OriginalDraftViewer token={token} bookId={bookId} chapterId={chapterId} />
        ) : compareMode ? (
          <>
            <SplitCompareView
              token={token}
              bookId={bookId}
              chapterId={chapterId}
              version={currentVersion}
              originalLanguage={chapter?.original_language}
            />
            <button
              onClick={() => setCompareMode(false)}
              className="mt-2 text-sm text-muted-foreground hover:underline"
            >
              Exit compare
            </button>
          </>
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
      </div>

      {/* Translate modal */}
      {showTranslateModal && (
        <TranslateModal
          token={token}
          bookId={bookId}
          chapterIds={[chapterId]}
          settings={settings!}
          onClose={() => {
            setLocalTranslateOpen(false);
            onTranslateClose();
          }}
          onJobCreated={(job) => {
            setLocalTranslateOpen(false);
            onTranslateJobCreated(job);
            void loadVersions();
          }}
        />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Revisions tab
// ─────────────────────────────────────────────────────────────────────────────

type RevisionItem = { revision_id: string; created_at: string; message?: string };

function RevisionsTab({
  token,
  bookId,
  chapterId,
}: {
  token: string;
  bookId: string;
  chapterId: string;
}) {
  const [revisions, setRevisions] = useState<RevisionItem[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const pageSize = 15;
  const [preview, setPreview] = useState<(RevisionItem & { body: string }) | null>(null);
  const [loadingList, setLoadingList] = useState(true);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [isRestoring, setIsRestoring] = useState(false);
  const [error, setError] = useState('');

  const loadRevisions = useCallback(async () => {
    setLoadingList(true);
    try {
      const r = await booksApi.listRevisions(token, bookId, chapterId, {
        limit: pageSize,
        offset: (page - 1) * pageSize,
      });
      setRevisions(r.items);
      setTotal(r.total);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingList(false);
    }
  }, [token, bookId, chapterId, page]);

  useEffect(() => { void loadRevisions(); }, [loadRevisions]);

  const selectRevision = async (r: RevisionItem) => {
    if (preview?.revision_id === r.revision_id) return;
    setLoadingPreview(true);
    try {
      const detail = await booksApi.getRevision(token, bookId, chapterId, r.revision_id);
      setPreview({ ...r, body: detail.body });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoadingPreview(false);
    }
  };

  const restore = async () => {
    if (!preview) return;
    setIsRestoring(true);
    try {
      await booksApi.restoreRevision(token, bookId, chapterId, preview.revision_id);
      setPreview(null);
      await loadRevisions();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setIsRestoring(false);
    }
  };

  const totalPages = Math.ceil(total / pageSize);

  return (
    <div className="flex h-full gap-4 overflow-hidden p-4">
      {/* Left: revision list */}
      <div className="flex w-64 shrink-0 flex-col gap-1 overflow-y-auto">
        {loadingList ? (
          Array.from({ length: 8 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded-md" />
          ))
        ) : revisions.length === 0 ? (
          <p className="text-sm text-muted-foreground">No revisions yet. Save the draft to create one.</p>
        ) : (
          revisions.map((r) => (
            <button
              key={r.revision_id}
              onClick={() => void selectRevision(r)}
              className={`rounded-lg border p-3 text-left text-sm transition-colors hover:bg-muted ${
                preview?.revision_id === r.revision_id
                  ? 'border-primary bg-primary/5'
                  : 'border-transparent'
              }`}
            >
              <p className="font-mono text-xs tabular-nums text-foreground">
                {new Date(r.created_at).toLocaleString(undefined, {
                  month: 'short',
                  day: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
              {r.message && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{r.message}</p>
              )}
            </button>
          ))
        )}

        {/* Simple page nav */}
        {totalPages > 1 && (
          <div className="mt-2 flex items-center justify-between text-xs text-muted-foreground">
            <button
              disabled={page === 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded px-2 py-1 hover:bg-muted disabled:opacity-40"
            >
              ← Prev
            </button>
            <span>{page} / {totalPages}</span>
            <button
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded px-2 py-1 hover:bg-muted disabled:opacity-40"
            >
              Next →
            </button>
          </div>
        )}
      </div>

      {/* Right: preview */}
      <div className="flex flex-1 flex-col gap-3 overflow-hidden">
        {error && <p className="text-xs text-destructive">{error}</p>}

        {!preview && !loadingPreview ? (
          <div className="flex h-full items-center justify-center">
            <p className="text-sm text-muted-foreground">Select a revision to preview</p>
          </div>
        ) : loadingPreview ? (
          <Skeleton className="h-full w-full rounded-md" />
        ) : preview ? (
          <>
            <div className="flex shrink-0 items-center justify-between">
              <div>
                <p className="text-sm font-medium">
                  {new Date(preview.created_at).toLocaleString()}
                </p>
                {preview.message && (
                  <p className="text-xs text-muted-foreground">{preview.message}</p>
                )}
              </div>
              <Button
                size="sm"
                variant="outline"
                disabled={isRestoring}
                onClick={() => void restore()}
              >
                <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
                {isRestoring ? 'Restoring…' : 'Restore this revision'}
              </Button>
            </div>
            <div className="flex-1 overflow-auto whitespace-pre-wrap rounded-md border bg-muted p-4 text-sm leading-relaxed">
              {preview.body}
            </div>
          </>
        ) : null}
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Original draft viewer (used in Translations tab when lang = null)
// ─────────────────────────────────────────────────────────────────────────────

function OriginalDraftViewer({
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
    booksApi
      .getDraft(token, bookId, chapterId)
      .then((d) => setBody(d.body))
      .catch(() => setBody(null))
      .finally(() => setLoading(false));
  }, [token, bookId, chapterId]);

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!body) return <p className="text-sm text-muted-foreground">No draft content available.</p>;

  return (
    <div className="whitespace-pre-wrap rounded-md border bg-muted p-4 text-sm leading-relaxed">
      {body}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Lexical plain-text editor (shared)
// ─────────────────────────────────────────────────────────────────────────────

function LexicalPlainEditor({
  initialValue,
  onChange,
}: {
  initialValue: string;
  onChange: (value: string) => void;
}) {
  return (
    <LexicalComposer
      initialConfig={{
        namespace: 'chapter-editor-v2',
        onError: (err) => { throw err; },
        editorState: () => {
          const root = $getRoot();
          root.clear();
          const p = $createParagraphNode();
          p.append($createTextNode(initialValue || ''));
          root.append(p);
        },
      }}
    >
      <div className="min-h-[320px] rounded-md border focus-within:ring-1 focus-within:ring-ring">
        <PlainTextPlugin
          contentEditable={
            <ContentEditable className="min-h-[320px] whitespace-pre-wrap px-4 py-3 text-sm leading-relaxed outline-none" />
          }
          placeholder={
            <p className="pointer-events-none absolute px-4 py-3 text-sm text-muted-foreground">
              Write chapter draft here…
            </p>
          }
          ErrorBoundary={() => <></>}
        />
        <HistoryPlugin />
        <OnChangePlugin
          onChange={(editorState: EditorState) => {
            editorState.read(() => {
              onChange($getRoot().getTextContent());
            });
          }}
        />
      </div>
    </LexicalComposer>
  );
}
