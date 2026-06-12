import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';
import { useAuth } from '@/auth';
import { enrichmentApi } from '../api';
import type { Proposal } from '../types';

/** The proposal lifecycle actions (approve / reject / edit / promote / retract).
 *  Each acts on the proposal's OWN project_id; promote/retract also pass the book
 *  anchor. Promote is the ④ gate — it auto-walks proposed→approved first (the
 *  backend requires `approved` before canon). On success: invalidate the list +
 *  toast. No useEffect — these are explicit handlers (per the FE rules). */
export function useProposalActions(bookId: string) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();
  const { t } = useTranslation('enrichment');
  const [busy, setBusy] = useState(false);

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ['enrichment-proposals', bookId] });

  async function run<T>(fn: () => Promise<T>, successKey: string): Promise<T | null> {
    setBusy(true);
    try {
      const out = await fn();
      toast.success(t(successKey));
      invalidate();
      return out;
    } catch (e) {
      toast.error((e as Error).message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  return {
    busy,
    approve: (p: Proposal) =>
      run(() => enrichmentApi.approve(p.proposal_id, p.project_id, accessToken!), 'actions.approved'),
    reject: (p: Proposal, reason?: string) =>
      run(() => enrichmentApi.reject(p.proposal_id, p.project_id, reason, accessToken!), 'actions.rejected'),
    edit: (p: Proposal, content: string) =>
      run(() => enrichmentApi.edit(p.proposal_id, p.project_id, content, accessToken!), 'actions.edited'),
    /** The ④ promote — approve first if not yet approved, then promote to canon. */
    promote: (p: Proposal) =>
      run(async () => {
        if (p.review_status !== 'approved') {
          await enrichmentApi.approve(p.proposal_id, p.project_id, accessToken!);
        }
        return enrichmentApi.promote(p.proposal_id, p.project_id, bookId, accessToken!);
      }, 'actions.promoted'),
    retract: (p: Proposal) =>
      run(() => enrichmentApi.retract(p.proposal_id, p.project_id, bookId, accessToken!), 'actions.retracted'),
  };
}
