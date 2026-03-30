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
  const [file, setFile] = useState<File | null>(null);
  const [importing, setImporting] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const accept = '.txt,.docx,.epub,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/epub+zip';

  const handleImport = async () => {
    if (!file) return;
    setImporting(true);
    setError('');
    try {
      // For now, only .txt is supported via existing API
      // .docx and .epub will be added in P2-11b (backend)
      if (file.name.endsWith('.txt')) {
        // Use existing chapter upload API
        const { booksApi } = await import('@/features/books/api');
        const token = JSON.parse(localStorage.getItem('lw_auth') ?? '{}').accessToken;
        if (token) {
          await booksApi.createChapterUpload(token, bookId, {
            file,
            original_language: 'auto',
            title: file.name.replace('.txt', ''),
          });
        }
        onImported();
        onOpenChange(false);
        setFile(null);
      } else {
        setError(`${file.name.split('.').pop()?.toUpperCase()} import requires backend support (P2-11b). Only .txt is supported for now.`);
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
      title="Import Chapter"
      description="Upload a file to create a new chapter."
      footer={
        <>
          <button onClick={() => onOpenChange(false)} className="rounded-md border px-4 py-2 text-sm font-medium hover:bg-secondary">
            Cancel
          </button>
          <button
            onClick={() => void handleImport()}
            disabled={!file || importing}
            className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {importing ? 'Importing...' : 'Import'}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {error && (
          <div className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">{error}</div>
        )}

        {!file ? (
          <div
            onClick={() => inputRef.current?.click()}
            className="flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed py-10 transition-colors hover:border-ring/40"
          >
            <Upload className="mb-3 h-8 w-8 text-muted-foreground/40" />
            <p className="text-sm text-muted-foreground">Click to upload or drag and drop</p>
            <p className="mt-1 text-xs text-muted-foreground/60">.txt supported now · .docx .epub coming soon</p>
          </div>
        ) : (
          <div className="flex items-center gap-3 rounded-lg border p-4">
            <FileText className="h-8 w-8 text-primary" />
            <div className="flex-1 min-w-0">
              <p className="truncate text-sm font-medium">{file.name}</p>
              <p className="text-xs text-muted-foreground">{(file.size / 1024).toFixed(1)} KB</p>
            </div>
            <button onClick={() => setFile(null)} className="rounded p-1 text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        <input
          ref={inputRef}
          type="file"
          accept={accept}
          className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
      </div>
    </FormDialog>
  );
}
