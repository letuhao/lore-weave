// Interview-practice roleplay (M7) — types mirror the chat-service backend
// (session_templates + the /evaluate scorecard). The turn loop itself reuses
// the chat feature's ChatSession/ChatMessage types — we only add the
// template (persona) and scorecard shapes here.

export interface ScenarioCharter {
  goal: string;
  phases: string[];
  checklist: string[];
  time_budget_min?: number | null;
  language: string;
}

export interface SessionTemplate {
  template_id: string;
  owner_user_id: string | null; // null ⇒ System tier (read-only default)
  tier: 'system' | 'user';
  code: string;
  name: string;
  description: string | null;
  system_prompt: string;
  model_source: string | null;
  model_ref: string | null;
  scenario: ScenarioCharter;
  rubric: Record<string, unknown> | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StartPracticePayload {
  title?: string;
  model_source?: string;
  model_ref?: string;
  project_id?: string;
}

export interface ChecklistVerdict {
  item: string;
  covered: boolean;
  note: string | null;
}

export interface Scorecard {
  overall_score: number | null;
  star_coverage: string | null;
  clarity: string | null;
  filler: string | null;
  checklist: ChecklistVerdict[];
  strengths: string[];
  improvements: string[];
  summary: string | null;
  partial: boolean;
}

export interface EvaluateResponse {
  output_id: string;
  session_id: string;
  scorecard: Scorecard;
  model_source: string;
  model_ref: string;
}
