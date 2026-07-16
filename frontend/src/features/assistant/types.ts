// WS-1.10 — the Work Assistant feature types. The assistant reuses the chat surface
// (features/chat) bound to the user's private diary book + assistant knowledge project;
// these types cover the assistant-specific control plane (provision, consent, end-of-day).

/** The provisioning half-state map (BFF: v1/assistant/provision). Every step is surfaced,
 *  never silently omitted — the home strip reads it and re-drives on open. */
export interface ProvisionStatus {
  diary_book: string;
  assistant_project: string;
  work_ontology: string;
  todays_session: string;
  self_entity: string;
  consent: string;
  timezone: string;
}

export interface ProvisionResult {
  provisioned: boolean;
  book_id?: string;
  project_id?: string;
  provision_status: ProvisionStatus;
}

/** Result of POST /v1/assistant/end-day (the public distiller trigger). */
export interface EndDayResult {
  enqueued: boolean;
  entry_date?: string;
  message_id?: string;
}

/** One diary entry (GET /v1/books/{id}/diary/entries) — the distilled prose for a day. */
export interface DiaryEntry {
  chapter_id: string;
  entry_date: string;
  entry_zone: string;
  title: string;
  word_count: number;
  journal_kind: string;
  kept: boolean;
  body: string;
  diary_kept_at?: string;
  draft_updated_at?: string;
}

export interface DiaryEntriesResponse {
  entries: DiaryEntry[];
  count: number;
}

/** WS-2.6a / D17 — result of POST /v1/assistant/correct (edit a diary day's entry text). Leg 1 (amend
 *  the PG SSOT) is fatal-if-failed; leg 2/3 (graph reconcile) is NON-FATAL — `reextract_enqueued:false`
 *  + `reextract_error` means "correction saved, memory sync pending; offer a retry". */
export interface CorrectResult {
  amended: boolean;
  entry_date?: string;
  kept_preserved?: boolean;
  reextract_enqueued: boolean;
  message_id?: string;
  reextract_error?: string;
}

/** WS-2.6c / D17 — result of POST /v1/assistant/forget (erase a remembered person). Leg 1 (delete the
 *  structured KG memory + facts + pending tombstone) is fatal-if-failed; leg 2 (redact the name from the
 *  diary source prose) is NON-FATAL — `redaction_error` means "memory erased, name may linger in prose". */
export interface ForgetResult {
  forgotten: boolean;
  name?: string;
  entities_deleted?: number;
  facts_deleted?: number;
  pending_tombstoned?: number;
  redacted_entries?: number;
  redaction_error?: string;
}

/** C8 / WS-5.6 — a surfaced weekly-reflection pattern the user can DISMISS (period-independent key). */
export interface ReflectionPattern {
  detector_code: string;
  summary: string;
  pattern_key: string;
}

/** C8 / WS-5.21 — one scored coaching dimension (server-authoritative from the rubric; the model
 *  contributes only a clamped 1-5 score + note per fixed key). `score` is null when the model omitted it. */
export interface ScorecardDimension {
  key: string;
  label: string;
  score: number | null;
  note?: string | null;
}

/** C8 — the coaching scorecard. `quarantine` (SD-7) is SHOWN but EXCLUDED from any trend line until a
 *  human-rating milestone certifies the scorer; every self-run score is quarantine=true (fail-closed). */
export interface Scorecard {
  overall_score?: number | null;
  summary?: string | null;
  quarantine: boolean;
  dimensions: ScorecardDimension[];
}

/** R2 (D-COACHING-SCORECARD-MOUNT) — one persisted scorecard (a chat_outputs 'scorecard' row) + its
 *  card. `card` may be malformed/partial from an old row, so consumers normalize before rendering. */
export interface ScorecardItem {
  output_id: string;
  session_id: string | null;
  title: string | null;
  created_at: string | null;
  card: Scorecard;
}

/** WS-2.5 — one pending diary fact awaiting the user's confirm/reject (the fact inbox). Mirrors
 *  knowledge-service's PendingFact model incl. the WS-2.2 structured fields (nullable — a coarse fact
 *  carries only fact_text; a structured one carries the subject/predicate/object trio + event_date). */
export interface DiaryPendingFact {
  pending_fact_id: string;
  user_id: string;
  project_id: string | null;
  session_id: string | null;
  fact_type: 'decision' | 'preference' | 'milestone' | 'negation' | 'statement';
  fact_text: string;
  created_at: string;
  subject?: string | null;
  predicate?: string | null;
  object?: string | null;
  event_date?: string | null;
  provenance?: string | null;
}

// A3 — the autonomous-layer schedule. Closed set of job_kinds (mirrors scheduler-service + the gateway).
export type AutonomousJobKind =
  | 'eod_distill'
  | 'weekly_rollup'
  | 'weekly_reflection'
  | 'proactive_nudge'
  | 'nudge';

export interface ScheduleRow {
  job_kind: AutonomousJobKind;
  cadence: string;
  fire_local_time: string;
  timezone: string;
  enabled: boolean;
  next_fire_at?: string | null;
}
