# Plan — Lazy tool-loading (find_tools) for the public MCP edge

**Date:** 2026-06-29 · **Branch:** `fix/critical-ux-bugs` · **Size:** L (two TS services on the
public-security edge — needs /review-impl).

## Problem (verified in code)

The public MCP gateway dumps too many tool schemas at an external agent, bloating its context:

- `mcp-public-gateway` scope-filters `tools/list` by **permission** (`filterListResponseText` →
  `filterTools`, PUB-3/H-F: a key only sees tools it *may* call) — but then ships that **entire
  scoped list**. A broad-scope key still gets 100+ schemas in one `tools/list`.
- The scope filter cuts by permission, never by **relevance / on-demand**.
- The chat agent is already protected (`chat-service/tool_discovery.py`: ≤8 core + per-surface hot
  domains + `find_tools` lazy tail, new domains lazy-by-default) — but that is **consumer-side,
  chat-only**. The public edge has no equivalent.

## Decision (user, 2026-06-29)

- **Default-on, all keys, minimum tool loads** — ship the smallest possible `tools/list` (core +
  `find_tools`), load the rest on demand (ChatGPT/Anthropic-style load-when-needed). No opt-in flag.
- **Shared `find_tools` in ai-gateway** — the federation layer owns the canonical search; the
  public edge uses it (single source of truth).
- **The state machine BELONGS TO THE SESSION** (user, 2026-06-29) — like ChatGPT/Anthropic/LM
  Studio, the loaded toolset is **per-session state** for maximum control: a session starts minimal
  and the agent **progressively activates** tools (via `find_tools`) that **persist for the rest of
  the session**. The public gateway already mints a **stable session per key** (`session_id =
  key_id` — "one key = one long-lived agent session"), so the activated-tool set is **Redis-backed,
  keyed by session_id**, and grows across turns within that session. This is NOT a stateless
  per-request minimal list — it is a real per-session progressive-disclosure state machine.

## Design

### M1 — ai-gateway: the canonical `find_tools` (source of truth)
- `federation/find-tools.ts` (NEW): port the proven `tool_discovery.py` search to TS — pure
  `searchCatalog(catalog, intent, limit, exclude) → {matches, confident}` (token-overlap + a
  strong-fuzzy rescue; no deps). Plus `FIND_TOOLS_TOOL` (the meta-tool schema) and
  `findToolsResult(catalog, intent, limit, exclude, availability)` (matches + the H10
  unavailable-provider note), mirroring the chat-service contract.
- `mcp/handlers.ts`:
  - `handleListTools` → **prepend `FIND_TOOLS_TOOL`** to the advertised tools (so the public edge
    relays it; chat-service already has find_tools as core → deduped by name + excluded from its
    own search, so no disruption).
  - `handleCallTool` → **intercept `name === 'find_tools'`**: run `searchCatalog` over
    `federation.catalog()` and return `{tools: matches}` locally (no provider; consumer-local meta
    tool — no envelope/ownership needed, OD-1).
- Tests: `find-tools.spec.ts` (search ranking/threshold/empty) + handlers (list prepends
  find_tools; call routes find_tools locally).

### M2 — mcp-public-gateway: the per-SESSION tool-activation state machine
- `session/tool-activation-store.ts` (NEW): a Redis-backed per-session activated-tool set, keyed
  by `session_id` (= `key_id`), mirroring `redis-idempotency-store.ts`. Ops: `activate(sessionId,
  names[])` (SADD + sliding TTL), `activated(sessionId) → names[]` (SMEMBERS). Sliding TTL (e.g.
  24h) bounds an idle session; an in-memory fallback store (like idempotency) keeps tests/dev
  hermetic. This IS the state machine — the loaded toolset is session state, not request state.
- `tools/list` (response filter): advertise the **EDGE CORE** (`find_tools` + `confirm_action`) **∪
  the session's activated set**, all **∩ the key's scope** (`isToolAllowed`). A fresh session →
  just the core; a session that has discovered tools → core + those tools. So the surface GROWS
  per session, deliberately.
- `find_tools` call: relay to ai-gateway's search → **intersect matches with the key's scope** →
  **`activate()` the matched names into the session set** → return the matches. The activated tools
  then (a) are immediately callable and (b) appear on the next `tools/list` (the agent can re-list
  to see its grown surface). Emit `notifications/tools/list_changed` when the set grew (best-effort)
  so an MCP client re-lists.
- Anti-oracle: find_tools never reveals an out-of-scope tool (results are scope-intersected), and
  activating an out-of-scope name is impossible (it's filtered before SADD). `tools/call` stays
  gated by `gateRequestBody` — **no security change**: a key still cannot call outside its scope.
- Tests: fresh session lists only {find_tools, confirm_action}∩scope; after find_tools, the
  activated tool appears in the next list (state persisted) + is callable; out-of-scope name never
  activates + still denied at the gate; TTL/SMEMBERS round-trip (in-memory store).
- VERIFY: cross-service live smoke (external agent → mcp-public-gateway → ai-gateway → providers):
  session 1 lists minimal; `find_tools` activates a tool; a re-`tools/list` shows the grown set; the
  discovered tool calls; a second key's session stays minimal (per-session isolation).

## Security / invariants (must hold)
- **No scope widening:** the edge core + find_tools results are always ∩ the key's scope; the
  request-side `gateRequestBody` default-deny is unchanged (the real enforcement).
- **Anti-oracle preserved:** find_tools never reveals an out-of-scope tool's existence (results are
  scope-intersected), matching the list filter's existing anti-oracle contract.
- **Wildcard dev key:** `*` scope bypasses the list filter today; it also bypasses the minimal-core
  collapse (a dev/smoke key keeps the full list) — least surprise for smokes.
- **Consumer-local find_tools (OD-1):** carries no user-data envelope; the ai-gateway handler reads
  only the catalog, never a provider — no ownership guard needed.

## Out of scope (tracked)
- **chat-service migration to the shared find_tools** — chat keeps its local `tool_discovery.py`
  search for now (same algorithm); pointing it at the gateway's find_tools is a separate refactor
  (a network hop per discovery) → `D-FINDTOOLS-CHAT-SHARE`. The user's "shared via ai-gateway"
  intent is met by the gateway OWNING the canonical impl the public edge uses.

## Amendment (2026-07-07) — `list_changed` never worked; replaced by an `invoke_tool` facade

An external bug report (an outside Claude Code agent testing the live public MCP edge) confirmed
the design gap this plan's line 63 flagged as "best-effort": **`notifications/tools/list_changed`
was never implemented**, and even if it had been, a standard MCP client (Claude Code confirmed;
most others too) caches `tools/list` ONCE at connect and never re-polls mid-session. So a tool
`find_tools` "activated" into the session set was **permanently uncallable** — the client refuses
to send a `tools/call` for a name it never saw listed. The state-machine design (session-scoped
activation, scope-safety, anti-oracle contract) above is all still correct and unchanged; only the
"the client will re-list" assumption was wrong.

**Fix:** keep everything above as-is, add a third ALWAYS-present synthetic edge tool —
`invoke_tool(name, arguments)` (`src/scope/invoke-tool.ts`) — that a client CAN call (it's always
in `tools/list`, like `find_tools`). The edge unwraps it into a normal `tools/call` for the real
target at the very top of the request pipeline (`public-mcp.controller.ts`, before rate-limiting/
scope-gate/idempotency read the body), so every gate documented above keeps working completely
unmodified — the request is indistinguishable from the agent having called the real tool directly
once unwrapped. An additional activation gate (skipped for the wildcard key) denies an
`invoke_tool` target that was never `find_tools`-activated this session, with a message pointing
the agent at `find_tools` (never a silent no-op).

Also fixed in the same pass: ai-gateway's MCP `initialize` response carried no `instructions` at
all (zero onboarding for a fresh client — it had to reverse-engineer the domain from ~150+ tool
names). `proxy-server.factory.ts` now sets `instructions` describing the system + the
find_tools→invoke_tool flow; the edge additionally rewrites `find_tools`'s OWN description in
`tools/list` to state the edge-specific detail (calling a matched name directly won't work here —
use `invoke_tool`), since that claim is only true behind this edge, not for a direct ai-gateway
consumer whose `tools/list` is never filtered.
