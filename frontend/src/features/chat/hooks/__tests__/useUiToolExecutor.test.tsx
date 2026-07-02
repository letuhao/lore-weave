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
});
