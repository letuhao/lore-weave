// Shared empty state for the 3 quality-* panels backed by composition-service
// (promises/critic/coverage) when this book has no composition Work yet
// (useWorkResolution status !== 'found'). Quality is a read-only diagnostic
// destination — it doesn't try to replicate the old workspace's create/pick
// wizard, it just explains why there's nothing to show yet.
import { useTranslation } from 'react-i18next';

export function QualityNoWorkState({ testId }: { testId: string }) {
  const { t } = useTranslation('studio');
  return (
    <div data-testid={testId} className="flex h-full min-h-0 items-center justify-center p-6 text-center">
      <p className="max-w-sm text-sm text-neutral-500 dark:text-neutral-400">
        {t('quality.noWork', {
          defaultValue: 'This book has no co-writer session yet — start composing a chapter first, then quality data will appear here.',
        })}
      </p>
    </div>
  );
}
