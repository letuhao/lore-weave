# Security Standard (main platform)

**Status:** ACTIVE (rules) · enforcement partly built — see §Enforcement · **Date:** 2026-07-04
**Governs:** the security controls every main-platform service must uphold — secrets, authN/authZ, injection, PII, encryption, SSRF, rate-limiting, input validation, audit. (Tenancy is the separate [User Boundaries standard](./README.md#a-platform-build-standards).) Indexed in [`README.md`](./README.md); current-state in [audit](../plans/2026-07-04-enterprise-hardening-audit.md#area-3--security).

> **Why.** Two inverted regimes exist: the MMO/foundation meta layer is heavily governed (15 lints, RS256 `adminjwt` adversarially tested, PII/KMS crypto-shred) but much has no running code; the **product** (book/glossary/chat/knowledge/auth/…) runs on convention + spot tests. The strong disciplines here (parameterized SQL, injection sanitize, credential encryption, 404-anti-oracle) are habits, not gates — and there are genuine holes (no edge rate-limit, no dep-vuln scan, chat prompt-injection).

## Rules

- **SEC-1 · Secrets.** No hardcoded secrets (gitleaks on **every** branch + pre-commit, not just `main`). Every secret via env with **fail-closed startup validation** (a service must refuse to start on a missing required secret).
- **SEC-2 · AuthN.** One shared, adversarially-tested JWT verifier for platform user tokens (mirror `contracts/adminjwt`'s matrix: alg-pinned, `exp` required, `iss`/`aud` checked, reject `alg:none`/HS-downgrade). No per-service hand-rolled variant. The gateway is either a real auth boundary or the standard explicitly blesses per-service validation **using the shared verifier**.
- **SEC-3 · AuthZ.** 404-anti-oracle (denied ≡ nonexistent, never 403) + E0 grant-gating on every private-resource read route, proven by a **required shared test pattern** (generalize `book-service/grant_mapping_test.go` to every owning service).
- **SEC-4 · Injection.** Every untrusted text entering an LLM prompt — **including chat-service** (today's hole) — passes `neutralize_injection` (`sdks/python/loreweave_grounding/sanitize.py`). Every value in every SQL query is parameterized; only allowlisted identifiers are interpolated.
- **SEC-5 · PII.** Every migration touching user data carries classification + retention + erasure tags (extend `pii-classify-lint` from `migrations/meta/` to `services/*/migrations/`); platform user PII has a defined erasure mechanism.
- **SEC-6 · Encryption.** All secrets/credentials encrypted at rest (AES-GCM/KMS envelope — BYOK creds already do this). A **unified key-management + rotation** policy; distinct keys per purpose (see [LLM Call Logging LOG-5](./llm-call-logging.md) — the payload key must not be `JWT_SECRET`). TLS at the edge; internal hops documented.
- **SEC-7 · SSRF.** Every outbound fetch to a user/agent-supplied URL goes through the SSRF-safe resolve-then-connect client (generalize `agent-registry-service/internal/api/probe.go` into a shared lib all services use).
- **SEC-8 · Rate limiting.** Edge rate limits at the gateway (today absent) + per-owner caps on expensive/LLM/MCP routes.
- **SEC-9 · Input validation.** Pydantic `extra="forbid"` + field caps mandatory on request models; a global request-body size cap (413).
- **SEC-10 · Security audit trail.** Structured, append-only security-event log for admin actions, **auth failures, and authorization denials** (main platform emits none today) — via the `*_audit` tables ([Logging LG-7](./logging.md)).
- **SEC-11 · Dependency vulnerabilities.** CVE scanning for every ecosystem (Go/Python/TS/Rust) in CI + a dependabot config. (Lockfile pinning ≠ vuln scanning.)

## Enforcement

| Rule | Status | Gate |
|---|---|---|
| SEC-1 secrets | **partial → all-branch (P1)** | gitleaks (`foundation-ci.yml`) — extend trigger to `**` + add to `.githooks/pre-commit` |
| SEC-6 BYOK-at-rest · SEC-7 SSRF · SEC-2 admin JWT · SEC-3 404-oracle (book) · SEC-8 auth rate-limit | **ENFORCED (implemented/tested)** | `provider-registry server.go:999`, `agent-registry probe.go`, `contracts/adminjwt/adminjwt_test.go`, `book-service grant_mapping_test.go`, `auth ratelimit` |
| SEC-4 SQL param · SEC-4 injection-coverage | **to build (P1)** | raw-SQL/unparameterized lint (Go+Py) · injection-coverage lint (every LLM-prompt feed routes through the sanitizer — allowlist model like `prompt-assembly-discipline-lint.sh`) |
| SEC-2 shared verifier · SEC-3 all services | **to build (P1)** | shared JWT-verifier adversarial suite (template `adminjwt_test.go`) + generalized grant/404 harness |
| SEC-5 platform PII | **to build (P1)** | extend `pii-classify-lint` to `services/*/migrations/` |
| SEC-11 dep-vuln | **to build (P1)** | govulncheck + pip-audit + npm-audit + cargo-audit + osv-scanner + `.github/dependabot.yml`; + semgrep |
| SEC-8 edge rate-limit | **to build (P1)** | `@nestjs/throttler`/helmet at the gateway |

## Checklist — a new endpoint / service
- [ ] Required secrets fail-closed at startup (SEC-1); no hardcoded secrets
- [ ] User JWT via the shared verifier (SEC-2)
- [ ] Private reads: 404-anti-oracle + grant-gated, with the shared test (SEC-3)
- [ ] Untrusted text → LLM prompt passes `neutralize_injection`; all SQL parameterized (SEC-4)
- [ ] User-data migration carries PII tags (SEC-5)
- [ ] Secrets/creds encrypted at rest, purpose-distinct keys (SEC-6)
- [ ] User-supplied URLs fetched via the SSRF-safe client (SEC-7)
- [ ] Expensive/LLM/MCP route has a per-owner cap; gateway edge-limited (SEC-8)
- [ ] Request model `extra="forbid"` + caps (SEC-9)
- [ ] Admin/auth-failure/authz-denial audited (SEC-10)
