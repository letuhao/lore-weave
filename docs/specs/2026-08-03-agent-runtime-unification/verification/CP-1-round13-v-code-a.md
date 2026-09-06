# CP-1 · round 13 · V-CODE — Verifier A (the arming, the flag, and the guards)

*Artifact frozen at `5ce95de376b68bfced83b1ae39d0ce8885f461b2`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move.** I wrote
no tracked file other than this one, ran no `git checkout`, and touched nothing live. Every injection
was applied to a **copy of `services/chat-service` in a scratch directory** and reversed by restoring
a pristine snapshot; `git status services/` is clean.*

**Every line marked *measured* was produced by code I executed.** Every injection printed a
source-content assertion before its suite ran — and that rule earned its keep in the first ten
minutes of this session: my initial scratch copy **nested inside a stale `cs/` left by an earlier
round**, and the first three injections reported `!!! INJECTION ABSENT` against a tree whose test
counts nevertheless matched the baseline exactly (`2 failed, 110 passed`). Three green rows that
meant nothing would have been indistinguishable from three real ones. The scratch tree was rebuilt
under a fresh path, re-baselined, and every row below carries a verified-present injection.

## Baselines I measured myself

| where | suites | result |
|---|---|---|
| in-tree | `test_cp0_instrument` + `test_stream_service` | **`182 passed`** |
| in-tree | + `test_admin_surface` + `test_knowledge_client` + `test_cp1_membrane` + `test_cp0_merge_db` + `test_voice_router` + `test_voice_billing` | **`432 passed`** |
| scratch copy | the wide set **minus** `test_cp1_membrane` (7 suites) | **`2 failed, 319 passed`** |
| scratch copy | `test_cp0_instrument` alone | **`2 failed, 110 passed`** |
| scratch copy | `TestTheTurnSinkIsArmedBeforeAnythingNarrows` ("the gate") | **`6 passed`** |
| scratch copy | `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE` alone | **`1 passed`** |
| scratch copy | `test_knowledge_client` + `test_admin_surface` | **`104 passed`** |

The scratch copy's two failures are the copy artefacts rounds 10–12 identified
(`test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason`,
`test_the_fingerprint_does_not_hash_a_column_no_class_reads`). `test_cp1_membrane` is excluded from
the scratch set for the same reason as R11/R12. Every row below reports **extra** failures beyond
the two.

---

## 1 · Verdict

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **arming ADOPTS and the outage fact is derived from the rows** | **PASS on the mechanism, FAIL on the account of it.** Narrow-then-arm now keeps both rows and the outage (measured, and reverting it reds 2). The flag does not outlive a drained turn (X5 reds 2). **But the docstring's justification is false in three measured ways**, the writer's own `set(True)` is unguarded (X7 at baseline), the flag has **no live consumer** — every production read precedes every drain — and the change opened **two leak channels that did not exist before it** | latent (2 of 3), adversarial (1) |
| 2 | **the row/notice contradiction is closed on every construction order** | **FAIL. 7 of 12 orders still contradict**, and the mechanism is new: `arm_turn_surface`'s derivation is a **write**, so it can only *lower* the flag — `narrow → build → drain → arm` erases a real outage. The guard covers **1** order | latent — one arm per request today |
| 3 | **`_as_text` is exact-typed and `absorb` coerces the container** | **FAIL.** 3 of R12's 6 shapes closed; **one still crashes at the exact line it names**, the coercion **created two new defects**, the malformed-row guard is now **dead code**, and — the finding that decides it — **both fixes are at BASELINE under injection: neither has a test.** And the crash class is **re-created twice in this round's own new code**, with `isinstance`, in the commit whose headline is *"`isinstance` was the bug"* | 1 production-reachable (dead code / lost diagnostic), 4 adversarial |
| 4 | **the terminal-write gate's `Name` escape hatch, recorded OPEN** | **CONFIRMED OPEN.** `_withheld_json = None` kills the main `INSERT` **and** the orphan `UPDATE` and the gate is **`1 passed`**, wide at baseline. The clean finish binding `None` likewise. Control (voice) reds. Reachable by an **ordinary refactor**, not only by someone trying | production-reachable as a regression channel |
| 5 | **route sixteen and the wrong `_NOT_A_TURN` reason, recorded OPEN** | **BOTH CONFIRMED**, each with a matched control. **Route seventeen found**: `_TURN_SCOPE` is a **two-directory, non-recursive glob**, so a byte-identical entry point is discovered under `app/services/` and **not discovered at all** under **`app/agentruntime/`** — the package CP-2 is scheduled to put the next turn entry point in | production-reachable (as a future blind spot), by construction |
| 6 | **`[]`-not-cached has no test, recorded OPEN** | **CONFIRMED.** Re-caching `[]` on the admin door leaves `test_knowledge_client` + `test_admin_surface` at `104 passed` and the wide set at baseline. The **user** door still serves `[]` for the full 60 s across a recovered gateway; a **non-empty** admin catalogue is still pinned forever | production-reachable (both doors) |

**Overall: FAIL.**

**What round 13 got right, and it is the most substantial advance in this run's record.** R12's
headline finding was that the previous fix closed the case nobody had reported while all eight
measured routes stayed open. **That is fixed, at the class rather than at the instance.** Measured
against the real functions in a fresh `copy_context()`:

```
narrow ×2, then arm_turn_surface(), then build the recorder -> outage=True   rows=2   ← was 0
arm_turn_surface() first, then narrow ×2  (the control)     -> outage=True   rows=2
recorder built BEFORE the arm (R12's S1b)                   -> rows=1, told=True   ← was 1 / False
```

Reverting the adoption reds `test_NARROW_THEN_ARM_KEEPS_THE_ROWS__the_shape_all_eight_routes_have`
**and** `test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER` — the guard and the fix arrived
together, the guard reds for the reason it names, and the round **deleted the test that had blessed
the defect** (`test_arming_still_REPLACES_the_sink_so_a_turn_starts_clean`) rather than working
around it. R12's own §8 named adoption as the smaller change that would make the fix's sentence true;
it is the change that was made. The self-introduced `ContextVar` leak is disclosed in the docstring,
in the test name, and on the board, and the derived form is guarded (X5, X6). Four fixes in my scope
are properly closed this round.

**Three things turn the verdict.**

1. **Two of the round's four fixes have no test at all, and one of them is R12's finding #3.**
   Reverting `_as_text` to `isinstance` — the exact regression R12 reported and this round's
   headline coercion fix — leaves `test_cp0_instrument` at **`2 failed, 110 passed`** and the wide
   set at **`2 failed, 319 passed`**: *baseline*. Deleting the sink-container coercion: baseline.
   Deleting the malformed-row guard: baseline, because it is now **unreachable code**. This round's
   own standing rule reads *"a fix without a red-able test is not a closed finding, however correct
   the code is"*, and R12 failed the previous round partly on that rule applied to a single fix.
   Three fixes now fail it.

2. **The crash class is re-created inside the new code written to close it, twice, in the same
   commit.** `_as_text` was changed to `type(value) is str` because *"`isinstance` meant the two
   crashes this function's own comment claimed to close were still live."* Forty lines earlier the
   same commit adds `catalogue_outage.set(any(isinstance(e, dict) and e.get("scope") == …))`, and
   `catalogue_outage_registered` keeps `any(e.get("scope") …)`. Measured: a `dict` subclass whose
   `.get` raises makes **`arm_turn_surface` itself raise** — the first statement of every turn entry
   point — and a non-dict row makes `catalogue_outage_registered()` raise `AttributeError` at
   `instrument.py:449`. `absorb` was hardened against precisely these two shapes in the same diff.
   That is the builder's own record — *"a crash recreated inside the function written to fix it"* —
   arriving for the fifth time, and this time the two halves are eighty lines apart in one commit.

3. **`_as_text` does not produce a plain `str`, at the line it names.** `type(value) is str` closes
   the direct subclass; the `try: return str(value)` fallback does not, because CPython's
   `PyObject_Str` returns whatever `tp_str` returned and accepts any `str` **instance**. Measured:
   an object whose `__str__` returns an unhashable `str` subclass still reaches
   `key = (tool, stage, len(self._passes))` and raises **`TypeError: unhashable type: 'NoHash'` @
   `instrument.py:564`** — R12's shape #4, verbatim, at the same line, under the comment that says
   the class is closed. `str.__str__(value)` (or `"%s" % value`, or `"".join([str(value)])`) is the
   one-token version of the property claimed.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every fix in this delta that falls in my scope. `manifest.py` is Verifier B's.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| `arm_turn_surface` **ADOPTS** (`instrument.py:350–353`) | **yes** — `test_NARROW_THEN_ARM_KEEPS_THE_ROWS…`, `test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER` | **yes** — X4 (restore the replace) reds **2 extra**, both by name | **yes.** The reason named is *"all eight routes are narrowings ABOVE an arm"*, and narrow-then-arm is exactly what the test drives. **The best-targeted guard in this run's record** |
| the flag is **DERIVED** from the rows (`:364–365`) | **yes** — `test_THE_OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN`, and `test_AN_EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE__AT_THE_CALLER_TOO` catches it too | **yes** — X5 (leave the flag alone when adopting — the builder's own first version) reds **2 extra** | **yes** |
| `catalogue_outage_registered` reads the flag (`:444–445`) | **yes**, transitively | **yes** — X6 reds **1 extra** (`test_the_ROW_AND_THE_NOTICE…`) | **yes** |
| `record_catalogue_unavailable` **sets** the flag (`:427`) | **NO** | — | — **X7: neutering it leaves `test_cp0_instrument` at `2 failed, 110 passed` — BASELINE.** Masked by the sink-scan fallback at `:446–449`, which answers identically on every order any test drives |
| `_as_text` is exact-typed (`:279`) — **R12's finding #3** | **NO** | — | — **X1: reverting to `isinstance` is at BASELINE on both the instrument suite and the wide set.** A "no" in column one, for the round's headline coercion fix |
| `absorb` coerces the **container** (`:677–680`) | **NO** | — | — **X3: deleting it is at BASELINE** |
| `absorb` coerces a non-plain **row** (`:683–689`) | **partly** — `test_ABSORB_IS_TOTAL…` params `"not a dict"`, `None`, `42` | it is the only path those params take now | **NO, and the old guard is now DEAD.** X2 (delete the `:690–695` malformed fallback) is at **BASELINE**, because `row = {}` on the `else` branch makes `isinstance(row, dict)` true before it. Measured: a row of `42` now records `stage: "unknown", reason: "unrecorded (unrecognised scope '')"` where it used to record `stage: "malformed", reason: "sink row was int"` |
| `test_the_arming_still_REPLACES…` **deleted** and replaced | n/a (a test change) | — | **yes, and worth naming.** The old test asserted the defect as a property; deleting it rather than adding beside it is the correct move |

---

## 3 · The falsifier, per claim — stated before the search

### 1 · Arming adopts; the outage flag is derived — **PASS on the mechanism, FAIL on the account**

**Falsifier (stated first):** any narrowing that still fails to reach the column; any way the derived
flag can be wrong — stale rows in a reused context, a sink mutated after arming, a subagent,
`asyncio.create_task`, a thread pool; any way adopting carries a **previous turn's** rows into this
turn's column; any live read that the derivation makes wrong.

**The mechanism works.** Measured above: narrow-then-arm keeps both rows and the outage, and X4
proves the guard.

**A1 · The writer's own flag set is unguarded, and the flag has no live consumer.** X7 neuters
`catalogue_outage.set(True)` in `record_catalogue_unavailable` and the suite is at baseline — because
`catalogue_outage_registered()` still falls through to the sink scan, and no test drives a read
*after* a drain. I then checked whether production does. It does not:

```
stream_response          arm :5003 → fetch :5623/:5625 → READ :5642 → _emit_chat_turn :6132
_emit_chat_turn          recorder :6576 → adopt+bind_sink :6583–6590 → drains :6970/:7132/:7424/…
resume_stream_response   arm :7749 → fetch :8066/:8075 → READ :8176 → _emit_chat_turn :8181
voice_stream_response    arm :237  → fetch :418        → READ :422  → drain :684
```

**Every one of the three live reads precedes every drain.** The flag's stated purpose — surviving a
drain — has no live path today. It is a correctness floor, which is defensible; what is not
defensible is that the floor's only *measurable* effects in production are the two channels below,
both of which the previous shape did not have.

**A2 · The flag outlives its request in a pooled worker thread.** A thread has no per-request context
copy, and a `ContextVar` set in it lives as long as the thread:

```
req_A on worker 1 (a real outage, drained)      -> catalogue_outage_registered() = True
req_B on worker 1 (NO outage, empty sink)       -> catalogue_outage_registered() = True   ← leak
```

This is the **same defect the round says it fixed** — *"a context that had already served a turn kept
`True`, so a later turn inserted TOOL CATALOGUE UNAVAILABLE with no outage"* — in the one place the
derivation cannot reach, because nothing arms on a worker thread. Before this round there was no flag
and the drained sink answered `False`. **Reachability: adversarial/latent.** `run_in_executor` appears
only in `app/storage/minio_client.py`, which narrows nothing; I checked rather than assumed.

**A3 · `asyncio.create_task` splits the flag from the rows.** A child task copies the context (its
`set` does not propagate up) but shares the **same list object** (`copy_context` copies the binding,
not the list). Measured:

```
narrow inside create_task, parent reads BEFORE the drain -> True   (the sink fallback saves it)
                          parent reads AFTER  the drain -> False   while the row IS persisted
```

That is R12's headline contradiction — column says outage, prompt says none — re-enterable through a
child task. **Reachability: adversarial/latent.** I enumerated all eleven `create_task` sites in
`stream_service.py` and `voice_stream_service.py`; none narrows, and `_fire_executive_tick` /
`_auto_generate_title` were checked individually.

**A4 · Adoption *can* carry a previous turn's rows, and the docstring's reason for why it cannot is
the same fact that makes route A5 lossy.** The docstring reads *"a sink already present at the top of
a turn is that turn's own early narrowing — each request runs in its own task and therefore its own
context copy, so it cannot be a previous turn's."* Two measured counter-examples:

```
A4a  turn 1 narrows and DIES before the terminal write (client disconnect, cancellation);
     turn 2 arms in the same context
       -> turn 2 outage=True, turn 2 column = [{scope: catalogue, reason: "turn_1_outage"}]

A4b  a narrowing in the BASE context pins one list; every later task copy shares that object
       -> turn 1 outage=True, turn 1 column = [{... reason: "BASE_CONTEXT_OUTAGE"}]
       (under the old REPLACE semantics turn 1 would have discarded it)
```

Both are latent — **reachability: adversarial/latent**, decided by enumerating the callers: every
`surface_withheld.set()` today happens inside a request handler, uvicorn creates a task per request,
and no startup or background path narrows. But the docstring states the impossibility
unconditionally, and it is the sentence the whole fix rests on. A4b is a *new* consequence of
adoption: the ambient-sink leak R12 recorded as latent now **delivers** a foreign row into the first
turn that runs, rather than having it thrown away.

**A5 · The pre-arm class is NOT closed for a child task, and this is the route adoption cannot
reach.** Measured, with a matched control:

```
create_task(prefetch that narrows), THEN arm   -> outage=False  rows=None   ← LOST ENTIRELY
arm, THEN create_task(the same prefetch)       -> outage=True   rows=1      ← control
gather() of two narrowing prefetches, then arm -> rows=None
```

The child copies the context with `surface_withheld = None`, so `_sink_for_record` auto-arms **in the
child's context** and the list dies with the task. The docstring's *"each request runs in its own
context copy"* is exactly why. **Reachability: adversarial/latent today** — no live narrowing is
spawned before an arm — and the ordering gate *does* cover it positionally for the five names in
`_NARROWING_CALLS`, which is the one place in this area where a gate is doing real work.

**A6 · A rogue row makes the arm itself raise.** See claim 3.

### 2 · The row/notice contradiction, on every construction order — **FAIL**

**Falsifier:** any order of *(narrow, arm, build the recorder, drain)* in which the persisted row and
`catalogue_outage_registered()` disagree.

All 12 legal permutations, driven against the real functions, one `copy_context()` each:

| order | model told | row persisted | |
|---|---|---|---|
| `narrow → arm → build → drain` | True | True | ok |
| `narrow → build → arm → drain` | True | True | ok |
| **`narrow → build → drain → arm`** | **False** | **True** | **CONTRADICT** |
| `arm → narrow → build → drain` | True | True | ok |
| `arm → build → narrow → drain` | True | True | ok |
| `arm → build → drain → narrow` | True | True | ok |
| `build → …` (6 orders) | True | **False** | **CONTRADICT ×6** |

**7 of 12.** Two distinct mechanisms, and the first is created by this round:

* **`arm_turn_surface`'s derivation is a WRITE, so it can only lower the flag.** After a drain the
  sink is empty, so an arm that follows one sets `False` over a `True` that a real outage put there.
  The fix for *"the flag outlived its turn"* made the arm authoritative over a fact it recomputes
  from a container **other code empties**. `catalogue_outage.set(True) if any(...) else <leave>` — or
  deriving in the reader rather than the writer — is the shape that has neither failure.
* **A recorder built before anything armed adopts `None`** and never drains, so the row is lost while
  the flag says outage. `_emit_chat_turn` is safe only because it calls `bind_sink` explicitly at
  `:6590` — the step R11 deleted for being forgettable and then restored.

**Reachability: latent, all seven.** Each entry point arms exactly once, at its first statement, and
both recorder construction sites sit inside an armed turn. The finding is that the guard covers **one**
of twelve orders and the docstring claims all of them.

### 3 · `_as_text` exact-typing and container coercion — **FAIL**

**Falsifier:** any row shape, or any sink shape, that crashes `absorb`, `withheld_json`, the
`json.dumps` at the write boundary, **or the arming**; any value recorded that is not what the sink
said; any of the three fixes surviving deletion.

20 shapes driven through a real recorder inside a real armed turn, each ending at `json.dumps`.

| shape | outcome | vs R12 |
|---|---|---|
| `stage` / `tool` is a `str` subclass, unhashable | ✅ handled | **fixed** |
| `stage` is a `str` subclass whose `__hash__` raises | ✅ handled | **fixed** |
| a `dict` subclass whose `.get` raises | ✅ handled (read through `__getitem__`) | **fixed** |
| **`stage.__str__` RETURNS a `str` subclass** | **`TypeError: unhashable type` @ `instrument.py:564`** | **still open** |
| **`tool.__str__` RETURNS a `str` subclass** | **`TypeError` @ `:564`** | **still open** |
| **the sink is truthy and not iterable (`42`)** | **`TypeError: 'int' object is not iterable` @ `:680`** | **NEW — created by the coercion** |
| **the sink is a `list` SUBCLASS** | no crash, **the original is never drained** — see below | **NEW** |
| `count` is `False` / `True` | persists `"count": false` / `true` | **still open** |
| row is `42` / `None` / `"str"`; sink is a tuple / generator / str / dict; `__str__` raises; `__getitem__` raises | ✅ no crash | — |

**B1 · `str(value)` does not normalise a subclass.** `PyObject_Str` returns `tp_str`'s result if it is
a `str` **instance**, subclass included. So an object whose `__str__` returns an unhashable subclass
walks through `_as_text`'s fallback and blows the dedupe key at `record_withheld` (`:564`) and
`_record_scoped` (`:644`) — the two lines the comment three above it says are closed.
**Reachability: adversarial-input only.** It needs a hand-written class in the sink; I decided this by
enumerating the producers — every live `sink.append` is `instrument.py`'s own two dict literals.

**B2 · The container coercion drains the COPY.** `if type(sink) is not list: sink = list(sink)`
rebinds the local; `while sink: sink.pop(0)` then empties the copy and leaves the caller's object
full. Measured across a mid-turn checkpoint and a terminal write with a `list` subclass sink:

```
checkpoint rows = 1     terminal rows = 2     sink STILL HOLDS 1 row
```

The same narrowing is recorded twice at two pass numbers — the non-monotone `withheld_tools` array
F-48's segment stamping exists to prevent, produced by the fix for a different problem.
**Reachability: adversarial-input only** (`bind_sink` is called with a plain list at both live sites).

**B3 · The malformed-row guard at `:690–695` is unreachable, and its diagnostic is gone.** The new
`else` branch assigns `row = {}`, so `if not isinstance(row, dict)` can never be true. X2 deletes it
at baseline. Measured behaviour change: a row of `42` used to record
`stage: "malformed", reason: "sink row was int"` and now records
`stage: "unknown", reason: "unrecorded (unrecognised scope '')"` — the type of the bad row, which is
the only thing that would let anyone find its producer, is no longer written down.
**Reachability: production-reachable** — this is a live behaviour change on the existing
malformed-row path, and it is the one finding in this claim that does not need a hostile input, only
a buggy one.

**B4 · The crash class re-created in this round's new code, twice.**

```
arm_turn_surface           :364  catalogue_outage.set(any(isinstance(e, dict) and e.get("scope") …))
catalogue_outage_registered:449  return any(e.get("scope") == SCOPE_CATALOGUE for e in sink)
```

Measured:

```
a dict subclass whose .get raises, in the sink -> arm_turn_surface()             RAISES RuntimeError
                                              -> catalogue_outage_registered()   RAISES RuntimeError
a row of 42 / None in the sink                -> catalogue_outage_registered()   AttributeError @ :449
```

`absorb`, eighty lines below, was hardened against **both** of these shapes in **this same commit**,
with `type(row) is not dict` and a defensive read — and the commit's headline is that `isinstance`
was the wrong check. The first of the two is at the **first statement of every turn entry point**, so
where `absorb` degraded a row this takes the turn.
**Reachability: adversarial-input only** — same reasoning as B1.

**B5 · `count` still admits a bool.** `isinstance(row.get("count"), int)` is `True` for `True` and
`False`, so `"count": false` reaches the jsonb. `count is not None` exists at `:657` precisely
because *absent is not zero*; `false` is a third thing that is neither. R12's finding, unanswered and
unmentioned. **Reachability: adversarial-input only.**

### 4 · The terminal-write gate's `Name` escape hatch — **CONFIRMED OPEN**

**Falsifier:** any way to stop a persisted column carrying the recorder's value while the gate is
green.

Baseline: gate alone `1 passed`; wide `2 failed, 319 passed`.

| # | injection | gate | wide |
|---|---|---|---|
| **G1** | `_withheld_json = None` at `stream_service.py:6341` — **both** the main `INSERT` (`:6390`) and the orphan `UPDATE` (`:6303`) now persist NULL | **`1 passed` — GREEN** | **baseline** |
| **G2** | `:7424` — the clean finish binds `None` (R10's I13, *"the path every successful turn takes"*) | **`1 passed` — GREEN** | **baseline** |
| G3 | CONTROL — voice `:684` binds `None` (R10's I4) | **`1 failed`** ✅ | 1 extra ✅ |

Byte-identical to R12's measurement, on a gate the round did not touch. The offender test is **per
function** and its second disjunct is *any `ast.Name` whose id contains `"withheld"`* — so the local
variable `_withheld_json` on the left-hand side absolves the function while both of its binds carry
`None`.

**Reachability: production-reachable, as a regression channel rather than as a live bug.** The column
is correct today. What is reachable by an ordinary edit — R12 measured a plain rename keeping it
green with one of three occurrences surviving — is landing NULL in `withheld_tools` on every text
turn with CI green, which is the exact failure this gate was written for and which has now happened
twice. The honest form is unchanged from R11 §8 and R12: assert **per bind expression**, over each
`execute`/`fetchrow`/`fetchval` whose SQL names the column, that the argument at the column's
position contains `withheld_json()`. That reds G1, G2 and G3 and does not red a parameterised column
name (R12's G5 false positive).

### 5 · Route sixteen, the wrong `_NOT_A_TURN` reason, and route seventeen — **CONFIRMED, plus a new one**

**Falsifier:** any construction that puts a narrowing above an arming, or a narrowing entry point
with no arming, while the gate is green; any exempted entry whose stated reason is untrue.

**The gate is byte-identical this round.** `git diff 9c8df78..HEAD -- tests/test_cp0_instrument.py`
touches `_NOT_A_TURN`, `_TURN_SCOPE`, `_NARROWING_CALLS`, `arming`, `glob`, `_narrowings_in` and
`_called_name` **zero** times.

**Route sixteen — confirmed, matched control.**

| variant | sweep discovers it? | gate |
|---|---|---|
| `send_message_v2` narrows, **returns** | `['routers/r16_probe.py::send_message_v2']` | **`2 failed`** ✅ |
| `send_message_v2` narrows, **then delegates to `stream_response`** | **`[]` — not discovered at all** | **`6 passed`**, wide **at baseline** |

**Route seventeen — `_TURN_SCOPE` is a two-directory, non-recursive glob.** `_turn_entry_calls` reads
`(base / sub).glob("*.py")` for `sub in ("services", "routers")` only. The same file, byte for byte:

| where the turn entry point lives | sweep discovers it? | gate |
|---|---|---|
| `app/services/runtime_probe.py` — CONTROL | `['services/runtime_probe.py::runtime_turn_probe']` | **`2 failed`** ✅ |
| **`app/agentruntime/runtime_probe.py`** | **`[]` — not discovered** | **`6 passed`**, wide at baseline |
| `app/client/runtime_probe.py` | **`[]` — not discovered** | **`6 passed`** |

This is not a hypothetical directory. **`app/agentruntime/` is the package this checkpoint exists to
build**, and the board's next step reads *"CP-2 — the runtime that serves through the membrane"*. The
gate that has taken four rounds and seventeen routes to harden cannot see the file the next turn
entry point is scheduled to be written in. **Reachability: production-reachable by construction** —
not an input an adversary supplies, a directory the sweep does not open.

**Route eighteen, the other way — a false positive on correct code.** Moving the voice arm inside an
`async with contextlib.AsyncExitStack():` at the top of the body — a perfectly ordinary
resource-scoped arm — reds the gate as a *conditional* arm (`1 failed`), because `top_level_arm_lines`
accepts only `ast.Expr` and `ast.Assign`. R11's warning stands: a guard that reds on correct code is
a guard that gets deleted.

**The `_NOT_A_TURN` reason is still factually wrong.** `routers/catalog.py::list_tools_catalog`:

> *"…and `record_catalogue_unavailable` **correctly no-ops unarmed** rather than attributing a row to
> a turn that never happened."*

`record_catalogue_unavailable` has not no-op'd unarmed for two rounds — R11 deleted that behaviour and
this round's `arm_turn_surface` docstring restates the deletion in bold. The exemption's entire
justification describes code that no longer exists, and the three routers it covers
(`catalog.py`, `tool_permissions.py` ×2) now each auto-arm a sink and set `catalogue_outage = True`
in a non-turn request. `test_NO_ALLOW_LIST_ENTRY_IS_STALE` cannot see it: it compares membership
against `discovered`, and the entry is still discovered.
**Reachability: production-reachable** as a false statement in the tree that will be read as true by
the next person to classify an entry; harmless at runtime, because those contexts are discarded.

**One thing to say plainly about routes 16–18.** Adoption changed what they cost. Under the old
REPLACE semantics a pre-arm narrowing in the same context was *lost*, and R12 was right that route
sixteen was a loss channel. It is not one now — I drove it: the router's rows survive the delegation.
So these are **gate-completeness** findings, not data-loss findings, and the loss route that remains
(A5, the child task) is the one the gate actually covers. The gate is now protecting a property the
runtime no longer needs, in two directories, while the two mechanisms that carry the fact today —
the auto-arm and the adoption — are guarded by unit tests instead (X4, X5, and correctly so).

### 6 · The `[]`-not-cached fix and the two doors — **CONFIRMED OPEN**

**Falsifier:** the `[]`-not-cached fix having a guard; either door registering an outage on a
*successful* empty fetch; a recovered gateway not being re-dialled.

Driven against the real `KnowledgeClient` with a stubbed MCP transport, one armed turn per row,
counting real dials at `session.initialize`:

```
--- ADMIN door (process-wide cache, no TTL) ---
  turn 0: gateway offers []            -> got 0  dials=1  outage=False
  turn 1: gateway offers ['a']         -> got 1  dials=2  outage=False     ← [] re-dialled ✅
  turn 2: gateway offers ['a','b','c'] -> got 1  dials=2  outage=False     ← non-empty PINNED
--- USER door (per-user cache, TTL = 60.0 s) ---
  turn 0: gateway offers []            -> got 0  dials=1  outage=False
  turn 1: gateway offers ['a']         -> got 0  dials=1  outage=False     ← [] cached
  turn 2: gateway offers ['a','b','c'] -> got 0  dials=1  outage=False     ← still []
  a real transport failure  -> outage=True ✅      no admin token at all -> outage=True ✅
```

* **`[]`-not-cached works on the admin door and still has no test.** C-B (`if self._admin_tool_definitions is not None:`) leaves `test_knowledge_client` + `test_admin_surface` at **`104 passed`** and the wide set at baseline. The comment that justifies deleting the empty-catalogue registration calls this fix *"the real finding it was reaching for"*; nothing asserts it. **Confirmed OPEN, production-reachable.**
* **The user door still caches `[]` for the full 60 s.** One zero-tool answer and the next turn's model gets no tools while the gateway is healthy, with no outage registered — correctly, because there was none. Same shape as the admin bug, bounded by a TTL. **Production-reachable.**
* **A non-empty admin catalogue is still pinned forever.** `self._admin_tool_definitions = tools` is unconditional and the class has no TTL field, so a catalogue that grows from one tool to three is never seen. R11's A3, unfixed and unmentioned for three rounds. **Production-reachable.**
* The empty-vs-outage revert remains correct on both doors and its guard still reds for its reason. Not re-graded.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| a narrowing can no longer be lost to ordering | **a narrowing in a child task spawned before the arm** — auto-arms in the child's context and dies with it | ✅ A5, `outage=False rows=None`, control reds | adversarial/latent |
| a sink at the top of a turn cannot be a previous turn's | turn 1 dies before draining; turn 2 adopts its rows **and its outage** | ✅ A4a | adversarial/latent |
| " | a base-context narrowing pins one list every task copy shares | ✅ A4b | adversarial/latent |
| the outage fact does not outlive its turn | a **pooled worker thread** keeps `True` for the thread's life | ✅ A2 | adversarial/latent |
| the row and the notice cannot contradict | `narrow → build → drain → arm` — the arm **lowers** a true flag | ✅ 1 of 12 orders | latent |
| " | a recorder built before anything armed adopts `None` | ✅ 6 of 12 orders | latent |
| " | a narrowing in a child task, read after the drain | ✅ A3 | adversarial/latent |
| U-2 · the recorder's value reaches `withheld_tools` | `_withheld_json = None` — main INSERT **and** orphan UPDATE | ✅ G1, gate `1 passed`, wide baseline | **production (regression channel)** |
| " | `:7424` the clean finish binds `None` | ✅ G2, baseline | **production (regression channel)** |
| arm-order gate · no narrowing precedes the arming | a router that narrows **then delegates** — not discovered | ✅ R16, control reds | production (blind spot) |
| " | **an entry point in `app/agentruntime/` or `app/client/`** — not discovered | ✅ R17, control reds | **production, by construction** |
| the gate does not red on correct code | a top-level arm inside `async with` reds as "conditional" | ✅ R18 | production (false positive) |
| `_NOT_A_TURN` entries are trustworthy | `catalog.py`'s reason cites a no-op deleted two rounds ago | ✅ by reading | production (documentation) |
| `_as_text` yields a plain `str` | `__str__` that returns a `str` subclass → `TypeError` @ `:564` | ✅ | adversarial |
| `absorb` cannot crash | a truthy non-iterable sink → `TypeError` @ `:680` (**new**) | ✅ | adversarial |
| `absorb` drains its sink | a `list` subclass → the copy is drained, the original is not; rows double | ✅ 1 → 2 | adversarial |
| a malformed row is recorded as malformed | the `:690–695` fallback is **unreachable**; the type is no longer written | ✅ X2 baseline | **production** |
| the arming cannot crash | a rogue row in the sink → `arm_turn_surface` raises (**new**) | ✅ | adversarial |
| `count` is absent-or-a-count | `count: false` persists | ✅ | adversarial |
| the admin `[]` is not cached | none — the fix works — **but nothing tests it** | ✅ C-B baseline | **production** |
| the user `[]` is not cached | it is, for 60 s | ✅ | **production** |
| a non-empty admin catalogue is refreshed | it never is | ✅ | **production** |

---

## 5 · The red-ability table

Baseline for every row: **the scratch copy**. Gate rows use `TestTheTurnSinkIsArmedBeforeAnythingNarrows`
alone (**`6 passed`**); terminal-write rows use that test alone (**`1 passed`**); "instrument" rows use
`test_cp0_instrument.py` alone (**`2 failed, 110 passed`**); "wide" is the 7-suite set
(**`2 failed, 319 passed`**); "doors" is `test_knowledge_client` + `test_admin_surface`
(**`104 passed`**). "extra" counts failures **beyond** the two copy artefacts. Every injection was
applied to the scratch copy, **verified present by a source-content grep printed before the run**,
and reversed by restoring a pristine snapshot — never `git checkout`.

| # | injection | what it models | result |
|---|---|---|---|
| **X1** | `_as_text` back to `isinstance(value, str)` | **R12's finding #3 — this round's headline coercion fix** | **instrument BASELINE, wide BASELINE — GREEN** |
| **X2** | delete the `:690–695` malformed-row fallback | the guard R11 added for a non-dict row | **BASELINE — GREEN (it is dead code)** |
| **X3** | delete the sink-container coercion | this round's new container guard | **BASELINE — GREEN** |
| X4 | `arm_turn_surface` REPLACES again | **the round's headline fix** | **2 extra** ✅ — `test_NARROW_THEN_ARM_KEEPS_THE_ROWS…`, `test_the_ROW_AND_THE_NOTICE…` |
| X5 | the flag is left alone when adopting | **the defect the builder introduced and disclosed** | **2 extra** ✅ — incl. `test_THE_OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN` |
| X6 | `catalogue_outage_registered` stops reading the flag | the drained-sink read | **1 extra** ✅ |
| **X7** | `record_catalogue_unavailable` stops setting the flag | the flag's **writer** | **BASELINE — GREEN** (masked by the sink fallback) |
| **G1** | `_withheld_json = None` | the main `INSERT` **and** the orphan `UPDATE` persist NULL | **gate `1 passed`, wide baseline — GREEN** |
| **G2** | `:7424` clean finish binds `None` | R10's I13, still open | **GREEN — baseline** |
| G3 | CONTROL — voice `:684` binds `None` | R10's I4 | **`1 failed`, wide 1 extra** ✅ |
| **C-B** | cache `[]` on the admin door again | **the empty-catalogue revert's stated justification** | **doors `104 passed`, wide baseline — GREEN** |
| **R16** | a router that narrows, then delegates | route sixteen | **not discovered; gate `6 passed`, wide baseline** |
| R16-b | the same router **without** the delegation | the matched control | discovered; **gate `2 failed`** ✅ |
| **R17** | the same entry point in `app/agentruntime/` | **route seventeen** | **not discovered; gate `6 passed`, wide baseline** |
| R17-b | the byte-identical file in `app/services/` | the matched control | discovered; **gate `2 failed`** ✅ |
| R17-c | the byte-identical file in `app/client/` | the second directory | **not discovered; gate `6 passed`** |
| R18 | a top-level arm inside `async with` | a correct resource-scoped arm | **`1 failed` — FALSE POSITIVE** |

**X1, X3, X7 and C-B are the block that decides this round.** Four of the fixes in my scope survive
their own deletion with the suite exactly at baseline, and one of them — X1 — is the direct answer to
the finding that failed the previous round. G1 and C-B are R12's open items, unchanged and confirmed.
R17 is new and is the one I would fix first, because it is the only finding here whose subject is
*the next thing this project is going to build*.

---

## 6 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| arming adopts | the other half — a pre-arm narrowing in a **different context** | drove `create_task` and `gather` before the arm | **NO** — A5, lost entirely |
| " | whether adoption can carry a **previous turn's** rows | drove an undrained turn and a base-context sink | **NO** — A4a/A4b; the docstring denies both |
| " | whether the delegation exemption is still sound under it | R16 + matched control | the exemption is unchanged; its **cost** is now lower, not gone |
| " | whether any `_NOT_A_TURN` reason was invalidated | read all five against the current `record_*` bodies | **NO** — `catalog.py`'s reason is still untrue, two rounds on |
| the derived flag | whether the **writer's** set is guarded | X7 | **NO — baseline** |
| " | whether the flag can be wrong in a thread / a subagent / a task | drove all three | **NO** — A2 and A3 are new channels |
| " | whether any live read is after a drain (does the fix have a consumer?) | enumerated all four turn paths by line | **NO live consumer today** |
| `_as_text` exact-typing | every value that is nominally a `str` but does not behave like one | drove 20 shapes | **NO** — `str()` still returns a subclass; `:564` unchanged |
| " | whether the fix is guarded | X1 | **NO — baseline** |
| the container coercion | whether coercing changes what gets drained | drove a checkpoint + terminal write with a `list` subclass | **NO — the original is never drained, rows double** |
| " | whether the coercion itself can crash | drove a truthy non-iterable | **NO — new `TypeError` @ `:680`** |
| " | whether the fix is guarded | X3 | **NO — baseline** |
| the defensive row read | whether the old malformed guard still runs | X2 + a behavioural read of `row = 42` | **NO — dead code, and the type diagnostic is lost** |
| " | whether the **same** class was closed in the new flag code | drove a rogue row through the arm and the reader | **NO — re-created twice, with `isinstance`, in this commit** |
| " | `count`'s type check | drove `True` / `False` | **NO** — `count: false` persists |
| the terminal-write gate | whether a bind inside a covered function can still be `None` | G1, G2 | **NO** — unchanged from R12 |
| the ordering gate | whether the sweep reaches every package | R17 across three directories with a matched control | **NO — route seventeen** |
| the `[]`-not-cached fix | whether anything asserts it | C-B | **NO — still no test** |
| " | the user door's `[]` cache | drove U0→U2 | **NO** — 60 s, no re-dial |
| " | a **non-empty** stale admin value | drove A0→A2 across a growing gateway | **NO** — pinned forever, still no TTL |

---

## 7 · Where the builder's documentation of a residual is incomplete or wrong

1. **`arm_turn_surface`'s docstring asserts an impossibility that is false twice and lossy once.**
   *"A sink already present at the top of a turn is that turn's own early narrowing — each request
   runs in its own task and therefore its own context copy, so it cannot be a previous turn's."*
   Measured: an undrained turn hands its rows and its outage to the next arm in the same context; a
   base-context sink is shared by every later task copy. And the second half of the sentence — the
   per-task context copy — is precisely why a narrowing spawned in a child task before the arm is
   **lost entirely**. The sentence is used as a safety argument and it is also the mechanism of the
   one residual loss route.
2. **`_as_text`'s new comment claims a totality the code does not have.** *"The whole point of
   coercing at the boundary is that what comes out is a plain `str`."* It is a plain `str` on the
   `type(value) is str` and `None` branches and **not** on the `str(value)` branch, which returns
   whatever `__str__` returned. `TypeError: unhashable type` at `:564` is still one class definition
   away, at the line the comment names.
3. **`absorb`'s container comment describes a guard that changes what gets drained.** *"A `list`
   subclass can lie about `pop`, `__bool__` or `__len__` and hand this loop something other than what
   it holds."* True — and `sink = list(sink)` then drains the copy, so the caller's sink keeps its
   rows and the next `withheld_json()` records them again at a different pass number. The `while
   sink: sink.pop(0)` loop and the coercion cannot both be right; draining the copy **into** a
   `sink.clear()` is the version that keeps the stated property.
4. **`absorb`'s row comment leaves a dead guard standing.** *"`isinstance` again: a `dict` subclass
   whose `.get` raises took the turn down."* Fixed — and the `if not isinstance(row, dict)` fallback
   six lines below is now unreachable, taking with it the `"sink row was {type}"` diagnostic that a
   previous round added on purpose. X2 deletes it at baseline.
5. **The commit's own lesson is not applied to the code it added.** `_as_text` was changed *because*
   `isinstance` was too loose; `arm_turn_surface:364` and `catalogue_outage_registered:449` use
   `isinstance` and a bare `.get` on the same kind of input, and both raise on the shapes `absorb`
   was hardened against in the same diff. One of the two is the first statement of every turn.
6. **`test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER` names a property it tests once.**
   The name says *cannot*; the test drives one of twelve orders. Seven still contradict, and one of
   the seven is created by this round's derivation.
7. **The `_NOT_A_TURN` reason for `list_tools_catalog` has now been wrong for two consecutive
   rounds**, and R12 reported it. It is three lines of comment.
8. **Exemplary, and worth naming.** The adoption fix is the change R12's §8 asked for, made at the
   class rather than at the instance, and it arrived with a guard that reds for the reason it names
   and with the *deletion* of the test that had blessed the old behaviour. Deleting a test you wrote
   yourself, because it asserted the defect, is the hardest correction in this file to make and it
   was made without hedging. The self-introduced `ContextVar` leak is disclosed in the docstring, in
   the test's name, and on the board, with the diagnostic signature (green alone, red in the full
   run) written down for whoever meets it next. That is four properly closed fixes and one honest
   post-mortem in a single commit.

---

## 8 · What would have to be true for this to PASS

* **`_as_text` must be `str.__str__(value)`** (or `"%s" % value`) on the fallback path, not
  `str(value)` — and it needs the test X1 would red. The parameter is one line:
  `type("x", (str,), {"__str__": lambda s: NoHash(s)})`.
* **The container coercion must drain the caller's sink**, not a copy — and it needs the test X3
  would red.
* **The `:690–695` fallback must be reachable or deleted.** A malformed row should record what it
  was; `row = {}` erases the only evidence.
* **The new flag code must use the check the same commit says is required.** `type(e) is dict` and a
  defensive read at `:364` and `:449`, so a rogue row cannot take a turn at its first statement.
* **`record_catalogue_unavailable`'s flag set needs a test that drives a read AFTER a drain** — which
  is the only situation the flag exists for, and X7 shows nothing does. Or the flag should be
  reconsidered: it has no live consumer, and its two measurable production effects are the thread
  leak and the task split.
* **`arm_turn_surface` must not be able to lower a set flag.** Derive in the reader, or raise-only in
  the arm; `narrow → drain → arm` currently erases a real outage.
* **The terminal-write gate must anchor per bind, not per function** — unchanged from R11 §8 and
  R12 §8. G1 and G2 are two rounds old.
* **`_TURN_SCOPE` must be `app/**/*.py`, not two flat directories** — and the first file to check
  against it is the next entry point in `app/agentruntime/`. Route seventeen is the only finding here
  that is guaranteed to bite, because the code it hides has not been written yet.
* **The delegation exemption must be positional**, and `_NOT_A_TURN` needs its *reasons* checked, not
  just its membership.
* **`[]`-not-cached needs the test C-B would red**, the user door needs the same fix, and the
  non-empty admin catalogue needs a TTL. Three rounds, three verifiers, hand-measured each time.

`git rev-parse HEAD` at start: `5ce95de376b68bfced83b1ae39d0ce8885f461b2`.
`git rev-parse HEAD` before writing: `5ce95de376b68bfced83b1ae39d0ce8885f461b2`.
