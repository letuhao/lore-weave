import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';
import type { ChatSession } from '../../types';

// W3 — useCompactSession: the "Compact now" controller. API mapping, toasts,
// session refresh on success, pending gating, and the failure path.

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock('sonner', () => ({
  toast: {
    success: (...a: unknown[]) => toastSuccess(...a),
    error: (...a: unknown[]) => toastError(...a),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k: string, o?: Record<string, unknown>) => (o ? `${k}:${JSON.stringify(o)}` : k) }),
}));

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const compactMock = vi.fn();
const getSessionMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    compactSession: (...a: unknown[]) => compactMock(...a),
    getSession: (...a: unknown[]) => getSessionMock(...a),
  },
}));

const updateActiveSession = vi.fn();
let activeSession: ChatSession | null;
vi.mock('../../providers', () => ({
  useChatSession: () => ({ activeSession, updateActiveSession }),
}));

import { useCompactSession } from '../useCompactSession';

const SESSION = {
  session_id: 's-1',
  compacted_before_seq: null,
} as unknown as ChatSession;

const RESULT = {
  summary_tokens: 120,
  compacted_message_count: 4,
  compacted_before_seq: 5,
  tokens_before_estimate: 4000,
  tokens_after_estimate: 900,
};

describe('useCompactSession', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    activeSession = SESSION;
  });

  it('maps the call: instructions trimmed in, omitted when blank', async () => {
    compactMock.mockResolvedValue(RESULT);
    getSessionMock.mockResolvedValue({ ...SESSION, compacted_before_seq: 5 });
    const { result } = renderHook(() => useCompactSession());

    act(() => result.current.onCompact('  keep the prophecy  '));
    await waitFor(() => expect(result.current.pending).toBe(false));
    expect(compactMock).toHaveBeenCalledWith('tok-test', 's-1', { instructions: 'keep the prophecy' });

    act(() => result.current.onCompact('   '));
    await waitFor(() => expect(compactMock).toHaveBeenCalledTimes(2));
    expect(compactMock).toHaveBeenLastCalledWith('tok-test', 's-1', {});
  });

  it('success → toast with before/after + session refreshed from the server', async () => {
    compactMock.mockResolvedValue(RESULT);
    const fresh = { ...SESSION, compacted_before_seq: 5 };
    getSessionMock.mockResolvedValue(fresh);
    const { result } = renderHook(() => useCompactSession());

    act(() => result.current.onCompact(''));
    expect(result.current.pending).toBe(true); // pending while in flight
    await waitFor(() => expect(result.current.pending).toBe(false));

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(String(toastSuccess.mock.calls[0][0])).toContain('context_panel.compact.success');
    expect(getSessionMock).toHaveBeenCalledWith('tok-test', 's-1');
    expect(updateActiveSession).toHaveBeenCalledWith(fresh);
  });

  it('success but GET refresh fails → marker patched locally', async () => {
    compactMock.mockResolvedValue(RESULT);
    getSessionMock.mockRejectedValue(new Error('blip'));
    const { result } = renderHook(() => useCompactSession());

    act(() => result.current.onCompact(''));
    await waitFor(() => expect(result.current.pending).toBe(false));

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(updateActiveSession).toHaveBeenCalledWith({ ...SESSION, compacted_before_seq: 5 });
  });

  it('failure → error toast, no session update', async () => {
    compactMock.mockRejectedValue(new Error('nothing to compact'));
    const { result } = renderHook(() => useCompactSession());

    act(() => result.current.onCompact('keep names'));
    await waitFor(() => expect(result.current.pending).toBe(false));

    expect(toastError).toHaveBeenCalledTimes(1);
    expect(String(toastError.mock.calls[0][0])).toContain('context_panel.compact.failed');
    expect(updateActiveSession).not.toHaveBeenCalled();
  });

  it('no active session → no call', () => {
    activeSession = null;
    const { result } = renderHook(() => useCompactSession());
    act(() => result.current.onCompact('x'));
    expect(compactMock).not.toHaveBeenCalled();
    expect(result.current.compactedBeforeSeq).toBeNull();
  });

  it('exposes the session compact marker', () => {
    activeSession = { ...SESSION, compacted_before_seq: 9 };
    const { result } = renderHook(() => useCompactSession());
    expect(result.current.compactedBeforeSeq).toBe(9);
  });
});
