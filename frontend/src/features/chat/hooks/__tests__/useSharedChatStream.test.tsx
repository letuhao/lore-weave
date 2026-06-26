import { renderHook, act } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { useSharedChatStream } from '../useSharedChatStream';
import type { ChatLiveState } from '../../workers/chatStateHub';

// Mirrors useSharedCompositionStream.test — a fake SharedWorker so the consumer
// hook (which has no real worker in jsdom) can be driven via lastPort.onmessage.
type FakePort = {
  postMessage: ReturnType<typeof vi.fn>;
  onmessage: ((e: { data: unknown }) => void) | null;
  onmessageerror: (() => void) | null;
  start: ReturnType<typeof vi.fn>;
  close: ReturnType<typeof vi.fn>;
};
let lastPort: FakePort;
let lastWorker: FakeSharedWorker;

class FakeSharedWorker {
  port: FakePort;
  onerror: (() => void) | null = null;
  constructor() {
    this.port = { postMessage: vi.fn(), onmessage: null, onmessageerror: null, start: vi.fn(), close: vi.fn() };
    lastPort = this.port;
    lastWorker = this;
  }
}

vi.mock('../../api', () => ({
  chatApi: { toolResultsUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/tool-results` },
}));

beforeEach(() => { vi.stubGlobal('SharedWorker', FakeSharedWorker); });
afterEach(() => vi.unstubAllGlobals());

const EMPTY: ChatLiveState = {
  turnId: 0, streamingText: '', streamingReasoning: '', streamPhase: 'idle', thinkingElapsed: 0,
  streamStatus: 'idle', isComposing: false, toolCalls: [], activities: [], memoryMode: null,
  messageId: null, usage: {}, timing: {}, suspendedRun: null, initiatorNonce: null, ended: false, result: null, error: null,
};
const snap = (over: Partial<ChatLiveState> = {}): ChatLiveState => ({ ...EMPTY, ...over });
const emit = (s: ChatLiveState) => act(() => lastPort.onmessage!({ data: { type: 'state', state: s } }));

/** The nonce the hook stamped on its most recent start/toolResult postMessage —
 *  the hub echoes it onto the turn's snapshots, so the test echoes it too. */
const sentNonce = (): string => {
  const calls = lastPort.postMessage.mock.calls.map((c) => c[0] as { nonce?: string });
  const withNonce = calls.filter((m) => m.nonce);
  return withNonce[withNonce.length - 1]!.nonce!;
};

const ARGS = { sessionId: 's1', content: 'hi' };

describe('useSharedChatStream (M2 D-T5.4-CHAT-HOIST)', () => {
  it('does NOT create a worker when disabled (caller uses the in-process path)', () => {
    renderHook(() => useSharedChatStream('tok', false));
    expect(lastPort).toBeUndefined();
  });

  it('connects + starts the port and mirrors broadcast snapshots', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    expect(lastPort.start).toHaveBeenCalledTimes(1);
    emit(snap({ turnId: 1, streamingText: 'Hello', streamStatus: 'streaming' }));
    expect(result.current.streamingText).toBe('Hello');
    expect(result.current.streamStatus).toBe('streaming');
  });

  it('start() posts the command with the latest token + a nonce', () => {
    const { result, rerender } = renderHook(({ t }) => useSharedChatStream(t, true), { initialProps: { t: 'tok1' } });
    rerender({ t: 'tok2' });
    act(() => result.current.start(ARGS));
    expect(lastPort.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'start', args: ARGS, token: 'tok2', nonce: expect.any(String) }),
    );
  });

  // ── D-T5.4-CHAT-MULTIWINDOW: single-writer election (nonce-matched) ──────────
  it('claims initiatedTurnId for the turn carrying OUR nonce', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    expect(result.current.initiatedTurnId).toBe(0);
    act(() => result.current.start(ARGS));                       // we asked for the turn…
    emit(snap({ turnId: 1, initiatorNonce: sentNonce(), streamStatus: 'streaming' })); // hub echoes our nonce
    expect(result.current.initiatedTurnId).toBe(1);
  });

  it('does NOT claim a turn carrying a FOREIGN nonce (another window started it)', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    act(() => result.current.start(ARGS));   // we have a pending nonce…
    // …but a turn from ANOTHER window arrives first (foreign nonce). Even though our
    // nonce is pending, the mismatch keeps us an observer — the race the nonce closes.
    emit(snap({ turnId: 7, initiatorNonce: 'other-window:1', streamStatus: 'streaming', streamingText: 'from elsewhere' }));
    expect(result.current.streamingText).toBe('from elsewhere');
    expect(result.current.initiatedTurnId).toBe(0);
  });

  it('does NOT claim a late-join replay with a null nonce', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    emit(snap({ turnId: 3, initiatorNonce: null, streamStatus: 'streaming' }));
    expect(result.current.initiatedTurnId).toBe(0);
  });

  it('submitToolResult claims the resumed turn via its nonce', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    act(() => result.current.submitToolResult('s1', 'r1', 'c1', 'apply', 'text'));
    expect(lastPort.postMessage).toHaveBeenCalledWith(expect.objectContaining({
      type: 'toolResult',
      override: { url: 'http://test/v1/chat/sessions/s1/tool-results', body: { run_id: 'r1', tool_call_id: 'c1', outcome: 'apply', applied_text: 'text' } },
      token: 'tok',
      nonce: expect.any(String),
    }));
    emit(snap({ turnId: 2, initiatorNonce: sentNonce(), streamStatus: 'streaming' }));
    expect(result.current.initiatedTurnId).toBe(2);
  });

  it('stop() and clear() post their commands; clear is locally optimistic', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    emit(snap({ turnId: 1, streamingText: 'text' }));
    act(() => result.current.stop());
    expect(lastPort.postMessage).toHaveBeenCalledWith({ type: 'stop' });
    act(() => result.current.clear());
    expect(lastPort.postMessage).toHaveBeenCalledWith({ type: 'clear' });
    expect(result.current.streamingText).toBe('');
  });

  it('closes its port on unmount', () => {
    const { unmount } = renderHook(() => useSharedChatStream('tok', true));
    const port = lastPort;
    unmount();
    expect(port.close).toHaveBeenCalledTimes(1);
  });

  it('surfaces a worker error instead of hanging silently', () => {
    const { result } = renderHook(() => useSharedChatStream('tok', true));
    expect(result.current.error).toBeNull();
    act(() => lastWorker.onerror!());
    expect(result.current.error).toMatch(/worker failed/i);
  });
});
