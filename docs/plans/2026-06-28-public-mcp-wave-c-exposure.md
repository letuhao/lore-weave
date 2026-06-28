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
- **Slice 4 — staged advertise flip, provider-by-provider** (`D-PMCP-PRICED-EXPOSURE-FLIP`).
  Flip the edge `tool-policy`/`scope-filter` advertise bit per provider, gated on §2's per-provider DoD + a passing attribution live-smoke for that provider. Order: **book → composition → glossary → translation → knowledge** (read-heavy/cheapest first; priced LLM tools last). Each provider is its own commit + live-smoke.

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
