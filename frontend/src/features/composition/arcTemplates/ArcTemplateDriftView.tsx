// Wave-4 (D-ARC-TEMPLATE-DRIFT-VIEW) — the structured render of a template-drift report,
// replacing the raw <pre> JSON dump in ArcTemplatesPanel.DriftSection. The report is an
// `ArcConformance` (coarse: spec-node vs its arc_template). There is NO status enum — drift is
// the SUM of signals (coverage gaps, pacing drift, succession violations, folded placements),
// so the header derives its own one-line verdict + each section renders an honest empty.
import type { TFunction } from 'i18next';
import type { ArcConformance } from '../motif/types';

function driftCounts(r: ArcConformance) {
  const gaps = r.thread_progress.reduce((n, tp) => n + tp.missing.length, 0);
  const violations = r.succession.threads.reduce((n, s) => n + s.violations.length, 0);
  const folded = r.unmaterialized.length;
  const pacing = r.pacing.comparable ? r.pacing.max_drift : null;
  const clean = gaps === 0 && violations === 0 && folded === 0 && (pacing == null || pacing === 0);
  return { gaps, violations, folded, pacing, clean };
}

export function ArcTemplateDriftView({ report: r, t }: { report: ArcConformance; t: TFunction }) {
  const c = driftCounts(r);
  const structural = c.gaps + c.violations + c.folded;
  return (
    <div data-testid="arc-drift-view" className="mt-1 flex flex-col gap-2 text-[11px]">
      {/* Derived one-line verdict — honest "no drift" when every signal is clean. A pacing-ONLY
          drift (no structural gaps but the tension curve moved) gets its own line so the summary
          never reads "0 · 0 · 0" while the arc is not clean (the pacing section shows the number). */}
      {c.clean ? (
        <p data-testid="arc-drift-clean" className="rounded bg-emerald-50 px-2 py-0.5 text-emerald-700 dark:bg-emerald-950/30 dark:text-emerald-300">
          {t('motif.arc.templates.driftClean', { defaultValue: 'No drift — the realized arc matches its template.' })}
        </p>
      ) : structural === 0 && c.pacing ? (
        <p data-testid="arc-drift-summary" className="rounded bg-amber-50 px-2 py-0.5 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          {t('motif.arc.templates.driftPacingOnly', { drift: c.pacing, defaultValue: 'Structure matches, but the pacing drifted (max {{drift}}).' })}
        </p>
      ) : (
        <p data-testid="arc-drift-summary" className="rounded bg-amber-50 px-2 py-0.5 text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
          {t('motif.arc.templates.driftSummary', {
            gaps: c.gaps, violations: c.violations, folded: c.folded,
            defaultValue: '{{gaps}} coverage gap(s) · {{violations}} ordering issue(s) · {{folded}} folded placement(s)',
          })}
        </p>
      )}

      {/* Coverage — planned template placements vs those the realized arc actually bound. */}
      <section>
        <h5 className="mb-0.5 font-medium text-foreground/70">{t('motif.arc.templates.driftThreads', { defaultValue: 'Thread coverage' })}</h5>
        {r.thread_progress.length === 0 ? (
          <p className="text-muted-foreground">{t('motif.arc.templates.driftNoThreads', { defaultValue: 'The template has no threads to compare.' })}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {r.thread_progress.map((tp) => (
              <li key={tp.thread} data-testid={`arc-drift-thread-${tp.thread}`} className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate">{tp.label}</span>
                <span className={tp.covered < tp.planned ? 'text-amber-700 dark:text-amber-300' : 'text-emerald-700 dark:text-emerald-400'}>
                  {tp.covered}/{tp.planned}
                  {tp.missing.length > 0 && (
                    <span data-testid={`arc-drift-missing-${tp.thread}`} className="ml-1 text-muted-foreground">
                      ({tp.missing.map((m) => m.motif_code ?? `#${m.ord}`).join(', ')})
                    </span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Pacing — planned-vs-realized tension. Only meaningful when the template had a curve. */}
      <section data-testid="arc-drift-pacing">
        <h5 className="mb-0.5 font-medium text-foreground/70">
          {t('motif.arc.templates.driftPacing', { defaultValue: 'Pacing' })}
          {r.pacing.comparable && r.pacing.max_drift != null && (
            <span data-testid="arc-drift-max" className="ml-1 text-muted-foreground">
              {t('motif.arc.templates.driftMax', { drift: r.pacing.max_drift, defaultValue: 'max drift {{drift}}' })}
            </span>
          )}
        </h5>
        {r.pacing.comparable ? (
          <div className="flex flex-wrap gap-1">
            {r.pacing.realized.map((p) => (
              <span key={p.chapter_index} className="rounded bg-muted px-1 tabular-nums text-muted-foreground" title={`ch ${p.chapter_index}`}>
                {Math.round(p.avg_tension)}
              </span>
            ))}
          </div>
        ) : (
          <p className="text-muted-foreground">{t('motif.arc.templates.driftPacingNC', { defaultValue: 'Not comparable yet — the template has no tension curve.' })}</p>
        )}
      </section>

      {/* Succession — reversed/illegal motif ordering vs the template's precedes graph. */}
      <section>
        <h5 className="mb-0.5 font-medium text-foreground/70">{t('motif.arc.templates.driftSuccession', { defaultValue: 'Ordering' })}</h5>
        {r.succession.threads.every((s) => s.violations.length === 0) ? (
          <p data-testid="arc-drift-succession-ok" className="text-muted-foreground">{t('motif.arc.templates.driftSuccessionOk', { defaultValue: 'No ordering violations.' })}</p>
        ) : (
          <ul className="flex flex-col gap-0.5">
            {r.succession.threads.filter((s) => s.violations.length > 0).map((s) => (
              <li key={s.thread} data-testid={`arc-drift-violation-${s.thread}`} className="text-amber-700 dark:text-amber-300">
                {t('motif.arc.templates.driftViolation', { label: s.label, n: s.violations.length, defaultValue: '{{label}}: {{n}} out-of-order' })}
              </li>
            ))}
          </ul>
        )}
      </section>

      {/* Folded — template placements that produced no binding (the closest thing to "removed"). */}
      {r.unmaterialized.length > 0 && (
        <section data-testid="arc-drift-folded">
          <h5 className="mb-0.5 font-medium text-foreground/70">{t('motif.arc.templates.driftFolded', { defaultValue: 'Folded (never bound)' })}</h5>
          <p className="text-muted-foreground">{r.unmaterialized.map((u) => u.motif_code ?? `#${u.ord}`).join(', ')}</p>
        </section>
      )}
    </div>
  );
}
