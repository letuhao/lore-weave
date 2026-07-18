# Track D brief — Tool Liveness & Metadata Correctness

**One-liner:** make every MCP tool *declare what it is* and *prove it works when an LLM calls it* —
then make that proof a precondition for shipping workflows.

- **Read first:** [`README.md`](README.md) (the measured gap + phasing) · [`contracts.md`](contracts.md)
  (CD1–CD4 — Track D **owns** all four).
- **Why it's a track, not a chore:** Tracks A/B/C built the machinery to *find*, *load*, and
  *sequence* tools. None of them proved the tools **work** when an LLM drives them. The flagship S06
  baseline recorded **`effectful_tool_calls: 0`** while the agent claimed *"I have locked that into
  the core of the project."* Shipping curated workflows on unproven tools ships that lie at scale.

---

## Owns (services · files)

| Area | Files |
|---|---|
| Kit (`_meta`) | `sdks/go/loreweave_mcp/meta.go` (`WithPaid`), `sdks/python/loreweave_mcp/meta.py` (`paid=`) |
| glossary-service (Go) | `internal/api/mcp_server.go`, `*_tool.go`, `RegisterBookTools` — `_meta` adoption |
| composition · lore-enrichment (Py) | `app/mcp/server.py` — `async`/`paid`/tier corrections |
| Every domain service | a `tools/list` meta gate test (pattern: `knowledge-service/tests/test_mcp_server.py`) |
| mcp-public-gateway (TS) | `src/scope/tool-policy.ts` — derive `paid_read` from `_meta.paid` |
| Harness | `scripts/eval/tool_liveness/**` (new) |
| Reports | `docs/eval/tool-liveness/<date>/{matrix.json,matrix.md,transcript.jsonl}` |
| **Coordinated (Track A owns)** | `agent-registry .../workflows.go` `validateWorkflow` — the CD4 ship gate |

---

## Deliver in order

### WS-D0 · Metadata correctness + the spend gate — **first** *(size L)*
> Must land before any glossary probe runs, or every probe tests the wrong gating.
> **Ordering is load-bearing:** the spend gate precedes any paid tool reaching the hot path.

- **D0a — `_meta.paid`** (CD1): kit field in Go + Py (`WithPaid` / `paid=True`); mark the ~25
  money-spending tools.
- **D0b — the internal SPEND GATE** *(new prerequisite; nothing like it exists)*. Verified: nothing in
  the chat tool-loop reads a spend concept, and `mcp-public-gateway` marks its own gate *"P3/pending"*.
  A `paid` tool must require approval-on-first-use and count against a spend budget — **independent of
  `tier`** (CD1: `paid ⊥ tier`; a paid *read* stays a read and remains allowed in `ask` mode).
  Then derive `mcp-public-gateway`'s `paid_read` from `tier == R ∧ paid == true` instead of restating it.
- **D0c — glossary `_meta` adoption**: assign `tier` + `scope` to all `/mcp` + `/mcp/admin` tools,
  calibrating exactly as knowledge did (reversible→`A`, destructive/`confirm_token`→`W`,
  read/derive→`R`). ≥27 of 35 scanned carry none.
- **D0d — async audit** *(do not trust the inventory)*: for each of `composition_motif_mine`,
  `composition_arc_import_analyze`, `composition_conformance_run`, `plan_propose_spec(mode=llm)` —
  **read the handler**, confirm it enqueues, and only then mark `async`.
- **D0e — `lore_enrichment_auto_enrich` tier** *(RESOLVED 2026-07-10: stays `A`, not `W`)*: on
  reading the handler it mints **no `confirm_token`, so it cannot satisfy the Tier-W contract
  (the consumer awaits a token that is never sent). Its docstring records `A` as deliberate: the job
  only emits **quarantined** proposals (never a canon write) and is **cost-bounded**
  (`max_spend_tokens` + per-job cap). It is already `async_job=True`. Its spend runs on the **job
  path**, which already reserves — so it is **not** marked `_meta.paid` (that flag gates the *sync*
  path; marking it would double-gate an already-reserved job — Layer-2 territory, out of WS-D0). The
  `mcp-public-gateway`'s `write_confirm` reclassification is the **public edge's** own stricter
  policy and is orthogonal to the internal tier — no internal change needed to keep it.
- **D0f — universalize `web_search`** (CD5 + the C1 change). Decided 2026-07-09:
  1. **Mint C1 category `research`** — 3 lockstep declarations (`find-tools.ts GROUP_DIRECTORY`,
     `tool_discovery.py GROUP_DIRECTORY`, `tool-policy.ts Domain`) + `_DOMAIN_ALIASES: web → research`
     on both engines. Guarded by `find-tools.spec.ts`'s drift-lock. *(C1 is Track A's frozen contract —
     the change is recorded in its change log and announced on the board.)*
  2. **Move the tool to provider-registry-service**, which owns the capability
     (`POST /internal/web-search`, provider-gateway invariant) and already serves MCP tools
     (`settings_*`). Carry over the INV-6 neutralization + its tests.
  3. **Rename** `glossary_web_search` → **`web_search`**; retain the old name as a
     `visibility: legacy` alias (never delete). `_meta`: `tier R`, `scope none`, `paid true`.
  4. **Delete `composition-service/app/clients/web_search_client.py`** — it hand-rolls a second client
     and *mirrors this tool's safety caps* (drift risk). Composition calls the tool.
  5. **`glossary_deep_research` KEEPS its prefix** — verified NOT universal (requires `book_id` +
     `entity_id`; attaches draft evidence to one entity). Only its missing `_meta` is a defect.
  6. **After D0b lands:** add `web_search` to `ALWAYS_ON_CORE_NAMES`. ⚠️ This consumes the **last free
     slot (9 → 10 of 10)**; the `<= 10` assertion in `test_tool_discovery.py:645` then pins the cap —
     any further core tool requires an explicit decision to raise it.
- **D0g — per-service wire gates** (CD1 enforcement) for every domain service.

**Exit:** zero tools with absent `tier`/`scope`; every `paid` tool declares it **and** passes the spend
gate; `web_search` is universal, categorized, and hot-path; each service has a `tools/list` gate. → **ND1**

### WS-D1 · `propose_*` semantics (CD2) — ✅ **SHIPPED 2026-07-10** *(size S)*
Declare each `propose_*` tool's pattern (token vs draft) in its description; add the
`propose ⇒ tier ∈ {A,W}` lint. **Audit `glossary_propose_aliases`**. No renames: the
"propose = direct write" finding was **verified false** (see `contracts.md` → Rejected findings).

**Outcome.** Wire lints on **three** services (glossary Go · knowledge Py · composition Py) cover
**19** `propose_*` tools — 15 federated + **4 `glossary_admin_propose_*`** that never appear in the
gateway catalog (the admin server isn't federated) and so were invisible to the tool audit.

- **Rule 1 (`tier ∈ {A,W}`) already held** — Wave 1's `_meta` adoption tiered every `propose_*`.
  The lint is now the regression gate that keeps it true.
- **Rule 4 (description declares the pattern) had exactly one real violation:**
  `plan_propose_spec` declared neither. It writes `status='proposed'` (draft pattern) — fixed.
- The checks are **tier-directed**, and that is load-bearing. A naive substring scan false-positives:
  `glossary_propose_status_change` is Tier **W** yet contains the word "draft" — as a *status value*
  (`active|inactive|draft|rejected`), not a pattern declaration. Only "a W tool must carry a confirm
  marker" / "an A tool must carry a draft marker **and must not claim a `confirm_token`**" is sound.
- **The A-branch's no-`confirm_token` rule caught its author.** The first draft of
  `plan_propose_spec`'s new description said "…(CD2 draft pattern, no `confirm_token`)" and the lint
  reddened. That is correct behavior, not a false positive: models handle negation poorly, so naming
  a token that is never minted invites the exact confusion the rule exists to prevent. Prose fixed.
- Each lint ships a **negative control** (`…LintIsNotVacuous` / `…marker_predicate_discriminates`)
  proving the predicate rejects non-declaring prose, accepts real declarations, and never lets the
  `draft` status value satisfy a Tier-W confirm requirement.

**Audit result — `glossary_propose_aliases` is draft-only, confirmed at the SQL:** its
`entity_attribute_values` insert creates an empty `'[]'` scaffold under
`ON CONFLICT DO UPDATE SET original_value = entity_attribute_values.original_value` — a
self-assignment no-op that only RETURNs the existing row id, so it cannot alter existing content;
and `upsertDraftTranslation` writes `confidence='draft', translator='assistant'` guarded by
`ON CONFLICT … WHERE confidence <> 'verified'`, so it can **never** overwrite a verified rendering.
Tier A is correct. (Rules 2/3 — "no canonical mutation at call time" — are not decidable from the
wire and remain per-handler audits.)

### WS-D2 · TLE harness P0 *(size L)*
Build the six components (`README.md` §5). Reuse the SSE driver + tool-record parser; **build** the
three that don't exist:
1. **Confirm resolver** — the single biggest gap: no NL harness in the repo posts to
   `/v1/<domain>/actions/confirm`. Without it all 37 Tier-W tools suspend and never execute.
2. **Fixture factory** — throwaway book + project + chapter, torn down after. The safety boundary:
   *no probe may touch an id it did not create.*
3. **Effect oracle** + async poller + matrix reporter.

Auth through the real `/v1/auth/login` edge. Agent model = local gemma (**$0**). Pre-allowlist
`user_tool_approvals` so Tier-A writes don't stall — and add one test asserting the card *does*
appear when not allowlisted.

**Exit:** 10 tools spanning R/A/W/async, all four gates, ≥1 genuine bug found. → **ND2**

### WS-D3 · TLE P1 — the workflow-critical set + ship gate *(size M)*
**The gate itself is SHIPPED 2026-07-10.** Probing the full workflow-critical set remains
(that is the P1 grind, and it is what actually populates the manifest).

- `contracts/tool-liveness.json` is **generated** by `scripts/eval/tool_liveness/manifest.py`
  (CD4: never hand-maintained), together with two byte-identical service copies — `go:embed` and
  Python package data cannot climb out of their modules. A **drift lock** in each service reds if a
  copy diverges, and it *fails*, never skips.
- **`validateWorkflow` (agent-registry Go):** rejects a step whose tool is **proven broken**
  (`executes: false`); emits a sorted, deduped `unproven_tool` **warning** otherwise. The
  `proposeWorkflowOut.warnings` field is omitted when clean, so a proven set sees no shape change.
- **`tool_list` / `tool_load` (chat-service Python):** a proven-broken tool is withdrawn.
  `tool_load` reports it under `unavailable` + `unavailable_reason` — never a silent drop, and
  never `not_found` (which would send the model hunting for a name that exists).
- **The manifest carries derived `executes` / `proven` fields** so the Go gate and the Python filter
  never re-implement the verdict logic in two languages.
- **`executes` is three-valued and that is the point.** `null` = never checked. Reading it as
  `false` would reject/hide the ~200 tools with no probe yet; reading it as `true` would ship a
  broken tool. Both consumers test for an **explicit** `false`. See the amended CD4 phasing table.
- **Today the gate is provably inert:** 0 tools blocked, 5 warned. It cannot false-block, because
  the current matrix predates the capability field so every RED is honestly `null`.

Remaining for WS-D3: probe every tool an authored C3 workflow can reference, so the manifest stops
being 10 rows. → **ND3**
**Exit:** the ship gate is real. → **ND3** *(this is the actual "before we ship workflow" gate)*

### WS-D4 · TLE P2 — full sweep *(size XL, grind)* — ✅ **62 → 13 null, 0 broken (2026-07-11)**
All domain tools, batched per service. The capability sweep reached `211/224 executes:true · 0
executes:false · 13 null` at $0; **all 13 residue are genuine WAIVES** with per-tool gate reasons
(browser-JWT ontology / real async job / bespoke multi-FK seed / paid / cross-service / pre-existing
draft — see [`TRACK-D-COMPLETION.md`](TRACK-D-COMPLETION.md) → Results). The prior "13 buildable-next"
deferral was CLEARED this run (kg node-chain, motif links/bind, scene/outline chains all built; needed
`kg_create_node` deployed). CD4 stays **reject-on-`executes:false`** (the "flip warn→reject" for
`null` is the consciously-rejected WS-D5c tightening — `null` ≠ broken).
**Exit:** matrix ≥95% non-RED **or** explicitly WAIVED with a reason — met via 94% proven, 0 broken,
13 waived. Plus the Track-A gateway prefix-drop test now exists
(`scripts/eval/tool_liveness/tests/test_federation_prefix.py`).

> **⚠ Naming (WS-D5 collision, resolved 2026-07-11).** Two different deliverables shared "WS-D5":
> **WS-D5a** = the *tool-description disambiguation* follow-up ([`WS-D5-followups.md`](WS-D5-followups.md),
> DONE) and **WS-D5** below = the *frontend-tools liveness* deliverable. Historical commits/handoff
> lines labelled "WS-D5" refer to WS-D5a; the frontend-tools work is this section.

### WS-D5 · Frontend tools (12) via Playwright *(size M)* — ✅ **DONE (2026-07-11)**
The loop **suspends**; the real FE resolver/executor/card runs; G4 asserts the effect + the resume
round-trip. G3 (all 12) via the pure-resolver + BE contract tests; G4 (real browser) via
`frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts` (+ `helpers/frontendToolInject.ts`) — 4
injected tests green, covering both executor code paths; the other 8 share the proven paths.
Precedent honoured: `agent-gui-loop-needs-live-browser-smoke-not-raw-stream`. See
[`TRACK-D-COMPLETION.md`](TRACK-D-COMPLETION.md) → Phase 2.

### WS-D6 · Macro journeys *(size M)* — ✅ **S06 PROVEN (2026-07-11)**
S06 flagship re-run on local gemma: **`effectful_tool_calls > 0` (4/5 warm), `persist_claims_without_write == []` (6/6)**,
DB-verified plan_runs. **Exit met.** Report:
[`../../eval/discoverability/2026-07-11-S06-flagship-rerun.md`](../../eval/discoverability/2026-07-11-S06-flagship-rerun.md).
The **D-side** proof (an LLM persists honestly via tools) is established; the full **N3** product
go/no-go additionally needs Track C (catalog+UI), out of Track D's scope. → **ND4** (D-side)

---

## Integration nodes

| Node | Gate |
|---|---|
| **ND1** — after WS-D0 | every tool declares tier/scope; `paid ⇒ tier != R`; wire gates green ⇒ probes test the *right* gating |
| **ND2** — after WS-D2 | harness proven end-to-end incl. confirm resolution + effect read-back |
| **ND3** — after WS-D3 | CD4 ship gate live ⇒ **Track C's curated workflows may ship** |
| **ND4** — after WS-D6 | flagship S06 green with real effects ⇒ the platform's headline claim is true |

---

## Definition of done

1. No MCP tool ships without `tier` + `scope`; job-starters declare `async`; money-spenders declare
   `paid`. A CI gate per service enforces it on the real wire.
   *(Corrected 2026-07-10: this line used to read "…and are never tier `R`". That conflated spend
   with mutation and contradicts CD1's `paid ⊥ tier`. A paid **read** is Tier `R` — `web_search`
   ships as `tier:R, paid:true`, and the rule as written would have forced it out of `ask` mode
   or dropped its spend gate. `tier` governs mutation; `paid` governs money.)*
2. `docs/eval/tool-liveness/<date>/matrix.json` exists, is **generated** from the live gateway, and a
   tool without an authored probe is a RED cell.
3. Every tool in the workflow-critical set passes **G1–G4** — including the confirm round-trip for
   Tier-W and terminal-status polling for async.
4. A workflow cannot reference an unproven tool (CD4), and `tool_list` never advertises a RED-G3 tool.
5. Flagship S06 shows `effectful_tool_calls > 0` and `persist_claims_without_write == []`.

## Watch

- **Safety:** destructive probes (`book_purge`, `glossary_entity_delete`, `memory_forget`, …) run
  **only** against the fixture. Repo precedent: `kg-integration-tests-truncate-shared-dev-db` — an
  ontology test once truncated the live dev DB. Never scope a probe to a real book.
- **Cost:** the agent is free (local gemma); **tools** are not. ~25 spend real money. Default
  `SKIP → UNTESTED-PAID`; opt in with `--allow-paid` + a hard USD cap and minimal inputs.
- **Don't trust the inventory.** One of its four "findings" was verified **false** and one is still
  unproven. Read the handler before you mark a tool `async` or rename anything.
- **Shared checkout:** Tracks B/C are owned by other sessions. Track D touches `validateWorkflow`
  (Track A's file) for CD4 only — coordinate via the board.
