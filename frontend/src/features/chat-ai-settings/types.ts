// Chat & AI settings — shared types (spec docs/specs/2026-07-05-chat-ai-settings.md §6).

export type ModelRef = { model_source: string; model_ref: string };

/** Per-field resolution: the winning value, which tier supplied it, and the full
 *  raw per-tier stack (so the UI can render "overriding book's X · revert to
 *  inherited (would be Y)" and key on tier, not value-equality). */
export type FieldResolution<T = unknown> = {
  effective_value: T | null;
  source_tier: string | null;
  tier_stack: Record<string, T>;
};

export type ModelResolution = {
  effective_value: ModelRef | null;
  source_tier: string;          // tool|session|book|account|system|unavailable|no_model_configured
  tier_stack: Record<string, ModelRef>;
  skipped: string[];            // tiers whose ref was dead/skipped
};

export type EffectiveSettings = {
  context_ref: { book_id: string | null; session_id: string | null };
  models: Record<string, ModelResolution>;               // keyed by ModelRole
  behavior: Record<string, FieldResolution>;
  grounding: Record<string, FieldResolution>;
  voice: Record<string, FieldResolution>;
  context: Record<string, FieldResolution>;
};

export type AiPrefs = {
  behavior: Record<string, unknown>;
  grounding: Record<string, unknown>;
  voice: Record<string, unknown>;
  context: Record<string, unknown>;
  version: number;
};

/** Partial deep-merge patch; a null leaf clears (inherits), absent is untouched. */
export type AiPrefsPatch = Partial<Pick<AiPrefs, 'behavior' | 'grounding' | 'voice' | 'context'>>;

export type ModelRole = 'chat' | 'composer' | 'planner' | 'embedding' | 'rerank' | 'critic';

/** A deploy-tier capability ceiling (D-WS4C-EFFECTIVE-VALUE). `deploy_allows` is the
 *  process-global kill-switch; a consumer computes `effective = deploy_allows && knob`
 *  where `knob` is its own user/project opt-in. `source_tier` is always 'system'. */
export type CapabilityCeiling = { deploy_allows: boolean; source_tier: string };

export type ChatCapabilities = {
  canon_capture: CapabilityCeiling;
};
