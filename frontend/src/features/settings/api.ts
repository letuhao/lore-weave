import { apiJson } from '@/api';
import { aiModelsApi, type UserModel, type ModelPricing } from '@/features/ai-models/api';

// W5 consolidation: the canonical UserModel type + list client live in
// features/ai-models/api.ts — re-exported here so existing settings imports
// keep working without a second divergent definition.
export type { UserModel, ModelPricing } from '@/features/ai-models/api';

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

  // Delegates to the canonical ai-models client (W5 consolidation). Keeps this
  // module's historical include_inactive=true default (the settings management
  // list shows deactivated models too; pickers use the shared ModelPicker which
  // defaults to active-only).
  listUserModels(token: string, opts?: { capability?: string }) {
    return aiModelsApi.listUserModels(token, { include_inactive: true, capability: opts?.capability });
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
    /** D-PRICING-REFRESH — omit to leave pricing unchanged; a full replace
     *  when present (not a per-field merge), so callers must spread the
     *  model's existing pricing first if they only mean to edit one field. */
    pricing?: ModelPricing;
  }) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}`, {
      method: 'PATCH', token, body: JSON.stringify(payload),
    });
  },

  /** D-PRICING-REFRESH — best-effort live-pricing suggestion from OpenRouter's
   *  public catalog for this model. Never auto-applied: the caller reviews
   *  `pricing`/`source_model_id` and, if it looks right, calls patchUserModel
   *  itself to persist it. */
  suggestPricing(token: string, modelId: string) {
    return apiJson<{ found: boolean; source_model_id?: string; pricing?: ModelPricing }>(
      `/v1/model-registry/user-models/${modelId}/pricing/suggest`, { token },
    );
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

// Domain scopes (PUB-3 / OD-5). A key reaches a tool only if it holds the tool's
// TIER scope AND a `domain:<d>` scope for every domain the tool touches (the edge
// scope-filter enforces both — docs/specs/2026-06-26-public-mcp/05 §2, H-F). New
// keys default to `read` on `book + glossary + knowledge` (OD-5). Stored in the same
// flat `scopes[]` array as the tier scopes, prefixed with `domain:`.
export const MCP_DOMAINS = [
  'book',
  'glossary',
  'knowledge',
  'translation',
  'composition',
  'jobs',
  'settings',
  'lore_enrichment',
  'catalog',
] as const;
export type McpDomain = (typeof MCP_DOMAINS)[number];

export const DEFAULT_MCP_DOMAINS: McpDomain[] = ['book', 'glossary', 'knowledge'];

/** The scope token a key must carry to reach domain `d` (mirrors the edge). */
export const domainScope = (d: McpDomain): string => `domain:${d}`;

/** Split a stored `scopes[]` into its tier tokens and bare domain names. */
export function splitScopes(scopes: string[]): { tiers: string[]; domains: string[] } {
  const tiers: string[] = [];
  const domains: string[] = [];
  for (const s of scopes) {
    if (s.startsWith('domain:')) domains.push(s.slice('domain:'.length));
    else tiers.push(s);
  }
  return { tiers, domains };
}

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

// Partial edit of an existing key's SAFE metadata — name / limits / expiry /
// self-confirm. Scopes and the secret are intentionally NOT editable here (a
// credential's reach is fixed at issue; widen it by revoking + re-creating). Every
// field is optional: only the ones sent are changed. `expires_at` is tri-state —
// an RFC3339 string sets it, `''` clears it (no expiry), `undefined` leaves it.
export type McpKeyUpdatePayload = {
  name?: string;
  spend_cap_usd?: number | null;
  rate_limit_rpm?: number;
  allow_self_confirm?: boolean;
  expires_at?: string | null;
};

// One per-key call audit row (H-O) — the owner's view of what an agent did with a key.
export type McpAuditRow = {
  audit_id: string;
  method: string;
  tool_name: string | null;
  outcome: 'relayed' | 'denied_scope' | 'rate_limited' | 'unauthorized' | 'upstream_error' | 'tool_error';
  trace_id: string | null;
  created_at: string;
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
  update(token: string, keyId: string, payload: McpKeyUpdatePayload) {
    return apiJson<McpKey>(`/v1/account/mcp-keys/${keyId}`, {
      method: 'PATCH', token, body: JSON.stringify(payload),
    });
  },
  revoke(token: string, keyId: string) {
    return apiJson<void>(`/v1/account/mcp-keys/${keyId}`, { method: 'DELETE', token });
  },
  audit(token: string, keyId: string) {
    return apiJson<{ items: McpAuditRow[] }>(`/v1/account/mcp-keys/${keyId}/audit`, { token });
  },
};

// ── Public MCP human-approval queue (P4 / OD-2) ─────────────────────────────
// A DEFAULT key's (allow_self_confirm=false) Tier-W action is held here until the
// owner approves — the edge diverts the propose to auth-service instead of handing
// the agent the confirm token. The owner approves (the action executes, attributed
// to the agent's key) or denies (the token is dropped).
// See docs/specs/2026-06-26-public-mcp/03-public-mcp-security-design.md §6.3.

export type McpApproval = {
  approval_id: string;
  key_id: string;
  tool_name: string;
  domain: string;
  preview: Record<string, unknown>;
  cost_estimate_usd?: number | null;
  status: 'pending' | 'denied' | 'expired' | 'executed' | 'failed';
  expires_at: string;
  created_at: string;
  decided_at?: string | null;
};

export const mcpApprovalsApi = {
  list(token: string, status = 'pending') {
    const qs = status ? `?status=${encodeURIComponent(status)}` : '';
    return apiJson<{ items: McpApproval[] }>(`/v1/account/mcp-keys/approvals${qs}`, { token });
  },
  approve(token: string, approvalId: string) {
    return apiJson<{ status: string; result?: unknown; detail?: unknown }>(
      `/v1/account/mcp-keys/approvals/${approvalId}/approve`,
      { method: 'POST', token },
    );
  },
  deny(token: string, approvalId: string) {
    return apiJson<{ status: string }>(`/v1/account/mcp-keys/approvals/${approvalId}/deny`, {
      method: 'POST', token,
    });
  },
};
