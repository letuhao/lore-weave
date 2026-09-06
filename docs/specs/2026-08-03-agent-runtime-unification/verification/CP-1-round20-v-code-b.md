# CP-1 · round 20 · V-CODE · **Verifier B — the membrane**

**Artifact:** `b73e086caeac55e6c43332c630411ad84ac29bd4`
`git rev-parse HEAD` **at start:** `b73e086caeac55e6c43332c630411ad84ac29bd4`
`git rev-parse HEAD` **at finish:** `b73e086caeac55e6c43332c630411ad84ac29bd4` — **unmoved.**

**Graded delta:** `35cf987ce` against `5b531e22a`.
**Scope:** `services/chat-service/app/agentruntime/`, `scripts/agentruntime-membrane-gate.py`,
`services/chat-service/tests/test_cp1_membrane.py`.

**Method.** Every claim below was **executed**. Two independent full-layout scratch replicas
(`services/`, `scripts/`, `contracts/`, `.github/workflows/`) so no repo-path-dependent test
deselects; both replicas reproduce the real tree's baseline **`134 passed`** and gate exit 0.
Every injection is an **anchored source edit** that asserts its anchor count *before* writing and
asserts the injected text is *present in the file* afterwards — a mismatched anchor aborts rather
than producing an inert run. Restoration is from **my own pristine snapshot**
(`scratchpad/b20pristine/`), never `git checkout`. The real tree was never edited:
`git status --porcelain services/chat-service scripts contracts docs/plans` is **empty**, and the
real tree reproduces `134 passed` + gate exit 0 at finish.

**The delta in my scope is 14 lines, test-only.** `git diff 5b531e22a 35cf987ce --stat --
app/agentruntime/ scripts/agentruntime-membrane-gate.py` is **empty**. `test_cp1_membrane.py` is
**+14 / −0**, all of it inside one existing test body. **Third consecutive round with zero source
lines changed in `app/agentruntime/`.**

---

# ▶ ITEM ZERO — the termination question

Answered first, against evidence I gathered myself, and written for the PO.

## 0.1 — Is this loop converging? **No, and I can now show exactly which part was never measurable.**

| measurement | series | direction |
|---|---|---|
| `introduced`, raw, my scope | `2,1,2,1,3,2,4,3,2,2,2,` **`2`** | **none, twelve rounds** |
| closure of the previous verdict's findings | `14, 10, 8, 27, 54, 25–37, 22–28, 36–41,` **`23–27`** | **none — it tracks what the delta attempted** |
| the denominator each verifier derived | `11 · 48 · 87 · 92 ·` **`84`** | **rose three times, then fell — see below** |
| the **mechanical `raise` census** | `68 sites` ×3 · silent set **13, 13, 13, identical members** | ✅ **converged** |

Two things carry the answer, and they point opposite ways.

**The defect rate has no trend and the closure figure is not a process measurement.** This round's
delta changed **14 lines** in my scope and closed **3 of 13**; last round's changed 82 and closed
4 of 11. R16-B and R18-B said closure tracks delta structure; a third data point at a fifth of the
line count says it again. `introduced` sat at 2 for the twelfth round. Neither is converging and
neither can converge, because both are functions of how hard the verifier looked — which the
denominator series proves directly: 48 → 87 → 92, each verifier larger than the last.

**And this round the denominator went DOWN, to 84, for a reason that matters.** The 87/92
divergence was never in the codebase. Both predecessors derived the `raise` half **by AST** and the
structural half **by hand**. I re-derived both mechanically — AST for `raise`, and an AST rule for
the structural half (§3) — and got a *smaller*, *reproducible* number. **Every unit of divergence in
the denominator series lived in the hand-picked half.** The half that was mechanised converged
perfectly on the first attempt and has now converged three times.

**So: no evidence of convergence in defect discovery. Decisive evidence of convergence in the one
measurement that was mechanised.** That is the whole finding of item zero.

## 0.2 — What would close CP-1?

**Not** *"three consecutive rounds at `introduced == 0`"*. That criterion is unfalsifiable here:
`introduced` is a function of verifier effort, the denominator series proves each verifier looks
harder than the last, and a builder can reach it by the delta getting smaller. This round's delta
was 14 lines and still produced 2.

**The criterion that is checkable, reachable this run, and not satisfiable by the builder writing
more tests about the builder's own fixes:**

> **The census is a CI script, the silent set is a checked-in allowlist with one graded reason per
> row, and the gate fails on any diff.**

Concretely — and I ran exactly this, so the cost is known, not estimated:

1. AST-enumerate every `raise` in `app/agentruntime/` (**68**, three independent derivations agree)
   and every defensive copy / materialisation — `dict|list|tuple|set|frozenset|MappingProxyType`
   over a single Name/Attribute/Subscript/comprehension — plus every `assert` (**16**).
2. Neuter each of the **84** one at a time; run `tests/test_cp1_membrane.py` after each.
3. Fail if the SILENT set differs from `agentruntime-SILENT.txt`.

**Cost: 84 suite runs, ~5 minutes wall clock**, measured — that is the two background jobs in this
verdict. It fits a CI job today.

Why this and not more rounds:

* **A new silent site becomes a CI failure at the commit that creates it.** No verifier round needed.
* **It makes the register mechanical.** *"A finding is closed"* becomes *"this named site moved
  SILENT → RED"*, which the gate proves. **The seven-times-repeated failure of this run — a fix
  landing at the site a verifier pointed AT rather than the one it named — is structurally
  impossible against a named-site diff.** This round's delta is the proof: the builder finally fixed
  `surface.py:72` and my census shows it flipping SILENT → RED **automatically**, with no argument.
* **It is not self-satisfiable.** A test about the builder's own fix that does not move a named site
  does not move the file.
* **It converts CP-1's residue from a paragraph into 20 enumerated rows** (§3), each of which is
  either fixed or allowlisted with a reason.

**CP-1 closes when every one of the 84 sites is RED or allowlisted with a graded reason, and the
script that says so runs in CI.** Today: **64 RED, 20 silent, 0 allowlisted, 0 in CI.**

## 0.3 — Is more V-CODE the right axis? **No — and the prompt's premise for asking is false.**

> R20's prompt, line 27: *"Nothing in CP-0 or CP-1 has ever been through **V-LIVE**."*

**That is false, and the counter-evidence is eleven files in the same directory as the prompt.**
`CP-0-v-live.md` plus `-round2` … `-round9` (**nine** verdicts) and **`CP-1-v-live.md`** (artifact
`083ed4c98`) and **`CP-1-v-live-round2.md`** (artifact `7f50949dc`), all dated 2026-08-04. The true
statement — and it is worse than the false one — is:

> **CP-1's live axis ran twice, on 2026-08-04, and both rounds returned `CANNOT DETERMINE` on all
> four items. It has not run since, and none of the eleven V-CODE deltas has been through it.**

And the reason those two rounds could not determine anything is the whole answer. From
`CP-1-v-live-round2.md` §1: *"the turn cannot be placed on the new surface."* I verified the cause
directly, repo-wide and by AST:

```
importers of `agentruntime` outside the package : NONE
  the only references are scripts/agentruntime-membrane-gate.py
  and .github/workflows/lint-foundation.yml
```

**The package has zero production callers.** Eleven rounds of V-CODE have graded a membrane that
has never been in the path of a chat turn. My own reachability column this round reads
**0 production-reachable**; R19-B's read 1 of 13; every other finding across both rounds is
guard-only, structural, adversarial or process.

**So the largest unmeasured risk is not in the source I am reading — and it is not visible to
V-LIVE either, today, because there is nothing live to look at.** The honest statement is:

> **CP-1 cannot be closed by V-CODE, and it cannot be closed by V-LIVE, because the artifact has no
> live surface. What V-CODE can still deliver is the mechanised census — a finite, checkable,
> non-self-satisfiable criterion. Everything else at this checkpoint is waiting on CP-2 wiring the
> import.**

Two facts sharpen that: `db/migrate.py:367-368` already ships
`runtime_variant … CHECK (… IN ('legacy','agentruntime'))`, and `instrument.py:100` already defines
`RUNTIME_AGENTRUNTIME`. **The socket is built. The plug is one import.** Eleven rounds have been
spent hardening a door nobody has walked through, and the twelfth would be too.

**Recommendation to the PO: ship the census gate, close CP-1 against it, and spend the next round's
budget on CP-2's first import — because that is the commit that makes V-LIVE able to answer
anything at all.**

---

## Verdicts

| # | claim | verdict |
|---|---|---|
| 1 | `rows_of`'s `dict(r)` now has its own assertion; it reds for the reason it names; the `validate_document` half was not weakened | ✅ **B19-1 CLOSED, and correctly this time.** Neutering `surface.py:72` → **`1 failed`**, the new test. Neutering `manifest.py:448` → **`2 failed`**, and the new test *and* the pre-existing test each red **alone** — the second half was not weakened. My AST census independently flips `surface.py:72` from SILENT to **RED**. 🟡 Two residuals: the copy is **shallow**, and every one of the four exported doors hands back the source document's own `members` **list** (**B20-1**, §2b); and the careful message the author wrote is **never printed** — a bare identity assert fires first (**B20-6**) |
| 2 | B18-8 and B18-11, open and unfixed for three rounds, are back on the board — re-measure and state reachability | 🔴 **BOTH STILL OPEN, both re-measured.** **B18-8**: all four sites silent — `contract.py:220-222` removed → `134 passed`; downgraded to `isinstance` → `134 passed`; `:254-257` removed → `134 passed`; downgraded → `134 passed`. The pins **work** (control refuses a `str` subclass key) — they have **no test**. *Coverage gap, adversarial-only.* **B18-11**: `nfc()`'s refuted docstring is **verbatim** at `canon.py:42`, and AST says `canon` has **zero attribute uses anywhere in the package** while `contract.py:21` and `manifest.py:27` both import it — **two dead imports and a dead module**, sharper than recorded |
| 3 | B18-10 — a fifth exported door, six rounds old. If the CP-2 scoping is still honest, say what would make it dishonest | 🔴 **UNCHANGED, SIXTH ROUND.** An exported `summarise_rows` reading `r['id']`/`r['kind']` directly: **`134 passed`**, **gate exit 0**. **Scoping still honest** — zero importers, verified repo-wide. **What would make it dishonest:** the first commit that imports `app.agentruntime` from anything in `app/` — at that instant every one of the run's guard-only findings becomes production-reachable *retroactively*, with no new defect and no round to catch it. That commit is CP-2.1 |
| 4 | `surface.py:305` (`OrderBy`'s key-pair shape) and `_ID`'s missing length bound | 🔴 **BOTH OPEN, both executed.** `:305` removed → **`134 passed`**; my AST census lists it in the silent 13. Control refuses all three vehicles (list pair, self-deciding tuple subclass, 3-tuple) — so the clause is **load-bearing and untested**, the one remaining member of the stage-parameter family the delta guarded four of. `_ID`: a **300-character** id passes `admit()` → `build()` → a written row **in the control** |
| 5 | the record: verify every claim in R19's RUNSTATE block against the verdicts, including the corrected `Open, carried` list | 🔴 **THE CORRECTED LIST IS WRONG IN THE OTHER DIRECTION — B20-4.** The two findings that were dropped are back ✅ — and **four more were dropped in the same edit**: **B18-1**, **B18-2**, **B18-9** and **B19-5**, plus A's contradictory-comments item. I re-measured the first three and **all three are open**. Fourth consecutive round of B17-8. Everything else in the block checks out, with **one number misreported (B20-5)**: the `introduced` series `2,1,2,1,3,2,4,3,2,2,2` is **my scope only** — R19-A measured **3**, and says so — and R20's prompt inherits it as *the run's* number in the sentence that frames the termination question |
| 6 | convergence, item zero, one new falsifiable prediction | **Closure 3 clean of 13 = 23%; 27% with the partial at half** — `14, 10, 8, 27, 54, 25–37, 22–28, 36–41,` **`23–27`**. Introduced **2** code/guard on **14** changed lines (**4** with the record). **Executed-vs-argued in my scope: 3 : 3 — executed 3/3 correct, argued 0/3 correct.** Predictions §6c. Item zero above |

**Overall: FAIL** — on **B20-4**, the register dropping four open findings in the very edit that
restored the two it dropped last round, for the **fourth** consecutive round; and on **B20-1**, the
`dict(r)` fix being **shallow** at all four exported doors so that the exact write-through its own
assertion message describes — *"every narrowing stage then writes through into the document the
assembler was given"* — still happens, through `members`, at the site the finding named, with the
suite at `134 passed`.

**And the best thing in this delta belongs first, because it is the one that generalises.** The
builder fixed B19-1 **at the site the verifier named**, after seven rounds of fixing siblings. I did
not have to take that on trust and neither will the next reader: my AST census flipped
`surface.py:72` from SILENT to RED **mechanically**, with no argument and no anchor to maintain.
That is the closure criterion of §0.2 working on its first real case, and it is why I am
recommending it rather than a twelfth round.

---

## Falsifiers, stated before the search

| claim | what would have falsified it |
|---|---|
| 1 | the new assertion staying GREEN when `surface.py:72` is neutered; or the `validate_document` half no longer reddening alone |
| 2 | any of B18-8's four sites reddening the suite; a non-comment `canon.<attr>` use anywhere in the package |
| 3 | the injected fifth door being refused by suite or gate; any importer of `agentruntime` outside the package |
| 4 | `surface.py:305` reddening the suite; `_ID` refusing a 300-character id |
| 5 | every open finding in the verdicts appearing in RUNSTATE's `Open, carried` |
| 6 | the raise census returning a different site count or a different silent set from the two predecessors |
| item zero | a production importer of `agentruntime`; a CP-1 V-LIVE verdict that determined anything |

---

## 1 — the `dict(r)` guard, the site it names, and the half it must not weaken

Each mutation applied **alone**, anchor verified present, full suite after.

| mutation | suite | which tests |
|---|---|---|
| **`surface.py:72` `dict(r)` → `r`** (the site the finding named) | 🔴 **`1 failed`** | `…THE_ROW_COPY_IS_WHAT_LEAVES_THE_VALIDATOR` |
| `manifest.py:448` `[dict(r) for r in rows]` → `rows` (the sibling) | 🔴 **`2 failed`** | the new test **and** `…ROWS_OWN_GET_CANNOT_SMUGGLE…` |
| …the pre-existing test **alone** on that mutation | 🔴 `1 failed, 133 deselected` | not weakened ✅ |
| …the **new** test **alone** on that mutation | 🔴 `1 failed, 133 deselected` | both halves live ✅ |
| both copies removed | 🔴 `2 failed` | — |
| control | `134 passed`, gate exit 0 | — |

**B19-1 is closed at the named site.** R19-B's `P19-B1` first clause — *"R20's delta will close
B19-1 at the site I named"* — **CONFIRMED**.

### 1a · 🔴 **B20-1 — the copy is SHALLOW, and `members` is a list**

`dict(r)` copies the mapping and shares every value. Rows carry `members`, which the writer emits as
a **list**. Measured at all four exported doors, control tree, no injection:

```
                     row is a copy   members SHARED with source   source after caller's append
  rows_of            True            True                          ['book_list', 'INJECTED']
  validate_document  True            True                          ['book_list', 'INJECTED']
  declarations       True            True                          ['book_list', 'INJECTED']
  discover           True            True                          ['book_list', 'INJECTED']
```

And the corruption is consequential, not theoretical — feeding the mutated document back through
the validator refuses **the source document**:

```
ContractViolation: sk.<memory>:declarations[1].members[1]: not a declaration id: 'INJECTED'.
```

The new test asserts `rows[0]["id"] = "MUTATED"` — a **top-level rebinding**, which `dict(r)`
already stopped. It does not assert the one part of a row that has mutable substructure. The
finding's own words, in the assertion message the builder wrote eight lines above:
*"every narrowing stage then **writes through into the document** the assembler was given"* — that
is precisely what `members` still does. `members` is M5's foreign-key list and every `AllowList` /
`DenyList` membership decision downstream of it.

**Reachability: guard-only today (no in-package consumer writes to a row); production-reachable at
CP-2**, in the same bucket the delta just accepted for B19-1. **Introduced by the graded delta:**
the *behaviour* is pre-existing; the **false completeness is new** — the delta and both records now
say `dict(r)` is guarded, and for the half that matters it is not. I count it introduced on the
guard axis and say plainly that the behaviour predates it.

### 1b · 🟡 **B20-6 — the message the author wrote is never printed**

Under the one mutation the finding names, the failure the reader sees is:

```
>       assert rows[0] is not good["declarations"][0]
E       AssertionError: assert {'admitted_against': '1.0.0', …} is not {'admitted_against': '1.0.0', …}
```

The bare identity assert short-circuits the annotated one below it, so
*"`rows_of` handed the consumer the caller's own row object…"* is unreachable for every natural
mutation (`copy.copy`, `r.copy()`, `{**r}` all keep distinct identity). Two 200-character dict
reprs, no sentence. This is **B19-5's family** — the file's own rule at `:1667`, *"Two mechanisms,
two assertions"* — one round later, in the fix for the finding B19-5 sat beside. Put the message on
the identity assert. **Guard-only. Introduced: YES.**

---

## 2 — the findings the register carries, re-measured

| finding | age | measurement on this artifact | verdict |
|---|---|---|---|
| **B18-8** key pin removed | 3rd rd | `134 passed` | 🔴 silent |
| **B18-8** key pin → `isinstance` | 3rd rd | `134 passed` | 🔴 silent |
| **B18-8** members pin removed | 3rd rd | `134 passed` | 🔴 silent |
| **B18-8** members pin → `isinstance` | 3rd rd | `134 passed` | 🔴 silent |
| **B18-11** `nfc()` docstring | 3rd rd | verbatim unchanged at `canon.py:42` | 🔴 open |
| **B18-11** `canon` callers | 3rd rd | **0 attribute uses**, 2 dead imports (AST) | 🔴 open, sharper |
| **B18-10** fifth exported door | **6th rd** | `134 passed`, gate exit 0 | 🔴 open |
| **B19-4** `surface.py:305` | 2nd rd | `134 passed`; control refuses all 3 vehicles | 🔴 silent |
| **B19-12** `_ID` length | 2nd rd | 300-char id written end-to-end in the control | 🔴 open |

### 2a · B18-8 is a coverage gap, not a live bypass — **and my first probe said otherwise**

My first vehicle set `bad[S("id")] = "x"` on a dict that already had `"id"`. Python keeps the
original key object on an equal-hash assignment, so **the subclass key was never installed** and the
probe would have reported a bypass that does not exist. Rebuilt with the subclass key inserted
first:

```
  stored key types      : ['S', 'str', 'str', 'str', 'str', 'str', 'str']
  CONTROL subclass KEY  : refused -> ContractViolation: has a non-string key 'id'
  CONTROL subclass MEMBER: refused -> ContractViolation: declarations[1].members: contains 'x'
```

**The pins hold. They have no test.** Recorded here because a verifier's conflated vehicle is the
same defect as a builder's, and this is the third round running in which one of us has made it.

### 2b · B18-11 is worse than the register says

```
  contract.py   imports canon at [21]   canon.<attr> uses: []
  manifest.py   imports canon at [27]   canon.<attr> uses: []
  (all 8 modules)                       canon.<attr> uses: []
```

Not *"uncalled and unexported"* — **uncalled, unexported, and imported twice by modules that never
touch it**, while its docstring at `:42` still states the harm a verifier refuted by execution three
rounds ago. The membrane gate counts modules; it does not ask whether one has a reader.

### 2c · 🔴 **B20-3 — the defeated construct is still defined, and it still works**

`surface.py:407` — `_KIND_SET = frozenset(STAGE_KINDS)`. AST across the package and the suite: its
**only** non-comment occurrence is its own definition. Three separate comments
(`surface.py:116`, `:420`, and the suite at `:1966`/`:1994`) exist solely to explain why it was
replaced. Executed:

```
  type(forged) in _KIND_SET        -> True    <- the defeated comparison, still importable
  any(type(forged) is k for k …)   -> False   <- the live one
  validate_pipeline([forged])      -> REFUSED
```

A metaclass forgery passes the dead constant and fails the live check. Neutering the constant leaves
`134 passed` — it is in my silent set. This is the module's own recorded lesson
(`contract.py:108-114`: *"a field kept because removing it feels lossy is a field the next reader
will trust"*) applied to everything except itself. **Adversarial / latent; the cost is the next edit
that reaches for the name. Introduced: no.**

---

## 3 — the census, mechanised end to end, and my denominator

**I re-derived it from scratch and did not read the predecessors' lists first.**

### 3a · layer 1 — every `raise`, by AST. **Third derivation, third agreement.**

68 `raise` statements across the eight modules (`admission` 4, `canon` 4, `contract` 18,
`manifest` 17, `surface` 25, `__init__`/`ambient`/`narrowing` 0). Each replaced with `pass` at its
own indent, one at a time, full suite after each; injection asserted present on disk before the run.

### **55 red-able · 13 SILENT · 0 broken**

```
canon.py:60    canon.py:71    canon.py:84
contract.py:221  contract.py:255  contract.py:381
manifest.py:245  manifest.py:297  manifest.py:310  manifest.py:408  manifest.py:428
surface.py:305   surface.py:389
```

**This is R19-B's silent raise set, member for member, all thirteen.** R18-B derived the same 68
sites. **Three independent verifiers, three identical answers.** This number is no longer a
measurement of who looked hardest — it is a property of the artifact, and it belongs in CI.

### 3b · layer 2 — the structural half, **also by AST**, and this is where the divergence lived

R18-B (19) and R19-B (24) hand-picked their structural sets, which is why the denominators diverged
while the silent sets agreed. I replaced the hand-picking with a rule:

> every call `dict(X)` / `list(X)` / `tuple(X)` / `set(X)` / `frozenset(X)` / `MappingProxyType(X)`
> with exactly one positional argument that is a Name / Attribute / Subscript / comprehension —
> i.e. every defensive copy and materialisation — neutered by replacing the call with its argument;
> plus every `assert`.

**16 sites. 9 red-able. 7 silent.**

| site | verdict | triage |
|---|---|---|
| `manifest.py:135` `list(d.members)` | RED (2) | ✅ |
| `manifest.py:259` `set(origin)` | RED (4) | ✅ |
| `manifest.py:376` `set(doc)` | RED (21) | ✅ |
| **`manifest.py:448` `dict(r)`** | RED (2) | ✅ |
| `narrowing.py:77` `list(k)` | RED (1) | ✅ |
| **`surface.py:72` `dict(r)`** | **RED (1)** | ✅ **the delta's fix, seen mechanically** |
| `surface.py:524` `list(pipeline)` | RED (1) | ✅ |
| `surface.py:547` `tuple(e.as_record() …)` | RED (14) | ✅ |
| `surface.py:575` `tuple(sorted(…))` | RED (2) | ✅ |
| `manifest.py:220` `list(_prev_rows)` | 🟢 SILENT | **redundant, measured** — the `type(_prev_rows) is not list` pin two lines above refuses the two-faced subclass first |
| `manifest.py:409` `list(rows)` | 🟢 SILENT | redundant behind `type(rows) is not list` |
| `surface.py:595` `list(rows)` | 🟢 SILENT | redundant behind `_is_exactly(rows, list)` |
| `surface.py:329` `list(rows)` in `OrderBy.sort` | 🟡 SILENT | redundant in-package; `OrderBy` is exported, so a direct caller's list is sorted in place |
| `contract.py:296` `tuple(row["members"])` | 🟡 SILENT | cosmetic — the `Declaration` is discarded immediately |
| `surface.py:427` `tuple(k.__name__ …)` | 🟡 SILENT | cosmetic — message formatting only |
| **`surface.py:407` `frozenset(STAGE_KINDS)`** | 🔴 SILENT | **B20-3 — dead, and it is the defeated construct** |

`manifest.py:220` is the finding I did **not** get to keep: I expected the fourth door's
materialisation to be a live TOCTOU guard, drove a two-faced `list` subclass at `build(previous=)`,
and the exact-type pin refused it before the materialisation was reached. **Redundant, measured** —
recorded because the alternative was a finding built on an unexercised vehicle.

### **My denominator: 84 · red-able 64 (76%) · silent 20**

| | count |
|---|---|
| `raise` statements (AST, 8 modules) | 68 |
| structural copies / materialisations / asserts (AST rule) | 16 |
| **denominator** | **84** |
| red-able | **64 — 76%** |
| silent | **20** |

**The denominator fell for the first time in the series** (48 → 87 → 92 → **84**), and the ratio
fell with it (72% → 79% → 76%). Both are *good* news and I want to be explicit about why: the
number is smaller because it is **derived by a rule a script can re-run**, not because less was
checked. The previous two were larger because their structural halves were mined by hand, and a
hand-mined denominator grows with effort forever. **This one does not.**

---

## 4 — the record

### 4a · ✅ what R19's RUNSTATE block got right — verified claim by claim against the verdicts

| claim in the block | source | verdict |
|---|---|---|
| *"Prompt committed first, two V-CODE on frozen `5b531e22a`"* | `git log` | ✅ the prompt file's only commit **is** `5b531e22a` |
| the `O_K` table: flag-only **3/9** wrong; +recorder **1/9**, at baseline | R19-A `:73-74` | ✅ verbatim |
| *"Both predictions HELD"* | R19-B §1a/§1b | ✅ |
| *"R18-B's own published control was wrong"*; `salience`→1, `relevance`/`lane`/`tier`→2, `cost`→4 | R19-B §1a | ✅ **and independently re-executed by me**: `relevance` → `2 failed`, `cost` → `4 failed` |
| *"the `rows_of` half reds when its copy is removed"* | the delta | ✅ **executed**: `1 failed` |
| *"the sentence my two records finally agreed on is false"* | R19-B §5b | ✅ recorded plainly, in the builder's own words |
| *"B18-8 and B18-11 … missing from the carried list"* | R19-B §5c | ✅ recorded, and both are back |
| the `withheld_tools` oracle matches every assertion | R19-A `D19` | ✅ |
| `G01`/`G12` dropped from the carried list | R19-A §3.4 | ✅ **correctly** — A constructed the `G01` guard and graded `G12` *"no subject, close it"* |
| executed vs argued **7 : 6**, executed 7/7, argued 0/6 | A 3+3, B 4+3 | ✅ arithmetic correct |
| denominators *"me 11 · R17-B 48 · R18-B 87 · R19-B 92"* | the verdicts | ✅ — and **B19-11 is closed**: A's `13/24` closure figure is no longer filed beside B's census |
| *"two independent mechanical censuses now agree on the silent set"* | R18-B/R19-B | ✅ — **and it is three now** |
| *"2267 tests pass"* | — | ✅ arithmetic: `2267 tests collected` in `services/chat-service` |

That is a genuinely good audit result. Eleven of thirteen claims check out, including every one that
indicts the builder. **B18-3 stays closed and B19-11 closes.**

### 4b · 🔴 **B20-4 — the corrected list dropped four more, and three of them are the block's own subjects**

R18's `Open, carried` → R19's, diffed:

| carried in R18 | in R19's list? | status I measured |
|---|---|---|
| **B18-1** — the subset assertion contributes 0 of 2 | ❌ **DROPPED** | 🔴 **OPEN** |
| **B18-2** — the eleventh guard reds on CP-2's first operation | ❌ **DROPPED** | 🔴 **OPEN** |
| **B18-9** — `rows_of`'s document-stamp gap | ❌ **DROPPED** | 🔴 **OPEN** |
| the two contradictory comments in `catalogue_outage_registered` | ❌ **DROPPED** | 🔴 open per **R19-A `:471`**, *"untouched … carried, 5th round"* |
| **B19-5** — one test, three clauses, one indistinguishable message | ❌ never added | 🔴 open (test byte-identical) |
| B18-10 | ✅ | open, 6th round |
| B18-8, B18-11 | ✅ **restored** | open |

**B18-1 and B18-2 are the subjects of the two predictions the same block records as HELD.** A block
can not, in one edit, publish *"both predictions HELD"* and delete both findings from the open list.

Re-measured, executed, this artifact:

```
B18-1  required-not-emitted   assertion ON  -> 55 failed      NEUTERED -> 55 failed   identical
       emitted-not-allowed    assertion ON  -> 37 failed      NEUTERED -> 37 failed   identical
       control (neuter alone, no drift)     -> 134 passed
       => the assertion contributes 0 of 2, unchanged. P18-B2 holds a second time.

B18-2  relevance OPTIONAL + emitted -> 2 failed   (…EVERY_ROW_FIELD_IS_BOUNDED, …NOT_MAKE_IT_MANDATORY)
       cost      OPTIONAL + emitted -> 4 failed
       => CP-2's first operation still reds the guard whose docstring says it exists to allow it.

B18-9  doc-level stamps, 5 shapes x 5 doors:
         rows_of / declarations / discover / SurfaceAssembler : ACCEPT 5/5
         validate_document                                    : REFUSE 4/5
       => four exported doors read rows out of a document none of them will look at.
```

**This is B17-8 in its fourth consecutive round**, and the pattern has now inverted twice: two
rounds ago the two records disagreed; one round ago the sentence they agreed on was false; this
round the list corrected for dropping two is the list that dropped four. **A hand-typed register
cannot be fixed by typing it more carefully.** §0.2's allowlist is the same argument applied to the
register: generate it from the union of the verdicts, or it will keep losing rows.

### 4c · 🟡 **B20-5 — the `introduced` series is one verifier's scope, presented as the run's**

RUNSTATE: *"`introduced`, raw, eleven rounds | `2,1,2,1,3,2,4,3,2,2,2` — **no direction**"*, and
R20's prompt opens with it as the premise of the termination question. **That series is my scope
only.** R19-A `:540`: *"The raw introduced count is **3 in R18 and 3 in R19**."* The run's combined
figure for those rounds is **5 and 5**, not 2 and 2.

It does not change the *conclusion* — neither series has a direction, and mine is 2 again this
round — but a number that frames a termination decision should say whose scope it is. **Process.
Introduced: YES, mildly.**

### 4d · 🟡 **B20-7 — R20's prompt asserts a V-LIVE fact that eleven files in its own directory refute**

Covered in §0.3. *"Nothing in CP-0 or CP-1 has ever been through V-LIVE"* is false; the true and
more useful statement is that CP-1's two V-LIVE rounds both returned `CANNOT DETERMINE` and
**predate all eleven V-CODE deltas**. I record it under the record because the termination question
is built on it, and because it is another **argued** claim in a run whose argued claims are 0-for-9.
**Process. Introduced: YES.**

---

## 5 — the two standing instruments

### 5a · Executed vs argued — **3 : 3, and the argued are 0/3**

| load-bearing claim | established by | correct? |
|---|---|---|
| *"the `rows_of` half reds when its copy is removed"* | **EXECUTION** | ✅ `1 failed` |
| *"`validate_document`'s copy already had a red-able test"* | **EXECUTION** (R19-B's, re-run) | ✅ `1 failed` alone |
| *"Both new guards proven red-able before this commit"* | **EXECUTION** | ✅ both, individually |
| RUNSTATE's `Open, carried` is the set of open findings | **ARGUMENT** | ❌ **B20-4** — four dropped, three re-measured open |
| *"`introduced`, raw: 2,1,2,…"* as the run's series | **ARGUMENT** | ❌ **B20-5** — A measured 3 |
| *"Nothing in CP-0 or CP-1 has ever been through V-LIVE"* | **ARGUMENT** | ❌ **B20-7** — 11 V-LIVE verdicts, same directory |

**Executed 3/3 correct. Argued 0/3 correct.** Run total across three rounds and two verifiers:
**executed 10/10, argued 0/9.** At n=19 the polarity has never broken.

**And note where the three failures landed this round: all three are claims about the run's own
record, none about the code.** The builder's *executed* engineering is now reliable in my scope;
what is not reliable is every sentence anyone writes about it without running something. That is an
argument for mechanising the register, not for another round of reading it.

### 5b · The census — **it agrees a third time**

68 sites, 13 silent, identical members, three independent derivations, two of which did not see the
others' lists. **This is the first coverage number in this run that could become a CI gate rather
than a paragraph, and §0.2 is the proposal.** The structural half is now mechanical too (§3b), which
is what made the denominator finally stop growing.

---

## 6 — convergence, and the prediction

### 6a · closure of R19-B's thirteen findings

| finding | now |
|---|---|
| **B19-1** the `dict(r)` guard landed on the sibling | ✅ **CLOSED at the named site** (residuals **B20-1**, **B20-6**) |
| **B19-2** both records carry a false closure sentence | ✅ **CLOSED** — stated plainly in RUNSTATE and the commit message |
| **B19-3** two open findings dropped from the register | 🟡 **PARTIAL** — both restored, **four more dropped** (**B20-4**) |
| **B19-4** `surface.py:305` unguarded | 🔴 **OPEN** — silent; carried in the register |
| **B19-5** one test, three clauses, one message | 🔴 **OPEN** — byte-identical; **not in the register**; recurs in the new guard (**B20-6**) |
| **B19-8 / B18-10** a fifth exported door | 🔴 **OPEN** — sixth round |
| **B19-11** A's `13/24` filed beside B's `63/87` | ✅ **CLOSED** — the denominators table is now one kind of number |
| **B19-12** `_ID` has no length bound | 🔴 **OPEN** — carried |
| **B18-1** subset gate 0 of 2 | 🔴 **OPEN** — re-measured; **dropped from the register** |
| **B18-2** eleventh guard reds at CP-2 | 🔴 **OPEN** — re-measured (2 tests, 4 for `cost`); **dropped** |
| **B18-8** `str` subclass pins | 🔴 **OPEN** — four silent sites; **restored** ✅ |
| **B18-9** document-stamp gap at four doors | 🔴 **OPEN** — 5/5 shapes; **dropped** |
| **B18-11** `canon` dead; refuted docstring | 🔴 **OPEN** — **restored** ✅ |

**3 clean of 13 = 23%; 27% with the partial at half.**
Series: `14, 10, 8, 27, 54, 25–37, 22–28, 36–41,` **`23–27`**.

### 6b · introduced, per changed line

| definition | count | per 100 changed lines |
|---|---|---|
| code/guard (**B20-1**, **B20-6**) | 2 | 14.3 |
| + record (**B20-3** is pre-existing; **B20-4**, **B20-5**, **B20-7**) | 5 | 35.7 |

**Both normalised figures are noise and I will not defend either.** The delta changed **14 lines** in
my scope, none of them source; a 14-line denominator makes 2 findings read as a catastrophe, exactly
as 404 lines made 3 read as excellence in R18. **Raw is the signal: 2, for the twelfth round —
`2,1,2,1,3,2,4,3,2,2,2,2`.** Three consecutive deltas have changed **zero source lines** in
`app/agentruntime/`, which means the last three rounds have measured the builder's *tests* and the
builder's *record*, not the membrane.

### 6c · 🔮 the predictions

> **P20-B1 — the class survives the site.** R21's delta will fix **B20-1** at `rows_of` (a deep copy,
> or freezing `members` to a tuple) and the class will survive: on R21's artifact, at **≥1** of the
> other three exported doors (`validate_document`, `declarations`, `discover`), the row handed back
> will still satisfy `got["members"] is src["members"]`.
>
> **Falsified if** all four doors return rows whose `members` container is a distinct object.
> **Confirmed if** any one still shares. Today all four share, measured in §1a. The sibling record in
> this run is 1-of-N seven times running, and the four doors are four modules-worth of the same
> statement.

> **P20-B2 — the census is stable, and that is the point** *(two commands, ~5 min).* Re-running
> `census.py` and `census2.py` on R21's artifact will report **68 raise sites** and **the same
> 13-member silent raise set**, minus exactly those sites R21 names as fixed, plus none.
>
> **Falsified if** the site count moves without a source edit to `app/agentruntime/`, or if any
> silent member disappears without a named fix that claims it, or if a *new* silent site appears.
> Confirmation is not a nice-to-have here — it is the evidence that §0.2's gate would be stable
> enough to block CI, and it is cheap enough that R21 should run it whether or not anyone verifies.

---

## Bypass table

| property the delta claims | bypass found | evidence | reachability |
|---|---|---|---|
| `rows_of`'s row copy is now guarded | **none for the top-level rebinding** — `surface.py:72` neutered ⇒ `1 failed` | 1 mutation, suite + isolated test | — |
| …and the guard covers what the finding meant | **yes** — the copy is **shallow**; `members` is shared at all four doors | behaviour probe ×4 doors, control tree | guard-only → prod at CP-2 |
| …and it names its reason when it reds | **yes** — the annotated assert is unreachable; a bare identity assert fires first | failure text captured | guard-only |
| the `validate_document` half was not weakened | **none** — both tests red alone on that mutation | 1 mutation × 2 isolated runs | — |
| a row key / member may not be a `str` subclass | **no live bypass** (pins hold) — **but 4 silent sites** | 4 mutations, `134 passed` each | adversarial-only |
| `OrderBy` keys are `(field, direction)` pairs | **no live bypass** — **but silent** | 1 mutation, `134 passed` | guard-only → prod at CP-2 |
| every row-reader goes through `check_row` | **yes** — a fifth exported door serves an invalid row | injected door: suite + gate green | structural |
| the consumer doors read a valid **document** | **yes** — 4 doors accept 5/5 malformed-stamp documents | 5 shapes × 5 doors | structural → prod at CP-2 |
| `ROW_REQUIRED ⊆ emitted ⊆ ROW_FIELDS` gates the writer | **yes, unchanged** — 0 of 2 with the assertion neutered | 2 drifts × ON/OFF + control | guard-only |
| the eleventh guard serves *"what CP-2 and CP-4 need"* | **yes, unchanged** — 2 tests red on `relevance`, 4 on `cost` | 2 field injections | CI-blocking at CP-2 |
| `_ID` bounds a declaration id | **yes** — 300 chars written end-to-end | control probe | adversarial-only |
| stage-kind membership is by identity only | **yes** — `_KIND_SET` is dead **and** the forgery passes it | AST + forgery probe | latent |
| `canon` is the one place §0.14.2 is decided | **yes** — 0 uses, 2 dead imports, refuted docstring | AST over 8 modules | doc / dead code |
| the register names every open finding | **yes** — 4 dropped, 3 re-measured open | diff of two carried lists + 3 injections | process |

## Red-ability table — **my own denominator, mechanically derived**

| | count |
|---|---|
| `raise` statements (AST, 8 modules) | **68** |
| structural copies / materialisations / asserts (AST rule, §3b) | **16** |
| **denominator** | **84** |
| red-able | **64 — 76%** |
| silent | **20** |

Silent: **13 raise** (§3a) + **7 structural** (§3b). Of the 20: **7 real** (`contract.py:221`,
`:255`, `surface.py:305`, `surface.py:407`, `canon.py:60`/`:71`/`:84`) · **5 redundant, measured**
(`contract.py:381`, `manifest.py:220`, `:408`, `:409`, `surface.py:595`) · **2 dead handlers**
(`manifest.py:245`, `:428`) · **1 latent at CP-4** (`surface.py:389`) · **1 carried**
(`manifest.py:310`) · **1 low** (`manifest.py:297`) · **3 cosmetic** (`contract.py:296`,
`surface.py:329`, `:427`).

Series: 48 → 87 (72%) → 92 (79%) → **84 (76%)**.

## Sibling table — *a correction applied to one member of a set*

| correction | members | applied to | missed |
|---|---|---|---|
| **a row copy that a consumer cannot write through** | `manifest.py:448` ✅ top-level, ✗ nested · **`surface.py:72`** ✅ top-level, ✗ nested · `declarations` ✗ · `discover` ✗ | **2 of 4 doors, 0 of 4 for `members`** | 🔴 **B20-1** |
| an assertion carries the message it means | the `rows_of` behavioural assert ✅ · **the identity assert above it** ✗ | 1 of 2 | 🟡 **B20-6** |
| a stage parameter is non-empty **and** well-shaped | `TopK.k` ✅ `Filter.field` ✅ `OrderBy.keys` ✅ `TakeWhileBudget.cost_field` ✅ · **`OrderBy` pair shape** ✗ | **4 of 5** | 🔴 **B19-4** |
| exact-type pins against a `str` subclass | stages ✅ · **row keys** ✗ · **row members** ✗ | 1 of 3 | 🔴 **B18-8** |
| identity, not equality, for kind membership | `validate_pipeline` ✅ · **`_KIND_SET` still defined** ✗ | 1 of 2 | 🔴 **B20-3** |
| deleting a refuted claim | the call-site comment ✅ · **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 **B18-11** |
| a materialisation before a second iteration | `:409` ✅ `:595` ✅ `:220` ✅ | **3 of 3, all redundant behind their pins** | — ✅ |
| document-level validity at the consumer doors | `validate_document` ✅ · `rows_of` ✗ · `declarations` ✗ · `discover` ✗ · `SurfaceAssembler` ✗ | **1 of 5** | 🔴 **B18-9** |
| a gate that must not red on its own legitimate branch | `REQUIRED_SET` ✅ · **the eleventh guard** ✗ | 1 of 2 | 🔴 **B18-2** |
| every open finding appears in the register | 2 restored ✅ · **B18-1, B18-2, B18-9, B19-5** ✗ | restored 2, lost 4 | 🔴 **B20-4** |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| property | test | reds? | for the right reason? |
|---|---|---|---|
| **`rows_of` returns a copy (top level)** | `…LEAVES_THE_VALIDATOR` | ✅ `1 failed` | 🟡 yes, but with a bare identity message (**B20-6**) |
| **`rows_of`'s copy shares no mutable substructure** | **none** | **n/a** | 🔴 **B20-1** |
| `validate_document` returns copies | new test **+** `…SMUGGLE…` | ✅ ×2, each alone | ✅ not weakened |
| C-12's PATH survives `check_row`'s re-raise | `…SURVIVE_EVERY_RE_RAISE` | ✅ ×2 mechanisms | ✅ |
| a tool with resolving members is refused | `…STILL_A_TOOL_WITH_MEMBERS` | ✅ | ✅ |
| `Filter`/`OrderBy`/`TakeWhileBudget`/`pipeline` non-empty | `…MUST_NAME_THE_FIELD…`, `…NOT_A_SILENT_NO_OP` | ✅ each alone | 🟡 three share one message (**B19-5**) |
| **an order_by key is a `(field, direction)` pair** | **none** | **n/a** | 🔴 **B19-4** |
| **a row key / member is not a `str` subclass** | **none** ×4 | **n/a** | 🔴 **B18-8** |
| **a declaration id has a bounded length** | **none** | **n/a** | 🔴 **B19-12** |
| **document-level validity at the consumer doors** | **none** | **n/a** | 🔴 **B18-9** |
| **a fifth row-reading door** | **none** | **n/a** | 🔴 **B18-10**, 6th round |
| **`canon` has a reader** | **none** | **n/a** | 🔴 **B18-11** |
| **kind membership has exactly one mechanism** | **none** | **n/a** | 🔴 **B20-3** |
| naming a field does not make it mandatory | `…NOT_MAKE_IT_MANDATORY` | ✅ | 🔴 reds on the legitimate path too (**B18-2**) |
| the writer's keys sit between REQUIRED and ALLOWED | `…ACTUALLY_EMITS` | **NO** (0 of 2) | 🔴 **B18-1** |

## Reachability verdict on every finding

| # | finding | bucket | introduced by the graded delta |
|---|---|---|---|
| **B20-1** | `dict(r)` is shallow; all four exported doors share the source document's `members` list | guard-only → **prod-reachable at CP-2** | behaviour **no**; the false completeness **YES** |
| **B20-3** | `_KIND_SET` is dead and is the construct the identity check replaced; the forgery passes it | latent / adversarial | no |
| **B20-4** | four open findings dropped from `Open, carried` — B17-8, **4th round** | process | **YES** |
| **B20-5** | the `introduced` series is B-scope-only, published as the run's | process | **YES**, mildly |
| **B20-6** | the new guard's annotated message is unreachable; a bare identity assert fires first | guard-only | **YES** |
| **B20-7** | R20's prompt asserts no CP-0/CP-1 V-LIVE has ever run; 11 verdicts say otherwise | process | **YES** |
| **B19-4** | `surface.py:305` silent; a mutable list pair and a self-deciding tuple subclass are refused only by an untested clause | guard-only → prod at CP-2 | no |
| **B19-5** | one test, three clauses, one indistinguishable message | guard-only | no |
| **B19-12** | `_ID` unbounded; 300-char id written in the control | adversarial-only | no |
| **B18-1** | the subset gate contributes 0 of 2 | guard-only | no (**dropped from register**) |
| **B18-2** | the eleventh guard reds on CP-2's first operation (2 tests; 4 for `cost`) | guard-only, **CI-blocking at CP-2** | no (**dropped**) |
| **B18-8** | four silent `str`-subclass pins | adversarial-only | no |
| **B18-9** | four exported doors accept 5/5 malformed-stamp documents | structural → prod at CP-2 | no (**dropped**) |
| **B18-10** | a fifth exported row-reading door, suite + gate green | structural | no |
| **B18-11** | `canon` dead, two dead imports, refuted docstring verbatim | dead code / doc | no |

**0 production-reachable today · 3 adversarial-only · 8 guard-only/structural · 4 process · total 15
· introduced 2 (code/guard) / 5 (with the record).**

**The zero in that first column is item zero's evidence.** Eleven rounds, and not one finding in my
scope is reachable by a running system, because no running system imports the package.

---

## What I would fix first

1. **Ship the census as CI** (§0.2). It is 84 sites, ~5 minutes, three independent derivations
   agreeing on the mechanisable half, and it is the only closure criterion available at this
   checkpoint that a verifier round cannot substitute for. It would have caught B19-1 without a
   verifier, and it caught this round's fix without one.
2. **Generate the register from the verdicts.** Four rounds of B17-8; the fix that restored two rows
   deleted four. A hand-typed list of open findings is the same failure mode as a hand-picked census
   denominator, and it has the same fix.
3. **B20-1** — deep-copy or freeze `members` at **all four** doors, and assert the shared-container
   property, not the rebinding. Then **B20-6**: move the message onto the assert that actually fires.
4. **B18-1, B18-2, B18-9** — put them back, then fix **B18-2** (one line: anchor the eleventh guard's
   probe on `ROW_FIELDS = MappingProxyType({`) because it is the first thing CP-2 will hit, and it
   reds **2** tests, **4** for `cost`.
5. **The seven real silent sites** — `contract.py:221`/`:255`, `surface.py:305`, `surface.py:407`
   (delete `_KIND_SET`), `canon.py:60`/`:71`/`:84` (or delete `canon` and its two dead imports).
   With the gate in place these stop being a paragraph and become seven rows that must go green or
   be signed for.
6. **Then stop verifying and wire the import.** CP-1's V-LIVE returned `CANNOT DETERMINE` ×4 because
   the turn cannot be placed on the new surface. That is the measurement this effort has never been
   able to take, and no twelfth V-CODE round will take it.

---

**Files touched by this verifier: this file only.**
`git status --porcelain services/chat-service scripts contracts docs/plans` is **empty**; the real
tree is `134 passed` and the membrane gate exits 0 (selftest + gate) at finish; nothing committed.
All injections were made in two full-layout replicas under the session scratchpad and restored from
my own pristine snapshot. **No `git checkout` was used at any point.**

`git rev-parse HEAD` = `b73e086caeac55e6c43332c630411ad84ac29bd4` — **unmoved.**
