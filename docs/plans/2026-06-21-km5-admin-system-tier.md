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

## Carry-forward into KM5-M2
- **Bind `asub`:** at confirm, re-present + re-verify the RS256 `X-Admin-Token`, assert its
  `sub == claims.admin_sub` AND `sub`/`asub` are **non-empty**, AND `has_scope(admin:write)`.
- **Resolve the key once** (module singleton / DI provider), not per request (parse cost + log spam);
  parse-failure → log loud + disable (503), never crash-loop.
- **Terse uniform 401** at the route (don't leak the distinct internal kid/sig messages).
- Add `kg_system_create|patch|delete` to the confirm codec's live descriptor set (tripwire test).
- System-template writes are **DML** on the existing `kg_graph_schemas` table — **no migration**.
