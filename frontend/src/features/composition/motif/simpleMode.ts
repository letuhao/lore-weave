// Narrative Motif Library (W6) — §6 simple-mode label registries + tenancy-tier
// derivation. ALL pure + testable (no React, no i18n). The beginner persona never
// sees Greimas/Propp jargon (§6); simple is the FE default for a first-run user.
//
// NOTE: these maps return the i18n KEY (not English). Components pass the key
// through `t()` so the strings are translatable + the test convention (assert on
// keys) holds. The English copy lives in composition.json under `motif.*`.

import type { Actant, MotifKind, Motif, MotifTier } from './types';

// ── tenancy tier derivation (§3.4) — the FE grouping, NOT a wire field ────────

/** Derive the presentation tier from {owner_user_id, visibility} relative to the
 *  viewing user. System = ownerless. User = the caller owns it. Public = a row
 *  the caller can see that someone ELSE owns (visibility public/unlisted). */
export function motifTier(
  motif: Pick<Motif, 'owner_user_id' | 'visibility'>,
  meUserId: string | null,
): MotifTier {
  if (motif.owner_user_id == null) return 'system';
  if (meUserId != null && motif.owner_user_id === meUserId) return 'user';
  return 'public';
}

/** A motif is read-only to the caller unless the caller OWNS it — OR it is a book's SHARED tier
 *  row, which every EDIT-grantee of that book may edit (D-MOTIF-ADOPT-BOOK-COLLAB-TIER).
 *
 *  System and another user's PUBLIC motif stay clone-to-edit: that is the kinds-bug lesson, and
 *  it still holds — a user never mutates a *global* row. But the lesson was being applied one
 *  tier too wide. The LOCKED tenancy table says the per-book tier is writable by the owner AND
 *  its grantees, and the backend has implemented exactly that (`PATCH ?book_id=` → `patch_shared`,
 *  EDIT-gated on the book) since the collab tier shipped. The FE simply had no way to SEE it:
 *  the B-3 redaction nulls `owner_user_id` on a foreign row, `motifTier` derives the tier from
 *  precisely that field, so every shared row came back looking like `system` — the capability was
 *  built on one side and invisible on the other (F3, 2026-07-28).
 *
 *  `book_shared` is the signal to use because it survives the redaction; `owner_user_id` does not.
 *  Whether the caller actually holds EDIT is the SERVER's call, not a guess made here. */
export function isReadOnly(
  motif: Pick<Motif, 'owner_user_id' | 'visibility' | 'book_shared'>,
  meUserId: string | null,
): boolean {
  if (motif.book_shared) return false;
  return motifTier(motif, meUserId) !== 'user';
}

/** Fields a NON-OWNER never receives (the server's `_PUBLIC_DETAIL_REDACT`) and therefore must
 *  never send back. A redacted read hands them over as `[]`, indistinguishable from genuinely
 *  empty, so echoing the whole object would wipe content the caller was not even allowed to see.
 *  The server refuses such a write (400 MOTIF_REDACTED_FIELD_NOT_WRITABLE) — this keeps a legal
 *  edit from tripping that refusal for a field the user never touched. */
export const REDACTED_FIELDS = ['examples'] as const;

/** True when this row reached us REDACTED — i.e. it is shared into a book by someone else.
 *  Keyed on the redaction's own tell (`owner_user_id` nulled) rather than on a user-id compare,
 *  because that is exactly the state the payload is in. */
export function isRedactedForViewer(
  motif: Pick<Motif, 'owner_user_id' | 'book_shared'>,
): boolean {
  return !!motif.book_shared && motif.owner_user_id == null;
}

// ── simple ↔ expert label registries (§6.1) — return i18n keys ────────────────

const ACTANT_SIMPLE: Record<Actant, string> = {
  subject: 'motif.simple.actant.subject',
  sender: 'motif.simple.actant.sender',
  object: 'motif.simple.actant.object',
  receiver: 'motif.simple.actant.receiver',
  helper: 'motif.simple.actant.helper',
  opponent: 'motif.simple.actant.opponent',
};

const ACTANT_EXPERT: Record<Actant, string> = {
  subject: 'motif.expert.actant.subject',
  sender: 'motif.expert.actant.sender',
  object: 'motif.expert.actant.object',
  receiver: 'motif.expert.actant.receiver',
  helper: 'motif.expert.actant.helper',
  opponent: 'motif.expert.actant.opponent',
};

const KIND_SIMPLE: Record<MotifKind, string> = {
  sequence: 'motif.simple.kind.sequence',
  situation: 'motif.simple.kind.situation',
  hook: 'motif.simple.kind.hook',
  emotion_arc: 'motif.simple.kind.emotion_arc',
  trope: 'motif.simple.kind.trope',
  pattern: 'motif.simple.kind.pattern',
  scheme: 'motif.simple.kind.scheme',
};

const KIND_EXPERT: Record<MotifKind, string> = {
  sequence: 'motif.expert.kind.sequence',
  situation: 'motif.expert.kind.situation',
  hook: 'motif.expert.kind.hook',
  emotion_arc: 'motif.expert.kind.emotion_arc',
  trope: 'motif.expert.kind.trope',
  pattern: 'motif.expert.kind.pattern',
  scheme: 'motif.expert.kind.scheme',
};

/** The i18n key for an actant label, registry chosen by mode. */
export function actantLabelKey(actant: Actant, simple: boolean): string {
  return (simple ? ACTANT_SIMPLE : ACTANT_EXPERT)[actant];
}

/** The i18n key for a kind label, registry chosen by mode. */
export function kindLabelKey(kind: MotifKind, simple: boolean): string {
  return (simple ? KIND_SIMPLE : KIND_EXPERT)[kind];
}

/** Field-label keys that differ between modes (§6.1). */
export function fieldLabelKey(
  field: 'tension_target' | 'preconditions' | 'effects' | 'info_asymmetry',
  simple: boolean,
): string {
  return `motif.${simple ? 'simple' : 'expert'}.field.${field}`;
}

/** The i18n key for the tier chip word (always paired with hue — §5.3 co-encode). */
export function tierLabelKey(tier: MotifTier): string {
  return `motif.tier.${tier}`;
}

// ── conformance flag → glyph + key (§5.3 — glyph + word + hue, never hue alone) ─

export type ConformanceTone = 'ok' | 'warn' | 'bad';

export function conformanceGlyph(tone: ConformanceTone): string {
  return tone === 'ok' ? '✓' : tone === 'warn' ? '⚠' : '✗';
}

/** Classify a scene's conformance into a tone for the glyph+word+hue triple. */
export function conformanceTone(beatRealized: boolean, tensionMatch: boolean): ConformanceTone {
  if (beatRealized && tensionMatch) return 'ok';
  if (!beatRealized) return 'bad';
  return 'warn';
}
