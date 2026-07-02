import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStream } from '../providers';
import { isUiTool, resolveUiTool } from '../nav/uiNav';
import { useUiNavInterceptor } from '../nav/uiNavScope';
import type { ToolCallRecord } from '../types';

// MCP fan-out (C-NAV) — the browser-side executor for `ui_*` navigation tools.
//
// When the agent calls ui_navigate / ui_open_book / ui_open_chapter /
// ui_show_panel / ui_watch_job, the run SUSPENDS and the assistant message
// carries a pending tool record (like propose_edit). Unlike propose_edit there
// is NO human gate: the agent asked to move the UI, so we perform the router
// action and POST the resolve immediately, which the agent reads on its next
// pass.
//
// This is a genuine synchronization concern (new streamed data → side effect),
// not user-event handling, so it lives in a useEffect — but it is idempotent:
// every pending nav record is executed AT MOST ONCE, tracked by toolCallId in a
// ref, so a re-render or a message-list refetch never re-navigates.

/** Pull pending `ui_*` records out of a message's tool_calls. */
function pendingUiToolCalls(records: ToolCallRecord[] | null | undefined): ToolCallRecord[] {
  if (!records) return [];
  return records.filter(
    (tc) => tc.pending === true && isUiTool(tc.tool) && !!tc.runId && !!tc.toolCallId,
  );
}

/**
 * Mount once inside the chat provider tree (it reads useChatStream + useNavigate).
 * Watches the message list for pending nav tool calls and resolves them.
 */
export function useUiToolExecutor(): void {
  const navigate = useNavigate();
  const { messages, submitToolResolve } = useChatStream();
  // Nav-scope seam: an embedding surface (the studio) may claim a call and run a
  // surface-internal effect instead of an SPA navigation (see uiNavScope.ts).
  const intercept = useUiNavInterceptor();
  // toolCallIds we have already executed — never act on the same suspend twice.
  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    const pending: ToolCallRecord[] = [];
    for (const m of messages) {
      for (const tc of pendingUiToolCalls(m.tool_calls)) pending.push(tc);
    }
    for (const tc of pending) {
      const id = tc.toolCallId!;
      if (handledRef.current.has(id)) continue;
      handledRef.current.add(id);

      const args = (tc.args ?? {}) as Record<string, unknown>;
      const interception = intercept?.(tc.tool, args) ?? null;
      const { path, result, effect } = interception ?? { ...resolveUiTool(tc.tool, args), effect: undefined };
      if (effect) {
        try { effect(); } catch { /* surface action can throw if its host isn't ready */ }
      }
      if (path) {
        try {
          navigate(path);
        } catch {
          // navigation can throw if the router isn't ready; the resolve below
          // still reports the attempted outcome so the agent isn't left hanging.
        }
      }
      // Resolve the suspended run with the (navigated|opened|shown|watching) flag.
      void submitToolResolve(tc.runId!, id, result);
    }
  }, [messages, navigate, submitToolResolve, intercept]);
}
