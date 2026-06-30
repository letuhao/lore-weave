// Types for the knowledge-temporal feature — the FE's view of the KAL (knowledge-gateway)
// read surface (contracts/api/knowledge-gateway/kal.v1.yaml). Shapes mirror what the KAL
// CONTROLLERS actually return (which thinly wrap the glossary/knowledge responses), so fields
// the runtime may omit are optional/nullable — the FE degrades, never crashes, on a sparse read.

/** Per-substrate honoring of `as_of` (§12.5.1). The KG reports temporal_unsupported until F3. */
export interface TemporalCapability {
  glossary?: string; // 'ordinal_valid_time' | 'current_only'
  kg?: string; // 'ordinal_valid_time' | 'from_order_only' | 'temporal_unsupported'
}

/** The folded canonical snapshot (or its degrade-to-canon-content fallback). */
export interface CanonicalSnapshot {
  entity_id: string;
  content: string; // bounded prose; '' when unbuildable
  as_of_ordinal?: number | null;
  canonical_status?: 'current' | 'stale' | 'unbuildable' | string;
  /** 'snapshot' (fresh fold) | 'canon-content' (degrade fallback). */
  source?: 'snapshot' | 'canon-content' | string;
}

/** On-demand translation of the folded canonical into `language_code` (§6B/§7.6). `status`
 *  drives the FE: ready (translated `content`, `cached`) | translating (original `content`, poll) |
 *  failed (original `content` + `error_code`) | unbuildable (no canonical). */
export interface CanonicalTranslation {
  entity_id: string;
  language_code: string;
  content: string;
  translated: boolean;
  status: 'ready' | 'translating' | 'failed' | 'unbuildable' | string;
  /** Set only when status=failed: no_model | quota | provider | no_user | unconfigured. */
  error_code?: string;
  cached?: boolean;
  as_of_ordinal?: number | null;
  canonical_status?: string;
  source?: string;
}

/** One bi-temporal fact. valid_to_ordinal null = open (+∞). */
export interface Fact {
  fact_id: string;
  entity_id: string;
  fact_kind: 'attribute' | 'relation' | 'event' | 'name' | 'alias' | string;
  attr_or_predicate: string;
  value: string;
  valid_from_ordinal: number;
  valid_to_ordinal: number | null;
  cardinality: 'single' | 'multi' | string;
  source_episode_id?: string | null;
}

export interface FactsResponse {
  items: Fact[];
  temporal_capability?: TemporalCapability;
}

/** A timeline change row (the per-entity change feed). The glossary timeline returns facts
 *  with their interval; `kind` may be derived FE-side from valid_to/invalidated state. */
export interface TimelineEntry extends Fact {
  kind?: 'open' | 'close' | 'invalidate' | string;
  at_ordinal?: number;
  invalidated_at?: string | null;
  invalidated_reason?: string | null;
  // Evidence/citation (best-effort — may be absent until KG quote-on-citation is dense).
  source_chapter_id?: string | null;
  quote?: string | null;
}

export interface TimelineResponse {
  items: TimelineEntry[];
  next_cursor?: string | null;
}

export interface AttrValuesResponse {
  items: Fact[];
  next_cursor?: string | null;
}

export interface RosterEntry {
  entity_id: string;
  name: string;
}

export interface RosterResponse {
  items: RosterEntry[];
  next_cursor?: string | null;
}

export interface RetrievedSegment {
  id?: string;
  text?: string;
  score?: number;
  // Citation: the live runtime returns `chapter_id`; the frozen contract declares
  // `chapter_ordinal` (+ `episode_id`). Carry both so the chapter label survives either shape.
  chapter_id?: string | null;
  chapter_ordinal?: number | null;
  episode_id?: string | null;
  [k: string]: unknown;
}

export interface RetrieveResponse {
  items: RetrievedSegment[];
  temporal_capability?: TemporalCapability;
}

export interface Edge {
  [k: string]: unknown;
}

export interface NeighborhoodResponse {
  edges: Edge[];
  temporal_capability?: TemporalCapability;
}
