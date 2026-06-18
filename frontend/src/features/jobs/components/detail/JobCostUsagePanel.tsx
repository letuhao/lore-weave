import { useTranslation } from 'react-i18next';

import type { Job } from '../../types';
import { formatCost } from '../../lib';

/** Cost & Usage panel: cost prominent (reliable), tokens best-effort, model(s).
 *  Renders nothing when the job carries no usage at all (e.g. a brand-new pending
 *  job) so the detail page isn't cluttered with empty cells. */
export function JobCostUsagePanel({ job }: { job: Job }) {
  const { t } = useTranslation('jobs');
  const cost = formatCost(job.cost_usd);
  const hasUsage =
    job.cost_usd != null || job.tokens_in != null || job.tokens_out != null || job.model != null;
  if (!hasUsage) return null;

  const embedding = typeof job.params?.embedding_model === 'string' ? job.params.embedding_model : null;
  const num = (n: number | null) => (n != null ? n.toLocaleString() : '—');

  return (
    <div className="grid grid-cols-3 gap-4 rounded-xl border border-primary/35 bg-card p-4">
      <div>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t('detail.costSoFar', { defaultValue: 'Cost so far' })}
        </div>
        <div className="mt-0.5 text-xl font-semibold tabular-nums text-primary">{cost ?? '—'}</div>
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t('detail.tokensIn', { defaultValue: 'Tokens in' })}{' '}
          <span className="normal-case">· {t('detail.bestEffort', { defaultValue: 'best-effort' })}</span>
        </div>
        <div className="mt-0.5 text-lg tabular-nums">{num(job.tokens_in)}</div>
      </div>
      <div>
        <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
          {t('detail.tokensOut', { defaultValue: 'Tokens out' })}{' '}
          <span className="normal-case">· {t('detail.bestEffort', { defaultValue: 'best-effort' })}</span>
        </div>
        <div className="mt-0.5 text-lg tabular-nums">{num(job.tokens_out)}</div>
      </div>
      {(job.model || embedding) && (
        <div className="col-span-3">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">
            {t('detail.models', { defaultValue: 'Models' })}
          </div>
          <div className="mt-0.5 font-mono text-xs">
            {[job.model, embedding].filter(Boolean).join(' · ')}
          </div>
        </div>
      )}
    </div>
  );
}
