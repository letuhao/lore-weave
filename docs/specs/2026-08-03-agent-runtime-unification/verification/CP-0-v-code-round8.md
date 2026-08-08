# CP-0 · V-CODE — verdict, ROUND 8

Artifact frozen at `4a2fc1dc44eb358ea620902e72974f445ddbd600`. **`git status --porcelain` is empty** —
the committed state and the graded state are the same state. The brief is unmodified since
`aa9ef87c4`.

Source-only review. Nothing in the product was run. No tracked file was modified. No commit message
or builder rationale prose was read. Every finding below was re-derived from source at this SHA.

**Method note.** Two harnesses, both over **in-memory** copies. (1) Every *source-scanning* gate is
transcribed verbatim and re-run against mutated strings; `mutate()` asserts the needle exists **and**
that the string changed, so a no-op cannot masquerade as a blind spot. (2) Every *behavioural* gate is
re-run against a **mutated module** — `instrument.py` / `tool_surface.py` compiled from a mutated
source into a fresh module object — so a behavioural gate can be scored the same way a syntactic one
can. Both harnesses reproduce a fully GREEN baseline on the unmutated tree first. For rulings about
values I called the real functions; "measured" below is a mechanical result.

**64 mutations. 35 caught, 29 blind spots. The gate that was RED on the unmutated tree in R7 is now
GREEN.**

---

## 1. Verdict

**Overall: `FAIL`.** Two of the three things handed to me this round are met; the third is not, and
the round created one new instance of the project's signature defect while closing two.

| item | claim | R5 | R6 | R7 | **R8** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — unchanged; voice still discards the `advertised` chunks it receives and binds NULL |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL — and the largest single improvement of the run.** The unregistered candidate-selection stage is closed and measured. Residuals: two counting conventions in one column, pass-1-only, voice has no column |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL** — unchanged residuals; `latency_ms` measured at 4 of ~30 mint sites and has no gate at all |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL — improved.** F-19 closed at the text path; the empty-turn hole closed. The same defect is now live in the voice pipeline, uncopied |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS** |
| 0.6 | binding-format measurement scripted **and its output committed** | PASS | PASS | PASS | **PASS** |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS** |

| property | ruling |
|---|---|
| **P4** — no CP-0 column bound to a constant at any INSERT reachable from >1 terminal condition | **NOT MET.** Met at the clean finish — the site it was red at, verified mechanically. Not met at `routers/internal.py:934` and at `voice_stream_service.py:615/633`. **And my R7 scoring of both of those was too lenient; for one of them I held the evidence and filed it as a footnote instead of a score.** §3 |
| **P2** — a call's `source` is assigned structurally, never inferred | **Load-bearing half HOLDS — verified mechanically, the builder's claim is correct. The `source_inferred` gating IS sufficient to keep the residual countable; it is not a way to stop counting.** It is *not* sufficient as a gate on P2: nothing bounds the residual or stops it growing. §4 |

**What landed, credited before the findings.**

1. **F-19 is closed at the site it was found.** `stream_service.py:7305` and `:7313` now bind
   `outcome` and `finish_reason` from the same expression (`_loop_finish_reason or "stop"`), and the
   `DO UPDATE SET` at `:7274` takes `EXCLUDED.finish_reason` instead of re-pinning `'stop'`. I
   recounted the statement: 22 columns, 22 value slots, 20 arguments, `$20` → `finish_reason`,
   `$16` → `outcome`. **The extended Gate C I ran in R7 — which went RED on the unmutated tree — is
   GREEN on the unmutated tree now.** That was the sharpest finding of R7 and it is genuinely gone.
2. **The mapping fix is right, and the fail-safe survived it.** Measured on the real function:
   `length`/`tool_calls`/`max_tokens` → `completed`, `content_filter` → `failed`, `error` → `failed`,
   `streaming` → `crashed`, `interrupted` → `interrupted`, and **every unrecognised word and `None`
   → `interrupted`, never `completed`**. Mutating the `case _` default to `completed` goes red at two
   tests. The fail-safe direction holds.
3. **P1's unregistered narrowing is closed, and I measured it on the branch production actually
   uses.** With a 320-tool, 16-domain catalog and the ContextVar armed exactly as
   `stream_service.py:5991` arms it and **no `withheld_sink` argument** — the production shape —
   `discovery_seed_for_surface` registers **240 `domain_not_selected` + 63 `hot_seed` = 303 of 320**.
   Reconciled against pass 1: **303 tools absent, 303 registered, 0 unregistered.** The "237 of 315
   in neither bucket" class is gone at pass 1. This is the largest thing this checkpoint has fixed.
4. **The empty-turn hole is closed as a recording hole.** `stream_service.py:6205-6237` stamps the
   session's newest un-outcomed user row and reports via `RETURNING` whether it matched. The
   re-anchoring from `parent_message_id` to `session_id` is the correct fix for the measured
   0-of-3,154 defect, and mutating it back goes red.

**And the pattern held for an eighth round, in the place it is hardest to see.** R6's defect was in
column *values*, R7's in the *justifications*, then in a *derived expression*. R8's is in the
**gate**: the P1 test hands itself the precondition production does not supply, which is verbatim the
failure its own sibling gate documents nine lines of docstring warning about — written into the file
that contains the warning, in the same pass. The code is right and the gate is blind; that is the
good version of this failure, and it is the fifth recurrence of the mechanism.

---

## 2. The falsifier

Stated before the findings. What I looked for that would have made each ruling go the other way, and
what each search returned.

1. **Would P4 at the clean finish survive a mechanical check?** *Yes.* Search: recounted the INSERT's
   column/value/argument mapping by hand; re-ran my R7 extended Gate C (which scans
   `ON CONFLICT … DO UPDATE SET`, the blind spot that hid F-19) over the unmutated tree. It went
   GREEN, and goes RED again the moment either upsert re-pins `finish_reason`. §3.1.
2. **Is `internal.py:937` genuinely single-condition?** *No — an error path reaches it.*
   `_generate_proactive_content` swallows **every** exception (`internal.py:847-849`) and returns
   `None`; `_clean_proactive_text` also returns `None` for scaffolding-only or <12-char output; the
   caller degrades to `_PROACTIVE_STATIC` at `:913`. A provider outage and a grounded generation
   commit the same row. §3.2.
3. **Is there a P4 site nobody counted?** *Yes — `voice_stream_service.py:633`.* Search: grepped
   `finish_reason` in the voice module — **two hits, one a column name and one a comment.** Voice
   never reads the signal, which `_stream_with_tools` yields to it on the terminal chunk
   (`stream_service.py:2778`). §3.3.
4. **Can anything acquire `source='tool'` by inference?** *No.* Search: `grep '"source":' / ["source"] =`
   over `app/services/*.py` returns exactly two lines, both in `instrument.py` (`:133`, `:224`), and
   `:224` can only produce `meta` or `breaker`. Mutating it to default to `tool` goes red at three
   tests. §4.
5. **Is `source_inferred` escapable — can an inferred row look declared?** *No, in either
   direction.* Deleting the mark goes red at three tests; adding it to a *declared* row goes red at
   one. And it is persisted: the chokepoint mutates in place and the mutated dict is what all three
   INSERT paths serialize (`:7098-7104`, `:6246-6249`, `voice:505`). §4.
6. **Does P1 register on the branch production uses, or only on the one the test uses?** *It
   registers on both — but only the test's branch is guarded.* Measured, §5.1. This is the round's
   headline gate finding and the one that would most easily have been missed by reading the test.
7. **Does P1's per-pass claim hold past pass 1?** *No.* Measured: pass 2 of the same turn has **303
   absent, 0 registered**. §5.2.
8. **Does any other provider word reach a wrong outcome?** *Bounded — and the enum the fix's comment
   cites is not closed at the boundary it cites.* §3.4.
9. **DDL appended to an applied ledger step.** *Not applicable, re-checked a fourth time.*
   `migrate.py:791` runs the whole `DDL` string on every boot; all four CP-0 statements are
   `ADD COLUMN IF NOT EXISTS`, and Gate F goes red when any is deleted (measured).
10. **`advertised_tools` overwritten rather than appended.** *Not found, an eighth time.* Mutating
    `record_pass` to overwrite goes red at two tests; both upserts `COALESCE`.

Two things I **cannot determine from source**, unchanged across eight rounds:

- **Whether the recorded values are right.** `grep` for the four CP-0 columns across `services/`,
  `frontend/src` and `contracts/` returns hits **only** in the five chat-service files that write
  them and their tests, and `grep 'SELECT.*outcome|SELECT.*advertised_tools|…'` over `app/` returns
  **nothing at all**. `source_inferred` has no reader either. Every recording remains write-only.
  This is the brief's hunting ground #3 and it is why F-19 could ship: a value nothing reads is
  contradicted by nothing.
- **The live frequency of each mis-recorded class.** Whether voice truncations are 0.1% or 10% of
  voice turns is a database question and I did not run one. §7 hands V-LIVE the exact query.

---

## 3. P4 — ruling on my own gate

**The gate, as I proposed it in R7:**

> *An INSERT reachable from **more than one terminal condition** must not assert `outcome` **or**
> `finish_reason`; both must be derived from what the turn did, and from the **same** signal.*

### 3.1 The clean finish — **MET.** The site it was red at is closed.

`stream_service.py:7254-7314`. `finish_reason` is `$20`, bound at `:7313` to
`_loop_finish_reason or "stop"`; `outcome` is `$16`, bound at `:7305` to
`instrument.outcome_for_finish_reason(_loop_finish_reason or "stop")`. One signal, two columns, and
the `DO UPDATE SET` at `:7274` propagates `EXCLUDED.finish_reason` rather than re-pinning.

`_loop_finish_reason` is captured at `:6896` from any chunk carrying a truthy `finish_reason`. I
traced the consumer's dispatch order to confirm nothing eats it first: `suspend` (`:6822`),
`tool_call` (`:6827`→`continue :6869`) and `advertised` (`:6873`→`continue :6890`) all `continue`
before `:6895`, and none of the three chunk kinds carries a `finish_reason` — the only two truthy
producers are `:2778` (the normal terminal yield) and `:4743` (the budget-exhausted exit), both
content chunks. **The capture is complete for the text path.**

Verified mechanically: my R7 extended Gate C — the check that scans `ON CONFLICT … DO UPDATE SET`,
which is where F-19 hid — is **GREEN on the unmutated tree** for the first time, and goes RED again
under either re-pin. That is the falsifier for this row and it returned the builder's answer.

### 3.2 `routers/internal.py:934` — **NOT MET**, and the builder's factual claim is false

**An error path reaches this INSERT.** `internal.py:913`:

```python
content = await _generate_proactive_content(...) or _PROACTIVE_STATIC
```

and `_generate_proactive_content` returns `None` from a bare `except Exception` (`:847-849`), and
`_clean_proactive_text` returns `None` for scaffolding-only or sub-12-character output (`:870-875`).
So **three distinct conditions** — a grounded generation, a provider outage/timeout, and a model that
emitted only junk — commit the same row, with the same two constants:

```sql
VALUES ($1, $2, 'assistant', $3, 0, 'assistant_proactive', 'stop', $4, $5)
--                                                          ^^^^^^  ^^ instrument.OUTCOME_COMPLETED
```

**Ruling, split, because the two columns are not in the same position:**

- **`outcome` — the gate is MET.** All three routes terminate the turn identically: a complete
  assistant message is committed and the session list shows it. `completed` is classified by the
  path, which is exactly the case my R7 narrowing was written to exempt. I do not score this.
- **`finish_reason` — the gate is NOT met.** `'stop'` is an SQL literal asserting a **provider's**
  terminal reason. On the fallback branch **no provider spoke at all** — the exception was thrown
  before any `DoneEvent` — and the row nonetheless states that one finished normally. That is a
  fabricated value in a column whose whole meaning is "what the model said", and it is now the only
  remaining constant-bound `finish_reason` at an assistant INSERT in the package. It is the same
  class as the F-19 defect the round just fixed, one file over.

**And I have to own the R7 scoring.** I wrote *"the proactive check-in passes (one condition — though
see below)"* and then, in a bounded note, recorded that `:928-930` claims the content *"is generated,
complete and delivered"* while `:913` degrades to a static line. **I held the evidence and filed it as
a footnote instead of applying my own gate to it.** The builder's claim this round is a restatement
of my own too-lenient score, so this correction is mine to make, not theirs to answer for.

### 3.3 `voice_stream_service.py:615` / `:633` — **NOT MET**, and this site was not on anyone's list

Both fields derive from `_voice_suspended` — which is what I scored as passing in R7. That was the
wrong question. **`_voice_suspended` is a two-valued flag over a terminal space with at least four
values**, so deriving from it is not the same as deriving from what the turn did:

| how the voice chunk loop ends | `_voice_suspended` | recorded |
|---|---|---|
| suspend break (`:495-496`) | True | `awaiting_input` / `awaiting_input` |
| generator exhausted, provider said `stop` | False | `completed` / `'stop'` ✔ |
| generator exhausted, provider said **`length`** (truncated) | False | `completed` / **`'stop'`** ✘ |
| generator exhausted, provider said **`content_filter`** (refused) | False | **`completed`** / **`'stop'`** ✘ |

The signal that would separate them **arrives and is discarded.** `_stream_with_tools` yields
`finish_reason` on its terminal chunk (`stream_service.py:2778`); voice's loop reads `content`,
`reasoning_content`, `usage`, `suspend` and `tool_call` and nothing else. `grep finish_reason` over
`voice_stream_service.py` returns **two hits: a column name (`:598`) and a comment (`:632`)**. This is
byte-for-byte the same shape as the `advertised` chunk voice discards for 0.1 — a signal reaching a
consumer that does not look at it.

So the F-19 fix — *"`finish_reason` and `outcome` now derive from THE SAME signal"* — was applied to
one of the two pipelines that write an assistant row, and the pipeline it was not applied to records
a content-filter refusal as `outcome='completed', finish_reason='stop'`. **F-24.**

### 3.4 The F-19 mapping — correct, with one bounded overstatement

Measured against the real function; the fail-safe holds (`case _` and `None` → `interrupted`, never
`completed`; flipping it goes red). The bounded part is the reachable vocabulary. The fix's comment
cites the openapi enum `stop|length|content_filter|tool_calls|error`
(`anthropic_streamer.go:266`) — but **that same function passes unknown values through by default**:

```go
func mapAnthropicStopReason(r string) string {
    switch r { case "end_turn": ...; case "max_tokens": ...; default: return r }
}
```

and the OpenAI-compat path (`streamer.go:373-374`) forwards `choice.finish_reason` **verbatim,
unnormalised**. So the input set is open, not closed. Two words documented by providers *today*
would land in the deprecated bucket: OpenAI's legacy **`function_call`** (semantically `tool_calls`,
so `completed` under this scheme) and Anthropic's **`refusal`** (semantically `content_filter`, so
`failed`). Both are *correct fail-safe behaviour* — an unclassified word becoming a countable finding
is the design — so this is **not a FAIL**. What is inaccurate is the comment's premise that the enum
is closed. `case "max_tokens"` is also **vacuous**: the gateway maps it to `length` before it leaves
Go, and nothing else emits it.

---

## 4. P2 — is the `source_inferred` gating countability, or a way to stop counting?

**Ruling: it is countability. It is not a way to stop counting.** Three independent reasons, each
verified mechanically rather than read.

1. **The load-bearing half holds, and the builder's statement of it is exactly right.**
   `chunk["source"]` is assigned in **exactly two places in the entire package** — `instrument.py:133`
   (`stamp_tool_call`, explicit) and `:224` (the chokepoint) — and `:224` can only produce
   `SOURCE_META` or `SOURCE_BREAKER`. There is no third writer, so **no mint site can set `source`
   directly and thereby look declared without passing a dispatch.** Mutating `:224` to assign
   `SOURCE_TOOL` goes RED at three tests. Five `stamp_tool_call` sites exist; four assert
   `SOURCE_TOOL` and each sits on a real execution (`:3487` subagent — dispatched tools of its own,
   documented; `:4671` in-loop MCP; `:7771` ext-task, on `mcp_execute_tool` at `:7763`; `:7917`
   approval resume), and the fifth (`:7929`) asserts `SOURCE_BREAKER` for a user denial explicitly
   rather than leaving it to inference.
2. **The mark cannot drift in either direction without a gate moving.** Deleting
   `chunk["source_inferred"] = True` → RED at three tests. Adding the mark to a **declared** row →
   RED at `test_a_declared_source_never_acquires_the_inferred_mark`. So the residual can neither be
   hidden nor inflated by relabelling.
3. **The mark reaches the database.** `ensure_tool_call_instrumented` mutates in place, and the
   mutated dict is what every INSERT path serializes — `:7098-7104` (clean finish), `:6246-6249`
   (terminal), `voice:505`. So the residual is derivable from the persisted column with one query,
   which is precisely how the RUNSTATE's `110 of 201` was obtained. That is real countability, not a
   claim of it.

**Where it is insufficient, and this is a different question from the one asked.** The gating keeps
the residual *visible*; nothing keeps it *bounded*:

- **Nothing asserts the residual's size, or that it does not grow.** There are ~30
  `yield {"tool_call": …}` mint sites and 5 declaring ones. A 31st unstamped site added tomorrow
  raises the inferred fraction and **all 42 tests stay green**. The `~29 mint sites` closure is
  scoped and deferred honestly, but no gate will notice it moving backwards in the meantime.
- **The closed set is closed by assertion, not by construction.** `RUNTIME_PRIMITIVES`
  (`instrument.py:146-150`) is a hand-maintained frozenset of 8 names. Emptying it goes red **only**
  because one test happens to pin `tool_list`. Adding a *new* runtime primitive without adding it to
  the set silently files it as `breaker`, and nothing moves. Nothing derives the set from the
  handlers that actually answer out of the catalog.
- **There is no reader.** `source_inferred` and `tool_calls[].source` have no consumer anywhere in
  the repository. "Countable" here means *a verifier can count it by hand*, not *the system counts
  it* — the standing F-8 condition, which applies to every CP-0 field equally.

So: **the gate the builder added is the right gate and it works.** P2 remains RED, openly, with a
measurable residual — which is the honest state, and a better one than a closed-looking split.

---

## 5. THE GATE AUDIT — 64 mutations, 35 caught, 29 blind spots

`tests/test_cp0_instrument.py` is 778 lines and **42 tests** across 10 classes (the brief said ~39).
Baseline: all 11 replicated source gates and all 33 replicated behavioural gates GREEN on the
unmutated tree.

### 5.0 The headline — the newest gate stages the precondition production does not supply

`test_tools_outside_the_hot_domains_register_as_withheld` (`:697-721`) calls:

```python
discovery_seed_for_surface(catalog, pins=…, editor=False, book_scoped=True, withheld_sink=sink)
```

**Neither production call site passes `withheld_sink`.** `stream_service.py:5991-6010` and
`:7994-8012` both arm the ContextVar (`instrument.surface_withheld.set([])`) and call without the
argument, so production runs the `else:` fallback at `tool_surface.py:397-400`. Measured: **deleting
that fallback branch leaves this gate GREEN.**

This is verbatim the defect documented nine lines of docstring away, in the same file, by the gate
written to close the *previous* instance of it (`test_cp0_instrument.py:107-113`):

> *"The previous version of this test called `surface_withheld.set(...)` itself — supplying the exact
> precondition production was failing to supply — so it passed while the real path recorded nothing.
> A behavioural gate that stages its own precondition is a source gate wearing a costume."*

**Fifth recurrence, in the gate written to close the fourth.** Two mitigations, both real: the
production branch *does* work (§1.3, measured on the production shape), so this is a blind gate over
correct code rather than the reverse; and the sibling D-gate's positional check (`:114-123`) does
guard that the two call sites are preceded by an arming. What is unguarded is the
`domain_not_selected` block's own fallback. **F-23.**

### 5.1 The second-newest gate — red for the byte-pattern, green for the property

`test_the_clean_finish_writes_both_fields_from_one_signal` (`:631-637`) is two needles:

```python
assert "finish_reason = EXCLUDED.finish_reason" in src
assert "$15, 'stop'," not in src
```

| reintroduction of its own stated property | should be | **is** |
|---|---|---|
| clean finish re-pins the SQL literal in the `VALUES` list (same byte pattern) | red | red ✔ |
| the `DO UPDATE SET` re-pins `finish_reason = 'stop'` | red | red ✔ (my C-ext, not this gate) |
| **the ARGUMENT at `:7313` reverts to the Python literal `"stop"`** — F-19 exactly, one line lower | red | **GREEN** |
| **`outcome` derived from a literal while `finish_reason` varies** — the contradiction from the other side | red | **GREEN** |
| **the clean finish stops updating `finish_reason` at all** (needle 1 is satisfied by the *other* upsert at `:6276`) | red | **GREEN** |

Needle 2 pins one parameter number; the binding it guards is no longer at that parameter number.
Needle 1 is paid for by a different statement in the same file — the exact arithmetic slack Gate B's
own docstring names (*"a surplus stamp somewhere else in the file can no longer pay for a missing one
here"*). **3 of 5 reintroductions of the property invisible. F-27.**

### 5.2 THIS ROUND'S NEW CODE — 14 of 25 mutations caught

| mutation | should be | **is** |
|---|---|---|
| **P1** registration block deleted outright | red | red ✔ (behavioural) |
| **P1** stage label renamed | red | red ✔ |
| **P1** reason emptied | red | red ✔ |
| **P1** `_unselected` always empty | red | red ✔ |
| **P1** tool name dropped from the record | red | red ✔ |
| **P1 ContextVar fallback deleted — the branch production uses** | red | **GREEN** — §5.0 |
| **P3** re-anchor on `parent_message_id` (the 0-of-3,154 defect) | red | red ✔ |
| **P3** drop the `outcome IS NULL` guard | red | red ✔ |
| **P3** assert `completed` instead of deriving | red | red ✔ |
| **P3** the stamp reverted to a no-op (`_stamped = None if True else …`) | red | **GREEN** |
| **P3** `ORDER BY sequence_num DESC` dropped — stamps an arbitrary user row | red | **GREEN** |
| **P3** `if _stamped is not None:` → `if True:` — success logged unconditionally | red | **GREEN** |
| **F-19** `length` → interrupted | red | red ✔ |
| **F-19** `tool_calls` → interrupted | red | red ✔ |
| **F-19** `content_filter` → completed | red | red ✔ |
| **F-19** the `case _` fail-safe flipped to `completed` | red | red ✔ |
| **F-19** `is_error` short-circuit removed | red | red ✔ |
| **F-19** `error` → completed | red | **GREEN** — no test pins the word `error` |
| **F-19** the clean finish's `_loop_finish_reason` capture deleted | red | **GREEN** |
| **F-19** clean-finish `outcome` reverts to the `OUTCOME_COMPLETED` constant | red | **GREEN** |
| **P2** `source_inferred` deleted | red | red ✔ |
| **P2** unstamped chunks default to `tool` | red | red ✔ |
| **P2** all unstamped classified `meta` | red | red ✔ |
| **P2** `RUNTIME_PRIMITIVES` emptied | red | red ✔ |
| **P2** a declared row also gets the inferred mark | red | red ✔ |
| **P2** `latency_unmeasured` reason dropped — a null latency reads as instant | red | **GREEN** |

The P3 row worth naming: `RETURNING message_id` is asserted as **text present in the window**, not as
a value acted upon. `if _stamped is not None:` → `if True:` re-creates the original defect in mirror
image — a guard reporting the *presence* of a row it failed to check, where the old one reported the
*absence* of a row it failed to look for.

### 5.3 Carried gates — unchanged from R7 except Gate C

| gate | mutation | **is** |
|---|---|---|
| A · budgeter wiring | revert a site to the plain variant | red ✔ |
| A | **a NEW narrowing calling `_ex` and discarding `dropped`** | **GREEN** |
| B · dispatch stamping | a 4th unstamped dispatch at EOF | red ✔ |
| B | **a dispatch through a differently-named receiver (`_kc.mcp_execute_tool`)** | **GREEN** |
| C · outcome/finish_reason lockstep | **the CURRENT tree, extended to `ON CONFLICT … DO UPDATE SET`** | **GREEN — was RED unmutated in R7. Closed.** |
| C | a NEW `UPDATE chat_messages SET finish_reason` in `voice_stream_service.py` | **GREEN** (one-file scope) |
| D · surface narrowing | source half: arming line demoted to a comment | **GREEN** |
| D | behavioural half: the real budgeter with a ContextVar sink | red ✔ |
| E · assistant-INSERT outcome | voice / proactive drop the `outcome` **column** | red ✔ |
| E | a brand-new assistant INSERT in another file | red ✔ |
| E | **voice binds `None` instead of a value** | **GREEN** |
| E | **a new assistant INSERT with `role` bound as a parameter** | **GREEN** |
| F · vocabulary + column existence | delete any of the four `ADD COLUMN` lines; drift the vocabulary | red ✔ |
| F | **rename `advertised_tools` → `advertised_tools_v2`** (prefix preserved) | **GREEN** — substring test |
| voice (5 value mutations: outcome constant, `finish_reason` literal, stops recording calls, binds NULL, persists RAW) | 0/5 | **all GREEN** |
| internal | **proactive outcome flipped to a WRONG constant (`crashed`)** | **GREEN** — Gate E checks the column is named, never the value |

### 5.4 Scorecard

| gate | red-able for its own defect? |
|---|---|
| A · budgeter wiring | **partly** — green over an `_ex` caller that discards `dropped` |
| B · dispatch stamping | **yes** for its three named sites; blind to a renamed receiver |
| C · outcome/finish_reason lockstep | **property TRUE on the current tree** (R7's red closed); needle still misses upserts and other files |
| D · surface narrowing | source half **no** (5 blind spots); behavioural half **yes** |
| E · assistant-INSERT outcome | **partly** — catches a missing column anywhere; blind to every value |
| F · vocabulary + column existence | **yes**, all four columns, both directions |
| **P1 · candidate selection** | **partly — 5/6, but blind on the branch production uses** |
| **P2 · structural source** | **yes — 5/6, the strongest new class in the suite** |
| **P3 · orphan stamp** | **partly — 3/6; blind to a no-op stamp and to an unchecked result** |
| **F-19 · both fields from one signal** | **no — 3 of 5 reintroductions of its own property are green** |
| — · voice, everything | **no — 0/5** |
| — · `latency_unmeasured` | **no — no gate exists** |

---

## 6. Findings

### F-23 · The P1 gate exercises the branch production does not use — fifth recurrence, in the gate written to close the fourth
§5.0. `test_cp0_instrument.py:712` vs `stream_service.py:5992` / `:7995` and
`tool_surface.py:392` vs `:397-400`. Measured: deleting the ContextVar fallback leaves the gate green.
The code is correct on the production branch (measured, §1.3); the gate cannot see it.

### F-24 · The F-19 fix was applied to one of the two pipelines; voice records a content-filter refusal as `completed` / `'stop'`
§3.3. `voice_stream_service.py:615-616`, `:633`. Voice receives `finish_reason` on the terminal chunk
(`stream_service.py:2778`) and never reads it — `grep` returns two hits in the whole file, a column
name and a comment. Same discard shape as the `advertised` chunk that keeps 0.1 failing.

### F-25 · `withheld_tools` now carries two counting conventions and ~44 KB per row
Measured on a production-shaped 320-tool call: 303 withheld rows, **44,627 bytes** of jsonb for one
turn. And the conventions differ **by stage**: `token_budget` (in-loop, `stream_service.py:2206-2208`)
fans out one row **per pass** — re-measured 1→1, 2→2, 3→3, 6→6, 10→10 — while `domain_not_selected`
and the surface-assembly `hot_seed` drops are drained once (`:6881-6885`, `while _surface_sink: pop`)
and appear at **pass 1 only**. A consumer counting rows in this column is counting narrowings for
some stages and pass-instances for others, in the same array. Neither is documented at the column.

### F-26 · P1's per-pass claim holds at pass 1 and nowhere else
Measured on the same call: **pass 1 — 303 absent, 303 registered, 0 unregistered. Pass 2 — 303
absent, 0 registered.** Surface assembly runs once per turn and the sink is drained once, so every
pass after the first re-advertises the same narrowed surface with no record for that pass. Whether
this falsifies P1 depends on which reading governs: `AdvertisedToolsRecorder`'s own docstring says
*"withholdings accumulate across the turn rather than per pass"*, which makes pass-1-only correct;
the RUNSTATE states P1 as *"every tool absent from **a pass's** advertised set registers"*, which it
does not meet. **The two documents disagree, and the disagreement is the finding** — a property claim
falsifiable at n=1 has to say which n.

### F-27 · The F-19 gate is red for the byte pattern of the R7 defect and green for three reintroductions of its stated property
§5.1. `test_cp0_instrument.py:631-637`.

### F-28 · `internal.py:934` asserts a provider `finish_reason` on a path where no provider spoke
§3.2. The literal `'stop'` is committed when `_generate_proactive_content` returned `None` from a
swallowed exception (`:847-849`). The comment at `:928-930` still says the content *"is generated,
complete and delivered by the time it lands here"*; on that branch none of the three words is true.
Carried from R7's bounded note and now **scored**, because it is my gate and it applies.

### F-20 (carried, unchanged) · The false voice comment still sits directly above its own refutation
`voice_stream_service.py:604-608` still reads verbatim *"It reaches this INSERT only on a clean
finish, so `completed` is the honest value."* Lines `:609-614` immediately beneath say the opposite.
Both are in the argument list of the same INSERT. Third round this sentence has been quoted as the
defect and left in place.

### F-21 (carried, unchanged) · The recorder's docstring and the gate's docstring still assert the invariant F-16 corrected
`instrument.py:316-317` still says withholdings are *"Deduplicated on `(tool, stage)` so a tool
dropped by the same stage on five passes is one withholding rather than five"*. The key is
`(tool, stage, len(self._passes))` (`:341`) and the measurement is 5 passes → 5 rows.
`test_cp0_instrument.py:322-324` repeats the same false claim; the gate is green only because it
records five withholdings against **zero** passes, which production never does.

### F-22 (carried, unchanged) · The voice suspend's own pending tool call is not recorded
`voice_stream_service.py:484-496` reads only `input_tokens`/`output_tokens` from the suspend payload;
the text path records exactly this call at `stream_service.py:6943-6962`. A voice turn records every
call except the one that ended it.

### F-8⁵ (carried) · Every recording remains write-only
Re-verified: `grep 'SELECT.*(outcome|advertised_tools|withheld_tools|runtime_variant)'` over `app/`
returns **nothing**, and the repo-wide grep outside chat-service returns nothing. `source_inferred`
has no reader either. This is the standing reason a wrong derived value ships as easily as a wrong
constant did.

### F-11⁶ · `runtime_variant`, `declaration` and `unclassified` remain constants or dead
`RUNTIME_AGENTRUNTIME` has no producer; `declaration` is `chunk.get("tool")` at every site;
`tool_call_source()` still has zero callers; `dedupe_recorded_calls` still unwired by design.

### F-1⁹ · 0.2's residuals
`budget_rail_tools`' drops still go to `logger.warning` (`tool_surface.py:550-554`); the tool-free
pseudo-entry `{"tool": "*"}` (`stream_service.py:2327`); **voice's INSERT still has no
`withheld_tools` column at all** (`voice:596-598`), and voice runs `permission_mode="ask"`.

### F-9 · `run_arms.py:114` still claims an assertion it does not make (0.5)
Unchanged from rounds 3–7. A docstring overstatement, not a bypass.

### RESOLVED · F-19's contradiction at the clean finish
§3.1. My R7 extended Gate C is green on the unmutated tree. Verified by re-running the exact check
that was red.

### RESOLVED · The largest unregistered narrowing (P1's `domain_not_selected`)
§1.3. Measured on the production branch, 303 of 303 absent tools registered at pass 1.

---

## 7. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | writes? | outcome | R8 |
|---|---|---|---|---|---|
| 1 | clean finish, provider said `stop` | `stream_service.py:7254` | yes | `completed` | pass |
| 1b | clean finish, provider said `length`/`tool_calls` | `:7305` ← `:6896` ← `:2778` | yes | `completed`, `finish_reason` agrees | **CLOSED — was F-19** |
| 1c | clean finish, provider said `content_filter` | same | yes | `failed` | pass |
| 1d | clean finish, an unrecognised provider word | same | yes | `interrupted` — a countable finding, fail-safe | pass (bounded, §3.4) |
| 2 | frontend-tool suspend | `:7010` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7458` | yes | `abandoned_by_user` | pass |
| 4 | mid-stream exception | `:7506` | yes | `failed` | pass |
| 5 | abandoned suspend, no provisional row | `:6338` | yes | `abandoned_by_user` | pass |
| 6 | abandoned suspend, provisional row | `:6381` | yes | `abandoned_by_user` | pass |
| 7 | **empty terminal turn** | `:6205-6237` | **user row stamped** | derived | **CLOSED as a recording hole** — the turn still gets no reply (CP-3.6), and the stamp targets *the session's newest un-outcomed user row*, which is the current turn's only when this turn created one |
| 8 | mid-turn checkpoint (crash surrogate) | `:6850` | yes | `crashed`, pessimistic | pass — good design |
| 9 | **process death before the first checkpoint** | no handler runs, so the orphan stamp is unreachable | **no** | ❌ none | **FAIL** |
| 10 | **tool-loop pass exhaustion** | `break :1994` → `"stop"` at `:4743` → `completed` | yes | ⚠️ `completed` | **FAIL — unchanged.** The exit yields the string literal `"stop"`; documented unreachable in practice (D7 forces the final pass tool-free) |
| 11 | expired / mismatched resume | delegates to #6 | yes | ✅ | pass |
| 12 | voice turn, clean finish, provider said `stop` | `voice:593-635` | yes | `completed` | pass |
| 12b | **voice turn, provider said `length` or `content_filter`** | `voice:615`/`:633` | yes | ⚠️ `completed` / `'stop'` | **FAIL — new. F-24** |
| 13a | **voice turn, exception** | INSERT at `:593` inside `try:` at `:442`; `except` at `:784` logs and returns | **no** | ❌ none — the recorded tool calls die with it | **FAIL** |
| 13b | **voice turn, suspend-abort** | `:495-496` → `:615`/`:633` | yes | ⚠️ `awaiting_input` on a turn nothing can resume (voice creates no `suspended_runs` record) | **FAIL, downgraded** |
| 14 | proactive check-in, generation succeeded | `internal.py:927-937` | yes | ✅ `completed` | pass |
| 14b | **proactive check-in, generation failed → static fallback** | `internal.py:847-849` → `:913` → `:934` | yes | ⚠️ `completed` / `'stop'` with no provider | **FAIL — F-28** |
| 15 | **suspend never resumed, never expired** | `db/suspended_runs.py:187` — `sweep_expired_runs` still has **zero callers** (re-verified repo-wide) | yes | ❌ stays `awaiting_input` forever | **FAIL** |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing rule | n/a | n/a | — |

**Seven paths fail (#9, #10, #12b, #13a, #13b, #14b, #15); two closed this round (#1b, #7).** Gate E
can see none of the seven: #9 and #13a write no row; the other five write values the gate does not
inspect.

**Handoff to V-LIVE, executable:**

```sql
-- F-24: a voice turn that was truncated or refused, recorded as a clean completion
SELECT finish_reason, outcome, count(*) FROM chat_messages
 WHERE content_parts ? 'voice_tts_sentences' GROUP BY 1,2;
-- F-28: proactive rows are indistinguishable between a grounded check-in and the static fallback
SELECT content = <_PROACTIVE_STATIC>, count(*) FROM chat_messages
 WHERE initiated_by='assistant_proactive' GROUP BY 1;
-- F-25/F-26: the two counting conventions, per turn
SELECT w->>'stage', w->>'pass', count(*) FROM chat_messages,
       LATERAL jsonb_array_elements(withheld_tools) w GROUP BY 1,2 ORDER BY 1,2;
-- P2 residual, the number the gating exists to keep countable
SELECT (tc->>'source_inferred') IS NOT NULL AS inferred, tc->>'source', count(*)
  FROM chat_messages, LATERAL jsonb_array_elements(tool_calls) tc GROUP BY 1,2;
```

---

## 8. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `domain_not_selected` registration | **Yes, ~240 times per turn** — measured. The opposite of vacuous; see F-25 on its size |
| the orphan stamp | **Yes** — any turn that ends with no content, no reasoning and no tool calls |
| `ensure_tool_call_instrumented` inference | **Yes, constantly** — 110/201 live |
| `source_inferred` mark | **Yes**, on every inferred row, unconditionally |
| `stamp_tool_call` raises on unknown source | **Yes** — a future mint site with a typo'd constant |
| `tool_call_source` → `unclassified` | **No** — zero callers |
| `dedupe_recorded_calls` | **No — by design.** Its two tests are gates on dead code |
| ContextVar fallback in `_budget_and_register` | **Yes** — the only branch production uses |
| ContextVar fallback in the `domain_not_selected` block | **Yes** — same, and **no gate covers it** (F-23) |
| `record_withheld`'s pass-scoped dedupe | **Yes, every multi-pass turn** — and it fans out (F-25) |
| `"pass": len(self._passes) or None` → `None` | **No** — unreachable; the comment says so |
| `outcome_for_finish_reason` `case "max_tokens"` | **No** — the gateway maps it to `length` first |
| `outcome_for_finish_reason` `case _` at the clean finish | **Yes** — `function_call`, `refusal`, any passthrough word (§3.4) |
| voice `_voice_suspended` branch | **Yes** — `permission_mode="ask"` suspends on paid Tier-R reads |
| voice non-suspend, non-`stop` termination | **Yes** — truncation and content-filter are routine; **F-24** |
| proactive static fallback | **Yes** — any provider error, timeout, or scaffolding-only reply; **F-28** |
| `outcome` / `runtime_variant` CHECK constraints | **Yes** for outcome; **No** for runtime_variant — only `'legacy'` is written |
| `latency_unmeasured` | **Yes, on ~26 of ~30 mint sites** — and **no gate exists** |

---

## 9. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:468-507` receives an `advertised` chunk on every pass and discards it (`content = chunk_data.get("content", "")` swallows it); `:631` therefore binds NULL, with an honest retraction comment. Not bypassed by overwrite: `record_pass` appends (mutation red), both upserts COALESCE. |
| **0.2** | **Largely closed for the text path this round.** Remaining: voice's INSERT has **no `withheld_tools` column at all** (`voice:596-598`); `budget_rail_tools`' drops go to `logger.warning` (`tool_surface.py:550-554`); the `{"tool": "*"}` pseudo-entry (`:2327`); and the column mixes per-pass and per-turn conventions (F-25) so any count over it is ambiguous. Per-pass registration stops after pass 1 (F-26). |
| **0.3** | `source`: **no bypass found** — assigned in exactly two places package-wide, `tool` unreachable by inference, inferred rows self-marking (all verified by mutation). Remaining: the voice suspend's own pending call is never recorded (F-22); the voice exception path writes no row at all; nested subagent calls are consumed at `:4850-4858` and never re-yielded, so they reach no INSERT on either pipeline; `latency_ms` is measured at **4 of ~30** mint sites and has **no gate**. |
| **0.4** | Seven paths. Write **no row**: pre-checkpoint process death, `voice_stream_service.py:784`. Write a **wrong** value: `:4743`→`completed` on pass exhaustion; `voice:615/633` (`completed`/`'stop'` on truncation or refusal — **F-24**); `internal.py:934` (`completed`/`'stop'` with no provider — **F-28**). Write a **success-class** value on an unresumable turn: `voice:495`→`:615`. Write a **stale** value: `db/suspended_runs.py:187`, zero callers. Full enumeration §7. |
| **0.5** | No bypass. `git ls-files` confirms `contracts/agent-runtime-baseline/{baseline-metrics.sql, baseline-metrics.frozen.txt, tools-list.snapshot.json}` and `eval/arms/run_arms.py`. F-9 is a docstring overstatement. |
| **0.6** | No bypass. `eval/arms/binding_format.py` plus `results/binding-format-20260804T035320Z.json` and `results/binding-format-FINDING.md` are all tracked. |
| **0.7** | No bypass of the literal claim. All three chokepoints (`:7098-7104`, `:6246-6249`, `voice:505`) route every recorded call through `ensure_tool_call_instrumented`, which sets `declaration` and `runtime_variant` unconditionally (both mutations red); `DEFAULT 'legacy'` in the DDL is the fail-safe direction. Bounded by F-11⁶ and by nested subagent calls reaching no INSERT. |

---

## 10. What changed in the failure

**Three real closures, and they are the right kind.** F-19's contradiction is gone at the site it was
found, verified by re-running the exact check that was red. The candidate-selection stage — P1's
whole finding, and the largest narrowing in the system — is instrumented, and I measured it on the
branch production actually runs rather than the one the test runs. The empty-turn recording hole is
closed by an insight that was genuinely a correction of an assumption, not a patch: an outcome is a
column, not a property of a role.

**And the class moved again, into the last place left.** For six rounds the defect was a confident
answer to something nobody measured — a column value, then a justification, then a derived
expression. This round the code is right and **the gate is what stages its own precondition** — the
P1 test hands itself `withheld_sink=` while both production call sites rely on a fallback branch no
gate touches, which is verbatim the failure the sibling gate's docstring warns about nine lines
earlier in the same file. The measurement that matters is that the *code* survives the mutation and
the *gate* does not: this checkpoint is now correct in a place it cannot prove it is correct.

**And one thing I have to record about my own work.** My R7 narrowing of P4 scored two of four sites
as passing that do not pass it. For `internal.py` I held the evidence — I quoted `_PROACTIVE_STATIC`
against the comment claiming the content is *"generated"* — and filed it as a bounded note instead of
a score. For voice I asked *"is it a constant?"* and never asked *"is the signal complete?"*, so a
two-valued flag over a four-valued terminal space read as derived. A gate that its own author applies
selectively is worth less than no gate, for the same reason a green test over an unreceived artifact
is: it reports safety. **The correction belongs to me, not to the builder, and the builder's claim
this round is a faithful restatement of what I told them.**

**My falsifier for this round's headline ruling, stated so a later round can execute it:** delete the
`else:` fallback at `tool_surface.py:397-400` and run the suite. If `test_tools_outside_the_hot_domains_register_as_withheld`
goes red, F-23 is withdrawn in full and the P1 gate covers production. If it stays green — which is
what I measured — then the largest narrowing in the system is instrumented by code that no test
protects, and one edit returns it to the state that falsified P1 live.
