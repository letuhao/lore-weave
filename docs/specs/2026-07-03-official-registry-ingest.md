# Spec — Official MCP Registry Ingest + Admin Curation · REG-P5-03

**Status:** DESIGN (clears `D-REG-P5-REGISTRY-INGEST`).
**Owner surface:** agent-registry-service (Go) + a small admin FE.
**Depends on:** P3 external-MCP security (SSRF guard + supply-chain scan) — an ingested
server reuses that pipeline before it can federate.

---

## 1. Goal

Let an **admin** populate the System-tier MCP catalog from the **official MCP Registry**
(`registry.modelcontextprotocol.io`) instead of hand-typing each server: pull the public
server list into a **curation queue**, review, and **approve** entries into System-tier
`mcp_server_registrations` — where they then pass the existing P3 supply-chain scan
before any user sees them.

## 2. Non-goals (v1)

- Auto-publish. **Nothing federates without explicit admin approval** (the whole point
  of the queue). No scheduled auto-approve.
- Local/stdio packages. We only ingest **`remotes` with `transport_type` streamable-http**
  (matches our external-MCP support; stdio is `D-STDIO-MCP`).
- Per-user ingest. This is a **System-tier, admin-only** curation flow.

## 3. Acceptance criteria (from REG-P5-03)

1. A pull lands official entries in the queue as **`pending`**; nothing is System-visible yet.
2. **Only an admin** can pull / approve / reject (a regular user → 403/404).
3. Approve → a System-tier `mcp_server_registration` is created and enters the **P3 scan**
   (`pending`→`active`/`suspended`); it federates only if the scan clears.
4. An entry whose remote URL is internal/loopback/metadata is **rejected by the existing
   SSRF guard** on approval (an official listing can't smuggle an internal target).
5. Re-pulling is idempotent (upsert by the registry's stable id; already-approved entries
   aren't duplicated).

## 4. Data model (additive)

```sql
CREATE TABLE registry_ingest_queue (
  ingest_id      UUID PRIMARY KEY DEFAULT uuidv7(),
  source         TEXT NOT NULL DEFAULT 'official',      -- future: other catalogs
  registry_id    TEXT NOT NULL,                          -- the official registry's stable server id
  name           TEXT NOT NULL,                          -- reverse-DNS
  description    TEXT NOT NULL DEFAULT '',
  version        TEXT NOT NULL DEFAULT '',
  endpoint_url   TEXT NOT NULL,                          -- the chosen streamable-http remote
  raw            JSONB NOT NULL DEFAULT '{}',            -- the full upstream entry (audit)
  status         TEXT NOT NULL DEFAULT 'pending'         -- pending | approved | rejected
                 CHECK (status IN ('pending','approved','rejected')),
  reviewed_by    UUID,
  approved_server_id UUID REFERENCES mcp_server_registrations(mcp_server_id) ON DELETE SET NULL,
  reject_reason  TEXT NOT NULL DEFAULT '',
  first_seen_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX uq_ingest_source_regid ON registry_ingest_queue(source, registry_id);
```

## 5. Upstream API (official registry)

- List: `GET https://registry.modelcontextprotocol.io/v0/servers?limit=&cursor=`
  (cursor-paginated). Each entry carries `name`, `description`, `version_detail`,
  `packages[]` (local — ignored) and `remotes[]` (`{transport_type, url}`).
- **Ingest rule:** take the first `remote` with a streamable-http transport; skip an
  entry with no usable remote (log the skip — never silently drop coverage).
- The upstream host is fetched through the **SSRF-safe client** (`newProbeClient`) — it's
  a trusted public host, but no exception to the guard. A pull is bounded (timeout,
  response cap, page cap) and fail-soft (a partial pull is fine; log what was fetched).

## 6. Endpoints (admin-gated)

Admin auth reuses the existing System-tier gate (`role == "admin"` in the JWT; the same
check `createMcpServer`/`createPlugin` use for System writes). All under
`/v1/agent-registry/admin/`:

- `POST /ingest/pull` — fetch the official registry → upsert into the queue as `pending`
  (idempotent on `(source, registry_id)`; updates description/version/endpoint on
  re-pull, but never downgrades an `approved`/`rejected` row back to `pending`). Returns
  `{ fetched, new, updated, skipped_no_remote }`.
- `GET /ingest/queue?status=&limit=&offset=` — list queue entries (admin).
- `POST /ingest/queue/{id}/approve` — validate the endpoint via the **P3 SSRF guard +
  model-capability rejection**; on pass, create a **System-tier**
  `mcp_server_registration` (endpoint + display_name + `is_external=true`, `status=pending`),
  fire the **P3 async scan**, set the queue row `approved` + link `approved_server_id`.
  Audited (`actor_kind=admin`). SSRF/model-cap failure → 400, queue row stays `pending`.
- `POST /ingest/queue/{id}/reject` — mark `rejected` + `reject_reason` (audited).

## 7. Security

- **Admin-only** on every route (a non-admin → 403; anti-oracle 404 on unknown id).
- **Approval reuses the P3 guard** — `classifyRegistrationURL` (SSRF: internal/loopback/
  metadata rejected even if the official listing points there) + `looksLikeModelEndpoint`
  (a model-capability "MCP server" is refused, upholding the provider-gateway invariant)
  + the supply-chain **scan** (`scanAsync`) so an official server with a poisoned
  tools/list quarantines (`suspended`) exactly like a user-registered one.
- **No secrets ingested** — official remotes are unauthenticated or OAuth-discovered;
  auth is configured separately (P3 OAuth) after approval if needed. The queue stores no
  credentials.
- **Egress:** the pull itself is one bounded outbound call to the known registry host;
  no user input drives the URL.

## 7b. Edge cases & residual risks (from an industry-practice review)

The official registry does namespace authentication (GitHub/DNS/HTTP challenges) but
explicitly "relies on the broader ecosystem for security scanning of actual server code"
and expects "aggregators to implement additional security checks, ratings, or curation."
And **verification ≠ safety** — the official channel has shipped a backdoor (Postmark) and
a verified marketplace leaked 3,000 credentials (Smithery). So our scan + admin gate is
the correct second layer, and these edge cases are load-bearing:

1. **Denylist / retroactive-removal sync (MUST).** The registry can denylist or remove a
   server after we approved it (spam/malicious/impersonation). On each `pull`, an
   already-`approved` `registry_id` that is now **absent or flagged deleted upstream** →
   the linked System server is **suspended** (dropped from federation) + the queue row
   marked `revoked_upstream`, audited. Without this we'd keep serving a rug-pulled server.
2. **Rug-pull / tool-definition mutation (MUST for System tier).** A server can serve a
   clean `tools/list` at approval and a poisoned one later (the "rug-pull" the 2026 MCP
   literature + mcp-scan mutation-detection target). System-tier ingested servers get a
   **periodic re-scan** (reuse the P3 `runScan`); a newly-HIGH finding → auto-`suspended`.
   (This also retro-hardens P3: a scheduled rescan of external servers, not just on-demand.)
3. **Endpoint dedup on approve (MUST).** Two registry entries can share an endpoint, or an
   endpoint may already be a System server. Approve rejects/links a duplicate rather than
   creating a second System row (System-tier currently has no `UNIQUE(endpoint)` — add a
   `uq_mcp_reg_system` partial index or check-before-insert).
4. **Refresh cadence.** Industry guidance: aggregators pull "on a regular but infrequent
   basis (~once/hour)." v1 is manual admin pull; a **scheduled hourly pull worker** (+ the
   denylist-sync + rescan of #1/#2) is the M-next target, off by default.
5. **OAuth-required official servers.** An entry whose remote needs auth → the approval
   scan probe 401s → the System server lands `error` (not federated), and the admin UI
   surfaces "needs OAuth" so the admin runs the P3 `/oauth/start` flow before it activates.
6. **Pull abuse / upstream courtesy.** A min-interval between pulls (admin-only, but avoid
   hammering the upstream) + a page cap; a partial pull is fine (fail-soft, logged).
7. **Namespace-auth trust is NOT sufficient.** We do not treat an official listing as
   trusted — every approval still runs the full P3 SSRF guard + model-capability rejection
   + scan. (This is the "verification ≠ safety" lesson made concrete.)

## 8. Testing

- **Unit:** the upstream-entry → queue-row mapping (pick the streamable-http remote; skip
  no-remote; reverse-DNS name); the idempotent upsert (re-pull doesn't duplicate / doesn't
  revert an approved row); the admin gate.
- **Live E2E-P5-C:** (a) a non-admin `pull`/`approve` → 403; (b) an admin pull (against a
  **stubbed** registry response — inject 2 entries incl. one with an internal remote and
  one public) lands both `pending`; (c) approve the public one → System row created +
  scan runs; (d) approve the internal-remote one → 400 SSRF_BLOCKED, stays `pending`;
  (e) the approved System server appears in a normal user's effective catalog only after
  the scan clears. (The live-against-the-real-registry pull is a smoke; the deterministic
  E2E uses a stubbed upstream to avoid a network dependency in CI.)

## 9. Milestones

- **M1** — schema + the pull (SSRF-safe fetch + entry mapping + idempotent upsert) + unit.
- **M2** — the admin queue list + approve (reuse P3 guard + scan) + reject + audit.
- **M3** — the admin FE (a curation table: pending entries with the flagged scan report,
  approve/reject) — lands in the **admin/CMS surface**, not the user Extensions panel.
- **M4** — live E2E-P5-C (stubbed upstream) + a real-registry pull smoke + `/review-impl`
  (admin-gate + SSRF-on-approve are load-bearing) + session update.

## 10. Estimated size

**L** (1 service + a small admin FE, an external integration, a new curation workflow,
admin-privilege + SSRF boundaries). Write the plan file at build time; `/review-impl`
mandatory. The buildable core (M1–M2) is agent-registry-only and self-contained; the
upstream API shape should be re-verified at build time (the official registry is young
and its `/v0` schema may still move — treat §5 as indicative, confirm against the live
API first).
