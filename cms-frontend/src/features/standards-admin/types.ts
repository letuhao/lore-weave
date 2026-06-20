// Types for the System-tier standards admin API (glossary-service via gateway).
// Only the fields the CMS uses are modeled; the API may return more.

export type SystemGenre = {
  genre_id: string;
  code: string;
  name: string;
  icon: string | null;
  color: string | null;
  sort_order: number;
  tier?: string;
};

export type GenreCreate = {
  name: string;
  code?: string;
  icon?: string;
  color?: string;
  sort_order?: number;
};

export type GenreUpdate = {
  name?: string;
  icon?: string;
  color?: string;
  sort_order?: number;
};

export type SystemKind = {
  kind_id: string;
  code: string;
  name: string;
  description: string | null;
  icon: string | null;
  color: string | null;
  is_hidden: boolean;
  sort_order: number;
};

export type KindCreate = {
  name: string;
  code?: string;
  description?: string;
  icon?: string;
  color?: string;
  is_hidden?: boolean;
  sort_order?: number;
};

export type KindUpdate = {
  name?: string;
  description?: string;
  icon?: string;
  color?: string;
  is_hidden?: boolean;
  sort_order?: number;
};

export type FieldType =
  | 'text'
  | 'textarea'
  | 'select'
  | 'number'
  | 'date'
  | 'tags'
  | 'url'
  | 'boolean';

export const FIELD_TYPES: FieldType[] = [
  'text',
  'textarea',
  'select',
  'number',
  'date',
  'tags',
  'url',
  'boolean',
];

export type SystemAttribute = {
  attr_id: string;
  kind_id: string;
  genre_id: string;
  code: string;
  name: string;
  description: string | null;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options: string[] | null;
  auto_fill_prompt?: string | null;
  translation_hint?: string | null;
};

export type AttributeCreate = {
  kind_id: string;
  genre_id: string;
  name: string;
  code?: string;
  description?: string;
  field_type?: FieldType;
  is_required?: boolean;
  sort_order?: number;
  options?: string[];
  auto_fill_prompt?: string;
  translation_hint?: string;
};

export type AttributeUpdate = {
  name?: string;
  description?: string;
  field_type?: FieldType;
  is_required?: boolean;
  sort_order?: number;
  options?: string[];
  auto_fill_prompt?: string;
  translation_hint?: string;
};

// ---- Recycle bin (G-C8 soft-delete) -------------------------------------

export type SystemTrashRow = {
  id: string;
  code: string;
  name: string;
  /** attributes only — the cell context (survives a deprecated parent) */
  kind_code?: string;
  genre_code?: string;
  field_type?: string;
  deprecated_at: string;
};

export type SystemTrash = {
  genres: SystemTrashRow[];
  kinds: SystemTrashRow[];
  attributes: SystemTrashRow[];
};
