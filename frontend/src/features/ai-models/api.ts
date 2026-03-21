import { apiJson } from '@/api';

export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio';

export type ProviderCredential = {
  provider_credential_id: string;
  provider_kind: ProviderKind;
  display_name: string;
  endpoint_base_url?: string | null;
  status: 'active' | 'invalid' | 'disabled' | 'archived';
  created_at: string;
  updated_at: string;
};

export type ModelTag = {
  tag_name: string;
  note?: string;
};

export type UserModel = {
  user_model_id: string;
  provider_credential_id: string;
  provider_kind: ProviderKind;
  provider_model_name: string;
  context_length?: number | null;
  alias?: string | null;
  is_active: boolean;
  is_favorite: boolean;
  tags: ModelTag[];
  capability_flags?: Record<string, boolean>;
  created_at: string;
  updated_at: string;
};

export type PlatformModel = {
  platform_model_id: string;
  provider_kind: ProviderKind;
  provider_model_name: string;
  display_name: string;
  status: 'active' | 'maintenance' | 'retired';
  pricing_policy?: Record<string, unknown>;
  quota_policy_ref?: string | null;
  capability_flags?: Record<string, boolean>;
};

export type UsageLog = {
  usage_log_id: string;
  request_id: string;
  owner_user_id: string;
  provider_kind: ProviderKind;
  model_source: 'user_model' | 'platform_model';
  model_ref: string;
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
  total_cost_usd: number;
  billing_decision: 'quota' | 'credits' | 'rejected';
  request_status: 'success' | 'provider_error' | 'billing_rejected';
  created_at: string;
};

export const aiModelsApi = {
  listProviders(token: string) {
    return apiJson<{ items: ProviderCredential[] }>('/v1/model-registry/providers', { token });
  },
  createProvider(
    token: string,
    payload: {
      provider_kind: ProviderKind;
      display_name: string;
      secret?: string;
      endpoint_base_url?: string;
      active?: boolean;
    },
  ) {
    return apiJson<ProviderCredential>('/v1/model-registry/providers', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },
  listProviderInventory(token: string, providerCredentialId: string, refresh = false) {
    const qs = new URLSearchParams();
    if (refresh) qs.set('refresh', 'true');
    return apiJson<{ items: Array<{ provider_model_name: string; context_length?: number | null }>; synced_at?: string }>(
      `/v1/model-registry/providers/${providerCredentialId}/models${qs.toString() ? `?${qs.toString()}` : ''}`,
      { token },
    );
  },
  listUserModels(token: string, params?: { only_favorites?: boolean; include_inactive?: boolean; provider_kind?: ProviderKind }) {
    const qs = new URLSearchParams();
    if (params?.only_favorites !== undefined) qs.set('only_favorites', String(params.only_favorites));
    if (params?.include_inactive !== undefined) qs.set('include_inactive', String(params.include_inactive));
    if (params?.provider_kind) qs.set('provider_kind', params.provider_kind);
    return apiJson<{ items: UserModel[] }>(`/v1/model-registry/user-models${qs.toString() ? `?${qs.toString()}` : ''}`, { token });
  },
  createUserModel(
    token: string,
    payload: {
      provider_credential_id: string;
      provider_model_name: string;
      context_length?: number;
      alias?: string;
      tags?: ModelTag[];
    },
  ) {
    return apiJson<UserModel>('/v1/model-registry/user-models', { method: 'POST', token, body: JSON.stringify(payload) });
  },
  patchUserModelActivation(token: string, userModelId: string, isActive: boolean) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${userModelId}/activation`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ is_active: isActive }),
    });
  },
  patchUserModelFavorite(token: string, userModelId: string, isFavorite: boolean) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${userModelId}/favorite`, {
      method: 'PATCH',
      token,
      body: JSON.stringify({ is_favorite: isFavorite }),
    });
  },
  putUserModelTags(token: string, userModelId: string, tags: ModelTag[]) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${userModelId}/tags`, {
      method: 'PUT',
      token,
      body: JSON.stringify({ tags }),
    });
  },
  listPlatformModels(token: string) {
    return apiJson<{ items: PlatformModel[] }>('/v1/model-registry/platform-models', { token });
  },
  listUsageLogs(token: string, params?: { limit?: number; offset?: number }) {
    const qs = new URLSearchParams();
    if (params?.limit !== undefined) qs.set('limit', String(params.limit));
    if (params?.offset !== undefined) qs.set('offset', String(params.offset));
    return apiJson<{ items: UsageLog[]; total: number }>(`/v1/model-billing/usage-logs${qs.toString() ? `?${qs.toString()}` : ''}`, {
      token,
    });
  },
  getUsageLogDetail(token: string, usageLogId: string) {
    return apiJson<{
      usage_log: UsageLog;
      input_payload: Record<string, unknown>;
      output_payload: Record<string, unknown>;
      viewed_at: string;
    }>(`/v1/model-billing/usage-logs/${usageLogId}`, { token });
  },
  getUsageSummary(token: string, period: 'last_24h' | 'last_7d' | 'current_month' = 'current_month') {
    return apiJson<{
      period: string;
      request_count: number;
      total_tokens: number;
      total_cost_usd: number;
      charged_credits: number;
      quota_consumed_tokens: number;
    }>(`/v1/model-billing/usage-summary?period=${period}`, { token });
  },
  getAccountBalance(token: string) {
    return apiJson<{
      tier_name: string;
      month_quota_tokens: number;
      month_quota_remaining_tokens: number;
      credits_balance: number;
      billing_policy_version: string;
    }>('/v1/model-billing/account-balance', { token });
  },
};
