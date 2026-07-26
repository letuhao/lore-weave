// WI-1 (mockup 04) — the corpus-MINING panel. Pick a scope (this book | my whole
// corpus) + a min-support + a model → PROPOSE (mint a confirm token) → confirm the cost
// → poll → the mined drafts land in the Drafts tab. Render-only; logic is in useMotifMine.
// Corpus scope yields real patterns (PrefixSpan counts BOOKS as sequences); a single book
// rarely does — the copy steers users there.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { CostConfirmCard } from './CostConfirmCard';
import { ModelRolePicker } from '../../../campaigns/components/ModelRolePicker';
import { useMotifMine } from '../hooks/useMotifMine';

type Props = {
  token: string | null;
  bookId?: string | null;
  /** jump to the Drafts tab after a successful mine (so the user reviews/promotes). */
  onViewDrafts?: () => void;
  onClose?: () => void;
};

export function MotifMinePanel({ token, bookId, onViewDrafts, onClose }: Props) {
  const { t } = useTranslation('composition');
  const mine = useMotifMine(token, bookId);
  const [model, setModel] = useState<string | null>(null);
  const busy = mine.mint.isPending || mine.confirm.isPending;

  return (
    <div data-testid="motif-mine-panel" className="flex flex-col gap-2 p-2 text-[11px]">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {t('motif.mine.title', { defaultValue: 'Mine motifs from your writing' })}
        </span>
        {onClose && (
          <button type="button" data-testid="motif-mine-close" className="text-neutral-400 hover:text-neutral-600" onClick={onClose}>✕</button>
        )}
      </div>

      {mine.estimate ? (
        <CostConfirmCard
          estimate={mine.estimate}
          whatItDoes={t('motif.mine.what', {
            defaultValue: 'Abstract the recurring plot patterns in your corpus into draft motifs (LLM-metered).',
          })}
          confirming={mine.confirm.isPending}
          onConfirm={() => mine.confirm.mutate()}
          onCancel={() => mine.cancel()}
        />
      ) : (
        <div className="flex flex-col gap-1.5">
          {/* scope */}
          <div role="radiogroup" aria-label={t('motif.mine.scope', { defaultValue: 'Scope' })} className="flex gap-1">
            <button
              type="button"
              role="radio"
              aria-checked={mine.scope === 'book'}
              data-testid="motif-mine-scope-book"
              disabled={!mine.canBook || busy}
              className={`rounded px-2 py-0.5 ${mine.scope === 'book' ? 'bg-amber-600 text-white' : 'border border-neutral-300 dark:border-neutral-600'} disabled:opacity-40`}
              onClick={() => mine.setScope('book')}
            >
              {t('motif.mine.thisBook', { defaultValue: 'This book' })}
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={mine.scope === 'corpus'}
              data-testid="motif-mine-scope-corpus"
              disabled={busy}
              className={`rounded px-2 py-0.5 ${mine.scope === 'corpus' ? 'bg-amber-600 text-white' : 'border border-neutral-300 dark:border-neutral-600'}`}
              onClick={() => mine.setScope('corpus')}
            >
              {t('motif.mine.corpus', { defaultValue: 'My whole corpus' })}
            </button>
          </div>
          {mine.scope === 'book' && (
            <p data-testid="motif-mine-book-hint" className="text-[10px] text-amber-700 dark:text-amber-400">
              {t('motif.mine.bookHint', { defaultValue: 'A single book rarely repeats a pattern — corpus scope finds more.' })}
            </p>
          )}

          {/* min support */}
          <label className="flex items-center gap-2">
            <span className="text-neutral-600 dark:text-neutral-300">{t('motif.mine.minSupport', { defaultValue: 'Min support' })}</span>
            <input
              type="number"
              min={2}
              max={20}
              data-testid="motif-mine-min-support"
              className="w-16 rounded border border-neutral-300 px-1 py-0.5 dark:border-neutral-600 dark:bg-neutral-800"
              value={mine.minSupport}
              disabled={busy}
              onChange={(e) => mine.setMinSupport(Math.max(2, Number(e.target.value) || 2))}
            />
          </label>

          {/* model */}
          <ModelRolePicker
            capability="chat"
            label={t('motif.mine.model', { defaultValue: 'Mining model' })}
            value={model}
            onChange={setModel}
            disabled={busy}
          />

          <button
            type="button"
            data-testid="motif-mine-run-btn"
            className="self-start rounded border border-amber-500 px-2 py-0.5 text-amber-700 hover:bg-amber-50 disabled:opacity-50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            disabled={!model || !token || busy}
            onClick={() => model && mine.mint.mutate(model)}
          >
            {mine.mint.isPending
              ? t('motif.mine.estimating', { defaultValue: 'Estimating…' })
              : mine.confirm.isPending
                ? t('motif.mine.running', { defaultValue: 'Mining…' })
                : t('motif.mine.run', { defaultValue: 'Mine' })}
          </button>

          {(mine.mint.isError || mine.confirm.isError) && (
            <p data-testid="motif-mine-error" className="text-rose-600 dark:text-rose-400">
              {mine.isQuota
                ? t('motif.mine.quota', { defaultValue: 'Mining quota reached.' })
                : ((mine.error as Error | null)?.message
                  || t('motif.mine.failed', { defaultValue: 'Mining failed.' }))}
            </p>
          )}
        </div>
      )}

      {/* result summary */}
      {mine.result && (
        <div data-testid="motif-mine-result" className="rounded border border-neutral-200 p-2 dark:border-neutral-700">
          {mine.result.mined > 0 ? (
            <button
              type="button"
              data-testid="motif-mine-view-drafts"
              className="font-medium text-amber-700 underline hover:text-amber-800 dark:text-amber-300"
              onClick={() => onViewDrafts?.()}
            >
              {t('motif.mine.minedN', { n: mine.result.mined, defaultValue: '{{n}} draft(s) mined — review them' })}
            </button>
          ) : (
            <p data-testid="motif-mine-none" className="text-neutral-500">
              {mine.result.reason === 'beat_extractor_unavailable'
                ? t('motif.mine.noCorpus', { defaultValue: 'No analyzed corpus yet — extract a book first, then mine.' })
                : t('motif.mine.noPatterns', { defaultValue: 'No recurring patterns found. Try corpus scope or a lower min-support.' })}
            </p>
          )}
          {/* §11 no-silent-drop: below-gate candidates were considered but not added */}
          {mine.result.below_gate != null && mine.result.below_gate > 0 && (
            <p data-testid="motif-mine-below-gate" className="mt-1 text-[10px] text-neutral-400">
              {t('motif.mine.belowGate', { n: mine.result.below_gate, defaultValue: '{{n}} candidate(s) held below the quality gate.' })}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
