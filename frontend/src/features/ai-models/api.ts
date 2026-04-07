import { apiJson } from '../../api';

export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio' | (string & {});

export type UserModel = {
  user_model_id: string;
  provider_credential_id: string;
  provider_kind: ProviderKind;
  provider_model_name: string;
  context_length?: number | null;
  alias?: string | null;
  is_active: boolean;
  is_favorite: boolean;
  capability_flags?: Record<string, boolean>;
  tags: Array<{ tag_name: string; note?: string }>;
  created_at: string;
};

export const aiModelsApi = {
  listUserModels(token: string, params?: { only_favorites?: boolean; include_inactive?: boolean; provider_kind?: ProviderKind; capability?: string }) {
    const qs = new URLSearchParams();
    if (params?.only_favorites !== undefined) qs.set('only_favorites', String(params.only_favorites));
    if (params?.include_inactive !== undefined) qs.set('include_inactive', String(params.include_inactive));
    if (params?.provider_kind) qs.set('provider_kind', params.provider_kind);
    if (params?.capability) qs.set('capability', params.capability);
    return apiJson<{ items: UserModel[] }>(`/v1/model-registry/user-models${qs.toString() ? `?${qs.toString()}` : ''}`, { token });
  },
};
