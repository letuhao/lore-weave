import { apiJson } from '@/api';
import type {
  UsageLog,
  UsageLogDetail,
  UsageSummary,
  AccountBalance,
  UsageFilters,
  Period,
} from './types';

export const usageApi = {
  listLogs(
    token: string,
    params: { limit?: number; offset?: number } & UsageFilters = {},
  ) {
    const qs = new URLSearchParams();
    if (params.limit !== undefined) qs.set('limit', String(params.limit));
    if (params.offset !== undefined) qs.set('offset', String(params.offset));
    if (params.provider_kind) qs.set('provider_kind', params.provider_kind);
    if (params.request_status) qs.set('request_status', params.request_status);
    if (params.purpose) qs.set('purpose', params.purpose);
    if (params.from) qs.set('from', params.from);
    if (params.to) qs.set('to', params.to);
    const q = qs.toString();
    return apiJson<{ items: UsageLog[]; total: number; limit: number; offset: number }>(
      `/v1/model-billing/usage-logs${q ? `?${q}` : ''}`,
      { token },
    );
  },

  getLogDetail(token: string, usageLogId: string) {
    return apiJson<UsageLogDetail>(
      `/v1/model-billing/usage-logs/${usageLogId}`,
      { token },
    );
  },

  getSummary(token: string, period: Period = 'last_7d') {
    return apiJson<UsageSummary>(
      `/v1/model-billing/usage-summary?period=${period}`,
      { token },
    );
  },

  getBalance(token: string) {
    return apiJson<AccountBalance>('/v1/model-billing/account-balance', { token });
  },
};
