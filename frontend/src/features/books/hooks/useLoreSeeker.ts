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
  const entities = useQuery({
    queryKey: ['lore-seeker-entities', projectId, trimmed],
    queryFn: () =>
      knowledgeApi.listEntities(
        { project_id: projectId!, search: trimmed.length >= 2 ? trimmed : undefined, limit: 20 },
        accessToken!,
      ),
    enabled: !!accessToken && !!projectId,
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
