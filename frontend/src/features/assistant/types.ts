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
