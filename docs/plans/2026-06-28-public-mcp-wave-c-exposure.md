# Public MCP — Wave-C Write/Priced Tool Exposure (CLARIFY + Plan)

- **Date:** 2026-06-28
- **Branch:** `feat/public-mcp-gateway`
- **Status:** CLARIFY (PO checkpoint) — human green-lit "start the exposure track" 2026-06-28
- **Anchors:** [`05-tool-scope-map.md`](../specs/2026-06-26-public-mcp/05-tool-scope-map.md) §2/§4/§6, [`2026-06-28-public-mcp-p4-wave-c.md`](2026-06-28-public-mcp-p4-wave-c.md) §8 staged flip, [`03-public-mcp-security-design.md`](../specs/2026-06-26-public-mcp/03-public-mcp-security-design.md)
- **Closes (when complete):** `D-PMCP-PROVIDER-HARDENING`, `D-PMCP-KG-WRITE-BUILD-EXPOSURE`, `D-PMCP-PRICED-EXPOSURE-FLIP`, and the remaining feature-gap half of `D-PMCP-MEMORY-PROJECT-OWNER`.

---

## 1. What is already done (the spine — do NOT rebuild)

The hard, risky machinery is built + live-proven in P0–P5 (see SESSION_HANDOFF ✅ rows):

| Capability | Status |
|---|---|
| Per-key spend attribution (`mcp_key_id` → `job_meta` → `usage_logs`) | ✅ live-proven (carrier + worker-carrier) |
| Per-key spend sub-cap (H-K) → 402 `MCP_KEY_CAP_EXCEEDED` | ✅ live-proven E2E |
| Human-approval spine (OD-2, `mcp_pending_approvals`) + `confirm_action` self-confirm | ✅ shipped + proven |
| Edge propose→confirm divert (fail-closed) | ✅ shipped (single-message; batch → `D-PMCP-BATCH-WCONFIRM-DIVERT`) |
| Append-only audit per call (H-O) | ✅ shipped + live-smoked |
| Per-key rate-limit (edge Redis fixed-window) | ✅ shipped |
| BYOK-only spend gate (PUB-12) + per-tool `incurs_cost` gate (PUB-10) | ✅ shipped, 3 registry entry points |
| Memory owner-gate (H-U) on the 5 `memory_*` handlers | ✅ shipped + **cross-tenant live-proven 2026-06-28** |
| H-I project_id-as-arg scope adoption (safe behind H-U) | ✅ shipped |

**So Wave-C is NOT green-field.** It is (a) the small remaining per-provider hardening, and (b) flipping the edge `advertise` bit per provider, each behind a live-smoke gate.

---

## 2. What remains (the 4 rows) → scope of THIS track

### Row → work mapping
| Deferred row | Remaining work |
|---|---|
| `D-PMCP-PROVIDER-HARDENING` | `idempotency_key` (H-G) on non-idempotent Tier-A creates (book_create, book_chapter_create, glossary create_chapter_link/create_evidence/propose_new_entity/user_create, composition outline/rule/link/work creates) + decide the `include_shared` representation for list/read tools |
| `D-PMCP-KG-WRITE-BUILD-EXPOSURE` | H-I ownership-checked `project_id` path on kg **write/build** tools + `incurs_cost` cost-tag mechanism for `kg_build_graph`/`kg_build_wiki`/`kg_run_benchmark` (the `_meta`-exempt legacy knowledge tools have no `incurs_cost` hook yet) |
| `D-PMCP-MEMORY-PROJECT-OWNER` (remaining half) | H-I on kg write/build tools — folds into the row above |
| `D-PMCP-PRICED-EXPOSURE-FLIP` | the staged §8 flip: advertise priced Tier-W tools provider-by-provider, each only **after** that provider's attribution live-smoke passes |

### The per-provider EXPOSURE GATE (Definition of Done before a provider's write/priced tools advertise)
A provider's tools flip to advertised ONLY when ALL hold:
1. **Idempotency** — every non-idempotent create takes an `idempotency_key`; edge dedups `(key_id, tool, args_hash)`.
2. **Ownership** — every tool is owner/owner-scoped (OD-8); project-scoped tools H-I+owner-gated (the memory pattern).
3. **Cost-tag** — every priced tool carries `incurs_cost`; the BYOK + cap gate fires (PUB-10/12 + H-K).
4. **Attribution live-smoke** — a real cross-process spend through the worker-carrier lands `usage_logs.mcp_key_id` AND a tiny cap → 402 (the `D-PMCP-CARRIER-E2E-LIVE-SMOKE` recipe, per provider).
5. **Approval** — Tier-W defaults to the human-approval queue; `allow_self_confirm` is opt-in per key.
6. **Audit** — every relayed/denied/capped call appears in `mcp_call_audit` (already universal).

---

## 3. Recommended slice order (each is one /loom slice, size S–M)

Ordered cheapest-and-safest first; priced/write advertise LAST per provider.

- **Slice 1 — Edge-centric idempotency for ALL write_auto creates** ✅ **SHIPPED 2026-06-28** (`D-PMCP-PROVIDER-HARDENING` idempotency half).
  **Design pivot from the original per-service sketch:** the dedup lives at the **edge** (`mcp-public-gateway`), keyed on tier — so a single mechanism covers **every** `write_auto` create across all providers (book, glossary, composition), not just book+composition, and needs **zero Go/Python service changes** (no shared-tree hazard with the concurrent composition LOOM). An agent supplies `idempotency_key` on a single `write_auto` `tools/call`; the edge dedups on `(key_id, tool, idempotency_key)` via Redis (mirrors the rate-limiter): first call relays + caches the response, a retry REPLAYS it, a concurrent in-flight retry gets an "in progress" error. The key is **stripped before relay** (ForbidExtra-safe) and **advertised** on `write_auto` tools' schemas at `tools/list`. Fail-OPEN on store outage (a Redis blip must not block a write). `composition_create_work` + `book_chapter_bulk_create` already idempotent → untouched. **VERIFY:** 171/171 edge suite (incl. 51 new idempotency unit tests + a controller strip integration test) + tsc + nest build clean. Single-service; live double-submit folds into the Slice-4 per-provider exposure smoke. **This collapses the original Slice 1+2 idempotency work into one.**
- **Slice 2 — `include_shared` decision** ✅ **RESOLVED 2026-06-28 (no code change — owner-only already enforced)** (`D-PMCP-PROVIDER-HARDENING` remainder).
  A full audit of every list/read MCP tool (book/glossary/knowledge/translation/composition) found **all are already owner-scoped for public keys**: `book_list` drops the collaborator clause via `OwnerOnlyFromCtx` (OD-8, live-proven); glossary list tools gate on `bookToolAuth` + book-scoped queries; kg reads use `_resolve_project_owner` (owned-only, anti-oracle "project not found"); translation gates on `require_book_owner`; composition repos filter on `user_id` + `_work_or_deny`. The only intentionally-shared reads are System-tier (`glossary_list_system_standards`, `kg_list_templates`) and already hardened (EntityCount stripped). **Decision: keep owner-only, do NOT add an `include_shared` opt-in** — a public key enumerating shared rows IS the OD-8 list-leak class. → `D-PMCP-PROVIDER-HARDENING` fully closed.
- **Slice 3 — knowledge kg write/build H-I** ✅ **SHIPPED 2026-06-28** (`D-PMCP-KG-WRITE-BUILD-EXPOSURE` + memory remainder).
  **The real gap was narrow + precise:** all 14 kg write/build handlers ALREADY owner-gate (`_resolve_project_owner`/`_and_level`, OD-8-enforced for public keys) — but their arg models extended `BaseModel` with **no `project_id` field**, so a public key (the edge mints no `X-Project-Id`) couldn't *target* a project (fail-closed "a project must be in scope", unusable not leaky). Fix = the proven memory H-I pattern: switched the 13 project-scoped write/build arg models from `BaseModel` → `ProjectScopedArgs` (10 in `graph_schema_tools.py`, 3 in `build_tools.py`) + added `project_id` to their hand-written schemas (drift-lock test enforces schema==model). `kg_project_create` (book-id, creates the project) + `KgEntityEdgeTimelineArgs` (entity-scoped) correctly left alone. The executor's universal `_resolve_project_scope` (envelope wins → arg supplies → owner gate validates, D3 preserved) makes it safe. **Cost-tags: NOT needed** — `kg_build_graph`/`wiki`/`run_benchmark` are `write_confirm` tier → propose→confirm → carrier (`mcp_key_id`+`spend_cap`) → H-K cap; there is no spend path bypassing human-approval-or-cap (direct `/v1/kg/actions/confirm` is browser-JWT-only, unreachable from the edge), so the explicit `incurs_cost` flag is redundant for Tier-W (it matters only for Tier-R/A paid tools). **VERIFY:** 3143 knowledge unit tests pass incl. 3 new cross-tenant security tests (public-key write → "project not found" anti-oracle; build-tool D3 envelope-wins; build-tool cross-tenant denial). **/review-impl: no HIGH/MED** — verified all 13 handlers gate + parent-scope every client-supplied id to the owned project (no `worker-loaded-id` leak). **LOW-1** (coverage): cross-tenant tests directly cover 2/13 tools; the other 11 rely on the shared, independently-tested owner gate + verified parent-scoping (accepted — single enforcement point). **LOW-2** (staging): kg-specific attribution live-smoke (carrier→`usage_logs.mcp_key_id` + cap on a real `kg_build` job) is a **Slice-4 per-provider gate**, not yet live-proven.
- **Slice 3b — FastMCP wrapper gap (caught by the Slice-4 live-smoke)** ✅ **FIXED 2026-06-28.**
  Slice 3 updated the kg arg models + bespoke `definitions.py` schemas (what the *executor* validates) but NOT the **FastMCP tool-function signatures** in `services/knowledge-service/app/mcp/server.py` — which is what FastMCP advertises as `inputSchema` AND validates incoming args against. So FastMCP **stripped `project_id`** before the executor saw it → a public `kg_build_graph` call got "a project must be in scope". Added `project_id: _PROJECT_ID_ARG = None` + the pass-through to all **13 write/build wrappers** (mirroring the read wrappers). **The regression guard already existed** — `test_mcp_inputschema_mirrors_bespoke_openai_schema` in `tests/test_mcp_server.py` — but it lives in `tests/`, not `tests/unit/`, so the Slice-3 verification (which ran `tests/unit/`) missed it. **Lesson: a knowledge tool-schema change MUST run `tests/test_mcp_server.py` (the FastMCP-vs-bespoke drift guard), not just `tests/unit/`.** Now 3/3 green; live-proven below. *(All 3143 unit tests passed WITH the bug present — only the live-smoke + the tests/ guard catch the FastMCP layer.)*

- **Slice 4 — per-provider live-smoke campaign** (`D-PMCP-PRICED-EXPOSURE-FLIP`). **KEY FINDING: there is no code "advertise flip".** Exposure is purely scope-driven (`isToolAllowed` = tier scope + domain scopes); write/priced tools are ALREADY reachable by any key holding those scopes, gated only by the `PUBLIC_MCP_ENABLED` kill-switch. So Slice 4 = proving each provider live with a properly-scoped real key (+ attribution for priced), not flipping a bit. **Results:**
  - ✅ **book (write_auto, free):** minted `[write_auto,domain:book]` key → `book_create` through the edge → real book created, owned by the resolved test user (PUB-1 identity, not spoofable); `[read,domain:book]` key → `book_create` = `-32601 not available` (scope gate real). Cleaned up.
  - ✅ **knowledge (write_confirm, priced):** default `[write_confirm,domain:knowledge]` key → `kg_build_graph` on own project → **diverted to the approval queue** (`pending_human_approval`, no token, no spend — money-safety); cross-tenant project → `project not found` (OD-8 live through the full edge). Approval row verified + cleaned up. **This live-proved Slice 3 + 3b.**
  - ✅ **composition (write_auto, free):** `[write_auto,domain:composition]` key → `composition_create_work` → Work created for the test user through the edge. Cleaned up.
  - ✅ **glossary (paid_read):** `[paid_read,domain:glossary]` key → `glossary_web_search` → **real searxng search** returned actual sources ("Dracula is an 1897 Gothic horror novel by Bram Stoker"); a plain `[read,domain:glossary]` key → `-32601 not available` (**PUB-10**: a cost-incurring tool is unreachable without `paid_read`). Cleaned up.
  - ◐ **translation (write_confirm, priced):** default key → `translation_start_job` → **diverted to approval** (write_confirm divert holds for translation too); self-confirm key → `translation_start_job` → **real cost ESTIMATE + confirm_token** returned (`cost_usd≈0.0038` for Dracula ch1, 7655 input tokens) — the priced propose works end-to-end for a public key. **Self-confirm EXECUTION blocked: `AUTH_CONFIRM_DOMAIN_UNROUTABLE`.**
  - **🔴 Deployment-config gap (`D-PMCP-SELFCONFIRM-ROUTES`):** self-confirm EXECUTION (the headless agent's `confirm_action`→domain-confirm replay) needs auth-service's per-domain `DomainConfirmServiceURLs`, loaded from `*_SERVICE_URL` env (`TRANSLATION_SERVICE_URL=http://translation-service:8087`, `BOOK_SERVICE_URL`, `COMPOSITION_SERVICE_URL`, `GLOSSARY_SERVICE_URL`, `KNOWLEDGE_SERVICE_URL`, `PROVIDER_REGISTRY_SERVICE_URL`). **None are set on the dev auth-service**, so self-confirm execution returns `AUTH_CONFIRM_DOMAIN_UNROUTABLE` for EVERY domain. The DIVERT path (default keys → human approval) is unaffected and proven. Wiring these env vars (a compose change + recreate) unblocks self-confirm execution; the real-spend attribution then completes (the `usage_logs.mcp_key_id` tagging + H-K cap mechanism is independently proven — 11 tagged rows + the prior `D-PMCP-CARRIER-E2E-LIVE-SMOKE`).
  - **Net:** all 5 providers + all 4 tiers proven at the EDGE (scope-gate + relay + divert + cross-tenant + paid_read + cost-estimate). The only unproven leg is self-confirm real-LLM EXECUTION, gated by the `*_SERVICE_URL` deployment config above — not a code defect.
  - **Deploy note:** the dev Docker build serves stale images (build cache + `docker cp` mtime quirk); the working deploy path this session was `docker cp` the changed files → clear `__pycache__` → `docker restart` → restart `ai-gateway` to re-federate.

**Never advertised:** admin, secret-create, `book_delete`/`book_purge`.

---

## 4. Open decisions for the PO (CLARIFY) — my recommended defaults in **bold**

1. **Self-confirm default for public keys** — should new public keys get `allow_self_confirm` (agent is its own second actor), or default to the human-approval queue?
   → **Default to human-approval queue; `allow_self_confirm` strictly opt-in per key.** (Safest; matches OD-2. The queue is built.)
2. **`include_shared` default on list/read tools** — owner-only, or include shared-with-me rows?
   → **Default false (owner-only).** A public key enumerating shared resources is the OD-8 list-leak class; opt-in via explicit arg.
3. **Provider rollout order** — accept book→composition→glossary→translation→knowledge, or front-load a specific provider you care about?
   → **Accept the order above** unless you want a specific provider first.
4. **Scope of v1 priced exposure** — all priced tools, or hold the most expensive (composition_generate, kg_build_graph) for a later wave?
   → **Expose priced per-provider as each live-smoke passes; no artificial hold** — the cap + BYOK + audit make per-call spend bounded and attributable.

---

## 5. Sizing & guardrails

- **Whole track = XL**, but each slice is independently S–M and shippable. Run as a continuous effort (CLAUDE.md budget-driven cadence), checkpoint/commit at each provider's exposure boundary (a genuine risk boundary).
- **Quality gates stay:** VERIFY evidence + 2-stage REVIEW per slice; **/review-impl mandatory on Slice 3** (kg write exposure = canon/money + tenant-isolation surface); per-provider attribution live-smoke is the exposure gate, not optional.
- **No silent caps:** every advertise flip is logged; the edge drift-log records any denied/unknown tool.
