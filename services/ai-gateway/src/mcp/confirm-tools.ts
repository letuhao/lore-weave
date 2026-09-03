// The three KIND-C human-gate tools, as ai-gateway CONSUMER-LOCAL DIRECTIVE tools.
//
// 🔴 WHY DIRECTIVES AND NOT DOMAIN MCP TOOLS. These three ARE the human gate: a card is
// rendered, a person clicks, and the BROWSER posts to POST /v1/<domain>/actions/confirm (or
// PATCHes the record). A domain MCP tool has a SERVER EXECUTOR — the model calls it and the
// server performs the write — so re-homing them that way would let the model complete its own
// confirmation with no human in the loop, deleting the gate they exist to provide, and every
// test would still pass because nothing asserts "a human was involved".
//
// So they take propose_edit's P2.2 shape (propose-edit-tool.ts): a GATED directive in
// structuredContent that chat-service detects in the RESULT and suspends on, and the FE renders
// as a card. No server executor. See docs/plans/2026-09-03-retire-v1-BUILD.md DQ-V9, which
// overturns DQ-V5's "glossary-service MCP tools" ruling for exactly this reason.
//
// WHAT THIS DOES NOT CHANGE. The confirm_token spine is untouched and PERMANENT (mcp-tool-io.md
// GATE-2): domains keep minting tokens for non-tasks clients, and `confirm_action` keeps
// redeeming them. mcp-public-gateway's OWN confirm_action (src/scope/confirm-action.ts) is a
// different tool with the same name and is not affected.
//
// Arg shapes are the contract's (contracts/browser-tools.contract.json), which stays the SoT.

/** A gated CONFIRM directive. Distinct from PROPOSE_EDIT_DIRECTIVE_TYPE (an editor write) and
 *  from UI_DIRECTIVE_TYPE (resolve-immediately nav): the client must gate on the human, then
 *  commit through the domain's own confirm route. */
export const CONFIRM_DIRECTIVE_TYPE = 'io.loreweave/confirm-action';

/** The GLOSSARY-scoped confirm's own marker.
 *
 *  🔴 IT MUST NOT SHARE `CONFIRM_DIRECTIVE_TYPE`. It did, and that silently broke a card.
 *  chat-service maps marker -> suspend NAME, so emitting the shared marker made every
 *  `glossary_confirm_action` call suspend as `confirm_action`. The main chat UI accepts either
 *  name and was unaffected; `cms-frontend`'s admin transcript gates on exactly
 *  `tc.tool === 'glossary_confirm_action'` (MessageList.tsx) and has NO auto-confirm fallback, so
 *  its AdminConfirmCard stopped rendering and the confirm became a 10px grey text line an admin
 *  cannot click. TypeScript cannot see this: the name crosses the wire as a string.
 *
 *  The rule this restores is the one the move was justified by — **the tool's HOME changed; its
 *  IDENTITY did not.** A marker that collapses two tools into one name changes the identity. */
export const GLOSSARY_CONFIRM_DIRECTIVE_TYPE = 'io.loreweave/glossary-confirm-action';

/** A gated RECORD-EDIT directive (glossary_propose_entity_edit): the browser PATCHes the record
 *  with If-Match after the human approves. There is no server executor — GATE-2 class (d). */
export const RECORD_EDIT_DIRECTIVE_TYPE = 'io.loreweave/propose-record-edit';

const CONFIRM_DOMAINS = ['glossary', 'book', 'composition', 'translation', 'settings'] as const;

type Check = { ok: true } | { ok: false; error: string };

function requireString(a: Record<string, unknown>, key: string, tool: string): Check {
  const v = a[key];
  if (v === undefined || v === null) {
    return { ok: false, error: `required: missing property '${key}' for ${tool}` };
  }
  if (typeof v !== 'string' || v === '') {
    return { ok: false, error: `type: ${key} must be a non-empty string for ${tool}` };
  }
  return { ok: true };
}

/** Validate `confirm_action`. The domain enum is closed and validated HERE, on the wire —
 *  a free string was how a weak model reached a resolver that silently no-op'd (IN-3). */
export function validateConfirmAction(args: Record<string, unknown>): Check {
  const a = args ?? {};
  for (const k of ['confirm_token', 'descriptor', 'title', 'domain']) {
    const c = requireString(a, k, 'confirm_action');
    if (!c.ok) return c;
  }
  if (!CONFIRM_DOMAINS.includes(a.domain as (typeof CONFIRM_DOMAINS)[number])) {
    return {
      ok: false,
      error:
        `enum: domain must be one of ${CONFIRM_DOMAINS.join(', ')} for confirm_action ` +
        `(got ${JSON.stringify(a.domain)})`,
    };
  }
  if (a.items !== undefined && a.items !== null && !Array.isArray(a.items)) {
    return { ok: false, error: 'type: items must be an array for confirm_action' };
  }
  return { ok: true };
}

/** Validate `glossary_confirm_action` — the glossary-scoped confirm. No `domain`: it is implied,
 *  which is why it is a separate tool rather than a default on the general one. */
export function validateGlossaryConfirmAction(args: Record<string, unknown>): Check {
  const a = args ?? {};
  for (const k of ['confirm_token', 'descriptor', 'title']) {
    const c = requireString(a, k, 'glossary_confirm_action');
    if (!c.ok) return c;
  }
  return { ok: true };
}

/** Validate `glossary_propose_entity_edit` — the C1 record edit.
 *
 *  🔴 `base_version` IS REQUIRED AND IS NOT DECORATION: the browser sends it as If-Match, so a
 *  missing or stale one is what turns a concurrent edit into a lost update. */
export function validateGlossaryProposeEntityEdit(args: Record<string, unknown>): Check {
  const a = args ?? {};
  for (const k of ['book_id', 'entity_id', 'base_version']) {
    const c = requireString(a, k, 'glossary_propose_entity_edit');
    if (!c.ok) return c;
  }
  if (!Array.isArray(a.changes)) {
    return {
      ok: false,
      error: "required: missing property 'changes' for glossary_propose_entity_edit (an array)",
    };
  }
  if (a.changes.length === 0) {
    return { ok: false, error: 'changes must not be empty for glossary_propose_entity_edit' };
  }
  if (a.rationale !== undefined && a.rationale !== null && typeof a.rationale !== 'string') {
    return { ok: false, error: 'type: rationale must be a string for glossary_propose_entity_edit' };
  }
  return { ok: true };
}

type ToolResult = {
  content: { type: 'text'; text: string }[];
  structuredContent: Record<string, unknown>;
  isError?: boolean;
};

function invalid(tool: string, error: string): ToolResult {
  return {
    content: [{ type: 'text', text: error }],
    structuredContent: { code: `${tool}_invalid_args`, message: error },
    isError: true,
  };
}

/** confirm_action → a gated confirm directive the FE renders as a Confirm card. */
export function handleConfirmAction(args: Record<string, unknown>): ToolResult {
  const check = validateConfirmAction(args ?? {});
  if (!check.ok) return invalid('confirm_action', check.error);
  const a = args ?? {};
  const directive: Record<string, unknown> = {
    type: CONFIRM_DIRECTIVE_TYPE,
    confirm_token: a.confirm_token,
    descriptor: a.descriptor,
    title: a.title,
    domain: a.domain,
  };
  if (Array.isArray(a.items) && a.items.length) directive.items = a.items;
  return {
    content: [
      {
        type: 'text',
        text: 'confirmation requested: the user will Confirm or Cancel. Report the change as ' +
          'done ONLY on an action_done outcome.',
      },
    ],
    structuredContent: directive,
  };
}

/** glossary_confirm_action → its OWN marker, with the domain implied. */
export function handleGlossaryConfirmAction(args: Record<string, unknown>): ToolResult {
  const check = validateGlossaryConfirmAction(args ?? {});
  if (!check.ok) return invalid('glossary_confirm_action', check.error);
  const a = args ?? {};
  return {
    content: [
      {
        type: 'text',
        text: 'confirmation requested: the user will Confirm or Cancel. Report the change as ' +
          'done ONLY on an action_done outcome.',
      },
    ],
    structuredContent: {
      type: GLOSSARY_CONFIRM_DIRECTIVE_TYPE,
      confirm_token: a.confirm_token,
      descriptor: a.descriptor,
      title: a.title,
      domain: 'glossary',
    },
  };
}

/** glossary_propose_entity_edit → a gated record-edit directive; the browser PATCHes on approval. */
export function handleGlossaryProposeEntityEdit(args: Record<string, unknown>): ToolResult {
  const check = validateGlossaryProposeEntityEdit(args ?? {});
  if (!check.ok) return invalid('glossary_propose_entity_edit', check.error);
  const a = args ?? {};
  const directive: Record<string, unknown> = {
    type: RECORD_EDIT_DIRECTIVE_TYPE,
    book_id: a.book_id,
    entity_id: a.entity_id,
    base_version: a.base_version,
    changes: a.changes,
  };
  if (typeof a.rationale === 'string' && a.rationale) directive.rationale = a.rationale;
  return {
    content: [
      { type: 'text', text: 'proposal: the user will review these changes and Apply or Dismiss them.' },
    ],
    structuredContent: directive,
  };
}

// ── The tool DEFINITIONS ─────────────────────────────────────────────────────────────────────
//
// GENERATED FROM the chat-service defs at move time (2026-09-03), not retyped: the descriptions
// run to several hundred characters each and a description is what decides WHEN a weak model
// reaches for a tool, so a transcription slip is a behaviour change that no schema test catches.
// `served_by` is the one field deliberately changed — this file is now the server.
//
// After V7 deletes the chat-service copies there is no second definition to drift from, which is
// why these carry no mirror test: the drift surface is gone rather than guarded.

export const CONFIRM_ACTION_TOOL = {
  "name": "confirm_action",
  "description": "Ask the user to CONFIRM a high-impact action (publish, delete, start a PRICED job, change a default) that you proposed with a domain MCP tool. Pass the `confirm_token`, `descriptor`, and `domain` you received from that propose call. High-impact and irreversible changes ALWAYS require explicit human confirmation — the action is NOT applied automatically. For a BULK action (e.g. publish several chapters) pass `items` so the user gets ONE card with a single Apply, not many cards. After the user decides you receive an `outcome`: `action_done` (applied), `token_expired` (the confirmation lapsed — propose again), `action_error` (it failed), or `cancelled` (the user declined). State that the change happened ONLY when the outcome is `action_done`.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "confirm_token": {
        "type": "string",
        "description": "The confirm_token returned by the propose call."
      },
      "descriptor": {
        "type": "string",
        "description": "The action descriptor from the propose call (e.g. 'book.publish', 'translation.start_job')."
      },
      "title": {
        "type": "string",
        "description": "Human-readable title of the action, shown on the card."
      },
      "domain": {
        "type": "string",
        "enum": [
          "glossary",
          "book",
          "composition",
          "translation",
          "settings"
        ],
        "description": "Selects which service commits the action on Confirm."
      },
      "items": {
        "type": "array",
        "description": "OPTIONAL — for a BATCH confirm: one entry per affected row (e.g. the chapters to publish). The browser renders one card listing all of them with a single Apply.",
        "items": {
          "type": "object",
          "additionalProperties": true
        }
      }
    },
    "required": [
      "confirm_token",
      "descriptor",
      "title",
      "domain"
    ],
    "additionalProperties": false
  },
  "_meta": {
    "tier": "W",
    "scope": "none",
    "served_by": "ai-gateway"
  }
} as const;

export const GLOSSARY_CONFIRM_ACTION_TOOL = {
  "name": "glossary_confirm_action",
  "description": "Ask the user to CONFIRM a high-impact glossary action (a new kind/attribute, or DELETING a genre/kind/attribute) that you proposed with a glossary_propose_* or glossary_ontology_delete MCP tool. Pass the `confirm_token` and `descriptor` you received from that propose call. The action is shown with a Confirm button and is NOT applied automatically — high-impact and destructive changes ALWAYS require explicit human confirmation. After the user decides you receive an `outcome`: `action_done` (applied), `token_expired` (the confirmation lapsed — propose again), `action_error` (it failed), or `cancelled` (the user declined). State that the change happened ONLY when the outcome is `action_done`.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "confirm_token": {
        "type": "string",
        "description": "The confirm_token returned by the propose call."
      },
      "descriptor": {
        "type": "string",
        "description": "The action `descriptor` from the propose call (e.g. book_delete, schema_create_kind) — keys which confirm card the browser renders."
      },
      "title": {
        "type": "string",
        "description": "Human-readable title of the action (the `title` from the propose call), shown on the confirm card."
      }
    },
    "required": [
      "confirm_token",
      "descriptor",
      "title"
    ],
    "additionalProperties": false
  },
  "_meta": {
    "tier": "W",
    "scope": "none",
    "served_by": "ai-gateway",
    "_confirm_step": true
  }
} as const;

export const GLOSSARY_PROPOSE_ENTITY_EDIT_TOOL = {
  "name": "glossary_propose_entity_edit",
  "description": "Propose ONE OR MORE edits to an EXISTING glossary entity (correct the name, an alias, the description, and/or any attribute) — all applied TOGETHER, atomically. The changes are shown to the user as a diff card with an Apply button and are NOT applied automatically — the user reviews them first. BEFORE calling this, call glossary_get_entity to read the current values and the entity's `updated_at` (pass it as `base_version`); for an attribute edit also read that attribute's `attr_value_id`. PRESERVE each value's format in `new_value` — if `old_value` is a JSON array (e.g. aliases like [\"King\",\"Art\"]) keep it a JSON array; if it is a number or a fixed option, keep that shape. After the user decides you receive an `outcome`: `applied_saved` (the edit was saved), `applied_conflict` (the entity changed since you read it — call glossary_get_entity again and propose afresh), `applied_error` (the save failed), or `dismissed` (the user declined). State that the change was made ONLY when the outcome is `applied_saved`. This tool ONLY EDITS an entity that ALREADY EXISTS. To CREATE a new entity that does not exist yet, call `tool_load(name='glossary_propose_entities')` and use that instead — do NOT call this with a made-up or placeholder entity_id.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "book_id": {
        "type": "string",
        "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        "description": "The book the entity belongs to (UUID)."
      },
      "entity_id": {
        "type": "string",
        "pattern": "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$",
        "description": "The entity to edit (UUID, from glossary_get_entity/glossary_search). MUST be a real existing entity's id — never a placeholder."
      },
      "base_version": {
        "type": "string",
        "description": "The entity's `updated_at` value from glossary_get_entity — used to detect a concurrent change (optimistic concurrency). One token covers ALL the changes (they apply in a single transaction)."
      },
      "changes": {
        "type": "array",
        "description": "One or more field changes to apply together. A single-field edit is just a one-element array.",
        "items": {
          "type": "object",
          "properties": {
            "target": {
              "type": "string",
              "enum": [
                "short_description",
                "attribute"
              ],
              "description": "short_description = the entity's summary. attribute = one attribute value (name, aliases, or any attribute), identified by attr_value_id."
            },
            "attr_value_id": {
              "type": "string",
              "description": "Required when target=attribute: the attribute value to change (from glossary_get_entity)."
            },
            "field_label": {
              "type": "string",
              "description": "Human-readable label of the field (e.g. 'Name', 'Aliases', 'Description'), shown on the diff card."
            },
            "old_value": {
              "type": "string",
              "description": "The current value, for the diff."
            },
            "new_value": {
              "type": "string",
              "description": "The proposed new value."
            }
          },
          "required": [
            "target",
            "field_label",
            "old_value",
            "new_value"
          ],
          "additionalProperties": false
        }
      },
      "rationale": {
        "type": "string",
        "description": "Optional one-line explanation shown to the user."
      }
    },
    "required": [
      "book_id",
      "entity_id",
      "base_version",
      "changes"
    ],
    "additionalProperties": false
  },
  "_meta": {
    "tier": "W",
    "scope": "book",
    "served_by": "ai-gateway"
  }
} as const;
