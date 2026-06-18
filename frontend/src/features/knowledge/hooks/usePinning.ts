import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type GlossaryEntityStatsResponse } from '../api';
import {
  autoPinSuggestions,
  distinctKinds,
  filterEntities,
  pinnedWindowTokens,
  type EntityFilter,
} from '../lib/pinning';

// C13 — "controller" for the build-wizard Step-2 glossary-pinning dual-list.
// Owns the pinned-set + filter state and the stats query; the PinningStep view
// only renders what this returns. Self-contained per the FE hooks rule.
export function usePinning(projectId: string, enabled: boolean) {
  const { accessToken } = useAuth();

  // The set of pinned glossary entity ids (the wizard posts this).
  const [pinnedIds, setPinnedIds] = useState<Set<string>>(new Set());
  const [filter, setFilter] = useState<EntityFilter>({
    search: '',
    kind: '',
    minMentions: 0,
  });

  const statsQuery = useQuery<GlossaryEntityStatsResponse>({
    queryKey: ['knowledge', 'glossary-entity-stats', projectId],
    queryFn: () => knowledgeApi.getGlossaryEntityStats(projectId, accessToken!),
    enabled: enabled && !!accessToken && !!projectId,
    staleTime: 60_000,
    retry: false,
  });

  const stats = statsQuery.data?.items ?? [];
  const chapterCount = statsQuery.data?.chapter_count ?? 0;

  const suggestions = useMemo(
    () => autoPinSuggestions(stats, chapterCount),
    [stats, chapterCount],
  );
  const kinds = useMemo(() => distinctKinds(stats), [stats]);

  // Available = not-yet-pinned, after the search/kind/frequency filters.
  const available = useMemo(
    () => filterEntities(stats, filter).filter((s) => !pinnedIds.has(s.entity_id)),
    [stats, filter, pinnedIds],
  );
  // Pinned = the pinned-set, resolved back to stat rows (order-stable by stats).
  const pinned = useMemo(
    () => stats.filter((s) => pinnedIds.has(s.entity_id)),
    [stats, pinnedIds],
  );

  const pin = (id: string) =>
    setPinnedIds((prev) => new Set(prev).add(id));
  const unpin = (id: string) =>
    setPinnedIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  // Apply the auto-pin suggestions (additive — keeps any manual pins).
  const applySuggestions = () =>
    setPinnedIds((prev) => {
      const next = new Set(prev);
      suggestions.forEach((id) => next.add(id));
      return next;
    });
  const reset = () => {
    setPinnedIds(new Set());
    setFilter({ search: '', kind: '', minMentions: 0 });
  };

  const pinnedIdList = useMemo(() => Array.from(pinnedIds), [pinnedIds]);
  // Pending suggestions = suggested ids the user hasn't pinned yet (drives the
  // "Pin N suggestions" banner; hidden once all are pinned).
  const pendingSuggestions = useMemo(
    () => suggestions.filter((id) => !pinnedIds.has(id)),
    [suggestions, pinnedIds],
  );

  return {
    statsQuery,
    chapterCount,
    available,
    pinned,
    kinds,
    filter,
    setFilter,
    pin,
    unpin,
    applySuggestions,
    reset,
    pinnedIdList,
    pendingSuggestions,
    perWindowTokens: pinnedWindowTokens(pinnedIds.size),
  };
}
