// M5 — the workflow rack. A "workflow" is a saved recipe the agent can run step-by-step
// (a rail): "set up my world", "check my story for contradictions", etc. The rack is where a
// user SEES which recipes exist and picks one — the FE consumer of the agent-registry
// `GET /v1/agent-registry/workflows` list (System + their own + granted-book tiers).

export type WorkflowTier = 'system' | 'user' | 'book';

export interface WorkflowMeta {
  // workflow_id + enabled are present on the REST list (S-12); the older rack ignores them.
  workflow_id?: string;
  slug: string;
  title: string;
  description: string;
  tier: WorkflowTier;
  status: string;
  enabled?: boolean;
}

export interface WorkflowList {
  workflows: WorkflowMeta[];
}

// S-12 — the full single-workflow shape (get-one).
export interface WorkflowStep {
  id: string;
  tool: string;
  gate?: string;
  when?: string;
}

export interface WorkflowFull {
  workflow_id: string;
  slug: string;
  title: string;
  description: string;
  tier: WorkflowTier;
  surfaces: string[];
  inputs: Record<string, string>;
  steps: WorkflowStep[];
  notes_md: string;
  status: string;
  enabled: boolean;
}

// S-12 — workflow proposals (the propose→approve HITL inbox; mirrors skill proposals).
export type WorkflowProposalStatus = 'pending' | 'approved' | 'rejected' | 'expired';

export interface WorkflowProposal {
  proposal_id: string;
  action: 'create' | 'update';
  slug: string;
  title: string;
  description: string;
  surfaces: string[];
  inputs: Record<string, string>;
  steps: WorkflowStep[];
  notes_md: string;
  status: WorkflowProposalStatus;
  reject_reason: string;
  from_session_id: string;
  from_session_label: string;
  created_at: string;
  expires_at: string;
}

export interface WorkflowProposalList {
  items: WorkflowProposal[];
  total: number;
  limit: number;
  offset: number;
}
