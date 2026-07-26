// #09 Lane B reconciler — watches the chat stream for COMPLETED MCP tool calls and runs the code
// effect handlers (invalidate / reload / publish). The SOLE path from an agent MCP write → GUI
// refresh (G3). Dedupes so a re-render / message refetch never re-runs a handler.
//
// Mounted only in the studio Compose panel (via the chat provider-slot), so useStudioHost() is
// inside a provider.
//
// Handlers are registered per-domain in `handlers/*.ts`; §8.0b of spec 30 is the one-file-per-domain
// owner map. Coverage is machine-checked by `__tests__/effectCoverage.contract.test.ts` — do not add a
// domain without a row there.
import { useEffect, useRef } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useChatStream } from '@/features/chat/providers';
import type { ToolCallRecord } from '@/features/chat/types';
import { useStudioHost } from '../host/StudioHostProvider';
import { useManuscriptUnit } from '../manuscript/unit/ManuscriptUnitProvider';
import { runEffectHandlers } from './effectRegistry';
import { registerAllStudioEffectHandlers } from './handlers';

export function useStudioEffectReconciler(): void {
  const host = useStudioHost();
  const unit = useManuscriptUnit();
  const { messages } = useChatStream();
  const queryClient = useQueryClient();
  const handledRef = useRef<Set<string>>(new Set());
  // Keep a live ref so the messages-effect always reads the CURRENT unit (dirty state, active id).
  const unitRef = useRef(unit);
  unitRef.current = unit;

  // Register every Lane-B domain handler once (idempotent). Goes through the handlers/index.ts
  // BARREL — the same function effectCoverage.contract.test.ts calls, so a handler file that is not
  // in the barrel is dead in the app AND reds the ledger. Do not hand-roll the list back in here.
  useEffect(() => {
    registerAllStudioEffectHandlers();
  }, []);

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
          reloadScenes: u
            ? (chapterId) => { if (u.state.chapterId === chapterId) void u.reloadScenes(); }
            : undefined,
        });
      });
    }
  }, [messages, host, queryClient]);
}
