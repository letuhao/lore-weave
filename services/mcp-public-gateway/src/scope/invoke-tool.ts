/**
 * `invoke_tool` — the always-present execution facade that makes lazy tool-loading actually
 * WORK for a standard MCP client (PURE helpers, unit-tested).
 *
 * The lazy-loading design (find_tools discovers, the match becomes "activated" server-side)
 * assumed a client would re-fetch `tools/list` after activation. In practice a spec-compliant
 * client (Claude Code confirmed; most others too) caches `tools/list` ONCE at connect and never
 * re-polls mid-session — so an "activated" tool can never actually be CALLED: the client refuses
 * to send a `tools/call` for a name it never saw in its cached list. `invoke_tool` is always in
 * `tools/list` (like `find_tools`), so it IS callable; its job is to unwrap `{name, arguments}`
 * into a normal `tools/call` for the real target — done at the very top of the request pipeline
 * (`public-mcp.controller.ts`, BEFORE rate-limiting/scope-gate/idempotency read the body) so every
 * existing gate keeps working unmodified: after the unwrap, the request IS indistinguishable from
 * the agent having called the real tool directly.
 */

export const INVOKE_TOOL_NAME = 'invoke_tool';

/** The synthetic `invoke_tool` tool definition injected into every `tools/list` response
 * (mirrors `confirm-action.ts`'s `CONFIRM_ACTION_TOOL` injection pattern). */
export const INVOKE_TOOL_TOOL = {
  name: INVOKE_TOOL_NAME,
  description:
    'Execute a tool by name — REQUIRED to actually run a tool a find_tools match returned; ' +
    "calling that tool's name directly will not work (it is not in this list). Pass the exact " +
    "`name` from a find_tools match and `arguments` per the schema find_tools described.",
  inputSchema: {
    type: 'object',
    properties: {
      name: { type: 'string', description: 'The exact tool name from a find_tools match.' },
      arguments: { type: 'object', description: "The target tool's arguments, per its find_tools description." },
    },
    required: ['name'],
    additionalProperties: false,
  },
};

interface JsonRpcCall {
  jsonrpc?: unknown;
  method?: unknown;
  id?: unknown;
  params?: { name?: unknown; arguments?: unknown };
}

/** A malformed `invoke_tool` call — shaped as an MCP tool-error result (never a silent no-op),
 * so the agent sees exactly what to fix. */
function malformedResult(id: unknown): unknown {
  return {
    jsonrpc: '2.0',
    id: id ?? null,
    result: {
      isError: true,
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: 'invoke_tool requires a string "name" — the target tool name from a find_tools match.',
        }),
      }],
    },
  };
}

export type InvokeToolDetection =
  | { kind: 'rewrite'; rewritten: unknown; targetName: string }
  | { kind: 'malformed'; response: unknown };

/**
 * Detect + unwrap a SINGLE (non-batch) `invoke_tool` call into a normal `tools/call` for its
 * real target. Returns null when the body isn't an invoke_tool call — pass it through as-is.
 * v1 is single-call only (mirrors confirm_action's batch-exclusion precedent); a batched
 * invoke_tool call falls through unrewritten and is denied by the ordinary scope gate
 * (invoke_tool carries no TOOL_POLICY entry of its own).
 */
export function detectInvokeToolCall(body: unknown): InvokeToolDetection | null {
  if (Array.isArray(body) || !body || typeof body !== 'object') return null;
  const m = body as JsonRpcCall;
  if (m.method !== 'tools/call' || m.params?.name !== INVOKE_TOOL_NAME) return null;

  const args = (m.params?.arguments ?? {}) as Record<string, unknown>;
  const targetName = args.name;
  if (typeof targetName !== 'string' || !targetName) {
    return { kind: 'malformed', response: malformedResult(m.id) };
  }
  const targetArgs = args.arguments && typeof args.arguments === 'object' ? args.arguments : {};
  return {
    kind: 'rewrite',
    targetName,
    rewritten: { ...m, params: { name: targetName, arguments: targetArgs } },
  };
}

/** Synthetic edge tools that need no prior find_tools activation: `find_tools` itself (an
 * agent would never route it through invoke_tool, but it must not dead-end on the activation
 * check if it does — it still gets scope-gated normally downstream) and `confirm_action`
 * (already its own always-advertised synthetic tool). `invoke_tool` itself is listed too so
 * a self-referential `invoke_tool(name: "invoke_tool", ...)` never dead-ends HERE — it is
 * NOT a no-op, though: `gateRequestBody` denies it downstream (no TOOL_POLICY entry for
 * `invoke_tool`), same fail-closed outcome as any other unclassified tool name. */
const ALWAYS_AVAILABLE = new Set(['find_tools', 'confirm_action', INVOKE_TOOL_NAME]);

/** True iff `name` must have been find_tools-activated this session before invoke_tool may
 * call it. Scope-safe by construction: `toolActivation`'s activated set can only ever contain
 * names `isToolAllowed` already passed (see scope-filter.ts `filterOneFindToolsResult`), so this
 * check can never be MORE permissive than the scope gate that still runs after it. */
export function requiresActivation(name: string): boolean {
  return !ALWAYS_AVAILABLE.has(name);
}

/** The anti-oracle denial for an invoke_tool target that hasn't been activated this session.
 * Deliberately the SAME message shape whether the name is genuinely undiscovered-but-in-scope
 * or actually out of scope (out-of-scope names can never enter the activated set either — see
 * `requiresActivation` — so this can't leak more than find_tools already would). */
export function notActivatedError(id: unknown, name: string): unknown {
  return {
    jsonrpc: '2.0',
    id: id ?? null,
    result: {
      isError: true,
      content: [{
        type: 'text',
        text: JSON.stringify({
          error: `'${name}' is not available yet — call find_tools with what you want to do, then invoke_tool with a name it returns.`,
        }),
      }],
    },
  };
}

interface ToolsListResult {
  result?: { tools?: unknown };
}

/**
 * Edge-only `tools/list` augmentation, run in the same pass as `filterListResponseText`:
 * appends `INVOKE_TOOL_TOOL` (idempotent) and rewrites `find_tools`'s description to state the
 * edge-specific flow (this endpoint hides every other tool; ai-gateway's own shared
 * `FIND_TOOLS_TOOL` text stays generic for a direct, non-edge consumer where find_tools'
 * "become callable" claim is literally true — the full catalogue is never hidden there).
 */
const EDGE_FIND_TOOLS_DESCRIPTION =
  'Find tools that can perform an intent. Call this FIRST when you need a capability you ' +
  "don't already have. Returns matching tool names + descriptions — then call `invoke_tool` " +
  '(name, arguments) to actually RUN one; calling the matched name directly will not work ' +
  'through this endpoint. If it returns nothing useful, try once more with broader wording.';

function augmentOneListMessage(msg: ToolsListResult): void {
  const tools = msg?.result?.tools;
  if (!Array.isArray(tools)) return;
  for (const t of tools) {
    if (t && typeof t === 'object' && (t as { name?: unknown }).name === 'find_tools') {
      (t as { description?: unknown }).description = EDGE_FIND_TOOLS_DESCRIPTION;
    }
  }
  if (!tools.some((t) => (t as { name?: unknown })?.name === INVOKE_TOOL_NAME)) {
    tools.push(INVOKE_TOOL_TOOL);
  }
}

/** Parse-or-passthrough like `injectConfirmActionTool` — on unparseable JSON, returns the text
 * unchanged rather than throwing. */
export function injectInvokeToolTool(text: string): string {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    return text;
  }
  if (Array.isArray(parsed)) parsed.forEach((m) => augmentOneListMessage(m as ToolsListResult));
  else augmentOneListMessage(parsed as ToolsListResult);
  return JSON.stringify(parsed);
}
