// W6 §3.4 / §6.2 — "why this motif". Simple mode renders ONLY match_reason.summary
// (the plain sentence — "show, don't define"); expert mode expands the tension /
// genre / precond / cosine numeric breakdown. Render-only.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { MatchReason } from '../types';
import { useMotifSimpleMode } from '../context/MotifSimpleModeContext';

export function MatchReasonChip({ reason }: { reason: MatchReason }) {
  const { t } = useTranslation('composition');
  const { simple } = useMotifSimpleMode();
  const [open, setOpen] = useState(false);

  if (simple) {
    return (
      <p data-testid="motif-match-reason" className="text-[11px] italic text-neutral-500 dark:text-neutral-400">
        {reason.summary}
      </p>
    );
  }

  return (
    <div data-testid="motif-match-reason" className="text-[11px] text-neutral-500 dark:text-neutral-400">
      <button type="button" aria-expanded={open} className="underline decoration-dotted" onClick={() => setOpen((v) => !v)}>
        {t('motif.match.why', { defaultValue: 'Why this motif?' })}
      </button>
      {open && (
        <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2">
          <dt>{t('motif.match.tension', { defaultValue: 'Tension fit' })}</dt><dd>{reason.tension.toFixed(2)}</dd>
          <dt>{t('motif.match.genre', { defaultValue: 'Genre' })}</dt><dd>{reason.genre.join(', ') || '—'}</dd>
          <dt>{t('motif.match.precond', { defaultValue: 'Setup' })}</dt><dd>{reason.precond || '—'}</dd>
          <dt>{t('motif.match.cosine', { defaultValue: 'Similarity' })}</dt><dd>{reason.cosine.toFixed(2)}</dd>
        </dl>
      )}
    </div>
  );
}
