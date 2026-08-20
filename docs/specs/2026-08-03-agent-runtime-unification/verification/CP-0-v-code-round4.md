# CP-0 · V-CODE — verdict, ROUND 4

Artifact frozen at `8aa01a77ad547abec25588e98b0f0378ae7f8f92`. **`git status --porcelain` is empty** —
the working tree is clean, so the committed state and the graded state are the same state. (Round 3
had to grade around unrelated dirt; this round has none.)

Source-only review. Nothing was run. No tracked file was modified. No commit message or builder
rationale prose was read — with the one exception the brief compels: the RUNSTATE's item table and
its `WHAT CLOSES CP-0` / `C1–C6 IS WITHDRAWN` sections, which are in scope because *"are the
withdrawals real"* is a question I was asked. The round-3 verdict was read as a list of claims to
re-check; every finding below was re-derived from source at this SHA.

I confirmed the brief is unmodified: `git log aa9ef87c4..8aa01a77a -- …/CP-0-V-CODE-PROMPT.md`
returns no commits.

**Method note for the gate audit.** For each gate I replicated its *string logic* verbatim over
in-memory copies of the real sources, applied the specific mutation the gate claims to reject, and
recorded whether it goes red. No tracked file was edited — the mutations were applied to strings in
memory in a scratchpad script. Where I say "green over the mutation", that is a mechanical result,
not an inference.

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R1 | R2 | R3 | **R4** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — tool-free passes genuinely fixed; the voice pipeline still persists no `advertised_tools` |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL** — **fourth iteration.** The ContextVar is armed *after* both narrowings have already run |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL** — `source` sound; `latency_ms` measured at 3 of 30, now *honestly* marked unmeasured |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL** — 2 of 6 paths fixed; 4 remain, and the narrowing that exempted 2 of them is withdrawn |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS** |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | FAIL | FAIL | **FAIL** — what is committed is a statement that the measurement did not complete |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS** on the literal claim; same vacuity bounds |

Four things are **genuinely fixed** this round and I want them on the record before the findings:
the proactive check-in writes an outcome; the voice clean-finish writes an outcome; tool-free passes
(D7 / D8 / ask-mode) now emit an advertise record; and `latency_ms` null is now self-describing
rather than silent. Three of those four close the exact defect the previous round named.

**The pattern from round 3 holds and is now four for four.** Each fix closes the precise `file:line`
the previous verdict cited, and each new gate is scoped to *the edit* rather than to *the property*.
0.2 is the clearest instance: R1 a function with no callers → R2 the wrong file → R3 an argument no
caller passed → **R4 a ContextVar armed 435 lines after the code that reads it has already run.**

---

## 2. The falsifier

Stated before the findings, so the two PASSes are readable. What I looked for that would have made
this FAIL, and what each search returned.

1. **A production narrowing that still discards its drops.** *Found — the fourth time, by a fourth
   route.* The registration path is now unconditional inside `_budget_and_register`, so the
   round-3 route is genuinely closed. But `instrument.surface_withheld` is armed at
   `stream_service.py:6420`, inside `_emit_chat_turn`, and **both** callers of
   `discovery_seed_for_surface` run strictly before `_emit_chat_turn` is ever invoked
   (`:5985` before `:6044`; `:7900` before `:7951`). *How I searched:* `grep -rn` for every
   `discovery_seed_for_surface` / `effective_enabled_tools` / `_budget_and_register` /
   `surface_withheld` call site repo-wide, then read each call site and traced the straight-line
   order in both enclosing functions. See F-1⁗.
2. **A terminal path writing no outcome, a stale one, or a wrong one.** *Found — four remain.* §5.
3. **A gate that is green over the defect it names.** *Found — three of six.* §4, with mutations.
4. **`advertised_tools` overwritten rather than appended.** *Not found, a fourth time.* `record_pass`
   appends (`instrument.py:237-245`); both upserts `COALESCE` (`stream_service.py:6222-6223`,
   `:7190` region).
5. **`source` defaulting to `tool`.** *Not found.* `ensure_tool_call_instrumented` assigns `meta`
   (closed name set) or `breaker` with `source_inferred` (`instrument.py:156-159`); `stamp_tool_call`
   raises on an unknown source (`:117-118`).
6. **DDL appended to an already-applied ledger step** (the brief's flagged likely failure).
   *Not applicable, re-checked independently.* `migrate.py` is one DDL string executed in full on
   every boot; no version table, step list or applied-marker. All four CP-0 statements are
   `ADD COLUMN IF NOT EXISTS` (`:319, :327, :344, :359`). The repository rule the brief cites belongs
   to the Go services' ledgers, not this one.
7. **Committed output for the 0.6 measurement.** *Found, and it is a statement of non-completion.*
   `git ls-files eval/arms/` now returns the two scripts **plus**
   `eval/arms/results/binding-format-INCOMPLETE.md`. No `binding-format-*.json` exists. F-10′.
8. **A closure criterion or scope correction that removes a failing property.** *Withdrawn — and one
   sentence of it survives.* §3.

Two things I **cannot determine from source**, unchanged across four rounds and worth restating
because they bound the two PASSes:

- **Whether the recorded values are right.** `advertised_tools|withheld_tools|runtime_variant`
  appears in five files: `migrate.py`, `instrument.py`, `stream_service.py`, and two tests. No query,
  model field, router or SQL reads any of them back. `latency_unmeasured` — new this round — is
  written at `instrument.py:168` and read by nothing at all. This is a V-LIVE/V-METRIC question.
- **The real-world frequency of a D7 forced-final pass**, which sets how much 0.1's new tool-free
  record actually captures.

---

## 3. Are the withdrawals real?

**`C1–C6`: yes, fully.** RUNSTATE lines 354–370. The six-row table is gone, not restated; the
withdrawal accepts each of the five specific charges by name (dropped 0.6/0.7, dropped the
`latency_ms` conjunct, narrowed 0.4, added a self-certifying C6, two rows false on source); and it
restores the exit condition explicitly: *"The exit condition for CP-0 is items 0.1–0.7 as frozen at
`aa9ef87c4`, unchanged."* I checked for the criterion reappearing under another name — there is no
replacement table, no renumbered rows, no `D1–Dn`. It did not reappear.

**Item 0.4's narrowing: withdrawn in substance, but one sentence of it is still live on the same
page — and it is the operative sentence.**

- Line 331 restores the frozen text verbatim, annotates *"my narrowing of this line is withdrawn"*,
  and grades the item **❌ FAILING**. Correct.
- Lines 372–378 withdraw the narrowing explicitly and give the reason. Correct.
- **Line 346–349, twenty-five lines earlier, still asserts it in the present perfect:**

  > *"CP-0.4's 'every terminal path' has been **corrected** to 'every terminal path that writes a
  > row', because a path that writes no row cannot carry a column…"*

  This sits under the heading `WHAT CLOSES CP-0` as **rule 1** — i.e. in the section a reader
  consults to decide whether the checkpoint may close. A reader of that section alone gets the
  narrowed criterion.

I am not calling this a hedge; the item row and the withdrawal section are both more specific and
both say the opposite, and the most likely explanation is an edit that missed one paragraph. But the
document currently states the narrowing as current fact in the one section whose job is to decide
closure, so **as an artifact the withdrawal is incomplete.** I graded 0.4 against the frozen text.

One new closure statement did survive the withdrawal — rule 2, *"CP-0 closes when the instrument
records honestly, not when the thing it measures is good, and not when a bound is provable."* I do
**not** rule this a weakening: it separates CP-0 from CP-4 rather than removing a property from any
of the seven items, and CP-4 is where a bound is first claimed. It is doing no work this round
regardless — 0.1, 0.2, 0.4 and 0.6 fail on their frozen text under any reading of it.

---

## 4. THE GATE AUDIT — six gates, three green over the defect they name

`tests/test_cp0_instrument.py` (486 lines). For each gate: the boundary it draws, the mutation that
should make it red, and whether it does. Mutations were applied to in-memory copies of the real
source and the gate's own logic re-run over them.

### Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:42-76`) — **GREEN OVER ITS OWN DEFECT, ROUND 3 RUNNING**

**Boundary drawn:** *text*. Five string predicates over two files: `"= budget_names_by_tokens("`
absent; `"_budget_withheld"` present; `'"stage": "token_budget"'` present; `"_budget_and_register("`
present; and `count(call) − count(def) >= 4`.

| mutation | should be | **is** |
|---|---|---|
| delete the ContextVar fallback in `_budget_and_register` (`tool_surface.py:246-253`) — restoring exactly the round-3 state where the narrowing registers nowhere | red | **GREEN** |
| add `return budget_names_by_tokens(catalog, names, token_budget=token_budget)` as the first line of `_budget_and_register` — a discarding call in the highest-traffic budgeter | red | **GREEN** |
| revert a site to `x = budget_names_by_tokens(` | red | red ✔ |

The second mutation is the instructive one. The gate forbids the *substring* `= budget_names_by_tokens(`.
`return budget_names_by_tokens(`, `foo(budget_names_by_tokens(...))`, and
`x = budget_names_by_tokens (` all discard the drops and all pass. The boundary is drawn around one
assignment form, not around "the drops reach a sink".

And the first mutation is the point: **Gate A is green today over the live production defect (F-1⁗),
for the third consecutive round.** Its own docstring states the standard it fails — *"a correct
mechanism with no production caller … count the callers"* — and it counts callers of a helper, never
whether the helper's registration path can reach a sink at the moment it runs. Also note the
docstring at `tool_surface.py:237-239` still ships the exemption round 3 flagged (*"``sink`` is
optional … That is a real hole and it is the honest one"*), now contradicted by the code beneath it.

### Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:155-195`) — **SOUND for its subject; the subject shrank**

**Boundary drawn:** *syntax-ish, and positional*. Each occurrence of
`await knowledge_client.mcp_execute_tool(` owns the region from itself to the next occurrence, and
that region must contain `source=instrument.SOURCE_TOOL`.

| mutation | should be | **is** |
|---|---|---|
| unstamp the in-loop dispatch (`:4672`) | red | red ✔ names line 4453 |
| unstamp the ext-task dispatch (`:7684`) | red | red ✔ names line 7670 |
| unstamp the approval-resume dispatch (`:7825`) | red | red ✔ names line 7784 |
| dispatch via a differently-named receiver (`await _kc.mcp_execute_tool(`) | red | red ✔ (trips the `>= 3` floor — **by luck**, not by design: it is invisible to the region logic and only the arity floor catches it) |

Region-ownership is a real invariant and a surplus stamp can no longer pay for a deficit. **This gate
is correct and I have no fault to find in its arithmetic.** Two scope notes, both forward-looking:
the needle narrowed from round 3's `mcp_execute_tool(` to
`await knowledge_client.mcp_execute_tool(`, so a fourth dispatch added through any other receiver is
counted only by the `>= 3` floor (which a *fourth* site would satisfy while going unstamped); and the
gate reads `stream_service.py` only, in a run whose entire purpose is to add a new runtime module
that will dispatch tools.

### Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:442-466`) — **SOUND, scope unchanged**

**Boundary drawn:** *syntax*. Each `UPDATE chat_messages SET` in `stream_service.py`; the clause
before `WHERE`; if it mentions `finish_reason` it must mention `outcome`. Plus an explicit
anti-vacuity assertion (`:466`).

| mutation | should be | **is** |
|---|---|---|
| drop `outcome = $2` from the abandoned-suspend UPDATE (`:6320`) | red | red ✔ names 6320 |
| a `finish_reason` UPDATE added in `voice_stream_service.py` or `routers/messages.py` | red | **invisible** — gate reads `stream_service.py` only |

Both other files do contain `UPDATE chat_messages`; neither touches `finish_reason` today, so
nothing is missed *now*. Best-constructed of the six, as in round 3.

### Gate D · `test_a_surface_narrowing_registers_without_anyone_wiring_it` (`:78-117`) — NEW — **RED-ABLE FOR ITS SUBJECT, AND ITS SUBJECT IS NOT THE PRODUCTION DEFECT**

**Boundary drawn:** *behaviour* — and this is the right instinct. The docstring says so explicitly
and correctly: *"this gate stops reading source. It runs the real budgeter with a real over-budget
catalog and asserts the narrowing ARRIVES."*

It does exactly that, and it would go red on all three historical states. **But look at line 99:**

```python
sink: list[dict] = []
token = _inst.surface_withheld.set(sink)      # ← the test arms the ContextVar itself
try:
    kept = _budget_and_register(None, "hot_seed", catalog, {...}, token_budget=200)
```

The comment on line 101 reads *"No explicit sink argument — exactly how both production call sites
invoke it."* That is true of the **argument** and false of the **context**. The one thing production
does differently — and the one thing that is broken — is that nothing has called
`surface_withheld.set()` by the time `_budget_and_register` runs. The test supplies the missing
precondition and then asserts the consequence.

This is the brief's own listed failure mode: *"does it assert over the artifact the consumer
receives, or over an intermediate the test itself constructed?"* The sink is an intermediate the test
constructed. **The gate is green over F-1⁗, the live production defect it was written to catch, and
it is green for the same structural reason as the three gates before it: the boundary was drawn
around the edit rather than around the property.** A gate that arms the ContextVar the way
`_emit_chat_turn` does — or better, that calls `discovery_seed_for_surface` and asserts a
`hot_seed` entry arrives in a recorder — is red today.

### Gate E · `test_every_assistant_row_insert_anywhere_writes_an_outcome` (`:119-153`) — NEW — **RED-ABLE for a missing column; BLIND to a missing value**

**Boundary drawn:** *syntax, and genuinely so.* This is the gate the builder describes as fixing "the
third time a gate of mine matched prose instead of code", and that specific fix is real: `head` is
cut at the first `VALUES`, `cols` is bounded by the column list's own parentheses, and SQL `--`
comments are stripped. The 1400-char comment block at `stream_service.py:6217-6221` — which contains
the word "outcome" — is correctly excluded. Scope is the whole `app` package, which is the right
population.

| mutation | should be | **is** |
|---|---|---|
| voice drops the `outcome` column from its list (the exact round-3 defect) | red | red ✔ names `voice_stream_service.py:581` |
| both `stream_service` terminal INSERTs drop `outcome` | red | red ✔ names 6202 and 7183 |
| **voice binds `None` instead of `instrument.OUTCOME_COMPLETED`** — column named, value NULL | red | **GREEN** |
| a new assistant INSERT with the role bound as a parameter (`VALUES ($1,$2,$3,…)`, `"assistant"` passed from Python) | red | **GREEN** — the `"'assistant'" in stmt` test never matches |
| an assistant `INSERT … SELECT` (no `VALUES` keyword) | red | red ✔ — but by accident: with no `VALUES`, `head` becomes the full 1400-char window and `cols` becomes whatever `rfind(")")` happens to enclose. It failed *closed* on my probe; the enclosed blob is arbitrary surrounding Python, and Python `#` comments are **not** stripped, so a nearby comment containing the word "outcome" flips it green |

**The third row is the finding.** The claim is *"every terminal path writes an outcome"*. The gate
verifies that the column is **named**. Round 3's complaint about voice was, in its exact words, *"the
column is not in the list"* — and the gate that was written to prevent recurrence tests precisely
that string. `outcome` present in the column list with `NULL` bound to it satisfies this gate
completely, and produces a row indistinguishable from the pre-CP-0 state in the database. This is the
`toBeVisible()`-asserts-presence-not-content shape: a named column binding NULL is present, listed,
and empty.

It is also structurally unable to see three of the four remaining 0.4 failures (§5): a path that
writes **no row** is not an INSERT; a **wrong** value (`completed` on a breaker exit) is a value; and
a **stale** value (`awaiting_input` forever) is written by nobody. The gate's docstring claims it
covers *"the actual population the claim is about"*; the population the claim is about is terminal
paths, and the gate's population is INSERT statements.

### Gate F · `test_the_vocabulary_matches_the_database_constraint` (`:468-485`) — **SOUND for `outcome`; covers nothing else**

**Boundary drawn:** *syntax* — a regex over the real DDL, comparing the CHECK list against
`instrument.OUTCOMES`. Red-able both directions (add a Python constant, or drop one from the DDL).

| mutation | should be | **is** |
|---|---|---|
| drop a value from either side | red | red ✔ |
| **delete the `advertised_tools` / `withheld_tools` / `runtime_variant` `ADD COLUMN` lines entirely** | red | **GREEN** ×3 |

Unchanged from round 3 and still the suite's largest structural gap: **no test asserts that three of
the four CP-0 columns exist in the schema at all.** Given the brief flags the unapplied-migration
class as the most likely way 0.1/0.2/0.7 is written but never applied, that is the one assertion
worth having.

### Scorecard

| gate | boundary | red-able for its own defect? |
|---|---|---|
| A · budgeter wiring | text | **NO** — green over the live defect, 3rd round |
| B · dispatch stamping | positional syntax | **yes** |
| C · outcome/finish_reason lockstep | syntax | **yes**, within one file |
| D · surface narrowing arrives | behaviour, precondition supplied by the test | **NO** — green over the live defect |
| E · assistant-INSERT outcome | syntax | **partly** — catches a missing column, blind to a NULL value and to a parameterised role |
| F · outcome vocabulary vs DDL | syntax | **yes** for `outcome`; blind to the other three columns |

Three of six are green over a defect in their own stated subject. The brief asked whether the
boundary is drawn around text or syntax: A is text; D is behaviour with the failing precondition
handed to it; E and F are syntax and are the two best-built gates in the file, each with one
specific hole named above.

---

## 5. Terminal-path enumeration (0.4) — full, not summarised

Graded against the **frozen** criterion (*"every terminal path, incl. cancel and crash"*), the
narrowing having been withdrawn.

| # | terminal path | `file:line` | writes a row? | outcome | R4 |
|---|---|---|---|---|---|
| 1 | clean finish | `stream_service.py:7183` | yes | `completed` | pass |
| 2 | frontend-tool suspend | `:6920` region | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7352` region | yes | `abandoned_by_user` (`shield`ed) | pass |
| 4 | mid-stream exception | `:7393` region | yes | `failed` | pass |
| 5 | abandoned suspend, no provisional row | `:6276` region | yes | `abandoned_by_user` | pass |
| 6 | abandoned suspend, provisional row | `:6320` | yes | `abandoned_by_user` | pass |
| 7 | **empty terminal turn** | `:6163-6176` | **no** | ❌ none | **FAIL** — was the one case the withdrawn narrowing exempted; back in scope. Honestly labelled *"CP-0.4, KNOWN HOLE, DELIBERATELY NOT CLOSED HERE"* and logged at INFO, so it is countable |
| 8 | mid-turn checkpoint (crash surrogate) | `:6798` | yes | `crashed`, pessimistic | pass — good design |
| 9 | **process death before the first checkpoint** | checkpoint is inside `if tool_call is not None:`, throttled 1.5 s | **no** | ❌ none | **FAIL** — *crash* is named in the frozen criterion |
| 10 | **tool-loop pass exhaustion** | `break` at `:1994`, `:4722` → defensive `finish_reason: "stop"` | yes | ⚠️ `completed` | **FAIL, and the worst kind** — a breaker exit recorded as a clean success. Not a hole, a wrong answer; nobody re-checks a column that has one |
| 11 | expired / mismatched resume | delegates to #6 | yes | ✅ | pass |
| 12 | **voice turn, clean finish** | `voice_stream_service.py:581-595` | yes | ✅ `completed` | **FIXED this round** |
| 13 | **voice turn, exception** | INSERT at `:581` sits inside `try:` at `:440`; `except Exception` at `:744` logs and returns | **no** | ❌ none | **FAIL** — a voice turn that errors mid-stream records nothing at all |
| 14 | **proactive check-in** | `routers/internal.py:932-940` | yes | ✅ `completed` | **FIXED this round** |
| 15 | **suspend never resumed, never expired** | `db/suspended_runs.py:187` — `sweep_expired_runs` still has **zero callers** (`grep -rn` repo-wide → the definition only) | yes | ❌ stays `awaiting_input` forever | **FAIL** — a success state on a dead turn |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing "no timeout on LLM pipelines" | n/a | n/a | — |

**Two of six fixed; four remain (#7, #9, #10, #13, #15 — five, of which #7 and #9 are the two the
withdrawn narrowing had exempted).** Note that Gate E can see **none** of the four: #7, #9 and #13
write no row; #10 and #15 write a value the gate does not inspect.

---

## 6. Findings

Fixes first.

### RESOLVED · The proactive check-in and the voice clean-finish write an outcome

`routers/internal.py:932-940` and `voice_stream_service.py:581-595`. Both add
`finish_reason, outcome, runtime_variant` to the column list and bind
`instrument.OUTCOME_COMPLETED` / `instrument.RUNTIME_LEGACY`. Both are honest values: the proactive
message is complete when it lands, and the voice INSERT is reachable only on a clean finish. Round
3's F-6 and path #14 are closed at the level they were named. This is a real fix to a real finding
and it was made in the two files the instrument was not built in — the correct response to the
round-3 diagnosis.

### RESOLVED · Tool-free passes emit an advertise record (0.1's F-7)

`stream_service.py:2315-2331`. The `if not offered_tools:` block sits at pass-loop scope, after the
`if offered_tools: … else: offered_tools = False` chain, so it fires on all three tool-free routes —
D7 forced-final (`last_iter`, `:2069-2070`), D8 provider rejection (`tools_supported = False`), and
ask-mode filtering everything out (`:2311-2314`). The consumer at `:6806-6811` turns it into
`record_pass([])`, so the `pass` ordinals now correspond to the turn's real model-call count and the
comment at `:2159` is no longer false. Correctly ordered, too: `record_pass` runs before the
withheld drain, so the `pass` stamp lands on the right pass.

*One defect inside the fix.* The withheld entry it emits is
`{"tool": "*", "stage": "pass_offered_no_tools", …}`. `"*"` is not a tool name, and `record_withheld`
dedupes on `(tool, stage)` — so a turn with three tool-free passes registers **one** entry, and it
names none of the tools that actually became unreachable. The column is typed
`[{tool, stage, reason}]`; a consumer counting withheld tools now has a literal `*` to special-case.
It records *that* a pass was tool-free (which is the useful half) but not *what* was withheld.

### RESOLVED-IN-KIND · `latency_ms` null is now self-describing

`instrument.py:166-168`. Every unmeasured entry gets `latency_ms: None` plus
`latency_unmeasured: <source>`. The reasoning in the comment is right — recording `0` for a result
our own code minted would be a fabricated number, and an explicit null with a reason reads as "not
measured here" rather than "instant". This is the honest construction. It does not change the
arithmetic: `grep -c 'yield {"tool_call"'` → **30**; sites supplying a real latency → **3** (`:4672`,
`:7684`, `:7825`). And `latency_unmeasured` is itself read by nothing.

### F-1⁗ · The same defect, a fourth time: the sink is armed after the narrowing has already run (0.2) — **the finding that decides 0.2**

R1: `budget_names_by_tokens_ex` had zero production callers.
R2: the four `tool_surface` sites still called the plain variant.
R3: those sites called `_budget_and_register`, whose `withheld_sink` no caller supplied.
**R4: registration no longer depends on the argument — it depends on a ContextVar that is set 435
lines and one stack frame too late.**

The registration path itself is now unconditional and correct:

```
tool_surface.py:243-253   if dropped:
                              if sink is not None:  sink.extend(...)
                              else:                 record_surface_withheld(n, stage=..., reason=...)
instrument.py:197-200     sink = surface_withheld.get()
                          if sink is None: return          # ← the silent exit
```

The arming site is `stream_service.py:6419-6420`:

```
_surface_sink: list[dict] = []
instrument.surface_withheld.set(_surface_sink)
```

which is inside **`_emit_chat_turn`** (`async def` at `:6331`). The two production narrowings are:

| call site | enclosing function (`def` line) | `_emit_chat_turn` invoked at | order |
|---|---|---|---|
| `discovery_seed_for_surface` `stream_service.py:5985` | `stream_response` (`:4905`) | `:6044` | narrowing runs **59 lines earlier**, straight-line |
| `discovery_seed_for_surface` `stream_service.py:7900` | `resume_stream_response` (`:7513`) | `:7951` | narrowing runs **51 lines earlier**, straight-line |

Both are plain sequential statements in the same function body — no branch reorders them. And
`_emit_chat_turn` is an **async generator**: its body does not begin executing until the first
`__anext__` driven by the `async for` at `:6044` / `:7951`, so `:6420` cannot run before `:5985` /
`:7900` under any interleaving.

At the moment `_budget_and_register` runs, `surface_withheld.get()` therefore returns the
ContextVar's declared default — `None` (`instrument.py:187`) — and `record_surface_withheld` returns
at its second line. **The `hot_seed`, `hot_seed_plan_forge`, `hot_seed_skill` and
`hot_seed_glossary` stages still cannot appear in `withheld_tools` on any turn.**

I verified the reachability closure: `grep -rn` repo-wide shows `_budget_and_register` is called only
from `discovery_seed_for_surface` (`tool_surface.py:375, 423, 465`) and `effective_enabled_tools`
(`:596`), and `effective_enabled_tools` has exactly one caller — `discovery_seed_for_surface:388`.
So every one of the four sites is reachable *only* through the two call sites above. There is no
third route and no other arming site (`grep -rn "surface_withheld"` → `instrument.py:187,190,197` and
`stream_service.py:6420` only).

This remains the largest narrowing in the system: `HOT_SEED_TOKEN_BUDGET = 2000` against a 315-tool
frozen catalog, on every turn, fresh and resume. It is structurally identical to arm E, the founding
measurement of the whole rebuild. Against invariant 3 (*"Every withholding registers. An exclusion
with no `{tool, stage, reason}` row is a defect"*), the largest exclusion in the system has now
registered nothing for four consecutive rounds.

**A note on the mechanism choice, because it bears on whether the fix is legitimate.** A ContextVar
is a defensible answer to "the call sites keep not passing the argument" — it is inherited by asyncio
tasks, so it is naturally per-request, and the docstring's claim that it *inverts the failure mode*
(forgetting now over-records loudly rather than under-recording silently) would be true **if the var
were armed at the top of the request**. Armed where it is, the failure mode is not inverted at all —
it is the same silent under-recording, one layer further out. The mechanism is not the problem; the
arming point is. I record this because "is a ContextVar a legitimate fix or a way to make an untested
path look wired" was put to me directly: **the mechanism is legitimate; this instance of it is
untested where it matters, and Gate D is the test that hides that** (§4).

Two smaller residuals on the same item, both unchanged from round 3:

- `budget_rail_tools` returns `(kept, dropped)` and the caller sends the drops to `logger.warning`
  (`tool_surface.py:257-291`, caller at `:515-518`), not to `withheld_tools`.
- `_budget_withheld` is drained only inside `if offered_tools:` (`stream_service.py:2206` region), so
  activation drops accumulated before a D7 forced-final pass are still discarded — note the new
  `:2322` block yields its own advertise chunk but does **not** drain `_budget_withheld`.

### F-6′ · The voice pipeline records the outcome and still records none of the other three (0.1, 0.2, 0.3)

`voice_stream_service.py:581-595`. The column list is now
`(message_id, session_id, owner_user_id, role, content, content_parts, sequence_num, model_ref,
branch_id, local_date, finish_reason, outcome, runtime_variant)` — **no `advertised_tools`, no
`withheld_tools`, no `tool_calls`.**

This is not a tool-free path. `voice_stream_service.py:512` calls the shared `_stream_with_tools`
with `permission_mode="ask"`, so its passes emit `{"advertised": …}` events — including, now, the new
`pass_offered_no_tools` records and any `permission_mode_ask` withholdings — and the voice consumer
loop absorbs the chunk into `chunk_data.get("content", "")` and discards it. Its `tool_call` chunks
are emitted as SSE and never persisted, so voice-dispatched tools carry `source` and `latency_ms`
only vacuously, by never being recorded.

**Gate E certified this file as compliant.** The gate asks for `outcome`; `outcome` was added;
`advertised_tools` and `withheld_tools` were not, and no gate asks. This is the round-3 pattern
exactly: the fix closes the string the verdict named.

### F-4′ · The empty terminal turn is back in scope and still writes nothing (0.4)

`stream_service.py:6163-6176`. `_persist_terminal_assistant` returns `False` before any write when
`not content and not reasoning and not tool_calls_history`, under a comment naming itself *"CP-0.4,
KNOWN HOLE, DELIBERATELY NOT CLOSED HERE"* and logging at INFO so the hole is countable. The
labelling and the logging are the right way to carry a known hole. But the narrowing that exempted it
is withdrawn (§3), so under the frozen criterion this is a failing path again — as is process death
before the first checkpoint (#9), the other case the narrowing covered.

### F-9 · `run_arms.py` still claims an assertion it does not make (0.5)

`eval/arms/run_arms.py:114`: *"That the answer tool is absent is asserted below, never assumed."*
There is no such assertion. `has_answer` is computed at `:193`, printed at `:195`, stored at `:198`;
nothing exits or fails. If a future budgeter change kept the answer tool, arm E would silently stop
being an arm. Not fatal to 0.5 as worded, but the docstring overstates the artifact — unchanged from
round 3.

### F-10′ · What is committed for 0.6 is a statement that the measurement did not happen

`eval/arms/results/binding-format-INCOMPLETE.md` is committed (`git ls-files eval/arms/` confirms;
it is the only file in `results/`). No `binding-format-{stamp}.json` — the artifact
`binding_format.py:206` actually produces — exists on disk or in the index.

**I want to credit this properly, because the instinct is right.** Committing *"attempted, and here
is exactly how far it got and why it stopped"* is materially better than an empty directory, and the
document's self-assessment is unusually rigorous: it states that 2 of 5 arms ran; that
`decoy_control` — the only arm separating *"the model read the binding"* from *"the model copied the
one UUID in sight"* — never ran; that 3/3 bounds a failure rate only at ≤63.2%; and that it ran on
one model. It then says, in its own words: *"This is not a result, and no design decision may cite
it."*

I take that at face value, and it decides the item. The claim is *"the binding-format measurement is
scripted **and its output committed**"*. The second conjunct exists so that a later checkpoint has a
number to cite. **A record of non-completion is not the measurement's output**, and the document
itself forbids citing it. `0.6` fails, and it fails by the artifact's own statement rather than by my
inference.

(One drift note: RUNSTATE line 333 still reads *"measurement **running** … result not yet in"*, while
the committed artifact says it stopped when LM Studio evicted the model. The item state is stale
against its own artifact.)

### F-11″ · `runtime_variant`, `declaration` and `unclassified` remain constants or dead (0.7, vacuity)

- `RUNTIME_AGENTRUNTIME` (`instrument.py:85`) has no producer: the constant, the test, and nothing
  else. Every write site passes `RUNTIME_LEGACY` or relies on `DEFAULT 'legacy'` (`migrate.py:359`).
- `declaration` is `chunk.get("tool")` at both assignment points (`instrument.py:122`, `:169`); no
  site passes a differing `declaration`.
- `tool_call_source()` (`:88-98`), the only function that can return `unclassified`, still has
  **zero callers**. The persistence chokepoint is `ensure_tool_call_instrumented`, which assigns
  `meta` or `breaker` and never `unclassified`. No row can carry the value.

These are NV-class rather than item verdicts — 0.7's literal claim holds — but they bound its PASS.

### F-8′ · Five of six recordings remain write-only

`advertised_tools|withheld_tools|runtime_variant` appears repository-wide in exactly five files:
`migrate.py`, `instrument.py`, `stream_service.py`, `tests/test_cp0_instrument.py`,
`tests/test_tool_discovery.py`. `chat_messages.outcome` has no reader. `latency_unmeasured` — new
this round — has no reader. `tc->>'source'` is read only at
`contracts/agent-runtime-baseline/baseline-metrics.sql`, which is the pre-CP-0 baseline, not a live
consumer. This is the brief's hunting ground #3 and the `finish_reason='streaming'` precedent
reproduced. It does not by itself falsify *"the database records X"*, but it is why no source-level
evidence can show the recorded values are right.

---

## 7. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source (`instrument.py:117`) | **Yes** — a future mint site with a typo'd constant. Covered. |
| `ensure_tool_call_instrumented` inference (`:156`) | **Yes, constantly** — 27 of 30 mint sites are unstamped. |
| `tool_call_source` → `unclassified` (`:98`) | **No** — zero callers. F-11″. |
| `_budget_and_register`'s ContextVar fallback (`tool_surface.py:246-253`) | **No.** `surface_withheld` is `None` at both production call sites because it is armed later. The four `hot_seed` stages cannot appear in any row. **F-1⁗ — the round's central vacuity finding.** |
| `pass_offered_no_tools` withheld record (`stream_service.py:2326`) | **Yes** — D7/D8/ask-mode. But dedup on `(tool, stage)` caps it at one entry per turn and it names no real tool. |
| `outcome` CHECK constraint (`migrate.py:344-346`) | **Yes** — drift-guarded by Gate F, which parses the real DDL. |
| `runtime_variant` CHECK (`migrate.py:360`) | **No** — only `'legacy'` is ever written. |
| `run_arms.py` hash-mismatch refusal (`:65-68`) | **Yes** — any edit to the snapshot's `tools` array. |
| `run_arms.py` "answer tool absent in arm E" | **Never** — the assertion does not exist. F-9. |
| The five discovery-gated `withheld_tools` stages (`stream_service.py:2171-2200` region) | **Yes** — live suppressions today. |
| `permission_mode_*` stage (`:2209` region) | **Yes**, incl. on voice — where the event is discarded (F-6′). |
| `token_budget` stage (activation) | **Yes**, on `tool_load`/`tool_list` cap only. |
| Gate A | **Yes**, and **green over a live instance of its own defect for the third round.** §4 |
| Gate B | **Yes**, positional, correct. |
| Gate C | **Yes**, with an explicit anti-vacuity assertion. |
| Gate D | **Yes**, but its subject is a precondition the test supplies itself; **green over the live defect.** §4 |
| Gate E | **Yes** for a missing column; **cannot fire** on a NULL-bound outcome or a parameterised role. |
| Gate F | **Yes** for `outcome`; **cannot fire** on the other three columns being dropped from the DDL. |

---

## 8. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:581-595` — persists no `advertised_tools` though it runs `_stream_with_tools` (`:512`) and discards the `advertised` event. F-7 (tool-free passes) is **closed** at `stream_service.py:2315-2331`. Not bypassed by overwrite: the recorder appends (`instrument.py:237-245`) and both upserts COALESCE (`:6222-6223`, `:7190` region). Search: `grep -rn "INSERT INTO chat_messages"` over `app/` → 6 sites, column list read on each. |
| **0.2** | `tool_surface.py:375, 423, 465, 596` — all four surface-assembly narrowings call `record_surface_withheld`, which returns immediately because `instrument.surface_withheld` is armed at `stream_service.py:6420`, **after** the only two call sites that reach them (`:5985` → `_emit_chat_turn` at `:6044`; `:7900` → `:7951`). `budget_rail_tools`' drops go to `logger.warning`. `_budget_withheld` drained only under `if offered_tools:`. Search: `grep -rn` for every caller of `_budget_and_register` / `discovery_seed_for_surface` / `effective_enabled_tools` / `surface_withheld` repo-wide, then read both enclosing functions for straight-line order. |
| **0.3** | `source`: **no bypass found** — all three `mcp_execute_tool(` sites stamped and recorded; the chokepoint classifies the rest by a closed name set. `latency_ms`: measured at 3 of 30 mint sites; the other 27 carry an explicit null plus `latency_unmeasured`. Voice tool calls reach no INSERT at all. Search: `grep -c 'yield {"tool_call"'` → 30; `grep -n "latency_ms"` → 3; `grep -rn "mcp_execute_tool"` → 3 call sites, cross-checked against the four stamp offsets. |
| **0.4** | Five paths, graded against the restored frozen criterion. Write **no row**: `stream_service.py:6163` (empty turn), pre-checkpoint process death, `voice_stream_service.py:744` (voice exception). Write a **wrong** value: `:1994`/`:4722` file a breaker exit as `completed`. Write a **stale** value: `db/suspended_runs.py:187` — `sweep_expired_runs` has zero callers repo-wide. Fixed this round: proactive check-in and voice clean-finish. Full enumeration of 17 paths in §5. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/` holds `tools-list.snapshot.json`, `baseline-metrics.sql`, `baseline-metrics.frozen.txt`. `run_arms.py` builds all five arms from the snapshot and refuses on hash mismatch (`:65-68`). F-9 is a docstring overstatement, not a bypass. |
| **0.6** | The committed artifact is `binding-format-INCOMPLETE.md`, which states 2 of 5 arms ran, the control never ran, and *"no design decision may cite it."* No `binding-format-*.json`. Search: `git ls-files eval/arms/`, `ls eval/arms/results/`, and a content search for `binding_format\|binding-format` across `*.json *.md *.txt`. |
| **0.7** | No bypass of the literal claim: both `stream_service` INSERT chokepoints route every entry through `ensure_tool_call_instrumented`, which sets `declaration` and `runtime_variant` unconditionally (`instrument.py:169-170`); `voice_stream_service.py:595` and `routers/internal.py:940` now pass `RUNTIME_LEGACY` explicitly; `DEFAULT 'legacy'` (`migrate.py:359`) is the fail-safe direction for an omitting writer. Bounded by F-11″ (both values constant, dead `unclassified`) and by voice tool calls reaching no INSERT, so *"every recorded call"* holds partly because those calls are never recorded. |

---

## 9. What is genuinely better this round

Briefly, because the brief asks me to spend words on what is not.

**Four fixes are real and correctly diagnosed.** The two outcome writes landed in the two files the
instrument was not built in — the right response to a finding about scope, not about a line. The
tool-free advertise record closes F-7 at the producer *and* the consumer, in the right order, and it
is the fix with the most measurement value in it. The `latency_unmeasured` marker is the honest
construction of a null and its reasoning is correct. **Gate E's syntax fix is real**: `head` cut at
`VALUES`, `cols` bounded by the column list's own parens, SQL comments stripped, whole-package scope
— I tried to make it match a comment and could not.

**And the withdrawals are the strongest thing in this round.** `C1–C6` is retracted in full, each
charge accepted by name, with the exit condition restored to the frozen items — that is the correct
response to Ruling 1, and the one paragraph of the 0.4 narrowing still standing at RUNSTATE line
346-349 reads as an editing miss against two more specific passages that say the opposite. A builder
that withdraws a criterion it authored, and grades its own item ❌ FAILING afterwards, is operating
the protocol as written.

**The pattern is nonetheless four for four, and it is the thing I would want recorded.** Each round's
fix closes the exact `file:line` the previous verdict cited, and each round's new gate is scoped to
that edit rather than to the property. On 0.2 the defect has now moved four times — no caller, wrong
file, unpassed argument, unarmed context — and *"every narrowing registers"* has not been true at any
point across four rounds. Gate D is the sharpest illustration: the builder correctly diagnosed that
source-reading gates were the problem, correctly chose a behavioural gate instead, and then supplied
the gate with the one precondition production does not supply. **The next gate on this item should be
written before the fix, and should call `discovery_seed_for_surface` — not `_budget_and_register` —
through the real entry point.**
