# KM5 — Admin / System-tier MCP surface (RS256 + `/mcp/admin` + System template writes)

**Epic:** KG customizable-ontology (`2026-06-20-knowledge-graph-ontology-build.md`),
phase **KM5** (the high-risk auth milestone). **Spec:** `docs/specs/2026-06-20-knowledge-assistant-mcp-tools.md`
§4 (authority/identity), §5 (gating), §6.1 (2 MCP servers), §8 (KM5 row), INV-T2/T3/T4/T6.
**Reference (read-only, Go):** `contracts/adminjwt/{verify,claims,parse_key,breakglass}.go`
+ glossary `internal/api/system_admin_handler.go` (System CRUD) + `action_confirm.go`
(`authorityAdmin` branch — itself still 501 in glossary).

## Why this is XL and decomposed

KM5 stacks four distinct risk surfaces: a new **RS256 admin authority** (never trust
`X-User-Id`), **System-tier writes** (every one human-confirmed, INV-T3), a **physically
separate `/mcp/admin` MCP transport** (RS256-gated before `tools/list`, INV-T6), and
**cross-service federation** (ai-gateway TS + chat CMS surface). Built as four
risk-boundary milestones, each its own `/loom` run + commit + `/review-impl` (auth).

> **Key finding (2026-06-21):** glossary's admin tier is **REST-only** — its MCP
> `/mcp/admin` server and `authorityAdmin` confirm branch are themselves **unbuilt** (also
> 501). So the *RS256 verify contract* has a shipped Go upstream to port (M1), but the
> *MCP-admin server + gateway federation* (M3/M4) have **no shipped upstream to mirror** —
> they are net-new and carry the most risk.

| Milestone | Scope | Risk | Upstream |
|---|---|---|---|
| **KM5-M1** ✅ | RS256 admin-JWT verify machinery (port `adminjwt`) + config + `cryptography` pin | low (pure, no DB) | ✅ `contracts/adminjwt` |
| **KM5-M2** | System-tier template write effect (create/patch/delete) + wire `auth=admin` confirm branch (re-verify RS256 at confirm, bind `asub`) + direct admin HTTP routes + `kg_system_*` descriptors | med-high (System writes) | ✅ glossary `system_admin_handler` |
| **KM5-M3** | `/mcp/admin` MCP server (RS256-gated transport) + admin tools (`kg_admin_template_read` R, `kg_admin_propose_template` C) | high (new transport, INV-T6) | ⚠️ none |
| **KM5-M4** | ai-gateway `/mcp/admin` federate (TS) + chat CMS surface + `knowledge_skill.py` | highest (cross-service) | ⚠️ none |

## Contract (mirror `contracts/adminjwt`, identical wire bytes)

A SINGLE platform admin token (minted by auth-service over its KMS key) must verify the
same in Go (glossary) and Python (knowledge) — so the constants are pinned identical:
- **`iss = "loreweave-auth"`, `aud = "admin-cli"`, scope `"admin:write"`.**
- **RS256 only** (rejects `alg:none` + HS/EC/PS; alg-confusion dead via allow-list + key object).
- **exp required + enforced**; **iss/aud pinned**; **kid pinned** = `hex(SHA-256(SPKI DER))`.
- Key config env `ADMIN_JWT_PUBLIC_KEY_PEM` (SPKI/PKIX "PUBLIC KEY" PEM, or base64 of it;
  PKCS#1 rejected). Unset → admin **disabled** (callers 503). Same env name as glossary.
- **Scope check is the caller's** (route asserts `admin:write`, 403 if absent) — verify only authenticates.

## KM5-M1 — RS256 admin-JWT verify machinery ✅ SHIPPED (2026-06-21)

Pure, fail-closed, no DB — the security keystone, mirroring how the class-C confirm spine
started codec-first (KM6-M1).

| File | Change |
|---|---|
| `app/auth/admin_jwt.py` | **NEW** — `verify_admin_token`, `load_admin_key`, `parse_rsa_public_key_pem`, `key_fingerprint`; `AdminClaims` (has_scope), `AdminKey`, `AdminTokenInvalid`; `ISSUER/AUDIENCE/SCOPE_ADMIN_WRITE`. Port of `adminjwt`. |
| `app/config.py` | `admin_jwt_public_key_pem: str = ""` (optional; unset → admin disabled). |
| `requirements.txt` | pin `cryptography>=42` (RS256 backend — was transitive-only; security-critical). |
| `tests/unit/test_admin_jwt.py` | **NEW** — 20 unit tests. |

**Stricter than Go on purpose:** `load_admin_key` always sets `kid = fingerprint`, so kid is
**always** enforced (Go's `expectKID` is optional). A real admin token already carries the
kid header (auth-service sets it), so this is safe and tighter.

**VERIFY:** 2870 unit passed on host (`PYTHONPATH=sdks/python`, no `INTERNAL_SERVICE_TOKEN`),
incl. 20 new admin_jwt tests: valid-verify+scope, scope-is-caller-side, wrong-key, **alg:none**,
**HS256 alg-confusion (hand-crafted — PyJWT refuses to *encode* it)**, expired, missing-exp,
bad-iss, bad-aud, kid-mismatch, missing-kid, None-key, empty-token, unset→None, SPKI parse +
stable fingerprint, **PKCS#1 rejected**, **non-RSA SPKI (EC) rejected**, base64-of-PEM, garbage→raise.
*(The baked prod container is NOT a test env — missing test deps + httpx/starlette drift give
false failures; host is the canonical runner — see memory.)*

**LIVE-SMOKE:** N/A at M1 — pure machinery, no path wires it yet → **deferred to
`D-KM5-M2-LIVE-SMOKE`** (the `auth=admin` confirm branch is where verify first runs cross-service).

**`/review-impl` (auth boundary, mandatory):** 0 HIGH. **1 MED accepted + documented** — `verify`
does not require `sub` (faithful to Go); the **M2 admin-confirm binding MUST reject an empty
`sub`/`asub`** (the guard belongs at the binding site, not the codec). 1 LOW fixed (added the
non-RSA-key rejection test). COSMETIC redundant-except accepted.

## KM5-M2 — System-tier writes + `auth=admin` confirm branch ✅ SHIPPED (2026-06-21)

The load-bearing milestone: System-tier template writes (INV-T3 — every System write
human-confirmed) reached ONLY via the RS256-gated `auth=admin` confirm path.

| File | Change |
|---|---|
| `app/db/repositories/system_templates.py` | **NEW** — `SystemTemplatesRepo` (create/patch/deprecate + `get_system_template`/`code_exists`). `_load_system` is the **inverse** of `OntologyMutationsRepo._load_writable`: it asserts the row IS system, so the admin path can never reach a user/project schema. `create` requires a new code (rejects the seeded `general`/`xianxia-harem`). |
| `app/ontology/system_effect.py` | **NEW** — `SystemTemplateParams`(verb create/patch/delete) + `apply`/`preview`; re-validates target + `expected_schema_version` drift at confirm (optimistic concurrency). |
| `app/ontology/confirm.py` | `DESC_SYSTEM_CREATE|PATCH|DELETE` added to `_LIVE_DESCRIPTORS` (admin authority). |
| `app/routers/public/kg_actions.py` | `auth=admin` branch wired (`_authorize_admin`): re-verify RS256 `X-Admin-Token` → require `admin:write` → bind `sub == asub` (both non-empty) **before** the jti claim → dispatch `_confirm_system`. **Authority↔descriptor pairing enforced** (a System descriptor MUST be admin authority, a grant descriptor MUST be grant — `/review-impl` fix). Cached admin key (resolve-once, fail-disable→503). |
| tests | `tests/unit/test_kg_actions_admin.py` (15 admin-branch tests, real RS256), `tests/integration/db/test_system_effect.py` (10 real-PG), tripwire + non-live-descriptor updated. |

**VERIFY:** 2884 unit + 51 KG-ontology integration (real PG, incl. 10 new `system_effect`)
green. 4 unrelated integration failures (`extraction_jobs`/`provenance` — no import path to
any changed file) are pre-existing/environmental.

**LIVE-SMOKE (D-KM5-M2-LIVE-SMOKE CLEARED):** in-container driver on real PG + real RS256 +
real `consumed_tokens` ledger — preview 200 (non-consuming) → confirm 200 (system row landed,
verified in PG) → replay 422 (single-use) → no-admin-token 401; smoke row cleaned. Driver removed.

**`/review-impl` (auth boundary, mandatory):** 0 HIGH. **1 MED found + FIXED** — authority↔descriptor
pairing was unenforced (an `auth=admin` + grant descriptor could drive a project effect; an
`auth=grant` + System descriptor could drive a System write — only forgeable with the JWT
secret, but the authority model must enforce it). Fixed + 2 tests. The KM5-M1-carry MED
(reject empty `sub`/`asub`) is implemented + tested (`test_admin_empty_asub_403`). LOW accepted:
admin key cached at startup → rotation needs a restart (matches glossary; documented).

## KM5-M3 — the `/mcp/admin` MCP server (RS256-gated transport) ✅ SHIPPED (2026-06-21)

The agent PROPOSE side of the System tier — a physically separate, RS256-gated MCP
endpoint. Net-new (no shipped glossary upstream).

| File | Change |
|---|---|
| `app/auth/admin_key.py` | **NEW** — shared process-cached admin-key resolver (`get_admin_key`), used by both the confirm branch (M2) and the transport gate (M3). kg_actions refactored to use it. |
| `app/mcp/admin_server.py` | **NEW** — second `FastMCP` instance + `kg_admin_template_read` (R) + `kg_admin_propose_template` (C: verb create/patch/delete → mints an `auth=admin` confirm-token, `asub`=verified RS256 `sub`, NO write). `rs256_gate` ASGI wrapper verifies `X-Admin-Token` BEFORE `tools/list` (401/503; `inner` never runs without a valid token → can't enumerate). |
| `app/db/repositories/system_templates.py` | `list_templates(include_deprecated=)` for the admin read tool. |
| `app/main.py` | mount `/mcp/admin` **before** `/mcp` (Starlette prefix order); run the admin session manager in the shared MCP exit-stack. |
| tests | `tests/unit/test_admin_mcp_server.py` (9: catalog isolation both directions, mount-order, gate 401/503/invalid/delegate, propose scope/sub/disabled), `tests/integration/db/test_admin_mcp_tools.py` (3, real PG: read lists seeded, propose mints valid token + writes nothing, patch descriptor matches verb). |

**Defense-in-depth (3 independent checks, INV-T2/T3/T6):** (1) transport RS256 gate blocks
enumeration without a verified token; (2) each tool re-verifies to recover claims + checks
`admin:write` for the mint; (3) the confirm endpoint (M2) re-verifies AGAIN + binds `sub==asub`
before the single-use write.

**VERIFY:** 2893 unit + KG-ontology integration (real PG) green. **LIVE-SMOKE
(D-KM5-M3-LIVE-SMOKE cleared):** real mounted `/mcp/admin` gate → 401 without token; then the
**full KM5 chain** — `kg_admin_propose_template` mints (real RS256) → redeemed at
`/v1/kg/actions/confirm` → System template written to real PG → cleaned.

**`/review-impl` (auth boundary):** 0 HIGH. **1 MED fixed** — the mount order (`/mcp/admin`
before `/mcp`) is load-bearing for INV-T6 but was untested; added a route-order assertion (a
reorder would route the admin surface to the ungated public app). 1 LOW accepted: admin read
needs only a valid admin token (System templates are already world-readable via `/mcp`'s
`kg_list_templates`, so this is already stricter than the data requires); propose needs `admin:write`.

## KM5 status: backend COMPLETE (M1–M3). Remaining = KM5-M4 (cross-service, deferred)
The RS256 keystone, System-tier writes + `auth=admin` confirm, and the `/mcp/admin` server are
all shipped + live-proven. **KM5-M4** (ai-gateway `/mcp/admin` federation in TypeScript + the
chat CMS surface + `knowledge_skill.py`) is the cross-service surfacing layer — highest blast
radius, no shipped upstream, and glossary hasn't shipped its half either. Recommended **deferred**
(`D-KM5-M4-GATEWAY-CMS`) until the gateway/chat admin-federation pattern is built (shared with
the glossary epic). The knowledge backend is fully ready for it.

## (historical) Carry-forward into KM5-M3 (the `/mcp/admin` server — no shipped upstream)
- The **mint** side is still absent: nothing mints `auth=admin` + `kg_system_*` tokens in prod
  yet (the confirm path is fully tested but unreachable until M3 wires the MCP admin tool). This
  dead-mint window (M2→M3) is intentional + documented.
- M3 builds the **physically separate `/mcp/admin`** FastMCP app (RS256-gated at transport BEFORE
  `tools/list` → no token = 401, can't enumerate; INV-T6) + `kg_admin_template_read` (R) +
  `kg_admin_propose_template` (verb create|patch|delete — mints the `auth=admin` confirm-token,
  `asub` = the verified RS256 `sub`). Reuse `verify_admin_token` (M1) at the transport gate.
- The admin tools must NEVER appear in the existing `/mcp` catalog (INV-T6) — separate registry.
