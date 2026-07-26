import { useState } from 'react';
import { Loader2, FileText, AlertTriangle } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';

interface StepUploadProps {
  bookId: string;
  file: File | null;
  pageCount: number | null;
  peekError: string | null;
  onFileSelected: (file: File | null) => void;
  onPeekResult: (pageCount: number | null, error: string | null) => void;
}

export function StepUpload({ bookId, file, pageCount, peekError, onFileSelected, onPeekResult }: StepUploadProps) {
  const { t } = useTranslation('pdf-import');
  const { accessToken } = useAuth();
  const [peeking, setPeeking] = useState(false);

  const handleFile = async (selected: File | null) => {
    onFileSelected(selected);
    if (!selected || !accessToken) return;
    setPeeking(true);
    try {
      const { page_count } = await booksApi.pdfPeek(accessToken, bookId, selected);
      onPeekResult(page_count, null);
    } catch (e) {
      onPeekResult(null, (e as Error).message || t('upload.readError'));
    } finally {
      setPeeking(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('upload.intro')}</p>

      <label className="flex flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed p-8 text-center cursor-pointer hover:bg-secondary/50 transition-colors">
        <FileText className="h-6 w-6 text-muted-foreground" />
        <span className="text-sm font-medium">{file ? file.name : t('upload.choosePdf')}</span>
        <span className="text-[11px] text-muted-foreground">{t('upload.pdfOnly')}</span>
        <input
          type="file"
          accept=".pdf"
          className="hidden"
          onChange={(e) => void handleFile(e.target.files?.[0] ?? null)}
        />
      </label>

      {peeking && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          {t('upload.checking')}
        </div>
      )}

      {peekError && (
        <div className="flex items-center gap-2 rounded-md border border-destructive/50 bg-destructive/10 p-2.5 text-xs text-destructive">
          <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
          {peekError}
        </div>
      )}

      {pageCount != null && !peekError && (
        <div className="rounded-md border bg-card/50 p-2.5 text-xs">
          {t('upload.pageCount', { count: pageCount })}
        </div>
      )}
    </div>
  );
}
