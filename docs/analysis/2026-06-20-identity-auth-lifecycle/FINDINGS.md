# Identity / Auth-Lifecycle Architecture — Findings

- **Date:** 2026-06-20 · **Status:** ✅ COMPLETE · **Type:** read-only audit (no code changed)
- **Source:** gap-analysis §11 Task 10 (identity half). Distinct from the IDOR sweep (resource-authz) — this is identity & session *lifecycle*.

## Headline
The **cryptographic primitives are strong** (Argon2id passwords, KMS-RS256 alg-pinned admin tokens, one-shot origin/fingerprint-bound WS tickets, an excellent dual-actor break-glass). The **gaps cluster in the distributed lifecycle**: revocation doesn't propagate, the SVID/ACL service-identity model is designed-but-unwired, a legacy URL-token WS path is still live, identity hangs on one shared secret, and there's no MFA/device registry. **4 High.**

## Prioritized
| # | Sev | Finding | Location |
|---|---|---|---|
| 1 | **HIGH** | Legacy `/ws` gateway still live takes **JWT in the URL query string** — reintroduces every S12 token-leak threat (access logs, Referer, proxy cache); no origin/fingerprint/per-message-authz/forced-disconnect | `api-gateway-bff/src/ws/events.gateway.ts:24-55`, mounted `ws.module.ts:42` |
| 2 | **HIGH** | **No session-revocation propagation** — access tokens stateless; nothing re-checks `revoked_at`. Logout/reset/delete leave tokens valid until expiry (≤15m), and **no code publishes `ws_disconnect_user`** so live sockets are never force-closed (the gateway consumer + `disconnectUser` exist but are never fed) | auth-service (no publisher); `ws-server.ts:346` (consumer, no producer); D-WS-FORCED-DISCONNECT (135) |
| 3 | **HIGH** | **Service ACL matrix (I11/SVID) is unenforced** — `CheckRPCAllowed` is library-only, **0 callers**; no SVID/mTLS exists. Real S2S auth = one shared `INTERNAL_SERVICE_TOKEN` bearer → flat-trust network | `contracts/service_acl/matrix.go` (0 callers); `handlers.go:1117` |
| 4 | **HIGH** | **Single shared HS256 `JWT_SECRET`** is the whole-platform identity anchor — any one service/env leak forges user tokens everywhere; the gateway doesn't verify JWTs, each service re-parses with the shared secret | `config.go:69`; `book-service/server.go:308-311` |
| 5 | MED | WS **per-message authz is a production stub** (`InMemoryAuthzProvider`); the real session-membership/privacy check (roleplay-service RPC) is unwired — the S2-regression-via-WS vector L3 exists to close is open | `ws.module.ts:36`; `per-message-authz.ts:36-37` |
| 6 | MED | Admin/break-glass tokens **replay for full TTL** (15m/24h) — stateless verify, no jti denylist; 24h replay on the highest-authority credential | `adminjwt/verify.go`; D-ADMIN-JWT-JTI-DENYLIST (093) |
| 7 | MED | **No refresh-token reuse-detection** — replay of a rotated token returns generic "expired", no lineage/family revocation, no theft alert | `handlers.go:201-203` |
| 8 | MED | **No MFA, no device registry** — can't enforce 2FA, list active sessions, or "log out other devices". Enterprise blocker | auth-service (absent) |
| 9 | LOW | User `ParseAccess` doesn't pin `iss`/`aud` or require `exp` (admin verifier does) | `authjwt/jwt.go:30-45` |
| 10 | LOW | `/internal/*` user-lookup gated only by network isolation (not ACL/SVID) — email→user_id oracle if the boundary softens (interacts with the IDOR-sweep `/internal/users/*` finding) | `handlers.go:1130-1189` |

## What's sound (reference patterns)
- Admin token: RS256 via KMS (private key never leaves KMS), kid-pinned, `WithValidMethods(["RS256"])` + alg-confusion re-assert, `exp`/`iss`/`aud` enforced, issuer secret distinct from internal token.
- Refresh rotation in one tx (old `revoked_at`, new inserted), tokens SHA-256 at rest; password-reset/delete revoke **all** sessions; change-password revokes all-but-current.
- Password reset: generic 202 (no enumeration), 32-byte hashed single-use 1h token.
- Break-glass: dual-actor (both present own KMS-verified admin tokens, body actor-ids untrusted), break-glass token can't be reused as approver, ≥100-char reason (stored as HMAC), incident ref, ≤24h, mandatory audit before return.

## Net
Items 1–4 are **must-fix before any production/enterprise exposure** — they're distributed-identity gaps, not crypto gaps. The recurring shape matches the rest of the audit: **the good design (S11 SVID, S12 forced-disconnect, real per-message authz) is specced and even partly coded, but not wired** — the gateway's `disconnectUser` with no producer, and the ACL matrix with 0 callers, are the clearest examples.
