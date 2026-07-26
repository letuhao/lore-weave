import { useState } from 'react';
import { Loader2, Minimize2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuth } from '@/auth';
import { useImportEvents, type ImportStatusEvent } from '@/hooks/useImportEvents';
import { usePdfImportPolling } from './usePdfImportPolling';

interface StepProgressProps {
  bookId: string;
  jobId: string;
  expectedChapters: number;
  onComplete: (finalStatus: 'completed' | 'failed', chaptersCreated: number, error?: string) => void;
  onBackground?: () => void;
}

export function StepProgress({ bookId, jobId, expectedChapters, onComplete, onBackground }: StepProgressProps) {
  const { t } = useTranslation('pdf-import');
  const { accessToken } = useAuth();
  const [wsEvent, setWsEvent] = useState<ImportStatusEvent | null>(null);

  // Primary: live push. Falls back to polling below if WS never connects
  // (useImportEvents degrades silently — this hook keeps polling as the
  // backup path regardless, per its own doc comment).
  useImportEvents(accessToken, (event) => {
    if (event.job_id === jobId) setWsEvent(event);
  });
  const { job } = usePdfImportPolling(accessToken, bookId, jobId);

  const status = wsEvent?.status ?? job?.status ?? 'processing';
  const chaptersCreated = wsEvent?.chapters_created ?? job?.chapters_created ?? 0;
  const errorMsg = wsEvent?.error ?? job?.error ?? undefined;

  if ((status === 'completed' || status === 'failed') ) {
    queueMicrotask(() => onComplete(status, chaptersCreated, errorMsg ?? undefined));
  }

  const pct = expectedChapters > 0 ? Math.min(100, Math.round((chaptersCreated / expectedChapters) * 100)) : 0;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center animate-pulse">
            <Loader2 className="h-3.5 w-3.5 text-primary animate-spin" />
          </div>
          <div>
            <p className="text-sm font-medium">{t('progress.importing')}</p>
            <p className="text-[10px] text-muted-foreground">
              {t('progress.chapterOf', { current: chaptersCreated, total: expectedChapters })}
            </p>
          </div>
        </div>
        {onBackground && (
          <button
            onClick={onBackground}
            className="inline-flex items-center gap-1 rounded-md border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
          >
            <Minimize2 className="h-3 w-3" />
            {t('progress.runInBackground')}
          </button>
        )}
      </div>

      <div>
        <div className="flex justify-between text-xs mb-1">
          <span className="text-muted-foreground">{t('progress.progress')}</span>
          <span className="font-mono text-primary">{pct}%</span>
        </div>
        <div className="w-full h-1.5 bg-border rounded-full overflow-hidden">
          <div
            className="h-full bg-primary rounded-full transition-all duration-500"
            style={{ width: `${pct}%` }}
          />
        </div>
      </div>

      <p className="text-[11px] text-muted-foreground">{t('progress.longNote')}</p>
    </div>
  );
}
