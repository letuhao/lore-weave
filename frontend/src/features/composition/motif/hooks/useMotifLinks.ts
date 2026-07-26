// 3a-C — the motif GRAPH controller. Reads/writes one motif's relationship edges via
// BE-M3 (GET/POST /motifs/{id}/links, DELETE /motif-links/{id}). No JSX. The DB
// motif_link_guard trigger (self-link/cycle/cross-tier) surfaces as a 409 whose
// detail.message the mutation carries to the view (inline, not a swallowed toast).
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { motifApi, type MotifLinkKind } from '../api';

export function useMotifLinks(motifId: string | null, token: string | null, bookId?: string | null) {
  const qc = useQueryClient();
  const listKey = ['composition', 'motif-links', motifId, bookId ?? null];
  const query = useQuery({
    queryKey: listKey,
    queryFn: () => motifApi.links(motifId!, token!, { direction: 'both', bookId }),
    enabled: !!motifId && !!token,
    select: (d) => d.links,
  });
  // Invalidate every direction/book variant for this motif after a write.
  const invalidate = () => qc.invalidateQueries({ queryKey: ['composition', 'motif-links', motifId] });

  const create = useMutation({
    mutationFn: (args: { to_motif_id: string; kind: MotifLinkKind; ord?: number | null }) =>
      motifApi.createLink(motifId!, { ...args, book_id: bookId ?? null }, token!),
    onSuccess: invalidate,
  });
  const remove = useMutation({
    mutationFn: (linkId: string) => motifApi.deleteLink(linkId, token!, bookId ?? null),
    onSuccess: invalidate,
  });

  return {
    links: query.data ?? [],
    isLoading: query.isLoading,
    isError: query.isError,
    refetch: query.refetch,
    create,
    remove,
  };
}
