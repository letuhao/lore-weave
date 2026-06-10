# ai-gateway P0 — design + plan

- **Date:** 2026-06-10 · **Phase:** P0 of `2026-06-10-glossary-assistant-architecture.md` · **Size:** XL
- **Goal:** stand up `ai-gateway` (TS/NestJS) as the single MCP face: MCP **server** upstream (consumers) + MCP **client** downstream federating knowledge's existing `/mcp`. Hard-cutover chat's TOOL path to the gateway; knowledge unchanged. Glossary-independent keystone.
- **PO locked (CLARIFY):** default v2.2 (no /amaw P0); **hard cutover** (no fallback) → AC10 live-smoke is the gate; chat uses MCP `list-tools` for definitions + MCP execute; port 8210.

## Key design decisions

1. **Service `services/ai-gateway/`** — NestJS 10 (mirror `api-gateway-bff` deps) + `@modelcontextprotocol/sdk`. Container port **8210**, host `8218:8210`. Internal-only (NOT behind api-gateway-bff) — SO-1.

2. **Upstream MCP server (`/mcp`)** — low-level `Server` + `StreamableHTTPServerTransport`, **stateless** (`enableJsonResponse: true`, no session store). Two proxy handlers:
   - `ListToolsRequestSchema` → return the federated catalog.
   - `CallToolRequestSchema` → look up `tool→provider` in the registry, forward downstream with the per-call envelope, return the result.
   A thin Nest controller/middleware reads envelope headers off the HTTP request, **validates `X-Internal-Token`** (SO-1, constant-time), and binds `{userId, sessionId, traceId}` into a per-request context the CallTool handler forwards. (Mirrors the proven H3 pattern, now TS-server side; downstream is TS-client→knowledge FastMCP which already reads headers.)

3. **Federation service (registry)** — on startup + TTL refresh (e.g. 30 s) + reconnect, for each provider: open an MCP client, `list-tools`, record `tool_name → provider`. Build:
   - `catalog`: merged tool list (P0: knowledge's 5 `memory_*` — no re-prefix needed with 1 provider; namespacing rule lands with provider #2).
   - `catalogVersion`: stable hash of sorted `(name, schema)` (H10). Exposed via `/health/catalog`.
   - **Partial catalog** when a provider is down (H10): contribute the providers that answered; mark partial; shorter refresh.
   - **Per-provider MCP client/session** (H14), independent `initialize` negotiation.

4. **Downstream execution (INV-7)** — per tool call, open a **fresh stateless** `StreamableHTTPClientTransport` to the owning provider with `requestInit.headers` = the per-call envelope (`X-User-Id/Session/Internal-Token/Trace`); call; close. Never reuse a connection across users. (Proven pattern, spec §20.)

5. **chat-service surgical cutover** — `knowledge_client._base_url` today serves BOTH `build_context` (grounding) AND tools. P0 cuts **only tools** over:
   - add config `ai_gateway_url = http://ai-gateway:8210`.
   - `get_tool_definitions` → MCP `list-tools` against the gateway, converted MCP-tool-def → OpenAI-function-shape (chat's existing expected shape).
   - `mcp_execute_tool` → gateway `/mcp` (repoint that one URL).
   - **`build_context` STAYS on `knowledge_service_url`** (grounding = P6, not P0). No fallback (hard cutover).

6. **SO-1 trust boundary** — gateway is internal-only, `X-Internal-Token` gated; trusts `X-User-Id` that chat derived from the user JWT (same chain as today's chat→knowledge). Gateway never derives identity from the LLM. Documented in the service README + config.

## Build steps (→ TodoWrite)
1. Scaffold `services/ai-gateway/` (package.json, tsconfig, nest-cli, main.ts, app.module, Dockerfile, jest config, .env.example) + health.
2. `FederationService` — registry + catalog version + partial-on-down + per-provider client (H10/H14). Unit-tested with a fake provider.
3. Upstream MCP proxy `Server` + `/mcp` controller (envelope read + internal-token gate + ListTools/CallTool proxy). Unit-tested.
4. chat-service cutover (config + MCP list-tools definitions + execute repoint; build_context untouched). Unit-tested (mock gateway).
5. docker-compose: ai-gateway service + chat `AI_GATEWAY_URL` env.
6. VERIFY: ai-gateway jest + chat pytest green; **live-smoke** chat→gateway→knowledge `memory_*` tool call on a stack-up (AC10 — the cutover gate).

## Acceptance criteria (§18 DoD)
AC1 service runs internal-only · AC2 MCP server+client · AC3 federate knowledge 5 tools, route ok · AC4 per-call envelope (INV-7) · AC5 chat tools repointed · AC6 knowledge unchanged (its tests + /mcp green) · AC7 H10 catalog version+partial · AC8 H14 per-provider session · AC9 SO-1 documented+enforced · AC10 cross-service live-smoke.

## Risks / watch
- TS MCP low-level `Server` proxy (ListTools/CallTool passthrough) is the core; verify the SDK's request-handler API shape at build (version 1.29.0).
- Stateless server + per-call client connect cost (PERF-1) — accept for P0.
- chat MCP `list-tools` → OpenAI-shape conversion must preserve the schemas knowledge advertises (round-trip parity test).
