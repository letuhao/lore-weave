// TMP-Q6 chunk C — pure helper for the MetadataPanel decoration-family
// breakdown table.
//
// Backend's decoration_placer denormalizes `family` onto every
// `TilemapObjectPlacement` of `kind == 'decoration'` (chunk C),
// so this helper reads the field directly without registry lookup —
// matching the chunk-B [[builder-validation-parity]] discipline of
// "validate once, denormalize once, no per-call lookups".
//
// Filter by SEMANTIC property (`kind === 'decoration'`), not by
// incidental id-prefix, per [[completeness-gate-filter-by-semantic]].
// Unfamilied decoration placements (legacy pre-Q6 fixtures + the 2
// grandfathered TYPE-marker exempt entries) bucket as `'none'` so
// they remain VISIBLE in the breakdown rather than silently dropped.

import type { TilemapObjectPlacement, TilemapView } from '@/types/tilemap';

/**
 * Per-family aggregate row consumed by the MetadataPanel
 * `DecorationFamilyBreakdown` section.
 *
 * Sorted desc by `count` with `family` ASC tiebreaker (deterministic
 * display order matching {@link computeRoleBreakdown}'s convention).
 *
 * `percent` is rounded to 1 decimal place (display invariant) so the
 * shown values sum to ~100% absent floating-point edge cases.
 */
export interface DecorationFamilyRow {
  family: string;
  count: number;
  percent: number;
}

/** Sentinel for placements whose backend `family` was `None` / absent.
 *  Visible in the breakdown so authors notice unfamilied entries
 *  (legacy or TYPE-marker) rather than have them silently disappear.
 *
 *  MED-1 fix from chunk-C /review-impl: `'_unfamilied'` starts with
 *  underscore so it CANNOT collide with a real per-book family name —
 *  backend's `is_valid_family_id` regex `^[a-z][a-z0-9_]*$` requires the
 *  first char be `a-z`. If a per-book registry ever declared a family
 *  literally named `'none'`, the previous sentinel would have silently
 *  conflated it with truly-unfamilied placements. The leading
 *  underscore makes the sentinel structurally distinct. */
export const FAMILY_NONE = '_unfamilied';

/**
 * Single source of truth predicate: "this placement is a decoration".
 *
 * Used by BOTH the MetadataPanel "decorations N" counter AND the
 * `computeDecorationFamilyBreakdown` helper so the two surfaces can
 * never silently disagree on the population they count.
 *
 * The OR (primitive OR kind) is forward-compat for two cases:
 *   1. pre-V2 fixtures (no `primitive` field) — `kind` is the fallback
 *   2. future per-book registries declaring new kinds with
 *      `primitive: 'decoration'` semantics — `primitive` is the
 *      SoT for engine behavior
 *
 * Per [[extract-cross-surface-predicate]] memory — the chunk-C
 * /review-impl MED-1 fix that ALMOST landed a drift between the
 * counter (using OR) and the helper (using only kind).
 */
export function isDecorationPlacement(p: TilemapObjectPlacement): boolean {
  return p.primitive === 'decoration' || p.kind === 'decoration';
}

/**
 * Compute per-family breakdown rows for decoration placements in the
 * current TilemapView.
 *
 * Pure function: depends only on `view.object_placements` (filtering
 * by `kind === 'decoration'`). The `registry` parameter is accepted
 * for API parity with `computeRoleBreakdown(view)` and reserved for
 * a future enrichment (per-family color/label from
 * `registry.decoration_family_density`) — chunk-C v1 does not consult
 * it.
 *
 * Empty view ⇒ empty array.
 */
export function computeDecorationFamilyBreakdown(
  view: TilemapView,
  _registry: { decoration_family_density?: Record<string, number> } | null = null,
): DecorationFamilyRow[] {
  // Bucket by family. Filter by SEMANTIC kind via the shared
  // `isDecorationPlacement` predicate (MED-1 from chunk-C /review-impl)
  // so this surface never disagrees with the MetadataPanel
  // "decorations N" counter on which placements to count.
  const counts = new Map<string, number>();
  let total = 0;
  for (const p of view.object_placements ?? []) {
    if (!isDecorationPlacement(p)) continue;
    const family = p.family ?? FAMILY_NONE;
    counts.set(family, (counts.get(family) ?? 0) + 1);
    total += 1;
  }
  if (total === 0) return [];

  // Build rows + sort.
  const rows: DecorationFamilyRow[] = [];
  for (const [family, count] of counts) {
    const percent = Math.round((count / total) * 1000) / 10; // 1 decimal
    rows.push({ family, count, percent });
  }
  // Sort: count DESC, family ASC tiebreaker (deterministic display).
  rows.sort((a, b) => {
    if (b.count !== a.count) return b.count - a.count;
    return a.family.localeCompare(b.family);
  });
  return rows;
}
