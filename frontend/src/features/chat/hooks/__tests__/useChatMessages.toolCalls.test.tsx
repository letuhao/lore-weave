import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// K21-C (D2): useChatMessages must accumulate `tool-call` SSE events
// and attach them to the locally-appended assistant message.

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

describe('useChatMessages — tool-call accumulation', () => {
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
          JSON.stringify({ type: 'tool-call', tool: 'memory_search', ok: true }),
          JSON.stringify({ type: 'text-delta', delta: 'Hi there' }),
          JSON.stringify({ type: 'tool-call', tool: 'memory_remember', ok: false }),
          JSON.stringify({ type: 'data', data: [{ message_id: 'm-1' }] }),
          '[DONE]',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    await act(async () => {
      await result.current.send('hello');
    });

    // user (optimistic) + assistant (appended)
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
          JSON.stringify({ type: 'text-delta', delta: 'No tools used' }),
          '[DONE]',
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

  it('ignores an unknown SSE type and a tool-call event missing `tool`', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'some-future-event', foo: 1 }),
          JSON.stringify({ type: 'tool-call', ok: true }), // no `tool` — skipped
          JSON.stringify({ type: 'tool-call', tool: 'memory_timeline', ok: true }),
          JSON.stringify({ type: 'text-delta', delta: 'done' }),
          '[DONE]',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    // Only the well-formed tool-call event accumulates.
    expect(assistant!.tool_calls).toEqual([{ tool: 'memory_timeline', ok: true }]);
  });

  it('defaults ok to false when the event omits it', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'tool-call', tool: 'memory_forget' }),
          JSON.stringify({ type: 'text-delta', delta: 'x' }),
          '[DONE]',
        ]),
      ),
    );

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toEqual([{ tool: 'memory_forget', ok: false }]);
  });
});
