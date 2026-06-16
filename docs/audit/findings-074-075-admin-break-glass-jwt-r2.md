# Adversary cold-start review — DEFERRED 074 + 075 (admin-cli signed-JWT verify + auth-service admin/break-glass JWT issuance)

Round 2 · agent: adversary · phase: review-design
Plan under review: C:\Users\NeneScarlet\.claude\plans\shimmying-splashing-micali.md

Exactly 3 problems. No "what is good" section.

---

## R1 resolution check

- **r1-BLOCK1 (KMS-Sign -> RS256 wire format asserted, never pinned)** — **RESOLVED (with a residual gap, see R2-BLOCK1).** Phase D now pins the wire contract byte-for-byte (lines 54-60): signingInput = base64url(header) + "." + base64url(claimsJSON), digest = SHA-256(signingInput), MessageType=DIGEST, SigningAlgorithm=RSASSA_PKCS1_V1_5_SHA_256, signature segment base64.RawURLEncoding, fixed header {"alg":"RS256","typ":"JWT"}. Authors a real DigestSigner contract (no longer "mirrors" Decrypt-only contracts/meta) + golden-vector test. Residual: GetPublicKey DER->*rsa.PublicKey decode is still untested against real KMS output (see R2-BLOCK1).
- **r1-BLOCK2 (shared INTERNAL_SERVICE_TOKEN gates both profile-read and minting; dual-actor defeated)** — **PARTIAL.** Secret separation IS fixed: distinct AdminTokenIssuerSecret gates /internal/admin/* via subtle.ConstantTimeCompare, with a test proving the profile-read token is rejected at the mint endpoint (lines 63, 67); rate-limit added. BUT the break-glass "require both actors' own validated tokens" fix introduces a bootstrapping contradiction that defeats the break-glass use case (R2-BLOCK2), and the issuer secret has no entropy floor (r1 asked for >=32-char floor; not stated).
- **r1-WARN3 (failure paths unaudited, unsalted reason hash, dev-KMS-override fail-closed regression)** — **RESOLVED.** Audit-on-failure via outcome discriminator (success/deny/error), row inserted before returning (lines 46, 48); reason hash upgraded to keyed HMAC-SHA256(ADMIN_AUDIT_HMAC_KEY, reason) + reason_len (line 47); dev-KMS override removed entirely — LocalRSASigner is test-only, main always uses KMSSigner, fail-closed if key absent (line 52). (A new, smaller audit-DoS concern appears as R2-WARN3, but the original three sub-points are resolved.)

---

## [BLOCK] 1 — GetPublicKey DER->*rsa.PublicKey decode and the public-key DISTRIBUTION channel are still unpinned; admin-cli and auth-service can silently disagree on the verifying key, and KMS's actual key-export shape is untested

**Concrete risk.** R1-BLOCK1 pinned the *signing* assembly path, but the *verification key acquisition* path on BOTH ends remains unpinned and untested against real KMS:

1. **KMS GetPublicKey returns SubjectPublicKeyInfo DER (PKIX), not PKCS#1.** Phase D (line 61) says the public key is "fetched from KMS GetPublicKey (and exported to env for admin-cli)." Phase A's parse_key.go (line 35) is ParseRSAPublicKeyPEM using stdlib crypto/x509+encoding/pem. x509.ParsePKIXPublicKey parses PKIX/SPKI; x509.ParsePKCS1PublicKey parses PKCS#1 — NOT interchangeable, and the plan never pins WHICH one, nor the PEM block type (PUBLIC KEY vs RSA PUBLIC KEY) the operator must wrap the KMS DER in. The LocalRSASigner unit test exercises whatever MarshalPKIXPublicKey the test author picks — which can diverge from the KMS-export shape an operator pastes into ADMIN_JWT_PUBLIC_KEY_PEM. Same class of "the test proves the test, not the wire" gap r1 flagged for signing, now on the verify side.
2. **Key distribution is a manual env-PEM copy with no fingerprint/consistency check.** auth-service signs with the KMS private key (by key-id); admin-cli verifies with a hand-pasted PEM in a different process/host. Nothing binds these to the same key — no kid header, no startup assertion that the configured PEM matches the KMS key. A stale/wrong-env public key makes EVERY admin token silently fail (DoS of all admin tooling); in rollover, a token signed by key A is checked against key B with no diagnostic. The fixed header {"alg":"RS256","typ":"JWT"} (line 56) carries NO kid, so mismatch is undetectable.

**Why BLOCK, not WARN.** Captured-rule #2: live smoke is the only way to catch wire-format incompatibilities. The signing path now has a golden vector, but the GetPublicKey->PEM->ParseRSAPublicKeyPEM->rsa.VerifyPKCS1v15 chain has NO end-to-end coverage and NO real-KMS export sample — and PKIX DER is exactly where the encoding trap lives. Captured-rule #1: GetPublicKey is named, not pinned (output encoding + parse fn unspecified). A green unit suite here is the "compile-clean != contract-clean" trap, because both signer and verifier are fed keys by the SAME test helper.

**Where it lands.** Phase A (parse_key.go), Phase D (line 61 GetPublicKey + env export), Phase E (line 71 ADMIN_JWT_PUBLIC_KEY_PEM load).

**Remediation.**
- Pin ParseRSAPublicKeyPEM to x509.ParsePKIXPublicKey (SPKI) + pin PEM block type to PUBLIC KEY; add a golden vector using a literal captured KMS GetPublicKey DER byte string (committed fixture): base64->DER->PEM->parse->verify a golden token. Catches PKIX-vs-PKCS1 without LocalStack.
- Add a kid to the JWT header (KMS key-id or SHA-256 of the SPKI DER); adminjwt.Verify rejects a token whose kid does not match the loaded key — loud, attributable error, not blanket silent failure.
- At admin-cli startup, log the SPKI fingerprint of the loaded PEM; document that it must equal auth-service's KMS key fingerprint. (JWKS endpoint may stay deferred; a fingerprint cross-check cannot.)

---

## [BLOCK] 2 — Break-glass issuance now requires each actor's own VALID admin JWT, but you break glass precisely BECAUSE admin access is down — the dual-actor-at-issuer fix creates a chicken-and-egg that defeats the break-glass use case

**Concrete risk.** The r1-BLOCK2 remediation (line 65) hardens break-glass minting to require BOTH actors to present their OWN validated credential: {primary_actor_token, secondary_actor_token, ...}, each resolving to a distinct, active admin principal. The only thing that mints an admin token an actor could present is POST /internal/admin/token (line 64). So:

1. **Bootstrapping deadlock.** To get a break-glass token, both actors must already hold valid admin JWTs. To get an admin JWT, /internal/admin/token must be reachable AND the actor must be an active row in admin_principals. Break-glass exists for when normal admin issuance is unavailable or an actor was (wrongly/temporarily) deactivated — exactly when those admin JWTs cannot be minted. The control is strongest precisely when it is useless. The plan's own framing (line 5: break-glass is the emergency path) contradicts requiring the non-emergency path to function first.
2. **active principal requirement is doubly wrong for break-glass.** Line 65 requires each break-glass actor to be an active admin principal. A common break-glass trigger is "an admin's normal access was revoked/suspended and we need two other trusted humans to act." Gating break-glass on active=true in the SAME table normal issuance uses means a deactivation incident also kills the escape hatch. There is no separate break-glass-eligible actor set.
3. **What kind of token, really?** The consumer (dispatcher.go:106) calls auth.Validate(inv.SecondActorToken) — accepts only admin JWTs (or env-gated dev: tokens). If the issuer mirrors that, the break-glass issuer consumes admin JWTs to produce a break-glass JWT — a token-laundering step that adds a dependency without adding a distinct second factor (the admin JWT was itself minted from a single shared AdminTokenIssuerSecret caller).

**Why BLOCK.** A correctness-defeating contradiction in the control, not polish: the design as written cannot serve its stated purpose, and the failure is silent (works in the happy path during testing, fails in the real incident). Captured-rule #1: the break-glass issuance contract must be pinned to a workable bootstrap, not gestured at by "present their own validated token."

**Where it lands.** Phase D (line 65 break-glass handler), interplay with Phase B (admin_principals.active).

**Remediation.** Pick and PIN one workable model:
- (a) Out-of-band human factor: break-glass actors authenticate with a pre-provisioned, separately-stored credential set (e.g. hardware-token-signed assertions or pre-issued break-glass actor certs) flagged break_glass_eligible in admin_principals, NOT requiring a freshly-minted admin JWT from /internal/admin/token. Do not gate on the active used by normal issuance; use a distinct break_glass_eligible column.
- (b) If you keep "present own token": explicitly document that this break-glass is "admin-access-degraded" not "admin-access-down," add a DEFERRED row naming the true cold-start break-glass (offline-signed approval) as follow-up, and have the PO sign off that the emergency served is the narrower one. Either way, decide now — do not ship the deadlock.

---

## [WARN] 3 — Issuer-secret authenticates the CALLER only, so a single compromised caller forges break-glass; combined with shared-secret rate-limit keying and the pre-auth deny audit write, replay (no jti uniqueness) and audit-table inflation are open

**Concrete risk.** Three smaller-but-real gaps the r1 fixes left ajar:

1. **One caller still = both actors (residual of r1-BLOCK2 #2).** Even with two actor tokens required, a single service holding AdminTokenIssuerSecret plus two actors' admin JWTs (harvested from logs, or self-minted via /internal/admin/token which needs only the one issuer secret) can self-assemble a break-glass request. The two-token rule raises the bar but does not establish two independent human approvals, because both admin JWTs trace back to one secret-holder. r1 asked for "cryptographic proof of both actors"; two bearer JWTs one party can obtain is not non-repudiable proof.
2. **jti replay not pinned.** AdminClaims carries jti (line 33), audit table has NULLable jti UUID (line 46), but nothing enforces uniqueness — no unique index, and admin-cli Verify (line 34) checks only alg+exp, not single-use. A captured admin/break-glass token is replayable for its whole TTL (up to 24h for break-glass). At minimum: issuer rejects duplicate jti; audit table enforces UNIQUE(jti) WHERE jti IS NOT NULL.
3. **Pre-auth deny rows = audit-table inflation; rate-limit key unspecified.** Lines 46/48 insert an audit row on deny/error "before returning." If requireAdminIssuerToken rejects (bad/missing X-Internal-Token) BEFORE the handler, the plan is ambiguous whether that 401 writes a row. If it does, an unauthenticated attacker spamming the endpoint inflates the append-only admin_token_issuance_audit (write-amplification DoS on the auth DB; no DELETE). The plan says "rate-limit both endpoints" (line 63) but does not pin the KEY — keying on the shared issuer secret/constant means all callers share one bucket (one noisy caller starves real minting); keying on client IP behind the gateway may collapse to the gateway IP.

**Where it lands.** Phase C (audit schema: jti uniqueness, pre-auth write policy), Phase D (line 63 rate-limit keying, line 65 actor proof).

**Remediation.**
- Pin rate-limit key to per-source-actor (or per-incident-ticket for break-glass), not the shared secret; decide explicitly: 401-at-middleware does NOT write a durable audit row (only authenticated-but-denied attempts do), or use a separate bounded/rotated counter for unauth probes so the durable table can't be inflated by anonymous traffic.
- Add UNIQUE(jti) (partial, WHERE jti IS NOT NULL) to the audit table and reject duplicate jti at mint; document consumer-side single-use enforcement as a tracked DEFERRED row.
- Note for PO: true two-human non-repudiation needs per-actor signing keys, not shared-secret-minted bearer JWTs — track as a DEFERRED hardening row if not done now.

---

Captured rules: read pre-loaded; Guardrails relevant: DB-migration-L+ (satisfied).
