// TMP-Q5 chunk B — pure helper for the MetadataPanel zone-role
// breakdown table AND the canvas overlay color-per-zone lookup.
//
// Shared `zoneIndexOfPlacement` + `zoneRoleColor` so the canvas tint,
// the panel swatch, and the inspector all agree per zone.

import {
  ZONE_ROLE_FALLBACK,
  zoneRoleColor,
  zoneRoleLabel,
} from '@/game/render/zone-role-palette';
import type { TilemapView } from '@/types/tilemap';

/**
 * Per-role aggregate row consumed by the MetadataPanel
 * `RoleBreakdown` section.
 *
 * `zone_ids` lists the zones bucketed under this role — useful for
 * future drill-down (click row → highlight matching zone centres
 * in the canvas). Sorted alphabetically for determinism.
 */
export interface ZoneRoleRow {
  role: string;
  count: number;
  color: number;
  label: string;
  zone_ids: string[];
}

/**
 * Compute per-role breakdown rows for the current TilemapView.
 *
 * Sort: `count` DESC with `role` ASC tiebreaker. Empty roles
 * (no zones in that role bucket) are naturally absent. Per-book
 * `RegistryRef.zone_role_colors` (chunk A) flows through
 * `zoneRoleColor` so the panel swatch matches the canvas overlay.
 */
export function computeRoleBreakdown(view: TilemapView): ZoneRoleRow[] {
  const override = view.registry_ref?.zone_role_colors ?? null;
  // Bucket by role.
  const buckets = new Map<string, string[]>();
  for (const zone of view.zones ?? []) {
    const role = zone.zone_role;
    let bucket = buckets.get(role);
    if (!bucket) {
      bucket = [];
      buckets.set(role, bucket);
    }
    bucket.push(zone.zone_id);
  }
  const rows: ZoneRoleRow[] = [];
  for (const [role, zone_ids] of buckets) {
    // Sort zone_ids for deterministic display + tooltip order.
    zone_ids.sort();
    rows.push({
      role,
      count: zone_ids.length,
      color: zoneRoleColor(role, override),
      label: zoneRoleLabel(role),
      zone_ids,
    });
  }
  // Sort: count DESC, role ASC tiebreaker (deterministic).
  rows.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.role.localeCompare(b.role);
  });
  return rows;
}

/** TMP-Q5 — re-export so callers don't need a second import for the
 *  unclassified-color sentinel. */
export { ZONE_ROLE_FALLBACK };
