import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { PropsWithChildren } from 'react';

const useAuthMock = vi.fn();
vi.mock('@/auth', () => ({
  useAuth: () => useAuthMock(),
}));

const getUserCostsMock = vi.fn();
vi.mock('../../api', async () => {
  const actual = await vi.importActual<Record<string, unknown>>('../../api');
  return {
    ...actual,
    knowledgeApi: { getUserCosts: (...args: unknown[]) => getUserCostsMock(...args) },
  };
});

import { useUserCosts } from '../useUserCosts';

function wrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: PropsWithChildren) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const SAMPLE = {
  all_time_usd: '42.50',
  current_month_usd: '7.25',
  monthly_budget_usd: '20.00',
  monthly_remaining_usd: '12.75',
};

describe('useUserCosts', () => {
  beforeEach(() => {
    useAuthMock.mockReset();
    getUserCostsMock.mockReset();
  });

  it('returns costs from the API when authenticated', async () => {
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
    getUserCostsMock.mockResolvedValue(SAMPLE);
    const { result } = renderHook(() => useUserCosts(), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.costs).toEqual(SAMPLE);
    });
    expect(getUserCostsMock).toHaveBeenCalledWith('tok');
  });

  it('is disabled when no accessToken (returns null costs, never calls API)', async () => {
    useAuthMock.mockReturnValue({ accessToken: null, user: null });
    getUserCostsMock.mockResolvedValue(SAMPLE);
    const { result } = renderHook(() => useUserCosts(), { wrapper: wrapper() });
    // Give React Query a chance to fire if it were going to.
    await new Promise((r) => setTimeout(r, 20));
    expect(result.current.costs).toBeNull();
    expect(getUserCostsMock).not.toHaveBeenCalled();
  });

  it('surfaces API errors via the error field', async () => {
    useAuthMock.mockReturnValue({
      accessToken: 'tok',
      user: { user_id: 'u1', email: 'a@b', display_name: null, avatar_url: null },
    });
    const boom = new Error('cost fetch failed');
    getUserCostsMock.mockRejectedValue(boom);
    const { result } = renderHook(() => useUserCosts(), { wrapper: wrapper() });
    await waitFor(() => {
      expect(result.current.error).toBe(boom);
    });
  });
});
