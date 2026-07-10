import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Brain, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';
import type { Project } from '@/features/knowledge/types';

/**
 * Track B B1(2) — MULTI-select knowledge-project picker (the multi-KG grounding
 * set: world + member books unioned into one chat context). Sibling of the
 * single-select {@link ProjectPicker}; the two share the load-once + name-filter
 * shape but this one keeps a SET.
 *
 * Selection is rendered as removable chips; the search dropdown lists projects
 * NOT already chosen and adds on click. An empty set is VALID (falls back to the
 * legacy single-project / no-project path). Capped at {@link Props.max} (default
 * 16, mirroring knowledge-service's ContextBuildRequest cap) — the input is
 * disabled once the cap is reached.
 *
 * A linked-but-unlisted project (archived after linking) is resolved by id so
 * its chip shows a name, not a raw UUID — same affordance ProjectPicker has.
 */
interface Props {
  /** Selected project_ids (UUIDs). */
  value: string[];
  onChange: (projectIds: string[]) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Cap on projects fetched for the picker. MUST be ≤ 100: the route declares
   *  `Query(default=50, ge=1, le=100)`, so a larger value is a 422 and the picker
   *  lists NOTHING. It defaulted to 200 and had been silently empty. */
  limit?: number;
  /** Max projects selectable (multi-KG union cap). */
  max?: number;
  /** When set, renders an inline "create new" row that calls this. */
  onCreateNew?: () => void;
}

export function MultiProjectPicker({
  value,
  onChange,
  disabled,
  placeholder,
  limit = 100, // the route's own ceiling (le=100); 200 was a silent 422
  max = 16,
  onCreateNew,
}: Props) {
  const { accessToken } = useAuth();
  const [projects, setProjects] = useState<Project[] | null>(null);
  // id → name for any selected project not in the loaded active list (archived).
  const [fallbacks, setFallbacks] = useState<Record<string, string>>({});
  const [error, setError] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const atCap = value.length >= max;

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

  const byId = useMemo(() => {
    const m = new Map<string, Project>();
    for (const p of projects ?? []) m.set(p.project_id, p);
    return m;
  }, [projects]);

  // Resolve any selected id missing from the active list (archived) by id, so
  // its chip shows a name. Fires once the list has loaded.
  useEffect(() => {
    if (!accessToken || projects === null) return;
    const missing = value.filter((id) => !byId.has(id) && !(id in fallbacks));
    if (missing.length === 0) return;
    let cancelled = false;
    Promise.allSettled(missing.map((id) => knowledgeApi.getProject(id, accessToken))).then(
      (results) => {
        if (cancelled) return;
        const next: Record<string, string> = {};
        results.forEach((r, i) => {
          if (r.status === 'fulfilled' && r.value) next[missing[i]] = r.value.name;
        });
        if (Object.keys(next).length) setFallbacks((prev) => ({ ...prev, ...next }));
      },
    );
    return () => {
      cancelled = true;
    };
  }, [value, accessToken, projects, byId, fallbacks]);

  const matches = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    const selected = new Set(value);
    const list = (projects ?? []).filter((p) => !selected.has(p.project_id));
    if (!q) return list.slice(0, 50);
    return list.filter((p) => p.name.toLowerCase().includes(q)).slice(0, 50);
  }, [projects, debounced, value]);

  function add(p: Project) {
    if (value.includes(p.project_id) || atCap) return;
    onChange([...value, p.project_id]);
    setQuery('');
  }
  function remove(id: string) {
    onChange(value.filter((v) => v !== id));
  }

  function nameFor(id: string): string {
    return byId.get(id)?.name ?? fallbacks[id] ?? 'Linked project';
  }

  return (
    <div ref={rootRef} className="relative">
      {/* Selected chips */}
      {value.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5" data-testid="multi-project-chips">
          {value.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1 rounded-md border bg-secondary px-2 py-1 text-xs"
            >
              <Brain className="h-3 w-3 shrink-0 text-muted-foreground" />
              <span className="max-w-[160px] truncate">{nameFor(id)}</span>
              {!disabled && (
                <button
                  type="button"
                  onClick={() => remove(id)}
                  aria-label={`Remove ${nameFor(id)}`}
                  className="rounded-sm p-0.5 text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3 w-3" />
                </button>
              )}
            </span>
          ))}
        </div>
      )}

      <div className="flex items-center gap-2 rounded-md border bg-input px-3 py-2">
        <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <input
          type="text"
          role="combobox"
          data-testid="multi-project-input"
          aria-expanded={open}
          aria-controls="multi-project-list"
          value={query}
          disabled={disabled || projects === null || atCap}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={
            atCap
              ? `Max ${max} knowledge graphs selected`
              : placeholder ?? 'Add a knowledge graph by name…'
          }
          className="flex-1 bg-transparent text-sm outline-none disabled:opacity-60"
        />
      </div>
      {open && !atCap && projects !== null && (
        <ul
          id="multi-project-list"
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
                  onClick={() => add(p)}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-foreground/[0.04]',
                  )}
                >
                  <Plus className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
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
