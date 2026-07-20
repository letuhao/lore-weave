import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

// MCP fan-out (C-NAV) — useUiToolExecutor acts on an `io.loreweave/ui-directive` tool
// RESULT (ai-gateway ran the ui_* tool locally): it navigates (allowlisted) or runs the
// studio surface effect, exactly once, with NO suspend to resolve. (The legacy
// pending-suspend path was retired in Phase 4 once the ui_* cutover was live-proven.)

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

let streamMessages: unknown[] = [];
vi.mock('../../providers', () => ({
  useChatStream: () => ({ messages: streamMessages }),
}));

import type { ReactNode } from 'react';
import { useUiToolExecutor } from '../useUiToolExecutor';
import { UiNavInterceptorContext, type UiNavInterceptor } from '../../nav/uiNavScope';
import type { ChatMessage, ToolCallRecord } from '../../types';

function msgWith(tc: ToolCallRecord): ChatMessage {
  return {
    message_id: 'm1', session_id: 's', owner_user_id: '', role: 'assistant',
    content: '', content_parts: null, sequence_num: 1, branch_id: 0,
    input_tokens: null, output_tokens: null, model_ref: null, is_error: false,
    error_detail: null, parent_message_id: null, created_at: new Date().toISOString(),
    tool_calls: [tc],
  };
}

// The result carries chat-service's REAL {ok, result: <directive>} envelope
// (runChatStream parses the whole TOOL_CALL_RESULT content into `result`) — using the
// bare directive here once hid a live bug the browser E2E caught (the directive was
// nested under `.result`, so the un-unwrapped detector never fired).
const directiveRecord: ToolCallRecord = {
  tool: 'ui_navigate', ok: true, pending: false, toolCallId: 'd1',
  result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_navigate', args: { path: '/books/b1/glossary' } } },
};

const withInterceptor = (interceptor: UiNavInterceptor) =>
  ({ children }: { children: ReactNode }) => (
    <UiNavInterceptorContext.Provider value={interceptor}>{children}</UiNavInterceptorContext.Provider>
  );

describe('useUiToolExecutor (directive path)', () => {
  beforeEach(() => {
    navigate.mockClear();
    streamMessages = [];
  });

  it('acts on a ui-directive RESULT once (idempotent by toolCallId)', () => {
    streamMessages = [msgWith(directiveRecord)];
    const { rerender } = renderHook(() => useUiToolExecutor());
    expect(navigate).toHaveBeenCalledWith('/books/b1/glossary');
    rerender(); // same message → must NOT re-navigate
    expect(navigate).toHaveBeenCalledTimes(1);
  });

  it('ui_watch_job directive opens the focused jobs route', () => {
    streamMessages = [msgWith({
      tool: 'ui_watch_job', ok: true, pending: false, toolCallId: 'w1',
      result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_watch_job', args: { job_id: 'j9' } } },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).toHaveBeenCalledWith('/jobs?focus=j9');
  });

  it('a disallowed path does not navigate (no-op, never fatal)', () => {
    streamMessages = [msgWith({
      ...directiveRecord, toolCallId: 'd2',
      result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_navigate', args: { path: '/evil' } } },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
  });

  it('consults the nav interceptor: a claimed studio call runs its effect, never navigates', () => {
    const effect = vi.fn();
    streamMessages = [msgWith({
      tool: 'ui_open_studio_panel', ok: true, pending: false, toolCallId: 'd3',
      result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_open_studio_panel', args: { panel_id: 'compose' } } },
    })];
    renderHook(() => useUiToolExecutor(), {
      wrapper: withInterceptor((tool) =>
        tool === 'ui_open_studio_panel' ? { path: null, result: { opened: true }, effect } : null),
    });
    expect(effect).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
  });

  it('falls through to the router navigate when the interceptor returns null', () => {
    streamMessages = [msgWith(directiveRecord)];
    renderHook(() => useUiToolExecutor(), { wrapper: withInterceptor(() => null) });
    expect(navigate).toHaveBeenCalledWith('/books/b1/glossary');
  });

  it('ignores a non-directive result (a normal tool result is not a nav)', () => {
    streamMessages = [msgWith({
      tool: 'book_list', ok: true, pending: false, toolCallId: 'd4', result: { books: [] },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
  });

  it('ignores a legacy pending record (the suspend path is retired — nothing acts on it)', () => {
    streamMessages = [msgWith({
      tool: 'ui_navigate', ok: true, pending: true, runId: 'r1', toolCallId: 'p1', args: { path: '/books' },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
  });
});
