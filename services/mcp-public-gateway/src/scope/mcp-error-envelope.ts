/**
 * Shared JSON-RPC "isError" TOOL-RESULT envelope (item #10, narrow scope).
 *
 * Three call sites in this package hand-built the SAME `result.isError:true` +
 * `result.content[0].text` shape independently: invoke-tool.ts's `malformedResult()` +
 * `notActivatedError()`, and confirm-action.ts's `confirmActionResult()` business-error
 * branch. Consolidated here into one helper so those three (and any future 4th caller) build
 * an identical envelope instead of re-inventing the shape.
 *
 * Deliberately NOT the raw JSON-RPC transport-error shape (`{jsonrpc, error:{code,message}}`,
 * no `result` wrapper) used by scope-filter.ts's `denyError` and confirm-action.ts's
 * `denyConfirmAction` — that is shape #1, an intentionally different JSON-RPC semantic
 * (a transport-level `-32601 method not allowed`, not a tool RESULT carrying an error) and is
 * explicitly out of scope for this consolidation.
 */
export function buildErrorEnvelope(id: unknown, code: string, message: string): unknown {
  return {
    jsonrpc: '2.0',
    id: id ?? null,
    result: {
      isError: true,
      content: [{ type: 'text', text: JSON.stringify({ code, message }) }],
      structuredContent: { code, message },
    },
  };
}
