import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// usageApi owns the network; useAuth + sonner are ambient. Stub all three.
const getGuardrailMock = vi.fn();
const getPlatformBalanceMock = vi.fn();
const patchGuardrailMock = vi.fn();
vi.mock('./api', () => ({
  usageApi: {
    getGuardrail: (...a: unknown[]) => getGuardrailMock(...a),
    getPlatformBalance: (...a: unknown[]) => getPlatformBalanceMock(...a),
    patchGuardrail: (...a: unknown[]) => patchGuardrailMock(...a),
  },
}));
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useBudget } from './useBudget';

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
  vi.clearAllMocks();
});

describe('useBudget', () => {
  it('fetches the guardrail + platform balance on mount', async () => {
    getGuardrailMock.mockResolvedValue(guardrail);
    getPlatformBalanceMock.mockResolvedValue(platform);

    const { result } = renderHook(() => useBudget());
    expect(result.current.loading).toBe(true);

    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.guardrail).toEqual(guardrail);
    expect(result.current.platform).toEqual(platform);
  });

  it('saveLimits PATCHes and folds the server response into guardrail', async () => {
    getGuardrailMock.mockResolvedValue(guardrail);
    getPlatformBalanceMock.mockResolvedValue(platform);
    const updated = { ...guardrail, daily_limit_usd: 99 };
    patchGuardrailMock.mockResolvedValue(updated);

    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.saveLimits(99, 100);
    });
    expect(ok).toBe(true);
    expect(patchGuardrailMock).toHaveBeenCalledWith('tok', {
      daily_limit_usd: 99,
      monthly_limit_usd: 100,
    });
    // The hook must adopt the server's authoritative row, not the inputs.
    expect(result.current.guardrail).toEqual(updated);
  });

  it('saveLimits returns false and keeps the old guardrail on error', async () => {
    getGuardrailMock.mockResolvedValue(guardrail);
    getPlatformBalanceMock.mockResolvedValue(platform);
    patchGuardrailMock.mockRejectedValue(new Error('boom'));

    const { result } = renderHook(() => useBudget());
    await waitFor(() => expect(result.current.loading).toBe(false));

    let ok: boolean | undefined;
    await act(async () => {
      ok = await result.current.saveLimits(1, 2);
    });
    expect(ok).toBe(false);
    expect(result.current.guardrail).toEqual(guardrail);
  });
});
