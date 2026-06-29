# Plan — Public MCP P3: per-key call audit + owner view (H-O)

- **Date:** 2026-06-28 · **Branch:** feat/public-mcp-gateway · **Size:** L (cross-service: edge + auth; 1 migration)
- **Spec:** docs/specs/2026-06-26-public-mcp/03 §H-O · 04 §P3 ("append-only `mcp_call_audit` + owner audit view").
- **Default /loom v2.2; /review-impl at POST-REVIEW** (credential-domain, append-only-integrity).

## Why H-O now (not H-K)
H-K (per-key spend sub-cap) needs the key's `spend_cap_usd` at provider-registry's atomic
reserve — which requires it riding `job_meta`, the **dormant Wave-C carrier** (no priced tool
exposed yet). So H-K is premature. **H-O is live-meaningful today**: the edge sees *every*
public-MCP call (reads, denials, rate-limits), so the audit trail is real now, with no Wave-C
dependency. H-K → deferred to Wave-C/P4 alongside `D-PMCP-KEYID-JOBMETA-WIRING`.

## Design
auth-service owns the credential domain + the edge already calls it (`/internal/mcp-keys/resolve`),
so the audit table + endpoints live there. Mirror the existing `admin_token_issuance_audit`
append-only pattern (incl. the `REVOKE UPDATE,DELETE` guard).

### auth-service
- **Migration** `mcp_call_audit` (append-only): `audit_id`, `key_id`, `owner_user_id`, `tool_name`
  (NULL for non-call methods), `method`, `outcome` CHECK (`relayed`/`denied_scope`/`rate_limited`/
  `unauthorized`/`upstream_error`), `trace_id` NULL, `created_at`. Index `(owner_user_id, key_id,
  created_at DESC)`. REVOKE UPDATE/DELETE (same dev-stack caveat as admin audit).
- **`POST /internal/mcp-keys/audit`** (X-Internal-Token) — ingest a **batch** of rows
  `{key_id, owner_user_id, method, tool_name?, outcome, trace_id?}[]` (a JSON-RPC batch = N rows).
  Best-effort; validates owner_user_id/key_id UUIDs; bulk INSERT.
- **`GET /v1/account/mcp-keys/{key_id}/audit`** (JWT, owner-only) — recent rows for a key the
  caller owns (verify ownership; `limit`/`offset`, default 50). Returns rows + the key name.

### edge (mcp-public-gateway)
- New `AuditClient` (fire-and-forget POST to auth `/internal/mcp-keys/audit`; never blocks/raises
  into the response path; drops on error — best-effort, matches the resolve `last_used_at` write).
- Controller fires audit at each terminal branch with the resolved key/user + the tool name(s)
  from the request: `rate_limited` (429), `denied_scope` (gate), `relayed` (sent upstream;
  outcome refined to `upstream_error` on a 5xx/transport fail). One row per `tools/call`
  (reuse the existing tool-name extraction); non-call methods → `method` only, `tool_name` NULL.

### FE (Settings → MCP access)
- Minimal per-key **audit view**: expand a key row → recent calls (tool · outcome · time) via
  `GET …/{key_id}/audit`. Hook + api + i18n ×4. (Read-only; flag-gated like the rest of the tab.)

## VERIFY (≥2 services → live-smoke)
- auth-service real-PG: ingest batch → owner read returns them; append-only (UPDATE/DELETE blocked
  under app role — dev caveat noted); cross-owner read denied.
- edge unit: AuditClient fires the right outcome per branch; never blocks on auth failure.
- **Live-smoke:** through the running edge, make a `relayed` call, a `denied_scope` call, and a
  `rate_limited` burst with a real key → `GET /v1/account/mcp-keys/{id}/audit` shows all three
  outcomes; cross-owner read 403/404.

## Out of scope / deferred
- **H-K** per-key spend sub-cap → Wave-C/P4 (needs the dormant carrier). 
- Retention/rotation of audit rows (volume) — note only; revisit if it grows.
