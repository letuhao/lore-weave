// D-A3-PROACTIVE — the proactive controller: reads the chat opt-in gate (fail-closed), and enabling sets
// BOTH the gate AND the schedule row so it can never silently no-op.
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

const getAiPrefs = vi.fn();
const setProactiveEnabled = vi.fn();
const setSchedule = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({
  assistantApi: {
    getAiPrefs: (...a: unknown[]) => getAiPrefs(...a),
    setProactiveEnabled: (...a: unknown[]) => setProactiveEnabled(...a),
    setSchedule: (...a: unknown[]) => setSchedule(...a),
  },
}));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import { useProactiveSetting } from '../useProactiveSetting';

beforeEach(() => {
  getAiPrefs.mockReset();
  setProactiveEnabled.mockReset();
  setSchedule.mockReset();
});

describe('useProactiveSetting (D-A3-PROACTIVE)', () => {
  it('reads the proactive_enabled gate, fail-closed when absent', async () => {
    getAiPrefs.mockResolvedValueOnce({ assistant: {} });
    const { result } = renderHook(() => useProactiveSetting());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.enabled).toBe(false);
  });

  it('reflects an enabled gate', async () => {
    getAiPrefs.mockResolvedValueOnce({ assistant: { proactive_enabled: true } });
    const { result } = renderHook(() => useProactiveSetting());
    await waitFor(() => expect(result.current.enabled).toBe(true));
  });

  it('enabling sets BOTH the chat gate AND the schedule row (never one alone)', async () => {
    getAiPrefs.mockResolvedValueOnce({ assistant: {} }); // initial OFF
    setProactiveEnabled.mockResolvedValueOnce({});
    setSchedule.mockResolvedValueOnce({});
    getAiPrefs.mockResolvedValueOnce({ assistant: { proactive_enabled: true } }); // re-read
    const { result } = renderHook(() => useProactiveSetting());
    await waitFor(() => expect(result.current.loading).toBe(false));

    await act(async () => { await result.current.setProactive(true, 'UTC'); });
    expect(setProactiveEnabled).toHaveBeenCalledWith('tok', true);
    expect(setSchedule).toHaveBeenCalledWith('tok', { job_kind: 'proactive_nudge', enabled: true, timezone: 'UTC' });
    // On ENABLE the gate is set LAST (after the schedule), so a schedule failure can't leave the gate ON
    // with no trigger — the silent-no-op this control exists to avoid.
    expect(setSchedule.mock.invocationCallOrder[0]).toBeLessThan(setProactiveEnabled.mock.invocationCallOrder[0]);
    expect(result.current.enabled).toBe(true); // reflects the server re-read
  });

  it('on DISABLE the gate is turned off FIRST (stop firing/spending before touching the schedule)', async () => {
    getAiPrefs.mockResolvedValueOnce({ assistant: { proactive_enabled: true } });
    setProactiveEnabled.mockResolvedValueOnce({});
    setSchedule.mockResolvedValueOnce({});
    getAiPrefs.mockResolvedValueOnce({ assistant: { proactive_enabled: false } });
    const { result } = renderHook(() => useProactiveSetting());
    await waitFor(() => expect(result.current.enabled).toBe(true));

    await act(async () => { await result.current.setProactive(false, 'UTC'); });
    expect(setProactiveEnabled.mock.invocationCallOrder[0]).toBeLessThan(setSchedule.mock.invocationCallOrder[0]);
    expect(result.current.enabled).toBe(false);
  });

  it('a read failure leaves it OFF (fail-closed)', async () => {
    getAiPrefs.mockRejectedValueOnce(new Error('down'));
    const { result } = renderHook(() => useProactiveSetting());
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.enabled).toBe(false);
  });
});
