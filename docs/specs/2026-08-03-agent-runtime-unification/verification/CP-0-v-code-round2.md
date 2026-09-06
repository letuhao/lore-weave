# CP-0 · V-CODE — verdict, ROUND 2

Artifact frozen at `e75ad5d7d9c650ffc768fdcb767dddb6d96339d7`. `git status --porcelain` is **empty** —
the working tree is clean and the committed state is the state graded. (Round 1 recorded
`eval/arms/binding_format.py` as uncommitted-dirty; that is now committed.)

Source-only review. Nothing was run; no service was started; no tracked file was modified. No commit
message or rationale document was read. The round-1 verdict was read **only** as a list of claims to
re-check against current source; every finding below was re-derived from the code at this SHA.

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R1 | R2 |
|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | **FAIL** — mechanism still correct; both coverage holes untouched |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | **FAIL** — half-wired. The activation budget now reports; the per-turn hot-seed budget still does not |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | **FAIL** — `source` is now right at 2 of 3 dispatches; `latency_ms` is null at 28 of 30 mint sites |
| 0.4 | every terminal path writes an outcome | FAIL | **FAIL** — 2 of 6 holes closed; 6 paths still write none or a wrong one |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | **PASS** — hash re-verified by recomputation; F-9 unresolved but not fatal to the claim |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | **FAIL** — unchanged. No output exists in the index or on disk |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | **PASS** on the literal claim; the same two vacuity bounds, plus one new one |

Three round-1 findings are **genuinely resolved** (F-2, F-5, and F-1 *in part*). Six are not. The
shape of the round-2 delta is consistent: each fix closed the exact `file:line` the previous verdict
named, and the new gates were scoped to the file that was edited rather than to the property that was
claimed. Two of the three fixes are real and well-made; the third fixed four call sites out of eight
and shipped a gate that cannot see the other four.

---

## 2. The falsifier

Stated before the findings, so the two PASSes are readable. What I looked for that would have made
this FAIL, and what each search returned:

1. **A production caller still discarding the budgeter's drops.** *Found — four.*
   `tool_surface.py:336, 383, 424, 553`. Search: `grep -n "budget_names_by_tokens" ` over
   `stream_service.py` and `tool_surface.py`, then read each site. See F-1′.
2. **A real dispatch still filed as non-`tool`.** *The one round 1 named is fixed.* A **third**
   dispatch exists and is neither stamped nor recorded: `stream_service.py:7609`. See F-2′.
3. **A terminal path writing no outcome or a stale one.** *Found — six.* Full enumeration in §5.
   The specific stale-success round 1 named (`awaiting_input` surviving abandonment) is fixed.
4. **Committed output for the 0.6 measurement.** *Looked for; still does not exist.*
   `git ls-files eval/` → `eval/arms/binding_format.py`, `eval/arms/run_arms.py`, and nothing else
   under `eval/arms/`. `eval/arms/results/` is absent from disk. `grep -rn "binding_format"` over
   `*.md *.json *.py *.txt` finds no result artifact anywhere in the repo.
5. **`advertised_tools` overwritten rather than appended.** *Not found, again.* `record_pass`
   appends with `"pass": len(self._passes) + 1` (`instrument.py:199-207`); both upserts
   `COALESCE(EXCLUDED.…, chat_messages.…)` (`stream_service.py:6199-6200`, `7174-7175`). This
   remains the best-built part of CP-0.
6. **`source` defaulting to `tool`.** *Not found.* `ensure_tool_call_instrumented` assigns `meta`
   (closed name set) or `breaker` and flags `source_inferred` (`instrument.py:155-158`);
   `stamp_tool_call` raises on an unknown source (`instrument.py:116-117`).
7. **DDL appended to an already-applied ledger step** (the brief's flagged likely failure).
   *Not applicable, re-checked independently.* `services/chat-service/app/db/migrate.py` is one
   `DDL = """…"""` string (lines 3-786) executed in full on every boot by `run_migrations`
   (`migrate.py:789-791`). No version table, no step list, no applied-marker. The four new
   statements are `ADD COLUMN IF NOT EXISTS` (`:319, :327, :344, :359`). *How I searched:* read the
   file for a chain/step/version construct and read the runner. The repository rule the brief cites
   belongs to the Go services' ledgers, not to this one.
8. **A wiring gate that cannot fail, or that tests the wrong subject.** *Both gates can fail; both
   test one file rather than the property.* One of them is **green today over a live instance of the
   defect it names.* See §6.

Two things I **cannot determine from source**, unchanged from round 1 and worth restating because
they bound several verdicts:

- **Whether the recorded values are right.** Repository-wide search for
  `advertised_tools|withheld_tools|runtime_variant` across `*.py *.ts *.tsx *.go` returns exactly
  five files: `migrate.py`, `instrument.py`, `stream_service.py`, and two tests. `outcome` is absent
  from the read model (`routers/messages.py:80` exposes `finish_reason` and nothing new;
  `models.py:577` likewise). The one partial exception is `tc->>'source'`, read by
  `contracts/agent-runtime-baseline/baseline-metrics.sql:39` — and that query is the *pre*-CP-0
  baseline, where the field is NULL on every row by construction. So four of the five recordings are
  still write-only. This is a V-LIVE/V-METRIC question; from source I can only show the writes exist.
- **The real-world frequency of the D7 forced-final pass** (0.1 bypass), which depends on how often
  turns exhaust the write budget.

---

## 3. Findings

Ordered so the resolved ones are disposed of first.

### RESOLVED · F-2 → the approved Tier-A resume dispatch is now stamped

`stream_service.py:7711-7754`. The resume path now takes `_resume_t0 = _time.monotonic()` before
`knowledge_client.mcp_execute_tool(...)` and calls
`instrument.stamp_tool_call(_chunk, source=instrument.SOURCE_TOOL, latency_ms=_resume_ms)` at `:7752`
before handing `_chunk` out as `pre_tool_chunks`. The sibling denial branch is stamped
`SOURCE_BREAKER` **explicitly** at `:7764-7768` rather than left to inference, which is the stronger
form of the fix: the one branch where a human reader could mistake the classifier's default for a
decision now states it. Genuinely resolved, and resolved well.

### RESOLVED · F-5 → an abandoned suspend no longer keeps a success outcome

`stream_service.py:6296-6300`. The statement is now
`UPDATE chat_messages SET finish_reason = 'interrupted', outcome = $2 WHERE message_id = $1` bound to
`instrument.OUTCOME_ABANDONED_BY_USER`. Both columns move together. Genuinely resolved.

The **compounding half of F-5 is not resolved**: `sweep_expired_runs` (`db/suspended_runs.py:187`)
still has no caller anywhere in the service (`grep -rn "sweep_expired_runs" services/chat-service/`
→ one hit, the definition). A user who never returns to a confirm card leaves a row at
`outcome='awaiting_input'` permanently, because nothing ever reaches `_mark_suspend_abandoned` for it.
The fix corrected what the abandonment path writes; it did not make the abandonment path run.

### F-1′ · The budgeter reports its drops on the activation path and not on the surface path (0.2)

Round 1 named eight production sites. **Four are fixed** —
`stream_service.py:2915, 3031, 3133, 3312` now call `budget_names_by_tokens_ex` and extend
`_budget_withheld` with `{"tool": …, "stage": "token_budget", "reason": "did not fit the activation
token budget"}` (`:2924, 3040, 3142, 3321`), drained into the `advertised` event at `:2206-2208`.
That mechanism is correct and I could not fault it.

**Four are not**, all in `tool_surface.py`, all still calling the plain variant and discarding the
second return value:

| site | what it budgets | when it runs |
|---|---|---|
| `tool_surface.py:336` | `raw_hot_seed` — the whole surface's hot domains | **every turn**, fresh (`stream_service.py:5968`) and resume (`:7828`) |
| `tool_surface.py:383` | `plan_hot` — plan-mode skill tools | curated plan-mode turns |
| `tool_surface.py:424` | `extra_hot` — pinned-skill hot domains | curated turns with a pinned skill |
| `tool_surface.py:553` | `effective_enabled_tools` — the glossary auto-union | curated glossary turns |

The first of these is the one that matters. `HOT_SEED_TOKEN_BUDGET = 2000` (`tool_surface.py:50`,
annotated *"~4-6 tools hot; rest lazy"*) against a **315-tool** frozen catalog. Its own comment at
`:333-335` describes the narrowing: *"token-budget the hot-seed instead of seeding the WHOLE
domain(s). Cuts the always-advertised base ~24K → ~4K."* That is the largest and most frequent
narrowing in the system, it fires on every single turn, and it registers nothing in `withheld_tools`.

It is also the one that structurally *is* arm E. `eval/arms/run_arms.py:118-120` builds arm E by
calling `budget_names_by_tokens_ex(catalog, {all book_* names}, token_budget=1500)` — a fixed token
ceiling over one domain's tools. I evaluated the committed budgeter against the committed snapshot:
that call keeps **6** tools and `book_list` is **absent**. The production analogue of that exact
call is `tool_surface.py:336` with `token_budget=2000`, and it is the one call site the fix did not
touch. The wired sites (`stream_service.py:2915` et al.) are the *activation* budget — they fire only
when the model calls `tool_load` or trips the `tool_list` category cap, which is a different and
rarer moment.

Two smaller residuals on the same item:

- `budget_rail_tools` **does** return `(kept, dropped)` and the caller **does** receive the drops —
  and sends them to `logger.warning` (`tool_surface.py:479-483`), not to `withheld_tools`. Unchanged
  from round 1.
- `_budget_withheld` is drained **only inside `if offered_tools:`** (`stream_service.py:2206`, nested
  under `:2070`). Drops accumulated during a tool-result pass are flushed on the *next* advertising
  pass. If the next pass is the D7 forced tool-free final pass (`last_iter`, `:2032`), there is no
  next advertising pass and the accumulated drops are discarded. The comment at `:2201-2205`
  correctly identifies that gating the budget stage on `discovery` would lose it; it is instead
  gated on `offered_tools`, one level out.

**Consequence:** the `token_budget` stage now exists and can fire, so this is no longer a signature
with no behaviour — but the column still does not capture the narrowing the column was justified by.

### F-2′ · A third real MCP dispatch is neither stamped nor recorded (0.3)

There are **three** `await knowledge_client.mcp_execute_tool(` sites, not two:

- `stream_service.py:4436` — in-loop dispatch. Stamped `SOURCE_TOOL` + `latency_ms` at `:4654-4655`.
- `stream_service.py:7712` — approved Tier-A resume. Stamped at `:7752`. **Fixed this round.**
- `stream_service.py:7609` — the **ext-tasks durable-gate `provide-input` dispatch**. It executes
  `<prefix>_task_provide_input` against MCP for real, and its result is appended to `working` as a
  `role: "tool"` message at `:7616-7619` — so the model sees it as a tool result. No
  `stamp_tool_call`, no `tool_call` chunk, no entry in `tool_calls_history`. It is not misclassified;
  it is **invisible**. A real dispatch that produces no recorded call is the same hole as a
  mis-sourced one, arriving from the other direction.

This matters twice, because it is also what makes the new wiring gate pass — see §6.

### F-3′ · `latency_ms` is still null at 28 of 30 mint sites (0.3)

`grep -c 'yield {"tool_call"'` over `stream_service.py` → **30**. `grep -n "latency_ms"` over the
same file → **2** (`:4655`, `:7753`). Every other recorded call receives
`chunk.setdefault("latency_ms", None)` at `instrument.py:161`.

The claim is *"every entry in `chat_messages.tool_calls` carries `source ∈ {tool, breaker, meta}`
**and** `latency_ms`."* The first conjunct now holds at the chokepoint. The second holds only as key
presence. Nothing reads `latency_ms` back (repository-wide search finds it in `instrument.py`,
`stream_service.py` and the test only), so no consumer would notice that ~93% of the values are
blank. `toBeVisible()` asserts presence, not content — a row rendering null is present, and blank.

### F-4 · The empty terminal turn still writes nothing, by documented exemption (0.4)

`stream_service.py:6140-6153`. `_persist_terminal_assistant` returns `False` before any write when
`not content and not reasoning and not tool_calls_history`, under a comment naming itself
*"CP-0.4, KNOWN HOLE, DELIBERATELY NOT CLOSED HERE … one of the four silent exits"*, deferred to
CP-3.6. Unchanged.

This is the brief's hunting ground #1 — a new gate shipping its own documented exemption — and I
record it as such. It is honestly labelled and now logged at INFO (`:6148-6152`), which makes it
countable, and the stated reason (writing a blank assistant bubble is a product change) is a real
constraint. None of that changes the arithmetic: the item claims *every* terminal path, and this is
the chokepoint all five in-turn terminal callers route through (`:6254`, `:6756`, `:6903`, `:7320`,
`:7357`).

### F-6 · The voice turn pipeline still records none of the four fields (0.1, 0.3, 0.4)

`voice_stream_service.py:578-587`. The assistant-row INSERT column list is unchanged:
`(message_id, session_id, owner_user_id, role, content, content_parts, sequence_num, model_ref,
branch_id, local_date)` — no `outcome`, no `advertised_tools`, no `withheld_tools`, no `tool_calls`.

This is not a tool-free path. `voice_stream_service.py:512-523` calls the shared `_stream_with_tools`
with `permission_mode="ask"`, so the pass emits `{"advertised": …}` events **including**
`permission_mode_ask` withholdings (`stream_service.py:2209-2222`). The voice consumer loop reads
`content` / `reasoning_content` / `usage` / `suspend` / `tool_call` (`:530-548`); the `advertised`
chunk is absorbed by `chunk_data.get("content", "")` and discarded silently. Its `tool_call` chunks
are emitted as SSE at `:487-489` with `continue` and are **never persisted at all**.

So every voice turn still has `outcome IS NULL`, and every tool a voice turn calls exists in no
`tool_calls` row. `runtime_variant` survives only because the DDL `DEFAULT 'legacy'`
(`migrate.py:359`) is the fail-safe direction — the one place the design's caution pays off here.

A third assistant-row writer, the proactive check-in at `routers/internal.py:926-929`, likewise
writes no `outcome`.

### F-7 · Passes with `offered_tools == False` still emit no record (0.1)

`stream_service.py:2070` — the entire CP-0.1/0.2 emit block (`:2152-2264`) sits inside
`if offered_tools:`, where `offered_tools = tools_supported and not last_iter` (`:2069`).

The comment at `:2159-2160` still claims *"Emitted for a tool-FREE pass too (`names: []`)."* That is
true for a pass that reached the advertise filter and came out empty; it is false for the two ways a
pass is genuinely tool-free:

- **D7 forced-final pass** (`last_iter = write_passes >= max_iterations - 1`, `:2032`) — the pass
  that produces the user-visible answer after a tool loop. Unrecorded.
- **D8 provider tool rejection** (`tools_supported = False`) — every pass after it is unrecorded, and
  `advertised_tools` silently keeps only the pre-rejection passes.

Consequence, unchanged: the `pass` ordinals in the column do not correspond to the turn's model-call
count, and the concluding pass is missing whenever D7 fires. `_stream_via_gateway`
(`stream_service.py:343`) also emits nothing — defensible under the documented `None` ≠ `[]` semantics
(`instrument.py:233-241`).

### F-8 · Four of the five recordings are still write-only

Repository-wide, `advertised_tools|withheld_tools|runtime_variant` appears in exactly five files:
`app/db/migrate.py`, `app/services/instrument.py`, `app/services/stream_service.py`,
`tests/test_cp0_instrument.py`, `tests/test_tool_discovery.py`. No query, model field, router, script
or SQL reads any of them back. `outcome` likewise has no reader; `baseline-metrics.sql` computes its
§4 outcome table *through the `finish_reason` shim*, not from the column (`grep -n "outcome"` over
that file → one hit, in a prose comment at `:164`).

`tc->>'source'` **is** read (`baseline-metrics.sql:39`), which is a genuine improvement in kind over
the other four — but that query is the pre-CP-0 baseline and its own comment says
*"NULL for every pre-CP-0 row"*, so it does not demonstrate a live consumer either.

This is the brief's hunting ground #3, and the `finish_reason='streaming'` precedent it names is
reproduced. It does not by itself falsify *"the database records X"* — but it is the reason several
sub-verdicts here are bounded, and it is why no source-level evidence can show the recorded values
are right.

### F-9 · `run_arms.py` still claims an assertion it does not make (0.5)

`eval/arms/run_arms.py:112-114`: *"That the answer tool is absent is asserted below, never assumed."*
There is still no such assertion. `main` computes `has_answer` at `:193`, prints it in the header
`:194-196`, stores it in the results JSON `:198` — nothing exits or fails. If a future budgeter change
kept the answer tool, arm E would silently stop being an arm and would score like arm D.

I evaluated the committed budgeter against the committed snapshot: arm E resolves to **6** tools and
`book_list` is absent, so the variable holds *today*. Two docstring drifts also persist: the module
header (`:11-14`) says arm C is *"35 book_* tools, 19 retired"* and arm E is *"exactly the 7"*; the
committed detector over the committed snapshot yields 35 book_* tools, **17** retired, and **6** in
arm E.

### F-10 · No committed output for the binding-format measurement (0.6)

Unchanged. `eval/arms/binding_format.py` writes to `OUT_DIR = eval/arms/results` (`:42`, `:206`).
That directory does not exist on disk. `git ls-files eval/arms/` returns the two scripts and nothing
else. Nothing under `eval/` is git-ignored. `grep -rn "binding_format\|binding-format"` over
`*.md *.json *.py *.txt` finds only the script itself and the two verification prompts.

The script half is now fully committed (round 1 recorded it as working-tree-dirty), so the claim's
first clause holds. The claim is *"scripted **and its output committed**"*, and the second clause is
the one the checkpoint exists for. A method is not a measurement.

### F-11′ · `runtime_variant` and `declaration` are still constants — and now `unclassified` joins them (0.7, vacuity)

- `RUNTIME_AGENTRUNTIME` has no producer: `grep` finds it in `instrument.py:84` and the test only.
  Every write site passes `RUNTIME_LEGACY` (`stream_service.py:6124` default, `:7186`) or relies on
  the column default.
- `declaration` is `chunk.get("tool")` at both assignment points (`instrument.py:121`, `:159`) — no
  site passes a `declaration` differing from `tool`.
- **New this round:** `SOURCE_UNCLASSIFIED` was added to the vocabulary (`instrument.py:55, 57`) and
  `tool_call_source()` (`:87-97`) was written to return it as the fail-safe default for an unlabelled
  chunk — the docstring calls this *"the one place where the fail-safe direction matters most."*
  `tool_call_source` has **zero callers** anywhere in the repository (`grep -rn "tool_call_source"`
  → four hits, all inside `instrument.py` itself). The persistence chokepoint is
  `ensure_tool_call_instrumented`, which assigns `meta` or `breaker` and never `unclassified`
  (`:155-158`). So no row can ever carry the value, and the function that would assign it is dead
  code. The reasoning in that docstring is sound; nothing executes it.

All three are NV-class rather than item verdicts — a label is not a gate — but the third is new and
is exactly the shape the brief warns about: a correct mechanism with no caller.

---

## 4. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:116`) | **Yes** — a future mint site with a typo'd constant. Covered by `test_an_unknown_source_is_refused_at_the_stamp`. |
| `ensure_tool_call_instrumented` inference (`:155`) | **Yes, constantly** — 28 of 30 mint sites are unstamped. Fires on nearly every tool-bearing turn. |
| `tool_call_source` → `unclassified` (`:97`) | **No** — zero callers. F-11′. |
| `outcome` CHECK constraint (`migrate.py:344-346`) | **Yes** — a write site inventing a value fails the INSERT. Drift-guarded by `test_the_vocabulary_matches_the_database_constraint`, which parses the real DDL. |
| `runtime_variant` CHECK (`migrate.py:360`) | **No** — only `'legacy'` is ever written. F-11′. |
| `run_arms.py` hash-mismatch refusal (`:65-68`) | **Yes** — any edit to the snapshot's `tools` array. I re-verified the hash matches by recomputation. |
| `run_arms.py` "answer tool absent in arm E" | **Never** — the assertion does not exist. F-9. |
| The four discovery-gated `withheld_tools` stages (`stream_service.py:2171-2200`) | **Yes** — live suppressions today. |
| `permission_mode_*` stage (`:2209`) | **Yes**, but gated on `not discovery` — fires only on the non-discovery surface, which includes voice, where the event is then discarded (F-6). |
| `token_budget` stage (`:2924, 3040, 3142, 3321`) | **Yes** — on activation (`tool_load` / `tool_list` cap). **Never** for the per-turn hot-seed, which is the narrowing the stage was named for. F-1′. |
| Wiring gate A (budgeter) | **Yes**, but only against `stream_service.py`. §6. |
| Wiring gate B (dispatch stamping) | **Yes**, and it is **green today over a live instance of its own defect class**. §6. |

---

## 5. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | outcome | Δ vs R1 |
|---|---|---|---|---|
| 1 | clean finish | `stream_service.py:7147-7187` | `completed` ✅ | — |
| 2 | frontend-tool suspend | `stream_service.py:6903-6917` | `awaiting_input` ✅ | — |
| 3 | cancellation / client disconnect | `stream_service.py:7308-7344` | `abandoned_by_user` ✅ (`asyncio.shield`ed) | — |
| 4 | mid-stream exception | `stream_service.py:7346-7368` | `failed` ✅ | — |
| 5 | abandoned suspend, **no** provisional row | `stream_service.py:6287-6288` → `:6270` | `abandoned_by_user` ✅ | — |
| 6 | abandoned suspend, provisional row exists (**preferred branch**) | `stream_service.py:6296-6300` | `abandoned_by_user` ✅ | **FIXED** |
| 7 | empty terminal turn | `stream_service.py:6140-6153` | ❌ no row at all — F-4 | unchanged |
| 8 | mid-turn checkpoint (crash surrogate) | `stream_service.py:6751-6774` | `crashed` ✅ pessimistic — good design | — |
| 9 | process death **before** the first checkpoint | checkpoint sits inside the `if tool_call is not None:` branch (`:6731`→`:6751`), throttled by `_CHECKPOINT_MIN_INTERVAL_S = 1.5` (`:443`) | ❌ no row. A prose-only turn killed mid-stream records nothing; a tool turn killed inside the first 1.5 s likewise | unchanged |
| 10 | tool-loop pass exhaustion | `break` at `:1994` (`iteration >= max_total_passes`) and `:4722` (D7 defiance) → defensive yield at `:4723-4732` with `finish_reason: "stop"` | ⚠️ falls into path 1 → `completed`. A breaker exit is recorded as a clean success | unchanged |
| 11 | expired/mismatched resume | delegates to path 6 | ✅ | **FIXED** (consequentially) |
| 12 | voice turn (any ending) | `voice_stream_service.py:578-587` | ❌ column not in the INSERT — F-6 | unchanged |
| 13 | voice suspend refusal | `voice_stream_service.py:483-489` → same INSERT as 12 | ❌ | unchanged |
| 14 | proactive check-in | `routers/internal.py:926-929` | ❌ | unchanged |
| 15 | suspend never resumed and never expired | `db/suspended_runs.py:187` `sweep_expired_runs` has no caller | ❌ row sits at `outcome='awaiting_input'` forever | unchanged |
| 16 | spend-gate refusal | searched — no such gate in this service (`grep` for `quota\|insufficient\|spend_gate\|402` over `stream_service.py` and `routers/messages.py`) | n/a — the subject does not exist | — |
| 17 | turn-level timeout | searched — no wrapper. Consistent with the repository's standing "no timeout on LLM pipelines" position | n/a | — |

Two closed, six still reaching the end of a turn without a correct outcome; two of those (12, 15) are
common.

---

## 6. Judging the tests — with the two wiring gates read closely

`services/chat-service/tests/test_cp0_instrument.py` (340 lines) is still the only CP-0 test file. The
pure-function tests round 1 assessed are unchanged and remain honest, red-able work; I re-read them
and have nothing to add. Three checks are new. The brief asks specifically whether the wiring gates
can fail and whether they test the right subject, so I take them one at a time.

### Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:38-58`)

**Can it fail? Yes.** Reverting any of the four `stream_service.py` sites to the plain variant would
reintroduce the literal substring `= budget_names_by_tokens(` and trip `:52`; dropping the
accumulator trips `:50`; dropping the stage label trips `:58`; removing a call drops the count below
4 at `:55`. Determined by reading the assertions against the current file text: `:2907, 3024, 3130,
3310` are bare import lines ending in a comma (no `(`), so the `>= 4` count at `:55` is measuring the
four call sites and not the imports. It is a working gate.

**Is it the right subject? No.** Its entire input is `_stream_src()` — `app/services/stream_service.py`
and nothing else (`:25-26`, `:49`). The four remaining production call sites that discard their drops
live in `tool_surface.py`, and they are written in **exactly the form the gate forbids**:

```
tool_surface.py:336   raw_hot_seed = budget_names_by_tokens(
tool_surface.py:383   plan_hot = budget_names_by_tokens(
tool_surface.py:424   extra_hot = budget_names_by_tokens(
tool_surface.py:553   hot = budget_names_by_tokens(
```

Adding one file to the gate's input turns it red today. The gate's own docstring states the defect it
rejects as *"a correct mechanism with no production caller … count the callers"* — and it counts them
in one of the two files where they live, the one that was edited. A gate scoped to the region already
fixed reports safety over the region that was not.

It is also blind to two things a behavioural test would have caught: that `_budget_withheld` is
drained only under `if offered_tools:` (F-1′), and that no drop from the per-turn hot-seed can ever
reach the column at all.

### Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:60-77`)

**Can it fail? Yes.** Deleting the resume stamp at `stream_service.py:7752` drops `stamps` to 2
against `dispatches` of 3 and trips `:74`.

**Does it pass today over the defect it names? Yes.** The gate compares two *counts* with no
positional correspondence:

```
dispatches = src.count("await knowledge_client.mcp_execute_tool(")   # :4436, :7609, :7712  → 3
stamps     = src.count("source=instrument.SOURCE_TOOL")              # :3470, :4655, :7753  → 3
assert stamps >= dispatches                                          # 3 >= 3 → PASS
```

The stamp at `:3470` is the **subagent** site — deliberately not an `mcp_execute_tool` dispatch
(`instrument.py:129-130` says so explicitly). The dispatch at `:7609` — the ext-tasks
`provide-input` execution — has **no** stamp and produces no recorded call. So the equality holds
because one uncounted stamp exactly offsets one unstamped dispatch. The gate's docstring claims it
*"ties the count of real dispatch sites to the count of `tool` stamps, so ADDING a dispatch without
stamping it fails here."* Adding a dispatch **and** a stamp anywhere — including at a site that is
not a dispatch — passes. A tie by cardinality is not a tie.

This is the gate class the brief warns about most precisely: it fires on a plausible future
regression, and it is green right now over a live instance of the exact defect it was written to
reject.

### Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:296-320`)

**The best of the three.** It scans `stream_service.py` for `UPDATE chat_messages SET`, takes a
260-character window, splits at `WHERE`, and requires that any clause mentioning `finish_reason` also
mentions `outcome`. Two such statements exist (`:6297`, `:7193`); one contains `finish_reason` and is
checked. It closes with `assert checked, "found no finish_reason UPDATE at all — the gate would pass
vacuously"` — an explicit anti-vacuity guard on its own subject, which is the right instinct and is
rare. Reverting the F-5 fix turns it red. The window approach is deliberately documented and the
failure direction is safe (a clause longer than 260 chars false-*positives* red).

Its limit is the same as A's: one file. `UPDATE chat_messages` also appears at
`routers/messages.py:449` and `voice_stream_service.py:864` — neither touches `finish_reason` today,
so nothing is missed *now*, but a future `finish_reason` UPDATE in either file is invisible to it.

### What the suite still does not do

Unchanged from round 1 and still the whole gap. No test asserts that any INSERT actually carries
`advertised_tools` / `withheld_tools` / `runtime_variant`; that the DDL contains those three columns
at all (only `outcome`'s CHECK is parsed); that any terminal path passes an `outcome`; or that the
`advertised` producer and consumer agree — F-7 lives in exactly that seam, between
`stream_service.py:2264` and `:6779`, and nothing looks at it. The suite tests `instrument.py`, and
`instrument.py` is correct. Three call-site gates now also look at `stream_service.py`. Nothing looks
at `tool_surface.py`, `voice_stream_service.py`, or `routers/internal.py`, which is where four of the
six open findings live.

---

## 7. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:578-587` — the voice pipeline persists no `advertised_tools` though it runs `_stream_with_tools` (`:512`) and drops the `advertised` event at `:530`. Also `stream_service.py:2070` — every pass with `offered_tools == False` (D7 final `:2032`, D8 rejection) emits no entry, contradicting the comment at `:2159`. *Not* bypassed by overwrite: the recorder appends (`instrument.py:199-207`) and both upserts COALESCE (`:6199`, `:7174`). |
| **0.2** | `tool_surface.py:336, 383, 424, 553` — four production sites still call `budget_names_by_tokens` and discard the drops, including the per-turn hot-seed (`:336`, `HOT_SEED_TOKEN_BUDGET=2000` over 315 tools) that structurally *is* arm E. `budget_rail_tools`' drops go to `logger.warning` (`tool_surface.py:479-483`). `_budget_withheld` is drained only under `if offered_tools:` (`stream_service.py:2206`), so drops preceding a D7 pass are discarded. Search: `grep -n "budget_names_by_tokens"` over both files, every hit classified. |
| **0.3** | `stream_service.py:7609` — a real `mcp_execute_tool` dispatch that is neither stamped nor recorded; its result is fed to the model at `:7616-7619`. `latency_ms` supplied at 2 of 30 mint sites (`:4655`, `:7753`). Search: `grep -c 'yield {"tool_call"'` → 30; `grep -n "latency_ms"` → 2; `grep -n "mcp_execute_tool("` → 3, cross-checked against the three `stamp_tool_call` sites. |
| **0.4** | Six: `stream_service.py:6140-6153` (empty turn, self-documented exemption), process death before the `:6751` checkpoint (which sits inside the `tool_call` branch), `:1994`/`:4722`→`:4723` (breaker exit filed `completed`), `voice_stream_service.py:578`, `routers/internal.py:926`, and `db/suspended_runs.py:187` (`sweep_expired_runs` has no caller, so an un-returned confirm card stays `awaiting_input`). Full enumeration of 17 paths in §5. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/tools-list.snapshot.json` present (315 tools); I recomputed `sha256` over `json.dumps(tools, sort_keys=True, ensure_ascii=False, separators=(',',':'))` and it matches `catalog_sha256`. `run_arms.py` builds all five arms from that file and refuses on mismatch (`:65-68`). Two findings (F-9), neither fatal to the claim as written. |
| **0.6** | `eval/arms/results/` does not exist; `git ls-files eval/arms/` returns the two scripts only; nothing under `eval/` is git-ignored; no binding-format artifact anywhere in the repo by content search. |
| **0.7** | No bypass of the literal claim: both INSERT chokepoints route every entry through `ensure_tool_call_instrumented` (`stream_service.py:6161-6164`, and the `_emit_chat_turn` path), which sets `declaration` and `runtime_variant` unconditionally (`instrument.py:159-160`), and `DEFAULT 'legacy'` (`migrate.py:359`) is the fail-safe direction for an omitting writer — as `voice_stream_service.py:580` is. Bounded by F-11′ (both values constant, plus a dead `unclassified` path) and by the fact that voice-turn tool calls reach no INSERT at all, so *"every recorded call"* holds partly because those calls are never recorded. |
