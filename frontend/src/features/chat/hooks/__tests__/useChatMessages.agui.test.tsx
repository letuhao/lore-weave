import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// ARCH-1 C4: useChatMessages consumes the AG-UI event protocol. These tests
// drive the hook with AG-UI SSE lines and assert the same observable outcomes
// the legacy parser produced — the hook's public contract is unchanged.

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
  return { ok: true, status: 200, statusText: 'OK', body } as unknown as Response;
}

function stubFetch(lines: string[]) {
  const fetchMock = vi.fn().mockResolvedValue(sseResponse(lines));
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

describe('useChatMessages — AG-UI protocol', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('sends the x-loreweave-stream-format: agui request header', async () => {
    const fetchMock = stubFetch([
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });
    // first arg = url, second = init
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['x-loreweave-stream-format']).toBe('agui');
  });

  it('accumulates reasoning then text, transitioning thinking → responding', async () => {
    stubFetch([
      JSON.stringify({ type: 'RUN_STARTED', threadId: 's-1', runId: 'r1' }),
      JSON.stringify({ type: 'REASONING_MESSAGE_START', messageId: 'm', role: 'reasoning' }),
      JSON.stringify({ type: 'REASONING_MESSAGE_CONTENT', messageId: 'm', delta: 'think ' }),
      JSON.stringify({ type: 'REASONING_MESSAGE_CONTENT', messageId: 'm', delta: 'hard' }),
      JSON.stringify({ type: 'REASONING_MESSAGE_END', messageId: 'm' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_START', messageId: 'm', role: 'assistant' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'Answer.' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_END', messageId: 'm' }),
      JSON.stringify({ type: 'CUSTOM', name: 'persisted', value: { messageId: 'm-final' } }),
      JSON.stringify({ type: 'RUN_FINISHED', result: { usage: { promptTokens: 3, completionTokens: 4 } } }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.message_id).toBe('m-final');
    expect(assistant!.content).toBe('Answer.');
    expect(assistant!.content_parts?.reasoning).toBe('think hard');
    expect(assistant!.input_tokens).toBe(3);
    expect(assistant!.output_tokens).toBe(4);
  });

  it('fires onMemoryModeRef from a CUSTOM memoryMode event', async () => {
    stubFetch([
      JSON.stringify({ type: 'RUN_STARTED', threadId: 's-1', runId: 'r1' }),
      JSON.stringify({ type: 'CUSTOM', name: 'memoryMode', value: { mode: 'degraded' } }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const seen: string[] = [];
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.onMemoryModeRef.current = (mode) => seen.push(mode);
    });
    await act(async () => {
      await result.current.send('hello');
    });
    expect(seen).toEqual(['degraded']);
  });

  it('fires onAgentSurfaceRef from CUSTOM agentSurface events', async () => {
    const payload = {
      phase: 'Discovering',
      pinned_count: 1,
      hot_seed_count: 3,
      activated_count: 0,
      injected_skills: ['glossary'],
      running_tool: null,
      last_find_tools_query: 'translate',
      find_tools_call_count: 1,
    };
    stubFetch([
      JSON.stringify({ type: 'RUN_STARTED', threadId: 's-1', runId: 'r1' }),
      JSON.stringify({ type: 'CUSTOM', name: 'agentSurface', value: payload }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const seen: unknown[] = [];
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.onAgentSurfaceRef.current = (state) => seen.push(state);
    });
    await act(async () => {
      await result.current.send('hello');
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ phase: 'Discovering', last_find_tools_query: 'translate' });
  });

  it('uses streamPinsRef for POST body when session arrays are stale', async () => {
    const fetchMock = stubFetch([
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const streamPinsRef = {
      current: { enabledTools: ['find_tools'], enabledSkills: ['glossary'] as string[] | undefined },
    };
    const { result } = renderHook(() =>
      useChatMessages('s-1', undefined, undefined, undefined, undefined, [], [], streamPinsRef),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(body.enabled_tools).toEqual(['find_tools']);
    expect(body.enabled_skills).toEqual(['glossary']);
  });

  it('exposes the extended contextBudget snapshot (W1/W2 additive fields)', async () => {
    stubFetch([
      JSON.stringify({
        type: 'CUSTOM', name: 'contextBudget',
        value: {
          used_tokens: 3676, context_length: 8192, effective_limit: 8000, pct: 0.4595,
          until_compact_pct: 0.2905, baseline_tokens: 3667,
          breakdown: { skills: 1907, history: 9, memory_knowledge: { total: 50, sections: { instructions: 33 } } },
        },
      }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });
    expect(result.current.contextBudget).toMatchObject({
      used_tokens: 3676,
      pct: 0.4595,
      until_compact_pct: 0.2905,
      baseline_tokens: 3667,
      breakdown: { skills: 1907, memory_knowledge: { total: 50, sections: { instructions: 33 } } },
    });
  });

  it('fires onCompactionRef from a CUSTOM compaction event', async () => {
    stubFetch([
      JSON.stringify({
        type: 'CUSTOM', name: 'compaction',
        value: {
          triggered: true, tool_results_cleared: 2, turns_truncated: 4, summarized: true,
          summarize_failed: false, overflowed: false, tokens_before: 9000, tokens_after: 4100,
        },
      }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const seen: unknown[] = [];
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.onCompactionRef.current = (e) => seen.push(e);
    });
    await act(async () => {
      await result.current.send('hello');
    });
    expect(seen).toHaveLength(1);
    expect(seen[0]).toMatchObject({ tokens_before: 9000, tokens_after: 4100, summarized: true });
  });

  it('W4: send(content, thinking, "deep") puts reasoning_effort on the POST body', async () => {
    const fetchMock = stubFetch([
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello', true, 'deep');
    });
    const body = JSON.parse(String((fetchMock.mock.calls[0][1] as RequestInit).body));
    expect(body).toMatchObject({ content: 'hello', thinking: true, reasoning_effort: 'deep' });
  });

  it('maps RUN_ERROR to the error path', async () => {
    stubFetch([
      JSON.stringify({ type: 'RUN_STARTED', threadId: 's-1', runId: 'r1' }),
      JSON.stringify({ type: 'RUN_ERROR', message: 'boom', code: 'STREAM_ERROR' }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    // RUN_ERROR surfaces as a thrown Error carrying the server message — the
    // same contract the legacy `error` event had. (Post-throw streamStatus
    // settles asynchronously via the catch's refetch, so we assert the throw,
    // which is the observable contract callers depend on.)
    await expect(
      act(async () => {
        await result.current.send('hello');
      }),
    ).rejects.toThrow('boom');
  });

  it('delivers per-token deltas to onStreamDeltaRef (voice pipeline)', async () => {
    stubFetch([
      JSON.stringify({ type: 'REASONING_MESSAGE_CONTENT', messageId: 'm', delta: 'r1' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 't1' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 't2' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const deltas: Array<[string, string]> = [];
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.onStreamDeltaRef.current = (d, type) => deltas.push([type, d]);
    });
    await act(async () => {
      await result.current.send('hello');
    });
    expect(deltas).toEqual([
      ['reasoning', 'r1'],
      ['content', 't1'],
      ['content', 't2'],
    ]);
  });

  it('handles the full live shape: reasoning → tool call → text in one turn', async () => {
    // review-impl C4 #2: the realistic memory-tool turn — reasoning, then a
    // tool call (sibling of the text message), then text — exercised together.
    stubFetch([
      JSON.stringify({ type: 'RUN_STARTED', threadId: 's-1', runId: 'r1' }),
      JSON.stringify({ type: 'CUSTOM', name: 'memoryMode', value: { mode: 'static' } }),
      JSON.stringify({ type: 'REASONING_MESSAGE_CONTENT', messageId: 'm', delta: 'Let me look. ' }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'One sec. ' }),
      JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'memory_search' }),
      JSON.stringify({ type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: '{}' }),
      JSON.stringify({ type: 'TOOL_CALL_END', toolCallId: 'c1' }),
      JSON.stringify({
        type: 'TOOL_CALL_RESULT', toolCallId: 'c1', messageId: 'm',
        content: JSON.stringify({ ok: true, result: { hits: [1] } }),
      }),
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'Kai is a knight.' }),
      JSON.stringify({ type: 'CUSTOM', name: 'persisted', value: { messageId: 'm-1' } }),
      JSON.stringify({ type: 'RUN_FINISHED', result: { usage: { promptTokens: 5, completionTokens: 9 } } }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('Who is Kai?');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.message_id).toBe('m-1');
    // text accumulated across the two TEXT_MESSAGE_CONTENT events (the tool
    // call between them does not interrupt the single text message)
    expect(assistant!.content).toBe('One sec. Kai is a knight.');
    expect(assistant!.content_parts?.reasoning).toBe('Let me look. ');
    expect(assistant!.tool_calls).toEqual([expect.objectContaining({ tool: 'memory_search', ok: true })]);
    expect(assistant!.output_tokens).toBe(9);
  });

  it('falls back to a synthetic message_id when no persisted event arrives', async () => {
    // review-impl C4 #3: CUSTOM(persisted) missing → message_id starts 'done-'.
    stubFetch([
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'hi' }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hello');
    });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.message_id).toMatch(/^done-/);
    expect(assistant!.content).toBe('hi');
  });

  it('aborts mid-stream cleanly when stop() is called', async () => {
    // review-impl C4 #3: stop() during AG-UI streaming → AbortError path
    // refetches + fires onStreamEndRef, does NOT throw to the caller. We model
    // a real aborted fetch: it rejects with a DOMException(name:'AbortError')
    // once the request signal fires (jsdom's fetch mock doesn't auto-wire the
    // signal, so we observe it explicitly).
    const fetchMock = vi.fn().mockImplementation((_url: string, init: RequestInit) => {
      return new Promise((_resolve, reject) => {
        const signal = init.signal;
        signal?.addEventListener('abort', () => {
          reject(new DOMException('aborted', 'AbortError'));
        });
      });
    });
    vi.stubGlobal('fetch', fetchMock);
    let ended = false;
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => {
      result.current.onStreamEndRef.current = () => {
        ended = true;
      };
    });
    await act(async () => {
      const p = result.current.send('hello');
      await new Promise((r) => setTimeout(r, 10));
      result.current.stop(); // triggers controller.abort() → fetch rejects
      // send() resolves (does not throw) on the AbortError path
      await expect(p).resolves.toBeDefined();
    });
    expect(ended).toBe(true);
  });
});
