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
   - **`glossary_web_search` — untiered, and its own description says it is PAID.** So it advertises as
     `R`: callable in read-only **ask** mode, no approval card, no write budget. **Highest severity —
     this is unmetered spend exposure.**
   - **`glossary_deep_research` — untiered, description says PAID.**
   - `glossary_adopt_standards` — untiered, yet **mints a confirm token** (advertises as a read).
   → *Same fix as knowledge: adopt `_meta` + a `tools/list` regression gate. Do this before the sweep
   (open question 4), else every glossary probe tests the wrong gating.*

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

## 10. Open questions

1. **Ship gate strictness** — reject an `unproven_tool` at workflow authoring, or warn only? (Recommend: warn in P1, reject from P2.)
2. **Probe authorship** — hand-write 223 NL asks, or generate a first draft per tool from its description + synonyms and hand-review? (Recommend: generate → review; a bad probe fails G1 and looks like a tool bug.)
3. **Frontend 12** — accept a simulated resolver (fast, P0-able) or hold them for Playwright (true, slow)? (Recommend: simulate for G3, Playwright for G4.)
4. **Untiered 42** — fix tiers *before* the sweep (else their probes test the wrong gating), or record the current behavior as the baseline? (Recommend: fix first — it's the same one-file change as knowledge.)
