import { useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useChatStream } from '../providers';
import { resolveUiTool, uiDirectiveFromResult } from '../nav/uiNav';
import { useUiNavInterceptor } from '../nav/uiNavScope';

// MCP fan-out (C-NAV) — the browser-side executor for the `ui_*` navigation tools.
//
// Since Phase 3 (P3.2) the ui_* tools are ai-gateway CONSUMER-LOCAL tools: the agent's
// call runs there and comes back as an `io.loreweave/ui-directive` tool RESULT rather
// than suspending the run. The FE acts on that directive (navigate / open a panel) —
// there is NO human gate and NO suspend to resolve (the agent asked to move the UI, so
// we just do it, exactly once).
//
// This is a genuine synchronization concern (new streamed data → side effect), not
// user-event handling, so it lives in a useEffect — idempotent: every directive is acted
// on AT MOST ONCE, tracked by toolCallId in a ref, so a re-render or a message-list
// refetch never re-navigates.
//
// (The legacy pending-suspend path was retired in Phase 4 / D-P3-RETIRE-UI-SUSPEND once
// the ui_* cutover was live-proven — no ui_* suspends any more.)

/**
 * Mount once inside the chat provider tree (it reads useChatStream + useNavigate).
 * Watches the message list for ui-directive tool results and acts on them.
 */
export function useUiToolExecutor(): void {
  const navigate = useNavigate();
  const { messages } = useChatStream();
  // Nav-scope seam: an embedding surface (the studio) may claim a call and run a
  // surface-internal effect instead of an SPA navigation (see uiNavScope.ts).
  const intercept = useUiNavInterceptor();
  // toolCallIds we have already acted on — never act on the same directive twice.
  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const m of messages) {
      for (const tc of m.tool_calls ?? []) {
        const directive = tc.toolCallId ? uiDirectiveFromResult(tc.result) : null;
        if (!directive) continue;
        if (handledRef.current.has(tc.toolCallId!)) continue;
        handledRef.current.add(tc.toolCallId!);
        dispatchUiAction(directive.tool, directive.args, navigate, intercept);
      }
    }
  }, [messages, navigate, intercept]);
}

/** Perform a ui_* action: navigate for the SPA tools, or the surface effect for a studio
 * tool via the interceptor (the studio claims the call and runs a dock action). */
function dispatchUiAction(
  tool: string,
  args: Record<string, unknown>,
  navigate: ReturnType<typeof useNavigate>,
  intercept: ReturnType<typeof useUiNavInterceptor>,
): void {
  const interception = intercept?.(tool, args) ?? null;
  const { path, effect } = interception ?? { ...resolveUiTool(tool, args), effect: undefined };
  if (effect) {
    try { effect(); } catch { /* surface action can throw if its host isn't ready */ }
  }
  if (path) {
    try {
      navigate(path);
    } catch {
      // navigation can throw if the router isn't ready; a missed nav just means the user
      // clicks the target themselves — never fatal.
    }
  }
}
