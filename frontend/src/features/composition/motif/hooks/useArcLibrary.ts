// W10 arc-timeline — list the caller's visible arc templates (owned + system) for the
// arc library surface. Tier-merged via scope='all' (NOT others' public — that's the
// catalog). No JSX.
import { useQuery } from '@tanstack/react-query';
import { arcApi } from '../arcApi';
import type { ArcTemplate } from '../arcTypes';

export function useArcLibrary(token: string | null) {
  return useQuery<ArcTemplate[]>({
    queryKey: ['composition', 'arc-templates', 'all'],
    queryFn: async () => (await arcApi.list({ scope: 'all', limit: 100 }, token!)).arc_templates,
    enabled: !!token,
    staleTime: 30_000,
  });
}
