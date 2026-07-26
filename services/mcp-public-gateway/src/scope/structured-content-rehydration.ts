/**
 * MCP spec 2025-06-18 (Tools § Structured Content) compliance for LEGACY clients — the one
 * place in this repo where "does the caller understand `structuredContent`?" is actually
 * unknown at request time: an external agent through this edge, whose protocol version we
 * don't control.
 *
 * Background (external MCP discoverability audit #9): domain services now compact
 * `content[0].text` to a short constant placeholder whenever `structuredContent` is present
 * (`sdks/go/loreweave_mcp.RegisterTool` / `sdks/python/loreweave_mcp.patch_convert_result`),
 * saving ~2x tokens per call — safe for our OWN internal traffic (chat-service → ai-gateway →
 * domain service), since we control both ends and always read `structuredContent`.
 *
 * BUT the spec's own wording is a real, verified normative recommendation, not a nitpick:
 * "For backwards compatibility, a tool that returns structured content SHOULD also return the
 * serialized JSON in a TextContent block" — https://modelcontextprotocol.io/specification/2025-06-18/server/tools#structured-content.
 * `structuredContent` itself was INTRODUCED in the 2025-06-18 revision — a client that
 * negotiated an OLDER protocol version (2025-03-26 / 2024-11-05 / 2024-10-07,
 * per `@modelcontextprotocol/sdk`'s `SUPPORTED_PROTOCOL_VERSIONS`) has no way to read
 * `structuredContent` at all. Serving it the placeholder wouldn't just cost it more tokens
 * (the pre-fix state) — it would silently lose 100% of the tool's actual data, a real
 * regression for a third-party client we don't control (unlike our own internal traffic).
 *
 * This can only be resolved by branching per-client (per the ORIGINAL #9 writeup's own
 * fallback suggestion: "make it configurable per-client via a capability flag") — never in
 * the response body alone. This edge is the ONLY layer in the repo that actually terminates
 * the MCP handshake with an external client (`ai-gateway`'s own MCP `Server` is rebuilt
 * fresh, stateless, per HTTP request and exposes no negotiated-version getter — see the
 * investigation behind this file), so it's the only place with in-request access to what
 * that specific client negotiated: the `MCP-Protocol-Version` header, which a compliant
 * HTTP-transport client sends on every request after `initialize` (this edge already reads
 * it, at `public-mcp.controller.ts`'s `mcpVersion` local, purely to forward it — this module
 * is the first thing to actually USE it).
 *
 * Deliberately conservative: an ABSENT or unrecognized version is treated as "cannot confirm
 * structuredContent support" — rehydrate. A false-positive rehydration (a modern client that
 * simply forgot to send the header) costs that one response some tokens; a false-negative
 * (assuming support that isn't there) silently destroys data for a client we can never see the
 * complaint from. The costs are not symmetric, so the default favors correctness over savings.
 *
 * Only rehydrates a block matching the EXACT known placeholder strings our own SDKs emit —
 * never touches any other `content`, so a handler's genuinely custom content (or a tool that
 * was never compacted in the first place, e.g. `find_tools`'s own synthetic response, which
 * always duplicates unconditionally) is completely unaffected either way.
 */

// The first spec revision to define `structuredContent` (verified against the spec text
// above). Both dates being ISO 8601 (YYYY-MM-DD) means plain string comparison sorts
// correctly — this stays valid for any future protocol version without needing an
// allowlist bump every time `@modelcontextprotocol/sdk` adds one.
const STRUCTURED_CONTENT_MIN_VERSION = '2025-06-18';

// Must stay byte-identical to `compactContentPlaceholder` (sdks/go/loreweave_mcp/register_tool.go)
// and `_PLACEHOLDER_TEXT` (sdks/python/loreweave_mcp/compact_content.py) — this is the exact
// marker that distinguishes "we deliberately compacted this" from any other content shape.
const KNOWN_PLACEHOLDER_TEXTS = new Set(['ok — see structuredContent for the full result']);

/** Whether a client that negotiated `protocolVersion` can be trusted to read `structuredContent`. */
export function clientSupportsStructuredContent(protocolVersion: string | null | undefined): boolean {
  return typeof protocolVersion === 'string' && protocolVersion.length > 0 && protocolVersion >= STRUCTURED_CONTENT_MIN_VERSION;
}

interface RehydratableResult {
  content?: unknown;
  structuredContent?: unknown;
}

function rehydrateOneResult(result: unknown): boolean {
  if (!result || typeof result !== 'object') return false;
  const r = result as RehydratableResult;
  if (r.structuredContent === undefined || !Array.isArray(r.content) || r.content.length === 0) return false;
  const first = r.content[0] as { type?: unknown; text?: unknown };
  if (first?.type !== 'text' || typeof first.text !== 'string' || !KNOWN_PLACEHOLDER_TEXTS.has(first.text)) {
    return false; // not our placeholder — leave whatever this is untouched
  }
  first.text = JSON.stringify(r.structuredContent);
  return true;
}

/**
 * Rehydrates every compacted `content[0].text` placeholder back to the full serialized
 * `structuredContent` JSON, for a client whose negotiated protocol version can't be
 * confirmed to support `structuredContent`. A no-op (returns `rawBody` unchanged, by
 * reference-equal string) when the client's version supports it, when the body isn't
 * parseable JSON (e.g. an SSE stream), or when nothing in the body matches our own
 * placeholder marker.
 */
export function rehydrateContentForLegacyClients(rawBody: string, protocolVersion: string | null | undefined): string {
  if (clientSupportsStructuredContent(protocolVersion)) return rawBody;
  let parsed: unknown;
  try {
    parsed = JSON.parse(rawBody);
  } catch {
    return rawBody; // not JSON (e.g. SSE) — never touch
  }
  const messages = Array.isArray(parsed) ? parsed : [parsed];
  let changed = false;
  for (const m of messages) {
    if (m && typeof m === 'object' && 'result' in (m as Record<string, unknown>)) {
      if (rehydrateOneResult((m as { result?: unknown }).result)) changed = true;
    }
  }
  return changed ? JSON.stringify(parsed) : rawBody;
}
