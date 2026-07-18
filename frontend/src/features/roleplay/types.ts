// Roleplay practice — types mirror the roleplay-service backend (roleplay_scripts
// + start) and the chat-service /evaluate scorecard. The turn loop reuses the
// chat feature's ChatSession/ChatMessage types; we add the script (persona) and
// scorecard shapes here. Interview is a preset genre of roleplay.

export interface ScenarioCharter {
  goal?: string;
  premise?: string;
  phases: string[];
  checklist: string[];
  beats?: string[];
  time_budget_min?: number | null;
  language?: string;
  // ACP A4 — the fixed question count an interview drives before wrapping (a scenario may
  // pin it; else an interview genre defaults to 5 server-side — mirrored in practiceProgress).
  question_target?: number | null;
}

export interface Script {
  script_id: string;
  owner_user_id: string | null; // null ⇒ System tier (read-only default)
  tier: 'system' | 'user' | 'book';
  code: string;
  name: string;
  description: string | null;
  system_prompt: string;
  model_source: string | null;
  model_ref: string | null;
  scenario: ScenarioCharter;
  rubric: Record<string, unknown> | null;
  genre: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface StartScriptPayload {
  model_source?: string;
  model_ref?: string;
}

export interface StartScriptResponse {
  session_id: string;
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
