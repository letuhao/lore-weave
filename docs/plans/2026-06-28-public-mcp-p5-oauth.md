# P5 OAuth — build plan (per-slice checklist)

Spec: [2026-06-28-public-mcp-p5-oauth.md](../specs/2026-06-28-public-mcp-p5-oauth.md). Branch `feat/public-mcp-gateway`. Size XL → 4 slices, checkpoint/commit at each risk boundary (migration / cross-service seam). PO checkpoint (POST-REVIEW) at each shippable slice. **Push only with explicit user approval.**

## Slice 1 — discovery + edge audience-verify (S9 foundation) [no migration]
**auth-service (Go):**
- `internal/authjwt/oauth.go` — `SignOAuthAccessToken(signer, sub, clientID, grantID, scopes, aud, ttl)` reusing `assembleRS256` with a NEW claims type `{iss: OAuthIssuer, sub, aud, scope, client_id, grant_id, iat, exp, jti}`. Distinct `OAuthIssuer`/audience consts (NOT adminjwt's).
- `internal/api/oauth_meta.go` — `GET /.well-known/oauth-authorization-server` (RFC 8414) + `GET /oauth/jwks` (RFC 7517 JWK from `signer.PublicKey()` — n,e,kid,alg=RS256,use=sig). Wire via a new `srv.EnableOAuth(signer, cfg)` in [server.go](../../services/auth-service/internal/api/server.go) + [main.go](../../services/auth-service/cmd/auth-service/main.go) (pass the same signer as `EnableAdminIssuance`).
- `internal/config/config.go` — `OAuthIssuer`, `OAuthResource` (canonical MCP url = the aud), `OAuthAccessTTL`, default RPM. Fail-closed if OAuth enabled but unset.
**edge (TS):**
- `src/oauth/token-verifier.ts` — JWKS fetch+cache (kid-keyed, TTL, refresh-on-unknown-kid) + RS256 verify + assert iss/aud/exp. Pure-ish (inject fetch). 
- `src/auth/key-resolver.ts` — branch: JWT shape → `token-verifier` → `ResolvedKey{userId:sub, keyId:grant_id, scopes, allowSelfConfirm:false, spendCapUsd:null, rateLimitRpm:default}`; else existing API-key path.
- `src/mcp/public-mcp.controller.ts` — `GET /.well-known/oauth-protected-resource` (RFC 9728 PRM: `{resource, authorization_servers:[issuer]}`); add `WWW-Authenticate: Bearer resource_metadata="…"` to the 401 deny.
- `src/config/config.ts` — `oauthIssuer`, `mcpResourceUrl`, `authServiceUrl` (exists).
**BFF (TS):** [gateway-setup.ts](../../services/api-gateway-bff/src/gateway-setup.ts) — route `/.well-known/oauth-protected-resource`→edge; `/.well-known/oauth-authorization-server`+`/oauth/*`→auth-service.
**TESTS:** authjwt oauth mint (golden claims, distinct iss/aud); oauth_meta handler (jwks shape, AS metadata fields, S256 advertised); edge token-verifier (valid / wrong-aud / wrong-iss / expired / bad-sig / unknown-kid-refresh); key-resolver branch (JWT vs lw_pk_); controller PRM doc + 401 WWW-Authenticate.
**VERIFY/DoD-slice:** mint a token in-process (auth) with the right aud → edge accepts + relays a read; wrong-aud → 401. **live smoke:** real auth `/oauth/jwks` + edge verify a real-signed token (≥2 services).

## Slice 2 — auth-code + PKCE + grants + consent [migration: mcp_oauth_grants (+ codes)]
**auth-service:** migration `mcp_oauth_grants` (+ `mcp_oauth_codes` table OR Redis code store — pick Redis if auth already deps it, else table); `internal/api/oauth_flow.go` — `GET /oauth/authorize` (validate client_id/redirect_uri/scope/PKCE S256/resource→aud; require user session; redirect to FE consent with a signed request handle), `POST /v1/account/oauth/consent` (JWT owner; mints single-use code bound to {user,client,grantedScopes,code_challenge,redirect_uri,resource}), `POST /oauth/token` (code+code_verifier → access+refresh; refresh-token grant; rotation; resource→aud check → `invalid_target`). Grant upsert `UNIQUE(owner_user_id,client_id)`.
**FE:** consent page (`features/settings` or a dedicated `/oauth/consent` route) — client name + requested scopes as tier/domain chips with **per-scope toggles** (reuse `MCP_SCOPES`/`MCP_DOMAINS`, `splitScopes`), approve(downscoped set)/deny; i18n ×4.
**edge:** unchanged from slice 1 (grant_id now real).
**TESTS:** authorize validation (bad redirect/scope/missing PKCE → error); PKCE S256 verify (good/bad verifier); code single-use + expiry; refresh rotation; grant downscope (granted ⊆ requested); real-PG grant upsert/revoke. FE consent (toggle downscopes, deny path, secret never persisted).
**VERIFY/DoD:** full auth-code+PKCE flow end-to-end (a script acting as the client) → token → edge read on-behalf-of. **live smoke** the flow.

## Slice 3 — open DCR (RFC 7591) [migration: mcp_oauth_clients]
**auth-service:** migration `mcp_oauth_clients`; `internal/api/oauth_register.go` — `POST /oauth/register` (open; **Q-GATE flag** → 403 when off; **per-IP rate-limit** reusing the existing auth rate-limit middleware; **audit** row; validate redirect_uris/grant_types; issue public `client_id`, no secret for PKCE). Add `registration_endpoint` to AS metadata.
**TESTS:** register happy-path (returns client_id, no secret); flag-off→403; rate-limit→429; bad redirect_uri→`invalid_redirect_uri`; audit row written (real PG).
**VERIFY/DoD:** register → authorize → token → edge read, fully self-served. **live smoke.**

## Slice 4 — catalog_* discovery provider (OD-7) [no migration]
**catalog-service (Go):** MCP read tools `catalog_list_public_books`, `catalog_get_book` (+ `catalog_search` if cheap) over the existing public catalog queries; register via the kit (stateless handler + IdentityMiddleware). ai-gateway federation entry. **edge** `tool-policy.ts`: classify `catalog_*` = `{tier:'read', domains:['catalog']}`; add `catalog` to `MCP_DOMAINS` (FE) + `DEFAULT_MCP_DOMAINS` if appropriate.
**TESTS:** catalog MCP tools (owner-agnostic public reads — these are PUBLIC content, not owner-scoped; verify they only return public-visible rows); edge policy (catalog_* read+domain:catalog, default-deny others); list-filter advertises catalog_* for a domain:catalog key.
**VERIFY/DoD:** a public OAuth key with `read+domain:catalog` lists/gets public books through the edge. **live smoke** (≥2 services).

## Cross-cutting
- provider-gate clean each slice. Distinct issuer+audience asserted (admin vs oauth separation) — a test that an OAuth token is rejected by the admin verify path and vice-versa.
- SESSION_HANDOFF updated per slice; deferred rows for anything that earns the gate.
- Q-GATE: OAuth endpoints + DCR all behind `PUBLIC_MCP_ENABLED` (reuse), DCR additionally gated as above.
