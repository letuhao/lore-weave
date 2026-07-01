// #09 Lane A executor — the studio counterpart of the chat's useUiToolExecutor. Watches the chat
// stream for pending studio `ui_*` tool calls and resolves them against the live StudioHost.
//
// Mounted only in the studio Compose panel (via the chat's provider-slot / actionBar), so
// useStudioHost() is always inside a provider here. Idempotent by toolCallId (a re-render or a
// message refetch never re-fires). Disjoint from the chat's own executor (different tool names),
// so the two never double-handle a suspend.
import { useEffect, useRef } from 'react';
import { useChatStream } from '@/features/chat/providers';
import type { ToolCallRecord } from '@/features/chat/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { isStudioUiTool, resolveStudioUiTool } from './studioUiNav';

function pendingStudioUiCalls(records: ToolCallRecord[] | null | undefined): ToolCallRecord[] {
  if (!records) return [];
  return records.filter(
    (tc) => tc.pending === true && isStudioUiTool(tc.tool) && !!tc.runId && !!tc.toolCallId,
  );
}

export function useStudioUiToolExecutor(): void {
  const host = useStudioHost();
  const { messages, submitToolResolve } = useChatStream();
  const handledRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    for (const m of messages) {
      for (const tc of pendingStudioUiCalls(m.tool_calls)) {
        const id = tc.toolCallId!;
        if (handledRef.current.has(id)) continue;
        handledRef.current.add(id);
        const { result, effect } = resolveStudioUiTool(tc.tool, (tc.args ?? {}) as Record<string, unknown>);
        try { effect?.(host); } catch { /* host action can throw if the dock api isn't ready */ }
        void submitToolResolve(tc.runId!, id, result);
      }
    }
  }, [messages, host, submitToolResolve]);
}
