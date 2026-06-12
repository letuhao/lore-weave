# Implementation Plan — Platform RBAC + System-Config (D-PLATFORM-SYSTEM-CONFIG-UI)

**Status:** PLAN-locked 2026-06-11, **BUILD DEFERRED** (see §0). Spec: [2026-06-11-platform-system-config-ui.md](../specs/2026-06-11-platform-system-config-ui.md).
**Deferred row:** DEFERRED 075.

## 0. Why deferred (read first)

CLARIFY + this PLAN are complete, but **BUILD is intentionally deferred**: another agent is
actively making large changes to the **authorization / permission** layer (auth-service),
and S0 (RBAC foundation) lands squarely in the same files — building now would create a
high-risk merge conflict. **Do not start S0 until that auth-permission work has merged**, then
re-baseline this plan against the new auth-service shape (the roles/JWT/middleware design
below may need to adapt to whatever RBAC primitives that work introduces — it may even make
S0 partly redundant). Re-confirm §1 against `main` before writing any code.

## 1. Locked architecture (from CLARIFY)

- **Full RBAC** in **auth-service** (identity SSOT, mints JWT). Roles in the JWT claim →
  `require_*` is a claim check, not a per-request DB hit.
- **New `config-service`** (Go/Chi, DB `loreweave_config`) owns `system_config` (overrides) +
  typed `config_registry`. `/internal/config` (services read) + `/v1/admin/config` (UI writes).
- **Runtime apply**: per-service `ConfigClient` (Py + Go) with TTL cache (BookProfile pattern).
  **Precedence: DB override > env > code default.**
- **Audit** on every admin config write.

## 2. Slices (each its own `/loom`)

### S0 — RBAC foundation (auth-service + gateway) ⚠️ conflict-blocked
**Target files (re-verify against main first):**
- `services/auth-service/internal/db/migrate.go` (or migrations dir) — new tables:
  - `roles(id, code UNIQUE, name, created_at)` — seed `admin`, `user`.
  - `permissions(id, code UNIQUE, description)` — seed `system_config:read`, `system_config:write`.
  - `role_permissions(role_id, permission_id)` — admin → both system_config perms.
  - `user_roles(user_id, role_id, granted_at, granted_by)`.
- `services/auth-service/internal/authjwt/jwt.go` — add `Roles []string` to `AccessClaims`
  (role **codes**, not permissions — keep tokens compact; resolve perms server-side).
- token-mint path (login/refresh handlers) — populate `Roles` from `user_roles` at mint time.
- `services/auth-service/internal/api/middleware.go` (new or existing) —
  `requirePermission(code)` resolves the caller's role codes → permissions (cached role→perm
  map) → 403 if missing; `requireAdmin` = convenience wrapper. A probe endpoint
  `GET /internal/authz/admin-check` (or similar) returns 200/403 for tests.
- **Bootstrap**: on startup, read `ADMIN_EMAILS` (csv env) → idempotently grant the `admin`
  role to any existing user with a matching email (INSERT … ON CONFLICT DO NOTHING). Document
  as the ONLY out-of-band grant; subsequent grants via an admin API in S1+.
- `services/api-gateway-bff/src/gateway-setup.ts` — guard `/v1/admin/*`: reject (401/403)
  a request whose JWT lacks an admin role **before** proxying (defense-in-depth; upstream
  re-checks). Mirror the existing `authProxy` pathFilter pattern.
- compose: `ADMIN_EMAILS` env on auth-service.

**Acceptance (spec §5.1):** admin probe 200 / non-admin 403 · bootstrap idempotent ·
old tokens (no `Roles` claim) → non-admin, no error · existing auth flows unregressed.
**Open design points (spec §5.2):** claim = role codes only (leaning); role-revoke staleness
bounded by access-TTL (track deferred if no deny-check). **/review-impl MANDATORY** (auth =
privilege-escalation surface; both guard layers fail-closed).
**Tests:** migration up/seed; claim-mint includes roles; middleware 200/403; bootstrap
idempotent (run twice); old-token-degrades; gateway guard blocks non-admin pre-proxy.

### S1 — config-service spine (new service + gateway)
- New `services/config-service/` (Go/Chi), DB `loreweave_config`:
  - `config_registry(key UNIQUE, value_type[bool|int|float|string], default_value,
    min, max, owning_service, description)` — the typed catalog (seeded, see S3).
  - `system_config(key FK→registry, value, updated_by, updated_at)` — overrides only.
  - `config_audit(id, key, old_value, new_value, changed_by, changed_at)`.
- `GET /internal/config` (all effective overrides; token-gated) + `GET /internal/config/{key}`.
- `GET /v1/admin/config` (registry ⨝ overrides, admin-gated) + `PATCH /v1/admin/config/{key}`
  (validate type+bounds, write override + audit) + `DELETE` (reset to env/default).
- gateway: proxy `/v1/admin/config*` (behind the S0 admin guard) + `configUrl` wiring + db
  bootstrap + compose block (pick a free port pair).

### S2 — runtime ConfigClient + first consumers
- **Python SDK** (`sdks/python/loreweave_config/` or per-service `clients/config_client.py`):
  `ConfigClient.get_bool/int/float(key, default)` — fetches `/internal/config` once, caches
  with TTL (≈30–60s, BookProfile pattern), **precedence DB > env > default**, never raises
  (degrade to env/default on config-service down).
- **Go SDK** (`services/.../internal/config` or a shared module) — same contract.
- Migrate the **wiki M8 flags** as the first live consumers: `knowledge-service`
  (`wiki_fewshot_enabled`, `wiki_llm_judge_enabled`, `wiki_llm_judge_sample_rate`) +
  `learning-service` (`wiki_learning_enabled`, `wiki_llm_judge_enabled`). Replace the direct
  `settings.x` reads at the call sites with `config.get_*(…, settings.x)` (env stays the
  fallback). **Live-smoke**: toggle in DB → effect within TTL, no restart.

### S3 — typed registry coverage
- Seed `config_registry` with all bool + numeric ops flags across knowledge/learning/
  translation/campaign/glossary (inventory them from each `config.py`/Go config). Per-field
  type + bounds. Each owning service's ConfigClient reads its own keys.
- Decision to make in S3 DESIGN: central seed file vs each service self-registers its keys on
  startup (POST `/internal/config/registry`). Self-register keeps ownership with the service.

### S4 — /admin FE page
- `frontend/src/features/admin/` (MVC): `hooks/useSystemConfig` (controller),
  `api.ts` (`/v1/admin/config`), `components/` (typed flag editor — toggle for bool, bounded
  number input for int/float, with default/override indication + reset), audit-log view.
- Role-gated route `/admin` (read `roles` from the auth context; the FE must surface roles —
  add to `UserProfile`/auth context, fed from the JWT or a `/v1/me` call).
- i18n ×4.

## 3. Risks (carry into BUILD)
- **R1 (HIGH, security)** broken guard = privilege escalation → `/review-impl` on S0 + S1.
- **R-CONFLICT (the deferral reason)** concurrent auth-permission work → re-baseline S0.
- **R-runtime** config-service down must degrade to env/default everywhere (never block a
  service from starting or serving).
- **R-staleness** role-revoke + config-cache TTL windows — document the bounds.

## 4. Pick-up checklist (future session)
1. Confirm the concurrent auth-permission work has merged to `main`.
2. Re-read auth-service's NEW authz shape; adapt §2-S0 (roles table / claim / middleware may
   already exist — reuse, don't duplicate).
3. Create branch `platform/rbac-system-config` off `main`.
4. `/loom` S0 from CLARIFY (re-validate acceptance criteria against the new auth baseline).
