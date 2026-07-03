# Plan — Official MCP Registry Ingest + Admin Curation · D-REG-P5-REGISTRY-INGEST

**Spec (DESIGN):** [`docs/specs/2026-07-03-official-registry-ingest.md`](../specs/2026-07-03-official-registry-ingest.md).
**Size:** L (1 service + small admin FE; external integration; admin-privilege + SSRF boundaries). `/review-impl` mandatory.
**Surface:** agent-registry-service (Go) + a small admin FE.

## Seams (verified against code)
- **Reuse the P3 pipeline wholesale on approve:** `looksLikeModelEndpoint` → `classifyRegistrationURL` (SSRF) → INSERT System-tier `mcp_server_registration` (`is_external=true, status=pending`) → `scanAsync` (pending→active/suspended). This is exactly `createMcpServer`'s spine ([registrations.go:79](../../services/agent-registry-service/internal/api/registrations.go)).
- **SSRF-safe upstream fetch:** `newProbeClient(allowInternal)` ([probe.go:63](../../services/agent-registry-service/internal/api/probe.go)) — IP-pinned dial + cross-host-redirect refusal — for the `GET /v0/servers` pull. Body capped with `io.LimitReader`.
- **Migration:** append `registry_ingest_queue` to `migrate.go` `schemaSQL` (idempotent `CREATE ... IF NOT EXISTS`). Add `uq_mcp_reg_system` partial UNIQUE on `(endpoint_url) WHERE tier='system'` for endpoint dedup (§7b#3).
- **Admin gate:** new `requireAdmin` (= `requireUser` + `role=='admin'` → else 403); anti-oracle 404 on unknown ingest id.
- **Config:** add `OfficialRegistryURL` (default `https://registry.modelcontextprotocol.io`, override `AGENT_REGISTRY_OFFICIAL_URL` for the stubbed-upstream E2E).
- Helpers reused: `audit`, `bumpCatalogVersion`, `writeJSON/writeError`, `parseUUIDParam`, `actorKindOf`, `isUniqueViolation`, `nullStr`, `clampLimit`.

## Milestones
- **M1** — schema (`registry_ingest_queue` + `uq_mcp_reg_system`) + config + the pull: `mapUpstreamEntry` (tolerant: pick the first streamable-http remote; skip no-remote → counted, not silently dropped; reverse-DNS name; stable `registry_id`), `pullOfficialRegistry` (SSRF-safe fetch, cursor pages capped, body capped, fail-soft), idempotent upsert (`ON CONFLICT (source, registry_id)` — updates descriptive fields, NEVER downgrades approved/rejected → pending). **Unit** (mapper, upsert-preserves-status). TDD.
- **M2** — admin routes under `/v1/agent-registry/admin/ingest/`: `POST /pull`, `GET /queue`, `POST /queue/{id}/approve` (reuse P3 guard+scan; endpoint dedup → link not duplicate; SSRF/model-cap fail → 400, row stays pending), `POST /queue/{id}/reject`. Admin-only + anti-oracle 404 + audit. Unit (admin gate, approve reuses guard, dedup).
- **M3** — admin FE curation table (pending entries + scan report, approve/reject) in the **admin/CMS surface**, not the user Extensions panel.
- **M4** — live E2E-P5-C (stubbed upstream: 2 entries incl. one internal-remote → approve public = System+scan; approve internal = 400 SSRF; non-admin = 403) + a real-registry pull smoke + `/review-impl` (admin-gate + SSRF-on-approve load-bearing) + SESSION + COMMIT.

## Non-goals (v1, from spec §2)
No auto-publish (approval always explicit). No local/stdio packages (streamable-http remotes only). No per-user ingest (System-tier, admin-only).

## Deferred (tracked — gate #2 structural / naturally-next-phase)
- `D-REG-P5-INGEST-SCHEDULED-WORKER` — the hourly pull worker + denylist/retroactive-removal sync (§7b#1: absent-upstream approved server → suspend + `revoked_upstream`) + rug-pull periodic rescan (§7b#2, folds into `D-REG-P3-SCHEDULED-RESCAN`). Needs a background loop — structural, not in the buildable admin-triggered core.

## Risk boundaries (checkpoint/commit)
M1 (schema + pull, self-contained) → M2 (admin routes + approve = the security seam; commit together) → M3 (FE) → M4 (proof + review).
