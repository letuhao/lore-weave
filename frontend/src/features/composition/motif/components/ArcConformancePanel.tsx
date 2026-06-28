// W10 (mockup 07-B) — the ARC-CONFORMANCE dashboard. Renders the coarse structural diff
// of the materialized bindings vs the arc template: thread-progress coverage, the realized
// pacing curve (vs the template curve when present), structural succession flags, and the
// §12.6 unmaterialized (folded-away) placements. Render-only; logic is in useArcConformance.
// Honest by construction: stamps "Coarse · structural only" (causal_verified=false).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MotifStateBoundary } from './MotifStateBoundary';
import { useArcConformance } from '../hooks/useArcConformance';

type Props = { projectId: string | null | undefined; arcTemplateId: string; token: string | null };

export function ArcConformancePanel({ projectId, arcTemplateId, token }: Props) {
  const { t } = useTranslation('composition');
  // deep = the realized-from-PROSE pacing overlay (a cross-service read) — opt-in via a button.
  const [deep, setDeep] = useState(false);
  const q = useArcConformance(projectId, arcTemplateId, token, deep);
  const r = q.data;

  // no work bound yet → nothing is materialized, so there's nothing to conform.
  if (!projectId) {
    return (
      <p data-testid="arc-conf-no-work" className="p-2 text-center text-[11px] text-neutral-500">
        {t('motif.arcConf.noWork', { defaultValue: 'Materialize this arc into a book to see conformance.' })}
      </p>
    );
  }

  return (
    <div data-testid="arc-conformance-panel" className="flex flex-col gap-2 p-1">
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium text-neutral-800 dark:text-neutral-100">
          {t('motif.arcConf.title', { defaultValue: 'Arc conformance' })}
        </span>
        <div className="flex items-center gap-1.5">
          {!deep && (
            <button
              type="button"
              data-testid="arc-conf-deep-btn"
              className="rounded border border-amber-400 px-1.5 py-0.5 text-[10px] text-amber-700 dark:text-amber-300"
              onClick={() => setDeep(true)}
            >
              {t('motif.arcConf.checkProse', { defaultValue: 'Check prose drift' })}
            </button>
          )}
          <span data-testid="arc-conf-coarse-badge" className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-500 dark:bg-neutral-700 dark:text-neutral-300">
            {t('motif.arcConf.coarse', { defaultValue: 'Coarse · structural only' })}
          </span>
        </div>
      </div>

      <MotifStateBoundary isLoading={q.isLoading} isError={q.isError} onRetry={() => q.refetch()} skeleton="rows">
        {r && r.chapter_count === 0 ? (
          <p data-testid="arc-conf-empty" className="p-3 text-center text-[11px] text-neutral-500">
            {t('motif.arcConf.empty', { defaultValue: 'Nothing materialized from this arc yet.' })}
          </p>
        ) : r ? (
          <div className="flex flex-col gap-3 text-[11px]">
            {/* thread-progress coverage */}
            <section>
              <h4 className="mb-1 font-medium text-neutral-600 dark:text-neutral-300">{t('motif.arcConf.threads', { defaultValue: 'Thread progress' })}</h4>
              <ul className="flex flex-col gap-1">
                {r.thread_progress.map((tp) => (
                  <li key={tp.thread} data-testid={`arc-conf-thread-${tp.thread}`} className="flex items-center justify-between gap-2">
                    <span className="truncate">{tp.label}</span>
                    <span className={tp.covered < tp.planned ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-400'}>
                      {tp.covered}/{tp.planned}
                      {tp.missing.length > 0 && (
                        <span data-testid={`arc-conf-missing-${tp.thread}`} className="ml-1 text-neutral-500">({tp.missing.map((m) => m.motif_code).join(', ')})</span>
                      )}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            {/* pacing curve */}
            <section data-testid="arc-conf-pacing">
              <h4 className="mb-1 font-medium text-neutral-600 dark:text-neutral-300">
                {t('motif.arcConf.pacing', { defaultValue: 'Pacing' })}
                {r.pacing.comparable && r.pacing.max_drift != null && (
                  <span data-testid="arc-conf-drift" className="ml-1 text-neutral-500">{t('motif.arcConf.drift', { drift: r.pacing.max_drift, defaultValue: 'max drift {{drift}}' })}</span>
                )}
              </h4>
              <div className="flex flex-wrap gap-1">
                {r.pacing.realized.map((p) => (
                  <span key={p.chapter_index} className="rounded bg-neutral-100 px-1 tabular-nums text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300" title={`ch ${p.chapter_index}`}>
                    {Math.round(p.avg_tension)}
                  </span>
                ))}
                {!r.pacing.comparable && (
                  <span className="text-neutral-400">{t('motif.arcConf.noPlanned', { defaultValue: 'no template curve' })}</span>
                )}
              </div>
            </section>

            {/* structural succession */}
            <section>
              <h4 className="mb-1 font-medium text-neutral-600 dark:text-neutral-300">{t('motif.arcConf.succession', { defaultValue: 'Succession (structural)' })}</h4>
              {r.succession.threads.every((s) => s.violations.length === 0) ? (
                <p data-testid="arc-conf-succession-ok" className="text-neutral-500">{t('motif.arcConf.successionOk', { defaultValue: 'No ordering violations.' })}</p>
              ) : (
                <ul className="flex flex-col gap-0.5">
                  {r.succession.threads.filter((s) => s.violations.length > 0).map((s) => (
                    <li key={s.thread} data-testid={`arc-conf-violation-${s.thread}`} className="text-amber-700 dark:text-amber-300">
                      {t('motif.arcConf.violation', { label: s.label, n: s.violations.length, defaultValue: '{{label}}: {{n}} out-of-order' })}
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* unmaterialized (folded away) */}
            {r.unmaterialized.length > 0 && (
              <section data-testid="arc-conf-unmaterialized">
                <h4 className="mb-1 font-medium text-neutral-600 dark:text-neutral-300">{t('motif.arcConf.unmaterialized', { defaultValue: 'Not materialized' })}</h4>
                <p className="text-neutral-500">{r.unmaterialized.map((u) => u.motif_code).join(', ')}</p>
              </section>
            )}

            {/* DEEP overlay — realized-from-PROSE pacing drift (only when deep was fetched) */}
            {r.deep && (
              <section data-testid="arc-conf-deep" className="rounded border border-indigo-200 p-2 dark:border-indigo-900">
                <h4 className="mb-1 font-medium text-indigo-700 dark:text-indigo-300">
                  {t('motif.arcConf.proseDrift', { defaultValue: 'Prose drift (realized vs plan)' })}
                </h4>
                {!r.deep.available ? (
                  <p data-testid="arc-conf-deep-empty" className="text-neutral-500">
                    {t('motif.arcConf.noProse', { defaultValue: 'No extracted prose yet — generate scenes to measure drift.' })}
                  </p>
                ) : (
                  <div className="flex flex-col gap-1">
                    <div className="flex flex-wrap items-center gap-2">
                      {r.deep.pacing.max_drift != null && (
                        <span data-testid="arc-conf-deep-drift" className="text-indigo-700 dark:text-indigo-300">
                          {t('motif.arcConf.maxDrift', { drift: r.deep.pacing.max_drift, defaultValue: 'max drift {{drift}}' })}
                        </span>
                      )}
                      <span className="text-neutral-400">{t('motif.arcConf.proseScale', { defaultValue: 'tension from extracted events (1–5 ×20)' })}</span>
                    </div>
                    <div className="flex flex-wrap gap-1">
                      {r.deep.pacing.realized.map((p) => (
                        <span key={p.chapter_index} className="rounded bg-indigo-50 px-1 tabular-nums text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300" title={`ch ${p.chapter_index}`}>
                          {Math.round(p.avg_tension)}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {/* honest: the two dims the Option-A extractor can't yet realize from prose */}
                <p data-testid="arc-conf-deep-blocked" className="mt-1 text-[10px] text-neutral-400">
                  {t('motif.arcConf.deepBlocked', { defaultValue: 'Thread + succession from prose need the thread-tagging extractor (P4+).' })}
                </p>
              </section>
            )}
          </div>
        ) : null}
      </MotifStateBoundary>
    </div>
  );
}
