// Mirrors services/knowledge-service/app/db/models.py.
// Track 1 surface only: extraction_* fields are present because the API
// returns them, but K8 Track 1 FE renders them as "disabled" (see
// SESSION_PATCH D-K8-02). Track 2 UI will consume the other states.

export type ProjectType = 'book' | 'translation' | 'code' | 'general';

export type ExtractionStatus =
  | 'disabled'
  | 'building'
  | 'paused'
  | 'ready'
  | 'failed';

export type ScopeType = 'global' | 'project' | 'session' | 'entity';

export interface Project {
  project_id: string;
  user_id: string;
  name: string;
  description: string;
  project_type: ProjectType;
  book_id: string | null;
  instructions: string;
  extraction_enabled: boolean;
  extraction_status: ExtractionStatus;
  embedding_model: string | null;
  extraction_config: Record<string, unknown>;
  last_extracted_at: string | null;
  estimated_cost_usd: string;
  actual_cost_usd: string;
  is_archived: boolean;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreatePayload {
  name: string;
  description?: string;
  project_type: ProjectType;
  book_id?: string | null;
  instructions?: string;
}

export interface ProjectUpdatePayload {
  name?: string;
  description?: string;
  instructions?: string;
  // book_id: omit to leave unchanged; null to clear; UUID to set.
  book_id?: string | null;
}

export interface ProjectListResponse {
  items: Project[];
  next_cursor: string | null;
}

export interface ProjectListParams {
  limit?: number;
  cursor?: string | null;
  include_archived?: boolean;
}

export interface Summary {
  summary_id: string;
  user_id: string;
  scope_type: ScopeType;
  scope_id: string | null;
  content: string;
  token_count: number | null;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface SummariesListResponse {
  // JSON field is "global" (aliased on backend). TS keyword is not a
  // problem as a property name but kept identical to the wire format.
  global: Summary | null;
  projects: Summary[];
}

export interface SummaryUpdatePayload {
  content: string;
}

export interface UserDataDeleteResponse {
  deleted: {
    summaries: number;
    projects: number;
  };
}

export interface UserDataExportBundle {
  schema_version: number;
  user_id: string;
  exported_at: string;
  projects: Project[];
  summaries: Summary[];
}
