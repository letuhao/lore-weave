# MCP Tool Liveness Eval (TLE) — every tool proven callable, correct, and *effectful*

**Status:** PLAN · authored 2026-07-09 · **Track D**
**One-liner:** For **every** MCP tool, send a natural-language ask to a real LLM, and prove the model
picked it, shaped its args correctly, the call actually executed, **and the system really changed**.

| Doc | What it is |
|---|---|
| this file | the measured gap · scope · gates · phasing · findings |
| [`contracts.md`](contracts.md) | **CD1–CD4, frozen** — the `_meta` completeness law, `propose_*` semantics, the G1–G4 gates + matrix schema, the ship gate |
| [`TRACK-D.md`](TRACK-D.md) | the track brief — workstreams WS-D0…D6, integration nodes, DoD |

---

## 1. Why this exists (the gap is measured, not suspected)

We ship tools that pass unit tests and are still **broken the moment an LLM calls them**: wrong
parameter shape, a server exception, a confirm gate that never resolves, or the worst failure mode —
a cheerful "saved!" with **nothing written**.

The evidence is already in the repo:

> `docs/eval/discoverability/runs/2026-07-09-S06-baseline/S06-metrics.json`
> → **`effectful_tool_calls: 0`**, with `persist_claims_without_write` firing.
> The agent said *"I have locked that into the core of the project."* Zero rows were written.

A survey of every existing harness confirms the structural cause:

| Harness | drives | (a) tool chosen | (b) args valid | (c) call succeeded | (d) **effect persisted** |
|---|---|---|---|---|---|
| `chat-service/eval/run_tool_catalog_eval.py` | provider-registry direct (**stub backend, nothing executes**) | ✅ | ✅ | ✗ | ✗ |
| `scripts/eval/run_discoverability_scenario.py` | chat SSE (agui) | ✅ | ✅ | ~ (`ok` flag only) | ✗ |
| `scripts/eval/run_skill_gate.py` | chat SSE | ✅ (name only) | ✗ | ✗ | ✗ |
| `scripts/eval/run_quality_gate.py` | chat SSE | ✅ (name only) | ✗ | ✗ | ✗ |
| `scripts/run_dracula_mcp_scenario.py` + smokes | **direct MCP, no LLM** | n/a | n/a | ✅ | ✅ |

**Nobody occupies the intersection.** The NL harnesses stop before the write lands; the
effect-verifying scripts have no model choosing the tool. Worse, **no NL harness resolves the
propose→confirm gate**, so all 37 Tier-W tools suspend and never execute — which is precisely why
S06 recorded zero effects.

TLE is that intersection: **model-driven selection + confirm resolution + effect assertion + async
polling, per tool.**

---

## 2. Scope — 223 tools, enumerated by the machine, never by hand

| Layer | Count |
|---|---|
| Federated domain tools (via `ai-gateway`) | **206** |
| chat-service consumer-local (5 meta + 12 frontend) | **17** |
| **Total** | **223** |

Domain split: glossary 55 · composition 56 · knowledge 33 · book 21 · provider-registry 12 ·
translation 12 · agent-registry 9 · jobs 5 · catalog 2 · lore-enrichment 1.

> **Design rule — the inventory is GENERATED, never inlined.** CLAUDE.md already warns that an
> inlined service table went stale and misled agents. TLE enumerates tools by calling
> `tools/list` on the live gateway and reading each tool's `_meta` (tier / scope / async). A tool
> that exists but has **no authored NL probe is a RED cell** in the matrix. Coverage therefore
> self-updates: *adding a tool without a probe fails the gate.*

---

## 3. The four gates (this is the whole contribution)

For each tool `T`, an authored **natural-language ask** (never the tool name — black-box, per the
scenario rule) is sent to a real mid-tier model on a real stack. Then:

| Gate | Question | Failure means |
|---|---|---|
| **G1 · SELECT** | Did the model call `T` at all? | undiscoverable / bad description / wrong tier gating |
| **G2 · SHAPE** | Are the args schema-valid? (required present, enums honored, ids well-formed) | schema too loose, prose-only enum, missing context-id injection |
| **G3 · EXECUTE** | Did the call return **without `isError`** — and for Tier-W, did the **confirm round-trip complete**? | server exception, bad param binding, unresolvable gate |
| **G4 · EFFECT** | Did the system **actually change**? Read it back from the DB/API. Async: poll to terminal + assert the artifact. | the "silent success" bug class — the one that matters |

G4 is non-negotiable and is what every existing harness lacks. A read tool's G4 is *"returned data
consistent with the seeded fixture"* — not merely "returned 200".

> **Anti-oracle rule for G4:** verify the effect through a **different path than the one that wrote
> it** (DB / REST read-back), *not* by calling the domain's own read tool — a shared bug would make
> both agree. (Repo precedent: `emit-wiring-live-proof-catches-bypass-chokepoint`,
> `checklist-is-self-report-enforce-by-tests`.)

---

## 4. Per-class test recipe

The tool's `_meta` (tier / async) selects the recipe. Counts from the live inventory:

| Class | n | Recipe |
|---|---|---|
| **R** — read | 53 explicit (+42 untiered, see §8) | G1,G2,G3 + G4 = result matches the seeded fixture |
| **A** — auto-write | 74 | G1–G3 + G4 = read the target row back; assert the field |
| **W** — confirm-token | 37 | G1–G3, then **resolve the gate**: capture `confirm_token` → `POST /v1/<domain>/actions/confirm` (user JWT) → G4 read-back |
| **async** (`_meta.async`) | 7 | G1–G3 + assert job enqueued → **poll `jobs_get` to terminal** → G4 asserts the produced artifact, *not* the job id |
| **frontend** (browser-resolved) | 12 | tool-loop must **suspend**; a simulated resolver POSTs the result back; G4 on the human-applied effect. Full fidelity ⇒ Playwright (P3) |
| **admin** (RS256) | 7 | same, with `X-Admin-Token`; admin confirm route |
| **paid** (real spend) | ~25 | default **SKIP → `UNTESTED-PAID`**; run only under `--allow-paid` with a budget cap (§9) |

**Tier-A note (new, from the knowledge `_meta` adoption):** Tier-A writes now surface the approval
card and count against per-op/aggregate auto-write caps. The harness must **pre-allowlist the test
account** (`user_tool_approvals`) so the run doesn't stall — and one dedicated test must assert the
card *does* appear when not allowlisted (the gate itself is a feature under test).

---

## 5. What must be built (and what to reuse)

| # | Component | Status | Reuse |
|---|---|---|---|
| 1 | **SSE driver** — session create + turn, full `TOOL_CALL_RESULT` capture (name + args + `ok` + result) | reuse | `run_discoverability_scenario.py:229-266` (`_create_session`/`_send_turn`) |
| 2 | **Confirm resolver** — detect `confirm_token`, POST to `/v1/<domain>/actions/confirm` w/ user JWT; resume the suspended run | **BUILD (biggest gap)** | token+confirm machinery from `scripts/run_dracula_mcp_scenario.py:33-53` |
| 3 | **Fixture factory** — throwaway book + project + chapter + seeded entities per run; teardown | **BUILD (does not exist)** | book-create pattern from the dracula script Phase 1 |
| 4 | **Effect oracles** — per-tool read-back (DB/REST), independent of the write path | **BUILD** | — |
| 5 | **Async poller** — poll `jobs_get` / `translation_job_status` to terminal, then assert artifact | **BUILD** | job-id scanner `run_discoverability_scenario.py:121` |
| 6 | **Cost governor** — `$0` local gemma for the *agent*; paid-tool budget cap + skip policy | **BUILD** | — |
| 7 | **Matrix reporter** — generated tool list × G1–G4 → `matrix.json` + `matrix.md` | **BUILD** | report writers `run_discoverability_scenario.py:622-628` |

**Auth:** existing harnesses self-mint an HS256 JWT from `JWT_SECRET` (in-container only). TLE should
authenticate the test account through the **real** `/v1/auth/login` edge so the auth path is under
test too (proven working this session).

**Model:** local gemma (`user_model_id` resolved live from `user_models`) → **$0 agent spend**.
`user_default_models` is empty for the test account, so an explicit `model_ref` is mandatory.

---

## 6. Output + the ship gate

Per run → `docs/eval/tool-liveness/<date>/`:
- `matrix.json` — one row per tool: `{tool, service, tier, async, probe, G1..G4, evidence, notes}`
- `matrix.md` — human table, grouped by service, RED cells first
- `transcript.jsonl` — every turn + every tool record (args, ok, result)

**The gate (this is the point of the exercise):**

> **A curated workflow MUST NOT reference a tool that has not passed G1–G4.**

Wire it into the C3 authoring path: `validateWorkflow` currently defers tool-catalog membership to
the runner. Add a **liveness set** — a workflow step whose tool is not in the passing set is rejected
at authoring (or admitted with a loud `unproven_tool` warning). That turns TLE from a report into an
enforced precondition for shipping workflows.

Additionally: **`tool_list` must not advertise a tool with a RED G3** (a tool the LLM cannot
successfully execute is worse than an absent one — it burns turns and produces false claims).

---

## 7. Phasing

| Phase | Deliverable | Exit |
|---|---|---|
| **P0** | Harness skeleton: SSE driver + fixture factory + confirm resolver + one effect oracle + matrix writer. Prove on **10 tools spanning R / A / W / async**. | 10 rows, ≥1 genuine bug found |
| **P1** | **The workflow-critical set** — every tool any authored workflow (C3) can reference. *This is the actual "before we ship workflow" gate.* | ship gate (§6) enforceable |
| **P2** | Full 206-tool sweep, batched per service (glossary 55 and composition 56 are the long poles) | matrix ≥95% non-RED or explicitly waived |
| **P3** | Frontend tools (12) via Playwright — the loop suspends, the FE resolver truly executes | browser-verified effects |
| **P4** | **Macro journeys** — S00–S06 + authored workflows: ordering, gates honored, async honesty, **zero false persist-claims** | flagship S06 passes with `effectful_tool_calls > 0` |

P0+P1 is the shippable unit. P2 is grind. P4 reuses the existing scenario harness with G3/G4 bolted on.

---

## 8. Pre-eval findings — bugs the inventory **already** proves (file these now)

The inventory alone, before a single probe runs, surfaces four real defects:

1. **Glossary-service tools largely carry NO `_meta.tier`** — absent tier silently defaults to **`R`**,
   the *exact* hole just fixed in knowledge-service (`f191cb858`), where untiered writes were executable
   in read-only **ask** mode and skipped the approval card.
   *Verified directly (a conservative scan): **≥27 of 35** glossary tools matched have no `Meta:`;
   a fuller sweep puts it at ~35 of 50 `/mcp` tools + 5 admin + 2 knowledge admin ≈ 42 domain tools.*
   Confirmed individually:
   - **`glossary_web_search` — untiered, and its own description says it is PAID.** **Highest severity:
     no internal spend gate exists at all** (verified — nothing in the chat tool-loop reads a spend
     concept, and the public gateway marks its own gate "P3/pending"). Unmetered spend exposure.
     > **The fix is NOT to force it to a write tier.** Spend ⊥ mutation (see `contracts.md` CD1,
     > corrected). It stays a **read** — allowed in ask mode — and gets `_meta.paid` + a **spend gate**.
   - **`glossary_deep_research` — untiered, description says PAID** (it *does* mint a confirm card
     with cost, so its gate exists; the missing `_meta` is the defect).
   - `glossary_adopt_standards` — untiered, yet **mints a confirm token** (advertises as a read).
   → *Same fix as knowledge: adopt `_meta` + a `tools/list` regression gate. Do this before the sweep
   (open question 4), else every glossary probe tests the wrong gating.*

5. **`glossary_web_search` is universal infrastructure filed under the wrong prefix** (verified four
   ways):
   - its own description: *"it needs no book or entity"*; args are just `query` (+`max_results`);
   - `universal_skill.py` already teaches it as **the bookless research tool** — an entire paragraph
     explaining how to reach it, which is a *workaround for the misleading prefix*;
   - the capability actually lives in **provider-registry** (`POST /internal/web-search`) per the
     provider-gateway invariant — glossary only wraps it;
   - **composition-service has its own `web_search_client.py`** hitting that same endpoint, and its
     comments say it *"mirror[s] `glossary_web_search`'s title/snippet/answer caps"* — a second
     consumer duplicating safety caps across services. **Real drift risk.**

   → Rename to **`web_search`** (universal), keep `glossary_web_search` as a `visibility: legacy`
   alias (never delete). **`glossary_deep_research` is NOT universal** — it requires `book_id` +
   `entity_id` and attaches draft evidence to a glossary entity; it keeps its prefix.

   **Blockers (verified — two are new and load-bearing):**
   - **⚠ CORRECTION.** An earlier draft of this doc said *"federation routing is safe — `providerFor()`
     resolves via a discovered `toolToProvider` map, not by prefix."* **Half-right and dangerously
     incomplete.** `providerFor()` *is* name-based, but its map is only populated by tools that survive
     the **C-GW prefix gate**: `catalog.ts:71` *"drop + warn a tool that escapes its namespace"*. The
     `settings` provider (= provider-registry) allows only `settings_`. A bare `web_search` hosted
     there is **silently dropped from the federated catalog**. → must add `web_` to
     `EXTRA_PREFIX_MAP.settings` (`config.ts:110`) or use the inline env override.
   - **The legacy alias cannot move.** `glossary_web_search` (prefix `glossary_`) would be dropped by
     the same gate on provider-registry. → keep it **registered on glossary-service**, demoted in place
     to `VisibilityLegacy` + `superseded_by: "web_search"`.
   - `_domain_of()` is prefix-derived ⇒ `web_search` (prefix `web`) has **no C1 category home** →
     C1 += `research` (done: Track A contract amended).
   - Hot-pathing consumes the **last free `ALWAYS_ON_CORE` slot (9→10 of 10)** and must wait on the
     spend gate.
   - `_meta.superseded_by` **has zero producers** today (consumers read it; only a synthetic test
     fixture sets it) → needs a `WithSupersededBy` kit helper. A same-handler-two-names alias is also a
     **new pattern** in this repo (no precedent).

6. **Bonus bug — compaction never protected web-search results.**
   `sdks/python/loreweave_context/compaction.py:51` declares
   `DEFAULT_EXCLUDE_TOOLS = frozenset({"web_search"})`, commented *"results NEVER evicted (their output
   is load-bearing / cited)"*. The real wire name is **`glossary_web_search`**, so **it has never
   matched** — cited web results have been silently evictable this whole time. The rename **fixes this
   by accident**; add a test pinning the exclude-set to the live wire name.

7. **Async omissions are 8, not 4** (audited handler-by-handler, not from the inventory):
   - **Tier-W confirm-then-job (5):** `composition_motif_mine`, `composition_arc_import_analyze`,
     `composition_conformance_run`, `composition_authoring_run_start`, `composition_authoring_run_resume`.
     Precedent settles it: **`kg_build_graph` is Tier-W *and* `async_job=True`** — the tool call enqueues
     nothing, the job starts at confirm, and the flag exists so the agent doesn't claim "done".
   - **Tier-A, enqueues at TOOL time (3):** `plan_propose_spec(mode=llm)` (strongest — returns
     `{"async": true, "job_id"}`), `plan_apply_revision`, `plan_compile(run_pipeline=true)`. These are
     **dual-mode** (sync or async by arg + `composition_worker_enabled`); `_meta.async` is a static flag
     → mark `true` (coarse but honest; the flag only *adds* a "watch the job" hint, never blocks).

> **A SECOND inventory finding was verified FALSE.** `glossary_propose_aliases` was flagged as possibly
> writing canonical data. Traced: its only `entity_attribute_values` write is an **empty `'[]'` scaffold**
> whose `ON CONFLICT DO UPDATE SET original_value = entity_attribute_values.original_value` is a
> **self-assignment no-op**; the alias payload lands in `attribute_translations` at
> `confidence='draft'`, guarded by `WHERE confidence <> 'verified'`. **Legitimate draft tool.** Two of
> the inventory's four findings did not survive. Read the handler.

2. **`propose_*` is overloaded, with no machine-checkable meaning.** It spans two *legitimate*
   patterns — **token** (tier `W`: mints a `confirm_token`, writes nothing) and **draft** (tier `A`:
   writes a pending row a human approves). Neither the model nor a reviewer can tell which from the
   name, so an agent cannot know whether a confirm round-trip is required. → declare the pattern in
   each description + lint `propose ⇒ tier ∈ {A,W}` (contract **CD2**).

   > ⚠️ **A claimed finding here was verified FALSE and rejected.** The inventory reported
   > `glossary_propose_translation`/`_aliases` as "direct writes despite the name". Source says
   > otherwise: `upsertDraftTranslation` inserts with `confidence='draft'`
   > (`pipeline_translate_tool.go:294-299`) — the legitimate *draft* pattern. **No rename needed.**
   > `glossary_propose_aliases` also touches `entity_attribute_values` → treat as **audit**, not a
   > proven defect.

3. **Async-honesty gaps — candidates, not yet proven.** Composition declares `async_job=True`
   **exactly once** (`composition_generate`), yet `composition_motif_mine`,
   `composition_arc_import_analyze`, `composition_conformance_run`, and `plan_propose_spec(mode=llm)`
   are described as starting background jobs. **Read each handler before marking it `async`** — do not
   mark on the inventory's word.

4. **`lore_enrichment_auto_enrich` is Tier-`A` but is `async` *and* paid** (all three verified). An
   auto-applying paid async tool contradicts the money model — `mcp-public-gateway` already
   reclassifies it `write_confirm`; the **internal tier should be `W`**, and the public one should be
   *derived* rather than restated.

Findings 1 and 4 are **gating/spend defects** (act now). 2 is a **contract gap** (CD2). 3 is an
**audit**. One of the inventory's four findings did not survive verification — a reminder that the
generated inventory is a lead, not evidence.

---

## 9. Cost + safety policy

- **Agent spend = $0** — local gemma via BYOK. All 223 probes drive the same free model.
- **Tool spend** is the real cost. ~25 tools spend money (web search, LLM extraction, generation,
  translation jobs, embeddings). Default: **skip → `UNTESTED-PAID`**. Opt in with `--allow-paid` +
  a hard USD cap; each paid probe uses the smallest possible input (1 chapter, 1 entity).
- **Destructive tools** (`book_purge`, `book_delete`, `glossary_entity_delete`, `memory_forget`, …)
  run **only against the throwaway fixture**, never a real book. The fixture factory is the safety
  boundary — no probe may touch an id it did not create.
- **Never run against the shared dev DB without scoping** (repo precedent:
  `kg-integration-tests-truncate-shared-dev-db` — an ontology test once truncated the live dev DB).

---

## 10. Resolved decisions (was: open questions)

All questions closed 2026-07-09 against source. **No open questions remain** — the track is
fan-out-ready.

| # | Question | **Decision** | Basis |
|---|---|---|---|
| 1 | Ship-gate strictness | **Warn in WS-D3, reject from WS-D4** | a hard reject before the matrix has coverage would block all authoring |
| 2 | Probe authorship (223 NL asks) | **Generate a draft per tool from its description + `_meta.synonyms`, then hand-review** | a bad probe fails G1 and is indistinguishable from a tool bug — review is the cheap guard |
| 3 | Frontend 12 | **Simulated resolver for G3; Playwright for G4** | precedent `agent-gui-loop-needs-live-browser-smoke-not-raw-stream` |
| 4 | Untiered tools: fix before sweep? | **Fix first (WS-D0)** | otherwise every glossary probe tests the wrong gating |
| 5 | **What IS the spend gate?** | **Two layers.** *Layer 1 (MVV, chat-service):* `_meta.paid` + a `tool_paid()` reader + a gate branch **orthogonal to tier**, reusing the existing `tool_approval` suspend/resume card + `user_tool_approvals` allowlist (approve-once / always-allow / deny). *Layer 2 (provider-registry):* add a **`per_call` pricing dimension** (none exists) and wrap the sync `/internal/web-search` in `Reserve → call → Reconcile`, finally consuming the `x-mcp-spend-cap-usd` header | 3 ledgers are **LIVE** (`spend_guardrails`, `platform_balances`, `mcp_key_usage`) but `Reserve/Reconcile` is **JOB-path only**; sync outward calls are **audited at $0, never reserved** (`server.go:3151`) |
| 6 | Gate style for `web_search` | **Approval-on-first-use, then allowlisted** — not a per-call cost card | fixed ~1-query cost; a card per call is noise. Reserve the cost-card style (à la `glossary_deep_research`) for variable/expensive tools |
| 7 | Does a paid READ stay callable in `ask` mode? | **Yes.** The gate is mode-independent and orthogonal to tier | CD1: `paid ⊥ tier`. `_filter_tools_for_ask` keeps tier-R advertised; `tool_paid` fires regardless of mode |
| 8 | Where does `web_search` live? | **provider-registry** (owns the capability) — **but** `web_` must be added to `EXTRA_PREFIX_MAP.settings`, or the C-GW gate silently drops it | `catalog.ts:71` |
| 9 | Where does the **legacy alias** live? | **Stays on glossary-service**, demoted in place to `VisibilityLegacy` + `superseded_by` | the prefix gate forbids `glossary_*` on the settings provider |
| 10 | `superseded_by` producer | **Add a `WithSupersededBy` kit helper** (Go); first production use | zero producers today — consumers read it, only a test fixture sets it |
| 11 | Composition's duplicate client | **Keep its HTTP client; move neutralization to the PRODUCER** (`/internal/web-search`) so 3 copies collapse to 1 | it is a service-to-service call with a graceful-degrade contract; routing it through an MCP tool would lose that and gain nothing |
| 12 | Dual-mode async (`plan_*`) | **Mark `async: true`** (coarse but honest) | `_meta.async` is a static flag; it only *adds* a "watch the job" hint, never blocks |
| 13 | Confirm-then-job tools: async? | **Yes** — 5 composition Tier-W tools get `async` | precedent: `kg_build_graph` is Tier-W **and** `async_job=True` |
| 14 | `domain:research` public scope | `web_search` → `domains: ['research']`; **existing public keys keep working via the `glossary_web_search` legacy row** (`domains: ['glossary']`). New scope needed only for the new name | `tool-policy.ts` `Domain` is a hand-maintained union — add `'research'` |
| 15 | G4 oracles for 206 tools | **Generic oracle by class + per-tool override.** `A` → REST/DB read-back · `W` → confirm, then read-back · `R` → assert against the seeded fixture · `async` → poll terminal, assert artifact | avoids hand-writing 206 bespoke oracles |
| 16 | `ALWAYS_ON_CORE` cap | `web_search` takes the **last slot (10/10)**. Raising the cap is a **separate, explicit decision** | `test_tool_discovery.py:645` pins `<= 10` |
