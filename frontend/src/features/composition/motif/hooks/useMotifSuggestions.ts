// 3b — ranked motif suggestions for a chapter node (BE-M4). Lazy: only fetches once the
// user asks (enabled), so the scene-inspector doesn't run the retriever on every select.
import { useQuery } from '@tanstack/react-query';
import { motifApi } from '../api';

export function useMotifSuggestions(
  projectId: string | null, nodeId: string | null, token: string | null, enabled: boolean,
) {
  return useQuery({
    queryKey: ['composition', 'motif-suggest', projectId, nodeId],
    queryFn: () => motifApi.suggestForChapter(projectId!, nodeId!, token!),
    enabled: !!projectId && !!nodeId && !!token && enabled,
    staleTime: 60_000,
    select: (d) => d.candidates,
  });
}
