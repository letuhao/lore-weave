// P1.2 (book-structure-pipeline spec §4.3) — the manuscript rail's "mode-by-content + toggle"
// decision. PURE + deterministic (unit-tested). This replaces the old `projectId ? 'outline' :
// 'chapters'` gate that hid a book's Parts whenever it had a Work (Bug 4).

export type ManuscriptLens = 'pending' | 'flat' | 'parts' | 'outline';

export interface StructureKinds {
  parts: boolean;
  outline: boolean;
}

/**
 * chooseManuscriptLens — what the manuscript rail renders, driven by the book's CONTENT:
 *   - parts only   → 'parts'   (grouped Part → chapters)
 *   - outline only → 'outline' (the arc→chapter→scene view — a planned book keeps it, no regression)
 *   - BOTH         → the user's `userLens` toggle, defaulting to 'parts'
 *   - neither      → 'flat'    (a plain chapter list; NO "Unassigned" banner)
 *   - kinds null   → 'pending' (structure not resolved yet)
 * `userLens` (the toggle choice) is honored ONLY when both kinds are present; ignored otherwise so a
 * stale toggle can never hide the single lens a book actually has.
 */
export function chooseManuscriptLens(
  kinds: StructureKinds | null,
  userLens: 'parts' | 'outline' | null,
): ManuscriptLens {
  if (kinds === null) return 'pending';
  if (kinds.parts && kinds.outline) return userLens === 'outline' ? 'outline' : 'parts';
  if (kinds.parts) return 'parts';
  if (kinds.outline) return 'outline';
  return 'flat';
}

/** Offer the [Parts | Outline] toggle ONLY when a book genuinely has both groupings. */
export function showLensToggle(kinds: StructureKinds | null): boolean {
  return !!kinds && kinds.parts && kinds.outline;
}
