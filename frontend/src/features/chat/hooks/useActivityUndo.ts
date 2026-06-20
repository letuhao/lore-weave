import { useCallback } from 'react';
import { useChatStreamOptional } from '../providers';
import type { ActivityEvent } from '../types';

// MCP fan-out (C-ACTIVITY) — the Undo action for a Tier-A activity. Clicking Undo
// must "issue the named reverse tool". The reverse tool is a SERVER MCP tool
// (e.g. chapter_delete, restoreRevision), not a frontend tool, so the FE can't
// call it directly — it drives a fresh agent turn carrying an explicit,
// unambiguous undo directive that names the tool + args. The agent then invokes
// that exact reverse tool (Tier-A reverse ops re-confirm only when destructive).
//
// We send a directive string rather than free prose so the model has no room to
// reinterpret "undo" — the tool name + args are spelled out.

export function useActivityUndo() {
  const stream = useChatStreamOptional();
  const send = stream?.send;

  return useCallback(
    (activity: ActivityEvent) => {
      const undo = activity.undo;
      if (!send || !undo?.available || !undo.tool) return Promise.resolve('');
      const args = undo.args ? JSON.stringify(undo.args) : '{}';
      const directive =
        `Undo the previous action "${activity.summary}". ` +
        `Call the tool \`${undo.tool}\` with arguments ${args}.`;
      return send(directive);
    },
    [send],
  );
}
