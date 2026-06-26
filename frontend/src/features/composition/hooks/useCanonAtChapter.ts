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
import { useQuery } from '@tanstack/react-query';
import { glossaryApi, type ChapterEntity, type KnownEntityAsOf } from '../../glossary/api';
import { knowledgeApi } from '../../knowledge/api';

export type CanonAtChapterInput = {
  bookId: string;
  /** The knowledge project to window (the Work's project, or a derivative's source project). */
  projectId: string;
  /** The chapter to window canon AS OF (book chapter UUID). */
  chapterId: string | null;
  /** The chapter's 0-based index/sort-order — required for glossary `before_chapter_index`
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
  /** Knowledge cast state as-of N: counts + the fail-closed window flag. */
  canonState: { active: number; gone: number; windowAvailable: boolean } | null;
  /** Knowledge timeline event count as-of N (the timeline endpoint's fail-closed
   *  windowing is server-side; it does not return a window flag — statuses does). */
  timeline: { events: number } | null;
  isLoading: boolean;
  /** True when every windowed source returned empty (vs still loading) — the panel
   *  shows "chapter not yet analyzed" rather than a bare empty. */
  isEmpty: boolean;
};

const RELEVANCE_RANK: Record<ChapterEntity['relevance'], number> = { major: 0, appears: 1, mentioned: 2 };

export function useCanonAtChapter(input: CanonAtChapterInput): CanonAtChapter {
  const { bookId, projectId, chapterId, chapterIndex, token, enabled } = input;
  const on = enabled && !!token && !!chapterId;

  const presentQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'present', bookId, chapterId],
    queryFn: () => glossaryApi.chapterEntities(bookId, chapterId!, token!),
    enabled: on,
    retry: false,
  });

  const establishedQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'established', bookId, chapterIndex],
    queryFn: () => glossaryApi.knownEntitiesAsOf(bookId, { beforeChapterIndex: chapterIndex!, limit: 200 }, token!),
    enabled: on && chapterIndex != null,
    retry: false,
  });

  const statusesQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'statuses', projectId, chapterId],
    queryFn: () => knowledgeApi.getEntityStatuses({ project_id: projectId, before_chapter_id: chapterId! }, token!),
    enabled: on && !!projectId,
    retry: false,
  });

  const timelineQ = useQuery({
    queryKey: ['composition', 'canon-at-chapter', 'timeline', projectId, chapterId],
    queryFn: () => knowledgeApi.listTimeline({ project_id: projectId, before_chapter_id: chapterId!, limit: 200 }, token!),
    enabled: on && !!projectId,
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

  const isLoading = presentQ.isLoading || establishedQ.isLoading || statusesQ.isLoading || timelineQ.isLoading;
  const isEmpty =
    !isLoading &&
    present.length === 0 &&
    (establishedQ.data?.length ?? 0) === 0 &&
    (canonState?.active ?? 0) + (canonState?.gone ?? 0) === 0 &&
    (timeline?.events ?? 0) === 0;

  return {
    present,
    established: chapterIndex != null ? (establishedQ.data ?? []) : null,
    canonState,
    timeline,
    isLoading,
    isEmpty,
  };
}
