# CP-0 · V-CODE — verdict, ROUND 10

Artifact frozen at `874b3524e6ab0755b0451060e9f5ff0ddc0a299b`.

## 🔴 THE FREEZE BROKE AGAIN — at the very end, in a file I graded and in the frozen baseline itself.

`git status --porcelain` was **empty** at my first call and stayed empty through the entire audit —
all four mutation batches, every reading, every measurement below. `HEAD` never moved: it is
`874b3524e` at my first call and at my last. **Everything in this verdict is graded against
`874b3524e`, and at the time I read each file it was byte-identical to that SHA.**

Then, between writing this verdict and my final integrity check, the tree went dirty:

```
 M contracts/agent-runtime-baseline/baseline-metrics.sql
 M services/chat-service/app/services/stream_service.py
?? docs/specs/.../verification/CP-0-v-metric-round9.md
```

**It was not me.** My harness writes only to an untracked scratch copy
(`…/scratchpad/mt/services/chat-service`, `…/scratchpad/mt/contracts`) — the paths are in the
harness and every batch restored its files and re-verified a GREEN baseline. The two modified files
contain hand-written builder commentary that matches none of my mutations.

**Two things follow, and both are findings rather than housekeeping.**

1. **The "frozen" baseline that item 0.5 certifies is under edit for the third consecutive round.**
   R9 recorded this and it has not changed. A checkpoint edited while it is graded cannot be closed
   by the grade, because the thing graded and the thing shipped are no longer known to be the same
   thing.
2. **The drift independently corroborates two of my findings, which I derived from source before
   seeing it, and I do not credit either fix — neither is in the artifact I was handed.**
   - The `stream_service.py` edit adds `outcome_source = 'path'` to both assistant INSERTs. That is
     **F-42**, and the builder's own comment supplies the live number I could not: *"64.8% of
     outcomed rows read as path-written when they were not."*
   - The `baseline-metrics.sql` edit makes the outcome class prefer `outcome` over `finish_reason`,
     with the comment: *"33 of 39 turns counted as `awaiting_input` — a state this codebase calls a
     SUCCESS — were turns the instrument itself records as DEAD."* That is **F-38**, measured at
     **84.6%**, in the direction I ruled it. Note what the fix does: it teaches the **reader** to
     prefer `outcome`, rather than making the sweep move `finish_reason` with it. The row still
     contradicts itself; the query now knows which half to believe. F-38 stands.

Source-only review. Nothing in the product was run. **No tracked file was modified** — every
mutation ran against an untracked copy of the tree in a scratch directory. No commit message or
builder rationale prose was read.

**Method — and it is stronger than R9's.** R9 transcribed 17 gates into a harness. This round I
copied `services/chat-service` + `sdks/python` + `contracts/agent-runtime-baseline` into a scratch
tree and ran **the real suite** (`pytest tests/test_cp0_instrument.py`) against it — all 56 tests,
as written, no transcription. Each mutation asserts (a) the needle occurs the expected number of
times and (b) the file text actually changed; a needle-miss or a no-op is reported as *not applied*
and never counted as a blind spot. Baseline verified GREEN before the first mutation and again after
the last restore, in every batch.

**104 mutations applied. 75 caught, 29 blind.** (R9: 30 applied, 6 caught, 24 blind.)

---

## 1. Verdict

**Overall: `FAIL`.** The three things handed to me this round are, in order: **right**, **right and
measurably so**, and **wrong in a way that reproduces the defect this run has now committed six
times.** The reconciler removal is correct. The gate rewrite genuinely works — I constructed all
five mutations the brief named and all five go red. `resolve_expired_suspends` is the first sweep in
this checkpoint built on evidence rather than absence, and it writes a row that contradicts itself
into a gate that cannot see the file it lives in. And `intent_gate`, P1's seventh frame, **registers
nothing in production on either of its two call sites** — guarded by a test that arms the
precondition production fails to supply, which is the exact failure its own sibling gate's docstring
names as "the fifth recurrence."

| item | claim | R7 | R8 | R9 | **R10** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — unchanged. `voice_stream_service.py:639` still binds the literal `None` with an honest retraction comment above it; F-26 (assembly stages register pass-1-only) unchanged |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL** — a seventh stage was added and is a **production no-op (F-37)**. Voice's INSERT still has **no `withheld_tools` column at all** (re-read at `:603-608`); `budget_rail_tools`' drops still go to `logger.warning` (`tool_surface.py:551`) — an eighth unregistered narrowing |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL** — unchanged. `source` is strong (5 mutations, 5 red). `latency_ms`: deleting the `latency_unmeasured` reason outright leaves the suite **green** — measured, still no gate |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL — one path genuinely closed, one deliberately re-opened, one new contradiction.** §3, §7 |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS at the SHA** — `git ls-tree 874b3524e` confirms all three baseline files + `eval/arms/run_arms.py`. ⚠️ `baseline-metrics.sql` went **modified in the working tree** during this audit, third round running. A "frozen" artifact under edit is a finding for whoever owns the freeze, not for this item's letter |
| 0.6 | binding-format measurement scripted **and its output committed** | PASS | PASS | PASS | **PASS** — `binding_format.py` + `binding-format-20260804T035320Z.json` + `binding-format-FINDING.md`, all tracked at the SHA |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS** — re-verified by mutation (4 mutations, 4 red). Bounded by F-11 |

| property | R10 ruling |
|---|---|
| **P1** — every tool absent from a pass's advertised set registers `{tool, stage, reason, pass}` | **NOT MET, and it moved BACKWARDS.** The seventh frame was added, correctly placed inside the function, behaviourally gated — and **wired at a point where its records are discarded twice over**. F-37, §5. F-26 unchanged. The `domain_not_selected` half re-verified strong (3 mutations, 3 red) |
| **P2** — a call's `source` is assigned structurally, never inferred | **Unchanged, and the strongest class in the suite.** Load-bearing half re-verified by mutation: defaulting the chokepoint to `tool`, dropping `source_inferred`, and inverting the meta/breaker split all go red. Residual countable, no reader |
| **P3** — every terminal path writes an outcome | **NOT MET, and the shape is better than it has been.** The guessing branch is gone (correct, §2). What remains is vacuous (F-31, carried and re-verified). #15 is **closed for the stream path** and structurally unreachable for voice (F-40). #13a unchanged |
| **P4** — no CP-0 column bound to a constant at any INSERT reachable from >1 terminal condition | **NOT MET at a NEW site.** R9's site (`instrument.py:528`) is genuinely gone. `instrument.py:584` replaces it: `OUTCOME_ABANDONED_BY_USER` asserted across ≥3 conditions. §6, mandate 3 |

**What landed, credited before the findings.**

1. **The reconciler's user branch is gone, not narrowed, and that was the right call.** §2.
2. **The gate rewrite is real.** All four reconciler gates now call the function against a stub pool.
   I constructed every mutation the brief named — short-circuited body, inverted age bound, flipped
   outcome, inverted predicate, deleted caller with the import retained — and **all five go red**.
   Measured, not reasoned. The reconciler moved from 2/12 to **12/19**. §4.1.
3. **`test_it_does_not_delete_the_evidence` was fixed correctly.** The brief flagged that its first
   version scanned for `"DELETE"` and matched the docstring's own explanation. It now parses the
   function with `ast`, filters to string constants naming a real table, and asserts over those. I
   added a genuine `DELETE FROM chat_suspended_runs` inside the function (S11) — **red**. The fix
   works, and it is the first time in ten rounds a prose-matching gate has been closed by reading
   the *code* rather than by narrowing the window.
4. **`resolve_expired_suspends` acts on evidence.** `expires_at <= now()` is a fact the row carries
   about itself, and `load_suspended_run` (`db/suspended_runs.py:116`) really does filter
   `expires_at > now()`. This is categorically different from the removed branch, which reasoned
   from the *absence* of a reply. Credit where it is due: the builder was asked for evidence and
   found some. §3.

---

## 2. Was removing the user-row branch — rather than narrowing it — right?

**Yes, and the reasoning in the removal is better than the reasoning in the thing removed.**

I set the bar before looking: a narrowing would have been right if a predicate existed that
separates *crash* from *the four other conditions*, using only facts the rows carry. It does not.

- **A user deleting an assistant reply** (`routers/messages.py:633`) leaves a row byte-identical to
  a crash orphan. No column distinguishes them: `chat_messages` has no `deleted_at`, no tombstone,
  and the DELETE is a hard delete. A "session had later activity" guard would have suppressed the
  86/223 measured wrong stamps **and** every genuine crash in a session the user came back to —
  which is most of them. That is not a narrowing, it is trading a false-positive rate for a
  false-negative rate with no way to measure either.
- **`branch_id`** would have to enter the predicate for edit-and-regenerate (R9 F-32), and even with
  it the deletion case survives.
- The decisive point is the one the removal comment makes: **the branch had no evidence, only
  absence.** Adding guards to a guess produces a narrower guess. This checkpoint's most expensive
  defects — the 65.7% with no derivation, the voice `advertised_tools` literal, F-19, F-28 — are all
  confident values for unobserved things. Removing is the only move that does not add a fifth.

**Does what remains have any purpose?** Three candidate purposes; only one survives.

1. **Draining the pre-CP-0 backlog.** Real, and it is a one-time effect. After the first boot of
   this build it stamps zero forever.
2. **Repairing future process deaths.** **No.** Re-verified at this SHA: `grep` for `'streaming'`
   across `app/` returns exactly one writer — `stream_service.py:6879` — and that call passes
   `outcome=instrument.OUTCOME_CRASHED` at `:6887`, deliberately, with a comment explaining why.
   `finish_reason='streaming' AND outcome IS NULL` is **unreachable for any row this build writes**.
   F-31 stands unchanged.
3. **A regression detector** — if a future mint site writes `'streaming'` without an outcome, this
   catches it. This is the only live purpose, and it is **unobservable**: the count is logged and
   nothing reads it, and `outcome_source='reconciler'` is written into a column that (see §8) no
   `SELECT` anywhere in `app/` reads.

So the honest description is the one the code itself now gives: *currently VACUOUS, which is the
honest state.* I accept that framing. **What I do not accept is that it is scored as a P3 closure.**
Terminal path #9b — process death before any checkpoint — went from *stamped with a fabricated
cause* to *not recorded at all*. That is an improvement in honesty and a **regression in coverage**,
and P3's letter ("every terminal path writes an outcome") is now falsified by that path rather than
satisfied wrongly. The right verdict is that P3 is unmet for a better reason than last round.

One dead artifact of the removal: `stamped_user` is initialised at `instrument.py:516`, **never
assigned**, and still read at `:547` and `:551` and returned as `{"user": 0}`. Harmless; it means
the function's own return contract advertises a branch that no longer exists.

---

## 3. `resolve_expired_suspends` — the three questions I was asked

### 3.1 Is `expires_at <= now()` genuine evidence, or the removed branch in a new costume?

**Genuine evidence for the proposition it can support, and the label over-claims it.**

The evidence half is sound and I verified the chain rather than taking the docstring's word:
`load_suspended_run` (`db/suspended_runs.py:104-116`) filters `WHERE run_id = $1 AND owner_user_id =
$2 AND expires_at > now()`. So an expired run genuinely cannot be resumed through the normal path.
This is a **positive fact the row carries**, not an inference from a missing sibling row. It is not
the removed branch in a costume, and the distinction is the right one.

**The over-claim is in the value, not the predicate.** The evidence supports *"the input window
closed"*. What is written is `abandoned_by_user`, which asserts **user intent**. The conditions that
reach it:

| condition | reality | recorded |
|---|---|---|
| the user saw the card and never came back | abandoned | `abandoned_by_user` ✔ |
| the stream died after `save_suspended_run` (`stream:6987`) before the card reached the client | **the user was never asked** | `abandoned_by_user` ✘ |
| the client received it and the tab/session was closed by something other than a decision | lost | `abandoned_by_user` ✘ |
| a resume was attempted and refused on a `tool_call_id` mismatch (`stream:7653`) | a fault | `abandoned_by_user` ✘ |

And it lands on the one constant in this module whose **own definition records a measured defect**
(`instrument.py:71-80`): *"this value currently means 'the stream ended from the client side', which
is NOT what its name claims… do not report this as a user-intent metric."* The new sweep does not
create that fusion — it **enlarges** it. `abandoned_by_user` is now asserted at four sites
(`stream:6376`, `stream:6405`, `stream:7495`, `instrument:584`) spanning at least seven distinct
conditions, under a name the module says not to trust.

### 3.2 🔴 Can it mislabel a turn the user could still have answered? — **Not through the normal resume. But it writes a row that contradicts itself, and it inverts the provenance guarantee.**

**The narrow question: no.** `load_suspended_run`'s TTL filter means an expired card is genuinely
dead to the resume endpoint. I looked for a race and found none worth scoring: the resolver runs in
`lifespan` before `yield`, and even a mid-flight resume would be refused by the same predicate.

**But two things I found while checking are worse than the question asked.**

**(a) The resolver moves `outcome` and leaves `finish_reason` behind.** `instrument.py:577-583` sets
`outcome = 'abandoned_by_user'` while the `WHERE` clause pins `m.finish_reason = 'awaiting_input'`
and nothing updates it. The row that results says, in one column, *the turn correctly stopped to
ask* (a SUCCESS state, per this module's own §0.5) and, in the next, *the user walked away*.

That is **exactly** the defect `test_outcome_never_moves_without_finish_reason_moving_with_it`
exists to reject. Its docstring: *"Shipped once already: a statement set `finish_reason='interrupted'`
on an abandoned suspend and left `outcome='awaiting_input'`… A missing value is a hole; a
contradictory one answers confidently and wrongly, and nobody re-checks a column that has an
answer."* The new sweep ships the **mirror image of that exact statement**.

The gate cannot see it, and I measured why. It reads `_stream_src()` — `stream_service.py` only.

| mutation | should be | **is** |
|---|---|---|
| add a `finish_reason`-only UPDATE in `stream_service.py` | red | red ✔ |
| **the resolver in `instrument.py` also moves `finish_reason` (i.e. FIX the contradiction)** | — | **GREEN — the gate is indifferent** |
| **add the same violation in `voice_stream_service.py`** | red | **GREEN** |

The correct write is 14 lines away in the same repository: `_mark_suspend_abandoned`
(`stream:6402-6406`) moves **both** columns, with a comment explaining that moving one without the
other is what shipped broken. **A gate's scope is part of the gate** — the lesson recorded verbatim
in `test_the_token_budgeter_reports_its_drops_in_production`'s own docstring, about this same gate
class, in this same file. Seventh recurrence.

**(b) A path-recorded outcome ends up wearing the sweep's mark.** `load_suspended_run_any`
(`:141`) **ignores the TTL**, and `resume_stream_response:7663-7666` uses it: a user who clicks a
stale card after the sweep has run reaches `_mark_suspend_abandoned`. Because the sweep did **not**
move `finish_reason`, the check at `:6395` (`row["finish_reason"] == "awaiting_input"`) is still
true, so it fires and rewrites both columns — and **does not reset `outcome_source`, which stays
`'reconciler'`**. The result is a row a terminal path wrote, labelled as a startup sweep's guess.
That is the precise inverse of the guarantee the column was added for, asserted in the gate one
class up: *"a swept row must never be mistakable for one a terminal path recorded."* The inverse is
now reachable, and no gate covers either direction of it beyond the string `outcome_source =
'reconciler'` appearing in the source.

### 3.3 Does not deleting the run leave a growing table? — **Yes, and the DDL's own comment claims otherwise.**

Not deleting is the **right call** — deleting the evidence that justifies the outcome is what made
these rows unexplainable, and the gate that rejects it is now genuinely red-able (S11). But the
consequence was not followed through:

- `delete_suspended_run` is called at exactly two sites: `stream:8053` (a real resume) and
  `stream:7666` (a refused resume the user actually attempted). **A suspend the user simply ignores
  is never deleted by anything.**
- `sweep_expired_runs` (`db/suspended_runs.py:187`) still has **zero callers** — re-verified
  repo-wide for the third round running. `resolve_expired_suspends`' own docstring cites this as a
  known state and then declines to change it.
- The table's DDL comment (`migrate.py:388`) reads *"Rows are deleted on resume; an `expires_at`
  sweep reclaims abandoned ones."* **The second clause is false and has been for three rounds.**
- The only reclamation is `ON DELETE CASCADE` on `chat_sessions(session_id)` (`migrate.py:391`) —
  i.e. the table is bounded by session deletion, which nothing routine performs.
- And the sweep re-scans it at every boot: `EXISTS (SELECT 1 FROM chat_suspended_runs r WHERE
  r.message_id = m.message_id …)`. The table's two indexes are on `session_id` and `expires_at`
  (`migrate.py:411-414`) — **there is no index on `message_id`**, the column the correlated subquery
  joins on. The join is unindexed against a table that only grows.

The `outcome IS DISTINCT FROM $1` guard makes the sweep idempotent in effect, so this is a cost and
a correctness-of-claim problem, not a data-corruption one. **Deleting the evidence was correctly
refused; nothing was put in its place, and the schema still advertises a reclaimer that does not
run.**

### 3.4 And the sweep cannot reach voice at all — F-40

`voice_stream_service.py:641` writes `finish_reason='awaiting_input'` when `_voice_suspended` is
set (`:496`). **Voice never calls `save_suspended_run`** — `grep` for it returns one hit,
`stream_service.py:6987`. So a voice suspend produces an `awaiting_input` row with **no
`chat_suspended_runs` row to expire**, the `EXISTS` never matches, and the sweep can never touch it.

R9's terminal path #13b — *"`awaiting_input` on a turn nothing can resume"* — is the single path
this mechanism most obviously exists to close, and it is the one path structurally excluded from it.
It stays FAIL.

---

## 4. THE GATE AUDIT — 104 mutations, 75 caught, 29 blind

Every mutation asserted its needle and asserted the text changed. Baseline re-verified GREEN after
each batch's restore. 56 tests, 12→15 classes, 1,073 lines.

### 4.1 🟢 THE RECONCILER REWRITE — the five named mutations, all red. 12 of 19 overall.

The brief asked me to verify the rewrite catches five specific things. It catches all five.

| the brief's named mutation | how I built it | result |
|---|---|---|
| **a short-circuited body** | `return {...}` inserted before the `try:` | **red** ✔ `test_it_executes_and_reports_what_it_stamped` |
| **an inverted age bound** | `now() - interval` → `now() + interval` | **red** ✔ |
| **a flipped outcome** | `OUTCOME_CRASHED` → `OUTCOME_COMPLETED` at the bind | **red** ✔ |
| **an inverted predicate** | `outcome IS NULL` → `IS NOT NULL`; and `finish_reason = 'streaming'` → `!=` | **red** ✔ (both) |
| **a deleted caller, import retained** | delete `await reconcile_crashed_turns(pool)` from `main.py:95`, keep `:94` | **red** ✔ `test_main_awaits_it_rather_than_merely_importing_it` |

R9's headline finding **F-33 is WITHDRAWN in full** — the falsifier R9 stated was executed and
returned the builder's answer. That is the second consecutive round a finding has been retired by
the procedure it named. Two more beyond the brief's list also go red: deleting the age bound
entirely, and returning a hardcoded zero.

**Seven blind spots remain in the reconciler:**

| mutation | should be | **is** |
|---|---|---|
| the call wrapped in `if False:` | red | **GREEN** — the regex matches `await reconcile_crashed_turns(` inside dead code |
| **the call moved ABOVE `run_migrations`** | red | **GREEN — a coverage REGRESSION.** R9's substring gate asserted `main.index("run_migrations(pool)") < main.index("reconcile_crashed_turns")`. The rewrite dropped the ordering assertion, so reconciling a schema that does not exist yet is now unguarded |
| `older_than_minutes` default `5 → 0` | red | **GREEN** — the gate calls with the default and never asserts the value; `now() - interval '0 minutes'` still contains the needle |
| `AND role = 'assistant'` dropped | red | **GREEN** |
| `AND` → `OR` precedence break (claims every un-outcomed assistant row) | red | **GREEN** — every asserted substring survives a precedence change |
| **the user-row branch reintroduced as `role='user'`** (no spaces) | red | **GREEN** |
| **the user-row branch reintroduced as `role IN ('user')`** | red | **GREEN** |

The last two are the structural limit of the fix. `test_it_no_longer_guesses_at_user_rows` asserts
`"role = 'user'" not in inspect.getsource(...)` — a **negative substring** gate, defeated by
whitespace. And the executing gate only ever inspects `issued[0]`: a second statement appended after
the first is never examined at all, whatever it does. The exact-spacing reintroduction (R17) *is*
caught, so the gate is not worthless — it rejects a copy-paste revert and nothing else.

### 4.2 🟢 `resolve_expired_suspends` — 8 of 12

| mutation | should be | **is** |
|---|---|---|
| the caller deleted from `main.py` | red | red ✔ |
| short-circuited body (`return 0`) | red | red ✔ |
| `expires_at <= now()` → `> now()` | red | red ✔ |
| outcome flipped to `completed` | red | red ✔ |
| the `awaiting_input` scope dropped | red | red ✔ |
| `outcome_source` → `'path'` (impersonating a terminal path) | red | red ✔ |
| a hardcoded zero returned | red | red ✔ |
| **a `DELETE FROM chat_suspended_runs` added** | red | **red ✔ — the AST rewrite works** |
| the call wrapped in `if False:` | red | **GREEN** |
| **`EXISTS` → `NOT EXISTS`** | red | **GREEN** |
| the idempotency guard `outcome IS DISTINCT FROM $1` deleted | red | **GREEN** |
| the join column changed to `m.parent_message_id` (matches nothing) | red | **GREEN** |

**`EXISTS` → `NOT EXISTS` is the finding here.** It inverts the mechanism completely: instead of
sweeping turns whose window has closed, it sweeps **every `awaiting_input` turn whose card is still
live** — stamping `abandoned_by_user` on exactly the turns the user *can* still answer. The gate
asserts `"expires_at <= now()" in sql`, and `NOT EXISTS (… AND r.expires_at <= now())` contains that
substring verbatim. The gate's own docstring calls this predicate *"the only admissible evidence"*
and then checks for its presence rather than its polarity. Same shape as the age-bound blindness the
rewrite fixed, one clause further out.

The wrong-join mutation is the quiet one: `r.message_id = m.parent_message_id` produces a sweep that
silently matches nothing forever, reports `0`, and passes every gate — the *"a mechanism with no
effect reads as coverage"* failure this whole class of gate was written to reject.

### 4.3 🔴 THE INTENT GATE — behaviourally gated, and a production no-op. F-37.

Six mutations of `filter_intent_gated_setup_tools` itself, **all six red**: a dead `dict(...)`
literal, a disabled registration, registering-without-dropping, over-registering the rail-exempted
tool, an emptied reason, a wrong stage name. The function is genuinely well gated. **The function is
not the problem.**

`record_surface_withheld` is a no-op when the ContextVar sink is `None` (`instrument.py:263-265`).
Measured positions:

```
fresh turn   intent gate @L5940   sink armed @L6013   -> GATE RUNS 73 LINES FIRST
resume       intent gate @L8001   sink armed @L8016   -> GATE RUNS 15 LINES FIRST
```

I confirmed there is no earlier arming: the only two `instrument.surface_withheld.set([])` sites in
the package are lines **6013 and 8016**, and there are **zero** armings inside
`resume_stream_response` (starts `:7628`) before its gate. Each request runs in its own asyncio task
with a fresh context copy, so the ContextVar holds its `default=None` at both call sites. I ran the
function under exactly that condition:

```
ContextVar at gate time (production, line 5940): None
gate dropped: 5 tools
sink after gate (production): None
```

**Five withholdings, recorded nowhere.**

And it is lost **twice over**: even if something had armed a sink earlier, line 6013 does
`set([])` — a **brand-new empty list** — which discards anything registered before it.
`_emit_chat_turn` then adopts *that* list at `:6506`. The records are unrecoverable by construction.

**The gate stages the precondition production fails to supply.** `test_the_gate_registers_what_it_drops`
does `token = _inst.surface_withheld.set(sink)` and then calls the function. Its sibling nine classes
above, `test_tools_outside_the_hot_domains_register_as_withheld`, carries this warning in its own
body (`:707-710`):

> *"DO NOT PASS withheld_sink. Neither production call site does… a gate that passes it explicitly
> stages the exact precondition production fails to supply, and deleting the fallback leaves it
> GREEN. That is the fifth recurrence of this one defect, and it is written as a warning in the
> sibling gate's docstring nine lines above."*

**Sixth recurrence, written the same way, in the same file, in the same pass.** And the gate that
*would* have caught it already exists: `test_a_surface_narrowing_registers_without_anyone_wiring_it`
asserts `"surface_withheld.set(" in src[idx-1200:idx]` for two named call sites. I applied that
identical check to the two intent-gate call sites:

```
'surface_withheld.set(' within 1200 chars before discovery_catalog = filter_i...: False
'surface_withheld.set(' within 1200 chars before resume_discovery_catalog = f...: False
```

**The repository's own gate, pointed at the new call sites, goes red today.** It was not pointed at
them.

### 4.4 Carried blind spots — R9's, re-measured against the real suite. All still blind.

| gate | mutation | **is** |
|---|---|---|
| E · assistant-INSERT outcome | voice re-pins the literal `'stop'` (**F-24 reintroduced verbatim**) | **GREEN** |
| E | voice outcome reverts to the `OUTCOME_COMPLETED` constant | **GREEN** |
| E | voice binds `outcome = None` | **GREEN** |
| E | voice discards the captured `finish_reason` again | **GREEN** |
| E | proactive `finish_reason` reverts to the literal `'stop'` (**F-28 reintroduced verbatim**) | **GREEN** |
| C · F-19 clean finish | outcome reverts to the `OUTCOME_COMPLETED` constant | **GREEN** |
| C | the `_loop_finish_reason` capture deleted | **GREEN** |
| P1 · catalog_miss | becomes a dead `dict(...)` literal | **GREEN** |
| P1 · permission_tier | becomes a dead `dict(...)` literal | **GREEN** |
| P1 · catalog_miss | **the record moved BELOW its own `continue`** — the defect the gate names | **GREEN** |
| F · schema | `advertised_tools` → `advertised_tools_v2` | **GREEN** (substring prefix) |
| F · schema | `outcome_source` → `outcome_source_x` | **GREEN** (substring prefix) |
| F · schema | `outcome_source` vocabulary widened with a third value | **GREEN** |
| — | `'error'` no longer maps to `failed` | **GREEN — no gate** |
| — | the `latency_unmeasured` reason dropped | **GREEN — no gate** |

**Both of R9's credited closures remain revertible with one edit each, suite green.** F-24 and F-28
were the two genuine fixes of round 9; nothing protects either. Deleting the `outcome_source` DDL
*outright* **is** caught — the blindness is only to a prefix-preserving rename, which is the carried
R8 finding in a third column.

### 4.5 What is strong — and it is most of the suite

Stated so the audit is not selective. **75 of 104 mutations were caught**, and the strength is
concentrated exactly where the claim's arithmetic lives:

| area | mutations | caught |
|---|---|---|
| `AdvertisedToolsRecorder` (0.1/0.2 core) | 8 | **8** — overwrite-instead-of-append, unsorted names, off-by-one pass stamp, reconciliation removed, turn-wide dedupe restored, args dropped from the dedupe key, `count` dropped, `[]`-for-`None` |
| `source` / `declaration` / `runtime_variant` (0.3/0.7) | 8 | **8** — including the chokepoint defaulting to `tool`, the `source_inferred` mark removed, and the meta/breaker split inverted |
| `outcome_for_finish_reason` vocabulary | 7 | **7** — every F-19 reintroduction, the fail-safe reading as success, `interrupted` retroactively relabelled |
| budgeter wiring (0.2) | 4 | **4** — including reintroducing a call to the discarding variant, in either file |
| orphan stamp (P3) | 3 | **3** — parent-vs-session anchor, `RETURNING` dropped, a literal outcome asserted |
| `domain_not_selected` (P1) | 3 | **3** — R9's F-23 withdrawal holds under the real suite |
| schema existence | 2 | **2** — deleting `advertised_tools` or `withheld_tools` DDL |
| assistant-INSERT / dispatch stamping | 2 | **2** |

The recorder and the classifier are the two things CP-0 exists to build, and both are genuinely
protected. The failures are in the **wiring** and in the **new terminal-path machinery**, which is
where they have been for ten rounds.

---

## 5. Findings

### F-37 · 🔴 The intent gate — P1's seventh frame — registers nothing in production
§4.3. `tool_discovery.py:495-503` vs `stream_service.py:5940` / `:6013` and `:8001` / `:8016`.
Measured: the ContextVar is `None` at both call sites; the function drops 5 tools and the sink is
`None` afterwards; and the arming at `:6013` installs a **fresh list**, so an earlier record would be
discarded even if one existed. The gate arms the sink itself. **Sixth recurrence of the defect its
own sibling gate's docstring names as the fifth.**

### F-38 · 🔴 `resolve_expired_suspends` writes a row that contradicts itself, into a gate that cannot see its file
§3.2(a). `instrument.py:577-583`. `outcome` moves to `abandoned_by_user`; `finish_reason` stays
`awaiting_input` — a SUCCESS state. This is the exact defect
`test_outcome_never_moves_without_finish_reason_moving_with_it` rejects, and that gate reads only
`stream_service.py`. Measured three ways (§3.2 table). The correct write —
`_mark_suspend_abandoned` at `stream:6402-6406` — moves both columns and explains why.

### F-39 · A terminal path's own write ends up marked `outcome_source='reconciler'`
§3.2(b). `stream:7663-7666` → `stream:6395-6406`. Reachable with no race: sweep at boot, user clicks
the stale card the next day. Because F-38 left `finish_reason='awaiting_input'`, the
`_mark_suspend_abandoned` guard still fires and rewrites both columns without resetting
`outcome_source`. The inverse of the guarantee the column exists to give.

### F-40 · The sweep is structurally unreachable for every voice suspend
§3.4. `voice_stream_service.py:496`/`:641` vs `stream_service.py:6987` (the only
`save_suspended_run` caller). No run row ⇒ the `EXISTS` never matches. R9's terminal path #13b — the
path this mechanism most obviously exists to close — is excluded by construction.

### F-41 · `chat_suspended_runs` has no reclaimer, and the DDL says it does
§3.3. `migrate.py:388` claims *"an `expires_at` sweep reclaims abandoned ones"*; `sweep_expired_runs`
has zero callers for the third round running. An ignored suspend is never deleted by anything but
session cascade. The sweep's correlated `EXISTS` joins on `message_id`, which is **unindexed**
(`migrate.py:411-414`).

### F-42 · `outcome_source = 'path'` has zero producers
§8. `grep` returns two writers of `outcome_source` package-wide, both `'reconciler'`
(`instrument.py:520`, `:578`). Every terminal path leaves it NULL. The gate asserts
`"'path', 'reconciler'" in ddl` — *"the vocabulary must be closed"* — over a value nothing writes.
NULL is therefore overloaded between *"a path recorded this"* and *"a pre-CP-0 row"*; recoverable via
`outcome IS NOT NULL`, so this is bounded, not fatal. **Corroborated from outside this review**: the
working-tree drift that landed at the end of my audit adds `outcome_source = 'path'` at both
assistant INSERTs and records the live number — *64.8% of outcomed rows read as path-written when
they were not*. Not credited; it is not in the artifact I was handed.

### F-43 · `abandoned_by_user` is asserted at a fourth site — mandate 3's seventh asserted value
§6.

### F-44 · The reconciler's ordering guarantee was lost in the rewrite
§4.1. R9's substring gate asserted the call runs after `run_migrations`; the executing rewrite
dropped that assertion. Moving the call above `run_migrations` is now green.

### F-33 · **WITHDRAWN** — the caller gate matches the `await`, not the name
§4.1. R9's stated falsifier executed and returned the builder's answer.

### F-29, F-32 · **RESOLVED by removal** — the user-row branch and its `branch_id` blindness are gone
§2. Correctly, and for a reason better than the branch itself had.

### Carried, unchanged
F-31 (the remaining branch is vacuous — re-verified: one `'streaming'` writer, and it stamps
`crashed`); F-30 (`stream:7495`); F-26 (assembly stages register pass-1-only); F-25 (two counting
conventions in one array); F-20 (voice's false comment at `:604-608`, **fifth round quoted**); F-11
(`RUNTIME_AGENTRUNTIME` has no producer, `tool_call_source()` zero callers); F-1/F-9; voice's INSERT
still carries **no `withheld_tools` column**; `budget_rail_tools`' drops still go to
`logger.warning` (`tool_surface.py:551`) — an eighth unregistered stage; `latency_ms` still measured
at a minority of mint sites with no gate; and **every CP-0 recording is still write-only**.

---

## 6. Mandate 3 — the search for asserted values. The seventh.

**How I searched.** Regex over every `.py` in `app/` for `INSERT INTO chat_messages` and `UPDATE
chat_messages`, comment-stripped, filtered to statements naming `outcome`; then a second pass for
every `OUTCOME_*` constant appearing in an argument position outside `instrument.py`. Eight
statements, nine constant bindings. For each: *how many distinct terminal conditions reach this
binding, and is the value a measurement of one of them?*

| site | value | conditions | ruling |
|---|---|---|---|
| `internal.py:937` | `OUTCOME_COMPLETED` | 1 (the message was delivered) | fine — reasoned explicitly at `:938-945` |
| `instrument.py:525` | `OUTCOME_CRASHED` | 1, evidence-backed | fine, but vacuous (F-31) |
| **`instrument.py:584`** | **`OUTCOME_ABANDONED_BY_USER`** | **≥3 (§3.1)** | 🔴 **THE SEVENTH** |
| `stream:6376` | `OUTCOME_ABANDONED_BY_USER` | 3 (incl. an *errored* resume) | carried, bounded |
| `stream:6405` | `OUTCOME_ABANDONED_BY_USER` + literal `finish_reason='interrupted'` | 3 (expired / refused / id-mismatch) | carried; note the pair is internally inconsistent by this module's own shim — `outcome_for_finish_reason('interrupted')` returns `interrupted`, not `abandoned_by_user` |
| `stream:6887` | `OUTCOME_CRASHED` | 1, pessimistic by design | correct, and it is what makes F-31 vacuous |
| `stream:7043` | `OUTCOME_AWAITING_INPUT` | 1 | fine |
| `stream:7495` | `OUTCOME_ABANDONED_BY_USER` | 2 (F-30) | carried |
| `stream:7536` | `OUTCOME_FAILED` | 1 | fine |

**The seventh asserted value is `instrument.py:584`, and its significance is cumulative rather than
local.** `abandoned_by_user` is now bound at four sites covering at least seven conditions — user
cancel, dead transport, expired window, never-delivered ask, refused resume, id mismatch, ignored
card — under a name whose own definition, 500 lines above, records the measurement showing it
already fuses two of them and instructs readers not to treat it as a user-intent metric. The sweep
did not create the fusion; it is the first change in three rounds to **widen** it.

---

## 7. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | writes? | outcome | R10 |
|---|---|---|---|---|---|
| 1 | clean finish, `stop` | `stream:7254` | yes | `completed` | pass |
| 1b–1d | clean finish, `length`/`tool_calls`/`content_filter`/unknown | `:7327` ← `:6918` | yes | derived, agreeing | pass — **ungated (F1/F2 green)** |
| 2 | frontend-tool suspend | `:7032-7043` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7480-7495` | yes | ⚠️ `abandoned_by_user` on a dead transport | **FAIL — F-30 carried** |
| 4 | mid-stream exception | `:7528-7536` | yes | `failed` | pass |
| 5/6 | abandoned suspend (± provisional row) | `:6376`/`:6405` | yes | `abandoned_by_user` | pass (bounded, §6) |
| 7 | empty terminal turn | `:6205-6259` | user row stamped | derived | pass — gated 3/3 |
| 8 | mid-turn checkpoint (crash surrogate) | `:6872-6887` | yes | `crashed`, pessimistic | pass |
| **9a** | process death AFTER a checkpoint | reconciler assistant branch | n/a | — | **VACUOUS — F-31 carried.** Already stamped by #8 |
| **9b** | **process death BEFORE any checkpoint** | — | **no** | ❌ **none** | **FAIL — newly uncovered.** The branch that stamped it is gone. Honest, and unrecorded (§2) |
| 9c | process death during edit-and-regenerate | — | no | ❌ none | **moot** — F-32 dissolved with the branch |
| 10 | tool-loop pass exhaustion | `:4759` → `"stop"` at `:4765` | yes | ⚠️ `completed` | FAIL — unchanged, documented unreachable |
| 11 | expired / mismatched resume | → #6 | yes | ✅ | pass |
| 12/12b | voice, clean finish / `length` / `content_filter` | `voice:593-643` | yes | derived | pass — **ungated (V1–V4 all green)** |
| 13a | **voice turn, exception** | `voice:792-794` | **no** | ❌ none | **FAIL — unchanged** |
| 13b | **voice suspend-abort** | `voice:496` → `:641` | yes | ⚠️ `awaiting_input` forever | **FAIL — and structurally unreachable by the new sweep (F-40)** |
| 14/14b | proactive check-in, generated / static fallback | `internal:927-945` | yes | `completed`, distinguishable | pass — **ungated (P1x green)** |
| **15** | **suspend never resumed, then expired** | `instrument.py:556-595` | **yes** | ⚠️ `abandoned_by_user`, **row self-contradictory** | **PARTIAL — CLOSED for the stream path, was FAIL. F-38/F-39/F-41** |
| 16/17 | spend-gate refusal · turn-level timeout | searched — neither exists in this service | n/a | n/a | — |

**Five paths fail (#3, #9b, #10, #13a, #13b); one genuinely closed (#15, with three defects);
one vacuity (#9a); one dissolved (#9c).**

**Handoff to V-LIVE, executable:**

```sql
-- F-37: does the seventh frame record ANYTHING? Source says no.
SELECT count(*) FROM chat_messages
 WHERE withheld_tools @> '[{"stage":"intent_gate"}]'::jsonb;            -- predict 0
-- F-38: the self-contradictory row the sweep writes.
SELECT count(*) FROM chat_messages
 WHERE outcome = 'abandoned_by_user' AND finish_reason = 'awaiting_input';
-- F-42: does 'path' have any producer at all?
SELECT outcome_source, count(*) FROM chat_messages GROUP BY 1;          -- predict no 'path'
-- F-31: does the surviving branch ever stamp anything after the first boot?
SELECT count(*) FROM chat_messages
 WHERE role='assistant' AND finish_reason='streaming' AND outcome IS NULL;  -- predict 0
-- F-41: the table nothing reclaims.
SELECT count(*) FILTER (WHERE expires_at <= now()) AS expired, count(*) AS total
  FROM chat_suspended_runs;
```

---

## 8. Vacuity (NV) — can each new check fire?

| check | realistic firing input? |
|---|---|
| **`intent_gate` registration** | **NO in production (F-37)** — fires only when a test arms the sink. Yes in the gate |
| **reconciler, assistant branch** | **NO — F-31 carried.** One `'streaming'` writer, and it stamps `crashed` |
| reconciler, user branch | **N/A — removed** |
| **`resolve_expired_suspends`, stream suspends** | **Yes** — 5 of 8 measured rows, and the evidence is real |
| **`resolve_expired_suspends`, voice suspends** | **NO — F-40.** No run row can exist |
| **`outcome_source = 'path'`** | **NO — F-42.** Zero producers |
| `outcome_source = 'reconciler'` | Yes, on the first boot's backlog and on every expired suspend |
| `catalog_miss` / `permission_tier` | Yes — code correct, guards are spell-checks (C1–C3 green) |
| `domain_not_selected` ContextVar fallback | **Yes** — the only branch production uses, and gated (3/3) |
| `outcome_for_finish_reason` `case _` | Yes |
| `runtime_variant = 'agentruntime'` | **No** — no producer (F-11) |
| `tool_call_source()` · `dedupe_recorded_calls` | **No** — zero callers; the latter by design |
| `latency_unmeasured` | Yes, at most mint sites — and still **no gate** |

**And the standing vacuity, tenth round: every CP-0 recording is write-only.** `grep` for `SELECT`
lines naming `advertised_tools`, `withheld_tools`, `outcome`, `outcome_source` or `runtime_variant`
across `app/` returns **nothing at all**. This is why F-38 could ship: a row whose two columns
contradict each other is contradicted by no consumer, because there is no consumer.

---

## 9. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:639` binds the literal `None`; voice receives the `advertised` chunk and swallows it. Assembly-stage per-pass registration stops after pass 1 (F-26). Not bypassed by overwrite — `record_pass` appends, re-verified by mutation (overwrite ⇒ 3 gates red) |
| **0.2** | **F-37 — the newest stage registers nowhere.** Voice's INSERT has no `withheld_tools` column (`voice:603-608`); `budget_rail_tools`' drops go to `logger.warning` (`tool_surface.py:551`); the `{"tool": "*"}` pseudo-entry (`stream:2349`); two counting conventions in one array (F-25) |
| **0.3** | `source` — **no bypass found.** Assigned in exactly two places package-wide; 8/8 mutations red. `latency_ms`: measured at a minority of mint sites, **no gate** (deleting `latency_unmeasured` is green); the voice suspend's own pending call unrecorded; nested subagent calls reach no INSERT |
| **0.4** | Five paths. Write **no row**: `voice:792` (exception), and process death before any checkpoint (#9b, newly uncovered). Write a **fabricated cause**: `stream:7495` (F-30), `:4765`, `instrument:584` (F-43). Write a **self-contradictory** row: `instrument:577-583` (F-38). Write a **stale** value forever: every voice suspend (F-40). Full enumeration §7 |
| **0.5** | No bypass at the SHA. `git ls-tree 874b3524e` confirms all three baseline files + `run_arms.py`. The tree was clean for the whole audit and went dirty at the end — `baseline-metrics.sql` modified, third consecutive round. F-9 remains a docstring overstatement |
| **0.6** | No bypass. `binding_format.py` + both result files tracked at the SHA |
| **0.7** | No bypass of the literal claim; all chokepoints route through `ensure_tool_call_instrumented`, re-verified by 4 red mutations. Bounded by F-11 |

---

## 10. What changed in the failure, and my falsifier

**The gate class finally moved, and it moved in the right direction.** For six rounds the pattern
was: a gate counts substrings, and the defect it names walks past it. This round the four reconciler
gates were rewritten to **call the function**, and all five mutations the brief named go red. The
`DELETE`-matching-its-own-docstring gate was fixed by parsing the AST rather than by narrowing a
window. R9's F-33 is withdrawn by its own stated procedure. That is real, and it is the second
consecutive round in which a finding died the way a finding should die.

**And the defect moved into the wiring, which is where it has always gone next.** `intent_gate` is a
correctly-written function, correctly gated as a function, called **73 lines and 15 lines before the
sink that would have caught its output**, in two places — and the record is destroyed a second time
by the `set([])` that arms that sink. The repository already contains the gate that catches this; it
asserts arming-before-narrowing for two named call sites and was not extended to the two new ones. I
ran that same assertion against the new sites and it goes **red today**.

**The through-line across all three deliverables is scope.** The reconciler gates were fixed by
making them *execute*, and the executing gate inspects `issued[0]` only, so a second statement is
invisible. The lockstep gate rejects exactly the contradiction `resolve_expired_suspends` writes, and
reads only `stream_service.py`. The sink-arming gate covers two call sites and two new ones appeared.
Every one of these gates is correct about the property it names and wrong about the *extent* of the
thing it is pointed at — which is the lesson already written, verbatim, in this file's own oldest
docstring: **"A gate's scope is part of the gate."**

**My falsifier, stated so a later round can execute it as R8's and R9's were:**

1. **F-37.** Run one non-world-setup discovery turn against this build and execute
   `SELECT count(*) FROM chat_messages WHERE withheld_tools @> '[{"stage":"intent_gate"}]'::jsonb`.
   **If it is non-zero, F-37 is withdrawn in full and I have misread the ContextVar's lifetime.**
   If it is zero — which is what I measured by running the function under production's actual
   ContextVar state, and what the two positional comparisons predict — then P1's seventh frame is a
   mechanism with a green gate and no output.
2. **F-38.** Execute `SELECT count(*) FROM chat_messages WHERE outcome='abandoned_by_user' AND
   finish_reason='awaiting_input'` after a boot that sweeps anything. **If it is zero, F-38 is
   withdrawn** and the sweep moves both columns after all. If it is non-zero, the row the sweep
   writes disagrees with itself, and the gate written to reject that disagreement never looked in
   `instrument.py`. *(Already answered by the drift, at 84.6% — 33 of 39. F-38 stands, and the drift
   fixes the reader rather than the row.)*
3. **F-42.** Execute `SELECT outcome_source, count(*) FROM chat_messages GROUP BY 1` **against a
   database that has served traffic on the artifact at `874b3524e`**. If any row reads `'path'`,
   F-42 is withdrawn and I have missed a writer. *(Answered by the drift at 64.8%, in the direction
   ruled; not credited, because the producer is not in the graded artifact.)*

**And one thing about my own work.** I set out to grade a rewrite and spent the first half of the
audit confirming it works — 75 of 104 mutations caught, against 6 of 30 last round. The failure I
report is not in what I was asked to check. It is in the one item handed to me that *nobody asked me
to check behaviourally*: `intent_gate` was described in the brief as "registration added", and I
would have accepted that from the function's own source, which is correct, if I had not gone looking
for the sink. The gate I used to find it is the repository's own, four classes up the same file.
