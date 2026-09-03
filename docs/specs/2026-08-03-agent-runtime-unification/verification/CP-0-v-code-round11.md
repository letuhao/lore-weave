# CP-0 · V-CODE — verdict, ROUND 11

Artifact frozen at `e6e38a8487b52435bed04ce42773ffba71cf349f`.

## 🟡 The freeze held on the ARTIFACT. HEAD advanced once, at the very end, touching nothing graded.

`git rev-parse HEAD` returned `e6e38a848` at my first call and at every checkpoint through the last
mutation batch; `git status --porcelain` returned **zero lines** at all of them. Every reading and
every measurement below is of a tree byte-identical to `e6e38a848`.

Between my final integrity check and this write, `HEAD` moved to `0b19d5e74`. I checked what it
carries: **`git diff --stat e6e38a848 0b19d5e74` is a single file, `RETROSPECTIVE-CP0.md`, +117 lines,
and `git diff … -- services/ contracts/` is empty.** No graded file changed. Recorded for the
freeze's owner — three consecutive rounds broke it with *code*; this one did not — and it changes
nothing in this verdict.

Source-only review. Nothing in the product was run. **No tracked file was modified** — all 70
mutations ran against an untracked copy of the tree under
`…/scratchpad/mt11/{services/chat-service, sdks, contracts}`. No commit message body was read; the
one `git log --oneline` call below was used to date a file's history, not to grade it.

**Method.** Same as R10 and extended: the real suite (`pytest tests/test_cp0_instrument.py`, **62
tests**, up from 56) run against the scratch copy, as written, no transcription. Each mutation
asserts (a) the needle occurs the expected number of times and (b) the text actually changed; a
needle-miss or no-op is reported *not applied* and never counted. Baseline verified GREEN before the
first mutation and after the last restore, in every batch. Four mutations were discarded after the
fact as invalid (two broke the module with a `NameError`, one was semantically a no-op, one was not a
defect) and are excluded from the score.

**70 mutations attempted · 7 not applied · 4 invalid · 59 scored: 30 caught, 29 blind.** The ratio is
*not* comparable to R10's 75/104 and I will not present it as a regression: R10 sampled the whole
suite including its strongest classes, this round deliberately concentrated on the **six changes I
was handed** and on R10's named blind spots. Every strong class R10 measured, I re-verified by
sampling (`H13` recorder-overwrite → red across 3 gates; `G19` source chokepoint → red across 7).

---

## 1. Verdict

**Overall: `FAIL`.**

Five of the six changes are real and three of them are the best work in this checkpoint. The sixth —
`finish_reason = 'abandoned_expired'` — **breaks the fix shipped beside it in the same commit**, and
the two together move the run's own acceptance number in the wrong direction while the file that
publishes it says `0.0%`. And the change the brief describes third did not happen: the
`domain_not_selected` registration was **never** inside `if binding_categories:`, at this SHA or at
the commit that introduced it, so the diagnosis in its comment and in its gate's docstring is false
about its own history.

| item | claim | R8 | R9 | R10 | **R11** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, **one entry per model pass** | FAIL | FAIL | FAIL | **FAIL, and it moved backwards.** The recorder still appends correctly (8/8 red). The *column* no longer holds one entry per pass: the concatenation stores one entry per **(pass × upsert)**, with repeated `pass` numbers. Measured: a 3-pass turn with 2 checkpoints stores **7** entries, pass numbers `[1,2,1,2,1,2,3]`. §3. Voice still binds the literal `None` (`voice:639`) — F-20, sixth round |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL, with a genuine closure inside it.** F-37 is **WITHDRAWN** — the sink is armed before catalog assembly at both paths and no re-arm survives between (§4, 6 mutations, 4 red incl. the verbatim reintroduction). But the same concatenation multiplies every withheld entry by the upsert count, and `domain_not_selected` alone registers ~215 tools/turn. Voice's INSERT still has **no `withheld_tools` column** (`voice:601-608`); `budget_rail_tools` still logs (`tool_surface.py:551`) |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL — unchanged.** `source` re-verified strong. `latency_ms`: deleting the `latency_unmeasured` mark outright is still **green** (`H5`) |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL.** §7. `outcome_source='path'` covers **2 of 4** assistant-row writers and is asserted by a **non-terminal** mid-turn checkpoint. #15 now writes a value **no reader in this repository understands** |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS at the letter, and the artifact is no longer frozen in substance.** All files tracked at the SHA (`git ls-tree`). But `baseline-metrics.frozen.txt` was **re-measured against a different corpus** (5,862 → 5,929 messages; `corpus_md5` `9cdacf69…` → `da6fdb5e…`) and **every class-1–5 number changed**. Fourth consecutive round the "frozen" baseline moved. F-47 |
| 0.6 | binding-format measurement scripted **and its output committed** | PASS | PASS | PASS | **PASS** — `eval/arms/binding_format.py` + `results/binding-format-20260804T035320Z.json` + `binding-format-FINDING.md`, tracked at the SHA |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS**, bounded by F-11 (no `agentruntime` producer). Re-verified: `G19` goes red across 7 gates |

| property | R11 ruling |
|---|---|
| **P1** — every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}` | **CLOSER THAN IT HAS EVER BEEN, still NOT MET.** The seventh frame (`intent_gate`) now genuinely reaches the sink — F-37 withdrawn. The eighth frame is a **no-op with a false rationale** (F-49): the block it claims to have hoisted was never nested. `budget_rail_tools` remains an unregistered narrowing; F-26 unchanged |
| **P2** — a call's `source` is assigned structurally, never inferred | **Unchanged and still the strongest class.** Disabling the chokepoint reddens 7 gates |
| **P3** — every terminal path writes an outcome | **NOT MET.** #13a (voice exception) writes nothing — re-verified at `voice:792-796`. #9b unrecorded. #15 writes a word no reader knows (F-45). #3, #10 carried |
| **P4** — no CP-0 column bound to a constant at any INSERT reachable from >1 terminal condition | **NOT MET at a NEW site, and this is the eighth asserted value.** `outcome_source = 'path'` is a literal at four positions across two upserts reachable from **six** conditions, one of which is *not a terminal path at all*. §5 |

**What landed, credited before the findings.**

1. **F-37 is withdrawn in full.** The sink is armed at `stream:5946` immediately before
   `filter_intent_gated_setup_tools` and at `stream:8037` before its resume twin; both later
   `set([])` calls are gone and replaced by comments explaining why. I reintroduced the defect
   verbatim (`H9`: delete the arm, restore it before the seed call) — **red**. I deleted each arm
   independently — **red, red**. I re-inserted a `set([])` between catalog assembly and the seed
   call — **red**. The gate that R10 pointed at the new call sites and found red today is now
   pointed at them by the builder. That is the third consecutive round a finding died by its own
   stated procedure.
2. **`EXISTS → NOT EXISTS` is closed.** R10's sharpest resolver blind spot — the inversion that
   would stamp `abandoned_by_user` on exactly the cards a user *can* still answer — now goes **red**
   (`D3`). A named blind spot was read and fixed.
3. **The concatenation is the right *diagnosis*.** COALESCE genuinely did erase a resume's pass
   history, and `AdvertisedToolsRecorder`'s docstring genuinely does promise "appended, never
   replaced". The problem is entirely in the *implementation*, and it is severe (§3).
4. **F-39 is closed as a side effect.** Because the sweep now moves `finish_reason` off
   `awaiting_input`, `_mark_suspend_abandoned`'s guard (`stream:6416`) no longer fires on a swept
   row, so a stale-card click can no longer rewrite a reconciler-marked row while leaving
   `outcome_source='reconciler'` in place. Not the stated purpose of the change, but real.

---

## 2. 🔴 THE HEADLINE — the two fixes shipped together defeat each other, and the direction is bad

This is the single most consequential thing in the artifact and neither half is visible from the
other's diff.

**The code fix** (`instrument.py:584-585`) now writes:

```
SET outcome = $1, outcome_source = 'reconciler', finish_reason = 'abandoned_expired'
WHERE m.finish_reason = 'awaiting_input' …
```

**The metric fix** (`baseline-metrics.sql:267-268`) now reads:

```sql
WHEN m.outcome IS NOT NULL AND m.finish_reason = 'awaiting_input' THEN m.outcome
```

**The branch requires the exact state the sweep has just eliminated.** I transcribed the class-4
`CASE` and ran every shape through it:

| row | written by | class 4 says |
|---|---|---|
| `finish_reason='awaiting_input'`, `outcome='abandoned_by_user'` | the sweep **as it was before this commit** | `abandoned_by_user` ✔ |
| **`finish_reason='abandoned_expired'`, `outcome='abandoned_by_user'`** | **the sweep as it ships now** | 🔴 **`unrecorded`** |
| `finish_reason='interrupted'`, `outcome='abandoned_by_user'` | `_mark_suspend_abandoned` (`stream:6424`) | `interrupted` |
| `finish_reason='awaiting_input'`, `outcome='awaiting_input'` | a live suspend (`stream:7060`) | `awaiting_input` ✔ |

`unrecorded` is **the number CP-0 exists to drive to zero**, and it carries the acceptance target
(`<5%`). A turn the instrument recorded three separate facts about — the outcome, the source, and a
finish reason — is counted by the run's own published class as one it failed to classify.

**And the frozen baseline proves the size of it.** `baseline-metrics.frozen.txt` at this SHA reports
`organic: 342 turns, abandoned_by_user 33, unrecorded 0, pct_unrecorded 0.0`. Those 33 rows carry
`finish_reason='awaiting_input'` **because the old build swept them**. The resolver's
`outcome IS DISTINCT FROM $1` guard means it will not re-touch them, so they stay classified — but
**every suspend that expires from now on** is stamped `abandoned_expired` and lands in `unrecorded`.
On the corpus as frozen, that is a drift from `0.0%` toward roughly `9.6%` (33/342) with no code
change and no traffic anomaly, in the exact bucket the number is supposed to certify.

**A third reader gives a third answer.** `outcome_for_finish_reason('abandoned_expired')` falls to
`case _` and returns **`interrupted`** — which this module's own DDL calls *"RETAINED AND DEPRECATED
… the metric to drive to zero"*. So one row now reads:

* `abandoned_by_user` in the `outcome` column,
* `unrecorded` through the published class-4 query,
* `interrupted` through the module's own migration shim.

F-38 asked for the two columns to stop contradicting each other. They no longer contradict each
other *inside the row*; the contradiction was **moved outward into three readers**, and the reader
that was fixed in the same commit is the one that now reads it wrong. The lockstep principle was
satisfied; the reason the lockstep principle exists was not.

**`abandoned_expired` is a value nothing else in the repository knows.** `grep` over
`services/chat-service/app`, `contracts/`, `frontend/src` returns exactly two hits — the write and
its own test. `finish_reason` has **no CHECK constraint** (`migrate.py:299` is a bare
`ADD COLUMN … TEXT`), so nothing at the schema level would have caught the introduction of a seventh
vocabulary word into a column whose documented vocabulary (`migrate.py:295-298`) is *"NULL = legacy;
'stop' = clean; 'error'; 'interrupted'"*. `AssistantMessage.tsx:217` badges only `interrupted` and
`error`, so the UI treats the new word as "no badge" — the same as the `awaiting_input` it replaced,
which is why this is a metric defect and not a product one.

**No gate anywhere covers class 4.** Deleting the new `outcome`-override branch from
`baseline-metrics.sql` outright is **green** (`G15`); deleting the new `abandoned_by_user` output
column is **green** (`G16`). The only test that reads that file (`:947`) asserts one substring about
the fingerprint.

### F-46 · and the fingerprint's stated justification is now false, with a gate enforcing it

`baseline-metrics.sql:35-39` says, in the fingerprint's own comment:

> *"`outcome` is deliberately NOT hashed. **No class below reads it** … A fingerprint must cover what
> the numbers DEPEND on."*

**Class 4 now reads `outcome`** — line 267, added in this commit. And
`test_the_fingerprint_does_not_hash_a_column_no_class_reads` (`:947-958`) actively asserts
`"coalesce(outcome,'')" not in pin`, i.e. it *enforces* the now-false rationale.

The live hole is narrow and I will not overstate it: the sweep also writes `finish_reason`, which
*is* hashed, so today's only outcome-writer that can move class 4 also moves the fingerprint. But the
invariant the file states about itself is violated, the gate keeps it violated, and one future writer
that stamps `outcome` on an `awaiting_input` row without touching `finish_reason` moves a published
acceptance number with a byte-identical pin — which is the precise defect the pin was rebuilt to
prevent in round 3.

---

## 3. MANDATE 1 — ruling on the concatenation

**It is the right diagnosis and a defective implementation. It duplicates, it grows quadratically
*within a single turn*, and it destroys the delta-encoding outright.**

`_advertised` is **one cumulative recorder per turn**, created at `stream_service.py:6520`.
`advertised_json()` returns `self._passes` — *the whole list so far* — and it is handed to a write at
**six** places: the mid-turn checkpoint (`:6909`, throttled to one per 1.5 s **at every tool
boundary**), the suspend checkpoint (`:7065`), the clean-finish INSERT (`:7363`), the cancel path
(`:7531`) and the error path (`:7572`). All of them upsert the **same `message_id`**. So each write
sends a *prefix of the same array*, and the SQL appends it to what is already stored.

I ran the real `AdvertisedToolsRecorder` against a transcription of the exact `CASE` expression:

```
S1  3 passes, 2 checkpoints + terminal  -> 7 stored entries;  pass numbers [1,2,1,2,1,2,3]
    duplicate pass numbers: {1: ×3, 2: ×3}   — byte-identical copies
S3  6 passes,  5 checkpoints            -> 22 stored entries (recorder holds 6)
S3 10 passes,  9 checkpoints            -> 56 stored entries (recorder holds 10)
```

**Can it duplicate passes?** Yes — *repeated `pass` numbers*, not merely repeated content. Pass 1 is
stored once per upsert. This is not an edge case: it is what **every tool-loop turn longer than 1.5 s
per boundary** produces, which is the normal shape of the turns CP-0 was built to measure.

**Can it grow unboundedly across resumes?** Yes, and worse than "grow":

```
S2  suspend checkpoint writes [pass 1: (a,b,c), pass 2: (a,b)]
    resume builds a FRESH recorder -> terminal write appends [pass 1: (a)]
    stored: pass numbers [1, 2, 1]
    "pass 1" now denotes two different sets in one array: ('a',) and ('a','b','c')
```

The array is no longer a sequence. `pass` stops being a key. A consumer asking *"what did the model
hold on pass 1?"* gets two contradictory answers with nothing in the row to order or disambiguate
them, and *"was tool X deleted between pass 1 and pass 2?"* — the founding question of this entire
effort, the one arm E failed — now depends on **which segment you happen to read**. COALESCE lost the
turn's history; concatenation keeps it and makes it unreadable. Both are wrong; this one is wrong in
the harder-to-notice direction, because the array is present, well-formed and longer.

**Does it break the delta-encoding a metric verifier flagged?** **Yes, completely.** Cumulative
reading of `withheld_tools` against `advertised_tools` is sound only if the array is monotone in
`pass`. The stored array is `[1,2,1,2,1,2,3]` — non-monotone by construction, and non-monotone
*across the resume boundary in content as well as in index*. Any cumulative reconstruction
double-counts by the number of upserts and, after a resume, reconstructs a surface the model never
held.

**Size.** `withheld_tools` is concatenated by the same expression, and `domain_not_selected` alone
registers ~215 entries per turn (the block's own comment: 237 of 315 catalogue tools). Six upserts
⇒ ~1,290 entries, each carrying a `reason` string naming the hot domains. This is a jsonb column with
no bound and no reader.

**Is the `NULL` handling right?** Yes, and it is the one part of the change I would keep unaltered.
Both `CASE`s test `EXCLUDED IS NULL` and `chat_messages IS NULL` before the concatenation, so a
bookkeeping write that carries no recorder preserves what is stored — the thing COALESCE got right.
I mutated it into the genuine data-loss form (drop the `EXCLUDED IS NULL` branch, so `a || NULL`
nulls the column) and it goes **red** (`G12`).

**Is any of this gated?** No. `grep` for `duplicat`/`dedup`/`distinct` across the 62 tests returns
nothing touching the persisted array. There is no assertion that `pass` numbers are unique, that the
stored array has the same length as the recorder's, or that it is monotone. The single mutation that
would matter most — *"the same pass is stored twice"* — cannot be expressed as a source mutation
because the defect **is** the shipped source.

---

## 4. MANDATE 2 — the gate audit. 59 scored mutations, 30 caught, 29 blind.

### 4.1 The three newest gates: can they fail?

**(a) Unconditional registration — the behavioural half works, the STRUCTURAL half cannot fail.**

`test_it_registers_on_a_turn_with_no_binding_categories` is a **good** gate: it arms the ContextVar
(production's own mechanism, *not* the `withheld_sink=` kwarg — correctly avoiding the "fifth
recurrence" its sibling docstring warns about) and calls the real function with
`binding_categories=None`. Every way I broke the registration reddened it: re-gating it behaviourally
(`A1`), nesting it structurally (`A2`), deleting it (`A3`), and killing it with `if False` (`A4`).

`test_the_block_is_not_nested_under_a_conditional` is the structural gate, and **it does not test
what its docstring says it tests.** Verified in isolation, not inferred:

```
mutation: the entire domain_not_selected block indented under `if binding_categories:`
$ pytest -k not_nested
1 passed
```

The gate collects `[st for st in fn.body if _mentions(st)]` where `_mentions` runs **`ast.walk`** over
the statement — so a top-level `ast.If` **transitively containing** the string satisfies it at any
nesting depth. It fires only when the literal `"domain_not_selected"` leaves the function entirely
(`A3`), which the behavioural gate already catches. As a nesting gate it is **vacuous**: it reports a
property it cannot observe, which is the NV-class failure this checkpoint's own brief calls *worse
than no gate*.

**(b) Resume concatenation — fails on the obvious reverts, defeated by its own comment.**

Red: revert both to COALESCE (`B1`), revert *one* (`B2`), reverse the operands (`B3`), remove a NULL
branch (`G12`). Then:

```
I5  the CASE replaced by `advertised_tools = EXCLUDED.advertised_tools`
    — a pure last-write-wins overwrite, the FOUNDING defect —
    with the three required substrings left behind as SQL comments   ->  GREEN
```

`test_the_upsert_concatenates_rather_than_replaces` is a raw `src.count(...)` over the file, and the
commit's own explanatory comment block sits directly above the expression. This is the **exact**
defect that `test_it_does_not_delete_the_evidence` was rewritten with `ast` to fix in round 10 —
credited then as *"the first time in ten rounds a prose-matching gate has been closed by reading the
code"*. The newest gate of round 11 is written in the defeated form, in the same file, one class
below the fix.

Also blind: a **third** upsert path that still COALESCEs (`H8` — I added one in
`voice_stream_service.py`; the `>= 2` count is already satisfied by the two in `stream_service.py`),
and the duplication of §3 entirely.

**(c) `outcome_source` two-directional — fails on deletion, defeated by a comment and a decoy, and
covers half the writers.**

Red: delete both DO-UPDATE assignments (`C2`), change both INSERT literals (`C3`), make the resolver
claim `'path'` (`C4`), make the assignment conditional (`C5`), drop the resolver's mark (`G24`). Then:

```
H2  both `outcome_source = 'path',` assignments prefixed with `-- `   ->  GREEN
I3  one VALUES literal replaced by NULL, `('path')` left in a comment ->  GREEN
I1  voice's INSERT claims outcome_source='reconciler'                 ->  GREEN
I4  the orphan user-row stamp claims outcome_source='reconciler'      ->  GREEN
```

And the substantive point behind `I1`/`I4`: **`'path'` is written by 2 of 4 assistant-row writers.**
`voice_stream_service.py:601-608` and `routers/internal.py:930-935` both write an `outcome` and leave
`outcome_source` NULL; so does the orphan user-row stamp at `stream:6233`. F-42 said NULL was
overloaded between *"a path recorded this"* and *"a pre-CP-0 row"*. It still is, for every voice
turn, every proactive check-in and every orphaned turn. The gate reads `_stream_src()` only — **a
gate's scope is part of the gate**, eighth recurrence, in the round's newest class.

### 4.2 Blind spots that remain (all measured this round, against the real suite)

| # | mutation | should be | **is** |
|---|---|---|---|
| H2 | both `outcome_source = 'path'` assignments commented out | red | **GREEN** |
| I3 | INSERT `'path'` literal removed, decoy left in a comment | red | **GREEN** |
| I5 | concatenation → plain overwrite, substrings left in comments | red | **GREEN** |
| I1 | voice claims `outcome_source='reconciler'` | red | **GREEN** |
| I4 | the orphan stamp claims `outcome_source='reconciler'` | red | **GREEN** |
| I6 | the reconciler binds a literal `'crashed'` instead of the constant | red | **GREEN** |
| H3 | resolver expiry neutralised with `OR true` (substring intact) | red | **GREEN** |
| H4 | resolver expiry widened by `+ interval '10 years'` | red | **GREEN** |
| D4 | resolver idempotency guard `outcome IS DISTINCT FROM $1` deleted | red | **GREEN** (carried) |
| D5 | resolver join → `m.parent_message_id` (matches nothing, forever) | red | **GREEN** (carried) |
| E4 | the arm becomes `surface_withheld.set(None)` — disarms the sink | red | **GREEN** |
| E5 | the arm wrapped in `if False:` | red | **GREEN** |
| H8 | a THIRD upsert path that still COALESCEs | red | **GREEN** |
| G13 | the mid-turn checkpoint stops carrying the recorder | red | **GREEN** |
| G15 | class 4's new `outcome`-override branch deleted | red | **GREEN** |
| G16 | class 4's new `abandoned_by_user` column deleted | red | **GREEN** |
| G1 | voice re-pins the literal `'stop'` (**F-24 reintroduced verbatim**) | red | **GREEN** (carried) |
| G2 | voice re-pins a fabricated `advertised_tools` (**F-20**) | red | **GREEN** (carried) |
| G3 | DDL `advertised_tools` → `advertised_tools_v2` | red | **GREEN** (carried) |
| G5 | reconciler call wrapped in `if False:` | red | **GREEN** (carried) |
| G6 | reconciler call moved **above** `run_migrations` | red | **GREEN** (F-44 carried) |
| G7 | resolver call wrapped in `if False:` | red | **GREEN** (carried) |
| G8 | user-row branch reintroduced as `role='user'` (no spaces) | red | **GREEN** (carried) |
| G9 | reconciler `AND` → `OR` (claims every un-outcomed assistant row) | red | **GREEN** (carried) |
| G11 | `catalog_miss` record moved **below** its own `continue` | red | **GREEN** (carried) |
| H5 | the `latency_unmeasured` mark deleted | red | **GREEN** (carried) |
| H6 | clean-finish outcome pinned to the constant (**F-19**) | red | **GREEN** (carried) |
| H7 | `_loop_finish_reason` capture defeated | red | **GREEN** (carried) |
| H14 | `'error'` no longer maps to `failed` | red | **GREEN** (carried) |

**Eleven of these twenty-nine are new**, and eight of the eleven are in code this round shipped.
**Every one of R10's carried blind spots is still blind** — none was addressed.

### 4.3 What is strong, stated so the audit is not selective

30 of 59 caught, and the strength is where the claim's arithmetic lives. Re-verified by sampling:
the recorder (`H13` overwrite-instead-of-append → 3 gates red), the source/declaration chokepoint
(`G19` → 7 gates red), the outcome vocabulary CHECK (`G4` → red), `record_surface_withheld` itself
(`G22` → 4 gates red), the intent-gate function (`G10`, `H10` → red), the sink arming (`E1`, `E2`,
`E3`, `E6`, `H9` → all red), and the resolver's core predicates (`D1`, `D2`, `D3`, `H12`, `G17`,
`I7` → all red). The `EXISTS → NOT EXISTS` closure is real and I confirmed it by executing the
inversion R10 named.

---

## 5. MANDATE 3 — the search for asserted values. **The eighth is `outcome_source = 'path'`.**

**How I searched.** Regex over every `.py` in `app/` for `INSERT INTO chat_messages` and
`UPDATE chat_messages`, comment-stripped, then a second pass for every `OUTCOME_*` constant in an
argument position outside `instrument.py`, then a third pass — new this round — for every **string
literal bound into a CP-0 column** (`outcome`, `outcome_source`, `finish_reason`, `runtime_variant`)
rather than only for the `OUTCOME_*` names, because the seventh was found by the constant and the
eighth is not a constant at all. Ten statements, four literal bindings not previously enumerated.

| site | value | conditions reaching it | ruling |
|---|---|---|---|
| `internal.py:937` | `OUTCOME_COMPLETED` | 1 | fine, reasoned at `:940-944` |
| `internal.py:944` | `'stop'` / `'static_fallback'` | 2, **discriminated** | fine — this is the model for how it should be done |
| `instrument.py:525` | `OUTCOME_CRASHED` | 1, evidence-backed | fine, vacuous (F-31) |
| `instrument.py:591` | `OUTCOME_ABANDONED_BY_USER` | ≥3 | R10's seventh, carried |
| **`instrument.py:585`** | **`finish_reason = 'abandoned_expired'`** | **the same ≥3** | same statement as above; its damage is §2, not P4 |
| `stream:6397` / `:6426` / `:7530` | `OUTCOME_ABANDONED_BY_USER` | 3 / 3 / 2 | carried |
| `stream:6908` | `OUTCOME_CRASHED` | 1, pessimistic by design | correct |
| `stream:7064` | `OUTCOME_AWAITING_INPUT` | 1 | fine |
| `stream:7571` | `OUTCOME_FAILED` | 1 | fine |
| **`stream:6294`, `:6307`, `:7305`, `:7324`** | **`outcome_source = 'path'`** | **6, one of which is NOT a terminal path** | 🔴 **THE EIGHTH** |

**Why it is the eighth and not merely a new column.** P4's wording is *"no CP-0 column bound to a
constant at any INSERT reachable from >1 terminal condition."* `'path'` is bound as a **bare SQL
literal** — not a parameter, not derived from anything the path knows — at four positions in two
statements, reached from: clean finish, mid-stream error, cancel/disconnect, frontend-tool suspend,
abandoned-suspend materialisation, **and the mid-turn checkpoint at `stream:6893`**.

That last one is the defect. The checkpoint is explicitly *not* a terminal path — its own call site
says *"NB: do NOT set `_persisted` — the turn isn't finished"* (`:6890`) — and it writes
`outcome='crashed'` pessimistically precisely because nothing else may run. It also now writes
`outcome_source='path'`, asserting **"a terminal path recorded this row"** about a row no terminal
path has reached. If the process then dies, the row is final: `reconcile_crashed_turns` skips it
(`outcome IS NOT NULL`), so it permanently claims an authorship it does not have.

The column's own gate docstring states the guarantee as *"a swept row must never be mistakable for
one a terminal path recorded."* The inverse — a row **no** terminal path recorded, marked as one — is
now written by design at every tool boundary of every long turn, and the closing half of the
justification (*"the distinction only bites if BOTH sides declare themselves"*) is satisfied by two
of the four writers.

---

## 6. Findings

### F-45 · 🔴 The `finish_reason` fix and the class-4 fix defeat each other, and the acceptance number moves the wrong way
§2. `instrument.py:585` vs `baseline-metrics.sql:267-268`. The metric branch requires
`finish_reason='awaiting_input'`; the sweep now writes `abandoned_expired`. Every future swept row is
classified **`unrecorded`** — the metric CP-0 exists to drive to zero, carrying the `<5%` acceptance
target. The frozen baseline's `0.0%` holds only because its 33 `abandoned_by_user` rows were swept by
the *previous* build. Three readers, three verdicts on one row: `abandoned_by_user` (column),
`unrecorded` (class 4), `interrupted` (`outcome_for_finish_reason`, `case _`). No gate covers class 4
at all (`G15`, `G16` both green).

### F-46 · The fingerprint's stated justification is now false, and a gate enforces it
§2. `baseline-metrics.sql:35-39` says *"no class below reads `outcome`"*; class 4 reads it as of line
267. `test_the_fingerprint_does_not_hash_a_column_no_class_reads` (`:947`) asserts the exclusion.
Live impact is narrow today because the sweep also writes the hashed `finish_reason`; the invariant
is one edit from being violated for real, and the gate would stay green.

### F-47 · The "frozen" baseline was re-measured on a different corpus — fourth consecutive round
`baseline-metrics.frozen.txt`: `messages 5862 → 5929`, `newest 04:58 → 11:57`,
`corpus_md5 9cdacf69… → da6fdb5e…`, and **every class-1–5 number changed**. Item 0.5's letter (files
tracked in `contracts/`) holds; its purpose — a fixed comparison point — does not. A baseline
re-measured each time a class is edited cannot be the thing a later arm is compared against.

### F-48 · 🔴 The concatenation stores duplicate passes and destroys the delta-encoding
§3. `stream_service.py:6320-6327` and `:7326-7333`. Measured against the real recorder: a 3-pass turn
with 2 checkpoints stores 7 entries with pass numbers `[1,2,1,2,1,2,3]`; 10 passes/9 checkpoints
stores 56. After a resume, `pass 1` denotes two different sets in one array. `withheld_tools` is
multiplied identically, at ~215 `domain_not_selected` entries per copy. No gate asserts uniqueness,
length or monotonicity, and the gate that exists is defeated by its own comment (`I5`).

### F-49 · The eighth-frame fix is a no-op, and its diagnosis is false about its own history
`tool_surface.py:380-385`. The comment and the gate docstring both state the `domain_not_selected`
block *"sat under `if binding_categories:`"*. It did not — at `874b3524e` and at `0362275bc`, the
commit that introduced it, `_selected = hot_tool_names(...)` is at **4-space (function-level)
indentation**. Verified by reading both blobs. What the commit actually changed is the *position of
the `hot_seed` budget registration* relative to that block, which alters record ordering and nothing
else. The stated cause (*"a control turn disproved the intent-gate diagnosis"*) therefore explains a
residual that this change cannot have moved — and the intent-gate diagnosis it says was disproved is
the one I independently confirmed **was** real and **is** now fixed (§1, credit 1).

### F-50 · `outcome_source = 'path'` is asserted by a non-terminal checkpoint, and covers 2 of 4 writers
§5. `stream:6294`/`:6307` reached from `stream:6893`, a mid-turn checkpoint. `voice:601`,
`internal:930` and the orphan stamp at `stream:6233` write an outcome and leave `outcome_source`
NULL. `I1`/`I4` show either can claim any authorship with the suite green.

### F-37 · **WITHDRAWN** — the intent gate now reaches the sink
§1. R10's falsifier was executed by the builder and returned the builder's answer, verified by five
mutations including the verbatim reintroduction.

### F-39 · **CLOSED**, as a side effect of F-38's fix
`stream:6416`'s guard no longer matches a swept row.

### Carried, unchanged
F-31 (the reconciler's surviving branch is vacuous — one `'streaming'` writer, and it stamps
`crashed`); F-30 (`stream:7530`); F-26 (assembly stages register pass-1-only); F-25; F-24/F-28
(**both revertible with one edit, suite green** — third round); F-20 (voice's `advertised_tools`
literal `None`, sixth round quoted); F-11; F-41 (`sweep_expired_runs` still zero callers, `migrate.py:388`
still claims a reclaimer, `message_id` still unindexed); F-40 (voice suspends structurally
unreachable by the sweep); F-44 (reconciler ordering guarantee lost); voice's INSERT still carries no
`withheld_tools`; `budget_rail_tools`' drops still go to `logger.warning` (`tool_surface.py:551`);
`latency_ms` still ungated; and **every CP-0 recording is still write-only** — `grep` for `SELECT`
lines naming `advertised_tools`, `withheld_tools`, `outcome`, `outcome_source` or `runtime_variant`
across `app/` returns nothing.

---

## 7. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | writes? | outcome | R11 |
|---|---|---|---|---|---|
| 1 | clean finish, `stop` | `stream:7300` | yes | `completed` | pass |
| 1b–1d | `length` / `tool_calls` / `content_filter` / unknown | `:7321` ← `:6938` | yes | derived | pass — **ungated (H6, H7 green)** |
| 2 | frontend-tool suspend | `:7053-7064` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7515-7530` | yes | ⚠️ `abandoned_by_user` on a dead transport | **FAIL — F-30 carried** |
| 4 | mid-stream exception | `:7563-7571` | yes | `failed` | pass |
| 5/6 | abandoned suspend (± provisional) | `:6397`/`:6426` | yes | `abandoned_by_user` + `finish_reason='interrupted'` | pass; class 4 counts it `interrupted` |
| 7 | empty terminal turn | `:6217-6252` | user row stamped | derived | pass — but `outcome_source` NULL (F-50) |
| 8 | mid-turn checkpoint (crash surrogate) | `:6893-6908` | yes | `crashed`, pessimistic | pass — **and now falsely marked `outcome_source='path'` (F-50)** |
| 9a | process death AFTER a checkpoint | reconciler assistant branch | n/a | — | **VACUOUS — F-31 carried** |
| 9b | process death BEFORE any checkpoint | — | **no** | ❌ none | **FAIL — carried** |
| 10 | tool-loop pass exhaustion | `:4759` → `"stop"` | yes | ⚠️ `completed` | FAIL — unchanged |
| 11 | expired / mismatched resume | → #6 | yes | ✅ | pass |
| 12/12b | voice, clean finish / derived | `voice:601-643` | yes | derived | pass — **ungated (G1, G2 green)**; `outcome_source` NULL |
| 13a | **voice turn, exception** | `voice:792-796` | **no** | ❌ none | **FAIL — unchanged, re-read at this SHA** |
| 13b | voice suspend-abort | `voice:496` → `:641` | yes | ⚠️ `awaiting_input` forever | **FAIL — F-40 carried** |
| 14/14b | proactive check-in | `internal:927-944` | yes | `completed`, discriminated | pass; `outcome_source` NULL |
| **15** | **suspend never resumed, then expired** | `instrument.py:576-592` | **yes** | ⚠️ `abandoned_by_user` + **`finish_reason='abandoned_expired'`** | **FAIL — was PARTIAL. The row is now internally consistent and unreadable to all three readers. F-45** |
| 16/17 | spend-gate refusal · turn-level timeout | searched — neither exists in this service | n/a | n/a | — |

**Six paths fail (#3, #9b, #10, #13a, #13b, #15); one vacuity (#9a); #15 regressed from PARTIAL.**

**Handoff to V-LIVE, executable:**

```sql
-- F-45: the row the new sweep writes, and what class 4 does with it.
SELECT finish_reason, outcome, outcome_source, count(*) FROM chat_messages
 WHERE outcome = 'abandoned_by_user' GROUP BY 1,2,3;   -- predict a NEW 'abandoned_expired' bucket
-- F-45: re-run class 4 after a boot that sweeps anything. pct_unrecorded must stay 0.0.
-- F-48: does one message_id hold the same pass twice?
SELECT message_id, e->>'pass' AS p, count(*) FROM chat_messages m,
       LATERAL jsonb_array_elements(m.advertised_tools) e
 WHERE m.advertised_tools IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1;   -- predict MANY
-- F-48: array length vs distinct pass count.
SELECT max(jsonb_array_length(advertised_tools)) AS entries,
       max((SELECT count(DISTINCT e->>'pass') FROM jsonb_array_elements(advertised_tools) e))
  FROM chat_messages WHERE advertised_tools IS NOT NULL;   -- predict entries >> distinct
-- F-50: which writers declare themselves?
SELECT outcome_source, count(*) FROM chat_messages WHERE outcome IS NOT NULL GROUP BY 1;
-- F-37 withdrawn — confirm it:
SELECT count(*) FROM chat_messages WHERE withheld_tools @> '[{"stage":"intent_gate"}]'::jsonb;  -- predict > 0
```

---

## 8. Vacuity (NV) — can each new check fire?

| check | realistic firing input? |
|---|---|
| **`intent_gate` registration** | **YES now** — sink armed before catalog assembly at both paths. F-37 withdrawn |
| **`domain_not_selected` unconditional** | Yes, and it always could — the branch it was "hoisted from" never contained it (F-49) |
| **`test_the_block_is_not_nested_under_a_conditional`** | 🔴 **NO — cannot fire on nesting.** `ast.walk` on top-level statements matches at any depth. Verified in isolation: the exact defect it names leaves it green |
| **concatenation, `advertised_tools`** | Yes — fires on every multi-write turn, which is the defect (F-48) |
| **`outcome_source = 'path'`** | Yes, on 2 of 4 writers; and fires on a non-terminal checkpoint (F-50) |
| **`finish_reason = 'abandoned_expired'`** | Yes — and every row it produces reads `unrecorded` in class 4 (F-45) |
| **class 4's `outcome` override** | 🔴 **NO for any row this build sweeps** — the state it matches is the one the sweep now eliminates (F-45) |
| **class 4's `abandoned_by_user` column** | Only for rows swept by the *previous* build. Reads 0 going forward |
| `resolve_expired_suspends`, stream suspends | Yes; voice suspends **NO** (F-40) |
| reconciler, assistant branch | **NO — F-31 carried** |
| `runtime_variant='agentruntime'` · `tool_call_source()` | **No** — no producer, zero callers (F-11) |
| `latency_unmeasured` | Yes, at most mint sites — still **no gate** |

**And the standing vacuity, eleventh round: every CP-0 recording is write-only.** Nothing in `app/`
`SELECT`s any of the five columns. This is why F-45 and F-48 could ship together: a row that reads
`unrecorded` in one query and holds a 56-entry array with three copies of pass 1 is contradicted by
no consumer, because there is no consumer.

---

## 9. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | The persisted array is no longer one-entry-per-pass on **any** multi-write turn (F-48) — the bypass is now in the write path itself, not around it. `voice:639` still binds `None`. Assembly stages register pass-1-only (F-26) |
| **0.2** | The intent gate is **no longer** a bypass (F-37 withdrawn). Remaining: voice's INSERT has no `withheld_tools` column (`voice:601-608`); `budget_rail_tools` logs instead of registering (`tool_surface.py:551`); every entry is stored once per upsert (F-48) |
| **0.3** | `source` — **no bypass found**, 8/8 chokepoint mutations red. `latency_ms`: minority of mint sites, **no gate** (`H5` green) |
| **0.4** | Six paths. Write **no row**: `voice:792` (#13a), process death before any checkpoint (#9b). Write a **fabricated cause**: `stream:7530` (F-30), `:4765`, `instrument:591`. Write a **word no reader knows**: `instrument:585` (F-45). Write a **stale** value forever: every voice suspend (F-40). Claim an authorship they do not have: `stream:6893` via `:6294`/`:6307` (F-50). Full enumeration §7 |
| **0.5** | No bypass at the SHA — `git ls-tree e6e38a848` confirms all three baseline files + `run_arms.py`. The tree was clean for the entire audit. But the artifact was **re-measured**, not merely re-published (F-47), and it now contains a self-contradiction (F-46) |
| **0.6** | No bypass. `binding_format.py` + both result files tracked at the SHA |
| **0.7** | No bypass of the literal claim; all chokepoints route through `ensure_tool_call_instrumented` (`G19` → 7 gates red). Bounded by F-11 |

---

## 10. What changed in the failure, and my falsifier

**Two of the three hard things I was asked to rule on came back the way a fix should.** F-37 was
withdrawn by executing the procedure I stated for it; `EXISTS → NOT EXISTS` — R10's sharpest resolver
blind spot — is closed and I confirmed the inversion goes red. The behavioural half of the new
registration gate is the best-constructed gate added to this file in eleven rounds: it uses
production's own ContextVar rather than staging a kwarg, and every one of the four ways I broke the
registration reddened it.

**And the failure moved from *wiring* to *arithmetic*, which is a harder place for it to hide.** For
ten rounds the pattern was: a mechanism built, and the call site not wired. This round the mechanisms
are wired and two of them are **wrong about each other**. `finish_reason='abandoned_expired'` and the
class-4 `outcome` override were shipped in one commit to close one finding, and the first makes the
second unreachable — so a turn the instrument records three facts about is published as one it failed
to classify, in the bucket carrying the acceptance target, in a file that says `0.0%`. Neither diff
shows the other. Nothing in 62 tests reads that file's class 4.

**The through-line is unchanged and it is not scope this time — it is that a gate written in the
defeated form was written again.** Round 10 credited `test_it_does_not_delete_the_evidence` for being
fixed by *parsing the code* instead of narrowing a prose window. Round 11 adds three gates that count
substrings over the raw file, and I defeated all three with the commit's **own comment block**
(`H2`, `I3`, `I5`) — including a mutation that restores last-write-wins, the founding defect of this
entire effort, with the suite green. And the one gate written with `ast` this round asserts a
property `ast.walk` cannot express, so the exact defect its docstring names leaves it passing.

**My falsifier, stated so a later round can execute it as R8's, R9's and R10's were:**

1. **F-45.** Boot this build, let one suspend expire, then run class 4 of `baseline-metrics.sql`.
   **If `pct_unrecorded` is still 0.0% and the row appears under `abandoned_by_user`, F-45 is
   withdrawn in full and I have misread the `CASE`.** If the row lands in `unrecorded` — which is
   what the transcribed `CASE` returns for `(finish_reason='abandoned_expired', outcome IS NOT NULL)`
   — then the two halves of this commit cancel, and the direction is toward the target, not away from
   it.
2. **F-48.** Run
   `SELECT message_id, e->>'pass', count(*) FROM chat_messages m, LATERAL jsonb_array_elements(m.advertised_tools) e GROUP BY 1,2 HAVING count(*)>1`
   against a database that has served one tool-loop turn longer than 1.5 s per boundary on this
   build. **If it returns zero rows, F-48 is withdrawn and I have misread the upsert's reach** — the
   claim rests on `_persist_terminal_assistant` being called more than once per `message_id` with a
   non-NULL recorder, which I verified at five call sites but did not observe.
3. **F-49.** Re-read `git show 0362275bc:services/chat-service/app/services/tool_surface.py`. **If
   `_selected = hot_tool_names(...)` is at 8-space indentation there, F-49 is withdrawn** and the
   hoisting happened as described. I read it at 4 spaces, at that SHA and at `874b3524e`.
4. **The structural gate.** Indent the `domain_not_selected` block under `if binding_categories:` and
   run `pytest -k not_nested` **alone**. **If it fails, my vacuity ruling is wrong.** I ran exactly
   this and got `1 passed`.

**And one thing about my own work.** I set out to rule on a concatenation and spent the first third
of the audit confirming that two of the six changes are genuinely good. The finding I lead with is
not in the mandate: nobody asked me to check whether the two `abandoned` fixes agree, because they
were written as answers to two different verifiers. They are the same row.
