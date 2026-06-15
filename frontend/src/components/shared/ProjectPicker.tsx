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
 * Active projects load once (`knowledgeApi.listProjects`, `include_archived:
 * false`) and filter client-side by name — the same load-once shape BookPicker
 * uses, scaling past a plain `<select>` because matches are filtered, not all
 * rendered. World-level projects are already hidden BE-side (W1: the HOME list
 * excludes `world_id IS NOT NULL`), so they never appear here.
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
    knowledgeApi
      .listProjects({ limit, include_archived: false }, accessToken)
      .then((res) => {
        if (!cancelled) setProjects(res.items);
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
  }, [accessToken, limit]);

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

  const selected = useMemo(
    () => (value ? projects?.find((p) => p.project_id === value) ?? null : null),
    [projects, value],
  );

  // Resolve a linked-but-unlisted project (archived) by id so the chip shows a
  // name, not a UUID. Only fires once the list has loaded and the value isn't
  // already in it.
  useEffect(() => {
    if (!value || !accessToken || selected || projects === null) {
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
  }, [value, accessToken, selected, projects]);

  const matches = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    const list = projects ?? [];
    if (!q) return list.slice(0, 50);
    return list.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 50);
  }, [projects, debounced]);

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

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-center gap-2 rounded-md border bg-input px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          type="text"
          role="combobox"
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
        </ul>
      )}
    </div>
  );
}
