import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Save, PanelLeft, PanelRight, Clock, ChevronRight, ChevronLeft, ChevronRight as ChevronRightNav, SpellCheck,
  BookOpen, FileText, BookMarked, Pen, Sparkles,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { useEditorPanels } from '@/hooks/useEditorPanels';
import { useEditorDirty } from '@/contexts/EditorDirtyContext';
import { RevisionHistory } from '@/components/editor/RevisionHistory';
import { TiptapEditor, type TiptapEditorHandle } from '@/components/editor/TiptapEditor';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { UnsavedChangesDialog } from '@/components/shared/UnsavedChangesDialog';
import { cn } from '@/lib/utils';
import { useGrammarEnabled } from '@/hooks/useGrammarCheck';
import { useEditorMode } from '@/hooks/useEditorMode';
import { setImageUploadContext } from '@/components/editor/ImageBlockNode';

function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export function ChapterEditorPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const panels = useEditorPanels();

  // Draft state
  const [version, setVersion] = useState<number | undefined>();
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState('');

  // Chapter metadata
  const [title, setTitle] = useState('');
  const [savedTitle, setSavedTitle] = useState('');

  // Editor content
  const [savedBody, setSavedBody] = useState<any>(null);
  const [tiptapJson, setTiptapJson] = useState<any>(null);
  const [textContent, setTextContent] = useState('');
  const tiptapEditorRef = useRef<TiptapEditorHandle>(null);

  // Editor mode + grammar
  const [editorMode, setEditorMode] = useEditorMode();
  const [grammarEnabled, setGrammarEnabled] = useGrammarEnabled();

  // Panels
  const [rightTab, setRightTab] = useState<'history' | 'ai'>('history');
  const [revKey, setRevKey] = useState(0);

  // Left sidebar
  const [leftTab, setLeftTab] = useState<'source' | 'chapters'>('chapters');
  const [originalContent, setOriginalContent] = useState<string | null>(null);
  const [originalLoading, setOriginalLoading] = useState(false);
  const [allChapters, setAllChapters] = useState<Chapter[]>([]);

  // Navigation
  const [prevChapterId, setPrevChapterId] = useState<string | undefined>();
  const [nextChapterId, setNextChapterId] = useState<string | undefined>();

  // Auto-save
  const autoSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const saveRef = useRef<() => Promise<void>>(async () => {});

  const { setIsDirty, guardedNavigate, pendingNavigation, confirmNavigation, cancelNavigation } = useEditorDirty();

  const bodyChanged = tiptapJson ? JSON.stringify(tiptapJson) !== JSON.stringify(savedBody) : false;
  const titleChanged = title !== savedTitle;
  const isDirty = bodyChanged || titleChanged;

  // Sync isDirty into context so EditorLayout sidebar can read it
  useEffect(() => {
    setIsDirty(isDirty);
    return () => setIsDirty(false);
  }, [isDirty, setIsDirty]);

  // Discard state for in-place cancel (no navigation)
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  const discardChanges = useCallback(() => {
    setTiptapJson(null);
    setTitle(savedTitle);
    tiptapEditorRef.current?.setContent(savedBody);
  }, [savedBody, savedTitle]);

  // ── Wire media upload context for image/video blocks ──────────────────────
  useEffect(() => {
    if (accessToken && bookId && chapterId) {
      setImageUploadContext({ token: accessToken, bookId, chapterId });
    }
    return () => setImageUploadContext(null);
  }, [accessToken, bookId, chapterId]);

  // ── Load ──────────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [draft, chapter] = await Promise.all([
        booksApi.getDraft(accessToken, bookId, chapterId),
        booksApi.getChapter(accessToken, bookId, chapterId),
      ]);
      setSavedBody(draft.body);
      setTextContent(draft.text_content ?? '');
      setTiptapJson(null);
      setVersion(draft.draft_version);
      const t = chapter.title ?? '';
      setTitle(t);
      setSavedTitle(t);
    } catch (e) { toast.error((e as Error).message); }
  }, [accessToken, bookId, chapterId]);

  useEffect(() => { void load(); }, [load]);

  // Load chapter list — used for prev/next nav and the Chapters sidebar tab
  useEffect(() => {
    if (!accessToken || !bookId || !chapterId) return;
    booksApi.listChapters(accessToken, bookId, { lifecycle_state: 'active', limit: 200, offset: 0 })
      .then((res) => {
        setAllChapters(res.items);
        const idx = res.items.findIndex((c) => c.chapter_id === chapterId);
        setPrevChapterId(idx > 0 ? res.items[idx - 1].chapter_id : undefined);
        setNextChapterId(idx >= 0 && idx < res.items.length - 1 ? res.items[idx + 1].chapter_id : undefined);
      })
      .catch(() => {});
  }, [accessToken, bookId, chapterId]);

  // Lazy-load original source when the Source tab is opened
  useEffect(() => {
    if (!panels.left || leftTab !== 'source' || originalContent !== null || originalLoading) return;
    if (!accessToken) return;
    setOriginalLoading(true);
    booksApi.getOriginalContent(accessToken, bookId, chapterId)
      .then((text) => setOriginalContent(text))
      .catch(() => setOriginalContent(''))
      .finally(() => setOriginalLoading(false));
  }, [panels.left, leftTab, accessToken, bookId, chapterId, originalContent, originalLoading]);

  // ── Save ──────────────────────────────────────────────────────────────────

  const save = useCallback(async () => {
    if (!accessToken) return;
    setSaving(true);
    if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
    try {
      const bodyToSave = tiptapJson ?? savedBody;
      try {
        await booksApi.patchDraft(accessToken, bookId, chapterId, {
          body: bodyToSave,
          body_format: 'json',
          commit_message: saveNote || undefined,
          expected_draft_version: version,
        });
      } catch (e) {
        // On version conflict, retry without version check (single-user, last-write-wins)
        if ((e as Error).message?.includes('stale draft version')) {
          await booksApi.patchDraft(accessToken, bookId, chapterId, {
            body: bodyToSave,
            body_format: 'json',
            commit_message: saveNote || undefined,
          });
        } else {
          throw e;
        }
      }
      if (title !== savedTitle) {
        await booksApi.patchChapter(accessToken, bookId, chapterId, { title: title || null });
      }
      setSaveNote('');
      toast.success('Chapter saved');
      setRevKey((k) => k + 1);
      await load();
    } catch (e) { toast.error((e as Error).message); }
    setSaving(false);
  }, [accessToken, bookId, chapterId, tiptapJson, savedBody, saveNote, version, title, savedTitle, load]);

  // Keep ref current so auto-save always calls the latest version
  useEffect(() => { saveRef.current = save; }, [save]);

  // ── Auto-save (5 minutes after last change) ─────────────────────────────

  useEffect(() => {
    if (!isDirty) {
      if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
      return;
    }
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => { void saveRef.current(); }, 300_000);
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [isDirty, tiptapJson, title]);

  // ── Leave-page guard ──────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: BeforeUnloadEvent) => {
      if (isDirty) { e.preventDefault(); e.returnValue = ''; }
    };
    window.addEventListener('beforeunload', handler);
    return () => window.removeEventListener('beforeunload', handler);
  }, [isDirty]);

  // ── Ctrl+S shortcut ───────────────────────────────────────────────────────

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [save]);

  // ── Chapter navigation (with unsaved-changes guard) ──────────────────────

  const navigateToChapter = (targetId: string) => {
    if (targetId === chapterId) return;
    guardedNavigate(`/books/${bookId}/chapters/${targetId}/edit`);
  };

  // ── Stats ─────────────────────────────────────────────────────────────────

  const wc = wordCount(textContent);
  const charCount = textContent.length;
  const paraCount = textContent ? textContent.split(/\n\n+/).filter(Boolean).length : 0;
  const chapterLang = allChapters.find((c) => c.chapter_id === chapterId)?.original_language;

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* ── Toolbar ──────────────────────────────────────────────────────── */}
      <div className="flex h-[42px] flex-shrink-0 items-center justify-between border-b bg-card px-4">

        {/* Breadcrumb + prev/next */}
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          {prevChapterId && (
            <button
              onClick={() => navigateToChapter(prevChapterId)}
              className="rounded p-1 hover:bg-secondary hover:text-foreground"
              title="Previous chapter"
            >
              <ChevronLeft className="h-3 w-3" />
            </button>
          )}
          <button onClick={() => guardedNavigate('/books')} className="hover:text-foreground">Workspace</button>
          <ChevronRight className="h-3 w-3" />
          <button onClick={() => guardedNavigate(`/books/${bookId}`)} className="hover:text-foreground">Book</button>
          <ChevronRight className="h-3 w-3" />
          <span className="font-medium text-foreground">{title || 'Chapter'}</span>
          {nextChapterId && (
            <button
              onClick={() => navigateToChapter(nextChapterId)}
              className="rounded p-1 hover:bg-secondary hover:text-foreground"
              title="Next chapter"
            >
              <ChevronRightNav className="h-3 w-3" />
            </button>
          )}
        </div>

        {/* Right controls */}
        <div className="flex flex-shrink-0 items-center gap-2">
          {/* Editor mode toggle */}
          <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
            <button
              onClick={() => setEditorMode('classic')}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                editorMode === 'classic'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              title="Classic mode — focused writing"
            >
              <Pen className="h-3 w-3" />
              Classic
            </button>
            <button
              onClick={() => setEditorMode('ai')}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                editorMode === 'ai'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              title="AI Assistant mode — full features"
            >
              <Sparkles className="h-3 w-3" />
              AI
            </button>
          </div>

          <div className="mx-1 h-4 w-px bg-border" />

          {/* Grammar check toggle */}
          <label
            className={cn(
              'flex cursor-pointer items-center gap-1.5 rounded px-2 py-1 text-[10px] font-medium transition-colors',
              grammarEnabled ? 'text-warning' : 'text-muted-foreground hover:text-foreground',
            )}
            title="Toggle grammar & spell check (LanguageTool)"
          >
            <input
              type="checkbox"
              checked={grammarEnabled}
              onChange={(e) => setGrammarEnabled(e.target.checked)}
              className="sr-only"
            />
            <SpellCheck className="h-3.5 w-3.5" />
          </label>

          <button
            onClick={panels.toggleLeft}
            className={cn('rounded p-1.5 transition-colors', panels.left ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
            title="Toggle source panel"
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={panels.toggleRight}
            className={cn('rounded p-1.5 transition-colors', panels.right ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
            title="Toggle history / AI panel"
          >
            <PanelRight className="h-3.5 w-3.5" />
          </button>
          <div className="mx-1 h-4 w-px bg-border" />

          {/* Save status */}
          {isDirty ? (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-warning/12 px-2 py-0.5 text-[10px] font-medium text-warning">
              <span className="h-1.5 w-1.5 rounded-full bg-warning" />
              Unsaved
            </span>
          ) : (
            <span className="inline-flex items-center gap-1.5 rounded-full bg-success/12 px-2 py-0.5 text-[10px] font-medium text-success">
              <span className="h-1.5 w-1.5 rounded-full bg-success" />
              Saved
            </span>
          )}
          <span className="text-[10px] font-mono text-muted-foreground">v{version ?? '?'}</span>

          {isDirty && (
            <button
              onClick={() => setShowDiscardConfirm(true)}
              className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-destructive/50 hover:text-destructive"
              title="Discard all unsaved changes"
            >
              Discard
            </button>
          )}

          <button
            onClick={() => void save()}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            <Save className="h-3 w-3" />
            Save
            <kbd className="ml-1 rounded border border-primary-foreground/20 bg-primary-foreground/10 px-1 py-px font-mono text-[9px]">Ctrl+S</kbd>
          </button>
        </div>
      </div>


      {/* ── Panel area ────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* Left panel */}
        {panels.left && (
          <div className="flex w-[300px] flex-shrink-0 flex-col border-r bg-card">
            {/* Tab bar */}
            <div className="flex border-b">
              <button
                onClick={() => setLeftTab('chapters')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'chapters' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <BookOpen className="h-3 w-3" />Chapters
              </button>
              <button
                onClick={() => setLeftTab('source')}
                className={cn(
                  'flex flex-1 items-center justify-center gap-1.5 px-3 py-2 text-xs font-medium transition-colors',
                  leftTab === 'source' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground',
                )}
              >
                <FileText className="h-3 w-3" />Original
              </button>
              <button
                className="flex flex-1 cursor-not-allowed items-center justify-center gap-1.5 px-3 py-2 text-xs text-muted-foreground/35"
                title="Glossary integration — coming soon"
                disabled
              >
                <BookMarked className="h-3 w-3" />Glossary
              </button>
            </div>

            {/* ── Chapters tab ─────────────────────────────────────────── */}
            {leftTab === 'chapters' && (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
                  {allChapters.length} chapter{allChapters.length !== 1 ? 's' : ''}
                </div>
                <div className="flex-1 overflow-y-auto">
                  {allChapters.length === 0 && (
                    <div className="space-y-1.5 p-3">
                      <Skeleton className="h-6 w-full" />
                      <Skeleton className="h-6 w-4/5" />
                      <Skeleton className="h-6 w-full" />
                    </div>
                  )}
                  {allChapters.map((ch, i) => (
                    <button
                      key={ch.chapter_id}
                      onClick={() => navigateToChapter(ch.chapter_id)}
                      className={cn(
                        'flex w-full items-start gap-2 border-b px-3 py-2.5 text-left transition-colors',
                        ch.chapter_id === chapterId
                          ? 'border-l-2 border-l-primary bg-primary/[0.07] text-primary'
                          : 'text-muted-foreground hover:bg-secondary/50 hover:text-foreground',
                      )}
                    >
                      <span className="mt-0.5 w-5 flex-shrink-0 text-right font-mono text-[10px] opacity-50">
                        {i + 1}
                      </span>
                      <span className="flex-1 text-xs leading-[1.5]">
                        {ch.title || ch.original_filename}
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* ── Original source tab ───────────────────────────────────── */}
            {leftTab === 'source' && (
              <div className="flex flex-1 flex-col overflow-hidden">
                <div className="flex-shrink-0 border-b px-3 py-2 text-[10px] text-muted-foreground">
                  Original uploaded text — read only
                </div>
                <div className="flex-1 overflow-y-auto p-3">
                  {originalLoading ? (
                    <div className="space-y-2">
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-5/6" />
                      <Skeleton className="h-3 w-full" />
                      <Skeleton className="h-3 w-4/5" />
                      <Skeleton className="h-3 w-full" />
                    </div>
                  ) : originalContent ? (
                    <div className="space-y-0">
                      {originalContent.split(/\n\n+/).filter(Boolean).map((line, i) => (
                        <div key={i} className="flex gap-2 border-b border-border/30 px-3 py-1.5">
                          <span className="w-5 flex-shrink-0 text-right font-mono text-[10px] text-muted-foreground/50">{i + 1}</span>
                          <p className="text-xs leading-[1.75] text-foreground/70">{line}</p>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <p className="text-[10px] italic text-muted-foreground">
                      No original source — this chapter was created directly in the editor (no file was imported).
                    </p>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Center — editor */}
        <div className="relative flex flex-1 flex-col overflow-hidden bg-background">

          {/* Title + metadata bar */}
          <div className="flex-shrink-0 border-b px-6 pt-4 pb-3">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-transparent font-serif text-xl font-semibold outline-none placeholder:text-muted-foreground/30"
              placeholder="Chapter title"
            />
            <div className="mt-1.5 flex items-center gap-2 text-[10px] text-muted-foreground">
              {chapterLang && (
                <>
                  <span>{chapterLang} <span className="font-mono opacity-60">({chapterLang})</span></span>
                  <span className="text-border">|</span>
                </>
              )}
              <span>{charCount.toLocaleString()} chars</span>
              <span className="text-border">|</span>
              <span>{wc.toLocaleString()} words</span>
              <span className="text-border">|</span>
              <span>{paraCount} paragraph{paraCount !== 1 ? 's' : ''}</span>
            </div>
          </div>

          {/* Tiptap editor */}
          <TiptapEditor
            ref={tiptapEditorRef}
            content={savedBody}
            onUpdate={(json) => setTiptapJson(json)}
            grammarEnabled={grammarEnabled}
            editorMode={editorMode}
            className="flex-1 overflow-y-auto"
          />

          {/* Save note */}
          <div className="flex-shrink-0 border-t px-4 py-2">
            <input
              value={saveNote}
              onChange={(e) => setSaveNote(e.target.value)}
              placeholder="Save note (optional) — e.g. &quot;added flashback scene&quot;"
              className="w-full rounded border bg-background px-3 py-1.5 text-xs placeholder:text-muted-foreground/40 focus:outline-none focus:ring-1 focus:ring-ring/40"
            />
          </div>
        </div>

        {/* Right panel */}
        {panels.right && (
          <div className="flex w-[300px] flex-shrink-0 flex-col border-l bg-card">
            <div className="flex border-b">
              <button
                onClick={() => setRightTab('history')}
                className={cn('flex-1 px-3 py-2 text-xs font-medium', rightTab === 'history' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground hover:text-foreground')}
              >
                <Clock className="mr-1.5 inline h-3 w-3" />History
              </button>
              <button
                onClick={() => setRightTab('ai')}
                className={cn('flex-1 cursor-not-allowed px-3 py-2 text-xs text-muted-foreground/40')}
                title="Coming soon"
                disabled
              >
                AI Chat
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              {rightTab === 'history' && (
                <RevisionHistory key={revKey} bookId={bookId} chapterId={chapterId} onRestore={() => void load()} />
              )}
            </div>
          </div>
        )}
      </div>

      {/* ── Status bar ───────────────────────────────────────────────────── */}
      <div className="flex h-6 flex-shrink-0 items-center justify-between border-t px-3 text-[10px] text-muted-foreground" style={{ background: 'rgba(24,20,18,0.6)' }}>
        <div className="flex items-center gap-3">
          <span className="inline-flex items-center gap-1">
            <span className="h-1.5 w-1.5 rounded-full bg-success" />
            Connected
          </span>
          {chapterLang && <span>{chapterLang}</span>}
          <span>{wc.toLocaleString()} words</span>
        </div>
        <div className="flex items-center gap-3">
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+B</kbd> Left panel</span>
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+J</kbd> Right panel</span>
          <span><kbd className="rounded border border-border bg-secondary px-1 py-px font-mono text-[9px]">Ctrl+S</kbd> Save</span>
        </div>
      </div>

      {/* In-place discard confirm */}
      <ConfirmDialog
        open={showDiscardConfirm}
        onOpenChange={setShowDiscardConfirm}
        title="Discard changes?"
        description="All unsaved changes will be permanently lost. This cannot be undone."
        confirmLabel="Discard changes"
        cancelLabel="Keep editing"
        variant="destructive"
        onConfirm={() => { discardChanges(); setShowDiscardConfirm(false); }}
      />

      {/* Navigation guard — shown when trying to leave with unsaved changes */}
      <UnsavedChangesDialog
        open={pendingNavigation !== null}
        onOpenChange={(open) => { if (!open) cancelNavigation(); }}
        onSave={async () => { await save(); confirmNavigation(); }}
        onDiscard={() => { discardChanges(); confirmNavigation(); }}
        saving={saving}
      />
    </div>
  );
}
