// C24 (dị bản) — persistent derivative-context banner (view). Shows at the top of
// the studio when the open Work is a DERIVATIVE: the branch_point (G3), a reminder
// that canon below the branch is a READ-ONLY reference, plus WS-B2 chips
// (taxonomy · POV · override count) and a "⚙ Divergence spec" popover that lists
// the full durable spec (branch, taxonomy, POV, overrides, canon rules). All
// fields come from useDerivativeContext's durable read-back; render-only.
import { useTranslation } from 'react-i18next';
import type { DerivativeContext } from '../hooks/useDerivativeContext';

const TAXONOMY_LABEL: Record<string, string> = {
  pov_shift: 'POV shift',
  character_transform: 'Character transform',
  au: 'Alternate universe',
};

function shortId(id: string | null): string {
  return id ? id.slice(0, 8) : '';
}

export function DerivativeBanner({ ctx }: { ctx: DerivativeContext }) {
  const { t } = useTranslation('composition');
  if (!ctx.isDerivative) return null;
  const overrideCount = ctx.overrideIds.size;
  const taxonomyLabel = ctx.taxonomy
    ? t(`derive.taxonomy.${ctx.taxonomy}`, { defaultValue: TAXONOMY_LABEL[ctx.taxonomy] ?? ctx.taxonomy })
    : null;
  return (
    <div
      data-testid="derivative-banner"
      className="flex flex-wrap items-center gap-2 border-b border-purple-200 bg-purple-50/70 px-2 py-1.5 text-xs text-purple-900 dark:border-purple-800 dark:bg-purple-950/40 dark:text-purple-200"
    >
      <span aria-hidden>⑂</span>
      <span className="font-medium">{t('derive.bannerTitle', { defaultValue: 'You are writing a what-if (derivative)' })}</span>
      <span data-testid="derivative-banner-source" className="text-purple-800/80 dark:text-purple-300/80">
        {t('derive.bannerSource', { defaultValue: 'Adapting from canon' })}
        {' · '}
        {ctx.branchPoint != null
          ? t('derive.bannerBranch', { defaultValue: 'branches at chapter {{n}}', n: ctx.branchPoint + 1 })
          : t('derive.bannerBranchStart', { defaultValue: 'branches from the start' })}
      </span>

      {/* WS-B2 chips — the divergence spec at a glance. */}
      {taxonomyLabel && (
        <span data-testid="derivative-chip-taxonomy" className="rounded-full bg-purple-200/70 px-2 py-0.5 font-medium dark:bg-purple-800/50">
          {taxonomyLabel}
        </span>
      )}
      {ctx.povAnchor && (
        <span data-testid="derivative-chip-pov" className="rounded-full bg-purple-200/70 px-2 py-0.5 dark:bg-purple-800/50" title={ctx.povAnchor}>
          {t('derive.chipPov', { defaultValue: 'POV · {{id}}', id: shortId(ctx.povAnchor) })}
        </span>
      )}
      {overrideCount > 0 && (
        <span data-testid="derivative-chip-overrides" className="rounded-full bg-amber-200/70 px-2 py-0.5 text-amber-900 dark:bg-amber-800/50 dark:text-amber-200">
          {t('derive.chipOverrides', { defaultValue: '{{n}} override(s)', n: overrideCount })}
        </span>
      )}

      {/* "⚙ Divergence spec" popover — native <details> (no extra dep, focusable). */}
      <details data-testid="derivative-spec-popover" className="relative ml-auto">
        <summary className="cursor-pointer select-none rounded px-1.5 py-0.5 hover:bg-purple-200/50 dark:hover:bg-purple-800/40">
          ⚙ {t('derive.specPopover', { defaultValue: 'Divergence spec' })}
        </summary>
        <div className="absolute right-0 z-20 mt-1 w-64 rounded border border-purple-200 bg-white p-2 text-left shadow-lg dark:border-purple-800 dark:bg-neutral-900">
          <dl className="flex flex-col gap-1">
            <div className="flex justify-between gap-2">
              <dt className="text-neutral-500">{t('derive.specBranch', { defaultValue: 'Branch' })}</dt>
              <dd>{ctx.branchPoint != null ? `ch. ${ctx.branchPoint + 1}` : t('derive.specBranchStart', { defaultValue: 'from start' })}</dd>
            </div>
            {taxonomyLabel && (
              <div className="flex justify-between gap-2">
                <dt className="text-neutral-500">{t('derive.specTaxonomy', { defaultValue: 'Taxonomy' })}</dt>
                <dd>{taxonomyLabel}</dd>
              </div>
            )}
            {ctx.povAnchor && (
              <div className="flex justify-between gap-2">
                <dt className="text-neutral-500">{t('derive.specPov', { defaultValue: 'POV anchor' })}</dt>
                <dd className="font-mono" title={ctx.povAnchor}>{shortId(ctx.povAnchor)}</dd>
              </div>
            )}
            <div className="flex justify-between gap-2">
              <dt className="text-neutral-500">{t('derive.specOverrides', { defaultValue: 'Overrides' })}</dt>
              <dd>{overrideCount}</dd>
            </div>
            {ctx.canonRules.length > 0 && (
              <div className="flex flex-col gap-0.5">
                <dt className="text-neutral-500">{t('derive.specCanonRules', { defaultValue: 'Canon rules' })}</dt>
                <dd>
                  <ul className="list-disc pl-4">
                    {ctx.canonRules.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                </dd>
              </div>
            )}
          </dl>
        </div>
      </details>

      <span className="basis-full text-purple-700/70 dark:text-purple-400/70">
        {t('derive.bannerReadonly', { defaultValue: 'Original chapters are a read-only reference — adapt them manually.' })}
      </span>
    </div>
  );
}
