# Adversary cold-start review — DEFERRED 074 + 075 (admin-cli signed-JWT verify + auth-service admin/break-glass JWT issuance)

Round 3 (FINAL for design) - agent: adversary - phase: review-design
Plan under review: C:\Users\NeneScarlet\.claude\plans\shimmying-splashing-micali.md

Exactly 3 problems. No "what is good" section.

---

## R2 resolution check

- **r2-BLOCK1 (GetPublicKey DER->*rsa.PublicKey decode + public-key distribution channel unpinned)** - **PARTIAL.** Decode IS now pinned: parse_key.go (line 35) fixes PEM block type "PUBLIC KEY" -> x509.ParsePKIXPublicKey (SPKI/PKIX, the KMS GetPublicKey shape) -> assert *rsa.PublicKey. Distribution mismatch IS now caught: kid = KeyFingerprint(pub) = hex SHA-256 of the PKIX-DER written on the signing header (line 60) and cross-checked by adminjwt.Verify(..., expectKID) (line 34); admin-cli recomputes the same fingerprint from env-PEM (line 74), so a stale/wrong PEM yields a loud kid mismatch, not silent universal failure. **Residual:** r2's specific remediation - a golden vector built from a literal captured real-KMS GetPublicKey DER byte string - was NOT adopted. The plan's golden vector (line 61) uses a checked-in RSA key marshaled by the test's own MarshalPKIXPublicKey, i.e. stdlib-encodes and stdlib-decodes the same bytes. Pins PKIX-vs-PKCS1 (real value) but does not prove the bytes AWS KMS actually emits parse cleanly. See R3-WARN1.
- **r2-BLOCK2 (break-glass bootstrap deadlock)** - **RESOLVED BY SCOPE (PO).** Plan line 64 + Step-0 PO decision lock the model to ELEVATED-AUTHORITY dual-actor (assumes normal admin auth works); auth-is-down recovery is OUT OF SCOPE. Per AMAW instruction not re-raised. Accepted.
- **r2-WARN3 (caller-only auth, rate-limit key, pre-auth audit inflation, jti replay)** - **PARTIAL.** Rate-limit key pinned to issuer-identity + RealIP (line 65); pre-auth 401 writes NO durable audit row (line 65) - resolved. Replay: jti recorded, consumption-side denylist deferred (D-ADMIN-JWT-JTI-DENYLIST, line 68). **Residual:** r2 also asked for UNIQUE(jti) WHERE jti IS NOT NULL + reject-duplicate-at-mint as the cheap issuer-side guard; schema (line 46) leaves jti UUID NULL with no unique constraint. Folded into R3-WARN3.

---

## [WARN] 1 - The "golden vector" still feeds the verifier bytes the test itself produced; the real-KMS GetPublicKey SPKI-DER is never parsed, so the one trap captured-rule #2 names on the verify side stays uncovered until real-AWS

**Concrete risk.** Phase D (line 61) closes the signing assembly trap, but the key-acquisition chain KMS GetPublicKey -> SPKI-DER -> operator pastes PEM -> ParseRSAPublicKeyPEM -> rsa.VerifyPKCS1v15 is validated only against bytes the test author marshaled with x509.MarshalPKIXPublicKey - a stdlib-encodes/stdlib-decodes round trip. It proves ParsePKIXPublicKey is wired (catches PKIX-vs-PKCS1, real value) but cannot surface anything specific to KMS export: wrong PEM header (RSA PUBLIC KEY rejected by the parser), copy-paste base64-wrap/newline quirks, or a KMS DER variant the stdlib tolerates differently. Captured-rule #2 applies to the verify side exactly as r1 established for the sign side; the plan took the analogous golden-vector fix for signing but declined the analogous fixture for key export. r2 asked for a committed literal KMS-DER fixture precisely to close this without LocalStack - ~300 bytes, not a live dependency.

**Why WARN not BLOCK.** The kid cross-check (line 34) turns the worst outcome (silent universal verify failure / wrong-key acceptance) into a loud parse/startup error, and the KMS-RPC live-smoke is legitimately deferred (D-ADMIN-JWT-KMS-LIVE-SMOKE). Degrades to "first real-AWS bring-up may need a PEM-wrapping fix," caught loudly. Not build-stopping.

**Where it lands.** Phase A (parse_key.go test), Phase D (line 61 golden vector), Phase F (line 79 live-smoke deferral).

**Remediation.** Commit a literal SPKI-DER fixture captured from a real KMS RSA GetPublicKey (or an openssl-generated SPKI byte-shaped like KMS): base64 -> DER -> PUBLIC KEY PEM -> ParseRSAPublicKeyPEM -> verify the golden token. Add a negative test that an RSA PUBLIC KEY (PKCS#1) PEM is rejected with a clear error so the operator-paste footgun is documented in code.

---

## [WARN] 2 - admin_principals.user_id is REFERENCES users(id) ON DELETE CASCADE: deleting a user silently and irrecoverably erases their admin grant, and the audit table's FK-free actor_id then dangles

**Concrete risk.** Phase B (line 41): admin_principals(user_id UUID PK REFERENCES users(id) ON DELETE CASCADE, ...). auth-service ships DELETE /account (server.go line 97, s.deleteAccount). An admin principal is a security grant, not user-owned content:

1. **Silent privilege deletion with no trace.** A deleted users row (self-service deletion, GDPR erase, ops mistake) CASCADE-drops the admin_principals row with zero audit. admin_token_issuance_audit (line 46) records issuance, not grant revocation, so the most security-relevant lifecycle event - an admin grant vanishing - leaves nothing in this service's own DB. You cannot answer "who lost admin and when."
2. **Dangling audit actor refs.** admin_token_issuance_audit.actor_id/second_actor_id (line 46) carry no FK (correct, so history survives), but after the cascade those ids reference a user that no longer exists anywhere - forensic reconstruction of a past break-glass mint loses the actor identity it most needs.

**Why WARN not BLOCK.** Data-lifecycle/forensics defect, not a mint-time auth-bypass; happy path and all gates still function. Cheap to fix at design time and exactly the "tracked, not forgotten" class CLAUDE.md flags.

**Where it lands.** Phase B (line 41 FK action), Phase C (line 46 actor columns).

**Remediation.** Change ON DELETE CASCADE to ON DELETE RESTRICT/NO ACTION so an active grant blocks naive user deletion and forces explicit active=false de-provision first; OR keep CASCADE but emit a revoke-kind audit row (trigger or from deleteAccount) so grant loss is durable. Either way denormalize the actor's user_ref/handle into the audit row at mint so forensic rows survive user deletion.

---

## [WARN] 3 - reason_len CHECK and the append-only REVOKE-vs-INSERT role interaction are under-pinned; one is a stated-but-unconstrained invariant, the other a runtime grant footgun

**Concrete risk.** Two residual Phase C gaps (lines 46-48):

1. **reason_len enforcement is prose, not DDL.** Line 47 says store reason_len "(with a derived check that it was >=100 at mint)" but reason_len INT NULL lives on a table whose outcome can be deny/error, where the reason legitimately was shorter / NULL. A naive CHECK (reason_len >= 100) rejects the very deny-audit row the design wants (line 46). The conditional form is never stated, so the implementer can write a CHECK that blocks deny inserts, or omit it and lose the ">=100 at mint" guarantee. 015's pattern was a concrete length CHECK; this is looser.
2. **REVOKE UPDATE/DELETE + INSERT role interaction unverified for THIS DB role.** Line 46 reuses 015/016's REVOKE UPDATE, DELETE ... EXCEPTION WHEN undefined_object guard. That guard enforces append-only ONLY if the connecting role is neither table owner nor superuser - REVOKE does not constrain the owner; superuser bypasses grants. 015/016 run in the meta DB under meta-worker's role; auth-service connects to its OWN DB (line 23) very plausibly as the owner/migration role. If auth-service writes audit rows as owner, the REVOKE is cosmetic and append-only is not enforced at runtime. The plan confirms INSERT is permitted (it is) but never confirms UPDATE/DELETE are actually denied to the connecting role.

**Why WARN not BLOCK.** Append-only is defense-in-depth/tamper-evidence, not a mint-time gate; the reason_len issue is a footgun BUILD/REVIEW will likely catch. Neither stops the build or opens an auth bypass.

**Where it lands.** Phase C (lines 46-48). Carries residual r2-WARN3 jti point.

**Remediation.** (a) Pin CHECK (reason_len IS NULL OR reason_len >= 100); document deny/error rows carry NULL. (b) Confirm the auth-service runtime DB role differs from the migration/owner role, or comment that the REVOKE is best-effort under owner-connection and the real guarantee is the absence of any UPDATE/DELETE code path - do not silently inherit 015/016's grant assumptions from a different role model. (c) Add UNIQUE(jti) WHERE jti IS NOT NULL and reject duplicate jti at mint.

---

Captured rules: read pre-loaded; Guardrails relevant: DB-migration-L+ (satisfied); break-glass model scoped by PO.
