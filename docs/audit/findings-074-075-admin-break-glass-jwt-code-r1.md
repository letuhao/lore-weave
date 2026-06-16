# AMAW Adversary — Code Review R1: 074/075 admin + break-glass JWT issuance/verify

Cold-start adversarial review. Read set only (12 files). Exactly 3 findings.

---

## [BLOCK] 1 — Break-glass token issues even when its append-only audit write fails (success-path audit loss)

**File:** services/auth-service/internal/api/admin.go:263 (auditIssuance), reached from the SUCCESS
branches at admin.go:116-121 (admin) and admin.go:201-209 (break-glass), with writeJSON(... 200 ...)
at admin.go:121 / admin.go:209.

**Risk.** auditIssuance ends with `_ = s.admin.store.InsertAudit(ctx, row)` — the error is discarded.
On the success path the token is minted and returned BEFORE the audit write, and the response is sent
regardless of whether the INSERT succeeded. The comment at admin.go:232-235 claims errors are
"surfaced via the returned 5xx path where relevant" — true for deny/error branches (which 5xx anyway)
but FALSE for success: a transient PG error / constraint hit / pool exhaustion on the audit INSERT
silently drops the record while the credential ships. For the highest-authority credential
(break_glass=true, up to 24h, primary's full role+scopes), migrate.go:97-102 promises an "append-only
audit of every admin/break-glass token ISSUANCE attempt". A break-glass token minted with NO durable
issuance row defeats that forensic guarantee exactly when it matters (post-incident attribution).
The issued jti is recorded only in this swallowed INSERT, so a dropped success row also loses the
authoritative jti<->actor binding.

**Remediation.** On the success path only, treat InsertAudit failure as fatal: have auditIssuance
return an error; in adminToken/breakGlassToken, after a successful Sign*, write the audit row BEFORE
writeJSON; on error return 500 and do NOT return the token. Best-effort swallow stays fine for
deny/error branches. Optionally wrap mint + audit in one tx.

---

## [WARN] 2 — admin_principals FK is ON DELETE RESTRICT; DELETE /account handler not updated -> raw 500 for any admin self-delete

**File:** services/auth-service/internal/migrate/migrate.go:88-89 (FK ON DELETE RESTRICT);
route services/auth-service/internal/api/server.go:114 (DELETE /account -> deleteAccount). Handler
body in handlers.go (outside read set) was not touched by this change.

**Risk.** With ON DELETE RESTRICT, deleting a users row that still has an admin_principals row raises
a PG FK violation (SQLSTATE 23503). The pre-existing deleteAccount handler does a plain DELETE FROM
users with no awareness of the new child table, so an admin user calling DELETE /account gets a raw
pgx FK error surfaced as 500 — opaque failure, account un-deletable until the admin grant is revoked.
The RESTRICT property itself is intended; the missing piece is graceful handling.

**Remediation.** In deleteAccount, detect the FK violation (pgx *pgconn.PgError Code == "23503" on the
admin_principals constraint) and return 409 with a clear message ("revoke admin access before
deleting"). If postponed, add a tracked deferred row rather than ship a silent 500.

---

## [WARN] 3 — Break-glass actor tokens accepted without asserting break_glass=false (token-class confusion)

**File:** services/auth-service/internal/api/admin.go:148-149 (verify primary/secondary actor tokens);
contracts/adminjwt/verify.go:27-57 (Verify checks alg/iss/aud/exp/kid but never inspects break_glass).

**Risk.** The two actor credentials are validated only as SOME valid admin JWT — Verify ignores the
BreakGlass claim (claims.go:28). Nothing stops an actor from presenting a previously minted
break_glass=true token as their approver credential to bootstrap a fresh break-glass mint. Combined
with the deferred jti denylist (D-ADMIN-JWT-JTI-DENYLIST), a single still-valid 24h break-glass token
can be re-presented as an actor input and behaves as a reusable approver within its window. The stated
threat model (admin.go:132-136) is "both actors present their OWN freshly-issued admin token", but the
code never enforces the admin (not break-glass) half of that contract.

**Remediation.** After verifying each actor token in breakGlassToken, reject if primary.BreakGlass or
secondary.BreakGlass is true — a cheap pure check that closes class-confusion independently of the
deferred jti denylist. Do not re-block on the jti-denylist deferral.

---

Captured rules: read pre-loaded; Guardrails: PASS.
