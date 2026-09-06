# CP-1 · round 20 · V-CODE — Verifier A (the instrument)

`git rev-parse HEAD` at start: **`b73e086caeac55e6c43332c630411ad84ac29bd4`**
`git rev-parse HEAD` before writing: **`b73e086caeac55e6c43332c630411ad84ac29bd4`** — it did not move.
`git status --porcelain -- services/chat-service`: **empty** at both ends. All four files I touched
restored byte-identical to their frozen shas (`c5eddca62d686492`, `53b55822949b2278`,
`748d460b16408bc8`, `b78641f0286f6188`). No `git checkout` anywhere.

Graded delta `35cf987ce`, diffed against `5b531e22a`. **Scope A production change: 47 lines** —
45 in `app/services/instrument.py`, 2 in `app/services/voice_stream_service.py`. `stream_service.py`,
`app/routers/` and `app/db/` are untouched. Plus 53 test lines in `tests/test_cp0_instrument.py`.

Scratch tree at `…/scratchpad/r20/root/`, built to the repo's own depth (`services/chat-service` +
`contracts/` + `sdks/` + `scripts/`) so `parents[3]` resolves and `pytest.ini`'s
`pythonpath = ../../sdks/python` finds the SDKs.

**Baselines, measured, not inherited:** `tests/test_cp0_instrument.py` = **`136 passed`**.
Full `tests/` = **`8 failed, 2257 passed, 2 skipped`** = **2267 tests**. The 8 are sibling-repo
absences (ai-gateway TS sources, `lint-foundation.yml`). The builder's "2267 tests pass" is correct.
Every delta below is against that baseline. Injections are bytes-in/bytes-out with the artifact's own
CRLF line endings, verified on disk before each run, and the restore is sha-asserted.

---

## ▶ ITEM ZERO — the termination question

*Answered first, from evidence I gathered, and addressed to the PO.*

### 1 · Is this loop converging? — **No, and this round is the strongest evidence yet that it is not.**

| measurement | series | direction |
|---|---|---|
| `introduced`, raw, rounds 9–19 | `2,1,2,1,3,2,4,3,2,2,2` | none in eleven rounds |
| `introduced`, raw, **R20 (this round, scope A)** | **5** | **the series maximum** |
| production lines in the delta | **47** — the smallest delta of the run | — |
| **executed vs argued**, cumulative over 3 rounds / 2 verifiers | **executed 9/9 correct · argued 0/10 correct** | the only stable one |

**The decisive evidence is the shape of this round, not its count.** R19-A did not merely report a
defect — it *wrote the patch*, measured it at baseline, and named the file and line. The builder
applied it essentially verbatim. That is the shortest possible path from finding to fix: no
interpretation step, no scoping judgement, nothing for the builder to get wrong. **And it still
produced a strict behavioural regression** (§3.2), an untyped crash door (§3.3), a bound with no
subject whose docstring asserts a reason that does not apply (§3.4), a production wiring that is
provably inert (§3.5), and a false claim in the source, the test docstring and RUNSTATE (§3.1).

**When the fix is handed over pre-written and the round still fails, the loop is not limited by the
quality of the findings.** It is limited by something the process does not touch.

**And I can name what.** R19-A established the recorder patch against **nine hand-picked orderings**
and reported "1 wrong of 9". I enumerated the operation space exhaustively — 30,948 sequences over
`{arm, record, construct-recorder, drain}` with a conceptual turn boundary — and the patch R19-A
certified **regresses 584 sequences**, 228 of them in the direction that tells a healthy turn its
tools are unreachable. *The verifier chain reproduced the builder's own failure mode at one remove:
a sample chosen by the party that wants it to pass.* Eleven rounds of "the builder argues, the
verifier executes" has hidden the fact that **the verifier's execution is over a sample the verifier
also chose**. That is not a convergent arrangement; it is the same error at a higher altitude.

### 2 · What would close CP-1?

**Not** "three consecutive rounds at `introduced == 0`". Twelve rounds give no reason to think that
is reachable, and it is trivially satisfiable by shrinking the delta — this round's delta was the
smallest of the run and scored the highest.

**The criterion that would actually close it removes the sampling judgement, and both halves are
cheap and were executed this round:**

* **(a) Exhaustive property enumeration replaces the hand-listed table.** For any invariant with a
  finite operation alphabet, enumerate the space and put the oracle in code. Mine ran ~31k sequences
  in about 40 seconds and found, in one pass: a **tenth ordering** the delta claims does not exist,
  a **228-case false-positive class**, and the decomposition that shows *which* class is reachable.
  A hand-picked table has now missed something in each of the last two rounds — R19-A's nine and the
  delta's three.
* **(b) The census in CI, over its reproducible half only.** I re-derived it independently: **68
  `raise` statements across the 8 `app/agentruntime/` modules** — exactly R18-B's and R19-B's count,
  a **third** independent derivation agreeing to the unit. **But 87 and 92 are not that number.**
  Both include a *structural addendum* (24 invariants carrying no `raise`) that no two verifiers have
  cut the same way. **Mechanise the 68; drop the addendum from any closure criterion**, because a
  denominator that each verifier re-cuts is the "who looked hardest" problem the PO already named.

**And the honest headline: neither of these closes CP-1**, because the largest unmeasured risk this
round is not in the source I was reading. That is question 3.

### 3 · Is more V-CODE the right axis? — **No. Stop, and run V-LIVE with one specific question.**

Three findings from this round, each executed, point the same way:

1. **The delta's only production change is provably inert.** `voice_stream_service.py:422` passes
   `_voice_advertised` to the outage read. I enumerated every use of that name in the file by AST:
   it is **constructed at :242, `bind_sink` at :243, read at :422, `withheld_json` at :684** — and
   `bind_sink` only assigns `self._sink`. **No method that can add a row to `_withheld` is called
   before the read**, and no alias exists. So `recorder.catalogue_outage()` is **provably `False` at
   the only call site in the codebase**, and the answer comes from the flag exactly as it did before
   the delta.
2. **And no V-CODE instrument can tell the difference.** Deleting the argument entirely
   (`F01`) leaves the **full 2267-test suite at baseline, +0 failures**. The only test that notices
   anything about this delta is the one unit test the delta shipped, which calls `instrument`
   directly and never touches the call site.
3. **The whole eleven-round argument may be about unreachable states, and nobody has checked.**
   `arm_turn_surface`'s own docstring rests on a premise: *"each request runs in its own task and
   therefore its own context copy, so it cannot be a previous turn's."* My decomposition shows the
   premise decides everything:

   | class | flag-only wrong | +recorder wrong | fixed | **regressed** |
   |---|---|---|---|---|
   | **SINGLE-TURN** (premise holds) | 234 | **60** | 174 | **0** |
   | **CROSS-TURN** (premise fails) | 2101 | **2297** | 47 | **243** |

   **If the premise holds, `O_J`, `O_D` and five rounds of argument were about states that cannot
   occur. If it fails, the delta makes the system worse than before it.** That single question — does
   one context ever serve two turns — is not answerable from the source. It is one probe on a running
   chat and voice turn.

**Recommendation to the PO: close V-CODE on CP-1 and run V-LIVE first, with three questions:**
(i) does any context serve two turns; (ii) is `_voice_advertised._withheld` ever non-empty at the
`:422` read; (iii) does the model ever receive `CATALOGUE_UNAVAILABLE_NOTICE` on a turn whose
catalogue was healthy. Nothing in CP-0 or CP-1 has ever been through V-LIVE, and (iii) is the
founding defect of this entire effort.

---

## 1 · Verdict — **FAIL**

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the recorder as a second witness — verify the nine orderings incl. `O_R`; is `O_J` the only survivor? look for a tenth** | **`O_K`/`O_R` GENUINELY CLOSED ✅ — and "the only survivor is `O_J`" is FALSE.** Exhaustive enumeration: within the single-turn class the recorder is a strict improvement (234→60 wrong, 174 fixed, **0 regressed**). But **60 single-turn residuals remain**, minimal witness **`O_S` = arm·recorder·record·drain·**arm**·**new recorder**·read** — truth `True`, both arrangements `False`. `O_S` has no `O_J` character and is **exactly as reachable as `O_K`**, the ordering the delta exists to fix | latent — same premise as `O_K`; **the false claim is in `instrument.py:557-559`, the test docstring and RUNSTATE** |
| 2 | **`stream_service.py:5642` / `:8176` read the outage with no recorder — real gap, and what does it cost?** | **NOT a gap in the failure direction, and the asymmetry is the opposite of what it looks like.** At both sites the recorder **does not yet exist** — `_advertised` is constructed at `:6576`, inside the downstream `_emit_chat_turn`, and the first `absorb` is at `:6987`. **No drain can precede either read**, so the flag is correct there and passing a recorder is impossible without hoisting the construction. **The cost is that the wired path is the inert one:** voice passes a recorder that is provably empty; chat, which cannot pass one, is correct anyway | none in the false-negative direction; **§3.5 is the real cost** |
| 3 | **the three weak oracles — confirm, and say which assertions they should name** | **CONFIRMED by execution, and the bypass runs.** All three (`:3236`, `:3291`, `:3370`) are byte-identical to R19's `:3183/:3238/:3317` (+53 for the delta's insert) — **untouched, fourth round**. Each *should* name **`:1704`**, whose message is unique: `"persists the column with no recorder-derived argument"`. Their `match="withheld_tools"` is also satisfied by `:1695` and `:1700`, the two NV guards | **PRODUCTION — demonstrated below** |
| 4 | **T11d — does the reassembly resolve `FormattedValue` through module constants, as `global_sql_names` does for the executor's arguments?** | **NO, and it cannot by that mechanism.** T11d **BLIND**, literal control **CAUGHT**; T11a **BLIND**. `global_sql_names` resolves *a name bound to a whole SQL string*; the column constant `_C = "withheld_tools"` is not SQL by `_names_the_column`'s own test, so it never enters that set. The delta touched neither file | **PRODUCTION — `stream_service.py:6297` is the live spelling; a one-token refactor blinds it, second round** |
| 5 | **W4 is four rounds old — write R16-A's rule or show why it cannot be written** | **IT CAN BE WRITTEN, IN ONE TOKEN, AND IT REDS NOTHING.** `s.body` → `s.body[:1]` in `_unconditional_calls`'s `Try` arm. W4, **W4b** (a raising `await`) and W7 all close; **9/9 shapes correct** vs 6/9 on the artifact; instrument suite `136 passed`; full suite at baseline `8 failed` | **W4 production-shaped, FIFTH round** |
| 6 | **the probe modules are written into the live `app/` tree — grade the risk and the fix** | **RISK CONFIRMED, and worse than recorded. FIX CONFIRMED AVAILABLE TODAY.** A leftover `_lwprobe_broken.py` reds **3 tests**, two of them the weak-oracle probes, all naming the *gate*. The fix needs **no gate change**: both gates already derive from the module constant `_TURN_SCOPE_ROOT`; redirected to a temp copy of `app/` with a probe added, the gate fired at **`:1704` on the probe** with both NVs satisfied. The six probe writers hardcode `"app"` instead of the constant that is already there | **certain** — any Ctrl-C, CI timeout or OOM; **second round** |

### The most valuable thing this round produced

**The patch a verifier wrote and certified introduces a strict behavioural regression, and the
verifier's own nine-ordering table is why it was not seen.**

`ACRD|A` — turn A arms, builds a recorder, records an outage, drains; turn B begins **in the same
context**, arms, and the caller still holds turn A's recorder:

| | truth for turn B | answer |
|---|---|---|
| **pre-delta** — flag only | `False` | **`False`** ✅ |
| **HEAD** — recorder consulted | `False` | **`True`** 🔴 |

`True` here means the model is handed `CATALOGUE_UNAVAILABLE_NOTICE` on a turn whose catalogue was
fine. That is not a new class of bug — it is **the founding defect of U-2**, which
`catalogue_outage_registered`'s own docstring, eight lines above the new code, exists to forbid:

> *"An empty catalogue and an unavailable one are different facts — a user with no permissions
> legitimately has zero tools — and conflating them is the very confusion U-2 exists to end. Three
> tests caught it by receiving an outage notice on a turn that simply had no tools."*

**And the delta's own test chose the fixture that hides it.** `_O_D` builds turn B a *fresh*
recorder (`instrument.AdvertisedToolsRecorder()`) and asserts `False`. The carried-recorder variant —
the one the new parameter makes possible for the first time — is never asserted. *A fixture chosen
for convenience answers a different question*, which is the sentence this package has now written
about the builder, about R18-B, and — this round — about R19-A.

---

## 2 · The falsifier, stated before each search

| claim | falsifier |
|---|---|
| 1 | *if any ordering outside `O_J` is answered wrong by HEAD, or if any ordering the pre-delta program answered right is answered wrong by HEAD, the claim is false* |
| 2 | *if a drain can precede either chat read, the flag is wrong there and the gap is real* |
| 3 | *if a failure that is NOT the probe being caught satisfies `match="withheld_tools"`, the oracle is not discriminating* |
| 4 | *if a module constant in the column position is caught while its literal control is caught, the reassembly resolves it* |
| 5 | *if the rule reds any correct shape, or moves the full suite off baseline, it cannot be written as specified* |
| 6 | *if a leftover probe leaves the suite green, there is no risk; if `_TURN_SCOPE_ROOT` cannot carry the gate, the fix cannot be written* |

---

## 3 · The findings

### 3.1 · The tenth ordering, and the exhaustive decomposition

Alphabet `{A arm, R record, C construct recorder, D drain}`, plus `|`, a **conceptual** turn boundary
with zero runtime effect that the truth oracle uses. Truth at the read = *did the current turn
record an outage*. Well-formedness = every turn segment begins with `A` (the arm-order gate's own
rule). Each sequence run in its own `contextvars.copy_context()`.

| class | n | flag-only wrong | +recorder wrong | fixed | **regressed** |
|---|---|---|---|---|---|
| SINGLE-TURN, reader builds own recorder | 4368 | 234 | **60** | 174 | **0** |
| SINGLE-TURN, reader holds a carried recorder | 1093 | 0 | 0 | 0 | 0 |
| CROSS-TURN, reader holds a carried recorder | 4368 | 1456 | **1669** | 15 | **228** |
| CROSS-TURN, reader builds own recorder | 3369 | 645 | 628 | 32 | 15 |

**Within a single turn the delta is a real improvement with no regression — that half of claim 1 is a
clean PASS.** Two things it does not support:

**(a) `O_J` is not the only survivor. `O_S` is, and it is single-turn.**

```
O_S = arm · construct rec1 · record · rec1.absorb(sink) · ARM AGAIN · construct rec2 · read(rec2)
      truth = True        HEAD = False        pre-delta = False
```

Executed. **60 single-turn residuals, every one a false negative**, all of the same shape: the drained
row is in a recorder nobody is holding at the read. `O_S` needs the *same* double-arm-in-one-turn
shape as `O_K` — so it is **exactly as reachable as the ordering the delta was written to fix**, and
it is not sink-borne, so the `O_J` excuse does not cover it. The false claim appears three times:
`instrument.py:557-559`, the new test's docstring, and RUNSTATE's *"the survivor (`O_J`…)"*.

**(b) The regression class.** 228 cross-turn sequences where the pre-delta program was **right** and
HEAD is **wrong**, all in the false-positive direction. Minimal witness `ACRD|A`, executed above.

### 3.2 · The new parameter is untyped, positional, defaulted and unguarded

`catalogue_outage_registered(recorder=None)` has no annotation, no type check and no `try`. Executed:

| argument | result |
|---|---|
| `[]` — **a list, i.e. the sink, the object actually in scope at `stream_service.py:6583`** | **`AttributeError: 'list' object has no attribute 'catalogue_outage'`** |
| `{}`, `"x"`, `object()`, `0` | `AttributeError` |
| a recorder whose method raises | the exception propagates |

This function is called **while assembling the system prompt**. A crash here takes the turn down from
inside the instrument that exists to report that something went wrong — the pattern this module
convicts itself for at `:571-575` (*"a malformed row in the sink took the turn down from inside the
function that exists to report that something went wrong"*), at `arm_turn_surface` (*"the
crash-inside-its-own-fix pattern, fifth occurrence"*), and in `absorb`. **Sixth occurrence, and it is
in the delta.** Every other door in this module carries `type(...) is`, `_is_exactly` or `_as_text`;
this one carries nothing.

**Reachability: latent, and pointed directly at the next step.** The R20 prompt asks whether the chat
path should pass a recorder. At `stream_service.py:5642` no recorder exists; the recorder-shaped
object nearest to hand is `_surface_sink`, a `list`.

### 3.3 · `type(v) is str` in `catalogue_outage()` has no subject, and its stated reason does not apply

The docstring: *"`type(...) is str` on the value, one read of it, **for the reason `_is_catalogue_row`
gives**."* `_is_catalogue_row`'s reason is that a hostile `__eq__` on the value runs user code. I
pushed hostile values through **every public door** into `_withheld`:

| door | resulting `type(scope)` |
|---|---|
| `absorb` a row with a `str` **subclass** scope | `str` (exact) — `_as_text` forces `str.__str__` |
| `absorb` a row with a non-`str` hostile scope | `str` (exact) |
| `absorb` a row with `scope=42` | `str` (exact) |
| `record_catalogue_withheld` / `record_withheld` / `record_pass_withheld` | `str` (exact) — module constants |
| `bind_sink` + hostile row + `absorb` | `str` (exact) |

**No public door can put a non-plain-`str` `scope` into `_withheld`.** The bound is defence with
nothing to defend against — and `E04` confirms nothing guards it. **This is `G12`'s exact shape**,
which R19-A closed one round ago as *"the property has no subject… stop carrying it"*; the delta
reintroduced it in the same commit, with a docstring that asserts a reason carried over from a place
where it was true. That is precisely R19-A's closing transferable lesson — *"a reason was generalised
past the change that made it true"* — repeated inside the commit that confesses to it.

Two asymmetries, recorded not demanded: the method applies the **value** bound but not the
**container** bound (`w.get(...)` with no `type(w) is dict`, unlike `_is_catalogue_row` which it
cites) — no public subject either; and `E05` shows the `== SCOPE_CATALOGUE` comparison is
**unguarded**, so a change making any scope count as a catalogue outage is green.

### 3.4 · The production wiring is inert **and** unguarded

Mechanised, by AST over `voice_stream_service.py` — every use of `_voice_advertised`:

```
line 242   <-- CONSTRUCTED        (before the read)
line 243   .bind_sink             (before the read)
line 422   <== THE READ
line 684   .withheld_json
line 685   .withheld_json
methods called before the read: ['<CONSTRUCTED>', 'bind_sink']
of those, methods that can add a row to _withheld: NONE
aliases that could smuggle a write in: NONE
```

`bind_sink` is `self._sink = sink`. Therefore `_withheld == []` at `:422` and
`recorder.catalogue_outage()` is **provably `False`** — the delta's production change cannot alter
any answer. And `F01` (drop the argument): **`8 failed, 2257 passed`, +0 new failures on 2267 tests.**

This is the module's own most-repeated history running backwards: the `catalogue_outage` docstring
spends forty lines on a **writer** deleted for being *"measured inert"*. The delta adds a **reader**
that is inert, and records it as a fix.

### 3.5 · The weak-oracle bypass, executed on a live site

All three probe tests do fire the intended assertion at baseline (`:1704`, verified by traceback line
number, with the probe module named in the message). The defect is that the oracle does not
*discriminate*. R19-A argued this; I executed it.

Injected R19-A's one-token refactor at the **live** site `stream_service.py:6297` — the literal
`'withheld_tools'` inside `segment_merge_sql(...)` replaced by a module constant, a change with no
behavioural effect:

```
the gate now fires at :1700 — "only 3 bind(s) of `withheld_tools` were found: [...]"
```

`:1700` is the **count NV**, and it fires *before* `:1704` is ever evaluated — so the probe is never
looked at. And then:

| test | under the refactor |
|---|---|
| `:3236 …sees_a_writer_in_ANY_module` | **PASSES** — oracle satisfied by the NV |
| `:3370 …sees_EVERY_SPELLING_OF_THE_SAME_WRITE` | **PASSES** — oracle satisfied by the NV |
| `:3306 …FAILS_CLOSED_on_a_file_it_cannot_parse` (the control, `match="could not be parsed"`) | passes **for its own reason** ✅ |

**Two probe tests report success while the thing they probe is unmeasured**, triggered by an ordinary
refactor at a production site. The correct oracle is already demonstrated 64 lines away at `:3306`.

### 3.6 · W4 — R16-A's rule, written, five rounds late

`s.body` → `s.body[:1]` in `_unconditional_calls`'s `Try` arm. *(In Python any statement can raise,
so "no statement precedes it in the chain" is exactly "it is the first statement".)*

| shape | artifact | **under the rule** | want |
|---|---|---|---|
| C1 arm at top level | clean ✅ | clean ✅ | clean |
| C2 arm inside an `if` | CONDITIONAL ✅ | CONDITIONAL ✅ | CONDITIONAL |
| W2 arm is the **first** statement of a `try:` | clean ✅ | clean ✅ | clean |
| **W4 arm in a `try:` after `x = 1/0`** | **clean** 🔴 | **CONDITIONAL** ✅ | CONDITIONAL |
| **W4b arm in a `try:` after a raising `await`** *(new)* | **clean** 🔴 | **CONDITIONAL** ✅ | CONDITIONAL |
| **W7 the same at depth 2** | **clean** 🔴 | **CONDITIONAL** ✅ | CONDITIONAL |
| W5 narrowing in the handler | CONDITIONAL ✅ | CONDITIONAL ✅ | CONDITIONAL |
| W6 narrowing after the whole `try` | clean ✅ | clean ✅ | clean |
| N1 a `with` whose body arms first | clean ✅ | clean ✅ | clean |
| | **6 / 9** | **9 / 9** | |

`tests/test_cp0_instrument.py` → `136 passed`. Full suite → `8 failed, 2257 passed` — **baseline, zero
new failures.** It closes W4, W4b and W7 together, exactly as R16-A said it would, four rounds ago.
**It is one token and it reds nothing.**

### 3.7 · The probe modules — risk, and a fix that needs no gate change

| leftover in the live `app/` tree | instrument suite |
|---|---|
| `_lwprobe_writer.py` | **`1 failed`** — names `test_EVERY_TERMINAL_WRITE_BINDS…`, i.e. blames `stream_service.py` |
| `_lwprobe_broken.py` (deliberately unparseable) | **`3 failed`** — the gate **plus both weak-oracle probes**, because `:1678` fires first and their `match="withheld_tools"` no longer matches |
| after removal | `136 passed` |

**The fix is already three-quarters built and nobody used it.** `_TURN_SCOPE_ROOT = "app"` is a module
constant at `:2151`, and **both** gates derive their sweep root from it (`:1626`, `:2289`). Executed:
copied `app/` to `apptmp/`, added a probe, set `_TURN_SCOPE_ROOT = "apptmp"` —

```
gate fires at :1704 = OFFENDER (the probe)
["services/_lwprobe_writer.py::probe_write:2 writes `withheld_tools` and NO argument …"]
```

Both NV guards satisfied (the real writers are in the copy), the probe caught. **The six probe
writers hardcode `"app"` instead of using the constant that is already there**; `test_cp1_membrane.py:204`
states the reason for doing it the other way.

---

## 4 · The bypass table

| guard | bypass | executed | reachability |
|---|---|---|---|
| `catalogue_outage_registered` + recorder | **`O_S`** — drain, re-arm, then build the turn's recorder | ✅ `False` vs truth `True` | latent — same premise as `O_K` |
| " | **carried recorder across a turn** — answers `True` on a healthy turn | ✅ regression vs pre-delta | latent; **live if one context serves two turns** |
| " | pass any non-recorder → `AttributeError` during prompt assembly | ✅ 5 argument types | latent, pointed at the next fix |
| `AdvertisedToolsRecorder.catalogue_outage` | `isinstance` for `type(v) is str` | ✅ `E04` GREEN | none — no subject |
| " | drop `== SCOPE_CATALOGUE` (any scope becomes an outage) | ✅ `E05` GREEN | latent |
| the voice wiring | delete the argument | ✅ `F01` **+0 on 2267** | **certain — it is inert already** |
| terminal-write gate `_names_the_column` | **T11d** f-string wrapping `segment_merge_sql(_C)` | ✅ BLIND, control CAUGHT | **production — the live spelling** |
| " | **T11a** f-string with the column in a constant | ✅ BLIND, control CAUGHT | production (`app/agentruntime/` is CP-2's landing zone) |
| the three weak oracles | make the **count NV** fire — a one-token refactor at a live site | ✅ two tests PASS over an unmeasured probe | **production** |
| arm-order gate `Try` rule | **W4 / W4b / W7** | ✅ clean, controls caught | **production-shaped, 5th round** |
| the whole probe apparatus | kill the process mid-test | ✅ 1 and 3 tests red, blaming the gate | **certain** |

## 5 · The red-ability table — **my denominator is 12**

**Derivation.** The 12 defeatable decision points the delta itself introduced, across its 47
production lines and its one new test. I do not use a whole-file denominator: that grades rounds 1–19
again. (For context: R19-A used 20 over 74 lines; R19-B's mechanical census is 92 over B's scope.)

| # | defeat | instrument suite | attributed to |
|---|---|---|---|
| E01 | delete the recorder consultation entirely | **RED** | `test_THE_RECORDER_IS_THE_SECOND_WITNESS…` ✅ |
| E02 | `catalogue_outage()` always `False` | **RED** | same ✅ |
| E03 | `catalogue_outage()` always `True` | **RED** | same ✅ |
| E04 | `type(v) is str` → `isinstance(v, str)` | GREEN | — |
| E05 | drop `v == SCOPE_CATALOGUE` | GREEN | — |
| E06 | read the wrong key (`scope` → `stage`) | **RED** | same ✅ |
| E07 | witness `self._sink` instead of the retained rows | **RED** | same ✅ |
| E08 | consult the recorder after the flag instead of before | GREEN | — |
| E09 | **the voice call site drops its recorder** | GREEN | — |
| E10 | the new test loses its `O_K` assertion | GREEN | — |
| E11 | the new test loses its `O_R` assertion | GREEN | — |
| E12 | the new test loses its `O_D` assertion | GREEN | — |

**5 / 12 = 42%.** Partitioned by what the delta claims:

| | red-ability |
|---|---|
| the mechanism inside `instrument.py` (E01–E08) | **5 / 8** |
| **the production wiring** (E09) | **0 / 1** — and `F01` confirms it on all 2267 |
| **the new test's own integrity** (E10–E12) | **0 / 3** |

**Every RED is attributed to the same single test.** The delta's entire guard surface is one test
function, which exercises `instrument` directly and never the call site — the same shape R19-A
measured on the `narrows` unification (0/7), one round later.

## 6 · The sibling table

| the delta fixed | the sibling it did not | executed | status |
|---|---|---|---|
| `O_K` / `O_R` via a retained-row witness | **`O_S`** — the same double-arm shape with a fresh recorder after the re-arm; 60 single-turn residuals | ✅ | 🔴 **NEW** |
| the false **negative** | the false **positive** it creates — a carried recorder, 228 sequences | ✅ | 🔴 **NEW** |
| a value bound on `scope` | the container bound (`w.get` with no `type(w) is dict`) the cited helper leads with | ✅ neither has a subject | 🔴 **NEW** |
| a new `recorder=` door | every other door in the module carries a type bound; this one carries none | ✅ 5 argument types crash | 🔴 **NEW** |
| the **voice** read | the two **chat** reads (`:5642`, `:8176`) — and the wired one is the inert one | ✅ AST + `F01` | 🔴 **NEW** |
| `_O_D` asserts the fresh-recorder case | the carried-recorder case the new parameter first makes possible | ✅ | 🔴 **NEW** |
| `catalogue_outage`'s comment extended (`:545-563`) | `:531` (*"Ask the turn's RECORDER first"*) vs `:542` (*"Read from the FLAG first"*) — still contradictory, now with a third instruction between them | read | 🔴 carried, **6th round** |
| — | **W4 / W7** — one token, reds nothing | ✅ 9/9 | 🔴 carried, **5th / 4th round** |
| — | the three weak oracles (`:3236`, `:3291`, `:3370`) | ✅ bypass runs | 🔴 carried, **4th round** |
| — | **T11d** — the live SQL spelling | ✅ BLIND, control CAUGHT | 🔴 carried, 2nd round |
| — | probe modules in the live `app/` tree; `_TURN_SCOPE_ROOT` already exists | ✅ risk + fix both | 🔴 carried, 2nd round |

## 7 · The guard table — *is there a test? can it red? does it red for the reason it names?*

| fix in the delta | is there a test? | can it red? | for the reason it names? |
|---|---|---|---|
| the recorder consultation | **yes** — one | **yes** (E01) | **yes** ✅ |
| `catalogue_outage()`'s row source | yes — the same one | **yes** (E07) | **yes** ✅ |
| `catalogue_outage()`'s key | yes — the same one | **yes** (E06) | **yes** ✅ |
| `catalogue_outage()`'s **value bound** | **NO** | — | E04 GREEN — **and it has no subject** |
| `catalogue_outage()`'s **scope predicate** | **NO** | — | E05 GREEN |
| **the voice call site** | **NO** | — | E09 / `F01` GREEN on 2267 |
| the false-positive direction (`_O_D`) | yes, but for the **fresh-recorder** case only | n/a | **no** — the carried case is unasserted and is wrong |
| the new test's three assertions | — | — | E10/E11/E12 GREEN — nothing outside it notices a weakening |

## 8 · Reachability verdict on every finding

| finding | reachability | basis |
|---|---|---|
| **A20-1** `O_S` — the tenth ordering, 60 single-turn residuals | **latent, = `O_K`'s** | needs a second arm in one turn; identical premise to the ordering the delta fixes |
| **A20-2** carried-recorder **false positive**, 228 sequences | **latent; LIVE if one context serves two turns** | executed regression vs pre-delta; premise unverified — **the V-LIVE question** |
| **A20-3** untyped `recorder=` → `AttributeError` in prompt assembly | **latent, pointed at the next fix** | 5 argument types; the chat sites have a `list` in scope and no recorder |
| **A20-4** the value bound has no subject + a false stated reason | **none** (no subject) — but the *record* is wrong | 7 public doors, all coerce to exact `str` |
| **A20-5** the production wiring is inert **and** unguarded | **certain** — it is the state of the tree | AST enumeration + `F01` +0 on 2267 |
| **A20-6** *"the only survivor is `O_J`"* — false in source, test docstring and RUNSTATE | **certain** | `O_S` executed |
| A19-2 the weak oracles (carried) | **PRODUCTION** | a one-token refactor at `stream_service.py:6297` makes two probe tests green over nothing |
| A19-1 T11d / T11a (carried) | **PRODUCTION** | the live spelling; one token keeps it visible |
| A19-4 W4 / W4b / W7 (carried) | **production-shaped**, 5th round | any `try` whose first statement can raise; **the fix is one token and reds nothing** |
| A19-6 probe modules in the live tree (carried) | **certain** | reproduced; 3 tests red on one leftover |
| the `:531` vs `:542` contradiction (carried) | n/a — record | 6th round, now with a third instruction between them |

## 9 · Executed vs argued

| # | load-bearing claim in the delta, scope A | established by | correct? |
|---|---|---|---|
| C1 | *"consulting the recorder's retained rows answers **8 of 9**"* | **PART-EXECUTED** — the test runs 3 of the 9 | **TRUE of the nine, and the nine are not the population** 🔶 |
| C2 | *"**The only survivor is `O_J`** … genuinely sink-borne"* | **ARGUED** | **FALSE** — `O_S`, 60 single-turn residuals 🔴 |
| C3 | *"The recorder is passed rather than held in a ContextVar … a caller that has one already knows which turn it is for"* | **ARGUED** | **FALSE as a safety claim** — nothing enforces it; violating it yields the U-2 founding defect 🔴 |
| C4 | *"`voice_stream_response` constructs it at `:242` and reads here at `:422`, same function"* | **EXECUTED** (a code fact) | **TRUE** ✅ — but the implication is false: the recorder is empty there |
| C5 | *"`type(...) is str` on the value … **for the reason `_is_catalogue_row` gives**"* | **ARGUED** | **FALSE** — no public door provides a subject 🔴 |
| C6 | *"2267 tests pass"* | **EXECUTED** | **TRUE** ✅ |

**Ratio 2 : 4. Executed correct 2 / 2. Argued correct 0 / 4.**

| | executed | argued |
|---|---|---|
| R18 (A + B) | 1 / 1 | 0 / 1 |
| R19 (A + B) | 7 / 7 | 0 / 6 |
| **R20-A** | **2 / 2** | **0 / 4** |
| **cumulative** | **10 / 10** | **0 / 11** |

**Three rounds, three verifiers, n = 21, polarity unbroken.** This is now strong enough to be a
merge gate: *a load-bearing sentence in a commit message or a source comment with no execution behind
it has been wrong 11 times out of 11.* It would have caught C2, C3 and C5 before either verifier was
deployed — and this round C2 and C3 are the two that regressed the program.

**The caveat I owe the PO, because it is the finding of §item-zero:** "executed" is not a guarantee
either. R19-A's refutation was executed — over nine orderings the verifier chose. It certified a
patch that regresses 228 sequences. **Execution over a hand-picked sample is argument wearing a lab
coat.** The gate should be *executed over an enumerated space*, not merely executed.

## 10 · Convergence

**Raw.** Six load-bearing claims in scope A. **Closed: 2** (C4, C6). **Refuted: 3** (C2, C3, C5).
**True-of-sample: 1** (C1).

**Findings introduced by this delta: 5** — A20-1 (`O_S` / the false residual claim is A20-6, counted
with it), A20-2 (the false-positive regression), A20-3 (the untyped door), A20-4 (the no-subject bound
with a false reason), A20-5 (inert + unguarded production wiring). Four are code, one is record.

**Findings closed by this delta: 1** — `O_K` and `O_R`, genuinely, within the single-turn class
(174 sequences fixed, 0 regressed). That is a real result and I do not want it lost in the FAIL.

**The series, raw:** `2,1,2,1,3,2,4,3,2,2,2,` **`5`** — twelve rounds, no direction, and the maximum
is this round, on the **smallest delta of the run** (47 production lines). Normalising by changed
lines would report ~10.6/100 against R19-A's 4.05 — a 2.6× "deterioration" driven entirely by the
denominator, which is exactly why R19-A recommended steering by the raw count. I agree, and I would
now go further: **`introduced` is not a convergence signal at all.** It has no direction in twelve
rounds, it does not track delta size, and it does not track whether the fix was handed to the builder
pre-written. The two numbers that *do* carry signal are §9's polarity and the enumerated-space
coverage in §3.1.

**Carried into whatever comes next, in priority order:**

1. **Answer the V-LIVE question before writing any more code here** (item zero §3). Whether one
   context ever serves two turns decides whether §3.1's regression is live and whether five rounds of
   ordering argument were about reachable states.
2. **Either wire the recorder somewhere it is not empty, or revert it.** As shipped it cannot change
   an answer at its only call site, and deleting it costs nothing on 2267 tests.
3. **Bound the new door** — `AttributeError` from inside prompt assembly, sixth occurrence of the
   crash-inside-its-own-fix pattern.
4. **Write W4's rule.** `s.body` → `s.body[:1]`. One token, 9/9, full suite at baseline. **Fifth round.**
5. **Fix the three weak oracles** to `match="persists the column with no recorder-derived argument"`.
   Fourth round, and the bypass is a production refactor.
6. **Point the probe writers at `_TURN_SCOPE_ROOT`** — the constant is already there and both gates
   already read it.
7. **Resolve the SQL matcher above the literal** (T11d), and **delete the `type(v) is str` bound or
   its stated reason** — one of the two is false.

---

`git rev-parse HEAD` at finish: **`b73e086caeac55e6c43332c630411ad84ac29bd4`** — unmoved.
`git status --porcelain -- services/chat-service`: **empty**. No tracked file was modified except this
verdict. No `git checkout` was used.
