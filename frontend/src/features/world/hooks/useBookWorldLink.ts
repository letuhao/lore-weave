import { useMutation } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { worldsApi } from '../api';

// W6 (G3) — link/unlink a book to a world from the BOOK side (the mirror of
// W5's world-side AddBookToWorldModal). `link` attaches; `unlink` detaches back
// to standalone. The caller reloads the book on success (the book read carries
// `world_id`, so a reload reflects the new state + drives the backlink).
export function useBookWorldLink(bookId: string) {
  const { accessToken } = useAuth();

  const linkMutation = useMutation({
    mutationFn: (worldId: string) => worldsApi.moveBookIntoWorld(accessToken!, worldId, bookId),
  });
  const unlinkMutation = useMutation({
    mutationFn: (worldId: string) => worldsApi.removeBookFromWorld(accessToken!, worldId, bookId),
  });

  return {
    link: linkMutation.mutateAsync,
    unlink: unlinkMutation.mutateAsync,
    isPending: linkMutation.isPending || unlinkMutation.isPending,
    error: (linkMutation.error ?? unlinkMutation.error) as Error | null,
  };
}
