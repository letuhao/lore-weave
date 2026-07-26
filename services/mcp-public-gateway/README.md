# mcp-public-gateway

The **public MCP security edge**. External agents (someone else's Claude/GPT agent, a CLI, a partner integration) connect here — through `api-gateway-bff` at `/mcp` — with their **own** credential, and the edge turns that into the trusted internal envelope the rest of the platform already understands.

```
external agent ──Bearer lw_pk_…──▶ api-gateway-bff /mcp ──▶ mcp-public-gateway ──X-Internal-Token + X-User-Id──▶ ai-gateway /mcp ──▶ domain MCP providers
```

## Why a separate service
`api-gateway-bff` is a deliberately auth-free pass-through proxy; `ai-gateway` is internal-only and trusts a forwarded `X-User-Id`. Neither can safely face untrusted callers. This edge is the one place that **authenticates an external credential, derives identity, and mints the internal envelope** — with its own deploy/scale/WAF surface and a small, auditable blast radius.

## Invariants (P0)
- **PUB-1** identity is derived here from the credential, never trusted from the agent.
- **PUB-2** `X-Internal-Token` is held here and never exposed to external callers.
- **PUB-9** the outbound envelope is built from scratch; the entire inbound `x-*` namespace is stripped (a smuggled `X-Admin-Token` / `X-Internal-Token` / `X-User-Id` is discarded). The edge relays to `/mcp` **only** — it has no route to `/mcp/admin` and holds no admin token.
- **H-R** the credential must arrive in the `Authorization` header; a key in the query string is refused.
- **Q-GATE** public MCP is OFF unless `PUBLIC_MCP_ENABLED=true` (fast kill-switch).

## Status
**P0** (this scaffold): envelope hop + inbound-`x-*` strip + admin isolation + feature flag, using a single static test credential (`MCP_PUBLIC_TEST_KEY` → `MCP_PUBLIC_TEST_USER_ID`). Read tools only; nothing priced/written yet.

**Next:** P1 real credential store (`mcp_api_keys` in auth-service) · P2 scope filter + ownership hardening · P3 rate-limit + per-key BYOK-only spend + audit · P4 human-approval write tier. See `docs/specs/2026-06-26-public-mcp/04-implementation-plan.md`.

## Env
See `.env.example`. Required: `INTERNAL_SERVICE_TOKEN` (fails fast without it). `AI_GATEWAY_URL` defaults to `http://ai-gateway:8210`.

## Test
`npm install && npm test` — unit tests cover the auth gate, H-R, and the PUB-9 header-strip / admin-isolation guarantees.
