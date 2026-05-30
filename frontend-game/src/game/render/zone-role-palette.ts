// TMP-Q5 chunk B — pure helpers for zone-role color attribution.
//
// `zoneRoleColor` is the single source of truth for "what color is
// this role?". Both the canvas overlay tint AND the MetadataPanel
// breakdown swatch consume it so a future palette tweak / per-book
// override updates both surfaces simultaneously.
//
// Per-book overrides ride the wire via chunk-A's
// `RegistryRef.zone_role_colors` and flow through this helper.

import type { ZoneRoleColors } from '@/types/tilemap';

/** TMP-Q5 — fallback role palette when the registry omits an override.
 *
 *  Aligned with the existing `ZONE_CENTER_COLORS` in `overlay-rt.ts`
 *  (Tailwind emerald-400 / indigo-400 / rose-400 / blue-400) so the
 *  centre marker dot + the zone-role tint use the SAME hue per role.
 *  A per-book override (chunk A wire shape) replaces one or more
 *  fields here; sparse overrides honored.
 */
export const ZONE_ROLE_DEFAULTS: Readonly<Record<string, number>> = {
  wilderness: 0x4ade80,
  hub:        0x818cf8,
  forbidden:  0xf87171,
  sea:        0x60a5fa,
};

/** TMP-Q5 — neutral fallback for unknown roles.
 *
 *  The FE `ZoneRole` type allows 8 variants (wilderness/hub/forbidden/
 *  sea + capital/arena/mine_camp/town) but the backend wire only
 *  ships the first 4. When a wider FE type lands or a future BE adds
 *  variants, this fallback keeps the overlay from rendering
 *  `undefined` (which crashes Phaser's fillStyle). slate-400 reads
 *  as "unclassified" without competing with the named roles.
 */
export const ZONE_ROLE_FALLBACK = 0x9ca3af;

/**
 * Pick the color for a zone role.
 *
 * Resolution order:
 *   1. `override?.[role]` — per-book registry override if SET (not
 *      undefined). LOW-1 from chunk-B self-review: explicit
 *      Number.isFinite check so a future malformed override that
 *      shipped a non-number doesn't poison the rendered color.
 *   2. `ZONE_ROLE_DEFAULTS[role]` — built-in default if role is
 *      known to the FE.
 *   3. `ZONE_ROLE_FALLBACK` — neutral gray for unknown roles.
 *
 * `override` is typed `ZoneRoleColors | null | undefined`:
 *   - `undefined` (no override declared) → defaults
 *   - `null` (explicit no-override) → defaults
 *   - `{}` (Some-empty wire from chunk A LOW-1 quirk) → defaults
 *   - `{wilderness: 0xff0000}` (sparse) → use override for
 *     wilderness, defaults for hub/forbidden/sea
 */
export function zoneRoleColor(
  role: string,
  override?: ZoneRoleColors | null,
): number {
  // Index by role string into the override struct. Since
  // `ZoneRoleColors` is a typed shape with named fields, we cast for
  // the dynamic lookup. Each field is `number | undefined` so the
  // Number.isFinite check defends against future shape drift.
  const overrideValue = override
    ? (override as unknown as Record<string, number | undefined>)[role]
    : undefined;
  if (overrideValue !== undefined && Number.isFinite(overrideValue)) {
    return overrideValue;
  }
  const defaultValue = ZONE_ROLE_DEFAULTS[role];
  if (defaultValue !== undefined) {
    return defaultValue;
  }
  return ZONE_ROLE_FALLBACK;
}

/**
 * V1 ships the raw role string as the panel label. Future
 * localization or pretty-printing (`Sea (singleton)` etc.) lands
 * here without an API churn.
 */
export function zoneRoleLabel(role: string): string {
  return role;
}
