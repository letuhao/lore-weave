import { useUserModels as useSharedUserModels } from '@/components/model-picker/useUserModels';
import type { UserModel } from '@/features/ai-models/api';

/** The caller's registered BYOK models for a capability (via provider-registry).
 *
 *  W5 consolidation: this is now a thin adapter over the shared
 *  `@/components/model-picker` useUserModels (one fetch path, shared short-TTL
 *  cache across every picker of the same capability) that preserves the original
 *  return shape for the enrichment consumers — the items list, empty until
 *  loaded. */
export function useUserModels(capability: 'chat' | 'embedding'): UserModel[] {
  const { models } = useSharedUserModels({ capability });
  return models ?? [];
}
