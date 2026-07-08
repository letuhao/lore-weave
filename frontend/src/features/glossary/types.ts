export type FieldType = 'text' | 'textarea' | 'select' | 'number' | 'date' | 'tags' | 'url' | 'boolean';

// Class-C confirm-card preview (spec §13.6) — the current-state render returned by
// POST /v1/glossary/actions/preview, keyed on the action `descriptor`.
export type ActionPreviewRow = { label: string; value: string; note?: string };
export type ActionPreview = {
  descriptor: string;
  title: string;
  preview_rows: ActionPreviewRow[] | null;
  destructive: boolean;
};
export type EntityStatus = 'draft' | 'active' | 'inactive' | 'rejected';
export type Confidence = 'verified' | 'draft' | 'machine';
export type Relevance = 'major' | 'appears' | 'mentioned';
export type EvidenceType = 'quote' | 'summary' | 'reference';

export type AttributeDefinition = {
  attr_def_id: string;
  code: string;
  name: string;
  description?: string | null;
  field_type: FieldType;
  is_required: boolean;
  is_system: boolean;
  is_active: boolean;
  sort_order: number;
  options?: string[];
  genre_tags: string[];
  auto_fill_prompt?: string | null;
  translation_hint?: string | null;
  // #26/#7 — the authored merge strategy; 'summarize' attrs render the synthesized
  // canonical_value as the headline + the raw items under a "sources" disclosure.
  merge_strategy?: string;
};

export type EntityKind = {
  kind_id: string;
  code: string;
  name: string;
  description?: string | null;
  icon: string;
  color: string;
  is_default: boolean;
  is_hidden: boolean;
  sort_order: number;
  genre_tags: string[];
  entity_count: number;
  default_attributes: AttributeDefinition[];
};

export type KindSummary = Pick<EntityKind, 'kind_id' | 'code' | 'name' | 'icon' | 'color'>;

export type ChapterLink = {
  link_id: string;
  entity_id: string;
  chapter_id: string;
  chapter_title: string | null;
  chapter_index: number | null;
  relevance: Relevance;
  note: string | null;
  added_at: string;
};

export type Translation = {
  translation_id: string;
  attr_value_id: string;
  language_code: string;
  value: string;
  confidence: Confidence;
  translator: string | null;
  updated_at: string;
};

export type Evidence = {
  evidence_id: string;
  attr_value_id: string;
  chapter_id: string | null;
  chapter_title: string | null;
  block_or_line: string;
  evidence_type: EvidenceType;
  original_language: string;
  original_text: string;
  note: string | null;
  created_at: string;
  translations: Array<{ id: string; evidence_id: string; language_code: string; value: string; confidence: Confidence }>;
};

// S4 — batch-translate dialog (GET translation-candidates / POST apply-translations).
export type TranslationCandidateAttr = {
  attr_value_id: string;
  code: string;
  field_type: string;
  original_language: string;
  original_value: string;
  existing_value?: string | null;
  existing_confidence?: string | null;
};
export type TranslationCandidateEntity = {
  entity_id: string;
  display_name: string;
  kind_code: string;
  status: string;
  attributes: TranslationCandidateAttr[];
};
export type TranslationCandidatesResponse = {
  book_id: string;
  target_language: string;
  total: number;
  limit: number;
  offset: number;
  items: TranslationCandidateEntity[];
};
export type ApplyTranslationItem = { entity_id: string; attr_value_id: string; value: string };
export type ApplyTranslationsResponse = {
  translated: number;
  skipped_verified: number;
  skipped_empty: number;
  failed: string[];
};

export type AttributeValue = {
  attr_value_id: string;
  entity_id: string;
  attr_def_id: string;
  attribute_def: AttributeDefinition;
  original_language: string;
  original_value: string;
  translations: Translation[];
  evidences: Evidence[];
  // #26/#7 summarize mode — the LLM-synthesized canonical value (null until the first
  // end-of-job resynthesis) + whether a re-synthesis is pending (the raw set changed since).
  canonical_value?: string | null;
  canonical_dirty?: boolean;
};

// Raw-search "why it matched" payload (search_mode=raw). Highlights are
// Unicode CODE-POINT (rune) offset pairs within `snippet` — render via
// Array.from() slicing (UTF-16 indexing would mis-slice astral/CJK).
export type EntityMatch = {
  field_code: string; // name | alias | translation
  snippet: string;
  highlights: number[][];
};

export type GlossaryEntitySummary = {
  entity_id: string;
  book_id: string;
  kind_id: string;
  kind: KindSummary;
  display_name: string;
  display_name_translation: string | null;
  status: EntityStatus;
  alive?: boolean | null;
  // Authored short description (≤500 chars, nullable). The BE entity GET returns it;
  // the type previously omitted it (drift). Surfaced in the KG entity detail (#11).
  short_description?: string | null;
  // Optional author-set disambiguator (e.g. a world/realm name) for a name that
  // legitimately recurs across different in-story contexts — D-GLOSSARY-ENTITY-SCOPE.
  scope_label?: string;
  tags: string[];
  chapter_link_count: number;
  translation_count: number;
  evidence_count: number;
  created_at: string;
  updated_at: string;
  match?: EntityMatch | null; // present only on raw-search results
};

// Whitelisted server sort keys (must match glossary-service entityOrderBy).
export type EntitySort =
  | 'updated_at'
  | 'updated_at_asc'
  | 'name'
  | 'name_desc'
  | 'created_at'
  | 'created_at_asc'
  | 'kind'
  | 'status'
  | 'alive'
  | 'links'
  | 'evidence'
  | 'relevance';

export type GlossaryEntity = GlossaryEntitySummary & {
  chapter_links: ChapterLink[];
  attribute_values: AttributeValue[];
};

export type GlossaryEntityListResponse = {
  items: GlossaryEntitySummary[];
  total: number;
  limit: number;
  offset: number;
};


// ── Kind-resolution review (unknown bucket + aliases) ────────────────────────
// When extract-entities can't resolve an incoming kind_code, the entity is parked
// under the 'unknown' system kind (never dropped) and remembers the code it arrived
// as in source_kind_code. These types back the author's triage GUI.

export type UnknownEntity = {
  entity_id: string;
  name: string;
  source_kind_code: string | null;
  status: string;
  created_at: string;
  // D-GLOSSARY-ENTITY-SCOPE — see GlossaryEntitySummary.scope_label.
  scope_label?: string;
};

export type EntityNameEntry = {
  entity_id: string;
  display_name: string;
  kind_code?: string;
  kind_color?: string;
  kind_icon?: string;
  kind_name?: string;
};

// ── Merge candidates (mui #1c — coreference merge inbox) ─────────────────────
// knowledge's coref detector proposes clusters of likely-same entities; the
// author reviews here and confirms via the R5 merge endpoint (or dismisses).

export type MergeCandidateMember = {
  entity_id: string;
  name: string;
  aliases: string[];
  chapter_link_count: number;
};

export type MergeCandidate = {
  candidate_id: string;
  kind_code: string;
  score: number;
  rationale: string;
  evidence: unknown;
  suggested_winner_entity_id?: string;
  status: 'proposed' | 'dismissed' | 'merged';
  created_at: string;
  members: MergeCandidateMember[];
};

export type MergeCandidateListResponse = {
  candidates: MergeCandidate[];
};

export type MergeResultItem = {
  loser_id: string;
  journal_id?: string;
  status: 'merged' | 'skipped' | 'failed';
  reason?: string;
};

export type MergeResult = {
  winner_id: string;
  results: MergeResultItem[];
};

export type FilterState = {
  kindCodes: string[];
  status: 'all' | EntityStatus;
  searchQuery: string;
};

export const defaultFilters: FilterState = {
  kindCodes: [],
  status: 'all',
  searchQuery: '',
};

// ── Evidence list types ──────────────────────────────────────────────────────

export type EvidenceListItem = {
  evidence_id: string;
  attr_value_id: string;
  attribute_name: string;
  attribute_code: string;
  chapter_id: string | null;
  chapter_title: string | null;
  chapter_index: number | null;
  block_or_line: string;
  evidence_type: EvidenceType;
  original_language: string;
  original_text: string;
  display_text: string;
  display_language: string;
  note: string | null;
  // Provenance (D-EVIDENCE-PROVENANCE-OVERHAUL M1): trust of the quote↔source match.
  // char_* are null when not offset-matched. status: exact/resolved (verified) |
  // ambiguous | unmatched (likely hallucinated) | unverified (no validation run).
  char_start: number | null;
  char_end: number | null;
  provenance_status: 'exact' | 'resolved' | 'ambiguous' | 'unmatched' | 'unverified';
  created_at: string;
};

export type EvidenceFilterOption = {
  attr_value_id: string;
  name: string;
};

export type EvidenceChapterOption = {
  chapter_id: string;
  chapter_title: string | null;
  chapter_index: number | null;
};

export type EvidenceListResponse = {
  items: EvidenceListItem[];
  total: number;
  limit: number;
  offset: number;
  available_attributes: EvidenceFilterOption[];
  available_chapters: EvidenceChapterOption[];
  available_languages: string[];
};

export type EvidenceListParams = {
  limit?: number;
  offset?: number;
  evidence_type?: EvidenceType;
  attr_value_id?: string;
  chapter_id?: string;
  language?: string;
  sort_by?: 'created_at' | 'chapter_index' | 'block_or_line' | 'attribute_name';
  sort_dir?: 'asc' | 'desc';
};

export type CreateEvidencePayload = {
  evidence_type: EvidenceType;
  original_text: string;
  original_language?: string;
  chapter_id?: string;
  chapter_title?: string;
  chapter_index?: number;
  block_or_line?: string;
  note?: string;
};

export type PatchEvidencePayload = {
  original_text?: string;
  original_language?: string;
  evidence_type?: EvidenceType;
  chapter_id?: string | null;
  chapter_title?: string | null;
  chapter_index?: number | null;
  block_or_line?: string;
  note?: string | null;
};

// ── VG-3: entity revision history (D-GLOSSARY-VERSIONING) ────────────────────

export type EntityRevisionSummary = {
  revision_id: string;
  revision_num: number;
  op: string; // created | updated | restore | baseline | delete
  actor_type: string; // user | pipeline | system
  actor_id?: string;
  created_at: string;
};

export type RevisionSnapshotTranslation = {
  language_code: string;
  value: string;
  confidence?: string;
};

export type RevisionSnapshotEvidence = {
  evidence_type?: string;
  original_text?: string;
  chapter_title?: string | null;
};

export type RevisionSnapshotAttribute = {
  code?: string;
  name?: string;
  original_value?: string;
  translations?: RevisionSnapshotTranslation[];
  evidences?: RevisionSnapshotEvidence[];
};

export type RevisionSnapshotChapterLink = {
  chapter_title?: string | null;
  chapter_index?: number | null;
  relevance?: string;
};

export type RevisionSnapshot = {
  status?: string;
  alive?: boolean;
  tags?: string[];
  kind?: { code?: string; name?: string };
  attributes?: RevisionSnapshotAttribute[];
  chapter_links?: RevisionSnapshotChapterLink[];
};

export type EntityRevisionDetail = EntityRevisionSummary & {
  snapshot: RevisionSnapshot;
};
