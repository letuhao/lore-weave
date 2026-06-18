import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { booksApi } from '@/features/books/api';
import { worldsApi } from '../api';

// W5 (G1) — populate a world with books. Two paths, both ending in C20's
// `moveBookIntoWorld` (sets `books.world_id`):
//   • attach(bookId)            — bring an existing book into the world.
//   • createAndAttach(payload)  — create a new book, THEN attach it.
//
// Create-and-attach is deliberately TWO steps (design decision ⑧): if the
// attach fails after the book is created, the book still exists standalone and
// is re-attachable — no orphan loss. The error surfaces so the user can retry
// the attach (a re-create would dup the book).
//
// On success we invalidate the living-world tree (so the new book's Works
// repopulate it) and the world rollup graph (a new member book may add nodes).
export function useAddBookToWorld(worldId: string | undefined) {
  const { accessToken } = useAuth();
  const qc = useQueryClient();

  const invalidate = () => {
    // Books list → cascades the per-book Works resolution (useQueries keys off
    // the refreshed book refs); the rollup graph re-reads the union.
    qc.invalidateQueries({ queryKey: ['living-world', 'books', worldId] });
    qc.invalidateQueries({ queryKey: ['world-subgraph'] });
  };

  const attachMutation = useMutation({
    mutationFn: (bookId: string) => worldsApi.moveBookIntoWorld(accessToken!, worldId!, bookId),
    onSuccess: invalidate,
  });

  const createMutation = useMutation({
    mutationFn: async (payload: { title: string; description?: string }) => {
      const book = await booksApi.createBook(accessToken!, payload);
      // Step 2 — attach. A failure here leaves `book` standalone (re-attachable).
      await worldsApi.moveBookIntoWorld(accessToken!, worldId!, book.book_id);
      return book;
    },
    onSuccess: invalidate,
  });

  return {
    attach: attachMutation.mutateAsync,
    createAndAttach: createMutation.mutateAsync,
    isPending: attachMutation.isPending || createMutation.isPending,
    error: (attachMutation.error ?? createMutation.error) as Error | null,
  };
}
