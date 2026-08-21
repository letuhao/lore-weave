import { AlertCircle, CheckCircle2, Loader2, Upload } from 'lucide-react';
import type { ImportJob } from '@/features/books/api';
import type { NewFB2ImportStage } from '@/features/books/hooks/useBooksList';

type Props = {
  stage: NewFB2ImportStage;
  progress: number;
  job: ImportJob | null;
  error: string;
};

export function FB2ImportProgress({ stage, progress, job, error }: Props) {
  if (stage === 'idle') return null;

  if (stage === 'failed') {
    return (
      <div role="alert" className="flex items-start gap-2 rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>FB2 import failed: {error}</span>
      </div>
    );
  }

  if (stage === 'completed') {
    return (
      <div className="flex items-start gap-2 rounded-md border border-green-500/30 bg-green-500/5 px-3 py-2 text-sm text-green-700 dark:text-green-400">
        <CheckCircle2 className="mt-0.5 h-4 w-4 flex-shrink-0" />
        <span>FB2 import complete — {job?.chapters_created ?? 0} chapters created.</span>
      </div>
    );
  }

  const isUploading = stage === 'uploading';
  return (
    <div aria-live="polite" className="rounded-md border bg-secondary/30 px-3 py-2 text-sm">
      <div className="flex items-center gap-2">
        {isUploading ? <Upload className="h-4 w-4" /> : <Loader2 className="h-4 w-4 animate-spin" />}
        <span>{isUploading ? `Uploading FB2… ${progress}%` : `Processing FB2… ${job?.chapters_created ?? 0} chapters created so far`}</span>
      </div>
      {isUploading && (
        <div className="mt-2 h-1.5 overflow-hidden rounded bg-muted">
          <div className="h-full rounded bg-primary transition-all" style={{ width: `${progress}%` }} />
        </div>
      )}
    </div>
  );
}
