import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// Verify-by-EFFECT for the §11a "live update … poll" item: the controller refetches
// the trace on an interval (and on window focus) while enabled — a finished turn
// appears without a manual click. getContextTrace is called synchronously (before
// its promise resolves), so call-counting under fake timers proves the poll fires.

const listSessions = vi.fn();
const getContextTrace = vi.fn();
vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok' }) }));
vi.mock('../../api', () => ({
  chatApi: {
    listSessions: (...a: unknown[]) => listSessions(...a),
    getContextTrace: (...a: unknown[]) => getContextTrace(...a),
  },
}));

import { useContextTrace, POLL_INTERVAL_MS } from '../useContextTrace';

describe('useContextTrace live update', () => {
  beforeEach(() => {
    listSessions.mockResolvedValue({ items: [{ session_id: 's1', title: 'S1' }] });
    getContextTrace.mockResolvedValue({ items: [] });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('polls the trace endpoint on an interval while enabled', async () => {
    vi.useFakeTimers();
    await act(async () => {
      renderHook(() => useContextTrace(true, 's1'));
      await Promise.resolve();
    });
    const initial = getContextTrace.mock.calls.length;
    expect(initial).toBeGreaterThanOrEqual(1); // the first fetch ran
    await act(async () => {
      vi.advanceTimersByTime(POLL_INTERVAL_MS + 50);
      await Promise.resolve();
    });
    expect(getContextTrace.mock.calls.length).toBeGreaterThan(initial); // a poll tick refetched
  });

  it('refetches on window focus (returning to the tab shows the latest)', async () => {
    vi.useFakeTimers();
    await act(async () => {
      renderHook(() => useContextTrace(true, 's1'));
      await Promise.resolve();
    });
    const before = getContextTrace.mock.calls.length;
    await act(async () => {
      window.dispatchEvent(new Event('focus'));
      await Promise.resolve();
    });
    expect(getContextTrace.mock.calls.length).toBeGreaterThan(before);
  });

  it('does NOT poll while disabled (mounted-but-hidden gates the fetch)', async () => {
    vi.useFakeTimers();
    await act(async () => {
      renderHook(() => useContextTrace(false, 's1'));
      await Promise.resolve();
    });
    await act(async () => {
      vi.advanceTimersByTime(POLL_INTERVAL_MS * 2);
      await Promise.resolve();
    });
    expect(getContextTrace).not.toHaveBeenCalled();
  });
});
