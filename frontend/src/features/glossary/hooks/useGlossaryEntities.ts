import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/auth';
import { glossaryApi } from '../api';
import type { FilterState, GlossaryEntitySummary } from '../types';
import { defaultFilters } from '../types';

const LIMIT = 50;

type State = {
  entities: GlossaryEntitySummary[];
  total: number;
  isLoading: boolean;
  isLoadingMore: boolean;
  error: string;
  filters: FilterState;
  hasMore: boolean;
};

type Actions = {
  setFilters: (f: Partial<FilterState>) => void;
  loadMore: () => void;
  refresh: () => void;
  removeEntity: (entityId: string) => void;
};

export function useGlossaryEntities(bookId: string): State & Actions {
  const { accessToken } = useAuth();
  const [entities, setEntities] = useState<GlossaryEntitySummary[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [error, setError] = useState('');
  const [filters, setFiltersRaw] = useState<FilterState>(defaultFilters);
  const [offset, setOffset] = useState(0);

  // Debounced search — only the searchQuery field is debounced
  const [debouncedSearch, setDebouncedSearch] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(filters.searchQuery), 300);
    return () => clearTimeout(t);
  }, [filters.searchQuery]);

  // Stable fetch trigger: bump to force a refresh
  const [fetchKey, setFetchKey] = useState(0);

  // Track active fetch to avoid stale setState
  const abortRef = useRef<AbortController | null>(null);

  const fetchPage = useCallback(
    async (pageOffset: number, append: boolean) => {
      if (!accessToken || !bookId) return;

      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;

      const setLoading = append ? setIsLoadingMore : setIsLoading;
      setLoading(true);
      setError('');

      try {
        const resp = await glossaryApi.listEntities(
          bookId,
          { ...filters, searchQuery: debouncedSearch, limit: LIMIT, offset: pageOffset },
          accessToken,
        );
        if (ctrl.signal.aborted) return;
        if (append) {
          setEntities((prev) => [...prev, ...resp.items]);
        } else {
          setEntities(resp.items);
        }
        setTotal(resp.total);
        setOffset(pageOffset + resp.items.length);
      } catch (e: unknown) {
        if (ctrl.signal.aborted) return;
        setError((e as Error).message || 'Failed to load entities');
      } finally {
        if (!ctrl.signal.aborted) setLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [
      accessToken,
      bookId,
      filters.kindCodes,
      filters.status,
      filters.chapterIds,
      debouncedSearch,
      filters.tags,
      fetchKey,
    ],
  );

  // Reset to page 0 whenever filters / bookId / accessToken change
  useEffect(() => {
    setOffset(0);
    fetchPage(0, false);
  }, [fetchPage]);

  function setFilters(partial: Partial<FilterState>) {
    setFiltersRaw((prev) => ({ ...prev, ...partial }));
  }

  function loadMore() {
    if (isLoadingMore || entities.length >= total) return;
    fetchPage(offset, true);
  }

  function refresh() {
    setFetchKey((k) => k + 1);
  }

  function removeEntity(entityId: string) {
    setEntities((prev) => prev.filter((e) => e.entity_id !== entityId));
    setTotal((t) => t - 1);
  }

  return {
    entities,
    total,
    isLoading,
    isLoadingMore,
    error,
    filters,
    hasMore: entities.length < total,
    setFilters,
    loadMore,
    refresh,
    removeEntity,
  };
}
