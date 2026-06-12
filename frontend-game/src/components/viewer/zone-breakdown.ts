// TMP-Q4 chunk C — pure helpers for the zone-tier overlay rendering
// AND the MetadataPanel "treasure breakdown" table. Both surfaces share
// the same zone-of-placement attribution + per-zone aggregation, so a
// regression in one surface cannot drift away from the other (MED-1
// from chunk-C self-review; same single-source-of-truth pattern as
// chunk-B's `shouldStampBadge`).

import {
  bandColor,
  bandLabel,
  pickValueBand,
  shouldStampBadge,
} from '@/game/render/treasure-badge';
import type {
  TileMask,
  TilemapObjectPlacement,
  TilemapView,
  ZoneRuntime,
} from '@/types/tilemap';

/**
 * Per-zone aggregate row consumed by both the MetadataPanel table and
 * the zone-tier canvas overlay color picker.
 *
 * `band` is derived from the zone's HIGHEST tier-0 pile value (the
 * "spotlight" pile that determines the zone's max-tier color), via
 * `pickValueBand(maxTier0Value, view.registry_ref?.value_band_thresholds)`.
 * Zones with no tier-0 piles fall back to the highest-value pile of any
 * tier; zones with no piles at all are omitted from the breakdown
 * entirely (LOW-1 fix).
 */
export interface ZoneBreakdownRow {
  zone_id: string;
  zone_role: string;
  pile_count: number;
  total_value: number;
  /** Color picker input: the value used to compute the band. */
  spotlight_value: number;
  /** 0..4 (low / low-mid / mid / high / gilt). */
  band: number;
  /** Hex color via `bandColor(band)`. Helper field so the MetadataPanel
   *  row + the overlay-rt fill share one source. */
  color: number;
  /** Human-readable band name. */
  band_name: string;
}

/**
 * MED-1 fix — authoritative "which zone owns this placement?" routes
 * through one function. Both the canvas overlay AND the panel
 * breakdown call this so a boundary placement can't be counted under
 * one zone but visually painted under another.
 *
 * Preference order:
 *   1. `assigned_tiles` bitmap lookup (backend's authoritative
 *      assignment).
 *   2. Voronoi `nearestZoneOf` fallback when the zone's
 *      `assigned_tiles` is undefined (pre-V1.2 fixture, parse
 *      failure, or sparse test view).
 *
 * Returns the zone's INDEX in `zones` (not its `zone_id`) so callers
 * can pass it directly to bitmap-array indexing if desired. Returns
 * `-1` when no zone owns the anchor (extremely rare; only when ALL
 * zones lack `assigned_tiles` AND `zones` is empty).
 */
export function zoneIndexOfPlacement(
  anchor: { x: number; y: number },
  zones: ReadonlyArray<ZoneRuntime>,
): number {
  if (zones.length === 0) return -1;
  // First pass — authoritative bitmap check.
  for (let i = 0; i < zones.length; i++) {
    const at = zones[i]!.assigned_tiles;
    if (at && tileMaskGet(at, anchor.x, anchor.y)) {
      return i;
    }
  }
  // Second pass — Voronoi fallback (used when no zone's bitmap claims
  // the tile, OR when all zones lack a bitmap). Compute on every call;
  // viewer-store assignment is one-shot per inspector open, and the
  // chunk-C overlay build is once per tilemap load, so the per-placement
  // cost is dwarfed by Phaser's per-fillRect overhead.
  let bestIdx = 0;
  let bestDist = Infinity;
  for (let i = 0; i < zones.length; i++) {
    const z = zones[i]!;
    const dx = z.center_position.x - anchor.x;
    const dy = z.center_position.y - anchor.y;
    const d = dx * dx + dy * dy;
    if (d < bestDist) {
      bestDist = d;
      bestIdx = i;
    }
  }
  return bestIdx;
}

/**
 * MED-1 — TileMask bit read. The backend's tilemask uses
 * `bits[y * width + x bit-index / 64]` with the bit at
 * `(y * width + x) % 64`. Returns `false` for out-of-bounds reads
 * (defensive — a registry / template authoring error should not
 * crash the inspector).
 */
export function tileMaskGet(mask: TileMask, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= mask.width || y >= mask.height) return false;
  const flat = y * mask.width + x;
  const wordIdx = Math.floor(flat / 64);
  const bitIdx = flat % 64;
  const word = mask.bits[wordIdx];
  if (word === undefined) return false;
  return (word & (1n << BigInt(bitIdx))) !== 0n;
}

/**
 * Compute the per-zone breakdown rows for the current TilemapView.
 *
 * Empty zones (no treasure piles attributed) are OMITTED (LOW-1).
 * Rows are sorted by `total_value` DESC with `zone_id` ASC as the
 * deterministic tiebreaker.
 *
 * Per-book `value_band_thresholds` (chunk A) override the default
 * scale; when absent, fall back to `VALUE_BAND_DEFAULTS`.
 */
export function computeZoneBreakdown(view: TilemapView): ZoneBreakdownRow[] {
  const thresholds = view.registry_ref?.value_band_thresholds ?? null;

  // Bucket treasure piles by zone via the shared attribution
  // (MED-1: same path as the canvas overlay).
  const piles_by_zone = new Map<number, TilemapObjectPlacement[]>();
  for (const p of view.object_placements ?? []) {
    if (!shouldStampBadge(p)) continue;
    const idx = zoneIndexOfPlacement(p.anchor, view.zones);
    if (idx < 0) continue;
    let bucket = piles_by_zone.get(idx);
    if (!bucket) {
      bucket = [];
      piles_by_zone.set(idx, bucket);
    }
    bucket.push(p);
  }

  const rows: ZoneBreakdownRow[] = [];
  for (const [idx, piles] of piles_by_zone) {
    const zone = view.zones[idx];
    if (!zone) continue; // defensive (zoneIndexOfPlacement returned valid idx)
    // Spotlight value: prefer the highest value among tier-0 piles
    // (the zone's highest band per chunk-A semantic); fall back to
    // the absolute max value when no pile has tier_index=0 (e.g.,
    // when the wire was produced by a pre-Q4 backend).
    let max_tier_0 = -1;
    let max_any = -1;
    let total = 0;
    for (const p of piles) {
      const v = p.value ?? 0;
      total += v;
      if (v > max_any) max_any = v;
      if (p.tier_index === 0 && v > max_tier_0) max_tier_0 = v;
    }
    const spotlight_value = max_tier_0 >= 0 ? max_tier_0 : max_any;
    const band = pickValueBand(spotlight_value, thresholds);
    rows.push({
      zone_id: zone.zone_id,
      zone_role: zone.zone_role,
      pile_count: piles.length,
      total_value: total,
      spotlight_value,
      band,
      color: bandColor(band),
      band_name: bandLabel(band),
    });
  }

  // Sort: total_value DESC, zone_id ASC tiebreaker.
  rows.sort((a, b) => {
    if (b.total_value !== a.total_value) return b.total_value - a.total_value;
    return a.zone_id.localeCompare(b.zone_id);
  });

  return rows;
}
