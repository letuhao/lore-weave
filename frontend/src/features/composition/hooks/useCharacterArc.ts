// LOOM Composition (T2.4) — Character Arc controller. The entity-scoped projection
// of the Timeline (T2.3): one character's events in event_order + the current 1-hop
// relations + an active→gone state band. Reuses the knowledge api + T2.3's decoupled
// spoiler cutoff (windowed count, NO FE stride). Hooks own logic (CLAUDE.md MVC).
import { useQuery } from '@tanstack/react-query';
import { knowledgeApi } from '../../knowledge/api';
import type { TimelineEvent } from '../../knowledge/api';
import { useKnowledgeProjectId } from './useCast';

export const ARC_LIMIT = 100;

// Pure (exported for tests): the index at which the character's arc transitions
// active→gone. `from_order` is the event_order of the gone-transition (spoiler-
// windowed by the BE, so always ≤ the cutoff). Returns:
//   • count  — still active (no gone band)
//   • 0      — gone with no recorded transition order (whole arc is "gone")
//   • i      — first event with event_order ≥ from_order (band: active [0,i), gone [i,count))
export function arcBandSplit(
  events: TimelineEvent[],
  status: 'active' | 'gone' | undefined,
  fromOrder: number | null | undefined,
): number {
  if (status !== 'gone') return events.length;
  if (fromOrder == null) return 0;
  const i = events.findIndex((e) => e.event_order != null && e.event_order >= fromOrder);
  return i < 0 ? events.length : i;
}

/**
 * Resolve the project + the character roster, pick the effective entity (the
 * controlled `selectedEntityId`, else the first), and compose the arc: events
 * (entity-scoped), the windowed visible-count for the cutoff, the relations, and
 * the spoiler-windowed story-state for the band.
 */
export function useCharacterArc(
  bookId: string | undefined,
  chapterId: string | undefined,
  token: string | null,
  selectedEntityId: string | null,
) {
  const projectQ = useKnowledgeProjectId(bookId, token);
  const projectId = projectQ.data;
  const enabled = !!projectId && !!token;
  // Normalize an EMPTY chapter id (the dock panel opens with `activeChapterId ??
  // ''` — no active reading position) to `undefined`: `before_chapter_id` is a
  // `UUID | None` server param, so an empty query value (`before_chapter_id=`)
  // 422s (uuid_parsing) instead of fail-closing the window. The cutoff query
  // already gates on `!!chapterId`, but the batch-status query does not.
  const beforeChapterId = chapterId || undefined;

  const rosterQ = useQuery({
    queryKey: ['composition', 'arc', 'roster', projectId],
    queryFn: () => knowledgeApi.listEntities({ project_id: projectId!, limit: 200 }, token!),
    enabled,
    select: (d) => d.entities,
    staleTime: 5 * 60 * 1000,
  });
  const roster = rosterQ.data ?? [];
  // Default to the first roster entity (without a useEffect) so the arc renders
  // something on first open; the picker / Cast-launch override via selectedEntityId.
  const effectiveEntityId = selectedEntityId ?? roster[0]?.id ?? null;
  const arcEnabled = enabled && !!effectiveEntityId;

  // Arc spine — the character's events (full set; the cutoff dims the future).
  const eventsQ = useQuery({
    queryKey: ['composition', 'arc', 'events', projectId, effectiveEntityId],
    queryFn: () => knowledgeApi.listTimeline(
      { project_id: projectId!, entity_id: effectiveEntityId!, limit: ARC_LIMIT }, token!),
    enabled: arcEnabled,
    select: (d) => d.events,
  });

  // Decoupled cutoff: the visible (≤ current chapter) count under the same entity
  // scope. limit:1 — only `total` is consumed (T2.3 pattern, no FE stride).
  const cutoffQ = useQuery({
    queryKey: ['composition', 'arc', 'cutoff', projectId, effectiveEntityId, beforeChapterId ?? null],
    queryFn: () => knowledgeApi.listTimeline(
      { project_id: projectId!, entity_id: effectiveEntityId!, before_chapter_id: beforeChapterId, limit: 1 }, token!),
    enabled: arcEnabled && !!beforeChapterId,
    select: (d) => d.total,
  });

  // Relations strip — the entity's 1-hop RELATES_TO.
  const detailQ = useQuery({
    queryKey: ['composition', 'arc', 'detail', effectiveEntityId],
    queryFn: () => knowledgeApi.getEntityDetail(effectiveEntityId!, token!),
    enabled: arcEnabled,
  });

  // State band — the spoiler-windowed story-state (active|gone + from_order). Batch
  // route (no per-entity status route exists); we read this entity's entry.
  const statusQ = useQuery({
    queryKey: ['composition', 'arc', 'status', projectId, beforeChapterId ?? null],
    queryFn: () => knowledgeApi.getEntityStatuses(
      { project_id: projectId!, before_chapter_id: beforeChapterId }, token!),
    enabled,
  });
  const state = effectiveEntityId ? statusQ.data?.statuses?.[effectiveEntityId] : undefined;

  return {
    projectId,
    projectLoading: projectQ.isLoading,
    roster,
    effectiveEntityId,
    // Authoritative name for the focus entity — lets the picker label a Cast-launched
    // entity that's past the 200-roster cap with its real name, not a raw id.
    focusName: detailQ.data?.entity.name ?? null,
    events: eventsQ.data ?? [],
    visibleCount: cutoffQ.data,
    relations: detailQ.data?.relations ?? [],
    state, // { status, from_order } | undefined
    isLoading: rosterQ.isLoading || eventsQ.isLoading,
  };
}
