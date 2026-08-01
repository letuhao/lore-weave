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
  // Optional: a view-only surface (the standing CriticPanel) renders canon without
  // a generate control to revise into, so it omits the per-violation Revise button.
  onRevise?: (v: CanonViolation) => void;
};

function violationLabel(v: CanonViolation): string {
  return v.name || v.matched || v.entity_id;
}

export function CanonGatePanel({ canon, onRevise }: Props) {
  const { t } = useTranslation('composition');
  // S1 — prefer the DERIVED headline over the legacy scalar. `status` describes the gone-cast
  // check only while wearing the guard's name, so a run whose name-grounding degraded reported
  // 'checked' here and this panel drew a green all-clear over it. `guard_status` is the worst
  // status across every check the guard ran; `?? status` keeps pre-S1 rows readable.
  const checked = (canon.guard_status ?? canon.status) === 'checked';
  // Defensive: the backend excludes judge-cleared (confirmed===false), but never
  // trust the wire — only true=HARD, null/undefined=ADVISORY are shown.
  const hard = checked ? canon.violations.filter((v) => v.confirmed === true) : [];
  const advisory = checked ? canon.violations.filter((v) => v.confirmed !== true && v.confirmed !== false) : [];
  // Gate the green "clear" line on the AUTHORITATIVE verdict, not just an empty filtered
  // list — the whole canon arc is "no silent false-green". If the backend ever reports a
  // failed verdict without an individual hard row, we must NOT show green (the panel renders
  // empty rather than a false all-clear).
  //
  // `verdict` IS `resolved && something-was-checked`, computed server-side by
  // `loreweave_guard.GuardReport`. This line used to restate that conjunction by hand, which
  // put a rule with Python tests into TypeScript where none of them apply. `?? resolved` is
  // the pre-S1 fallback, and it is still ANDed with `checked` above.
  // `=== undefined`, NOT `??`. The two nullish values mean OPPOSITE things here: `undefined`
  // is a pre-S1 row that never carried the field (fall back), while `null` is the server
  // saying *nothing verified this* (must not fall back). `??` collapses them, and the first
  // version of this line did exactly that — a green all-clear on an unverified scene, which
  // is the bug the field was added to close, reintroduced by the operator that reads as safe.
  const verdict = canon.verdict === undefined ? canon.resolved : canon.verdict;
  const clear = checked && verdict === true && hard.length === 0 && advisory.length === 0;

  // WHY it is unchecked, derived from `guard_status` — the per-check headline — and not from
  // the legacy scalar. Two defects this replaces, both measured:
  //   · the chain keyed on `canon.status`, the SAME field `checked` was moved off, so every
  //     status added since (`no_rules`, `unverified_input`, `unparseable`, `no_subject`) fell
  //     through to the final branch;
  //   · that branch asserts "the canon service was unavailable" for ANYTHING unrecognised — a
  //     cause it cannot know. A truncated JUDGE is not an outage, and telling the author to go
  //     look at a healthy service is worse than saying nothing.
  // The fallback now NAMES the status instead of inventing a reason for it.
  const REASONS: Record<string, string> = {
    no_subject: t('canonUncheckedNoCast', { defaultValue: 'no tracked characters in this scene' }),
    no_position: t('canonUncheckedNoPosition', {
      defaultValue: 'this scene has no reading-order position yet',
    }),
    no_rules: t('canonUncheckedNoRules', {
      defaultValue: 'nothing is known yet about this scene’s characters to check against',
    }),
    unverified_input: t('canonUncheckedUnverifiedInput', {
      defaultValue: 'part of what this check needed could not be loaded, so it is incomplete',
    }),
    unparseable: t('canonUncheckedUnparseable', {
      defaultValue: 'the reviewing model did not return a usable answer',
    }),
    degraded: t('canonUncheckedDegraded', { defaultValue: 'the canon service was unavailable' }),
    failed: t('canonUncheckedFailed', { defaultValue: 'the check itself errored' }),
  };
  // Pre-S1 rows carry only the legacy scalar; map its two known values onto the same reasons.
  const LEGACY: Record<string, string> = {
    skipped_no_cast: 'no_subject',
    skipped_no_position: 'no_position',
    degraded: 'degraded',
  };
  const reasonKey = canon.guard_status ?? LEGACY[canon.status] ?? canon.status;
  // No raw enum in author-facing copy. The first version interpolated `reasonKey` into the
  // sentence, so a novelist read "this check did not run (unparseable)" — developer vocabulary
  // leaking into the product. The value still has to reach support, so it rides `title=`,
  // which is where an untranslated internal token belongs.
  const uncheckedReason =
    REASONS[reasonKey] ?? t('canonUncheckedOther', { defaultValue: 'this check could not run' });
  // Which half of the composite could not run. Named because "the guard is amber" without
  // WHICH check is the same shape as the scalar this arc replaced.
  const stalledChecks = Object.entries(canon.checks ?? {})
    .filter(([, v]) => v !== 'checked' && v !== 'not_applicable')
    .map(([k]) => k);

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
      {onRevise && (
        <button
          data-testid={`canon-revise-${kind}`}
          className="shrink-0 rounded border border-neutral-300/60 px-2 py-0.5 text-[11px] font-medium hover:opacity-80 dark:border-neutral-600"
          onClick={() => onRevise(v)}
        >
          {t('revise', { defaultValue: 'Revise' })}
        </button>
      )}
    </div>
  );

  return (
    <div data-testid="canon-gate-panel" data-status={canon.status}
      data-guard-status={canon.guard_status ?? canon.status} className="rounded border border-neutral-200 p-2 dark:border-neutral-700">
      {!checked && (
        <div data-testid="canon-unchecked" title={reasonKey}
          className="rounded bg-amber-50 p-1.5 text-xs text-amber-800 dark:bg-amber-950 dark:text-amber-300">
          <span className="font-medium">{t('canonUncheckedTitle', { defaultValue: 'Canon not verified' })}</span> — {uncheckedReason}
          {stalledChecks.length > 0 && (
            <span data-testid="canon-unchecked-which" className="opacity-80"
              title={stalledChecks.join(', ')}>
              {' '}
              {t('canonUncheckedWhich', {
                defaultValue: '{{count}} of its checks did not complete',
                count: stalledChecks.length,
              })}
            </span>
          )}
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
