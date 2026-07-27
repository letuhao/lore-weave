// World Setup (glossary-build pipeline) — the FE view of composition-service's
// deterministic world-building FSM (spec docs/specs/2026-07-27-glossary-kg-build-workflows.md).
// The agent does NOT pick tools here: the human drives three checkpoints and the
// platform makes every write.

export type BuildStatus =
  | 'draft' | 'planning' | 'plan_ready' | 'building' | 'proposing' | 'proposed'
  | 'kg_projecting' | 'edges_ready' | 'done' | 'failed' | 'cancelled';

export type BuildDepth = 'standard' | 'deep';

/** One planned entity. `depth` is the dial the POC measured: standard = a single
 *  focused call; deep = outline → steered sections → distill (~10× the detail). */
export interface WorklistItem {
  name: string;
  kind: string;
  depth?: BuildDepth;
  why?: string;
}

export interface BuildItem {
  item_id: string;
  ordinal: number;
  name: string;
  kind: string;
  depth: BuildDepth;
  status: 'pending' | 'building' | 'built' | 'proposed' | 'skipped';
  skip_reason: string | null;
  proposed_entity_id: string | null;
  relations: { target_name?: string; type?: string; note?: string }[];
  section_count: number;
}

/** A relationship the executor emitted BY NAME, resolved server-side to graph
 *  node ids. `unresolved` ⇒ the target matched nothing — shown, never dropped. */
export interface BuildEdge {
  source_name: string;
  source_id: string | null;
  target_name: string;
  target_id: string | null;
  type: string;
  note?: string;
  unresolved: boolean;
}

export interface BuildRun {
  run_id: string;
  book_id: string;
  status: BuildStatus;
  params: Record<string, unknown>;
  worklist: WorklistItem[];
  edges: BuildEdge[];
  items?: BuildItem[];
  error_message: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface CreateRunBody {
  book_id: string;
  params: {
    model_source: string;
    /** user-model UUID — resolved via provider-registry, never a literal name. */
    model_ref: string;
    source_text: string;
    lang?: string;
    max_items?: number;
  };
}
