// #09 Lane B reconciler — watches the chat stream for COMPLETED MCP tool calls and runs the code
// effect handlers (invalidate / reload / publish). The SOLE path from an agent MCP write → GUI
// refresh (G3). Dedupes so a re-render / message refetch never re-runs a handler.
//
// Mounted only in the studio Compose panel (via the chat provider-slot), so useStudioHost() is
// inside a provider. SKELETON: handlers are stubbed (book/composition draft) until the Tier-4
// hoist (#04) provides a real reload + the dirty-guard.
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '@/features/chat/providers';
import type { ToolCallRecord } from '@/features/chat/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';
import { runEffectHandlers } from './effectRegistry';
import { registerDefaultEffectHandlers } from './handlers/bookEffects';

export function useStudioEffectReconciler(): void {
  const host = useStudioHost();
  const unit = useManuscriptUnit();
  const { messages } = useChatStream();
  const queryClient = useQueryClient();
  const handledRef = useRef<Set<string>>(new Set());
  // Keep a live ref so the messages-effect always reads the CURRENT unit (dirty state, active id).
  const unitRef = useRef(unit);
  unitRef.current = unit;

  // Register the default handlers once (idempotent).
  useEffect(() => { registerDefaultEffectHandlers(); }, []);

  useEffect(() => {
    for (const m of messages) {
      const records: ToolCallRecord[] = m.tool_calls ?? [];
      records.forEach((tc, i) => {
        // Only SUCCEEDED, non-suspended calls (a pending suspend is Lane A/C, not a domain write).
        if (tc.pending || tc.ok !== true) return;
        // MCP domain records may lack a toolCallId → a stable composite key for dedupe.
        const key = tc.toolCallId ?? `${m.message_id}:${tc.tool}:${tc.iteration ?? i}`;
        if (handledRef.current.has(key)) return;
        handledRef.current.add(key);
        const u = unitRef.current;
        void runEffectHandlers({
          tool: tc.tool, result: tc.result, bookId: host.bookId, host, queryClient,
          isChapterDirty: u ? u.isChapterDirty : undefined,
          // Reload only when the affected chapter IS the active unit (else the hoist holds a
          // different chapter — a no-op, never a hijack).
          reloadChapter: u
            ? (chapterId) => { if (u.state.chapterId === chapterId) void u.reload(); }
            : undefined,
        });
      });
    }
  }, [messages, host, queryClient]);
}
