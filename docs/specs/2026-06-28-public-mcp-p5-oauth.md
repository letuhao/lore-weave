# P5 — OAuth 2.1 + discovery for the public MCP gateway

**Status:** DESIGN (CLARIFY checkpoint passed 2026-06-28) · branch `feat/public-mcp-gateway` · supersedes the P5 stub in [04-implementation-plan.md](2026-06-26-public-mcp/04-implementation-plan.md) §P5.

**Goal / DoD:** a standards-compliant third-party MCP client completes an OAuth 2.1 authorization-code + PKCE flow **on-behalf-of** a LoreWeave user and calls a read tool through the public edge; an **audience-confused** token (minted for another resource) is **rejected at the edge** (S9). OAuth is **additive** — personal API keys (P1) keep working unchanged; both credential classes resolve to one `{user_id, scopes, key/grant id}` at the edge.

## PO decisions (CLARIFY, 2026-06-28)
- **DCR = open** (RFC 7591 self-registration) **behind the Q-GATE flag + per-IP rate-limit + audit**. Bounded by: a client still needs a user to consent, and registration is rate-limited + audited.
- **Full P5, four slices end-to-end** (below).
- **Consent = scope-aware with per-scope toggles** — the user sees the requesting client + the requested scopes (tier + domain chips, reusing the MCP-key UI vocabulary) and may **downscope** (uncheck tiers/domains) before approving. The granted set is `requested ∩ user-approved`.

## Standards
| RFC | What | Where |
|---|---|---|
| OAuth 2.1 (auth-code + PKCE S256) | the on-behalf-of grant | auth-service `/oauth/authorize` + `/oauth/token` |
| RFC 8414 Authorization Server Metadata | client discovers the AS endpoints | auth-service `GET /.well-known/oauth-authorization-server` |
| RFC 9728 Protected Resource Metadata | the resource advertises its AS(s) + canonical resource id | **edge** `GET /.well-known/oauth-protected-resource` + `WWW-Authenticate` on a 401 |
| RFC 7591 Dynamic Client Registration | a client self-registers | auth-service `POST /oauth/register` (open, flagged, rate-limited) |
| RFC 8707 Resource Indicators | the `resource` param binds the token `aud` | authorize + token carry `resource`; token `aud` = the MCP resource; **edge verifies `aud`** |
| RFC 7517 JWK Set | the edge gets the RS256 verify key | auth-service `GET /oauth/jwks` (built from the existing `DigestSigner.PublicKey()`) |

## Token model (reuses the admin RS256 infra)
- **Access token** = short-lived JWT, **RS256**, minted with the **existing `authjwt.DigestSigner`** ([admin.go](../../services/auth-service/internal/authjwt/admin.go) — KMS in prod, `LocalKeySigner` PEM in dev; `kid` = `adminjwt.KeyFingerprint(pub)`). The signer is already wired in [main.go](../../services/auth-service/cmd/auth-service/main.go) via `EnableAdminIssuance` — P5 hands the SAME signer to a new `EnableOAuth(...)`. **A distinct issuer + audience** (NOT `adminjwt.Issuer/Audience`) so an OAuth token can NEVER be replayed as an admin token and vice-versa (separate claim type + the edge only accepts the OAuth issuer/aud; ai-gateway `/mcp/admin` only accepts the admin issuer/aud).
  - Claims: `{ iss: <oauth issuer>, sub: <user_id>, aud: <mcp resource url>, scope: "<space-delimited>", client_id, grant_id, iat, exp, jti }`. TTL short (≈10 min); refresh extends.
- **Refresh token** = opaque, **hashed at rest** (mirror the existing session-refresh pattern), stored on `mcp_oauth_grants`. Rotated on use.
- **Audience (S9):** `aud` = the configured canonical MCP resource URL (e.g. `https://app.loreweave.dev/mcp`). The client MUST send `resource=<that url>` (RFC 8707) at authorize + token; the AS sets `aud` to it ONLY if it matches the configured resource (else `invalid_target`). **The edge verifies `aud == its configured resource`** → a token minted for any other audience is rejected (confused-deputy defense).

## Edge verification (local, no auth round-trip on the hot path)
[key-resolver.ts](../../services/mcp-public-gateway/src/auth/key-resolver.ts) gains a branch on the bearer shape:
- **`lw_pk_…` prefix** → the existing P1 API-key resolve (unchanged).
- **a JWT (three base64url segments)** → **local RS256 verify**: fetch + cache auth-service JWKS (`GET ${AUTH_SERVICE_URL}/oauth/jwks`, kid-keyed, TTL + refresh-on-unknown-kid for rotation), verify signature, then assert `iss == oauthIssuer`, `aud == mcpResourceUrl`, `exp` not past. On success return a `ResolvedKey`: `userId=sub`, `keyId=grant_id` (a UUID → rides `x-mcp-key-id` for attribution/audit/rate-limit/session, exactly like an API key id), `scopes` from `scope`, `allowSelfConfirm=false` (v1 OAuth is human-present; self-confirm stays API-key-only), `spendCapUsd=null` (owner guardrail), `rateLimitRpm = OAUTH_DEFAULT_RPM`.
- A malformed/expired/wrong-aud/wrong-iss token → the SAME uniform null → 401 (anti-oracle), with `WWW-Authenticate: Bearer resource_metadata="<PRM url>"` so a spec client knows where to discover the AS.

Because `keyId=grant_id` is a UUID, **everything downstream is unchanged**: PUB-12 BYOK gate (`isPublicMcpKeyCall` sees `x-mcp-key-id`), per-key cap (H-K, owner guardrail when null), H-O audit, PUB-8 rate-limit, scope filter, OD-8 owner-only — all key off `keyId`/`scopes`/`userId` and don't care whether the credential was a key or a grant.

## BFF routing (gateway invariant — external OAuth still flows through the edge BFF)
[gateway-setup.ts](../../services/api-gateway-bff/src/gateway-setup.ts) (already proxies `/mcp` → mcp-public-gateway):
- `GET /.well-known/oauth-protected-resource` → **mcp-public-gateway** (the resource serves its own PRM).
- `GET /.well-known/oauth-authorization-server` + `/oauth/*` → **auth-service** (the AS). Unversioned, matched before `/v1` like the `/mcp` proxy.

## Data model (auth-service, 2 idempotent migrations in [migrate.go](../../services/auth-service/internal/migrate/migrate.go))
- **`mcp_oauth_clients`** (RFC 7591): `client_id` (PK, public), `client_name`, `redirect_uris TEXT[]`, `grant_types TEXT[]`, `token_endpoint_auth_method` (`none` for public+PKCE), `scopes_requested TEXT[]` (advisory), `created_at`, `created_ip`, `status` (`active`/`disabled`). Public clients (PKCE) → no secret. Open DCR insert is flag+rate-limit+audit gated.
- **`mcp_oauth_grants`** (per user×client): `id` (PK UUID = the `grant_id`/session anchor), `owner_user_id` FK CASCADE, `client_id`, `scopes TEXT[]` (the GRANTED ∩, after downscoping), `refresh_token_hash`, `resource`, `created_at`, `last_used_at`, `expires_at`, `revoked_at`. Owner-scoped read for a "connected apps" view (FE, follow-up). `UNIQUE(owner_user_id, client_id)` — re-consent updates the same grant.
- **auth-code** = short-lived single-use, stored in Redis (or a tiny `mcp_oauth_codes` table) keyed by code → `{user, client_id, scopes, code_challenge, redirect_uri, resource, exp}`. Redis preferred (ephemeral, TTL-native); fall back to a table if Redis isn't a dependency of auth-service.

## Slices (each = a checkpoint/commit at its risk boundary)
1. **Discovery + edge audience-verify (S9 foundation).** auth-service: `EnableOAuth` wiring + `GET /oauth/jwks` (from `signer.PublicKey()`) + `GET /.well-known/oauth-authorization-server` (RFC 8414) + the OAuth-token mint helper + issuer/audience/resource config. edge: serve RFC 9728 PRM + `WWW-Authenticate` on 401 + the KeyResolver OAuth branch (local RS256 verify + aud/iss/exp). BFF: route `/.well-known/*` + `/oauth/*`. **DoD-slice:** a hand-minted (test) OAuth token with the right aud calls a read tool through the edge; wrong-aud → 401. (No grants table needed yet.)
2. **auth-code + PKCE + grants + consent.** auth-service: `mcp_oauth_grants` + auth-code store + `/oauth/authorize` (validates client/redirect/PKCE/scope/resource → redirects to FE consent) + an internal approve endpoint (mints the code after consent) + `/oauth/token` (code→token with PKCE verify, refresh grant, rotation). FE: scope-aware consent screen with **per-scope toggles** (downscope) → approve/deny. edge: resolve OAuth token grant-backed.
3. **Open DCR (RFC 7591).** auth-service: `mcp_oauth_clients` + `POST /oauth/register` (open, **Q-GATE flag**, **per-IP rate-limit**, **audit**) + `registration_endpoint` in AS metadata.
4. **`catalog_*` discovery provider (OD-7).** catalog-service (Go): MCP read tools for public-content discovery (`catalog_list_public_books`, `catalog_get_book`, + search if cheap) → ai-gateway federation + edge `tool-policy.ts` classification (`read`, `domain:catalog`). Lets a public agent find public books to act on.

## Security invariants (carried)
- **PUB-9 strip-and-mint** unchanged — the edge still discards inbound `x-*` and mints the envelope; an OAuth token changes only HOW identity is derived (local verify vs API-key resolve), not the envelope.
- **Admin/OAuth separation** — distinct issuer+audience; the edge never accepts the admin aud; `/mcp/admin` never accepts the OAuth aud. No new admin surface.
- **S9 confused-deputy** — audience binding (RFC 8707) verified at the edge is the core defense; covered by an explicit wrong-aud-rejected test + live-smoke.
- **DCR abuse** — open registration is flag-gated + rate-limited + audited; a registered client is inert until a user consents (no standing access from registration alone).
- **BYOK-only spend (PUB-12)** + **per-key cap (H-K)** + **OD-8 owned-only** + **H-O audit** + **PUB-8 rate-limit** — all hold unchanged (they key off the resolved `keyId`/`userId`/`scopes`, credential-class-agnostic).
