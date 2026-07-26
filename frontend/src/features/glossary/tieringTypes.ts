// G6 — genre·kind·attribute TIERED model types (System/User/Book).
// Mirrors the glossary-service contract `kinds_genres_attributes.yaml` (G1–G5).
// Kept separate from the legacy flat-model `types.ts` (retired in G6f).

export type Tier = 'system' | 'user' | 'book';

// Field types a tiered attribute can take (contract FieldType enum).
export type FieldType =
  | 'text'
  | 'textarea'
  | 'select'
  | 'number'
  | 'date'
  | 'tags'
  | 'url'
  | 'boolean';

// ── Standards tier (merged System + caller's User) ──────────────────────────

/** A genre as returned by `GET /v1/glossary/genres` (merged) or the user-genre CRUD. */
export interface Genre {
  genre_id: string;
  tier: Tier; // 'system' | 'user' (book genres come from the ontology read)
  owner_user_id?: string | null;
  code: string;
  name: string;
  icon: string;
  color: string;
  sort_order: number;
  cloned_from_genre_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface UserGenreCreate {
  code?: string;
  name: string;
  icon?: string;
  color?: string;
  sort_order?: number;
  clone_from_genre_id?: string | null;
}

/** A standards-tier attribute (`GET /system-attributes`, `/user-attributes`). */
export interface Attribute {
  attr_id: string;
  tier: Tier; // 'system' | 'user'
  kind_id: string;
  genre_id: string;
  code: string;
  name: string;
  description?: string | null;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options: string[];
  auto_fill_prompt?: string | null;
  translation_hint?: string | null;
}

export interface UserAttributeCreate {
  kind_id: string; // a live user_kind of the caller (attach-by-code)
  genre_id: string; // a live user_genre of the caller
  code?: string;
  name: string;
  description?: string | null;
  field_type?: FieldType;
  is_required?: boolean;
  sort_order?: number;
  options?: string[];
  auto_fill_prompt?: string | null;
  translation_hint?: string | null;
}

export interface UserKindCreate {
  code?: string;
  name: string;
  description?: string | null;
  icon?: string;
  color?: string;
  clone_from_kind_id?: string | null;
}

/** A user-tier kind (`GET /v1/glossary/user-kinds`). */
export interface UserKind {
  user_kind_id: string;
  owner_user_id?: string | null;
  code: string;
  name: string;
  description?: string | null;
  icon: string;
  color: string;
  is_active: boolean;
  cloned_from_kind_id?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface KindGenreLink {
  kind_id: string;
  genre_id: string;
}

// ── Book tier (the sovereign instance — from the ontology read) ─────────────

export interface BookGenre {
  genre_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
  sort_order: number;
  active: boolean;
  source_ref?: string | null; // 'system:<id>' | 'user:<id>' | null (book-native)
}

export interface BookKind {
  book_kind_id: string;
  code: string;
  name: string;
  description?: string | null;
  icon: string;
  color: string;
  sort_order: number;
  is_hidden: boolean;
  source_ref?: string | null;
}

export interface BookAttribute {
  attr_id: string;
  kind_id: string; // book_kind_id
  genre_id: string; // book genre_id
  code: string;
  name: string;
  description?: string | null;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options: string[];
  auto_fill_prompt?: string | null;
  translation_hint?: string | null;
  source_ref?: string | null;
  // How re-extraction merges this attribute (D-EXTRACT-ATTR-MERGE-DEFAULTS): append (accumulate),
  // overwrite (advance to latest), fill_if_empty (write-once), manual (queue for review).
  merge_strategy?: string;
}

/** `GET/POST /v1/glossary/books/{id}/ontology|adopt` — the book-local, single-tier read. */
export interface BookOntology {
  book_id: string;
  genres: BookGenre[];
  kinds: BookKind[];
  kind_genres: KindGenreLink[]; // book_kind_id ↔ book genre_id
  attributes: BookAttribute[];
}

/** R1 pick-list: codes to copy-down from the standards. */
export interface AdoptRequest {
  genres: string[];
  kinds: string[];
}

// Book-tier CRUD payloads.
export interface BookGenreCreate {
  code?: string;
  name: string;
  icon?: string;
  color?: string;
  sort_order?: number;
}
export interface BookKindCreate {
  code?: string;
  name: string;
  description?: string;
  icon?: string;
  color?: string;
  sort_order?: number;
}
export interface BookAttributeCreate {
  kind_id: string; // a live book_kind_id of this book
  genre_id: string; // a live book genre_id of this book
  code?: string;
  name: string;
  description?: string;
  field_type?: FieldType;
  is_required?: boolean;
  sort_order?: number;
  options?: string[];
  auto_fill_prompt?: string;
  translation_hint?: string;
}

// ── Sync (G5) ───────────────────────────────────────────────────────────────

export type SyncEntity = 'genre' | 'kind' | 'attribute';
export type SyncStatus = 'update_available' | 'source_retired';
export type SyncChoice = 'keep_mine' | 'take_theirs';

/** Semantic-field snapshot used in a sync diff (the hash surface). */
export interface SyncVals {
  name: string;
  description?: string | null;
  field_type?: FieldType;
  is_required?: boolean;
  options?: string[];
}

export interface SyncUpdateItem {
  entity: SyncEntity;
  id: string; // the BOOK row PK (genre_id | book_kind_id | attr_id)
  code: string;
  status: SyncStatus;
  source_ref: string; // 'system:<id>' | 'user:<id>'
  mine: SyncVals;
  theirs?: SyncVals | null; // null when source_retired
}

export interface SyncAvailable {
  book_id: string;
  updates: SyncUpdateItem[];
}

export interface SyncApplyItem {
  entity: SyncEntity;
  id: string;
  choice: SyncChoice;
}

export interface SyncApplyResult {
  applied: number;
  results: { entity: SyncEntity; id: string; result: 'applied' | 'source_retired' }[];
}

// ── Per-entity genre override (D2) ──────────────────────────────────────────

export interface EntityGenres {
  genre_ids: string[];
  uses_book_default: boolean; // true ⇒ no override; entity follows book active genres
}

// Generic list envelope for the standards reads (`{ items: T[] }`).
export interface ItemsResponse<T> {
  items: T[];
}
