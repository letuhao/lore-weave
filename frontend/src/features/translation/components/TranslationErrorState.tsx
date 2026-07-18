// Spec 29 D9 — the one typed error surface shared by every translation panel (the matrix,
// the version panel, the modal checklist). Renders a canned, localized message by kind and a
// Retry ONLY for retryable failures — a 403 gets "you don't have access", never a Retry that
// would just 403 again. Never renders the raw error string (T4's leaked proxy message).
import { AlertCircle, Ban, RefreshCw } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { cn } from '@/lib/utils';
import { classifyTranslationError } from '../lib/translationError';

export function TranslationErrorState({
  error,
  onRetry,
  className,
  compact,
}: {
  error: unknown;
  /** Offered only for retryable errors; omit to suppress Retry entirely. */
  onRetry?: () => void;
  className?: string;
  /** Inline variant for the modal checklist region (no big padding). */
  compact?: boolean;
}) {
  const { t } = useTranslation('translation');
  const { kind } = classifyTranslationError(error);
  const message =
    kind === 'forbidden' ? t('error.forbidden')
    : kind === 'notfound' ? t('error.notfound')
    : t('error.retryable');
  const showRetry = kind === 'retryable' && !!onRetry;
  const Icon = kind === 'forbidden' ? Ban : AlertCircle;

  return (
    <div
      data-testid="translation-error"
      data-kind={kind}
      role="alert"
      className={cn(
        'flex items-center gap-2 rounded-md border border-destructive/30 bg-destructive/5 text-destructive',
        compact ? 'px-3 py-2 text-[11px]' : 'p-4 text-sm',
        className,
      )}
    >
      <Icon className={cn('shrink-0', compact ? 'h-3.5 w-3.5' : 'h-4 w-4')} />
      <span className="flex-1">{message}</span>
      {showRetry && (
        <button
          type="button"
          onClick={onRetry}
          data-testid="translation-error-retry"
          className="inline-flex items-center gap-1 rounded-md border border-destructive/40 px-2 py-1 text-[11px] font-medium hover:bg-destructive/10"
        >
          <RefreshCw className={compact ? 'h-3 w-3' : 'h-3.5 w-3.5'} />
          {t('error.retry')}
        </button>
      )}
    </div>
  );
}
