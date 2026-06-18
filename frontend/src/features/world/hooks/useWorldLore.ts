import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';
import type { ChapterLink } from '../types';

export interface AuthorLoreArgs {
  kindId: string;
}

// C21 — world lore authoring controller. Authors a glossary entity against the
// world's BIBLE CHAPTER in two ordered steps:
//   1. create the entity in the bible BOOK (glossary `{kind_id}` contract), then
//   2. chapter-link it to the bible CHAPTER (the NOT-NULL anchor).
// The second step is what makes the lore "belong to the world" — its
// `chapter_id` MUST equal the world's bible_chapter_id. The hook owns the
// ordering + the cache invalidation; the view only calls `authorLore()`.
export function useWorldLore(bibleBookId: string | null, bibleChapterId: string | null) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();

  // Glossary kinds power the lore form's kind picker (reused, not world-specific).
  const kindsQuery = useQuery({
    queryKey: ['world-kinds'],
    queryFn: () => worldsApi.listKinds(accessToken!),
    enabled: !!accessToken,
  });

  const mutation = useMutation({
    mutationFn: async ({ kindId }: AuthorLoreArgs): Promise<ChapterLink> => {
      if (!bibleBookId || !bibleChapterId) {
        throw new Error('world bible anchor unavailable');
      }
      // Step 1 — entity in the bible book.
      const entity = await worldsApi.createBibleEntity(accessToken!, bibleBookId, kindId);
      // Step 2 — anchor it to the bible chapter (carries bible_chapter_id).
      return worldsApi.linkEntityToBibleChapter(
        accessToken!,
        bibleBookId,
        entity.entity_id,
        bibleChapterId,
      );
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['world-lore', bibleBookId] });
    },
  });

  return {
    kinds: kindsQuery.data ?? [],
    kindsLoading: kindsQuery.isLoading,
    authorLore: mutation.mutateAsync,
    isAuthoring: mutation.isPending,
    lastLink: mutation.data ?? null,
    error: mutation.error as Error | null,
  };
}
