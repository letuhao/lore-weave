import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { worldsApi } from '@/features/world/api';

// D-WORLD-PROJECT-BACKLINK (G3) — resolve a knowledge project's cross-links: its
// book (title) and, if that book is grouped into a world, the world (name). The
// book read carries `world_id` (W6), so one book GET yields the world id; a
// second GET resolves the world's name. Both are best-effort reads — a missing
// book/world degrades to the raw id (the OverviewSection still links out).
export function useProjectBacklinks(bookId: string | null | undefined) {
  const { accessToken } = useAuth();

  const bookQuery = useQuery({
    queryKey: ['project-backlink-book', bookId],
    queryFn: () => booksApi.getBook(accessToken!, bookId!),
    enabled: !!accessToken && !!bookId,
    staleTime: 30_000,
  });

  const worldId = bookQuery.data?.world_id ?? null;

  const worldQuery = useQuery({
    queryKey: ['project-backlink-world', worldId],
    queryFn: () => worldsApi.getWorld(accessToken!, worldId!),
    enabled: !!accessToken && !!worldId,
    staleTime: 30_000,
  });

  return {
    bookTitle: bookQuery.data?.title ?? null,
    worldId,
    worldName: worldQuery.data?.name ?? null,
    isLoading: bookQuery.isLoading,
  };
}
