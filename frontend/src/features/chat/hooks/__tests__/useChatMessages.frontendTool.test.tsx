import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// ARCH-1 C6 — useChatMessages handles a SUSPENDED run (frontend tool awaiting
// the user's apply/dismiss): it captures TOOL_CALL_ARGS, and on a
// RUN_FINISHED{status:"suspended"} pushes a pending propose_edit record with the
// parsed proposal args; submitToolResult POSTs the resume endpoint.

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

describe('useChatMessages — C6 frontend tool (propose_edit)', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
  });
  afterEach(() => vi.unstubAllGlobals());

  it('captures a suspended propose_edit as a pending tool record with args', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'propose_edit' }),
          JSON.stringify({ type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: JSON.stringify({ operation: 'insert_at_cursor', text: 'Hello' }) }),
          JSON.stringify({ type: 'TOOL_CALL_END', toolCallId: 'c1' }),
          JSON.stringify({
            type: 'RUN_FINISHED',
            result: { status: 'suspended', pendingToolCall: { runId: 'r1', toolCallId: 'c1', toolName: 'propose_edit' } },
          }),
        ]),
      ),
    );

    const { result } = renderHook(() =>
      useChatMessages('s-1', { book_id: 'b1', chapter_id: 'ch1' }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('rewrite this');
    });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toHaveLength(1);
    const tc = assistant!.tool_calls![0];
    expect(tc.tool).toBe('propose_edit');
    expect(tc.pending).toBe(true);
    expect(tc.runId).toBe('r1');
    expect(tc.toolCallId).toBe('c1');
    expect(tc.args).toEqual({ operation: 'insert_at_cursor', text: 'Hello' });
  });

  it('sends editor_context in the request body', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([JSON.stringify({ type: 'RUN_FINISHED', result: {} })]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() =>
      useChatMessages('s-1', { book_id: 'b1', chapter_id: 'ch1' }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('hi');
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.editor_context).toEqual({ book_id: 'b1', chapter_id: 'ch1' });
  });

  it('sends studio_context in the request body (studio compose panel → Lane A tools)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([JSON.stringify({ type: 'RUN_FINISHED', result: {} })]),
    );
    vi.stubGlobal('fetch', fetchMock);
    // studioContext is the 9th positional arg (after streamPinsRef).
    const { result } = renderHook(() =>
      useChatMessages('s-1', undefined, undefined, undefined, undefined, undefined, undefined, undefined, { book_id: 'b1' }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('open the editor for chapter 3');
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.studio_context).toEqual({ book_id: 'b1' });
  });

  it('sends book_context (not editor_context) for a glossary-page chat', async () => {
    // Glossary-assistant P3: a book-scoped, non-editor chat advertises the
    // glossary edit tool via book_context.
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([JSON.stringify({ type: 'RUN_FINISHED', result: {} })]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() =>
      useChatMessages('s-1', undefined, undefined, { book_id: 'b1' }),
    );
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.send('rename Nezha');
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.book_context).toEqual({ book_id: 'b1' });
    expect(body.editor_context).toBeUndefined();
  });

  it('submitToolResult forwards the glossary H6 outcome enum verbatim', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([JSON.stringify({ type: 'RUN_FINISHED', result: {} })]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.submitToolResult('r1', 'c1', 'applied_conflict');
    });
    const body = JSON.parse((fetchMock.mock.calls[0][1] as RequestInit).body as string);
    expect(body.outcome).toBe('applied_conflict');
  });

  it('submitToolResult POSTs the resume endpoint with the outcome', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      sseResponse([
        JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm', delta: 'Applied.' }),
        JSON.stringify({ type: 'RUN_FINISHED', result: {} }),
      ]),
    );
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.submitToolResult('r1', 'c1', 'applied', 'Hello');
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('http://test/v1/chat/sessions/s-1/tool-results');
    const body = JSON.parse((init as RequestInit).body as string);
    expect(body).toEqual({ run_id: 'r1', tool_call_id: 'c1', outcome: 'applied', applied_text: 'Hello' });
    // the resumed assistant message is appended
    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.content).toBe('Applied.');
  });
});
