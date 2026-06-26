// LOOM Composition (WS-B3 M4) — the what-if take judge badge.
//
// Renders each critic dim RELATIVE to the canon baseline (▲ better / ▼ worse / =
// same), with the absolute take/canon scores on hover. Degrade-safe: no baseline (or
// still judging) → the absolute take dims + a status note, never a fabricated 0-delta.
import { useTranslation } from 'react-i18next';
import type { Critic } from '../types';
import { vsCanonDeltas, deltaGlyph, DIM_LETTER } from '../hooks/useVsCanonDelta';

export function WhatIfJudgeBadge({ judge, canon, baselineAvailable, judging }: {
  judge: Critic;
  canon: Critic | null;
  baselineAvailable: boolean;
  judging: boolean;
}) {
  const { t } = useTranslation('composition');
  const deltas = vsCanonDeltas(judge, canon);
  const hasCanon = canon !== null && baselineAvailable;

  const absolute = deltas.map((d) => `${DIM_LETTER[d.dim]}${d.take ?? '–'}`).join(' · ');

  if (hasCanon) {
    return (
      <span
        data-testid="whatif-judge-badge"
        data-mode="delta"
        className="font-mono text-[10px] text-purple-700/80 dark:text-purple-300/80"
        title={deltas
          .map((d) => `${DIM_LETTER[d.dim]}: ${t('whatif.vsCanon.take', { defaultValue: 'take' })} ${d.take ?? '–'} ${t('whatif.vsCanon.vs', { defaultValue: 'vs canon' })} ${d.canon ?? '–'}`)
          .join(' · ')}
      >
        {deltas.map((d) => (
          <span key={d.dim} className="mr-1">
            {DIM_LETTER[d.dim]}
            <span
              className={
                d.delta === null ? 'opacity-50'
                  : d.delta > 0 ? 'text-green-600 dark:text-green-400'
                    : d.delta < 0 ? 'text-red-600 dark:text-red-400'
                      : 'opacity-70'
              }
            >
              {deltaGlyph(d.delta)}
            </span>
          </span>
        ))}
      </span>
    );
  }

  // No canon baseline (or the verdict is still loading) → absolute take dims + status.
  return (
    <span
      data-testid="whatif-judge-badge"
      data-mode="absolute"
      className="font-mono text-[10px] text-purple-700/80 dark:text-purple-300/80"
      title={t('whatif.vsCanon.absoluteHint', { defaultValue: 'Take scores (no canon baseline to compare)' })}
    >
      {absolute}
      {judging && (
        <span className="ml-1 opacity-60">{t('whatif.vsCanon.judging', { defaultValue: '· vs canon…' })}</span>
      )}
      {!judging && !baselineAvailable && (
        <span className="ml-1 opacity-60">{t('whatif.vsCanon.noBaseline', { defaultValue: '· no canon baseline' })}</span>
      )}
    </span>
  );
}
