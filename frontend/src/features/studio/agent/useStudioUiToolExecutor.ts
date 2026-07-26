// #09 Lane A executor — the studio counterpart of the chat's useUiToolExecutor. Watches the
// chat stream for the studio-specific `ui_*` tools (ui_open_studio_panel /
// ui_focus_manuscript_unit) and runs them against the live StudioHost (open a dock panel /
// focus a chapter's editor).
//
// Since Phase 3 (P3.2) these are ai-gateway CONSUMER-LOCAL tools that come back as an
// `io.loreweave/ui-directive` RESULT (they no longer suspend). This hook acts on that
// directive — the studio-specific tools are NOT claimed by makeStudioNavInterceptor (which
// only remaps the GENERIC nav tools to dock actions), and the chat's own useUiToolExecutor
// can't resolve them (resolveUiTool only knows the 5 SPA-nav tools), so WITHOUT this the
// dock-nav tools silently no-op. (Fixed in Phase 4 / P4.1 — the P3.2 cutover left this hook
// on the dead suspend path.)
//
// Mounted only in the studio Compose panel (via StudioAgentBridge), so useStudioHost() is
// always inside a provider here. Idempotent by toolCallId. Disjoint from the chat's own
// executor by tool name (ui_open_studio_panel / ui_focus_manuscript_unit only), so the two
// never double-act on a directive.
import { useEffect, useRef } from 'react';
import { useChatStream } from '@/features/chat/providers';
import { uiDirectiveFromResult } from '@/features/chat/nav/uiNav';
import { useStudioHost } from '../host/StudioHostProvider';
import { isStudioUiTool, resolveStudioUiTool } from './studioUiNav';

export function useStudioUiToolExecutor(): void {
  const host = useStudioHost();
  const { messages } = useChatStream();
  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const m of messages) {
      for (const tc of m.tool_calls ?? []) {
        const directive = tc.toolCallId ? uiDirectiveFromResult(tc.result) : null;
        if (!directive || !isStudioUiTool(directive.tool)) continue;
        const id = tc.toolCallId!;
        if (handledRef.current.has(id)) continue;
        handledRef.current.add(id);
        const { effect } = resolveStudioUiTool(directive.tool, directive.args);
        try { effect?.(host); } catch { /* host action can throw if the dock api isn't ready */ }
      }
    }
  }, [messages, host]);
}
