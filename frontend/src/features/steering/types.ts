// RAID C1 — per-book author steering rules (the "story-bible-as-steering" / Cursor-rules analog).
// Backend SSOT is book-service `book_steering`; chat-service renders enabled entries as a
// <steering> system part on book-scoped turns. This module is the FE authoring surface.

/** How an entry is injected into a turn. Closed set — mirrors the book-service enum.
 *  - always      → included on every book-scoped turn.
 *  - scene_match → included only when the turn's scene matches `match_pattern`.
 *  - manual      → included only when the author references it by #name.
 *  - auto        → v1-honest: currently triggered exactly like `manual` (#name). The UI
 *                  surfaces this so authors aren't misled into expecting auto-selection yet. */
export type InclusionMode = 'always' | 'scene_match' | 'manual' | 'auto';

export const INCLUSION_MODES: InclusionMode[] = ['always', 'scene_match', 'manual', 'auto'];

/** Caps enforced by the backend (422 on violation). Mirrored here for client-side guards. */
export const STEERING_LIMITS = {
  bodyMax: 8000,
  nameMax: 200,
  maxRows: 20,
} as const;

/** A steering entry as returned by book-service. */
export interface SteeringEntry {
  id: string;
  book_id: string;
  name: string;
  body: string;
  inclusion_mode: InclusionMode;
  match_pattern: string | null;
  enabled: boolean;
  author_user_id: string;
  created_at: string;
  updated_at: string;
}

/** Create/update payload — all fields optional on update; name+body required on create. */
export interface SteeringInput {
  name?: string;
  body?: string;
  inclusion_mode?: InclusionMode;
  match_pattern?: string | null;
  enabled?: boolean;
}
