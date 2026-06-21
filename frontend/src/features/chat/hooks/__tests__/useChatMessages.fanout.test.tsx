import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// MCP fan-out — useChatMessages additions:
//  - accumulates CUSTOM{name:"activity"} events onto the assistant message
//    (C-ACTIVITY) so the Undo strip renders from the live stream.
//  - submitToolResolve POSTs a structured `result` (not the outcome enum) for
//    the immediate nav resolve (C-NAV).

vi.mock('@/auth', () => ({ useAuth: () => ({ accessToken: 'tok-test' }) }));

const listMessagesMock = vi.fn();
vi.mock('../../api', () => ({
  chatApi: {
    listMessages: (...a: unknown[]) => listMessagesMock(...a),
    messagesUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/messages`,
    toolResultsUrl: (sid: string) => `http://test/v1/chat/sessions/${sid}/tool-results`,
  },
}));

import { useChatMessages } from '../useChatMessages';

function sseResponse(lines: string[]): Response {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const line of lines) controller.enqueue(encoder.encode(`data: ${line}\n`));
      controller.close();
    },
  });
  return { ok: true, status: 200, statusText: 'OK', body } as unknown as Response;
}

describe('useChatMessages — MCP fan-out (C-ACTIVITY + C-NAV)', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('accumulates activity events onto the assistant message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
      JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'Done.' }),
      JSON.stringify({ type: 'CUSTOM', name: 'activity', value: {
        op: 'chapter.create', summary: "Created 'Chapter 5'",
        undo: { available: true, tool: 'chapter_delete', args: { book_id: 'b1', chapter_id: 'ch5' } },
      } }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ])));

    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.send('make a chapter'); });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.activities).toHaveLength(1);
    expect(assistant!.activities![0]).toEqual({
      op: 'chapter.create', summary: "Created 'Chapter 5'",
      undo: { available: true, tool: 'chapter_delete', args: { book_id: 'b1', chapter_id: 'ch5' } },
    });
  });

  it('ignores malformed activity events (missing op/summary)', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([
      JSON.stringify({ type: 'CUSTOM', name: 'activity', value: { summary: 'no op' } }),
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ])));
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.send('hi'); });
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.activities).toBeNull();
  });

  it('S6: sends display_language in the body when provided (and omits it otherwise)', async () => {
    // Fresh response per call — a ReadableStream body locks once consumed.
    const fetchMock = vi.fn().mockImplementation(async () => sseResponse([
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]));
    vi.stubGlobal('fetch', fetchMock);

    // With a per-book display language → body carries display_language.
    const withLang = renderHook(() =>
      useChatMessages('s-1', undefined, undefined, { book_id: 'b1' }, 'en'),
    );
    await waitFor(() => expect(withLang.result.current.isLoading).toBe(false));
    await act(async () => { await withLang.result.current.send('hi'); });
    const sentBody = JSON.parse(
      (fetchMock.mock.calls.find((c) => String(c[0]).includes('/messages'))![1] as RequestInit).body as string,
    );
    expect(sentBody.display_language).toBe('en');
    expect(sentBody.book_context).toEqual({ book_id: 'b1' });

    // Without a display language → the field is omitted (source-language aliases).
    fetchMock.mockClear();
    const noLang = renderHook(() => useChatMessages('s-2'));
    await waitFor(() => expect(noLang.result.current.isLoading).toBe(false));
    await act(async () => { await noLang.result.current.send('hi'); });
    const sentBody2 = JSON.parse(
      (fetchMock.mock.calls.find((c) => String(c[0]).includes('/messages'))![1] as RequestInit).body as string,
    );
    expect(sentBody2.display_language).toBeUndefined();
  });

  it('submitToolResolve POSTs a structured result for a nav resolve', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([
      JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
    ]));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.submitToolResolve('r1', 'c1', { navigated: true });
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://test/v1/chat/sessions/s-1/tool-results');
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toEqual({ run_id: 'r1', tool_call_id: 'c1', result: { navigated: true } });
  });
});
