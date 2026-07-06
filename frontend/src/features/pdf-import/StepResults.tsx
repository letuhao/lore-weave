import { CheckCircle2, XCircle } from 'lucide-react';
import { useTranslation } from 'react-i18next';

interface StepResultsProps {
  status: 'completed' | 'failed';
  chaptersCreated: number;
  error?: string;
  onClose: () => void;
  onRestart: () => void;
}

export function StepResults({ status, chaptersCreated, error, onClose, onRestart }: StepResultsProps) {
  const { t } = useTranslation('pdf-import');
  const ok = status === 'completed';
  return (
    <div className="space-y-4 py-6 text-center">
      {ok ? (
        <CheckCircle2 className="h-10 w-10 text-green-500 mx-auto" />
      ) : (
        <XCircle className="h-10 w-10 text-destructive mx-auto" />
      )}
      <div>
        <p className="text-sm font-medium">{ok ? t('results.complete') : t('results.failed')}</p>
        <p className="text-xs text-muted-foreground mt-1">
          {ok
            ? t('results.chaptersCreated', { count: chaptersCreated })
            : error || t('results.genericError')}
        </p>
      </div>
      <div className="flex items-center justify-center gap-2">
        <button
          onClick={onRestart}
          className="rounded-md border px-4 py-1.5 text-xs font-medium text-muted-foreground hover:bg-secondary hover:text-foreground transition-colors"
        >
          {t('results.importAnother')}
        </button>
        <button
          onClick={onClose}
          className="rounded-md bg-primary px-4 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        >
          {t('results.done')}
        </button>
      </div>
    </div>
  );
}
