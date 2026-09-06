# CP-0 · V-CODE — verdict, ROUND 6

Artifact frozen at `2ef8f0f7f25a1f9e6ac1a27cc1ec15cd71776ace`. **`git status --porcelain` is empty** —
the working tree is clean, so the committed state and the graded state are the same state. The brief
is unmodified: `git log aa9ef87c4..2ef8f0f7f -- …/CP-0-V-CODE-PROMPT.md` returns no commits.

Source-only review. Nothing in the product was run. No tracked file was modified. No commit message
or builder rationale prose was read. Every finding below was re-derived from source at this SHA.

**Method note.** For the gate audit I replicated all six gates verbatim over **in-memory** copies of
the real sources, applied one mutation each, and recorded the result — with `mutate()` asserting both
that the needle was present and that the string actually changed, because round 4's harness silently
no-op'd on two probes. That assertion fired once during this round (my first Gate-A needle did not
exist in the file) and I fixed the needle rather than recording a false "red". For behavioural
rulings I imported the real `app.services.instrument` and `app.services.tool_surface` and called the
real functions; where I say "measured", that is a mechanical result. The harness reproduces a fully
GREEN baseline on the unmutated tree before any mutation is applied, so a red is a real red.

**28 mutations. 11 blind spots. 1 false positive.**

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R3 | R4 | R5 | **R6** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — the fabricated literal is **genuinely gone**; voice now writes an honest NULL while dropping the `advertised` chunks it receives |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL** — R5's deletion defect is **genuinely closed**; the same edit converts a per-turn narrowing count into a per-pass count and falsifies the recorder's own stated invariant |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL** — `dedupe_recorded_calls` is **genuinely unwired** and nothing else deletes recorded calls; `latency_ms` still 3 of 33, voice calls still reach no INSERT |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL** — five paths unchanged, plus a **sixth** found this round: a voice turn that was cut short records `completed` |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS** |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | FAIL | PASS | **PASS** |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS** on the literal claim; one R5 bound (`dedupe`) removed, the others stand |

**Three retractions landed and all three are real. They belong on the record before the findings.**

1. **The voice `advertised_tools` literal (F-12) is genuinely reverted.**
   `voice_stream_service.py:608` binds `None`, with a retraction comment at `:595-607` that states
   the original justification was false and names the two lines (`:449`, `:453`) that falsify it.
   The hand-typed `[{"pass":1,…}]` appears nowhere in the app package except inside that comment
   (`grep -rn '"pass":'` over `app/` returns three hits: `instrument.py:304`, `instrument.py:362`,
   and the comment). **This is the correct response to a fabricated value: withdraw it, do not
   improve it.**
2. **`dedupe_recorded_calls` is genuinely unreachable from production.**
   `grep -rn dedupe_recorded_calls` over `services/chat-service/` returns exactly three live hits:
   the definition (`instrument.py:153`) and two in `tests/`. Both persist paths now build
   `tool_calls_json` from a plain comprehension over `ensure_tool_call_instrumented`
   (`stream_service.py:6192-6194`, `:7038-7043`). I searched for any other route that removes a
   recorded call and found none — see §5.
3. **R5's Ruling 1(b) — the deletion of a true withholding — is closed, and I proved the fix
   load-bearing.** Reverting the dedupe key to `(tool, stage)` in memory makes
   `test_a_real_withholding_survives_the_reconciliation` go **red**; the real key
   `(tool, stage, len(self._passes))` makes it green.

**And the pattern held for a sixth round, in the same shape as the fifth.** The fix to 0.2 is at the
right layer and closes the cited defect — and the *same three-line edit* silently inverts the
recorder's other stated invariant. Measured, on the real class, in the ordering production actually
uses:

```
 1 passes ->  1 withheld records for ONE narrowing
 2 passes ->  2
 3 passes ->  3
 6 passes ->  6
10 passes -> 10
```

`record_withheld`'s own docstring, three lines above the changed key, still says: *"Deduplicated on
`(tool, stage)` so a tool dropped by the same stage on five passes is **one** withholding rather than
five — otherwise the count measures pass depth instead of narrowing."* That sentence is now false,
and the gate that names it is green only because it records zero passes.

---

## 2. The falsifier

Stated before the findings, so the three PASSes are readable. What I looked for that would have made
this FAIL, and what each search returned.

1. **The voice literal, or any surviving copy of it.** *Not found.* *How I searched:* `grep -rn`
   over `app/` for `"pass":`, `"count":`, `"names":`, `json.dumps([{`; then read every one of the six
   `INSERT INTO chat_messages` statements in the package and the bound value of every CP-0 column at
   each. The only occurrence of the literal is inside the retraction comment.
2. **Any *other* hardcoded instrument value in the app package** — the defect class I was told to
   hunt. **Found — four, one of them consequential.** §6. *How I searched:* the enumeration in (1)
   for values, plus a second sweep over every *causal or numeric claim* in the CP-0 comments,
   checking each against the code or the measurement it cites.
3. **A remaining path that deletes a recorded call.** *Not found.* *How:* `grep -n
   tool_calls_history` over `stream_service.py` — 14 sites, all append or read, none filter;
   `_collapse_identical_tool_calls` (`:1168`) has one caller (`:2844`) and runs on the model's
   *emitted* array **before** dispatch, so it removes duplicate requests, not records.
4. **A gate green over the defect it names.** *Found — three of six now (A, D, and newly the
   five-passes-is-one-withholding gate), with two more carrying named blind spots (B, E).* §4.
5. **A terminal path writing no outcome, a stale one, or a wrong one.** *Found — six.* §5.
6. **`advertised_tools` overwritten rather than appended.** *Not found, a sixth time.* `record_pass`
   appends (`instrument.py:303-311`); both upserts `COALESCE` (`:6229-6230`, `:7220-7221`).
7. **`source` defaulting to `tool`.** *Not found.* `ensure_tool_call_instrumented` assigns `meta`
   (closed name set) or `breaker` with `source_inferred` (`instrument.py:222-225`); `stamp_tool_call`
   raises on an unknown source (`:131-132`).
8. **DDL appended to an already-applied ledger step.** *Not applicable, re-checked independently.*
   `migrate.py` is one DDL string executed in full on every boot; no version table or applied-marker.
   All four CP-0 statements are `ADD COLUMN IF NOT EXISTS` (`:319, :327, :344, :359`) and I confirmed
   Gate F goes red when any one of the four is removed.

Two things I **cannot determine from source**, unchanged across six rounds:

- **Whether the recorded values are right.** `advertised_tools|withheld_tools|runtime_variant` still
  appears repository-wide in seven files and **no query, model field, router or SQL reads any of them
  back**. `chat_messages.outcome` has no reader; `latency_unmeasured` has no reader. This is the
  brief's hunting ground #3, and it is why F-12 could ship: a hand-typed value in a column nothing
  reads is found only by a path enumeration.
- **The live claim inside `dedupe_recorded_calls`'s docstring** (`instrument.py:157-161`): *"18
  entries, 18 distinct ids, 17 iterations … the excess is zero across all 37 rows."* That is a
  statement about the database and I did not run one. Its **direction** is now safe — the function is
  unwired, so a wrong retraction costs nothing — which is the correct way to be wrong here.

---

## 3. Was the specific defect class eradicated? — the hardcoded-instrument-value sweep

The brief asked me to confirm no similar hardcoded instrument value exists anywhere else in the app
package. **It does. Four remain, and one of them writes a success onto a turn the code has just told
the user it could not do.**

### F-14 · A voice turn cut short by a suspend is recorded `finish_reason='stop'`, `outcome='completed'` — **new, and the sharpest instance of the class**

`voice_stream_service.py:585` binds `'stop'` as a **SQL literal** and `:594` binds
`instrument.OUTCOME_COMPLETED` as an unconditional constant. Neither is derived from anything the
turn did.

The path that makes it wrong is in the same function, and its own comment proves the builder knows
the path is live (`:477-481`):

```python
_susp = chunk_data.get("suspend")
if _susp:
    last_usage = SimpleNamespace(...)
    yield _sse("error", {"errorText": "That needs a confirmation I can't do by voice — try it in text chat."})
    break                                   # :489
```

`break` exits the chunk loop and **falls straight through** to the flush at `:537` and the INSERT at
`:579`. There is no branch between them. So a turn in which the user was explicitly told *"I can't do
that by voice"* is written as `finish_reason='stop'`, `outcome='completed'`.

The comment at `:589-593` defends the constant with: *"It reaches this INSERT only on a clean finish,
so `completed` is the honest value."* **That is false against the same file, in the same way the
retracted `advertised_tools` comment was false against the same file** — a confident assertion about
control flow that the control flow contradicts, eleven lines above the reader. `permission_mode="ask"`
does not prevent it: `:477-481` says in as many words that *"a paid Tier-R read or a frontend tool
suspends even in 'ask' mode"*.

This is CP-0.4's stated failure mode exactly — a wrong value, not a hole — and no gate can see it:
Gate E asks only that the `outcome` column be **named**, and this INSERT names it (measured: binding
`None` in place of the constant leaves Gate E green, §4).

### F-15 · The `pass` stamp's justification cites a measurement that says something else

`instrument.py:353-357`:

> *"`max(len, 1)` fabricated a pass 1 for narrowings on turns where no pass was ever recorded,
> producing **145 records stamped at a pass that does not exist**."*

The only measurement of "145" in this run is `CP-0-v-metric-round6.md:389`, and it reports the
opposite mechanism: *"145 records are stamped at a pass that does not exist — `d0c8c43b` (47 records,
all **pass 3**, turn has 2 passes) and `18fd5eb4` (98 records, same). These are the **`len + 1`
off-by-one era**."* All 145 are pass-3-on-a-2-pass-turn. **None of them is a fabricated pass 1**, and
the no-pass population the comment describes is a *different* 332 records that carry no `pass` key at
all (same source, four lines above).

Worse, the state the fix protects against **cannot occur in production**. `record_withheld` has
exactly two call sites (`stream_service.py:6828`, `:6832`), both inside `if _adv_ev is not None:` and
both strictly after `record_pass` at `:6820`. Measured against the real recorder:

```
0-pass stamp:                          None      <- unreachable from stream_service
after a tool-free pass, stamp:         1         <- what production always produces
```

So `len(self._passes) or None` and `max(len(self._passes), 1)` are **identical on every production
path**. The edit is harmless and marginally more honest as a library contract. Its stated
justification — a measured 145-record defect it removes — is a number borrowed from a different bug
and attached to a branch that never fires. That is the same error the module's own header warns
about: *"a number that survives only by being repeated"*.

The test written for it (`test_cp0_instrument.py:314-318`) is red-able (reverting the stamp makes it
red — measured) but its **subject never occurs**, which under NV-1..6 is a `FAIL` finding on the gate
even though the code is correct.

### F-16 · The comment defending the new dedupe key asserts an invariant the key breaks

`instrument.py:333-334`: *"Including the pass **keeps the original intent** — a stage dropping a tool
on five passes is not five findings."*

Measured on the real class, production ordering (`record_pass` then `record_withheld`, as
`stream_service.py:6820-6830` does it): **five passes produce five records.** The original intent is
not kept; it is inverted. And the docstring twelve lines above (`:315-317`) still states the old
invariant as current fact.

The consequence is on the column, not just the prose. Every *persistent* narrowing now fans out by
the pass count: the `failure_breaker` suppression, the `suppress_tool_list` entry, the
`permission_mode_ask` filter list (which re-registers **every** filtered write tool on every pass),
and the `"*"` pseudo-tool at `stream_service.py:2326-2331`. A 6-pass turn that hides 20 write tools
now writes 120 withheld records where it previously wrote 20. Any count over `withheld_tools` — the
6.2% figure three live rounds measured, and any CP-4 comparison — now measures pass depth, which is
the exact failure the dedupe was introduced to prevent.

### F-17 · The clean-finish INSERT binds `completed` unconditionally

`stream_service.py:7229` binds `instrument.OUTCOME_COMPLETED` as a constant, consulting nothing. This
is the mechanism behind R5's 0.4 finding #10 (tool-loop pass exhaustion → defensive
`finish_reason: "stop"` at `:4743` → `completed`), restated here because it is the same class: a
value asserted rather than observed. Unchanged this round; recorded so the class count is honest.

**Bounded observations in the same family, not headline findings:**

- `routers/internal.py:928-930` — *"It is generated, complete and delivered by the time it lands
  here, so `completed` is honest."* `:914` is
  `await _generate_proactive_content(...) or _PROACTIVE_STATIC`, so a total generation failure lands
  the static fallback and is still recorded `completed`. The user did receive a message, so
  `completed` is defensible; the word *generated* is not.
- `stream_service.py:2328-2329` — the tool-free pass records
  `reason="provider rejected tools (D8) or ask-mode filtered all"`. The ask-mode case is knowable at
  that point (`offered_tools = False` is set four lines earlier at `:2314`); the disjunction guesses
  where the code holds the answer.
- `instrument.py:398` — *"So the final advertised set wins"* remains contradicted by the code, which
  reconciles per **stamped pass** (`:425`). Carried unchanged from R5. The code is the safer of the
  two, and **no test pins the difference**: replacing the per-pass lookup with a final-set-wins
  lookup leaves every test in the file green (measured).

---

## 4. THE GATE AUDIT — 28 mutations, 11 blind spots

`tests/test_cp0_instrument.py` (600 lines). **No gate was edited this round** — `git diff` over the
test file shows only one assertion flipped (`pass == 1` → `pass is None`) and two behavioural tests
added. Gates A–F are byte-identical to round 5, and `stream_service.py` changed by two equal-length
hunks, so every round-5 `file:line` still resolves. Every row below is a mechanical result.

### Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:42-85`)

| mutation | should be | **is** |
|---|---|---|
| revert one site to the plain variant (`stream_service`) | red | red ✔ |
| revert one site to the plain variant (`tool_surface`) | red | red ✔ |
| **delete the ContextVar fallback (`tool_surface.py:246-253`)** | red | **GREEN — but see below** |
| **a NEW narrowing that calls `budget_names_by_tokens_ex(...)` and discards `dropped`** | red | **GREEN** |
| rename the `token_budget` stage label (behaviour identical) | green | green ✔ |

**Correction to round 5, in the builder's favour.** R5 recorded the ContextVar-fallback deletion as
an uncovered blind spot for the fourth consecutive round. It is a blind spot *for Gate A* — and I
measured that **Gate D's behavioural half goes RED for it**: D calls the real
`_budget_and_register(None, …)` with the sink armed only through the ContextVar, so deleting the
fallback empties the sink and `assert sink` fails. **The suite is red-able for that mutation.** R5
audited per-gate and drew a suite-level conclusion it had not tested; I am withdrawing that row.

**Row 4 stands and is now the only uncovered one.** The `_ex` variant *returns* its drops, so a new
caller that ignores the second tuple element discards them exactly as completely as the plain variant
did — and the gate, which is drawn around "the plain function is not called", has no opinion. That is
the founding defect expressed through the function the gate exists to promote.

Also unchanged: the docstring at `tool_surface.py:237-239` still ships its exemption (*"``sink`` is
optional … That is a real hole and it is the honest one"*), contradicted by the fallback five lines
beneath it.

### Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:186-226`)

| mutation | should be | **is** |
|---|---|---|
| unstamp the in-loop dispatch (`:4453`/stamp `:4672`) | red | red ✔ |
| a 4th unstamped `knowledge_client` dispatch appended at EOF | red | red ✔ |
| **a dispatch through a differently-named receiver (`await _kc.mcp_execute_tool(`)** | red | **GREEN** |
| a 4th unstamped dispatch inserted **after** the `:3487` stamp, before `:4453` | red | **red ✔** |
| **a 4th unstamped dispatch inserted BEFORE the `:3487` stamp** | red | **GREEN** |

**Correction to round 5, again in the builder's favour and more precisely.** R5 said any dispatch
*"inserted BEFORE line 4453"* is green. It is not. Region ownership means a new dispatch at position
`P` owns `[P, 4453)`; that region contains the subagent stamp at `:3487` **only if `P < 3487`**. A
dispatch inserted anywhere between `:3487` and `:4453` is caught. The blind spot is real but narrower
than recorded: it is *the first ~3,487 lines of the file*, where the subagent stamp is available to
pay for it. The gate's docstring claim — *"a surplus stamp somewhere else in the file can no longer
pay for a deficit here"* — is false in the backward direction only.

The renamed-receiver blind spot is unchanged and is the more likely one to fire: the run's whole
purpose is to add a new runtime module that will dispatch tools, and this gate reads
`stream_service.py` only.

### Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:548-572`) — **SOUND**

| mutation | should be | **is** |
|---|---|---|
| drop `outcome = $2` from the abandoned-suspend UPDATE (`:6327`) | red | red ✔ |

Carries an explicit anti-vacuity assertion (`:572`). Still one file only; the two other files
containing `UPDATE chat_messages` (`voice_stream_service.py`, `routers/messages.py:449`) do not touch
`finish_reason` today, so nothing is missed *now*. Unchanged and still the best-built gate.

### Gate D · `test_a_surface_narrowing_registers_without_anyone_wiring_it` (`:87-148`) — **UNCHANGED; STILL GREEN OVER FIVE ADJACENT DEFECTS INCLUDING ONE ITS OWN DOCSTRING NAMES**

| mutation | should be | **is** |
|---|---|---|
| delete the arming line at `:5991` (the R4 defect) | red | red ✔ |
| `surface_withheld.set(None)` instead of `set([])` | red | **GREEN** |
| the arming line demoted to a **comment** | red | **GREEN** |
| **adopt then immediately replace the sink** | red | **GREEN** |
| a **third** `discovery_seed_for_surface(` call site, unarmed | red | **GREEN** |
| **delete the drain** at `:6826-6830` | red | **GREEN** |
| rename `discovery_seed_names` → `_v2` (no behaviour change) | green | **RED** (false positive) |

All seven rows reproduce round 5 exactly. Row 3 is the finding: the gate's own assertion at
`:125-128` states the property *"the turn must ADOPT that sink rather than replace it, or the records
are discarded"*, and a mutation that adopts and then immediately replaces it is green, because the
assertion only checks that a string is **present**. Row 5 is the one that decides whether any of this
reaches the database and it is invisible. The gate is a regression pin for one line, not a check that
narrowings register — **and the behavioural half is the part that actually earns its keep**, since it
is what catches the Gate-A row-3 mutation above.

### Gate E · `test_every_assistant_row_insert_anywhere_writes_an_outcome` (`:150-184`)

| mutation | should be | **is** |
|---|---|---|
| voice drops the `outcome` **column** | red | red ✔ |
| a brand-new assistant INSERT in another file | red | red ✔ |
| an assistant `INSERT … SELECT` (no `VALUES`) | red | red ✔ |
| **voice binds `None` instead of `OUTCOME_COMPLETED`** — column named, value NULL | red | **GREEN** |
| a new assistant INSERT with the role bound as a **parameter** | red | **GREEN** |

Whole-package scope is the right population and it works. The two blind spots are unchanged from R4
and R5: the gate verifies the column is **named**. This is exactly why **F-14 is invisible to it** —
the voice INSERT names `outcome` and binds a constant that is wrong on a live path.

### Gate F · `test_the_vocabulary_matches_the_database_constraint` (`:574-599`) — **SOUND**

| mutation | should be | **is** |
|---|---|---|
| remove the `advertised_tools` / `withheld_tools` / `runtime_variant` `ADD COLUMN` | red | red ✔ (all three) |
| drift a value in the DB vocabulary | red | red ✔ |

Unchanged from R5 and still the round's cleanest fix.

### NEW this round — a third gate green over its own stated subject

`test_the_same_stage_dropping_a_tool_twice_is_one_withholding` (`:320-326`) records **five
withholdings and zero passes**, then asserts one entry survives. Measured:

| ordering | result |
|---|---|
| the gate's ordering (0 `record_pass` calls) | 1 entry → **GREEN** |
| production's ordering (`record_pass` then `record_withheld`, ×5) | **5 entries** → the property is **false** |

The gate's docstring names the property it protects — *"a count that measures how many passes the
turn took rather than how much was narrowed"* — and the code now produces exactly that count on every
turn the gate does not exercise. **This is the same shape as Gate A and Gate D: green over a defect
in its own stated subject.**

### The two behavioural tests added this round

- `test_a_real_withholding_survives_the_reconciliation` (`:356-375`) — **genuinely red-able**:
  reverting the dedupe key to `(tool, stage)` makes it red (measured). It is the gate R5 asked for on
  the input side. It does **not** pin the per-pass reconciliation: replacing it with the
  final-set-wins rule the docstring describes leaves it green.
- `test_dedupe_never_collapses_two_different_calls` (`:377-396`) — correct, red-able, and **a gate on
  dead code**. `dedupe_recorded_calls` has zero production callers by design. Under NV-1..6 a gate
  whose subject never occurs is a `FAIL` finding on the gate. Harmless here (it documents why the
  function must not be re-wired), but it should not be counted as coverage of anything shipped.

### Scorecard

| gate | boundary | red-able for its own defect? |
|---|---|---|
| A · budgeter wiring | text | **partly** — the R3 no-sink state IS caught (by D's behavioural half); still green over an `_ex` caller that discards `dropped` |
| B · dispatch stamping | positional syntax | **yes** for its three named sites; green over a renamed receiver, and over any dispatch inserted before line `:3487` |
| C · outcome/finish_reason lockstep | syntax | **yes**, within one file |
| D · surface narrowing arrives | text + behaviour | **source half NO** (5 blind spots + 1 false positive); **behavioural half yes**, and it is the suite's only real guard on registration |
| E · assistant-INSERT outcome | syntax, whole package | **partly** — catches a missing column anywhere; blind to a NULL/constant value (this is how F-14 hides) and to a parameterised role |
| F · outcome vocabulary + column existence | syntax over real DDL | **yes**, all four columns, both directions |
| — · five-passes-is-one-withholding | behaviour | **NO — green over a state production never reaches, while the property is false in the state it does** |

---

## 5. Terminal-path enumeration (0.4) — full, not summarised

No 0.4 code changed at this SHA. Five paths fail as in R4/R5; **#13 splits into two** because the
voice exception and the voice suspend-abort fail differently.

| # | terminal path | `file:line` | writes a row? | outcome | R6 |
|---|---|---|---|---|---|
| 1 | clean finish | `stream_service.py:7195` | yes | `completed` (`:7229`) | pass |
| 2 | frontend-tool suspend | `:6960` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7392` | yes | `abandoned_by_user` | pass |
| 4 | mid-stream exception | `:7433` | yes | `failed` | pass |
| 5 | abandoned suspend, no provisional row | `:6300` | yes | `abandoned_by_user` | pass |
| 6 | abandoned suspend, provisional row | `:6327` | yes | `abandoned_by_user` | pass |
| 7 | **empty terminal turn** | `:6170-6183` | **no** | ❌ none | **FAIL** — returns `False`; labelled a known hole, logged at INFO, countable |
| 8 | mid-turn checkpoint (crash surrogate) | `:6810` | yes | `crashed`, pessimistic | pass — good design |
| 9 | **process death before the first checkpoint** | checkpoint is inside the tool-boundary branch | **no** | ❌ none | **FAIL** — *crash* is named in the frozen criterion |
| 10 | **tool-loop pass exhaustion** | `break` at `:1994`/`:4738` → `finish_reason: "stop"` at `:4743` → `OUTCOME_COMPLETED` at `:7229` | yes | ⚠️ `completed` | **FAIL** — a breaker exit recorded as clean success |
| 11 | expired / mismatched resume | delegates to #6 | yes | ✅ | pass |
| 12 | voice turn, clean finish | `voice_stream_service.py:579-609` | yes | ✅ `completed` | pass |
| 13a | **voice turn, exception** | INSERT at `:579` is inside `try:` at `:440`; `except` at `:758` logs, emits SSE, returns | **no** | ❌ none | **FAIL** |
| 13b | **voice turn, suspend-abort** | `break` at `:489` falls through to the INSERT at `:579` | yes | ⚠️ `completed` + `finish_reason='stop'` | **FAIL — new this round.** F-14 |
| 14 | proactive check-in | `routers/internal.py:932-937` | yes | ✅ `completed` | pass (bounded — see §3) |
| 15 | **suspend never resumed, never expired** | `db/suspended_runs.py:187` — `sweep_expired_runs` has **zero callers** (re-verified: `grep -rn` over the whole service returns the definition only) | yes | ❌ stays `awaiting_input` forever | **FAIL** |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing "no timeout on LLM pipelines" | n/a | n/a | — |

**Six paths fail (#7, #9, #10, #13a, #13b, #15).** Gate E can see **none** of them: #7, #9 and #13a
write no row; #10, #13b and #15 write a value the gate does not inspect.

---

## 6. Findings

### F-14 · A cut-short voice turn is recorded `completed` (0.4, and the asserted-value class)
§3. `voice_stream_service.py:483-489` → `:579-609`. The one instance of the hunted defect class that
changes what the database says about a live path.

### F-15 · The `pass`-stamp fix cites a measurement that describes a different bug, and guards a branch production cannot reach
§3. `instrument.py:353-357`; `test_cp0_instrument.py:314-318`.

### F-16 · The pass-scoped dedupe key inverts the recorder's own stated invariant, and fans out `withheld_tools` by the pass count
§3. `instrument.py:333-336` vs `:315-317`; measured 1→1, 10→10.

### F-17 · `stream_service.py:7229` binds `completed` unconditionally
§3. The mechanism behind path #10.

### RESOLVED · The voice `advertised_tools` literal is genuinely gone
`voice_stream_service.py:608` binds `None`. Verified by enumeration of all six chat_messages INSERTs
and by a package-wide grep for the literal's keys. **Correct handling of a fabricated value.**

### RESOLVED · `dedupe_recorded_calls` is unreachable from production, and nothing else deletes a recorded call
Three live references, all in the definition or tests. Both persist chokepoints
(`stream_service.py:6192`, `:7038`) now map `ensure_tool_call_instrumented` over the history with no
filter. `tool_calls_history` is appended at `:6479` and `:6773` and never filtered.
`_collapse_identical_tool_calls` runs pre-dispatch on the model's emitted array.

### RESOLVED · R5 Ruling 1(b) — the destroyed-true-withholding — is closed
Proved load-bearing by mutation, and covered by a red-able test.

### F-18 · The voice pipeline receives `advertised` events and drops them (0.1)
`voice_stream_service.py:466-493` handles `usage`, `suspend`, `tool_call`, `content`, `reasoning` —
and nothing else. `_stream_with_tools` yields `{"advertised": …}` on **every** pass
(`stream_service.py:2234`, `:2264`, `:2323`); in voice those chunks fall through to
`content = chunk_data.get("content", "")`, evaluate to `""`, and are discarded. So the column is NULL
not because the data is unavailable but because the consumer ignores it. Voice also still writes no
`withheld_tools` and no `tool_calls` (`:584`), so voice-dispatched tools carry `source`,
`latency_ms`, `declaration` and `runtime_variant` only vacuously.

### F-1⁶ · 0.2's residuals, unchanged
- `budget_rail_tools` returns `(kept, dropped)` and its caller sends the drops to `logger.warning`
  (`tool_surface.py:257-291`; caller `:516-519`), not to `withheld_tools`.
- `_budget_withheld` is drained only inside `if offered_tools:` (`stream_service.py:2206-2208`); the
  tool-free block at `:2322-2331` does not drain it, so activation drops accumulated before a D7
  forced-final pass are discarded when that pass is the last.
- The tool-free record's withheld entry is `{"tool": "*", …}` — not a tool name, in a column typed
  `[{tool, stage, reason}]` — and it now registers **once per tool-free pass** rather than once per
  turn (F-16).

### F-9 · `run_arms.py` still claims an assertion it does not make (0.5)
`eval/arms/run_arms.py:114`: *"That the answer tool is absent is asserted below, never assumed."*
There is no such assertion; `has_answer` is computed, printed and stored, and nothing fails.
Unchanged from rounds 3–5. A docstring overstatement, not a bypass.

### F-11⁴ · `runtime_variant`, `declaration` and `unclassified` remain constants or dead (0.7, vacuity)
- `RUNTIME_AGENTRUNTIME` (`instrument.py:99`) has no producer; every write site passes
  `RUNTIME_LEGACY` or relies on `DEFAULT 'legacy'`.
- `declaration` is `chunk.get("tool")` at both assignment points (`:136`, `:235`).
- `tool_call_source()` (`:102-112`), the only function that can return `unclassified`, still has
  **zero callers**.
- **Improved:** R5's fourth bound — *"every recorded call" is a set `dedupe_recorded_calls` has
  removed members from* — is gone.

### F-8‴ · Six of seven recordings remain write-only
Unchanged, and it is the standing reason no source-level evidence can show any recorded value is
right. It is also the mechanism by which F-14 has survived: nothing reads `outcome`, so a constant
bound on a wrong path has never been contradicted by anything.

---

## 7. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:131`) | **Yes** — a future mint site with a typo'd constant. |
| `ensure_tool_call_instrumented` inference (`:222`) | **Yes, constantly** — 30 of 33 mint sites are unstamped. |
| `tool_call_source` → `unclassified` (`:112`) | **No** — zero callers. |
| `dedupe_recorded_calls` (`:153`) | **No — by design.** Zero production callers. Correct as a decision; its test is therefore a gate on dead code. |
| `_budget_and_register`'s ContextVar fallback (`tool_surface.py:246-253`) | **Yes** — armed before both entry points, and Gate D's behavioural half proves it live. |
| `withheld_json` reconciliation (`instrument.py:415-427`) | **Yes** — and it no longer destroys a true withholding (measured). |
| `record_withheld`'s `pass`-scoped dedupe (`:336`) | **Yes, on every multi-pass turn** — and it fans out a persistent narrowing by the pass count. F-16. |
| `"pass": len(self._passes) or None` → `None` (`:362`) | **No** — both call sites run after `record_pass`. F-15. |
| `pass_offered_no_tools` withheld record (`stream_service.py:2326`) | **Yes** — D7/D8/ask-mode. Names no real tool; now one entry per tool-free pass. |
| voice `outcome=OUTCOME_COMPLETED` (`voice_stream_service.py:594`) | **Fires on every voice turn, and is wrong on the suspend-abort path.** F-14. |
| `outcome` CHECK constraint (`migrate.py:344`) | **Yes** — drift-guarded by Gate F. |
| `runtime_variant` CHECK (`migrate.py:360`) | **No** — only `'legacy'` is ever written. |
| Gate A | **Yes**; still green over an `_ex` caller that discards `dropped`. |
| Gate B | **Yes** for its three named sites; blind to a renamed receiver and to any dispatch before `:3487`. |
| Gate C | **Yes**, with an explicit anti-vacuity assertion. |
| Gate D (source half) | **Yes** for the deleted arming line only; green over five adjacent defects. |
| Gate D (behavioural half) | **Yes** — the suite's only real guard that a narrowing registers. |
| Gate E | **Yes** for a missing column anywhere; cannot fire on a constant/NULL value or a parameterised role. |
| Gate F | **Yes**, all four columns and both vocabulary directions. |
| five-passes-is-one-withholding | **Green over a state production never reaches**; the property is false in the state it does. |

---

## 8. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:466-493` receives an `advertised` chunk on every pass and discards it; `:608` therefore binds NULL. The fabricated literal is gone (verified by enumerating all six `INSERT INTO chat_messages` and grepping the package for its keys). Not bypassed by overwrite: `record_pass` appends (`instrument.py:303-311`), both upserts COALESCE. |
| **0.2** | Arming closed (R5) and the output-side deletion closed (R6, proved by mutation). The remaining bypasses are **quantitative**: one persistent narrowing now writes one record per pass (F-16, measured 1→1 … 10→10), so any count over the column measures pass depth; plus `budget_rail_tools`' drops → `logger.warning`, `_budget_withheld` drained only under `if offered_tools:`, and the `"*"` pseudo-tool. |
| **0.3** | `source`: **no bypass found** — all three `await knowledge_client.mcp_execute_tool(` sites are stamped and recorded; the chokepoint classifies the rest by a closed name set; no `tool` default. **R5's deletion bypass is gone** and no other route removes a recorded call (search in §2.3). `latency_ms`: measured at 3 of 33 mint sites (`:4672`, `:7696`, `:7837`); the other 30 carry an explicit null plus `latency_unmeasured`. Voice tool calls reach no INSERT at all. |
| **0.4** | Six paths. Write **no row**: `stream_service.py:6170` (empty turn), pre-checkpoint process death, `voice_stream_service.py:758` (voice exception). Write a **wrong** value: `:1994`/`:4738` → `:4743` → `:7229` (`completed` on a breaker exit) and **`voice_stream_service.py:489` → `:585`/`:594` (`stop`/`completed` after telling the user the turn could not be done — F-14)**. Write a **stale** value: `db/suspended_runs.py:187`, zero callers. Full enumeration of 17 paths in §5. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/` holds the snapshot, the metrics SQL and the frozen output; `run_arms.py` builds all five arms and refuses on hash mismatch (`:65-68`). F-9 is a docstring overstatement. |
| **0.6** | No bypass. `git ls-files eval/arms/` returns both scripts plus `results/binding-format-20260804T035320Z.json` and `results/binding-format-FINDING.md`; grading is in code on the argument actually sent. |
| **0.7** | No bypass of the literal claim: both `stream_service` chokepoints route every entry through `ensure_tool_call_instrumented`, which sets `declaration` and `runtime_variant` unconditionally; `voice_stream_service.py:594` and `routers/internal.py:937` pass `RUNTIME_LEGACY` explicitly; `DEFAULT 'legacy'` is the fail-safe direction. Bounded by F-11⁴ and by voice tool calls reaching no INSERT — **one R5 bound removed**. |

---

## 9. What changed in the failure, and the one thing I would want recorded

**All three retractions are real, and two of them are the hardest kind to make.** Withdrawing a
fabricated value back to NULL costs a filled column and gains nothing visible; unwiring a function you
just built and defended, because a live verifier showed the bug never existed, costs more. Both were
done at the property, with the reasoning left in place so the next person cannot re-introduce them by
accident. That is the correct response to R5 and it should be credited without qualification.

**The thing I would want recorded is that the class did not close — it changed medium.** For six
rounds the defect has been *a confident answer to something nobody measured*. It was a column value
in R5 (the voice literal, the phantom dedupe). In R6 the column values are honest and the confident
answers have moved into **the justifications**: a 145-record measurement borrowed from a different
bug to defend a branch that cannot fire (F-15), and a claim that an invariant is "kept" by an edit
that measurably inverts it (F-16). One instance did not move at all and is the finding of this round:
`voice_stream_service.py`'s `outcome` is still a constant defended by a sentence about control flow
that the control flow eleven lines above contradicts (F-14) — **the same sentence-shape, in the same
file, as the comment retracted this round.** The literal was withdrawn; the habit that produced it
wrote the same defence about a different column and nobody re-read it, because a column nothing reads
is never contradicted.

**For the next round, the gate that would settle this class** is not another string check. It is a
gate that asserts **no CP-0 column is bound to a constant at any INSERT site** — every `outcome`,
`advertised_tools`, `withheld_tools` binding must be a value derived from a recorder or a variable
the turn computed. That gate goes red on `voice_stream_service.py:585`/`:594`, on
`stream_service.py:7229` and on `routers/internal.py:937` today, which is the correct starting score
for a checkpoint whose premise is that a later question about a turn has an answer that is not a
reconstruction.
