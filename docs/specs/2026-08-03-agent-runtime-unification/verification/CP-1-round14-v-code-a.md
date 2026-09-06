# CP-1 · round 14 · V-CODE — Verifier A (the instrument, whose finding count is FLAT)

*Artifact frozen at `b30db5b8099a93fdf7ba7fafcb19a62747604672`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move.** I wrote
no tracked file other than this one, ran no `git checkout`, and touched nothing live. Every injection
was applied to a **fresh scratch copy** at
`…/scratchpad/r14a/cs` and reversed by restoring a pristine snapshot taken at copy time;
`git status services/` is clean.*

**The scratch tree was proved un-nested before anything ran**, because that is the failure that cost
R13 three rows: the path was decomposed and checked against every stale scratch directory name this
workspace carries (`cs`, `cs-pristine`, `r12`, `r13cs`, `r13pristine`, `repo`, `pkgcopy`, `mt`) —
**only the leaf `cs` matches, so the copy is not inside a stale one** — and the four files under test
were then sha256-compared against the artifact and printed equal. **Every injection printed a
source-content assertion before its suite ran**, and three injections in this session aborted on that
assertion rather than reporting a meaningless row.

## Baselines I measured myself

| where | suites | result |
|---|---|---|
| in-tree | `test_cp0_instrument` + `test_stream_service` | **`187 passed`** |
| scratch copy | the 7-suite wide set (`instrument`, `stream_service`, `admin_surface`, `knowledge_client`, `cp0_merge_db`, `voice_router`, `voice_billing`) | **`2 failed, 324 passed`** |
| scratch copy | `test_cp0_instrument` alone | **`2 failed, 115 passed`** |
| scratch copy | `TestTheTurnSinkIsArmedBeforeAnythingNarrows` ("the gate") | **`6 passed`** |
| scratch copy | `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE…` alone ("term") | **`1 passed`** |
| scratch copy | `test_knowledge_client` + `test_admin_surface` ("doors") | **`104 passed`** |

The two scratch failures are the copy artefacts rounds 10–13 identified
(`test_the_class_4_metric_no_longer_pins_outcome_to_one_finish_reason`,
`test_the_fingerprint_does_not_hash_a_column_no_class_reads`). `test_cp1_membrane` is excluded from
the scratch set for the same reason as R11–R13. **"extra" below counts failures beyond those two.**
Counts are R13's +5, which is this round's five new tests.

---

## 1 · Verdict

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the terminal-write gate now requires a `withheld*` local to come from a recorder or a conduit parameter** | **FAIL. Defeated six ways, and two of them are ordinary.** `_withheld_json: str \| None = None` — *an annotated assignment, which is this module's own house style for `withheld*` locals* — is invisible to the scan and kills both the main `INSERT` and the orphan `UPDATE`. And **the clean finish, `:7424`, is still bindable to `None` with the gate green**, because `_emit_chat_turn` has no such local at all and the check only looks at `ast.Assign`. R13's G1 **is** closed; R13's G2 = R10's I13 is **four rounds open** | **production-reachable (regression channel), ×2** |
| 2 | **`[]`-not-cached now has a test; check the user door and the second call after a failed fetch** | **PASS on the fix and its guard; FAIL on the sibling.** C-B reds `test_AN_EMPTY_ADMIN_CATALOGUE_IS_NOT_CACHED` by name. **Both doors correctly re-dial after a *failed* fetch** — measured, and clean. The **user door still caches `[]` for 60 s** and a **non-empty admin catalogue is still pinned for the process's life** (1 → 3 → 5 tools, `dials=1` throughout) | production-reachable ×2 |
| 3 | **`_as_text`, the container drain, the dead branch, `arm_turn_surface` not raising — can each red, and for its stated reason?** | **PASS, all four, and this is the round's real advance.** X1, X3b, X2, X8 each red **exactly one named test**, and each test's name is the mechanism. **Four fixes that were at BASELINE last round are now guarded.** But the container fix **introduced a new one**: a non-list sink now loses **every** row silently, where R13's code recorded them | 1 new, adversarial |
| 4 | **the recursive `app/` sweep; find route eighteen; is there an entry point that does not look like one?** | **Route 17 CLOSED — verified four ways.** But the recursion **created route twenty**: the `arming` exemption is a bare-NAME closure and it now spans the whole package, so a same-named arming helper in **`app/agentruntime/`** absolves a real un-arming entry point (gate `6 passed`, control `2 failed`). And **route nineteen**: `if not isinstance(fn, ast.AsyncFunctionDef): continue` — a **sync `def`** entry point is invisible. R13's route eighteen (the `async with` false positive) is **unchanged** | **production-reachable ×3** |
| 5 | **the flag has no live consumer — still true? inert or untriggered?** | **STILL TRUE, and INERT rather than untriggered.** All three live reads (`:5642`, `:8176`, voice `:422`) precede all six drains; driven on the live order, the read answers `True` with the writer's `set` **and without it**. X7 is at **BASELINE**, one round after R13 reported it. Its only measurable production effects remain negative: the worker-thread leak re-drives to `True` on a clean sink | production (an inert floor); leaks adversarial/latent |

**Overall: FAIL.**

### Grading the choice of scope, which the prompt asks for first

**The choice was right, and there is measured evidence for it rather than a preference.** R13's
sharpest finding in this scope was not any individual defect — it was that **four of the round's
fixes survived their own deletion at exactly baseline**. This round shipped five guards and
**five of five red, each on exactly one named test, each for the mechanism the name states.** That is
the best guard ratio this scope has produced in six rounds, and it is what a deliberate narrowing of
scope is supposed to buy.

**But the production-reachable set is not closed, and the round's own headline overstates it.** Of
R13's production-reachable items in my scope:

| R13 item | status |
|---|---|
| the malformed-row branch was dead code | **CLOSED + guarded** ✅ |
| route seventeen (`app/agentruntime/` invisible) | **CLOSED**, verified 4 ways ✅ |
| `_NOT_A_TURN`'s `catalog.py` reason cites a deleted no-op | **CLOSED** ✅ |
| `[]`-not-cached had no test | **CLOSED + guarded** ✅ |
| the terminal-write gate (G1 **and** G2) | **HALF.** G1 reds; **G2 green, four rounds** ❌ |
| route eighteen — the gate reds on correct code | untouched ❌ |
| the user door caches `[]` for 60 s | untouched ❌ |
| a non-empty admin catalogue is pinned forever | untouched ❌ (four rounds) |
| the flag's writer is unguarded / has no live consumer | untouched ❌ |
| route sixteen (narrow-then-delegate) | untouched; and its mechanism is now **wider** ❌ |

**Four closed, one half, five untouched — and the commit message's account of the gate is not true of
two of the three functions it covers.** It reads *"It now requires such a local to be assigned from a
recorder call or derived from the parameter a conduit was handed."* `_emit_chat_turn` has **no such
local**; its bind is a positional argument, and the new machinery never looks at it. That is the
fourth-round survival of the single finding this scope has reported most often.

### The most valuable thing I found, which is what the prompt asked for

**Something in the OPEN set became production-reachable because of these changes, and it is in the
same directory the fix was about.** Closing route seventeen made `_turn_entry_calls` parse
`app/**/*.py`. The sweep's `arming` set — which **grants an exemption**, skipping a discovered entry
point entirely — is a fixed-point closure over **bare function names**, and it now closes over the
whole package instead of two flat directories. Measured:

```
files      old= 68   new=115
fn names   old=447   new=641
colliding names  old=19  new=29
```

```
R20a  a genuine un-arming entry point in app/services/            -> gate 2 failed   ✅ control
R20b  + a same-named ARMING helper in app/agentruntime/           -> gate 6 passed   ← ABSOLVED
      (a file the two-directory glob would never have parsed)        wide at baseline
```

The comment beside `_narrowing_helpers_multi` says over-approximating is *"the safe direction for a
gate"*. **That is true of `reaching`, which buys more scrutiny, and false of `arming`, which buys
less** — and the change that closed route seventeen multiplied `arming`'s collision surface by the
size of the package. **CP-2 is going to put an arming runtime, with helper names of its own, into
exactly `app/agentruntime/`.** Route seventeen was a finding about the future; its fix created
another one, in the same package, about the same future.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every fix in R13's delta that falls in my scope. `manifest.py` / `surface.py` are Verifier B's.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| `_as_text` forces a plain `str` (`instrument.py:284–286`) | **yes** — `test_AS_TEXT_RETURNS_A_PLAIN_STR__not_a_subclass` | **yes** — X1 (back to `str(value)`) reds **1 extra** | **yes.** The parameter is the exact class R13 named (`__str__` returning a `str` subclass), and the test also drives it through a real `absorb` to the dedupe key |
| `absorb` clears the REAL container (`:692–697`) | **yes** — `test_ABSORB_EMPTIES_THE_REAL_SINK__not_a_copy_of_it` | **yes** — X3b (R13's exact `sink = list(sink)` shape) reds **1 extra** | **yes**, and the test asserts the *consequence* (a second absorb must not duplicate), not just the mechanism |
| the malformed-row branch names the type (`:706–711`) | **yes** — `test_a_NON_DICT_row_names_what_it_actually_WAS` | **yes** — X2 reds **1 extra** | **yes** — asserts `"int" in reason` for a row of `42`, which is precisely the diagnostic R13 measured lost |
| `_is_catalogue_row` — exact type at the arm (`:370–373`) | **yes** — `test_ARMING_CANNOT_RAISE_ON_ANY_SINK_CONTENT` | **yes** — X8 (back to `isinstance`) reds **1 extra** | **yes for the ROW's type; NO for its VALUES.** See F5: the docstring says *"this cannot raise on any input"* and a plain dict whose `scope` value has a hostile `__eq__` **still takes the arm down** |
| `[]` is not cached on the admin door (`knowledge_client.py:735`) | **yes**, at last — `test_AN_EMPTY_ADMIN_CATALOGUE_IS_NOT_CACHED` | **yes** — C-B reds **1 extra** | **yes** — it asserts the *re-dial* (`calls["n"] == 2`) and the recovered catalogue, which is the permanence, not the emptiness. **Placed in `test_cp0_instrument.py`, so the doors suite is still `104 passed` under C-B** |
| the terminal-write gate's `bad_bindings` / conduit scan (`test_cp0_instrument.py:1528–1578`) | **it is the test** | **partly** — T1 reds, T8 (a conduit call-site literal) reds | **NO.** Six defeats measured, **T2 and T3 without contrivance.** The property asserted is one syntactic form, not "the column carries the recorder's value" |
| `_TURN_SCOPE_ROOT = "app"`, recursive (`:2027–2028`, `:2114–2122`) | **yes** — the gate's own sweep, plus `assert real` | **yes** — R17-now / -c / -d all red `2 failed` against the `app/services/` control | **yes for route 17**, and it is the round's best fix. **But it opened R20** (name-collision exemption) and did not touch **R19** (sync `def`) |
| `record_catalogue_unavailable` **sets** the flag (`:431`) | **NO**, unchanged from R13 | — | — **X7: neutering it leaves instrument at `2 failed, 115 passed` and wide at `2 failed, 324 passed` — BASELINE**, one round after R13 reported it |
| `arm_turn_surface` ADOPTS (`:354–357`) — R12's fix, re-checked | yes | **yes** — X4 reds (not re-injected this round; anchor non-unique, and the mechanism is byte-identical to R13's measurement) | yes |
| the flag is DERIVED (`:369`) | yes | **yes** — X5 reds **4 extra** (`…OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN`, `…EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE…`, and **two prompt-caching tests in `test_stream_service`** — the cross-suite signature the builder documented) | yes |
| `catalogue_outage_registered` reads the flag (`:448–449`) | yes, transitively | **yes** — X6 reds **1 extra** | yes |

---

## 3 · The falsifier, per claim — stated before the search

### 1 · The terminal-write gate, rewritten — **FAIL**

**Falsifier (stated first):** any way to stop a persisted `withheld_tools` column carrying the
recorder's value while the gate is green; and for each such way, whether an ordinary edit reaches it.

The three functions the gate covers, with what the new code actually checks:

| function | conduit? | what the gate checks |
|---|---|---|
| `stream_service.py::_persist_terminal_assistant` (6214–6411) | **yes** (`withheld_tools` param) | `bad_bindings` on its one `ast.Assign` **+** its call sites for a literal `withheld_tools=` keyword |
| `stream_service.py::_emit_chat_turn` (6491–7720) | no | **only** `reads_recorder` — *"does the word `withheld_json` or `absorb` appear anywhere in 1200 lines"*. It has **no `withheld*` Assign at all**, so `bad_bindings` is vacuous |
| `voice_stream_service.py::voice_stream_response` (215–839) | no | `reads_recorder`; likewise no Assign |

Baseline: term `1 passed`; wide `2 failed, 324 passed`.

| # | injection | ordinary or contrived? | term | wide |
|---|---|---|---|---|
| **T1** | `_withheld_json = None` at `:6341` — **R13's G1 verbatim** | — | **`1 failed`** ✅ | 1 extra ✅ |
| **T2** | `_withheld_json: str \| None = None` — the same defect as an **annotated** assignment | **ORDINARY REFACTOR** | **`1 passed`** | **baseline** |
| **T3** | `:7424`, the **clean finish**, binds `None` — **R13's G2 = R10's I13** | **not even a refactor** | **`1 passed`** | **baseline** |
| T4 | CONTROL — voice `:684` binds `None` | — | `1 failed` | 1 extra |
| T5 | `(_withheld_json := None)` — a walrus, no `Assign` node | contrived | `1 passed` | baseline |
| **T6** | `_wj_tmp = None` then `_withheld_json = _wj_tmp` | **ordinary** (two-line extraction) | `1 passed` | baseline |
| T7 | `_withheld_json, _unused = None, None` — tuple target | contrived | `1 passed` | baseline |
| **T8** | conduit **call site** `withheld_tools=None` at `:6970` | — | **`1 failed`** ✅ | 1 extra ✅ |
| T9 | conduit call site `withheld_tools=_nothing_at_all` (a module local `= None`) | contrived | `1 passed` | baseline |
| T10 | conduit call site `withheld_tools=(None if session_id else None)` | contrived | `1 passed` | baseline |

**A1 · T2 is the finding, because the module already writes it that way.** `bad_bindings` walks
`ast.Assign` and nothing else. An `ast.AnnAssign` — a local with a type annotation — is invisible.
And annotated is **this file's own house style for exactly these locals**:

```
stream_service.py:1956   _budget_withheld: list[dict] = []      in _stream_with_tools
stream_service.py:2192   _withheld_now: list[dict] = []         in _stream_with_tools
```

So the single edit that defeats the round's headline gate fix is *"add a type annotation, the way the
two neighbouring `withheld*` locals already have one"*, and it lands `NULL` in `withheld_tools` on
both the main `INSERT` (`:6390`) and the orphan `UPDATE` (`:6303`) with CI green.
**Reachability: production-reachable as a regression channel.**

**A2 · T3 is the same finding four rounds later, and the commit's account of it is untrue.** The
commit reads *"It now requires such a local to be assigned from a recorder call or derived from the
parameter a conduit was handed."* `_emit_chat_turn` has no such local. Its bind is the positional
argument at `:7424`, and the only obligation the gate places on that function is that the string
`withheld_json` appears **somewhere** in it — which it does, four more times, at `:6970`, `:7132`,
`:7592` and `:7633`. Replacing `:7424` with `None` leaves all four standing.
**This is the path every successful turn takes.** R10 reported it as I13; R11, R12 and R13 each
re-measured it green; the round that rewrote the gate did not move it.
**Reachability: production-reachable as a regression channel.**

**A3 · The matched control reds for the wrong reason, so it is not evidence.** T4 (voice `:684` →
`None`) reds — but `:684–685` are the **only** `withheld_json()` calls in `voice_stream_response`, so
removing them flips `reads_recorder` to `False` and the offender message is *"writes the column and
never reads a recorder"*, not *"binds a literal"*. **No test in the tree asserts the per-bind
property for any of the three writers.**

**The honest form is unchanged from R11 §8, R12 §8 and R13 §3.4**, and the conduit half of this round
shows the builder can write it: assert **per bind expression** — over each `execute` / `fetchrow` /
`fetchval` whose SQL names the column, that the argument at the column's position contains
`withheld_json()` or a local transitively derived from it. That reds T1, T2, T3, T5, T6, T7 and T4,
and does not red a parameterised column name (R12's G5 false positive).

### 2 · `[]`-not-cached, the user door, and the second call after a failure — **PASS / FAIL / CLEAN**

**Falsifier:** the `[]`-not-cached fix having no guard; either door serving a stale answer when the
gateway's catalogue has changed; a *failed* fetch being cached.

Driven against the real `KnowledgeClient` with a stubbed MCP transport, one armed turn per row,
counting real dials at `session.initialize`:

```
ADMIN — [] then recovery  (this round's fix + its new test)
  turn 0: gateway offers 0 -> got 0  dials=1  outage=False
  turn 1: gateway offers 1 -> got 1  dials=2  outage=False     ← [] re-dialled ✅
  turn 2: gateway offers 3 -> got 1  dials=2  outage=False     ← non-empty PINNED

ADMIN — non-empty then GROWTH   (R11's A3, four rounds)
  turn 0: 1 -> got 1  dials=1 | turn 1: 3 -> got 1  dials=1 | turn 2: 5 -> got 1  dials=1

ADMIN — a FAILED fetch, then a healthy gateway
  turn 0: FAIL -> got 0  dials=1  outage=True  ✅
  turn 1: 2    -> got 2  dials=2  outage=False ✅  ← a failure is NOT cached

ADMIN — success, then the gateway DIES
  turn 0: 2 -> got 2  dials=1 | turn 1: FAIL -> got 2  dials=1  outage=False | turn 2: same

USER — [] then recovery   (the SAME shape, unfixed)
  turn 0: 0 -> got 0  dials=1 | turn 1: 1 -> got 0  dials=1 | turn 2: 3 -> got 0  dials=1

USER — a FAILED fetch, then a healthy gateway
  turn 0: FAIL -> got 0  dials=1  outage=True ✅ | turn 1: 2 -> got 2  dials=2 ✅
```

* **The fix works and is now guarded.** C-B (`if self._admin_tool_definitions is not None:`) reds
  `test_AN_EMPTY_ADMIN_CATALOGUE_IS_NOT_CACHED` — the finding R13 recorded is **CLOSED**. The test
  asserts the re-dial and the recovery, not the emptiness, which is the right property. Its one
  weakness is placement: it lives in `test_cp0_instrument.py`, so the doors suite is still
  `104 passed` under C-B and a `knowledge_client` reader will not find it beside the code it guards.
* **The second call after a *failed* fetch is CLEAN on both doors.** A failure writes neither cache
  and the next call re-dials, and the outage is registered on the failing turn only. This is the one
  thing in this claim that needed no correction, and it needed the check.
* **The user door still caches `[]` for the full 60 s.** One zero-tool answer and the next turn's
  model gets no tools while the gateway is healthy, with no outage registered — correctly, because
  there was none. Same shape as the admin bug, bounded by a TTL rather than by the process's life.
  **Production-reachable.**
* **A non-empty admin catalogue is still pinned for the life of the process.** `1 → 3 → 5` tools with
  `dials=1` throughout, and `success → FAIL → FAIL` never even discovers the outage because the
  cache short-circuits before the dial. R11's A3, **four rounds, three verifiers**, unmentioned.
  **Production-reachable.**

### 3 · The four guards — **PASS ×4, with one new defect**

**Falsifier:** any of the four fixes surviving its own deletion; any test that reds for a reason other
than the one its name states; any row or sink shape that still crashes, or that is recorded as
something other than what it was.

All four red, each on exactly one named test, each for its mechanism. **X1, X2, X3b and X8 are the
answer to R13's central finding and they are a real answer.** Two residuals:

**B1 · NEW, and introduced by this round's fix: a non-list sink now loses EVERY row, silently.**

```python
try:
    rows_in = list(sink)
    del sink[:]
except Exception:
    rows_in, _ = [], None
```

The read and the clear are in the **same `try`**, so a container that resists `del` discards the rows
that were already read successfully. Measured through a real recorder:

```
tuple sink, 1 row in                       -> withheld_json() is None      (R13's code RECORDED it)
generator sink, 1 row in                   -> None
list subclass forbidding __delitem__       -> None, and the sink still holds its row
```

The comment says *"Read defensively, then clear the real container."* The code throws the read away
when the clear fails. R13's version double-recorded these rows, which was the defect; this version
**loses** them, which is the one outcome the recorder exists to prevent. The fix is one line — keep
`rows_in` in the `except` and skip only the clear. **Reachability: adversarial-input only** — I
enumerated the producers: `bind_sink` is called at `stream_service:6590` and `voice_stream_service:243`
with plain lists, and `absorb` at `:6987` (the ContextVar's list) and `:6998` (a list comprehension).
But it is a strict behavioural **regression** against the previous artifact on inputs the previous
artifact handled.

**B2 · `count` still admits a bool.** `isinstance(row.get("count"), int)` is `True` for `True` and
`False`. Measured: `{"count": False}` reaches the jsonb as `'count': False`. `count is not None`
exists precisely because *absent is not zero*; `false` is a third thing that is neither. R12's
finding, **four rounds**, unanswered and unmentioned. **Adversarial-input only.**

**B3 · `_as_text` is genuinely closed.** `_as_text(Sneaky())` and `_as_text(NoHash("x"))` both return
`type … is str`; a `__str__` that raises returns `<unrepresentable Recursive>`. R13's B1 is fixed at
the class, not the instance.

### 4 · The recursive sweep, route eighteen, and the entry point that does not look like one — **FAIL**

**Falsifier:** any construction that puts a narrowing above an arming, or a narrowing entry point with
no arming, while the gate is green; any exemption granted on a false basis; any correct code the gate
reds.

**Route seventeen is CLOSED, and it is verified in four places, not one.** Baseline gate `6 passed`.

| where the byte-identical entry point lives | discovered? | gate |
|---|---|---|
| `app/services/` — CONTROL | yes | **`2 failed`** ✅ |
| **`app/agentruntime/`** — R13's route seventeen | **yes** | **`2 failed`** ✅ |
| `app/client/` — R13's third directory | **yes** | **`2 failed`** ✅ |
| **`app/agentruntime/runtime/turns/`** — arbitrary depth | **yes** | **`2 failed`** ✅ |

**C1 · Route twenty — created by the fix, in the package the fix was about.** See §1's headline.
`arming` is a fixed-point closure over **bare function names**, and an entry point whose name lands in
it is `continue`d out of the sweep entirely. The name index went from 68 files / 447 names / 19
colliding names to **115 / 641 / 29**. Today `arming` still holds the same 6 names, so this is
**latent-not-live** in the current tree — and it is **production-reachable by construction**, exactly
as route seventeen was, because the code that will collide has not been written yet and
`app/agentruntime/` is where it is scheduled to go. The asymmetry is the point: `reaching`
over-approximates toward more scrutiny; `arming` over-approximates toward an **exemption**. The
positional form (an entry point is covered only if the call that arms *precedes* every narrowing in
*that* function, resolved by module, not by name) is the same correction R13 asked for on the
delegation exemption.

**C2 · Route nineteen — the entry point that does not look like one.** `_turn_entry_calls` contains
`if not isinstance(fn, ast.AsyncFunctionDef): continue`. Measured, with a matched control:

| probe | discovered? | gate | wide |
|---|---|---|---|
| `async def probe_turn` in `app/services/` — CONTROL | yes | `2 failed` ✅ | — |
| **the same body as `def probe_turn_sync`** | **no** | **`6 passed`** | **baseline** |

This is not a hypothetical shape. FastAPI runs a `def` path operation in a threadpool; the whole
narrowing API (`record_surface_withheld`, `record_catalogue_unavailable`, `catalogue_outage_registered`)
is synchronous; and `app/routers/` already registers sync callables through the framework —
`internal.py:40 require_internal_token`, a `Depends` dependency, which is the *"reached only through a
framework registration"* half of the question. **It also compounds with claim 5's leak**: a sync entry
point both evades the gate and sets its `ContextVar` on a pooled worker thread that has no
per-request context copy. **Production-reachable as a blind spot.**

**C3 · R13's route eighteen — the false positive — is unchanged, and I re-drove it rather than
reading it.** Moving the voice arm inside `async with contextlib.AsyncExitStack():` at the top of the
body — a perfectly ordinary resource-scoped arm — gives **`1 failed`**:
`test_EVERY_DISCOVERED_entry_point_arms_exactly_once_and_unconditionally`. `top_level_arm_lines`
accepts only `ast.Expr` and `ast.Assign` at `fn.body` depth. R11's warning stands: a guard that reds
on correct code is a guard that gets deleted, and this one has now survived two rounds after being
reported. **Production — a false positive on correct code.**

**C4 · The `_NOT_A_TURN` reason for `catalog.py` is corrected, and correctly.** It now states the true
reason (no model is offered anything) and states what the exemption *costs* (one sink allocated per
picker request and discarded with the context) rather than claiming zero. That is the right shape for
an exemption and worth naming.

### 5 · The flag's live consumer — **STILL NONE, and the fix is INERT**

**Falsifier:** any production read of `catalogue_outage_registered()` that follows a drain; any way
neutering `catalogue_outage.set(True)` changes what a live read answers.

The line map, re-derived this round:

```
stream_response          arm :5003 → fetch → READ :5642 → _emit_chat_turn :6132
_emit_chat_turn          recorder :6576 → adopt+bind_sink :6583–6590 → drains :6970/:6987/:6998/:7132/:7424/:7592/:7633
resume_stream_response   arm :7749 → fetch → READ :8176 → _emit_chat_turn :8181
voice_stream_response    arm :237  → fetch → READ :422  → drain :684
```

**All three live reads precede all six drains.** Driven on that exact order against the real
functions:

```
with the writer's set:   read=True  rows=1   (a post-drain read would be True)
writer's set NEUTERED:   read=True  rows=1   (a post-drain read would be False)
```

The two answers differ **only** at a line that does not exist. X7 confirms it from the other side:
neutering the writer leaves instrument at `2 failed, 115 passed` and wide at `2 failed, 324 passed` —
**baseline**, unchanged from R13.

**So: inert, not merely untriggered.** "Untriggered" would mean a real consumer that this corpus
happens not to exercise. There is no consumer at all — the sink-scan fallback at `:446–449` answers
identically at every live read site, on every construction order any live path produces. A correctness
floor with no consumer is defensible in itself; what is not is that the floor's **only** measurable
production effects are negative, and they are still there:

```
req_A on worker 1 (a real outage, drained)  -> catalogue_outage_registered() = True
req_B on worker 1 (NO outage, empty sink)   -> catalogue_outage_registered() = True   ← leak
```

and

```
narrow → drain → arm   ->  row PERSISTED = 1,  flag after the arm = False   ← a real outage erased
```

The second is R13's claim-2 mechanism: `arm_turn_surface`'s derivation is a **write**, so it can only
*lower* the flag. Both were recorded OPEN and both are unchanged. `catalogue_outage.set(True) if
any(...) else <leave>`, or deriving in the reader rather than the writer, has neither failure.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | **`_withheld_json: str \| None = None`** — an annotated assignment, the module's own style | ✅ T2, term `1 passed`, wide baseline | **production (regression channel)** |
| " | **`:7424` the clean finish binds `None`** — no local, so `bad_bindings` never looks | ✅ T3, term `1 passed`, wide baseline | **production (regression channel)** |
| " | a two-step `_wj_tmp = None; _withheld_json = _wj_tmp` (allowed by `not isinstance(n.value, ast.Name)`) | ✅ T6 | production (ordinary edit) |
| " | a walrus / a tuple target | ✅ T5, T7 | adversarial |
| " | a conduit call site passing a local or a param-mentioning ternary | ✅ T9, T10 | adversarial |
| the control proves the property | voice reds because it lost its **only** recorder call, not because the bind is a literal | ✅ T4 offender text | — (evidential) |
| arm-order gate · no narrowing precedes the arming | **a same-named ARMING helper anywhere under `app/`** absolves a real entry point | ✅ R20b, gate `6 passed`, control `2 failed` | **production, by construction** |
| " | **a SYNC `def` entry point** — `AsyncFunctionDef` only | ✅ R19, gate `6 passed`, control `2 failed` | **production (blind spot)** |
| the gate does not red on correct code | a top-level arm inside `async with` reds as *conditional* | ✅ R18, `1 failed` | production (false positive) |
| `absorb` records what the sink held | a **non-list** sink (tuple / generator / undeletable subclass) loses **every** row | ✅ B1, 1 row → `None` | adversarial (**new this round**) |
| the arming cannot raise on any input | a **plain dict** whose `scope` value has a hostile `__eq__` | ✅ `RuntimeError` at `arm_turn_surface` | adversarial |
| the outage reader cannot raise | `catalogue_outage_registered` still does a bare `e.get(...)` at `:449` | ✅ `AttributeError` on `42`/`None`/`"x"`, `RuntimeError` on a hostile subclass | adversarial |
| `count` is absent-or-a-count | `count: false` persists | ✅ | adversarial |
| the outage fact does not outlive its turn | a **pooled worker thread** keeps `True` for the thread's life | ✅ re-driven | adversarial/latent |
| the row and the notice cannot contradict | `narrow → drain → arm` — the arm **lowers** a true flag | ✅ re-driven | latent |
| the flag survives a drain | nothing reads it after one | ✅ line map + X7 | production (inert) |
| the user door's `[]` is not cached | it is, for 60 s | ✅ | **production** |
| a non-empty admin catalogue is refreshed | it never is | ✅ 1 → 3 → 5, `dials=1` | **production** |
| a failed fetch is not cached | **none — both doors re-dial** | ✅ | — (clean) |

---

## 5 · The red-ability table

Baseline for every row: **the fresh scratch copy**. `term` = `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE…`
alone (**`1 passed`**); `gate` = `TestTheTurnSinkIsArmedBeforeAnythingNarrows` (**`6 passed`**);
`instr` = `test_cp0_instrument.py` (**`2 failed, 115 passed`**); `wide` = the 7-suite set
(**`2 failed, 324 passed`**); `doors` = `test_knowledge_client` + `test_admin_surface`
(**`104 passed`**). "extra" counts failures **beyond** the two copy artefacts. Every injection was
applied to the scratch copy, **verified present by a source-content assertion printed before the
run**, and reversed by restoring a pristine snapshot — never `git checkout`.

| # | injection | what it models | result |
|---|---|---|---|
| **X1** | `_as_text` back to `str(value)` | R12's finding #3 / R13's B1 | **1 extra** ✅ `test_AS_TEXT_RETURNS_A_PLAIN_STR__not_a_subclass` |
| **X2** | delete the malformed-row `reason` | R13's B3 (the dead branch) | **1 extra** ✅ `test_a_NON_DICT_row_names_what_it_actually_WAS` |
| **X3** | `rows_in = list(sink)` + `while sink: sink.pop(0)` | a *near-miss* reversion — still drains the real sink | **BASELINE** (my injection, not a finding) |
| **X3b** | R13's exact shape: rebind `sink = list(sink)`, drain the copy | R13's B2 | **1 extra** ✅ `test_ABSORB_EMPTIES_THE_REAL_SINK__not_a_copy_of_it` |
| **X8** | `_is_catalogue_row` back to `isinstance` | R13's B4, half of it | **1 extra** ✅ `test_ARMING_CANNOT_RAISE_ON_ANY_SINK_CONTENT` |
| **C-B** | cache `[]` on the admin door again | R13's finding 6 | **1 extra** ✅ `test_AN_EMPTY_ADMIN_CATALOGUE_IS_NOT_CACHED`; **doors still `104 passed`** |
| X5 | the flag is left alone when adopting | the disclosed self-introduced leak | **4 extra** ✅ incl. 2 in `test_stream_service` |
| X6 | `catalogue_outage_registered` stops reading the flag | the drained-sink read | **1 extra** ✅ |
| **X7** | `record_catalogue_unavailable` stops setting the flag | **the flag's WRITER** | **BASELINE — GREEN**, unchanged from R13 |
| **T1** | `_withheld_json = None` at `:6341` | **R13's G1** | **term `1 failed`, wide 1 extra** ✅ **CLOSED** |
| **T2** | `_withheld_json: str \| None = None` | the same defect, **annotated** | **term `1 passed`, wide baseline — GREEN** |
| **T3** | `:7424` clean finish binds `None` | **R13's G2 = R10's I13** | **term `1 passed`, wide baseline — GREEN** |
| T4 | CONTROL — voice `:684` binds `None` | R10's I4 | `1 failed` ✅ **but for the wrong reason** |
| T5 | `(_withheld_json := None)` | a walrus | GREEN |
| T6 | `_wj_tmp = None` then `_withheld_json = _wj_tmp` | a two-line extraction | GREEN |
| T7 | `_withheld_json, _unused = None, None` | a tuple target | GREEN |
| **T8** | conduit call site `withheld_tools=None` | the new call-site scan | **`1 failed`** ✅ **CLOSED** |
| T9 | conduit call site `withheld_tools=_nothing_at_all` | the same, one hop | GREEN |
| T10 | conduit call site `withheld_tools=(None if session_id else None)` | the param-mention escape | GREEN |
| **R17-now** | an entry point in `app/agentruntime/` | **R13's route seventeen** | **gate `2 failed`** ✅ **CLOSED** |
| R17-ctl / -c / -d | `app/services/`, `app/client/`, 3 levels deep | the matched controls | all `2 failed` ✅ |
| **R19** | the same entry point as a **sync `def`** | **route nineteen** | **gate `6 passed`, wide baseline — GREEN** |
| R20a | a genuine un-arming entry point in `app/services/` | the matched control | **gate `2 failed`** ✅ |
| **R20b** | + a same-named **arming** helper in `app/agentruntime/` | **route twenty** | **gate `6 passed`, wide baseline — GREEN** |
| R18 | a top-level arm inside `async with` | R13's route eighteen | **`1 failed` — FALSE POSITIVE**, unchanged |

**T2, T3, R19, R20b and X7 are the block that decides this round.** Two of them defeat the fix this
round's commit message leads with, one of them is the path every successful turn takes, two are new
holes in the gate the round widened, and one is R13's finding re-measured unchanged.

---

## 6 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| the terminal-write gate's `bad_bindings` | the **other two** SQL writers, which have no `withheld*` Assign | classified all three by AST | **NO** — `_emit_chat_turn` and `voice_stream_response` are checked only for the *presence of a word* |
| " | assignment forms other than `ast.Assign` | drove AnnAssign, walrus, tuple, two-step | **NO — four more, two ordinary** |
| " | whether the control proves the property | read the offender message T4 produces | **NO** — it reds on `reads_recorder`, not on the bind |
| " | the conduit call-site scan's own siblings | drove a local and a ternary | **NO** — literal keyword only |
| `[]`-not-cached | whether the **user** door has the shape | drove U0→U2 across a recovering gateway | **NO** — 60 s, no re-dial |
| " | a **non-empty** stale admin value | drove A0→A2 across a growing gateway | **NO** — pinned forever, four rounds |
| " | whether a **failed** fetch is cached at either door | drove FAIL→healthy on both | **YES — clean on both** ✅ |
| " | whether the new test sits with the code it guards | ran `doors` under C-B | **NO** — still `104 passed`; the test is in the instrument suite |
| `_is_catalogue_row` (the arm) | the **other line R13 named**, `catalogue_outage_registered:449` | drove `42`/`None`/`"x"`/hostile subclass | **NO — still raises**, and the new helper sits three lines above it |
| " | whether bounding the row's **type** bounds its **values** | drove a plain dict with a hostile `__eq__` | **NO — the arm raises**, and the docstring says it cannot |
| " | whether reversing the comparison would fix it | measured all three forms | **NO** — `"catalogue" == v` raises too; `type(v) is str and v == …` is the form that holds |
| the container drain | whether clearing can fail after the read succeeds | drove tuple / generator / undeletable subclass | **NO — every row is lost**, a new defect |
| the recursive sweep | whether widening the tree widened an **exemption** | counted the name index, then drove R20a/R20b | **NO — route twenty** |
| " | whether an entry point must be `async` | drove the sync twin against the async control | **NO — route nineteen** |
| " | whether the false positive was addressed | re-drove `async with` | **NO** — `1 failed`, unchanged |
| the flag | whether the **writer** is guarded yet | X7 | **NO — baseline**, second round |
| " | whether any live read is after a drain | re-derived the line map, then drove the live order with and without the set | **NO live consumer** — the fix is inert |
| `count` | `True` / `False` | drove both | **NO** — `count: false` persists, four rounds |

---

## 7 · Where the builder's documentation of a residual is incomplete or wrong

1. **The commit's account of the gate is untrue of two of the three functions it covers.** *"It now
   requires such a local to be assigned from a recorder call or derived from the parameter a conduit
   was handed."* `_emit_chat_turn` and `voice_stream_response` have **no such local**; their binds are
   positional arguments, and the only obligation on them is that the word `withheld_json` appears
   somewhere in the function. The sentence is true of `_persist_terminal_assistant` and of nothing
   else, and the clean finish — the path every successful turn takes — is the site it is false about.
2. **`_is_catalogue_row`'s docstring states an impossibility that is false.** *"Exact type, and no
   user code on the path… so this cannot raise on any input."* `type(row) is dict` bounds the
   container; `row.get("scope") == SCOPE_CATALOGUE` then runs the **value's** `__eq__`. Measured:
   `arm_turn_surface` raises `RuntimeError` on `{"scope": <hostile __eq__>}` — at the first statement
   of every turn entry point, which is the exact reason the fix was written. **Crash re-created inside
   its own fix, sixth occurrence, inside the function written to close the fifth.** And R13 named
   **two** lines; `catalogue_outage_registered:449` still carries the unguarded `.get`.
3. **`absorb`'s new comment describes a guard that loses what it was protecting.** *"Read defensively,
   then clear the real container."* The read and the clear share one `try`, so a container that
   resists the clear discards the rows the read already produced. R13's version double-recorded them;
   this one loses them. `except: pass` over the clear alone is the version that keeps the stated
   property.
4. **The board's "Open and recorded" list is stale in the safe direction and right by accident.** It
   names *"the terminal-write gate's `Name` hatch"* as OPEN while the same delta rewrote the gate. The
   label happens to remain correct — T2 and T3 are green — but the board does not record that the
   rewrite happened, so a reader cannot tell that the item has been *attempted and missed* rather than
   *deferred*.
5. **The route-17 comment claims a property the change does not deliver.** *"`app/` recursively… so a
   new package is IN scope by default and leaving it out is a decision someone writes down."* A new
   package is in scope for **discovery** and simultaneously in scope for the **`arming` exemption**,
   which is granted by bare name across the whole tree. A file in the new package can now remove an
   entry point from the gate without anyone writing anything down. The neighbouring comment —
   *"over-approximating on purpose… the safe direction for a gate"* — is true of `reaching` and false
   of `arming`, and the two sit fifteen lines apart.
6. **`test_ARMING_CANNOT_RAISE_ON_ANY_SINK_CONTENT` names a property broader than it tests.** The name
   says *any sink content*; the parameters are `[Hostile(), 42, None, "x"]` — four **row** shapes, no
   hostile **value**. One more entry, `{"scope": BadEq()}`, would red it today.
7. **Exemplary, and it is the round's real achievement.** Five guards, five red, each on exactly one
   named test, each for the mechanism the name states — including a cross-suite red (X5 takes two
   prompt-caching tests in `test_stream_service`) that the builder had already documented as the
   diagnostic signature. R13's central finding was four fixes at baseline; **that finding is closed,
   at the class.** The `[]`-not-cached test asserts the *permanence* rather than the emptiness, which
   is the distinction three previous rounds got wrong. And the `_NOT_A_TURN` reason was rewritten to
   state the true justification **and** what the exemption costs, instead of claiming zero — which is
   the right shape for an exemption and the first time one in this file has had it.

---

## 8 · What would have to be true for this to PASS

* **The terminal-write gate must anchor per BIND, not per assignment form.** Over each
  `execute`/`fetchrow`/`fetchval` whose SQL names `withheld_tools`, assert that the argument at the
  column's position contains `withheld_json()` or a local transitively derived from one. That reds
  T1–T7 and T4-for-the-right-reason. **This is unchanged from R11 §8, R12 §8 and R13 §3.4**, and the
  conduit half of this round proves the builder can write the harder version.
* **`:7424` needs a test that reds when it binds `None`.** It is the path every successful turn takes
  and it has been green for four rounds.
* **`catalogue_outage_registered:449` must use `_is_catalogue_row`.** The helper exists, three lines
  above, and was written for this.
* **`_is_catalogue_row` must bound the VALUE too:** `type(v) is str and v == SCOPE_CATALOGUE`
  (measured — reversing the operands does not help). And the test needs the fifth parameter.
* **`absorb`'s `except` must keep `rows_in`** and skip only the clear, so a container that resists
  deletion degrades to R13's behaviour rather than to silence.
* **`arming` must be positional and module-scoped, not a bare-name closure over `app/**/*.py`** — this
  is the one finding here that is guaranteed to bite, for the same reason route seventeen was: the
  code it will hide is scheduled to be written in `app/agentruntime/`.
* **The sweep must consider `ast.FunctionDef` as well as `ast.AsyncFunctionDef`**, and
  `top_level_arm_lines` must accept a `With`/`AsyncWith` body at depth 1 so it stops reddening correct
  code.
* **`record_catalogue_unavailable`'s flag set needs a test that drives a read AFTER a drain** — the
  only situation the flag exists for, and X7 shows nothing does. Or the flag should be reconsidered:
  it is **inert**, and its only measurable production effects are the thread leak and the
  `narrow → drain → arm` erasure.
* **`arm_turn_surface` must not be able to lower a set flag.**
* **The user door needs the `[]` fix, the admin catalogue needs a TTL, and `count` needs
  `type(...) is int`.** Four rounds, four verifiers, hand-measured each time.

---

## 9 · Convergence, for my scope

| round | production-reachable | adversarial-input only |
|---|---|---|
| 10 | 13 | 1 |
| 11 | 17 | 1 |
| 12 | 22 | 2 |
| 13 | 13 | 5 |
| **14** | **9** | **6** |

**The first fall, and it should be read with its caveat**: this round's prompt scoped me to R13's
delta and five questions, which is narrower than R13's brief, so part of the fall is the scope and not
the code. What is **not** scope-dependent is the guard ratio — 5 of 5 red for their reason, against
R13's 4 of 8 — and that is the number that says the round did something the previous four did not.

**Findings introduced by the previous round's fixes: 2 of 15, one of them production-reachable**
(route twenty, from the route-seventeen fix; the non-list-sink loss, from the container-drain fix).
That is the same ratio R13 measured across R11–R13 (3 introduced, 2 production-reachable). **The
introduction rate has not fallen, and it is the term that decides whether this loop terminates**: a
round that closes four and opens two nets two, and there were nine open in this scope before it
started.

`git rev-parse HEAD` at start: `b30db5b8099a93fdf7ba7fafcb19a62747604672`.
`git rev-parse HEAD` before writing: `b30db5b8099a93fdf7ba7fafcb19a62747604672`.
