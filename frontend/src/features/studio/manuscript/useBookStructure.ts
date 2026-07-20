import { useQuery } from '@tanstack/react-query';

import { structureApi } from './structureApi';

// P1.2 — react-query wrapper for the unified /structure read. A separate hook (like
// useWorkResolution) so consumers + tests can mock it. `staleTime` keeps the mode-by-content
// decision stable across the navigator's frequent re-renders.
export function useBookStructure(bookId: string, token: string | null) {
  return useQuery({
    queryKey: ['book-structure', bookId],
    queryFn: () => structureApi.get(token as string, bookId),
    enabled: !!token && !!bookId,
    staleTime: 5_000,
  });
}
