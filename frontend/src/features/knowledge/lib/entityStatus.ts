import type { Entity, EntityStatus } from '../api';
import { ENTITY_STATUSES } from '../api';

// C8 — entity semantic-layer status presentation. Pure helpers shared
// by EntitiesTable (per-row glyph + anchor badge) and EntitiesTab (the
// legend). Keeping the glyph map + derivation here (not inline JSX)
// keeps the precedence in ONE place and makes it unit-testable.

/** Glyph per derived status. ⭐ canonical · 💭 discovered · 📦 archived. */
export const STATUS_GLYPH: Record<EntityStatus, string> = {
  canonical: '⭐',
  discovered: '💭',
  archived: '📦',
};

/** Re-derive status FE-side as a fallback for rollout-window responses
 *  that predate the BE computed field. Mirrors the BE `Entity.status`
 *  precedence EXACTLY: archived > canonical > discovered. The BE value
 *  is authoritative when present; this only fills a missing field. */
export function deriveEntityStatus(e: Pick<Entity, 'archived_at' | 'glossary_entity_id'>): EntityStatus {
  if (e.archived_at != null) return 'archived';
  if (e.glossary_entity_id != null) return 'canonical';
  return 'discovered';
}

/** The status for an entity — BE-provided if present, else derived. */
export function entityStatus(e: Entity): EntityStatus {
  return e.status ?? deriveEntityStatus(e);
}

export function statusGlyph(e: Entity): string {
  return STATUS_GLYPH[entityStatus(e)];
}

/** The 3 statuses in legend display order (canonical first). */
export const STATUS_LEGEND_ORDER = ENTITY_STATUSES;

/** Anchor score → 0..100 integer for the badge. Clamped defensively. */
export function anchorPercent(anchorScore: number): number {
  if (!Number.isFinite(anchorScore)) return 0;
  return Math.max(0, Math.min(100, Math.round(anchorScore * 100)));
}
