import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { providerApi } from '@/features/settings/api';

/** The caller's registered BYOK models for a capability (via provider-registry).
 *  Shared by the enrichment model-pickers (Gaps + Compose) — keyed by capability so
 *  the react-query cache is shared (no double fetch). Returns the items list (empty
 *  until loaded). The single seam for "which models can this user pick", so the two
 *  panels don't each re-implement the same useQuery. */
export function useUserModels(capability: 'chat' | 'embedding') {
  const { accessToken } = useAuth();
  const { data } = useQuery({
    queryKey: ['user-models', capability],
    queryFn: () => providerApi.listUserModels(accessToken!, { capability }),
    enabled: !!accessToken,
  });
  return data?.items ?? [];
}
