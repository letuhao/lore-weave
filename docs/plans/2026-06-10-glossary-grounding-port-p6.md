# glossary assistant — grounding consolidation (gateway port) — P6 plan

- **Date:** 2026-06-10 · **Phase:** P6 · **Size:** L · **PO:** default v2.2; full gateway port (no flag). Optional/"below-the-line" phase — the assistant already ships at P5.
- **Goal:** route chat grounding (`build_context`) through the ai-gateway so it becomes the **single AI integration layer** (tools + grounding), with a **mandatory `[]`-on-failure + retained direct chat→knowledge fallback** (H2) and **unchanged billing** (SO-6). Spec §18 P6 DoD + Part II H2 / SO-6.

## Decisions (CLARIFY/DESIGN)
- **Gateway-first, knowledge-direct fallback** (no flag). Normal path: chat→gateway→knowledge (one internal hop). Gateway outage → chat→knowledge direct. Both unreachable → `_degraded()` (turn never errors — already the behavior).
- **Outage vs stable-degraded**: only a transport error / 5xx (after retries) from the gateway triggers the fallback. A stable knowledge signal proxied through (404 project-not-found / 501 Mode-3 / other 4xx / decode-fail) returns `_degraded()` WITHOUT the fallback (knowledge-direct would answer the same).
- **Gateway grounding URL** = `{ai_gateway_url}/internal/context/build`; **fallback** = `{knowledge_url}/internal/context/build`. Both URLs already on `KnowledgeClient` (`_tools_base_url` = gateway, `_base_url` = knowledge).
- **Gateway derives the knowledge base** by stripping `/mcp` from the knowledge provider's `mcpUrl` (overridable via `KNOWLEDGE_SERVICE_URL`) — no new required env.
- **SO-6 billing unchanged**: the gateway does no inference; grounding is retrieval, no token metering through it. No billing code touched.

## Build steps
### 1. ai-gateway (TS/NestJS)
- `config.ts`: add `groundingUrl: string` = `process.env.KNOWLEDGE_SERVICE_URL ?? <knowledge mcpUrl>.replace(/\/mcp$/, '')`.
- NEW `src/grounding/grounding.controller.ts` — `@Controller('internal/context')` `@Post('build')`: SO-1 token gate (`x-internal-token`, mirror McpController) → forward POST to `{groundingUrl}/internal/context/build` (global `fetch`) with the body + forwarded `x-user-id`/`x-trace-id` + the gateway's own internal token; return knowledge's status + JSON. On a transport failure to knowledge → 502 (so chat treats it as outage → falls back).
- `app.module.ts`: register `GroundingController`.
- Test (`test/grounding.controller.spec.ts`): 401 without token; forwards body + status on a faked knowledge; 502 when knowledge unreachable.

### 2. chat-service (Python)
- `knowledge_client.py`: refactor the per-URL attempt body into `_build_context_at(url, body, headers, attempts) -> KnowledgeContext | None` (None = OUTAGE: transport/5xx-exhausted; `_degraded()` for stable 404/501/4xx/decode; KnowledgeContext on 200). `build_context` orchestrates: gateway-first (`{_tools_base_url}/internal/context/build`) → on None, knowledge-direct (`{_base_url}/internal/context/build`) → on None, `_degraded()`.
- Tests: gateway success returns its context (no fallback); gateway OUTAGE → falls back to knowledge direct; gateway stable-404 → degraded WITHOUT fallback; both outage → degraded.

### 3. VERIFY
- chat `pytest` (build_context fallback matrix); ai-gateway `jest`.
- provider-gate.
- Cross-service (chat→gateway→knowledge): real grounding through the gateway on a stack-up → `LIVE-SMOKE deferred to D-GLOSSARY-GROUNDING-SMOKE` (or live if stack rebuilt).

## AC (§18 P6 DoD)
AC1 gateway grounding proxy (token-gated, header-forwarding) · AC2 H2 gateway-first + retained knowledge fallback, `[]`/degraded on total failure (never errors the turn) · AC3 stable knowledge signal → degraded without fallback · AC4 SO-6 billing unchanged.

## Risks
- Extra hop per turn (latency) — accepted (PO: full port); same-datacenter, small.
- Outage/stable distinction wrong → either no fallback when needed, or a pointless second call. Covered by the fallback-matrix tests.
- Gateway proxy must NOT meter tokens (SO-6) — it does no inference; no billing code touched.
- Single-host test wiring (`tools_base_url` defaults to `base_url`) → primary==fallback, harmless (tries twice).
