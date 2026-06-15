import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { translationApi, type SegmentStatusItem } from '../api';

/**
 * Controller for the per-segment drill-down (T2-M3): owns the segment-status query
 * for one (chapter, language) and the "re-translate changed" mutation. `target` is
 * null when the drill-down is closed (query disabled). On a successful re-translate
 * it invalidates the matrix + segment coverage so the badges refresh.
 */
export function useSegmentDrilldown(
  bookId: string,
  target: { chapterId: string; lang: string } | null,
  onRetranslated?: () => void,
) {
  const { accessToken } = useAuth();
  const queryClient = useQueryClient();
  const enabled = !!accessToken && !!target;

  const query = useQuery({
    queryKey: ['segment-status', target?.chapterId, target?.lang],
    queryFn: () => translationApi.getSegmentStatus(accessToken!, target!.chapterId, target!.lang),
    enabled,
  });

  const retranslate = useMutation({
    mutationFn: () => translationApi.retranslateDirty(accessToken!, target!.chapterId, target!.lang),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['translation-coverage', bookId] });
      queryClient.invalidateQueries({ queryKey: ['segment-coverage', bookId] });
      onRetranslated?.();
    },
  });

  const segments: SegmentStatusItem[] = query.data?.segments ?? [];
  return {
    segments,
    needsCount: query.data?.needs_count ?? 0,
    loading: query.isLoading && enabled,
    error: query.error ? (query.error as Error).message : '',
    retranslate: () => retranslate.mutate(),
    retranslating: retranslate.isPending,
    retranslateError: retranslate.error ? (retranslate.error as Error).message : '',
  };
}
