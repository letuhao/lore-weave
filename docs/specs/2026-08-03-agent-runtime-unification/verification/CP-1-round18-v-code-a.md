# CP-1 · round 18 · V-CODE — Verifier A (the instrument)

`git rev-parse HEAD` at start: **`2faa88bacd48340d6ba0ce87dcc8dd471f73c88d`**
`git rev-parse HEAD` before writing: **`2faa88bacd48340d6ba0ce87dcc8dd471f73c88d`** — it did not move.
`git status --porcelain -- services/chat-service`: **empty** at both ends.

Graded delta: `8a84f78e1` + `9453c9f86`, diffed against `6761cf013`. Scope A:
`app/services/instrument.py`, `stream_service.py`, `voice_stream_service.py`, `app/routers/`,
`app/db/`, and the gate machinery in `tests/test_cp0_instrument.py`. **404 changed lines in scope**
(`56+49` instrument, `233+66` tests; `stream_service.py`, `voice_stream_service.py`, `app/routers/`
and `app/db/` are **untouched** by this delta).

Everything below was **executed**, in a scratch tree at `…/scratchpad/r18/root/services/chat-service`
built to the repository's own depth — my first tree was one level short, `parents[3]` missed
`contracts/`, and two tests failed for that reason alone. I rebuilt it before trusting any number.
**Scratch baseline: `tests/test_cp0_instrument.py` `134 passed`; full `tests/` `19 failed, 2239
passed, 2 skipped` = 2260 tests.** The 19 are pre-existing (sibling repositories absent from the
scratch tree) and **every delta below is reported against that baseline, not against zero.** Every
injection prints an on-disk verification before its suite runs, and every restore is asserted
byte-identical by sha256.

---

## 1 · Verdict — **FAIL**

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **"the restored writer + the derivation satisfies every ordering except one, and that one rides the sink so no arrangement of this variable addresses it"** | **REFUTED, three ways.** A **seventh ordering** `O_K` (`arm → record → drain → arm → read`, one turn) answers **`False`** where truth is `True`, and its carrier is the **flag**, not the sink. Worse: `O_K` is **byte-identically the same execution** as the two-turn row the delta *asserts must answer `False`* — so the two requirements are **logically contradictory**, and the impossibility argument this delta deleted as "vacuous" **is true again, because restoring the writer made it true** | **latent today** (needs two arms in one context); **the contradiction is permanent and the delta's own test encodes the wrong answer for it** |
| 2 | **T9 closed by resolving SQL through module + cross-module constants; parse fail-closed** | **PASS on the nine T9 defeats — T10 FOUND, eight ways.** Controls red ✅ (function-local literal, module constant, a writer under `db/`). Blind to: string **concatenation**, **`.format()`**, **`%`**, **`" ".join`**, **extra whitespace**, an **aliased** cross-module import, a **`getattr` executor**, and **`copy_records_to_table`**. **Five of the eight were CAUGHT before this delta** and were blinded by item 5's own qualification — measured with per-probe attribution | **production — `app/agentruntime/` is CP-2's landing zone; `T10a` is `"…SET " + "withheld_tools" + " = $1"`** |
| 3 | **route 24 closed by refusing a delegate whose own arguments narrow** | **PASS on route 24 — ROUTE 25 FOUND, five variants.** `G-R24` reds ✅ and the args-filter is exact. But the `<=` line-number rule survives untouched beside it: a narrowing in a **ternary test**, a **boolean op**, a **list sibling**, a **subscript**, or after a **semicolon** on the delegate's line is still EXEMPTED. Control: disabling the exemption turns all five CAUGHT. **The fix moved the boundary again — for the third consecutive round** | **production, by construction** |
| 4 | **the `Try` rule: is it right, does it still red W4, does it accept route 18's shape?** | **The rule is RIGHT and it fixed the wrong subset.** It closes **W5** ✅ and **W10** ✅ and still accepts W2/W6/W11 ✅. But **W4 is still GREEN** — R16-A wrote *"still rejects W4"*, R17-A reported it, this delta names it in a comment and does not fix it — and **W7 (depth 2) is still GREEN** under a comment that says *"depth 1 … and no further"*. And it introduces **W5b**: the rule tests only `_NARROWING_CALLS`, while its sibling filter **eight lines above, in the same commit**, tests `_NARROWING_CALLS or reaching` | **W4 production-shaped; W5b adversarial-to-ordinary** |
| 5 | **`db/migrate.py` reddened; the SQL match was qualified to writes. Too narrow?** | **YES — measured.** The DDL story is true (`migrate.py::run_migrations:799` reds the pre-delta matcher ✅, and it is `ALTER TABLE … ADD COLUMN withheld_tools`). But the qualification **blinded the gate to five ordinary spellings of a real row write it saw before**: `T10a/b/c/h/j`. `"UPDATE  chat_messages SET withheld_tools  =  $1"` — **two spaces defeats both qualifiers** | **production — a two-space diff is invisible in review** |
| 6 | **convergence, raw and per changed line; steer by raw count?** | **Closure 13 of 24 = 54%.** **Introduced 3** over **404** changed lines = **0.74/100** — the **lowest normalised rate of the series**. I **agree** with steering by raw count and would add a second axis — §9 | §9 |

### The most valuable thing this round produced

**The argument the builder deleted as vacuous is true, and deleting it is what made it true.**

R17-A proved *"monotone and lowering are the same program"* — correct, because the writer was gone.
This delta restored the writer. The moment it did, monotone and lowering became **different programs
again**, and the incompatibility the old comment asserted came back with them. Measured:

| | `O_K` / two-turn row (`arm, record, drain, arm, read`) | instrument suite |
|---|---|---|
| **HEAD** (writer + lowering arm) | **`False`** | `134 passed` |
| **A-MONO** (writer + monotone arm) | **`True`** | **`5 failed`** |
| **A-NOWRITER** (R17 HEAD) | `False` | `1 failed` |

`O_K` needs `True`. The delta's own `test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN` **asserts `False`** for
that identical execution (as "turn B"). **No assignment of `catalogue_outage` can answer one `True`
and the other `False`, because there is nothing in this module that can tell them apart** — which is
precisely the sentence that was deleted. The delta did not resolve the ambiguity; it **removed the
description of it** while restoring the code that reinstates it.

And `instrument.py:425–431` — **untouched by this delta** — says so in the file:

> *"it therefore also **LOWERS a true flag when an arm follows a drain within one turn**. A verifier
> proved the two properties incompatible on a `ContextVar` (monotone reds two tests, lowering keeps
> the erasure)"*

That comment sits **77 lines below** the new `#:` block claiming the only residual rides the sink.
**For the second consecutive round the counter-example to the builder's headline claim is a sentence
the builder wrote and did not re-read.** R17's was one the builder had deleted; R18's is one the
builder left in.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every row **executed**: revert the fix → verify on disk → run `tests/test_cp0_instrument.py` → restore
byte-identically (sha256 asserted).

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| SQL resolved through module + cross-module constants (`:1631–1637`) | **yes** — `test_the_TERMINAL_GATE_sees_SQL_HOISTED_TO_A_MODULE_CONSTANT` | **yes** — `G-T9e` **`1 failed`**, and it is *that* test | **yes** ✅ — **and for a bare-name executor too**, both probes in one test |
| `except SyntaxError` → fail-**closed** (`:1623–1628`) | **yes** — `test_the_TERMINAL_GATE_FAILS_CLOSED_on_a_file_it_cannot_parse` | **yes** — `G-T9g` **`1 failed`**, and it is *that* test | **yes** ✅ |
| the write **qualification** on `_names_the_column` (`:1523–1533`) | the gate **is** the test | **yes** — `G-QUAL` **`1 failed`** on `db/migrate.py::run_migrations:799` | **yes for the DDL it was written for. NO for its blast radius** — no test asserts a *qualifying* write is still seen, and five spellings stopped being seen (§3.5) |
| the delegate-**arguments** filter (`:2414–2421`) | **yes** — `test_a_NARROWING_IN_THE_DELEGATES_ARGUMENTS_precedes_it` | **yes** — `G-R24` **`1 failed`**, and it is *that* test | **yes for a narrowing INSIDE the args. NO for one BESIDE the delegate on the same line** — route 25, five variants |
| the `Try`-handler rule (`:2247–2262`) | **yes** — `test_an_ARM_IN_A_TRY_WHOSE_HANDLER_NARROWS_is_not_COVERED` | **yes** — `G-TRY` **`1 failed`**, and it is *that* test | **yes for W5 and W10. NO for W5b** (handler narrows via a helper), **and it does not touch W4 or W7** |
| the restored writer, `record_catalogue_unavailable` (`:516`) | **yes** — `test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN…` | **yes** — `G-WRITER` **`1 failed`**, and it is *that* test | **yes for the drain rows** ✅. **NO for `O_K`** — the same test asserts the **wrong** answer for the arm-after-drain state (§3.1) |
| the derivation at the arm (`:432`) | **yes** — same test + three more | **yes** — `G-DERIV` **`5 failed`** | **yes** ✅ — and it is the number that falsifies *"monotone reds two tests"*: with the writer back it is **5**, not 2; without it, R17-A measured **0** |
| `instrument.py:425–431` — *"monotone reds two tests"*, *"the least wrong of the four arrangements"*, *"see `catalogue_outage_registered` for who owns the real fix"* | — | — | — **four false or stale statements, 4th round.** The delta rewrote `:307–348` and `:531–545` and left this block, which now **contradicts both** |
| `catalogue_outage_registered`'s own body (`:531–545`) | — | — | — *"Ask the turn's **RECORDER** first"* (`:531`) sits **eleven lines above** *"Read from the **FLAG** first"* (`:542`) in the same function. The recorder is not consulted at all |
| `_source` bound once (`:234`) | **NO** | — | — **`G01` SILENT on all 2260 tests. FOURTH round.** R16-A and R17-A both asked for it by name |
| `withheld_json`'s walrus (`:969`) | **NO** | — | — **`G12` SILENT on all 2260 tests. FOURTH round.** Same |

**7 of 7 fixes in this delta have a red-able test that reds for the reason it names.** That is the
best guard record in my scope in the series, and it should be the first line of the next brief.

---

## 3 · The falsifier, per claim — stated before the search

### 3.1 · Claim 1 — **REFUTED. The seventh ordering exists, and it is unfixable in a way the delta just stopped saying**

**Falsifier stated first:** *if there is an ordering other than "a turn that records and never arms"
in which `catalogue_outage_registered()` contradicts the turn's truth, and its carrier is the flag
rather than the sink (i.e. some arrangement of `catalogue_outage` changes the answer), claim 1 is
false.*

Executed, one `contextvars.copy_context()` per ordering, on the frozen tree, with the arrangement
verified by `inspect.getsource` before the first measurement (`WRITER PRESENT: True`,
`ARM DERIVES: True`):

| ordering | HEAD | A-MONO | A-NOWRITER (R17) | truth | |
|---|---|---|---|---|---|
| O_A arm → record → read | `True` | `True` | `True` | `True` | ✅ |
| O_B arm → record → **drain** → read | **`True`** | `True` | `False` | `True` | ✅ **the delta's win** |
| O_C record → recorder → arm → drain → read | `True` | `True` | `True` | `True` | ✅ |
| O_E two recorders in one turn | **`True`** | `True` | `False` | `True` | ✅ **the delta's win** |
| O_D turn A drains → **turn B arms** → read | `(T,**F**)` | `(T,**T**)` | `(F,F)` | `(T,F)` | ✅ |
| **O_K arm → record → drain → ARM AGAIN → read** | **`False`** | **`True`** | `False` | **`True`** | 🔴 **the seventh** |
| **O_J turn A arm/record/drain → turn B READS, no arm** | **`True`** | `True` | **`False`** | `False` | 🔴 **introduced** |
| O_L / O_M variants of O_K with a later `DECLARATION` row | `False` | `True` | `False` | `True` | 🔴 |
| O_N arm → drain(empty) → record → read | `True` | `True` | `True` | `True` | ✅ |
| O_P record → arm → read | `True` | `True` | `True` | `True` | ✅ |

**Three separate refutations of the one sentence:**

**(a) `O_K` is a seventh ordering and it is not sink-borne.** Step-by-step state, snapshotted per step
(my first trace stored list *references* and printed the final mutation for every row — I caught it,
fixed it, and re-ran; the numbers below are from the corrected probe):

```
O_K / O_D-second   [arm, record, drain, arm]      answer=False
   after arm     sink=[]                                           flag=False
   after record  sink=[{'scope':'catalogue',...}]                  flag=True
   after drain   sink=[]                                           flag=True     <-- the flag alone holds it
   after arm     sink=[]                                           flag=False    <-- the ARM destroys it
```

The sink is `[]`. The row is gone. The flag held the truth and **the derivation lowered it**. Nothing
about this rides the sink.

**(b) `O_K` and the delta's own asserted row are the SAME EXECUTION.** The delta's
`_two_turns` runs `arm(); record(); drain(); arm(); read()` and asserts the read is `False`, calling
that "the derivation is what buys this". `O_K` is that identical statement sequence, and it needs
`True`. **`arm_turn_surface` cannot distinguish "a new turn is starting" from "this turn already
narrowed", because a re-used context and a re-armed sink are the same program state** — the deleted
sentence, verbatim, and now demonstrable rather than argued: `A-MONO` answers **both** `True`,
`HEAD` answers **both** `False`, and no third assignment can split them. **The design space is not
empty for the reason the builder gave; it is non-empty in exactly the way the builder had written
down and then removed.**

**(c) the residual's stated precondition is the wrong one, so the gate does not forbid it.** The
delta says the residual is *"a turn that records and never calls `arm_turn_surface()`"* and that
*"the arm-order gate statically forbids the shape that produces it"*. Measured:

| shape | answer | does the arm-order gate forbid it? |
|---|---|---|
| turn A records, **never arms** → turn B arms | `(True, True)` leak | yes |
| turn A **arms**, records, **never drained** → turn B arms | **`(True, True)` leak** | **NO** — turn A arms exactly once, unconditionally, before narrowing |
| turn A arms, records, **drains** → turn B arms | `(True, False)` ✅ | — |

The precondition is **"the sink was never drained"**, not "the turn never armed". An entry point that
satisfies the arm-order gate *perfectly* and whose turn ends before `withheld_json()` runs — an early
return, an exception, a client disconnect — leaks identically. **The second mechanism the delta hands
this hole to does not own it.**

**And `O_J` is the cost the delta did not book.** R17-A named it in advance as R1's "honest cost"; it
is now in the tree. Turn B reads with an **empty** sink and gets `True`. Carrier: the flag.
`A-NOWRITER` answers `False`. **So "no arrangement of this variable addresses it" is false for `O_J`
as well** — an arrangement of this variable addressed it right up until this delta, at the price of
`O_B` and `O_E`. That is a **trade-off**, which is what the claim denies.

**Reachability.**
* `O_K`: **latent.** It needs two `arm_turn_surface()` calls in one context with a drain between. I
  mapped the tree: three arm sites (`stream_service:5003`, `:7749`, `voice_stream_service:237`), each
  in a distinct entry point reached from a distinct route (`messages.py:521`, `:596`, `voice.py:83`),
  so each gets its own task context today. It becomes reachable the moment one entry point calls
  another — which is the shape the delegation exemption exists to describe.
* `O_J`: **latent.** All three production readers arm first (`5003 < 5642`, `7749 < 8176`,
  `237 < 422`).
* The **sink-borne leak with a turn that armed correctly**: **production.** Any turn that narrows and
  does not reach `withheld_json()` leaves the row for the next turn in a pooled context.
* The **contradiction**: **permanent, and asserted wrong today.**

**One more thing worth saying plainly, because the delta is right about it and I re-measured it.**
Every production read still precedes every drain — I re-derived the map at this HEAD
(`withheld_json()` is itself the drain, at `instrument.py:939`, and every call site is at
`stream_service:6970+` / `voice:684`, all *after* the three reads). So the restored writer is **still
inert in production**, exactly as three earlier rounds measured. The difference — and it is the whole
point — is that it is now **guarded by a test that reds when it is removed**, so the next round
cannot delete it on a measurement of a tree that has it.

### 3.2 · Claim 2 — **T9 is closed; T10 is eight defeats, five of them freshly opened by item 5**

**Falsifier stated first:** *if a terminal writer can bind a literal `None` and the gate stays
`1 passed`, T10 exists.*

Controls first, and they matter here because a single un-attributed `1 failed` from `db/migrate.py`
made my first pre-delta run read as if every probe were caught. I re-ran with per-probe attribution
(does the offender list name **my** probe file?).

| # | injection (real module written under `app/`, removed in `finally`) | ordinary? | on **HEAD** | on the **pre-delta matcher** |
|---|---|---|---|---|
| CTL | function-local SQL literal | — | **`1 failed`** ✅ | caught ✅ |
| CTL2 | SQL hoisted to a **module constant** (the delta's own T9e) | — | **`1 failed`** ✅ | caught ✅ |
| CTL3 | the write lives under **`app/db/`** | — | **`1 failed`** ✅ | caught ✅ |
| **T10a** | `"UPDATE chat_messages SET " + "withheld_tools" + " = $1"` — **concatenation** | **the prompt named it** | **`1 passed`** ❌ | **caught** — 🔴 **INTRODUCED** |
| **T10b** | `"…SET {} = $1".format("withheld_tools")` | the prompt named it | **`1 passed`** ❌ | **caught** — 🔴 **INTRODUCED** |
| **T10c** | `"…SET %s = $1" % ("withheld_tools",)` | the prompt named it | **`1 passed`** ❌ | **caught** — 🔴 **INTRODUCED** |
| **T10h** | `" ".join(["UPDATE chat_messages SET", "withheld_tools", "= $1 …"])` | ordinary | **`1 passed`** ❌ | **caught** — 🔴 **INTRODUCED** |
| **T10j** | `"UPDATE  chat_messages SET withheld_tools  =  $1"` — **two spaces** | **a typo is ordinary** | **`1 passed`** ❌ | **caught** — 🔴 **INTRODUCED** |
| **T10d** | the module constant imported **under an alias** (`from … import WRITE_SQL as _W`) | the prompt named it | **`1 passed`** ❌ | blind ❌ | 
| **T10e** | `getattr(conn, "execute")(SQL, None, m)` | the prompt named it | **`1 passed`** ❌ | blind ❌ |
| **T10f** | `conn.copy_records_to_table("chat_messages", columns=[…, "withheld_tools"])` | **a real asyncpg bulk write** | **`1 passed`** ❌ | blind ❌ |
| **T10g** | `f"UPDATE chat_messages SET {_col} = $1"`, `_col = "withheld_tools"` | ordinary | **`1 passed`** ❌ | blind ❌ |

**The shape of T10.** T9's fix moved the anchor from *"a literal inside this function"* to *"a literal
anywhere in `app/`, plus names bound to one"*. What did **not** move is that the anchor is still **a
single `ast.Constant` that must satisfy the whole predicate by itself**. Every T10 defeat is one
statement whose column name and whose table/`=` qualifier live in **two different constant nodes**.
T8 was *file set*; T9 was *statement kind and SQL source*; **T10 is "the predicate is evaluated per
node and the SQL is per expression."** The gate's own `global_sql_names` mechanism proves the author
knows how to resolve across nodes — it just resolves across *bindings*, not across *operators*.

**Reachability: production.** `app/agentruntime/` is where CP-2's runtime lands, and `T10a` is what
happens the first time somebody wraps a long SQL string at 100 columns.

### 3.3 · Claim 3 — **route 24 closed; ROUTE 25 is the `<=` rule that route 24's fix left standing**

**Falsifier stated first:** *if a narrowing can run before the delegate and the entry point still be
exempted, route 25 exists.*

Every probe is a real module under `app/services/`, swept by the real `_turn_entry_calls()`, removed
in a `finally`. An exempted entry point is **absent from the sweep's output** (the exemption `continue`s
before the entry is built), so I proved the mechanism rather than assuming it: **disabling the
exemption turns every one of the five CAUGHT.**

| probe | on HEAD | exemption disabled (control) |
|---|---|---|
| CTL un-armed entry point that narrows | `arms=[]` ✅ caught | caught ✅ |
| CTL2 arm then narrow | clean ✅ | clean ✅ |
| **R24a** `return stream_response(await c.get_tool_definitions())` | **caught** ✅ **CLOSED** | caught |
| R25e narrowing in the args **via a helper** (`reaching`) | caught ✅ | caught |
| R25f the delegate wrapped in `await` | caught ✅ | caught |
| **R25a** `return stream_response(c) if await c.get_tool_definitions() else None` | **EXEMPTED** ❌ | **caught** |
| **R25b** `await c.get_tool_definitions(); return stream_response(c)` — **semicolon** | **EXEMPTED** ❌ | **caught** |
| **R25c** `return await c.get_tool_definitions() or stream_response(c)` | **EXEMPTED** ❌ | **caught** |
| **R25d** `return [await c.get_tool_definitions(), stream_response(c)]` | **EXEMPTED** ❌ | **caught** |
| **R25g** `return stream_response(c)[await c.get_tool_definitions()]` | **EXEMPTED** ❌ | **caught** |

**Did the fix remove a class, or move the boundary again? It moved it — for the third consecutive
round, and this time the movement is one word wide.** Route 23 was *"the delegate need not run"*.
Route 24 was *"the narrowing is inside the delegate's arguments"*. Route 25 is *"the narrowing is
anywhere else on the delegate's line"*. The fix enumerated **one** of the ways a narrowing can share
a line with a delegate and evaluate first; there are at least five others, and they are all the same
sentence — **the comparison unit is a line number and the property is evaluation order.** R17-A said
this in those words and proposed the general fix (*"exclude narrowings that are descendants of the
delegating call's args/keywords, **or require the delegate's whole statement to contain no
narrowing**"*). The delta implemented the first disjunct. **The second one closes all five.**

**Reachability: production, by construction.** `R25b` is two existing statements with the newline
removed; `R25c` is an idiom.

### 3.4 · Claim 4 — **the `Try` rule graded: right in principle, fixed one of the three shapes it was for, and opened a fourth**

**Falsifier stated first:** *if a shape R16-A or R17-A named as wrongly-green is still green, the rule
did not do the job it was written for; if a shape that was green before this delta is red now and is
correct code, it overshot.*

Same probe harness, plus a control that drops `Try` from the carriers entirely so I can attribute
each result to the rule rather than to something else.

| probe | on **HEAD** | `Try` dropped (control) | should be | |
|---|---|---|---|---|
| W2 arm is the first statement of a `try:` | **clean** | caught | clean | ✅ the carrier earns its place |
| W6 narrowing after the whole `try/except` | **clean** | caught | clean | ✅ |
| W11 narrowing in the `else:` clause | **clean** | caught | clean | ✅ correct — `else` runs only if the body completed |
| **W5** arm last in `try:`, narrowing in the **`except`** | **caught** | caught | caught | ✅ **the fix, and it is the right one** |
| **W10** arm in `try:`, narrowing in the **`finally`** | **caught** | caught | caught | ✅ **a shape nobody asked for, closed anyway** |
| **W4** arm in a `try:` **after `x = 1/0`** | **clean** ❌ | caught | caught | 🔴 R16-A: *"still rejects W4"*. R17-A reported it. **Still green** |
| **W7** arm in a `try` nested at **depth 2** | **clean** ❌ | caught | caught | 🔴 `:2184` still says *"depth 1 … and no further"* |
| **W5b** W5, but the handler narrows **through a helper** | **clean** ❌ | caught | caught | 🔴 **the rule tests `_NARROWING_CALLS` only** |

**Is the rule right?** Yes, and its justification is the best-reasoned sentence in the delta: *"A `try`
body is entered unconditionally, which is why it counts at all. But it only covers what is IN it."*
That is exactly the correct principle, it is stated at the right altitude, and it produces W5 and W10
without touching W2/W6/W11. **This is the first time in five rounds that a fix in this area was
derived from a property rather than from a probe.**

**Does it still red W4, and accept route 18's shape?** It **accepts route 18's shape** ✅ (W2 clean;
`voice_stream_service.py:237` still passes). It **does not red W4** ❌. The rule reasons about *where
the narrowing is*, and W4 is about *whether the arm is reached* — a different question, and the delta
did not answer it. That is defensible as scope, and it is **not** what the record says: R16-A
specified *"accept a `Try` body at depth 1 when no statement precedes the arm in the chain — this
accepts W1 and W2, still rejects W4"*, which is a rule that answers **both** in one clause. Two
rounds later W4 is still green and the specified rule is still unwritten.

**W5b is the sibling miss, and it is unusually clean to state.** Eight lines apart, in the same commit:

```python
# the route-24 filter                                    # the Try rule
_called_name(n) in _NARROWING_CALLS                      _called_name(n) in _NARROWING_CALLS
    or _called_name(n) in reaching                       # ← and nothing here
```

`reaching` is the transitive alias closure the file computes precisely because a narrowing usually
arrives through a helper. The route-24 filter uses it; the `Try` rule does not. **W5 through one level
of indirection is green.** This is the *fixed-at-what-the-verifier-pointed-at* pattern, eighth
occurrence — and the pointer and the miss are in the same diff hunk.

**Reachability:** W4 **production-shaped** (any `try` whose first statement can raise); W5b
**adversarial-to-ordinary** (an entry point whose handler calls a narrowing helper); W7 adversarial.

### 3.5 · Claim 5 — **the qualification is too narrow, and I have five real writes it no longer sees**

**Falsifier stated first:** *if a statement that genuinely writes a row value into `withheld_tools` is
matched by the pre-delta predicate and not by the qualified one, the qualification is too narrow.*

**The premise checks out.** With the qualification reverted, `db/migrate.py::run_migrations:799` reds
the gate (`1 failed`, measured), and the SQL it executes is `ALTER TABLE chat_messages ADD COLUMN IF
NOT EXISTS withheld_tools JSONB` (`migrate.py:327`) — DDL, binding nothing. **Recording it rather than
narrowing the sweep back was the right call**, and it is the second time this delta chose the harder
correct option over the convenient one.

**The qualification is nonetheless too narrow, five ways** — `T10a`, `T10b`, `T10c`, `T10h`, `T10j`
in §3.2, each **caught by the pre-delta predicate and blind now**, each attributed per-probe against
a control. The sharpest is `T10j`:

```python
await conn.execute("UPDATE  chat_messages SET withheld_tools  =  $1 WHERE message_id = $2", None, m)
```

Two spaces after `UPDATE`, two around the `=`. `"UPDATE chat_messages"` misses, `"withheld_tools ="`
misses, `"withheld_tools="` misses. **`1 passed`.** A whitespace difference is not visible in review
and is not visible in a diff that reflows a long line.

**The general defect:** the qualification asks *"does this string look like a write?"* by matching
**four literal spellings of SQL syntax**. SQL is whitespace-insensitive and the predicate is not. The
distinction the delta actually wants is *DDL vs DML*, and that is a **negative** test on two keywords
(`CREATE TABLE`, `ALTER TABLE`) rather than a **positive** test on four — a negative test cannot be
defeated by whitespace, because it fails **toward suspicion**, which is the direction the same file
argues for at `_narrowing_helpers_multi` (*"a gate that guesses may guess toward more scrutiny, never
less"*). The gate 400 lines above states the rule the gate here breaks.

**One sibling in the other direction, not a defect today:** a legitimate **backfill** in a migration
(`UPDATE chat_messages SET withheld_tools = '[]'`) *does* match the qualified predicate, carries no
recorder value, and would red the gate. There is none today. It is worth an allow-list line before
one exists rather than after.

**Reachability: production.**

---

## 4 · The bypass table

| the property asserts | the path that defeats it | measured? | reachable? |
|---|---|---|---|
| U-2 · the recorder's value reaches `withheld_tools` | the SQL is **concatenated** / `.format` / `%` / `" ".join` across the column name | ✅ T10a/b/c/h `1 passed` ×4 | **production — INTRODUCED by item 5** |
| " | **whitespace** defeats all four qualifiers | ✅ T10j `1 passed` | **production — INTRODUCED by item 5** |
| " | the module constant is imported **under an alias** | ✅ T10d `1 passed` | production — NEW (pre-existing, unfound until now) |
| " | the executor is reached via **`getattr`** | ✅ T10e `1 passed` | production — NEW |
| " | **`copy_records_to_table`** — not in `_EXECUTORS` | ✅ T10f `1 passed` | production — NEW |
| " | the column name is in a **variable** inside an f-string | ✅ T10g `1 passed` | adversarial — NEW |
| " | ~~module constant~~ / ~~bare-name executor~~ / ~~unparseable module~~ / ~~module scope~~ | ✅ controls red | — **T9 CLOSED** |
| " | ~~a writer in any other module~~ / ~~`:7424`~~ / ~~two-step bind~~ / ~~alias~~ / ~~`*args`~~ | (R16-A/R17-A) | — **CLOSED** |
| arm-order gate · no narrowing precedes the arming | the narrowing is **beside** the delegate on its line — ternary test, boolean op, list sibling, subscript, **semicolon** | ✅ R25a/b/c/d/g EXEMPTED; control turns all five CAUGHT | **production, by construction — NEW (route 25)** |
| " | ~~the narrowing is INSIDE the delegate's arguments~~ | ✅ `G-R24` reds | — **CLOSED (route 24)** |
| " | ~~narrow-then-delegate~~ / ~~dead branch~~ / ~~uncalled nested `def`~~ | (R17-A) | — **CLOSED (route 23)** |
| " | the exemption's premise (*"unconditionally executed"*) is **false for its one live beneficiary** — `stream_response` is an async generator, `messages.py:521` executes nothing | carried from R17-A, unaddressed | production (harmless today) — **CARRIED** |
| " | a module-scope **lambda**; a narrowing at **module scope** | carried R15/R16 | adversarial (unchanged) |
| the gate reds on an arm that may not run | the arm is in a `try:` **after a statement that raises** (W4) | ✅ **clean**, control caught | **production-shaped — CARRIED, 3rd round** |
| " | the arm is in a `try` nested at **depth 2** (W7) | ✅ **clean**, control caught | adversarial — CARRIED |
| " | the handler narrows **through a helper** (W5b) | ✅ **clean**, control caught | adversarial-to-ordinary — **NEW** |
| " | ~~arm last in `try:`, narrowing in the `except`~~ (W5) | ✅ caught | — **CLOSED** |
| " | ~~narrowing in the `finally`~~ (W10) | ✅ caught | — **CLOSED** |
| the gate does not red on correct code | the arm in a `for` iterator / an `if` test / a `finally` / a `with` **header** | ✅ R24f/g/h/i all `conditional=[…]` | adversarial (false positive) — **CARRIED unchanged.** R24h is now doubly odd: the same commit treats `finalbody` as a place a *narrowing* hides and an *arm* as conditional |
| the turn's outage survives the drain | ~~the drain empties the sink~~ | ✅ **O_B `True`** | — **CLOSED by the restored writer** |
| " | ~~two recorders in one turn~~ | ✅ **O_E `True`** | — **CLOSED** |
| **the turn's outage is not destroyed by an arm** | **an arm follows a drain in the same turn** (`O_K`) | ✅ **`False`**; A-MONO `True` | **latent — and the delta's own test asserts the opposite answer for the identical execution** |
| the outage does not outlive its turn | **turn B reads without arming** (`O_J`) | ✅ **`True`**; A-NOWRITER `False` | latent — **INTRODUCED, and predicted in advance by R17-A** |
| " | a turn that **arms correctly** and is never drained | ✅ `(True, True)`; the arm-order gate permits it | **production — the residual's stated precondition is wrong** |
| a recorded value is read once | `chunk.get("source")` twice; `withheld_json`'s `w["tool"]` twice | ✅ `G01`/`G12` **SILENT on 2260** | — **unguarded, 4th round** |
| " | `tc.get("tool")` then `tc["tool"]` (`stream_service.py:4884`); six `chunk_data` sites in `_emit_chat_turn` | carried from R17-A | adversarial — **CARRIED, unswept** |

---

## 5 · The red-ability table — **with a denominator I derived myself**

**How I derived it.** R17-A's §9 enumerates **13** findings in scope A (8 production + 5 adversarial).
I add the **7 facts this delta newly tightened**, each of which needs a guard of its own: the SQL
resolution, the fail-closed parse, the write qualification, the delegate-arguments filter, the
`Try`-handler rule, the restored writer, the derivation at the arm. Two of R17-A's 13 were bundled
(the `Try` regression covered W4–W7; the monotone claim was one row) and I split neither, to keep the
denominator comparable. **Denominator = 13 + 7 = 24.**

| # | R17-A finding / newly-tightened fact | injection | result | closed? |
|---|---|---|---|---|
| 1 | the revert lost `O_B`/`O_E`/`O_F` | head-to-head, four arrangements | **`O_B`/`O_E` now `True`** | **YES** ✅ |
| 2 | the negative existence claim ("no arrangement works") | built R1 → the delta shipped it | writer restored | **YES** ✅ |
| 3 | the `#:` block describing the reverted rehousing | read `:307–348` | rewritten, and honestly | **YES** ✅ |
| 4 | **"monotone reds two tests" is false** (`:313`) | `G-DERIV` / `A-MONO` | **removed from `:313`, SURVIVES VERBATIM at `:428–429`** — and the true number is **5**, never 2 | **NO — relocated** |
| 5 | the `Try` widening (W4/W5/W6/W7) | W-probes + carrier control | **W5 closed ✅; W4 and W7 still green** | **PARTIAL — NO** |
| 6 | route 24 | `G-R24` | **`1 failed`** ✅ | **YES** ✅ (route 25 opened) |
| 7 | T9 — nine defeats | 12 probes + 3 controls | **all nine red** ✅ | **YES** ✅ (T10 opened) |
| 8 | **G01 — `chunk.get("source")` read twice** | re-read at the classify | **`19 failed` = BASELINE, 2260 tests** | **NO — SILENT, 4th round** |
| 9 | **G12 — `withheld_json`'s walrus** | de-walrus it | **BASELINE, 2260 tests** | **NO — SILENT, 4th round** |
| 10 | the guard's misattributing failure message | read the new one | rewritten, and it now names the real cause | **YES** ✅ |
| 11 | the sink leak (`O_H`) | the three-shape probe | **still leaks, and the stated precondition is wrong** | **NO — OPEN, mis-scoped** |
| 12 | R24f/g/h/i false positives | re-ran all four | **`conditional=[…]` ×4, unchanged** | **NO — carried** |
| 13 | `tc['tool']` + 6 `chunk_data` sites | `stream_service.py` untouched by the delta | — | **NO — carried** |
| 14 | the exemption's premise vs `stream_response` (async generator) | unaddressed | — | **NO — carried** |
| 15 | W3 / module-scope lambda / module-scope narrowing | carried | — | **NO — carried adversarial** |
| 16 | **NEW** SQL resolved through module + cross-module constants | `G-T9e` | **`1 failed`**, the named test | **guarded ✅** |
| 17 | **NEW** fail-closed on an unparseable module | `G-T9g` | **`1 failed`**, the named test | **guarded ✅** |
| 18 | **NEW** the write qualification | `G-QUAL` | **`1 failed`** on `migrate.py:799` | **guarded ✅** (too narrow — §3.5) |
| 19 | **NEW** the delegate-arguments filter | `G-R24` | **`1 failed`**, the named test | **guarded ✅** |
| 20 | **NEW** the `Try`-handler rule | `G-TRY` | **`1 failed`**, the named test | **guarded ✅** |
| 21 | **NEW** the restored writer | `G-WRITER` | **`1 failed`**, the named test | **guarded ✅** |
| 22 | **NEW** the derivation at the arm | `G-DERIV` | **`5 failed`** | **guarded ✅** |
| 23 | **NEW** the claim that `O_K` does not exist | `O_K` probe + `A-MONO` | **`False`, and the test asserts `False` for the same execution** | **NOT GUARDED — ASSERTED WRONG** |
| 24 | **NEW** `O_J`, the restored writer's cost | `O_J` probe, three arrangements | **`True` where truth is `False`** | **NOT GUARDED, not documented** |

**Red-able and closed: 13 of 24 — `54%`** (rows 1, 2, 3, 6, 7, 10, 16–22). Up from R17-A's 56% on a
denominator of 16 — but the composition changed for the better: **seven of the thirteen are guards
this delta wrote itself, and all seven red for the reason they name.** Two of the eleven open rows
(8, 9) are now in their **fourth** round after being asked for by name twice, and two more (23, 24)
are new claims with no guard at all — one of which is guarded *backwards*.

---

## 6 · The sibling table

| fix | sibling I looked for | how | also fixed? |
|---|---|---|---|
| SQL resolved through module constants | SQL that is **not one constant** — concatenation, `%`, `.format`, `join` | 4 probes with attribution | **NO — T10a/b/c/h, and 4 of them were caught before this delta** |
| " | a constant imported **under an alias** | wrote the alias | **NO — T10d** |
| " | an executor that is not an `Attribute`/`Name` — `getattr` | wrote it | **NO — T10e** |
| " | a **write form** outside `_EXECUTORS` — `copy_records_to_table` | wrote it | **NO — T10f** |
| the write qualification | whether it still sees a **qualifying** write with different whitespace | `UPDATE  chat_messages … withheld_tools  =  $1` | **NO — T10j, `1 passed`** |
| " | whether a legitimate migration **backfill** would now false-positive | read `migrate.py` | none exists today — worth an allow-list line first |
| the delegate-arguments filter | a narrowing **beside** the delegate rather than inside it | ternary, `or`, list, subscript, semicolon | **NO — route 25 ×5, control confirms the exemption is the cause** |
| " | whether the filter uses the same narrowing set as the `Try` rule | read both | **it does — `_NARROWING_CALLS or reaching`** ✅ **and that is what makes W5b's omission a sibling** |
| " | whether the `<=` premise holds for its live beneficiary | re-read `stream_response` | **NO — still an async generator; `messages.py:521` executes nothing.** Carried unaddressed |
| the `Try`-handler rule | a handler that narrows **through a helper** | `reaching` probe | **NO — W5b, and the fix eight lines above uses `reaching`** |
| " | whether **W4** (named by R16-A and R17-A) is closed | probe + carrier control | **NO — still clean** |
| " | whether *"depth 1 and no further"* became true | W7 | **NO — recursion still unbounded** |
| " | whether the `finally` treatment is consistent | W10 (narrowing) vs R24h (arm) | **NO — a narrowing in `finally` counts, an arm in `finally` is "conditional"** |
| the restored writer | whether the arrangement is now correct in **every** ordering | 14 orderings × 4 arrangements | **NO — `O_K` `False`, `O_J` `True`** |
| " | whether the deleted impossibility argument became true again | `A-MONO` vs HEAD on the same execution | **YES it did — and the delta deleted it in the commit that made it true** |
| " | whether the residual's stated precondition is the real one | three two-turn shapes | **NO — it is "never drained", not "never armed", and the arm-order gate does not forbid it** |
| " | whether the comment block at the arm was updated with it | read `:425–431` | **NO — four false or stale statements, contradicting the new block 77 lines above** |
| " | whether `catalogue_outage_registered`'s body comments agree with each other | read `:531–545` | **NO — "Ask the RECORDER first" above "Read from the FLAG first"** |
| the `_tool`/`_source` pair | whether `G01` finally got a test | full suite, 2260 | **NO — SILENT, 4th round** |
| " | whether `G12` finally got a test | full suite, 2260 | **NO — SILENT, 4th round** |

---

## 7 · Where the builder's documentation of a residual is wrong

1. **`instrument.py:425–431` is the counter-example to the delta's headline claim, and it is in the
   delta's own file, untouched.** It states four things, all of which the delta contradicts or
   falsifies: *"the least wrong of **the four arrangements measured**"* (the delta reverted to
   arrangement one); *"monotone reds **two tests**"* (measured **5** with the writer restored, **0**
   without — never 2, in any tree, in any round); *"see `catalogue_outage_registered` … for **who owns
   the real fix**"* (that ownership paragraph was deleted by this commit); and — the one that matters
   — *"it therefore also **LOWERS a true flag when an arm follows a drain within one turn**"*, which
   **is** the seventh ordering, named in the file, 77 lines below a `#:` block claiming the only
   residual rides the sink. **Production-reachable: it is what a reader of the arm sees.**
2. **The residual's precondition is wrong, so the mechanism it is handed to does not own it.** The
   text says *"a turn that records and **never calls `arm_turn_surface()`**"* and *"the arm-order gate
   statically forbids the shape"*. Measured: a turn that **arms exactly once, unconditionally, before
   narrowing** — a turn the gate is fully satisfied by — leaks identically whenever its sink is not
   drained. The precondition is **"never drained"**. **Production.**
3. **`test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN` asserts the wrong answer for a state it does test.** Its
   two-turn row runs `arm, record, drain, arm, read` and requires `False`. That is the arm-after-drain
   state, which requires `True`. The test is not silent about `O_K`; it is **wrong** about it, and it
   will red on the day somebody fixes it. **Permanent.**
4. **The deleted argument was true.** *"`arm_turn_surface` cannot tell 'a new turn is starting' from
   'this turn already narrowed'"* is not vacuous at this HEAD — it is demonstrable: `A-MONO` answers
   both `True`, HEAD answers both `False`, and the two orderings need different answers. **The delta
   deleted the correct description of the hole in the commit that reinstated the hole.** The
   transferable sentence the delta itself wrote — *"a measurement is about the tree at the moment it
   ran"* — applies to **R17-A's refutation** as much as to the builder's original measurement, and
   nothing re-ran it against the restored tree.
5. **`catalogue_outage_registered:531` and `:542` give opposite instructions eleven lines apart.**
   *"Ask the turn's **RECORDER** first"* survives above *"Read from the **FLAG** first"*. The recorder
   is not consulted anywhere in the function.
6. **R16-A specified the `Try` fix two rounds ago and it is still unwritten.** *"still rejects W4"* was
   in the text; W4 is green; this delta's comment **names W4's sibling** and fixes a different shape.
   Eighth occurrence of *fixed at what a verifier pointed at rather than what it meant*.
7. **Exemplary, and it should lead the next brief.** **Seven of seven fixes in this delta have a
   red-able test that reds for the reason it names** — the best guard record in my scope in eighteen
   rounds. The `Try` rule is the first fix in this area **derived from a property** (*"a `try` body is
   entered unconditionally … but it only covers what is IN it"*) rather than from the shape of the
   last probe, and it closed a shape nobody asked for (`W10`) as a consequence — which is what a
   correct rule does and an enumeration never does. The `db/migrate.py` false positive was **recorded
   and reasoned about rather than silenced by narrowing the sweep back**, and the parse is now
   **fail-closed** with a test. And the delta shipped R17-A's one-line refutation in full, including
   the parts that made the builder look worse, with the history written out. **The failure of this
   round is not carelessness; it is that the round's central claim was re-derived by argument at the
   exact moment it needed to be re-executed.**

---

## 8 · Convergence, my scope

| round | production-reachable | adversarial-input only | changed lines (scope A) | introduced by the delta | **introduced per 100 changed lines** |
|---|---|---|---|---|---|
| 13 | 13 | 5 | 150 | 3 | 2.00 |
| 14 | 9 | 6 | 258 | 2 | 0.78 |
| 15 | 6 | 6 | 89 | 2 | 2.25 |
| 16 | 7 | 5 | 739 | 5 | 0.68 |
| 17 | 8 | 5 | 415 | 5 | 1.20 |
| **18** | **9** | **5** | **404** | **3** | **0.74** |

**Production-reachable, this round:** claim 1 refuted (`O_K`, counted once); the residual's wrong
precondition (a correctly-arming turn leaks); `instrument.py:425–431`'s four false/stale statements;
`catalogue_outage_registered`'s self-contradicting comments; T10's five *introduced* SQL blindnesses
(counted once); T10's four pre-existing ones (counted once); route 25 (five variants, counted once);
W4 still green; `G01`+`G12` silent for a fourth round (counted once).
**Adversarial:** W5b; W7; R24f/g/h/i (counted once); `tc['tool']` + the six `chunk_data` sites
(carried); the module-scope lambda / narrowing (carried).

**Introduced by this delta — 3:** (i) the item-5 qualification blinded the terminal-write gate to five
ordinary SQL spellings it caught before; (ii) `O_J` — the restored writer leaks into a turn that reads
without arming, which R17-A predicted **in advance** as R1's honest cost and which is undocumented;
(iii) the intra-file contradiction between the new `#:` block and the untouched comment at `:425–431`,
which previously agreed with each other.

**Closure: 13 of 24 — 54%.**

**Which number should this run steer by?** **I agree with steering by raw count with regressions
flagged separately, and I would add a second axis, because raw count is about to mislead in the
optimistic direction.** Raw introduced reads 3, 2, 2, 5, 5, **3**; normalised 2.00, 0.78, 2.25, 0.68,
1.20, **0.74** — the second-lowest ever, on a delta whose central claim is false. A rate cannot see
that, and neither can a count: **the three introduced defects this round are small, and the failure is
large.** The axis that does see it is the one this round makes measurable for the first time:

> **How many of the round's load-bearing claims were established by execution, and how many by
> argument?** This delta's two claims: claim 2 (the T9 closure) was **executed** — twelve probes, a
> test per defeat, and it is correct. Claim 1 was **argued** — and it is false, with the
> counter-example sitting in the same file. Ratio 1:1.

**That is the number I would steer by, alongside the raw count.** It is the fifth consecutive round in
which the *largest* change is the *least-executed* one, and it is the only metric that has been red
every single time. The terminating condition should stay at three consecutive rounds with
`introduced == 0`; this is not one of them, but it is the first round where the *guards* were
uniformly sound, and that is a real inflection worth naming as such.

---

## 9 · What would have to be true for this to PASS

* **Put `O_K` in the test and pick a side, in writing.** `arm → record → drain → arm → read` needs
  `True`; the two-turn row needs `False`; **they are the same execution**. Assert both and one of them
  reds — that is the point. Then either (a) restore the impossibility paragraph, corrected: *the
  contradiction is real, its owner is a turn identity, owner CP-2* — with `O_K` as the standing
  witness; or (b) give the module the one thing that resolves it, which is a token the arm can compare
  (`_turn_token: ContextVar[object]`; the arm lowers only when the token changes). **(a) is honest and
  costs nothing. (b) is four lines. What is not available is a third round of "this arrangement is
  correct".**
* **Rewrite `instrument.py:425–431`.** Delete *"monotone reds two tests"* (it is 5, and it was 0);
  delete *"the least wrong of the four arrangements measured"* (arrangement one was restored); delete
  the pointer to a paragraph this commit removed; and **keep** *"LOWERS a true flag when an arm follows
  a drain within one turn"*, which is the only true sentence in the block and is the residual.
* **Fix the residual's precondition** in the `#:` block and in the test docstring: it is *"a turn whose
  sink is never drained"*, not *"a turn that never arms"* — and say plainly that the arm-order gate
  **does not** forbid it.
* **Make `_names_the_column` a negative test.** Match `withheld_tools` and **exclude** `CREATE TABLE`
  / `ALTER TABLE`, rather than requiring one of four literal spellings. That restores T10a/b/c/h/j,
  keeps `migrate.py` green, and fails toward suspicion — the rule this file already states 400 lines
  above.
* **Resolve the SQL across operators, not just across bindings.** `BinOp`/`JoinedStr`/`.format`/`%`
  should be flattened to their constant parts and matched **as one string**, and `_EXECUTORS` should
  gain `copy_records_to_table`. Follow `ImportFrom` aliases into `global_sql_names`, and treat a call
  whose `func` is not resolvable to a name as **checkable, not skippable**.
* **Replace the delegation `<=` with the statement rule.** R17-A gave both disjuncts; the delta shipped
  one. *"Require the delegate's whole statement to contain no narrowing"* closes route 25's five
  variants and route 24's three in one clause, and `G-LTE` already showed the `<=` is only needed
  because the delegate and the narrowing share a statement — which is exactly the condition to forbid.
* **Give the `Try` rule `reaching`.** One clause, copied from the filter eight lines above it. Then
  **write R16-A's rule for W4**: accept a `Try` body's arm only when no statement precedes it in the
  chain. That closes W4 and W7 together, and it is the rule that was specified two rounds ago.
* **Give `G01` and `G12` a test each.** Fourth round. Both were asked for by name in R16-A and R17-A,
  and this delta wrote seven new guards without writing these two.
