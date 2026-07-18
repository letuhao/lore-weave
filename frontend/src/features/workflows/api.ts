// API layer for the workflow rack (M5) + the S-12 management/proposals surface.
// Same gateway path the extensions feature uses.
import { apiJson } from '@/api';
import type { WorkflowList, WorkflowFull, WorkflowProposalList } from './types';

const BASE = '/v1/agent-registry';

export const workflowsApi = {
  /** The workflows this user can see: System + their own + (if book_id given & granted) that book's. */
  list(token: string, params: { book_id?: string; surface?: string } = {}): Promise<WorkflowList> {
    const qs = new URLSearchParams();
    if (params.book_id) qs.set('book_id', params.book_id);
    if (params.surface) qs.set('surface', params.surface);
    const q = qs.toString();
    return apiJson<WorkflowList>(`${BASE}/workflows${q ? `?${q}` : ''}`, { token });
  },

  // ── S-12: single-workflow read + enable/disable + delete (mirror the skills surface) ──
  get(token: string, id: string): Promise<WorkflowFull> {
    return apiJson<WorkflowFull>(`${BASE}/workflows/${id}`, { token });
  },

  setEnabled(token: string, id: string, enabled: boolean): Promise<void> {
    return apiJson<void>(`${BASE}/workflows/${id}/enablement`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ enabled }),
    });
  },

  remove(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/workflows/${id}`, { method: 'DELETE', token });
  },

  // ── S-12: workflow proposals inbox (the propose→approve HITL loop) ──
  listProposals(
    token: string,
    params: { status?: string; limit?: number; offset?: number } = {},
  ): Promise<WorkflowProposalList> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    qs.set('limit', String(params.limit ?? 50));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<WorkflowProposalList>(`${BASE}/workflow-proposals?${qs.toString()}`, { token });
  },

  approveProposal(token: string, id: string): Promise<{ proposal_id: string; status: string; slug: string }> {
    return apiJson(`${BASE}/workflow-proposals/${id}/approve`, { method: 'PUT', token });
  },

  rejectProposal(token: string, id: string, reason = ''): Promise<{ proposal_id: string; status: string }> {
    return apiJson(`${BASE}/workflow-proposals/${id}/reject`, {
      method: 'POST',
      token,
      body: JSON.stringify({ reason }),
    });
  },
};
