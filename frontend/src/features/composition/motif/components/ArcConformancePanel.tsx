// W10 (mockup 07-B) — the ARC-CONFORMANCE dashboard. Renders the coarse structural diff
// of the materialized bindings vs the arc template: thread-progress coverage, the realized
// pacing curve (vs the template curve when present), structural succession flags, and the
// §12.6 unmaterialized (folded-away) placements. Render-only; logic is in useArcConformance.
// Honest by construction: stamps "Coarse · structural only" (causal_verified=false).
//
// D-W10-ARC-CONFORMANCE-DEEP-FE — the DEEP overlay (realized-from-prose pacing + thread
// progression + succession{structural/causal/entailment}) is a Tier-W JOB: pick a tagging
// model → PROPOSE (mint a confirm token via the FE→MCP-tool bridge) → confirm the cost →
// poll → render the deep arc report. It is NOT a synchronous GET (that would time out on a
// real book — ~120 LLM tagging calls).
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MotifStateBoundary } from './MotifStateBoundary';
import { CostConfirmCard } from './CostConfirmCard';
import { ModelRolePicker } from '../../../campaigns/components/ModelRolePicker';
import { useArcConformance } from '../hooks/useArcConformance';
import { useArcConformanceRun } from '../hooks/useArcConformanceRun';

type Props = {
  projectId: string | null | undefined;
  arcTemplateId: string;
  token: string | null;
  // optional default for the deep tagging model picker (seeds the selection).
  modelRef?: string | null;
};

export function ArcConformancePanel({ projectId, arcTemplateId, token, modelRef }: Props) {
  const { t } = useTranslation('composition');
  // Coarse structural diff — the cheap GET (no LLM). The deep overlay is a separate JOB.
  const q = useArcConformance(projectId, arcTemplateId, token);
  const r = q.data;
  // Deep prose conformance — propose → confirm → poll (the cost-gated tagging job).
  const run = useArcConformanceRun(projectId, arcTemplateId, token);
  const [selectedModel, setSelectedModel] = useState<string | null>(modelRef ?? null);
  const deepReport = run.result?.deep ?? null;

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
        <span data-testid="arc-conf-coarse-badge" className="rounded bg-neutral-100 px-1.5 py-0.5 text-[10px] text-neutral-500 dark:bg-neutral-700 dark:text-neutral-300">
          {t('motif.arcConf.coarse', { defaultValue: 'Coarse · structural only' })}
        </span>
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
          </div>
        ) : null}
      </MotifStateBoundary>

      {/* DEEP arc-conformance JOB — pick a tagging model, propose, confirm the cost, poll. */}
      <section data-testid="arc-conf-deep-run" className="rounded border border-indigo-200 p-2 dark:border-indigo-900">
        <h4 className="mb-1 font-medium text-indigo-700 dark:text-indigo-300">
          {t('motif.arcConf.proseDriftTitle', { defaultValue: 'Deep prose conformance' })}
        </h4>
        {run.estimate ? (
          <CostConfirmCard
            estimate={run.estimate}
            whatItDoes={t('motif.arcConf.deepWhat', {
              defaultValue: 'Re-tag the book’s prose with your model and diff it against this arc (LLM-metered).',
            })}
            confirming={run.confirm.isPending}
            onConfirm={() => run.confirm.mutate()}
            onCancel={() => run.cancel()}
          />
        ) : (
          <div className="flex flex-col gap-1.5">
            <ModelRolePicker
              capability="chat"
              label={t('motif.arcConf.model', { defaultValue: 'Tagging model' })}
              value={selectedModel}
              onChange={setSelectedModel}
              disabled={run.mint.isPending || run.confirm.isPending}
            />
            <button
              type="button"
              data-testid="arc-conf-run-deep-btn"
              className="self-start rounded border border-indigo-400 px-2 py-0.5 text-[11px] text-indigo-700 hover:bg-indigo-50 disabled:opacity-50 dark:text-indigo-300 dark:hover:bg-indigo-950/40"
              disabled={!selectedModel || !token || run.mint.isPending || run.confirm.isPending}
              onClick={() => selectedModel && run.mint.mutate(selectedModel)}
            >
              {run.mint.isPending
                ? t('motif.arcConf.estimating', { defaultValue: 'Estimating…' })
                : run.confirm.isPending
                  ? t('motif.arcConf.running', { defaultValue: 'Running…' })
                  : t('motif.arcConf.runDeep', { defaultValue: 'Run deep conformance' })}
            </button>
            {(run.mint.isError || run.confirm.isError) && (
              <p data-testid="arc-conf-deep-error" className="text-[11px] text-rose-600 dark:text-rose-400">
                {((run.mint.error || run.confirm.error) as Error | null)?.message
                  || t('motif.arcConf.deepError', { defaultValue: 'Couldn’t run deep conformance.' })}
              </p>
            )}
          </div>
        )}

        {/* the deep report (from the completed job) */}
        {deepReport && (
          <div data-testid="arc-conf-deep" className="mt-2 flex flex-col gap-2">
            <div>
              <h5 className="mb-1 font-medium text-indigo-700 dark:text-indigo-300">
                {t('motif.arcConf.proseDrift', { defaultValue: 'Prose drift (realized vs plan)' })}
              </h5>
              {!deepReport.available ? (
                <p data-testid="arc-conf-deep-empty" className="text-[11px] text-neutral-500">
                  {t('motif.arcConf.noProse', { defaultValue: 'No extracted prose yet — generate scenes to measure drift.' })}
                </p>
              ) : (
                <div className="flex flex-col gap-1">
                  <div className="flex flex-wrap items-center gap-2 text-[11px]">
                    {deepReport.pacing.max_drift != null && (
                      <span data-testid="arc-conf-deep-drift" className="text-indigo-700 dark:text-indigo-300">
                        {t('motif.arcConf.maxDrift', { drift: deepReport.pacing.max_drift, defaultValue: 'max drift {{drift}}' })}
                      </span>
                    )}
                    <span className="text-neutral-400">{t('motif.arcConf.proseScale', { defaultValue: 'tension from extracted events (1–5 ×20)' })}</span>
                  </div>
                  <div className="flex flex-wrap gap-1">
                    {deepReport.pacing.realized.map((p) => (
                      <span key={p.chapter_index} className="rounded bg-indigo-50 px-1 tabular-nums text-[11px] text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300" title={`ch ${p.chapter_index}`}>
                        {Math.round(p.avg_tension)}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* deep thread-progression (unblocked by THREAD-TAG) — realized threads vs planned */}
            {deepReport.thread_progression.available ? (
              <div data-testid="arc-conf-deep-threads">
                <h5 className="mb-0.5 font-medium text-indigo-700 dark:text-indigo-300">
                  {t('motif.arcConf.proseThreads', { defaultValue: 'Threads in the prose' })}
                </h5>
                <ul className="flex flex-col gap-0.5 text-[11px]">
                  {deepReport.thread_progression.threads.map((th) => (
                    <li key={th.thread} data-testid={`arc-conf-deep-thread-${th.thread}`}
                      className={th.realized ? 'text-emerald-700 dark:text-emerald-400' : 'text-amber-700 dark:text-amber-300'}>
                      {/* dynamic values rendered RAW (resilient to missing i18n + assertable) */}
                      {th.label}: {th.realized
                        ? <span className="tabular-nums">{th.realized_chapters} {t('motif.arcConf.chShort', { defaultValue: 'ch' })}</span>
                        : t('motif.arcConf.threadMissing', { defaultValue: 'not in prose' })}
                    </li>
                  ))}
                </ul>
                {deepReport.thread_progression.unplanned.length > 0 && (
                  <p data-testid="arc-conf-deep-unplanned" className="text-[11px] text-neutral-500">
                    {t('motif.arcConf.unplannedLabel', { defaultValue: 'unplanned in prose' })}: {deepReport.thread_progression.unplanned.join(', ')}
                  </p>
                )}
              </div>
            ) : (
              <p data-testid="arc-conf-deep-untagged" className="text-[10px] text-neutral-400">
                {t('motif.arcConf.notTagged', { defaultValue: 'Thread-progression needs tagging — run with a model.' })}
              </p>
            )}

            {/* deep succession (structural / causal / entailment) */}
            {deepReport.succession.available ? (
              <div data-testid="arc-conf-deep-succession">
                <h5 className="mb-0.5 font-medium text-indigo-700 dark:text-indigo-300">
                  {t('motif.arcConf.proseSuccession', { defaultValue: 'Succession in the prose' })}
                  <span className="ml-1 text-[10px] text-neutral-400">
                    {deepReport.succession.causal_verified
                      ? t('motif.arcConf.causal', { defaultValue: 'causally verified' })
                      : t('motif.arcConf.structural', { defaultValue: 'structural' })}
                  </span>
                </h5>
                <p className="tabular-nums text-[11px] text-neutral-600 dark:text-neutral-300">
                  {deepReport.succession.legal}/{deepReport.succession.transitions} {t('motif.arcConf.legalTransitions', { defaultValue: 'legal' })}
                  {deepReport.succession.caused != null && deepReport.succession.caused > 0 && (
                    <span data-testid="arc-conf-deep-succ-caused" className="ml-1 text-indigo-700 dark:text-indigo-300">· {deepReport.succession.caused} {t('motif.arcConf.caused', { defaultValue: 'caused' })}</span>
                  )}
                  {deepReport.succession.entailed != null && deepReport.succession.entailed > 0 && (
                    <span data-testid="arc-conf-deep-succ-entailed" className="ml-1 text-indigo-700 dark:text-indigo-300">· {deepReport.succession.entailed} {t('motif.arcConf.entailed', { defaultValue: 'entailed' })}</span>
                  )}
                </p>
                {deepReport.succession.violations.length > 0 && (
                  <ul data-testid="arc-conf-deep-succ-violations" className="flex flex-col gap-0.5 text-[11px]">
                    {deepReport.succession.violations.map((v) => (
                      <li key={`${v.from_motif_code}-${v.to_motif_code}`} className="text-amber-700 dark:text-amber-300">
                        {v.from_motif_code} → {v.to_motif_code}
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ) : (
              <p data-testid="arc-conf-deep-succ-untagged" className="text-[10px] text-neutral-400">
                {t('motif.arcConf.succUntagged', { defaultValue: 'Succession needs motif-tagging — run with a model.' })}
              </p>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
