# Plan — batch-clear the agent-journey MCP gaps · 2026-06-22

Branch `feat/knowledge-graph-ontology`. Clears the four BACKEND deferrals surfaced by the
agent-driven Dracula run + /review-impl, so the **entire** journey runs cleanly through the
**gateway** (not direct), with correct tenancy. Each fix is independent, low-risk, and
grounded in verified code (file:line below). One coherent effort = ONE continuous run.

**Out of this batch (separate FE + data track, not backend):** `D-JOURNEY-KG-BENCHMARK-UX`
M4 (FE badge/checklist/swap copy) + M5 (OpenAPI), `D-JOURNEY-ENRICH-COST-UNITS` (`*_cost_usd`→tokens
DB/API rename = migration + FE). These need the FE/contract surface, not this backend sweep.

Size: **L** (4 services, ~9 logic, side effects: gateway header contract + a new security gate
+ a new MCP tool + a wiki entity-source change). No phases skipped.

---

## M1 — `D-GW-XPROJECT-NOT-FORWARDED`: gateway forwards `X-Project-Id` (ai-gateway, TS)

**Root cause (verified):** the gateway never reads `X-Project-Id` inbound nor forwards it
downstream. `Envelope` has no `projectId`; `extractEnvelope`/`extractAdminEnvelope` don't read
it; `executeTool`/`adminHeaders` don't send it. So project-scoped tools (`kg_build_graph`,
`kg_build_wiki`, any `ctx.project_id`-resolving tool) get "no project in scope" through the gateway.

**Fix (5 additive edits):**
- `src/federation/federation.service.ts` — add `projectId?: string` to `Envelope` (lines 8-20); in `executeTool` header block (132-135) add `if (env.projectId) headers['X-Project-Id'] = env.projectId;`.
- `src/mcp/handlers.ts` `extractEnvelope` (14-21) — add `projectId: headerValue(headers, 'x-project-id')`.
- `src/mcp/admin-handlers.ts` `extractAdminEnvelope` (16-23) — same.
- `src/federation/admin-federation.service.ts` `adminHeaders` (97-105) — add the same forward line.

**Tests:** new `src/federation/federation.service.spec.ts` — `executeTool` with `projectId` in
the envelope sets `X-Project-Id` downstream; omitted when undefined. (No header-forwarding test
exists today; chat-service already sets `X-Project-Id` outbound + asserts it in its own tests.)

**Risk:** additive (forwards a header only when present) — cannot break callers that don't send it.

---

## M2 — wiki entity-frequency gate: `kg_build_wiki` finds 0 on a low-chapter book (knowledge-service, py) — NEW id `D-WIKI-ENTITY-FREQ-GATE`

**Root cause (verified, CORRECTS the earlier "draft-vs-active" framing):** `apply_build_wiki`
→ `_resolve_entity_ids` (build_wiki_effect.py:57) calls
`glossary_client.list_entities(book_id, status_filter="active")` → `GET …/known-entities?status=active`.
The Go handler `getKnownEntities` (extraction_handler.go:213-263) **IGNORES `status`** and gates on
`HAVING COUNT(chapter_entity_links) >= min_frequency` (**default 2**). On a single-chapter book the
26 entities each have frequency 1 → 0 returned → `BuildWikiNoEntities` → 422. (The OLD Dracula book
worked: 4 chapters → freq ≥2.) The `known-entities` endpoint is the EXTRACTION-ANCHOR endpoint
(frequency-gated by design); wiki should not use its frequency semantics.

**Fix (minimal, knowledge-service only — the Go handler already honors `min_frequency`):**
- `app/clients/glossary_client.py` `list_entities` (328-350) — add a `min_frequency: int = 2`
  param (preserves current callers) and pass it: `params={"status": status_filter, "min_frequency": min_frequency}`.
- `app/ontology/build_wiki_effect.py:57` — `_resolve_entity_ids` calls
  `list_entities(book_id, status_filter="active", min_frequency=1)` (wiki wants ALL of the book's
  entities, not just multi-chapter ones; each extracted entity has ≥1 link). `status` stays a no-op
  on the Go side, so drafts are included — correct for "build wiki for my book".
- (Alternative considered + rejected for now: switch wiki to `GET /internal/books/{id}/entities`
  — a frequency-independent list — but `min_frequency=1` is a 2-line change with the same effect.)

**Tests:** knowledge unit — `_resolve_entity_ids` passes `min_frequency=1` (assert the client call
kwargs); a glossary live/integration smoke that a 1-chapter book returns its entities at
`min_frequency=1` and 0 at the default 2.

**Risk:** low — only widens the wiki entity set on low-frequency books; high-frequency books unchanged.

---

## M3 — `D-ENRICH-MCP-OWNER-GATE`: book-ownership gate on auto-enrich (lore-enrichment, py)

**Root cause (verified):** `auto_enrich` (gaps.py:215) + the MCP tool take `book_id` as a free arg
with NO ownership check; `require_principal` is an unverified JWT decode; glossary coverage is read
via the internal S2S token (not user-scoped) → any authed user can enqueue a caller-paid enrichment
grounded on another user's book. lore-enrichment has book/glossary/knowledge clients but **no grant
client**.

**Fix (mirror composition's proven pattern + the shared `loreweave_grants` SDK):**
- NEW `app/clients/grant_client.py` — shim over `loreweave_grants.GrantClient` (init/get/close;
  `base_url=settings.book_service_url`, `internal_token=settings.internal_service_token`).
- `app/main.py` lifespan — `init_grant_client()` on startup, `close_grant_client()` on shutdown.
- `app/api/gaps.py` `auto_enrich` (after the `principal.user_id is None` 401, BEFORE the glossary
  read) — `lvl = await get_grant_client().resolve_grant(body.book_id, principal.user_id)`;
  `NONE → 404` (no existence oracle), `< VIEW → 403`. **VIEW** is the floor (read-only book +
  quarantined proposals; a viewer/translator may request enrichment). Fail-closed (book-service
  outage → NONE → 404). The MCP tool inherits the gate automatically (it delegates to `auto_enrich`).
- Book-service endpoint: `GET /internal/books/{book_id}/access?user_id=…` (X-Internal-Token) →
  `{grant_level, lifecycle_state}` (collaborators.go:174).

**Tests:** `tests/test_gaps_api.py` — mock `get_grant_client` (stub granting VIEW+) so the existing
contract-freeze tests stay green; add a no-grant→404 case. `tests/test_mcp_server.py` — add a
gate-denied case (the delegated handler raises 404 → tool returns `{success:false, status:404}`).

**Risk:** additive gate; existing tests need the grant-client stubbed (one fixture change).

---

## M4 — `D-COMPOSE-GENERATE-WORKER-POLL`: add `composition_get_generation_job` (composition, py)

**Root cause (verified):** when `COMPOSITION_WORKER_ENABLED=true` the `composition_generate`
confirm returns a `pending` job and there is no MCP tool to poll a composition generation job.

**Fix (Tier-R tool mirroring `composition_get_prose`):**
- `app/mcp/server.py` — new `composition_get_generation_job(project_id, job_id)`: `_ctx` →
  `_work_or_deny(project_id)` → `_gate(VIEW)` → `GenerationJobsRepo(get_pool()).get(tc.user_id, job_id)`
  (already exists, user-scoped) → assert `job.project_id == project_id` else `uniform_not_accessible()`
  → `job.model_dump(mode="json")`. `require_meta("R","book", synonyms=[…job status/poll job…])`.
- No repo change (`.get(user_id, job_id)` exists, generation_jobs.py:337).

**Tests:** `tests/unit/test_mcp_server.py` — add to `EXPECTED_TOOLS` + `TIER_R`; owner-ok + foreign-
project-refused cases.

**Risk:** read-only, gated; trivial.

---

## VERIFY (the batch payoff — re-run the journey THROUGH THE GATEWAY)

Rebuild ai-gateway + knowledge + lore-enrichment + composition images. Then on a fresh (or the
existing `019eef55`) book, **through the gateway** (`X-Project-Id` set):
1. `kg_build_graph` / `kg_build_wiki` no longer "no project in scope" (M1) → KG builds + **wiki
   produces articles** on the 1-chapter book (M2).
2. `lore_enrichment_auto_enrich` still works for the owner; a non-owner book_id → 404 (M3).
3. `composition_get_generation_job` appears in the federated catalogue + returns a job (M4).
Unit suites green per service; `python scripts/ai-provider-gate.py` clean; provider/language gates clean.

## Sequencing
M1→M2 unblock the gateway wiki path (do first, together); M3 + M4 are independent. All four land as
one continuous run with a single combined live-smoke. Update SESSION_HANDOFF (move the four rows to
"Recently cleared") + commit per milestone or one batch commit at the risk boundary.
