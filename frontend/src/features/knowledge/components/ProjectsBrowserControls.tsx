import { Search } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import {
  PROJECT_SORTS,
  PROJECT_STATE_FILTERS,
  type ProjectSort,
  type ProjectStateFilter,
} from '../lib/projectBrowser';

// C7 (G6) — search / sort / filter-by-state controls for the projects
// HOME browser. Pure view: all state lives in ProjectsTab; every change
// is an explicit onChange handler (CLAUDE.md FE rule — no
// useEffect-for-events). The narrowing itself is `narrowProjects` in
// lib/projectBrowser.ts.

interface Props {
  search: string;
  onSearchChange: (v: string) => void;
  sort: ProjectSort;
  onSortChange: (v: ProjectSort) => void;
  stateFilter: ProjectStateFilter;
  onStateFilterChange: (v: ProjectStateFilter) => void;
}

export function ProjectsBrowserControls({
  search,
  onSearchChange,
  sort,
  onSortChange,
  stateFilter,
  onStateFilterChange,
}: Props) {
  const { t } = useTranslation('knowledge');
  return (
    <div className="mb-4 flex flex-wrap items-center gap-2">
      <div className="relative min-w-[180px] flex-1">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="search"
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder={t('projects.browser.searchPlaceholder')}
          aria-label={t('projects.browser.searchLabel')}
          data-testid="projects-search"
          className="w-full rounded-md border bg-input py-1.5 pl-8 pr-2.5 text-xs outline-none focus:border-ring"
        />
      </div>

      <select
        value={stateFilter}
        onChange={(e) => onStateFilterChange(e.target.value as ProjectStateFilter)}
        aria-label={t('projects.browser.filterLabel')}
        data-testid="projects-state-filter"
        className="rounded-md border bg-input px-2.5 py-1.5 text-xs outline-none focus:border-ring"
      >
        {PROJECT_STATE_FILTERS.map((f) => (
          <option key={f} value={f}>
            {t(`projects.browser.stateFilter.${f}`)}
          </option>
        ))}
      </select>

      <select
        value={sort}
        onChange={(e) => onSortChange(e.target.value as ProjectSort)}
        aria-label={t('projects.browser.sortLabel')}
        data-testid="projects-sort"
        className="rounded-md border bg-input px-2.5 py-1.5 text-xs outline-none focus:border-ring"
      >
        {PROJECT_SORTS.map((s) => (
          <option key={s} value={s}>
            {t(`projects.browser.sortOption.${s}`)}
          </option>
        ))}
      </select>
    </div>
  );
}
