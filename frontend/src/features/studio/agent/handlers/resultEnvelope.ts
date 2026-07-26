// Shared cross-handler unwrap for the M-E live-caught bug class: the live stream delivers the
// chat-service TOOL_CALL_RESULT envelope `{ok, result}` — the domain payload a handler actually
// wants is NESTED under `.result`, and that nested value may itself still be a JSON STRING (MCP
// text content). A handler that only reads the top-level result works in unit tests (which feed
// the payload already unwrapped) but silently no-ops live (bookEffects.ts's `chapterIdFromResult`
// first hit this; extracted here so a THIRD handler doesn't reintroduce it — glossaryEffects.ts
// was the second, found by /review-impl).
export function unwrapToolResult(result: unknown): unknown {
  if (!result || typeof result !== 'object') return null;
  let inner = (result as Record<string, unknown>).result;
  if (typeof inner === 'string') {
    try { inner = JSON.parse(inner); } catch { return null; }
  }
  return inner ?? null;
}
