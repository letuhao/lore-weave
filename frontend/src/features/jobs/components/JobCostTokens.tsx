import type { Job } from '../types';
import { formatCost, formatTokenPair } from '../lib';
import { estimateTotalJobCost, estimateTokenCost, type TokenModelPricing } from '../modelPricing';

/** The "Cost · tokens" cell: cost_usd on top (reliable), the token pair below
 *  (best-effort). The optional "~$…" suffix is a display-only estimate using
 *  the model's current configured token prices. Renders an em-dash when cost is
 *  absent — never a misleading $0. */
export function JobCostTokens({ job, pricing }: { job: Pick<Job, 'cost_usd' | 'tokens_in' | 'tokens_out' | 'progress'>; pricing?: TokenModelPricing | null }) {
  const cost = formatCost(job.cost_usd);
  const tokens = formatTokenPair(job.tokens_in, job.tokens_out);
  const estimated = formatCost(
    estimateTotalJobCost(job.cost_usd, job.progress) ??
      estimateTokenCost(job.tokens_in, job.tokens_out, pricing),
  );
  if (cost == null && tokens == null) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <div className="tabular-nums">
      {cost != null ? <div className="text-sm">{cost}</div> : null}
      {tokens != null ? (
        <div className="text-[11px] text-muted-foreground">
          {tokens}
          {estimated != null ? (
            <span className="ml-1" title="Approximate total cost based on current spend and progress">
              · ~{estimated}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
