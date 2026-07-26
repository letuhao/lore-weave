import { apiJson } from '../../api';

export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio' | (string & {});

/**
 * Model pricing table (mirrors provider-registry `user_models.pricing` JSONB).
 * Empty object = unpriced (fails closed server-side); explicit zeros = priced-free
 * (local/self-hosted). Dimensions are additive — keep this loose.
 */
export type ModelPricing = {
  input_per_mtok?: number;
  output_per_mtok?: number;
  per_image?: number;
  per_second?: number;
  per_kchar?: number;
} & Record<string, number | undefined>;

/**
 * THE canonical UserModel type (W5 consolidation) — the former duplicate in
 * `features/settings/api.ts` re-exports this one. capability_flags carries TWO
 * historical schemas: canonical `{"chat": true}` booleans and legacy
 * `{"_capability": "chat", "_display_name": …}` metadata — use
 * {@link getUserModelMeta} instead of reading it directly.
 */
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
  pricing?: ModelPricing;
  notes?: string;
  /**
   * User-defined custom sort position ((8)-residual). `null`/absent = unordered
   * (sorts after ordered models, favorites-first fallback). Persisted server-side
   * so a drag-reorder in the shared ModelPicker survives across devices. The list
   * endpoint already returns rows in `sort_order ASC NULLS LAST, is_favorite DESC`
   * order — clients render in-order, they do NOT re-sort by this field.
   */
  sort_order?: number | null;
  tags: Array<{ tag_name: string; note?: string }>;
  created_at: string;
};

/** Provider kinds that run on the user's own hardware — the "$0 local" hint. */
export const LOCAL_PROVIDER_KINDS = new Set<string>(['lm_studio', 'ollama']);

/** Capability keys that are real capabilities (not `_`-prefixed metadata). */
const META_PREFIX = '_';

export type UserModelMeta = {
  /** alias > legacy `_display_name` > provider_model_name. */
  displayName: string;
  /** Declared capability tokens (canonical boolean keys + the legacy `_capability`). */
  capabilities: string[];
  /** True when the model runs on a local provider kind OR pricing is explicit-zero. */
  isFree: boolean;
  /** True when a non-empty pricing table is present. */
  isPriced: boolean;
};

/**
 * Single place that understands both capability_flags schemas + pricing.
 * (Consolidates the legacy `getInventoryMeta` handling for user models.)
 */
export function getUserModelMeta(m: UserModel): UserModelMeta {
  const flags = m.capability_flags ?? {};
  const displayName =
    (m.alias || undefined) ??
    (typeof flags._display_name === 'string' && flags._display_name
      ? (flags._display_name as string)
      : undefined) ??
    m.provider_model_name;

  const capabilities: string[] = [];
  for (const [k, v] of Object.entries(flags)) {
    if (!k.startsWith(META_PREFIX) && v === true) capabilities.push(k);
  }
  if (typeof flags._capability === 'string' && !capabilities.includes(flags._capability)) {
    capabilities.push(flags._capability);
  }

  const pricing = m.pricing ?? {};
  const priceValues = Object.values(pricing).filter((v): v is number => typeof v === 'number');
  const isPriced = priceValues.length > 0;
  const isFree =
    LOCAL_PROVIDER_KINDS.has(m.provider_kind) || (isPriced && priceValues.every((v) => v === 0));

  return { displayName, capabilities, isFree, isPriced };
}

/** Explicit non-chat capability flags that must never be auto-picked as a chat
 * default, even when the server's `capability=chat` filter also includes the
 * model (the legacy `_capability` fallback can contradict an explicit boolean
 * flag — e.g. a rerank model stamped `{"_capability":"chat","rerank":true}` by
 * a stale discovery run). D-PLANFORGE-MODEL-AUTOPICK. */
const NON_CHAT_CAPABILITY_FLAGS = ['rerank', 'embedding', 'tts', 'stt'] as const;

/** Safe to silently auto-select for a chat/LLM call — i.e. has no explicit
 * non-chat capability flag, regardless of what `capabilities`/`_capability`
 * also claims. Use this to filter candidates before picking a favorite/first
 * default; never trust the raw list order or a "chat" appearing in the merged
 * capabilities alone. */
export function isChatSafeDefault(m: UserModel): boolean {
  const flags = m.capability_flags ?? {};
  // An explicit `chat: true` always wins, even on a genuinely dual-capability
  // model (e.g. one that also embeds) -- the exclusion list below is only a
  // fallback heuristic for models with NO explicit chat flag.
  if (flags.chat === true) return true;
  return !NON_CHAT_CAPABILITY_FLAGS.some((k) => flags[k] === true);
}

export const aiModelsApi = {
  listUserModels(token: string, params?: { only_favorites?: boolean; include_inactive?: boolean; provider_kind?: ProviderKind; capability?: string }) {
    const qs = new URLSearchParams();
    if (params?.only_favorites !== undefined) qs.set('only_favorites', String(params.only_favorites));
    if (params?.include_inactive !== undefined) qs.set('include_inactive', String(params.include_inactive));
    if (params?.provider_kind) qs.set('provider_kind', params.provider_kind);
    if (params?.capability) qs.set('capability', params.capability);
    return apiJson<{ items: UserModel[] }>(`/v1/model-registry/user-models${qs.toString() ? `?${qs.toString()}` : ''}`, { token });
  },

  patchFavorite(token: string, modelId: string, isFavorite: boolean) {
    return apiJson<UserModel>(`/v1/model-registry/user-models/${modelId}/favorite`, {
      method: 'PATCH', token, body: JSON.stringify({ is_favorite: isFavorite }),
    });
  },

  /**
   * Persist a user-defined custom order ((8)-residual). `orderedIds` gets
   * sort_order 0..N-1; every other model the caller owns is reset to unordered
   * (NULL). Returns the freshly-ordered list (same shape/order as listUserModels).
   */
  reorderUserModels(token: string, orderedIds: string[]) {
    return apiJson<{ items: UserModel[] }>(`/v1/model-registry/user-models/reorder`, {
      method: 'PUT', token, body: JSON.stringify({ ordered_ids: orderedIds }),
    });
  },
};
