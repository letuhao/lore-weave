import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';

// C21 — single-world controller for the workspace shell. Resolves the world and
// exposes its bible handle (book + chapter) — the anchor the workspace threads
// into lore authoring + the graph embed. A world with a null bible handle
// (legacy) is surfaced as `anchorReady=false` so the workspace degrades rather
// than mis-anchoring.
export function useWorld(worldId: string | undefined) {
  const { accessToken } = useAuth();

  const query = useQuery({
    queryKey: ['world', worldId],
    queryFn: () => worldsApi.getWorld(accessToken!, worldId!),
    enabled: !!accessToken && !!worldId,
  });

  const world = query.data ?? null;
  const bibleBookId = world?.bible_book_id ?? null;
  const bibleChapterId = world?.bible_chapter_id ?? null;

  return {
    world,
    bibleBookId,
    bibleChapterId,
    anchorReady: !!bibleBookId && !!bibleChapterId,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error as Error | null,
  };
}
