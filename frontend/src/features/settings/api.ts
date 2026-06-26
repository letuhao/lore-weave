import { apiJson } from '@/api';

// ── Account / Profile ────────────────────────────────────────────────────────

export type Profile = {
  display_name: string | null;
  email: string;
  email_verified: boolean;
  // Q-GATE: read-only platform flag — when false the public-MCP tab is hidden.
  public_mcp_enabled?: boolean;
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

  deleteAccount(token: string) {
    return apiJson<void>('/v1/account', { method: 'DELETE', token });
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

export type APIStandard = 'openai_compatible' | 'anthropic' | 'ollama' | 'lm_studio';

export type ProviderCredential = {
  provider_credential_id: string;
  provider_kind: string;
  display_name: string;
  endpoint_base_url?: string | null;
  status: 'active' | 'invalid' | 'disabled' | 'archived';
  has_secret: boolean;
  api_standard?: APIStandard;
  // Per-credential concurrency cap. null/absent = unlimited (request-as-demand;
  // the backend infra is the limiter). Set only when the user knows their own
  // backend's limit (e.g. a local GPU that runs N calls at once).
  max_concurrency?: number | null;
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

// C0 rerank/reranker reconcile (BL-1): the canonical capability token is
// `rerank` — the value provider-registry tags rerank models with and the value
// RerankModelPicker/ModelRolePicker filter on. The settings display layer used
// the divergent `reranker`, so a registered rerank model rendered with no badge.
// Use this constant everywhere the rerank capability is referenced so a future
// rename can't silently re-introduce drift (the wiring test asserts the picker
// filters on exactly this token).
export const RERANK_CAPABILITY = 'rerank' as const;
export const EMBEDDING_CAPABILITY = 'embedding' as const;
// `planner` is a per-user default ROLE (the model glossary_plan plans with), not a model
// capability flag — so the picker LISTS the user's chat models but SAVES under 'planner'.
export const PLANNER_CAPABILITY = 'planner' as const;
export const CHAT_CAPABILITY = 'chat' as const;

// Per-user DEFAULT model per capability (rerank/embedding). The default is the
// user's own BYOK user_model, resolved server-side by provider-registry — it
// restores the default-model UX the removed RERANK_URL/_MODEL .env config gave,
// the BYOK way. Consumers (raw search) fall back to it when no scope model is set.
export const defaultModelsApi = {
  get(token: string) {
    return apiJson<{ defaults: Record<string, string> }>('/v1/model-registry/default-models', { token });
  },
  set(token: string, capability: string, userModelId: string | null) {
    return apiJson<{ capability: string; user_model_id: string | null }>(
      `/v1/model-registry/default-models/${capability}`,
      { method: 'PUT', token, body: JSON.stringify({ user_model_id: userModelId }) },
    );
  },
};

export type CapabilityType = 'chat' | 'embedding' | 'tts' | 'stt' | 'image_gen' | 'moderation' | 'rerank';

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

  createProvider(token: string, payload: { provider_kind: string; display_name: string; secret?: string; endpoint_base_url?: string; api_standard?: APIStandard; max_concurrency?: number | null }) {
    return apiJson<ProviderCredential>('/v1/model-registry/providers', {
      method: 'POST', token, body: JSON.stringify(payload),
    });
  },

  patchProvider(token: string, id: string, payload: { display_name?: string; secret?: string; endpoint_base_url?: string; active?: boolean; api_standard?: APIStandard; max_concurrency?: number | null }) {
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

  listUserModels(token: string, opts?: { capability?: string }) {
    const params = new URLSearchParams({ include_inactive: 'true' });
    if (opts?.capability) params.set('capability', opts.capability);
    return apiJson<{ items: UserModel[] }>(`/v1/model-registry/user-models?${params}`, { token });
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
    // C3: rerank verify returns ranked scores (a real /v1/rerank round-trip) in
    // addition to the generic verified/latency shape.
    return apiJson<{
      verified: boolean;
      latency_ms: number;
      error?: string;
      capability?: string;
      scores?: { index: number; relevance_score: number }[];
      top_index?: number;
      top_score?: number;
    }>(
      `/v1/model-registry/user-models/${modelId}/verify`, { method: 'POST', token },
    );
  },
};

// ── Public MCP API keys (P1) ────────────────────────────────────────────────
// External-agent credentials for the public MCP edge. The full secret is shown
// ONCE at creation (`McpKeyCreated.key`); only an Argon2id hash is stored. The
// whole feature's visibility is gated by the platform PUBLIC_MCP_ENABLED flag,
// surfaced on the profile (`Profile.public_mcp_enabled`).
// See docs/specs/2026-06-26-public-mcp/03-public-mcp-security-design.md §5.

// Coarse scope categories the public edge advertises against — the
// `public_scope_rec` tokens from docs/specs/2026-06-26-public-mcp/05 §2. P2's
// scope-filter keys on exactly these. New keys default to `read` only (Wave-A
// safe rollout: read/non-paid tools only).
export const MCP_SCOPES = ['read', 'paid_read', 'write_auto', 'write_confirm'] as const;
export type McpScope = (typeof MCP_SCOPES)[number];

export type McpKey = {
  key_id: string;
  name: string;
  key_prefix: string;
  scopes: string[];
  spend_cap_usd: number | null;
  rate_limit_rpm: number;
  allow_self_confirm: boolean;
  status: 'active' | 'revoked';
  last_used_at: string | null;
  expires_at: string | null;
  created_at: string;
};

// The create response — the ONLY payload that ever carries the raw secret.
export type McpKeyCreated = {
  key_id: string;
  name: string;
  key: string;
  key_prefix: string;
  scopes: string[];
  created_at: string;
};

export type McpKeyCreatePayload = {
  name: string;
  scopes?: string[];
  spend_cap_usd?: number | null;
  rate_limit_rpm?: number;
  allow_self_confirm?: boolean;
  expires_at?: string | null;
};

export const mcpKeysApi = {
  list(token: string) {
    return apiJson<{ items: McpKey[] }>('/v1/account/mcp-keys', { token });
  },
  create(token: string, payload: McpKeyCreatePayload) {
    return apiJson<McpKeyCreated>('/v1/account/mcp-keys', {
      method: 'POST', token, body: JSON.stringify(payload),
    });
  },
  revoke(token: string, keyId: string) {
    return apiJson<void>(`/v1/account/mcp-keys/${keyId}`, { method: 'DELETE', token });
  },
};
