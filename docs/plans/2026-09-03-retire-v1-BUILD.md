# BUILD PLAN + RUN-STATE — Retire architecture v1

Reconciles: Frontend-Tool Contract · Agent GUI Reconciliation (09) · Chat-agent ↔ MCP wiring — retiring the chat-service frontend-tool construct changes WHERE those three rows' rules are enforced, not what they say. The contract's SoT moves with it (`frontend-tools.contract.json` → `browser-tools.contract.json`), which is why the index row is repointed rather than a second contract being introduced.

> **FINAL REPORT (2026-09-03):** [`docs/plans/2026-09-03-retire-v1-FINAL-REPORT.md`](2026-09-03-retire-v1-FINAL-REPORT.md) — verdict `v1 IS DEAD`, every DQ-V6 decision, and what is deliberately not done.

- **Spec:** [`docs/specs/2026-09-03-retire-architecture-v1.md`](../specs/2026-09-03-retire-architecture-v1.md)
  (DRAFT — seal it by answering DQ-V1…V4 before starting Slice 1)
- **Branch:** `feat/frontend-tools-mcp-migration`
- **Predecessor:** [`2026-07-19-frontend-tools-mcp-migration-BUILD.md`](2026-07-19-frontend-tools-mcp-migration-BUILD.md)
  (S1/S3/S4 done; **S2 and S5 are what this plan finishes**) and its successor
  [`2026-07-20-frontend-tools-phases-2-4-BUILD.md`](2026-07-20-frontend-tools-phases-2-4-BUILD.md)
- **Re-read this file first after any compaction.**

## THE BOARD IS GENERATED. DO NOT TYPE COUNTS INTO IT.

Run `python scripts/v1_retire/runstate.py` for live state. Every number below that is not marked
`(snapshot)` is derived from the code by that script.

The predecessor board sat at `pending` for three slices that had shipped, for six weeks, because it
was typed. The audit that produced this plan found five more documents in the same condition. **A
count in this file that a script cannot re-derive is a bug in this file.**

---

## Invariants — do not re-litigate from memory

1. **v1 is three tools**, not 199: `confirm_action`, `glossary_confirm_action`,
   `glossary_propose_entity_edit`. Everything else on the live surface is already v2.
2. **The `confirm_token` spine is permanent.** The public edge and external agents cannot drive
   tasks. Only chat-service's *agent-facing wrapper* is being retired.
3. **`chat_suspended_runs` and `/tool-results` survive.** 6 of 7 suspend producers are not v1.
4. **`mcp-public-gateway` has its own `confirm_action`.** Different owner, same name. Every removal
   step names a FILE, never a tool name.
5. **`deprecated` still serves.** Only `retired` kills a manifest declaration, and it is terminal.
6. **Order is load-bearing:** prose → advertisement → interception → machinery. Removing the
   interception before the advertisement leaves the model calling a tool nothing handles.

---

## Slice board

State is one of: `pending` · `in-progress` · `done (evidence)`. Evidence is a real run, never "the
code looks right".

| # | Slice | Blocks on | State |
|---|---|---|---|
| **V0** | De-rot — correct every document that describes v1 as current | — | **D6** |
| **V1** | Gate totality — the 14 ungated mint sites open tasks | DQ-V2 | **D4** |
| **V2** | Prove the gate total on the wire (zero bare confirm_tokens) | V1 | **DONE** — measured live 2026-09-03 at $0, no paid run needed. `scripts/v1_retire/live_probe.py` P2: the same `translation_start_job` call answers a tasks-capable client with a durable task (`io.loreweave/task-handle`, `input_required`) and a non-capable one with a `confirm_token` |
| **V3** | Model-facing prose — stop steering the model to v1 | V0 | **DONE** — the Go descriptions were reviewed by census over all 202 live tools, not by reading: 4 steered at dropped tools and are repaired. Gated by `scripts/test_a_live_tool_never_sends_the_model_to_a_dropped_one.py` |
| **V4** | Advertisement — stop offering the three schemas | V3 | **D2** |
| **V5** | Frontend — re-home the card render gates | DQ-V4 | **DONE** — render gates fixed (the glossary identity fix), and DQ-V4's `batch_confirm` re-home landed with its FE half on 2026-09-03; pinned by `batchConfirmIdentity.test.ts` |
| **V6** | Interception — delete the v1 suspend branch | V4, V5 | **D1** |
| **V7** | Machinery — retire `frontend_tools.py`, re-home survivors | V6 | **D1** |
| **V8** | Manifest — `glossary_propose_entity_edit` → `retired` | V7 | **D3** |
| **V9** | Deprecated-is-dead — close `tool_load`'s legacy path | DQ-V3 | **D5** |
| **V10** | Enforcement — land G1…G6 so none of this regresses | V8, V9 | **D7** |

> 🔴 **THE STATUS COLUMN IS A POINTER, NOT A WORD.** Until 2026-09-03 every row above read
> `pending`, including V6 and V7 — whose completion is recorded in this same file, 500 lines down
> ("V6 + V7 teardown — DONE"). That is the precise defect this plan was written to remove, sitting
> in the plan's own board, because a typed status has no way to notice the work finished.
>
> A row now names the **board clause that proves it**: run `python scripts/v1_retire/runstate.py`
> and read that clause. A row that no clause can prove says **OPEN** or **PARTIAL** and says what
> is missing — never a word that quietly ages into a lie.

---

## V0 · De-rot

**Why first.** The audit found `task_detect.py` telling any reader that the ext-tasks gate is
"dormant" and that "chat-service does NOT yet declare tasks capability" — both false, in the file
that implements the replacement. An agent that picks this work up mid-way and reads that concludes v1
is the only live path and reverses the plan. Correct the map before moving.

Worklist: see `docs/plans/2026-09-03-retire-v1-DEROT.md` (generated worklist, one row per correction).

**Highest-severity items, all verified:**

| Target | The lie | The truth |
|---|---|---|
| `services/chat-service/app/services/task_detect.py:11-16, :76` | the tasks gate is "dormant", capability "not declared" | `knowledge_client.py:962` calls it under `tasks_gate_enabled: True` |
| `docs/sessions/SESSION_HANDOFF.md:1-13, :45` | ~100 commits stale; every count wrong; its one `▶` names a decision closed 2026-08-25 | 207 rows, 200 proven, 0 blocked, 0 open DQs |
| `docs/standards/README.md:56` + ~16 rows | routes rules to `CLAUDE.md` sections | `CLAUDE.md` is 15 lines and says it holds no rules; the home is `AGENTS.md` |
| `AGENTS.md:117`, `docs/standards/mcp-tool-io.md:8,:47` | names `ui_open_studio_panel` + `propose_edit` as frontend tools in `frontend_tools.py` | both moved to ai-gateway 2026-07-20 |
| `docs/standards/mcp-tool-io.md:147,211,219,236` | "315 tools / 198 shippable" | 316 total / 199 live / 117 legacy |
| `docs/plans/2026-08-10-toolv2-loop-RUNBOOK.md:3` | `Status: open` | its own `:1531` says the loop is closed |
| this plan's predecessor, `:19-21` | S2/S3/S4 `pending` | S3/S4 shipped 2026-07-20; only S2 is genuinely open |
| `contracts/tool-deep-dive-ledger.json` `progress.last_batch` | `batch-40 (2026-08-14)` | rows contain batch-41; evidence runs to 2026-09-02 |

**Also in V0 (instrument fixes — the audit found these lying by construction):**

- `scripts/toolloop/problem_remaining.py` **exits 0 while printing "STOPPING IS NOT YET LEGITIMATE"**.
  Any CI check or `$?` read scores 13 unwritten invariants as a pass. Make the exit code match the
  verdict.
- `contracts/tool-deep-dive-ledger.json` `release_surface` is a hand-typed `198` frozen 2026-08-13,
  against a numerator derived live from the rows (`200`), producing
  `remaining_in_release_surface: -2`. Derive the denominator from `tool-catalog-cache.json`, the SSOT
  created one day *after* that constant was frozen. Decide whether `workflow_list` — chat-service-local
  and not federated — belongs in a denominator defined as federated tools.
- `contracts/tool-catalog-cache.json` is **STALE**: `refresh_tool_catalog_cache.py --check` exits 1
  with 42 drifted `inputSchema`s (23 live, 19 legacy). Not all cosmetic — `glossary_entity_rename`'s
  live `required` has gained `book_id`. Six instruments read this file. Refresh it.

**Evidence for V0:** `problem_remaining.py` exits non-zero on the current tree; `--check` on the
catalogue exits 0; every corrected count re-derived by its named generator, not typed.

---

## V1 · Gate totality (blocks on DQ-V2)

Make every KIND-C write that chat-service can reach return a durable task to a tasks-capable client
**or cite a GATE-2 exemption**. Re-derive with `python scripts/v1_retire/runstate.py`.

> 🔴 **THE COUNT WAS 14 AND IS 9. Five composition sites are already-reasoned exemptions**, named
> in the code that declines to register them — `server.py:347-355`: *"NOT registered here — the
> ledger-guarded KIND-C confirms (decompile, motif_adopt, motif_mine, arc_import, conformance_run):
> their `_execute_*` require the confirm TOKEN (the consumed-token replay ledger; mine/import/
> conformance additionally key the usage-billing reserve on the token jti)"*. That is **GATE-2
> class (a)** verbatim. They are recorded in `scripts/v1_retire/gate_exemptions.json`, which the
> generator subtracts — without it D4 counted them as defects and could never pass, the same
> unreachable-success-condition shape as X2.

| Service | Remaining | Work |
|---|---|---|
| translation | 4 | **adopt the gate** (DQ-V2) — ⚠ see the blocker below |
| book | 2 | `mcp_actions.go:105`, `:886` — `GateOrConfirm` already used at `:345`, `:387` |
| composition | 2 | `server.py:5911` `composition_library_translate`, `:7041` `plan_bootstrap_apply` — **not** named in the exemption comment; classify or gate |
| provider-registry | 1 | `mcp_server.go:878` |
| *(exempt)* | *5* | *composition, GATE-2 class (a), cited* |

### ⚠ BLOCKER ON DQ-V2 THAT WAS NOT VISIBLE WHEN IT WAS DECIDED
translation-service has **no task store**, and `PgTaskStore` is **composition-service-local**
(`services/composition-service/app/mcp/pg_task_store.py`) — it is *not* in the `loreweave_mcp` kit.
The repo's SDK-First standard is explicit: **≥2 users ⇒ SDK, never copy-paste.** So "translation
adopts the gate" is really three pieces of work, in order:

1. **Promote `PgTaskStore` into `sdks/python/loreweave_mcp`** (+ its `mcp_gate_tasks` migration
   pattern), leaving composition importing it from the kit.
2. Wire translation-service: store, resolvers by descriptor, `register_task_endpoints(tool_prefix=
   "translation")`.
3. Route its 4 sites through `gate_or_confirm`.

Step 1 is the real cost and it lands in a shared SDK, so it needs its own falsifier and both
services green. **Re-confirm DQ-V2 against this price before starting** — the ruling was "adopt",
taken when the visible cost was "wire up 4 call sites".

**Do not** remove `confirm_fallback`. The gate returns it to non-tasks clients by design, and that is
what keeps the public edge working.

**Evidence:** for each site, a live call from a tasks-capable client returns a task; the same call
from a non-tasks client still returns a `confirm_token`. Both halves, or the site is not done.

---

## V2 · Prove the gate total

**The bar is a measured rate on the wire, not a code review.** Zero bare `confirm_token`s reaching
chat-service over a window that actually exercises the KIND-C tools.

This is the clause most likely to be faked by a green run over a population that never triggers. The
denominator must be *calls to the 14 tools*, not turns, not sessions. A rate that looks perfect
because nothing called them is not a pass — state the call count alongside the rate.

**Evidence:** `scripts/v1_retire/confirm_token_rate.py --since <date>`, reporting calls, tokens, tasks,
and the rate, stratified by tool. Not pooled.

---

### X4 · D4's census had a FALSE-NEGATIVE CLASS — an entire service was invisible
The census grepped `mint_confirm_token|MintConfirmToken`. **knowledge-service mints with its own
helper**, `mint_action_token` (`app/ontology/confirm.py:160`, *"Python port of glossary's
`action_confirm_token.go`"*), used by `build_tools.py` and `graph_schema_tools.py` — and that
service has **no task gate at all**. So D4 read 5 remaining when the honest figure was 13, and
could have reported PASS over a whole service still handing the model bare tokens.

A census keyed on one spelling measures the services that happened to use that spelling. Widened;
the 8 newly-visible sites need classifying:

| Site | Likely disposition |
|---|---|
| `kg_admin_propose_template` | GATE-2 class **(c)** — System-tier admin confirm |
| `_handle_kg_build_graph`, `_handle_kg_build_wiki` | the tools are `visibility: legacy` |
| `_handle_kg_schema_edit`, `_handle_kg_adopt_template`, `_handle_kg_sync_apply` | `visibility: legacy` |
| `_handle_kg_triage_place_edge`, `_handle_kg_triage_schema_write` | **LIVE** — real work or a cited exemption |

> Do not exempt the legacy ones by reflex. They are withheld from the model *today* (DIS-4), but
> `tool_load` still labels rather than refuses and a session pin re-admits — which is V9's subject.
> An exemption resting on "it is legacy" is only sound once V9 lands.

---

## V3 · Model-facing prose

> 🔴 **THIS SLICE WAS DEFINED WRONG AND HAS BEEN REWRITTEN.** It said *"strip v1 names from
> model-facing prose"*. Under the **DQ-V5 ruling the three tools keep their names** — they move to
> a domain service, they are not deleted — so stripping the names would have broken correct prose
> and left the model unable to drive the fallback.
>
> **The real defect is the opposite one:** the prose presents the `confirm_token` hand-off as the
> PRIMARY flow, when chat-service is tasks-capable (`tasks_gate_enabled: True`) and glossary routes
> **15 propose tools** through `gateOrCard` → `GateOrConfirm`. On the shipped path the model gets a
> durable TASK and never sees a token, so it was being told to perform a step that does not occur.
>
> **Done 2026-09-03** for `glossary_skill.py`: the gated proposals now read as *"returns a GATED
> proposal — the user is asked to approve it and you do NOT drive the approval yourself"*, with the
> token hand-off kept explicitly as the fallback shape.
>
> **Deliberately NOT touched, because their prose is CORRECT:**
> `settings_skill.py:98` (`settings_model_delete` is genuinely ungated), `translation_skill.py:53`
> (translation has no gate), and `glossary_skill.py:258` (`glossary_admin_*` are System-tier admin
> confirms — GATE-2 class (c)). Correcting those would have introduced the error it was fixing.
>
> **Still open:** four LIVE knowledge-service tools whose *descriptions* promise a `confirm_token`
> — `kg_ontology_propose`, `kg_triage_place_edge`, `kg_triage_schema_write`, `kg_build`. The token
> is real (`mint_action_token`), so the descriptions are not false; but `kg_build`'s ledger row
> records all five runs ending on a **Tier-A approval card**, not a token, so at least that one
> needs tracing through `_dispatch` before its description is trusted or changed. **Not guessed at.**

### Original scope (the Go descriptions — still to do)

Live prompt/description text that names the v1 tools — this steers the model toward them. Comments do
not count and are excluded.

- `services/chat-service/app/services/glossary_skill.py` — lines 69, 85, 87, 126, 165, 176, 227, 257, 262
- `universal_skill.py:61`, `translation_skill.py:6,54,89`, `settings_skill.py:99`, `jobs_skill.py:62`
- **glossary-service (Go)** — 19 refs across 11 files; `mcp_server.go:190,209,225,255,286` are
  descriptions (`:181` is a comment), plus `book_tools.go` ×3, `sync_tools.go` ×2, and one each in
  `action_confirm.go`, `action_plan_tools.go`, `action_propose_tools.go`, `curation_propose_tools.go`,
  `entity_delete_tools.go`, `pipeline_propose_tools.go`, `pipeline_write_tools.go`
- **composition-service** — `app/mcp/server.py:1925, 2972, 3052, 3169`

> **Sequencing trap.** `TestSkillClaimsLint` (`test_skill_registry.py:502,510`) **exempts** anything in
> `ALWAYS_ON_CORE_NAMES`, and `confirm_action` is in it. The lint therefore cannot catch stale claims
> until V4 removes it. V3 before V4, or the lint stays blind through both.

---

## V4 · Advertisement

- `tool_discovery.py:310` — remove `confirm_action` from `ALWAYS_ON_CORE_NAMES`
- `tool_discovery.py:1122` — `_STICKY_DOMAIN_IGNORE`
- `tool_plan.py:33` — `_EXECUTOR_KEEP_CORE = {"confirm_action","propose_edit","tool_load"}`
- `frontend_tool_defs()` call sites — `stream_service.py:10705`, `:10896`, `:13381`. **Edit, do not
  delete:** each also serves `propose_edit` on the editor branch.
- `stream_service.py:10693-10706` and `:13877-13888` — the admin branch appends
  `GLOSSARY_CONFIRM_ACTION_TOOL`. **This is the only admin System-write gate.** It cannot simply be
  removed; V5 must land its replacement first.

Tests touched: `test_permission_modes.py:34,148`, `test_tool_discovery.py:72`,
`test_stream_service.py:585,600,1275`, `test_compaction.py:316`.

---

## V5 · Frontend (blocks on DQ-V4)

**Breaks if edited carelessly — TypeScript will not warn on any of these:**

- `cms-frontend/src/features/admin-chat/components/MessageList.tsx:28` — **highest risk in the whole
  plan.** `tc.pending && tc.tool === 'glossary_confirm_action'` is the *sole* render gate for
  `AdminConfirmCard`, and cms-frontend has no auto-confirm fallback. Any other tool name renders as a
  10px text line. Verified directly.
- `frontend/src/features/chat/components/AssistantMessage.tsx:256-259` — the `FRONTEND_TOOLS` array.
  **Keep `'confirm_action'`** unless V6 also re-homes the `stream_service.py:7809` synthesiser (DQ-V4).
- `AssistantMessage.tsx:302`, `:322` — `explicitTokens` / `confirmProposals` dedup. If a v2 confirm
  tool arrives as a pending record under a new name, these produce **duplicate confirm cards**.
- `frontend/src/features/chat/utils/serverKey.ts:31,32,39` + `__tests__/serverKey.test.ts`
- `frontend/tests/e2e/specs/frontend-tools-liveness.spec.ts:128-137` — the only live-browser
  card-dispatch proof.

**Deletable with v1 — exactly one component:** `GlossaryDiffCard.tsx` + its test.

**Must survive:** `ConfirmActionCard.tsx`, `ConfirmCard.tsx`, `BatchConfirmCard.tsx`,
`TaskConfirmCard.tsx`, `ToolApprovalCard.tsx`, `DisambiguationCard.tsx`, `ProposeEditCard.tsx`, the
auto-confirm machinery, both `submitToolResult`/`submitToolResolve` pairs, `workers/chatStateHub.ts`.
Note `AssistantMessage.tsx:401` hard-codes `tool:'glossary_confirm_action'` on a **synthetic** record
routed by descriptor, never by name — read it before touching it.

---

## V6 · Interception

- `stream_service.py:7143-7321` — the `is_frontend_tool` branch, `_unwrap_wrapped_args`,
  `_inject_context_ids`, `validate_frontend_tool_args`, the `:7321` suspend
- `stream_service.py:7807-7818` — re-home or retire the synthesised batch-cap card (DQ-V4)
- `stream_service.py:78-84` — the import block

**Do not touch** `:7863`, `:8166`, `:8426`, `:8820`, `:8840` — those are the five non-v1 producers.

---

## V7 · Machinery

Re-home the survivors, then delete the file.

| Symbol | Consumers | Disposition |
|---|---|---|
| `is_browser_executed` | `agent_surface.py:78`, `subagent_runtime.py:99` | **Needs a new home** — covers `propose_edit` + `ui_*`, which survive. Its docstring documents the bug from conflating it with `is_frontend_tool`; **do not merge them.** |
| `_ALL_FRONTEND_TOOLS_BY_NAME` | `local_tools.py:27,36` | zero production consumers beyond this; `local_tool_defs()` becomes `[COMPOSE_PROSE_TOOL]` |
| `_studio_panel_tool` | `eval/run_lazy_context_ab_eval.py:28` | v2 studio tool, private import — re-point |
| `PROPOSE_EDIT_TOOL` + the 7 `ui_*` defs | the ai-gateway-down fallback | this is `D-P3-RETIRE-UI-FRONTEND-DEFS`; retiring it means sourcing the advertisement from the catalogue |

**Two tests become vacuous and must be rewritten, not deleted:**
- `test_frontend_tools_contract.py:74-78` — `CLOSED_SET_ARGS` contains only v1 tools, so
  `test_closed_set_args_are_enums` becomes an empty parametrize that passes forever.
- `test_cp5_localtools.py:43,57,67,80,115,117` — parametrised over `local_tool_defs()`, which shrinks
  to one tool; `:117`'s arithmetic assertion still passes while covering almost nothing.

**Historical ledgers are NOT rewritten:** `agent-runtime-toolv2-ledger.json`,
`tool-deep-dive-ledger.json`, `tool-call-outcomes.json`, `tool-resolution-problems.json`. They record
what was true when measured. Editing them to make v1 disappear destroys the evidence trail.

---

## V8 · Manifest

`glossary_propose_entity_edit`: `admitted` → `deprecated` → `retired`, via the state machine
(`app/agentruntime/contract.py:98-103`). Two moves, not one — `admitted → retired` is legal but skips
the sunset window; take it deliberately or not at all.

**Irreversible.** Resurrection is deliberately absent from `LIFECYCLE_MOVES`; a returning declaration
is a new admission against the current contract.

`confirm_action` and `glossary_confirm_action` are **not** in the manifest — no lifecycle move applies.

---

## V9 · Deprecated-is-dead — DONE 2026-09-03, and it was not what the plan said

> 🔴 **THE PLAN'S PREMISE WAS HALF WRONG.** V9 said *"`tool_load` currently labels a legacy tool
> rather than refusing it"* — taken from `tool_discovery.py:1270`, which is `visible_tools`, a
> different function. What `tool_load` actually does depends on the catalogue it is handed, and
> that is `drop_superseded_tools`' OUTPUT: since 2026-08-25 **every legacy tool is already gone
> from it**. So the labelling branch only ever fires for a **pinned** tool — which DQ-V3 keeps.
>
> **Measured against the live catalogue rather than reasoned about:**
>
> ```
> tool_load("book_get")  unpinned ->  {"not_found": ["book_get"]}
>                        pinned   ->  deprecated: True, superseded_by: book_read   ✓ correct
> ```
>
> **The real defect is the first line.** `book_get` exists, is federated, and declares
> `superseded_by: book_read` — and `tool_load` told the model it does not exist. That is the same
> false premise `tool_load_result`'s own docstring records as costing the 2026-07-23 incident
> (*"the model reasoned correctly from that false premise and gave up on a tool that exists"*),
> reached from the other direction: there because a provider was down, here because the tool was
> deprecated. A model told "no such tool" stops looking; told "deprecated, use `book_read`" it
> calls the successor — which is the whole point of dropping the predecessor.

**Built:** `tool_load_result` takes a `legacy_index` and answers a dropped legacy name with a
`deprecated` bucket naming its successor plus a `deprecated_note`, instead of `not_found`. The
index is built at the call site from `knowledge_client.get_tool_definitions` (per-user cached, so a
cache read, not a federation call) because `discovery_catalog` by construction contains no legacy
tool to look up. Degrades to today's behaviour if the lookup fails — never fails the turn.

`deprecated_note` is a **distinct key** from `note`: the provider-outage branch also writes `note`,
so a request mixing a deprecated name with an unresolvable one during an outage would have silently
lost whichever wrote first. That collision needs an outage to reach — my first test asserted `note`
was always set, which was wrong, and the corrected test drives the outage path explicitly.

**Falsifier:** `tests/test_a_deprecated_tool_is_refused_not_declared_absent.py` (6 tests). Proven
RED by disabling the branch — 4 red, and the **2 controls stayed green** (a genuinely absent name
still says `not_found`; a pinned legacy tool still LOADS), so the suite discriminates rather than
merely failing.

**`pinned_legacy` untouched, per DQ-V3.** A pin keeps the tool in the catalogue, so it loads
normally and never reaches the refusal branch.

### X5 · My first V9 implementation was rejected by the repo's own instrument — correctly
The first version fetched the index inside the tool_load handler:
`await knowledge_client.get_tool_definitions(user_id)` wrapped in `except Exception -> {}`. The
targeted tests passed. The full suite went **6 red**, all in `test_cp0_instrument.py`, on two
counts I had not considered:

1. **An unregistered catalogue narrowing.** `_stream_with_tools` (lines 4492..9303) carries **no
   `arm_turn_surface()`** — it is covered by delegation from `stream_response`, which arms at
   :9574. A catalogue read placed inside it therefore registers nowhere:
   *"zero means every narrowing in this turn registers nowhere."*
2. **A silently swallowed outage.** The bare `except -> {}` degraded a catalogue failure without
   registering it — the exact U-2A seam
   (`TestU2ACatalogueOutageIsRegistered::test_EVERY_catalogue_path_registers_on_a_real_failure`).

**The fix was not to appease the guard but to stop making the call.** `legacy_tool_index` is now
built at the drop site in `stream_response` — the only point where the pre-drop catalogue still
exists — and threaded down as a parameter. No catalogue read on the handler path, no `except` to
swallow, nothing to register. It is bound to `{}` *before* the `if discovery_eligible:` branch that
fills it, so the non-discovery path degrades to today's `not_found` instead of raising NameError.

`test_cp0_instrument.py`: **152 passed.** This is the guard doing exactly what it was built for,
against a change whose own targeted tests were green.

### What remains for the original V9 framing

- `tool_discovery.py:1270` — `tool_load` currently *labels* a legacy tool (`entry["deprecated"]=True`)
  rather than refusing it. Make it refuse and name the successor.
- `tool_surface.py:957-961` — `pinned_legacy` re-admits a pinned legacy tool on every turn of the
  session. **Recommendation is to keep this** as an explicit user escape hatch (DQ-V3); if kept, D5 is
  reworded to "unreachable by the model unaided".
- ai-gateway's raw `tools/list` (`handlers.ts:40-80`) returns the catalogue verbatim with no
  visibility filter. That is correct for a catalogue endpoint — the filter belongs in discovery — but
  it must be *documented* as such, or the next audit reports it as a leak.

---

## V10 · Enforcement

Land G1…G6 from the spec §5. Each gate must be proven **red on an original instance** before it is
accepted — a gate that has never failed is a gate nobody has tested.

> Three vacuous guards were found in this repo in one day: a regex that matched its own docstring, and
> two substring assertions that survived the fix being deleted. For each of G1…G6, delete the fix and
> confirm the gate goes red. If it stays green, the gate is theatre.

---

---

## DISCOVERED DURING V0 — pre-existing, not caused by this work

### X1 · `test_a_measured_turn_reaches_its_tool_gate.py` is RED at HEAD (2 tests)
Found while running the owning suite for R1. **Not introduced by this plan** — it reads
`contracts/tool-catalog-cache.json`, the scenario corpus and two baselines, none of which V0 had
touched at the time, and it fails identically against HEAD's cache and a freshly refreshed one.

```
test_no_new_measured_turn_fails_to_reach_its_own_tool   FAILED
test_no_NEW_scenario_turn_fails_to_reach_its_own_tool   FAILED
```

Six tools whose measured turn cannot reach them, against
`contracts/unreachable-measured-turns-baseline.json`: `book_chapter_create`, `book_get`,
`glossary_extract_entities_from_doc`, `kg_project_create`, `registry_update_skill`,
`translation_coverage`.

**I first assumed the stale cache (R4) was the cause. It was not** — refreshing the cache changed
nothing here. Two hypotheses remain, and neither is verified:
- the baseline predates the 2026-08-25 legacy-drop widening (only `book_get` of the six is legacy,
  so this explains at most one row); or
- the 2026-09-02 DQ-T76 / softsweep scenarios added turns whose wording does not reach their tool
  — note `kg_project_create`'s row carries *"Record that Aldric Vane and Mira Solene know each
  other"*, which is `scenarios-t76-wave1-after.json`'s prompt for **`kg_propose_edge`**, not for
  `kg_project_create`.

The gate is shrink-only by design and describes itself as *"a BASELINE, NOT A HARD FAILURE"*.
**Do not widen the baseline to make it green** — that is the move its own header warns against.
Out of scope for V0; triage separately before V10, since G1's reachability logic overlaps it.

### X2 · The anti-vacuity guards fail BECAUSE the loop finished — `scripts/` is 24-red at HEAD
Found running the full `scripts/` suite for R1: **24 failed, 947 passed**. One was mine and is
fixed (see below). The rest are one class, and it is worth understanding rather than silencing:

```
"no row is in ANY non-terminal state — is the ledger really finished?"   assert {}
"progress reports no non-terminal defects at all — is that true?"        assert 0 > 0
"the ledger has NO open questions at all — the generator has nothing to
 be right about, and this guard would pass vacuously"                    assert set()
"the derived set adds nothing over the hand-typed list"                  assert set() - {...}
```

Each guard was written to stop *itself* passing over an empty population — the repo's own
non-vacuity standard (NV-1..6). But each encodes that as **"the population must be non-empty"**,
which is true while work remains and false the moment it is finished. The ledger reached 0 open
defects / 0 open DQs / 0 non-terminal rows on **2026-09-02**, before this plan existed.

**So a completed loop leaves its own suite permanently red.** That matters to this plan directly:
the goal's EVIDENCE clause requires "whole owning suite green", and V10 requires each new gate be
proven red-able — neither is expressible against a suite that cannot go green.

**The fix is a design decision, not a patch:** an anti-vacuity guard needs a *finished* mode —
`pytest.skip("population legitimately empty: <derived count> == 0")` — so it distinguishes "this
guard is measuring nothing because it is broken" from "this guard is measuring nothing because
the work is done". Silencing them by deleting the assertions re-opens the vacuity hole they exist
to close. **Owner decision required before V10.**

### X3 · My own R2 fix was caught by an existing test — recorded because the catch was correct
`test_the_last_batch_regex_sees_both_naming_conventions` went red on my first R2 derivation.
Ordering evidence by `(directory-date, stem)` is right *across* days and wrong *within* one:
`batch40.json` and `b41-norail.json` share 2026-08-14, and a string max picks `batch40`, losing
the ordering the old regex got right. Corrected to `(date, batch-number-if-any, stem)` — the date
is structural and primary, the number is the secondary key. Both the synthetic case and the real
ledger (`softsweep4 (2026-09-02)`) now derive correctly.

Each was found by inventory, not by theory. Each breaks something silently.

### T1 · `deprecated-tool-scan.py` ordering — scrub the PROMPT first
`scripts/deprecated-tool-scan.py:58-62` `_CORE_EXTRA` is the live-tool allowlist and contains all
three v1 names. `test_skill_registry.py:549-580` asserts every tool a system skill names exists in
`build_catalog()`. The glossary skill prompt names them at 9 lines.

> **Remove the names from `_CORE_EXTRA` before scrubbing the prompt and the whole glossary skill
> goes red.** V3 (prose) strictly before any allowlist edit.
> **And the test SKIPS — never fails — if the scanner is unreachable or returns <100 tools
> (`:578-580`).** A partial edit hides behind a green skip. Assert the skip did not happen.

### T2 · Seeded production rails live in a MIGRATION, not a fixture
`services/agent-registry-service/internal/migrate/migrate.go:507`, `:602` seed rail steps with
`{"tool":"glossary_confirm_action","gate":"confirm"}`, and seeded skill prose at `:510`, `:536`,
`:610` instructs the agent to call it. `migrate_lint_test.go` lints rail *structure*, not tool
existence — **nothing goes red**; the rails simply point at a tool that cannot be called.

> **DDL added to an already-applied ledger step is a silent no-op.** This needs a NEW migration
> step, never an edit to the applied one. `test_mode_binding.py` and `test_rail_progress.py` mirror
> these rails and must move in the same slice.

### T3 · The `frontend_tool_schemas` metric loses its only vehicle
`test_stream_tools.py:2050-2074` asserts `split["frontend_tool_schemas"] > 0` using `confirm_action`;
its comment records that `propose_edit` was already swapped out of this role in Phase 2. With v1
gone there is no third tool, and the metric becomes structurally always-zero.
**Decide whether the metric survives before deleting the test.**

### T4 · The falsifiers anchor on literal source text
`scripts/agentruntime_falsifiers.py:2504-2545` injects drift into `frontend_tools.py`'s `_meta` lines
and `local_tools.py`'s `_ALL_FRONTEND_TOOLS_BY_NAME` to prove two tests red-able. Those anchors
vanish with v1, and **a falsifier that cannot find its target reports success**.

### T5 · `confirm_action` is FOUR things
v1 tool (`frontend_tools.py:562`) · domain HTTP route handlers
(`composition/app/routers/actions.py:247`, `translation/…:261`, `knowledge/…/kg_actions.py:364`) ·
the public edge's own MCP tool (`mcp-public-gateway/src/scope/confirm-action.ts:38`) ·
a suffix predicate (`scripts/cp5-residual.py:59` `tool.endswith("confirm_action")`).
**Only the first is v1.** Also: `mcp-public-gateway/src/scope/invoke-tool.ts:150-160` *rewrites*
`glossary_confirm_action` → `confirm_action` in federated descriptions; that becomes dead code when
V3 lands, and it fails safe.

---

## VACUITY REGISTER — tests that go GREEN while asserting nothing

Removing v1 empties the sets these iterate. An empty `parametrize` **collects zero tests and reports
no failure**. Every row here must be re-pointed or deleted, never left passing.

| Test | Why it goes vacuous |
|---|---|
| `test_frontend_tools_contract.py:119` | `set(FRONTEND_TOOL_NAMES) == set(ALL_FRONTEND_TOOLS)` → empty == empty |
| `test_frontend_tools_contract.py:121-141` | two empty parametrizes — **including the LOCKED "closed-set arg ⇒ enum" rule**; `CLOSED_SET_ARGS` has only v1 entries |
| `test_frontend_tools_contract.py:143-166` | iterates an empty dict; the committed contract JSON then drifts unchecked on the chat-service side |
| `test_frontend_tool_validation.py:113-127` | loops `FRONTEND_TOOL_NAMES`; the "no frontend tool may skip the validation seam" gate becomes a no-op |
| `test_cp5_localtools.py:43-60, :119-123` | parametrised over `local_tool_defs()`, which collapses 4 → 1 |
| `test_frontend_tools.py:53-58, :111-113, :152-173` | negative assertions against a permanently empty set |
| `test_stream_service.py:1357` | negative list naming tools that cannot exist (already half-vacuous today) |
| `test_admin_surface.py:246, :352` | negatives go inert once the tool cannot be advertised anywhere |
| `test_rail_progress.py`, `test_mode_binding.py` | fixture rails naming a nonexistent tool; `compute_rail_progress` never validates names |
| `test_a_frontend_tool_gets_the_same_id_repair.py` | never imports `frontend_tools`; passes forever about a tool that no longer exists |

> **If `is_frontend_tool` is DELETED, rows 6-8 go red instead of vacuous — which is what we want.
> If it is kept returning `False`, they go silently green.** Prefer deletion.

---

## Decisions register

## VS · SDK promotion — PROMOTION DONE 2026-09-03 (adoption still to come)

**One Python store, one Go store, three services re-pointed, all suites green.**

| | before | after |
|---|---|---|
| Python | `composition/app/mcp/pg_task_store.py` | `sdks/python/loreweave_mcp/pg_task_store.py` |
| Go | `book/internal/api/mcp_gate_task_store.go` + `glossary/…` (drifted, 66 lines apart) | `sdks/go/loreweave_mcp/pgstore/pg_task_store.go` |

Suites: composition **3988 passed**, book **exit 0 / 0 FAIL**, glossary **exit 0 / 0 FAIL**,
kit `go build ./...` + `go vet ./pgstore/` clean.

**DQ-V6 decisions taken here, and why:**
- **Python: added to the kit but NOT exported from `__init__.py`.** That module imports its
  submodules eagerly, so registering it would put `asyncpg` on the import path of every kit
  consumer, most of which never touch Postgres. Consumers import it by path;
  `asyncpg` stays optional.
- **Go: a `pgstore` SUBPACKAGE, not the kit root.** Go has no lazy import, so the root would carry
  `pgx` for everyone. Measured before choosing: **every Go service that already depends on
  `loreweave_mcp` also already depends on `pgx`**, so no consumer gains a dependency it lacked,
  and one that never imports `pgstore` never links it.

### 🔴 THE PROMOTION NEARLY SHIPPED THE WORSE COPY
I promoted **book's** Go store because it was the original. It is not the better one. Glossary's
copy carried a fix book's lacked — on an expired task it returns

> `%w — it EXPIRED (its %dms TTL lapsed before anyone answered it); re-run the action that
> proposed it to get a fresh task`

where book's returns a bare `ErrTaskNotWaiting`. Measured when glossary wrote it: 60 tasks sat in
`input_required`, one whose 10-minute TTL had lapsed **17 days** earlier, and declining it answered
"task is not awaiting input" while the same call wrote `error='task_expired'` onto the row. The
reason was computed, persisted, and withheld.

Both services *built* against the book-only version, so nothing failed at compile time. **What
caught it was diffing the two copies before trusting either** — and then glossary's own guard,
which went red because it read a path I had deleted. Merged as the superset; the guard moved into
the kit beside the code it guards and passes there.

> **A promotion must carry the SUPERSET.** Picking "the original" is picking by provenance, not by
> content — and drift means the newer copy is often the corrected one.

---

## V6 + V7 teardown — DONE 2026-09-03 · **D1, D2, D3 ALL PASS**

`services/chat-service/app/services/frontend_tools.py` **is deleted.** Suite: **3878 passed, 0
failed**. `D-P3-RETIRE-UI-FRONTEND-DEFS` closes with it — the `ui_*`/`propose_edit` residue it
tracked since P3.2 went in the same deletion.

Justified per SYMBOL, not assumed: `PROPOSE_EDIT_TOOL`, both `ui_*` defs and
`frontend_tool_def_by_name` each had **zero** production references once `frontend_tool_defs`
stopped advertising. The whole module was dead, not just its v1 half.

- The v1 intercept (**181 lines**) removed via **AST**, so the boundary was exact and the other six
  suspend producers were untouched.
- The advertise fallback `catalog_index.get(name) or generic_frontend_tool_def(name)` → catalogue
  only. **That `or` is why a chat-service-local schema reached the model on every turn for weeks**:
  `confirm_action` was absent from the catalogue, so the fallback always fired.
- The gateway-down branch DELETED, not emptied — every tool it re-advertised dispatches *inside*
  ai-gateway, so with the gateway down it offered tools that cannot execute (CD4: worse than none).
- `is_browser_executed` re-homed to `app/services/browser_tools.py`, membership named explicitly
  rather than by prefix (a `glossary_` rule would sweep the real glossary-service tools).
- The dead schema dicts became `tests/_v1_tool_fixtures.py`, headed with the warning that they are
  **not a source of truth**, naming each one's live owner and the contract as SoT.
  `is_browser_executed` is **re-exported from its real home**, never copied, so a test cannot drift
  from the live predicate.

### 🔴 THE TEARDOWN CREATED A DEAD MECHANISM, AND FINDING IT WAS THE POINT
`_UNRESOLVED_ID_RE` was left **defined and never read** — its only consumer was the deleted branch.
It classified a refusal as `unresolved_identifier`, the distinction that keeps a call refused for a
fabricated id out of the FAILURE count (CP-5.4: 101 calls at 0% that were refusals, inflating every
rate over the corpus). Verified the kind exists in **no contract**, and that its input class is
handled *better* on the surviving path — CP-5.3 **resolves** the name to an id instead of
classifying the refusal. Regex, its two tests and its two falsifier scenarios were retired together.

### The repo's own guards drove the rest, one refusal at a time
1. The falsifier guard **demanded red-ability** for the tests I renamed.
2. The stale-anchor guard found **four** falsifier scenarios pointing at deleted source.
3. When I wrote the two new falsifiers I **proved them red** — injecting
   `glossary_propose_entity_edit` back into chat-service's own set turned all four relevant guards
   red, including the two just written.
4. The manifest format guard **rejected my explanatory key**: *"an unknown key is not a newer file,
   it is one this reader cannot make claims about."* The reasoning belongs here, not in the data.

`test_frontend_tool_validation.py` was retired only after confirming its subject arrived elsewhere:
**44 cases across ai-gateway's three specs** (15 + 15 + 14).

---

## V4 + V7 chat-service half — DONE 2026-09-03 · **D2 PASSES**

`FRONTEND_TOOL_NAMES` is empty; `confirm_action` is out of `ALWAYS_ON_CORE_NAMES`;
`task_detect.gated_directive_suspend_args` detects the two new markers from the tool RESULT and
suspends with the SAME `(name, args)` the v1 intercept froze — so `ConfirmActionCard`,
`GlossaryDiffCard`, the admin card and the resume driver need no change.

**Live-wire proof** (`refresh_tool_catalog_cache.py` against a rebuilt gateway):

```
live catalogue : 319 tools      (was 316)
  added   : 3 ['confirm_action', 'glossary_confirm_action', 'glossary_propose_entity_edit']
  removed : 0
[PASS] D2  v1_in_federated_catalogue: all three True
```

### 🔴 EMPTYING THE SET SILENTLY BROKE A SAFETY PROPERTY
`is_browser_executed` answered True for these three only *because* they were in
`FRONTEND_TOOL_NAMES`. Emptying it flipped them to False, and two consumers changed behaviour with
nothing failing loudly:

- **`subagent_runtime.resolve_scoped_tools` stopped excluding them** — a HEADLESS sub-run was being
  handed a human-gate tool with no human to gate on. It can only hang or be answered dishonestly.
- `agent_surface` stopped routing them to the `ui` server bucket.

Caught by `test_subagent_runtime.py:69`, whose assertion is a NEGATIVE (`not in`) — the shape that
usually goes vacuous rather than red. Here it went red because the tools appeared where they must
never appear. Fixed at the predicate: the three joined `_BROWSER_EXECUTED_EXTRA` beside
`propose_edit`. **Moving a tool's HOME must not change WHO EXECUTES it.**

That same fix also resolved trap **T3** for free — the `frontend_tool_schemas` metric keys on
`is_browser_executed`, so it stopped being structurally zero and the metric survives the move.

### Test re-pointing — the property, never the phrase
`test_stream_tools.py` pinned the literal string `"required: missing properties"`, the Phase-0
validator's wording. Federated, the refusal now reads *"is missing required argument(s): [...] Do
NOT guess a value and do NOT substitute a placeholder"* — strictly better. The safety property
(rejected, never suspended, backend never called) never changed. Re-pointed to assert IN-6's
property — the refusal NAMES the missing arg and says what is wrong — so an improvement to the
sentence no longer reds the suite.

`test_tool_discovery` now asserts `FRONTEND_TOOL_NAMES == set()` **and** that the three are still
browser-executed, rather than being deleted: emptiness is the clause that would go quietly true
again if someone re-added a name, which is the whole failure mode v1 was.

---

## V7 · ai-gateway half — DONE 2026-09-03

`services/ai-gateway/src/mcp/confirm-tools.ts`: the three KIND-C tools as consumer-local
**directive** tools, wired in `handlers.ts` (advertised + dispatched + `consumerLocalTools()`).
Suite: **283 passed, 1 failed** — the one failure (`find_tools`) fails **alone at HEAD** with only
my two untracked files present, so it is pre-existing (recorded as X6).

`test/confirm-tools.spec.ts` (11 tests) asserts the thing a refactor here can silently destroy:
the returned directive carries **no** `status`/`result`/`job_id`/`applied`/`outcome`, the prose
tells the model to report success *only* on `action_done`, the three directive markers are
mutually distinct, and `glossary_confirm_action` **cannot be redirected** at another domain by
passing one. Proven RED by disabling the domain enum — 1 red, 10 green, so it discriminates.

**The definitions were GENERATED from the live chat-service defs, not retyped.** Each description
runs to several hundred characters, and a description decides *when* a weak model reaches for a
tool — a transcription slip is a behaviour change no schema test catches.

### 🔴 ADVERTISING A TOOL AND MAKING IT DISCOVERABLE ARE TWO SEPARATE WIRINGS
Adding the three to the advertised array left them invisible to `tool_list`, and **K23 caught it**:
*"tool_list enumerates every tool tools/list serves"* went red with exactly my three names. A model
narrowed to the discovery pair could have been served a tool it could never find — the blind spot
F17 retired `find_tools` to escape. Fixed at `consumerLocalTools()`, not by editing the guard.

Two other reds were legitimate: `handleListTools` pins the advertised array by **order**, not
membership, so it had to learn the new entries. Updated the expectations, not the assertions.

---

## 🔴 DQ-V5 IS OVERTURNED — DQ-V9, decided under DQ-V6 authority 2026-09-03

**The owner ruled DQ-V5 "split: the 2 confirms → glossary-service MCP tools". That ruling is
architecturally unsafe and I am not implementing it. Overrule me in review if you disagree —
this is exactly the case DQ-V6 exists for.**

**Why it cannot stand.** A glossary-service MCP tool has a **server executor**: the model calls it
and the server performs the write. `confirm_action` and `glossary_confirm_action` exist to *be the
human gate* — the card is rendered, a person clicks, and the BROWSER posts to
`POST /v1/<domain>/actions/confirm`. Give them a server executor and the model can complete its own
confirmation with no human in the loop. That deletes the gate the tools exist to provide, and it
would do so while every test still passed, because nothing asserts "a human was involved".

All three v1 tools are browser-executed: `is_frontend_tool` ⇒ `is_browser_executed`
(`frontend_tools.py:723-732`).

**DQ-V9 — the revised ruling: all three become ai-gateway consumer-local DIRECTIVE tools**,
mirroring `propose_edit`'s already-proven P2.2 pattern
(`services/ai-gateway/src/mcp/propose-edit-tool.ts:10-23`):

> *"PROPOSAL DIRECTIVE … the client must GATE on the human (Apply/Dismiss) … there is no server
> executor (contrast KIND-C's durable gate)."*

That shape satisfies every clause without weakening anything:

| | |
|---|---|
| **D1** | `frontend_tools.py` dies — no schema left in chat-service |
| **D2** | the tools are advertised by ai-gateway, not `generic_frontend_tool_def` |
| **D3** | the manifest row's owner becomes ai-gateway |
| **GATE-2** | the human gate is preserved, and `confirm_action` keeps redeeming bare `confirm_token`s |

### And this unblocks the whole back half of the plan
I had recorded V4/V6/V7 as blocked on D4, reasoning that withdrawing `confirm_action` would strand
the 12 ungated sites. **That was wrong.** D2 requires that nothing *chat-service-local* reaches the
model — not that `confirm_action` disappears. Re-homed as a gateway directive tool it is still
advertised and still redeems tokens, so **D1/D2/D3 do not depend on D4 at all.**

Consequence for ordering: **V7 now comes before the remaining gate work.** D4's 12 sites are a
separate concern (the ext-tasks rollout) that no longer gates v1 retirement.

---

### ROUND 2 — ruled 2026-09-03 after the first run stalled

The first goal **stalled**, and the fault was in its design, not in the work: its QUEUE held items
gated on owner decisions and its STOP required all of them, so every gate became a stopping point.
Ruled:

| id | Question | Ruling |
|---|---|---|
| **DQ-V6** | What do I do when I hit a decision mid-run? | **DECIDE IT MYSELF, RECORD IT, CONTINUE.** Never stop for a decision — including irreversible ones. Write the ruling and its reasoning into this register; the owner reviews the final report once everything is complete and overrules anything they disagree with. |
| **DQ-V7** | translation + provider-registry need a task store that is copy-pasted 3× and lives in no SDK | **PROMOTE IT.** `PgTaskStore` → `sdks/python/loreweave_mcp` and `sdks/go/loreweave_mcp`, re-point book/glossary/composition at the kit, then gate the remaining 5 sites. It is the biggest slice in the plan and it pays down a real triplication. |
| **DQ-V8** | 24 `scripts/` tests fail *because the loop finished* | **FINISHED-SKIP MODE.** Each anti-vacuity guard gains `pytest.skip("population legitimately empty: <derived> == 0")` so it distinguishes "measuring nothing because I am broken" from "measuring nothing because the work is done". Keeps NV-1..6 intact and makes "whole owning suite green" expressible again. |

> **DQ-V6 is the load-bearing one.** Under it there are no blocked slices — only slices whose first
> step is a decision I take and record. A queue item may still turn out to be wrong; it may not
> turn out to be *pending*.

---

**All five ROUND-1 questions RULED by the owner 2026-09-03. The spec is SEALED. Do not re-litigate.**

| id | Question | Ruling |
|---|---|---|
| DQ-V1 | Do the 3 names stay in `frontend-tools.contract.json`? | **RETAIN** + rename the contract to FE card-rendering ownership |
| DQ-V2 | Does translation-service adopt the tasks gate? | **ADOPT** — no exemption; all 4 sites open tasks |
| DQ-V3 | Does "deprecated is dead" mean unloadable? | **`tool_load` REFUSES** + names the successor; **`pinned_legacy` KEPT** |
| DQ-V4 | Re-home or retire the synthesised batch-cap card? | **RE-HOME as `batch_confirm`**, in the slice that moves the tool |
| DQ-V5 | Where do the three tools land? | **SPLIT** — the 2 confirms → glossary-service MCP tools; `glossary_propose_entity_edit` → ai-gateway directive tool |

**What the DQ-V5 ruling unblocks:** V6 and V7 can start. `frontend_tools.py` is deleted outright
rather than left returning `False` — which also turns the vacuity register's rows 6-8 **red instead
of silently green**, the outcome the register asks for.

## Open questions the inventory could not settle

1. Do `AssistantMessage.tsx:302`/`:322` need re-pointing? Depends on whether a v2 confirm tool arrives
   as a **pending** record and under what name. Wrong answer ⇒ duplicate confirm cards.
2. Do `agentruntime_arm` turns reach the v1 intercept? `stream_service.py:1863` returns early from the
   *advertise* chokepoint, but `:7143` is on the shared dispatch path. Trace before assuming.
