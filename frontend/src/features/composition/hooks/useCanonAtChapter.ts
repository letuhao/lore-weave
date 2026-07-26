// LOOM Composition (M6) — "Canon at chapter N" inspector data.
//
// Answers two writing questions from EXISTING windowed data, windowed to a chapter:
//   1. "What does chapter N establish / mention?"  → glossary chapter-entities (present
//      IN chapter N) + known-entities (established BY N, with first/last + coverage).
//   2. "What does canon KNOW as of chapter N?"     → knowledge windowed statuses + timeline
//      (before_chapter_id = N, fail-closed via resolve_before_order).
//
// Presence (glossary) and canon-state (knowledge) are TWO stores that can disagree — the
// panel labels each by source, never silently merges (per the M6 contract). Degrade-safe:
// a not-yet-extracted / unresolvable chapter surfaces "not analyzed" / "window unavailable",
// never an empty that reads as "nothing here".
//
// IMPORTANT (review-impl HIGH): the knowledge canon-state/timeline are keyed by the book's
// KNOWLEDGE project, which is DISTINCT from the composition project (the useCast precedent).
// We resolve it by book_id via useKnowledgeProjectId — passing work.project_id (composition)
// would query the wrong project and silently return an empty canon-state.
import { useQuery } from '@tanstack/react-query';
import { glossaryApi, type ChapterEntity, type KnownEntityAsOf } from '../../glossary/api';
import { knowledgeApi } from '../../knowledge/api';
import { useKnowledgeProjectId } from './useCast';

export type CanonAtChapterInput = {
  bookId: string;
  /** The chapter to window canon AS OF (book chapter UUID). */
  chapterId: string | null;
  /** The chapter's index/sort-order — required for glossary `before_chapter_index`
   *  (established-by-N). When absent that section is skipped (chapter-entities still works). */
  chapterIndex?: number | null;
  token: string | null;
  enabled: boolean;
};

export type CanonAtChapter = {
  /** Entities present IN this chapter (glossary), sorted major→appears→mentioned. */
  present: ChapterEntity[];
  /** Entities established BY this chapter (glossary known-entities). null = not requested. */
  established: KnownEntityAsOf[] | null;
  /** Knowledge cast state as-of N: counts + the fail-closed window flag. null when the
   *  knowledge project isn't resolved yet OR the fetch failed (see canonStateError). */
  canonState: { active: number; gone: number; windowAvailable: boolean } | null;
  /** Knowledge timeline event count as-of N (the timeline endpoint's fail-closed
   *  windowing is server-side; it does not return a window flag — statuses does). */
  timeline: { events: number } | null;
  /** True when a knowledge read errored (vs merely empty) — the panel shows
   *  "canon state unavailable" rather than implying a clean slate. */
  knowledgeError: boolean;
  isLoading: boolean;
  /** True when every windowed source returned empty (vs still loading) — the panel
   *  shows "chapter not yet analyzed" rather than a bare empty. */
  isEmpty: boolean;
};

const RELEVANCE_RANK: Record<ChapterEntity['relevance'], number> = { major: 0, appears: 1, mentioned: 2 };

export function useCanonAtChapter(input: CanonAtChapterInput): CanonAtChapter {
  const { bookId, chapterId, chapterIndex, token, enabled } = input;
  const on = enabled && !!token && !!chapterId;

  // Resolve the book's KNOWLEDGE project (distinct from the composition project). A
  // derivative shares book_id with its source, so this resolves the source canon's
  // knowledge graph — exactly what "canon as of the branch" wants.
  const kpQ = useKnowledgeProjectId(bookId, token);
  const kpId = kpQ.data ?? null;

  const presentQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'present', bookId, chapterId],
    queryFn: () => glossaryApi.chapterEntities(bookId, chapterId!, token!),
    enabled: on,
    retry: false,
  });

  const establishedQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'established', bookId, chapterIndex],
    // min_frequency=1: the inspector wants EVERY entity canon has established by N, not
    // just recurring ones (the route's default of 2 hides single-appearance entities).
    queryFn: () => glossaryApi.knownEntitiesAsOf(bookId, { beforeChapterIndex: chapterIndex!, minFrequency: 1, limit: 200 }, token!),
    enabled: on && chapterIndex != null,
    retry: false,
  });

  const statusesQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'statuses', kpId, chapterId],
    queryFn: () => knowledgeApi.getEntityStatuses({ project_id: kpId!, before_chapter_id: chapterId! }, token!),
    enabled: on && !!kpId,
    retry: false,
  });

  const timelineQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'timeline', kpId, chapterId],
    queryFn: () => knowledgeApi.listTimeline({ project_id: kpId!, before_chapter_id: chapterId!, limit: 200 }, token!),
    enabled: on && !!kpId,
    retry: false,
  });

  const present = [...(presentQ.data ?? [])].sort(
    (a, b) => RELEVANCE_RANK[a.relevance] - RELEVANCE_RANK[b.relevance] || b.mention_count - a.mention_count,
  );

  const statuses = statusesQ.data;
  const canonState = statuses
    ? {
        active: Object.values(statuses.statuses).filter((s) => s.status === 'active').length,
        gone: Object.values(statuses.statuses).filter((s) => s.status === 'gone').length,
        windowAvailable: statuses.window_available,
      }
    : null;

  const timeline = timelineQ.data ? { events: timelineQ.data.events.length } : null;
  const knowledgeError = statusesQ.isError || timelineQ.isError || kpQ.isError;

  const isLoading =
    presentQ.isLoading ||
    establishedQ.isLoading ||
    (on && kpQ.isLoading) ||
    statusesQ.isLoading ||
    timelineQ.isLoading;

  const isEmpty =
    !isLoading &&
    !knowledgeError &&
    present.length === 0 &&
    (establishedQ.data?.length ?? 0) === 0 &&
    (canonState?.active ?? 0) + (canonState?.gone ?? 0) === 0 &&
    (timeline?.events ?? 0) === 0;

  return {
    present,
    established: chapterIndex != null ? (establishedQ.data ?? []) : null,
    canonState,
    timeline,
    knowledgeError,
    isLoading,
    isEmpty,
  };
}
