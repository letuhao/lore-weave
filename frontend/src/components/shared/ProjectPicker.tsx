import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Brain, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';
import type { Project } from '@/features/knowledge/types';

/**
 * W4 (G2) — reusable knowledge-project picker, mirror of {@link BookPicker}.
 * Replaces the raw `<select>` of `project_id` (chat memory link, anywhere a
 * project is chosen): users pick BY NAME, never by a UUID dropdown. An empty
 * selection is VALID (no project linked).
 *
 * The name filter is the SERVER'S (`knowledgeApi.listProjects({ search })`,
 * `include_archived: false`), debounced and re-fetched. It used to be a
 * client-side `includes()` over one page: the call asks for `limit: 200` while
 * the route clamps to 100, so past 100 projects one simply could not be found
 * by typing its name — the same defect the library page shipped, one page
 * further in. World-level projects are already hidden BE-side (W1: the HOME
 * list excludes `world_id IS NOT NULL`), so they never appear here.
 *
 * A linked-but-unlisted project (e.g. one archived after it was linked) is
 * resolved by id (`getProject`) so the chip shows a name instead of a raw UUID
 * — preserving the archived-placeholder affordance the old `<select>` had.
 *
 * `onCreateNew` (optional) adds an inline "＋ Create new project" row; the
 * picker delegates creation to the consumer (which owns the modal) rather than
 * importing a feature modal into this shared component.
 */
interface Props {
  /** Selected project_id (UUID) or null. */
  value: string | null;
  onChange: (projectId: string | null) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Cap on projects fetched for the picker. */
  limit?: number;
  /** When set, renders an inline "create new" row that calls this. */
  onCreateNew?: () => void;
}

export function ProjectPicker({ value, onChange, disabled, placeholder, limit = 200, onCreateNew }: Props) {
  const { accessToken } = useAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [fallback, setFallback] = useState<Project | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Load the user's active projects once.
  useEffect(() => {
    if (!accessToken) {
      setProjects([]);
      return;
    }
    let cancelled = false;
    // THE NAME FILTER IS THE SERVER'S. It used to be a client-side `includes()`
    // over whatever this one call returned — and the call asks for `limit: 200`
    // while the route clamps to 100, so the picker narrowed 100 rows believing
    // it held every project. Below 101 projects that is invisible; above it, a
    // project simply cannot be found by typing its name and nothing says so.
    //
    // The `search` parameter has existed on `GET /v1/knowledge/projects` since
    // C7-followup, described in its own docstring as "server-side so the browser
    // narrows across ALL projects, not just loaded cursor pages", and the API
    // client already forwards it. Only this caller never sent it.
    knowledgeApi
      .listProjects(
        { limit, include_archived: false, ...(debounced.trim() ? { search: debounced.trim() } : {}) },
        accessToken,
      )
      .then((res) => {
        if (!cancelled) {
          setProjects(res.items);
          // This route is CURSOR-paginated and returns no `total`, so there is
          // no honest count of unshown matches. `next_cursor` is the one thing
          // it does say authoritatively: another page exists. Reporting that is
          // strictly better than the old inference — "the page came back full,
          // so there MAY be more" — which was also wrong in the other direction
          // whenever the last page happened to be exactly full.
          setHasMore(Boolean(res.next_cursor));
        }
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setProjects([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [accessToken, limit, debounced]);

  // Debounce the name filter.
  useEffect(() => {
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setDebounced(query), 180);
    return () => {
      if (timer.current) clearTimeout(timer.current);
    };
  }, [query]);

  // Close the dropdown on outside click.
  useEffect(() => {
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, []);

  // The selected project is REMEMBERED, not re-derived from the current page.
  // Deriving it worked only while this component held every project; now that
  // the list is a SEARCH RESULT, the chosen project is usually absent from it,
  // and re-deriving would blank the picker's own label the moment you typed —
  // and then fire the archived-project fallback fetch below on every keystroke.
  useEffect(() => {
    if (!value) {
      setSelectedProject(null);
      return;
    }
    const hit = projects?.find((p) => p.project_id === value);
    if (hit) setSelectedProject(hit);
  }, [projects, value]);
  const selected = selectedProject;

  // Resolve a linked-but-unlisted project (archived) by id so the chip shows a
  // name, not a UUID. Only fires once the list has loaded and the value isn't
  // already in it.
  // The guard reads the LOADED PAGE, not `selected`. `selected` is now set by
  // an effect, so for one render after the list arrives it is still null while
  // the project sits right there in `projects` — and gating on it fired a
  // getProject for a project the picker had already been handed. Harmless-
  // looking, but it is a request per load, and per keystroke once the list
  // became a search result.
  const valueInPage = projects?.some((p) => p.project_id === value) ?? false;
  useEffect(() => {
    if (!value || !accessToken || valueInPage || selected || projects === null) {
      setFallback(null);
      return;
    }
    let cancelled = false;
    knowledgeApi
      .getProject(value, accessToken)
      .then((p) => {
        if (!cancelled) setFallback(p);
      })
      .catch(() => {
        if (!cancelled) setFallback(null);
      });
    return () => {
      cancelled = true;
    };
  }, [value, accessToken, selected, projects, valueInPage]);

  // The server has already applied the name filter; this only caps the render.
  const matches = useMemo(() => (projects ?? []).slice(0, 50), [projects]);

  function select(p: Project) {
    onChange(p.project_id);
    setOpen(false);
    setQuery('');
  }
  function clear() {
    onChange(null);
    setQuery('');
  }

  // Selected: show the name + a clear affordance (internal branching, not
  // unmount — keeps the picker mounted).
  if (value) {
    const label = selected?.name ?? fallback?.name;
    return (
      <div ref={rootRef} className="flex items-center gap-2 rounded-md border bg-input px-3 py-2 text-sm">
        <Brain className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate" data-testid="project-picker-selected">
          {label ?? 'Linked project'}
        </span>
        {!disabled && (
          <button
            type="button"
            onClick={clear}
            aria-label="Clear selected project"
            className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
          >
            <X className="h-3.5 w-3.5" />
          </button>
        )}
      </div>
    );
  }

  // Kept rather than dropped once search moved server-side. The route clamps
  // `limit` to 100, so a search matching 140 still shows 100 — and a picker
  // that quietly lists 100 of 140 is indistinguishable from one whose user has
  // exactly 100 projects. `hasMore` comes from `next_cursor`, so it states a
  // fact the server reported instead of inferring one from the page size.

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-center gap-2 rounded-md border bg-input px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          type="text"
          role="combobox"
          data-testid="project-picker-input"
          aria-expanded={open}
          aria-controls="project-picker-list"
          value={query}
          disabled={disabled || projects === null}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? 'Search your projects by name…'}
          className="flex-1 bg-transparent text-sm outline-none disabled:opacity-60"
        />
      </div>
      {open && projects !== null && (
        <ul
          id="project-picker-list"
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-card shadow-lg"
        >
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-[11px] text-muted-foreground">
              {error
                ? 'Failed to load projects.'
                : projects.length === 0
                  ? 'No projects yet.'
                  : 'No matching projects.'}
            </li>
          ) : (
            matches.map((p) => (
              <li key={p.project_id} role="option" aria-selected={false}>
                <button
                  type="button"
                  onClick={() => select(p)}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-foreground/[0.04]',
                  )}
                >
                  <Brain className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{p.name}</span>
                </button>
              </li>
            ))
          )}
          {onCreateNew && (
            <li role="option" aria-selected={false} className="border-t">
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onCreateNew();
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm text-accent hover:bg-card-foreground/[0.04]"
              >
                <Plus className="h-3.5 w-3.5 shrink-0" />
                <span>Create new project</span>
              </button>
            </li>
          )}
          {hasMore && (
            <li
              className="border-t px-3 py-1.5 text-[10px] text-muted-foreground"
              data-testid="picker-page-full"
            >
              More matches exist than are shown — keep typing to narrow.
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
