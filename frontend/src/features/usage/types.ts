export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio';
// S4c: 'recorded' is the audit-only decision (token-quota deduction retired; USD
// enforcement is the spend guardrail). 'quota'|'credits'|'rejected' are kept for
// historical usage_logs rows written before the retirement.
export type BillingDecision = 'quota' | 'credits' | 'rejected' | 'recorded';
export type RequestStatus = 'success' | 'provider_error' | 'billing_rejected';
export type Purpose = 'translation' | 'chat' | 'chunk_edit' | 'image_gen' | 'unknown';

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
