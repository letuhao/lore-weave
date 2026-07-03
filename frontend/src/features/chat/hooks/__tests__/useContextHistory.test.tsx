import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import type { ChatSession } from '../../types';

// W1-residual — useContextHistory: the per-turn token-history controller.
// Fetches only when enabled, maps the API rows into typed points, and exposes
// loading/error state.

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const getContextHistoryMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    getContextHistory: (...a: unknown[]) => getContextHistoryMock(...a),
  },
}));

let activeSession: ChatSession | null;
vi.mock('../../providers', () => ({
  useChatSession: () => ({ activeSession }),
}));

import { useContextHistory } from '../useContextHistory';

const SESSION_ID = 'sess-123';

beforeEach(() => {
  getContextHistoryMock.mockReset();
  activeSession = { session_id: SESSION_ID } as ChatSession;
});

const SERIES = {
  items: [
    { sequence_num: 1, created_at: 't1', input_tokens: 1000, output_tokens: 50, breakdown: { system_prompt: 100, history: 10 } },
    { sequence_num: 3, created_at: 't3', input_tokens: 1200, output_tokens: 60, breakdown: { system_prompt: 120, history: 300 } },
  ],
};

describe('useContextHistory', () => {
  it('does NOT fetch while disabled', () => {
    renderHook(() => useContextHistory(false));
    expect(getContextHistoryMock).not.toHaveBeenCalled();
  });

  it('fetches + maps the series when enabled', async () => {
    getContextHistoryMock.mockResolvedValue(SERIES);
    const { result } = renderHook(() => useContextHistory(true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(getContextHistoryMock).toHaveBeenCalledWith('tok-test', SESSION_ID);
    expect(result.current.points.map((p) => p.sequence_num)).toEqual([1, 3]);
    expect(result.current.points[1].breakdown.history).toBe(300);
    expect(result.current.error).toBeNull();
  });

  it('surfaces an error and empties the series on failure', async () => {
    getContextHistoryMock.mockRejectedValue(new Error('boom'));
    const { result } = renderHook(() => useContextHistory(true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.error).toBe('boom');
    expect(result.current.points).toEqual([]);
  });

  it('degrades a malformed payload to an empty series', async () => {
    getContextHistoryMock.mockResolvedValue({});
    const { result } = renderHook(() => useContextHistory(true));
    await waitFor(() => expect(result.current.loading).toBe(false));
    expect(result.current.points).toEqual([]);
  });

  it('does not fetch when there is no active session', () => {
    activeSession = null;
    renderHook(() => useContextHistory(true));
    expect(getContextHistoryMock).not.toHaveBeenCalled();
  });
});
