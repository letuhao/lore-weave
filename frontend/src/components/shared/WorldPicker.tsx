import { useEffect, useMemo, useRef, useState } from 'react';
import { Search, X, Globe, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useAuth } from '@/auth';
import { worldsApi } from '@/features/world/api';
import type { World } from '@/features/world/types';

/**
 * W4 (G2) — reusable world picker, mirror of {@link BookPicker}. Emits a
 * `world_id`; an empty selection is VALID. Used by G3 cross-linking ("Add to
 * world") and anywhere a world is chosen by name rather than a UUID.
 *
 * Worlds load once (`worldsApi.listWorlds`) and filter client-side by name —
 * the list endpoint has no `search` param, so this is the same load-once shape
 * as BookPicker. `onCreateNew` (optional) adds an inline "＋ Create new world"
 * row; creation is delegated to the consumer (which owns the modal).
 */
interface Props {
  /** Selected world_id (UUID) or null. */
  value: string | null;
  onChange: (worldId: string | null) => void;
  disabled?: boolean;
  placeholder?: string;
  /** Cap on worlds fetched for the picker. */
  limit?: number;
  /** When set, renders an inline "create new" row that calls this. */
  onCreateNew?: () => void;
}

export function WorldPicker({ value, onChange, disabled, placeholder, limit = 200, onCreateNew }: Props) {
  const { accessToken } = useAuth();
  const [worlds, setWorlds] = useState<World[] | null>(null);
  const [fallback, setFallback] = useState<World | null>(null);
  const [error, setError] = useState(false);
  const [query, setQuery] = useState('');
  const [debounced, setDebounced] = useState('');
  const [open, setOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Load the user's worlds once.
  useEffect(() => {
    if (!accessToken) {
      setWorlds([]);
      return;
    }
    let cancelled = false;
    worldsApi
      .listWorlds(accessToken, { limit })
      .then((res) => {
        if (!cancelled) setWorlds(res.items);
      })
      .catch(() => {
        if (!cancelled) {
          setError(true);
          setWorlds([]);
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
    () => (value ? worlds?.find((w) => w.world_id === value) ?? null : null),
    [worlds, value],
  );

  // Resolve a selected-but-unlisted world by id so the chip shows a name.
  useEffect(() => {
    if (!value || !accessToken || selected || worlds === null) {
      setFallback(null);
      return;
    }
    let cancelled = false;
    worldsApi
      .getWorld(accessToken, value)
      .then((w) => {
        if (!cancelled) setFallback(w);
      })
      .catch(() => {
        if (!cancelled) setFallback(null);
      });
    return () => {
      cancelled = true;
    };
  }, [value, accessToken, selected, worlds]);

  const matches = useMemo(() => {
    const q = debounced.trim().toLowerCase();
    const list = worlds ?? [];
    if (!q) return list.slice(0, 50);
    return list.filter((w) => w.name.toLowerCase().includes(q)).slice(0, 50);
  }, [worlds, debounced]);

  function select(w: World) {
    onChange(w.world_id);
    setOpen(false);
    setQuery('');
  }
  function clear() {
    onChange(null);
    setQuery('');
  }

  if (value) {
    const label = selected?.name ?? fallback?.name;
    return (
      <div ref={rootRef} className="flex items-center gap-2 rounded-md border bg-input px-3 py-2 text-sm">
        <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
        <span className="flex-1 truncate" data-testid="world-picker-selected">
          {label ?? 'Selected world'}
        </span>
        {!disabled && (
          <button
            type="button"
            onClick={clear}
            aria-label="Clear selected world"
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
          aria-controls="world-picker-list"
          value={query}
          disabled={disabled || worlds === null}
          onChange={(e) => {
            setQuery(e.target.value);
            setOpen(true);
          }}
          onFocus={() => setOpen(true)}
          placeholder={placeholder ?? 'Search your worlds by name…'}
          className="flex-1 bg-transparent text-sm outline-none disabled:opacity-60"
        />
      </div>
      {open && worlds !== null && (
        <ul
          id="world-picker-list"
          role="listbox"
          className="absolute z-20 mt-1 max-h-56 w-full overflow-y-auto rounded-md border bg-card shadow-lg"
        >
          {matches.length === 0 ? (
            <li className="px-3 py-2 text-[11px] text-muted-foreground">
              {error
                ? 'Failed to load worlds.'
                : worlds.length === 0
                  ? 'No worlds yet.'
                  : 'No matching worlds.'}
            </li>
          ) : (
            matches.map((w) => (
              <li key={w.world_id} role="option" aria-selected={false}>
                <button
                  type="button"
                  onClick={() => select(w)}
                  className={cn(
                    'flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-card-foreground/[0.04]',
                  )}
                >
                  <Globe className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="flex-1 truncate">{w.name}</span>
                  <span className="text-[10px] text-muted-foreground">{w.book_count} bk</span>
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
                <span>Create new world</span>
              </button>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
