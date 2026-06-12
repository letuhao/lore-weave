// LOOM Composition (T2.1) — Cast & Codex controller. Reads the knowledge graph
// directly via the gateway (reusing features/knowledge/api): resolve the book's
// knowledge project, list its cast (entities) + batch spoiler-windowed story-state,
// and lazy-load one entity's relations / recent events / known facts on expand.
// Hooks own logic (CLAUDE.md MVC); the panel renders.
import { keepPreviousData, useQuery } from '@tanstack/react-query';
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

/**
 * The cast list + batch story-state, joined by entity id. `beforeChapterId` is
 * the current chapter (spoiler window). `search` is gated to ≥2 chars (the BE
 * 422s shorter) so short keystrokes don't round-trip.
 */
export function useCast(
  projectId: string | null | undefined,
  token: string | null,
  opts: { kind?: string; search?: string; beforeChapterId?: string },
) {
  const { kind, search, beforeChapterId } = opts;
  const effSearch = search && search.trim().length >= 2 ? search.trim() : undefined;
  const enabled = !!projectId && !!token;

  const entities = useQuery({
    queryKey: ['composition', 'cast', 'entities', projectId, kind ?? null, effSearch ?? null],
    queryFn: () => knowledgeApi.listEntities(
      { project_id: projectId!, kind, search: effSearch, limit: 200 }, token!),
    enabled,
    placeholderData: keepPreviousData,
    select: (d) => d.entities,
  });

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

  return { entities, statuses };
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
  return useQuery({
    queryKey: ['composition', 'cast', 'events', entityId, beforeChapterId ?? null],
    queryFn: () => knowledgeApi.listTimeline(
      { entity_id: entityId!, before_chapter_id: beforeChapterId, limit: 10 }, token!),
    enabled: !!entityId && !!token && enabled,
    select: (d) => d.events,
  });
}

/** Known facts (decision/preference/…) ABOUT one entity, windowed by chapter. */
export function useEntityFacts(
  entityId: string | null, beforeChapterId: string | undefined, token: string | null, enabled = true,
) {
  return useQuery({
    queryKey: ['composition', 'cast', 'facts', entityId, beforeChapterId ?? null],
    queryFn: () => knowledgeApi.getEntityFacts(entityId!, { before_chapter_id: beforeChapterId }, token!),
    enabled: !!entityId && !!token && enabled,
  });
}
