export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio';
// S4c: 'recorded' is the audit-only decision (token-quota deduction retired; USD
// enforcement is the spend guardrail). 'quota'|'credits'|'rejected' are kept for
// historical usage_logs rows written before the retirement.
export type BillingDecision = 'quota' | 'credits' | 'rejected' | 'recorded';
export type RequestStatus = 'success' | 'provider_error' | 'billing_rejected';

// bug #24: `purpose` is the per-operation label of an LLM call in the Usage GUI.
// It used to be a tiny closed union, but background jobs (extraction, prose
// drafting, KG summaries, judges …) now emit distinct labels via
// job_meta.usage_purpose, so it's an OPEN string set. Presentation degrades
// gracefully (family color/label fallback) for any label not enumerated here.
export type Purpose = string;

// The background-job purpose labels emitted across services (frozen taxonomy,
// bug #24). Seeds the filter dropdown so common purposes are selectable even
// before rows exist; merged at runtime with whatever `by_purpose` actually has.
export const KNOWN_PURPOSES: string[] = [
  'chat', 'translation', 'chunk_edit', 'image_gen',
  'glossary_extraction', 'glossary_translation',
  'prose_draft', 'prose_stitch', 'prose_rerank', 'prose_critic', 'prose_eval', 'prose_plan',
  'canon_check', 'promise_audit', 'narrative_thread', 'context_compress',
  'working_memory', 'coref_detect', 'kg_summary', 'wiki_generate', 'passage_select', 'kg_backfill',
  'reward_judge',
];

// purposeFamily buckets the many labels into a few visually-coherent groups, so
// the GUI stays readable as new labels are added without a per-label table.
type PurposeFamily =
  | 'chat' | 'translation' | 'glossary' | 'prose'
  | 'knowledge' | 'composition' | 'learning' | 'image' | 'chunk' | 'unknown';

const KNOWLEDGE_PURPOSES = new Set([
  'working_memory', 'coref_detect', 'kg_summary', 'wiki_generate', 'passage_select', 'kg_backfill',
]);
const COMPOSITION_PURPOSES = new Set([
  'canon_check', 'promise_audit', 'narrative_thread', 'context_compress',
]);

export function purposeFamily(p: string): PurposeFamily {
  if (p === 'chat') return 'chat';
  if (p === 'translation') return 'translation';
  if (p === 'chunk_edit') return 'chunk';
  if (p === 'image_gen') return 'image';
  if (p.startsWith('glossary_')) return 'glossary';
  if (p.startsWith('prose_')) return 'prose';
  if (p.startsWith('kg_') || KNOWLEDGE_PURPOSES.has(p)) return 'knowledge';
  if (COMPOSITION_PURPOSES.has(p)) return 'composition';
  if (p === 'reward_judge') return 'learning';
  return 'unknown';
}

const FAMILY_COLOR: Record<PurposeFamily, string> = {
  chat: '#3da692', translation: '#3dba6a', glossary: '#3dba6a', prose: '#5b9bd5',
  knowledge: '#46b3a0', composition: '#c08ad8', learning: '#e07a9a',
  image: '#e8a832', chunk: '#a78bfa', unknown: '#9e9488',
};
const FAMILY_BADGE: Record<PurposeFamily, string> = {
  chat: 'bg-accent/10 text-accent border-accent/15',
  translation: 'bg-green-500/10 text-green-400 border-green-500/15',
  glossary: 'bg-green-500/10 text-green-400 border-green-500/15',
  prose: 'bg-blue-500/10 text-blue-400 border-blue-500/15',
  knowledge: 'bg-teal-500/10 text-teal-400 border-teal-500/15',
  composition: 'bg-violet-500/10 text-violet-400 border-violet-500/15',
  learning: 'bg-pink-500/10 text-pink-400 border-pink-500/15',
  image: 'bg-primary/10 text-primary border-primary/15',
  chunk: 'bg-purple-500/10 text-purple-400 border-purple-500/15',
  unknown: 'bg-secondary text-muted-foreground border-border',
};

/** Hex bar/dot color for a purpose label (BreakdownPanels). */
export const purposeColor = (p: string): string => FAMILY_COLOR[purposeFamily(p)];
/** Tailwind badge classes for a purpose label (RequestLogTable). */
export const purposeBadgeClass = (p: string): string => FAMILY_BADGE[purposeFamily(p)];

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
  billing_decision: BillingDecision;
  request_status: RequestStatus;
  purpose: Purpose;
  created_at: string;
};

export type UsageLogDetail = {
  usage_log: UsageLog;
  input_payload: Record<string, unknown>;
  output_payload: Record<string, unknown>;
  viewed_at: string;
};

export type ProviderBreakdown = {
  provider_kind: ProviderKind;
  total_tokens: number;
  total_cost_usd: number;
  request_count: number;
};

export type PurposeBreakdown = {
  purpose: Purpose;
  total_tokens: number;
  request_count: number;
};

export type DailyBreakdown = {
  date: string;
  input_tokens: number;
  output_tokens: number;
  request_count: number;
};

export type UsageSummary = {
  period: string;
  request_count: number;
  total_tokens: number;
  total_cost_usd: number;
  charged_credits: number;
  quota_consumed_tokens: number;
  error_count: number;
  error_rate: number;
  prev_request_count: number;
  prev_total_tokens: number;
  prev_total_cost_usd: number;
  prev_error_rate: number;
  by_provider: ProviderBreakdown[];
  by_purpose: PurposeBreakdown[];
  daily: DailyBreakdown[];
};

// S4c: AccountBalance (deprecated token quota/credits ledger) retired from the FE.
// The USD wallet is Guardrail + PlatformBalance (below).

export type UsageFilters = {
  provider_kind?: ProviderKind;
  request_status?: RequestStatus;
  purpose?: Purpose;
  from?: string;
  to?: string;
};

export type Period = 'last_24h' | 'last_7d' | 'last_30d' | 'last_90d';

// Phase 6a-γ — spend guardrail (Subsystem A) + platform balance (Subsystem B).
export type Guardrail = {
  daily_limit_usd: number;
  monthly_limit_usd: number;
  daily_spent_usd: number;
  monthly_spent_usd: number;
  reserved_usd: number;
  daily_available_usd: number;
  monthly_available_usd: number;
};

export type PlatformBalance = {
  free_tier_allowance_usd: number;
  free_tier_used_usd: number;
  free_tier_remaining_usd: number;
  credits_balance_usd: number;
  reserved_usd: number;
};
