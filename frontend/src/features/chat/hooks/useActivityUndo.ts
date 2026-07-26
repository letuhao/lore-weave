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
// /review-impl FIX 2: two hardenings on the LLM-derived undo descriptor —
//   (a) STRUCTURED, not prose-interpolated. We never splice raw `undo.args` JSON
//       into a free-text sentence (where the model would have to RE-PARSE it and
//       could mis-map fields). Instead we emit the {tool,args} as a single fenced
//       JSON block the model maps VERBATIM, plus a one-line human framing. This
//       mirrors how the resume/tool-call path hands the model a typed payload
//       rather than prose.
//   (b) ALLOWLISTED reverse op. The reverse tool name is LLM-derived, so we gate
//       it against a fixed reverse-op allowlist (same defence pattern as
//       ALLOWED_NAV_PREFIXES in uiNav.ts). A `undo.tool` not in the set is never
//       issued — Undo is disabled for it (canUndo === false).

/** Reverse-op allowlist: the only MCP tool names an Undo strip may issue. These
 *  are the documented Tier-A reverse ops (C-ACTIVITY). A reverse tool minted by
 *  the model outside this set is refused — the defence mirror of
 *  ALLOWED_NAV_PREFIXES in nav/uiNav.ts. Extend deliberately as new reversible
 *  Tier-A ops ship; never widen to "any tool". */
export const ALLOWED_UNDO_TOOLS = [
  'chapter_delete',
  'chapter_restore',
  'chapter_update',
  'book_delete',
  'book_restore',
  'glossary_entity_delete',
  'glossary_entity_restore',
  'glossary_restore_revision',
  'wiki_restore_revision',
] as const;

export type AllowedUndoTool = (typeof ALLOWED_UNDO_TOOLS)[number];

/** True when this activity has a usable, allowlisted reverse op. The strip uses
 *  this to enable/disable the Undo button; the issuer re-checks before sending. */
export function canUndo(activity: ActivityEvent): boolean {
  const undo = activity.undo;
  return !!(
    undo?.available &&
    undo.tool &&
    (ALLOWED_UNDO_TOOLS as readonly string[]).includes(undo.tool)
  );
}

/** Build the structured (non-prose) undo directive. The model reads the fenced
 *  JSON verbatim — `tool` + `args` are NOT spliced into prose. Exported for the
 *  unit test so the exact contract is locked. Returns null when the activity is
 *  not undoable/allowlisted. */
export function buildUndoDirective(activity: ActivityEvent): string | null {
  if (!canUndo(activity)) return null;
  const undo = activity.undo!;
  const payload = { tool: undo.tool, args: undo.args ?? {} };
  // One line of human framing + a fenced, machine-parseable directive block.
  // The model invokes the named tool with these exact args (no re-parsing prose).
  return (
    `Undo the previous action "${activity.summary}" by calling the named reverse ` +
    `tool with the arguments below, verbatim:\n` +
    '```undo-directive\n' +
    JSON.stringify(payload) +
    '\n```'
  );
}

export function useActivityUndo() {
  const stream = useChatStreamOptional();
  const send = stream?.send;

  return useCallback(
    (activity: ActivityEvent) => {
      // Respect undo.available===false AND the reverse-op allowlist.
      if (!send || !canUndo(activity)) return Promise.resolve('');
      const directive = buildUndoDirective(activity);
      if (!directive) return Promise.resolve('');
      return send(directive);
    },
    [send],
  );
}
