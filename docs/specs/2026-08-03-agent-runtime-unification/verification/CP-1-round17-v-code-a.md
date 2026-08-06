# CP-1 · round 17 · V-CODE — Verifier A (the instrument)

`git rev-parse HEAD` at start: **`6761cf013891b9c88c338750985553fd08bf9b0e`**
`git rev-parse HEAD` before writing: **`6761cf013891b9c88c338750985553fd08bf9b0e`** — it did not move.
`git status --porcelain -- services/chat-service`: **empty** at both ends.

Graded delta: `869c5be52`, diffed against `d23ea5592`. Scope A: `app/services/instrument.py`,
`stream_service.py`, `voice_stream_service.py`, `app/routers/`, and the gate machinery in
`tests/test_cp0_instrument.py`. **415 changed lines** in scope (`54+37` instrument, `278+46` tests).

Every measurement below was **executed**, in a scratch tree at
`…/scratchpad/r17/` built to the repository's own depth (`parents[3]` reaches `contracts/`, which the
first tree got wrong and which I fixed before trusting a single number). Scratch baseline:
`tests/test_cp0_instrument.py` **130 passed**; full `tests/` **19 failed, 2234 passed, 2 skipped** —
the 19 are pre-existing, caused by sibling repositories absent from the scratch tree, and **every
delta below is reported against that baseline, not against zero.** Every injection prints a
verify-on-disk check before the suite runs, and every restore is asserted byte-identical.

---

## 1 · Verdict — **FAIL**

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the outage revert; is the new guard red on `530ce3eff`?** | **PASS on the guard — FAIL on the decision.** The guard **is** `1 failed` on `530ce3eff`'s `instrument.py` ✅ (the previous one was `1 passed`, which is why it existed). But **it reds because the replaced artifact was BETTER.** Head-to-head over nine orderings, three trees: HEAD is **worse than `530ce3eff` on three** (`O_B`, `O_D[0]`, `O_F`), **worse than `cba800fa8` on four** (those plus `O_E`), and **better than neither on any** | **production — `O_B` is the live post-drain read, asserted `False`** |
| 2 | **"no arrangement inside `instrument.py` can satisfy every ordering"** | **REFUTED.** `HEAD` is `cba800fa8` **minus one line**. Restoring `catalogue_outage.set(True)` in `record_catalogue_unavailable` satisfies **all four rows of the builder's own table** plus `O_E`/`O_F`, needs **no turn identity**, and reds **exactly one test in 2255** — the test that asserts the defect. And the argument the negative claim rests on is **vacuous**: the docstring's *"making the derivation monotone … reds two tests"* reds **zero of 2255** | **production — the fix is one line and available today** |
| 3 | **T8 closed by `rglob`; find T9** | **PASS on T8 — T9 FOUND, nine ways.** `G-T8` (revert to the 2-tuple) reds ✅. But the gate walks `FunctionDef` only and anchors on a **string literal in the call's own arguments**: **T9e** (SQL hoisted to a module-level constant), **T9d/T9j** (SQL from a helper module), **T9a/b/c/f** (module scope, `lambda`, comprehension, class body), **T9g** (an unparseable module — `except SyntaxError: continue` is **fail-open**), **T9h** (a bare-name executor). All **`1 passed`** against a control at `1 failed` | **production — `T9e` is the most ordinary refactor in the list** |
| 4 | **route 23 closed; one shared "unconditional"; find route 24** | **PASS on the closure — ROUTE 24 FOUND, three variants.** `G-R23` reds ✅ and `G-LTE` proves the `<=` load-bearing ✅. But the ordering test is **by line number**, and **Python evaluates a call's arguments before the call**: `return stream_response(await c.get_tool_definitions())` is **EXEMPTED**. The shared definition **moved** the hole rather than removing a class — §4.2 | **production, by construction** |
| 5 | **the `try:` body now counts as unconditional; grade the justification** | **FAIL.** The justification is candid about what it does *not* claim, and the **implementation does not implement the property it states** — an arm in a `for` iterator, an `if` test, a `finally` body or a `with` **header** is not guarded by any branch a reader can see and is reported **CONDITIONAL** (R24f/g/h/i). Worse, the widening **went past what R16-A specified** (*"when no statement precedes the arm in the chain … still rejects W4"*): **W4, W5, W6, W7 were RED on `d23ea5592` and are GREEN now** | **production — W5 is a turn that narrows into nothing, newly green** |
| 6 | **convergence, per changed line** | **Closure 6 of 12 = 50%**, down from R16's 75%. **Introduced 5**, over **415** changed lines = **1.20/100** | §9 |

### The most valuable thing this round produced

**The negative claim in item 2 is false, and the code that refutes it is in this repository's own
history.** `869c5be52`'s `instrument.py` is `cba800fa8`'s with a single statement deleted. Restore it
and every ordering the builder tabulated as unsatisfiable is satisfied — no turn identity, no CP-2,
one line, one red test in 2255 and that test is the one asserting the hole. The reason the builder
could not see this is the same reason as the last two rounds: **the incompatibility argument
(monotone-vs-lowering) reasons about a design that no longer exists in the file.** With the writer
deleted, nothing ever raises the flag, so "monotone" and "lowering" are the same program — which is
exactly what `G-MONO` measures: **0 of 2255.**

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| `_mods` → `rglob` over `app/` (`test_cp0_instrument.py:1593`) | **yes** — `test_the_TERMINAL_WRITE_GATE_sees_a_writer_in_ANY_module` | **yes** — `G-T8` `1 failed` | **yes for a module**; **NO for a writer that is not a `FunctionDef`, or whose SQL is not a literal in the call** — §3.3, nine defeats |
| the delegation exemption requires an unconditional, preceding delegate (`:2352–2361`) | **yes** — `test_the_DELEGATION_EXEMPTION_is_not_ordering_dead_branch_or_liveness_BLIND` | **yes** — `G-R23` `1 failed` | **yes for the three named variants; NO for a narrowing nested in the delegate's own arguments** — route 24 |
| `<=` rather than `<` in that ordering test (`:2361`) | it is the same test | **yes** — `G-LTE` `2 failed` | **yes, and the comment beside it is TRUE** ✅ — a strict `<` reds `send_message`, which is correct code |
| `_unconditional_calls` shared by both relations (`:2176–2204`) | **yes** — `test_an_ARM_INSIDE_A_TRY_BODY_is_not_CONDITIONAL_either` | **yes** — `G-W2` `1 failed` | **yes for W2. NO for the widening's blast radius**: W4/W5/W6/W7 flipped RED→GREEN and nothing asserts they should not have |
| `_tool` bound once in `ensure_tool_call_instrumented` (`:235`) | **yes** — `test_TOOL_READ_ONCE__the_pair_the_source_fix_left_behind` | **yes** — `G-TOOL` `1 failed` | **yes** ✅ |
| `_source` bound once, same function (`:234`) | **NO** | — | — **`G01` SILENT on the full 2255-test suite. Third round.** R16-A asked for this test by name |
| `withheld_json`'s walrus `_t := w.get("tool")` (`:962`) | **NO** | — | — **`G12` SILENT on the full suite. Third round.** R16-A asked for this test by name |
| the outage fact reverted to `ContextVar[bool]`, derived at the arm (`:413`) | **yes** — the new `test_THE_OUTAGE_FACT_IS_ORDERING_DEPENDENT…` | **yes** — `G-ARM` `2 failed`; **red on `530ce3eff`** ✅ | **it reds for the WRONG reason.** Its message says a red means *"someone has given the turn an identity"*. `530ce3eff`, `cba800fa8` **and** my one-line `R1` all red it **without** one |
| the `#:` block on `catalogue_outage` (`:307–329`) | — | — | — **it describes the REHOUSING that was reverted**: *"the fact moved to the object whose lifetime **is** one turn: the recorder"* (`:324`) sits above `catalogue_outage: ContextVar[bool]` (`:330`) |
| that block's *"monotone … reds two tests"* (`:313–316`) | — | **NO** | — **`G-MONO` reds `0 of 2255`.** This is the premise of the whole "no arrangement works" conclusion |
| `catalogue_outage()` method DELETED | n/a | n/a | ✅ — the R16-A `w["scope"]` read-twice is gone with it, and deleting beat keeping |
| `_is_catalogue_row` value bound | **yes** | **yes** — `G06` `1 failed` | **yes** ✅ |
| the NV floor (`:1633`) | it is the test | **not a valid probe alone** — `G-NV` `130 passed` on a clean tree by definition | carried from R16-A: **both bounds are floors** |

---

## 3 · The falsifier, per claim — stated before the search

### 3.1 · Claim 1 — **the guard reds on the replaced artifact; the decision it defends does not survive**

**Falsifier stated first:** *if `test_THE_OUTAGE_FACT_IS_ORDERING_DEPENDENT…` passes on
`530ce3eff`'s `instrument.py`, the round's headline change is unguarded, exactly as R16's was.*

Injected `git show 530ce3eff:…/instrument.py` into the scratch tree, verified on disk
(`_turn_recorder` present, `catalogue_outage: ContextVar` absent, `def catalogue_outage(self)`
present), ran the class:

```
1 failed, 3 passed
>   assert ctx().run(lambda: _turn(drain=True)) is False
E   assert True is False
```

**The guard is red-able on the artifact it replaced.** ✅ That is the narrow question and it passes.

**But the row that fires is row two, and it fires because `530ce3eff` answered it `True`.** So I ran
the head-to-head the prompt asked for rather than trusting the account. Same probe, same context
discipline (`contextvars.copy_context()` per ordering), three trees, verified per swap:

| ordering | `HEAD` `869c5be52` | `530ce3eff` (recorder) | `cba800fa8` (writer) | |
|---|---|---|---|---|
| **O_A** arm → record → read | `True` | `True` | `True` | the live shape |
| **O_B** arm → record → **drain** → read | **`False`** | `True` | `True` | 🔴 **HEAD alone loses it** |
| **O_C** record → recorder → arm → drain → read | `True` | `True` | `True` | |
| **O_D** turn A drains/reads, turn B arms/reads | **`(False, False)`** | `(True, False)` | `(True, False)` | 🔴 HEAD loses turn A's own answer |
| **O_E** two recorders in one turn | `False` | `False` | **`True`** | |
| **O_F** a background task drains the sink | **`False`** | `True` | `True` | 🔴 |
| **O_G** a turn that never drains | `True` | `True` | `True` | |
| **O_H** pooled context, three turns, no drain | `(T,T,T,1)` | `(T,T,T,1)` | `(T,T,T,1)` | **identical — the leak rides the SINK** |
| **O_I** narrowing before the arm | `True` | `True` | `True` | |

**HEAD is worse than `530ce3eff` on three orderings and worse than `cba800fa8` on four. It is better
than either on none.** R16-A concluded *"better on none I could construct"* about the **recorder**;
that conclusion was right about the recorder and the same sentence is now true of the thing that
replaced it. The one ordering every arrangement fails identically — `O_H` — is the sink leak, which
R16-A already established rides the sink and which **no** arrangement of the flag touches. It is
therefore not a discriminator, and using it to argue "every arrangement fails at least one ordering"
is counting a constant as a variable.

**Reachability of `O_B`: production.** It is the shape the builder's own table calls *"the drain
erases the turn's fact"* and asserts `False`. Its "reachability: none today" note rests on *every
read precedes every drain*, which is true and is a property of the **callers**, not of this module.

### 3.2 · Claim 2 — **the negative claim, REFUTED**

**Falsifier stated first:** *if I can write an arrangement, entirely inside `instrument.py`, with no
turn identity, that answers every row of the builder's own table correctly and does not red any test
that HEAD passes except the one asserting the defect, the claim is false.*

I did not have to write one. Unparsing the three trees function-by-function:

```
HEAD :: record_catalogue_unavailable      cba :: record_catalogue_unavailable
    sink = _sink_for_record()                 sink = _sink_for_record()
    entry: dict = {...}                       entry: dict = {...}
    if type(count) is not int: count = None   if count is not None: entry['count'] = count
    if count is not None: entry['count'] = count
    sink.append(entry)                        sink.append(entry)
                                              catalogue_outage.set(True)          <-- deleted
```

`arm_turn_surface` and `catalogue_outage_registered` are **byte-identical in intent** between the two
(`catalogue_outage.set(any(_is_catalogue_row(e) …))` / `if catalogue_outage.get(): return True`).
**The entire difference between "the least wrong of four arrangements" and its predecessor is one
deleted statement.**

**Candidate R1** = HEAD + that statement, two lines including a comment:

| | O_A | **O_B** | O_C | O_D | **O_E** | **O_F** | O_G | O_H | O_I |
|---|---|---|---|---|---|---|---|---|---|
| HEAD | T | **F** | T | (F,F) | **F** | **F** | T | (T,T,T,1) | T |
| **R1** | T | **T** | T | **(T,F)** | **T** | **T** | T | (T,T,T,1) | T |

**R1 answers all four rows of the builder's own table correctly**, including the row it asserts as a
defect, and it needs **no turn identity**. Full suite under R1: **20 failed vs the baseline's 19** —
**exactly one new failure in 2255**, and it is
`test_THE_OUTAGE_FACT_IS_ORDERING_DEPENDENT__and_this_records_WHICH_orderings`, i.e. the test that
asserts the hole. Nothing else moved: **not** the two prompt-caching tests the arm's docstring cites,
**not** `test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER`, nothing.

**R1's honest cost, measured rather than asserted.** `O_J` — turn A arms/records/drains, turn B
**never arms** and reads:

| | O_J |
|---|---|
| HEAD | `(False, False)` — turn A's own answer already lost |
| R1 / `530ce3eff` / `cba800fa8` | `(True, True)` — turn A right, turn B leaks |

R1 trades a leak into **a turn that does not call `arm_turn_surface()`** — the exact shape
`test_EVERY_DISCOVERED_entry_point_arms_exactly_once_and_unconditionally` exists to forbid and
statically enforces — for the live correctness of the post-drain read. HEAD is not *right* on `O_J`;
it is wrong on turn A and accidentally right on turn B.

**So the precise, defensible statement is:** *restricted to turns that arm — which the gate makes
mandatory — an arrangement inside `instrument.py` is correct in every ordering measured, and it is
one statement away.* The negative claim as written is **false**.

#### Why the builder could not see it: the argument's premise is vacuous

`instrument.py:313–316`:

> *"a verifier proved they cannot both be fixed by any single assignment: making the derivation
> monotone (so `narrow → drain → arm` stops ERASING a true flag) **reds two tests**, and leaving it
> lowering keeps the erasure."*

`G-MONO` — rewrite the arm's `catalogue_outage.set(any(…))` as `if any(…): catalogue_outage.set(True)`,
verified on disk — **reds `0` of `2255`.** And the orderings are **unchanged** (`O_A…O_I` identical to
HEAD). Of course they are: with the writer deleted, no code path ever raises the flag, so "monotone"
and "lowering" are the same program. The incompatibility that justifies *"every arrangement that
lives in this module fails at least one ordering"* was **measured on a design the same commit
removed**, and it is stated in the present tense on the variable that no longer implements it.

**Reachability: production.** This is the sentence that closes the item and hands it to CP-2.

### 3.3 · Claim 3 — **T8 is closed; T9 is nine defeats, and `T9e` is the ordinary one**

**Falsifier stated first:** *if a terminal writer can bind `None` and stay `1 passed`, T9 exists.*

Control first: a writer in a function in a new module, `1 failed` ✅ — and `rglob` genuinely closed
T8 (a probe in `app/agentruntime/`, `app/routers/` and `app/services/` all red).

| # | injection (probe module written under `app/`, removed in `finally`) | ordinary? | term |
|---|---|---|---|
| CTL | a writer in a **function** in a new module | — | **`1 failed`** ✅ **T8 CLOSED** |
| **T9e** | the SQL hoisted to a **module-level constant** in the same module | **the most ordinary refactor there is** | **`1 passed`** ❌ |
| **T9d** | the SQL returned by a **helper in a third module** | the prompt named it | **`1 passed`** ❌ |
| **T9j** | the SQL as an f-string over a **constant imported from another module** | ordinary | **`1 passed`** ❌ |
| **T9a** | the writer at **module scope** | ordinary in a bootstrap/migration | **`1 passed`** ❌ |
| **T9b** | the writer is a **`lambda`** | ordinary | **`1 passed`** ❌ |
| **T9c** | the writer inside a **comprehension** | ordinary | **`1 passed`** ❌ |
| **T9f** | the writer in a **class body** (not a method) | contrived | **`1 passed`** ❌ |
| **T9g** | the module **cannot be parsed** — `except SyntaxError: continue` | **fail-OPEN** | **`1 passed`** ❌ |
| **T9h** | the executor reached as a **bare name**, not an attribute | ordinary | **`1 passed`** ❌ |
| T9i | the writer in a **nested `def`** | control | **`1 failed`** ✅ |
| T9-real | an **existing named** writer's SQL hoisted to a module constant | control | **`1 failed`** ✅ — the NV floor catches the LOSS |

**The shape of T9:** the gate discovers **files** now, but it still enumerates **containers**
(`FunctionDef` only) and **anchors on a string literal that must appear inside the call's own
arguments**. T8 was *"a gate whose file set is typed out cannot notice a writer arriving somewhere
else"*; T9 is the same sentence with *file set* replaced by *statement kinds* and *SQL source*. The
gate's own `sql_locals` mechanism was built for *"SQL is often assembled into a local first"* — and
it looks only at locals bound **inside the same function**.

**Reachability: production, and `T9e` is the live one.** `app/agentruntime/` is where CP-2's runtime
lands; a new writer there that names its SQL constant at module scope — which is how everybody writes
SQL constants — binds `None` at `1 passed`. The existing three writers are protected only by the NV
*floor*, which R16-A already recorded as a floor in both directions.

### 3.4 · Claim 4 — **route 23 is closed; ROUTE 24 is the ordering test's unit**

**Falsifier stated first:** *if a narrowing can run before the delegate and the entry point still be
exempted, route 24 exists.*

Every probe below is a real module written under `app/services/`, swept by the real
`_turn_entry_calls()`, removed in a `finally`; residue checked clean after every run.

| probe | discovered? | gate |
|---|---|---|
| CTL — un-armed entry point that narrows | yes | **`arms=[]`** ✅ red |
| CTL — `send_message`'s real shape (delegate, then narrow) | exempted | ✅ correct |
| R23a re-driven — narrow on an earlier line, delegate after | yes, `arms=[]` | ✅ **CLOSED** |
| **R24a — `return stream_response(await c.get_tool_definitions())`** | **NO — EXEMPTED** | ❌ |
| **R24b — the same, narrowing on a later line inside the call** | **NO — EXEMPTED** | ❌ |
| **R24c — the narrowing in a keyword argument of the delegating call** | **NO — EXEMPTED** | ❌ |

`test_cp0_instrument.py:2361` compares `_delegates[0] <= min(ln for ln, _ in narrowings)`. **Python
evaluates a call's arguments before the call.** So for `f(g())`, `g` runs first while `f`'s lineno is
lower-or-equal — the ordering test's unit (a line number) is not the ordering it is testing
(evaluation order). R23a was *"narrow first, delegate afterwards"*; **R24a is R23a written on one
line**, and the `<=` chosen to keep `send_message` green is what admits it. `G-LTE` confirms the `<=`
is genuinely load-bearing (`<` reds `send_message`), so the comment defending it is **true** — and
the property it states, *"no narrowing happens BEFORE the delegation"*, is not what the code checks.

**And the exemption's premise does not hold for its one live beneficiary.**
`stream_service.py:4950` — `stream_response` is `async def` **with a direct `yield`**: an async
generator function. `routers/messages.py:521` **creates a generator object and executes nothing**;
`arm_turn_surface()` at `stream_service.py:5003` runs only when Starlette first iterates it, after
`send_message` has returned. The exemption's stated justification — *"a delegating call that is
**unconditionally executed** … and that **precedes** every narrowing"* — describes something that
does not happen at line 521. It is harmless there only because `send_message`'s sole narrowing **is**
the delegate (measured: `narrowings=[(521, 'stream_response->(narrows)')]`,
`unconditional delegate lines=[521]`), and it stops being harmless the moment a real narrowing is
nested in the argument list.

**Did the shared definition remove a class of hole, or move where the next one appears?** It **moved
it, and it moved it up one level** — the answer R16-A predicted in its §9. Route 23 was *two
relations computed two ways*; unifying them was right and is guarded (`G-R23` reds). Route 24 is *one
relation computed correctly over the wrong domain*: the shared predicate is now exact about **which
statements** are unconditional and still silent about **what happens inside one**. The class removed
was "the two definitions disagree". The class that appeared is "the single definition's unit is a
line".

**Reachability: production, by construction.** `return stream_response(await c.get_tool_definitions())`
is a one-line inlining of code that exists today.

### 3.5 · Claim 5 — **the `try:` justification, graded — and the widening is a regression**

**Falsifier stated first:** *if a shape that was RED on `d23ea5592` is GREEN now and is not W2, the
widening exceeded its warrant.*

R16-A §11 specified the fix precisely: *"Accept a `Try` body at depth 1 **when no statement precedes
the arm in the chain** — this accepts W1 and W2, **still rejects W4**."* The delta accepted the whole
`Try` body regardless of position. Same probes, both test files, verified on disk:

| probe | on `d23ea5592` | on **HEAD** | |
|---|---|---|---|
| **W2** arm is the first statement of a `try:` | RED | **GREEN** | ✅ the fix, correct |
| **W4** arm in a `try:` **after `x = 1/0`** | RED | **GREEN** | 🔴 **R16-A said "still rejects W4"** |
| **W5** arm **last** in a `try:`, the narrowing in the **`except` handler** | RED | **GREEN** | 🔴 **a turn that narrows into nothing** |
| **W6** arm in a `try:`, narrowing after the whole `try/except` | RED | **GREEN** | 🔴 |
| **W7** arm in a `try` nested in a `try` — **depth 2** | RED | **GREEN** | 🔴 the docstring says *"depth 1 … and no further"* |
| W8 arm in an `except` handler only | RED | RED | ✅ |
| W9 arm in a `try/else` | RED | RED | ✅ |

**W5 is the one with teeth**: the arm is the last statement of a `try` body and the narrowing is in
the handler, so on the path that narrows, the arm **provably did not run**. That is the sixth
recurrence's shape, and it was red before this delta.

**Now the justification itself, which is what the prompt asked me to grade.** The builder writes:

> *"The honest property is SYNTACTIC and is now stated as such: the arm is not guarded by a branch a
> reader can see. … **What it deliberately does NOT claim** is that the arm executes — no static rule
> can."*

The disclaimer is **right and well made**, and it is the best sentence in this part of the delta. The
problem is that **the implementation does not implement the stated property**, in four measurable
spellings — each of which is an arm not guarded by any branch a reader can see, reported CONDITIONAL:

| probe | reported | is it guarded by a branch a reader can see? |
|---|---|---|
| R24f `for _row in arm_turn_surface():` | `conditional=[5]` | **no** — the iterator runs unconditionally |
| R24g `if arm_turn_surface() is not None:` | `conditional=[5]` | **no** — the arm is the *test*, not the body |
| R24h `finally: arm_turn_surface()` | `conditional=[8]` | **no** — `finally` always runs |
| **R24i** `with contextlib.nullcontext(arm_turn_surface()):` | `conditional=[6]` | **no** — and the `with` **body** at depth 1 **is** accepted, while its **header**, which runs strictly earlier, is not |

R24i is the clean inconsistency: the delta widened `With` bodies and left the `With` header out, and
nothing in the stated property distinguishes them. So the grade is: **the justification is honest
about its limits and is still a justification for a line that was drawn around the shape somebody
measured** — the identical criticism R16-A made of the previous version, and the builder's own text
says *"that is the rationalisation shape this run keeps paying for."* It is being paid for again, in
both directions at once: **too narrow** (four false positives above) and **too wide** (W4–W7).

Also: `test_cp0_instrument.py:2184` says *"Depth 1 through `with` / `async with` / `try` bodies, and
**no further**"*. `_unconditional_calls` recurses into `s.body`, so nesting is **unbounded** — W7 at
depth 2 is green. Comment-denies-code, same file, same function.

**Reachability:** W5 **production** (correct-looking code the gate now waves through); W4/W6/W7
production-shaped but rarer; R24f/g/h/i **adversarial / false-positive-on-unusual-but-correct-code**.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | the SQL is a **module-level constant** | ✅ T9e `1 passed` | **production — NEW (T9)** |
| " | the SQL comes from a **helper in another module** / an f-string over an imported constant | ✅ T9d, T9j `1 passed` | **production — NEW** |
| " | the writer is at **module scope** / a `lambda` / a comprehension / a class body | ✅ T9a/b/c/f `1 passed` ×4 | **production — NEW** |
| " | the module **does not parse** — `except SyntaxError: continue` | ✅ T9g `1 passed` | **fail-open — NEW** |
| " | the executor is a **bare name** | ✅ T9h `1 passed` | production — NEW |
| " | ~~a writer in any other module~~ | ✅ red in three packages | — **T8 CLOSED** |
| " | ~~`:7424`~~ / ~~two-step bind~~ / ~~alias~~ / ~~`*args`~~ / ~~`executemany`~~ | (R16-A) | — **CLOSED** |
| arm-order gate · no narrowing precedes the arming | **the narrowing is an ARGUMENT of the delegating call** | ✅ R24a/b/c EXEMPTED, control red | **production, by construction — NEW (route 24)** |
| " | ~~narrow-then-delegate~~ / ~~dead branch~~ / ~~uncalled nested `def`~~ | ✅ `G-R23` reds | — **CLOSED (route 23)** |
| " | a module-scope **lambda**; a narrowing at **module scope** | carried from R15/R16 | adversarial (unchanged) |
| the gate reds on an arm that may not run | **the arm is last in a `try:` and the narrowing is in the `except`** | ✅ **W5 RED→GREEN** | **production — INTRODUCED** |
| " | the arm is in a `try:` **after a statement that raises** | ✅ **W4 RED→GREEN** | production — **INTRODUCED**, and R16-A named W4 explicitly |
| " | the arm is in a `try` nested at **depth 2** | ✅ **W7 RED→GREEN** | adversarial — INTRODUCED |
| " | ~~an arm in a `with` whose `__enter__` raises~~ (W3) | carried | adversarial — now *declared* as out of scope, honestly |
| the gate does not red on correct code | ~~an arm as the first statement of a `try:`~~ (W2) | ✅ `G-W2` reds | — **CLOSED** |
| " | the arm in a `for` iterator / an `if` test / a `finally` / a `with` **header** | ✅ R24f/g/h/i `conditional=[…]` | adversarial (false positive) — **NEW** |
| the turn's outage survives the drain | **the drain empties the sink and nothing else holds the fact** | ✅ **`O_B` `False`; `530ce3eff` and `cba800fa8` both `True`** | **production — REGRESSION vs BOTH predecessors** |
| " | a **background task** drains the shared sink | ✅ `O_F` `False`; both predecessors `True` | latent — **REGRESSION** |
| " | **two recorders in one turn** | ✅ `O_E` `False`; `cba800fa8` `True` | latent — **REGRESSION vs `cba800fa8`** |
| the outage does not outlive its turn | a turn that narrows and **never drains** leaks the row into the next turn in the same context | ✅ `O_H` `(T,T,T,1)` on **all four** trees | production (pooled context) — **rides the SINK; unchanged and not a discriminator** |
| a tool-call row is classified and stamped from one name | ~~`chunk["tool"]` read twice~~ | ✅ `G-TOOL` reds | — **CLOSED** |
| " | **`tc.get("tool")` then `tc["tool"]`** — `stream_service.py:4884–4885`, a sub-agent chunk | ✅ mixed-mechanism, §7 | adversarial — **the identical shape to the fix this delta shipped** |
| a recorded value is read once | `chunk.get("source")` twice; `withheld_json`'s `w["tool"]` twice | ✅ `G01`/`G12` **SILENT on 2255** | — **strengthening unguarded, 3rd round** |

---

## 5 · The red-ability table — **with a denominator I derived myself**

**How I derived it.** The prompt says the builder took `11` *"from your predecessors' verdicts"*.
R16-A's §9 enumerates **12** findings in my scope alone (7 production + 5 adversarial); R16-B's
enumerates **8**. **The denominator across the two verdicts is 20, not 11.** Within my scope I take
the denominator to be R16-A's **12 findings** plus the **4 facts this delta newly tightened that need
a guard of their own** (the `<=` ordering rule, the arm's derivation, the `Try` widening's bound, and
the monotone claim) = **16**.

| # | R16-A finding / newly-tightened fact | injection | result | closed? |
|---|---|---|---|---|
| 1 | T8 — the gate's hardcoded module pair | `G-T8` revert to the 2-tuple | **`1 failed`** ✅ | **YES** |
| 2 | route 23 — the blanket delegation exemption | `G-R23` revert to `ast.walk` | **`1 failed`** ✅ | **YES** (route 24 opened) |
| 3 | W2 — the `try:` false positive | `G-W2` drop `Try` from the carriers | **`1 failed`** ✅ | **YES** (W4–W7 opened) |
| 4 | `chunk["tool"]` read twice | `G-TOOL` re-read at the stamp | **`1 failed`** ✅ | **YES** |
| 5 | the outage guard green on the artifact it replaced | run the new guard on `530ce3eff` | **`1 failed`** ✅ | **YES** |
| 6 | G05 — `catalogue_outage()`'s value bound | method DELETED | n/a | **YES, by deletion** |
| 7 | `catalogue_outage`'s `w["scope"]` read twice | same deletion | n/a | **YES, by deletion** |
| 8 | **G01 — `chunk.get("source")` read twice** | re-read at the classify | **`19 failed` = BASELINE, 2255 tests** | **NO — SILENT, 3rd round** |
| 9 | **G12 — `withheld_json`'s walrus** | de-walrus it | **BASELINE, 2255 tests** | **NO — SILENT, 3rd round** |
| 10 | **O2/O4 — the regressions the revert was for** | `O_E`/`O_F` head-to-head | **`False`/`False`; `cba800fa8` `True`/`True`** | **NO — relocated, not closed** |
| 11 | the O1/O6-D sink leak | `O_H` | `(T,T,T,1)` on all four trees | **NO — OPEN, and honestly declared** |
| 12 | W3 — a `with` whose `__enter__` raises | carried | accepted by design | **NO — declared** |
| 13 | the module-scope lambda | carried | — | **NO — carried adversarial** |
| 14 | the module-scope narrowing | carried | — | **NO — carried adversarial** |
| 15 | **NEW** the `<=` delegation ordering rule | `G-LTE` `<=` → `<` | **`2 failed`** ✅ | **guarded ✅** |
| 16 | **NEW** the arm's derivation | `G-ARM` delete it | **`2 failed`** ✅ | **guarded ✅** |
| 17 | **NEW** the `Try` widening's bound (*"no statement precedes"*) | W4/W5/W6/W7 | **RED → GREEN ×4** | **NOT IMPLEMENTED, NOT GUARDED** |
| 18 | **NEW** *"monotone … reds two tests"* (`instrument.py:313`) | `G-MONO` | **`0 of 2255`** | **FALSE** |
| — | the NV floor | `G-NV` | `130 passed` — **not a valid probe alone** | carried |
| — | R1 (my candidate) | restore the writer | **exactly 1 new failure in 2255** | — |

**Red-able and closed: 9 of 16 — `56%`.** (1–7, 15, 16.)
**Independent re-run of the builder's `10 of 11`: it does not reproduce.** The denominator across
both verdicts is **20**; within my scope alone it is **16**, which is already larger than the
builder's figure for the whole run. Two of the "closed" items are closed by **deletion** rather than
by a guard, which is the right call and should be scored as such rather than as coverage. And the
eleventh — the one the builder *declares* unguarded with a reason — sits in Verifier B's scope, while
**three** in mine (`G01`, `G12`, and the `Try` widening's bound) are unguarded **without** a
declaration, two of them for the third consecutive round after R16-A asked for them by name.

---

## 6 · Independent re-run of the read-twice sweep

**Control asserted on a fixture BEFORE any real file is read** — this measurement has been wrong
twice and both times in the author's favour, so the control is not optional:

```
CONTROL PASSED: ['membership_then_read', 'reads_twice_mixed', 'reads_twice_same_mechanism']
                | mixed: ['membership_then_read', 'reads_twice_mixed']
```

`writes_only` (six write forms), `write_then_read` and `local_literal` are all correctly **excluded**;
a same-mechanism site, a mixed-mechanism site and an `in`-then-`[]` site are all correctly **found**.

**Definition** (mine, stated before the numbers): inside one function body, the same
`(container source-text, key)` read two or more times via `X[k]` (Load only), `X.get(k[, d])` or
`k in X`, where the container is not a literal constructed in that same function and the key is not
written in it. **Mixed-mechanism** = the reads do not all use one mechanism.

| | builder's claim | **my measurement, scope A** |
|---|---|---|
| same-fact sites | **6** | **100** |
| mixed-mechanism | **0** | **35** |
| `instrument.py` alone | — | **3 sites, 0 mixed** (`dedupe_recorded_calls`: `c['args']`, `c['iteration']`, `c['tool']`) |

**`6` does not reproduce under any definition I can construct** — not for scope A (100), not for
`instrument.py` alone (3). **`0 mixed-mechanism` is refuted outright**, and the refutation is in the
same defect class as the delta's own headline fix:

**`stream_service.py:4884–4885`** — `_run_subagent_call`:

```python
if tc.get("tool"):
    tools_used.append(tc["tool"])
```

`tc = ch.get("tool_call")` from a sub-agent gateway chunk. Gate on one value, append another —
**exactly** `ensure_tool_call_instrumented`'s `chunk["tool"]`, which this delta fixed and wrote a test
for, in the same service, unfixed and unswept. Plus **six** mixed-mechanism `chunk_data[…]` sites in
`_emit_chat_turn` (`finish_reason`, `suspend`, `usage`, `llm_call_count`, `response_id`,
`context_size`, all `.get` then `[]`, all on a gateway-supplied mapping) and
`_project_ambient_book_schema`'s `params['required']`.

**Reachability: adversarial-input only** for all of them — the same class the delta's own fix has, and
the reason to record them is that the sweep that found the fixed one reported zero.

I do **not** raise the remainder (asyncpg `Record` reads in `app/routers/`, self-built `gen_params`
dicts): the threat model is *a mapping supplied by another party*, and those are not it. That
exclusion is a judgement and I state it so it can be argued with rather than folded into a number.

---

## 7 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| `_mods` → `rglob` | a writer that is not a `FunctionDef` | module scope, `lambda`, comprehension, class body | **NO — T9a/b/c/f, `1 passed` ×4** |
| " | SQL that is not a literal in the call | module constant, helper module, imported f-string | **NO — T9e/d/j, `1 passed` ×3** |
| " | a module the sweep cannot parse | wrote one | **NO — T9g, fail-OPEN** |
| " | whether the NV catches losing a real writer to the same refactor | hoisted voice's SQL to a module constant | **YES** ✅ `1 failed` |
| the delegation exemption's ordering rule | a narrowing inside the delegate's arguments | one line, two lines, a kwarg | **NO — route 24 ×3** |
| " | whether the `<=` is load-bearing or a loosening | `G-LTE` | **it is load-bearing** ✅, and the comment is true |
| " | whether the premise holds for its live beneficiary | checked `stream_response` for `yield` | **NO — it is an async generator; nothing runs at line 521** |
| `_unconditional_calls` shared by both relations | whether the `Try` widening stayed inside its warrant | W4/W5/W6/W7 on both test files | **NO — four RED→GREEN, and R16-A named W4** |
| " | whether the stated property matches the code | `for` iterator, `if` test, `finally`, `with` header | **NO — four false positives** |
| " | whether *"depth 1 and no further"* is true | W7 | **NO — recursion is unbounded** |
| `_tool` bound once | whether its sibling `_source` got a test | `G01` on 2255 | **NO — SILENT, 3rd round** |
| " | whether `withheld_json`'s walrus got a test | `G12` on 2255 | **NO — SILENT, 3rd round** |
| " | whether the same shape survives elsewhere in scope | full sweep with an asserted control | **NO — `tc['tool']` and 6 `chunk_data` sites** |
| the outage revert | whether the new guard reds on the artifact it replaced | ran it on `530ce3eff` | **YES** ✅ |
| " | whether the revert is better than what it replaced | nine orderings, four trees | **NO — worse on 3 vs `530ce3eff`, 4 vs `cba800fa8`, better on none** |
| " | whether the negative claim is true | built R1, ran 2255 tests | **NO — REFUTED, one line** |
| " | whether the argument justifying the claim holds | `G-MONO` | **NO — `0 of 2255`** |
| " | whether the doc block was updated with the revert | read `:307–329` | **NO — it still describes the recorder** |
| `catalogue_outage()` deleted rather than kept | whether deletion was the right call | the R16-A `w["scope"]` finding dies with it | **YES** ✅ — the best decision in the delta |

---

## 8 · Where the builder's documentation of a residual is wrong

1. **`instrument.py:307–329` describes the rehousing that `:330` reverted.** *"So the fact moved to
   the object whose lifetime **is** one turn: the recorder"* (`:324`) and *"Neither failure mode is
   constructible against that lifetime"* (`:326`) sit directly above
   `catalogue_outage: ContextVar[bool]`. Both sentences were measured **false** by R16-A when they
   described the recorder; they are now attached to a variable that does not even attempt them. This
   is the listed pattern — *a guard loosened while the comment beside it denied it* — in its
   documentation form. **Production-reachable: it is the first thing a reader of this variable sees.**
2. **`instrument.py:313–316` — *"making the derivation monotone … reds two tests"* — is false.**
   `G-MONO` reds **0 of 2255**. It is the premise of the conclusion that hands this item to CP-2.
3. **The revert is not a revert.** It is a third arrangement, `cba800fa8` minus one statement, and it
   is worse than **both** predecessors. *"the least wrong of the four arrangements measured"* is not
   reproducible: on nine orderings it is better than neither and worse than both.
4. **`test_THE_OUTAGE_FACT_IS_ORDERING_DEPENDENT…`'s failure message is false.** It tells the next
   reader that a red means *"the ordering hole is CLOSED … someone has given the turn an identity."*
   `530ce3eff`, `cba800fa8` and my one-line R1 all red it **without** a turn identity. A message that
   misattributes its own cause is worse than none: it instructs the next round to update the board
   rather than to look at the diff. Same class as *"a repair layer that emits parseable-but-wrong
   output needs a post-condition."*
5. **R16-A specified the `Try` fix and the delta implemented a wider one.** *"still rejects W4"* was
   in the text; W4 is green. Seventh occurrence of *fixed at what a verifier pointed at rather than
   what it meant* — and this time it is the reverse polarity: the fix overshot rather than undershot,
   which the record has not seen before and which the next round's brief should say.
6. **`_unconditional_calls`'s *"Depth 1 … and no further"* is false of its own recursion** (W7).
7. **The delegation exemption's premise does not hold for its one live beneficiary.**
   `stream_response` is an async generator; line 521 executes nothing.
8. **Exemplary, and it should be said first in the next brief.** T8 is **closed at the class for
   modules** — probes in three packages red. Route 23 is closed with a real test that reds on the
   previous artifact. W2 is closed. `chunk["tool"]` is closed with a test that reds. **The new outage
   guard reds on the artifact it replaced** — the exact defect R16-A raised, fixed properly. The
   `catalogue_outage()` method was **deleted rather than left unread**, citing this package's own
   precedent, and that removed R16-A's `w["scope"]` finding for free. And `G-LTE` shows the `<=` is a
   measured necessity with a true comment beside it, not a loosening. **Five of six claims have
   red-able guards; the failure of this round is concentrated in one decision (the revert) and one
   over-wide predicate (`Try`).**

---

## 9 · Convergence, my scope

| round | production-reachable | adversarial-input only | changed lines (scope A) | introduced by the delta | **introduced per 100 changed lines** |
|---|---|---|---|---|---|
| 13 | 13 | 5 | 150 | 3 | 2.00 |
| 14 | 9 | 6 | 258 | 2 | 0.78 |
| 15 | 6 | 6 | 89 | 2 | 2.25 |
| 16 | 7 | 5 | 739 | 5 | 0.68 |
| **17** | **8** | **5** | **415** | **5** | **1.20** |

**Production-reachable, this round:** the revert measured worse than both predecessors (`O_B`/`O_E`/`O_F`);
the negative claim refuted by a one-line candidate; the stale `#:` block on `catalogue_outage`; the
false monotone claim; the `Try` widening's regression (W4–W7, counted once, W5 the live one); route 24
(three variants, counted once); T9 (nine defeats, counted once); `G01`+`G12` still silent (counted once).
**Adversarial:** R24f/g/h/i false positives (counted once); `tc['tool']` and the six `chunk_data`
mixed-mechanism sites (counted once); W3; the module-scope lambda; the module-scope narrowing.

**Introduced by this delta — 5:** (i) the outage arrangement now loses `O_B`/`O_E`/`O_F`, which both
predecessors held; (ii) the `Try` widening flipped W4/W5/W6/W7 RED→GREEN; (iii) route 24, opened by
the new line-number ordering rule; (iv) the `#:` block left describing a mechanism the same commit
deleted; (v) the new guard's misattributing failure message.

**Closure: 6 of R16-A's 12 — 50%**, down from 75%. Closed: T8; route 23; W2; `chunk["tool"]`; the
guard-green-on-the-replaced-artifact; the `w["scope"]` read-twice. Not closed: the sink leak
(declared, owner CP-2); the three silent strengthenings (`G05` closed by deletion, `G01` and `G12`
still silent); the O2/O4 regressions (**relocated, not closed**); W3; the two module-scope routes.

**Which number should this run steer by?** **Neither, and R16-A was right that the shape is what
matters — but the shape has now changed sign and that is the reportable event.** Raw introduced reads
3, 2, 2, 5, **5**; normalised 2.00, 0.78, 2.25, 0.68, **1.20**. R16 was the low point *per line* on a
739-line delta; this delta is 415 lines and the rate nearly doubled. More importantly, **for the first
time in the series a graded delta made a measured property worse in three orderings while describing
itself as a revert, and it did so with a guard that reds correctly and a message that explains the
red wrongly.** That is not a defect the introduction rate can see. **Steer by the raw count with the
regression flagged separately**, and keep three consecutive rounds at `introduced == 0` as the
terminating condition — this is not one of them, and the round in which the largest change is the
least-well-reasoned one is now the fifth consecutive.

---

## 10 · What would have to be true for this to PASS

* **Restore `catalogue_outage.set(True)` in `record_catalogue_unavailable`.** One statement. It
  answers all four rows of the builder's own table, costs one test in 2255 (the one asserting the
  hole), needs no turn identity, and closes `O_B`, `O_E` and `O_F` together. Then **delete the
  "every arrangement fails" paragraph** and re-scope CP-2 to the sink leak (`O_H`), which is the only
  ordering no arrangement of the flag can touch.
* **Rewrite `instrument.py:307–329`** so it describes the `ContextVar[bool]` beneath it, and **delete
  the monotone sentence** or re-measure it — it currently reds nothing.
* **Fix the guard's failure message** to say what a red actually means: *the post-drain read now
  returns the outage — check whether the writer was restored before assuming a turn identity exists.*
* **Bound the `Try` widening as R16-A specified** — accept the arm when no statement precedes it in
  the chain — and add W4 and **W5** as red-able probes. W5 is the one that matters.
* **Make the delegation ordering test compare evaluation order, not line numbers**: a delegate does
  not precede a narrowing that is one of its own arguments. Two lines: exclude narrowings that are
  descendants of the delegating call's `args`/`keywords`, or require the delegate's whole statement
  to contain no narrowing.
* **Anchor the terminal-write gate on the resolved SQL, not on a literal in the call** — follow
  module-level constants and cross-module imports the way `sql_locals` already follows function
  locals — and **walk `Lambda`, `Module.body` and `ClassDef.body`**, not just `FunctionDef`. Make
  `except SyntaxError` **fail closed**: an unparseable module under `app/` is a red, not a `continue`.
* **Give `G01` and `G12` a test each.** R16-A asked for both by name; the delta added a test for a
  third site in the same class and left these two silent for a third round.
* **Sweep `tc['tool']` at `stream_service.py:4884` and the six `chunk_data` sites** in
  `_emit_chat_turn` — same shape, same service, same threat model as the fix this delta shipped.
