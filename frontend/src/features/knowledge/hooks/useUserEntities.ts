import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { knowledgeApi, type Entity } from '../api';

// K19c.4 — user-scope entity listing hook. Consumes
// GET /v1/knowledge/me/entities shipped by K19c Cycle α.
//
// MVP scope = 'global' (cross-project preferences the Global tab's
// Preferences section renders). scope='project' lands alongside K19d.
//
// queryKey includes userId so a logout→login swap on a shared
// QueryClient doesn't leak cached entities between users — same
// defence pattern as useExtractionJobs / useUserCosts. staleTime 60s
// since entities only change when (a) Track 2 extracts a new one or
// (b) the user archives one via PreferencesSection; neither is
// high-frequency.

const DEFAULT_LIMIT = 50;

export interface UseUserEntitiesResult {
  entities: Entity[];
  isLoading: boolean;
  error: Error | null;
}

export function useUserEntities(
  scope: 'global' = 'global',
): UseUserEntitiesResult {
  const { accessToken, user } = useAuth();
  const userId = user?.user_id ?? 'anon';

  const query = useQuery({
    queryKey: ['knowledge-user-entities', userId, scope, DEFAULT_LIMIT] as const,
    queryFn: () =>
      knowledgeApi.listMyEntities(
        { scope, limit: DEFAULT_LIMIT },
        accessToken!,
      ),
    enabled: !!accessToken,
    staleTime: 60_000,
  });

  return {
    entities: query.data?.entities ?? [],
    isLoading: query.isLoading,
    error: (query.error as Error | null) ?? null,
  };
}
