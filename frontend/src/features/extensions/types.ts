// Agent Extensibility Registry — FE types (P1 slice: skills + proposals).
// Mirrors services/agent-registry-service response shapes.

export type SkillTier = 'system' | 'user' | 'book';
export type SkillStatus = 'draft' | 'published' | 'archived';

export interface Skill {
  skill_id: string;
  tier: SkillTier;
  slug: string;
  description: string;
  body_md: string;
  surfaces: string[];
  status: SkillStatus;
  source: string;
  used_count: number;
  created_at: string;
  updated_at: string;
}

export interface SkillList {
  items: Skill[];
  total: number;
  limit: number;
  offset: number;
}

export type ProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface Proposal {
  proposal_id: string;
  action: 'create' | 'update';
  slug: string;
  description: string;
  body_md: string;
  status: ProposalStatus;
  reject_reason: string;
  from_session_id: string;
  from_session_label: string;
  created_at: string;
  expires_at: string;
}

export interface ProposalList {
  items: Proposal[];
  total: number;
  limit: number;
  offset: number;
}

export interface UsageCounters {
  plugins: number;
  skills: { used: number; limit: number };
  mcp_servers: { used: number; limit: number };
  commands: { used: number; limit: number };
  proposals_pending: number;
}
