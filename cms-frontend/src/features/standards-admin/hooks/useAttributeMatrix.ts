import { useQueries, useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { listSystemAttributes, listSystemGenres } from '../api';
import type { SystemAttribute, SystemGenre } from '../types';

// G-C1 — the user-tier matrix fetches every attribute at once (useBookOntology); the
// System read REQUIRES both kind_id + genre_id (422 otherwise). So for the selected
// kind we fan out ONE listSystemAttributes(kind, genre) per active genre via useQueries
// and merge the results client-side, tagging each attribute by its genre_id.
export function useAttributeMatrix(kindId: string) {
  const { accessToken } = useAuth();

  const genres = useQuery({
    queryKey: ['system-genres'],
    queryFn: () => listSystemGenres(accessToken),
  });

  // All System genres are "active" (no per-book toggle exists at the System tier).
  const activeGenres: SystemGenre[] = genres.data ?? [];

  const attrQueries = useQueries({
    queries: activeGenres.map((g) => ({
      queryKey: ['system-attributes', kindId, g.genre_id],
      queryFn: () => listSystemAttributes(accessToken, kindId, g.genre_id),
      enabled: Boolean(kindId) && genres.isSuccess,
    })),
  });

  // Merge every genre's attributes into one flat list. The API already stamps each
  // attribute with its genre_id, so the rows are self-describing.
  const attributes: SystemAttribute[] = attrQueries.flatMap((q) => q.data ?? []);

  const isLoading = genres.isLoading || (Boolean(kindId) && attrQueries.some((q) => q.isLoading));
  const isError = genres.isError || attrQueries.some((q) => q.isError);

  return { activeGenres, attributes, isLoading, isError, genres };
}
