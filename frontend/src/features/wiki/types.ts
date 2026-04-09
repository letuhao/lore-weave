export interface WikiKindSummary {
  kind_id: string;
  code: string;
  name: string;
  icon: string;
  color: string;
}

export interface WikiArticleListItem {
  article_id: string;
  entity_id: string;
  book_id: string;
  display_name: string;
  kind: WikiKindSummary;
  status: string;
  template_code: string | null;
  revision_count: number;
  updated_at: string;
}

export interface WikiArticleListResp {
  items: WikiArticleListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface WikiAttrTranslation {
  translation_id: string;
  attr_value_id: string;
  language_code: string;
  value: string;
  confidence: string;
  translator?: string;
  updated_at: string;
}

export interface WikiAttrDef {
  attr_def_id: string;
  code: string;
  name: string;
  field_type: string;
  is_required: boolean;
  is_system: boolean;
  sort_order: number;
}

export interface WikiInfoboxAttr {
  attr_value_id: string;
  entity_id: string;
  attr_def_id: string;
  attribute_def: WikiAttrDef;
  original_language: string;
  original_value: string;
  translations: WikiAttrTranslation[];
  evidences: unknown[];
}

export interface WikiArticleDetail {
  article_id: string;
  entity_id: string;
  book_id: string;
  display_name: string;
  kind: WikiKindSummary;
  status: string;
  template_code: string | null;
  revision_count: number;
  updated_at: string;
  body_json: Record<string, unknown>;
  spoiler_chapters: string[];
  infobox: WikiInfoboxAttr[];
  created_at: string;
}

export interface WikiRevisionListItem {
  revision_id: string;
  article_id: string;
  version: number;
  author_id: string;
  author_type: string;
  summary: string;
  created_at: string;
}

export interface WikiRevisionListResp {
  items: WikiRevisionListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface WikiRevisionDetail extends WikiRevisionListItem {
  body_json: Record<string, unknown>;
}

export interface WikiSuggestionResp {
  suggestion_id: string;
  article_id: string;
  user_id: string;
  diff_json: Record<string, unknown>;
  reason: string;
  status: string;
  reviewer_note: string | null;
  created_at: string;
  reviewed_at: string | null;
  article_display_name?: string;
}

export interface WikiSuggestionListResp {
  items: WikiSuggestionResp[];
  total: number;
  limit: number;
  offset: number;
}
