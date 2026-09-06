# RT2 — Red team on A2 (the collapse), A4 (sub-agent under free text), A11 (the FSM lane)

**Mandate:** falsify, not grade. Every claim below carries `file:line` from this tree
(branch `feat/frontend-tools-mcp-migration`, HEAD `24dd7bdac`).

**Headline number: the honest decomposition lands at 76 advertised entries, not ~20.**
13 coarse job capabilities + **51 writes that refuse to collapse** + 12 per-domain searches.
The 51 is the finding; the 76 is the consequence.

---

## 0 · Method — how the numbers were derived

The `198`/`118` figures in `DESIGN-HYPOTHESIS.md:56-57` have no cited derivation. I re-derived
them mechanically from the registration sites, reusing the catalog scanner's own regexes
(`scripts/deprecated-tool-scan.py:67-138`) extended to also read `_meta.tier`:

```
305 registered · 191 advertised · 114 legacy
advertised by tier: A=84  R=73  W=33  ?=1
advertised writes (A+W+S) = 117
```

So **117 of 191**, not 118 of 198 — the spec's shape is right and its arithmetic is close
enough. The gap to the audit's `202 advertised` (`audits/04-mcp-servers-federation.md:78`) is
the 11 consumer-local names in `_CORE_EXTRA` (`scripts/deprecated-tool-scan.py:59-62`), which
are meta-tools, not product writes. **Nothing below depends on the exact total.**

Scanner and assignment table are reproducible; the assignment rule is the spec's own §2.2
four-part test (`SPEC.md:214-228`).

---

## A2 — "the product fits in ~20 advertised tools" · **KILLS**

### A2.1 The decomposition, done

I assigned all 117 advertised writes to a capability, using the *most generous* possible
reading of "coarse job" — anything with ≥2 steps and a plausible whole-job assent goes in.

| kind | count | detail |
|---|---|---|
| **JOB capabilities** | **13** | glossary_build(7), kg_build(8), plan_forge(9), compose_draft(6), arc_design(6), motif_work(4), translate_book(5), world_build(7), canon_check(2), derivative_make(5), book_structure(2), authoring_run(2), lore_enrich(1) — **64 tools absorbed** |
| **ATOMIC — refuse** | **51** | destructive/confirm-token 13 · human-in-the-loop 21 · interrupts 4 · user control-plane 9 · hash-gated apply 4 |
| unassigned | 2 | `world_map_update_marker`, `world_map_update_region` (direct-manipulation; see A2.3) |
| **searches** | **12** | one per read domain (book, catalog, composition, glossary, jobs, kg, memory, plan, settings, story, translation, world) |

**13 + 51 + 12 = 76.** The falsifier in `DESIGN-HYPOTHESIS.md:60` says *"an honest decomposition
that lands at 60+"*. It lands at 76 — and 13 job capabilities is already **63% over the stated
~8** before a single refusal is counted.

Note the direction of the error: even the JOB half misses. The spec says ~8; the domains do not
merge below 13 because `plan_forge` and `compose_draft` and `arc_design` are different *products*
inside composition-service, not different phrasings of one job.

### A2.2 Which writes refuse, and why — the load-bearing list

**(a) Confirm-token / destructive — 13.** These cannot be inside a job capability because the
Go kit makes the confirm route the *only* write path:

> "The propose tool mints it (**no write**); the per-domain `/v1/<domain>/actions/confirm` route
> verifies it and is the **ONLY write path (INV-9)**."
> — `sdks/go/loreweave_mcp/confirm_token.go:20-23`

A capability that "runs the whole job" and contains a Tier-W step must either suspend mid-job for
a human confirm (so it is not one call), or bypass INV-9 (so it is a security regression).
33 of 117 advertised writes (28%) are Tier-W. Members include
`glossary_entity_delete`, `glossary_ontology_delete`, `world_delete`, `world_map_delete`,
`settings_model_delete`, `book_steering_delete`, `memory_forget`, and all four
`glossary_admin_propose_*`.

**(b) Human-in-the-loop — 21.** The whole point is that the *user* decides the next step:

- `propose_edit` / `glossary_propose_entity_edit` / `confirm_action` are **executed by the
  browser, not the server**: the tool loop *suspends*, streams the call to the client, and
  *"the 'execution' is the human reviewing the proposed edit and clicking Apply/Dismiss —
  human-in-the-loop tool calling"* — `services/chat-service/app/services/frontend_tools.py:1-9`,
  set at `:47-79`, marker `is_browser_executed` at `:695-714`.
- `kg_triage_resolve` is explicitly per-item and explicitly bounded away from anything a job
  could decide: *"Schema-changing actions … are NOT available here — those need explicit human
  confirmation via the review surface"* — `services/knowledge-service/app/mcp/server.py:1334-1340`.
- `translation_patch_block` — *"Correct **ONE** translated block"* —
  `services/translation-service/app/mcp/server.py:545-550`.
- Plus `plan_review_checkpoint`, `plan_interpret_feedback`, `composition_authoring_run_review`,
  `composition_error_block_edit`, `glossary_propose_curation`, `book_chapter_restore_revision`.

**A text-in capability cannot serve these because the missing input is not text — it is a click
on a specific diff.** `SPEC.md:232` concedes exactly this class ("human-in-the-loop editing where
the user's next utterance determines the next step") and then A2 counts them anyway.

**(c) Interrupts — 4.** `jobs_cancel`, `jobs_pause`, `translation_job_control`,
`composition_authoring_run_manage`. These must be callable *while* a job runs. A coarse
capability implemented as one blocking tool call makes its own cancel tool unreachable for the
duration (see A4.3). This is a structural contradiction, not a count problem.

**(d) User control-plane — 9.** `settings_model_*` (6), `settings_update_profile`,
`book_steering_set`, `memory_remember`. Registering a provider model is per-change assent over
the user's own credentials; there is no artifact and no `done_when`. Failing §2.2 condition 3 and 4.

**(e) Hash/version-gated apply — 4.** `glossary_book_sync_apply` and `kg_sync_apply` require a
`base_source_hash` read from the matching `*_sync_available` call
(`services/chat-service/app/services/knowledge_skill.py:48`); `book_update_details` and
`glossary_adopt_standards` are Tier-W previews. A free-text call cannot carry the hash, and if
the capability re-reads it internally the concurrency guard becomes a blind clobber.

### A2.3 A capability whose text interface becomes a DSL — the second falsifier, also hit

`DESIGN-HYPOTHESIS.md:60` also fails A2 on *"a capability whose text interface cannot express a
real user request without becoming a DSL."* The map tools are that capability:
`world_map_add_marker` / `world_map_update_marker` / `world_map_add_region` /
`world_map_update_region` (advertised, Tier-A, `scope=none`). A marker's input is an
**(x, y) from a click**. "Put a marker on the mountain" either round-trips to the user for
coordinates (so it is not one call) or the text has to carry `x=0.42,y=0.71` — which is a DSL.

### A2.4 "One search per domain" is not 12 existing tools — it is 5 new ones

Of the 12 read domains, **five have no search tool at all**: `catalog`, `jobs`, `settings`,
`translation`, `world` (also `lore_*`). `composition` has two partial ones
(`composition_find_references`, `composition_motif_search`) and neither is a general search.
So the "one search per domain" line item is not a consolidation of 73 reads — it is a
consolidation of ~50 plus **five-to-seven searches that must be built**, across
Postgres + Neo4j + object storage + vector (already flagged 🔴 at `DESIGN-HYPOTHESIS.md:88-89`).

### A2.5 Cheapest observation that settles A2

Take the assignment table above, hand the **51 ATOMIC rows** to the PO, and ask a single
question per row: *"is the user's assent to this call, or to a job containing it?"* Any row
answered "to this call" stays advertised. **A2 is false the moment that count exceeds 12**
(20 − 8 capabilities). It is currently 51. No code, no run, one hour.

---

## A4 — "a sub-agent handed free text preserves the correctness the sequence gave" · **KILLS**

The spec's evidence for A4 is that *"the boundary exists (`subagent_runtime.py::tool_scope` — the
only real tool whitelist in the repo)"* (`DESIGN-HYPOTHESIS.md:78-79`). I read that runtime. It is
a real whitelist. **It is also structurally incapable of running the capabilities A2 assigns to
it**, for six independent reasons, four of which are hard errors in the code.

### A4.1 There are ZERO sub-agents. The mechanism has never run in production.

`run_subagent` is advertised **only if the user already has ≥1 enabled persona row**:

- resolution: `stream_service.py:6354-6374` → `registry_subagents_client.get_subagents(...)`
- tool built only when the list is non-empty: `subagent_runtime.py:129-140`
  (*"Returns `None` when there are no subagents (tool absent)"*)
- storage: `subagent_defs` table, `services/agent-registry-service/internal/migrate/migrate.go:303-327`
- **there is no `INSERT INTO subagent_defs` anywhere in the migration** — the 12 workflows are
  seeded (`migrate.go:497-766`); the personas are not.

So the only path to a sub-agent is a user hand-authoring one in
`frontend/src/features/extensions/components/SubagentsView.tsx:30` and typing glob strings into
`tool_scope`. **The "only real capability boundary in the repo" has zero instances.** Its
correctness under free text is not "unmeasured" — it is *unexercised*.

That also means the boundary is not a **capability** boundary at all: `tool_scope` is a
user-editable JSONB column (`migrate.go:312`), validated only as "an array of strings"
(`services/agent-registry-service/internal/api/subagents.go:66-71`). A shipped capability
cannot be defined by a row the user can edit.

### A4.2 A sub-agent cannot execute a Tier-W write. At all.

`subagent_runtime.py:50-53`, and enforced at three call sites:

| gate | what a sub-run gets | file:line |
|---|---|---|
| Tier-W/S mint→confirm | cannot complete — `confirm_action` is browser-executed and scope-excluded | `subagent_runtime.py:91-99`, `stream_service.py:4621-4623` |
| un-allowlisted Tier-A in write mode | `result.error`, *"it was NOT run"* | `stream_service.py:3992-4012` |
| `require_approval` hook | `result.error`, *"it was NOT run"* | `stream_service.py:3799-3812` |
| Tier-A volume cap hit | `result.error`, *"stopping further auto-writes"* | `stream_service.py:3748-3765` |

Cross-referenced against A2's 13 job capabilities: **`compose_draft`, `translate_book`,
`canon_check`, `derivative_make`, `glossary_build` and `kg_build` each contain at least one
Tier-W step.** Six of thirteen capabilities cannot run to completion in the mechanism the spec
nominates to run them. `composition_generate` — the flagship "write me a chapter" — is
Tier-W with `async_job=True` and states outright that it *"generates NOTHING until the user
confirms via confirm_action"* (`services/composition-service/app/mcp/server.py:2689-2707`).

### A4.3 The budget is 4 iterations and 12 writes. A whole job does not fit.

- `SUBAGENT_MAX_ITERATIONS = 4`, effective cap `min(caller_cap, 4)` —
  `subagent_runtime.py:76`, applied `stream_service.py:4662`
- `MAX_TOOL_ITERATIONS = 5` (parent) — `stream_service.py:435`
- `TIER_A_SAME_OP_CAP = 5`, `TIER_A_AGGREGATE_CAP = 12` per run — `stream_service.py:457,463`
- `MAX_SUBAGENT_DEPTH = 1` — no nesting, no fan-out — `subagent_runtime.py:61`
- result truncated at `SUBAGENT_RESULT_CHAR_CAP = 4000` chars — `subagent_runtime.py:71`

`world_build` as I grouped it is 7 tools and a real world has ≥1 map with ≥5 markers — that is
>12 Tier-A writes in one run, i.e. it *hits the aggregate cap and returns an error mid-job*.
`plan_forge` is 9 ordered steps against a 4-iteration ceiling. **The capability does not fit in
the runtime the spec assigns it**, and the failure mode is a truncated partial write, which is the
worst available outcome (see `feedback_unconditional_success_that_discards_its_own_signal`).

### A4.4 Cost: up to 25 LLM round-trips in one turn, all billed to the caller

One parent turn is ≤5 iterations (`:435`); each iteration may call `run_subagent`; each sub-run is
≤4 nested iterations. Worst case **5 + 5×4 = 25 sequential model calls in a single user turn**, and
`total_input += sub_in; total_output += sub_out` (`stream_service.py:3307-3308`) debits them all to
the same turn budget. The sub-run also re-derives its own tool surface and re-budgets it
(`:4676-4678` forwards `context_length` only when the sub-model equals the parent model).

### A4.5 Not cancellable, no progress, no interrupt

`_run_subagent_call` is a **single blocking `await`** inside the parent loop
(`stream_service.py:3289-3306`). Inside it, the nested generator's chunks are consumed and
**discarded** — `content` is accumulated and *reset to `""` after every tool call*
(`:4691-4696`), tool names are collected into a list, and nothing is re-yielded upward
(`:4686-4703`). The parent emits exactly one activity afterwards:
`summary: f"Ran subagent '{…}'"`, `undo: {available: False}` (`:3322-3330`).

Consequences, all three of which A2 needs and none of which exist:

- **no progress** — the user sees nothing for the duration of ≤4 model calls
- **no mid-job interrupt** — there is no `cancel_check` in the loop; the only cancellation is the
  HTTP disconnect cascade for the entire chat stream (`stream_service.py:182-191, 7049-7071`),
  which kills the turn, not the job, and leaves partial writes committed
- **no undo** — `undo: {available: False}` is hardcoded on the sub-run activity, with the comment
  *"No undo — a delegate read"*. It is not a read once the caller's turn is a write turn.

### A4.6 The three capabilities the spec names by name each REQUIRE a human mid-job

`SPEC.md:169-171` and `DESIGN-HYPOTHESIS.md:77` name exactly three exemplars: *"PlanForge
end-to-end, world setup, glossary build."* All three are built, all three work, and **all three
have blocking human checkpoints in the middle of the sequence** — which fails §2.2 condition 4
("the user's assent is to the whole job") for the very examples chosen to demonstrate it.

| capability | the checkpoints | file:line |
|---|---|---|
| **glossary build** | FSM is `draft → planning → plan_ready → **[human approves]** → building → proposing → proposed → kg_projecting → **edges_ready** → done`; `approve_plan` is docstringed *"[human checkpoint #1]"*, and CP2/CP3 follow | `services/composition-service/app/services/glossary_build/service.py:3-4, 207, 242-257, 274-285` |
| **PlanForge** | `PASS_REGISTRY` = 7 ordered passes with `depends_on`; `cast` and `beats` are `checkpoint="blocking"` | `services/composition-service/app/services/plan_pass_service.py:55-89` |
| **composition generate** | `pause_after_each_unit: bool = **True**` — the default is stop-after-every-unit, plus `/gate`, `/units/{i}/accept`, `/reject` | `services/composition-service/app/routers/authoring_runs.py:104, 209, 341, 360` |

**"World setup" is not a fourth thing** — `frontend/src/features/world-setup/api.ts:1-8` posts to
`/v1/composition/glossary-build`. It *is* glossary build. So the exemplar list is two pipelines,
not three, and both are checkpointed.

Why the checkpoints exist is documented and measured, not decorative:
*"the deep path DOES invent (it named materials the source never gives) — which is precisely why
CP2 is a human, not a loop"* (`docs/plans/2026-07-27-glossary-build-pipeline.md:119-127`), with
the sibling rule *"a retry that can only succeed by producing text is a hallucination pump."*

### A4.7 The production code already REFUTES the "one call runs the job" shape — in a comment

The glossary-build driver deliberately does **not** hand the job to one model call, because doing
so was measured to collapse:

> "BATCH pass (measured 3× cheaper): only `standard` items, grouped by kind, only for kinds whose
> schema is already narrow — and **NEVER mixing kinds in a call (that is the E2 collapse)**."
> — `services/composition-service/app/services/glossary_build/service.py:444-447`

The E2 collapse it cites is the measurement: one call asked to do the whole breadth×depth job
degraded **monotonically 7 → 1 attributes** across 9 entities (`n_attrs` = 7,6,6,4,2,1,1,1,1 in
`eval/out/glossary_build_poc.json` → `E2_horizontal_naive.depths`; table at
`docs/specs/2026-07-27-glossary-kg-build-workflows.md:93-97`). The split
planner→executor arm (E3) got 13 entities at 5.7 attrs.

**A4's claim is that a sub-agent handed free text is "at least as correct as the model driving the
steps." The one place in this repo where that comparison has actually been run measured the
opposite, and the winning arm is compiled into the shipped driver as Python control flow.** The
driver is an in-process `asyncio` task (`service.py:259`), not a model loop — deliberately.

### A4.8 The POC's own arm G did not test A4 — it tested A8

`poc/P1-P2-findings.md` P15 measured a 16-tool surface routing a Vietnamese multi-step request:
arm F (normal description) **0/3, fluent prose, `finish_reason: stop`, no tool call**; arm G (hard
anti-prose directive) **3/3**. That is evidence for **A8** (the anti-prose gate) and for **A1**
(the set, not the model). It is **not** evidence for A4: what arm G measured is that the model
*emitted* `run_world_setup` with the request passed verbatim. **`run_world_setup` does not exist**,
so nothing ran, and correctness of the run was never observed. The POC ledger says so itself:
*"the problem **moves** into the sub-agents, which need their own scoped surfaces and their own
correctness"* (`:961-965`).

### A4.9 Cheapest observation that settles A4

Seed **one** `subagent_defs` row with `tool_scope: ["glossary_*"]` and a persona whose task is
"build the glossary for book X", run it on the dogfood corpus in `write` mode, and count
(a) tool calls before the iteration cap, (b) `result.error` strings containing
*"was NOT run"* / *"cannot request approval"*, (c) entities created vs the stepwise path.
**A4 is false if any Tier-W step in the capability returns "was NOT run"** — which the code
guarantees it will, so the run is a confirmation, not a discovery. Cost: one INSERT and one turn.
Do it in a throwaway book (`feedback_live_smoke_must_not_write_into_the_dogfood_book`).

---

## A11 — "the FSM lane absorbs the ordered multi-step jobs" · **KILLS (and it takes A2 with it)**

The spec's own evidence already says the rack has no click handler
(`DESIGN-HYPOTHESIS.md:144`). Verified, and it is worse than "no click handler":

**There is no FSM lane. There is no runner, anywhere, in any language.**

- **Seeds exist.** 12 workflows, 45 steps, in a Go SQL constant —
  `services/agent-registry-service/internal/migrate/migrate.go:497-766`
  (`glossary-bootstrap` 4, `entity-triage` 4, `populate-from-notes` 3, `kg-build` 4,
  `vision-to-book` 9, `translation-pass` 3, `draw-a-map` 4, `lore-so-far` 1, `canon-check` 3,
  `chapter-compose` 2, `build-a-book` 3, `autonomous-drafting` 5). Table DDL `migrate.go:395`.
- **No run endpoint.** Routes are list / get / delete / enablement / revisions / proposals —
  `services/agent-registry-service/internal/api/server.go:295-309`, handlers
  `workflows_rest.go:23,174,214,250,290`. There is **no `POST /workflows/{id}/run`**, no
  `workflow_runs` table, no run-status resource.
- **The FE click is a literal no-op.** `WorkflowRack.tsx:16` declares `onPick?`, fires it at
  `:59`; `WorkflowRackPanel.tsx:8,13` forwards it; the only production mount —
  `frontend/src/features/extensions/pages/ExtensionsPage.tsx:134` — **does not pass `onPick`.**
  The only other caller is the test. `frontend/src/features/workflows/api.ts:8-58` has no `run`
  method. `WorkflowsView.tsx:1` describes itself as *"render-only workflow management"*.
- **`workflow_load` says so in the description the model reads:** *"Loading also makes the step
  tools callable; **it does NOT run anything**"* —
  `services/chat-service/app/services/workflow_runner.py:97`.
- **No non-chat engine.** The FSMs in the tree (authoring-run
  `services/composition-service/app/db/migrate.py:1740`, intent-collection `:736`, glossary-build
  `:2162`) read none of `workflows.steps` and know nothing about a workflow slug.

**What actually "runs" a workflow today is chat, driven by a regex.** A slug becomes active via
the mode-binding seed (exactly one: `write → vision-to-book`, `migrate.go:818`) or via keyword
match on the user's message — `services/chat-service/app/services/intent_workflows.py:32-105`,
called at `stream_service.py:5431-5436`. The rail is then rendered **as prompt text**
(`workflow_runner.py:257,373`) and a nudge loop re-prompts the model up to
`RAIL_REDRIVE_CAP = 8` times (`stream_service.py:588`, driver `:2485-2565`). It never invokes a
tool itself.

**This is A11's stated falsifier, verbatim** (`DESIGN-HYPOTHESIS.md:146-147`): the lane cannot be
reached by a user, so chat drives the sequence anyway. And the blast radius is as written —
**it takes A2 with it**, because every ordered multi-step job A2 hands to "the FSM lane" comes
back to the chat surface and needs advertised tools.

Sharper than the spec states it: `SPEC.md:246` says *"Migration list = the workflow table"* — but
the workflow table is a **catalog of recipes that has never been executed by anything**. It is not
a migration list; it is a wish list. Its 45 steps are unvalidated against the runtime, and 12 of
them name tools that the deprecated-tool scanner exists specifically because they went stale
(`scripts/deprecated-tool-scan.py` docstring: *"a whole `autonomous-drafting` rail built on
`composition_authoring_run_create` (retired)"*).

**And the model does not reliably drive a rail it has to discover.** The regex-pin exists precisely
because that was measured to fail — `services/chat-service/app/services/intent_workflows.py:8-13`:

> *"the OTHER rails … a mid-tier model has to DISCOVER (`workflow_list` → recognise →
> `workflow_load` → drive), and measured, gemma-26B does that inconsistently:
> **S03 entity-triage 0/3 · S04 kg-build 1/3 · S09 canon-check improvises KG ops** instead of
> `composition_conformance_run`."*

So A11's fallback ("chat drives the sequence anyway") is itself measured at 0/3 and 1/3 on two of
the twelve rails, unless a hand-written regex happens to fire first.

**Cheapest observation:** `grep -rn "workflow_run\|/run\b" services/agent-registry-service/internal/api/` →
zero handlers, and open `ExtensionsPage.tsx:134` and look for `onPick`. Five minutes, already done.

---

## Two cross-cutting findings the mandate asks for explicitly

### C1 — The repo already did A3 for its highest-traffic write, and it worked

`book_chapter_save_draft` **already** takes text and resolves ids internally:

> *"The backend **RESOLVES THE CHAPTER'S STATE FOR YOU**: you do NOT read the chapter first and
> you do NOT pass a version. Pick the chapter with `chapter` (its NUMBER like "1", or its TITLE)"*
> — `services/book-service/internal/api/mcp_server.go:312-325`

This is the strongest *positive* evidence in the tree for the text-in idea — and it was achieved
**inside one existing tool**, without a sub-agent, without a capability boundary, and without
changing the surface size. It is the cheapest rival shape (`DESIGN-HYPOTHESIS.md:192-194`) already
proven once in production: **fix argument resolution per-tool; leave the surface alone.**
Any POC that does not measure that rival is measuring the wrong thing.

### C2 — The 51 atomic writes are exactly the surface shape-3 (user curation) has to carry

If A2 is false and the fallback is shape 3 (`DESIGN-HYPOTHESIS.md:61-62`), the user is being asked
to curate a 51-item list of writes whose names are `composition_arc_template_edit` and
`kg_triage_place_edge`. Shape 3's stated cost — *"the user must know what they will need"* —
is not a footnote at 51 items; it is the whole product. **The fallback is not cheaper than the
thing it is a fallback from.**

---

## What survives — stated so the kills are not read as "everything is wrong"

- **The read half of A2 largely survives.** 73 reads → 12 domain searches is a real consolidation
  (5–7 of the searches must be built). This is the cheap, high-value half.
- **A sub-agent for READ work survives intact.** `clamp_permission_mode` collapses `ask`/`plan` to
  read-only (`subagent_runtime.py:37-55`); a read-only delegate hits none of the gates in A4.2 and
  none of the caps in A4.3 matter (they are Tier-A counters). The `tool_scope` whitelist is sound
  code. **What does not survive is using it as the write path.**
- **A1 is untouched by this review** and remains the load-bearing one (`P14`: arm E 0/3 vs A–D 3/3).
  If the fix is "stop deleting the right tool from the wire," none of A2/A4/A11 is needed to get it.

## Verdicts

| id | assumption | verdict | why, in one line |
|---|---|---|---|
| **A2** | 198 tools → ~20 (1 search/domain + ~8 caps) | **KILLS** | Honest decomposition = **76** (13 caps + **51 refusing writes** + 12 searches); the spec's own "60+" falsifier is exceeded, and the DSL falsifier is hit too (map markers) |
| **A4** | sub-agent + free text preserves correctness | **KILLS** | Zero sub-agent instances exist; the runtime hard-errors on every Tier-W step (`"it was NOT run"`), caps at 4 iterations / 12 writes, streams no progress and cannot be interrupted; and the one place the comparison was run (E2 7→1 vs E3) measured the *opposite*, with the winning arm compiled into the shipped driver as Python |
| **A11** | the FSM lane absorbs ordered jobs | **KILLS** | There is **no lane** — no run endpoint, no runner, no `workflow_runs` table; `onPick` is unwired at `ExtensionsPage.tsx:134`; chat drives it via regex, and drives it at 0/3 and 1/3 on two rails |
