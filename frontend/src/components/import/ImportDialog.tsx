import { useState, useRef, useCallback } from 'react';
import { Upload, X, CheckCircle2, AlertCircle, Loader2, FolderOpen, FileText } from 'lucide-react';
import { FormDialog } from '@/components/shared/FormDialog';
import { booksApi, ImportJob } from '@/features/books/api';
import { useImportEvents } from '@/hooks/useImportEvents';
import { ChapterImportReview } from './ChapterImportReview';
import { filterTxtFiles, readChapters, naturalCompare, type ParsedChapter } from './parseChapters';

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  onImported: () => void;
}

const ACCEPTED_EXTENSIONS = '.txt,.docx,.epub';
const MAX_SIZE = 200 * 1024 * 1024; // 200 MB per doc file
const BULK_BATCH = 100; // chapters per bulk request (sequential → order preserved)

type ImportState = 'idle' | 'reading' | 'uploading' | 'processing' | 'completed' | 'failed';

export function ImportDialog({ open, onOpenChange, bookId, onImported }: ImportDialogProps) {
  // Plain-text chapters go through the paginated review + bulk endpoint.
  const [parsed, setParsed] = useState<ParsedChapter[]>([]);
  // .docx/.epub keep the existing async per-file import-job flow.
  const [docFiles, setDocFiles] = useState<File[]>([]);
  const [importState, setImportState] = useState<ImportState>('idle');
  const [readProgress, setReadProgress] = useState({ done: 0, total: 0 });
  const [bulkProgress, setBulkProgress] = useState({ done: 0, total: 0 });
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentJob, setCurrentJob] = useState<ImportJob | null>(null);
  const [createdCount, setCreatedCount] = useState(0);
  const [skippedCount, setSkippedCount] = useState(0);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);
  const folderRef = useRef<HTMLInputElement | null>(null);

  const resolveRef = useRef<(() => void) | null>(null);
  const rejectRef = useRef<((err: Error) => void) | null>(null);
  const activeJobIdRef = useRef<string | null>(null);

  const token = (() => {
    try {
      return JSON.parse(localStorage.getItem('lw_auth') ?? '{}').accessToken ?? null;
    } catch {
      return null;
    }
  })();

  const handleWSEvent = useCallback(
    (event: { job_id: string; status: string; chapters_created: number; error?: string }) => {
      if (event.job_id !== activeJobIdRef.current) return;
      setCurrentJob((prev) =>
        prev ? { ...prev, status: event.status as ImportJob['status'], chapters_created: event.chapters_created, error: event.error ?? null } : prev,
      );
      if (event.status === 'completed') {
        resolveRef.current?.();
        resolveRef.current = null; rejectRef.current = null;
      } else if (event.status === 'failed') {
        rejectRef.current?.(new Error(event.error || 'Import failed'));
        resolveRef.current = null; rejectRef.current = null;
      }
    },
    [],
  );
  useImportEvents(open ? token : null, handleWSEvent);

  const ingest = async (fileList: FileList | null) => {
    if (!fileList) return;
    const all = Array.from(fileList);
    const txt = filterTxtFiles(all);
    const docs = all.filter((f) => /\.(docx|epub)$/i.test(f.name) && f.size <= MAX_SIZE);
    setError('');
    if (docs.length) setDocFiles((prev) => [...prev, ...docs]);
    if (txt.length) {
      setImportState('reading');
      setReadProgress({ done: 0, total: txt.length });
      try {
        const rows = await readChapters(txt, (done, total) => setReadProgress({ done, total }));
        // Append + keep globally natural-sorted by filename across batches.
        setParsed((prev) => [...prev, ...rows].sort((a, b) => naturalCompare(a.filename, b.filename)));
      } catch (e) {
        setError(`Failed to read files: ${(e as Error).message}`);
      } finally {
        setImportState('idle');
      }
    }
  };

  const setIncluded = (id: string, included: boolean) =>
    setParsed((prev) => prev.map((c) => (c.id === id ? { ...c, included } : c)));
  const setTitle = (id: string, title: string) =>
    setParsed((prev) => prev.map((c) => (c.id === id ? { ...c, title } : c)));
  const setAllIncluded = (included: boolean) =>
    setParsed((prev) => prev.map((c) => ({ ...c, included })));

  const includedChapters = parsed.filter((c) => c.included);
  const totalToImport = includedChapters.length + docFiles.length;

  const handleImport = async () => {
    if (!token) { setError('Not authenticated'); return; }
    if (totalToImport === 0) { setError('Nothing selected to import.'); return; }
    setError('');
    let created = 0;
    let skipped = 0;
    const errors: string[] = [];

    // 1) Bulk plain-text chapters — sequential batches preserve order.
    if (includedChapters.length > 0) {
      setImportState('uploading');
      setBulkProgress({ done: 0, total: includedChapters.length });
      for (let i = 0; i < includedChapters.length; i += BULK_BATCH) {
        const batch = includedChapters.slice(i, i + BULK_BATCH).map((c) => ({
          original_filename: c.filename,
          content: c.content,
          title: c.title.trim() || undefined,
        }));
        try {
          const res = await booksApi.bulkCreateChapters(token, bookId, batch);
          created += res.chapters_created;
          skipped += res.skipped_existing ?? 0;
          setBulkProgress({ done: Math.min(i + batch.length, includedChapters.length), total: includedChapters.length });
        } catch (e) {
          errors.push(`Batch ${i / BULK_BATCH + 1}: ${(e as Error).message}`);
          break; // stop on first batch error (order integrity)
        }
      }
    }

    // 2) .docx/.epub — existing async per-file import jobs.
    for (const file of docFiles) {
      try {
        setImportState('uploading');
        setUploadProgress(0);
        const job = await booksApi.startImport(token, bookId, file, 'auto', (pct) => setUploadProgress(pct));
        setCurrentJob(job);
        setImportState('processing');
        activeJobIdRef.current = job.id;
        await new Promise<void>((resolve, reject) => {
          resolveRef.current = resolve; rejectRef.current = reject;
          const interval = setInterval(async () => {
            try {
              const updated = await booksApi.getImportJob(token, bookId, job.id);
              setCurrentJob(updated);
              if (updated.status === 'completed') { clearInterval(interval); resolveRef.current?.(); resolveRef.current = null; rejectRef.current = null; }
              else if (updated.status === 'failed') { clearInterval(interval); rejectRef.current?.(new Error(updated.error || 'Import failed')); resolveRef.current = null; rejectRef.current = null; }
            } catch { /* keep polling */ }
          }, 5000);
          setTimeout(() => { clearInterval(interval); rejectRef.current?.(new Error('Import timed out')); resolveRef.current = null; rejectRef.current = null; }, 10 * 60 * 1000);
        });
        created += currentJob?.chapters_created ?? 0;
        activeJobIdRef.current = null;
      } catch (e) {
        errors.push(`${file.name}: ${(e as Error).message}`);
      }
    }

    setCreatedCount(created);
    setSkippedCount(skipped);
    if (errors.length > 0) { setImportState('failed'); setError(errors.join('\n')); }
    else { setImportState('completed'); onImported(); }
  };

  const handleClose = () => {
    if (importState === 'reading' || importState === 'uploading' || importState === 'processing') return;
    setParsed([]); setDocFiles([]); setImportState('idle');
    setReadProgress({ done: 0, total: 0 }); setBulkProgress({ done: 0, total: 0 });
    setUploadProgress(0); setCurrentJob(null); setCreatedCount(0); setSkippedCount(0); setError('');
    activeJobIdRef.current = null;
    onOpenChange(false);
  };

  const isBusy = importState === 'reading' || importState === 'uploading' || importState === 'processing';
  const hasSelection = parsed.length > 0 || docFiles.length > 0;

  return (
    <FormDialog
      open={open}
      onOpenChange={handleClose}
      title="Import Chapters"
      description="Choose a folder or files (.txt for bulk, or .docx/.epub). Review and reorder-free natural sorting is applied before import."
      footer={
        <>
          <button type="button" onClick={handleClose} disabled={isBusy}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-50">
            {importState === 'completed' ? 'Close' : 'Cancel'}
          </button>
          {importState !== 'completed' && (
            <button type="button" onClick={() => void handleImport()} disabled={!hasSelection || isBusy || totalToImport === 0}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50">
              {isBusy ? 'Working…' : `Import ${totalToImport} chapter${totalToImport !== 1 ? 's' : ''}`}
            </button>
          )}
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
            <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
            <span className="whitespace-pre-wrap">{error}</span>
          </div>
        )}

        {importState === 'completed' && (
          <div className="flex items-center gap-2 rounded-md border border-green-500/30 bg-green-500/5 px-3 py-2 text-sm text-green-700 dark:text-green-400">
            <CheckCircle2 className="h-4 w-4 flex-shrink-0" />
            <span>
              Import complete — {createdCount} chapter{createdCount !== 1 ? 's' : ''} created
              {skippedCount > 0 ? ` · ${skippedCount} skipped (already imported)` : ''}
            </span>
          </div>
        )}

        {/* Pickers */}
        {!isBusy && importState !== 'completed' && (
          <div
            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
            onDrop={(e) => { e.preventDefault(); e.stopPropagation(); void ingest(e.dataTransfer.files); }}
            className="flex flex-col items-center justify-center gap-3 rounded-lg border-2 border-dashed py-6"
          >
            <Upload className="h-7 w-7 text-muted-foreground/40" />
            <p className="text-xs text-muted-foreground">Drag & drop, or</p>
            <div className="flex gap-2">
              <button type="button" onClick={() => inputRef.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">
                <FileText className="h-3.5 w-3.5" /> Choose files
              </button>
              <button type="button" onClick={() => folderRef.current?.click()}
                className="inline-flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-xs font-medium hover:bg-secondary">
                <FolderOpen className="h-3.5 w-3.5" /> Choose folder
              </button>
            </div>
            <p className="text-[10px] text-muted-foreground/60">.txt (bulk) · .docx · .epub — max 200 MB per doc</p>
          </div>
        )}

        {/* Reading progress */}
        {importState === 'reading' && (
          <ProgressBar label={`Reading files… ${readProgress.done}/${readProgress.total}`}
            pct={readProgress.total ? (readProgress.done / readProgress.total) * 100 : 0} />
        )}

        {/* Plain-text review */}
        {importState !== 'completed' && parsed.length > 0 && (
          <ChapterImportReview
            chapters={parsed}
            onSetIncluded={setIncluded}
            onSetTitle={setTitle}
            onSetAllIncluded={setAllIncluded}
          />
        )}

        {/* Doc files (docx/epub) */}
        {importState !== 'completed' && docFiles.length > 0 && (
          <div className="space-y-1 rounded-lg border p-2">
            {docFiles.map((f, i) => (
              <div key={`${f.name}-${i}`} className="flex items-center gap-3 rounded px-3 py-1.5 text-xs">
                <span>{f.name.endsWith('.epub') ? '📖' : '📄'}</span>
                <span className="min-w-0 flex-1 truncate">{f.name}</span>
                {!isBusy && (
                  <button type="button" title="Remove" onClick={() => setDocFiles((p) => p.filter((_, j) => j !== i))}
                    className="rounded p-1 text-muted-foreground hover:text-foreground"><X className="h-3 w-3" /></button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Import progress */}
        {(importState === 'uploading' || importState === 'processing') && (
          <div className="space-y-2">
            {bulkProgress.total > 0 && (
              <ProgressBar label={`Importing chapters… ${bulkProgress.done}/${bulkProgress.total}`}
                pct={(bulkProgress.done / bulkProgress.total) * 100} />
            )}
            {docFiles.length > 0 && (
              <ProgressBar label={importState === 'uploading' ? `Uploading document… ${uploadProgress}%` : 'Converting document…'}
                pct={importState === 'uploading' ? uploadProgress : 100} />
            )}
          </div>
        )}

        <input ref={inputRef} type="file" accept={ACCEPTED_EXTENSIONS} multiple className="hidden"
          title="Select files" onChange={(e) => { void ingest(e.target.files); if (inputRef.current) inputRef.current.value = ''; }} />
        {/* Folder picker — webkitdirectory set via ref to avoid TS prop typing */}
        <input ref={(el) => { if (el) { el.setAttribute('webkitdirectory', ''); el.setAttribute('directory', ''); } folderRef.current = el; }}
          type="file" multiple className="hidden" title="Select a folder"
          onChange={(e) => { void ingest(e.target.files); if (folderRef.current) folderRef.current.value = ''; }} />
      </div>
    </FormDialog>
  );
}

function ProgressBar({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="space-y-1">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin" /> <span>{label}</span>
      </div>
      <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
        <div className="h-full rounded-full bg-primary transition-all" style={{ width: `${Math.min(100, pct)}%` }} />
      </div>
    </div>
  );
}
