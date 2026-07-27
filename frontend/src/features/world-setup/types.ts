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
  /** Fields the model said the story establishes NOTHING for — an authoring prompt,
   *  not a defect. Auto-filling these would write an invention into the SSOT. */
  absent?: string[];
  /** Fields it never answered at all — an attention drop, not a story gap. */
  missing?: string[];
  /** Content it produced under a code this kind has no home for. Dropped at the
   *  write boundary, surfaced here so the observation is not lost silently. */
  extra?: string[];
}

/** Per-outcome tally from indexing the built lore as retrievable passages.
 *  `no_embedding_model` is the one the author must act on: the lore exists but
 *  nothing can retrieve it until this book's knowledge project has an embed model. */
export interface LoreIndexReport {
  indexed?: number;
  unchanged?: number;
  no_embedding_model?: number;
  unsupported_dim?: number;
  embed_failed?: number;
  [outcome: string]: number | undefined;
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
  params: Record<string, unknown> & {
    lore_index?: { outcomes?: LoreIndexReport; entities_seen?: number; skipped?: string };
  };
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
