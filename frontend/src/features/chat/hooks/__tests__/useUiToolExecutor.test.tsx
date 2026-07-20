import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook } from '@testing-library/react';

// MCP fan-out (C-NAV) — useUiToolExecutor resolves a suspended ui_* nav tool
// immediately: it navigates (allowlisted) and POSTs the resolve exactly once,
// even across re-renders.

const navigate = vi.fn();
vi.mock('react-router-dom', () => ({ useNavigate: () => navigate }));

const submitToolResolve = vi.fn().mockResolvedValue('');
let streamMessages: unknown[] = [];
vi.mock('../../providers', () => ({
  useChatStream: () => ({ messages: streamMessages, submitToolResolve }),
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

const navRecord: ToolCallRecord = {
  tool: 'ui_navigate', ok: true, pending: true, runId: 'r1', toolCallId: 'c1',
  args: { path: '/books/b1/glossary' },
};

describe('useUiToolExecutor', () => {
  beforeEach(() => {
    navigate.mockClear();
    submitToolResolve.mockClear();
    streamMessages = [];
  });

  it('navigates and resolves a pending ui_navigate exactly once', () => {
    streamMessages = [msgWith(navRecord)];
    const { rerender } = renderHook(() => useUiToolExecutor());
    expect(navigate).toHaveBeenCalledWith('/books/b1/glossary');
    expect(submitToolResolve).toHaveBeenCalledWith('r1', 'c1', { navigated: true });
    // a re-render with the SAME message must NOT re-fire (idempotent by toolCallId)
    rerender();
    expect(navigate).toHaveBeenCalledTimes(1);
    expect(submitToolResolve).toHaveBeenCalledTimes(1);
  });

  it('resolves navigated:false (no navigate) for a disallowed path', () => {
    streamMessages = [msgWith({ ...navRecord, args: { path: '/evil' } })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
    // reject carries a corrective error too (no-silent-no-op); assert the flag, allow the error.
    expect(submitToolResolve).toHaveBeenCalledWith('r1', 'c1', expect.objectContaining({ navigated: false }));
  });

  it('ui_watch_job opens the focused jobs route', () => {
    streamMessages = [
      msgWith({ tool: 'ui_watch_job', ok: true, pending: true, runId: 'r2', toolCallId: 'c2', args: { job_id: 'j9' } }),
    ];
    renderHook(() => useUiToolExecutor());
    expect(navigate).toHaveBeenCalledWith('/jobs?focus=j9');
    expect(submitToolResolve).toHaveBeenCalledWith('r2', 'c2', { watching: true });
  });

  // Nav-scope seam (#12 M-E): an interceptor claiming the call runs its effect and
  // resolves WITHOUT navigating; returning null falls through to the router navigate.
  // This is the wiring proof — a dropped consult would silently restore the studio-killing nav.
  it('consults the nav interceptor: claimed call runs effect, never navigates', () => {
    const effect = vi.fn();
    const interceptor: UiNavInterceptor = (tool) =>
      tool === 'ui_navigate' ? { path: null, result: { navigated: true, note: 'in-surface' }, effect } : null;
    const wrapper = ({ children }: { children: ReactNode }) => (
      <UiNavInterceptorContext.Provider value={interceptor}>{children}</UiNavInterceptorContext.Provider>
    );
    streamMessages = [msgWith(navRecord)];
    renderHook(() => useUiToolExecutor(), { wrapper });
    expect(effect).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
    expect(submitToolResolve).toHaveBeenCalledWith('r1', 'c1', { navigated: true, note: 'in-surface' });
  });

  it('falls through to the router navigate when the interceptor returns null', () => {
    const interceptor: UiNavInterceptor = () => null;
    const wrapper = ({ children }: { children: ReactNode }) => (
      <UiNavInterceptorContext.Provider value={interceptor}>{children}</UiNavInterceptorContext.Provider>
    );
    streamMessages = [msgWith(navRecord)];
    renderHook(() => useUiToolExecutor(), { wrapper });
    expect(navigate).toHaveBeenCalledWith('/books/b1/glossary');
    expect(submitToolResolve).toHaveBeenCalledWith('r1', 'c1', { navigated: true });
  });

  it('ignores non-pending and non-ui tool calls', () => {
    streamMessages = [
      msgWith({ tool: 'ui_navigate', ok: true, pending: false, args: { path: '/books' } }),
      msgWith({ tool: 'propose_edit', ok: true, pending: true, runId: 'r3', toolCallId: 'c3', args: {} }),
    ];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
    expect(submitToolResolve).not.toHaveBeenCalled();
  });

  // Phase 3 cutover — the DIRECTIVE path: ai-gateway ran the ui_* tool and returned an
  // io.loreweave/ui-directive RESULT. The FE acts on it with NO suspend to resolve.
  // IMPORTANT: the result carries chat-service's REAL {ok, result: <directive>} envelope
  // (runChatStream parses the whole TOOL_CALL_RESULT content into `result`) — using the
  // bare directive here once hid a live bug the browser E2E caught (the directive was
  // nested under `.result`, so the un-unwrapped detector never fired).
  const directiveRecord: ToolCallRecord = {
    tool: 'ui_navigate', ok: true, pending: false, toolCallId: 'd1',
    result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_navigate', args: { path: '/books/b1/glossary' } } },
  };

  it('acts on a ui-directive RESULT once, WITHOUT resolving (no suspend)', () => {
    streamMessages = [msgWith(directiveRecord)];
    const { rerender } = renderHook(() => useUiToolExecutor());
    expect(navigate).toHaveBeenCalledWith('/books/b1/glossary');
    expect(submitToolResolve).not.toHaveBeenCalled(); // directive path never resolves
    rerender();
    expect(navigate).toHaveBeenCalledTimes(1); // idempotent by toolCallId
  });

  it('directive with a disallowed path does not navigate (and still never resolves)', () => {
    streamMessages = [msgWith({
      ...directiveRecord, toolCallId: 'd2',
      result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_navigate', args: { path: '/evil' } } },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
    expect(submitToolResolve).not.toHaveBeenCalled();
  });

  it('directive consults the interceptor (studio effect, no navigate)', () => {
    const effect = vi.fn();
    const interceptor: UiNavInterceptor = (tool) =>
      tool === 'ui_open_studio_panel' ? { path: null, result: { opened: true }, effect } : null;
    const wrapper = ({ children }: { children: ReactNode }) => (
      <UiNavInterceptorContext.Provider value={interceptor}>{children}</UiNavInterceptorContext.Provider>
    );
    streamMessages = [msgWith({
      tool: 'ui_open_studio_panel', ok: true, pending: false, toolCallId: 'd3',
      result: { ok: true, result: { type: 'io.loreweave/ui-directive', tool: 'ui_open_studio_panel', args: { panel_id: 'compose' } } },
    })];
    renderHook(() => useUiToolExecutor(), { wrapper });
    expect(effect).toHaveBeenCalledTimes(1);
    expect(navigate).not.toHaveBeenCalled();
    expect(submitToolResolve).not.toHaveBeenCalled();
  });

  it('ignores a non-directive result (a normal tool result is not a nav)', () => {
    streamMessages = [msgWith({
      tool: 'book_list', ok: true, pending: false, toolCallId: 'd4', result: { books: [] },
    })];
    renderHook(() => useUiToolExecutor());
    expect(navigate).not.toHaveBeenCalled();
    expect(submitToolResolve).not.toHaveBeenCalled();
  });
});
