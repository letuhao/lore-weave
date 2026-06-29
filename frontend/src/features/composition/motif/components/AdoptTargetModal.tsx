// W6 §4 / §4.5 — adopt → YOUR library. A focus-trapped dialog (Esc closes, focus
// returns to trigger) that mints the confirm token, then shows the CostConfirmCard
// (adopt is Tier-W — R2.8). On quota_exceeded shows the §4.4 non-blocking explainer
// (never a silent fail). Render-only — driven by useAdoptFlow. Adopt defaults to the
// user's global library; when a book is in context the user may target THIS book's
// library instead (D-MOTIF-ADOPT-PER-BOOK = model A book-scoped filter).
import { useTranslation } from 'react-i18next';
import { useEffect, useRef } from 'react';
import type { CostEstimate, QuotaError } from '../types';
import { CostConfirmCard } from './CostConfirmCard';

type Props = {
  open: boolean;
  estimate: CostEstimate | null;
  quota: QuotaError | null;
  minting: boolean;
  confirming: boolean;
  /** the adopt destination + whether a book context is available (else book is hidden) */
  target: 'user' | 'book' | 'book_shared';
  canTargetBook: boolean;
  onTarget: (t: 'user' | 'book' | 'book_shared') => void;
  onMint: () => void;
  onConfirm: () => void;
  onCancel: () => void;
};

export function AdoptTargetModal({
  open, estimate, quota, minting, confirming,
  target, canTargetBook, onTarget, onMint, onConfirm, onCancel,
}: Props) {
  const { t } = useTranslation('composition');
  const ref = useRef<HTMLDivElement>(null);

  // Focus the dialog on open + Esc to close (focus-trap basics — §5.1).
  useEffect(() => {
    if (open) ref.current?.focus();
  }, [open]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4" onMouseDown={(e) => { if (e.target === e.currentTarget) onCancel(); }}>
      <div
        ref={ref}
        role="dialog"
        aria-modal="true"
        aria-label={t('motif.adopt.title', { defaultValue: 'Adopt motif' })}
        tabIndex={-1}
        data-testid="motif-adopt-modal"
        className="w-full max-w-md rounded-lg border border-neutral-200 bg-white p-4 shadow-xl outline-none dark:border-neutral-700 dark:bg-neutral-900"
        onKeyDown={(e) => { if (e.key === 'Escape') onCancel(); }}
      >
        <h2 className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {t('motif.adopt.title', { defaultValue: 'Adopt motif' })}
        </h2>
        <p className="mt-1 text-xs text-neutral-500">
          {t('motif.adopt.bodyUser', { defaultValue: 'Adopt makes your own private, editable copy in your library.' })}
        </p>

        {quota && (
          <div data-testid="motif-adopt-quota" role="alert" className="mt-3 rounded border border-amber-300 bg-amber-50 p-2 text-xs text-amber-800 dark:border-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
            {t('motif.quota.adopt', {
              used: quota.used, limit: quota.limit,
              defaultValue: "You've adopted {{used}}/{{limit}} this period — archive some or wait.",
            })}
          </div>
        )}

        {estimate ? (
          <div className="mt-3">
            <CostConfirmCard
              estimate={estimate}
              whatItDoes={t('motif.adopt.whatItDoes', { defaultValue: 'Copy this motif into your library (a private, editable clone).' })}
              confirming={confirming}
              onConfirm={onConfirm}
              onCancel={onCancel}
            />
          </div>
        ) : (
          <div className="mt-4">
            {canTargetBook && (
              <fieldset className="mb-3" data-testid="motif-adopt-target">
                <legend className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
                  {t('motif.adopt.targetLegend', { defaultValue: 'Add to' })}
                </legend>
                <div className="mt-1 flex gap-2">
                  <button
                    type="button"
                    data-testid="motif-adopt-target-user"
                    aria-pressed={target === 'user'}
                    onClick={() => onTarget('user')}
                    className={`rounded border px-2 py-1 text-xs ${target === 'user' ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200' : 'border-neutral-300 text-neutral-600 dark:border-neutral-600 dark:text-neutral-300'}`}
                  >
                    {t('motif.adopt.targetUser', { defaultValue: 'My library' })}
                  </button>
                  <button
                    type="button"
                    data-testid="motif-adopt-target-book"
                    aria-pressed={target === 'book'}
                    onClick={() => onTarget('book')}
                    className={`rounded border px-2 py-1 text-xs ${target === 'book' ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200' : 'border-neutral-300 text-neutral-600 dark:border-neutral-600 dark:text-neutral-300'}`}
                  >
                    {t('motif.adopt.targetBook', { defaultValue: 'This book (private)' })}
                  </button>
                  <button
                    type="button"
                    data-testid="motif-adopt-target-book-shared"
                    aria-pressed={target === 'book_shared'}
                    onClick={() => onTarget('book_shared')}
                    className={`rounded border px-2 py-1 text-xs ${target === 'book_shared' ? 'border-amber-500 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200' : 'border-neutral-300 text-neutral-600 dark:border-neutral-600 dark:text-neutral-300'}`}
                  >
                    {t('motif.adopt.targetBookShared', { defaultValue: 'Share with collaborators' })}
                  </button>
                </div>
                {target === 'book_shared' && (
                  <p className="mt-1 text-[11px] text-neutral-500">
                    {t('motif.adopt.sharedHint', { defaultValue: "Everyone with access to this book can see and edit this motif." })}
                  </p>
                )}
              </fieldset>
            )}
            <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              data-testid="motif-adopt-cancel"
              className="rounded border border-neutral-300 px-2 py-1 text-xs text-neutral-600 hover:bg-neutral-100 dark:border-neutral-600 dark:text-neutral-300 dark:hover:bg-neutral-800"
              onClick={onCancel}
            >
              {t('motif.action.cancel', { defaultValue: 'Cancel' })}
            </button>
            <button
              type="button"
              data-testid="motif-adopt-mint"
              className="rounded bg-amber-600 px-3 py-1 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
              onClick={onMint}
              disabled={minting}
            >
              {minting
                ? t('motif.adopt.estimating', { defaultValue: 'Preparing…' })
                : t('motif.adopt.continue', { defaultValue: 'Continue' })}
            </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
