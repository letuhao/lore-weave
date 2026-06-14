import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi } from '@/features/knowledge/api';

// C21 — resolve the world's knowledge project (if any) for the read-only graph
// embed. A world's lore graph is the knowledge project linked to its bible book
// (`projects.book_id == bibleBookId`). Most worlds have NO project until they
// build a graph — that's expected; the graph view then shows its own empty
// state. This is a pure read (no new BE; reuses the existing list endpoint's
// `book_id` filter).
export function useWorldProject(bibleBookId: string | null) {
  const { accessToken } = useAuth();

  const query = useQuery({
    queryKey: ['world-project', bibleBookId],
    queryFn: () =>
      knowledgeApi.listProjects({ limit: 1, book_id: bibleBookId! }, accessToken!),
    enabled: !!accessToken && !!bibleBookId,
  });

  const projectId = query.data?.items?.[0]?.project_id ?? null;

  return {
    projectId,
    isLoading: query.isLoading,
  };
}
