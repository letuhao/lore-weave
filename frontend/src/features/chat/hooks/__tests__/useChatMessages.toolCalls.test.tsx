import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// K21-C (D2) + ARCH-1 C4: useChatMessages must accumulate executed memory tool
// calls and attach them to the locally-appended assistant message. The stream
// now speaks the AG-UI protocol — a tool call is framed across TOOL_CALL_START
// (name) and TOOL_CALL_RESULT (ok, inferred from the content payload).

vi.mock('@/auth', () => ({
  useAuth: () => ({ accessToken: 'tok-test' }),
}));

const listMessagesMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    listMessages: (...a: unknown[]) => listMessagesMock(...a),
    messagesUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/messages`,
  },
}));

import { useChatMessages } from '../useChatMessages';

/** Build a fetch Response whose body streams the given SSE lines. */
function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) {
        controller.enqueue(encoder.encode(`data: ${line}\n`));
      }
      controller.close();
    },
  });
  return {
    ok: true,
    status: 200,
    statusText: 'OK',
    body,
  } as unknown as Response;
}

/** The 4-event AG-UI sequence chat-service emits per executed tool call.
 *  content is the {ok, result|error} envelope the server encodes. */
function toolCallEvents(id: string, name: string, ok: boolean): string[] {
  const content = ok
    ? JSON.stringify({ ok: true, result: { hits: [] } })
    : JSON.stringify({ ok: false, error: 'nope' });
  return [
    JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: id, toolCallName: name }),
    JSON.stringify({ type: 'TOOL_CALL_ARGS', toolCallId: id, delta: '{}' }),
    JSON.stringify({ type: 'TOOL_CALL_END', toolCallId: id }),
    JSON.stringify({ type: 'TOOL_CALL_RESULT', toolCallId: id, messageId: 'm', content }),
  ];
}

describe('useChatMessages — tool-call accumulation (AG-UI)', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('attaches accumulated tool-call events to the appended assistant message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          ...toolCallEvents('c1', 'memory_search', true),
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm-1', delta: 'Hi there' }),
          ...toolCallEvents('c2', 'memory_remember', false),
          JSON.stringify({ type: 'CUSTOM', name: 'persisted', value: { messageId: 'm-1' } }),
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant).toBeDefined();
    expect(assistant!.message_id).toBe('m-1');
    expect(assistant!.tool_calls).toEqual([
      { tool: 'memory_search', ok: true },
      { tool: 'memory_remember', ok: false },
    ]);
  });

  it('leaves tool_calls null when the turn made no tool calls', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'No tools used' }),
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toBeNull();
  });

  it('ignores an unknown event and a RESULT without a matching START', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'SOME_FUTURE_EVENT', foo: 1 }),
          // RESULT with no preceding START — must be skipped, not crash.
          JSON.stringify({ type: 'TOOL_CALL_RESULT', toolCallId: 'orphan', messageId: 'm', content: '{}' }),
          ...toolCallEvents('c1', 'memory_timeline', true),
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'done' }),
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    // Only the well-framed tool call accumulates.
    expect(assistant!.tool_calls).toEqual([{ tool: 'memory_timeline', ok: true }]);
  });

  it('treats a non-JSON tool result as a successful opaque result', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'memory_forget' }),
          JSON.stringify({ type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'm', content: 'plain text' }),
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'x' }),
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toEqual([{ tool: 'memory_forget', ok: true }]);
  });

  it('reads ok from the envelope, not from an "error" key inside a success result', async () => {
    // review-impl C4 #1: a successful result whose own payload contains an
    // "error" field must still be ok=true (the server's ok flag is authoritative).
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'memory_search' }),
          JSON.stringify({
            type: 'TOOL_CALL_RESULT',
            toolCallId: 'c1',
            messageId: 'm',
            content: JSON.stringify({ ok: true, result: { hits: [], error: null } }),
          }),
          JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'x' }),
          JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toEqual([{ tool: 'memory_search', ok: true }]);
  });
});
