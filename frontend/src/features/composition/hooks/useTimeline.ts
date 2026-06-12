// LOOM Composition (T2.3) — Timeline controller. A spoiler-safe chronology of the
// book's :Event nodes (ordered by event_order, chapter-title enriched server-side).
// The "AI sees ≤ here" cutoff is derived WITHOUT any FE stride constant (PO decision
// 2026-06-11): a second windowed count query gives the visible total, and the visible
// set is an ascending PREFIX of the full list (the BE orders event_order ASC and only
// adds an upper-bound predicate), so an event at global index `offset+i` is hidden iff
// it falls past that count — pagination-safe, zero coupling to the BE event_order scheme.
import { useMemo, useState } from 'react';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '../../knowledge/api';
import type { TimelineEvent } from '../../knowledge/api';
import { useKnowledgeProjectId } from './useCast';

export const TIMELINE_LIMIT = 50;

// Pure (exported for tests): how many of THIS page's events fall on the visible
// (≤ cutoff) side. `visibleCount` is the windowed total under the same filters;
// `undefined` (hiding spoilers, or the count not yet loaded) means "no cutoff
// context" → treat the whole page as visible (nothing dimmed).
export function visibleOnPage(
  offset: number,
  pageLen: number,
  visibleCount: number | undefined,
): number {
  if (visibleCount == null) return pageLen;
  return Math.max(0, Math.min(visibleCount - offset, pageLen));
}

// Pure (exported for tests): even-spaced x for the i-th of `count` points across
// an axis of `width` with `pad` on both ends. Single point pins to the left pad.
export function axisX(index: number, count: number, width: number, pad: number): number {
  if (count <= 1) return pad;
  return pad + ((width - 2 * pad) * index) / (count - 1);
}

function is422(err: unknown): boolean {
  return !!err && typeof err === 'object' && (err as { status?: number }).status === 422;
}

/**
 * Resolve the book's knowledge project, hold the filter/page/hide state, and run
 * the two queries (full axis + windowed count). Hooks own logic (CLAUDE.md MVC).
 */
export function useTimeline(
  bookId: string | undefined,
  chapterId: string | undefined,
  token: string | null,
) {
  const projectQ = useKnowledgeProjectId(bookId, token);
  const projectId = projectQ.data;

  const [entityId, setEntityIdState] = useState<string | null>(null);
  const [dateFrom, setDateFrom] = useState<string | null>(null);
  const [dateTo, setDateTo] = useState<string | null>(null);
  const [hideSpoilers, setHideSpoilersState] = useState(false);
  const [page, setPage] = useState(0);

  // Narrowing a filter / toggling hide can shrink `total` below the current
  // page → reset to page 0 (a stale page would render empty). Pagination
  // (prev/next) uses setPage directly and is exempt.
  const setEntityId = (v: string | null) => { setEntityIdState(v); setPage(0); };
  const setDateRange = (from: string | null, to: string | null) => {
    setDateFrom(from); setDateTo(to); setPage(0);
  };
  const setHideSpoilers = (v: boolean) => { setHideSpoilersState(v); setPage(0); };

  const offset = page * TIMELINE_LIMIT;
  const enabled = !!projectId && !!token;

  const baseFilters = useMemo(
    () => ({
      project_id: projectId ?? undefined,
      entity_id: entityId ?? undefined,
      event_date_from: dateFrom ?? undefined,
      event_date_to: dateTo ?? undefined,
    }),
    [projectId, entityId, dateFrom, dateTo],
  );

  // Main query — the full axis page. In hide mode it carries before_chapter_id so
  // the BE drops hidden events entirely (no marker needed). retry:false so a 422
  // range error surfaces immediately rather than looking like a slow load.
  const mainQ = useQuery({
    queryKey: ['composition', 'timeline', 'list', projectId, entityId, dateFrom, dateTo, hideSpoilers, chapterId, offset],
    queryFn: () => knowledgeApi.listTimeline(
      {
        ...baseFilters,
        ...(hideSpoilers && chapterId ? { before_chapter_id: chapterId } : {}),
        limit: TIMELINE_LIMIT,
        offset,
      },
      token!,
    ),
    enabled,
    placeholderData: keepPreviousData,
    retry: false,
  });

  // Cutoff-count query — the visible (≤ current chapter) total under the SAME
  // filters. limit:1 because only `total` is consumed. Disabled while hiding
  // (the main fetch IS the visible set) or with no chapter context.
  const cutoffQ = useQuery({
    queryKey: ['composition', 'timeline', 'cutoff', projectId, entityId, dateFrom, dateTo, chapterId],
    queryFn: () => knowledgeApi.listTimeline(
      { ...baseFilters, before_chapter_id: chapterId, limit: 1, offset: 0 },
      token!,
    ),
    enabled: enabled && !hideSpoilers && !!chapterId,
    placeholderData: keepPreviousData,
    select: (d) => d.total,
    retry: false,
  });

  // Entity picker options (reused knowledge entity list).
  const entitiesQ = useQuery({
    queryKey: ['composition', 'timeline', 'entities', projectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: projectId!, limit: 200 }, token!),
    enabled,
    select: (d) => d.entities,
    staleTime: 5 * 60 * 1000,
  });

  const events: TimelineEvent[] = mainQ.data?.events ?? [];

  return {
    projectId,
    projectLoading: projectQ.isLoading,
    events,
    total: mainQ.data?.total ?? 0,
    offset,
    limit: TIMELINE_LIMIT,
    // undefined while hiding (no marker / no dim) — see visibleOnPage.
    visibleCount: hideSpoilers ? undefined : cutoffQ.data,
    page,
    setPage,
    entityId,
    setEntityId,
    dateFrom,
    dateTo,
    setDateRange,
    hideSpoilers,
    setHideSpoilers,
    entities: entitiesQ.data ?? [],
    isLoading: mainQ.isLoading,
    rangeError: is422(mainQ.error),
  };
}
