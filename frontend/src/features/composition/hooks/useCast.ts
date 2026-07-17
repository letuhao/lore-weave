// LOOM Composition (T2.1) — Cast & Codex controller. Reads the knowledge graph
// directly via the gateway (reusing features/knowledge/api): resolve the book's
// knowledge project, list its cast (entities) + batch spoiler-windowed story-state,
// and lazy-load one entity's relations / recent events / known facts on expand.
// Hooks own logic (CLAUDE.md MVC); the panel renders.
import { keepPreviousData, useInfiniteQuery, useQuery } from '@tanstack/react-query';
import { useMemo } from 'react';
import { knowledgeApi } from '../../knowledge/api';
import type { Entity, EntityStatusEntry } from '../../knowledge/api';

// Resolve the book's knowledge project (0-or-1). Distinct from the COMPOSITION
// project — the codex reads the knowledge graph, bound by book_id.
export function useKnowledgeProjectId(bookId: string | undefined, token: string | null) {
  return useQuery({
    queryKey: ['composition', 'cast', 'project', bookId],
    queryFn: () => knowledgeApi.listProjects({ book_id: bookId! }, token!),
    enabled: !!bookId && !!token,
    select: (d): string | null => d.items[0]?.project_id ?? null,
    staleTime: 5 * 60 * 1000,
  });
}

export type CastRow = Entity & { state: EntityStatusEntry | undefined };

// D-CAST-KEYSET-PAGING (S7) — the list is paged, not capped. The backend
// `list_entities_filtered` route already takes `offset` (`SKIP $offset LIMIT
// $limit`), so we page it offset-wise: each page pulls PAGE_SIZE rows, and
// `getNextPageParam` advances the offset until we've loaded the reported
// `total`. A >PAGE_SIZE cast is reachable via `loadMore` (a real control),
// NOT a dead-end truncation notice. Offset (not keyset) is fine here — the
// route exposes offset, and the cast list is a small, stable set (no infinite
// insert churn mid-scroll).
const PAGE_SIZE = 200;

/**
 * The cast list + batch story-state, joined by entity id. `beforeChapterId` is
 * the current chapter (spoiler window). `search` is gated to ≥2 chars (the BE
 * 422s shorter) so short keystrokes don't round-trip.
 *
 * The entity list is offset-paged: `entities.data` is the flattened union of
 * every loaded page; `hasMore`/`loadMore`/`isFetchingMore` drive the
 * "Load more" affordance; `total`/`loaded` report progress.
 */
export function useCast(
  projectId: string | null | undefined,
  token: string | null,
  opts: { kind?: string; search?: string; beforeChapterId?: string },
) {
  const { kind, search } = opts;
  // Normalize an EMPTY chapter id (no active reading position — the dock panel
  // opens with `activeChapterId ?? ''`) to `undefined`. `before_chapter_id` is a
  // `UUID | None` server param: an empty query value (`before_chapter_id=`) 422s
  // (uuid_parsing) instead of omitting the window, so the intended "window
  // unavailable → fail-closed + banner" path never runs. `'' || undefined`
  // omits it; a real UUID passes through.
  const beforeChapterId = opts.beforeChapterId || undefined;
  const effSearch = search && search.trim().length >= 2 ? search.trim() : undefined;
  const enabled = !!projectId && !!token;

  // A changed search / kind is part of the query identity → a fresh first page
  // (offset 0), not a re-page of the previously-loaded rows.
  const entitiesQuery = useInfiniteQuery({
    queryKey: ['composition', 'cast', 'entities', projectId, kind ?? null, effSearch ?? null],
    queryFn: ({ pageParam }) => knowledgeApi.listEntities(
      { project_id: projectId!, kind, search: effSearch, limit: PAGE_SIZE, offset: pageParam }, token!),
    initialPageParam: 0,
    // Advance the offset by however many rows we've actually loaded, stopping
    // once we've reached the server's reported `total`. `total` is read off the
    // latest page so it tracks a set that grew/shrank between fetches.
    getNextPageParam: (lastPage, allPages) => {
      const loaded = allPages.reduce((n, p) => n + p.entities.length, 0);
      return loaded < lastPage.total ? loaded : undefined;
    },
    enabled,
    placeholderData: keepPreviousData,
  });

  const flatEntities = useMemo<Entity[] | undefined>(
    () => entitiesQuery.data?.pages.flatMap((p) => p.entities),
    [entitiesQuery.data],
  );
  const total = entitiesQuery.data?.pages[0]?.total ?? 0;

  // Preserve the `{ data, isLoading }` shape the panel + StyleVoicePanel read,
  // now backed by the flattened infinite-query result.
  const entities = {
    data: flatEntities,
    isLoading: entitiesQuery.isLoading,
    isError: entitiesQuery.isError,
    error: entitiesQuery.error,
  };

  // Batch status is project + chapter scoped (NOT keyed on search/kind-filtered
  // ids) so it's fetched once and joined client-side. Kind is passed so a
  // kind-filtered view doesn't status the whole cast needlessly.
  const statuses = useQuery({
    queryKey: ['composition', 'cast', 'statuses', projectId, kind ?? null, beforeChapterId ?? null],
    queryFn: () => knowledgeApi.getEntityStatuses(
      { project_id: projectId!, kind, before_chapter_id: beforeChapterId }, token!),
    enabled,
    placeholderData: keepPreviousData,
  });

  return {
    entities,
    statuses,
    // D-CAST-KEYSET-PAGING — real paging past the first page.
    hasMore: !!entitiesQuery.hasNextPage,
    loadMore: entitiesQuery.fetchNextPage,
    isFetchingMore: entitiesQuery.isFetchingNextPage,
    total,
    loaded: flatEntities?.length ?? 0,
  };
}

// ── expanded-row detail (lazy) ────────────────────────────────────────

/** 1-hop relations + aliases for one entity (reuses the knowledge detail route). */
export function useEntityDetail(entityId: string | null, token: string | null, enabled = true) {
  return useQuery({
    queryKey: ['composition', 'cast', 'detail', entityId],
    queryFn: () => knowledgeApi.getEntityDetail(entityId!, token!),
    enabled: !!entityId && !!token && enabled,
  });
}

/** Recent spoiler-safe events for one entity (windowed by chapter). */
export function useEntityEvents(
  entityId: string | null, beforeChapterId: string | undefined, token: string | null, enabled = true,
) {
  // Empty chapter id (no reading position) → omit the window (see useCast); a
  // `before_chapter_id=` empty query value 422s the UUID param.
  const beforeId = beforeChapterId || undefined;
  return useQuery({
    queryKey: ['composition', 'cast', 'events', entityId, beforeId ?? null],
    queryFn: () => knowledgeApi.listTimeline(
      { entity_id: entityId!, before_chapter_id: beforeId, limit: 10 }, token!),
    enabled: !!entityId && !!token && enabled,
    select: (d) => d.events,
  });
}

/** Known facts (decision/preference/…) ABOUT one entity, windowed by chapter. */
export function useEntityFacts(
  entityId: string | null, beforeChapterId: string | undefined, token: string | null, enabled = true,
) {
  // Empty chapter id (no reading position) → omit the window (see useCast); a
  // `before_chapter_id=` empty query value 422s the UUID param.
  const beforeId = beforeChapterId || undefined;
  return useQuery({
    queryKey: ['composition', 'cast', 'facts', entityId, beforeId ?? null],
    queryFn: () => knowledgeApi.getEntityFacts(entityId!, { before_chapter_id: beforeId }, token!),
    enabled: !!entityId && !!token && enabled,
  });
}
