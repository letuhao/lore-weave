// EC-3c / EC-3d — the ONE place that answers "which Work does this book resolve to?".
//
// Before this, ~13 sites open-coded `candidates[0]` as "the canonical Work". That is
// wrong in two ways that were dormant only because the Studio could not create a
// derivative (this wave arms it):
//   • `candidates[0]` is canonical only by LUCK — resolve_by_book is ORDER BY
//     created_at and a derive requires a pre-existing source, so the source sorts
//     first TODAY. The predicate is `source_work_id IS NULL`, not "index 0".
//   • `=== null` is a trap: Work.source_work_id is OPTIONAL in the FE type and absent
//     from most fixtures, so `w.source_work_id === null` matches NOTHING for a pre-
//     derivative book. Use a nullish test (`!w.source_work_id`).
//
// DoD is a hygiene grep, not a count: `candidates[0]` (Work-resolution) must appear
// nowhere outside tests.
import type { Work, WorkResolution } from './types';

/** The canonical (non-derivative) Work: the one with no source. */
export function selectCanonicalWork(candidates: Work[]): Work | null {
  return candidates.find((w) => !w.source_work_id) ?? null;
}

/** The derivative (dị bản) Works: every candidate that branches from a source. */
export function selectDerivatives(candidates: Work[]): Work[] {
  return candidates.filter((w) => w.source_work_id);
}

/**
 * EC-3d — the Work the user is ACTIVELY editing, given a resolution + the per-user,
 * per-book active-work preference (`activeWorkProjectId`, a durable server pref; see
 * useActiveWorkId). Falls back to canonical when the pref is unset OR when its target
 * no longer resolves (the derivative was archived, or a stale/foreign pref) — so a
 * dropped pref degrades to canon, never to null.
 *
 * This is the FALLBACK-aware resolver the panels call; `selectCanonicalWork` is only
 * the fallback. A panel that called `selectCanonicalWork` directly would re-resolve
 * straight back to canon after a "Switch to", defeating it (EC-3d).
 */
export function resolveActiveWork(
  resolution: WorkResolution | undefined,
  activeWorkProjectId: string | null | undefined,
): Work | null {
  if (!resolution) return null;
  if (resolution.status === 'found') return resolution.work;
  if (resolution.status !== 'candidates') return null;
  const candidates = resolution.candidates ?? [];
  if (activeWorkProjectId) {
    const active = candidates.find((w) => w.project_id === activeWorkProjectId);
    if (active) return active;
  }
  return selectCanonicalWork(candidates);
}
