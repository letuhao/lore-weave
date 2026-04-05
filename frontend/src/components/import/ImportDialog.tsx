import { useState, useRef } from 'react';
import { Upload, FileText, X } from 'lucide-react';
import { FormDialog } from '@/components/shared/FormDialog';

interface ImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  bookId: string;
  onImported: () => void;
}

export function ImportDialog({ open, onOpenChange, bookId, onImported }: ImportDialogProps) {
  const [files, setFiles] = useState<File[]>([]);
  const [importing, setImporting] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = '.txt,.docx,.epub,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/epub+zip';

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList) return;
    setFiles((prev) => [...prev, ...Array.from(fileList)]);
  };

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  };

  const handleImport = async () => {
    const txtFiles = files.filter((f) => f.name.endsWith('.txt'));
    const nonTxt = files.filter((f) => !f.name.endsWith('.txt'));

    if (nonTxt.length > 0) {
      setError(`${nonTxt.length} file(s) skipped — only .txt is supported for now. (.docx/.epub coming in P2-11b)`);
    }

    if (txtFiles.length === 0) {
      if (nonTxt.length === 0) setError('No files selected.');
      return;
    }

    setImporting(true);
    setError('');
    setProgress({ done: 0, total: txtFiles.length });

    try {
      const { booksApi } = await import('@/features/books/api');
      const token = JSON.parse(localStorage.getItem('lw_auth') ?? '{}').accessToken;
      if (!token) throw new Error('Not authenticated');

      const errors: string[] = [];
      for (let i = 0; i < txtFiles.length; i++) {
        const file = txtFiles[i];
        try {
          await booksApi.createChapterUpload(token, bookId, {
            file,
            original_language: 'auto',
            title: file.name.replace('.txt', ''),
          });
        } catch (e) {
          errors.push(`${file.name}: ${(e as Error).message}`);
        }
        setProgress({ done: i + 1, total: txtFiles.length });
      }

      if (errors.length > 0) {
        setError(`${errors.length} file(s) failed:\n${errors.join('\n')}`);
      }

      onImported();
      if (errors.length === 0) {
        onOpenChange(false);
        setFiles([]);
      }
    } catch (e) {
      setError((e as Error).message);
    }
    setImporting(false);
  };

  return (
    <FormDialog
      open={open}
      onOpenChange={onOpenChange}
      title="Import Chapters"
      description="Upload one or more files to create chapters. Files are imported in order."
      footer={
        <>
          <button onClick={() => onOpenChange(false)} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary">
            Cancel
          </button>
          <button
            onClick={() => void handleImport()}
            disabled={files.length === 0 || importing}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {importing
              ? `Importing ${progress.done}/${progress.total}...`
              : `Import ${files.length} file${files.length !== 1 ? 's' : ''}`}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive whitespace-pre-wrap">{error}</div>
        )}

        {/* Drop zone */}
        <div
          onClick={() => inputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); }}
          onDrop={(e) => { e.preventDefault(); e.stopPropagation(); handleFiles(e.dataTransfer.files); }}
          className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed py-8 transition-colors hover:border-ring/40"
        >
          <Upload className="mb-3 h-8 w-8 text-muted-foreground/40" />
          <p className="text-sm text-muted-foreground">Click to upload or drag and drop</p>
          <p className="mt-1 text-xs text-muted-foreground/60">Select multiple .txt files · .docx .epub coming soon</p>
        </div>

        {/* File list */}
        {files.length > 0 && (
          <div className="max-h-60 space-y-1 overflow-y-auto rounded-lg border p-2">
            {files.map((file, i) => (
              <div key={`${file.name}-${i}`} className="flex items-center gap-3 rounded px-3 py-2 hover:bg-secondary/50">
                <FileText className="h-4 w-4 flex-shrink-0 text-primary" />
                <div className="flex-1 min-w-0">
                  <p className="truncate text-xs font-medium">{file.name}</p>
                  <p className="text-[10px] text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
                </div>
                {!importing && (
                  <button onClick={() => removeFile(i)} className="rounded p-1 text-muted-foreground hover:text-foreground">
                    <X className="h-3 w-3" />
                  </button>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Progress bar during import */}
        {importing && (
          <div className="space-y-1">
            <div className="h-1.5 overflow-hidden rounded-full bg-secondary">
              <div
                className="h-full rounded-full bg-primary transition-all"
                style={{ width: `${(progress.done / progress.total) * 100}%` }}
              />
            </div>
            <p className="text-[10px] text-muted-foreground text-center">
              Uploading {progress.done} of {progress.total} chapters...
            </p>
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          multiple
          className="hidden"
          onChange={(e) => { handleFiles(e.target.files); if (inputRef.current) inputRef.current.value = ''; }}
        />
      </div>
    </FormDialog>
  );
}
