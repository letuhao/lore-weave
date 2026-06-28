// W10 arc-timeline — the WIRE DTOs for the arc-template surface, mirrored from the
// composition-service F0 §3.6 / W10 models (app/db/models.py: ArcTemplate, ArcPlacement,
// ArcApplyArgs, ResolvedPlacement, DropMergeEntry, ArcApplyPlan). tsc fails here if a
// backend response drifts. The UI-interaction contract (ArcPlacement w/ synthetic id,
// ArcThread, ArcTimelineEdit) lives in arcTimelineContract.ts — these are the on-the-wire
// shapes the arcApi sends/receives; the hook maps between the two.
import type { MotifStatus, MotifVisibility } from './types';

export type ArcSourceKind = 'authored' | 'mined' | 'imported';

/** One backend `layout[]` entry — NOTE it carries NO `id` and NO `motif_name`
 *  (those are synthesized FE-side for keyboard focus + display). The hook strips
 *  them back to this shape on PATCH. */
export type ArcLayoutEntry = {
  motif_code: string;
  motif_id: string | null;
  thread: string;
  span_start: number;
  span_end: number;
  ord: number;
  role_hints?: Record<string, unknown>;
  triggers?: string[];
};

/** A backend `threads[]` entry. The write model is `{key,label}`; a `glyph` may ride
 *  the JSONB dict on read (co-encoding §2.2) but is not persisted via the basic
 *  layout-only PATCH (the editor never rewrites threads). */
export type ArcThreadEntry = { key: string; label: string; glyph?: string };

export type ArcRosterEntry = {
  key: string;
  actant?: string | null;
  label?: string;
  constraints?: string[];
};

/** The full arc-template read projection (owner's own / system / public). The
 *  `embedding` vector + raw `source_ref` are never projected. */
export type ArcTemplate = {
  id: string;
  owner_user_id: string | null;        // null = system tier
  code: string;
  language: string;
  visibility: MotifVisibility;
  name: string;
  summary: string;
  genre_tags: string[];
  chapter_span: number | null;
  threads: ArcThreadEntry[];
  layout: ArcLayoutEntry[];
  pacing: Record<string, unknown>[];
  arc_roster: ArcRosterEntry[];
  source: ArcSourceKind;
  imported_derived: boolean;
  source_version: number | null;
  status: MotifStatus;
  version: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type ArcTemplateListParams = {
  scope?: 'all' | 'system' | 'mine';
  genre?: string;
  q?: string;
  language?: string;
  status?: string;
  limit?: number;
};

export type ArcTemplateList = {
  arc_templates: ArcTemplate[];
  scope: string;
  limit: number;
};

// ── write args (mirror ArcTemplateCreateArgs / ArcTemplatePatchArgs — owner is
// NEVER an arg; the repo stamps it = caller) ──────────────────────────────────────
export type ArcTemplateCreateArgs = {
  code: string;
  name: string;
  language?: string;
  summary?: string;
  genre_tags?: string[];
  chapter_span?: number | null;
  threads?: ArcThreadEntry[];
  layout?: ArcLayoutEntry[];
  pacing?: Record<string, unknown>[];
  arc_roster?: ArcRosterEntry[];
  visibility?: MotifVisibility;
};

export type ArcTemplatePatchArgs = {
  name?: string;
  summary?: string;
  genre_tags?: string[];
  chapter_span?: number | null;
  threads?: ArcThreadEntry[];
  layout?: ArcLayoutEntry[];
  pacing?: Record<string, unknown>[];
  arc_roster?: ArcRosterEntry[];
  visibility?: MotifVisibility;
  status?: MotifStatus;
};

// ── apply-preview (§12.5 — the PURE/deterministic placement-rescale plan) ──────────
export type ArcApplyArgs = {
  target_chapters: number;
  /** arc_roster role-key → the new book's concrete cast (bound ONCE, propagated). */
  roster_bindings?: Record<string, unknown>;
};

/** One rescaled placement in the apply plan. `merged_codes` = other placements folded
 *  into this survivor when the target was smaller than the source span (§12.6). */
export type ResolvedPlacement = {
  motif_code: string;
  motif_id: string | null;
  thread: string;
  ord: number;
  src_span_start: number;              // the template's original span (audit)
  src_span_end: number;
  span_start: number;                  // rescaled into [1..target_chapters]
  span_end: number;
  role_hints: Record<string, unknown>;
  role_bindings: Record<string, unknown>;
  triggers: string[];
  merged_codes: string[];
};

/** One §12.6 reconciliation event — a motif lost to a scale-mismatch is NEVER silent. */
export type DropMergeEntry = {
  kind: 'dropped' | 'merged';
  motif_code: string;
  thread: string;
  src_span_start: number;
  src_span_end: number;
  into_motif_code: string | null;      // the survivor a merge folded into
  reason: string;
};

// ── materialize (D-W10-APPLY-PLANNER-MATERIALIZE — commit the arc onto a book) ──────
export type ArcMaterializeArgs = {
  arc_template_id: string;
  roster_bindings?: Record<string, unknown>;
  replace?: boolean;
  idempotency_key?: string;
};

/** The committed-outline report. `unresolved_placements` + `drop_merge_report` are
 *  surfaced so a lost motif (no visible match, or folded by a scale mismatch) is never
 *  silent (§12.6). */
export type ArcMaterializeResult = {
  arc_id: string;
  arc_template_id: string;
  chapter_ids: string[];
  scene_ids: string[];
  motif_applications: number;
  scenes_total: number;
  beats_distributed: number;
  unresolved_placements: { motif_code: string; thread: string; reason: string }[];
  drop_merge_report: DropMergeEntry[];
  replay: boolean;
};

export type ArcApplyPlan = {
  arc_template_id: string;
  source_chapter_span: number;
  target_chapters: number;
  threads: ArcThreadEntry[];
  placements: ResolvedPlacement[];
  roster_bindings: Record<string, unknown>;
  unbound_roster_keys: string[];       // roster slots with no binding supplied
  drop_merge_report: DropMergeEntry[];
  // per-chapter interleave: chapter_no (1-based, string key) → active placement ords.
  chapter_interleave: Record<string, number[]>;
};
