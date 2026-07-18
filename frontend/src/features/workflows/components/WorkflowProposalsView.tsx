// View (MVC) — render-only workflow-proposals inbox. Logic in useWorkflowProposals.
// Near-clone of extensions/ProposalsView; approving a pending proposal mints the workflow
// (the loop the agent's registry_propose_workflow description promised but had no UI for).
import { useTranslation } from 'react-i18next';
import { useWorkflowProposals } from '../hooks/useWorkflowProposals';
import type { WorkflowProposal } from '../types';

export function WorkflowProposalsView() {
  const { t } = useTranslation('extensions');
  const p = useWorkflowProposals();
  return (
    <div className="space-y-3" data-testid="workflow-proposals-view">
      <div className="flex items-center gap-2">
        <select
          value={p.status}
          onChange={(e) => p.setStatus(e.target.value)}
          data-testid="workflow-proposals-status-filter"
          className="rounded-md border bg-background px-2 py-1.5 text-xs"
        >
          <option value="pending">{t('proposals.status.pending')}</option>
          <option value="approved">{t('proposals.status.approved')}</option>
          <option value="rejected">{t('proposals.status.rejected')}</option>
          <option value="expired">{t('proposals.status.expired')}</option>
          <option value="">{t('proposals.status.all')}</option>
        </select>
        <span className="text-xs text-muted-foreground">{t('proposals.total', { count: p.total })}</span>
      </div>

      {p.error && <div className="rounded-md border border-red-400 bg-red-500/10 px-3 py-2 text-xs text-red-400">{p.error}</div>}
      {!p.loading && p.proposals.length === 0 && !p.error && (
        <div className="rounded-md border border-dashed px-6 py-8 text-center text-xs text-muted-foreground" data-testid="workflow-proposals-empty">
          {t('workflows.proposalsEmpty')}
        </div>
      )}

      <ul className="space-y-2">
        {p.proposals.map((pr) => (
          <WorkflowProposalCard key={pr.proposal_id} proposal={pr} onApprove={() => void p.approve(pr)} onReject={() => void p.reject(pr)} />
        ))}
      </ul>
    </div>
  );
}

function WorkflowProposalCard({ proposal, onApprove, onReject }: { proposal: WorkflowProposal; onApprove: () => void; onReject: () => void }) {
  const { t } = useTranslation('extensions');
  const pending = proposal.status === 'pending';
  return (
    <li className="rounded-md border p-3" data-testid="workflow-proposal-card">
      <div className="flex items-center gap-2">
        <span className="font-medium">{proposal.title || proposal.slug}</span>
        <span className="rounded border px-1.5 text-[10px] uppercase text-muted-foreground">{proposal.action}</span>
        {!pending && <span className="text-[11px] text-muted-foreground">{proposal.status}</span>}
      </div>
      <div className="mt-1 text-xs text-muted-foreground">{proposal.description}</div>
      {/* Show the STEPS being approved — a human approves the tool sequence, not blind
          (informed-consent: the review card must show what the workflow will do). */}
      {proposal.steps && proposal.steps.length > 0 && (
        <ol className="mt-2 space-y-0.5 rounded bg-muted/40 p-2 text-[11px]" data-testid="workflow-proposal-steps">
          {proposal.steps.map((s, i) => (
            <li key={s.id || i} className="flex gap-2">
              <span className="text-muted-foreground">{i + 1}.</span>
              <span className="font-mono">{s.tool}</span>
              {s.gate && s.gate !== 'auto' && <span className="rounded border px-1 text-[10px] text-amber-500">{s.gate}</span>}
            </li>
          ))}
        </ol>
      )}
      {proposal.notes_md && (
        <pre className="mt-2 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-[11px] whitespace-pre-wrap">{proposal.notes_md}</pre>
      )}
      {pending && (
        <div className="mt-2 flex gap-2">
          <button onClick={onApprove} data-testid="workflow-proposal-approve" className="rounded border border-green-400/60 px-3 py-1 text-xs text-green-400">{t('proposals.approve')}</button>
          <button onClick={onReject} data-testid="workflow-proposal-reject" className="rounded border border-red-400/60 px-3 py-1 text-xs text-red-400">{t('proposals.reject')}</button>
        </div>
      )}
      {proposal.reject_reason && <div className="mt-1 text-[11px] text-muted-foreground">{t('proposals.reason', { reason: proposal.reject_reason })}</div>}
    </li>
  );
}
