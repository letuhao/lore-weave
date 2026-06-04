// LOOM Composition (M8) — FE types mirroring the composition-service contract.

export type Work = {
  project_id: string;
  user_id: string;
  book_id: string;
  active_template_id: string | null;
  status: 'active' | 'archived';
  settings: Record<string, unknown>;
  version: number;
};

export type WorkResolution = {
  status: 'found' | 'candidates' | 'unmarked_single' | 'unmarked_candidates' | 'none' | 'unavailable';
  work: Work | null;
  candidates: Work[];
  book_project_id: string | null;
  book_project_ids: string[];
};

export type OutlineNode = {
  id: string;
  project_id: string;
  parent_id: string | null;
  kind: 'arc' | 'chapter' | 'scene' | 'beat';
  title: string;
  chapter_id: string | null;
  story_order: number | null;
  status: 'empty' | 'outline' | 'drafting' | 'done';
  synopsis: string;
  version: number;
};

export type Grounding = {
  blocks: Record<string, string>;
  prompt: string;
  profile: { source_language: string; voice: string; structure_pref: string };
  token_count: number;
  grounding_available: boolean;
  l4_dropped_no_position: number;
  warnings: string[];
};

export type CanonRule = {
  id: string;
  text: string;
  scope: 'world' | 'entity' | 'reveal_gate';
  entity_id: string | null;
  from_order: number | null;
  until_order: number | null;
  active: boolean;
  version: number;
};

export type Violation = {
  rule_id: string;
  violated: boolean;
  span: string;
  why: string;
  dismissed?: boolean;
};

export type Critic = {
  coherence: number | null;
  voice_match: number | null;
  pacing: number | null;
  canon_consistency: number | null;
  violations: Violation[];
  error?: string;
} | null;

export type GenerationJob = {
  id: string;
  project_id: string;
  outline_node_id: string | null;
  operation: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'cancelled';
  result: { text?: string; measured?: boolean; output_tokens?: number } | null;
  critic: Critic;
};

// One decoded SSE frame from POST /generate.
export type StreamEvent =
  | { type: 'job'; job_id: string; created: boolean; grounding_available: boolean }
  | { type: 'token'; delta: string }
  | { type: 'reasoning'; delta: string }
  | { type: 'capped' }
  | { type: 'error'; error: string }
  | { type: 'done'; job_id: string; status: string; output_tokens?: number; measured?: boolean; capped?: boolean; replay?: boolean };
