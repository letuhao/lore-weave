# CP-0 · V-CODE — verdict, ROUND 7

Artifact frozen at `af85ce0a8d147cf6dae4ecb455908dc3681f0e07`. **`git status --porcelain` is empty** —
the working tree is clean, so the committed state and the graded state are the same state. The brief
is unmodified: `git log aa9ef87c4..af85ce0a8 -- …/CP-0-V-CODE-PROMPT.md` returns no commits.

Source-only review. Nothing in the product was run. No tracked file was modified. No commit message
or builder rationale prose was read. Every finding below was re-derived from source at this SHA.

**Method note.** The gate audit replicates all six gates verbatim over **in-memory** copies of the
real sources; `mutate()` asserts both that the needle exists and that the string actually changed,
and the harness reproduces a fully GREEN baseline on the unmutated tree before any mutation. That
assertion earned its keep twice this round: my first Gate-F probe *renamed* `advertised_tools` →
`advertised_tools_x`, which the gate's substring test still matched — I recorded that as a harness
artefact, re-ran the mutation as an outright line deletion, and Gate F went red as R6 said it would.
**One row of R6's scorecard would have been wrong if I had not re-run it.** For behavioural rulings I
imported the real `app.services.instrument` and `app.services.tool_surface` and called the real
functions; "measured" below is a mechanical result.

**38 mutations. 23 blind spots. 1 false positive. 1 gate red on the UNMUTATED tree.**

---

## 1. Verdict

**Overall: `FAIL`.**

| item | claim | R4 | R5 | R6 | **R7** |
|---|---|---|---|---|---|
| 0.1 | `advertised_tools` jsonb, one entry per model pass | FAIL | FAIL | FAIL | **FAIL** — unchanged; voice still discards the `advertised` chunks it receives and binds NULL |
| 0.2 | `withheld_tools`; the budget function returns what it dropped | FAIL | FAIL | FAIL | **FAIL** — no code changed; the false invariant was corrected in **one of the three places it is stated**, and the fan-out it describes is unchanged (measured 1→1 … 10→10) |
| 0.3 | every `tool_calls[]` entry carries `source` + `latency_ms` | FAIL | FAIL | FAIL | **FAIL — but genuinely improved.** Voice records tool calls for the first time. The call that *causes* the voice suspend is still not among them, and no gate protects any of it (4/4 mutations green) |
| 0.4 | every terminal path writes an outcome | FAIL | FAIL | FAIL | **FAIL — and one live population moved in the wrong direction.** F-19 |
| 0.5 | frozen baseline in `contracts/`, A–E arm scripts committed | PASS | PASS | PASS | **PASS** |
| 0.6 | binding-format measurement scripted **and its output committed** | FAIL | PASS | PASS | **PASS** |
| 0.7 | `runtime_variant` + declaration identity on every recorded call | PASS | PASS | PASS | **PASS**, and strengthened — one R6 bound (voice calls reach no INSERT) is removed |

**What landed, credited before the findings.**

1. **Voice records tool calls at all.** `voice_stream_service.py:505` appends every `tool_call`
   chunk through `instrument.ensure_tool_call_instrumented`, and `:598/:634` persist them. R6's
   "voice-dispatched tools carry `source`, `latency_ms`, `declaration` and `runtime_variant` only
   vacuously" is now false: measured on realistic voice chunks, a `conversation_search` result
   classifies `meta`, a refused write classifies `breaker` with `source_inferred`, and a pre-stamped
   dispatch keeps `source='tool'` with its latency. A whole pipeline that was invisible to CP-0.3 is
   no longer invisible. That is the real closure of an R6 finding.
2. **F-15's attribution correction is accurate on every property I could check.** The corrected
   comment (`instrument.py:358-370`) says the 145 are *pass 3 on 2-pass turns, at stage
   `token_budget`*. `CP-0-v-metric-round6.md:389-390` supports the pass claim (47 + 98 = 145,
   `pass 3`, 2-pass turns); `CP-0-v-metric-round7.md:397-398` supports the stage claim
   (`token_budget` on both). The "unreachable in production" claim is also true and I verified it
   independently: `record_withheld` has exactly two call sites (`stream_service.py:6829`, `:6833`),
   both inside `if _adv_ev is not None:` and both after `record_pass` at `:6821`; `grep -rn` over
   `app/` finds no third. **This correction is right, and it withdraws a claim rather than improving
   it.**
3. **F-14's outcome is no longer a constant.** `voice_stream_service.py:615-616` and `:633` both
   derive from `_voice_suspended`. The parameter mapping is correct (15 columns, 15 values, `$12`
   lands on `finish_reason` and `$9` on `outcome` — I recounted).

**And the pattern held for a seventh round, in a new medium.** R6's summary was that the class had
moved from column *values* into the *justifications*. In R7 it has moved again — into the **derived
expression itself**. The F-17 fix replaces a literal with a function call, and the function call is
wrong on a population nobody looked at:

```
finish_reason='stop'            -> outcome='completed'      <- the breaker exit, unchanged
finish_reason='length'          -> outcome='interrupted'    <- was 'completed' before this round
finish_reason='content_filter'  -> outcome='interrupted'
finish_reason='tool_calls'      -> outcome='interrupted'
finish_reason=<any other word>  -> outcome='interrupted'
```

`interrupted` is the value `migrate.py:352` calls *"RETAINED AND DEPRECATED … a finding about US …
**The metric to drive to zero**"*. The change routes a live class of clean turns into it, on a write
site whose own SQL pins `finish_reason = 'stop'` in the same statement.

---

## 2. The falsifier

Stated before the findings. What I looked for that would have made this PASS or FAIL, and what each
search returned.

1. **Does the breaker exit report something other than `stop`?** If it did, F-17's fix would be a
   real distinction and 0.4's finding #10 would close. *It does not.* `stream_service.py:4742-4743`
   yields the **string literal** `"stop"`. §3.1. Search: read both loop exits (`break` at `:1994`,
   `break` at `:4738`), the terminal yields at `:2777` and `:4742`, and traced `finish_reason`'s
   scope (declared per-pass at `:2375`).
2. **Does the derived expression change any value it should not?** *Yes — measured.* §3.1. Search:
   called `instrument.outcome_for_finish_reason` on the canonical gateway enum
   (`anthropic_streamer.go:266`: `stop|length|content_filter|tool_calls|error`) plus the passthrough
   cases (`streamer.go:373-374` forwards upstream `finish_reason` verbatim, unnormalised).
3. **Are ALL voice tool calls captured, or only one branch?** *All chunk-borne calls, both branches
   — and one call that is not chunk-borne is missed.* §3.2. Search: enumerated all 31
   `yield {"tool_call":` sites in `_stream_with_tools`, traced voice's consumer ordering
   (suspend at `:485` precedes tool_call at `:497`), and compared against what the text path records
   at the same suspend (`stream_service.py:6943-6962`).
4. **Are the two corrected comments accurate, or merely different?** *F-15 accurate. F-16 accurate
   where written, and left standing in two other places.* §3.3.
5. **Did the four constant-bound INSERT sites close?** *Two of four closed, one converted into a
   derived-but-wrong expression, one untouched.* §5.
6. **A gate green over a defect in its own stated subject.** *Found — four now, and this round
   created the fourth.* §4. My extended Gate C goes **red on the current, unmutated tree**.
7. **`advertised_tools` overwritten rather than appended.** *Not found, a seventh time.*
   `record_pass` appends (`instrument.py:303-311`); both upserts `COALESCE` (`:6229-6230`,
   `:7227-7228`).
8. **`source` defaulting to `tool`.** *Not found.* Unchanged from R6.
9. **DDL appended to an already-applied ledger step.** *Not applicable, re-checked.* `migrate.py` is
   one DDL string run in full on every boot; all four CP-0 statements are `ADD COLUMN IF NOT EXISTS`
   and Gate F goes red when any of the three added ones is deleted (measured — see the method note).

Two things I **cannot determine from source**, unchanged across seven rounds:

- **Whether the recorded values are right.** `grep -rn advertised_tools\|withheld_tools\|runtime_variant`
  across `services/`, `frontend/src` and `contracts/` returns hits **only** in the five chat-service
  files that write them and their tests. `chat_messages.outcome` has no reader anywhere
  (`models.py:549`'s `outcome` is the frontend-tool result field, a different thing).
  `latency_unmeasured` has no reader. This is the brief's hunting ground #3 and it is the standing
  reason a wrong derived value can ship as easily as a wrong constant did.
- **How often `finish_reason != 'stop'` occurs live.** That is a database question and I did not run
  one. What I can state from source: the path is live, unguarded, and reachable on the default cloud
  provider (Anthropic always receives `max_tokens`, per
  `max_tokens_policy_test.go:5-6` — *"Anthropic is the documented exception … we keep the 8192
  default"* — and `max_tokens` maps to `length`). **This is the round's handoff to V-METRIC.**

---

## 3. Findings on the three claimed changes

### 3.1 F-17 · THE HONESTY CHECK — the claimed limit is real, and the change does something else the comment does not claim

The comment at `stream_service.py:7244-7250` states the limit honestly and refuses to settle it:
*"if the breaker exit reports `stop` like any other completion, the recorded outcome is unchanged …
Whether the breaker produces one is a live question for a verifier."* Settled:

**The breaker exit reports the literal string `"stop"`.**

```python
# stream_service.py:1992-1995      the loop exit
while True:
    iteration += 1
    if iteration >= max_total_passes:
        break
...
# stream_service.py:4740-4743      what that break falls through to
# Write budget exhausted. The final pass is forced
# tool-free (D7) so this is unreachable in practice — defensive.
yield {"content": "", "reasoning_content": "",
       "finish_reason": "stop",
```

`outcome_for_finish_reason("stop")` returns `OUTCOME_COMPLETED` (measured). So on the path F-17
names, **the recorded value is byte-identical to what the constant produced. The fix removes a
literal and distinguishes nothing.** The repeated-failure breaker proper (`:2192`) does not terminate
the loop at all — it de-advertises the tool and the turn ends through the normal final pass, also
`stop`. Both readings of "breaker exit" land on `completed`.

**And the same edit changes a population the comment does not mention.** `_loop_finish_reason` is
whatever the *final pass's* `DoneEvent` reported (`:2375` declares it per-pass, `:2445` assigns it,
`:2778` forwards `finish_reason or "stop"`). Measured against the real function:

| final pass reports | recorded `outcome` | before this round |
|---|---|---|
| `stop` | `completed` | `completed` |
| **`length`** (max_tokens — Anthropic default 8192, always sent) | **`interrupted`** | `completed` |
| `content_filter` | `interrupted` | `completed` |
| `tool_calls` | `interrupted` | `completed` |
| any upstream word forwarded verbatim by `streamer.go:373-374` | `interrupted` | `completed` |

`interrupted` is the deprecated catch-all: `instrument.py:91-95` — *"Anything still landing here
after CP-0 is a path we failed to classify — a finding about us. **The number to drive to zero.**"*
`outcome_for_finish_reason`'s own docstring says it is *"a migration shim, not the intended path: the
write sites set `outcome` directly."* The clean finish is now the one write site that routes through
the shim, and it inherits the shim's fail-safe `case _` — which is the correct default for reading
**historical** rows and the wrong default for classifying a **live** turn whose reason is known.

**Worse, the same statement pins the neighbouring column.** `:7207` binds `finish_reason` as the SQL
literal `'stop'`, and `:7220` re-pins it in the `DO UPDATE SET`. So a truncated turn now writes:

```
finish_reason = 'stop'        (asserted)
outcome       = 'interrupted' (derived)
```

That is the exact contradiction Gate C exists to prevent — *"a column that disagrees with its
neighbour … a contradictory one answers confidently and wrongly, and nobody re-checks a column that
has an answer"* — and Gate C cannot see it, because it scans `UPDATE chat_messages SET` and this is
an `ON CONFLICT … DO UPDATE SET`. §4.

**Ruling.** The claimed limit is honest and correct: the fix distinguishes nothing on the breaker
exit and only removes a literal there. It is not value-neutral elsewhere: it silently reclassifies
every non-`stop` clean finish into the deprecated bucket while leaving `finish_reason` asserting the
opposite. **F-19.**

### 3.2 THE VOICE COMPLETENESS CHECK — every chunk-borne call is captured on both branches; the one call that explains the suspend is not

*Are all voice tool calls captured, or only those on one branch?* **All chunk-borne calls, on both
branches.** The append at `:505` sits in the `tool_call` handler, which every one of the 31
`yield {"tool_call": …}` sites in `_stream_with_tools` reaches; voice consumes the same generator the
text path does, so the captured population is identical to `tool_calls_history`.

*Does the suspend/break path lose them?* **No.** `_voice_suspended = True; break` at `:495-496`
exits the chunk loop and falls through to the flush at `:552` and the INSERT at `:593`; the list is
function-scoped (`:436`) and is bound at `:634`. Calls completed before the suspend are persisted. I
traced this rather than assuming it, because the same `break` is what made F-14 wrong.

**What IS lost, and it is the call that explains the turn:** the *pending* tool call — the one whose
confirmation voice cannot render — never arrives as a `tool_call` chunk. It arrives inside the
suspend payload (`stream_service.py:4707-4712`, `pending_tool_call`) and voice's suspend branch reads
only `input_tokens`/`output_tokens` from it. **The text path records exactly this call**, 100 lines
away in the same codebase:

```python
# stream_service.py:6943-6950
_pending_record = {"tool": pending.get("name"), "ok": False, "pending": True,
                   "runId": run_id, "toolCallId": pending.get("id"), "args": pending.get("args")}
...
tool_calls_history=[*tool_calls_history, _pending_record],
```

So a voice turn that ends because of tool X records every call except X. A reader asking *"what was
this turn trying to do when it stopped?"* gets the reads that succeeded and no trace of the write
that halted it.

**Three further residuals, unchanged:**

- The voice **exception** path (`:784`) is outside the INSERT's reach — the row is never written, so
  the recorded calls, the outcome and the tokens are all lost together. Terminal path #13a.
- The voice INSERT still has **no `withheld_tools` column at all** (measured: column list at
  `:596-598` contains `outcome`, `runtime_variant`, `advertised_tools`, `tool_calls` and not
  `withheld_tools`). So voice narrowings — and voice runs `permission_mode="ask"`, which narrows
  every write tool — register nowhere.
- `latency_ms` is `None` on every voice call (measured), correctly flagged `latency_unmeasured`.
  Voice has no dispatch-time measurement of its own.

### 3.3 F-15 / F-16 — are the corrections accurate, or merely different?

**F-15: accurate.** Verified in three places, §1.2. It also correctly labels the branch unreachable
rather than claiming a fix. The gate it defends (`test_cp0_instrument.py:316-320`) is still a gate on
an unreachable branch — an NV finding on the gate, not on the code — but the comment now *says so*,
which is the difference between a vacuous gate and a hidden one.

**F-16: accurate where it is written, and left standing in two other places.** The new comment at
`instrument.py:334-340` is correct: *"Measured: 1 pass -> 1 entry, 6 -> 6, 10 -> 10 … it is a change,
not a preservation."* I reproduced that measurement on the real class in production ordering:

```
 1 passes ->  1 withheld records for ONE narrowing
 2 passes ->  2
 3 passes ->  3
 6 passes ->  6
10 passes -> 10
```

**But the false statement it corrects appears three times and only one copy was corrected.** Still
present, unchanged, at this SHA:

- `instrument.py:316-317`, the **docstring of the very method**, eighteen lines above the correction:
  *"Deduplicated on `(tool, stage)` so a tool dropped by the same stage on five passes is one
  withholding rather than five — otherwise the count measures pass depth instead of narrowing."*
  Both halves are now false: the key is `(tool, stage, len(self._passes))` (`:341`), and the count
  *does* measure pass depth.
- `test_cp0_instrument.py:322-324`, the gate's own docstring: *"REJECTS: a count that measures how
  many passes the turn took rather than how much was narrowed. Five passes each dropping the same
  tool is one narrowing."* The gate is green because it records **five withholdings and zero
  passes**; in production ordering the same five produce five entries (measured, both orderings).

A reader who opens `record_withheld` reads the false invariant first, in the docstring, and the
correction second, in a comment inside the method body. **The correction is accurate; the file is
still, on net, wrong about itself.**

---

## 4. THE GATE AUDIT — 38 mutations, 23 blind spots, 1 gate red unmutated

`tests/test_cp0_instrument.py` is 601 lines. The only change this round is the F-15 comment at
`:309-315`; **Gates A–F are byte-identical to rounds 5 and 6.** Every row below is a mechanical
result from the harness described in the method note.

### 4.0 The ten mutations of THIS ROUND'S NEW CODE — **all ten invisible**

| mutation | should be | **is** |
|---|---|---|
| revert F-17: `outcome_for_finish_reason(…)` → `OUTCOME_COMPLETED` | red | **GREEN** |
| delete the `_loop_finish_reason` capture (`:6841-6842`) entirely | red | **GREEN** |
| neuter the capture (assignment → `pass`) | red | **GREEN** |
| voice outcome conditional → constant `OUTCOME_COMPLETED` (re-introduce F-14) | red | **GREEN** |
| voice `finish_reason` conditional → literal `"stop"` | red | **GREEN** |
| voice suspend flag never set (`True` → `False`) | red | **GREEN** |
| voice stops recording tool calls (append deleted) | red | **GREEN** |
| voice INSERT drops the `tool_calls` column again | red | **GREEN** |
| voice binds `tool_calls` but always NULL | red | **GREEN** |
| voice persists RAW calls (`ensure_tool_call_instrumented` bypassed) | red | **GREEN** |

**Every change shipped this round is unprotected.** The exact defect the round was convened to fix —
a constant bound at the voice INSERT — can be reintroduced by one word and no gate moves. This is
not a new observation about the *gates*; it is the observation that **seven rounds of fixes have
added zero red-able coverage for the fixes themselves**, so each round's work is re-losable at the
cost of one edit.

### 4.1 Gate A · `test_the_token_budgeter_reports_its_drops_in_production` (`:42-85`)

| mutation | should be | **is** |
|---|---|---|
| revert one site to the plain variant (`stream_service`) | red | red ✔ |
| revert the `tool_surface` helper to the plain variant | red | red ✔ |
| delete the ContextVar fallback (`tool_surface.py:246-253`) | red | **GREEN for A** — Gate D's behavioural half catches it (re-measured: the real `_budget_and_register(None, …)` fills a ContextVar-armed sink with 3 entries; deleting the fallback empties it) |
| **a NEW narrowing calling `budget_names_by_tokens_ex(…)` and discarding `dropped`** | red | **GREEN** |
| rename the `token_budget` stage label (behaviour identical) | green | green ✔ |

Unchanged from R6, including R6's correction in the builder's favour. Row 4 remains the only
uncovered one, and the docstring exemption at `tool_surface.py:237-239` still ships.

### 4.2 Gate B · `test_every_real_dispatch_is_stamped_as_a_real_dispatch` (`:186-226`)

| mutation | should be | **is** |
|---|---|---|
| unstamp the in-loop dispatch (`:4671-4672`) | red | red ✔ |
| a 4th unstamped `knowledge_client` dispatch appended at EOF | red | red ✔ |
| **a dispatch through a differently-named receiver (`await _kc.mcp_execute_tool(`)** | red | **GREEN** |
| a 4th unstamped dispatch inserted **after** the `:3487` stamp | red | red ✔ |
| **a 4th unstamped dispatch inserted BEFORE the `:3487` stamp** | red | **GREEN** |
| a 4th dispatch inserted before `:3487` **with its own stamp** (legitimate) | green | green ✔ |

Unchanged from R6, including R6's narrowing of the backward blind spot to `[0, 3487)`. The
renamed-receiver hole remains the one most likely to fire: this run's purpose is to add a new runtime
module that dispatches tools, and this gate reads `stream_service.py` only.

### 4.3 Gate C · `test_outcome_never_moves_without_finish_reason_moving_with_it` (`:550-574`) — **NO LONGER SOUND. This round broke its stated property and the gate cannot see it.**

| mutation | should be | **is** |
|---|---|---|
| drop `outcome = $2` from the abandoned-suspend UPDATE (`:6327`) | red | red ✔ |
| a NEW `UPDATE chat_messages SET finish_reason` in `voice_stream_service.py`, no outcome | red | **GREEN** (one-file scope) |
| **the CURRENT tree, gate extended to the `ON CONFLICT … DO UPDATE SET` blocks** | green | **RED — unmutated** |

The extended check enumerates both upsert blocks in `stream_service.py`:

```
upsert at :6216   finish_reason = EXCLUDED.finish_reason    outcome = EXCLUDED.outcome     OK
upsert at :7209   finish_reason = 'stop'                    outcome = EXCLUDED.outcome     PINNED
```

`_persist_terminal_assistant` moves both together and derives one from the other when a caller omits
it (`:6196`) — that half is well built. The clean finish now **moves `outcome` while asserting
`finish_reason`**, which is the precise wording of the defect the gate's docstring says shipped once
already. Gate C's needle is `"UPDATE chat_messages SET"`; `ON CONFLICT (message_id) DO UPDATE SET`
does not contain it. **Fourth gate green over a defect in its own stated subject — and the first one
this project created *while fixing something else*.**

### 4.4 Gate D · `test_a_surface_narrowing_registers_without_anyone_wiring_it` (`:87-148`)

| mutation | should be | **is** |
|---|---|---|
| delete the arming line at `:5991` | red | red ✔ |
| `surface_withheld.set(None)` instead of `set([])` | red | **GREEN** |
| the arming line demoted to a **comment** | red | **GREEN** |
| adopt then immediately replace the sink | red | **GREEN** |
| a **third** `discovery_seed_for_surface(` call site, unarmed | red | **GREEN** |
| **delete the drain** at `:6827-6831` | red | **GREEN** |
| rename `discovery_seed_names` → `_v2` (no behaviour change) | green | **RED** (false positive, reproduced) |

All seven rows reproduce R5 and R6 exactly. The behavioural half remains the suite's only real guard
that a narrowing registers, and it is what pays for Gate A's row 3.

### 4.5 Gate E · `test_every_assistant_row_insert_anywhere_writes_an_outcome` (`:150-184`)

| mutation | should be | **is** |
|---|---|---|
| voice drops the `outcome` **column** | red | red ✔ |
| a brand-new assistant INSERT in another file | red | red ✔ |
| the proactive INSERT drops its `outcome` column | red | red ✔ |
| **voice binds `None` instead of a value** — column named, value NULL | red | **GREEN** |
| a new assistant INSERT with the role bound as a **parameter** | red | **GREEN** |

Whole-package scope is the right population and it works for its unit. Its unit is *the column is
named*, which is why all ten of §4.0's value mutations pass it.

### 4.6 Gate F · `test_the_vocabulary_matches_the_database_constraint` (`:576-601`) — **SOUND**

| mutation | should be | **is** |
|---|---|---|
| delete the `advertised_tools` `ADD COLUMN` line outright | red | red ✔ |
| delete the `withheld_tools` `ADD COLUMN` line outright | red | red ✔ |
| delete the `runtime_variant` `ADD COLUMN` line outright | red | red ✔ |
| drift a value in the DB vocabulary | red | red ✔ |
| **rename `advertised_tools` → `advertised_tools_v2`** (prefix preserved) | red | **GREEN** — substring test |

R6's ruling stands. The rename blind spot is real but unrealistic; recorded for completeness because
it is what made my first probe read as a false red.

### 4.7 Scorecard

| gate | boundary | red-able for its own defect? |
|---|---|---|
| A · budgeter wiring | text | **partly** — green over an `_ex` caller that discards `dropped` |
| B · dispatch stamping | positional syntax | **yes** for its three named sites; blind to a renamed receiver and to `[0, 3487)` |
| C · outcome/finish_reason lockstep | syntax, one file, `UPDATE` only | **NO — its property is false on the current tree at `:7209` and the gate is green** |
| D · surface narrowing arrives | text + behaviour | source half **NO** (5 blind spots + 1 false positive); behavioural half **yes** |
| E · assistant-INSERT outcome | syntax, whole package | **partly** — catches a missing column anywhere; blind to every value |
| F · outcome vocabulary + column existence | syntax over real DDL | **yes**, all four columns, both directions |
| — · five-passes-is-one-withholding | behaviour | **NO** — green over a state production never reaches; false in the state it does |
| — · **everything shipped in R7** | — | **NO — 10/10 mutations green** |

---

## 5. The gate I proposed in R6 — audit, including of my own proposal

R6 closed by proposing *"a gate that asserts no CP-0 column is bound to a constant at any INSERT
site"*, red at four sites. Both halves of that need answering honestly.

**How many of the four remain?** Enumerated across all six `INSERT INTO chat_messages` statements in
the package:

| R6 site | R7 state |
|---|---|
| `voice_stream_service.py:585` — `finish_reason` SQL literal `'stop'` | **closed** — `$12`, derived from `_voice_suspended` |
| `voice_stream_service.py:594` — `outcome` constant | **closed** — conditional expression |
| `stream_service.py:7229` — `outcome` constant | **converted, not closed** — now derived, and wrong on a live population (F-19) |
| `routers/internal.py:937` — `outcome` constant | **unchanged** |

**One of four is untouched; one is a different defect now.** And the same statement that lost its
`outcome` constant kept a *new* one nobody counted: `stream_service.py:7207/:7220` bind
`finish_reason = 'stop'` as an SQL literal, on the path where `outcome` now varies.

**Would the gate be satisfiable?** **No — my R6 proposal was wrong, and I withdraw it as stated.** It
would fire on at least ten legitimate bindings:

- `runtime_variant` is `instrument.RUNTIME_LEGACY` at **every** site and must be, until an
  `agentruntime` producer exists. Five false positives on their own.
- `outcome=instrument.OUTCOME_CRASHED` at the mid-turn checkpoint (`:6811`) — a *deliberately*
  pessimistic constant, and one of the better decisions in this checkpoint.
- `outcome=OUTCOME_AWAITING_INPUT` at the suspend persist (`:6967`),
  `OUTCOME_ABANDONED_BY_USER` at the cancel handler (`:7414`) and the abandoned-suspend UPDATEs
  (`:6294`, `:6327`), `OUTCOME_FAILED` at the exception handler (`:7455`). At each, **the path *is*
  the classification**; deriving it from anything would be strictly worse.
- `advertised_tools=None` at voice (`:631`) — the R6 retraction, an honest NULL.

**The satisfiable version, and its score today.** The defensible rule is not "no constants" but:

> *An INSERT reachable from **more than one terminal condition** must not assert `outcome` **or**
> `finish_reason`; both must be derived from what the turn did, and from the **same** signal.*

Under that rule, scored at this SHA: `_persist_terminal_assistant` **passes** (parameterised;
callers classify; `:6196` derives one from the other). Voice **passes** (both derived from
`_voice_suspended`). The proactive check-in **passes** (one condition — though see below). The clean
finish **FAILS**, at exactly one binding: `finish_reason = 'stop'` at `:7207`/`:7220` while `outcome`
varies. **That is a gate that is red today, red for a real reason, and satisfiable by one edit** —
which is what R6's proposal should have been.

Bounded note carried from R6, unchanged: `routers/internal.py:928-930` still says the content *"is
generated, complete and delivered by the time it lands here"*, while `:913` is
`await _generate_proactive_content(...) or _PROACTIVE_STATIC`. `completed` is defensible (a message
did reach the user); the word *generated* is not.

---

## 6. Terminal-path enumeration (0.4) — full, not summarised

| # | terminal path | `file:line` | writes a row? | outcome | R7 |
|---|---|---|---|---|---|
| 1 | clean finish, provider said `stop` | `stream_service.py:7200` | yes | `completed` | pass |
| 1b | **clean finish, provider said anything else** | `:7251` ← `:6841` ← `:2778` | yes | ⚠️ **`interrupted`** while `finish_reason='stop'` | **FAIL — new. F-19** |
| 2 | frontend-tool suspend | `:6956` | yes | `awaiting_input` | pass |
| 3 | cancellation / client disconnect | `:7400` | yes | `abandoned_by_user` | pass |
| 4 | mid-stream exception | `:7447` | yes | `failed` | pass |
| 5 | abandoned suspend, no provisional row | `:6294` | yes | `abandoned_by_user` | pass |
| 6 | abandoned suspend, provisional row | `:6327` | yes | `abandoned_by_user` | pass |
| 7 | **empty terminal turn** | `:6170-6183` | **no** | ❌ none | **FAIL** — labelled, logged, countable; deferred to CP-3 |
| 8 | mid-turn checkpoint (crash surrogate) | `:6811` | yes | `crashed`, pessimistic | pass — good design |
| 9 | **process death before the first checkpoint** | checkpoint is inside the tool-boundary branch | **no** | ❌ none | **FAIL** |
| 10 | **tool-loop pass exhaustion** | `break :1994` → `"stop"` at `:4743` → `completed` at `:7251` | yes | ⚠️ `completed` | **FAIL — unchanged. The F-17 fix does not reach it.** |
| 11 | expired / mismatched resume | delegates to #6 | yes | ✅ | pass |
| 12 | voice turn, clean finish | `voice_stream_service.py:593-635` | yes | ✅ `completed` | pass |
| 13a | **voice turn, exception** | INSERT at `:593` inside `try:` at `:442`; `except` at `:784` logs and returns | **no** | ❌ none — and the recorded tool calls die with it | **FAIL** |
| 13b | **voice turn, suspend-abort** | `:495-496` → `:615`/`:633` | yes | ⚠️ `awaiting_input` | **FAIL, downgraded** — see below |
| 14 | proactive check-in | `routers/internal.py:932-937` | yes | ✅ `completed` | pass (bounded, §5) |
| 15 | **suspend never resumed, never expired** | `db/suspended_runs.py:187` — `sweep_expired_runs` still has **zero callers** (re-verified repo-wide) | yes | ❌ stays `awaiting_input` forever | **FAIL** |
| 16 | spend-gate refusal | searched — no such gate in this service | n/a | n/a | — |
| 17 | turn-level timeout | searched — no wrapper; consistent with the repo's standing rule | n/a | n/a | — |

**On #13b — why it is still a FAIL, and why it is nonetheless better.** The value moved from
`completed` to `awaiting_input`. Both are documented **SUCCESS states**: `instrument.py:67` annotates
`awaiting_input` *"a SUCCESS state (§0.5)"*, and `test_asking_the_user_is_a_success_state`
(`:522-526`) pins it there. So on the axis the column exists to measure — did the user's request get
carried out — **the class did not change**. And `awaiting_input` makes a claim the code cannot honour:
voice creates no suspended-run record (`grep suspended_runs voice_stream_service.py` → nothing) and
has no resume loop (the file says so at `:471-472`), so the row waits for input that can never
arrive. It lands in exactly the state path #15 is failed for. It is better than `completed` because
it is *distinguishable* — a query can find these rows — and worse than it looks, because the word
says "waiting" and nothing is.

**Seven paths fail (#1b, #7, #9, #10, #13a, #13b, #15).** Gate E can see none: #7, #9 and #13a write
no row; #1b, #10, #13b and #15 write values the gate does not inspect.

---

## 7. Findings

### F-19 · The clean finish records `interrupted` for every non-`stop` provider word, while asserting `finish_reason='stop'` on the same row — **new, and the sharpest instance of the round**
§3.1. `stream_service.py:7251` with `:7207`/`:7220`. Measured mapping; `interrupted` is the value the
DDL and the module both call "the metric to drive to zero". Invisible to Gate C by one keyword
(`DO UPDATE SET` vs `UPDATE … SET`) and to Gate E by design.

### F-20 · The false comment F-14 named was never removed — it now sits directly above its own refutation
`voice_stream_service.py:604-608` still reads, verbatim: *"It reaches this INSERT only on a clean
finish, so `completed` is the honest value."* Lines `:609-614`, immediately beneath it, say the
opposite and explain why. Both are in the argument list of the same INSERT. R6 found that sentence
and quoted it as the defect; the fix was made two lines lower and the sentence was left. A reader
arriving at this INSERT reads the false control-flow claim first.

### F-21 · The recorder's docstring and the gate's docstring still assert the invariant F-16 corrected
§3.3. `instrument.py:316-317` and `test_cp0_instrument.py:322-324`. One of three copies corrected.

### F-22 · The voice suspend's own pending tool call is not recorded
§3.2. `voice_stream_service.py:484-496` vs `stream_service.py:6943-6962`. The turn records every call
except the one that ended it.

### F-16² · The pass-scoped dedupe fans `withheld_tools` out by pass count
Code unchanged; re-measured 1→1 … 10→10. Any count over the column measures pass depth. The comment
now says so; the docstring above it does not.

### F-17 (retired) → superseded by F-19
The constant at `stream_service.py:7229` is gone. What replaced it is `completed` on the path F-17
named and `interrupted` on paths it did not.

### RESOLVED · Voice tool calls reach an INSERT
`voice_stream_service.py:505`, `:598`, `:634`. Verified against the full chunk population and both
loop branches. This removes one of R6's four bounds on 0.7.

### RESOLVED · F-15's attribution
§1.2, verified against both metric rounds and against the call sites.

### F-1⁷ · 0.2's residuals, unchanged
`budget_rail_tools`' drops still go to `logger.warning` (`tool_surface.py:257-291`, caller `:516-519`);
`_budget_withheld` is drained only inside `if offered_tools:` (`stream_service.py:2206-2208`); the
tool-free record's `{"tool": "*"}` pseudo-entry; **and voice has no `withheld_tools` column at all**.

### F-9 · `run_arms.py:114` still claims an assertion it does not make (0.5)
Unchanged from rounds 3–6. A docstring overstatement, not a bypass.

### F-11⁵ · `runtime_variant`, `declaration` and `unclassified` remain constants or dead (0.7)
`RUNTIME_AGENTRUNTIME` has no producer; `declaration` is `chunk.get("tool")` at both assignment
points; `tool_call_source()` still has zero callers.

### F-8⁴ · Every recording remains write-only
Re-verified repo-wide across `services/`, `frontend/src` and `contracts/`: nothing reads
`advertised_tools`, `withheld_tools`, `runtime_variant` or `outcome`. This is why F-19 could ship —
a derived value in a column nobody reads is contradicted by nothing.

---

## 8. Vacuity (NV) — can each check fire?

| check | realistic firing input? |
|---|---|
| `stamp_tool_call` raises on unknown source | **Yes** — a future mint site with a typo'd constant |
| `ensure_tool_call_instrumented` inference | **Yes, constantly** — and now on voice calls too |
| `tool_call_source` → `unclassified` | **No** — zero callers |
| `dedupe_recorded_calls` | **No — by design.** Its test is a gate on dead code |
| ContextVar fallback in `_budget_and_register` | **Yes** — measured live via Gate D's behavioural half |
| `record_withheld`'s pass-scoped dedupe | **Yes, every multi-pass turn** — and it fans out |
| `"pass": len(self._passes) or None` → `None` | **No** — unreachable, and the comment now says so |
| `outcome_for_finish_reason`'s `case _` at a WRITE site (`:7251`) | **Yes** — any `length`/`content_filter`/passthrough word. F-19 |
| voice `_voice_suspended` branch | **Yes** — `permission_mode="ask"` suspends on paid Tier-R reads and frontend tools (`:479-483`) |
| voice `_voice_tool_calls` | **Yes** — voice fetches the full catalog (`:451`) and hands it to `_stream_with_tools` |
| `outcome` / `runtime_variant` CHECK constraints | **Yes** for outcome (Gate F); **No** for runtime_variant — only `'legacy'` is written |
| Gates A / B / D-behavioural / E / F | **Yes**, within the bounds tabulated in §4 |
| **Gate C** | **Fires for its one file's `UPDATE` statements; CANNOT fire for the upsert where its property is now false** |
| **every gate, against every change made in R7** | **No — 10/10 mutations green** |

---

## 9. Bypass table — one row per item

| item | the path that skips it, or the search that found none |
|---|---|
| **0.1** | `voice_stream_service.py:468-507` receives an `advertised` chunk on every pass and discards it (`content = chunk_data.get("content", "")` swallows it); `:631` therefore binds NULL. Not bypassed by overwrite: `record_pass` appends, both upserts COALESCE. |
| **0.2** | No code changed. Quantitative bypasses stand: one persistent narrowing writes one record per pass (measured 1→1 … 10→10); `budget_rail_tools`' drops → `logger.warning`; `_budget_withheld` drained only under `if offered_tools:`; the `"*"` pseudo-tool; **voice has no `withheld_tools` column**. |
| **0.3** | `source`: no bypass found — all three real dispatch sites stamped, closed-name-set classifier for the rest, no `tool` default. **Voice calls now reach an INSERT** (closed). Remaining: the voice suspend's own pending call is never recorded (F-22); the voice exception path writes no row at all; nested subagent calls are consumed at `stream_service.py:4850-4858` and never re-yielded, so they reach no INSERT on either pipeline; `latency_ms` measured at 3 of 33 mint sites. |
| **0.4** | Seven paths. Write **no row**: `:6170` (empty turn), pre-checkpoint process death, `voice_stream_service.py:784` (voice exception). Write a **wrong** value: `:1994`→`:4743`→`:7251` (`completed` on a breaker exit, **unchanged by this round's fix**) and **`:7251` again (`interrupted` + `finish_reason='stop'` on any non-`stop` provider word — F-19)**. Write a **success-class** value on a turn that failed: `voice_stream_service.py:495`→`:615` (`awaiting_input`, unresumable). Write a **stale** value: `db/suspended_runs.py:187`, zero callers. Full enumeration in §6. |
| **0.5** | No bypass. `contracts/agent-runtime-baseline/` holds the snapshot, the metrics SQL and the frozen output; `eval/arms/run_arms.py` builds all five arms and refuses on hash mismatch. F-9 is a docstring overstatement. |
| **0.6** | No bypass. `git ls-files eval/arms/` returns both scripts plus `results/binding-format-20260804T035320Z.json` and `results/binding-format-FINDING.md`. |
| **0.7** | No bypass of the literal claim, and it is **stronger this round**: both `stream_service` chokepoints and now the voice chokepoint route every recorded call through `ensure_tool_call_instrumented`, which sets `declaration` and `runtime_variant` unconditionally; `DEFAULT 'legacy'` is the fail-safe direction. Bounded by F-11⁵ (no `agentruntime` producer) and by nested subagent calls reaching no INSERT. |

---

## 10. What changed in the failure, and the one thing I would want recorded

**Two real closures, and they are the right kind.** Voice records its tool calls — that is a whole
pipeline moving from invisible to instrumented, and it is the largest single improvement in three
rounds. F-15's correction withdraws a number rather than defending it, and it is accurate on every
property I could independently check. Neither is cosmetic.

**The thing I would want recorded is what the class did this round.** For six rounds the defect was
*a confident answer to something nobody measured* — a column value, then a justification. In R7 it
became **a derived expression that is correct in form and wrong in reach**. The builder replaced a
literal with a function call, wrote an unusually honest comment saying the fix might distinguish
nothing, handed that question to a verifier — and the question that actually mattered was not the one
handed over. The breaker exit was the *named* risk and it turned out inert. The *unnamed* one is that
the same expression reclassifies every truncated, filtered or non-standard finish into the deprecated
bucket, on a row whose neighbouring column asserts the opposite, in a codebase where nothing reads
either. **Deriving a value does not make it observed; it moves the unobserved assumption from the
value into the mapping.**

And one measurement about the process rather than the code, offered because seven rounds now support
it: **all ten mutations against everything shipped this round are green.** The gates test the state of
the code as of round 4. Every fix since has been made in the space the gates do not cover, which
means the fix rate and the regression rate are both unbounded. The single most useful thing the next
round could add is not another finding — it is that **each round's fix must arrive with the mutation
that would have caught it**, because the ten rows in §4.0 are, collectively, a statement that this
checkpoint's work is one edit away from being undone at any point and nobody would know.

**My falsifier for this round's headline ruling, stated so a later round can execute it:** run
`SELECT finish_reason, outcome, count(*) FROM chat_messages WHERE outcome IS NOT NULL GROUP BY 1,2`
against `loreweave_chat` for rows created after this SHA deploys. **A single row with
`finish_reason='stop'` and `outcome='interrupted'` confirms F-19 as live.** Zero such rows after a
population that includes at least one truncated turn would overturn it and reduce F-19 to a
theoretical reachability claim — which I would accept, and which I could not settle from source
because nothing in this repository reads the column back.
