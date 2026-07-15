// M5 — the workflow rack. A "workflow" is a saved recipe the agent can run step-by-step
// (a rail): "set up my world", "check my story for contradictions", etc. The rack is where a
// user SEES which recipes exist and picks one — the FE consumer of the agent-registry
// `GET /v1/agent-registry/workflows` list (System + their own + granted-book tiers).

export type WorkflowTier = 'system' | 'user' | 'book';

export interface WorkflowMeta {
  slug: string;
  title: string;
  description: string;
  tier: WorkflowTier;
  status: string;
}

export interface WorkflowList {
  workflows: WorkflowMeta[];
}
