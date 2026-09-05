# CP-1 · round 16 · V-CODE — Verifier A (the instrument)

*Artifact frozen at `d23ea559294ae2daa4fa1414d87b734d2e1e2479`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move**, and
`git status --porcelain` over `services/chat-service` is **empty** at both ends. I wrote no tracked
file other than this one, ran no `git checkout`, and touched nothing live.*

**One fresh scratch tree, proved un-nested before anything ran.** `…/scratchpad/r16a/cs`, with two
snapshots I took myself: `…/r16a/pristine` (restore source) and `…/r16a/prev` (the **previous
artifact's** `instrument.py` from `cba800fa8` dropped onto the delta's tests, for the head-to-head in
§5). The path was decomposed and **every ancestor component** checked against the twenty-two
directory names this scratchpad already carried (`cs`, `cs-pristine`, `r12`, `r13cs`, `r13pristine`,
`r14a`, `r15a`, `r15b`, `repo`, `pkgcopy`, `mt`, `mt11`, `inj`, `probe`, `head`, `audit`, `gochk`,
`sb`, `vb`, `vlive_r5`, `snap`, `__pycache__`) — **zero stale ancestors**, and `r16a` is proved not to
have pre-existed. Only the leaf is `cs`, which is not a nesting. Five files were then sha256-compared
against the artifact and printed **EQUAL**. Every injection asserted its own text **present on disk,
read back after the write**, before its suite ran; every anchor was asserted unique; reversal is
always a restore from my snapshot.

My baselines, measured this session: `instr` = `tests/test_cp0_instrument.py` → **`2 failed, 124
passed`** (the two copy artefacts rounds 10–15 identified); `term` → **`1 passed`**; `gate` =
`TestTheTurnSinkIsArmedBeforeAnythingNarrows` → **`6 passed`**; the two new classes → **`4 passed`**
and **`5 passed`**. R15's `instr` baseline was `2 failed, 115 passed`; **this delta added nine tests**,
which is the first round in three where my scope gained an assertion at all.

---

## 1 · Verdict

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the per-bind terminal-write gate; find T8; grade the NV** | **PASS on the gate — T8 FOUND, and it is the module list.** T1–T7 all red (`1 failed` each), including **T3 (`:7424`, seven rounds) and T6**. Ten in-module defeats red: alias ×2, `*args`, `**kwargs`, a returning helper, `executemany`, a renamed executor, SQL across one **and** two locals, a lost writer, a gained writer. **T8 = a fourth writer in ANY third module.** `_mods` is a hardcoded 2-tuple; probes in `app/services/`, `app/routers/` **and `app/agentruntime/`** each bind `None` at **`1 passed`** | **production-reachable — CP-2's runtime is scheduled for `app/agentruntime/`** |
| 2 | **routes 21/22 deleted; `discovery_seed_for_surface` allow-listed with a stated reason; find route 23** | **PASS on the deletions and on the reason — ROUTE 23 FOUND, three variants.** Routes 21/22 are gone and guarded by new tests. The reason for the new entry is **true of the code** (verified by line number, §4.2). **Route 23 = the delegation exemption**, which is **ordering-blind, dead-branch-blind and liveness-blind**: narrow-then-delegate, a delegating call under `if False:`, and one inside a never-called nested `def` are each **`6 passed`** against a control at **`2 failed`** | **production-reachable by construction** |
| 3 | **route 18 fixed by accepting `With`/`AsyncWith` at depth 1; `If`/`Try` deliberately not widened** | **PASS on `async with` — FAIL on the line.** W1 green (route 18 closed, third round). But an arm that is the **first statement of a `try:` body** — nothing precedes it, so nothing can stop it — reds `1 failed`: **the same false-positive-on-correct-code, in a new spelling.** And the stated reason for excluding `Try` is **falsified by the widening itself**: a `with` whose `__enter__` raises is accepted as unconditional (W3, `6 passed`) though the arm provably never runs | **production-reachable (false positive)** |
| 4 | **the outage fact moved onto the recorder; is it better than the boolean, or merely different?** | **FAIL — measured head-to-head, it is WORSE.** Six orderings, same probe, both trees: **identical on four, strictly worse on two** (a second recorder in one turn; a background task that drains), **better on none I could construct.** And the guard written for it — `test_the_outage_survives_the_DRAIN__and_does_not_outlive_the_TURN` — is **GREEN on `cba800fa8`'s `instrument.py`**, the exact artifact the rehousing replaced | **production (the leak survives); the regression is latent-not-live** |
| 5 | **the container `try` split; `count` is `type(...) is int` at three doors, one recorded redundant** | **PASS, and the annotation is HONEST — verified, not accepted.** The split is real (tuple/generator/undeletable all record; re-merging reds). Doors 1 and 3 each red **alone**. Door 2 is **green when weakened AND green when deleted outright** — exactly what the comment says. **Keep it**: unlike the flag it replaced, it cannot produce a second, contradictory answer | — **CLOSED** |
| 6 | **convergence, per changed line** | **Closure 75% (9 of R15's 12), the highest of the series. Introduced 5 — a raw rise, but 0.68/100 changed lines, the LOWEST of the four measured rounds** | see §9 |

**Overall: FAIL.** But this is a materially different failure from R15's. Five of six claims pass on
their stated half; nine of my predecessor's twelve findings are closed, including `:7424` after seven
rounds; and for the first time the round shipped tests over its own fixes. It fails on three things:
**T8 and route 23 are the same structural defect as the ones just closed, one level out**; **the
headline change of the round is a measured regression with a vacuous guard**; and three
strengthenings ship silent.

### The most valuable thing this round produced, which the prompt asked for

**The rehousing is not an improvement — it is a lateral move with two regressions, and its guard
cannot see the difference.** I ran the identical six-ordering probe against the previous artifact and
against the delta (§5). Four orderings are byte-identical in outcome; two got worse; none got better.
Then I ran the delta's own new guard against the previous artifact's `instrument.py`: **`1 passed`.**
The other three guards in that same class correctly red on the previous artifact. The one guarding the
largest structural change in the delta is the one that cannot see it.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every fix in the graded delta that falls in my scope. `contract.py` / `manifest.py` / `surface.py`
are Verifier B's. "Red-able" = the strengthening reverted **alone**, whole `instr` suite run.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| the terminal-write gate re-anchored **per BIND** (`test_cp0_instrument.py:1516–1637`) | **it is the test** | **yes** — T1–T7 all `1 failed`; T3 and T6 closed | **yes, for ten in-module defeats.** **NO for a third module** — §3.1's T8 |
| the NV: three named writers + `len(binds_checked) >= 4` (`:1623–1632`) | it is the test | **yes** — an aliased executor is caught **only** by the NV (G14′ green without it, G14″ red with it) | **yes for LOSING a writer; NO for GAINING one.** Both bounds are floors |
| routes 21 + 22 deleted (`:2256–2284`) | **yes** — two new tests, both real | **yes** — each reds on the previous artifact's gate | **yes.** This is the round's cleanest work |
| `_NOT_A_TURN` += `discovery_seed_for_surface` with a reason | **yes**, `test_NO_ALLOW_LIST_ENTRY_IS_STALE`; the entry **is** discovered | **yes** | **yes on the conclusion; one premise is inert** — §4.2 |
| `_unconditional` accepts a `With`/`AsyncWith` body at depth 1 (`:2315–2321`) | **yes** — `test_a_TOP_LEVEL_ARM_INSIDE_AN_ASYNC_WITH_is_not_CONDITIONAL` | **yes** — G15 reverts it → `3 failed` | **yes for `with`. The line itself is wrong** — §3.3 |
| the outage fact rehoused onto the recorder | **yes** — `test_the_outage_survives_the_DRAIN…` | **G02/G03/G04 red**, so the *plumbing* is guarded | **NO for the CHANGE.** The test is **`1 passed` on the artifact the change replaced** |
| `_is_catalogue_row` bounds the VALUE (`type(v) is str`) | **yes** | **yes** — G06 `3 failed` | **yes** ✅ |
| `catalogue_outage()` bounds the value "for the same reason" | **NO** | — | — **G05 is SILENT**, and the method **reads `w["scope"]` twice**, so it is not the same reason and not the same bound |
| `catalogue_outage_registered` uses `_is_catalogue_row` | **yes** | **yes** — G07 `3 failed` | **yes** ✅ |
| `count` door 1 (`record_catalogue_unavailable`) | **yes**, asserted separately | **yes** — G08 `3 failed` | **yes** ✅ |
| `count` door 3 (`_record_scoped`) | **yes**, asserted separately | **yes** — G09 `3 failed` | **yes** ✅ |
| `count` door 2 (`absorb`) | **no, and it says so** | **NO** — G10 green, **G10b (deleted outright) also green** | — **the annotation is exactly right** ✅ |
| `absorb`'s split `try` | **yes** — `test_A_SINK_THAT_RESISTS_CLEARING_LOSES_NOTHING` | **yes** — G11 re-merged → `3 failed` | **yes** ✅ **CLOSED** |
| `ensure_tool_call_instrumented` binds `_source` once | **NO** | — | — **G01 SILENT.** And the same function still reads **`chunk["tool"]` twice** (§7) |
| `withheld_json`'s walrus `_t := w.get("tool")` | **NO** | — | — **G12 SILENT** |

**9 of 16 weakenings red. Seven are silent**, four of them by design (the two gate-meta probes, and
door 2 which is declared). **Three are silent and undeclared: G01, G05, G12.**

---

## 3 · The falsifier, per claim — stated before the search

### 3.1 · The terminal-write gate — **PASS, and T8 is the module list**

**Falsifier (stated first):** any way to stop a persisted `withheld_tools` column carrying the
recorder's value while the gate is green; and for each, whether an ordinary edit reaches it.

| # | injection | ordinary or contrived? | term |
|---|---|---|---|
| T1 | `_withheld_json = None` | — | **`1 failed`** ✅ |
| T2 | annotated `_withheld_json: str \| None = None` | ordinary | **`1 failed`** ✅ |
| **T3** | **`:7424`, the clean finish, binds `None`** — R10's I13 | not even a refactor | **`1 failed`** ✅ **CLOSED, seventh round** |
| T4 | CONTROL — voice binds `None` | — | **`1 failed`** ✅ |
| T5 | walrus at the clean finish | contrived | **`1 failed`** ✅ |
| **T6** | `_wj_tmp = None; _withheld_json = _wj_tmp` | **ordinary two-line extraction** | **`1 failed`** ✅ **CLOSED** |
| T7 | tuple target | ordinary | **`1 failed`** ✅ |
| T8a/T8b | executor reached by an **alias** (`_fx = conn.fetchrow`), on each writer | ordinary | **`1 failed`** ✅ (caught by the NV) |
| T8d | a **helper that returns** the value | ordinary | **`1 failed`** ✅ |
| T8e/T8f | bind through **`*args`** / a starred list | ordinary | **`1 failed`** ✅ |
| T8g/T8g2 | **SQL assembled across two locals** / one local | ordinary | **`1 failed`** ✅ |
| T8h | **`executemany`** | ordinary | **`1 failed`** ✅ |
| T8i | a **renamed executor** (`conn.run`) | ordinary | **`1 failed`** ✅ (NV) |
| NV1 | the orphan-`UPDATE` writer's bind **deleted** | — | **`1 failed`** ✅ |
| NV2 | a **fourth writer added inside `voice_stream_service.py`** binding `None` | ordinary | **`1 failed`** ✅ |
| **T8c** | **a fourth writer in a NEW module under `app/services/`** | **ordinary — this is how a module is added** | **`1 passed`** ❌ |
| **T8c2** | the same writer in **`app/routers/`** | ordinary | **`1 passed`** ❌ |
| **T8c3** | the same writer in **`app/agentruntime/`** | **CP-2's scheduled package** | **`1 passed`** ❌ |

**A1 · Every question the prompt listed is answered, and every one of them is red.** SQL across two
locals, `*args`, `**kwargs`, an aliased executor, a returning helper, `executemany` — all caught. This
gate is a genuine, large improvement, and `:7424` is closed after seven rounds. That should be said
plainly before the finding.

**A2 · T8 is not a syntactic form. It is the enumeration.**

```python
_mods = ("stream_service.py", "voice_stream_service.py")
_base = Path(__file__).resolve().parents[1] / "app" / "services"
trees_all = [ast.parse((_base / m).read_text(encoding="utf-8")) for m in _mods]
```

Two filenames, written down, with **no staleness test over the pair**. A terminal writer anywhere else
is not "harder to check" — it is **not parsed at all**, so the loop that finds offenders never sees it
and the NV's floors are both satisfied by the four binds that remain.

**The contrast is inside the same file, sixty lines away.** The arm-order gate solved this exact
problem structurally: `base.rglob("*.py")` over `_TURN_SCOPE_ROOT = "app"`, with an explicit comment
recording that a cross-module entry point *"is in scope by construction"* and an assertion
(`:2559`) that the sweep still reaches a second module. **The builder derived the file set for one
gate and hardcoded it for the other, in the same round, in the same file.** That is the finding.

**Reachability: production-reachable.** `app/agentruntime/` is where CP-2's runtime lands and a probe
placed there is invisible today. This is the same prediction that came true for route 17, then route
20, then route 22.

**The fix is two lines**, and the file already contains it: sweep `app/` with `rglob`, and assert the
discovered writer set against the three named functions rather than asserting a floor.

**A3 · The NV — is naming three functions the right bound?** Measured both directions:

* It **catches a writer being lost**: NV1 (`1 failed`), an aliased executor (G14″ `1 failed` with the
  NV, G14′ `1 passed` without it), a renamed executor (T8i). The builder's comment — *"a count alone
  is satisfied by any four"* — is correct, and naming them is the right shape.
* It **cannot catch a writer being gained** anywhere the parse does not reach. `_binding_fns >= {…}`
  and `len(binds_checked) >= 4` are **both floors**. A fifth writer in a third module satisfies both.

So: naming three functions does **not** license losing a fourth. It licenses **gaining** one. The
bound is on the right axis for the failure that has happened and the wrong axis for the one T8 is.

### 3.2 · Route 23 — **the deletions are real, and the exemption they left is the next route**

**Falsifier:** any construction that puts a narrowing above an arming, or a narrowing entry point with
no arming, while the gate is green; any exemption granted on a false basis.

Gate baseline **`6 passed`**. Every probe is a real module written under `app/` and removed on restore.

| probe | discovered? | gate |
|---|---|---|
| CTL — un-armed async entry point that narrows | yes | **`2 failed`** ✅ |
| route 21 re-driven (`_`-prefixed, transitive) | yes | **`2 failed`** ✅ **CLOSED**, and now guarded by a test |
| route 22 re-driven (named like each of the five primitives) | yes ×5 | **`2 failed`** ✅ **CLOSED**, and now guarded |
| **R23a — narrow FIRST, then delegate to an armer** | **NO** | **`6 passed`** ❌ |
| **R23b — the delegating call sits under `if False:`** | **NO** | **`6 passed`** ❌ |
| **R23c — the delegating call is inside a never-called nested `def`** | **NO** | **`6 passed`** ❌ |
| R23-off — disable the delegation exemption on the **pristine** tree | — | **`2 failed`**, revealing `routers/messages.py::send_message` |

**C1 · Routes 21 and 22 are genuinely closed, judged rather than suppressed, and — this is new —
each has a test.** `test_an_UNDERSCORED_entry_point_narrowing_TRANSITIVELY_is_discovered` and
`test_an_entry_point_NAMED_LIKE_A_PRIMITIVE_is_discovered` both write real modules under `app/` and
sweep them with the real `_turn_entry_calls()`. R15's complaint — *"three routes closed, zero
assertions"* — was heard and answered.

**C2 · Route 23 is the delegation exemption, and it is route 22's shape one level up.**

```python
if f"{mod}::{fn.name}" in arming and not any(
    isinstance(n, ast.Call) and _called_name(n) == "arm_turn_surface"
    for n in ast.walk(fn)
):
    continue
```

`arming` is grown to a fixed point by `any(... for n in ast.walk(fn))`. So **any syntactic call token
anywhere in the function's AST** that resolves through `visible` to an arming function grants a
**total** exemption — the function is `continue`d before `arms`, `conditional`, `raw_sets`, `aliases`
or the ordering comparison are computed. Measured, three ways:

* **ordering-blind (R23a).** The probe narrows at line 4 and delegates at line 5. The arm therefore
  happens strictly *after* the narrowing — which is the defect this gate exists for, in its purest
  form — and the gate never looks. `6 passed`.
* **reachability-blind (R23b).** `if False:` around the delegating call still grants it. `6 passed`.
* **liveness-blind (R23c).** The delegating call inside a nested `async def` that is never invoked
  still grants it. `6 passed`.

And it bypasses the discipline the round just finished defending: **no `_NOT_A_TURN` entry, no stated
reason at any site, and outside `test_NO_ALLOW_LIST_ENTRY_IS_STALE`'s reach** — the three sentences
`_NOT_A_TURN`'s own header uses to condemn exactly this. Route 22 was `if fn.name in _NARROWING_CALLS:
continue`; route 23 is `if key in arming: continue`. Same statement, wider key.

**Which assumption did the deletion introduce?** The prompt's question is the right one. Deleting
routes 21 and 22 removed the two *other* exemption paths, so **every exemption that is not an
allow-list entry now flows through this one**, and it is the one with no reason, no staleness test and
no ordering check. The deletion did not create route 23; it made route 23 load-bearing.

**Reachability: production-reachable by construction — but I will grade the mechanism fairly.**
Disabling it on the pristine tree reveals exactly one function, `routers/messages.py::send_message`,
and I verified that function directly: it contains **no narrowing call of its own** and delegates at
`:521`. So unlike route 22 — which was suppressing an unjudged offender — this exemption is *correct
for its single present beneficiary*. The defect is the rule, not today's outcome. `+0` live, and the
three probes are ordinary router shapes.

**The correction is one line and keeps the intent**: require the delegating call to be at statement
depth 1 of the body (the same test `_unconditional` already applies to the arm), and require it to be
**below** every narrowing in the function — i.e. run the ordering check *before* granting the
exemption rather than instead of it.

### 3.3 · Route 18's line — **PASS on `async with`, and the line is drawn wrong in both directions**

**Falsifier:** correct code the gate reds; unreachable code the gate accepts.

| probe | gate | |
|---|---|---|
| W1 — arm at depth 1 inside `async with contextlib.AsyncExitStack()` | **`6 passed`** ✅ | **route 18 CLOSED, third round** |
| **W2 — arm is the FIRST statement of a `try:` body** | **`1 failed`** ❌ | **false positive on correct code** |
| **W3 — arm at depth 1 inside a `with` whose `__enter__` RAISES** | **`6 passed`** ❌ | **false negative on unreachable code** |
| W4 — arm inside `try:` **after** `x = 1/0` | `1 failed` ✅ | correctly red |

**The stated reason for excluding `Try` is falsified by the widening in the same diff.** The comment
says: *"an arm inside a `try` is one exception away from a turn that narrows into nothing."* That
sentence is **equally true of `with`** — W3 proves it: `__enter__` raises, the body never runs, the arm
never happens, and the gate calls it unconditional. So the property the code actually implements is
not "unconditional at entry"; it is "the statement kind is `With`".

The property that separates W2 from W4 is neither: it is **whether anything that can raise precedes
the arm inside that block.** W2 has nothing before it and is red; W4 has a division by zero before it
and is red; the gate cannot tell them apart, so it reds both. A `try:` wrapping a streaming entry
point with `except Exception:` at the bottom is an ordinary shape — `voice_stream_service.py:237` is
one refactor from it, which is the exact sentence the delta wrote about `async with`.

**Reachability: production-reachable as a false positive**, which is the failure mode the builder
correctly identifies as fatal — *"a gate that reds on correct code is one that gets deleted the first
time it is inconvenient."* Third round for that sentence, second spelling.

**The honest line:** count a statement as unconditional if it sits at depth 1 of the function body or
of any chain of `With`/`AsyncWith`/`Try` bodies **and no statement precedes it in that chain**. That
accepts W1 and W2, rejects W4, and — with a one-line addition that the entered context manager be a
`Name`/`Attribute` call rather than arbitrary — narrows W3.

### 3.4 · The `count` doors — **the annotation is honest, and I verified it rather than accepting it**

**Falsifier:** a door whose bound changes an outcome that the comment says it cannot, or vice versa.

| door | weakened to `isinstance` | deleted outright | comment's claim |
|---|---|---|---|
| 1 — `record_catalogue_unavailable` | **`3 failed`** ✅ | — | independently guarded — **TRUE** |
| 3 — `_record_scoped` | **`3 failed`** ✅ | — | independently guarded — **TRUE** |
| **2 — `absorb`** | **`2 failed, 124 passed` = BASELINE** | **also BASELINE** | *"not independently guarded"* — **TRUE, and stated before I measured it** |

**Ruling: honest, and keep the door.** The builder recorded the exact fact my sweep produces, including
that it *"is not independently guarded and claiming otherwise would be the vacuity failure this file
has a standard about."* I also verified the routing claim: `absorb` → `record_catalogue_withheld` →
`_record_scoped`, so door 2 does feed door 3 and cannot diverge from it.

**And it is not the flag.** The standard this run applied to the `ContextVar` — *"a field that is both
dead and duplicated is not a mechanism, it is a place for the next reader to be wrong"* — does not
transfer, and the difference is precise: the flag was a **second answer** that could contradict the
first; door 2 is a **narrower** coercion feeding the same door, so no reader can ever see two answers.
Deleting it would be defensible; keeping it with this annotation is better, because the annotation is
what makes the next reader safe. **This is the one item in my scope I grade CLOSED with no residual.**

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | **a terminal writer in a third module** — `_mods` is a hardcoded pair | ✅ T8c/c2/c3, `1 passed` ×3 vs 10 in-module defeats red | **production (CP-2's package) — NEW** |
| " | ~~`:7424` the clean finish~~ | ✅ T3 **now `1 failed`** | — **CLOSED, 7 rounds** |
| " | ~~a two-step extraction~~ / ~~walrus~~ / ~~tuple target~~ / ~~annotation~~ | ✅ T6/T5/T7/T2 all red | — **CLOSED** |
| " | ~~an aliased executor~~ / ~~`*args`~~ / ~~a returning helper~~ / ~~`executemany`~~ / ~~SQL across two locals~~ | ✅ all red | — **CLOSED** |
| arm-order gate · no narrowing precedes the arming | **narrow, then delegate to an armer** — the exemption is granted before the ordering check | ✅ R23a `6 passed`, control `2 failed` | **production, by construction — NEW** |
| " | **a delegating call under `if False:`** | ✅ R23b `6 passed` | **production, by construction — NEW** |
| " | **a delegating call inside a never-called nested `def`** | ✅ R23c `6 passed` | **production, by construction — NEW** |
| " | ~~a `_`-prefixed transitive narrower~~ / ~~a name in `_NARROWING_CALLS`~~ | ✅ both **now `2 failed`**, both now guarded | — **CLOSED** |
| " | a module-scope **lambda**; a narrowing at **module scope** | ✅ both `6 passed` | adversarial (carried, unchanged) |
| the gate does not red on correct code | **an arm as the first statement of a `try:` body** | ✅ W2 `1 failed` | **production (false positive) — NEW SPELLING** |
| the gate reds on a conditional arm | **an arm inside a `with` whose `__enter__` raises** | ✅ W3 `6 passed` | adversarial |
| the outage fact does not outlive its turn | **a turn that narrows and never drains** leaks the fact **and its rows** into the next turn in the same context | ✅ O1 `(True, True, 1 row inherited)`; O6-D `True` | **production (pooled/reused context)** — *identical to the boolean* |
| the outage fact cannot be erased by a drain | **an arm after a drain releases the recorder** while the recorder still holds the row | ✅ O3 `True → False` | latent — *identical to the boolean* |
| " | **a second recorder in one turn** hides the first's absorbed row | ✅ O2 `True → False`; **the boolean answered `True`** | latent — **REGRESSION** |
| " | **a background task's `absorb`** drains the parent's shared sink; the parent cannot see the task's recorder | ✅ O4 `False`; **the boolean answered `True`** | latent — **REGRESSION** |
| `catalogue_outage()`'s value bound | it **reads `w["scope"] twice`** — the type check and the `==` see different values | ✅ `catalogue_outage() = False` on a catalogue row | adversarial — **NEW, introduced** |
| a tool-call row is classified and stamped from one name | **`chunk["tool"]` is read twice** (`:230`, `:243`) | ✅ classified `breaker` from `read_file`, stamped `delete_everything` | **production — the sweep that fixed `source` missed the pair** |
| `absorb` records what the sink held | ~~a non-list sink loses every row~~ | ✅ tuple/generator/undeletable all record | — **CLOSED** |
| the arming cannot raise on any input | ~~a hostile `__eq__` on `scope`~~ | ✅ guarded and red-able | — **CLOSED** |
| the outage reader cannot raise | ~~`catalogue_outage_registered` bare `.get`~~ | ✅ G07 red | — **CLOSED** |
| `count` is absent-or-a-count | ~~`count: false` / `count: true`~~ | ✅ two doors each independently red | — **CLOSED, 5 rounds** |

### 4.2 · Is the `_NOT_A_TURN` reason true of the code?

The new entry claims `discovery_seed_for_surface` *"takes `withheld_sink: list[dict] | None = None`
and its two call sites (`stream_service.py:6073`, `:8119`) are both inside an already-armed turn."*

**Verified, and the conclusion is true.** I re-derived it from the AST rather than reading it:
`:6073` is inside `stream_response` (`4950–6205`, arms at **5003**) and `:8119` inside
`resume_stream_response` (`7723–8248`, arms at **7749**). Both narrowings are strictly below their
arm. The function does call `_budget_and_register`, so it is genuinely narrowing machinery, and the
entry is **discovered** — `test_NO_ALLOW_LIST_ENTRY_IS_STALE` reports zero stale entries.

**One premise is inert and should be said.** Neither call site actually passes `withheld_sink`; both
take the default `None`. `tool_surface.py:261` records this in the codebase's own words — *"`withheld_sink`
was optional and BOTH production call sites omitted it."* So the half of the reason that reads *"a
function that RECEIVES the turn's sink is by definition running inside a turn somebody else armed"* is
an argument from a signature production does not exercise. The **line-number** half carries the
exemption on its own, and it is the half that is true. Worth correcting in the comment, not a defect.

---

## 5 · Question 4 — better than the boolean, or merely different? **Worse.**

Six orderings, one probe file, run against two trees: `…/r16a/prev` (the **previous artifact's**
`instrument.py`, sha256-verified equal to `cba800fa8`'s, on the delta's test file) and
`…/r16a/pristine` (the delta). The probe printed which mechanism it had loaded before each run
(`has _turn_recorder=…`, `has catalogue_outage=…`), so neither result can be the wrong tree.

| ordering | **BOOLEAN** (previous) | **RECORDER** (delta) | verdict |
|---|---|---|---|
| **O1** turn A narrows, never drains; turn B arms in the same context | `(True, **True**, 1 row inherited)` | `(True, **True**, 1 row inherited)` | **identical — both leak** |
| **O2** two recorders in one turn | `(True, **True**)` | `(True, **False**)` | **REGRESSION** |
| **O3** an arm after a drain, inside one turn | `(True, **False**)` | `(True, **False**)` | **identical — both erase** |
| **O4** a background task drains the sink | `(True, **True**)` | `(True, **False**)` | **REGRESSION** |
| **O5** a turn that never constructs a recorder | `(True)` | `(True)` | identical |
| **O6** pooled thread, four turns A/B/C/D | `(T, F, T, **T**)` | `(T, F, T, **T**)` | **identical — both leak at D** |

**Identical on four, worse on two, better on none.**

**The two claims in the docstring are both false as written.**

> *"a pooled thread cannot keep a previous turn's answer (a new turn builds a new recorder)"*

O1 and O6-D refute it. The leak does not ride the recorder — it rides the **sink**, which
`arm_turn_surface` deliberately adopts when non-empty, and which is non-empty precisely when the
previous turn died before absorbing. Turn B then reports `True` **and inherits turn A's row into its
own `withheld_tools`**, which is strictly worse than the flag was: the flag leaked a boolean, this
leaks a persisted row onto the wrong message.

> *"a drain cannot erase it (the drain is what puts the row IN the recorder)"*

O3 refutes it. The drain **empties the sink**; the next `arm_turn_surface` sees `not sink` and executes
`_turn_recorder.set(None)`. The recorder still holds the row — I asserted that in the same probe — and
the reader can no longer reach it. The erasure was not removed; its trigger moved from
`catalogue_outage.set(any(...))` to `_turn_recorder.set(None)`.

**And the guard cannot see any of this.** `test_the_outage_survives_the_DRAIN__and_does_not_outlive_the_TURN`
run against `cba800fa8`'s `instrument.py`:

```
1 passed
```

The other three tests in that class correctly red on the previous artifact
(`test_a_HOSTILE_SCOPE_VALUE…`, `test_COUNT_FALSE_IS_NOT_A_COUNT…`, `test_A_SINK_THAT_RESISTS_CLEARING…`
all FAILED). So three of four new guards are genuinely red-able against the code they replaced; **the
fourth — the one guarding the largest structural change in the delta — is green on it.** All four of
its orderings are satisfied by the boolean, which is why. That is the run's own standard, verbatim:
*a check whose control and seed agree is theatre.*

**What I would do instead.** The mismatch the rehousing correctly diagnosed is real — a turn-lifetime
fact in a context-lifetime container. But the recorder is not a turn-lifetime object either; it is a
*constructed-object*-lifetime object, and a turn can construct zero, one or two. The object whose
lifetime is exactly one turn is **the sink**, and the arm already owns it. Make the arm **replace**
the sink with a fresh list and stamp a turn id on it; carry the outage as a row in that list; and have
`absorb` move rows to the recorder **without** clearing the turn's answer. Then O1, O3, O4 and O6-D all
collapse to the same statement — *this turn's list is this turn's list* — and no reader needs to know
whether a drain has happened.

**Reachability, stated honestly.** O1/O6-D is production-reachable wherever a context is reused
(a pooled worker, a reused task context) — the same reachability the flag had, neither better nor
worse. O2 and O4 are **latent-not-live**: production constructs exactly one recorder per turn
(`stream_service.py:6576`, `voice_stream_service.py:242`, verified by AST) and no background task
absorbs today. I record them as regressions because they are regressions, not because they are firing.

---

## 6 · The red-ability table

Baseline for every row: **my own scratch copy**, measured this session. `instr` = `2 failed, 124
passed`; `term` = `1 passed`; `gate` = `6 passed`. "RED" means failures beyond the two copy artefacts.
Every injection printed a source-content assertion read back **off disk** before its suite ran;
reversal is always a restore from my own snapshot.

| # | injection | what it models | result |
|---|---|---|---|
| **T3** | `:7424` clean finish binds `None` | **R10's I13, seven rounds** | **term `1 failed`** ✅ **CLOSED** |
| **T6** | two-step extraction | R15's ordinary-edit defeat | **term `1 failed`** ✅ **CLOSED** |
| T1/T2/T4/T5/T7 | literal / annotated / voice control / walrus / tuple | rounds 10–14 | term `1 failed` ×5 ✅ |
| T8a/b, T8d–i, NV1, NV2 | alias ×2, helper, `*args`, `**kwargs`, `executemany`, rename, SQL ×2, lost writer, gained writer | the prompt's T8 list | term `1 failed` ×10 ✅ |
| **T8c / T8c2 / T8c3** | **a writer in `app/services/`(new) / `app/routers/` / `app/agentruntime/`** | **T8** | **term `1 passed` ×3 — INVISIBLE** |
| G14′ | NV removed **+** an aliased executor | is the NV load-bearing? | **term `1 passed`** — yes, it is the only thing catching it |
| G14″ | NV kept **+** the same alias (control) | " | term `1 failed` ✅ |
| **R23a/b/c** | narrow-then-delegate / dead branch / never-called nested | **route 23** | **gate `6 passed` ×3 — INVISIBLE** |
| CTL / R21 / R22 | control, and routes 21 & 22 re-driven | R15's two new routes | gate `2 failed` ✅ ×3 **CLOSED** |
| R23-off | disable the delegation exemption on the pristine tree | is it load-bearing? | **gate `2 failed`** — covers `routers/messages.py::send_message`, correctly |
| W1 | arm inside `async with` | **route 18** | gate `6 passed` ✅ **CLOSED** |
| **W2** | **arm as the first statement of a `try:` body** | route 18's class | **gate `1 failed` — FALSE POSITIVE** |
| **W3** | arm inside a `with` whose `__enter__` raises | the inverse | **gate `6 passed` — accepted though unreachable** |
| W4 | arm inside `try:` after `1/0` (control) | " | gate `1 failed` ✅ |
| R24 / R25 | module-scope lambda / module-scope narrowing | R15's carried adversarial pair | gate `6 passed` ×2 (unchanged) |
| **G01** | `ensure_tool_call_instrumented` reads `source` twice again | **the delta's own headline read-twice fix** | **instr BASELINE — SILENT** |
| G02/G03/G04 | recorder does not register / arm always releases / arm never releases | the rehousing's plumbing | instr `4/4/7 failed` ✅ |
| **G05** | `catalogue_outage()` drops its `type(...) is str` bound | the bound whose docstring cites `_is_catalogue_row` | **instr BASELINE — SILENT** |
| G06/G07 | `_is_catalogue_row` value bound / `catalogue_outage_registered`'s bare `.get` | R15's two named sites | instr `3 failed` ✅ ×2 |
| G08/G09 | count doors 1 and 3 → `isinstance` | five rounds | instr `3 failed` ✅ ×2 |
| **G10 / G10b** | count door 2 weakened / **deleted outright** | the door the builder calls redundant | **BASELINE ×2 — the annotation is TRUE** |
| G11 | `absorb`'s two `try`s re-merged | R15's B1 | instr `3 failed` ✅ |
| **G12** | `withheld_json` reads `w["tool"]` twice again | the delta's other read-twice fix | **instr BASELINE — SILENT** |
| G15 | the `With`/`AsyncWith` widening reverted | route 18's fix | instr `3 failed` ✅ |
| **PREV** | the delta's **new outage guard** run on `cba800fa8`'s `instrument.py` | is the headline guard red-able? | **`1 passed` — GREEN ON THE CODE IT REPLACED** |
| PREV-ctl | the other three new guards, same tree | control | **all three FAILED** ✅ |

**Independent re-run of the builder's claim "10/10 instrument guards proven red-able": I measure
9/16.** Two of the seven silent ones are not valid probes (they weaken the gate itself, which is green
on a clean tree by definition) and one is declared silent by the builder and confirmed. **Three are
silent and undeclared: G01, G05, G12** — and G01 and G12 are the two read-twice fixes the round was
named for.

**Independent re-run of the builder's read-twice sweep: not 0.** My sweep (§7) asserts its own control
first — `writes_only` → `[]`, `reads_twice` → found, `write_then_read` → `[]` — so it does not repeat
the builder's first version's error of counting writes as reads. In `instrument.py` it confirms **two
sites closed** (`chunk["source"]`, `withheld_json`'s `w["tool"]` — both present on the previous
artifact, both gone) and reports **two live**: one missed and one introduced.

---

## 7 · The read-twice sweep — two sites, one missed and one introduced

My sweep counts only Load-context `X[k]`, `X.get(k)` and `k in X`; `X[k] = v`, `del X[k]`,
`X.setdefault`, `X.pop` and `X.update` are excluded, and that exclusion is asserted on a fixture
before the real files are read. Locally-constructed literal dicts are excluded.

**Site 1 — `ensure_tool_call_instrumented` still reads `chunk["tool"]` twice, at `:230` and `:243`.**
Present on the previous artifact at `:224`/`:236`; still present. This is **the same function, thirteen
lines apart, in the diff that fixed the sibling read of `source`** — and the comment added beside the
fix states the threat model exactly: *"a `chunk` is an ordinary argument here, nothing bounds its type,
and a container answering the two reads differently would classify one way and stamp another."* That
sentence is true of `tool` and was not acted on. Driven through the real function:

```
classified source  : breaker             (from the 1st read of `tool`)
declaration stamped: delete_everything   (from the 2nd read of `tool`)
```

The row says it is a `breaker` call named `delete_everything` while the classification that produced
`breaker` was computed from `read_file`. **Reachability: production-reachable** — `chunk` is an
ordinary argument from a chunk producer, exactly as reachable as `source` was.

**Site 2 — `AdvertisedToolsRecorder.catalogue_outage` reads `w["scope"]` twice, at `:752`. Introduced
by the graded delta.**

```python
return any(type(w.get("scope")) is str and w.get("scope") == SCOPE_CATALOGUE
           for w in self._withheld)
```

The type bound checks one value and the `==` compares another, so the bound is not a bound. Driven:
a row whose first read is `"catalogue"` and whose second is an arbitrary object gives
`catalogue_outage() = False` — the outage is lost by the method written to hold it.

**Three lines above, `_is_catalogue_row` does it correctly** (`v = row.get("scope"); return type(v) is
str and v == SCOPE_CATALOGUE`), and `catalogue_outage`'s docstring says it bounds the value *"for the
same reason `_is_catalogue_row` does it."* It does not do it the same way. **Reachability:
adversarial-input only** — every row in `_withheld` is built by `_record_scoped` from an `_as_text`-ed
value, so a hostile container cannot get in through a live path. I record it because it is the same
defect class the delta fixed twice in this file, recreated in the new code, with a comment asserting
parity that the code does not have.

Elsewhere in scope the sweep reports 95 further `(container, key)` repeats — overwhelmingly asyncpg
`Record` reads in `app/routers/` and `gen_params` dicts the function itself constructed. I do not
raise them: the threat model that matters here is *a mapping supplied by another party*, and those are
not it. Both sites above are.

---

## 8 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| the per-bind terminal gate | every bind form the prompt named | drove alias, `*args`, `**kwargs`, helper, `executemany`, rename, SQL ×2 | **YES ×8** ✅ |
| " | a writer the parse never reaches | wrote one in three different packages | **NO — T8**, `1 passed` ×3 |
| " | whether the NV bounds gains as well as losses | drove NV1 (loss) and NV2/T8c (gain) | **NO** — both bounds are floors |
| routes 21/22 deleted | the exemption they left behind | drove the delegation rule three ways | **NO — route 23**, and the deletion made it load-bearing |
| " | whether the deletions got tests | read the two new tests, re-drove both routes | **YES** ✅ — R15's complaint answered |
| `_NOT_A_TURN` += `discovery_seed_for_surface` | whether the reason is true of the code | re-derived enclosing functions and arm lines from the AST | **YES on the conclusion**; one premise is inert |
| `With`/`AsyncWith` at depth 1 | whether `Try` is the same shape | drove W2 (first statement) and W4 (after a raise) | **NO — W2 is a false positive** |
| " | whether `With` really is unconditional | drove W3, a `with` whose `__enter__` raises | **NO — accepted though unreachable** |
| the outage rehoused | whether it beats what it replaced | ran six orderings on **both** trees | **NO — 4 identical, 2 worse, 0 better** |
| " | whether its guard can see the change | ran the guard on the previous artifact | **NO — `1 passed`** |
| " | whether the other three new guards are real | same tree | **YES — all three FAILED** ✅ |
| `_is_catalogue_row` bounds the value | whether its twin does | read both; drove a two-faced row through `catalogue_outage` | **NO — reads `w["scope"]` twice** |
| `ensure_tool_call_instrumented` binds `_source` | whether `tool` is read twice in the same function | swept, then drove a two-faced chunk | **NO — `:230`/`:243`, production-reachable** |
| `withheld_json`'s walrus | whether the fix has a test | G12 | **NO — silent** |
| the `count` doors | whether the "redundant" claim is true | weakened door 2, then deleted it | **the claim is TRUE** ✅ |
| `absorb`'s split `try` | whether tuple/generator/undeletable now record | drove all three plus a plain-list control | **YES** ✅ **CLOSED** |
| the module-scope lambda / module-scope narrowing | whether R15's carried pair moved | re-drove both | **NO** — unchanged, adversarial |

---

## 9 · Convergence, my scope

| round | production-reachable | adversarial-input only | changed lines (scope A) | introduced by the delta | **introduced per 100 changed lines** |
|---|---|---|---|---|---|
| 13 | 13 | 5 | 150 | 3 | 2.00 |
| 14 | 9 | 6 | 258 | 2 | 0.78 |
| 15 | 6 | 6 | 89 | 2 | 2.25 |
| **16** | **7** | **5** | **739** | **5** | **0.68** |

**Production-reachable, this round:** T8 (the gate's hardcoded module pair); route 23 (three variants,
counted once); W2 (the `try:` false positive); `chunk["tool"]` read twice; the outage guard that is
green on the code it replaced; the O1/O6-D leak with its inherited row; three strengthenings shipped
silent (G01/G05/G12, counted once).
**Adversarial:** the O2/O4 regressions (counted once); `catalogue_outage`'s `w["scope"]` read-twice;
W3; the module-scope lambda; the module-scope narrowing.

**Closure: 9 of R15's 12 findings — 75%, by far the highest of the series** (R15 was ~27%, and two of
its four were incidental). Closed: `:7424` after **seven rounds**; the two-step bind; routes 21 and 22
*with tests*; route 18's `async with` case; the container `try`; the hostile `__eq__` at the arm;
`catalogue_outage_registered`'s bare `.get`; `count: false` after **five rounds**. Not closed: the
module-scope lambda and module-scope narrowing (both adversarial, both correctly deprioritised), and
the outage leak — which was *relocated* rather than closed.

**Is the introduction rate falling? Per changed line, yes — and only per changed line.** The raw
series reads 3, 2, 2, **5**: rising. Normalised, it reads 2.00, 0.78, 2.25, **0.68**: this is the
lowest of the four measured rounds, and it is not an artefact of shipping less — the delta is
**739 lines in my scope against R15's 89**, so the normalisation is working against the round, not for
it. Both numbers are honest and they disagree, which is why the prompt asked for both.

**The number I would actually watch is neither.** It is the *shape* of what gets introduced. R15
introduced routes 21 and 22 — exemptions bolted onto a gate. R16 introduced W2 and route 23 — the
**same class of defect one level of abstraction out**: an enumeration written down instead of derived
(T8), and an exemption granted before the check it exempts from (route 23). The fixes are getting
structurally better and the residual is moving up the stack at the same rate. Three consecutive rounds
at `introduced == 0` remains the right terminating condition, and this round is not one of them.

---

## 10 · Where the builder's documentation of a residual is incomplete or wrong

1. **The rehousing's two central claims are both false, and I measured them against the artifact they
   describe.** *"a pooled thread cannot keep a previous turn's answer"* — O1/O6-D: it can, because the
   leak rides the sink and the arm adopts a non-empty sink. *"a drain cannot erase it"* — O3: the drain
   empties the sink and the next arm's `if not sink` releases the recorder. The docstring calls both
   *"unconstructible"*; both are constructed above in twelve lines of probe.
2. **The guard for the round's headline change is green on the code the change replaced.** All four of
   its orderings are satisfied by the `ContextVar[bool]`. The other three guards in the same class red
   correctly, which makes this one an oversight rather than a pattern — but it is the fourth
   consecutive round in which the largest change is the least guarded one.
3. **The `10/10 instrument guards proven red-able` claim does not reproduce. I measure 9/16**, with
   three silent and undeclared — including **both** of the round's own read-twice fixes (G01, G12).
4. **The `0 sites` read-twice claim does not reproduce for my scope.** Two live sites: `chunk["tool"]`
   in the very function the sweep fixed, and a **new** one at `catalogue_outage:752` whose docstring
   claims parity with the correctly-written helper three lines above it.
5. **The terminal-write gate hardcodes its file set sixty lines from an arm-order gate that derives
   its own** and asserts, in a comment, that deriving it is what makes cross-module entry points *"in
   scope by construction."* The same insight, in the same file, in the same round, applied once.
6. **The stated reason for excluding `Try` from `_unconditional` is refuted by the `With` it widened.**
   W3 shows a `with` body is exactly as "one exception away" as a `try` body. The line is drawn by
   *what a verifier measured* rather than by a property, and the comment beside it says so honestly
   — *"only the shape a verifier measured is widened"* — which is candid and is also precisely why
   W2 exists.
7. **Route 23 is route 22's statement with a wider key**, in the commit that deleted route 22 and
   explained why blanket exemptions are wrong. Unlike route 22 it is correct for its one present
   beneficiary, which I verified; also unlike route 22 it has no reason, no allow-list entry and no
   staleness test, and it now carries every exemption that is not an allow-list entry.
8. **Exemplary, and it should be said first in the next round's brief.** `:7424` is **closed after
   seven rounds**, and it is closed at the class: eleven distinct bind forms red, including every one
   the prompt named. `count: false` is closed after five. Routes 21 and 22 are closed **with tests**,
   which is what R15 asked for and did not get. The container `try` and the hostile `__eq__` are
   closed and guarded. And the `count` door-2 annotation is the best single line in the delta:
   the builder measured its own defence, found it not independently guarded, wrote that down rather
   than claiming otherwise, and I re-measured it and it is exactly right. **Three of six claims are
   fully closed with red-able tests; the failure of this round is concentrated in one change (the
   rehousing) and two enumerations (`_mods`, and the exemption order).**

---

## 11 · What would have to be true for this to PASS

* **Derive the terminal-write gate's file set** — `rglob("*.py")` over `app/`, the way the arm-order
  gate already does — and assert the discovered writer set **equals** the named three rather than
  containing them. Two lines; the pattern is sixty lines away in the same file.
* **Run the ordering check before granting the delegation exemption**, and require the delegating call
  to be at statement depth 1. That closes R23a/b/c and keeps `send_message` exempt.
* **Accept a `Try` body at depth 1 when no statement precedes the arm in the chain** — this accepts W1
  and W2, still rejects W4, and stops the gate reddening correct code for a fourth round.
* **Do not tune the recorder handoff — move the fact onto the SINK.** The arm already owns exactly one
  object per turn; make it a fresh list with a turn stamp, carry the outage as a row in it, and stop
  `absorb` from being able to clear the turn's answer. O1, O3, O4 and O6-D collapse together.
* **Re-write the outage guard so it reds on `cba800fa8`'s `instrument.py`.** Until it does, the
  rehousing has no guard, whatever the class docstring says.
* **Bind `chunk["tool"]` once** in `ensure_tool_call_instrumented`, and **bind `w["scope"]` once** in
  `catalogue_outage` — the second one is three lines from the helper that already does it right.
* **Give G01, G05 and G12 a test each**, or delete G05 (its bound is unreachable through any live path,
  so the docstring's justification overstates what it buys).

`git rev-parse HEAD` at start: `d23ea559294ae2daa4fa1414d87b734d2e1e2479`.
`git rev-parse HEAD` before writing: `d23ea559294ae2daa4fa1414d87b734d2e1e2479`.
`git status --porcelain -- services/chat-service`: **empty** at both ends.
