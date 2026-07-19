import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStream } from '../providers';
import { isUiTool, resolveUiTool, uiDirectiveFromResult } from '../nav/uiNav';
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
// every nav record is executed AT MOST ONCE, tracked by toolCallId in a ref, so a
// re-render or a message-list refetch never re-navigates.
//
// TWO shapes are handled (Phase 3 cutover):
//   1. DIRECTIVE result (the new path) — ai-gateway ran the ui_* tool locally and
//      returned an `io.loreweave/ui-directive` RESULT; the FE just acts on it. There
//      is NO suspend to resolve.
//   2. PENDING suspend (the legacy path) — the run suspended on a ui_* frontend tool
//      and the FE performs the action + POSTs the resolve. Unfed once P3.2 stops
//      chat-service intercepting ui_* (kept for a safe coexistence window; retire in
//      P4 — D-P3-RETIRE-UI-SUSPEND).

/** Pull pending `ui_*` suspend records out of a message's tool_calls (legacy path). */
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
    for (const m of messages) {
      for (const tc of m.tool_calls ?? []) {
        // (1) DIRECTIVE result — act, no resolve.
        const directive = tc.toolCallId ? uiDirectiveFromResult(tc.result) : null;
        if (directive) {
          if (handledRef.current.has(tc.toolCallId!)) continue;
          handledRef.current.add(tc.toolCallId!);
          dispatchUiAction(directive.tool, directive.args, navigate, intercept);
          continue;
        }
        // (2) PENDING suspend — act + resolve (legacy path).
        if (tc.pending === true && isUiTool(tc.tool) && tc.runId && tc.toolCallId) {
          if (handledRef.current.has(tc.toolCallId)) continue;
          handledRef.current.add(tc.toolCallId);
          const args = (tc.args ?? {}) as Record<string, unknown>;
          const resolved = dispatchUiAction(tc.tool, args, navigate, intercept);
          void submitToolResolve(tc.runId, tc.toolCallId, resolved);
        }
      }
    }
  }, [messages, navigate, submitToolResolve, intercept]);
}

/** Perform a ui_* action (navigate for the SPA tools, or the surface effect for a
 * studio tool via the interceptor). Shared by both the directive and the legacy
 * suspend paths. Returns the resume payload (used only by the suspend path). */
function dispatchUiAction(
  tool: string,
  args: Record<string, unknown>,
  navigate: ReturnType<typeof useNavigate>,
  intercept: ReturnType<typeof useUiNavInterceptor>,
): Record<string, unknown> {
  const interception = intercept?.(tool, args) ?? null;
  const { path, result, effect } = interception ?? { ...resolveUiTool(tool, args), effect: undefined };
  if (effect) {
    try { effect(); } catch { /* surface action can throw if its host isn't ready */ }
  }
  if (path) {
    try {
      navigate(path);
    } catch {
      // navigation can throw if the router isn't ready; the caller still reports the
      // attempted outcome so the agent isn't left hanging.
    }
  }
  return result;
}
