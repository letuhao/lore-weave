import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';

interface StepConfirmProps {
  bookId: string;
  file: File;
  pageCount: number;
  pagesPerChunk: number;
  captionImages: boolean;
  modelSource: string | null;
  modelRef: string | null;
  onJobCreated: (jobId: string) => void;
}

export function StepConfirm({
  bookId,
  file,
  pageCount,
  pagesPerChunk,
  captionImages,
  modelSource,
  modelRef,
  onJobCreated,
}: StepConfirmProps) {
  const { t } = useTranslation('pdf-import');
  const { accessToken } = useAuth();
  const [submitting, setSubmitting] = useState(false);
  const chapterCount = Math.ceil(pageCount / Math.max(1, pagesPerChunk));
  const canSubmit = !captionImages || (!!modelSource && !!modelRef);

  const handleStart = async () => {
    if (!accessToken || submitting || !canSubmit) return;
    setSubmitting(true);
    try {
      const job = await booksApi.startImport(accessToken, bookId, file, undefined, undefined, {
        pagesPerChunk,
        captionImages,
        modelSource: modelSource ?? undefined,
        modelRef: modelRef ?? undefined,
      });
      onJobCreated(job.id);
    } catch (e) {
      toast.error((e as Error).message || t('confirm.startFailed'));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border bg-card/50 p-3 text-xs space-y-1.5">
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('confirm.file')}</span>
          <span className="font-medium">{file.name}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('confirm.pages')}</span>
          <span className="font-medium">{pageCount}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('confirm.pagesPerChunk')}</span>
          <span className="font-medium">{pagesPerChunk}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('confirm.chaptersToCreate')}</span>
          <span className="font-medium text-primary">{chapterCount}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">{t('confirm.captionImages')}</span>
          <span className="font-medium">{captionImages ? t('confirm.yes') : t('confirm.no')}</span>
        </div>
      </div>

      {!canSubmit && <p className="text-xs text-destructive">{t('confirm.needModel')}</p>}

      <p className="text-[11px] text-muted-foreground">{t('confirm.backgroundNote')}</p>

      <button
        onClick={() => void handleStart()}
        disabled={submitting || !canSubmit}
        className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
      >
        {submitting && <Loader2 className="h-4 w-4 animate-spin" />}
        {t('confirm.startImport')}
      </button>
    </div>
  );
}
