# ai-gateway

The internal **AI/MCP gateway** — the single MCP face for LoreWeave's AI
consumers. It federates the domain services' MCP tool servers (P0: knowledge;
P1+: glossary, …) behind one endpoint so a consumer (chat, composition) talks to
**one** MCP server instead of N.

Spec: [`docs/specs/2026-06-10-glossary-assistant-architecture.md`](../../docs/specs/2026-06-10-glossary-assistant-architecture.md)
· Plan: [`docs/plans/2026-06-10-ai-gateway-p0.md`](../../docs/plans/2026-06-10-ai-gateway-p0.md)

## What it does (P0)

- **MCP server upstream** (`/mcp`, stateless streamable-HTTP) — consumers connect here.
- **MCP client downstream** — federates each provider's `/mcp` (`list-tools` →
  `tool → provider` registry + a catalog version), routes each `CallTool` to the
  owning provider. Degrades to a **partial catalog** if a provider is down.
- **Transparent proxy** — returns the provider's `CallToolResult` verbatim.

## Trust boundary (SO-1)

- **Internal-only.** Not exposed through `api-gateway-bff`; reached only by
  in-cluster services over the private network.
- **Service auth:** every `/mcp` request must carry `X-Internal-Token`
  (validated in `McpController`). The gateway forwards its **own** token to
  providers — the consumer's token never leaves the gateway.
- **Identity:** the consumer (which verified the user JWT) forwards `X-User-Id`
  /`X-Session-Id`/`X-Trace-Id`; the gateway **trusts and forwards** these — same
  chain as the prior direct chat→knowledge path. Identity is **never** derived
  from the LLM (SEC-1). Per-call downstream connections carry that call's
  envelope and are never shared across users (INV-7).

## Endpoints

| Path | Purpose |
|---|---|
| `POST /mcp` | the federated MCP endpoint — initialize / **list-tools** (consumers fetch tool defs here) / call-tool |
| `GET /health` · `/health/ready` | liveness / readiness |
| `GET /health/catalog` | federated catalog `{version, tools, providers, partial}` (H10) |

Consumers are **pure MCP**: they fetch tool definitions via MCP `list-tools` and
execute via `call-tool` — there is no bespoke HTTP tool endpoint.

## Config

See `.env.example`. `INTERNAL_SERVICE_TOKEN` is required (fail-fast).

## Dev

```
npm install
npm run build
npm test
```
