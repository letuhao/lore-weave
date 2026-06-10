// LOOM Composition (A2-S4a) — the canon gate verdict on the converged auto
// winner (view only). Distinguishes three states the author must tell apart:
//   • HARD     — a CONFIRMED contradiction survived auto-revision (resolved=false).
//                A `gone` cast member is portrayed present/acting. Blocks at publish.
//   • ADVISORY — symbolic-only (the judge was down / not distinct): flag + override.
//   • UNCHECKED— canon protection did NOT apply (no cast / no reading position /
//                knowledge outage). Dirty data is normal; warn, don't false-block.
// Each violation row carries a Revise affordance — the parent pre-fills the guide
// textarea with the violation context so the author can steer a re-generate.
import { useTranslation } from 'react-i18next';
import type { CanonResult, CanonViolation } from '../types';

type Props = {
  canon: CanonResult;
  onRevise: (v: CanonViolation) => void;
};

function violationLabel(v: CanonViolation): string {
  return v.name || v.matched || v.entity_id;
}

export function CanonGatePanel({ canon, onRevise }: Props) {
  const { t } = useTranslation('composition');
  const checked = canon.status === 'checked';
  // Defensive: the backend excludes judge-cleared (confirmed===false), but never
  // trust the wire — only true=HARD, null/undefined=ADVISORY are shown.
  const hard = checked ? canon.violations.filter((v) => v.confirmed === true) : [];
  const advisory = checked ? canon.violations.filter((v) => v.confirmed !== true && v.confirmed !== false) : [];
  // Gate the green "clear" line on the AUTHORITATIVE `resolved` field, not just an
  // empty filtered list — the whole canon arc is "no silent false-green". If the
  // backend ever reports resolved=false without an individual hard row, we must
  // NOT show green (the panel renders empty rather than a false all-clear).
  const clear = checked && canon.resolved && hard.length === 0 && advisory.length === 0;

  const uncheckedReason =
    canon.status === 'skipped_no_cast'
      ? t('canonUncheckedNoCast', { defaultValue: 'no tracked characters in this scene' })
      : canon.status === 'skipped_no_position'
        ? t('canonUncheckedNoPosition', { defaultValue: 'this scene has no reading-order position yet' })
        : t('canonUncheckedDegraded', { defaultValue: 'the canon service was unavailable' });

  const row = (v: CanonViolation, kind: 'hard' | 'advisory', i: number) => (
    <div
      key={`${kind}-${i}`}
      data-testid={`canon-${kind}-row`}
      className="mt-1 flex items-start justify-between gap-2 rounded p-1.5 text-xs"
    >
      <span>
        <span className="font-medium">{violationLabel(v)}</span>
        {v.why ? <span className="opacity-80"> — {v.why}</span> : v.span ? <span className="opacity-60"> — “{v.span}”</span> : null}
      </span>
      <button
        data-testid={`canon-revise-${kind}`}
        className="shrink-0 rounded border border-neutral-300/60 px-2 py-0.5 text-[11px] font-medium hover:opacity-80 dark:border-neutral-600"
        onClick={() => onRevise(v)}
      >
        {t('revise', { defaultValue: 'Revise' })}
      </button>
    </div>
  );

  return (
    <div data-testid="canon-gate-panel" data-status={canon.status} className="rounded border border-neutral-200 p-2 dark:border-neutral-700">
      {!checked && (
        <div data-testid="canon-unchecked" className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <span className="font-medium">{t('canonUncheckedTitle', { defaultValue: 'Canon not verified' })}</span> — {uncheckedReason}
        </div>
      )}

      {hard.length > 0 && (
        <div data-testid="canon-hard" className="rounded bg-red-50 p-1.5 text-red-800 dark:bg-red-950 dark:text-red-300">
          <div className="text-xs font-semibold uppercase tracking-wide">
            {t('canonHardTitle', { defaultValue: 'Canon contradiction' })}
          </div>
          {hard.map((v, i) => row(v, 'hard', i))}
        </div>
      )}

      {advisory.length > 0 && (
        <div data-testid="canon-advisory" className="mt-1 rounded bg-amber-50 p-1.5 text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <div className="text-xs font-semibold uppercase tracking-wide">
            {t('canonAdvisoryTitle', { defaultValue: 'Possible canon issue (unverified)' })}
          </div>
          {advisory.map((v, i) => row(v, 'advisory', i))}
        </div>
      )}

      {clear && (
        <div data-testid="canon-clear" className="text-xs text-emerald-700 dark:text-emerald-400">
          {t('canonClear', { defaultValue: 'Canon: clear' })}
          {canon.iterations > 0 && (
            <span className="ml-1 opacity-70">{t('canonAutoRevised', { defaultValue: 'auto-revised ×{{n}}', n: canon.iterations })}</span>
          )}
        </div>
      )}
    </div>
  );
}
