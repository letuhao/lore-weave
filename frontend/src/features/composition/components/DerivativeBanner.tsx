// C24 (dị bản M0) — persistent derivative-context banner (view). Shows at the top
// of the studio when the open Work is a DERIVATIVE: the source it adapts from, the
// chapter-level branch_point (G3), and a reminder that canon below the branch is a
// READ-ONLY reference (the writer adapts manually — reference spine is NOT
// auto-inserted, LOCKED). Render-only; logic in useDerivativeContext.
import { useTranslation } from 'react-i18next';
import type { DerivativeContext } from '../hooks/useDerivativeContext';

export function DerivativeBanner({ ctx }: { ctx: DerivativeContext }) {
  const { t } = useTranslation('composition');
  if (!ctx.isDerivative) return null;
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
      <span className="text-purple-700/70 dark:text-purple-400/70">
        {t('derive.bannerReadonly', { defaultValue: 'Original chapters are a read-only reference — adapt them manually.' })}
      </span>
    </div>
  );
}
