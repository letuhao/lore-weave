export type FieldType = 'text' | 'textarea' | 'select' | 'number' | 'date' | 'tags' | 'url' | 'boolean';
export type EntityStatus = 'draft' | 'active' | 'inactive';
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

export type AttributeValue = {
  attr_value_id: string;
  entity_id: string;
  attr_def_id: string;
  attribute_def: AttributeDefinition;
  original_language: string;
  original_value: string;
  translations: Translation[];
  evidences: Evidence[];
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
  tags: string[];
  chapter_link_count: number;
  translation_count: number;
  evidence_count: number;
  created_at: string;
  updated_at: string;
};

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

export type GenreGroup = {
  id: string;
  book_id: string;
  name: string;
  color: string;
  description: string;
  sort_order: number;
  created_at: string;
};

export type EntityNameEntry = {
  entity_id: string;
  display_name: string;
  kind_code?: string;
  kind_color?: string;
  kind_icon?: string;
  kind_name?: string;
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
