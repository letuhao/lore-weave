# Plan — Public MCP P4 / Wave-C: headless writes + priced jobs open

- **Date:** 2026-06-28
- **Branch:** `feat/public-mcp-gateway`
- **Spec:** `docs/specs/2026-06-26-public-mcp/` — `04-implementation-plan.md §P4`, `03-public-mcp-security-design.md §6.3 / H-J / H-K / H-N`, `05-tool-scope-map.md §2 (write_confirm) / §6 (Wave C)`
- **Phase predecessors:** P0–P3 shipped (edge isolation, credential subsystem, scope filter + OD-8, rate-limit, **PUB-12 BYOK-only**, per-key attribution rails, H-O audit).
- **Size:** **XL** — new external write trust boundary, a new migration-bearing approval surface, cross-service notification leg, FE approval card, and activation of the dormant P3 spend/cap rails. Built as **slices**, each its own `/loom` run + `/review-impl`.
- **AMAW:** the spec marks P4 `/amaw`-mandatory; the human chose **default v2.2 + `/review-impl`** (AMAW is human-initiated only). Each load-bearing slice (spend/write gate) runs `/review-impl` at POST-REVIEW.

---

## 1. Goal (P4 DoD, verbatim from the plan)

> A default key's priced action waits for a human **Approve** before any spend; an `allow_self_confirm` key runs propose→confirm→execute headless bounded by spend cap; a re-price breach is **surfaced, not silently spent**; an agent can **cancel its own job**.

Plus the blocking-order rule (§04 plan): **priced tools must not be exposed to a public key until the carrier (`job_meta.mcp_key_id` SET in production) + the per-key cap (H-K) are live** — until then the edge advertises non-cost tools only. So the carrier+cap slice (**D**) is the gate that actually *opens* any priced tool, and **A** (the human-approval spine) is the gate that opens any write at all.

---

## 2. What already exists (build on, do not rebuild)

| Capability | Where | Reuse for |
|---|---|---|
| `confirm_token` propose→execute split (server-minted, user+payload+expiry, single-use, re-priced) | internal MCP tools (glossary/translation/kg/composition) | A, B, C — the token *is* the gate primitive; P4 only adds the **second actor** (human queue / `confirm_action`) |
| FE confirm-card renderer | `frontend/src/features/chat/components/ConfirmCard.tsx`, `ConfirmActionCard.tsx`, `actionsApi.ts` | A — the approval card reuses this renderer (preview + estimate + Approve/Deny) |
| Event→notification pipeline | provider-registry publishes `TerminalEvent` → `loreweave.events` (topic) → `notification-service` consumer binds `user.*.llm.#` → `notifications` row → FE stream | A — add a new binding (`user.*.mcp.approval`) or a new event category for the approval notification |
| Spend guardrail reserve/reconcile/release | `services/provider-registry-service/internal/billing/client.go` (`Reserve`/`Reconcile`/`Release`), usage-billing `/internal/billing/guardrail/*` | D — H-K per-key sub-cap extends the reserve (or a Redis edge reserve keyed by `key_id`) |
| **Dormant** per-key carrier | `job_meta.mcp_key_id` parsed in `FinalizeWithUsageOutbox`; `usage_outbox.mcp_key_id` → relay → `usage_logs.mcp_key_id`; `X-Mcp-Key-Id` header on sync paths; PUB-12 gate at all 3 spend entry points | D — production **SET** of the carrier for priced tools activates the whole attribution+cap rail (currently only ever set by direct test injection) |
| Edge controller + scope filter | `services/mcp-public-gateway/src/mcp/public-mcp.controller.ts`, `src/scope/scope-filter.ts`, `src/audit/audit-client.ts` | B, C, E — `confirm_action` exposure, re-price interception, `jobs_cancel/pause` advertise; audit already fires per call |
| Per-key fields on the credential | `mcp_api_keys.allow_self_confirm`, `.spend_cap_usd`, `.scopes[]` (incl. `write_confirm`) | A/B/D — already minted + carried through `/internal/mcp-keys/resolve`; P4 reads them at the gate |

**Key insight:** P1–P3 deliberately built the *carriers, flags, and primitives* dormant. P4 is mostly **activation + the human leg**, not green-field. The two genuinely new surfaces are `mcp_pending_approvals` (A) and the `confirm_action` edge exposure (B).

---

## 3. Slice DAG (dependency order)

```
            ┌──────────────────────────────┐
            │ D — carrier SET + H-K cap     │  (gates exposure of ANY priced tool)
            │   job_meta.mcp_key_id in prod │
            │   + per-key atomic reserve     │
            │   + web_search BYOK (sync)     │
            └───────────────┬───────────────┘
                            │ (priced tools may now be advertised)
   ┌────────────────────────┴───────────────────────────┐
   │ A — OD-2 human-approval spine                        │  (gates ANY write_confirm)
   │   mcp_pending_approvals + notification + FE card      │
   └───┬─────────────────────────────────┬───────────────┘
       │                                  │
┌──────┴────────┐              ┌──────────┴───────────┐
│ B — self-confirm│              │ C — H-J re-price-on  │
│   confirm_action│              │   -execute (price_   │
│   opt-in path   │              │   changed + token)   │
└─────────────────┘              └──────────────────────┘
   (independent of A's queue;        (independent; needs the
    needs the token primitive)        confirm path B or the
                                       queue-approve path A)

  E — H-N jobs_cancel/jobs_pause (Tier-A)   ← independent, no dep on A/D
  F — H17 partial-failure honesty           ← independent, edge-only polish
```

- **A and D are both gates** but along different axes: **A** = "no write reaches canon/money without a human (or self-confirm flag)"; **D** = "no priced tool is even advertised until the cost lands attributed + capped." Either can go first; **D** is the harder/riskier (provider-registry + migration), **A** is the bigger surface (migration + FE + notification). Recommend **D first** (it unblocks advertising and is the money-safety floor), then **A**.
- **E and F are independent** and small — good warm-up / interleave slices.
- **B depends on A** only in that self-confirm is the *opt-in alternative* to the queue; mechanically B needs only the token + `confirm_action` exposure, so it can land right after the token plumbing is confirmed.
- **C (H-J)** needs a confirm execution path to intercept — so it lands after B (self-confirm) or wires into A's approve-execute.

---

## 4. Per-slice design

### Slice D — carrier activation + H-K per-key cap + web_search BYOK  *(money-safety floor, do FIRST)*

**Why first:** the blocking-order rule forbids advertising any priced tool until the cost is attributed (carrier SET) and capped (H-K). P3 built these rails dormant; D turns them on.

**D1 — production SET of `job_meta.mcp_key_id` (`D-PMCP-KEYID-JOBMETA-WIRING`).**
- Today `mcp_key_id` is only ever in `job_meta` via direct test injection. The live path: edge relays `X-Mcp-Key-Id` → `ai-gateway` forwards it (additive, already done in the kit pre-step) → shared kit lifts to ctx → **provider-registry submit chokepoint merges it into `job_meta`** (mirror exactly how `campaign_id` is merged via the per-task contextvar at `submit_and_wait`). Verify the merge happens for the **async jobs** path (the sync stream/proxy paths already carry the header live).
- Files: `sdks/{go,python}/loreweave_mcp` (ctx lift — confirm done), `provider-registry submit` merge site (the `campaign_id` contextvar chokepoint), edge relay header (already set).
- **Live-smoke (the proof):** run a real priced tool (`translation_start_job` or `kg_build_graph`) through the edge with a real key → assert the cost lands in `usage_logs.mcp_key_id` tagged with that key (not via injection). This is the H-C DoD ("run `translation_start_job` via a key, see the cost land tagged").

**D2 — H-K per-key spend sub-cap (atomic reserve).**
- `mcp_api_keys.spend_cap_usd` is the per-key ceiling. Two concurrent priced calls can both pass a naive pre-check → overshoot. Patch (spec §H-K): **atomic reserve keyed by `key_id`** — either (a) extend the usage-billing guardrail `Reserve` to also hold against a `key_id` ceiling in the same txn, or (b) an **edge-side Redis reserve** (`INCRBY` the key's running reserve, check ≤ cap, reject 402 on breach), reconciled/released at job terminal. Accept bounded overshoot ≤ in-flight concurrency.
- **Decision to make in the slice's CLARIFY:** (a) usage-billing reserve extension (authoritative, durable, but couples to the billing txn) vs (b) edge Redis reserve (fast, edge-local, but needs its own reconcile/release leg at terminal). Spec offers both; **lean (b)** for edge-locality + because the edge already owns the rate-limit Redis — but (a) reuses the proven reserve/reconcile/release lifecycle. Resolve at CLARIFY.
- **Release site (lesson `p5-wfq-fairness-substrate-and-release-site`):** the decoupled reserve **must** be released at the per-unit terminal carried by a deterministic token (the `job_id`/`mcp_key_id` pair on the terminal event), or a crashed job leaks the reserve forever. Wire release into the same terminal path that reconciles usage.
- **Test:** the `D-PMCP-SUBCAP-RESERVE-LEAK-TEST` (LOW, already tracked) — prove a failed/cancelled priced job releases the per-key reserve.

**D3 — `glossary_web_search` BYOK (`D-PMCP-WEBSEARCH-BYOK`).**
- `glossary_web_search` is a **synchronous** `/internal/web-search` chokepoint (Go), not the async job path — so PUB-12 (BYOK-only) must be enforced *there* too, the same as the 3 provider-registry spend entry points. Resolve the would-be model; reject 402 if it maps to a platform model. This is the `paid_read` Wave-B tool; it cannot open until its BYOK gate lands.

**DoD (D):** a priced tool run through a real key lands cost in `usage_logs.mcp_key_id` (live smoke); two concurrent calls cannot exceed `spend_cap_usd` (bounded overshoot only); a cancelled priced job releases its reserve; `glossary_web_search` rejects 402 on a platform model.

---

### Slice A — OD-2 human-approval spine  *(write gate; do SECOND)*

**A1 — `mcp_pending_approvals` table (auth-service migration).** Owner of the credential subsystem is auth-service, so the approval surface lives there.
- Columns (draft): `approval_id` (uuidv7 PK), `key_id` UUID NOT NULL, `owner_user_id` UUID FK→users CASCADE, `tool_name` text, `confirm_token` text (the server-minted token to execute on approve — store hashed? it's single-use + expiry-bound + user-bound; store as-is for replay-to-execute, or store a reference and re-fetch), `preview` jsonb (the propose result shown to the human), `cost_estimate_usd` numeric NULL, `status` text CHECK (`pending`/`approved`/`denied`/`expired`/`executed`), `expires_at` timestamptz (mirror the token TTL), `created_at`, `decided_at` NULL. Index `(owner_user_id, status, created_at DESC)`.
- **Tenancy (CLAUDE.md User Boundaries):** every row scoped by `owner_user_id` + `key_id`; owner reads/decides only their own (WHERE owner_user_id = caller). Same anti-oracle posture as revoke/audit (not-yours ≡ not-found).

**A2 — edge routes a Tier-W propose to the queue (default path).**
- When a `write_confirm`-scoped key (with `allow_self_confirm = false`) calls a Tier-W tool, the provider returns `{preview, cost_estimate, _meta:{confirm_token}}` **without spending**. The edge intercepts: instead of returning the raw token to the agent, it **POSTs the approval row to auth-service** (`POST /internal/mcp-keys/approvals` — internal-token) and returns to the agent `{status: "pending_human_approval", approval_id}`. The agent must not self-confirm (it doesn't get the token).
- The edge must recognize a "propose result" — detect `_meta.confirm_token` in the relayed response and divert. Pure function, unit-testable like `buildAuditRows`.

**A3 — notification leg.** On approval-row insert, the owner gets a notification. Reuse the event pipeline: auth (or the edge) publishes a `user.<id>.mcp.approval` event (or a direct notification-service ingest) → `notifications` row → existing FE stream. Add the binding/category to `notification-service/internal/consumer`.

**A4 — owner read + decide endpoints (auth-service, JWT, owner-scoped).**
- `GET /v1/account/mcp-keys/approvals?status=pending` — list the owner's pending approvals (preview + estimate + which key).
- `POST /v1/account/mcp-keys/approvals/{approval_id}/approve` — execute the action (replay the `confirm_token` to the owning service's confirm endpoint via the edge/internal path), mark `executed`. **This is where the spend actually happens** — so the carrier (D1) must already tag it.
- `POST /v1/account/mcp-keys/approvals/{approval_id}/deny` — drop the token, mark `denied`.
- Token replay safety (spec S8): token is user+payload+expiry-bound, single-use; a mismatched key/user → reject.

**A5 — FE approval card.** Settings (or a notification action) surfaces pending approvals; reuse `ConfirmActionCard` renderer (preview + estimate + key name + Approve/Deny). i18n ×4.

**DoD (A):** a default key's Tier-W call returns `pending_human_approval` + an approval id, fires a notification, appears in the owner's FE card; Approve executes (spend lands, attributed to the key); Deny drops it; a cross-owner read returns nothing.

---

### Slice B — `allow_self_confirm` + `confirm_action` server tool  *(opt-in headless; after A)*

- For keys with `allow_self_confirm = true`, the edge advertises a generic **`confirm_action(confirm_token)`** tool (the FE `glossary_confirm_action` generalized + exposed through the edge). The agent calls the Tier-W tool (gets token + estimate), then calls `confirm_action(token)` to execute — the agent itself is the second actor, bounded by `write_confirm` scope + spend sub-cap (D2) + audit.
- The edge gates: `confirm_action` is only advertised/accepted when the resolved key holds **both** `write_confirm` and `allow_self_confirm`. A key without the flag calling `confirm_action` → denied_scope (audited).
- Same token, different second actor (vs A's human). No new table — the token already exists.

**DoD (B):** a `write_confirm` + `allow_self_confirm` key runs propose→`confirm_action`→execute headless, spend bounded by cap + attributed; a key missing the flag is denied; the call is audited.

---

### Slice C — H-J re-price-on-execute  *(no silent overspend; after B/A)*

- A confirm token re-prices at execute. If `actual > estimate × 1.25`, the execute path must **not** silently spend over the breach (default behavior would). Patch: `confirm_action` (and the A-approve execute) returns a **structured `price_changed` result with the new estimate + a fresh token** — the agent (or human) re-confirms explicitly.
- Implement at the edge re-price interception point (re-estimate before relaying the confirm) **or** surface a provider-side `price_changed` structured error and translate it at the edge. Lean on the provider's existing re-price (FE internal H14 already re-confirms a changed price via a new card) — expose that same structured result headlessly.

**DoD (C):** a priced confirm whose actual exceeds estimate×1.25 returns `price_changed` + a fresh token instead of spending; the agent can re-confirm at the new price; under threshold it executes normally.

---

### Slice E — H-N agent self-cancel (`jobs_cancel` / `jobs_pause`)  *(independent, small)*

- Today `jobs_*` over MCP is read-only; `job_control` (cancel/pause) is REST/FE-only → a public agent can start a priced job but can't stop a runaway. Add `jobs_cancel`/`jobs_pause` as **Tier-A** (free, reversible) MCP tools on the jobs domain, behind the `jobs` scope, so an agent aborts its own spend. Scope-filter advertises them for `jobs`-scoped keys; owner/ownership-scoped to the agent's own jobs (a key can only cancel jobs it/its-owner launched).
- Files: jobs-service MCP tool registration; edge scope-map entry; `05-tool-scope-map.md` already lists these under `write_auto`/jobs.

**DoD (E):** an agent that started a job can cancel/pause it via MCP; cannot touch another owner's job.

---

### Slice F — H17 multi-step partial-failure honesty  *(independent, edge polish)*

- A multi-step agent action that partially lands must report **what actually landed** (not "success" or an opaque failure). Edge-level: when a relayed multi-step/batch call returns partial results, surface a structured per-step outcome so the agent reports honestly. Smallest slice; good closer.

**DoD (F):** a partially-failed multi-step call returns per-step outcomes; the agent can report what landed.

---

## 4b. Build-ready resolutions (fan-out 2026-06-28)

Six read-only investigation agents pinned exact files/lines and resolved the open questions. Key findings + corrections below.

### D — carrier + H-K cap + web_search BYOK  *(RE-DESIGNED 2026-06-28 after CLARIFY investigation — was M, now XL; all priced providers in scope)*

**Carrier correction (supersedes the fan-out's D1).** The fan-out said provider-registry lifts `X-Mcp-Key-Id` from the request header. **Wrong for the priced-tool path:** public priced tools are MCP tools on *domain services* (`edge → ai-gateway → domain-service → provider-registry`), and the header **dies** on the domain-service→provider-registry hop — `loreweave_llm.submit_job` builds a fresh typed request, it does not forward ambient headers. The proven mechanism is the `campaign_id` **contextvar→`job_meta` bridge** at the submit chokepoint ([translation llm_client.py:101-103](services/translation-service/app/llm_client.py#L101-L103)). So the **carrier is `job_meta`**, and both `mcp_key_id` *and* `spend_cap_usd` ride it.

- **D-foundation (universal):**
  - **Shared `loreweave_llm` SDK** ([client.py:325 submit_job](sdks/python/loreweave_llm/client.py#L325)): add `_mcp_key_id_ctx` + `_spend_cap_ctx` contextvars + `set_public_key_attribution(key_id, cap)`; in `submit_job`, merge both into `job_meta` (server-set → **overwrite**, unlike campaign_id's "caller wins"). `mcp_key_id` is cross-cutting (any public call) so the bridge lives in the **shared** SDK, not per-service (where `campaign_id` lives because campaigns are translation-specific).
  - **`loreweave_mcp` kit:** lift `x-mcp-spend-cap-usd` → `ToolContext.spend_cap_usd` (py [context.py:121](sdks/python/loreweave_mcp/context.py#L121) + go identity.go); and in `build_tool_context`, **soft-call** `loreweave_llm.set_public_key_attribution(mcp_key_id, spend_cap)` (try-import; no hard dep) so EVERY tool call sets/clears the contextvar automatically — the universal hook that makes "all providers" work without per-tool wiring. A first-party call (no key) sets `None` → no cap, no attribution, no leak.
  - **provider-registry preflight** ([jobs_handler.go:402](services/provider-registry-service/internal/api/jobs_handler.go#L402)): read `mcp_key_id` + `spend_cap_usd` from `in.JobMeta`, pass to `Reserve`. The async worker already reads `mcp_key_id` back at finalize via `ParseJobMetaMcpKeyID` → usage_logs (P3 rail).
  - **usage-billing** ([guardrail.go:93 reserve](services/usage-billing-service/internal/api/guardrail.go#L93)): add `mcp_key_id` column to `token_reservations` (migration); when `mcp_key_id`+`cap` present, after the **existing owner-row `FOR UPDATE` lock** (which serializes ALL that owner's reserves → race-safe for free), compute per-key total = `SUM(usage_logs.cost WHERE mcp_key_id, monthly window)` + `SUM(token_reservations.estimated_usd WHERE mcp_key_id AND status='held')`; if `+estimate > cap` → 402 `MCP_KEY_CAP_EXCEEDED`. Reconcile/release already flip reservation status → held-sum decrements naturally (**no new release leg**). Cap window = **monthly** (matches the existing guardrail window + the H-C rollup).
  - **edge** ([public-mcp.controller.ts:91](services/mcp-public-gateway/src/mcp/public-mcp.controller.ts#L91)): forward `x-mcp-spend-cap-usd` (when non-null) next to `x-mcp-key-id`; **ai-gateway** must forward it too (additive, mirror `x-mcp-key-id`).
- **D-providers (all, this slice):** the universal hook covers every Python service that submits via `loreweave_llm.submit_job` — verify each priced provider (translation, knowledge, composition, lore-enrichment, glossary plan/deep_research) actually routes through it (not a raw submit), and live-smoke where feasible.
- **D3 web_search BYOK — DEFERRED** (`D-PMCP-WEBSEARCH-BYOK`): sync `/internal/web-search`, no `job_meta`; the key header is gone by glossary's internal call. One `paid_read` tool, kept off the public surface until its own gate lands — doesn't block the carrier/cap slice.

### A — OD-2 approval spine
- New table in [auth migrate.go](services/auth-service/internal/migrate/migrate.go) mirroring `mcp_call_audit`; new [mcp_approvals.go](services/auth-service/internal/api) mirroring `mcp_audit.go` (4 handlers). Edge: new `approval-client.ts` (fire-and-forget like `audit-client.ts`) + a **pure propose-detector** (`_meta.confirm_token` present) in the controller, returning `{status:'pending_human_approval', approval_id}` to the agent.
- **Token storage — RESOLVED: store plaintext.** The token is already single-use (provider jti ledger) + expiry-bound + user-scoped; hashing would force a re-mint round-trip. Set the row's `expires_at` from the token's own `exp`. FE reuses `ConfirmActionCard`; poll (not SSE) — approvals are rare. Notification via a new `user.*.mcp.approval` binding on `loreweave.events`.
- **Critical wiring:** the approve-execute path must put `X-Mcp-Key-Id = key_id` on the replayed confirm so cost attributes to the **agent's key, not the human's session** → hard dep on **D1**.

### B — confirm_action (self-confirm)
- **KEY FINDING: `confirm_action` is a generic gateway tool, not per-provider.** The confirm token carries a `descriptor` (domain); ai-gateway decodes it (kit `verify_confirm_token` is domain-agnostic) and routes to `/v1/<domain>/actions/confirm`. The edge **relays it like any tool** — no new edge REST path. **`confirm_action` itself is $0** — spend was already reserved at the propose step; confirm just executes. Dual-flag gate (`write_confirm` **AND** `allow_self_confirm`) in `scope-filter.ts` (special-case, anti-oracle deny). Dep: A + D.

### C — H-J re-price
- **KEY FINDING: already built on the BE.** translation-service ships the H14 gate: `reprice_exceeds_threshold` (×1.25 + $0.50 abs, [estimate.py:226-257](services/translation-service/app/mcp/estimate.py#L226-L257)) → `_reprice_refusal` returns **409 `TRANSL_REPRICE_REQUIRED`** with a fresh estimate ([actions.py:425-442](services/translation-service/app/routers/actions.py#L425-L442)). **RESOLVED: relay the 409 transparently** — no edge interception. The FE confirm card ([ConfirmActionCard.tsx:160-176](frontend/src/features/chat/components/ConfirmActionCard.tsx#L160-L176)) currently treats 409 as a generic error → change it to detect `reprice_required`, re-render with the new estimate + fresh token, allow re-confirm. Headless agents get the 409 as a JSON-RPC error with `detail.status='reprice_required'`.
- **NEW RISK → `D-TRANSL-REPRICE-THRESHOLD-DRIFT`:** verify the FE has no divergent hardcoded threshold; BE constant is `1.25`/`$0.50`. C mostly = a FE change + a contract doc for future priced providers (glossary/composition/kg confirm handlers must emit the same 409 shape).

### E — jobs_cancel / jobs_pause  *(INDEPENDENT — no deps)*
- `control.forward_control()` already exists and is owner-scoped. Add two Tier-A tools in [jobs-service mcp/server.py](services/jobs-service/app/mcp/server.py) after the read tools (~:219) + `tool-policy.ts` entries `{tier:'write_auto', domains:['jobs']}`. Reversible + free → Tier-A, no confirm. **Risk:** `forward_control` 501s if the owning service lacks a control endpoint; the owning service must M4-re-verify ownership (anti-oracle 404 on a non-owned job). Can ship **anytime, in parallel**.

### F — H17 partial-failure  *(INDEPENDENT — edge-only)*
- Pure helpers `parseRequestSteps` + `buildStepOutcomes` in `scope-filter.ts`; inject a `step_outcomes` wrapper **only for batch requests** (`Array.isArray(body)`), single requests unchanged (backward-compat). Build the outcome map **as the edge gates** (it's the source of truth), don't parse the opaque upstream response. Batch-level rate-limit/upstream-fail stays a single error (no per-step). Smallest slice.

## 5. Recommended build order & milestones

1. **D** (carrier SET + H-K cap + web_search BYOK) — money-safety floor; live-smoke the attribution. *Most load-bearing → `/review-impl`.* Unblocks advertising priced tools.
2. **A** (OD-2 approval spine) — migration + notification + FE. *Load-bearing → `/review-impl`.* Unblocks all `write_confirm`.
3. **B** (`confirm_action` + `allow_self_confirm`) — opt-in headless path. *`/review-impl` (scope gate).*
4. **C** (H-J re-price) — overspend safety on the execute path.
5. **E** (H-N self-cancel) — small, independent; can interleave anytime.
6. **F** (H17 partial-failure) — closer.

Each is one `/loom` slice (size S–M individually; the *whole* P4 effort is XL). Priced tools are advertised per-provider only **after D's live-smoke passes for that provider** (the staged Wave-C exposure, §05 ¶105).

---

## 6. Open decisions — RESOLVED by the fan-out (2026-06-28)

- **H-K reserve substrate (D2):** ✅ **usage-billing reserve extension** (NOT edge-Redis — corrected at CLARIFY 2026-06-28). The edge has no cost estimate; the estimate + reserve/reconcile/release lifecycle live at provider-registry→usage-billing. Per-key cap rides `job_meta`, checked inside the existing reserve tx (race-safe via the owner-row lock), released for free by the existing reconcile/release. See §4b-D.
- **`confirm_token` storage (A1):** ✅ **store plaintext**, row `expires_at` = token `exp`. Token is already single-use (jti) + expiry + user-bound, so at-rest exposure is bounded and a re-mint round-trip is avoided.
- **Approval-execute spend attribution (A4):** ✅ approve handler puts `X-Mcp-Key-Id = key_id` (from the approval row) on the replayed confirm → cost attributes to the agent's key, not the human session. **Hard dep on D1.**
- **`price_changed` threshold (C):** ✅ BE owns it (`1.25` + `$0.50` abs); relay the 409 transparently. **New action:** verify the FE has no divergent constant → `D-TRANSL-REPRICE-THRESHOLD-DRIFT` if it does.
- **`confirm_action` routing (B):** ✅ generic gateway tool — token `descriptor` carries the domain; ai-gateway decodes + routes to `/v1/<domain>/actions/confirm`; edge relays like any tool. No new edge REST path.

---

## 7. Deferred rows carried into P4 (from P3)

| ID | Severity | Lands in slice |
|---|---|---|
| `D-PMCP-KEYID-JOBMETA-WIRING` | — | **D1** |
| `D-PMCP-WEBSEARCH-BYOK` | — | **D3** |
| `H-K` (per-key spend sub-cap) | 🟡 | **D2** |
| `D-PMCP-SUBCAP-RESERVE-LEAK-TEST` | LOW | **D2** (test) |
| `D-PMCP-AUDIT-DOWNSTREAM-OUTCOME` | MED | folds into A/B — the approve/confirm execute path can record the *true* tool verdict (the edge `relayed` audit doesn't see it) |
| `D-TRANSL-REPRICE-THRESHOLD-DRIFT` | LOW (NEW) | **C** — verify FE has no hardcoded re-price threshold diverging from BE `1.25`/`$0.50` |
| `D-PMCP-CARRIER-E2E-LIVE-SMOKE` | MED (NEW, from /review-impl) | **B** — priced tools spend at the confirm-route effect (slice B), so the full edge→…→usage_logs.mcp_key_id attribution can only be live-smoked once `confirm_action` exists. Slice-D rail + cap are unit+real-PG verified; e2e is gated on B. |
| `D-PMCP-WORKER-CARRIER` | MED (NEW, from /review-impl) | **B**, per priced tool at exposure — the contextvar carrier only survives an IN-PROCESS submit. Confirm-route effects that enqueue to a background worker (translation chapter-worker, worker-ai extraction) lose it at the process boundary; `mcp_key_id` must ride the enqueued job row + the worker re-set it (mirror how `campaign_id` reaches the worker). In-process confirm effects (composition worker-off path) are covered by the universal hook. |

---

## 8. Out of scope (P5+)

OAuth 2.1 + discovery (P5); signed webhook completion (OD-3); import/upload MCP path; anomaly alerting on key audit; partner org/team RBAC (P6+). Priced-tool **per-provider** fanout exposure happens incrementally as each provider's attribution live-smoke passes — tracked, not a single big-bang flip.
