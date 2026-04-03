import { apiJson } from '@/api';

// ── Account / Profile ────────────────────────────────────────────────────────

export type Profile = {
  display_name: string | null;
  email: string;
  email_verified: boolean;
};

export const accountApi = {
  getProfile(token: string) {
    return apiJson<Profile>('/v1/account/profile', { token });
  },

  patchProfile(token: string, payload: { display_name?: string }) {
    return apiJson<Profile>('/v1/account/profile', {
      method: 'PATCH',
      token,
      body: JSON.stringify(payload),
    });
  },

  changePassword(token: string, payload: { current_password: string; new_password: string }) {
    return apiJson<void>('/v1/auth/change-password', {
      method: 'POST',
      token,
      body: JSON.stringify(payload),
    });
  },

  requestVerifyEmail(token: string) {
    return apiJson<void>('/v1/auth/verify-email/request', { method: 'POST', token });
  },

  confirmVerifyEmail(verifyToken: string) {
    return apiJson<void>('/v1/auth/verify-email/confirm', {
      method: 'POST',
      body: JSON.stringify({ token: verifyToken }),
    });
  },
};

// ── Provider Registry (extend v2 ai-models API) ─────────────────────────────

export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio';

export type ProviderCredential = {
  provider_credential_id: string;
  provider_kind: ProviderKind;
  display_name: string;
  endpoint_base_url?: string | null;
  status: 'active' | 'invalid' | 'disabled' | 'archived';
  has_secret: boolean;
  created_at: string;
  updated_at: string;
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
  capability_flags?: Record<string, unknown>;
  notes?: string;
  tags: Array<{ tag_name: string; note?: string }>;
  created_at: string;
};

export type InventoryModel = {
  provider_model_name: string;
  context_length?: number | null;
  capability_flags?: Record<string, unknown>;
};

export type CapabilityType = 'chat' | 'embedding' | 'tts' | 'stt' | 'image_gen' | 'moderation' | 'reranker';

export function getInventoryMeta(m: InventoryModel) {
  const f = m.capability_flags ?? {};
  return {
    displayName: (f._display_name as string) ?? m.provider_model_name,
    capability: (f._capability as CapabilityType) ?? 'chat',
    isRecommended: (f._is_recommended as boolean) ?? false,
  };
}

export const providerApi = {
  listProviders(token: string) {
    return apiJson<{ items: ProviderCredential[] }>('/v1/model-registry/providers', { token });
  },

  createProvider(token: string, payload: { provider_kind: ProviderKind; display_name: string; secret?: string; endpoint_base_url?: string }) {
    return apiJson<ProviderCredential>('/v1/model-registry/providers', {
      method: 'POST', token, body: JSON.stringify(payload),
    });
  },

  patchProvider(token: string, id: string, payload: { display_name?: string; secret?: string; endpoint_base_url?: string; active?: boolean }) {
    return apiJson<ProviderCredential>(`/v1/model-registry/providers/${id}`, {
      method: 'PATCH', token, body: JSON.stringify(payload),
    });
  },

  deleteProvider(token: string, id: string) {
    return apiJson<void>(`/v1/model-registry/providers/${id}`, { method: 'DELETE', token });
  },

  listInventory(token: string, providerId: string, refresh = false) {
    const qs = refresh ? '?refresh=true' : '';
    return apiJson<{ items: InventoryModel[]; synced_at?: string }>(
      `/v1/model-registry/providers/${providerId}/models${qs}`, { token },
    );
  },

  listUserModels(token: string) {
    return apiJson<{ items: UserModel[] }>('/v1/model-registry/user-models?include_inactive=true', { token });
  },

  createUserModel(token: string, payload: {
    provider_credential_id: string;
    provider_model_name: string;
    alias?: string;
    context_length?: number;
    capability_flags?: Record<string, unknown>;
    tags?: Array<{ tag_name: string; note?: string }>;
    notes?: string;
  }) {
    return apiJson<UserModel>('/v1/model-registry/user-models', {
      method: 'POST', token, body: JSON.stringify(payload),
    });
  },

  patchUserModel(token: string, modelId: string, payload: {
    alias?: string;
    context_length?: number | null;
    capability_flags?: Record<string, unknown>;
    notes?: string;
  }) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}`, {
      method: 'PATCH', token, body: JSON.stringify(payload),
    });
  },

  putUserModelTags(token: string, modelId: string, tags: Array<{ tag_name: string; note?: string }>) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}/tags`, {
      method: 'PUT', token, body: JSON.stringify({ tags }),
    });
  },

  patchActivation(token: string, modelId: string, isActive: boolean) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}/activation`, {
      method: 'PATCH', token, body: JSON.stringify({ is_active: isActive }),
    });
  },

  patchFavorite(token: string, modelId: string, isFavorite: boolean) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}/favorite`, {
      method: 'PATCH', token, body: JSON.stringify({ is_favorite: isFavorite }),
    });
  },

  deleteUserModel(token: string, modelId: string) {
    return apiJson<void>(`/v1/model-registry/user-models/${modelId}`, { method: 'DELETE', token });
  },

  verifyUserModel(token: string, modelId: string) {
    return apiJson<{ verified: boolean; latency_ms: number; error?: string }>(
      `/v1/model-registry/user-models/${modelId}/verify`, { method: 'POST', token },
    );
  },
};
