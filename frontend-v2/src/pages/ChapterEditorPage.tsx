import React, { useEffect, useState, useCallback, useRef } from 'react';
import { useParams } from 'react-router-dom';
import { toast } from 'sonner';
import {
  Save, PanelLeft, PanelRight, Clock, ChevronRight, ChevronLeft, ChevronRight as ChevronRightNav, SpellCheck,
  BookOpen, FileText, BookMarked, LayoutList, ScrollText, Scissors, Plus, X,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi, type Chapter } from '@/features/books/api';
import { useChunks } from '@/hooks/useChunks';
import { useEditorPanels } from '@/hooks/useEditorPanels';
import { useEditorDirty } from '@/contexts/EditorDirtyContext';
import { ChunkItem } from '@/components/editor/ChunkItem';
import { ChunkInsertRow } from '@/components/editor/ChunkInsertRow';
import { RevisionHistory } from '@/components/editor/RevisionHistory';
import { Skeleton } from '@/components/shared/Skeleton';
import { ConfirmDialog } from '@/components/shared/ConfirmDialog';
import { UnsavedChangesDialog } from '@/components/shared/UnsavedChangesDialog';
import { cn } from '@/lib/utils';
import { useGrammarEnabled, useGrammarCheck, useSourceGrammarCheck } from '@/hooks/useGrammarCheck';

type ViewMode = 'chunk' | 'source';

function wordCount(text: string): number {
  return text.trim() ? text.trim().split(/\s+/).length : 0;
}

export function ChapterEditorPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const panels = useEditorPanels();

  // Draft state
  const [body, setBody] = useState('');
  const [version, setVersion] = useState<number | undefined>();
  const [saving, setSaving] = useState(false);
  const [saveNote, setSaveNote] = useState('');

  // Chapter metadata
  const [title, setTitle] = useState('');
  const [savedTitle, setSavedTitle] = useState('');

  // View / panels
  const [viewMode, setViewMode] = useState<ViewMode>('source');
  const [sourceBody, setSourceBody] = useState('');

  // Grammar check
  const [grammarEnabled, setGrammarEnabled] = useGrammarEnabled();
  const grammar = useGrammarCheck(grammarEnabled);
  const sourceRef = React.useRef<HTMLTextAreaElement>(null);
  const sourceGrammar = useSourceGrammarCheck(sourceBody, sourceRef, grammarEnabled);
  const [savedBody, setSavedBody] = useState('');
  const [rightTab, setRightTab] = useState<'history' | 'ai'>('history');
  const [revKey, setRevKey] = useState(0);

  // Auto-chunk preview (source mode only)
  const [autoChunkPreview, setAutoChunkPreview] = useState<string[] | null>(null);

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

  // Newly inserted chunk index for auto-focus
  const [focusIndex, setFocusIndex] = useState<number | null>(null);

  const chunks = useChunks(body);
  const { setIsDirty, guardedNavigate, pendingNavigation, confirmNavigation, cancelNavigation } = useEditorDirty();

  const isDirty = viewMode === 'source'
    ? sourceBody !== savedBody
    : chunks.isDirty || title !== savedTitle;

  // Sync isDirty into context so EditorLayout sidebar can read it
  useEffect(() => {
    setIsDirty(isDirty);
    return () => setIsDirty(false);
  }, [isDirty, setIsDirty]);

  // Discard state for in-place cancel (no navigation)
  const [showDiscardConfirm, setShowDiscardConfirm] = useState(false);

  const discardChanges = useCallback(() => {
    setSourceBody(savedBody);
    setTitle(savedTitle);
    if (viewMode === 'chunk') chunks.reset(savedBody);
  }, [savedBody, savedTitle, viewMode, chunks]);

  // ── Load ──────────────────────────────────────────────────────────────────

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const [draft, chapter] = await Promise.all([
        booksApi.getDraft(accessToken, bookId, chapterId),
        booksApi.getChapter(accessToken, bookId, chapterId),
      ]);
      setBody(draft.body);
      setSourceBody(draft.body);
      setSavedBody(draft.body);
      chunks.reset(draft.body);
      setVersion(draft.draft_version);
      const t = chapter.title ?? '';
      setTitle(t);
      setSavedTitle(t);
    } catch (e) { toast.error((e as Error).message); }
  }, [accessToken, bookId, chapterId]);

  useEffect(() => { void load(); }, [load]);

  // Run grammar check on initial load
  const initialGrammarDone = useRef(false);
  useEffect(() => {
    if (!grammarEnabled || !body || initialGrammarDone.current) return;
    initialGrammarDone.current = true;
    const paragraphs = body.split(/\n\n+/).map((t) => t.trim()).filter(Boolean);
    void grammar.checkAll(paragraphs.map((text, i) => ({ index: i, text })));
  }, [body, grammarEnabled, grammar]);

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

  // ── Mode switch ───────────────────────────────────────────────────────────

  const switchMode = (mode: ViewMode) => {
    if (mode === viewMode) return;
    if (mode === 'source') {
      setSourceBody(chunks.reassemble());
    } else {
      chunks.reset(sourceBody);
    }
    grammar.clear();
    sourceGrammar.clear();
    setViewMode(mode);
  };

  // ── Save ──────────────────────────────────────────────────────────────────

  const save = useCallback(async () => {
    if (!accessToken) return;
    setSaving(true);
    if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
    try {
      const bodyToSave = viewMode === 'source' ? sourceBody : chunks.reassemble();
      await booksApi.patchDraft(accessToken, bookId, chapterId, {
        body: bodyToSave,
        commit_message: saveNote || undefined,
        expected_draft_version: version,
      });
      if (title !== savedTitle) {
        await booksApi.patchChapter(accessToken, bookId, chapterId, { title: title || null });
      }
      setSaveNote('');
      toast.success('Chapter saved');
      setRevKey((k) => k + 1);
      await load();
    } catch (e) { toast.error((e as Error).message); }
    setSaving(false);
  }, [accessToken, bookId, chapterId, viewMode, sourceBody, chunks, saveNote, version, title, savedTitle, load]);

  // Keep ref current so auto-save always calls the latest version
  useEffect(() => { saveRef.current = save; }, [save]);

  // ── Auto-save (30 s after last change) ───────────────────────────────────

  useEffect(() => {
    if (!isDirty) {
      if (autoSaveTimer.current) { clearTimeout(autoSaveTimer.current); autoSaveTimer.current = null; }
      return;
    }
    if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current);
    autoSaveTimer.current = setTimeout(() => { void saveRef.current(); }, 30_000);
    return () => { if (autoSaveTimer.current) clearTimeout(autoSaveTimer.current); };
  }, [isDirty, viewMode, sourceBody, title]);

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

  // ── Chunk insert helper ───────────────────────────────────────────────────

  const handleDeleteChunk = (index: number) => {
    chunks.deleteChunk(index);
    grammar.clear();
  };

  const handleInsertChunk = (position: number) => {
    chunks.insertChunk(position);
    setFocusIndex(position);
    grammar.clear();
    requestAnimationFrame(() => setFocusIndex(null));
  };

  // ── Chapter navigation (with unsaved-changes guard) ──────────────────────

  const navigateToChapter = (targetId: string) => {
    if (targetId === chapterId) return;
    guardedNavigate(`/books/${bookId}/chapters/${targetId}/edit`);
  };

  // ── Auto-chunk (source → chunk preview) ──────────────────────────────────

  const sourceParagraphs = sourceBody.split(/\n\n+/).map((t) => t.trim()).filter(Boolean);

  const openAutoChunkPreview = () => {
    // Always open — even if only 1 paragraph, the preview explains how blank lines work
    const paragraphs = sourceParagraphs.length > 0 ? sourceParagraphs : [''];
    setAutoChunkPreview(paragraphs);
  };

  const applyAutoChunk = () => {
    setAutoChunkPreview(null);
    switchMode('chunk');   // syncs chunks.reset(sourceBody) internally
  };

  const cancelAutoChunk = () => setAutoChunkPreview(null);

  // ── Word count display ────────────────────────────────────────────────────

  const currentBody = viewMode === 'source' ? sourceBody : chunks.reassemble();
  const wc = wordCount(currentBody);
  const totalGrammarIssues = viewMode === 'source' ? sourceGrammar.totalIssues : grammar.totalIssues;

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
        <div className="flex items-center gap-2">
          {/* View mode toggle */}
          <div className="flex items-center rounded-md border bg-muted/30 p-0.5">
            <button
              onClick={() => switchMode('chunk')}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                viewMode === 'chunk'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              title="Chunk mode — edit paragraph by paragraph"
            >
              <LayoutList className="h-3 w-3" />
              Chunks
            </button>
            <button
              onClick={() => switchMode('source')}
              className={cn(
                'flex items-center gap-1 rounded px-2 py-1 text-[10px] font-medium transition-colors',
                viewMode === 'source'
                  ? 'bg-background text-foreground shadow-sm'
                  : 'text-muted-foreground hover:text-foreground',
              )}
              title="Source mode — edit raw text directly"
            >
              <ScrollText className="h-3 w-3" />
              Source
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
            {grammarEnabled && totalGrammarIssues > 0 && (
              <span className="rounded-full bg-warning/20 px-1.5 py-px text-[9px] font-semibold text-warning">
                {totalGrammarIssues}
              </span>
            )}
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
            <span className="text-[10px] text-warning">Unsaved changes</span>
          ) : (
            <span className="text-[10px] text-muted-foreground">v{version ?? '?'}</span>
          )}

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
                    <p
                      className="text-xs leading-[1.75] text-foreground/70"
                      style={{ whiteSpace: 'pre-wrap' }}
                    >
                      {originalContent}
                    </p>
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
            <div className="mt-1.5 flex items-center gap-3">
              <p className="text-[10px] text-muted-foreground">
                {wc.toLocaleString()} words
                {viewMode === 'chunk' && (
                  <> · {chunks.chunks.length} paragraphs
                    {chunks.selected.size > 0 && ` · ${chunks.selected.size} selected`}
                  </>
                )}
                {' · '}
                {isDirty ? 'unsaved changes' : 'all saved'}
                {grammarEnabled && totalGrammarIssues > 0 && (
                  <>
                    {' · '}
                    <span className="text-warning">{totalGrammarIssues} grammar issue{totalGrammarIssues !== 1 ? 's' : ''}</span>
                  </>
                )}
              </p>

              {/* Auto-chunk button — always visible in source mode when there's text */}
              {viewMode === 'source' && sourceBody.trim().length > 0 && (
                <button
                  onClick={openAutoChunkPreview}
                  className="inline-flex items-center gap-1 rounded border border-dashed border-border px-2 py-0.5 text-[10px] text-muted-foreground transition-colors hover:border-primary/50 hover:text-primary"
                  title="Split text into paragraph chunks using blank lines as separators"
                >
                  <Scissors className="h-2.5 w-2.5" />
                  {sourceParagraphs.length > 1
                    ? `Split into ${sourceParagraphs.length} paragraphs`
                    : 'Split into paragraphs'}
                </button>
              )}
            </div>
          </div>

          {/* Content area */}
          {viewMode === 'chunk' ? (
            <div className="flex-1 overflow-y-auto px-4 py-2">
              <div className="flex flex-col">
                {/* Insert before first chunk */}
                <ChunkInsertRow onInsert={() => handleInsertChunk(0)} />

                {chunks.chunks.map((chunk, i) => (
                  <div key={chunk.index}>
                    <ChunkItem
                      index={chunk.index}
                      text={chunk.text}
                      selected={chunks.selected.has(chunk.index)}
                      autoFocus={focusIndex === chunk.index}
                      onSelect={chunks.toggleSelect}
                      onChange={chunks.updateChunk}
                      onDelete={handleDeleteChunk}
                      grammarMatches={grammar.results.get(chunk.index)}
                      onBlurGrammar={grammar.checkChunk}
                    />
                    {/* Insert after this chunk */}
                    <ChunkInsertRow onInsert={() => handleInsertChunk(i + 1)} />
                  </div>
                ))}

                {/* Quick add at the very bottom */}
                <button
                  onClick={() => handleInsertChunk(chunks.chunks.length)}
                  className="mt-1 flex w-full items-center justify-center gap-1.5 rounded-md border border-dashed border-border/50 py-2 text-[11px] text-muted-foreground/50 transition-colors hover:border-primary/40 hover:text-primary"
                >
                  <Plus className="h-3 w-3" />
                  Add paragraph
                </button>
              </div>
            </div>
          ) : (
            <textarea
              ref={sourceRef}
              value={sourceBody}
              onChange={(e) => setSourceBody(e.target.value)}
              className="flex-1 resize-none bg-transparent px-6 py-3 text-sm leading-[1.8] outline-none placeholder:text-muted-foreground/40"
              placeholder="Start writing..."
              spellCheck={false}
            />
          )}

          {/* Auto-chunk preview overlay — appears over the content area */}
          {autoChunkPreview && (
            <div className="absolute inset-0 z-10 flex flex-col bg-background">
              {/* Preview header */}
              <div className="flex flex-shrink-0 items-center justify-between border-b px-6 py-3">
                <div>
                  <p className="text-sm font-medium">
                    {autoChunkPreview.length > 1
                      ? `Split into ${autoChunkPreview.length} paragraphs`
                      : 'No paragraph breaks detected'}
                  </p>
                  {autoChunkPreview.length > 1 ? (
                    <p className="text-[10px] text-muted-foreground">
                      Review how your text will be divided. Apply to switch to chunk mode.
                    </p>
                  ) : (
                    <p className="text-[10px] text-muted-foreground">
                      Your text is one continuous block.{' '}
                      <span className="font-medium text-foreground">
                        Press Enter twice (blank line) between sections
                      </span>{' '}
                      to create paragraph boundaries, then click Split again.
                    </p>
                  )}
                </div>
                <button
                  onClick={cancelAutoChunk}
                  className="rounded p-1.5 text-muted-foreground hover:bg-secondary hover:text-foreground"
                  title="Cancel"
                >
                  <X className="h-4 w-4" />
                </button>
              </div>

              {/* Chunk preview list */}
              <div className="flex-1 overflow-y-auto px-6 py-3">
                <div className="flex flex-col gap-2">
                  {autoChunkPreview.map((text, i) => (
                    <div key={i} className="flex gap-3 rounded-md border border-border/40 px-3 py-2">
                      <span className="w-5 flex-shrink-0 pt-0.5 text-right font-mono text-[10px] text-muted-foreground/40">
                        {i + 1}
                      </span>
                      <p className="flex-1 text-sm leading-[1.7]" style={{ whiteSpace: 'pre-wrap' }}>
                        {text}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              {/* Actions */}
              <div className="flex flex-shrink-0 items-center justify-end gap-2 border-t px-6 py-3">
                <button
                  onClick={cancelAutoChunk}
                  className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary"
                >
                  Cancel — stay in source
                </button>
                <button
                  onClick={applyAutoChunk}
                  disabled={autoChunkPreview.length <= 1}
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  <LayoutList className="h-3.5 w-3.5" />
                  Apply — switch to chunk mode
                </button>
              </div>
            </div>
          )}

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

      {/* Bottom bar — chunk selection */}
      {viewMode === 'chunk' && chunks.selected.size > 0 && (
        <div className="flex h-9 flex-shrink-0 items-center justify-between border-t bg-card px-4 text-xs">
          <span className="text-muted-foreground">{chunks.selected.size} paragraph(s) selected</span>
          <button onClick={chunks.clearSelection} className="text-muted-foreground hover:text-foreground">
            Clear selection
          </button>
        </div>
      )}

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
