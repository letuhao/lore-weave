# Spec — Platform System-Config / Feature-Flags UI (D-PLATFORM-SYSTEM-CONFIG-UI)

**Status:** CLARIFY locked 2026-06-11 · epic sliced S0→S4 · S0 in DESIGN
**Branch:** TBD (`platform/rbac-system-config` off `main`) — NOT the wiki branch
**Origin:** SESSION_HANDOFF "▶ NEXT" after the M8 wiki flywheel; surfaces the M8 flags
(`wiki_fewshot_enabled`, `wiki_llm_judge_*`, `wiki_learning_enabled`) + all other ops
flags to operators without an env redeploy.

---

## 1. Problem

Every operational flag in LoreWeave is a Pydantic `BaseSettings` / Go env var **read once
at process startup**. Changing one (e.g. enabling the wiki few-shot path) requires editing
compose env + restarting the container. There is **no admin role, no central config store,
and no UI**. JWT carries only `sid` + `user_id` ([auth-service/internal/authjwt/jwt.go:11](../../services/auth-service/internal/authjwt/jwt.go#L11));
no `is_admin`/`role` column exists; the gateway has no authz guard.

## 2. Goal

An admin-gated UI to view + edit typed platform config at runtime, with changes taking
effect **without a service restart**, backed by an auditable store and enforced by a real
authorization model.

## 3. CLARIFY decisions (PO-locked 2026-06-11)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Admin/authz model | **Full RBAC** — roles + permissions, not a bare `is_admin` bool |
| D2 | Runtime application | **Apply without restart** — services read config from a shared store with cached reads (toggle effective within the cache TTL) |
| D3 | v1 config scope | **All typed config** — bools + floats/ints (sample rates, `max_examples`, `cost_per_article`, timeouts) across services |
| D4 | Slicing | **5 slices S0→S4, each its own `/loom`** (like campaign-service S0–S6); start S0 |
| D5 | Config store home | **New `config-service`** (Go/Chi, own DB) — per the "each service owns its DB" rule |

### Derived architecture (Lead recommendation, ratified at CLARIFY)
- **RBAC home = auth-service** (identity SSOT; mints the JWT). Roles travel in the **JWT
  claim** so `require_*` is a claim check, not a per-request DB hit; short access-token TTL
  bounds staleness.
- **config-service** (Go/Chi, DB `loreweave_config`) owns `system_config` (overrides) + a
  typed `config_registry` (key, type, default, bounds, owning-service, description). Exposes
  `/internal/config` (services read) + `/v1/admin/config` (UI writes, admin-gated at gateway).
- **Runtime consumption** = a small `ConfigClient` per consuming service (Python + Go) with a
  **TTL cache** (reuse the proven BookProfile 60s-TTL pattern), falling back to env/default on
  miss. **Precedence: DB override > env > code default.**
- **Audit** — every admin config write records who/when/old→new.

## 4. Slicing (each its own `/loom`, full 12 phases + PO checkpoints)

| Slice | Scope | Touches |
|-------|-------|---------|
| **S0** | RBAC foundation: roles/permissions/user_roles tables, roles in JWT claim, `require_permission`/`require_admin` middleware, env-seeded bootstrap admin, gateway `/v1/admin/*` guard | auth-service, api-gateway-bff |
| **S1** | config-service spine: DB (`system_config` + `config_registry`) + `/internal/config` read API + `/v1/admin/config` admin API + gateway wiring + audit table | config-service (new), api-gateway-bff |
| **S2** | Runtime `ConfigClient` (Py + Go, TTL cache, precedence) + migrate the **wiki M8 flags** as the first live consumers (end-to-end proof) | knowledge-service, learning-service, shared SDK |
| **S3** | Typed registry coverage: register all bool + numeric flags across services; per-field type/bounds validation | all flag-owning services |
| **S4** | `/admin` FE page: role-gated route, typed flag editor, audit-log view | frontend |

Each slice ends committed + handoff-updated; later slices can re-scope as earlier ones land.

---

## 5. S0 — RBAC foundation (this slice)

### 5.1 Acceptance criteria
1. A `roles`, `permissions`, `role_permissions`, `user_roles` schema exists in auth-service's
   DB, seeded with an `admin` role granting a `system_config:write` (and `:read`) permission
   and a default `user` role.
2. On login/refresh, the access token carries the user's **role codes** (and/or permission
   codes) as a claim.
3. auth-service exposes a `require_permission("…")` (and convenience `require_admin`)
   middleware; a protected probe endpoint returns 200 for an admin, 403 for a non-admin.
4. A **bootstrap** mechanism: `ADMIN_EMAILS` (env, comma-sep) → on startup, any existing user
   with a listed email is granted the `admin` role (idempotent). Documented as the only
   out-of-band admin grant; further grants go through an admin API (S1+).
5. The gateway guards `/v1/admin/*`: a request without the admin claim is rejected **before**
   proxying (defense-in-depth; the upstream service re-checks).
6. **No regression** to existing auth flows (login/refresh/logout/preferences); existing
   tokens without the new claim degrade safely (treated as no roles → non-admin).

### 5.2 Open design points (resolve in S0 DESIGN, ratify at REVIEW)
- **Claim shape**: role codes vs permission codes vs both in the JWT. Lean: **role codes**
  (compact) + a server-side role→permission resolution in middleware (so adding a permission
  to a role doesn't require re-minting tokens). Revisit if tokens get large.
- **Staleness**: revoking a role only takes effect at token refresh. Acceptable for v1 given
  short access-TTL (currently 7200s — may tighten for admin, or add a deny-check). Track as a
  deferred row if not solved in S0.
- **Migration ordering / idempotency**: bootstrap must be safe on every boot and on a fresh DB.

### 5.3 Risks
- **R1 (security, HIGH)** — a broken guard = privilege escalation. Both layers (gateway +
  upstream) must fail-closed; `/review-impl` mandatory before COMMIT.
- **R2** — JWT claim bloat if permissions are embedded; mitigated by role-codes-only.
- **R3** — token-staleness window on role revoke (see 5.2).
- **R4** — existing long-lived tokens lack the claim → must degrade to non-admin, never error.

### 5.4 Out of scope for S0
The config store, the runtime ConfigClient, the typed registry, and the FE page (S1–S4). S0
delivers ONLY the authorization substrate + the admin bootstrap + the gateway guard.
