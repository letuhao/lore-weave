import { useEffect, useState, useCallback } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  Save, Check, PanelLeft, PanelRight, Clock, ChevronRight, BookOpen, FileText, BookMarked,
  LayoutList, ScrollText,
} from 'lucide-react';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { useChunks } from '@/hooks/useChunks';
import { useEditorPanels } from '@/hooks/useEditorPanels';
import { ChunkItem } from '@/components/editor/ChunkItem';
import { RevisionHistory } from '@/components/editor/RevisionHistory';
import { cn } from '@/lib/utils';

type ViewMode = 'chunk' | 'source';

export function ChapterEditorPage() {
  const { bookId = '', chapterId = '' } = useParams();
  const { accessToken } = useAuth();
  const panels = useEditorPanels();
  const [body, setBody] = useState('');
  const [version, setVersion] = useState<number | undefined>();
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [title, setTitle] = useState('');
  const [rightTab, setRightTab] = useState<'history' | 'ai'>('history');
  const [revKey, setRevKey] = useState(0);

  const [viewMode, setViewMode] = useState<ViewMode>('chunk');
  const [sourceBody, setSourceBody] = useState('');
  const [savedBody, setSavedBody] = useState('');

  const chunks = useChunks(body);

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const d = await booksApi.getDraft(accessToken, bookId, chapterId);
      setBody(d.body);
      setSourceBody(d.body);
      setSavedBody(d.body);
      chunks.reset(d.body);
      setVersion(d.draft_version);
      setTitle((d as Record<string, unknown>).title as string ?? '');
      setError('');
    } catch (e) { setError((e as Error).message); }
  }, [accessToken, bookId, chapterId]);

  useEffect(() => { void load(); }, [load]);

  const switchMode = (mode: ViewMode) => {
    if (mode === viewMode) return;
    if (mode === 'source') {
      setSourceBody(chunks.reassemble());
    } else {
      chunks.reset(sourceBody);
    }
    setViewMode(mode);
  };

  const isDirty = viewMode === 'source'
    ? sourceBody !== savedBody
    : chunks.isDirty;

  const save = async () => {
    if (!accessToken) return;
    setSaving(true);
    try {
      const bodyToSave = viewMode === 'source' ? sourceBody : chunks.reassemble();
      await booksApi.patchDraft(accessToken, bookId, chapterId, {
        body: bodyToSave,
        commit_message: message || undefined,
        expected_draft_version: version,
      });
      setMessage('');
      setSaved(true);
      setTimeout(() => setSaved(false), 2000);
      setRevKey((k) => k + 1);
      await load();
    } catch (e) { setError((e as Error).message); }
    setSaving(false);
  };

  // Ctrl+S shortcut
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 's') {
        e.preventDefault();
        void save();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [chunks, sourceBody, viewMode, version, message]);

  return (
    <div className="flex h-full flex-col overflow-hidden">
      {/* Toolbar */}
      <div className="flex h-[42px] flex-shrink-0 items-center justify-between border-b bg-card px-4">
        <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
          <Link to="/books" className="hover:text-foreground">Workspace</Link>
          <ChevronRight className="h-3 w-3" />
          <Link to={`/books/${bookId}`} className="hover:text-foreground">Book</Link>
          <ChevronRight className="h-3 w-3" />
          <span className="font-medium text-foreground">{title || 'Chapter'}</span>
        </div>
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

          <button
            onClick={panels.toggleLeft}
            className={cn('rounded p-1.5 transition-colors', panels.left ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
            title="Toggle left panel (Ctrl+B)"
          >
            <PanelLeft className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={panels.toggleRight}
            className={cn('rounded p-1.5 transition-colors', panels.right ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:bg-secondary')}
            title="Toggle right panel (Ctrl+J)"
          >
            <PanelRight className="h-3.5 w-3.5" />
          </button>
          <div className="mx-1 h-4 w-px bg-border" />
          {saved ? (
            <span className="inline-flex items-center gap-1 rounded-full bg-success/10 px-2 py-0.5 text-[10px] font-medium text-success">
              <Check className="h-3 w-3" /> Saved
            </span>
          ) : isDirty ? (
            <span className="text-[10px] text-warning">Unsaved changes</span>
          ) : (
            <span className="text-[10px] text-muted-foreground">v{version ?? '?'}</span>
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

      {error && <div className="border-b bg-destructive/5 px-4 py-2 text-xs text-destructive">{error}</div>}

      {/* Panel area */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left panel */}
        {panels.left && (
          <div className="flex w-[300px] flex-shrink-0 flex-col border-r bg-card">
            <div className="flex border-b">
              <button className="flex-1 border-b-2 border-primary px-3 py-2 text-xs font-medium text-primary">
                <FileText className="mr-1.5 inline h-3 w-3" />Source
              </button>
              <button className="flex-1 px-3 py-2 text-xs text-muted-foreground hover:text-foreground">
                <BookOpen className="mr-1.5 inline h-3 w-3" />Chapters
              </button>
              <button className="flex-1 px-3 py-2 text-xs text-muted-foreground hover:text-foreground">
                <BookMarked className="mr-1.5 inline h-3 w-3" />Glossary
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-3 text-xs text-muted-foreground">
              <p className="italic">Source text panel — will show original text synced with editor chunks.</p>
            </div>
          </div>
        )}

        {/* Center — editor */}
        <div className="flex flex-1 flex-col overflow-hidden bg-background">
          <div className="flex-shrink-0 px-6 pt-4">
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              className="w-full bg-transparent font-serif text-xl font-semibold outline-none"
              placeholder="Chapter title"
            />
            <p className="mt-1 text-[10px] text-muted-foreground">
              {viewMode === 'chunk'
                ? `${chunks.chunks.length} paragraphs${chunks.selected.size > 0 ? ` · ${chunks.selected.size} selected` : ''} · ${isDirty ? 'unsaved' : 'saved'}`
                : `source mode · ${isDirty ? 'unsaved' : 'saved'}`
              }
            </p>
          </div>

          {viewMode === 'chunk' ? (
            <div className="flex-1 overflow-y-auto px-4 py-3">
              <div className="flex flex-col gap-1.5">
                {chunks.chunks.map((chunk) => (
                  <ChunkItem
                    key={chunk.index}
                    index={chunk.index}
                    text={chunk.text}
                    selected={chunks.selected.has(chunk.index)}
                    onSelect={chunks.toggleSelect}
                    onChange={chunks.updateChunk}
                  />
                ))}
              </div>
            </div>
          ) : (
            <textarea
              value={sourceBody}
              onChange={(e) => setSourceBody(e.target.value)}
              className="flex-1 resize-none bg-transparent px-6 py-3 text-sm leading-[1.8] outline-none placeholder:text-muted-foreground/40"
              placeholder="Start writing..."
              spellCheck={false}
            />
          )}

          {/* Commit message */}
          <div className="flex-shrink-0 border-t px-4 py-2">
            <input
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Commit message (optional)"
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
                className={cn('flex-1 px-3 py-2 text-xs font-medium', rightTab === 'history' ? 'border-b-2 border-primary text-primary' : 'text-muted-foreground')}
              >
                <Clock className="mr-1.5 inline h-3 w-3" />History
              </button>
              <button
                onClick={() => setRightTab('ai')}
                className={cn('flex-1 px-3 py-2 text-xs font-medium', rightTab === 'ai' ? 'border-b-2 border-accent text-accent' : 'text-muted-foreground')}
              >
                AI Chat
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              {rightTab === 'history' ? (
                <RevisionHistory key={revKey} bookId={bookId} chapterId={chapterId} onRestore={() => void load()} />
              ) : (
                <div className="p-4 text-xs italic text-muted-foreground">AI Chat panel — coming in P3-19.</div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Bottom bar — chunk selection (chunk mode only) */}
      {viewMode === 'chunk' && chunks.selected.size > 0 && (
        <div className="flex h-9 flex-shrink-0 items-center justify-between border-t bg-card px-4 text-xs">
          <span className="text-muted-foreground">{chunks.selected.size} chunk(s) selected</span>
          <button onClick={chunks.clearSelection} className="text-muted-foreground hover:text-foreground">Clear</button>
        </div>
      )}
    </div>
  );
}
