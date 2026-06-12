# Plan — 077 D-GAME-WS-EDGE-CONTROLS: full WS ticket chain + edge controls

**Date:** 2026-06-03 · **Size:** XL+ (multi-service TS) · **Branch:** mmo-rpg/foundation-mega-task
**Workflow:** v2.2 + cold-start `/review-impl` before commit (new public-edge security boundary, credentials, cross-service). No push without approval. Depends on **068** (base64 ticket wire form — DONE).

## Context (investigation 2026-06-03)

`game-server` (services/game-server, **ESM** Colyseus) is the PRR-20 sanctioned 2nd public WS entry point; clients connect directly. Today its `onAuth` is a static-token placeholder. The 4 edge controls (PRR-20 / 068-row): (1) validate the gateway-issued ticket on handshake, (2) per-conn + per-user rate caps, (3) connection-lifecycle audit, (4) AWS security groups.

**What already exists (reuse > rewrite):**
- The **gateway** (services/api-gateway-bff, **NestJS/CommonJS**) ISSUES tickets: `POST /v1/ws/ticket` (`ticket-endpoint.ts`) → `makeTicket` → DI-wired `TicketStore` (`TICKET_STORE_TOKEN`, currently `InMemoryTicketStore`). Reply returns only `{ticketId, expiresAt, ttlMs}`.
- `ticket-store.ts` (TS) is a documented **wire-compatible mirror** of the Go canonical `contracts/ws/ticket.go`: `Ticket` (hashes as 32-byte `Buffer`), `validateTicket`, `makeTicket`, `hashOrigin`/`hashFingerprint`, `constantTimeBufferEquals`, `InMemoryTicketStore` — and explicitly says "Production REPLACES this with a Redis-backed store (atomic GET+DEL Lua)."
- auth-service has **zero** ticket issuance (the contract comment is stale — the gateway is the issuer).

**The cross-service gap:** the gateway's store is **in-memory per-replica**, so the game-server (separate process) cannot redeem a gateway-issued ticket. The shared **Redis** store bridges issuer→redeemer.

**Structural constraint:** the two backend services are **separate npm packages, different module systems** (NestJS CJS gateway, ESM game-server), and **NOT** in the pnpm workspace (that's frontend-game + client `packages/*`). So a workspace-extracted shared package is not the right tool here.

## Key decisions

1. **Shared logic = copy-as-wire-compatible-mirror, guarded by a GOLDEN fixture (not a workspace package).** The repo's established pattern is "canonical (Go) + wire-compatible mirrors" (the gateway TS store is one). game-server gets its own redeem/validate mirror (ESM). Drift is guarded by the **132 golden fixture**: a fixed 32-byte digest → known base64 literal + a known ticket-JSON, asserted by BOTH services' tests + the Go canonical. This is the honest mitigation for the duplication (Node `Buffer.from` is lenient → only an explicit literal catches StdEncoding-vs-URLEncoding drift).
2. **Redis ticket JSON wire form** (the shared contract both services serialize): `{ticketId, userRefId, allowedRealities[], allowedScopes[], originHash(base64-std), clientFingerprintHash(base64-std), issuedAt(ms), expiresAt(ms)}`. base64 **StdEncoding** matches 068 (Go `Hash32`) + ws/v1.yaml `format: byte`.
3. **Redis is config-gated.** `LW_WS_REDIS_URL` (or similar) selects `RedisTicketStore`; unset → `InMemoryTicketStore` (dev/test stay Redis-free; the gateway's existing tests keep passing). `ioredis` added to both services.
4. **Redeem atomicity** = a single Lua `local t=GET(k); DEL(k); return t` (one-shot across replicas), then wall-clock expiry + binding checks server-side.
5. **Strict binding** (origin + fingerprint exact, constant-time) → close codes 4007/4009. **Ticket-only** handshake auth (forced-disconnect-on-revoke deferred). **TLS-session-id** stays empty (ALB plumbing later).
6. **Rate caps (#2): real but basic** — per-user connection cap + per-connection message-rate cap at the WS edge (clears **035**); close 4006/4008.
7. **Audit (#3): structured-log** connection lifecycle (open/close/redeem-outcome) — honest interim; event-stream deferred.
8. **AWS SG (#4): doc only** (no IaC in repo) — origin-whitelist note + ALB-only-ingress note.

## Slices / files

1. **Gateway Redis store** — `api-gateway-bff/src/ws/redis-ticket-store.ts` (new, implements `TicketStore`; ioredis; Lua redeem; base64 (de)serialize) + `ws.module.ts` (config-gated provider) + test + the golden fixture test. `package.json` +ioredis.
2. **game-server ticket mirror** — `game-server/src/ws/ticket.ts` (Ticket type + validate + binding + base64 (de)serialize, ESM mirror) + `game-server/src/ws/redis-ticket-store.ts` (redeem-only Redis) + golden-fixture test (same literal as gateway/Go). `package.json` +ioredis.
3. **game-server redemption** — `index.ts`/`EchoRoom.ts`: extract `ticketId` from `Sec-WebSocket-Protocol: lw.v1, ticket.<id>`, recompute origin/fingerprint hashes from the upgrade headers (X-Forwarded-For /24 + UA), redeem + validate + bind, reject with close codes. Replace the static-token `authenticate`.
4. **Rate caps (#2)** — `game-server/src/ws/rate-limit.ts` (per-user conn cap + per-conn msg-rate) + wired into the room; test.
5. **Audit (#3)** — `game-server/src/ws/audit.ts` (structured-log connection lifecycle) + wired; test.
6. **Docs** — plan (this), DEFERRED (077→ADDRESSED + new rows for the deferred depth: event-stream audit, Redis-HA, forced-disconnect, TLS-session, AWS-IaC), SESSION_PATCH.

## Verification
- `tsc` build + `node --test` in BOTH api-gateway-bff + game-server (incl. the **golden fixture** asserted identically in both + against the Go `contracts/ws` base64).
- Redis store tests run against an in-memory fake OR a real Redis if `LW_WS_REDIS_URL` set; the atomic-redeem one-shot + base64 round-trip pinned.
- Lints: language-rule (game-server/gateway = ts), lint-contract (ws/v1.yaml unchanged), relevant foundation lints.
- **Live smoke:** DEFERRED — full cross-process (gateway issue → Redis → game-server redeem over a real WS upgrade) needs a running Redis + both services + a browser client; track `D-GAME-WS-LIVE-SMOKE`.
- Cold-start `/review-impl` before commit (public-edge security).

## Deferrals to open
`D-GAME-WS-LIVE-SMOKE` (cross-process e2e), `D-WS-AUDIT-EVENT-STREAM` (structured-log → real event stream), `D-WS-FORCED-DISCONNECT` (revoke-mid-session), `D-WS-TLS-SESSION-ID` (ALB plumbing), `D-GAME-WS-AWS-IAC` (security groups), `D-WS-REDIS-HA` (Redis failover/cluster). (132 cross-lang golden fixture is CLEARED by this task's golden test.)

## Guardrails
- Lane: touches api-gateway-bff + game-server (realtime track) + adds ioredis to both — authorized by the user's "full ticket chain" choice; flagged at POST-REVIEW. Stage only changed files (no `-A`). Co-author trailer. No push without approval.
