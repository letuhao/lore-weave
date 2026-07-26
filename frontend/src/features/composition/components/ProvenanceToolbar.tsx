// LOOM Composition (T5.3) — AI-provenance toolbar (render-only).
// Eye toggle for the unreviewed-AI underlay + a live count + "mark all reviewed".
// Hidden entirely when there is no AI prose AND the underlay is on (nothing to do).
import { useTranslation } from 'react-i18next';

type Props = {
  visible: boolean;
  unreviewedCount: number;
  onToggleVisible: () => void;
  onMarkAllReviewed: () => void;
};

export function ProvenanceToolbar({ visible, unreviewedCount, onToggleVisible, onMarkAllReviewed }: Props) {
  const { t } = useTranslation('composition');
  if (unreviewedCount === 0 && visible) return null; // nothing to review, underlay on → no chrome

  return (
    <div
      data-testid="provenance-toolbar"
      className="flex items-center gap-2 rounded-md border border-violet-300/40 bg-violet-50/40 px-2 py-1 text-xs dark:border-violet-400/20 dark:bg-violet-400/5"
    >
      <span className="font-medium text-violet-700 dark:text-violet-300">
        {t('provenance.title', { defaultValue: 'AI provenance' })}
      </span>
      <span data-testid="provenance-count" className="text-neutral-600 dark:text-neutral-400">
        {t('provenance.unreviewedCount', { n: unreviewedCount, defaultValue: '{{n}} unreviewed' })}
      </span>
      <div className="ml-auto flex items-center gap-1.5">
        <button
          type="button"
          data-testid="provenance-toggle-visible"
          className="rounded border px-1.5 py-0.5 hover:bg-violet-100 dark:hover:bg-violet-400/10"
          onClick={onToggleVisible}
          aria-pressed={visible}
        >
          {visible
            ? t('provenance.hide', { defaultValue: 'Hide' })
            : t('provenance.show', { defaultValue: 'Show' })}
        </button>
        <button
          type="button"
          data-testid="provenance-mark-all"
          className="rounded bg-violet-600 px-1.5 py-0.5 text-white disabled:opacity-40"
          onClick={onMarkAllReviewed}
          disabled={unreviewedCount === 0}
        >
          {t('provenance.markAllReviewed', { defaultValue: 'Mark all reviewed' })}
        </button>
      </div>
    </div>
  );
}
