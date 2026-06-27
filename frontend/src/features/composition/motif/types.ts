// Narrative Motif Library (W6) — the FROZEN DTO/API shapes mirrored from
// F0 §3.6 / W6 §1.3. These are the parallelization contract: tsc fails if a
// W1/W2/W3/W5 response drifts from these shapes. W6 is a PURE consumer — it
// exposes nothing back-end; it binds to these and mocks the API in tests until
// the real endpoints land.

// ── motif library DTOs ──────────────────────────────────────────────────────

/** DERIVED on the FE from {owner_user_id, visibility} — see `motifTier` in
 *  simpleMode.ts. The wire never sends a `tier`; it's a presentation grouping. */
export type MotifTier = 'system' | 'user' | 'public';

export type MotifKind =
  | 'sequence' | 'situation' | 'hook' | 'emotion_arc' | 'trope' | 'pattern' | 'scheme';
export type MotifStatus = 'draft' | 'active' | 'archived';
export type MotifSource = 'authored' | 'mined' | 'adopted' | 'imported';
export type MotifVisibility = 'private' | 'unlisted' | 'public';
export type Actant = 'subject' | 'object' | 'sender' | 'receiver' | 'helper' | 'opponent';

export type MotifBeat = {
  key: string;
  label: string;
  intent?: string;
  tension_target?: number;
  order: number;
};

export type MotifRole = {
  key: string;
  actant: Actant;
  label: string;
  constraints?: string;
};

/** §15.1 scheme intrigue (kind='scheme'). */
export type InfoAsymmetry = { knows: string[]; deceived: string[]; gap: string };

/** The full motif read projection (owner's own / system / public). The
 *  `embedding` vector + raw `source_ref` are NEVER projected (F0 — server-side). */
export type Motif = {
  id: string;
  owner_user_id: string | null;            // null = system tier
  code: string;
  language: string;
  visibility: MotifVisibility;
  kind: MotifKind;
  category: string | null;
  name: string;
  summary: string;
  genre_tags: string[];
  roles: MotifRole[];
  beats: MotifBeat[];
  preconditions: { text: string }[];
  effects: { text: string }[];
  tension_target: number | null;
  emotion_target: string | null;
  info_asymmetry?: InfoAsymmetry | null;
  examples: { text: string }[];
  abstraction_confidence: 'high' | 'med' | 'low' | null;
  source: MotifSource;
  source_version: number | null;
  judge_score: number | null;
  mining_support: number | null;
  status: MotifStatus;
  version: number;
};

/** The catalog allow-list projection (audit B-3): a STRICT subset — never a full
 *  Motif. The wire shape is exactly `_CATALOG_COLS` in the backend
 *  motif_repo.list_public (+ `adopt_target` stamped by the router). It STRUCTURALLY
 *  omits embedding / examples / beats / roles / raw source_ref / owner_user_id /
 *  visibility, so a non-owner never receives authored prose or the author id.
 *  GET /v1/composition/motifs/catalog answers `{ items, total, limit, offset }`. */
export type CatalogMotif = Pick<
  Motif, 'id' | 'code' | 'language' | 'kind' | 'category' | 'name' | 'summary'
  | 'genre_tags' | 'tension_target' | 'emotion_target' | 'source'
  | 'abstraction_confidence'
> & {
  judge_score: number | null;
  version: number;
  updated_at: string;            // ISO — list_public projects updated_at
  adopt_target: 'user';          // router-stamped: adopt always clones to the user tier
  adopt_count?: number;          // P2+ social fields — not yet on the wire
  rating?: number;
};

/** The catalog list envelope (B-3 discovery). Distinct from the `{ motifs }`
 *  envelope of GET /motifs — the catalog route paginates with total/offset. */
export type CatalogList = {
  items: CatalogMotif[];
  total: number;
  limit: number;
  offset: number;
};

// ── planner-binding DTOs (W2 exposes; the existing DecomposePreview gains these) ─

export type MatchReason = {
  tension: number;
  genre: string[];
  precond: string;
  cosine: number;
  summary: string;          // the plain-language one-liner (simple mode leads with it)
};

export type RoleBinding = { entity_id: string | null; entity_name: string };

export type BoundMotif = {
  motif_id: string | null;
  motif_name: string;
  motif_source: MotifSource;
  role_bindings: Record<string, RoleBinding>;   // role_key → cast (null = unresolved)
  match_reason: MatchReason;
};

/** Extends an existing decompose scene node with the motif binding. `motif: null`
 *  ⇒ free-form (the A3 invent fallback) — NOT an error state. */
export type DecomposeSceneMotif = {
  beat_key?: string;
  beat_label?: string;
  tension_target?: number;
  motif?: BoundMotif | null;
};

/** D-MOTIF-FE-PLANNERVIEW-WIRING (Shape A) — a committed scene's bound motif as
 *  returned by GET …/outline/motif-bindings: a BoundMotif plus the scene's beat_key. */
export type SceneBoundMotif = BoundMotif & { beat_key?: string | null };

/** The motif-bindings read response: per committed scene node, its bound motif (or
 *  null = free-form). The planner renders MotifBindingCard per node from this map. */
export type MotifBindingsResponse = {
  chapter_id: string;
  bindings: Record<string, SceneBoundMotif | null>;
};

export type OveruseWarning = {
  motif_id: string;
  motif_name: string;
  applied_in: string[];        // chapter labels where it's already applied
};

export type SuccessionHint = {
  from_motif_id: string;
  to_motif_code: string;
  to_motif_name: string;
  for_node_id: string;
};

// ── conformance trace (W5 exposes — GET …/conformance?scope=chapter) ──────────
// The shape MIRRORS the chapter reader's nested rows (routers/conformance.py
// `_assemble_conformance`): per scene `{planned, realized, conformance}`. The
// `conformance` dim is the critic.motif_conformance verdict (or null when no
// completed job / no dim yet / no bound motif). `calibrated=false` ⇒ the verdict is
// an advisory unverified self-report (R2.1 honesty). booleans may be null when the
// judge degraded (error set). NB: the reader emits NO chapter-level `conform_count`
// or `motif_name` — a chapter holds per-scene motifs, so a single chapter motif_name
// is ill-defined; the panel DERIVES the conforming/total count from `scenes`.

/** The critic.motif_conformance dim, echoed verbatim from the latest job's critic. */
export type ConformanceDim = {
  beat_realized: boolean | null;
  tension_band_match: boolean | null;
  reason?: string;
  motif_id?: string | null;
  beat_key?: string | null;
  planned_tension_band?: [number, number];
  calibrated: boolean;          // false ⇒ "advisory, unverified self-report"
  error?: string;               // set when the judge degraded (booleans null)
};

export type SceneConformance = {
  outline_node_id: string;
  title: string;
  beat_role: string | null;
  planned: {
    motif_id: string | null;
    motif_version: number | null;
    beat_key: string | null;
    tension: number | null;            // 0-100 (outline_node scale)
    role_bindings: Record<string, string>;
  };
  realized: {
    job_id: string | null;
    has_prose: boolean;                // presence only — the trace never carries prose
  };
  conformance: ConformanceDim | null;  // null = not judged yet / no bound motif
};

export type ChapterConformance = {
  scope?: string;
  chapter_id: string;
  calibrated: boolean;                 // chapter-level calibration flag (R2.1)
  scenes: SceneConformance[];
};

// ── quota / cost-confirm (Tier-W — the FE mints + confirms, never executes) ───

export type ConfirmDescriptor =
  | 'composition.motif_mine' | 'composition.arc_import' | 'composition.conformance_run';

export type CostEstimate = {
  confirm_token: string;
  descriptor: ConfirmDescriptor;
  est_usd: number;
  est_tokens: number;
  quota_remaining: number | null;
};

export type QuotaError = {
  code: 'quota_exceeded';
  resource: 'publish' | 'adopt' | 'mine';
  limit: number;
  used: number;
};

// ── write-arg shapes (mirror F0 MotifCreateArgs — owner is NEVER an arg) ───────

export type MotifCreateArgs = {
  code: string;
  name: string;
  language?: string;
  kind?: MotifKind;
  category?: string | null;
  summary?: string;
  genre_tags?: string[];
  roles?: MotifRole[];
  beats?: MotifBeat[];
  preconditions?: { text: string }[];
  effects?: { text: string }[];
  info_asymmetry?: InfoAsymmetry | null;
  tension_target?: number | null;
  emotion_target?: string | null;
  examples?: { text: string }[];
  visibility?: MotifVisibility;
};

export type MotifPatchArgs = Partial<Omit<MotifCreateArgs, 'code' | 'language'>> & {
  status?: MotifStatus;
};

/** The bind→COMMIT→GENERATE route contract (W6 designs; W2 wires it). §4.6. */
export type CommitAndGenerateRoute = {
  tab: 'compose' | 'assemble';
  sceneId: string;
};
