// D-REG-SKILLPROPOSAL-CARD (spec §12b) — renders a completed registry_propose_skill
// / registry_update_skill result as a human-approvable card. The agent PROPOSES
// (never writes); the human Approves (creates/updates the skill in their tier) or
// Rejects (result.error to the model). Also appears in the Proposals inbox — this
// is the in-chat surface. Never a silent no-op (Frontend-Tool-Contract rule).
import { useState } from 'react';
import { useAuth } from '@/auth';
import { extensionsApi } from '@/features/extensions/api';
import type { ToolCallRecord } from '../types';

export interface SkillProposal {
  proposalId: string;
  action: 'create' | 'update';
  slug: string;
  description: string;
  body: string;
}

/** Extract a skill proposal from a COMPLETED registry propose/update tool call. */
export function skillProposal(tc: ToolCallRecord): SkillProposal | null {
  if (tc.pending) return null;
  if (tc.tool !== 'registry_propose_skill' && tc.tool !== 'registry_update_skill') return null;
  // proposal_id comes from the result ({proposal_id} | {result:{proposal_id}} | JSON string).
  let res: unknown = tc.result;
  if (typeof res === 'string') {
    try { res = JSON.parse(res); } catch { res = null; }
  }
  const ro = (res && typeof res === 'object' ? res as Record<string, unknown> : null);
  const inner = ro && ro.result && typeof ro.result === 'object' ? ro.result as Record<string, unknown> : ro;
  const proposalId = inner && typeof inner.proposal_id === 'string' ? inner.proposal_id : '';
  if (!proposalId) return null;
  const args = (tc.args ?? {}) as Record<string, unknown>;
  return {
    proposalId,
    action: tc.tool === 'registry_update_skill' ? 'update' : 'create',
    slug: typeof args.slug === 'string' ? args.slug : '(skill)',
    description: typeof args.description === 'string' ? args.description : '',
    body: typeof args.body_md === 'string' ? args.body_md : '',
  };
}

export function SkillProposalCard({ proposal }: { proposal: SkillProposal }) {
  const { accessToken } = useAuth();
  const [state, setState] = useState<'pending' | 'approving' | 'approved' | 'rejected' | 'error'>('pending');
  const [msg, setMsg] = useState('');

  const approve = async () => {
    if (!accessToken) return;
    setState('approving');
    try {
      await extensionsApi.approveProposal(accessToken, proposal.proposalId);
      setState('approved');
    } catch (e) {
      setState('error');
      setMsg(e instanceof Error ? e.message : 'approve failed');
    }
  };
  const reject = async () => {
    if (!accessToken) return;
    try {
      await extensionsApi.rejectProposal(accessToken, proposal.proposalId);
      setState('rejected');
    } catch (e) {
      setState('error');
      setMsg(e instanceof Error ? e.message : 'reject failed');
    }
  };

  return (
    <div data-testid="skill-proposal-card" className="my-2 rounded-lg border border-indigo-400/60 bg-indigo-500/5 p-3">
      <div className="mb-1 text-[11px] font-bold uppercase tracking-wide text-indigo-400">
        {proposal.action === 'update' ? 'Skill update proposed' : 'Skill proposed'} — your approval needed
      </div>
      <div className="flex items-center gap-2">
        <span className="font-mono font-medium">{proposal.slug}</span>
      </div>
      {proposal.description && <div className="mt-0.5 text-xs text-muted-foreground">{proposal.description}</div>}
      {proposal.body && (
        <pre className="mt-2 max-h-48 overflow-auto whitespace-pre-wrap rounded bg-muted/40 p-2 text-[11px]">{proposal.body}</pre>
      )}
      {state === 'pending' || state === 'approving' ? (
        <div className="mt-2 flex items-center gap-2">
          <button
            onClick={() => void approve()}
            disabled={state === 'approving'}
            data-testid="skill-proposal-approve"
            className="rounded border border-green-400/60 px-3 py-1 text-xs text-green-400 disabled:opacity-50"
          >{state === 'approving' ? 'Saving…' : 'Approve — save skill'}</button>
          <button
            onClick={() => void reject()}
            data-testid="skill-proposal-reject"
            className="rounded border border-red-400/60 px-3 py-1 text-xs text-red-400"
          >Reject</button>
          <span className="text-[11px] text-muted-foreground">Nothing is saved until you approve · expires in 7 days</span>
        </div>
      ) : (
        <div className="mt-2 text-xs" data-testid="skill-proposal-outcome">
          {state === 'approved' && <span className="text-green-400">✓ Saved to your skills.</span>}
          {state === 'rejected' && <span className="text-muted-foreground">Rejected.</span>}
          {state === 'error' && <span className="text-red-400">{msg}</span>}
        </div>
      )}
    </div>
  );
}
