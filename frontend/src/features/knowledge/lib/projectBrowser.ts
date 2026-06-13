import type { ExtractionStatus, Project } from '../types';

// C7 (G6) — client-side search / sort / filter-by-state for the projects
// HOME browser. The BE list endpoint paginates by cursor but has no
// search/sort/status params (see api.ts ProjectListParams), so the
// browser narrows over the rows already loaded into `useProjects`. Pure
// functions here so ProjectsTab stays a thin view and the narrowing is
// unit-testable in isolation.

export type ProjectSort = 'name_asc' | 'name_desc' | 'recent' | 'oldest';

// A "state" filter maps to the project's derived extraction status plus
// the archived flag. `all` = no narrowing. `archived` is its own bucket
// (archived rows only appear when the caller loaded them via
// include_archived; this filter then isolates them).
export type ProjectStateFilter = 'all' | ExtractionStatus | 'archived';

export const PROJECT_SORTS: ProjectSort[] = [
  'name_asc',
  'name_desc',
  'recent',
  'oldest',
];

export const PROJECT_STATE_FILTERS: ProjectStateFilter[] = [
  'all',
  'disabled',
  'building',
  'paused',
  'ready',
  'failed',
  'archived',
];

function matchesState(p: Project, filter: ProjectStateFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'archived') return p.is_archived;
  // A non-archived row's bucket is its extraction_status. Archived rows
  // are excluded from the status buckets so "ready" etc. mean "live and
  // ready", not "ready but archived".
  return !p.is_archived && p.extraction_status === filter;
}

function compare(a: Project, b: Project, sort: ProjectSort): number {
  switch (sort) {
    case 'name_asc':
      return a.name.localeCompare(b.name);
    case 'name_desc':
      return b.name.localeCompare(a.name);
    case 'recent':
      // Most-recently-updated first. ISO-8601 strings sort lexically.
      return b.updated_at.localeCompare(a.updated_at);
    case 'oldest':
      return a.updated_at.localeCompare(b.updated_at);
    default:
      return 0;
  }
}

/**
 * Narrow + order the loaded project rows. `search` is a case-insensitive
 * substring over the project name (and book_id for power users pasting a
 * UUID). Returns a NEW array (does not mutate input).
 */
export function narrowProjects(
  projects: readonly Project[],
  opts: { search: string; sort: ProjectSort; stateFilter: ProjectStateFilter },
): Project[] {
  const q = opts.search.trim().toLowerCase();
  const filtered = projects.filter((p) => {
    if (!matchesState(p, opts.stateFilter)) return false;
    if (!q) return true;
    return (
      p.name.toLowerCase().includes(q) ||
      (p.book_id ?? '').toLowerCase().includes(q)
    );
  });
  // Slice before sort so we never mutate the source array reference.
  return filtered.slice().sort((a, b) => compare(a, b, opts.sort));
}
