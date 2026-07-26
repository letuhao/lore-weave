import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';
import { useBookKnowledgeProject } from '@/features/knowledge/hooks/useBookKnowledgeProject';

// W11 lore-seeker controller — the reader-side "ask the lore" facade. The whole point is the
// SPOILER WINDOW: an entity's known facts are fetched with `before_chapter_id = the chapter the
// reader is on`, so a reader only ever sees what has been established BY where they've read. The
// server fails CLOSED (an omitted/unresolvable chapter → no facts), so a fresh reader with no
// position sees nothing — never a leak. This hook owns the project resolve + the two reads; the
// panel renders. `chapterId` empty → the window can't resolve → facts stay hidden.
export function useLoreSeeker(bookId: string, chapterId: string) {
  const { accessToken } = useAuth();
  const { projectId } = useBookKnowledgeProject(bookId);
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const trimmed = query.trim();
  // FAIL-CLOSED at the LIST too, not just the facts (adversarial review, 2026-07-15): the entity
  // list is now SERVER-WINDOWED — `before_chapter_id` restricts it to entities the reader has met
  // (a fact established by their chapter), fail-closed on an unresolvable position. Gating on
  // `!!chapterId` still blocks the zero-position reader entirely; passing `before_chapter_id`
  // additionally stops an EARLY-position reader (ch1) from browsing the NAMES of characters first
  // introduced in later chapters — the leak the review found (facts were windowed, names were not).
  const entities = useQuery({
    queryKey: ['lore-seeker-entities', projectId, trimmed, chapterId],
    queryFn: () =>
      knowledgeApi.listEntities(
        {
          project_id: projectId!,
          search: trimmed.length >= 2 ? trimmed : undefined,
          limit: 20,
          before_chapter_id: chapterId,
        },
        accessToken!,
      ),
    enabled: !!accessToken && !!projectId && !!chapterId,
  });

  // The windowed read — the spoiler gate. Only runs once an entity is picked AND the reader has a
  // position (chapterId). before_chapter_id is the reader's chapter; the server windows to it.
  const facts = useQuery({
    queryKey: ['lore-seeker-facts', selectedId, chapterId],
    queryFn: () =>
      knowledgeApi.getEntityFacts(selectedId!, { before_chapter_id: chapterId || undefined }, accessToken!),
    enabled: !!accessToken && !!selectedId && !!chapterId,
  });

  return {
    projectId,
    query,
    setQuery,
    entities: entities.data?.entities ?? [],
    isEntitiesLoading: entities.isLoading,
    selectedId,
    select: setSelectedId,
    facts: facts.data?.facts ?? [],
    windowAvailable: facts.data?.window_available ?? false,
    isFactsLoading: facts.isLoading,
    hasPosition: !!chapterId,
  };
}
