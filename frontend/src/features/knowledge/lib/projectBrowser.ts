import type {
  ExtractionStatus,
  Project,
  ProjectSortBy,
  ProjectSortDir,
  ProjectStatusFilter,
} from '../types';

// C7 (G6) — search / sort / filter-by-state for the projects HOME
// browser. C7-followup (KN-7): the narrowing now runs SERVER-SIDE (the
// BE list endpoint takes search/sort/status), so `toServerParams` maps
// the UI's control state to the BE query params and `narrowProjects`
// stays only as a thin presentational safety net (the server is the
// source of truth for which rows the user sees).

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
 * C7-followup (KN-7): map the UI's control state to the BE list
 * endpoint's server-side narrowing params. The UI's combined
 * sort+direction token splits into `sort_by` + `sort_dir`; `recent` /
 * `oldest` order by `updated_at` (matching the prior client-side
 * `compare`). The state filter maps straight to the BE `status`
 * allowlist (`all` ⇒ no status param; `archived` + the five extraction
 * states pass through 1:1).
 */
export function toServerParams(opts: {
  search: string;
  sort: ProjectSort;
  stateFilter: ProjectStateFilter;
}): {
  search?: string;
  sort_by: ProjectSortBy;
  sort_dir: ProjectSortDir;
  status?: ProjectStatusFilter;
} {
  const sortMap: Record<ProjectSort, { sort_by: ProjectSortBy; sort_dir: ProjectSortDir }> = {
    name_asc: { sort_by: 'name', sort_dir: 'asc' },
    name_desc: { sort_by: 'name', sort_dir: 'desc' },
    recent: { sort_by: 'updated_at', sort_dir: 'desc' },
    oldest: { sort_by: 'updated_at', sort_dir: 'asc' },
  };
  const trimmed = opts.search.trim();
  return {
    search: trimmed || undefined,
    ...sortMap[opts.sort],
    status: opts.stateFilter === 'all' ? undefined : opts.stateFilter,
  };
}

/**
 * Narrow + order the loaded project rows. `search` is a case-insensitive
 * substring over the project name (and book_id for power users pasting a
 * UUID). Returns a NEW array (does not mutate input).
 *
 * C7-followup (KN-7): the SERVER now does the authoritative narrowing
 * (see `toServerParams`); this stays as a thin presentational fallback
 * so a brief window where loaded rows haven't refetched under a new
 * filter doesn't flash stale rows. It must NEVER widen past what the
 * server returned — it only filters/orders the already-returned set.
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
