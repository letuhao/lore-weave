// TMP-Q4 chunk B — value-band visualization helpers.
//
// Maps treasure pile `value` (u32, gold-equivalent) to a 5-band index.
// The bands are HoMM3-inspired: low / low-mid / mid / high / gilt. The
// backend ships per-book overrides via `RegistryRef.value_band_thresholds`
// (chunk A); when absent, this module's defaults apply.
//
// `pickValueBand` is the single source of truth for which color a pile
// gets. Both the object-overlay badge stamper AND the TileInspector
// swatch consume it, so a future palette tweak updates both surfaces.

/** TMP-Q4 — fallback band thresholds when the per-book registry doesn't
 *  declare its own. 4 strictly-ascending values produce 5 bands:
 *   value < 500       → band 0 (low      — slate-400)
 *   value < 2000      → band 1 (low-mid  — emerald-500)
 *   value < 5000      → band 2 (mid      — blue-500)
 *   value < 12000     → band 3 (high     — purple-500)
 *   value ≥ 12000     → band 4 (gilt     — amber-400)
 */
export const VALUE_BAND_DEFAULTS = [500, 2000, 5000, 12000] as const;

/** TMP-Q4 — 5 colors aligned with Tailwind palette for in-app consistency. */
export const BAND_COLORS = [
  0x9ca3af, // slate-400
  0x10b981, // emerald-500
  0x3b82f6, // blue-500
  0xa855f7, // purple-500
  0xfbbf24, // amber-400
] as const;

/** Human-readable band names for the inspector. */
export const BAND_LABELS = ['low', 'low-mid', 'mid', 'high', 'gilt'] as const;

/**
 * Pick a 0..4 band index for a treasure pile value.
 *
 * **LOW-6 defensive (chunk-A /review-impl)** — TS tuple types don't
 * enforce strictly-ascending at runtime. The backend validates at
 * `Registry::from_file`, but unit-test stubs or buggy backend builds
 * could still ship invalid arrays. This helper:
 *   1. Coerces NaN / non-finite thresholds to the default scale.
 *   2. Sorts the threshold array ascending locally so non-ascending
 *      input still produces a deterministic band assignment.
 *   3. Clamps the input value to a finite non-negative integer.
 *
 * Threshold semantic: `value < thresholds[i]` ⇒ band `i`. So a pile
 * value EXACTLY equal to a threshold lands in the HIGHER band (e.g.,
 * value 500 with default thresholds ⇒ band 1, not 0).
 */
export function pickValueBand(
  value: number,
  thresholds?: readonly [number, number, number, number] | null,
): number {
  const safeValue = Number.isFinite(value) ? Math.max(0, Math.floor(value)) : 0;
  const raw: number[] =
    thresholds && thresholds.every((t) => Number.isFinite(t) && t >= 0)
      ? [thresholds[0], thresholds[1], thresholds[2], thresholds[3]]
      : [
          VALUE_BAND_DEFAULTS[0],
          VALUE_BAND_DEFAULTS[1],
          VALUE_BAND_DEFAULTS[2],
          VALUE_BAND_DEFAULTS[3],
        ];
  raw.sort((a, b) => a - b);
  for (let i = 0; i < 4; i++) {
    // The non-null assertion is safe: `raw` is constructed with exactly
    // 4 elements above, sort doesn't shrink it, and the loop bound is 4.
    if (safeValue < raw[i]!) return i;
  }
  return 4;
}

/** Returns BAND_LABELS[clamp(band, 0, 4)]. Never throws / undefined. */
export function bandLabel(band: number): (typeof BAND_LABELS)[number] {
  const i = Number.isFinite(band) ? Math.max(0, Math.min(4, Math.floor(band))) : 0;
  // Non-null assertion: i is clamped to [0, 4], BAND_LABELS has 5 entries.
  return BAND_LABELS[i]!;
}

/** Returns BAND_COLORS[clamp(band, 0, 4)]. Never throws / undefined. */
export function bandColor(band: number): number {
  const i = Number.isFinite(band) ? Math.max(0, Math.min(4, Math.floor(band))) : 0;
  // Non-null assertion: i is clamped to [0, 4], BAND_COLORS has 5 entries.
  return BAND_COLORS[i]!;
}

/**
 * Minimal subset of `TilemapObjectPlacement` that the badge-stamp gate
 * needs. Typed as a structural interface so tests can pass partial
 * fixtures without importing the full wire-shape type.
 */
export interface BadgeEligible {
  kind?: string;
  primitive?: string;
  value?: number | null;
}

/**
 * TMP-Q4 chunk B + LOW-5 (chunk-B /review-impl) — the value-band badge
 * gate. Both `object-overlay.ts` (canvas) and any future inspector-side
 * code that needs to know whether a placement is band-eligible MUST
 * route through this predicate so the V1→V2 migration doesn't silently
 * leave the badge dark.
 *
 * Dual-gate (V1+V2): treasure piles ride on the wire as either
 *   - V1: `kind === 'treasure'`
 *   - V2: `primitive === 'pickup'` (per data-model-v2-registry-footprint ADR)
 * MonsterLair guards inherit `tier_index` but their `value` is strength
 * not gold, so they MUST NOT badge (MED-1 from chunk-B self-review).
 * A finite `value` (including 0 — a degenerate-tier pile is still
 * technically a pile, LOW-6) is required so the renderer has something
 * to map to a band.
 */
export function shouldStampBadge(p: BadgeEligible): boolean {
  const isTreasure = p.kind === 'treasure' || p.primitive === 'pickup';
  if (!isTreasure) return false;
  if (p.value == null) return false;
  if (!Number.isFinite(p.value)) return false;
  return true;
}
