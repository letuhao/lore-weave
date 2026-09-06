# CP-1 · round 19 · V-CODE — Verifier A (the instrument)

`git rev-parse HEAD` at start: **`5b531e22ae93f52cc45f55741b3016b76d754691`**
`git rev-parse HEAD` before writing: **`5b531e22ae93f52cc45f55741b3016b76d754691`** — it did not move.
`git status --porcelain -- services/chat-service`: **empty** at both ends.

Graded delta: `7bb963db9`, diffed against `2faa88bac`. Scope A: `app/services/instrument.py`,
`stream_service.py`, `voice_stream_service.py`, `app/routers/`, `app/db/`, and the gate machinery in
`tests/test_cp0_instrument.py`. **74 changed lines in scope** (`60+14`, all in
`tests/test_cp0_instrument.py`). `instrument.py`, `stream_service.py`, `voice_stream_service.py`,
`app/routers/` and `app/db/` are **untouched** by this delta.

Everything below was **executed**, in a scratch tree at `…/scratchpad/r19/root/services/chat-service`
built to the repository's own depth (`services/chat-service` + `contracts/` + `sdks/` + `scripts/`),
so `parents[3]` resolves and no test fails for tree-shape reasons.

**Scratch baseline: `tests/test_cp0_instrument.py` = `135 passed`, verified deterministic over
10 consecutive serial runs. Full `tests/` = `8 failed, 2256 passed, 2 skipped` = 2266 tests.** The 8
are sibling-repo absences (ai-gateway TS sources; `.github/workflows/lint-foundation.yml`) and every
delta below is reported against that baseline, not against zero. The builder's "2266 tests" is the
correct total.

Every injection prints an on-disk verification before its suite runs; every restore is asserted
byte-identical by sha256 against **the frozen blob**, not merely against my own snapshot. No
`git checkout` was used anywhere.

---

## 0 · Two errors in my own instrument, found and corrected before any number below

Recorded first, because the round grades instruments and mine was wrong twice.

1. **I ran a node id that does not exist.** `test_the_TERMINAL_GATE_sees_EVERY_SPELLING_OF_THE_SAME_WRITE`
   is in `TestTheARM_ORDER_GATE_SEES_THE_SHAPES_IT_WAS_BLIND_TO`, not in
   `TestU2ACatalogueOutageIsRegistered`. pytest reports a missing node id as `ERROR` with a non-zero
   exit, which my harness read as **RED**. Three measurements were wrong in the alarming direction
   until I checked the collection list. *A non-zero exit is not a failing test.*
2. **`pathlib.write_text` on Windows translates `LF` → `CRLF`**, so every "restore" I performed
   reproduced the file's *meaning* and not its *bytes* — sha `ea4fc414…` where the artifact is
   `79e56d81…`. Semantics were unaffected, so no measurement was invalidated, but a restore that
   changes the artifact is not a restore. `patchkit` now reads and writes bytes and asserts the
   restored sha against `git show <frozen>:…`.
3. **I claimed the suite was flaky and it is not.** I observed `3 failed`, `1 failed`, then
   `135 passed` on identical bytes. The cause was mine: a foreground run I had killed at the
   10-minute cap skipped its `finally`, and the leftover probe module poisoned later runs. Serially,
   the artifact is **10/10 `135 passed`**. The flakiness claim is **withdrawn**. What survives is a
   real and different property — §3.6.

---

## 1 · Verdict — **FAIL**

| # | claim under test | verdict | reachability of the residual |
|---|---|---|---|
| 1 | **the SQL matcher is reassembled: all five blinded spellings caught again, `db/migrate.py` still out** | **PASS on both halves, measured. SIXTH SPELLING FOUND — five variants.** All five (concatenation, `.format`, `%`, `" ".join`, two spaces) are **CAUGHT** again ✅; `db/migrate.py` is **in the 115-module sweep and not in `binds_checked`** ✅, so the exclusion is by qualification, not by scope. Blind to: an **f-string with the column in a constant**, **table+column both interpolated**, **double-quoted SQL identifiers**, **an f-string wrapping the repo's own `segment_merge_sql` with a constant argument**, and **SQL arriving as a default argument** — each with a positive control | **production. `stream_service.py:6297/6382/7398` already write this SQL as f-strings through `segment_merge_sql`; only the string literal `'withheld_tools'` inside the call keeps them visible** |
| 2 | **one narrowing predicate now serves both the `Try` rule and the delegation filter; do they agree, did unifying widen anything?** | **They agree — by call-site convention, not by construction. W5b and W5c are CLOSED ✅.** The exemption was **not** widened (the relation is monotone: a broader `narrows` can only refuse more). What *was* widened is the `Try` rule's false-positive namespace, from 5 primitive names to 13; a false positive is constructible (`_assert_known_tool`) but **inert today** — 0 of the 13 names is defined twice. **The coupling is a default argument (`narrows=None`), so a third call site reproduces W5b in silence** | **latent. The widening is inert; the default-argument coupling is one added call site away** |
| 3 | **W4 and W7 still green at R18 — confirm; is the `Try` rule's subset now right or merely different?** | **Confirmed: W4 CLEAN, W7 CLEAN.** W4 is **fourth round** — R16-A specified the rule, R17-A and R18-A reported it, this delta names its sibling in a comment and does not fix it. The subset is **right and still incomplete**: the delta correctly extends the *"a handler that narrows"* rule through helper hops (W5b, W5c, W10b all now CAUGHT), which is a genuine improvement — but W4 is a different question (*is the arm reached*) and remains unasked | **W4 production-shaped (any `try` whose first statement can raise); W7 adversarial** |
| 4 | **`G01` and `G12` — construct the guard or state the property has no subject** | **BOTH ANSWERED, and the two answers differ.** `G01`: the **`tool` half IS guarded** (`test_TOOL_READ_ONCE…`, `:3188`) — R18-A's *"G01 SILENT"* was half wrong. The **`_source` half is genuinely unguarded**: a double read leaves the full suite at baseline `8 failed`. Guard **constructed**, green on the artifact, **red on both halves**. `G12`: **the property HAS NO SUBJECT** — every public door rebuilds the row as a plain `dict`, measured at 0 reads of `tool` on a two-faced mapping. The builder's negative claim at `:966-968` is **TRUE** | **`G01`/`_source`: adversarial (needs a two-faced argument). `G12`: none — close it** |
| 5 | **"the outage residual is unaddressable by this variable"** | **REFUTED, by execution, and the fix runs the full suite at baseline.** FLAG-only answers **3 of 9** orderings wrong — including **O_R, an eighth ordering I found**. Consulting the **recorder's own retained rows** answers **8 of 9**, leaving only the sink-borne `O_J` the builder correctly identifies. It splits `O_K` (True) from the two-turn case (False) — the pair the delta calls byte-identical — because they differ in *which recorder the reader holds*. It is not a turn identity, it does not touch `catalogue_outage`, and **`voice_stream_response` already has its recorder in scope at the read** | **production. `voice_stream_service.py:242` constructs it, `:422` reads — same function, no new plumbing** |
| 6 | **convergence, raw and per changed line, plus executed-vs-argued** | **Closure 3 of 6 claims. Introduced 3 over 74 changed lines = 4.05/100.** Executed-vs-argued **3:3 — executed 3/3 true, argued 0/3 true.** §9 | §9 |

### The most valuable thing this round produced

**The negative claim is refuted for the third consecutive round, and this time the refutation runs.**

R17's refutation was a sentence the builder had deleted. R18's was a sentence the builder had left in.
R19's is neither: it is a six-line patch that answers the ordering the delta calls unanswerable and
leaves the whole suite at baseline.

| | `O_K` (arm, record, drain, **arm**, read) | two-turn `O_D` (turn B) | orderings wrong | full suite |
|---|---|---|---|---|
| truth | **`True`** | **`False`** | — | — |
| **HEAD** — flag only | **`False`** 🔴 | `False` ✅ | **3 / 9** | `8 failed, 2256 passed` |
| **+ recorder** | **`True`** ✅ | `False` ✅ | **1 / 9** | `8 failed, 2266 passed` — **baseline** |

The delta's argument is that `O_K` and the two-turn case are *"byte-identically the same execution, so
no assignment of the flag can split them."* **The premise is true and the conclusion does not follow.**
They are byte-identical *in the ContextVars*. They differ in the object the reader is holding: in
`O_K` the drained outage row went into the recorder that is still live; in the two-turn case turn B
builds its own. The delta reasoned about the state it had chosen to look at and concluded about all
possible states.

And the mechanism is not new. `instrument.py:531` says, in the imperative:

> *"Ask the turn's **RECORDER** first, not the sink's current contents"*

…eleven lines above `:542`, which says *"Read from the **FLAG** first"*, in a function that consults no
recorder at all. R18-A reported that contradiction. This delta did not touch it, and then built a
negative existence claim on the side of it that is wrong.

**The transferable part:** the objection recorded at `:587-590` — *"a turn can construct zero, one or
two recorders, so it was never the turn-lifetime home"* — is an objection to a **ContextVar** home. It
was carried across to rule out the recorder **as an argument**, where it does not apply, because a
caller passing the recorder it is about to write with cannot pass the wrong one. A reason was
generalised past the change that made it true. That is the same failure the delta's own `catalogue_outage`
comment spends thirty lines confessing to, one level up.

---

## 2 · The guard table — *is there a test? can it red? does it red for the reason it names?*

Every row **executed**: revert the fix → verify on disk → run the suite → restore byte-identically.

| fix in the delta | is there a test? | can it red? | does it red for the reason it names? |
|---|---|---|---|
| the SQL **reassembly** (`:1540-1548`) | **yes** — `test_the_TERMINAL_GATE_sees_EVERY_SPELLING_OF_THE_SAME_WRITE` | **yes** — `D01` **`1 failed`**, and it is *that* test | **yes for the four spellings it executes** ✅. **NO for the fifth it names** (`%` is in the docstring, absent from the dict — I verified `%` is caught independently, so nothing hides behind it) |
| the whitespace normalisation (`.split()`) | the gate **is** the test | **yes** — `D02` **`1 failed`** | **yes** ✅ — attributed to the gate itself |
| `"UPDATE chat_messages"` alternative | yes | **yes** — `D05` **`1 failed`** | **yes** ✅ |
| `"INSERT INTO chat_messages"` alternative | yes | **yes** — `D04` **`1 failed`** | **yes** ✅ |
| the write-**qualification** as a whole (`:1543`) | yes | **yes** — `D03`/`D08` **`1 failed`** each | **yes** ✅ — both the widening and the narrowing direction red |
| `"withheld_tools ="` alternative | **NO** | — | — **`D06` GREEN.** Deleting it leaves `135 passed` |
| `"withheld_tools="` alternative | **NO** | — | — **`D07` GREEN** |
| the `segment_merge_sql` branch (`:1549-1553`) | **NO** | — | — **`D09` GREEN.** Currently redundant with `_flat`; nothing says so, and nothing would notice when it stops being redundant |
| **the `narrows` unification — the W5b fix** (`:2229`, `:2273`, `:2434`, `:2437`, `:2490`) | **NO** | — | — **`D10`, `D11`, `D12`, `D14`, `D15`, `D16` ALL GREEN.** Reverting the arm site alone restores **W5b and W5c to CLEAN** at **`135 passed`**. *A fix without a red-able test is not a closed finding* |
| the `Try` handler rule (pre-existing, R17) | **yes** — `test_an_ARM_IN_A_TRY_WHOSE_HANDLER_NARROWS_is_not_COVERED` | **yes** — `D13`/`D17` **`1 failed`** | **yes for W5** ✅ — **and it is the R17 rule, not this delta's contribution** |
| the `finalbody` arm of the `Try` rule (closes W10) | **NO** | — | — **`D18` GREEN** |
| the new spelling test's own **oracle** (`match='withheld_tools'`) | **NO** | — | — **`D19` GREEN.** Widening it to a bare `pytest.raises(AssertionError)` changes nothing |
| the new spelling test's **case list** | **NO** | — | — **`D20` GREEN.** Deleting the `two spaces` case — the headline of §3.5 of R18-A — changes nothing |
| `G01` — `_source` bound once (`:234`) | **NO** | — | — **unguarded, measured**: double read → full suite at baseline `8 failed`. **Guard constructed in §5, red-able.** *R18-A said "silent"; half of it is not — see §5* |
| `G01` — `_tool` bound once (`:235`) | **yes** — `:3188` | **yes** — `1 failed` | **yes** ✅ |
| `G12` — `withheld_json`'s walrus (`:969`) | — | — | — **the property has no subject. CLOSE IT** (§5) |
| `catalogue_outage_registered`'s own body (`:531` vs `:542`) | — | — | — **the contradiction R18-A reported is untouched, and §3.5 shows the side it resolves to is the wrong one** |

**Red-ability: 8 of 20 (40%).** The SQL matcher is 6 of 9; **the delta's `narrows` unification is 0 of 7
of its own decision points**; the new test's own integrity is 0 of 2.

---

## 3 · The falsifier, per claim — stated before the search

### 3.1 · Claim 1 — the reassembly. **PASS on both halves. Sixth spelling found, five variants**

**Falsifier stated first:** *if any of the five spellings R18-A attributed is still blind, or if
`db/migrate.py` re-enters `binds_checked`, the fix failed; if a spelling of an ordinary row write
exists that the reassembly does not see, the class is still open.*

Each probe is one module written into `app/services/`, the gate run alone, the file removed, and the
result **attributed by module name in the assertion text** — not merely "red".

| spelling | result |
|---|---|
| S1 concatenation `"UPDATE chat_messages SET " + "withheld_tools = $1…"` | **CAUGHT** ✅ |
| S2 `.format()` | **CAUGHT** ✅ |
| S3 `%` | **CAUGHT** ✅ — *and this is the one the delta's own test does not execute* |
| S4 `" ".join([...])` | **CAUGHT** ✅ |
| S5 two spaces `"UPDATE  chat_messages SET withheld_tools  =  $1"` | **CAUGHT** ✅ |
| S6 implicit adjacent-literal concatenation | **CAUGHT** ✅ |
| S8 newline inside a triple-quoted literal | **CAUGHT** ✅ |
| S9 lowercase `update … set` | **CAUGHT** ✅ |
| S10 `UPDATE public.chat_messages` | **CAUGHT** ✅ |
| S12 `UPDATE chat_messages AS m SET` | **CAUGHT** ✅ |
| S13 `INSERT INTO chat_messages (id, withheld_tools) VALUES` | **CAUGHT** ✅ |

**`db/migrate.py`:** instrumented the gate to print its own working set. `SWEPT_MODULES = 115`,
`MIGRATE_IN_SWEEP = ['db/migrate.py']`, and `BINDS_CHECKED` is exactly the four named writers. **The
DDL is inside the sweep and outside the check** — the exclusion is the qualification doing its job,
not the scope being narrowed back. ✅

**The sixth spelling — `T11`, five variants, each with a positive control** (the identical statement
with a literal column name, which the gate catches; so every BLIND below is the *spelling* and not the
*statement*):

| # | spelling | control | probe |
|---|---|---|---|
| **T11a** | f-string, column via a module constant — `f"UPDATE chat_messages SET {_COL} = $1…"` | CAUGHT | **BLIND** |
| **T11b** | f-string, table **and** column interpolated | CAUGHT | **BLIND** |
| **T11c** | double-quoted SQL identifiers — `'UPDATE "chat_messages" SET "withheld_tools" = $1…'` | CAUGHT | **BLIND** |
| **T11d** | **f-string wrapping `instrument.segment_merge_sql(_C)`** | CAUGHT | **BLIND** |
| **T11e** | SQL arriving as a **default argument** | CAUGHT | **BLIND** |
| T11f | `"…SET COL = $1…".replace("COL", "withheld_tools")` | CAUGHT | CAUGHT ✅ |

**Why the reassembly misses these and it is not an oversight of effort.** `_flat` concatenates
`ast.Constant` string values. An f-string's interpolated part is a `FormattedValue` wrapping a `Name`,
not a `Constant`, so the column name is simply not in the assembled text. The delta moved from
*"one literal must contain the whole pattern"* to *"the concatenation of all literals must"* — a real
widening, which is why S1–S5 came back — but both are **literal-only**, and the repository's live SQL
is not literal-only.

**T11d is the reachable one, and the reachability is not hypothetical.** This is how the code is
written **today**:

```python
# stream_service.py:6296-6297
"UPDATE chat_messages SET outcome = $2, "
f"       {instrument.segment_merge_sql('withheld_tools')} "
```

The only thing keeping this site visible to the gate is the string literal `'withheld_tools'` **inside
the call**. I substituted a module constant for that literal at the live site — a one-token refactor
that changes no behaviour — and the site went invisible: `binds_checked` dropped from 4 to 3.

**The count NV guard caught that, and that is worth saying plainly:** `assert len(binds_checked) >= 4`
fired, so a maintainer cannot silently lose one of the four. The NV guard is doing real work. But it
is a **count**, so it is satisfied by any four: a *new* writer added in the T11a/d spelling while the
existing four remain is invisible, and that is exactly probe T11a — **GREEN, binding a literal `None`**.
`app/agentruntime/` is CP-2's landing zone and is in the sweep by construction; a terminal write there
written as an f-string is not covered.

### 3.2 · Claim 2 — the unified predicate. **They agree. The exemption was not widened. The coupling is a default argument**

**Falsifier stated first:** *if the two sites disagree on any shape, or if unifying them granted an
exemption that was previously refused, the fix is wrong; if the agreement is not enforced, it is not
closed.*

**They agree, and they agree by construction at the two call sites**, because both are handed the same
`_narrows` object (`:2437`, `:2490`). Measured over 16 shapes — §3.3.

**Was the exemption widened anywhere? No, and the reason is monotone rather than empirical.** The
`Try` rule descends only when `not any(handler narrows)`. A broader `narrows` makes `any` true more
often, so it descends **less** often, so it yields **fewer** delegates and **fewer** top-level arms.
Fewer delegates = fewer exemptions. The direction is strictly toward suspicion, which is the safe one.

**What was widened is the false-positive namespace of the `Try` rule**, from `|_NARROWING_CALLS| = 5` to
`|reaching| = 13`. I measured the population: **13 of 644 function names under `app/` (2%), and zero of
the 13 is defined in more than one place.** So the over-approximation is **inert today**. It is
constructible: I defined a local helper named `_assert_known_tool` returning `x + 1`, called it from a
handler, and the arm was reported **CONDITIONAL** — a false positive on correct code, control clean.
Adversarial today; it becomes ordinary the day someone reuses one of those 13 names.

**The finding is the coupling, not the predicate.** `_unconditional_calls(body, pred, narrows=None)`
keeps a default that silently restores the bare primitive set. The two sites pass `_narrows` *by
convention*. A third call site written without the third argument reproduces W5b exactly, and §3.3
shows nothing would red. **The delta fixed "one relation, two definitions" by making one definition and
two call sites that must both remember to use it** — which is the same shape one level down, and is the
shape the commit message says it is fixing.

### 3.3 · Claim 3 — W4 and W7. **Both still CLEAN. The subset is right and still incomplete**

Sixteen shapes, each a real module written under `app/services/` and swept by the real
`_turn_entry_calls()`. `CAUGHT` = the arm is reported conditional.

| shape | R18 | **R19** | correct? |
|---|---|---|---|
| C1 arm at top level, then narrow | clean | **clean** | ✅ control |
| C2 arm inside an `if` | caught | **caught** | ✅ control |
| W2 arm is the first statement of a `try:` | clean | **clean** | ✅ |
| **W4 arm in a `try:` after `x = 1/0`** | clean ❌ | **clean** ❌ | 🔴 **4th round** |
| W5 arm in `try:`, narrowing in the handler | caught | **caught** | ✅ |
| **W5b handler narrows through a helper** | clean ❌ | **caught** | ✅ **CLOSED by this delta** |
| **W5c handler narrows through two helpers** | — | **caught** | ✅ **closed too** |
| W6 narrowing after the whole `try/except` | clean | **clean** | ✅ |
| **W7 arm in a `try` nested at depth 2** | clean ❌ | **clean** ❌ | 🔴 comment still says *"depth 1 … and no further"* |
| W7b depth-2, inner handler narrows | — | **caught** | ✅ |
| W7c depth-2, outer handler narrows | — | **caught** | ✅ |
| W10 arm in `try:`, narrowing in the `finally` | caught | **caught** | ✅ |
| **W10b `finally` narrows through a helper** | — | **caught** | ✅ **closed as a consequence** |
| W11 narrowing in the `else:` clause | clean | **clean** | ✅ |
| W12 handler narrows via an **alias** (`p = c.get_tool_definitions; p()`) | — | **NOT DISCOVERED** | 🔶 the function is not recognised as an entry point at all; `aliases` is collected but does not make a function a turn |
| W13 arm in a `with` whose inner `try` handler narrows | — | **caught** | ✅ |

**Is the subset right or merely different?** **Right, and incomplete.** The rule the delta extends —
*"a `try` body covers only what is in it; if a handler of the same `try` narrows, no arm inside the body
precedes that narrowing"* — is stated at the correct altitude, and extending it through the transitive
closure is the correct completion of it: W5b, W5c and W10b all close together, and W2/W6/W11 stay clean.
That is a good fix.

**W4 is a different question and remains unasked.** The `Try` rule reasons about *where the narrowing
is*; W4 is about *whether the arm is reached*. R16-A wrote the rule that answers both — *accept a `try`
body's arm only when no statement precedes it in the chain* — two rounds ago. It closes W4 and W7
together. It is still unwritten, and this delta's comment names W4's sibling while fixing a third thing.

**And the delta's own fix is unguarded.** Reverting `_narrows` at the arm site (`:2490`):

| | W5 | W5b | W5c | instrument suite |
|---|---|---|---|---|
| **HEAD** | caught | **caught** | **caught** | `135 passed` |
| arm site drops `_narrows` | caught | **clean** 🔴 | **clean** 🔴 | **`135 passed`** |

The defect the delta exists to fix comes back, and the suite does not notice.

### 3.4 · Claim 4 — `G01` and `G12`. **One has a subject and now has a guard; the other has no subject**

**`G01` — and R18-A's record of it is half wrong.** The `tool` half **is** guarded, by
`test_TOOL_READ_ONCE__the_pair_the_source_fix_left_behind` at `:3188`: restoring the double read of
`tool` reds it (`1 failed`, full suite `9 failed` vs baseline `8`). *"G01 SILENT on all 2260 tests,
FOURTH round"* is not true of the pair.

The **`_source` half is genuinely unguarded**, which is the half `G01` is named for. Restoring the
double read of `source` — classify from one read, stamp `latency_unmeasured` from another — leaves the
full suite at **`8 failed, 2262 passed` = exactly baseline, zero non-baseline failures.**

**Constructed** (`tests/test_zz_r19_g01.py`, my scratch tree, not committed). The property is *"one read
of each fact, bound to a local"*, so the guard is the **read count**, not a downstream symptom a later
`setdefault` can mask:

| | `_source` double read | `_tool` double read | artifact |
|---|---|---|---|
| `test_G01_source_is_read_ONCE` | **RED** ✅ | green | **green** ✅ |
| `test_G01_tool_is_read_ONCE` | green | **RED** ✅ | **green** ✅ |

Forty lines, three tests, no false positive on the artifact. *It was not harder; it was deferred* —
the same sentence this file already carries about the terminal-write anchor.

**`G12` — the property has no subject, and that is a finding, not a deferral.** The comment at
`:966-968` claims *"the rows here are the recorder's own, so a container that answers twice differently
is not constructible."* **That negative claim is TRUE.** I pushed a two-faced mapping through every
public door:

| door | caller's object retained in `_withheld`? | reads of `tool` on it | row type stored |
|---|---|---|---|
| `bind_sink` → `withheld_json` | **no** | **0** | `dict` |
| `absorb` | **no** | **0** | `dict` |
| `record_withheld` | **no** | 0 | `dict` |

`absorb`'s `type(row) is not dict` branch rebuilds every non-plain row via `{k: row[k] for k in list(row)}`
and `_as_text` coerces every value, so nothing a caller owns survives into `_withheld`. The walrus at
`:969` is defence with nothing to defend against. **Close `G12` as "no subject" and stop carrying it** —
a fifth round of asking for a guard whose property is not falsifiable is a fifth round of the register
being wrong.

### 3.5 · Claim 5 — **REFUTED. The mechanism is the recorder, it is not a turn identity, and it runs**

**Falsifier stated first:** *if some mechanism other than `catalogue_outage`, and other than a turn
identity, answers `O_K` `True` while keeping the two-turn case `False`, the claim is false.*

Nine orderings, one `contextvars.copy_context()` each, arrangement verified by `inspect.getsource`
before the first measurement (`ARM DERIVES: True`, `WRITER PRESENT: True`).

| ordering | truth | **FLAG only (HEAD)** | **+ RECORDER** |
|---|---|---|---|
| O_A arm, record, read | True | `True` ✅ | `True` ✅ |
| O_B arm, record, drain, read | True | `True` ✅ | `True` ✅ |
| **O_K arm, record, drain, ARM AGAIN, read** | **True** | **`False`** 🔴 | **`True`** ✅ |
| **O_D turn A drains; turn B arms, reads** | **False** | `False` ✅ | **`False`** ✅ |
| O_J turn A drains; turn B reads with no arm | False | `True` 🔴 | `True` 🔴 |
| O_N arm, drain(empty), record, read | True | `True` ✅ | `True` ✅ |
| O_P record, arm, read | True | `True` ✅ | `True` ✅ |
| O_Q clean turn | False | `False` ✅ | `False` ✅ |
| **O_R arm, record, drain, arm, DRAIN AGAIN, read** | **True** | **`False`** 🔴 | **`True`** ✅ |
| | | **3 wrong of 9** | **1 wrong of 9** |

**`O_K` and `O_D` are split.** The delta's premise — that they are byte-identical — is true of the
ContextVars and false of the program: in `O_K` the drained row is in the recorder the reader holds; in
`O_D` turn B builds its own. That is the discriminator, and it is:

* **not `catalogue_outage`** — the patch does not touch the variable;
* **not a turn identity** — no id, epoch, token or counter is introduced;
* **already in scope at a live reader** — `voice_stream_service.py:242` constructs `_voice_advertised`
  and `:422` reads the outage, **in the same function**;
* **already prescribed by the file** — `instrument.py:531`, *"Ask the turn's RECORDER first."*

**And it is not a sketch.** Six lines: an optional `recorder=None` parameter on
`catalogue_outage_registered`, a scan of its retained catalogue rows before the flag, and
`voice_stream_response` passing the recorder it already holds.

```
FULL SUITE: 8 failed, 2266 passed, 2 skipped   — identical to baseline, 0 new failures
```

`test_THE_OUTAGE_FACT_SURVIVES_A_DRAIN` — the test whose turn-B row the delta says makes `O_K`
unsatisfiable — **stays green**, because the recorder answers turn B correctly for the same reason it
answers `O_K` correctly.

**I also found an eighth ordering.** `O_R` (arm, record, drain, arm, **drain again**, read) is wrong
today and was not in R18-A's table. The recorder fixes it too, which is what a mechanism at the right
altitude does.

**What survives:** `O_J` — a turn that records and never arms, leaking into a later read in the same
context — is wrong under both, and **that one is genuinely sink-borne.** The builder's sentence is
correct about `O_J` and false about the seventh ordering it was written to excuse. The honest record is
*"one residual, sink-borne, `O_J`"* — which is what the pre-delta comment said before `O_K` was
discovered, and the delta answered the discovery by widening the excuse instead of narrowing it.

### 3.6 · A finding I created and then measured — the probe modules are written into the live tree

Five tests in this file write probe modules **into the real `app/` tree** under fixed names —
`_lwprobe_writer.py` (into `agentruntime/`, `routers/`, `services/`), `_lwprobe_hoisted.py`,
`_lwprobe_broken.py`, `_lwprobe_d*_probe.py`, and the delta's new `_lwprobe_spelling.py` — each removed
in a `finally`.

A `finally` does not run when the process is killed. I killed one at a 10-minute cap and then spent
three measurements chasing a suite I believed was flaky. Reproduced deliberately:

| | result |
|---|---|
| artifact, 10 serial runs | **`135 passed` × 10** — deterministic |
| artifact + one leftover `app/routers/_lwprobe_writer.py` | **`1 failed`** — and it stays red until someone deletes the file by hand |
| after removal | `135 passed` |

The failure names the *gate*, not the leftover, so the reading is *"a terminal writer stopped binding
`withheld_tools`"* — a maintainer is sent to `stream_service.py` for a file the test suite dropped.
Worse, `_lwprobe_broken.py` is deliberately unparseable and the gate is deliberately **fail-closed**, so
that leftover reds the gate on *every* module.

**The sibling is in the next file and it states the reason** — `test_cp1_membrane.py:204`:

> *"Run over a temp file, so proving the gate red-able never mutates a tracked artifact."*

`tmp_path` is not available to these tests unchanged, because the gates sweep `app/` by design — but
`_TURN_SCOPE_ROOT` is a module constant and the sweep could be pointed at a temp package. This is
recorded rather than demanded: it cost me three wrong measurements, and it will cost the next person
the same.

---

## 4 · The bypass table — *for each guard, a way past it*

| guard | bypass | executed | reachability |
|---|---|---|---|
| terminal-write gate: `_names_the_column` | f-string with the column in a constant (**T11a**) | ✅ GREEN, control CAUGHT | **production** |
| " | f-string wrapping `segment_merge_sql(_C)` (**T11d**) | ✅ GREEN, control CAUGHT | **production — the live spelling** |
| " | double-quoted SQL identifiers (**T11c**) | ✅ GREEN, control CAUGHT | ordinary (Postgres-legal) |
| " | SQL as a default argument (**T11e**) | ✅ GREEN, control CAUGHT | ordinary |
| " | table **and** column interpolated (**T11b**) | ✅ GREEN, control CAUGHT | ordinary |
| the `>= 4` count NV | add a writer in a T11 spelling; the four survivors satisfy the count | ✅ T11a GREEN with a literal `None` bound | **production** |
| the `_binding_fns` name NV | same — the three named functions are untouched | ✅ | production |
| arm-order gate: the `Try` rule | **W4** — arm in a `try:` after a statement that raises | ✅ clean, control caught | **production-shaped, 4th round** |
| " | **W7** — arm in a `try` nested at depth 2 | ✅ clean, control caught | adversarial |
| " | **W12** — handler narrows via an alias; the function is not discovered at all | ✅ NOT-FOUND | adversarial |
| the unified `narrows` | add a third `_unconditional_calls` call site without the argument | ✅ D10/D15/D16 GREEN | **latent, one call site away** |
| the new spelling test | any earlier assertion in the gate fires → the oracle is satisfied and all four spellings report CAUGHT | ✅ **V2 demonstrated** | **production — the count NV fires on an ordinary refactor (§3.1)** |
| `catalogue_outage_registered` | `O_J` — a turn that records and never arms | ✅ wrong under both arrangements | latent; the arm-order gate forbids the shape statically |

---

## 5 · The red-ability table — **my denominator is 20**

**Derivation.** R18's builder published 11; two verifiers derived 48 and 87 over all eight modules.
Mine is scoped to what this delta can be held to: **the 20 defeatable decision points inside the 74
changed lines of scope A.** For context I also counted, by AST: **119** decision points across the ten
gate helpers, **243** assert statements and **332** assertion sub-clauses in the file. I report against
20 because a denominator drawn from the whole file grades rounds 1–18 again.

| # | defeat | suite | attributed to |
|---|---|---|---|
| D01 | reassembly → the pre-delta per-constant matcher | **RED** | `…sees_EVERY_SPELLING_OF_THE_SAME_WRITE` ✅ |
| D02 | drop the whitespace normalisation (`.split()`) | **RED** | the gate itself ✅ |
| D03 | `"withheld_tools" in _flat` → `True` | **RED** | the gate ✅ |
| D04 | drop the `INSERT INTO chat_messages` alternative | **RED** | the gate ✅ |
| D05 | drop the `UPDATE chat_messages` alternative | **RED** | `…EVERY_SPELLING…` ✅ |
| D06 | drop the `withheld_tools =` alternative | GREEN | — |
| D07 | drop the `withheld_tools=` alternative | GREEN | — |
| D08 | drop the write-qualification entirely | **RED** | the gate ✅ |
| D09 | drop the `segment_merge_sql` branch | GREEN | — |
| D10 | `_unconditional_calls` ignores `narrows` | GREEN | — |
| D11 | `narrows` not propagated through `With` | GREEN | — |
| D12 | `narrows` not propagated through `Try` | GREEN | — |
| D13 | `_narrows` loses the `_NARROWING_CALLS` operand | **RED** | `…ARM_IN_A_TRY_WHOSE_HANDLER_NARROWS…` (the **R17** rule) |
| D14 | `_narrows` loses the `reaching` operand — **the W5b regression** | GREEN | — |
| D15 | delegate site stops passing `_narrows` | GREEN | — |
| D16 | arm site stops passing `_narrows` | GREEN | — |
| D17 | the `Try` rule stops checking handlers | **RED** | same **R17** test |
| D18 | the `Try` rule stops checking `finalbody` (closes W10) | GREEN | — |
| D19 | the new test's oracle widened to a bare `AssertionError` | GREEN | — |
| D20 | the new test loses its `two spaces` case | GREEN | — |

**8 / 20 = 40%.** Partitioned by what the delta claims:

| the delta's three fixes in scope A | red-ability |
|---|---|
| the SQL reassembly | **6 / 9** |
| the `narrows` unification (**the W5b fix**) | **0 / 7** — D13/D17 red the *pre-existing* R17 rule |
| the new spelling test's own integrity | **0 / 2** |

Baseline verified byte-identical to the frozen blob before the sweep and after it (`79e56d814274`).

---

## 6 · The sibling table

| the delta fixed | the sibling it did not | executed | status |
|---|---|---|---|
| `_names_the_column` reassembles all string **Constants** | the `segment_merge_sql` branch still matches only a **literal** argument (T11d) | ✅ BLIND, control CAUGHT | 🔴 **NEW** |
| `_unconditional_calls` takes `narrows` | `_narrowing_helpers` and `_narrowing_helpers_multi` are still **two closures over one relation**, 26 lines apart | read + executed (both live) | 🔶 carried |
| one predicate, two call sites | the parameter is **optional**, so the coupling is convention (D10/D15/D16 GREEN) | ✅ | 🔴 **NEW** |
| a new test for the spelling class | it is the **third** test using `match="withheld_tools"`, an oracle every assertion in the gate satisfies; the correct pattern (`match="could not be parsed"`) is **64 lines above** at `:3253` | ✅ V2 | 🔴 **NEW — the family is `:3183`, `:3238`, `:3317`** |
| the docstring names five spellings | the dict executes **four** — `%` is absent | ✅ (`%` verified caught independently) | 🔶 record drift |
| the test loops `for label, sql in …` | `label` is **unused**, so a regression names no spelling | read | 🔶 |
| `W5b` closed through helper hops | **W4** and **W7** untouched, 4th and 3rd round | ✅ both clean | 🔴 carried |
| probe modules removed in `finally` | a killed process leaves them; **five** tests write into the live `app/` tree while `test_cp1_membrane.py:204` uses `tmp_path` **and says why** | ✅ reproduced | 🔴 **NEW** |
| `catalogue_outage`'s comment rewritten (`:311-348`) | `:425-431` and `:531`-vs-`:542` — the contradiction R18-A reported — **untouched**, and §3.5 shows it resolves to the wrong side | read + executed | 🔴 carried, 5th round |

---

## 7 · Reachability verdict on every finding

| finding | reachability | basis |
|---|---|---|
| **A19-1** T11d — f-string + `segment_merge_sql(constant)` | **PRODUCTION** | it is the live spelling at `stream_service.py:6297/6382/7398`; one token keeps it visible |
| **A19-1** T11a/b — f-string with the column interpolated | **PRODUCTION** | `app/agentruntime/` is in the sweep and is CP-2's landing zone; a new writer there is uncovered |
| **A19-1** T11c — double-quoted identifiers | ordinary | Postgres-legal; invisible in review |
| **A19-1** T11e — SQL as a default argument | ordinary | a common way to make SQL overridable in tests |
| **A19-2** the new test's oracle is satisfied by any assertion in the gate | **PRODUCTION** | the count NV fires on the one-token refactor in §3.1; on that day the spelling test goes green and stops testing spellings |
| **A19-3** the W5b fix is unguarded (0/7) | **certain** — it is the state of the tree | D10/D14/D15/D16 GREEN; W5b and W5c regress at `135 passed` |
| **A19-3b** the coupling is a default argument | latent | one added call site |
| **A19-4** W4 clean | **production-shaped**, 4th round | any `try` whose first statement can raise |
| **A19-4b** W7 clean | adversarial, 3rd round | the comment is false either way |
| **A19-5** the ordering claim is false | **PRODUCTION** | `voice_stream_response` reads the outage at `:422` with its recorder in scope from `:242`; `O_K`/`O_R` are wrong there today |
| **A19-6** leftover probe modules poison the tree | **certain** — I caused it | any Ctrl-C, CI timeout or OOM during five named tests |
| **A19-7** `G01`/`_source` unguarded | adversarial | needs a two-faced argument; `chunk` is unbounded by contract |
| **A19-8** `G12` has no subject | n/a | close it |
| **A19-9** `%` named and not executed | none (verified caught) | record drift only |
| **A19-10** the `segment_merge_sql` branch is deletable green | latent | redundant today, undocumented as such |
| **A19-11** the `finalbody` arm is unguarded (W10) | latent | W10 closes with no test |
| **A19-12** the `Try` rule's FP namespace widened 5 → 13 | **inert today** | 0 of 13 names is defined twice; constructible |

---

## 8 · Executed vs argued — **the axis R18-A proposed, second measurement**

| # | load-bearing claim in scope A | established by | correct? |
|---|---|---|---|
| C1 | *"the SQL is assembled … which still keeps `db/migrate.py` out"* | **EXECUTED** (gate green; I confirmed the mechanism: in sweep, not in binds) | **TRUE** ✅ |
| C2 | *"…and discards no spelling of a write"* | **ARGUED** — a universal negative with no probe behind it | **FALSE** — 5 blind spots 🔴 |
| C3 | *"all five previously-blinded spellings caught again"* | **EXECUTED** for 4, **ARGUED** for `%` | **TRUE** ✅ (I executed the 5th) |
| C4 | *"One predicate now, passed to both"* closes W5b | **ARGUED** — no assertion over it | **mechanism TRUE, closure UNESTABLISHED** 🔶 |
| C5 | *"no assignment of the flag can split them … unaddressable by this variable"* | **ARGUED** | **FALSE** — refuted by a patch that runs 🔴 |
| C6 | *"2266 tests pass"* | **EXECUTED** | **TRUE** ✅ |

**Ratio 3 : 3.** **Executed claims correct 3 / 3. Argued claims correct 0 / 3.**

R18-A measured **1 : 1** with the identical polarity. Two rounds, six claims, and the split is clean:
**every claim this builder executed is true, and every claim this builder argued is false or
unestablished.** The signal is not the builder's care — the executed claims are careful. It is that the
argued claims are, without exception, the ones where the conclusion was the convenient one: *"discards no
spelling"* excuses not probing, *"one predicate"* excuses not writing a test, *"unaddressable"* excuses
not fixing the ordering.

**This is now strong enough to be a rule rather than an observation, and it is cheap to enforce:** a
claim in a commit message that no execution stands behind is a claim that has been 0 for 3 across two
rounds. Requiring one line of evidence per load-bearing sentence would have caught C2, C4 and C5 before
either verifier was deployed.

---

## 9 · Convergence

**Raw.** Six load-bearing claims in scope A. **Closed: 3** (C1, C3, C6). **Refuted: 2** (C2, C5).
**Unestablished: 1** (C4).

**Findings introduced by this delta: 3** — A19-2 (a third instance of the weak-oracle family), A19-3
(the W5b fix with 0 of 7 of its own decision points guarded), A19-12 (the FP namespace widened, inert).
A19-6 is pre-existing and surfaced by my own error, not introduced here.

**Findings closed by this delta: 3** — the five blinded spellings (T10a/b/c/h/j), W5b, W10b. Plus one
closed by *this verdict* rather than by the delta: **`G12` has no subject.**

**Per changed line: 3 introduced over 74 = 4.05 / 100.** R18-A measured **0.74 / 100** over 404.

**And that comparison is the point.** The raw introduced count is **3 in R18 and 3 in R19**. The
normalised rate moved 5.5× because the denominator shrank 5.5×. R18-A recommended steering by raw count
and adding a second axis; this round is the confirmation: **normalising by changed lines rewards a large
delta and punishes a small one for producing the same number of defects.** The stable signal is the raw
count, and it has not moved.

The second axis I would add is §8's, because it did move and it is actionable: **executed 3/3, argued
0/3, twice running.**

**Carried into R20, in priority order:**

1. **Fix the ordering with the recorder** (§3.5). It is six lines, the full suite stays at baseline, it
   closes `O_K` and `O_R`, and the file has been telling you to do it at `:531` for four rounds. Then
   the honest residual is `O_J` alone, and it is genuinely sink-borne.
2. **Give the W5b fix a test** (§3.3). Six of the seven decision points behind it are deletable green.
   Whatever else happens, `_unconditional_calls`'s `narrows` should stop being optional.
3. **Write R16-A's W4 rule** — *accept a `try` body's arm only when no statement precedes it in the
   chain*. It closes W4 and W7 together and is now three rounds old.
4. **Resolve the SQL matcher above the literal.** Five spellings is not a list to extend; the assembled
   text should resolve `FormattedValue` through module constants the way `global_sql_names` already
   resolves them for the executor's arguments. T11d is the live spelling.
5. **Fix the three weak oracles** (`:3183`, `:3238`, `:3317`) to name the assertion they mean, as
   `:3253` already does.
6. **Adopt `G01`'s `_source` guard** (§3.4) and **close `G12` as "no subject"**.
7. **Point the probe sweeps at a temp package** (§3.6), or accept that an interrupted run leaves the
   tree red with a message that blames the wrong file.

---

`git rev-parse HEAD` at finish: **`5b531e22ae93f52cc45f55741b3016b76d754691`** — unmoved.
`git status --porcelain -- services/chat-service`: **empty**. No tracked file was modified except this
verdict. No `git checkout` was used.
