# Track A brief — Discovery & Workflow Mechanism (the critical-path spine)

**One-liner:** build the deterministic discovery + workflow machinery + the gateway-central cross-cutting
fixes. This is the spine every other track integrates with.

- **Read first:** the umbrella spec (§4.1, §4.3, §4.4, §6, §6b) · `contracts.md` (you OWN C1–C4, C6-resolve) ·
  investigation `investigations/2026-07-09-persistent-memory-and-longsession-continuity.md` (§2 hot-path trim).
- **Owns (services · files):**
  - ai-gateway (TS): `src/federation/find-tools.ts`, `src/mcp/handlers.ts`, `src/federation/catalog.ts`, config
  - mcp-public-gateway (TS): `src/scope/{tool-policy.ts, scope-filter.ts, invoke-tool.ts}`, activation store,
    structured-content/error normalization
  - chat-service (Py — **only these files**): `app/services/{tool_discovery.py, tool_surface.py, catalog.py,
    tool_result_wire.py}`, a new step-runner + workflow client module, `app/services/stream_service.py`
    (LLM-call/output-budget + advertise paths only)
  - agent-registry-service (Go): `internal/migrate/migrate.go` (`workflows` table), workflow authoring API
  - CI: a tier-tag gate script
- **Deliver in order (milestones):**
  1. **WS-0 Foundations** — single-source the C1 enum (+ `lore_enrichment`→glossary alias); define the C2
     visible set = `catalog ∩ non-legacy ∩ isToolAllowed`; make legacy tools **labeled-deprecated** not
     dropped; tier-tag CI gate (every write tool has explicit non-R `_meta.tier`).
  2. **WS-1a Discovery triad** — `tool_list`/`tool_load`/`skill_list`/`skill_load` (C2), TS+Py lockstep,
     extend `find-tools.spec.ts`; demote `find_tools` (OQ1). **WS-1b hot-path write fix** — always-hot write
     allowlist / reserved write sub-budget in `tool_surface.py` + read-verb classifier fix. → **N1**
     > **AS-BUILT (reconciled 2026-07-14, all-tracks-clear M9).** `tool_list`/`tool_load` shipped as named
     > (TS+Py lockstep). **The skill half shipped under DIFFERENT names**: agent-callable skill discovery is
     > `registry_list_skills` + `registry_get_skill` (agent-registry-service `mcp_server.go`, federated under
     > the `registry` domain, Tier-R, discoverable via `tool_list`) — NOT `skill_list`/`skill_load`. The
     > capability the "asymmetry fix" wanted (a model can ask "what skills exist" + "load skill Y"
     > deterministically) exists; only the tool name differs from this brief. A 28-agent audit initially
     > flagged `skill_list`/`skill_load` as an unbuilt GAP; the adversarial refuter overturned it — inverse
     > drift (built-under-another-name). No code change needed; if a future scenario shows a model reaching
     > for the literal `skill_list`, add it as a thin alias then.
  3. **WS-2a Workflow storage+authoring** — `workflows` table + C3 `steps` schema + `registry_propose_workflow`
     (system+user/book) + HITL spine. **WS-2b Step-runner** — deterministic runner honoring gates + async-honesty
     guard (OQ9); `workflow_list`/`workflow_load`. → **N2**
  4. **Gateway cross-cutting** (any time after WS-0): C4 error-envelope normalization + content/structuredContent
     uniformity; #6 gated-reason in `tool_list`; F3 reserved-output floor.
  5. **WS-6** — retire mandatory `find_tools` bias once evals (Track C) confirm mid-tier success.
- **Produces contracts:** C1, C2, C3, C4; the resolve side of C6.
- **Definition of done:** a mid-tier model does `tool_list`→`tool_load`→call with the write tool already hot
  (no brute-force); workflows author+run with gates honored + async honesty; all failures share the C4 envelope.
- **Validates via:** scenarios S00a, S00b, S00c (mechanism); feeds N3 flagship.
- **Watch:** the TS/Py lockstep tax lives here — every discovery primitive lands in both `find-tools.ts` and
  `tool_discovery.py`, guarded by `find-tools.spec.ts`.
