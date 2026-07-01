// LOOM Composition · Q1+Q2 Quality Report (view) — read-only advisory panel in the Polish gate.
//
// Surfaces the planner's own judges to the author: the 4-dim critic (coherence / voice / pacing /
// canon) and the promise audit (what the chapter sets up vs. what it DROPS). Diagnostic only —
// no accept/reject, no apply. It informs; the author decides what to rewrite.
import { useTranslation } from 'react-i18next';

import { useQualityReport } from '../hooks/useQualityReport';
import type { QualityCritic } from '../api';

interface Props {
  projectId: string;
  chapterId: string;
  token: string | null;
  modelRef: string;
}

const DIMS: (keyof Pick<QualityCritic, 'coherence' | 'voice_match' | 'pacing' | 'canon_consistency'>)[] = [
  'coherence', 'voice_match', 'pacing', 'canon_consistency',
];

export function QualityReportSection({ projectId, chapterId, token, modelRef }: Props) {
  const { t } = useTranslation('composition');
  const q = useQualityReport(projectId, chapterId, token, modelRef);
  const critic = q.report?.critic;
  const promises = q.report?.promises;

  return (
    <div data-testid="composition-quality-report" className="mt-3 flex flex-col gap-2 border-t border-neutral-100 pt-3 dark:border-neutral-800">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-neutral-600 dark:text-neutral-300">
          {t('qualityTitle', { defaultValue: 'Quality report' })}
        </span>
        <button
          type="button"
          data-testid="quality-run"
          disabled={!modelRef || q.loading}
          onClick={() => q.run()}
          className="rounded bg-sky-600 px-2 py-1 text-[11px] text-white disabled:opacity-50"
        >
          {q.loading
            ? t('qualityLoading', { defaultValue: 'Analyzing…' })
            : q.ran
              ? t('qualityRerun', { defaultValue: 'Re-analyze' })
              : t('qualityRun', { defaultValue: 'Analyze quality' })}
        </button>
      </div>
      <p className="text-[11px] text-neutral-400">
        {t('qualityIntro', {
          defaultValue: 'Advisory only — how the chapter scores and what it promises but never pays off. Nothing here changes your prose.',
        })}
      </p>

      {q.error && <div data-testid="quality-error" className="text-[11px] text-amber-600">{q.error}</div>}

      {critic && (
        <div className="flex flex-wrap gap-2" data-testid="quality-critic">
          {critic.error ? (
            <span className="text-[11px] text-neutral-400">{t('qualityCriticNa', { defaultValue: 'Critic unavailable.' })}</span>
          ) : (
            DIMS.map((d) => (
              <span key={d} className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300">
                {t(`qualityDim_${d}`, { defaultValue: d.replace('_', ' ') })}: {critic[d] ?? '—'}/5
              </span>
            ))
          )}
        </div>
      )}

      {critic && critic.violations.length > 0 && (
        <ul className="flex flex-col gap-0.5" data-testid="quality-violations">
          {critic.violations.map((v, i) => (
            <li key={i} className="text-[11px] text-rose-500">
              ⚠ {v.why}{v.span ? ` — “${v.span}”` : ''}
            </li>
          ))}
        </ul>
      )}

      {promises?.error && (
        <span data-testid="quality-promises-na" className="text-[11px] text-neutral-400">
          {t('qualityPromisesNa', { defaultValue: 'Promise audit unavailable.' })}
        </span>
      )}

      {promises && !promises.error && (
        <div className="flex flex-col gap-1" data-testid="quality-promises">
          {promises.dropped.length > 0 ? (
            <>
              <span className="text-[11px] font-medium text-rose-600">
                {t('qualityDropped', { defaultValue: '{{n}} dropped promise(s) — set up but never paid off:', n: promises.dropped_count })}
              </span>
              <ul className="flex flex-col gap-0.5">
                {promises.dropped.map((p, i) => (
                  <li key={i} className="text-[11px] text-rose-500">• {p}</li>
                ))}
              </ul>
            </>
          ) : (
            q.ran && <span className="text-[11px] text-emerald-600">{t('qualityNoDrop', { defaultValue: 'No dropped promises — setups are paid off.' })}</span>
          )}
          {promises.resolved.length > 0 && (
            <span className="text-[10px] text-neutral-400">
              {t('qualityResolved', { defaultValue: '{{r}}/{{i}} promises resolved', r: promises.resolved_count, i: promises.introduced_count })}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
