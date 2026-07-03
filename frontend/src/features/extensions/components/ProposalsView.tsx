// View (MVC) — render-only proposals inbox. Logic lives in useProposals.
import { useProposals } from '../hooks/useExtensions';
import type { Proposal } from '../types';

export function ProposalsView() {
  const p = useProposals();
  return (
    <div className="space-y-3" data-testid="extensions-proposals-view">
      <div className="flex items-center gap-2">
        <select
          value={p.status}
          onChange={(e) => p.setStatus(e.target.value)}
          data-testid="proposals-status-filter"
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
        >
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="rejected">Rejected</option>
          <option value="expired">Expired</option>
          <option value="">All</option>
        </select>
        <span className="text-xs text-muted-foreground">{p.total} total</span>
      </div>

      {p.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{p.error}</div>}
      {!p.loading && p.proposals.length === 0 && !p.error && (
        <div className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground">
          No proposals. Skills the agent proposes appear here for your approval.
        </div>
      )}

      <ul className="space-y-2">
        {p.proposals.map((pr) => (
          <ProposalCard key={pr.proposal_id} proposal={pr} onApprove={() => void p.approve(pr)} onReject={() => void p.reject(pr)} />
        ))}
      </ul>
    </div>
  );
}

function ProposalCard({ proposal, onApprove, onReject }: { proposal: Proposal; onApprove: () => void; onReject: () => void }) {
  const pending = proposal.status === 'pending';
  return (
    <li className="rounded-md border p-3" data-testid="proposal-card">
      <div className="flex items-center gap-2">
        <span className="font-medium">{proposal.slug}</span>
        <span className="rounded border px-1.5 text-[10px] uppercase text-muted-foreground">{proposal.action}</span>
        {!pending && <span className="text-[11px] text-muted-foreground">{proposal.status}</span>}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{proposal.description}</div>
      {proposal.body_md && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-[11px] whitespace-pre-wrap">{proposal.body_md}</pre>
      )}
      {pending && (
        <div className="mt-2 flex gap-2">
          <button onClick={onApprove} data-testid="proposal-approve" className="rounded border border-green-400/60 px-3 py-1 text-xs text-green-400">Approve</button>
          <button onClick={onReject} data-testid="proposal-reject" className="rounded border border-red-400/60 px-3 py-1 text-xs text-red-400">Reject</button>
        </div>
      )}
      {proposal.reject_reason && <div className="mt-1 text-[11px] text-muted-foreground">Reason: {proposal.reject_reason}</div>}
    </li>
  );
}
