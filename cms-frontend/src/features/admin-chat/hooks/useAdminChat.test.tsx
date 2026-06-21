import { renderHook, act, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/api', () => ({ apiBase: () => '' }));

import { useAdminChat } from './useAdminChat';

// Build a fake fetch Response whose body streams the given SSE `data:` lines.
function sseResponse(lines: string[]) {
  const encoder = new TextEncoder();
  const chunks = lines.map((l) => encoder.encode(`data: ${l}\n`));
  let i = 0;
  return {
    ok: true,
    text: async () => '',
    body: {
      getReader: () => ({
        read: async () =>
          i < chunks.length ? { done: false, value: chunks[i++] } : { done: true, value: undefined },
        cancel: async () => {},
      }),
    },
  } as unknown as Response;
}

const SUSPEND_TURN = [
  JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm1', delta: "I'll propose that." }),
  JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 't1', toolCallName: 'glossary_confirm_action' }),
  JSON.stringify({
    type: 'TOOL_CALL_ARGS',
    toolCallId: 't1',
    delta: JSON.stringify({ confirm_token: 'ct', descriptor: 'system_create', title: 'Add genre' }),
  }),
  JSON.stringify({
    type: 'RUN_FINISHED',
    result: { status: 'suspended', pendingToolCall: { runId: 'r1', toolCallId: 't1', toolName: 'glossary_confirm_action' } },
  }),
];

beforeEach(() => {
  global.fetch = vi.fn().mockResolvedValue(sseResponse(SUSPEND_TURN));
});
afterEach(() => vi.clearAllMocks());

describe('useAdminChat', () => {
  it('streams with the user bearer + X-Admin-Token and admin_context', async () => {
    const { result } = renderHook(() => useAdminChat('s1', 'user-hs256', 'admin-rs256'));
    await act(async () => {
      await result.current.send('add a steampunk genre');
    });

    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe('/v1/chat/sessions/s1/messages');
    expect(init.headers.Authorization).toBe('Bearer user-hs256');
    expect(init.headers['X-Admin-Token']).toBe('admin-rs256');
    expect(init.headers['x-loreweave-stream-format']).toBe('agui');
    const body = JSON.parse(init.body);
    expect(body.admin_context).toBeTruthy();
    expect(body.content).toBe('add a steampunk genre');
  });

  it('surfaces the suspended confirm as a pending tool record carrying the args', async () => {
    const { result } = renderHook(() => useAdminChat('s1', 'user-hs256', 'admin-rs256'));
    await act(async () => {
      await result.current.send('add a steampunk genre');
    });
    await waitFor(() => expect(result.current.messages.length).toBe(2)); // user + assistant
    const assistant = result.current.messages[1];
    const pending = assistant.tool_calls?.find((tc) => tc.pending);
    expect(pending?.tool).toBe('glossary_confirm_action');
    expect(pending?.runId).toBe('r1');
    expect((pending?.args as { confirm_token?: string }).confirm_token).toBe('ct');
  });

  it('submitToolResult POSTs the outcome to the tool-results endpoint', async () => {
    const { result } = renderHook(() => useAdminChat('s1', 'user-hs256', 'admin-rs256'));
    // A resume turn ends cleanly (no further suspend).
    (global.fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      sseResponse([JSON.stringify({ type: 'TEXT_MESSAGE_CONTENT', messageId: 'm2', delta: 'Done.' })]),
    );
    await act(async () => {
      await result.current.submitToolResult('r1', 't1', 'action_done');
    });
    const call = (global.fetch as ReturnType<typeof vi.fn>).mock.calls.at(-1)!;
    expect(call[0]).toBe('/v1/chat/sessions/s1/tool-results');
    const body = JSON.parse(call[1].body);
    expect(body).toMatchObject({ run_id: 'r1', tool_call_id: 't1', outcome: 'action_done' });
    expect(call[1].headers['X-Admin-Token']).toBe('admin-rs256');
  });

  it('does not stream without a session id', async () => {
    const { result } = renderHook(() => useAdminChat(null, 'user-hs256', 'admin-rs256'));
    await act(async () => {
      await result.current.send('hi');
    });
    expect(global.fetch).not.toHaveBeenCalled();
  });
});
