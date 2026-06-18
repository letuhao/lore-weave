import type { Job } from '../types';
import { formatCost, formatTokenPair } from '../lib';

/** The "Cost · tokens" cell: cost_usd on top (reliable), the token pair below
 *  (best-effort). Renders an em-dash when cost is absent — never a misleading $0. */
export function JobCostTokens({ job }: { job: Pick<Job, 'cost_usd' | 'tokens_in' | 'tokens_out'> }) {
  const cost = formatCost(job.cost_usd);
  const tokens = formatTokenPair(job.tokens_in, job.tokens_out);
  if (cost == null && tokens == null) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <div className="tabular-nums">
      {cost != null ? <div className="text-sm">{cost}</div> : null}
      {tokens != null ? <div className="text-[11px] text-muted-foreground">{tokens}</div> : null}
    </div>
  );
}
