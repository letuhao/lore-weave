// W10 arc-timeline — list the caller's visible arc templates (owned + system) for the
// arc library surface. Tier-merged via scope='all' (NOT others' public — that's the
// catalog). No JSX.
//
// ARC-I18N: the reader's language goes on the wire. Without a caller sending it the
// whole translation layer is dead weight and a Vietnamese reader still gets English —
// the repo's most repeated bug shape, and the reason the motif library's own version of
// this line exists. It is a RE-WORDING, not a filter (the server used to treat it as a
// WHERE arm, which returned an empty library), so it is safe to send unconditionally.
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { arcApi } from '../arcApi';
import type { ArcTemplate } from '../arcTypes';

export function useArcLibrary(token: string | null) {
  const { i18n } = useTranslation();
  const display_language = i18n.language || undefined;
  return useQuery<ArcTemplate[]>({
    queryKey: ['composition', 'arc-templates', 'all', display_language ?? null],
    queryFn: async () => (
      await arcApi.list({ scope: 'all', limit: 100, display_language }, token!)
    ).arc_templates,
    enabled: !!token,
    staleTime: 30_000,
  });
}
