import { beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { UsageLogsPage } from './UsageLogsPage';

const listUsageLogs = vi.fn();
const getAccountBalance = vi.fn();
const getUsageSummary = vi.fn();

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'token-1' }),
}));

vi.mock('@/features/ai-models/api', () => ({
  aiModelsApi: {
    listUsageLogs: (...args: unknown[]) => listUsageLogs(...args),
    getAccountBalance: (...args: unknown[]) => getAccountBalance(...args),
    getUsageSummary: (...args: unknown[]) => getUsageSummary(...args),
  },
}));

describe('UsageLogsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    cleanup();
  });

  it('renders usage summary, balance, and log items', async () => {
    listUsageLogs.mockResolvedValueOnce({
      items: [
        {
          usage_log_id: 'log-1',
          provider_kind: 'openai',
          model_source: 'user_model',
          billing_decision: 'quota',
          total_tokens: 120,
          total_cost_usd: 0.0123,
          request_status: 'success',
        },
      ],
      total: 1,
    });
    getAccountBalance.mockResolvedValueOnce({
      tier_name: 'starter',
      month_quota_tokens: 100000,
      month_quota_remaining_tokens: 99000,
      credits_balance: 500,
    });
    getUsageSummary.mockResolvedValueOnce({
      request_count: 1,
      total_tokens: 120,
      total_cost_usd: 0.0123,
    });

    render(
      <MemoryRouter>
        <UsageLogsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('starter')).toBeInTheDocument();
    expect(await screen.findByText('Requests: 1')).toBeInTheDocument();
    expect(await screen.findByText(/openai/)).toBeInTheDocument();
    expect(await screen.findByText(/Tokens: 120/)).toBeInTheDocument();
  });

  it('renders error state when request fails', async () => {
    listUsageLogs.mockRejectedValueOnce(new Error('usage load failed'));
    getAccountBalance.mockResolvedValueOnce({});
    getUsageSummary.mockResolvedValueOnce({});

    render(
      <MemoryRouter>
        <UsageLogsPage />
      </MemoryRouter>,
    );

    expect(await screen.findByText('usage load failed')).toBeInTheDocument();
  });
});
