// Module 05 — Glossary & Lore Management types (SP-1 foundation)

export type FieldType = 'text' | 'textarea' | 'select' | 'number' | 'date' | 'tags' | 'url' | 'boolean';

export type AttributeDefinition = {
  attr_def_id: string;
  code: string;
  name: string;
  field_type: FieldType;
  is_required: boolean;
  sort_order: number;
  options?: string[];
};

export type EntityKind = {
  kind_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
  is_default: boolean;
  is_hidden: boolean;
  sort_order: number;
  genre_tags: string[];
  default_attributes: AttributeDefinition[];
};

// ── Entity (added in SP-2) ───────────────────────────────────────────────────

export type EntityStatus = 'draft' | 'active' | 'inactive';

export type ChapterLink = {
  link_id: string;
  entity_id: string;
  chapter_id: string;
  chapter_title: string | null;
  chapter_index: number | null;
  relevance: 'major' | 'appears' | 'mentioned';
  note: string | null;
  added_at: string;
};

export type Confidence = 'verified' | 'draft' | 'machine';

export type Translation = {
  translation_id: string;
  attr_value_id: string;
  language_code: string;
  value: string;
  confidence: Confidence;
  translator: string | null;
  updated_at: string;
};

export type EvidenceTranslation = {
  id: string;
  evidence_id: string;
  language_code: string;
  value: string;
  confidence: Confidence;
};

export type Evidence = {
  evidence_id: string;
  attr_value_id: string;
  chapter_id: string | null;
  chapter_title: string | null;
  block_or_line: string;
  evidence_type: 'quote' | 'summary' | 'reference';
  original_language: string;
  original_text: string;
  note: string | null;
  created_at: string;
  translations: EvidenceTranslation[];
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
  kind: EntityKind;
  display_name: string;
  display_name_translation: string | null;
  status: EntityStatus;
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

// ── Filter state ─────────────────────────────────────────────────────────────

export type FilterState = {
  kindCodes: string[];
  status: 'all' | EntityStatus;
  chapterIds: string[] | 'unlinked';
  searchQuery: string;
  tags: string[];
};
