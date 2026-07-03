import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// M2 (D-T5.4-CHAT-HOIST / D-T5.4-CHAT-MULTIWINDOW) — the SharedWorker bridge inside
// useChatMessages. The hub fans the SAME terminal snapshot to every window, so the
// per-turn side-effects (assembled-message append + onStreamEnd fan-out) must run
// ONLY in the window that initiated the turn (worker.turnId === worker.initiatedTurnId);
// observer windows converge via refetch and never double-fire the fan-out.

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-test' }) }));

const listMessagesMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    listMessages: (...a: unknown[]) => listMessagesMock(...a),
    getLatestContextBudget: () => Promise.resolve({ budget: null }),
    messagesUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/messages`,
    toolResultsUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/tool-results`,
  },
}));

// The provider is mocked so the hook takes the worker path; `shared` is a plain
// controllable snapshot object we swap + rerender to drive the bridge effect.
let shared: Record<string, unknown> | null = null;
vi.mock('../../providers/ChatLiveStateContext', () => ({
  useChatLiveStateOptional: () => (shared ? { useWorker: true, shared } : null),
}));

import { useChatMessages } from '../useChatMessages';

const RESULT = {
  content: 'Done.', reasoning: '', toolCalls: [], activities: [],
  messageId: 'm1', usage: {}, timing: {},
};

const sharedSnap = (over: Record<string, unknown> = {}) => ({
  turnId: 0, initiatedTurnId: 0, streamingText: '', streamingReasoning: '', streamPhase: 'idle',
  thinkingElapsed: 0, streamStatus: 'idle', isComposing: false, toolCalls: [], activities: [],
  memoryMode: null, messageId: null, usage: {}, timing: {}, suspendedRun: null, ended: false,
  result: null, error: null,
  start: vi.fn(), stop: vi.fn(), clear: vi.fn(), submitToolResult: vi.fn(), submitToolResolve: vi.fn(),
  ...over,
});

describe('useChatMessages worker bridge — single-writer election', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
    shared = null;
  });

  it('WRITER (initiated the turn) appends the assembled message and fires onStreamEnd', async () => {
    shared = sharedSnap();
    const onEnd = vi.fn();
    const { result, rerender } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { result.current.onStreamEndRef.current = onEnd; });

    // Clean-end snapshot for a turn we own (turnId === initiatedTurnId).
    shared = sharedSnap({ turnId: 1, initiatedTurnId: 1, ended: true, result: RESULT, streamStatus: 'idle' });
    rerender();

    await waitFor(() => expect(result.current.messages.some((m) => m.role === 'assistant')).toBe(true));
    expect(result.current.messages.find((m) => m.role === 'assistant')!.content).toBe('Done.');
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('OBSERVER (foreign turn) does NOT blind-append, but DOES refetch AND fire its own onStreamEnd', async () => {
    shared = sharedSnap();
    const onEnd = vi.fn();
    const { result, rerender } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { result.current.onStreamEndRef.current = onEnd; });
    const callsBefore = listMessagesMock.mock.calls.length;

    // A turn started in ANOTHER window: initiatedTurnId stays 0 ≠ turnId. This is also
    // the ORPHAN case (D-T5.4-CHAT-MULTIWINDOW-ORPHAN) — the initiator may have closed,
    // so the observer must keep its own session/facts tracked, not skip the fan-out.
    shared = sharedSnap({ turnId: 9, initiatedTurnId: 0, ended: true, result: RESULT, streamStatus: 'idle' });
    rerender();

    // Converges via refetch (server SSOT), no blind append…
    await waitFor(() => expect(listMessagesMock.mock.calls.length).toBeGreaterThan(callsBefore));
    expect(result.current.messages.some((m) => m.role === 'assistant')).toBe(false);
    // …and fires its OWN per-window fan-out (session refresh + pending-facts) so the
    // turn stays tracked/resumable even if the initiator window is gone.
    expect(onEnd).toHaveBeenCalledTimes(1);
  });

  it('compaction replay guard: a late-joining tab records a stale compaction WITHOUT toasting', async () => {
    const COMPACTION = {
      triggered: true, tool_results_cleared: 0, turns_truncated: 2, summarized: true,
      summarize_failed: false, overflowed: false, tokens_before: 9000, tokens_after: 4000,
    };
    shared = sharedSnap();
    const onCompaction = vi.fn();
    const { result, rerender } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { result.current.onCompactionRef.current = onCompaction; });

    // The hub's addPort full-state replay: a PAST turn's compaction arrives on
    // an idle snapshot (the turn finished long ago) — record, never toast.
    shared = sharedSnap({ turnId: 3, compaction: COMPACTION, streamStatus: 'idle' });
    rerender();
    expect(onCompaction).not.toHaveBeenCalled();

    // A LIVE compaction later (turnId changed while streaming) still toasts…
    shared = sharedSnap({ turnId: 4, compaction: COMPACTION, streamStatus: 'streaming' });
    rerender();
    expect(onCompaction).toHaveBeenCalledTimes(1);
    // …exactly once per turn (snapshot rebroadcast does not re-fire).
    shared = sharedSnap({ turnId: 4, compaction: COMPACTION, streamStatus: 'streaming', streamingText: 'more' });
    rerender();
    expect(onCompaction).toHaveBeenCalledTimes(1);
  });

  it('fires the terminal branch only ONCE per turn within a window (per-window dedupe)', async () => {
    shared = sharedSnap();
    const onEnd = vi.fn();
    const { result, rerender } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => { result.current.onStreamEndRef.current = onEnd; });

    const ended = sharedSnap({ turnId: 1, initiatedTurnId: 1, ended: true, result: RESULT, streamStatus: 'idle' });
    shared = ended; rerender();
    // Re-broadcast of the SAME terminal snapshot (the hub fans many times) must not re-fire.
    shared = sharedSnap({ ...ended, streamingText: 'noise' }); rerender();
    await waitFor(() => expect(onEnd).toHaveBeenCalledTimes(1));
    expect(result.current.messages.filter((m) => m.role === 'assistant')).toHaveLength(1);
  });
});
