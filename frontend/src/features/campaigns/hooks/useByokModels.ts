import { useQuery } from '@tanstack/react-query';
import { useAuth } from '@/auth';
import { aiModelsApi, type UserModel } from '../../ai-models/api';

/** D-S5C-PICKER-DEDUP — the caller's BYOK models for a capability, behind react-query
 *  keyed by capability so every picker of that capability SHARES one fetch. The Model
 *  Matrix renders four `chat` pickers (extractor/translator/verifier/eval-judge); with
 *  the prior per-picker useEffect that was four identical requests, now it's one. */
export function useByokModels(
  capability: string,
): { models: UserModel[]; loading: boolean; error: boolean } {
  const { accessToken } = useAuth();
  const q = useQuery({
    queryKey: ['campaign-byok-models', capability],
    queryFn: () => aiModelsApi.listUserModels(accessToken!, { capability, include_inactive: false }),
    enabled: !!accessToken,
  });
  return { models: q.data?.items ?? [], loading: q.isLoading, error: q.isError };
}
