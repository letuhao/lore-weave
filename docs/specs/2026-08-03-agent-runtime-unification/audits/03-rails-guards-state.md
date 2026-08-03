# Audit 03 — Rails, Guards, Action-Gating and Conversation State

Scope: LoreWeave's own agentic runtime (chat-service driving an LLM over MCP tools).
Read-only. `stream_service.py` was inspected by targeted `grep -n` with context only.
All line numbers verified against the working tree at branch `feat/frontend-tools-mcp-migration`.

---

## 0. Executive summary — the five load-bearing findings

| # | Finding | Evidence |
|---|---|---|
| **F1** | **The `repeat` flag never reaches the consumer.** The registry serves rail steps through a Go struct where `Repeat` is a **string**; every seeded rail writes `"repeat": true` (a **bool**). `json.Unmarshal` records a type error, the caller **discards it** (`_ =`), the field is left zero and `omitempty` **drops it from the wire**. Verified experimentally. ⇒ the `repeat`-exemption branch in the action gate is **vacuous in production**; every repeatable step (save-cast, place-cast, arc-plan, apply-categories, draft) is disarmed after one success. | `services/agent-registry-service/internal/api/workflows.go:45`, `workflows_rest.go:110,140`, `internal/migrate/migrate.go:555,576,602,605,607,608,727,745`; consumer `sdks/python/loreweave_agent_control/rail.py:321,720` |
| **F2** | **The gate that was written yesterday to prove F1's semantics reads the seed SQL, not the wire.** `TestSchemaSQL_SameActionMeansTheSameThingInEveryRail` regex-scrapes `'[...]'::jsonb` out of `migrate.go` and asserts `st["repeat"].(bool)` — so it is green while the field is dropped 3 lines later in a different service. Classic "the scope never reaches it". | `services/agent-registry-service/internal/migrate/migrate_lint_test.go:300-316,338-385` |
| **F3** | **`step_lock` mode still contains the cross-session disarm bug that `done_suppress` was fixed for, and an all-done rail suppresses EVERY rail tool.** `done_suppress` was split onto `session_done`; `step_lock` was left on the durable `resume` verdict, and when `next_step is None` `allowed` stays empty so `every - allowed` = all rail tools. This is pinned as *expected* by a test. | `sdks/python/loreweave_agent_control/rail.py:696-710`; `sdks/python/loreweave_agent_control/tests/test_rail_gate.py:157-159` |
| **F4** | **Every loop breaker is turn-local and resets on a confirm suspend/resume.** All 14 counters live in `_stream_with_tools`'s frame; `chat_suspended_runs` persists only `working`, `pinned_step_tools`, `book_id`. A model that loops → hits a confirm card → resumes gets a fresh budget on every breaker *and* a fresh `rail_twice_nudged`, re-arming the honest give-up. | `stream_service.py:1863-1957`; `app/db/suspended_runs.py:21-53,74-89` |
| **F5** | **Hooks (the only declarative deny/approval layer) only see backend MCP tools.** Frontend tools break out at `:3502`, and `tool_load`/`workflow_load`/`load_skill`/`find_tools`/`conversation_search` all dispatch at `:2904-3227` — the `decide_pre_tool_call` seam is at `:3783`. A `deny` hook on `propose_edit` or `tool_load` is a **silent no-op**, and nothing tests the seam. | `stream_service.py:2904,3002,3061,3084,3227,3502,3783-3831`; `tests/test_hook_engine.py` (57 lines, pure-function only) |

Cross-cutting: **there is no unified state model and no guard contract.** Nine independent gating mechanisms write into three different suppression sets, unioned once at one advertise chokepoint; the model observes the *effect* of six of them and the *reason* for none of them. An agent cannot answer "why can't I call this tool right now?" — and neither can a developer without reading ~2,000 lines of `stream_service`.

---

## 1. STATE INVENTORY

### 1.1 Durable (Postgres, `loreweave_chat`)

| State | Where | Written by | Lifetime | Survives compaction? | Survives restart? |
|---|---|---|---|---|---|
| `chat_messages.tool_calls` (JSONB `[{iteration,tool,args,ok,result\|error}]`) | Postgres | the tool loop, per assistant turn | session | **Yes** — read by SQL, not from the message array | Yes |
| `chat_sessions.compact_summary` + `compacted_before_seq` | Postgres | `compact_service.persist_auto_compact:224-228` (OCC on prev seq), manual `/compact` route | session | it *is* the compaction | Yes |
| `chat_sessions.activated_tools TEXT[]` (the session hot-set) | Postgres | `activation_state["dirty"]` flush; `oneshot_deadvertise_mode="session"` deletes from it (`stream_service.py:4424-4433`) | session | yes | yes |
| `chat_sessions.working_memory_seed JSONB` (frozen roleplay charter) | Postgres | session create only; **immutable** | session | yes | yes |
| `chat_session_blocks` (label=`story_state`, value, token_estimate, refreshed_turn, source_hash, version) | Postgres | `session_blocks.refresh_block:85-106` (upsert, hash-gated) | session | **yes — it is the compaction safety net** | yes |
| `chat_suspended_runs` (run_id, `working` JSONB, pending_tool_call, `pinned_step_tools`, `book_id`, permission_mode) | Postgres | `suspended_runs.save_suspended_run:74-89` | until resume/delete | n/a | yes |
| tool approvals / decisions | Postgres (`app/db/tool_approvals.py`) | HITL gate | session-scoped decision | yes | yes |
| The rail DEFINITION (`workflows.steps` JSONB) | Postgres in **agent-registry-service**, seeded by `migrate.go` | admin/seed + MCP `propose_workflow` HITL | permanent | n/a | yes |
| Per-book steering entries | Postgres in **book-service** (`GET /internal/books/{id}/steering`) | user | permanent | n/a | yes |
| Hook definitions | agent-registry `/internal/hooks` | user/admin | permanent | n/a | yes |

### 1.2 Derived-per-turn (recomputed, never stored)

| State | Source | Notes |
|---|---|---|
| `BookState` (categories/cast/connections/plan/structure/structure_fresh/chapters/prose/suggestions) | `book_state_probe.probe_book_state:159-207` — 7 parallel `/internal` GETs, 2 s timeout each | `None` = UNKNOWN, never 0 (`:83-87,:113-121`). Probed **twice** per driven turn: once at assembly (`stream_service.py:5498`) and again fresh inside `decide_rail_drive` (`harness.py:102`) |
| `RailProgress[]` | `compute_rail_progress` (rail.py:189-325) | turn-start snapshot; also recomputed on resume (`stream_service.py:638`) |
| `EntityPresence` | `entity_presence.detect_entity_presence` | drives the T5 grounding gate |
| `AutoDetectResult` | `context_autodetect.resolve_context_pressure` | ANDed with an env ceiling at the call site |
| `ContextBudget` / `ContextBreakdown` | `token_budget.py` | emitted on the `contextBudget` frame |

### 1.3 In-memory, per-turn, per-process (**all lost on suspend/resume and on restart**)

Declared in one block at `stream_service.py:1856-1957`:

```
active_tool_names            planner_call_counts        blank_tool_args_streak
read_call_results            noop_write_counts          fail_by_tool_error
failure_suppress             oneshot_suppress           listed_categories
tool_list_total              suppress_tool_list         turn_succeeded (Counter)
rail_redrive_count           rail_nudge_counts          rail_twice_nudged
rail_drove_this_turn         narrated_write_nudges      turn_text_parts / turn_attempted
reasoning_loop_interventions _suppress_reasoning_next_pass
```

Plus `ReasoningLoopDetector` — one per LLM pass (`:2266`), discarded each pass.

### 1.4 State that exists in TWO places — flagged

1. **"which tools succeeded"** — `turn_succeeded` (in-memory, **backend chokepoint only**, `:4338-4339`) vs `succeeded_tool_counts()` (Postgres, all tool_calls incl. frontend/confirm). A frontend confirm never lands in `turn_succeeded`; the workaround is a third flag, `rail_in_flight`, carried on the suspended run (`stream_service.py:1740-1743`, `_rail_is_in_flight:998-1025`).
2. **"is this step done"** — `StepProgress.done` (durable, book-first) vs `StepProgress.session_done` (this chat) vs the *implicit* third: the effective flag `done or _consume(turn_succeeded)`. `rail.py:696-700` now materialises two of the three as `resume` and `gated`; `step_lock` uses `resume`, `done_suppress` uses `gated`.
3. **The same "done" verdict is consumed by two layers with different semantics** — the **budget** layer (`tool_surface.py:420-426`, via `_rail_done_tools` at `stream_service.py:5793`) still de-prioritises on the **durable** `s.done`, while the **advertise gate** deliberately no longer suppresses on it. So a step done in a *prior* session keeps its tool advertised but at the back of the token budget; if `next_step is None` (a fully-done rail) the `_next_exempt` set is empty too and every rail tool can be budget-dropped.
4. **The rail step is normalised twice** — `workflow_runner._rail_step:131-156` (for prose; treats `repeat` as a *string*, `!= "none"`) and `rail.compute_rail_progress` (for progress; treats `repeat` as a *bool*). Two readers, two types, one field. See F1.
5. **`COMPACT_TRIGGER_RATIO`** is imported back into two consumers by lazy function-scoped import (`stateful_chain.py:33`, `token_budget.py:169`) to dodge import-order coupling with the re-export shim — a smell, not a bug.
6. **`rail_progress.py` / `compaction.py` are pure re-export shims** over `loreweave_agent_control.rail` and `loreweave_context.compaction`; both re-export private names (`_STATE_LABELS`, `_PLACEHOLDER`) because tests import them.

### 1.5 The stale SDK duplicate (requested)

`sdks/python/build/lib/**` is a **stale build artifact checked into the tree**, and it is not a byte copy — it is an *older* version:

```
sdks/python/build/lib/loreweave_agent_control/rail.py   589 lines  (no `repeat`, no `session_done`, NO action-gating at all)
sdks/python/loreweave_agent_control/rail.py             724 lines  (current)
```

19 packages are duplicated there (`loreweave_context`, `loreweave_mcp`, `loreweave_grounding`, …), plus a stale copy of the SDK's own tests (`build/lib/loreweave_agent_control/tests/`). Anything that adds `sdks/python/build/lib` to `sys.path` (or a `pip install .` from a dirty tree) silently gets a rail driver with **no action-space gating**. This should be `.gitignore`d and deleted.

---

## 2. THE RAIL MODEL

### 2.1 What a rail is

A **rail** = a *pinned workflow*: an ordered list of C3 steps rendered verbatim into the system prompt every turn of a mode, with its step tools pre-activated.

- **Definition lives in Postgres** (agent-registry `workflows.steps` JSONB), **seeded from Go source** (`internal/migrate/migrate.go:520-770`). Not YAML, not code, not chat-service.
- **Step schema** (`workflows.go:40-66`): `id`, `tool`, `gate ∈ {none,confirm,approval}`, `when`, `repeat`, `inputs_map`, `async_job *bool`, `done_when`.
- **Pinning** comes from a registry *mode binding* (`binding.inject_workflows`), intersected with the visible workflow set (`stream_service.py:614-617`).
- **Rendering**: `workflow_runner.pinned_rail_block:257-329` — recipe text + guidance + (last, for recency) the driver's progress block.

### 2.2 How progress is computed — `compute_rail_progress` (rail.py:189-325)

Three signals, in strict precedence:

1. **Artifact** — `done_when` parsed by a closed grammar (`_PREDICATE_RE`, rail.py:74; keys `BOOK_STATE_KEYS` rail.py:49-66) evaluated against the `BookState` probe. Hard in **both** directions: present ⇒ done, **absent ⇒ NOT done even if the tool "succeeded"**.
2. **Call log** — `succeeded_tool_counts()` from `chat_messages.tool_calls`, consumed **in step order** with a `Counter` so two steps sharing a tool need two successes (`:262-266`).
3. **Contiguity** — `last_artifact_done` (`:230-244` region): a step before an unbroken run of present artifacts is inferred done ("the pipeline already ran past this"), stopping at the first *proven-absent* artifact.

A `gate: "confirm"` step is done exactly when the step named in its `inputs_map` is done (`:239-252` region).

`next_index` = first not-done step. `session_done[i]` is computed **independently**, over its own counter (`:268-280`).

### 2.3 How a rail advances — **code drives, model executes**

```
model stops with no tool call
  → 10 boolean guards (stream_service.py:2497-2515)
  → decide_rail_drive (harness.py:72-142)
      → FRESH probe_book_state
      → compute_rail_progress
      → next_actionable_step  → DRIVE | STOP_DONE | STOP_USER | STOP_ASYNC | STOP_UNKNOWN
      → enforcement_for(strength, cap) → nudge vs honest give-up
  → verdict.directive_text appended as a synthetic role=user message (stream_service.py:2556)
  → `continue` → one more LLM pass
```

Notable, and correct: the directive is a **`role=user`** message, not system, because the stateful continuation path hoists system messages to the front and buries them (`rail.py:485-491`). It is never persisted (`working` is ephemeral), and it forces a stateful chain-head drop at turn end (`rail_drove_this_turn`, `stream_service.py:1944-1951`).

Also correct, and hard-won: `render_progress_block` (rail.py:333-402 region) owns **WHERE**, never **WHEN** — its docstring documents two live failures from trying to own WHEN.

### 2.4 Bounds

| Bound | Value | Where |
|---|---|---|
| redrives per turn | `RAIL_REDRIVE_CAP = 8` | `stream_service.py:588` |
| redrives per step (required) | `rail_required_nudge_cap = 3` | `config.py:52`, clamped ≥1 at `rail.py:560` |
| redrives per step (optional) | `RAIL_OPTIONAL_NUDGE_CAP = 1` | `rail.py:552` region |
| deploy strength | `rail_enforcement ∈ {enforce,nudge,off}` | `config.py:49` |
| escape hatch | literal regex on the user's words, never an LLM guess | `rail.py:_ABANDON_RE` (~:596-608) |

---

## 3. GATING — every guard that can block, drop, rewrite or force a tool call

### 3.A Guards that REMOVE a tool from the advertised surface (schema-gating)

All five union into one `_suppress` set at the single advertise chokepoint, `stream_service.py:2066-2108`. **Only reachable on the `discovery` path** — the legacy/full-catalog path (`:2109-2113`) gets none of them.

| # | Guard | Trigger | Effect | What the model observes |
|---|---|---|---|---|
| A1 | **rail action gate** `rail_gate_suppressions` | `rail_action_gate_mode ∈ {done_suppress, step_lock}` and rail progress exists | drops rail STEP tools | **Nothing.** The tool silently vanishes from the schema list. Only the advisory prose "ALREADY DONE — do NOT repeat" hints at it. |
| A2 | **oneshot de-advertise** | `oneshot_deadvertise_mode`: `existence` (context id present) / `per_turn` / `session` (on `created:false`) | drops `kg_project_create` | Nothing (session mode also deletes it from `activated_tools`) |
| A3 | **repeated-failure de-advertise** | same tool + same error ≥ `REPEATED_FAILURE_CAP=2` | `failure_suppress.add(name)` (`:3576` FE, `:4089` BE) | It first gets an explicit `error` string; then the tool disappears |
| A4 | **tool_list exhaustion** | `tool_list_total ≥ TOOL_LIST_TOTAL_CAP=5` | `suppress_tool_list=True` → `tool_list` dropped from ALWAYS_ON (`:1354`) | Nothing; `tool_load` stays |
| A5 | **rail step-tool token budget** | `budget_rail_tools` over-budget | a rail step tool never reaches the wire | Nothing — it only logs `WARNING "the rail names tools the agent cannot see"` (`tool_surface.py:440-443`) |

`suppress_names` is applied **only** inside the `active_tool_names` loop (`:1386`); the `ALWAYS_ON_CORE_NAMES` loop (`:1344`) is untouched — so discovery/answer tools can never be stranded by A1-A3. **This invariant is real but unasserted** (see §5).

### 3.B Guards that BLOCK a dispatched call (short-circuit, model gets an error string)

Ordered as they appear in the dispatch chain:

| # | Guard | Trigger | Model observes |
|---|---|---|---|
| B1 | **pre_tool_call hook `deny`** (`hook_engine.decide_pre_tool_call:36-52`, wired `:3783-3797`) | a declarative hook whose `tool_pattern` fnmatches | `{"error":"blocked_by_hook","message":…}` — explicit |
| B2 | **pre_tool_call hook `require_approval`** (`:3798-3831`) | ditto | at depth 0: a HITL suspend card. In a **subagent**: an explicit error saying it cannot request approval — correctly no silent no-op |
| B3 | **planner hard-stop** (`:3839-3861`) | `glossary_plan` called ≥ `PLANNER_CALLS_PER_TURN_CAP=1` this turn | `{"error":"planner_already_ran", …}` with a forward steer |
| B4 | **repeated-failure breaker** (`:4066-4098`) | same dominant error ≥2 | error text echoing the tool's own error + "STOP calling it" |
| B5 | **idempotent-no-op-write breaker** (`:4099-4122`) | `created:false` seen ≥ `IDEMPOTENT_NOOP_WRITE_CAP` for the same (tool,args) | explicit error + "take that existing id and move on" |
| B6 | **repeated-read breaker** (`:4123-4144`) | same (tool,args) returned a **byte-identical result** ≥ `REPEAT_READ_CAP=2`. Counts *unchanged results*, not calls, so polling is exempt (`:515-521`) | explicit error |
| B7 | **blank/invalid-args breaker** (`:4146-4180`, FE mirror `:3554`) | `BLANK_TOOL_ARGS_CAP=2` blank/missing-required failures, **shared across tools** | explicit directive to stop and tell the user |
| B8 | **spend gate / tier-A caps** (`TIER_A_AGGREGATE_CAP=12`, `tier_a_op_counts`) | Tier-A write volume | HITL suspend |
| B9 | **permission mode** (`_filter_tools_for_ask:1398`, `_advertise_discovery_tools:1323`) | `ask`/`plan` mode | non-tier-R tools simply absent (advertise-time, silent) |

### 3.C Guards that REWRITE the call or the schema

| # | Guard | Effect | Observable? |
|---|---|---|---|
| C1 | **ambient-book schema projection** (`_project_ambient_book_schema:1272-1294`) | strips `book_id` from an `_meta.ambient_book` tool's schema so the model cannot even form the belief it needs one; backfilled server-side | Not observable — by design ("Absent from the schema, the belief cannot form") |
| C2 | **context-id injection** (`_inject_context_ids`) | fills omitted `book_id`/`chapter_id`/`project_id` from session context | Silent |
| C3 | **planner `model_ref` strip** (`:3863-3874`) | the model's model choice is deleted so the user's setting wins | Silent |
| C4 | **tool-result cap** (`tool_result_content_capped_ex`, `:4444`) | oversized results truncated | A self-correcting notice is appended |

### 3.D Guards that FORCE an action (inject a synthetic turn)

| # | Guard | Trigger | Injected as |
|---|---|---|---|
| D1 | **rail redrive** (`:2550-2568`) | 10 guards all true + a drivable step | `role=user` `[SYSTEM DIRECTIVE …] call \`{tool}\` in THIS turn` |
| D2 | **rail honest give-up** (`rail.honest_giveup_directive`) | nudge count ≥ cap and step is enforced | `role=user` "tell the user plainly it did not land" |
| D3 | **reasoning-loop steer** (`:2393-2410`) | `ReasoningLoopDetector` trips, under `REASONING_LOOP_INTERVENTION_CAP=2` | `role=user` directive; also forces `reasoning=off` next pass |
| D4 | **narrated-write nudge** (`:2589-2620`) | prose names a real write tool the turn never attempted | directive + **arms** the named tool onto the surface |
| D5 | **tool_list repeat auto-load** (`:2808-2866`) | 2nd list of the same category | auto-loads the category's tools and steers forward — deliberately *not* an error (two reverted fixes proved an error made it retry harder: 28→311 calls) |
| D6 | **hook `inject_text`** (`collect_injections`) | pre_turn/post_turn hook | prompt block |
| D7 | **rail step re-arm** (`:4338-4366`) | a rail step tool succeeded ⇒ the rail moved | re-activates the whole step set so the *new* next step is on the wire |

### 3.E Content guards (not tool guards)

| Guard | Applies to | Not applied to |
|---|---|---|
| `neutralize_injection` (`injection_defense.py:40-55`) | `kctx.context`, `kctx.stable_context`, `kctx.volatile_context` (`:4948-4950`), `wm_pinned`/`wm_tail` (`:5012-5013`), voice path (`voice_stream_service.py:363,381`), `evaluate.py:63` | **MCP tool results**, `conversation_search` results, compaction summaries, steering bodies |
| `select_steering` cap (`steering.py:98-109`) | drops from the tail while over `scale_by_window(2000)` | keeps at least one entry regardless of size (`len(selected) > 1`) |

---

## 4. FAILURE MODES

### 4.1 Deadlock — "needs tool X, guard removed tool X"

**FM-1 · `step_lock` on an all-done rail suppresses every rail tool.**
`rail.py:702-710`: `current = next(s for s,d in zip(steps, resume) if not d)`. All done ⇒ `current is None` ⇒ `allowed` empty ⇒ returns **every** rail step tool as suppressed. Pinned as intended by `test_rail_gate.py:157-159` (`test_step_lock_all_done_drops_everything`). Since `step_lock` uses the **durable** verdict, a *new* session on a finished book loses the entire rail action space — the exact Mị Đế bug `done_suppress` was split off `session_done` to fix (`rail.py:158-168`, `683-695`). Mitigated only by `step_lock` not being the default (`config.py:342`), and it is documented as measurement-DISQUALIFIED (`config.py:335-338`) — but it is still a selectable, unvalidated env value. <!-- doc-language-gate: ok -- "Mị Đế" is the proper name of the dogfood book, an identifier used across this repo; renaming it would break cross-doc traceability -->

**FM-2 · budget starvation of a rail whose `next_step` is None.**
`_rail_next_tools` (`stream_service.py:5811-5815`) is empty when every step is durably done, and `_rail_done_tools` then contains *all* step tools, which `tool_surface.py:422-426` pushes to the back of the budget queue. So a "finished" rail's tools are simultaneously (a) not exempt, (b) lowest priority, (c) still named by the rail prose. Symptom = the documented "reads a recipe naming tools it cannot see" (`tool_surface.py:440-443`).

**FM-3 · `session_done` is session-lifetime, never windowed.**
`succeeded_tool_counts` (`tool_call_history.py:27-36`) counts every success in the session with **no branch filter** and no recency window. In a long session a step performed 60 turns ago still disarms its tool — the Mị Đế bug at session scale rather than book scale. It also counts successes from *other branches* (`branch_id` is not in the WHERE clause, unlike `compact_service.py:187`). <!-- doc-language-gate: ok -- "Mị Đế" is the proper name of the dogfood book, an identifier used across this repo; renaming it would break cross-doc traceability -->

**FM-4 · a `confirm` step's producer marked done by contiguity.**
Guarded (the `last_artifact_done` **contiguous** scan exists precisely because the first cut jumped over a proven-absent artifact and deadlocked the confirm — `rail.py:~205-228`). Worth noting as a *fixed* deadlock whose fix is only unit-covered.

### 4.2 Silent no-ops

**FM-5 · every advertise-time suppression is invisible to the model.** A1/A2/A4/A5/B9 remove a tool with no signal. The project's own measurement says pre-emptive removal *causes* substitution loops (`config.py:295-298`: `existence` mode → 57 attempts anyway; `:335`: `step_lock` → `glossary_propose_entity_edit ×59`). The system keeps re-learning that a silent removal is not a communication.

**FM-6 · hooks never see non-backend tools.** §0 F5. Also: hooks are only consulted when `hooks` is truthy — a registry outage yields `[]` and every `deny` hook silently lapses. No "hooks unavailable ⇒ fail closed" path exists.

**FM-7 · closed-set settings are never enum-validated.** `VALID_GATE_MODES` is defined (`rail.py:636`) and **exported through two `__init__`s and the chat shim — and used nowhere** (`grep`: only definition + re-export lines). Consequences of a typo:
- `RAIL_ACTION_GATE_MODE=done_supress` → `rail.py:667` `mode not in (…)` → `set()` → gating **silently off**.
- `RAIL_ENFORCEMENT=enfroce` → guard `strength_on` (`stream_service.py:2505`) is `!= "off"` ⇒ **true**, so the rail still drives; but `enforcement_for` (`rail.py:~561`) returns `(False, 1)` ⇒ every step gets the optional cap of 1 and nothing is ever held. Enforcement silently degrades to "nudge" while the log line at `:2560-2563` prints `strength=enfroce`.
This violates the repo's own Settings & Config Boundary (enum-validate closed-set values on write).

**FM-8 · `persist_auto_compact` swallows the summarizer failure** (`compact_service.py:212-213`, `return None`). Correct for safety (session unchanged, ephemeral tiers still guard the turn) but there is no counter/telemetry, so a permanently-failing summarizer re-pays the ephemeral compaction cost every turn, forever, silently.

**FM-9 · `task_detect.py` is entirely dormant** — the module's own docstring (`:13-16`) says it is not wired into `mcp_execute_tool` and chat-service does not declare the tasks capability. `tasks_capability_meta()` is defined and unused. `propose_edit_suspend_args_from_result` *is* used (`stream_service.py:~4320`). So the file is half live, half dead, under a name (`task_detect`) that reads like rail/task detection and is not.

### 4.3 Vacuous guards (cannot fire)

**FM-10 · the `repeat` exemption.** §0 F1 — the field is dropped on the wire, so `bool(st.get("repeat"))` is always `False` for every seeded rail. Both consumers are dead: `rail.py:720` (`if d and not s.repeat`) and `stream_service.py:5803-5808` → `tool_surface.py:421`.

**FM-11 · `repeat` is also type-incompatible for AUTHORED workflows.** The API's own type is `string ∈ {"", "none", "per_item:<key>"}` (`workflows.go:45`, validated `:205-218`). Python does `bool(st.get("repeat"))`, so an authored `repeat: "none"` would read as **repeatable = True** — the inverse of its meaning. Today unreachable only because F1 strips the field; fixing F1 naively (making the Go type `any`) would activate FM-11.

**FM-12 · the lint that guards `repeat` cannot see the wire.** §0 F2. `migrate_lint_test.go:313-315` even self-checks against vacuity (`if len(out) < 20 … "the lint would be vacuously permissive"`) — it guards its *sample size* but not its *subject*.

**FM-13 · `ReasoningLoopDetector` is largely blind to CJK.**
`_SEGMENT_BOUNDARY = r"[^\n.?!]*[\n.?!]+"` (`reasoning_loop_detector.py:45`) recognises only ASCII `.` `?` `!` and `\n`. A Chinese/Japanese reasoning stream punctuated with `。！？` and no newlines never yields a complete segment: `_buf` grows unboundedly and `feed` **never** trips. This is a multilingual novel product whose target local model reasons in the book's language; the incident that motivated the detector was English. (Vietnamese is unaffected — it uses ASCII `.`.) Also a slow unbounded-buffer growth on such a stream.

**FM-14 · `context_autodetect` treats an unrecognised mode as `auto`** (`context_autodetect.py:77`) — deliberate bias-to-include, but it means a typo'd per-session `context.mode` is indistinguishable from `auto` with no surfaced source. `AutoDetectResult.source` would report `"auto"`, not `"invalid"`.

**FM-15 · `book_state_probe` logs `%d/6 sources` while listing 7** (`book_state_probe.py:190-206`) and omits `structure_fresh` from `failed_sources` entirely. So a `structure_fresh`-only failure is invisible to the operator, and `structure_fresh` is precisely the key that gates the `compile` step (`rail.py:59-62`).

### 4.4 Reset-on-resume (F4, expanded)

`chat_suspended_runs` carries `working` + `pinned_step_tools` + `book_id` + `permission_mode` and **nothing else**. On resume:
- every B-class breaker counter restarts at 0;
- `failure_suppress` / `oneshot_suppress`(per_turn) / `suppress_tool_list` are empty ⇒ tools de-advertised pre-suspend come **back**;
- `rail_twice_nudged` and `rail_nudge_counts` are empty ⇒ a step that already exhausted its honest give-up can be driven 3 more times;
- `rail_redrive_count` restarts at 0 ⇒ up to 8 more redrives.
Since the vision-to-book rail's **step 3 is a confirm gate**, this is the *normal* path, not an edge case. `_compute_rail_drive_context:591-644` faithfully rebuilds the rail context on resume — and just as faithfully rebuilds none of the guard state.

### 4.5 Cost / correctness

**FM-16 · double probe per driven turn.** `probe_book_state` runs at assembly (`stream_service.py:5498`) *and* fresh inside `decide_rail_drive` (`harness.py:102`) — 14 internal HTTP calls on a driven turn, each with a 2 s timeout. Deliberate (the turn-start probe is stale after mid-turn writes) but uncached and unbounded per redrive: **8 redrives ⇒ up to 9 probes ⇒ 63 internal GETs in one turn.**

**FM-17 · `STOP_UNKNOWN` can wedge a rail when a probe source is permanently down.** `next_actionable_step` (`rail.py:~460-463`) refuses to drive when *any* earlier step's `done_when` key reads `None`. `_connections` returns `None` whenever the KG stats cache is uncomputed (`book_state_probe.py:83-87`). A permanently-uncomputed cache therefore permanently stops the driver past that step — with no user-visible signal (only `logger.info "guards held but no actionable step"`, `stream_service.py:2534-2537`).

---

## 5. INTERACTION WITH THE OTHER LAYERS

### 5.1 What the rail/guard layer assumes about the TOOL-SURFACING layer

| Assumption | Exact symbols | Enforced? |
|---|---|---|
| "a returned suppression can only ever be a rail STEP tool, so this can never strand the agent's discovery/answer path" (`rail.py:646-649`) | `ALWAYS_ON_CORE_NAMES` (`tool_discovery.py:282`) vs `suppress_names` applied only at `stream_service.py:1386` | **Not enforced, and the docstring is already stale**: it names "find_tools/tool_load/workflow_load/frontend tools" as always-on, but `find_tools` was retired from the core set (`tool_discovery.py:283-289`) and `workflow_list/workflow_load` are conditional on `has_workflows` (`stream_service.py:1365`). Nothing asserts `rail_gate_suppressions() ∩ ALWAYS_ON_CORE_NAMES == ∅`. |
| the rail's step tools are on the wire | `pinned_step_tools` → `tool_surface.discovery_seed_for_surface(..., pinned_step_tools=, rail_done_step_tools=, rail_repeat_done_step_tools=, rail_next_step_tools=)` (`stream_service.py:5826-5829`) | Only a `logger.warning` when the budget drops one (`tool_surface.py:440`). The rail prose still names the dropped tool. |
| the seed is recomputed when the rail advances mid-turn | `stream_service.py:4340-4366` (`_rearm`) + `merge_activated_tools` | Yes — added after a live wedge; but it fires only on a **success** at the backend chokepoint, so a frontend/confirm step never re-arms |
| async steps are known | `rail_async_tools` from `tool_async(td)` on the catalog (`stream_service.py:623-625`); `_step_is_async` prefers the authored `async_job` (`rail.py:~428-435`) | `async_job` survives the wire (it is `*bool`), unlike `repeat` |
| a suppressed tool is still *reachable* | `tool_load` stays in ALWAYS_ON | True, but the model is never told this is the recovery path when a tool vanishes |

### 5.2 What it assumes about the SKILL layer

| Assumption | Symbols | Enforced? |
|---|---|---|
| a skill prompt that names a tool gets that tool on the wire | `injected_skill_codes` → `D-SKILL-NAMED-TOOLS-RIDE` exemption (`tool_surface.py:444-450`) | partially — a *budget* exemption only |
| a skill's `hot_domains` only seed when the skill is visible on the surface | `SYSTEM_SKILLS`, `_skill_visible`, `_surface_key` (`tool_surface.py:376-382`) | yes, in code |
| the rail gate never removes a tool a skill instructs the model to use | — | **Not enforced.** `rail_gate_suppressions` runs after the skill block is already in the prompt. A skill saying "add characters with `glossary_propose_entities`" plus a done `save-cast` step ⇒ instruction without capability. Given FM-10 this is live today. |
| deprecated tools disappear from every list | `ALWAYS_ON_CORE_NAMES` ⇄ `TestSkillClaimsLint` | The comment at `tool_discovery.py:292-306` documents this exact hole having shipped (four skills instructing `ui_watch_job` after it stopped reaching the wire) |

### 5.3 Cross-service contract couplings (the fragile seam)

| Concept | agent-registry (Go) | chat-service (Python) | Status |
|---|---|---|---|
| `done_when` grammar | `doneWhenRe` (`workflows.go:76`) | `_PREDICATE_RE` + `BOOK_STATE_KEYS` (`rail.py:49-74`) | **Two hand-maintained copies**, comment-linked ("MUST stay in lockstep"), no test. Already drifted: Python knows `structure` and `structure_fresh`; Go's regex rejects them, so an author cannot write the predicate the seeds use. |
| `repeat` | `string` | `bool` | **BROKEN** (F1/FM-10/FM-11) |
| `gate` | `validWorkflowGates` (`workflows.go:28`) | `VALID_GATES` (`workflow_runner.py:138`) | duplicated, agrees today |
| `async_job` | `*bool` | `bool` | ok |
| step round-trip | `[]workflowStepIn` at `workflows_rest.go:110` | raw dicts | **any field not on the Go struct is silently dropped** — the struct comment at `workflows.go:62-64` says so explicitly, and `repeat` is the case where the field *is* declared but with the wrong type, which the comment's rule does not cover |

---

## 6. PATCHWORK TELLS

**6.1 Nine independent anti-loop mechanisms, each added after one live incident, each with its own counter and its own constant.** `MAX_TOOL_ITERATIONS`, `TIER_A_AGGREGATE_CAP`, `PLANNER_CALLS_PER_TURN_CAP`, `BLANK_TOOL_ARGS_CAP`, `REPEAT_READ_CAP`, `IDEMPOTENT_NOOP_WRITE_CAP`, `REPEATED_FAILURE_CAP`, `TOOL_LIST_CATEGORY_CAP`+`TOOL_LIST_TOTAL_CAP`, `REASONING_LOOP_INTERVENTION_CAP`, `RAIL_REDRIVE_CAP`, `NARRATED_WRITE_NUDGE_CAP`. Every one is documented by the measurement that produced it (`24 times`, `×57`, `205 identical`, `28→311`, `19×`, `30+`). None share a framework.

**6.2 Fixes layered on fixes, in the source.**
> `rail.py:353` — *"Cut 1 gave the model an unconditional imperative … Cast: 0. Cut 2 over-corrected … Cast: 0 again."*

> `tool_surface.py:413` — *"D-RAIL-REPEAT-BUDGET (**v2** of the done-exclusion)"*

> `stream_service.py:563` — *"**Two reverted fixes** proved the breaker's usual lever BACKFIRES here"*

> `rail.py:683` — *"Two different flags, because there are two different questions."* (the `resume`/`gated` split, added after the plan_propose_spec incident)

**6.3 Env-flag kill switches gating agent behaviour.** `RAIL_DRIVER_ENABLED`, `RAIL_ENFORCEMENT`, `RAIL_REQUIRED_NUDGE_CAP`, `RAIL_ACTION_GATE_MODE`, `ONESHOT_DEADVERTISE_MODE`, `LAZY_SKILL_BODIES`, `LAZY_WORKFLOW_DIRECTIVE`, `LLM_STATEFUL_CACHE`, `LLM_STATEFUL_MAX_CHAIN_TOKENS`, `COMPACT_BREADCRUMB_ENABLED`. Each is defended in-comment as "a deploy ceiling, not a per-user knob" — and `config.py:42-44` concedes the per-user version is deferred (`D-G2-SETUSER`). None is enum-validated (FM-7). Several are really **A/B experiment selectors left in the code after the experiment** (`config.py:293-303`, `:325-341` carry the full result tables).

**6.4 Per-model branches embedded in guard logic.**
> `compact_service.py:96-99` — *"Hidden thinking is DISABLED for the summary call (live-caught: **gemma** spent the whole max_tokens budget on ReasoningEvents and returned EMPTY prose)"*

> `stream_service.py:1276-1279` — the ambient-book schema strip, justified by a **Vietnamese** quote from a live gemma session pasted into a source comment (also a written-artifacts-are-English violation).

> `config.py:328-335` — the gate-mode default is chosen from a matrix over `qwen2.5-7b` vs `gemma-4-26b`.

> `stream_service.py:2230` — reasoning suppression *"on local Qwen3/Gemma (lm_studio/vLLM)"*.

**6.5 Superseded / dead paths still in the tree.**
- `sdks/python/build/lib/**` — a stale second copy of 19 SDK packages, including a pre-gating `rail.py` (§1.5).
- `find_tools` — retired from the model's view but *"stays dispatchable for any legacy caller"* (`tool_discovery.py:287-289`); still special-cased at `stream_service.py:1345,1418,3084`.
- `VALID_GATE_MODES` — exported through three modules, referenced by none (FM-7).
- `task_detect.tasks_capability_meta()` — defined, dormant, unused (FM-9).
- `_STATE_LABELS`, `_PLACEHOLDER`, `_DUP_PLACEHOLDER` re-exported from shims *"because an existing chat test imports it"* (`rail_progress.py:11`).
- `rail_drove_this_turn` is set by the **reasoning-loop** steer too (`stream_service.py:2408`) — one flag, two owners, a name that lies.

**6.6 A guard whose own log line documents that a previous version of it was undebuggable.**
> `stream_service.py:2539-2543` — *"A step-runner that silently does not fire is indistinguishable from a rail with nothing to do — and that ambiguity cost a live debugging session … Name the guard that held, so the next occurrence is one grep instead of a code read."*

This is the single best evidence for §7: the fix was to *log* the guard verdict. The right fix is to make the verdict a first-class, queryable object.

---

## 7. WHAT A UNIFIED ARCHITECTURE NEEDS

The goal, stated as the acceptance test: **at any moment, for any tool, the runtime can answer "why can't I call this right now?" with a single structured record — and the model can ask.**

### 7.1 The minimal state model

Three scopes, named, with explicit lifetimes and one owner each:

```
TurnState        (in-memory, one per LLM turn, DIES at turn end)
  ├─ pass_index, write_passes
  ├─ succeeded: Counter[tool]         # every executor, not just the backend chokepoint
  ├─ attempted: Counter[tool]
  ├─ failures:  {tool: {error_sig: n}}
  ├─ results:   {(tool,args): (fingerprint, unchanged_count)}
  └─ interventions: {kind: n}         # redrive / reasoning-steer / narrated-write

RunState         (persisted with the suspended run — SURVIVES suspend/resume)
  ├─ TurnState (serialised — fixes FM-4/F4)
  ├─ rail: {slug: {nudges: {step_id: n}, given_up: [step_id], redrives: n}}
  └─ suppressions: [SuppressionRecord]   (see 7.2)

SessionState     (Postgres, SURVIVES restart)
  ├─ activated_tools, compact_summary/before_seq, working_memory_seed
  ├─ chat_session_blocks (story_state, …)
  └─ tool_calls ledger  ← the ONLY durable "what has been done"
```

Rules that fall out:
- **One reader per fact.** "did this chat do X" must come from exactly one place; today it is `turn_succeeded` ∪ `succeeded_tool_counts` ∪ `rail_in_flight`. Make the executor write into `TurnState.succeeded` for *every* dispatch path (backend, frontend-suspend, consumer-local meta-tools) and derive the DB count only as the cross-turn tail.
- **Window the session verdict.** `session_done` must be "done in the last N turns / since the last user goal change", not "ever in this session" (FM-3), and must filter `branch_id`.
- **Separate ORIENT from DISARM, permanently.** `done` (book) may only inform the prompt; `session_done` (chat, windowed) may remove a capability. `rail.py:158-168` states this — apply it to `step_lock` and to the budget layer too (FM-1, §1.4 item 3).

### 7.2 The guard contract

Every guard becomes an implementation of one interface, registered in one list, evaluated at one of three named seams:

```python
@dataclass(frozen=True)
class GuardVerdict:
    guard_id: str            # "rail.done_suppress" | "breaker.repeated_read" | "hook.deny" | …
    tool: str
    decision: Literal["allow","hide","block","rewrite","force"]
    reason_code: str         # CLOSED SET, enum-validated
    reason_text: str         # what the MODEL is told (required for hide+block)
    recovery: str | None     # "call tool_load('X') if you genuinely need it again"
    evidence: dict           # {"succeeded_this_session": 3, "step_id": "save-cast"}
    scope: Literal["pass","turn","run","session"]   # when it expires
```

with three seams: `on_advertise(tool, state) -> GuardVerdict`, `on_dispatch(call, state) -> GuardVerdict`, `on_stall(state) -> DriveVerdict | None`.

Non-negotiable properties, each of which fixes a finding above:

1. **No silent hide.** A `hide` verdict must be surfaced — minimally as a compact line in the prompt (`unavailable this turn: glossary_propose_entities — you already saved characters in this chat; call tool_load if you need it again`). Today five guards hide silently (FM-5), and the project's own A/B data says silent removal *causes* substitution loops (`config.py:295-298,335`).
2. **Every seam sees every executor.** One dispatch chokepoint that all tool kinds pass through, so hooks/breakers cannot be bypassed by dispatching earlier (F5).
3. **Verdicts are the log.** `stream_service.py:2497-2515` already builds a named guard dict precisely so "the log can never disagree with the branch it explains" — generalise that: emit the `GuardVerdict` list on the `contextBudget`/Inspector frame, and expose a `why_not(tool)` meta-tool so the *model* can ask.
4. **Guards never touch `ALWAYS_ON_CORE_NAMES`** — asserted by a test, not by a docstring (§5.1).
5. **`scope` is declared, and the runtime honours it** — a `run`-scoped suppression serialises into the suspended run; a `turn`-scoped one does not. This is F4/FM-4 solved by construction rather than by remembering to add a column.
6. **Closed-set config is enum-validated at startup**, with the effective value + source tier exposed (`VALID_GATE_MODES` finally used) — FM-7.

### 7.3 The rail-definition contract

One schema, one generator, two consumers:

- Publish the C3 step schema as a **machine contract** (the repo already has the pattern: `contracts/frontend-tools.contract.json`, and `docs/standards/mcp-tool-io.md`). Generate the Go struct field types and the Python reader from it, or at minimum add a round-trip test that POSTs/seeds a step with every field set and asserts `GET /internal/workflows` returns them **byte-identical** — that single test kills F1, FM-11, FM-12 and the `done_when` grammar drift in §5.3 at once.
- Never `_ =` a `json.Unmarshal` on a payload that crosses a service boundary (`workflows_rest.go:140`, and the same pattern at `workflows.go:348,372,850`).
- Make `repeat` one type. Given the Python reader and the seeds already use a bool and the string form's `per_item:` fan-out is not implemented anywhere in chat-service, `bool` is the honest choice; the string form should be retired or renamed.

### 7.4 Sequencing (cheapest-first, all independently shippable)

1. Fix `workflows_rest.go` type + add the round-trip test (F1/F2). One-line type change, one test. Highest value per line in this audit.
2. Delete `sdks/python/build/lib/**`, add to `.gitignore` (§1.5).
3. Enum-validate the four closed-set settings at startup (FM-7). ~10 lines.
4. Make `step_lock` use `gated` and treat `current is None` as "suppress nothing" (FM-1). Two lines + flip the test's expectation.
5. Serialise `TurnState`+rail counters into `chat_suspended_runs` (F4).
6. Add `。！？` and a buffer cap to `_SEGMENT_BOUNDARY` (FM-13).
7. Then the `GuardVerdict` refactor — by then the state model is already three named scopes and the refactor is mechanical.
