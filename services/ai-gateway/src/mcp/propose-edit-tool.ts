// Phase 2 (frontend-tools → MCP migration) — the KIND-B `propose_edit` tool, relocated
// from chat-service's frontend_tools.py to ai-gateway as a CONSUMER-LOCAL tool (the
// tool_list/tool_load/ui_* shape: handled in mcp/handlers.ts with no downstream provider).
// Spec: docs/specs/2026-07-19-frontend-tools-mcp-migration.md §4.1 (KIND B) + D3.
//
// UNLIKE the resolve-immediately ui_* tools, propose_edit is HUMAN-GATED: its effect is a
// CLIENT edit into the open Tiptap document, applied only after the human clicks Apply.
// So the tool VALIDATES its args (the incident's root cause — a propose_edit called with
// propose_record_edit's args once rendered an un-appliable card) and returns a GATED
// PROPOSAL DIRECTIVE (a distinct type from ui-directive): chat-service detects it and
// SUSPENDS the run (its durable chat_suspended_runs is the "task"), the FE renders the
// Apply card, and on Apply the client applies the text + resolves. Nothing is written
// server-side — there is no server executor (contrast KIND-C's durable gate).
//
// SoT: contracts/frontend-tools.contract.json (propose_edit entry) — this is a committed
// MIRROR (ai-gateway can't read the repo-root contract at runtime); propose-edit-tool.
// contract.spec.ts drift-tests it. The prose description moves here from frontend_tools.py
// (a MOVE, not a duplication — Phase 4 removes chat-service's copy).

/** A gated-proposal directive marker in a propose_edit tool result. Distinct from the
 * resolve-immediately UI_DIRECTIVE_TYPE: the client must GATE on the human (Apply/Dismiss)
 * before acting, never navigate/apply automatically. */
export const PROPOSE_EDIT_DIRECTIVE_TYPE = 'io.loreweave/propose-edit';

export const PROPOSE_EDIT_OPERATIONS = ['insert_at_cursor', 'replace_selection'] as const;

export const PROPOSE_EDIT_TOOL = {
  name: 'propose_edit',
  description:
    'Propose an edit to the chapter the user is currently writing. The edit is shown to the ' +
    'user with an Apply button and is NOT applied automatically — the user reviews it first. ' +
    'Use this to suggest inserting new prose at the cursor, or rewriting the current selection. ' +
    'After the user decides, you receive whether they applied or dismissed it.',
  inputSchema: {
    type: 'object' as const,
    properties: {
      operation: {
        type: 'string',
        enum: [...PROPOSE_EDIT_OPERATIONS],
        description:
          'insert_at_cursor = insert `text` at the user\'s cursor. replace_selection = replace ' +
          'the user\'s currently selected text with `text`.',
      },
      text: { type: 'string', description: 'The prose to insert, or the replacement for the selection.' },
      rationale: { type: 'string', description: 'Optional one-line explanation shown to the user.' },
    },
    required: ['operation', 'text'],
    additionalProperties: false,
  },
};

export const PROPOSE_EDIT_NAME = PROPOSE_EDIT_TOOL.name;

export interface ProposeEditValidationOk {
  ok: true;
}
export interface ProposeEditValidationError {
  ok: false;
  error: string;
}

/** Validate propose_edit args: `operation` present + in the enum, `text` present + a string.
 * Returns the enum/required signal on any miss (the model repairs it) — never a silent pass,
 * which is the exact bug class this migration exists to kill. */
export function validateProposeEditArgs(
  args: Record<string, unknown>,
): ProposeEditValidationOk | ProposeEditValidationError {
  const a = args ?? {};
  const op = a.operation;
  if (op === undefined || op === null || op === '') {
    return { ok: false, error: "required: missing property 'operation' for propose_edit" };
  }
  if (typeof op !== 'string') {
    return { ok: false, error: 'type: operation must be a string for propose_edit' };
  }
  if (!(PROPOSE_EDIT_OPERATIONS as readonly string[]).includes(op)) {
    return {
      ok: false,
      error: `enum: '${op}' is not a valid operation for propose_edit — allowed: ${PROPOSE_EDIT_OPERATIONS.join(', ')}`,
    };
  }
  const text = a.text;
  if (text === undefined || text === null || text === '') {
    return { ok: false, error: "required: missing property 'text' for propose_edit" };
  }
  if (typeof text !== 'string') {
    return { ok: false, error: 'type: text must be a string for propose_edit' };
  }
  if (a.rationale !== undefined && a.rationale !== null && typeof a.rationale !== 'string') {
    return { ok: false, error: 'type: rationale must be a string for propose_edit' };
  }
  return { ok: true };
}

/** A consumer-local propose_edit CallTool result. On valid args → a GATED proposal directive
 * (structuredContent carries {type: PROPOSE_EDIT_DIRECTIVE_TYPE, operation, text, rationale?})
 * that chat-service suspends on and the FE renders as an Apply card; on invalid → an isError
 * result with the enum/required signal (never a silent no-op). */
export function handleProposeEdit(args: Record<string, unknown>): {
  content: { type: 'text'; text: string }[];
  structuredContent: Record<string, unknown>;
  isError?: boolean;
} {
  const check = validateProposeEditArgs(args ?? {});
  if (!check.ok) {
    return {
      content: [{ type: 'text', text: check.error }],
      structuredContent: { code: 'propose_edit_invalid_args', message: check.error },
      isError: true,
    };
  }
  const a = args ?? {};
  const directive: Record<string, unknown> = {
    type: PROPOSE_EDIT_DIRECTIVE_TYPE,
    operation: a.operation,
    text: a.text,
  };
  if (typeof a.rationale === 'string' && a.rationale) directive.rationale = a.rationale;
  return {
    content: [{ type: 'text', text: 'proposal: the user will review and Apply or Dismiss this edit.' }],
    structuredContent: directive,
  };
}
