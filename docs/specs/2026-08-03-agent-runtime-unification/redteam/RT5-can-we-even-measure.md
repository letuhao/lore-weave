# RT5 — A10: can we even measure? (red team, falsification pass)

**Assignment:** falsify **A10** — *"per-tool live verification is a valid acceptance signal"*.
**Method:** read the schema and the writers, then query the live dev stack (`infra-postgres-1`,
`loreweave_chat` + `loreweave_provider_registry`, 2026-08-04) rather than trusting the register.
**Verdict up front: A10 is FALSE TODAY, and it fails on the one axis the whole spec turns on.**

The design's own root cause (P13/P14) is *"the correct tool was silently removed from the wire."*
**Nothing in this system records what was on the wire.** So the failure mode the spec exists to kill
is, in production, undetectable by construction — not hard to see, *unrepresented*.

---

## 0 · Scoreboard

| id | verdict | one-line |
|---|---|---|
| RT5-1 | **KILLS** | the advertised tool set per turn is persisted nowhere; arm-E silent deletion is invisible in production |
| RT5-2 | **KILLS** | there is no ground-truth label anywhere — `message_feedback` holds **3 rows**, none human-authored |
| RT5-3 | **KILLS** | "tool failed" / "model chose wrong" / "tool not advertised" are not separable from any stored field |
| RT5-4 | **KILLS** | the standing acceptance instrument (liveness matrix 211/224) runs **zero LLM turns** for 214 of 224 tools |
| RT5-5 | **KILLS** | N=3 cannot reject a 63% failure rate; production's own average (54%) sits inside the interval |
| RT5-6 | **WOUNDS** | the register's "35% coverage" is a denominator error — it is 83% of assistant rows; the real hole is `finish_reason` at **9.4%** |
| RT5-7 | **WOUNDS** | the chat path has **no `seed`** and its temperature is unrecorded; the POC ran at 0.2, production runs 0.0 |
| RT5-8 | **WOUNDS** | the *only* advertised-set record is an INFO log line with no join key, destroyed on container recreate (6 lines survive) |
| RT5-9 | **WOUNDS** | `llm_jobs` — the other candidate store — records `{"stream": true}` for the chat surface, 148 rows, 0 tools, 0 tokens |
| RT5-10 | **WOUNDS** | sampled 3 of the 13 prior "verifications"; all three are vacuous by NV-2/NV-3/NV-4 |
| RT5-11 | **SURVIVES** | `chat_messages.tool_calls` is real, high-coverage and honest — A10 is one column short, not hopeless |

---

## 1 · What telemetry exists TODAY for a tool call

### 1.1 The record itself

`chat_messages.tool_calls JSONB` — added by `services/chat-service/app/db/migrate.py:186-190`
(*"K21-B — per-message tool-call history (JSONB) for UI replay"*). Written at the terminal UPSERT,
`services/chat-service/app/services/stream_service.py:6901-6928` (and the checkpoint/interrupt paths
at `:5998` and `:6749`). Entries are appended at `:6525` from the `{"tool_call": {...}}` chunks
minted at `stream_service.py:2872-2875`, `:2893-2896`, `:2975-2978` and the dispatch sites.

**Measured field census over 2,000 live entries:**

```
iteration 2000 · args 2000 · result 2000 · error 2000 · ok 2000 · tool 2000 · id 1995 · activity 59
```

**Volume, live:** `7,447` tool calls, `4,010` failed (**53.8%**) — P2's headline reproduces.

| field | present? |
|---|---|
| tool name, args, ok, error, result, iteration | ✅ |
| **latency** | ❌ `0 / 7,447` |
| **the tool set advertised on that pass** | ❌ `0 / 7,447` |
| **whether the error came from the TOOL or from a loop-breaker** | ❌ (see RT5-3) |
| **model_ref / temperature for the pass** | ❌ (message-level `model_ref` only) |

The single exception: **18 of 7,447 records (0.24%)** carry `result.loaded_tools` — the F18
auto-load's *survivor* list (`stream_service.py:2833, 2850`). It is the post-deletion output, never
the pre-deletion input. **The one place in the entire persisted history that names a tool set names
it after the deletion that P14 identified as the root cause.**

### 1.2 Context / token telemetry

`chat_messages.context_breakdown JSONB` — `migrate.py:197-201`. Built by
`token_budget.context_budget_event()` (`services/chat-service/app/services/token_budget.py:234-297`),
persisted at `stream_service.py:6867-6888 → :6906`. Category vocabulary is fixed at
`token_budget.py:92-111` (16 keys, incl. `mcp_tool_schemas`, `frontend_tool_schemas`, `tool_results`).

**It is a token map. It contains no tool names, no tool identities, no set membership.**

### 1.3 Session / outcome records

`chat_messages`: `input_tokens`, `output_tokens`, `model_ref`, `is_error`, `error_detail`,
`response_id`, `finish_reason` (`migrate.py:299`), `usage_log_id`.
`chat_sessions`: `enabled_tools`, `enabled_skills`, `activated_tools`, `pinned_legacy_tools` — all
**session-level cumulative arrays**, not a per-turn snapshot, and populated on almost nothing:

```
825 sessions · 18 with activated_tools · 28 with enabled_tools
```

### 1.4 Coverage — the register's number, corrected

The register claims *"context telemetry covers 35% of messages and nothing before July 2026."*
**The second half is right. The first half is a denominator error.**

```
all rows 5,720 · assistant rows 2,653 · assistant rows with context_breakdown 2,212  → 83.4%
first context_breakdown 2026-07-02 · first message ever 2026-04-03
```

`context_breakdown` is written **only on assistant rows** (`stream_service.py:6906`). Dividing by all
5,720 messages includes user rows that structurally cannot carry one — `2,029/5,720 = 35%` is the
register's figure and its denominator contains a set that can never be in the numerator. This is the
same shape as the repo's own *"derive the denominator from the SSOT, not from what you built"*
lesson, inverted.

**Per month (measured):**

| month | assistant rows | with `context_breakdown` | with `finish_reason` | with `input_tokens` |
|---|---|---|---|---|
| 2026-04 | 84 | **0** | **0** | 39 |
| 2026-05 | 108 | **0** | **0** | 6 |
| 2026-06 | 192 | **0** | **0** | 188 |
| 2026-07 | 2,263 | 2,209 (97.6%) | **243 (10.7%)** | 2,222 |
| 2026-08 | 6 | 3 | 6 | 3 |

**So the correction cuts both ways.** Context telemetry is *better* than the register says (98% in
July). But the register was looking at the wrong column: **the turn-OUTCOME column, `finish_reason`,
covers 249 of 2,653 assistant rows — 9.4%.**

```
finish_reason:  NULL 2,404 · stop 205 · awaiting_input 31 · interrupted 11 · error 2
```

**90.6% of every assistant turn ever recorded has no recorded outcome at all.** P6's flagship
observation — *"the turn ended `interrupted`, not `stop`"* — is a statement about a column that
exists for 1 turn in 11.

---

## 2 · What is NOT recorded that a per-tool acceptance test needs

### RT5-1 (KILLS) — the advertised tool set per turn is persisted nowhere

**The set exists in memory and is thrown away.** It is assembled at
`stream_service.py:2101-2144` and handed to the provider at `:2143-2144`
(`request_kwargs["tools"] = advertised`). Three things read it, and **none of them writes to a
store**:

1. **`AgentSurfaceTracker.advertised_pass`** (`services/chat-service/app/services/agent_surface.py:179-221`),
   called at `stream_service.py:2190-2197`. Its payload carries the full name lists
   (`agent_surface.py:130`) and is **yielded as an SSE frame** — a live inspector feed. Grep the
   persistence path: the assistant UPSERT (`stream_service.py:6901-6928`) writes
   `content, content_parts, input_tokens, output_tokens, model_ref, tool_calls, context_breakdown,
   response_id, exclude_from_memory, local_date, finish_reason`. **`advertised` is not among them.**
   The column does not exist: the chat DB's complete tool-shaped column list is
   `chat_messages.tool_calls`, `chat_sessions.{activated,enabled,pinned_legacy}_tools`,
   `chat_suspended_runs.{pending_tool_call,pinned_step_tools}`, `user_tool_approvals.tool_name`.
2. **A log line** — see RT5-8.
3. **`schema_tokens`** — a token *count*, folded into `context_breakdown`, identity-free.

**And the deletion itself is unrecorded.** `budget_names_by_tokens`
(`services/chat-service/app/services/tool_surface.py:125-162`) returns **only `kept`**. It never
returns, logs or emits the dropped names. Its sibling twenty lines below,
`budget_rail_tools` (`tool_surface.py:180-214`), returns `(kept, dropped)` and its own docstring
says why (`:197`): *"whatever gets dropped is REPORTED so the caller can log it rather than pretend."*
**The correct shape exists in the same file and was not applied to the function that P14 proved is
the root cause.**

Confirming the negative mechanically:

```
grep -rn "excluded_by|class Availability|Withheld" services/chat-service/app   →  0 hits
```

**The scenario:** the rebuild ships capability #4. A live run is driven; the model writes prose
instead of calling it; the turn is scored a failure and the capability's description is rewritten.
In fact the capability was budget-dropped, or suppressed by `failure_suppress`
(`stream_service.py:2100`), or filtered by ask-mode (`:2111`), and **was never on the wire.** Nothing
stored can distinguish those. This is arm E, in production, with the instrument the plan proposes to
use. **The design's own reproducible root cause is the one thing production cannot see.**

**Cheapest observation that settles it:** take any assistant row with a failed tool call and ask the
database which tools that turn advertised. There is no query that answers it.

### RT5-2 (KILLS) — there is no ground truth, anywhere

`message_feedback` (`migrate.py:409`) is the only label channel. **Live contents: 3 rows.**

```
rating=-1, reason='regenerated'  ×3 — one user, one session, 2026-06-28, 07:21/07:23/07:27
```

All three are auto-stamped by the regenerate path, not a human judgment. **0 rows carry a free-text
reason. 0 rows are positive. 0 rows exist since 2026-06-28.** Against 2,653 assistant turns that is
a labelling rate of **0.11%**, and the labels that exist say only *"the user pressed regenerate"*.

There is no column, anywhere, for:

* **which tool was the right one** for this request,
* **whether the turn satisfied the user**,
* **whether the turn's answer was correct**.

`finish_reason='stop'` means *the loop terminated*, not *the user got what they asked for*. P6's
capture is the proof: a turn can be a total product failure and the only stored evidence is a status
enum with 9.4% coverage.

**Consequence for the plan.** "Stack one brick, see if the tower falls" presumes a *fall detector*.
The detector is a human watching a screen. That is not telemetry; it is anecdote, and the register
already records what anecdote produced — thirteen mechanisms each verified by a live look.

### RT5-3 (KILLS) — the three causes are not separable

| the question | what would answer it | present? |
|---|---|---|
| did the tool fail? | `tool_calls[].ok=false` + `error` | ⚠️ **polluted** |
| did the model pick the wrong tool? | a ground-truth expected tool | ❌ none |
| was the right tool even on the wire? | the advertised set | ❌ none (RT5-1) |

The first is polluted because **58% of `ok=false` records are our own loop-breaker prose, not tool
failures** (P2, and the mechanism is visible at `stream_service.py:2834-2851` — the breaker builds a
`_steer` string and yields it through the same `{"tool_call": ...}` shape as a real result, with the
same `ok`/`error` fields). **Nothing in the record marks a breaker response as a breaker response.**
A per-tool acceptance test that counts `ok=false` per tool is therefore measuring, for the worst
tools, *how loudly our own breakers argued with the model*.

`tool_list` is the extreme case: 1,180 breaker fires attributed to a tool that never ran.

### RT5-4 (KILLS) — the standing acceptance instrument is blind to all three

The repo already has an instrument that answers *"does this tool work?"* per tool, and the audit
cites it: **matrix 211/224 passing, ship gate "0 tools blocked"**
(`docs/specs/2026-08-03-agent-runtime-unification/audits/06-documented-intent-and-drift.md:436-459`).
P8 falsified its verdict from production data (12 tools at a **0%** real success rate, one at 0/101).
Reading the harness explains *why it could never have caught them*:

* **`scripts/eval/tool_liveness/sweep.py:1-8`** — the 224-tool sweep is explicitly **MCP-direct with
  zero model turns**: *"the CD4 ship gate blocks on `executes`, and `executes` does not need a
  model."* It answers *"does this work when called correctly?"* It cannot observe selection,
  advertisement, or identifier resolution — **the three things this entire spec is about.**
* **`scripts/eval/tool_liveness/probes.py:1-21`** — the model-driven set is **P0: 10 tools.**
* **`scripts/eval/tool_liveness/probes.py:144-194` + `run.py:63-67`** — **8 of those 10 set
  `needs_context: True`**, and `_context_for` returns `{"book_context": {"book_id": fx.book_id}}`.
  That is precisely the binding that makes the server-side `_inject_context_ids` repair fire. **The
  harness hands the model the identifier that 57% of production failures are about**, and it runs on
  a book-bound surface, while P6's failure was on plain `/chat` where `session_row["book_id"]` is
  NULL (`stream_service.py:5143`).

**Arithmetic: 224 tools · 10 model-driven · 2 without an injected identifier. Effective coverage of
the failure class this spec targets: 2 of 224 — 0.9%.** NV-2 (the subject cannot vary) and NV-4 (an
adjacent decision — fixture id injection — defeats the check) simultaneously.

The fourth harness is worse. `scripts/eval/tool_liveness/selection.py:18-22` scores selection by
asking the model to route **the tool's own longest `_meta.synonym`** back to it, with the whole
catalog as text, out of loop. The seed and the control are written by the same author in the same
file. That is the repo's own *"a check whose seed and control agree is theatre"* — and it also, by
presenting the whole catalog, structurally removes the arm-E variable.

---

## 3 · Statistical power, and whether the target model is deterministic

### RT5-5 (KILLS) — N=3 cannot reject the status quo

For a binary per-tool outcome, an exact one-sided 95% bound after `k` successes in `n` trials with
zero failures is `p_fail ≤ 1 − 0.05^(1/n)`:

| n | 95% upper bound on the true failure rate after n/n successes |
|---|---|
| **3** | **63.2%** |
| 10 | 25.9% |
| 29 | **9.9%** |
| 59 | 5.0% |

> **A 3/3 arm is statistically compatible with a tool that fails 63% of the time.**
> Production's *measured* average tool failure rate is **53.8%** (7,447 calls, 4,010 failed).
> **The status quo lies inside the confidence interval of every 3/3 arm in the POC.**

Symmetrically, arm E's 0/3 is compatible with a true success rate up to 63%.

Fisher's exact on 3/3 vs 0/3 gives **p = 0.05 one-tailed** — the *smallest p-value obtainable* at
n=3 per arm. So P14's result is the maximum evidence the design is achievable at that N, and it is
exactly at the threshold. **Anything less extreme than a total flip is undetectable:** 3/3 vs 1/3
gives p = 0.20.

**What an honest per-tool acceptance test needs:** to certify *"this capability reaches ≤10% failure"*
requires **29 consecutive successes** per capability. At the spec's ~20-capability target that is
**≈580 live turns per candidate surface**, plus a matched control arm if the claim is comparative.
That number should appear in §4 of DESIGN-HYPOTHESIS before any brick is stacked, because it decides
whether the acceptance test is affordable at all — and it is the argument for spending the effort on
*instrumented production traffic* rather than on hand-driven arms.

### RT5-7 (WOUNDS) — the chat path is not seedable, and the POC did not run production's config

* **No seed exists on the chat path.** `StreamRequest`
  (`sdks/python/loreweave_llm/models.py:134-184`) has `model_source, model_ref, messages, tools,
  tool_choice, temperature, max_tokens, reasoning_effort, chat_template_kwargs, stream_format,
  trace_id, stream_job_id, stateful, previous_response_id`. **There is no `seed` field.** A `seed`
  reaches a provider from exactly one place in the repo —
  `services/composition-service/app/engine/llm_json.py:144` — on the *job* path, and 133 `llm_jobs`
  rows carry it. **Zero chat turns can.**
* **Production temperature is 0.0, and unrecorded.** `StreamRequest.temperature` defaults to `0.0`
  (`models.py:147`); `stream_service.py:377-378` sets it only when the session supplies one, and
  **823 of 825 sessions have no `temperature` in `generation_params`** (the other 2 have `0.1`).
* **The POC arms ran at temperature 0.2** (`poc/P1-P2-findings.md:855`). So P14's five arms measured
  a configuration production does not use, and neither the POC nor production stores the temperature
  it actually ran at for a chat turn.
* Two consequences pull in opposite directions and both hurt: at 0.0 the three trials of an arm are
  near-perfectly correlated (**effective N ≈ 1**, sampling only server-side batching/MoE jitter); at
  0.2 they sample a distribution the product never runs.
* Minor, same seam: `stream_service.py:379-380` sets `request_kwargs["top_p"]`, but `StreamRequest`
  has no `top_p` field and Pydantic v2 ignores extras — **the caller's `top_p` is silently dropped.**
  A caller-supplied value defeated by the schema, exactly the pattern already in this repo's lore.

---

## 4 · Where the advertised set almost survives, and why it doesn't

### RT5-8 (WOUNDS) — one log line, no join key, evaporates on redeploy

`stream_service.py:2198-2214` logs the exact advertised names per pass. Its own comment states the
motive precisely: *"when the agent 'refuses' or reaches for the wrong tool, the first question is
'did it even SEE the tool it should have used?' — unanswerable from counts."* **The repo diagnosed
RT5-1 and answered it with a log line.** Why that is not telemetry:

1. **No join key.** It carries `session_id` only — no `message_id`, no `sequence_num`, no
   `iteration`. It cannot be joined to the `tool_calls` row it explains.
2. **Not queryable.** stdout, `json-file` driver, no aggregation.
3. **Destroyed on container recreate**, which the eval corpus records happening *~every 90 minutes*
   during a run (`audits/06:451-453`).
4. **Live proof of the retention:** the running `infra-chat-service-1` (up since 2026-08-03T04:46Z)
   contains **6** such lines, all from session `019fc893-…` — the P6 capture. Against 2,653
   assistant turns in the database, the surviving advertised-set record covers **6 passes**.
5. It requires `LOG_LEVEL=INFO` and `surface_tracker is not None`, neither of which is asserted
   anywhere.

### RT5-9 (WOUNDS) — `llm_jobs` records nothing for the chat surface

`loreweave_provider_registry.llm_jobs` is the only other store on the request path
(minted at `stream_service.py:2219-2222`, one job id per pass).

```
3,375 rows · operation=chat 3,254 · rows whose input carries a "tools" key: 0
```

For the **chat streaming surface** specifically the input body is literally `{"stream": true}`:

| `input` key set | rows | latest |
|---|---|---|
| `chat_template_kwargs, max_tokens, messages, reasoning_effort, response_format, temperature` | 1,899 | 2026-08-03 |
| `chat_template_kwargs, max_tokens, messages, reasoning_effort, temperature` | 868 | 2026-08-02 |
| **`stream`** | **148** | 2026-08-03 |
| `…, seed, temperature` | 133 | 2026-07-29 |

Those 148 rows are the chat surface's observability rows: **0 with a result, 0 with `tokens_used`,
0 with `tools`, 0 with `messages`.** Billing-neutral placeholders. The one store that sits on the
wire and *could* have captured the tools array captures the word `stream`.

---

## 5 · RT5-10 — the prior track record, sampled

Three of the thirteen, checked against `docs/standards/non-vacuity.md`.

**#10 — eager tool-index mode.** `docs/specs/2026-07-21-eager-tool-index-mode.md:28-35`:
*"✅ RIGHT … Confirmed four-for-four. Every 'the model is weak' verdict dissolved into one of our
bugs."* The evidence is **four anecdotes, no control arm, no repetition, N unstated per case**
("live-verified on weak Gemma" for the follow-on fixes). By the RT5-5 table, 4/4 bounds the failure
rate at ≤53% — i.e. it does not exclude the status quo. **NV-2:** state an input that would have
reddened it. There is none, because the acceptance criterion was *"the agent did the thing once
while I watched."* The document's own closing lesson — *"verify the mechanics (is the tool
advertised?…) BEFORE theorizing"* — names exactly the field RT5-1 shows is not stored.

**#8/#9 — `tool_list`/`tool_load` discovery.** `docs/eval/tool-liveness/discovery-gap/RESULTS.md:15,
32-40`: *"Discovery WORKS… The foundational concern is resolved… the hot-set + lazy-tail +
catalog-unification strategy is **validated**."* The same file states the harness **did not
replicate F18** (*"The probe over-reported the loop precisely because it did NOT replicate F18"*).
**NV-3, and with an exquisite twist:** the divergence the report treats as harness *noise* is the
mechanism P13 later proves is the *defect* — F18's auto-load feeding `budget_names_by_tokens`, which
deleted the answer. The verification declared the strategy validated by running a harness that
omitted the component that breaks it, and then blamed the harness for being pessimistic.

**#4 — `GROUP_DIRECTORY` + CAT-4.** `audits/06:222, 476-478`: *"24K → ~4,118 tok, 83% reduction,
**live-confirmed**."* The confirmed quantity is **prompt size**. Nothing in that verification
measures whether the model still selects correctly from the shrunken set — and shrinking the set is
the operation P14 later proved is the root cause. **NV-4:** a real check (token accounting) whose
subject was made permanently conforming by choosing the one metric that improves when the failure
gets worse.

**Pattern across all three: every "verification" measured something the mechanism could not fail at.**
That is not a run of bad luck — it is what happens when the only cheap instruments are a token
counter, a direct-MCP prober, and a human watching one turn. **A10 is not merely unproven; its
track record is a register of NV-2/NV-3/NV-4.**

---

## 6 · RT5-11 — what SURVIVES, and why A10 is repairable

`chat_messages.tool_calls` is a genuine instrument: 7,447 calls, every call, args and error text
retained, joinable to a session and a message, three months deep, and it is what produced every
number in P2/P8 that has survived red-teaming. `context_breakdown` at 98% of July's assistant rows
is real too.

**A10 is false today because of four missing fields, not because the idea is wrong.** The system
records *what the model did*. It records nothing about *what the model was allowed to do*, and no
statement about *whether it should have*.

---

## 7 · MINIMUM INSTRUMENTATION BEFORE ANY BRICK IS STACKED

Each item names table, column, write site. All four are additive; none needs a new service.

**I1 — `chat_messages.advertised_tools JSONB` (the wire record).**
Migration: a new `DO $$ … ALTER TABLE chat_messages ADD COLUMN advertised_tools JSONB` block in
`services/chat-service/app/db/migrate.py` (mirroring `:197-201`). **Must be a NEW chain entry** — a
DDL edit inside an already-applied block is a silent no-op.
Shape: `[{pass:int, tool_choice:str, core:[…], frontend:[…], activated:[…]}]`, one element per
provider pass.
Write site: accumulate at the existing chokepoint `stream_service.py:2143-2144` (the same place the
tracker and the log line already compute the split, `:2176-2197`), persist in the assistant UPSERT
at `stream_service.py:6901-6928` and the checkpoint/interrupt writers at `:5998` and `:6749`.
**This is the one item that makes arm-E-shaped silent deletion visible. Without it nothing else on
this list matters.**

**I2 — `chat_messages.withheld_tools JSONB` (the reason a tool was NOT on the wire).**
Change `budget_names_by_tokens` (`tool_surface.py:125-162`) to return `(kept, dropped)` exactly as
its sibling `budget_rail_tools` (`tool_surface.py:180-214`) already does — the shape is twenty lines
away in the same file. Every other filter on the path must contribute a row: `failure_suppress`
(`stream_service.py:2100`), `suppress_tool_list` (`:2105`), `_filter_tools_for_ask` (`:2111`),
`oneshot_deadvertise_mode` (`config.py:279-304`), `is_legacy_tool`.
Shape: `[{tool, stage, reason}]`. Write site: same chokepoint, same UPSERT.
This is `excluded_by`/R4 reduced to its telemetry core — and today
`grep -rn "excluded_by|Withheld" services/chat-service/app` returns **0**.

**I3 — `tool_calls[].source` + `tool_calls[].latency_ms` (stop counting our own prose as tool
failures).** Add `source ∈ {tool, breaker, meta}` at every site that mints a `{"tool_call": …}`
chunk — `stream_service.py:2872-2875`, `:2893-2896`, `:2975-2978`, and each breaker's
`working.append` (the F18 site at `:2868-2875` is the largest single source, 1,180 fires). No
migration needed; `tool_calls` is JSONB. **Until this exists, 58% of the error signal is noise and
no per-tool pass/fail rate is trustworthy.**

**I4 — turn outcome, made mandatory.** `finish_reason` covers **9.4%** of assistant rows. The
checkpoint writers already stamp `'streaming'`/`'awaiting_input'`; make every terminal path stamp a
value, and add a test that a turn ending by disconnect, error, cap or suspend leaves a non-NULL
`finish_reason`. Then add `chat_messages.expected_tool TEXT NULL` — written **only** by the eval
harness — as the minimum ground-truth column, so "did it pick the right one" is a SQL join rather
than a memory. Human feedback stays where it is (`message_feedback`), but note it has **3 rows** and
cannot be the acceptance channel.

**I5 — reproducibility on the chat path.** Add `seed: int | None` to `StreamRequest`
(`sdks/python/loreweave_llm/models.py:134-170`) and forward it (the job path already accepts one —
`composition-service/app/engine/llm_json.py:144`). Record the effective `temperature`, `top_p` and
`seed` on the turn (fold into `context_breakdown` or `advertised_tools`); today the chat path stores
none of them, and `top_p` is silently discarded by the schema (`stream_service.py:379-380` vs
`models.py:134-170`). Pin the eval config to production's `temperature=0.0` — **the POC's arms ran
at 0.2 and therefore did not measure the product.**

**I6 — the acceptance arithmetic, written into §4 before the first brick.** Per capability, a
≤10% failure claim needs **29 consecutive successes**; a ≤25% claim needs 10. **N=3 bounds nothing
below 63% and cannot separate a working capability from today's 53.8% baseline.** Either budget
~29 trials per capability, or accept that the acceptance signal is instrumented production traffic
(which I1–I4 make possible) rather than hand-driven arms.

**I7 — bite-test the new telemetry before trusting it (NV-6).** Deliberately drop a required tool
from the advertised set on a real turn and confirm that (a) `advertised_tools` shows its absence and
(b) `withheld_tools` names it with a stage and reason. Paste the output. Then put it back —
**without `git checkout` on that file.** A telemetry column that has never been watched to show a
deletion is exactly the vacuous check `docs/standards/non-vacuity.md` is a register of.

---

## 8 · The one-line verdict

> **A10 is false today.** The system records what the model *did* and nothing about what it was
> *allowed to do*, and it holds no statement anywhere about what it *should* have done. The plan's
> own root cause — a silent deletion from the advertised set — is not merely hard to observe in
> production; **there is no field in which it could appear.** Ship I1 and I2 first, or the rebuild
> inherits the thirteen predecessors' verification standard: a human, watching one turn, once.
