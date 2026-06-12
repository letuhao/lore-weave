import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

// useBudget owns the network; stub it so the panel test is pure-render.
const useBudgetMock = vi.fn();
vi.mock('./useBudget', () => ({
  useBudget: () => useBudgetMock(),
}));

import { BudgetPanel } from './BudgetPanel';

const guardrail = {
  daily_limit_usd: 10,
  monthly_limit_usd: 100,
  daily_spent_usd: 3,
  monthly_spent_usd: 20,
  reserved_usd: 1,
  daily_available_usd: 6,
  monthly_available_usd: 79,
};

const platform = {
  free_tier_allowance_usd: 50,
  free_tier_used_usd: 12,
  free_tier_remaining_usd: 38,
  credits_balance_usd: 5,
  reserved_usd: 0,
};

beforeEach(() => {
  useBudgetMock.mockReset();
});

describe('BudgetPanel', () => {
  it('shows a loading state', () => {
    useBudgetMock.mockReturnValue({
      guardrail: null,
      platform: null,
      loading: true,
      saving: false,
      saveLimits: vi.fn(),
    });
    render(<BudgetPanel />);
    // The global react-i18next mock returns the key, so assert on keys.
    expect(screen.getByText('budget.loading')).toBeInTheDocument();
  });

  it('renders the daily/monthly limits and the platform balance', () => {
    useBudgetMock.mockReturnValue({
      guardrail,
      platform,
      loading: false,
      saving: false,
      saveLimits: vi.fn(),
    });
    render(<BudgetPanel />);
    expect(screen.getByText('budget.daily')).toBeInTheDocument();
    expect(screen.getByText('budget.monthly')).toBeInTheDocument();
    // Daily "used" = spent 3 + reserved 1 = $4.00.
    expect(screen.getByText(/\$4\.00/)).toBeInTheDocument();
    expect(screen.getByText('budget.platform_balance')).toBeInTheDocument();
  });

  it('validates the edit form and saves valid limits', () => {
    const saveLimits = vi.fn().mockResolvedValue(true);
    useBudgetMock.mockReturnValue({
      guardrail,
      platform,
      loading: false,
      saving: false,
      saveLimits,
    });
    render(<BudgetPanel />);

    fireEvent.click(screen.getByText('budget.edit_limits'));
    const dailyInput = screen.getByLabelText('budget.daily_limit_usd');

    // A zero limit is rejected — message shown, Save disabled.
    fireEvent.change(dailyInput, { target: { value: '0' } });
    expect(screen.getByText('budget.limits_invalid')).toBeInTheDocument();
    expect(screen.getByText('budget.save')).toBeDisabled();

    // A valid edit saves; monthly was untouched → its prefilled 100 stands.
    fireEvent.change(dailyInput, { target: { value: '15' } });
    fireEvent.click(screen.getByText('budget.save'));
    expect(saveLimits).toHaveBeenCalledWith(15, 100);
  });
});
