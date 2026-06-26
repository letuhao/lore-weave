// W6 §4.5 — the Tier-W cost-confirm card (the studio's existing composition_generate
// confirm pattern, reused for motif Tier-W ops). The FE NEVER executes the spend —
// it shows the $ estimate + token count + quota remaining, an explicit Confirm /
// Cancel, and a one-line "what this does". Idempotency: Confirm DISABLES after the
// first click (no double-spend); a consumed-token reply is treated as success in
// the api layer. Render-only.
import { useTranslation } from 'react-i18next';
import type { CostEstimate } from '../types';

type Props = {
  estimate: CostEstimate;
  whatItDoes: string;          // a one-line, already-localized description
  confirming: boolean;         // mutation pending → disable Confirm
  onConfirm: () => void;
  onCancel: () => void;
};

export function CostConfirmCard({ estimate, whatItDoes, confirming, onConfirm, onCancel }: Props) {
  const { t } = useTranslation('composition');
  return (
    <div data-testid="motif-cost-confirm" role="group" aria-label={t('motif.cost.title', { defaultValue: 'Confirm cost' })} className="rounded border border-amber-300 bg-amber-50 p-3 text-sm dark:border-amber-800 dark:bg-amber-950/30">
      <p className="font-medium text-amber-800 dark:text-amber-200">{whatItDoes}</p>
      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-neutral-500">{t('motif.cost.usd', { defaultValue: 'Est. cost' })}</dt>
          <dd data-testid="motif-cost-usd" className="font-medium">${estimate.est_usd.toFixed(2)}</dd>
        </div>
        <div>
          <dt className="text-neutral-500">{t('motif.cost.tokens', { defaultValue: 'Est. tokens' })}</dt>
          <dd className="font-medium">{estimate.est_tokens.toLocaleString()}</dd>
        </div>
        <div>
          <dt className="text-neutral-500">{t('motif.cost.quota', { defaultValue: 'Quota left' })}</dt>
          <dd className="font-medium">{estimate.quota_remaining == null ? '∞' : estimate.quota_remaining}</dd>
        </div>
      </dl>
      <div className="mt-3 flex items-center justify-end gap-2">
        <button
          type="button"
          data-testid="motif-cost-cancel"
          className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
          onClick={onCancel}
          disabled={confirming}
        >
          {t('motif.action.cancel', { defaultValue: 'Cancel' })}
        </button>
        <button
          type="button"
          data-testid="motif-cost-confirm-btn"
          className="rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          onClick={onConfirm}
          disabled={confirming}
        >
          {confirming
            ? t('motif.cost.confirming', { defaultValue: 'Working…' })
            : t('motif.cost.confirm', { defaultValue: 'Confirm' })}
        </button>
      </div>
    </div>
  );
}
