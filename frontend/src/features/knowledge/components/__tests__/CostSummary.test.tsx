import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { UserCostSummary } from '../../api';

vi.mock('@/auth', () => ({
  useAuth: () => ({
    accessToken: 'tok-test',
    user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
  }),
}));

const setUserBudgetMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: {
      setUserBudget: (...args: unknown[]) => setUserBudgetMock(...args),
    },
  };
});

const toastErrorMock = vi.fn();
vi.mock('sonner', () => ({
  toast: { error: (...args: unknown[]) => toastErrorMock(...args) },
}));

const useUserCostsMock = vi.fn();
vi.mock('../../hooks/useUserCosts', () => ({
  useUserCosts: () => useUserCostsMock(),
}));

import { CostSummary } from '../CostSummary';

function setHookState(overrides: {
  costs?: UserCostSummary | null;
  isLoading?: boolean;
  error?: Error | null;
}) {
  useUserCostsMock.mockReturnValue({
    costs: overrides.costs ?? null,
    isLoading: overrides.isLoading ?? false,
    error: overrides.error ?? null,
  });
}

function renderCard() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const utils = render(
    <QueryClientProvider client={qc}>
      <CostSummary />
    </QueryClientProvider>,
  );
  return { ...utils, qc };
}

describe('CostSummary', () => {
  beforeEach(() => {
    useUserCostsMock.mockReset();
    setUserBudgetMock.mockReset();
    toastErrorMock.mockReset();
  });

  it('renders a loading placeholder when isLoading', () => {
    setHookState({ isLoading: true });
    renderCard();
    expect(screen.getByTestId('cost-summary-loading')).toBeInTheDocument();
  });

  it('renders an error alert when the hook errors', () => {
    setHookState({ error: new Error('network down') });
    renderCard();
    expect(screen.getByTestId('cost-summary-error')).toHaveTextContent('network down');
  });

  it('omits the budget row and progress bar when no cap is set', () => {
    setHookState({
      costs: {
        all_time_usd: '40.00',
        current_month_usd: '5.00',
        monthly_budget_usd: null,
        monthly_remaining_usd: null,
      },
    });
    renderCard();
    expect(screen.getByTestId('cost-summary-month')).toBeInTheDocument();
    expect(screen.getByTestId('cost-summary-alltime')).toBeInTheDocument();
    expect(screen.queryByTestId('cost-summary-budget')).toBeNull();
    expect(screen.queryByTestId('cost-summary-bar')).toBeNull();
  });

  it('renders a budget row + progress bar when cap is set', () => {
    setHookState({
      costs: {
        all_time_usd: '40.00',
        current_month_usd: '5.00',
        monthly_budget_usd: '20.00',
        monthly_remaining_usd: '15.00',
      },
    });
    renderCard();
    expect(screen.getByTestId('cost-summary-budget')).toBeInTheDocument();
    const bar = screen.getByTestId('cost-summary-bar');
    expect(bar.getAttribute('data-pct')).toBe('25'); // 5/20 = 25%
  });

  it('colours the bar by spend thresholds', () => {
    // <80%: primary
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '5',
        monthly_budget_usd: '20', monthly_remaining_usd: '15',
      },
    });
    const { unmount } = renderCard();
    let inner = screen.getByTestId('cost-summary-bar').firstElementChild;
    expect(inner?.className).toMatch(/bg-primary/);
    unmount();

    // 80%+ (not yet 100): amber
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '18',
        monthly_budget_usd: '20', monthly_remaining_usd: '2',
      },
    });
    const { unmount: u2 } = renderCard();
    inner = screen.getByTestId('cost-summary-bar').firstElementChild;
    expect(inner?.className).toMatch(/bg-amber-500/);
    unmount;
    u2();

    // 100%+: destructive
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '25',
        monthly_budget_usd: '20', monthly_remaining_usd: '0',
      },
    });
    renderCard();
    inner = screen.getByTestId('cost-summary-bar').firstElementChild;
    expect(inner?.className).toMatch(/bg-destructive/);
  });

  it('opens the edit dialog when the edit button is clicked', () => {
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '0',
        monthly_budget_usd: null, monthly_remaining_usd: null,
      },
    });
    renderCard();
    expect(screen.queryByTestId('cost-summary-input')).toBeNull();
    fireEvent.click(screen.getByTestId('cost-summary-edit'));
    expect(screen.getByTestId('cost-summary-input')).toBeInTheDocument();
  });

  it('saves a new budget via PUT and invalidates the cost query on success', async () => {
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '0',
        monthly_budget_usd: null, monthly_remaining_usd: null,
      },
    });
    setUserBudgetMock.mockResolvedValue({ user_id: 'u1', ai_monthly_budget_usd: '15.00' });
    const { qc } = renderCard();
    const spy = vi.spyOn(qc, 'invalidateQueries');
    fireEvent.click(screen.getByTestId('cost-summary-edit'));
    fireEvent.change(screen.getByTestId('cost-summary-input'), { target: { value: '15.00' } });
    fireEvent.click(screen.getByTestId('cost-summary-save'));
    await waitFor(() => {
      expect(setUserBudgetMock).toHaveBeenCalledWith(
        { ai_monthly_budget_usd: '15.00' },
        'tok-test',
      );
    });
    await waitFor(() => {
      expect(spy).toHaveBeenCalledWith({ queryKey: ['knowledge-costs', 'u1'] });
    });
  });

  it('toasts and keeps dialog open when save fails', async () => {
    setHookState({
      costs: {
        all_time_usd: '0', current_month_usd: '0',
        monthly_budget_usd: null, monthly_remaining_usd: null,
      },
    });
    setUserBudgetMock.mockRejectedValue(new Error('boom'));
    renderCard();
    fireEvent.click(screen.getByTestId('cost-summary-edit'));
    fireEvent.change(screen.getByTestId('cost-summary-input'), { target: { value: '10' } });
    fireEvent.click(screen.getByTestId('cost-summary-save'));
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalled();
    });
    // vitest.setup.ts's i18n mock returns dotted keys verbatim
    // (templates like "{{error}}" don't live in the key string), so
    // asserting the rendered toast text includes "boom" isn't possible
    // here — the template/interpolation contract is enforced by the
    // JOBS_KEYS iterator in projectState.test.ts.
    expect(toastErrorMock.mock.calls[0][0]).toBe('jobs.costSummary.saveFailed');
    // Dialog stays open on failure.
    expect(screen.getByTestId('cost-summary-input')).toBeInTheDocument();
  });
});
