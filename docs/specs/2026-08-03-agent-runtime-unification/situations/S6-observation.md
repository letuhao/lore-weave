# S6 · P5 OBSERVATION — coverage interrogation

**Module:** P5 Observation (`ARCHITECTURE.md` §0.2, §5) — five fields: `advertised_tools`,
`withheld_tools`, `source ∈ {tool,breaker,meta}`, mandatory outcome, wrong-object counter.

**Method:** every claim below is checked against the live schema (`infra-postgres-1`), the real
writers (`stream_service.py`), the real migration path (`app/db/migrate.py`), and the *current*
OpenTelemetry GenAI specification — fetched, not recalled.

**Verdict in one line:** the five fields are correctly chosen and each answers a real question, but
**they are all per-CALL or per-TURN, and every acceptance question this rebuild depends on is
per-PLAN, per-TASK, or per-PHASE.** P5 as specified cannot compute a single number in §4.2's
acceptance arithmetic.

---

## 0 · Ground — what actually exists, measured 2026-08-04

### 0.1 The store

`loreweave_chat.chat_messages` — 23 columns. Relevant ones:

| column | type | state |
|---|---|---|
| `tool_calls` | `jsonb` | the whole tool record. **7,447 elements** across **973 turns / 550 sessions** |
| `finish_reason` | `text` | **249 of 2,653** assistant rows populated = **9.4%** (2,404 NULL) |
| `context_breakdown` | `jsonb` | inspector payload — token split, trace spans, status chips |
| `input_tokens` / `output_tokens` / `model_ref` / `usage_log_id` | | per-**message** cost |
| `is_error` / `error_detail` | | transport-level, not tool-level |

**There is no `advertised_tools` column and no `withheld_tools` column.** Confirmed by `\d` and by
`grep -rn advertised_tools app/` → **zero hits outside the in-memory local variable** at
`stream_service.py:2130-2145`.

`finish_reason` distribution, live:

```
(null)          2404
stop             205
awaiting_input    31
interrupted       11
error              2
```

### 0.2 The real `tool_calls[]` element shape — derived from the data, not from the code

```sql
select jsonb_object_keys(e) as k, count(*)
from chat_messages m, jsonb_array_elements(m.tool_calls) e group by 1 order by 2 desc;
```

```
ok 7447 · args 7447 · tool 7447 · error 7416 · iteration 7416 · result 7416 · id 7411
activity 1129 · pending 31 · runId 31 · toolCallId 31 · task 10
```

**Seven fields. No `source`. No `duration`. No `error_class`. No `plan_id`. No `step`.**
`ok` split: **3,437 true / 4,010 false = 53.8% failure**, matching the 54.2% decontaminated figure.

### 0.3 The trap: `chat_sessions` *looks* like it answers §5.1 and does not

`chat_sessions` carries `enabled_tools text[]`, `activated_tools text[]`, `pinned_legacy_tools
text[]`. These are **session configuration, mutated in place, with no history**. Reading them to
reconstruct what a turn from 2026-07-13 advertised returns **today's** value. Any query that joins
them to a past turn is silently wrong. This must be stated in the spec, because it is the most
plausible shortcut somebody will take instead of adding the column.

### 0.4 The migration path is cheap — this is good news

`app/db/migrate.py` is **not a versioned ledger**. It is one idempotent `DDL` blob of
`ALTER TABLE … ADD COLUMN IF NOT EXISTS`, re-executed in full on every boot (`run_migrations`).
`finish_reason` was added at line 299 as exactly one such line. **Adding `advertised_tools` and
`withheld_tools` is two lines and no chain entry** — the *"DDL added to an applied ledger step is a
silent no-op"* hazard does not apply here. §4.3 items 1–2 are hours of work, not a migration project.

### 0.5 OpenTelemetry today — the "buy" is currently a no-op

- `sdks/python/loreweave_obs/setup_tracing()` installs a `TracerProvider` + OTLP/HTTP exporter +
  `FastAPIInstrumentor` + `HTTPXClientInstrumentor`.
- **`grep -rn "get_tracer|start_as_current_span" services/chat-service/app/` → zero.** There is not
  one manual span in chat-service. All tracing is auto-instrumented HTTP in/out.
- The running container has **`OTEL_EXPORTER_OTLP_ENDPOINT=""`** → `setup_tracing` returns early →
  **no-op tracer**.
- `otel-collector`, `tempo`, `grafana` exist in `infra/docker-compose.yml:1908-1950` behind the
  `observability` / `full` profiles and are **not running** (absent from `docker ps`).

> **We do not "already have OTel" for this. We have HTTP spans, switched off.**

### 0.6 The other two lanes (C3) — three stores, three vocabularies

| lane | store | rows | outcome vocabulary | args/result? |
|---|---|---|---|---|
| chat agent + browser-executed | `loreweave_chat.chat_messages.tool_calls` | 7,447 | `ok bool` + `finish_reason` (9.4%) | ✅ |
| third-party keys | **`loreweave_auth.mcp_call_audit`** | **345** | `{relayed, denied_scope, rate_limited, unauthorized, upstream_error, tool_error}` | ❌ none |
| FE bridge (8 tools, 2 files) | **nothing** | **0** | — | ❌ |

`mcp_call_audit` has `{audit_id, key_id, owner_user_id, method, tool_name, outcome, trace_id,
created_at}` — **no session, no turn, no arguments, no result, and an `outcome` enum that shares not
one value with `finish_reason`.** A cross-lane question is a cross-*database* UNION today.

### 0.7 The plan has no home

`workflows` (12 seeded rows, `steps jsonb`, `used_count`, `last_run_at`) lives in
**`loreweave_agent_registry`** — a different database from `chat_messages`. There is no
`workflow_runs` table, no `plan_runs`, no step table anywhere. `used_count`/`last_run_at` are the
entire execution record, and nothing writes them (there is no runner — §0.4 of ARCHITECTURE).

---

## 1 · What QUESTION must each field answer — as SQL, against the real schema

For each: the question, the SQL, and **what breaks it today**.

### 1.1 `advertised_tools`

> **Q1a — "When the model failed to call `X`, was `X` even on the wire?"**

```sql
-- INTENDED (needs the new column)
select
  count(*) filter (where 'book_list' = any(m.advertised_tools))            as was_offered,
  count(*) filter (where not ('book_list' = any(m.advertised_tools)))      as was_deleted
from chat_messages m
where m.role = 'assistant'
  and m.created_at >= now() - interval '30 days';
```

**Today this query cannot be written at all.** The nearest thing the schema permits is:

```sql
-- WHAT YOU CAN RUN TODAY — and it answers a DIFFERENT question
select count(*) from chat_messages m, jsonb_array_elements(m.tool_calls) e
where e->>'tool' = 'book_list';          -- => calls MADE, never calls OFFERED
```

That is the arm-E blind spot in one line: **the only evidence a tool exists is that it was called.**
A tool silently deleted by `budget_names_by_tokens` produces the identical row count as a tool that
was offered and correctly not needed. **This is the field the whole spec was written for.**

> **Q1b — "Did the advertised surface CHANGE inside a single turn?"** (F18 auto-load did exactly this)

This is the coverage hole *inside* the field. `tool_calls[].iteration` proves a turn has multiple
passes (7,416 elements carry it). A scalar `advertised_tools text[]` on the message row records
**the last pass** and silently loses the mid-turn mutation — which is the deletion event itself.

```sql
-- REQUIRED SHAPE: jsonb, one entry per pass
-- advertised_tools = [{"pass":0,"tool_choice":"auto","tools":[...]}, {"pass":1,...}]
select m.message_id, p->>'pass', jsonb_array_length(p->'tools')
from chat_messages m, jsonb_array_elements(m.advertised_tools) p
where jsonb_array_length(p->'tools')
      < (select jsonb_array_length(p2->'tools') from jsonb_array_elements(m.advertised_tools) p2
         where (p2->>'pass')::int = 0)
;   -- turns where the surface SHRANK mid-turn
```

**Design correction:** §5.1 says *"with `tool_choice` and pass number"* — so the intent is right, but
the field must be **`jsonb` (array of passes), not `text[]`**. A `text[]` cannot hold it. This is a
one-word change now and a migration later.

### 1.2 `withheld_tools`

> **Q2 — "Which filter, at which stage, is deleting the most reachable capability, and why?"**

```sql
select w->>'stage' as stage, w->>'reason' as reason, w->>'tool' as tool, count(*)
from chat_messages m, jsonb_array_elements(m.withheld_tools) w
where m.created_at >= now() - interval '7 days'
group by 1,2,3 order by 4 desc limit 20;
```

**Today: no column. And the writers are asymmetric** — `budget_rail_tools` already returns
`(kept, dropped)`; its sibling `budget_names_by_tokens` twenty lines above returns only `kept`.
Partial evidence exists at `stream_service.py:4222-4251` (`_withheld = c["name"] in
INTENT_GATED_SETUP_TOOLS`) but it is **log-only prose, not a row**.

> **Q2b — the one the field as-designed CANNOT answer: "is the withheld RATE getting worse?"**

```sql
-- BROKEN even with the field: the denominator moves under you
select date_trunc('week', created_at)::date,
       avg(jsonb_array_length(withheld_tools))
from chat_messages group by 1;
```

The admitted set changes **only by deploy** (§0.1) — which is exactly what makes it a valid
denominator and exactly why its absence is fatal. Two weeks with different manifests are not
comparable. **`withheld_tools` needs a companion `manifest_revision` on the same row.** Without it
the field records events but supports no *rate*, and every §5 question is a rate question.

### 1.3 `source ∈ {tool, breaker, meta}`

> **Q3 — "Of everything the model saw as an error, how much did a tool actually produce?"**

```sql
select e->>'source' as source, count(*),
       round(100.0*count(*)/sum(count(*)) over (), 1) as pct
from chat_messages m, jsonb_array_elements(m.tool_calls) e
where (e->>'ok')::bool = false
group by 1 order by 2 desc;
-- EXPECTED, from the audit: breaker ≈ 65.7%
```

**No migration needed — `tool_calls` is already `jsonb`.** This is the cheapest of the five and it
re-labels **4,010 rows' worth of signal per 7,447 calls.**

> **Q3b — the limit of the field, and it is a hard one.** `source` says **who wrote the message**,
> not **whose fault it was**. `source='tool'` covers both *"the tool correctly rejected bad input"*
> and *"our Go typed-struct dropped the field the model sent, then reported it missing"* (§0.5 shape
> 3). See §2.5 — this is C-12's territory and P5 has no field for it.

### 1.4 Mandatory outcome

> **Q4 — "What fraction of turns reached a defined terminal state, and what were they?"**

```sql
select coalesce(finish_reason,'(none)') as outcome, count(*),
       round(100.0*count(*)/sum(count(*)) over (),1) as pct
from chat_messages where role='assistant' group by 1 order by 2 desc;
-- TODAY:  (none) 2404 = 90.6%  |  stop 205  |  awaiting_input 31  |  interrupted 11  |  error 2
```

**90.6% of assistant turns have no recorded outcome.** Every §0.5 invariant is stated over this
column — *"`interrupted` is a defect, not an outcome"* is a claim about **11 rows out of 2,653**, and
the real `interrupted` population is hiding in the 2,404 NULLs. Making it mandatory does not just
improve a metric; **it is the difference between the invariant being checkable and being decorative.**

> **Q4b — "Is `awaiting_input` trending up?"** — §0.5 declares it a **success**. It is 31 rows. This
> is the single most important number in the recovery design and it is currently unmeasurable
> against a 90.6%-NULL denominator.

### 1.5 Wrong-object counter

> **Q5 — "How often did a call report success against the wrong object?"**

```sql
-- The query we want
select e->>'tool', count(*)
from chat_messages m, jsonb_array_elements(m.tool_calls) e
where (e->>'ok')::bool = true and (e->>'wrong_object')::bool = true
group by 1 order by 2 desc;
```

**This query is not merely missing a column — it is missing a DETECTOR, and that is a different
class of problem.** See §2.2. The only related artefact in the repo, `noop_write_counts`
(`stream_service.py:1895, 4062, 4411`), is:

- an **in-memory dict**, scoped to one turn's loop, **never persisted** — the "263 no-op writes"
  figure was obtained from logs, not from a column, and cannot be recomputed;
- counting a **different thing** — repeated `created=false` successes, not wrong-object successes;
- keyed on `f"{name}::{json.dumps(args)}"` for **tier A only**, so a wrong-object read is invisible
  to it by construction.

---

## 2 · Questions we will certainly need, for which the design has NO field

Ranked by how badly the rebuild needs them.

### 2.1 🔴 "Did the model pick the RIGHT declaration?" — there is no ground truth, anywhere

**This is the top gap and it invalidates the acceptance arithmetic.**

§4.2 requires **29 consecutive successes** to assert ≤10% failure. All five P5 fields define
"success" as `ok=true` — and **C-5 exists precisely because `ok=true` can be a lie.** The gate and
the failure class it must catch are defined in the same vocabulary.

What ground truth exists in the repo, measured:

| candidate source | rows | usable? |
|---|---|---|
| `message_feedback` (rating, reason) | **3** — against 2,653 assistant turns = **0.11%** | no |
| `message_feedback.regenerated_from_message_id` | column exists, **nothing writes it** | **not yet — but it is free** |
| a golden/labelled task set | **does not exist** | no |
| `chat_sessions.status` abandonment | derivable, **never derived** | **free** |

**Consequence:** solo-live-run admission (§6.2) has no scoreable outcome except `ok`, so admitting a
tool on 29 `ok=true` results admits it on the *one signal C-5 says is unreliable*.

**No new P5 field fixes this.** Ground truth must come from outside the runtime. The three cheapest
channels, in order:

1. **Wire the regenerate button to `regenerated_from_message_id`.** A regenerate is a revealed
   negative preference, it costs the user nothing, and **the column is already built.** This is the
   single highest-value unbuilt thing in the observation module.
2. **A frozen task set with expected end-state** (not expected tool sequence — that would re-fuse
   plan and execution, §0.4). Admission scores against end-state.
3. **An LLM judge over the turn**, `gen_ai.evaluation.*` shaped — but note the repo's own lesson:
   *a check whose seed and control agree is theatre*; the judge must extract, and code must compare.

### 2.2 🔴 "Did a wrong-object success happen?" — a counter is specified, a DETECTOR is not

§5.5 names a *counter*. A counter without a detector is a column of zeros.

**How is a wrong object even detected, given the caller does not know it was wrong?** Three
mechanisms, and only one is cheap:

| # | detector | cost | coverage |
|---|---|---|---|
| **a** | **at the substitution site** — C-5 says never substitute; when the runtime *would have*, count it. `stream_service.py:1619-1623` overwrites a non-UUID `chapter_id` with the turn's id | **trivial** — the code already knows | only substitution-shaped wrong-objects |
| **b** | **binding mismatch** — the plan bound `chapter_id` from step 3's `emits`; step 7 sent something else. **The plan knows; the call does not** | needs the plan executor | the 61.8% carry-forward class |
| **c** | post-hoc human/judge label | expensive | general |

> **(a) is the only one P5 can do alone, and it covers the smallest slice. (b) — the class that
> matters — is detectable ONLY from plan-level state.** The wrong-object counter is therefore
> **mis-located**: it is written as a P5 field but its evidence lives in the plan executor.
> Ship (a) now as a floor; state in the spec that general wrong-object detection is a **plan**
> capability, not an observation one, or the field will ship reading zero and be believed.

### 2.3 🔴 "Which plan was running, and which step failed?" — the new central object is invisible

§0.4/§0.5 make the plan the load-bearing new abstraction. **§5 gives it no field.** Missing:

`plan_run_id` · `plan_source ∈ {model, template, human}` · `workflow_id` (the template) ·
`manifest_revision` · `step_index` · `step_declaration` · **plan-level outcome ∈ {step-local,
binding-invalid, plan-invalid, needs-human}** · `replan_count` · `replan_budget_remaining` ·
`binding_satisfied_by ∈ {model, runtime}` · `done_when_result`.

```sql
-- UNANSWERABLE: "which step of which plan fails most, and does it replan or die?"
select r.workflow_id, s.step_index, s.declaration, s.plan_outcome, count(*)
from plan_runs r join plan_steps s using (plan_run_id)
where s.plan_outcome <> 'ok' group by 1,2,3,4 order by 5 desc;
--   plan_runs: does not exist.  plan_steps: does not exist.
--   workflows: exists — in loreweave_agent_registry, a DIFFERENT DATABASE.
```

Three consequences, each fatal to a stated claim:

1. **§0.5's invariant is unenforceable.** *"No plan may terminate except by satisfying `done_when` or
   by reaching a human; `interrupted` is a defect"* — with no plan-run row there is nothing to attach
   a terminal state to.
2. **The 61.8% claim becomes uncheckable.** §0.4 asserts the plan is a better carrier than the
   conversation. Proving it needs `binding_satisfied_by='runtime'` counted against
   `binding_satisfied_by='model'` — **that is the experiment**, and no field records it.
3. **Cross-database join.** `workflows.workflow_id` is in `loreweave_agent_registry`;
   `chat_messages` is in `loreweave_chat`. Even "which template did this turn adopt" is not a SQL
   join today. Store `workflow_id` denormalised on the plan-run row, or accept two-query analytics
   forever.

### 2.4 🔴 "Did the guardrail fire when the model would have recovered on its own?"

§0.5 property 3 — *"guardrail fire-rate must fall toward zero as model strength rises"* — is
**declared the test of whether we built an enabler or a ceiling.** It is currently unrunnable, for
two independent reasons:

1. **No fire event is recorded.** The six breakers mint prose into the message text. There is no
   `guardrail_fired` row, no breaker identity, no trigger evidence. `source='breaker'` (§1.3) gets us
   *"a breaker spoke"* but not *which one, on what evidence, after how many repeats.*
2. **The counterfactual is unobservable by construction.** A guardrail that fires *prevents* the
   next model action — so *"would it have recovered?"* is a question the instrumented system can
   never answer.

> **The only mechanism that answers it is a SHADOW ARM: on a sampled percentage of eligible turns,
> evaluate the guardrail, record that it *would* have fired, and DO NOT BLOCK.** Then compare
> outcomes. This is a **design requirement on the guardrail**, not a telemetry column, and **it must
> be built into the first version.** Retrofitting a shadow mode into a breaker that has always
> blocked means re-deriving a baseline nobody has.

Required fields once shadow mode exists: `guardrail_id` · `mode ∈ {enforced, shadow}` ·
`trigger_evidence` · `model_ref` (currently **nullable** on `chat_messages` — must be NOT NULL for
this comparison to mean anything) · the subsequent turn outcome.

### 2.5 🟠 "Was this failure the model's fault or ours?" — `source` is the wrong axis

`source ∈ {tool, breaker, meta}` answers *who emitted the text*. Fault attribution is orthogonal:

| case | `source` | fault |
|---|---|---|
| tool correctly rejects a bad id | `tool` | **model** |
| Go typed struct drops a misspelled key, then reports *"missing required"* | `tool` | **ours** (§0.5 shape 3) |
| breaker fires on a genuine model loop | `breaker` | **model** |
| breaker fires on a model that was about to recover | `breaker` | **ours** |

C-12 (fault locus) is a *contract* clause with **no observation field**. Needed on the call record:
`rejected_field_path` · `rejection_reason` · `accepted_alternatives` · **`dropped_by_server bool`**
(the corollary — *a field the server drops may never be reported as absent*). Without
`dropped_by_server`, the defect that makes a model unrecoverable is the one defect telemetry cannot
see, because it looks identical to a well-behaved rejection.

### 2.6 🟠 "How many admissions this week, and is throughput keeping up?"

§0.3 states the risk with a number attached: *"admission rate must be reported per phase, and a phase
that admits fewer than it retires is a red flag."* **No store exists.** The manifest is a git file —
it has revisions but no durable per-tool admission record.

```sql
-- UNANSWERABLE
select date_trunc('week', admitted_at)::date wk,
       count(*) filter (where event='admitted') as admitted,
       count(*) filter (where event='retired')  as retired,
       min(asserted_failure_bound)              as weakest_bound
from admission_ledger group by 1 order by 1 desc;
--   admission_ledger: does not exist.
```

Needs an **admission ledger**: `declaration_id` · `event ∈ {admitted, retired, amended}` ·
`admitted_at` · `consecutive_successes` · **`asserted_failure_bound`** (§6.3 — *"state the bound each
tool was admitted at; never state a bound the run cannot support"*, which is a **field**, not a
convention) · `adversarial_arm_result` · `manifest_revision`. Without `asserted_failure_bound`
persisted, §6.3's discipline is a docstring — and *consolidation claimed in a docstring is not
consolidation.*

### 2.7 🟠 "Is this regression new?" — the baseline cannot survive the rebuild

§7 makes the old runtime the **control group**. But a control group is only useful if the same metric
is computable on both arms, and:

- the old lane's record is `{tool, args, ok, error, result, iteration, id}` — **no `source`, no
  `advertised`, no outcome on 90.6% of turns**;
- **7,447 historical rows can never be re-labelled** — `source` is knowable only at emission time;
- so every new-runtime number will be strictly richer and **not comparable** to the control.

**What the design does not say and must:** the *minimum shared schema* both lanes emit. At minimum
the old lane needs `source` backfilled going forward (JSONB, no migration) and mandatory
`finish_reason` — otherwise the control group is frozen at a coarser grain than the claim it exists
to bound, and §7's "control group" is rhetorical.

### 2.8 🟠 Multi-lane (C3) — one telemetry table or three?

Measured in §0.6: **three stores, three outcome vocabularies, and one lane with zero rows.**

```sql
-- "all calls to composition_motif_bind this week, every lane" — needs a cross-DATABASE union
-- lane 1: loreweave_chat.chat_messages.tool_calls        (7,447 rows, ok bool)
-- lane 2: loreweave_auth.mcp_call_audit                  (345 rows, 6-value outcome enum)
-- lane 3: FE bridge, 8 tools, 2 files                    (0 rows — no telemetry at all)
```

**Recommendation: one logical schema, three writers, and one lane deleted.** §4.3a already found the
cheap fix — *"give those 8 real REST endpoints and MCP becomes exactly one lane with exactly one
telemetry table. Small, and it makes the denominator exact."* Do that **before** P5 ships, or P5
ships a per-lane vocabulary that will never be reconciled. `mcp_call_audit.outcome` sharing zero
values with `finish_reason` is what that looks like after the fact.

### 2.9 🟡 Cost and latency **per plan**, not per call

`input_tokens` / `output_tokens` / `model_ref` / `usage_log_id` are **per-message**. A plan spans
many messages and, per §0.5, possibly a replan. There is no grouping key.

```sql
-- UNANSWERABLE: "median cost of completing a plan, including replans"
select workflow_id, percentile_cont(0.5) within group (order by total_tokens)
from (select plan_run_id, workflow_id, sum(input_tokens+output_tokens) total_tokens
      from chat_messages group by 1,2) t group by 1;
--   plan_run_id: does not exist.
```

Also missing: **per-call latency**. `tool_calls[]` has no `duration_ms` — so "which admitted tool is
slow" has no answer, and `gen_ai.execute_tool.duration` (the OTel metric that would give it) needs a
manual span that does not exist (§0.5). Note the repo's own lesson that *latency + a short timeout +
a best-effort degrade is a correctness bug* — we currently cannot see the latency half of that.

Second cost ledger: unified-job LLM-call counts ride `params`, a **different** accounting from
`chat_messages`. Two ledgers, no join key.

### 2.10 🟡 `withheld_tools` has no denominator — `manifest_revision` is missing

Covered in §1.2/Q2b. `manifest_revision` on every turn row is one `text` column and it converts
every §5 field from an event log into a rate. §0.1's *"admitted changes only by deploy"* is exactly
what makes the revision a valid key.

### 2.11 🟡 Retention, sampling, and cardinality — the store the questions actually need

Every question in this document is *"over months, grouped by tool"*. That is an **analytical**
workload. Traces are sampled and retention-bounded; `chat_messages` is the only durable store.

> **Decision the design must make explicitly: Postgres is the system of record for P5; OTel is the
> live-debugging view.** If OTel is treated as the store, §4.2's 580-instrumented-turn budget is
> being accumulated in a sampled, expiring buffer — in a stack that **is not currently running.**

---

## 3 · OTel GenAI conventions — what they actually define, checked

Fetched 2026-08-04 from `opentelemetry.io` and
`github.com/open-telemetry/semantic-conventions-genai`.

### 3.0 Two facts about the "buy" that change its price

1. **The GenAI conventions have RELOCATED.** `opentelemetry.io/docs/specs/semconv/gen-ai/*` now
   serves only a redirect notice; every `gen_ai.*` attribute in the main registry is marked
   **Deprecated**, pending the move to `open-telemetry/semantic-conventions-genai`.
2. **Stability of the spans document is `Development`.** `gen_ai.tool.name`, `gen_ai.tool.type`,
   `gen_ai.operation.name` are all **Development**. Only `error.type`, `server.address`,
   `server.port` are **Stable** — and those are generic, not GenAI.

> **We would be buying a Development-stability convention mid-repository-relocation.** That is still
> the right buy for *attribute naming* — it costs nothing to name our columns after theirs — but it
> is **not** a buy that removes work, and the spec should not book it as one.

### 3.1 What the standard defines (verbatim)

**Execute-tool span** — name `{gen_ai.operation.name}`, i.e. `execute_tool`:

| attribute | requirement | stability |
|---|---|---|
| `gen_ai.operation.name` | **Required** | Development |
| `error.type` | Conditionally Required | **Stable** |
| `gen_ai.tool.name` | Conditionally Required | Development |
| `gen_ai.tool.type` ∈ `{function, extension, datastore}` | Recommended | Development |
| `server.address` / `server.port` | Recommended / Cond. Required | Stable |

**Inference span** (relevant subset): `gen_ai.operation.name` **Required** ·
`gen_ai.conversation.id` **Conditionally Required** · `gen_ai.response.finish_reasons` (string[])
**Recommended** · `error.type` **Conditionally Required** · **`gen_ai.tool.definitions` — Opt-In**.

**Metrics:** `gen_ai.execute_tool.duration` (Req `gen_ai.tool.name`; CondReq `error.type`,
`gen_ai.agent.name`) · `gen_ai.invoke_agent.tool_calls` · `gen_ai.invoke_agent.duration` ·
`gen_ai.workflow.duration` (CondReq `gen_ai.workflow.name`, `error.type`) ·
`gen_ai.client.operation.duration` · `gen_ai.client.token.usage`.

**MCP namespace — the entire registry:** `mcp.method.name`, `mcp.protocol.version`,
`mcp.resource.uri`, `mcp.session.id`. **Nothing records the contents or the size of a `tools/list`
response.**

### 3.2 The mapping verdict — our five fields

| # | our field | standard attribute | requirement | verdict |
|---|---|---|---|---|
| 1 | `advertised_tools` | `gen_ai.tool.definitions` | **Opt-In**, `any`/JSON | ⚠️ **name-only.** It is the full *schema blob*, not the name list; Opt-In means no vendor emits it; and it is a span attribute, not a queryable column. **Borrow the name, build the column.** No MCP attribute records `tools/list` contents |
| 2 | `withheld_tools` | **none** | — | 🔴 **fully custom.** OTel models *what happened*, never *what was suppressed*. There is no attribute, no metric, and no concept for it in either namespace. **This is our contribution and there is nothing to buy** |
| 3 | `source ∈ {tool,breaker,meta}` | **none** | — | 🔴 **custom.** `gen_ai.tool.type ∈ {function,extension,datastore}` is a *different axis* — what kind of tool, not who authored the result. Do **not** overload it |
| 4 | mandatory outcome | `gen_ai.response.finish_reasons` (string[]) · `error.type` | **Recommended** / Cond.Req | ⚖️ **half.** Call-level maps and `error.type` is the one **Stable** attribute we get. **Plan-level outcome** (`step-local`/`binding-invalid`/`plan-invalid`/`needs-human`) has **no standard**. And *mandatory* is ours — the standard says **Recommended** |
| 5 | wrong-object counter | **none** | — | 🔴 **custom, and worse than custom.** Every OTel error metric keys off `error.type`; a wrong-object success has `error.type` **unset by definition**. The standard's error model cannot express it |

**Score: 0 of 5 map cleanly. 1 name-only, 1 half, 3 pure custom.**

### 3.3 What we *should* buy, and it is not nothing

- **`error.type`** — Stable, the only stable GenAI-adjacent attribute. Use it verbatim for C-7.
- **`gen_ai.operation.name`, `gen_ai.tool.name`, `gen_ai.conversation.id`, `gen_ai.usage.*`,
  `gen_ai.request.model` / `gen_ai.response.model`** — free naming; zero reason to invent our own.
- **`gen_ai.execute_tool.duration`** — the per-call latency we are missing entirely (§2.9), and it
  needs one manual span.
- **`gen_ai.workflow.duration` + `gen_ai.workflow.name`** — the closest standard thing to plan
  telemetry. It gives duration and `error.type`; it gives **no step, no binding, no replan**.
- **`gen_ai.evaluation.{name,score.value,score.label,explanation}`** — the shape for §2.1's ground
  truth, if we build a judge.

**Concrete correction to `ARCHITECTURE.md` §0:** the build-or-buy row reads *"✅ buy — … OTel GenAI
conventions (P5)"*. On the evidence that should read:

> **⚖️ buy the vocabulary, build the store.** Adopt `gen_ai.*` / `error.type` naming; **build** the
> five fields as Postgres columns, because three of five have no standard attribute, the store is
> analytical not tracing, and the tracing stack is currently switched off.

---

## 4 · Minimum additions, ordered by (value ÷ cost)

| # | add | where | cost | unlocks |
|---|---|---|---|---|
| 1 | `tool_calls[].source` | JSONB, no migration | ~1h | §1.3 — re-labels 65.7% of the error signal |
| 2 | wire regenerate → `message_feedback.regenerated_from_message_id` | column **already exists** | ~2h | §2.1 — the only free ground-truth channel in the repo |
| 3 | `finish_reason` NOT NULL on every terminal path | 5 call sites already exist | ~2h | §1.4 — moves outcome from 9.4% to 100% |
| 4 | `advertised_tools jsonb` (**array of passes**, not `text[]`) | `migrate.py`, 1 line | ~3h | §1.1 — the field the spec exists for |
| 5 | `withheld_tools jsonb` + `manifest_revision text` | `migrate.py`, 2 lines + `budget_names_by_tokens` returns `(kept, dropped)` | ~1d | §1.2 — and gives every other field a denominator |
| 6 | `tool_calls[].duration_ms` | JSONB | ~1h | §2.9 |
| 7 | `dropped_by_server bool` + `rejected_field_path` | JSONB (C-12) | ~1d | §2.5 — the unrecoverable-model defect |
| 8 | wrong-object counter **at the C-5 substitution site** | `stream_service.py:1619` | ~2h | §2.2(a) floor — ship with the caveat that (b) needs the plan |
| 9 | `plan_runs` + `plan_steps` tables in **`loreweave_chat`** (denormalise `workflow_id`) | new | ~1w | §2.3, §2.9 — the whole recovery design |
| 10 | guardrail **shadow mode** + `guardrail_fired` rows; `model_ref` NOT NULL | design change | ~1w | §2.4 — must be in v1 or §0.5's test is permanently unrunnable |
| 11 | `admission_ledger` with `asserted_failure_bound` | new | ~2d | §2.6 — §6.3 becomes a gate, not a convention |
| 12 | one logical schema across three lanes; retire the FE bridge's 8 | §4.3a | ~1w | §2.8 — makes the denominator exact |

**Items 1–3 cost roughly one day between them and are the highest-leverage things in this document.**
Items 9 and 10 are the ones that must be decided *now*, because both are un-retrofittable: a plan
with no run table is invisible forever, and a guardrail that has only ever blocked has no
counterfactual to recover.
