# CP-1 · round 15 · V-CODE — Verifier A (the instrument)

*Artifact frozen at `cba800fa81f4a663ae363e9f871a953745ec393b`. `git rev-parse HEAD` verified at the
start of this session and again immediately before writing this file; **HEAD did not move**, and
`git status --porcelain` is **empty** at both ends. I wrote no tracked file other than this one, ran
no `git checkout`, and touched nothing live.*

**Two fresh scratch trees, both proved un-nested before anything ran.** `…/scratchpad/r15a/cs`
(behaviour + the terminal-write gate) and `…/scratchpad/r15b/cs` (the arm-order sweep), each with its
own pristine snapshot taken at copy time. The path was decomposed and every **ancestor** component
checked against every stale scratch name this workspace carries (`cs`, `cs-pristine`, `r12`,
`r13cs`, `r13pristine`, `r14a`, `repo`, `pkgcopy`, `mt`, `mt11`, `inj`, `probe`, `head`, `audit`,
`gochk`, `sb`, `vb`, `vlive_r5`) — **zero stale ancestors**; only the leaf is `cs`, which is not a
nesting. The five files under test were then sha256-compared against the artifact and printed equal.
**Every injection printed a source-content assertion before its suite ran**; every anchor was
asserted unique; reversal is always a restore from the pristine snapshot.

---

## 0 · The fact that frames the whole verdict

**The graded delta contains no production change in my scope at all.**

```
git diff --stat b30db5b8..cba800fa
  services/chat-service/app/agentruntime/contract.py   | 88 +      <- Verifier B
  services/chat-service/app/agentruntime/manifest.py   | 17 +-     <- Verifier B
  services/chat-service/app/agentruntime/surface.py    | 39 +-     <- Verifier B
  services/chat-service/tests/test_cp0_instrument.py   | 89 +-     <- MINE, and it is a TEST
  services/chat-service/tests/test_cp1_membrane.py     | 48 +-     <- Verifier B
```

`instrument.py`, `stream_service.py`, `voice_stream_service.py`, `knowledge_client.py` and
`app/routers/` are **byte-identical to R14's artifact**. So every behavioural finding R14 recorded
OPEN in my scope is open by construction, and the only thing there is to grade is the gate itself.

**And the gate gained no test.** My scratch baseline is `2 failed, 115 passed` — *identical* to
R14's, on a delta that added 89 lines to that file. The delta rewrote gate machinery and shipped
**zero new assertions**, which means the four route fixes below are guarded only by the routes
themselves and by nothing that would notice if they regressed.

---

## 1 · Verdict

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the gate also matches `ast.AnnAssign`; `:7424` was still bindable to `None`** | **PASS on the AnnAssign half — CONFIRMED FAIL on `:7424`.** T2 now **reds** (term `1 failed`), and so does the annotation-then-rebind variant. But **T3 — the clean finish binding `None` — is still `term 1 passed, wide baseline`. R10's I13, SEVEN rounds open.** T6, an ordinary two-line extraction, is also still green. **I built the check that catches them: 7/7 red, 0 false positives** (§3.1) | **production-reachable (regression channel) ×2** |
| 2 | **route 20 was created by the previous fix; it now follows import edges. Verify, and find twenty-one** | **PASS on route 20 — and TWO new routes, both created by this fix.** R20b now reds `2 failed` (was `6 passed`). But the same commit added **two fresh bare-name/blanket exemptions**: **route 21**, a `_`-prefix skip that makes a `_`-prefixed transitive narrower invisible (`6 passed` vs control `2 failed`) *while the function's own docstring twelve lines above still says the opposite*; and **route 22**, `fn.name in _NARROWING_CALLS`, a bare-name exemption across all of `app/` with **no allow-list entry, no written reason, no staleness test** — and it is **load-bearing**: disabling it turns the gate `2 failed` | **production-reachable ×2, by construction** |
| 3 | **route 19 (`async def` only) is closed; is there an entry point that is neither `def` nor `async def` at module scope?** | **PASS on route 19 — FAIL on the sibling, twice.** A sync `def` now reds `2 failed`. But `ast.FunctionDef`/`AsyncFunctionDef` is still the *only* shape considered: a **module-scope lambda** and a **narrowing at module scope inside no function** are both `6 passed`, invisible | adversarial-input only (see §3.3) |
| 4 | **`_NOT_A_TURN` grew two entries; is each genuinely not a turn, and is the narrowing-primitive rule sound?** | **PASS on the content — FAIL on the form, and the prompt's own premise is wrong.** `_NOT_A_TURN` grew **one** entry, not two. `effective_enabled_tools` is genuinely not a turn (it *takes* `withheld_sink` as a parameter — it runs inside someone else's turn). The second helper was exempted by a **different mechanism** that carries none of the allow-list's discipline. The rule's *content* is sound; its *form* is route 20's mechanism re-created inside route 20's fix | **production-reachable, by construction** |
| 5 | **the flag is INERT; keep, simplify, or remove?** | **INERT confirmed a THIRD round — and I rule: REMOVE the writer, REPLACE the home of the fact, do not delete the mechanism.** X7 is at baseline for the third consecutive round; every production read still precedes every drain; and I measured that the derivation **cannot** be fixed in place — making it monotone reds two tests, leaving it lossy erases a real outage. Full ruling with its deciding evidence in §5 | production (an inert floor); its two live effects are both defects |
| 6 | **the container `try`: a tuple or generator sink now loses every row** | **CONFIRMED, unchanged.** tuple / generator / undeletable subclass → `withheld_json()` is `None`; the matched plain-list control records the row | adversarial-input only (behavioural **regression** vs the R13 artifact) |

**Overall: FAIL.** Three of six claims pass on their stated half and fail on the sibling; the round's
own headline sentence — *"an over-approximation is only safe in the direction of suspicion"* — is
falsified **twice inside the commit that wrote it**.

### The most valuable thing this round produced, which the prompt asked for

**The check that closes `:7424` exists, is forty lines, reds all seven known defeats, and is green on
the pristine tree.** R11 §8, R12 §8, R13 §3.4 and R14 §8 each *described* it; nobody built it, and the
finding is now seven rounds old. I built it and measured it (§3.1). That removes the last defensible
reason to carry I13 forward: it is no longer "the harder version", it is a diff.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every fix in the graded delta that falls in my scope. `contract.py` / `manifest.py` / `surface.py`
are Verifier B's.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| the gate lifts `ast.AnnAssign` into `_assigns` (`test_cp0_instrument.py:1541–1547`) | **it is the test** | **yes** — T2 reds term `1 failed`, wide 1 extra; T2b (bare annotation + plain rebind) reds too | **yes for AnnAssign, NO for the property.** It still asserts *one syntactic form of one local*, so T3 and T6 remain green. **No new test was added** |
| `arming` keyed `MODULE::NAME` + import-following (`:2168–2200`) | **NO — no new test** | **yes, by injection** — R20b `2 failed` (was `6 passed`) | **yes**, and the matched control (R20a alone) also `2 failed`. **The fix is real and it is unguarded**: nothing in the suite would notice a revert to the bare-name closure |
| route 19 — `ast.FunctionDef` accepted (`:2204–2210`) | **NO — no new test** | **yes, by injection** — a sync `def` entry point `2 failed` (was `6 passed`) | **yes.** Also unguarded |
| **NEW** `_`-prefix skip (`:2211–2215`) | **NO** | — | — **it is not a fix, it is route 21.** Reveals nothing today (`+0` discovered) and hides a matched-pair probe: `6 passed` vs control `2 failed` |
| **NEW** `fn.name in _NARROWING_CALLS` skip (`:2219`) | **NO** | — | — **it is route 22.** Disabling it turns the gate **`2 failed`**, so it is suppressing a real offender by bare name with no recorded reason |
| `_NOT_A_TURN` += `tool_surface.py::effective_enabled_tools` | **yes**, transitively — `test_NO_ALLOW_LIST_ENTRY_IS_STALE` | **yes** (the entry is discovered, so it is not stale) | **yes.** This is the round's one clean piece of work: a written reason, a discovered entry, and a staleness test over it — which is exactly what route 22 lacks |
| `top_level_arm_lines` — **untouched** | it is the test | **reds on CORRECT code** — R18 re-driven: an arm inside `async with contextlib.AsyncExitStack()` gives `1 failed` | **NO.** R13's route eighteen, **third round**, unchanged |
| `record_catalogue_unavailable` **sets** the flag (`instrument.py:440`) | **NO**, unchanged from R13 and R14 | — | — **X7: baseline for the THIRD round.** And F2 shows it is not merely unguarded, it is **redundant** — the derivation at `:372` re-computes the same fact three lines away |
| the container `try` (`instrument.py:694–698`) | **NO**, unchanged from R14 | — | — B1 re-driven and unchanged |

---

## 3 · The falsifier, per claim — stated before the search

### 3.1 · The terminal-write gate — **PASS on AnnAssign, FAIL on `:7424`**

**Falsifier (stated first):** any way to stop a persisted `withheld_tools` column carrying the
recorder's value while the gate is green; and for each, whether an ordinary edit reaches it.

Baselines I measured myself: term (`test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE…` alone)
**`1 passed`**; wide (7 suites) **`2 failed, 324 passed`**.

| # | injection | ordinary or contrived? | term | wide |
|---|---|---|---|---|
| T1 | `_withheld_json = None` at `:6341` | — | **`1 failed`** ✅ | 1 extra ✅ |
| **T2** | `_withheld_json: str \| None = None` — **R14's finding** | ordinary refactor | **`1 failed`** ✅ **CLOSED** | 1 extra ✅ |
| **T2b** | bare annotation, then a plain rebind from a constant | ordinary | **`1 failed`** ✅ | 1 extra ✅ |
| **T3** | **`:7424`, the clean finish, binds `None`** — R10's I13 | **not even a refactor** | **`1 passed`** ❌ | **baseline** ❌ |
| **T6** | `_wj_tmp = None` then `_withheld_json = _wj_tmp` | **ordinary** (two-line extraction) | **`1 passed`** ❌ | **baseline** ❌ |
| T11 | keep the real bind, then `_withheld_json = _withheld_json and None` | contrived | `1 failed` ✅ | 1 extra ✅ |
| T4 | CONTROL — voice `:684` binds `None` | — | `1 failed` ✅ | 1 extra ✅ |

**A1 · The AnnAssign half is genuinely closed, and it was closed at the class.** T2 *and* T2b red, so
the fix covers the annotated form and the annotate-then-rebind form. Credit where it is due: this is
the finding R14 led with, and it is fixed.

**A2 · `:7424` is unchanged, and this is now its seventh round.** `_emit_chat_turn` has no `withheld*`
local at all, so `bad_bindings` is vacuous over it; the only obligation the gate places on that
function is that the string `withheld_json` appears *somewhere* in its 1,200 lines — which it still
does, four more times (`:6970`, `:7132`, `:7592`, `:7633`), all of which survive T3 untouched. **This
is the path every successful turn takes.** R10 reported it as I13; R11–R14 each re-measured it green;
the round that rewrote the gate for the second consecutive time did not move it.
**Reachability: production-reachable as a regression channel.**

**A3 · The shape of check that catches it without a false positive — built and measured, not
described.** Anchor per **BIND**, not per assignment form: *for every `execute`/`fetchval`/`fetchrow`
whose SQL names `withheld_tools`, at least one argument of **that call** must be recorder-derived* —
containing a `withheld_json()`/`absorb()` call, or a local transitively assigned (through `Assign`
**and** `AnnAssign`) from one, or the conduit parameter. Depth-bounded so a cycle cannot hang it.
Forty lines. Measured against the same scratch tree:

| case | this check |
|---|---|
| **PRISTINE — the false-positive test** | **green** ✅ |
| T1 `_withheld_json = None` | **RED** (`:6288`, `:6350`) |
| T2 annotated | **RED** |
| **T3 `:7424` the clean finish** | **RED** (`_emit_chat_turn`, `:7363`) ✅ |
| **T6 two-step extraction** | **RED** ✅ |
| T5 walrus | **RED** ✅ |
| T7 tuple target | **RED** ✅ |
| T4 CONTROL voice | **RED — and now naming the BIND** (`voice_stream_response`, `:635`), not `reads_recorder` |

**7 of 7 red, 0 false positives.** It also cannot produce R12's G5 false positive, because it keys on
the SQL text of the individual call rather than on a column name matched anywhere in the function.
The control now reds for the right reason, which R14 correctly said it did not.

### 3.2 · Route 20, and route twenty-one — **PASS, then TWO new routes**

**Falsifier:** any construction that puts a narrowing above an arming, or a narrowing entry point with
no arming, while the gate is green; any exemption granted on a false basis.

Gate baseline: **`6 passed`**. Every probe is a file created under `app/`, removed on restore.

| probe | discovered? | gate |
|---|---|---|
| CTL — a plain `async def` entry point that narrows and never arms, in `app/services/` | yes | **`2 failed`** ✅ |
| **R20b — + a same-named ARMING helper in `app/agentruntime/`** (R14's route 20) | **yes** | **`2 failed`** ✅ **CLOSED** |
| **R21c — a `_`-prefixed entry point narrowing *transitively* through a helper that is itself exempt** | **NO** | **`6 passed`** ❌ |
| R21c-ctl — byte-identical, non-underscore name | yes | **`2 failed`** ✅ |
| **R22 — an entry point *named* `discovery_seed_for_surface`** | **NO** | **`6 passed`** ❌ |
| R22b/c/d — the same, named `_budget_and_register` / `filter_intent_gated_setup_tools` / `get_admin_tool_definitions` | **NO** ×3 | **`6 passed`** ×3 ❌ |

**C1 · Route 20 is closed, and the fix is the right one.** `arming` is now `MODULE::NAME` with an
`ImportFrom` edge for cross-module delegation. A same-named arming helper in another package no
longer absolves anything. I re-drove R14's exact probe and it reds. Note also that the import-map
handles only `ImportFrom` with an `app.`-prefixed module — a **relative** import (`from .x import y`)
or a plain `import app.x as y` falls back to the module-local default, which fails toward *more*
scrutiny. That is the correct direction and worth recording as deliberate.

**C2 · Route twenty-one — the `_`-prefix skip, and the docstring beside it still denies it.** The new
line is:

```python
if fn.name.startswith("_") and f"{mod}::{fn.name}" not in _NOT_A_TURN and not any(
    isinstance(n, ast.Call) and _called_name(n) in _NARROWING_CALLS
    for n in ast.walk(fn)
):
    continue
```

`narrowings` is computed from `reaching` — the **transitive** closure — but this filter admits a
`_`-prefixed function only on a **direct** call to a primitive. So a `_`-prefixed entry point that
narrows through one hop of helper is dropped before `_narrowings_in` ever runs. Measured with a
matched pair whose helper is exempt for its own reason, so the probe entry point is the only thing
the gate could red on: **`6 passed` vs control `2 failed`.**

`_turn_entry_calls`'s own docstring, **twelve lines above the new filter and unedited**, reads:

> *"Entry points are DISCOVERED, not listed — **including `_`-prefixed ones, because a leading
> underscore is a naming convention and not a guarantee that nothing routes to it.**"*

That is now false, and the sentence that made it false is in the same function. **This is the
builder's own named pattern — a guard loosened while the comment beside it claims it has not been.**
It reveals `+0` today, so it is latent-not-live; it is **production-reachable by construction**,
because the three functions the file says were *deliberately removed* from `_NOT_A_TURN`
(`_stream_with_tools`, `_emit_chat_turn`, `_run_subagent_call`) are all `_`-prefixed, and the stated
reason for removing them was that **discovery would catch them if they ever became turns.** This
filter is exactly the thing that stops discovery catching them.

**C3 · Route twenty-two — a bare-name exemption, in the commit that condemned bare-name exemptions.**

```python
if fn.name in _NARROWING_CALLS:
    continue
```

`_NARROWING_CALLS` is a set of five bare names. Any function under `app/` bearing one of them is
skipped **unconditionally** — measured on four of the five, all `6 passed` against a `2 failed`
control. And it is **load-bearing**: disabling it alone turns the pristine gate **`2 failed`**,
revealing `services/tool_surface.py::discovery_seed_for_surface`. So a real offender surfaced by the
widened sweep was silenced by a blanket rule rather than by an allow-list entry.

Set that against the commit message ten lines above it — *"An over-approximation is only safe in the
direction of suspicion"* — and against `_NOT_A_TURN`'s own header — *"each needs a stated reason,
because 'it is not a turn' is exactly what would be said about a turn nobody armed"*. Route 22 grants
an exemption, over-approximates toward **less** scrutiny, has **no** stated reason at any site, and
is **not** covered by `test_NO_ALLOW_LIST_ENTRY_IS_STALE`, which only ever sees `_NOT_A_TURN`.
`app/agentruntime/` defines none of the five names today; CP-2's arming runtime is scheduled for
exactly that package. **Production-reachable by construction — the same sentence R14 wrote about
route 20, one round later, about the fix for route 20.**

### 3.3 · Route 19's sibling — **PASS on 19, FAIL on the sibling**

**Falsifier:** a turn entry point the sweep cannot represent at all.

Route 19 is closed: a sync `def` twin of the control now reds `2 failed`. The sibling assumption
underneath it — *an entry point is a function-definition node* — is still there.

| probe | discovered? | gate |
|---|---|---|
| a **module-scope lambda** bound to a name, narrowing (`ast.Lambda`) | **NO** | **`6 passed`** |
| a narrowing at **module scope**, inside no function at all | **NO** | **`6 passed`** |

**Reachability: adversarial-input only, and I will not inflate it.** Neither shape appears in this
codebase, both would block the event loop at import time, and neither is a plausible product of an
ordinary edit. I record them because the question was asked and the answer is *yes, two* — not
because they should be fixed before routes 21 and 22.

### 3.4 · `_NOT_A_TURN`'s new entry and the narrowing-primitive rule — **content sound, form wrong**

**Falsifier:** an exemption granted to something that narrows *and* begins a turn; an exemption whose
stated reason is not true of the code.

**The prompt's premise is inaccurate and it matters.** `_NOT_A_TURN` grew **one** entry
(`services/tool_surface.py::effective_enabled_tools`), not two. The second budgeting helper —
`discovery_seed_for_surface` — was exempted by route 22's blanket rule instead, which is precisely the
substitution worth noticing: one helper got the allow-list's discipline (a written reason, a
discovered entry, a staleness test) and the other got a bare name in a set.

* **`effective_enabled_tools` is genuinely not a turn.** Its signature takes
  `withheld_sink: list[dict] | None = None` and it passes that sink to `_budget_and_register`. A
  function that *receives* the turn's sink as a parameter is by definition running inside a turn
  somebody else armed; arming here would replace a sink already holding rows, which is the discard
  the sixth recurrence was about. The stated reason is true of the code.
* **The rule *"a function that IS a narrowing primitive is not an entry point"* is sound as a
  proposition** — `discovery_seed_for_surface` and `_budget_and_register` are the machinery entry
  points call, not entry points — **and unsound as written**, because it is keyed on a bare name over
  the whole package rather than on the two specific functions it was written for. It does not today
  exempt anything that narrows *and* begins a turn; it **will** exempt exactly that the first time a
  runtime in `app/agentruntime/` defines a function with one of those five names, which is the same
  prediction that came true for route 17 and then again for route 20.

The correction is one line and preserves the intent: put the two `MODULE::NAME` keys in `_NOT_A_TURN`
with their reasons, where `test_NO_ALLOW_LIST_ENTRY_IS_STALE` polices them, and delete the blanket
`continue`.

### 3.5 · The container `try` — **CONFIRMED**

**Falsifier:** a sink shape whose rows survive `absorb` on the R13 artifact and are lost on this one.

```python
try:
    rows_in = list(sink)
    del sink[:]
except Exception:
    rows_in, _ = [], None
```

Driven through a real recorder with no advertised pass, so nothing is reconciled away:

```
tuple sink,  1 catalogue row in            -> withheld_json() = None            <- LOST
plain list,  1 catalogue row in (CONTROL)  -> [{'scope': 'catalogue', ...}]     <- recorded
generator sink,               1 row in     -> None
list subclass forbidding __delitem__       -> None
```

The read and the clear share one `try`, so a container that resists `del` discards rows the read had
already produced. The comment says *"Read defensively, then clear the real container."* The code
throws the read away when the clear fails. **Confirmed, unchanged, and the fix remains one line** —
keep `rows_in` in the `except` and skip only the clear, so a hostile container degrades to R13's
double-record rather than to silence. **Reachability: adversarial-input only** — every live producer
passes a plain list (`bind_sink` at `stream_service:6590` / `voice_stream_service:243`, `absorb` at
`:6987` / `:6998`) — but it is a strict behavioural **regression** against the R13 artifact on inputs
the R13 artifact handled.

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | **`:7424` the clean finish binds `None`** — no `withheld*` local, so `bad_bindings` is vacuous | ✅ T3, term `1 passed`, wide baseline | **production (regression channel), 7 rounds** |
| " | a two-step `_wj_tmp = None; _withheld_json = _wj_tmp` | ✅ T6 | **production (ordinary edit)** |
| " | ~~an annotated assignment~~ | ✅ T2 **now reds** | — **CLOSED** |
| " | a walrus / a tuple target | ✅ T5, T7 (green in-tree; **red under §3.1's check**) | adversarial |
| arm-order gate · no narrowing precedes the arming | **a `_`-prefixed entry point narrowing transitively** | ✅ R21c, `6 passed`, control `2 failed` | **production, by construction (NEW)** |
| " | **a function *named* like a narrowing primitive**, anywhere under `app/` | ✅ R22 ×4, `6 passed`, control `2 failed`; **the rule suppresses a real `2 failed`** | **production, by construction (NEW)** |
| " | ~~a same-named arming helper elsewhere in `app/`~~ | ✅ R20b **now `2 failed`** | — **CLOSED** |
| " | ~~a sync `def` entry point~~ | ✅ **now `2 failed`** | — **CLOSED** |
| " | a module-scope **lambda**; a narrowing at **module scope** | ✅ both `6 passed` | adversarial |
| the gate does not red on correct code | a top-level arm inside `async with` reds as *conditional* | ✅ R18, `1 failed` | **production (false positive), 3rd round** |
| `absorb` records what the sink held | a **non-list** sink loses **every** row | ✅ tuple/generator/undeletable → `None`, control records | adversarial (regression) |
| the arming cannot raise on any input | a plain dict whose `scope` value has a hostile `__eq__` | ✅ `RuntimeError` at `arm_turn_surface` | adversarial |
| the outage reader cannot raise | `catalogue_outage_registered:462` still does a bare `e.get(...)` | ✅ `AttributeError` on `42` / `None` / `"x"` | adversarial |
| `count` is absent-or-a-count | `count: false` persists into the jsonb | ✅ re-measured | adversarial, 5 rounds |
| the outage fact does not outlive its turn | a pooled worker thread keeps `True` for the thread's life | ✅ `req_A=True, req_B=True` | adversarial/latent |
| the row and the notice cannot contradict | `narrow → drain → arm` — the arm **lowers** a true flag | ✅ rows=2, flag=`False` | latent |
| the flag survives a drain | nothing reads it after one | ✅ line map re-derived + X7 | production (inert), 3rd round |

---

## 5 · Question 5 — the ruling on the flag

**The flag is INERT for the third consecutive round, and this is a ruling, not another observation.**

**The evidence, measured this round:**

1. **The line map, re-derived at this HEAD** (not carried from R14). Three production reads —
   `stream_service.py:5642`, `:8176`, `voice_stream_service.py:422` — and eight drains —
   `stream_service.py:6970`, `:6987`, `:6998`, `:7132`, `:7424`, `:7592`, `:7633`,
   `voice_stream_service.py:684`. In all three turn shapes **the read precedes every drain**
   (arm `5003` → read `5642` → drains `6970+`; arm `7749` → read `8176` → `8181`; arm `237` →
   read `422` → drain `684`).
2. **Driven on that exact order against the real functions**, with and without the writer:
   `writer live: pre-drain read = True` · `writer NEUTERED: pre-drain read = True`. The two answers
   differ **only** at a post-drain read, and no such line exists.
3. **X7, third round: `2 failed, 115 passed` / `2 failed, 324 passed` — exact baseline.**
4. **F2 is the new fact that decides the first half.** Removing *only* `catalogue_outage.set(True)`
   at `instrument.py:440` leaves the suite at **exact baseline**, and — critically — the one test the
   flag mechanism guards (`test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER`) **still
   passes**, because `arm_turn_surface`'s derivation at `:372` recomputes the same fact from the rows
   three lines away. The writer is not merely unguarded — **it is redundant.**
5. **X7b decides the second half.** Removing the flag *entirely* (writer + derivation + the reader's
   first branch) reds **exactly one** test — `test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER`
   — which drives `record → construct recorder → arm → withheld_json() → read`, a genuine **post-drain**
   read. So the mechanism does buy a real property; it is just not one production exercises.
6. **F1 proves the mechanism cannot be repaired where it stands.** Making the derivation monotone —
   `if any(...): set(True)`, which fixes the `narrow → drain → arm` erasure I re-measured at
   `rows=2, flag=False` — reds **two** tests (`test_THE_OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN` and
   `test_AN_EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE__AT_THE_CALLER_TOO`). Leaving it lowering keeps the
   erasure. **`arm_turn_surface` cannot tell "a new turn is starting" from "this turn already
   narrowed", so no assignment it makes is correct in both orders** — measured in both directions.

**The ruling, in three parts:**

* **REMOVE the writer** — `catalogue_outage.set(True)` at `instrument.py:440`. It is provably dead
  (X7 baseline ×3) *and* provably redundant (F2: its only guard passes without it). Removing it also
  halves the leak surface. This is unconditional and costs nothing.
* **REPLACE the home of the fact — do not tune the assignment.** The `ContextVar`'s lifetime is the
  context/thread; the fact's lifetime is the turn. That mismatch *is* both live defects: the pooled
  worker keeps `True` past the turn (leak) and the next arm lowers `True` inside it (erasure), and F1
  shows one write cannot satisfy both. The fact belongs on the object whose lifetime is already
  exactly one turn — **the recorder**: `absorb` marks that it drained a catalogue row, and
  `catalogue_outage_registered()` consults the turn's recorder plus the live sink. Neither failure
  mode is constructible against that lifetime.
* **DO NOT simply delete the mechanism.** X7b reds a real property test. "Remove it, it does nothing"
  would be the wrong reading of "inert": the *writer* does nothing; the *derivation* is load-bearing
  for one genuine ordering.

**The falsifier that would overturn this ruling:** a production read of `catalogue_outage_registered()`
that follows a drain. I re-derived the full read/drain/arm map at this HEAD rather than trusting
R14's, and there is none. If CP-2 adds one, the ruling does not change — it becomes *more* urgent,
because the flag as written is already wrong for that read in both directions.

---

## 6 · The red-ability table

Baseline for every row: **the fresh scratch copies**, measured by me this session.
`term` = `test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE…` alone (**`1 passed`**);
`gate` = `TestTheTurnSinkIsArmedBeforeAnythingNarrows` (**`6 passed`**);
`instr` = `test_cp0_instrument.py` (**`2 failed, 115 passed`**);
`wide` = the 7-suite set (**`2 failed, 324 passed`**);
`doors` = `test_knowledge_client` + `test_admin_surface` (**`104 passed`**);
in-tree `test_cp0_instrument` + `test_stream_service` (**`187 passed`**).
The two scratch failures are the copy artefacts rounds 10–14 identified; **"extra" counts failures
beyond those two.** Every injection was applied to a scratch copy, **verified present by a
source-content assertion printed before the run**, and reversed by restoring a pristine snapshot —
never `git checkout`.

| # | injection | what it models | result |
|---|---|---|---|
| **T2** | `_withheld_json: str \| None = None` | **R14's headline finding** | **term `1 failed`, wide 1 extra** ✅ **CLOSED** |
| **T2b** | bare annotation + plain rebind | the same, one hop | **term `1 failed`** ✅ |
| T1 | `_withheld_json = None` | R13's G1 | term `1 failed` ✅ |
| **T3** | **`:7424` clean finish binds `None`** | **R10's I13** | **term `1 passed`, wide baseline — GREEN, 7th round** |
| **T6** | `_wj_tmp = None; _withheld_json = _wj_tmp` | an ordinary two-line extraction | **term `1 passed`, wide baseline — GREEN** |
| T11 | keep the bind, then `and None` | a contrived wipe | term `1 failed` ✅ |
| T4 | CONTROL — voice `:684` binds `None` | R10's I4 | term `1 failed` ✅ |
| **R20b** | un-arming entry point + same-named ARMING helper in `app/agentruntime/` | **R14's route 20** | **gate `2 failed`** ✅ **CLOSED** |
| **R19** | the same entry point as a **sync `def`** | **R14's route 19** | **gate `2 failed`** ✅ **CLOSED** |
| CTL | a plain un-arming async entry point in `app/services/` | the matched control | gate `2 failed` ✅ |
| **R21c** | a **`_`-prefixed** entry point narrowing **transitively** | **route 21 — NEW** | **gate `6 passed`, INVISIBLE** |
| R21c-ctl | byte-identical, non-underscore name | the matched control | **gate `2 failed`** ✅ |
| **R22** | an entry point **named** `discovery_seed_for_surface` | **route 22 — NEW** | **gate `6 passed`, INVISIBLE** |
| R22b/c/d | the same, `_budget_and_register` / `filter_intent_gated_setup_tools` / `get_admin_tool_definitions` | route 22, per name | **`6 passed`** ×3 |
| **R22-off** | **disable the `fn.name in _NARROWING_CALLS` skip on the PRISTINE tree** | is the exemption load-bearing? | **gate `2 failed`** — **yes, it suppresses a real offender** |
| U-off | disable the `_`-prefix skip on the pristine tree | what does it hide today? | **+0 discovered** — latent, not live |
| R23 | a module-scope **lambda** entry point | route 19's sibling | gate `6 passed` |
| R24 | a narrowing at **module scope**, in no function | route 19's sibling | gate `6 passed` |
| R18 | a top-level arm inside `async with AsyncExitStack()` | R13's route eighteen | **`1 failed` — FALSE POSITIVE on correct code**, 3rd round |
| **X7** | `record_catalogue_unavailable` stops setting the flag | **the flag's WRITER** | **instr + wide at BASELINE — 3rd round** |
| **F2** | the writer removed, derivation kept | is the writer *redundant*? | **BASELINE, and the flag's guard test still passes** |
| **F1** | the derivation made **monotone** (fixes the erasure) | can the flag be repaired in place? | **2 extra** — `…OUTAGE_FACT_DOES_NOT_OUTLIVE_ITS_TURN`, `…EMPTY_CATALOGUE_IS_NOT_AN_OUTAGE…` |
| **X7b** | the flag removed **entirely** | is the mechanism inert *as a whole*? | **1 extra** — `test_the_ROW_AND_THE_NOTICE_CANNOT_CONTRADICT_EACH_OTHER` |
| **PB** | **§3.1's per-bind check**, run over the pristine tree and all seven defeats | the fix I am recommending | **7/7 RED, pristine GREEN** |

**T3, T6, R21c, R22 and R22-off are the block that decides this round.** Two of them are the finding
the gate has now been rewritten twice without moving; three are holes the rewrite itself opened, one
of which is demonstrably covering a live offender.

---

## 7 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| the gate lifts `AnnAssign` | the **other bind forms** (walrus, tuple, two-step) | drove T5, T6, T7 | **NO** — T6 is an ordinary edit |
| " | the **other two writers**, which have no `withheld*` local | classified all three by AST; drove T3 | **NO** — `:7424` green, 7th round |
| " | whether the control proves the property | read the offender text T4 produces | **NO** in-tree; **YES** under §3.1's check, which names the bind |
| " | whether a per-bind check false-positives | built it and ran it on the pristine tree | **it does not** — 0 offenders, 7/7 red |
| `arming` keyed by module | whether the **other** name-keyed relation is an exemption too | found `fn.name in _NARROWING_CALLS`; drove 4 names | **NO — route 22**, and it is load-bearing |
| " | whether `reaching` is still safely over-approximating | it grants scrutiny, not exemption | **YES** — unchanged and correct |
| " | whether import-following handles relative / plain imports | read the `ImportFrom`+`app.` filter | **fails toward MORE scrutiny** ✅ deliberate |
| route 19 (`FunctionDef` added) | whether the new `_`-prefix filter undoes it | drove a matched underscore/non-underscore pair | **NO — route 21**, and the docstring above it still denies it |
| " | an entry point that is neither `def` nor `async def` | drove a module-scope lambda and module-scope code | **NO** ×2 — adversarial |
| `_NOT_A_TURN` += `effective_enabled_tools` | whether the reason is true of the code | read the signature — it *takes* `withheld_sink` | **YES** ✅ the round's clean piece |
| " | whether the **second** helper got the same discipline | diffed `_NOT_A_TURN`; found the blanket rule instead | **NO** — one entry, not two; the other bypasses the staleness test |
| `top_level_arm_lines` | whether R13's false positive was addressed | re-drove the `async with` arm | **NO** — `1 failed`, 3rd round |
| the container `try` | whether clearing can fail after the read succeeds | drove tuple / generator / undeletable subclass vs a plain-list control | **NO — every row lost**, unchanged |
| the flag | whether the **writer** is guarded yet | X7 | **NO — baseline, 3rd round** |
| " | whether the writer is even *needed* | F2 — removed it alone | **NO — it is REDUNDANT with the derivation** |
| " | whether the derivation can be made non-lossy | F1 — made it monotone | **NO — reds 2 tests; the two properties are incompatible on a ContextVar** |
| " | whether any live read follows a drain | re-derived the full map at this HEAD | **NO live consumer** — inert, 3rd round |
| `_is_catalogue_row` | the second line R13 named, `catalogue_outage_registered:462` | drove `42` / `None` / `"x"` | **NO — still `AttributeError`** |
| " | whether bounding the row's type bounds its values | drove a plain dict with a hostile `__eq__` | **NO — `arm_turn_surface` still raises** |
| `count` | `True` / `False` | drove `count=False` | **NO** — persists, 5 rounds |

---

## 8 · Where the builder's documentation of a residual is incomplete or wrong

1. **The commit's own thesis is falsified twice inside the commit.** *"An over-approximation is only
   safe in the direction of suspicion"* is correct, is well argued, and is the right fix for `arming`.
   The same diff then adds **two** new over-approximations in the direction of **exemption** — the
   `_`-prefix skip and the bare-name `_NARROWING_CALLS` skip — and one of them is demonstrably hiding
   a live offender (`R22-off`: pristine gate goes `2 failed`). A sentence that diagnoses a class of
   defect and is contradicted twelve lines below it is worse than no sentence, because it reads as
   the class having been handled.
2. **`_turn_entry_calls`'s docstring now states the opposite of what the function does.** It still
   says entry points are discovered *"including `_`-prefixed ones, because a leading underscore is a
   naming convention and not a guarantee that nothing routes to it."* Twelve lines below, `_`-prefixed
   functions are `continue`d out unless they call a primitive directly. **A guard loosened while the
   comment beside it claims it has not been** — the builder's own listed pattern, verbatim.
3. **The route-19 and route-20 fixes shipped with no test.** Both are real, both were verified only by
   my injections, and nothing in the suite would notice a revert. The round that closed two routes
   added **zero** assertions and left the suite count unchanged at `2 failed, 115 passed`. That is the
   same "fix without a red-able test" the standing rules name, applied to the round's best work.
4. **The route-22 exemption has no stated reason at any site.** `_NOT_A_TURN`'s header insists that
   *"each needs a stated reason, because 'it is not a turn' is exactly what would be said about a turn
   nobody armed"*, and `test_NO_ALLOW_LIST_ENTRY_IS_STALE` enforces it. `discovery_seed_for_surface`
   was exempted **around** that discipline, ten lines from the comment demanding it.
5. **The prompt's own account of `_NOT_A_TURN` is wrong, and the error is in the flattering
   direction.** It says the list *"grew two entries"*; it grew one. The second helper was exempted by
   a mechanism with none of the list's safeguards — so a reader of the board would believe two
   exemptions are under the staleness test when only one is.
6. **The gate's account of what it now requires remains untrue of `_emit_chat_turn`.** The
   AnnAssign fix is real, but the property is still *"one syntactic form of one local"*. `:7424` binds
   a positional argument, has no `withheld*` local, and is unmoved after two consecutive rewrites of
   this gate. §3.1 shows the honest form is forty lines and has no false positives, so the reason to
   keep deferring it has run out.
7. **Exemplary, and it should be said plainly.** Route 20 and route 19 were both closed, both
   verified by me four ways, and the route-20 fix is the *right* fix — module-keyed with real import
   edges, failing toward scrutiny on the import forms it does not model. The `effective_enabled_tools`
   exemption is the best-shaped one in this file: a true reason, a discovered entry, and a staleness
   test over it. **The problem is not the quality of the fixes; it is that this round closed three
   holes and opened two, with no test on any of them.**

---

## 9 · What would have to be true for this to PASS

* **Ship §3.1's per-bind check.** It exists, it is measured, it reds T1–T7 including `:7424` and T6,
  and it is green on the pristine tree. Seven rounds is enough.
* **Delete the `_`-prefix skip**, or make it consult `reaching` rather than `_NARROWING_CALLS` so a
  transitive narrower is still discovered — and fix the docstring either way.
* **Delete the bare-name `_NARROWING_CALLS` skip** and put `services/tool_surface.py::discovery_seed_for_surface`
  and `services/tool_surface.py::_budget_and_register` in `_NOT_A_TURN` with written reasons, where
  the staleness test can see them.
* **Give routes 19 and 20 a test each.** Both fixes are correct and both are currently unguarded.
* **`top_level_arm_lines` must accept a `With`/`AsyncWith` body at depth 1** so the gate stops
  reddening correct code — third round.
* **`absorb`'s `except` must keep `rows_in`** and skip only the clear.
* **The flag: remove the writer, move the fact to the recorder** — see §5. Do not delete the
  derivation; X7b reds a real test.
* **`catalogue_outage_registered:462` must use `_is_catalogue_row`**, and `_is_catalogue_row` must
  bound the VALUE (`type(v) is str and v == SCOPE_CATALOGUE`) — the helper exists three lines above
  and was written for this.
* **`count` needs `type(...) is int`** — five rounds.

---

## 10 · Convergence, for my scope

| round | production-reachable | adversarial-input only |
|---|---|---|
| 10 | 13 | 1 |
| 11 | 17 | 1 |
| 12 | 22 | 2 |
| 13 | 13 | 5 |
| 14 | 9 | 6 |
| **15** | **6** | **6** |

**Production-reachable, this round:** `:7424` (T3); the two-step bind (T6); route 21; route 22; the
R18 false positive; the flag's inert floor with its two negative live effects counted once.
**Adversarial:** the container `try`; the hostile `__eq__` at the arm; `catalogue_outage_registered:462`;
`count: false`; the module-scope lambda; module-scope narrowing.

**Findings introduced by the graded delta: 2 of 12, and both are production-reachable** — routes 21
and 22, both created by the fix for route 20. R14 measured 2 of 15 with one production-reachable;
R13 measured 3 introduced with 2 production-reachable. **The introduction rate has not fallen in
three rounds, and this is the first round where every introduced finding is production-reachable.**

The count is falling, and part of that is genuine: five bypasses that were green in R14 are red now
(T2, T2b, R20b, R19, and the control for the right reason under §3.1's check). But **the fall is
flattered by the scope**: the delta contained no production change in my scope, so nothing
behavioural *could* newly break. The number that matters is the other one — **three closed, two
opened, and zero tests written over any of the five** — and it says the loop is not yet contracting
on the mechanism that decides whether it terminates.

`git rev-parse HEAD` at start: `cba800fa81f4a663ae363e9f871a953745ec393b`.
`git rev-parse HEAD` before writing: `cba800fa81f4a663ae363e9f871a953745ec393b`.
`git status --porcelain`: empty at both ends.
