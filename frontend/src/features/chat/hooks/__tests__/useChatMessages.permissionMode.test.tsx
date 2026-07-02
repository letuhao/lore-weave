import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor, act } from '@testing-library/react';

// RAID C2 (DR-C2) — permission_mode plumbing:
//  - default ('write') sends NO permission_mode field (wire byte-identical),
//  - setPermissionMode('ask') sends permission_mode:'ask' on the message POST
//    and persists to localStorage (mirrors the editor composeMode pattern),
//  - a suspended `tool_approval` (server tool name + kind-marker args) is
//    captured as a pending record on the EXISTING pending-tool-call surface.

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

const FINISH = JSON.stringify({ type: 'RUN_FINISHED', result: {} });

describe('useChatMessages — RAID C2 permission mode', () => {
  beforeEach(() => {
    listMessagesMock.mockReset();
    listMessagesMock.mockResolvedValue({ items: [] });
    localStorage.removeItem('lw_chat_permission_mode');
  });
  afterEach(() => {
    vi.unstubAllGlobals();
    localStorage.removeItem('lw_chat_permission_mode');
  });

  it('default write mode sends NO permission_mode field (byte-identical wire)', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([FINISH]));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.permissionMode).toBe('write');
    await act(async () => { await result.current.send('hi'); });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).not.toHaveProperty('permission_mode');
  });

  it('ask mode sends permission_mode:"ask" and persists the choice', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([FINISH]));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.setPermissionMode('ask'));
    await act(async () => { await result.current.send('research this'); });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.permission_mode).toBe('ask');
    // persisted like composeMode (localStorage write-through)
    expect(localStorage.getItem('lw_chat_permission_mode')).toBe('ask');
  });

  it('rehydrates the persisted mode on mount', async () => {
    localStorage.setItem('lw_chat_permission_mode', 'ask');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([FINISH])));
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.permissionMode).toBe('ask');
  });

  // RAID B2 — plan mode rides the same seam as ask.
  it('plan mode sends permission_mode:"plan" and persists the choice', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([FINISH]));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    act(() => result.current.setPermissionMode('plan'));
    await act(async () => { await result.current.send('plan the arc'); });
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body.permission_mode).toBe('plan');
    expect(localStorage.getItem('lw_chat_permission_mode')).toBe('plan');
  });

  it('rehydrates a persisted plan mode on mount', async () => {
    localStorage.setItem('lw_chat_permission_mode', 'plan');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([FINISH])));
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.permissionMode).toBe('plan');
  });

  it('an unknown persisted value falls back to write', async () => {
    localStorage.setItem('lw_chat_permission_mode', 'yolo');
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse([FINISH])));
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.permissionMode).toBe('write');
  });

  it('captures a suspended tool_approval as a pending record (existing surface)', async () => {
    const approvalArgs = {
      kind: 'tool_approval',
      tool: 'book_create',
      args: { title: 'My Book' },
      tier: 'A',
    };
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        sseResponse([
          JSON.stringify({ type: 'TOOL_CALL_START', toolCallId: 'c1', toolCallName: 'book_create' }),
          JSON.stringify({ type: 'TOOL_CALL_ARGS', toolCallId: 'c1', delta: JSON.stringify(approvalArgs) }),
          JSON.stringify({ type: 'TOOL_CALL_END', toolCallId: 'c1' }),
          JSON.stringify({
            type: 'RUN_FINISHED',
            result: { status: 'suspended', pendingToolCall: { runId: 'r9', toolCallId: 'c1', toolName: 'book_create' } },
          }),
        ]),
      ),
    );
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.send('make a book'); });

    const assistant = result.current.messages.find((m) => m.role === 'assistant');
    expect(assistant!.tool_calls).toHaveLength(1);
    const tc = assistant!.tool_calls![0];
    expect(tc.tool).toBe('book_create');
    expect(tc.pending).toBe(true);
    expect(tc.runId).toBe('r9');
    expect(tc.toolCallId).toBe('c1');
    expect(tc.args).toEqual(approvalArgs);
  });

  it('submitToolResult posts the approval outcome to the resume endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue(sseResponse([FINISH]));
    vi.stubGlobal('fetch', fetchMock);
    const { result } = renderHook(() => useChatMessages('s-1'));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => {
      await result.current.submitToolResult('r9', 'c1', 'approved_always');
    });
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain('/tool-results');
    const body = JSON.parse(init.body as string);
    expect(body).toMatchObject({ run_id: 'r9', tool_call_id: 'c1', outcome: 'approved_always' });
  });
});
