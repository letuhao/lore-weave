// Agent Extensibility Registry — FE API layer (P1 slice).
import { apiJson } from '@/api';
import type {
  Skill,
  SkillList,
  ProposalList,
  UsageCounters,
} from './types';

const BASE = '/v1/agent-registry';

export const extensionsApi = {
  listSkills(
    token: string,
    params: { q?: string; tier?: string; sort?: string; limit?: number; offset?: number } = {},
  ): Promise<SkillList> {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.tier) qs.set('tier', params.tier);
    if (params.sort) qs.set('sort', params.sort);
    qs.set('limit', String(params.limit ?? 20));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<SkillList>(`${BASE}/skills?${qs.toString()}`, { token });
  },

  createSkill(
    token: string,
    body: { slug: string; description: string; body_md: string; surfaces?: string[]; status?: string },
  ): Promise<Skill> {
    return apiJson<Skill>(`${BASE}/skills`, { method: 'POST', token, body: JSON.stringify(body) });
  },

  patchSkill(token: string, id: string, patch: Partial<Pick<Skill, 'description' | 'body_md' | 'surfaces' | 'status'>>): Promise<Skill> {
    return apiJson<Skill>(`${BASE}/skills/${id}`, { method: 'PATCH', token, body: JSON.stringify(patch) });
  },

  deleteSkill(token: string, id: string): Promise<void> {
    return apiJson<void>(`${BASE}/skills/${id}`, { method: 'DELETE', token });
  },

  setSkillEnabled(token: string, id: string, enabled: boolean): Promise<void> {
    return apiJson<void>(`${BASE}/skills/${id}/enablement`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ enabled }),
    });
  },

  shadowCheck(token: string, slug: string): Promise<{ slug: string; shadows_system: boolean }> {
    return apiJson(`${BASE}/skills/shadow-check?slug=${encodeURIComponent(slug)}`, { token });
  },

  listProposals(
    token: string,
    params: { status?: string; sort?: string; limit?: number; offset?: number } = {},
  ): Promise<ProposalList> {
    const qs = new URLSearchParams();
    if (params.status) qs.set('status', params.status);
    if (params.sort) qs.set('sort', params.sort);
    qs.set('limit', String(params.limit ?? 20));
    qs.set('offset', String(params.offset ?? 0));
    return apiJson<ProposalList>(`${BASE}/proposals?${qs.toString()}`, { token });
  },

  approveProposal(token: string, id: string): Promise<{ proposal_id: string; status: string; slug: string }> {
    return apiJson(`${BASE}/proposals/${id}/approve`, { method: 'PUT', token });
  },

  rejectProposal(token: string, id: string, reason = ''): Promise<{ proposal_id: string; status: string }> {
    return apiJson(`${BASE}/proposals/${id}/reject`, {
      method: 'POST',
      token,
      body: JSON.stringify({ reason }),
    });
  },

  usage(token: string): Promise<UsageCounters> {
    return apiJson<UsageCounters>(`${BASE}/usage`, { token });
  },
};
