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
/**
 * C4 (contract) — the CLOSED stable tool-error code set, copied from ai-gateway
 * (handlers.ts TOOL_ERROR_CODES). The public edge builds its OWN errors (rate-limit,
 * scope-deny, malformed invoke, confirm-deny) that never reach ai-gateway's normalizer,
 * so they must use the same closed vocabulary. Relayed downstream tool failures are
 * already normalized upstream — this file only governs edge-generated tool-RESULT errors.
 * Extend only in lockstep with ai-gateway + contracts.md C4.
 */
export const TOOL_ERROR_CODES = [
  'VALIDATION',
  'NOT_FOUND',
  'NOT_PERMITTED',
  'NOT_DISCOVERED',
  'CONFIRM_REQUIRED',
  'CONFIRM_FAILED',
  'BUSINESS_RULE',
  'RATE_LIMITED',
  'UPSTREAM_UNAVAILABLE',
] as const;
export type ToolErrorCode = (typeof TOOL_ERROR_CODES)[number];

/**
 * Map an edge-local or upstream-authored code into the C4 closed set. An already-C4
 * code passes through; auth-service / edge codes are folded to their closest C4 class,
 * defaulting to BUSINESS_RULE (the "ran and was refused on merits" bucket — matches
 * ai-gateway's inferCodeFromText default). NEVER used on an anti-oracle deny path (those
 * keep a single fixed code so NOT_PERMITTED/NOT_FOUND can't be distinguished).
 */
export function toC4Code(code: string): ToolErrorCode {
  if ((TOOL_ERROR_CODES as readonly string[]).includes(code)) return code as ToolErrorCode;
  const c = code.toLowerCase();
  // Keyword-based so auth-service's arbitrary codes (AUTH_APPROVAL_EXPIRED, …) and the
  // edge's own (MALFORMED_INVOKE_ARGS, TOOL_NOT_DISCOVERED) fold without an exhaustive list.
  if (/not_discovered|undiscovered/.test(c)) return 'NOT_DISCOVERED';
  if (/expired|confirm.*fail|approval/.test(c)) return 'CONFIRM_FAILED';
  if (/permission|forbidden|not.?permitted|unauthorized/.test(c)) return 'NOT_PERMITTED';
  if (/rate.?limit|too.?many/.test(c)) return 'RATE_LIMITED';
  if (/not.?found|unroutable|no.?such|missing/.test(c)) return 'NOT_FOUND';
  if (/malformed|validation|invalid|required|bad.?request/.test(c)) return 'VALIDATION';
  if (/unavailable|timeout|upstream/.test(c)) return 'UPSTREAM_UNAVAILABLE';
  return 'BUSINESS_RULE';
}

export function buildErrorEnvelope(id: unknown, code: string, message: string): unknown {
  const c4 = toC4Code(code);
  return {
    jsonrpc: '2.0',
    id: id ?? null,
    result: {
      isError: true,
      // C4 — top-level `code` mirrors structuredContent.code (parity with ai-gateway's
      // toolErrorEnvelope), so a consumer can branch without parsing content.
      code: c4,
      content: [{ type: 'text', text: JSON.stringify({ code: c4, message }) }],
      structuredContent: { code: c4, message },
    },
  };
}
