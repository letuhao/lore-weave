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

/** A motif is read-only to the caller unless the caller OWNS it. System +
 *  another user's public motif are clone-to-edit only (the kinds-bug lesson:
 *  a user never mutates a shared row, they clone-down). */
export function isReadOnly(
  motif: Pick<Motif, 'owner_user_id' | 'visibility'>,
  meUserId: string | null,
): boolean {
  return motifTier(motif, meUserId) !== 'user';
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
