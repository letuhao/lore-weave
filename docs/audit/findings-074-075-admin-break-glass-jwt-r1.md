# Adversary cold-start review — DEFERRED 074 + 075 (admin-cli signed-JWT verify + auth-service admin/break-glass JWT issuance)

Round 1 · agent: adversary · phase: review-design
Plan under review: C:\Users\NeneScarlet\.claude\plans\shimmying-splashing-micali.md

Exactly 3 problems. No "what is good" section.

---

## [BLOCK] 1 — KMS-Sign -> golang-jwt RS256 wire format is asserted, never pinned; the only test that would catch a mismatch is deferred to real AWS

**Concrete risk.** The plan (Phase D, line 51) says auth-service will "call kms.Sign with MessageType=DIGEST, SHA-256 of signing input, SigningAlgorithm=RSASSA_PKCS1_V1_5_SHA_256 ... assemble header.claims.sig -> standard RS256 JWT verifiable by adminjwt.Verify." That is the happy-path description, not a pinned contract, and it hides wire traps that produce a token golang-jwt's RS256 verifier rejects even though everything compiles:

1. **Digest identity.** golang-jwt RS256 verify computes sha256([]byte(headerB64 + "." + claimsB64)) itself and runs rsa.VerifyPKCS1v15. KMS MessageType=DIGEST must receive exactly that 32-byte digest — SHA-256 of the ASCII signing string, not of the raw claims JSON. The plan never states which bytes are hashed; "SHA-256 of signing input" is ambiguous.
2. **Signature encoding.** KMS Sign returns a raw PKCS#1 v1.5 signature for RSA (DER-wrapped only for ECDSA). The JWT third segment must be that raw signature base64url-encoded, no padding (base64.RawURLEncoding). The plan never pins this; std base64 or leftover padding silently breaks verification.
3. **alg header.** The header must literally be {"alg":"RS256","typ":"JWT"}. Because the plan signs out-of-band via the KMS signer, the header must be hand-constructed to match RS256 or the strict keyfunc (correctly) rejects it.

**Why BLOCK, not WARN.** Captured-rule #2 ("compile-clean != contract-clean: live smoke is the only way to catch wire-format incompatibilities") is the exact failure mode, and the plan's mitigation is to defer the only KMS live-smoke to real AWS (Phase F, line 64; D-ADMIN-JWT-KMS-LIVE-SMOKE). The unit tests use LocalRSASigner (real rsa.SignPKCS1v15), which exercises the crypto but NOT the KMS wire path — it cannot reproduce KMS digest-mode, raw-vs-DER signature shape, or GetPublicKey DER->*rsa.PublicKey parse. The production signing path ships with zero end-to-end coverage. Captured-rule #1 also bites: the plan cites contracts/meta/kms.go as the "standalone-module shape," but that interface is Decrypt-only — there is no Sign and no GetPublicKey anywhere to "mirror." The contract being mirrored does not exist; it must be authored and pinned.

**Where it lands.** Phase D (internal/authjwt/admin.go, KMSSigner) + Phase F (live-smoke deferral). Origin: line 51 + line 64.

**Remediation.**
- Pin the wire contract at byte granularity: signing input = base64url(header) + "." + base64url(claims); KMS digest = sha256(signingInput); MessageType=DIGEST; signature segment = base64.RawURLEncoding; header fixed {"alg":"RS256","typ":"JWT"}.
- Author a real Signer (Sign(ctx, digest []byte) ([]byte, error)) + PublicKeyProvider (GetPublicKey(ctx) (*rsa.PublicKey, error)) as the pinned contract — do not "mirror contracts/meta," which has neither.
- Add a unit test that assembles the token exactly as KMSSigner will (raw RSA sig over the same digest, base64url-RawEncoded) and round-trips it through adminjwt.Verify — catches the encoding/digest traps without LocalStack.
- Real-AWS KMS live-smoke deferral is acceptable only after that assembled-bytes/golden-vector test exists.

---

## [BLOCK] 2 — One shared INTERNAL_SERVICE_TOKEN gates both a benign profile read AND admin/break-glass minting; break-glass dual-actor is defeated by any single internal caller

**Concrete risk.** Today cfg.InternalServiceToken is a single shared secret (config.go lines 49/66) and /internal has no inbound check (server.go lines 64-67, "no JWT required"). The plan (Phase D, line 52) adds requireInternalToken comparing X-Internal-Token against that same cfg.InternalServiceToken, mounted on /internal/admin/{token,break-glass-token}.

1. **Privilege concentration.** The same secret that authorizes read-only GET /internal/users/{id}/profile now authorizes minting an admin JWT for any active admin principal and minting a break_glass=true token. Any service holding the internal token for profile reads is silently upgraded to "can mint admin credentials."
2. **Dual-actor bypass.** Break-glass's security value is two distinct human actors. But /internal/admin/break-glass-token authenticates only the calling service (one shared token), then trusts the primary_actor/secondary_actor body fields. A single caller POSTs two different active-admin UUIDs and gets a break-glass token — no proof either human consented. The dispatcher (dispatcher.go lines 106-118) requires the second actor's OWN signed token, but the issuance endpoint requires no such proof: the strong control exists only on the consumer side, absent at the mint side. Captured-rule #1: the issuance module pins a strictly weaker invariant than the consumer enforces.
3. **Constant-time compare insufficient.** subtle.ConstantTimeCompare is necessary but does nothing about an over-broad, shared, long-lived secret. No rate limit on mint endpoints; existing check is only "non-empty" (line 66).

**Where it lands.** Phase D (server.go middleware + handlers; config.go token sourcing).

**Remediation.**
- Do not reuse INTERNAL_SERVICE_TOKEN for minting. Add a separate ADMIN_TOKEN_ISSUER_SECRET (distinct env, >=32-char entropy floor, fail-closed) gating only /internal/admin/*.
- For break-glass issuance require cryptographic proof of both actors at mint time (each actor's own valid JWT, validated server-side, mirroring PRR-43) so the mint enforces the same dual-actor invariant the consumer does.
- Add per-caller rate limit on both mint endpoints; audit every call including 401/403 (see finding 3).

---

## [WARN] 3 — Audit + fail-closed posture incomplete: only successful issuances audited, reason-hash unsalted/underspecified, dev KMS override reopens the fail-closed hole

**Concrete risk.**

1. **Failure paths unaudited.** The plan (Phase C/D, lines 45-55) writes admin_token_issuance_audit only on successful mint. The most security-relevant events — rejected/attempted issuance (bad X-Internal-Token 401, non-principal/inactive 403, failed dual-actor policy) — produce no row, so probing the mint endpoint leaves no durable trace in the service's own DB. Contrast 015, which lands a row for result_kind='error' too (015_admin_action_audit.up.sql lines 50-78).
2. **reason_hash unsalted + loosely specified.** Plan line 45 stores a SHA-256 reason_hash BYTEA. A >=100-char incident reason is often low-entropy/templated; unsalted SHA-256 is dictionary-reversible, partially defeating PII-avoidance. 015 pairs its hash with scrubbed text + scrub_version + a 32-byte length CHECK; the plan drops the length CHECK and versioning and adds no salt/pepper.
3. **Dev KMS override is a fail-closed regression.** Plan line 50: refuse start if KMSAdminSigningKeyID empty "UNLESS a dev override mirrors the existing dev-token posture." But the existing dev-token posture is consumer-side (ADMIN_CLI_ALLOW_DEV_TOKENS) and only bypasses verification. A KMS-side dev override on the issuer would let auth-service mint signature-valid admin/break-glass tokens with a local key when KMS is absent — strictly larger blast radius (forges real admin JWTs admin-cli accepts). If it leaks to non-dev, the whole control collapses to "whoever can set one env var." Left undecided (captured-rule #1: pin it, don't gesture).

**Where it lands.** Phase C (audit schema + writer), Phase D (config fail-closed, handler audit-on-failure).

**Remediation.**
- Audit every issuance attempt, success and failure, with an outcome discriminator (success|denied_auth|denied_principal|denied_policy) and a 32-byte hash length CHECK + append-only REVOKE guard like 015/016; insert the row before returning 401/403.
- Pin reason_hash as salted (HMAC with server pepper) or keep 015's scrubbed-text + scrub_version pattern.
- Resolve the dev-override "UNLESS" now: issuer hard fail-closed when KMSAdminSigningKeyID empty in any non-dev build; dev path behind a build tag or loud ADMIN_ISSUER_DEV_LOCAL_KEY=1 asserted-off in CI for prod images.

---

Captured rules: read pre-loaded; Guardrails relevant: DB-migration-L+ (satisfied: AMAW on + rollback documented).
