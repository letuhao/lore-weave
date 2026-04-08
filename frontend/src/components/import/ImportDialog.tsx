import { useState, useRef, useCallback } from 'react';
import { Upload, X, CheckCircle2, AlertCircle, Loader2 } from 'lucide-react';
import { FormDialog } from '@/components/shared/FormDialog';
import { booksApi, ImportJob } from '@/features/books/api';
import { useImportEvents } from '@/hooks/useImportEvents';

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  onImported: () => void;
}

const ACCEPTED_EXTENSIONS = '.txt,.docx,.epub';
const ACCEPTED_MIME = 'text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/epub+zip';
const MAX_SIZE = 200 * 1024 * 1024; // 200 MB

type ImportState = 'idle' | 'uploading' | 'processing' | 'completed' | 'failed';

export function ImportDialog({ open, onOpenChange, bookId, onImported }: ImportDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [importState, setImportState] = useState<ImportState>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [currentJob, setCurrentJob] = useState<ImportJob | null>(null);
  const [error, setError] = useState('');
  const [fileIndex, setFileIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Resolve refs for the active job's promise settle callbacks
  const resolveRef = useRef<(() => void) | null>(null);
  const rejectRef = useRef<((err: Error) => void) | null>(null);
  const activeJobIdRef = useRef<string | null>(null);

  const accept = `${ACCEPTED_EXTENSIONS},${ACCEPTED_MIME}`;

  // Get auth token for WS connection
  const token = (() => {
    try {
      return JSON.parse(localStorage.getItem('lw_auth') ?? '{}').accessToken ?? null;
    } catch {
      return null;
    }
  })();

  // WebSocket handler — instant status updates from worker-infra via RabbitMQ → gateway
  const handleWSEvent = useCallback(
    (event: { job_id: string; status: string; chapters_created: number; error?: string }) => {
      if (event.job_id !== activeJobIdRef.current) return;

      setCurrentJob((prev) =>
        prev ? { ...prev, status: event.status as ImportJob['status'], chapters_created: event.chapters_created, error: event.error ?? null } : prev,
      );

      if (event.status === 'completed') {
        resolveRef.current?.();
        resolveRef.current = null;
        rejectRef.current = null;
      } else if (event.status === 'failed') {
        rejectRef.current?.(new Error(event.error || 'Import failed'));
        resolveRef.current = null;
        rejectRef.current = null;
      }
    },
    [],
  );

  useImportEvents(open ? token : null, handleWSEvent);

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    const newFiles = Array.from(fileList).filter((f) => {
      if (f.size > MAX_SIZE) {
        setError(`${f.name} exceeds 200 MB limit`);
        return false;
      }
      return true;
    });
    setFiles((prev) => [...prev, ...newFiles]);
    setError('');
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const getFileIcon = (name: string) => {
    if (name.endsWith('.epub')) return '📖';
    if (name.endsWith('.docx')) return '📄';
    return '📝';
  };

  const handleImport = async () => {
    if (files.length === 0) {
      setError('No files selected.');
      return;
    }

    if (!token) {
      setError('Not authenticated');
      return;
    }

    setImportState('uploading');
    setError('');
    setFileIndex(0);

    const errors: string[] = [];

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      setFileIndex(i);
      setUploadProgress(0);

      try {
        if (file.name.endsWith('.txt')) {
          await booksApi.createChapterUpload(token, bookId, {
            file,
            original_language: 'auto',
            title: file.name.replace('.txt', ''),
          });
        } else {
          const job = await booksApi.startImport(token, bookId, file, 'auto', (pct) =>
            setUploadProgress(pct),
          );
          setCurrentJob(job);
          setImportState('processing');
          activeJobIdRef.current = job.id;

          // Wait for completion — WS resolves instantly, poll is fallback (5s interval)
          await new Promise<void>((resolve, reject) => {
            resolveRef.current = resolve;
            rejectRef.current = reject;

            // Fallback poll in case WS is not connected
            const interval = setInterval(async () => {
              try {
                const updated = await booksApi.getImportJob(token, bookId, job.id);
                setCurrentJob(updated);
                if (updated.status === 'completed') {
                  clearInterval(interval);
                  resolveRef.current?.();
                  resolveRef.current = null;
                  rejectRef.current = null;
                } else if (updated.status === 'failed') {
                  clearInterval(interval);
                  rejectRef.current?.(new Error(updated.error || 'Import failed'));
                  resolveRef.current = null;
                  rejectRef.current = null;
                }
              } catch {
                // keep polling
              }
            }, 5000); // 5s interval (WS handles instant updates)

            // Timeout after 10 minutes
            setTimeout(() => {
              clearInterval(interval);
              rejectRef.current?.(new Error('Import timed out'));
              resolveRef.current = null;
              rejectRef.current = null;
            }, 10 * 60 * 1000);
          });

          activeJobIdRef.current = null;
        }
      } catch (e) {
        errors.push(`${file.name}: ${(e as Error).message}`);
      }
    }

    if (errors.length > 0) {
      setImportState('failed');
      setError(errors.join('\n'));
    } else {
      setImportState('completed');
      onImported();
    }
  };

  const handleClose = () => {
    if (importState === 'uploading' || importState === 'processing') return;
    setFiles([]);
    setImportState('idle');
    setUploadProgress(0);
    setCurrentJob(null);
    setError('');
    activeJobIdRef.current = null;
    onOpenChange(false);
  };

  const isProcessing = importState === 'uploading' || importState === 'processing';

  return (
    <FormDialog
      open={open}
      onOpenChange={handleClose}
      title="Import Chapters"
      description="Upload .txt, .docx, or .epub files to create chapters. EPUB files are split into multiple chapters automatically."
      footer={
        <>
          <button
            type="button"
            onClick={handleClose}
            disabled={isProcessing}
            className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary disabled:opacity-50"
          >
            {importState === 'completed' ? 'Close' : 'Cancel'}
          </button>
          {importState !== 'completed' && (
            <button
              type="button"
              onClick={() => void handleImport()}
              disabled={files.length === 0 || isProcessing}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
            >
              {isProcessing
                ? 'Importing...'
                : `Import ${files.length} file${files.length !== 1 ? 's' : ''}`}
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
              Import complete
              {currentJob ? ` — ${currentJob.chapters_created} chapter${currentJob.chapters_created !== 1 ? 's' : ''} created` : ''}
            </span>
          </div>
        )}

        {/* Drop zone */}
        {!isProcessing && importState !== 'completed' && (
          <div
            onClick={() => inputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
            onDrop={(e) => {
              e.preventDefault();
              e.stopPropagation();
              handleFiles(e.dataTransfer.files);
            }}
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed py-8 transition-colors hover:border-ring/40"
          >
            <Upload className="mb-3 h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">Click to upload or drag and drop</p>
            <p className="mt-1 text-xs text-muted-foreground/60">
              .txt .docx .epub — max 200 MB per file
            </p>
          </div>
        )}

        {/* File list */}
        {files.length > 0 && importState !== 'completed' && (
          <div className="max-h-60 space-y-1 overflow-y-auto rounded-lg border p-2">
            {files.map((file, i) => (
              <div
                key={`${file.name}-${i}`}
                className="flex items-center gap-3 rounded px-3 py-2 hover:bg-secondary/50"
              >
                <span className="text-base">{getFileIcon(file.name)}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{file.name}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {(file.size / 1024 / 1024).toFixed(1)} MB
                  </p>
                </div>
                {!isProcessing && (
                  <button
                    type="button"
                    title="Remove file"
                    onClick={() => removeFile(i)}
                    className="rounded p-1 text-muted-foreground hover:text-foreground"
                  >
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Progress */}
        {isProcessing && (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              <span>
                {importState === 'uploading'
                  ? `Uploading ${files[fileIndex]?.name ?? 'file'}... ${uploadProgress}%`
                  : `Processing ${files[fileIndex]?.name ?? 'file'}...`}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{
                  width: importState === 'uploading' ? `${uploadProgress}%` : '100%',
                }}
              />
            </div>
            {importState === 'processing' && (
              <p className="text-[10px] text-muted-foreground text-center">
                Converting document and creating chapters...
              </p>
            )}
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple
          title="Select files to import"
          className="hidden"
          onChange={(e) => {
            handleFiles(e.target.files);
            if (inputRef.current) inputRef.current.value = '';
          }}
        />
      </div>
    </FormDialog>
  );
}
