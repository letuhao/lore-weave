export type ProviderKind = 'openai' | 'anthropic' | 'ollama' | 'lm_studio';
export type BillingDecision = 'quota' | 'credits' | 'rejected';
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
  by_provider: ProviderBreakdown[];
  by_purpose: PurposeBreakdown[];
  daily: DailyBreakdown[];
};

export type AccountBalance = {
  tier_name: string;
  month_quota_tokens: number;
  month_quota_remaining_tokens: number;
  credits_balance: number;
  billing_policy_version: string;
};

export type UsageFilters = {
  provider_kind?: ProviderKind;
  request_status?: RequestStatus;
  purpose?: Purpose;
  from?: string;
  to?: string;
};

export type Period = 'last_24h' | 'last_7d' | 'last_30d' | 'last_90d';
