# CP-1 · round 19 · V-CODE · **Verifier B — the membrane**

**Artifact:** `5b531e22ae93f52cc45f55741b3016b76d754691`
`git rev-parse HEAD` **at start:** `5b531e22ae93f52cc45f55741b3016b76d754691`
`git rev-parse HEAD` **at finish:** `5b531e22ae93f52cc45f55741b3016b76d754691` — **unmoved.**

**Graded delta:** `7bb963db9` against `2faa88bac`.
**Scope:** `services/chat-service/app/agentruntime/`, `scripts/agentruntime-membrane-gate.py`,
`services/chat-service/tests/test_cp1_membrane.py`.

**Method.** Every claim below was **executed**. All injections were made in a fresh full-layout
scratch replica (`services/chat-service/`, `scripts/`, `contracts/`, `.github/workflows/`) so the
repo-path-dependent tests run rather than deselecting — the replica baseline is **`134 passed`,
identical to the real tree**, gate exit 0, and no test was excluded from any measurement. Every
injection is a **source edit** picked up by a fresh `pytest` process, asserts its anchor count
**before** writing and asserts the text **present in the file** afterwards; a mismatched anchor
aborts rather than producing an inert run. Restoration is from **my own pristine copy**, never
`git checkout`. The real tree was never edited: `git status` over `services/chat-service/`,
`scripts/`, `contracts/` and `docs/plans/` is **empty**, and the real-tree suite reproduces
`134 passed` / gate exit 0 at finish.

**Baseline:** `134 passed` (129 + R18's five new tests); membrane gate **green**
(`8 module(s), 0 allowed external import(s), 2 single-sited type(s)`).

**The delta in my scope is test-only.** `git diff 2faa88bac HEAD --stat -- app/agentruntime/
scripts/agentruntime-membrane-gate.py` is **empty**. `test_cp1_membrane.py` is `+82 / −0`.

---

## 1 — the two predictions, settled first

### 1a · ✅ **P18-B1 — HELD**

> *fixing B18-2 at the anchor leaves the class alive: the CP-2 injection will still leave ≥1 test
> red. **Falsified if it yields `0 failed`.***

The injection is CP-2's real change as the prediction specifies it: `relevance` added to
`ROW_FIELDS` **and emitted by `_row`**, `ROW_REQUIRED` untouched. Injection verified present in
both files before anything was trusted:

```
ROW_FIELDS gains relevance (OPTIONAL) : True
_row EMITS relevance                  : True
ROW_REQUIRED untouched                : True

=== SUITE UNDER THE CP-2 INJECTION ===
2 failed, 132 passed, 1 warning in 1.81s

FAILED tests/test_cp1_membrane.py::TestP4No…::test_EVERY_ROW_FIELD_IS_BOUNDED__not_only_the_id
FAILED tests/test_cp1_membrane.py::TestP4No…::test_NAMING_A_FIELD_DOES_NOT_MAKE_IT_MANDATORY
E       AssertionError: the schema literal moved; this probe is stale
tests\test_cp1_membrane.py:1036: AssertionError
```

**`2 failed`, not `0`. HELD.** And it held for a reason stronger than the one predicted: the
prediction's antecedent — *"R19's delta will fix B18-2 at the anchor I named"* — **did not happen**.
`test_NAMING_A_FIELD_DOES_NOT_MAKE_IT_MANDATORY` is byte-identical in this delta; the anchor
`'    "members": (list, tuple),\n})'` is untouched, so the guard still aborts with
*"the schema literal moved; this probe is stale"* on the exact operation its own docstring says it
exists to enable. That is a HELD prediction on a delta that did not attempt the fix — worth less
than a HELD prediction on a delta that did, and I record it that way.

**The measurement R18-B published as its control was wrong, and it was wrong the way R18-B told the
builder not to be.** R18-B wrote *"Today the count is 1"* — but it measured with `salience`, a field
the prediction does not name and that appears in no checkpoint. Run across the four fields the
eleventh guard's docstring actually names:

| field added OPTIONAL **and** emitted | suite | tests red |
|---|---|---|
| `relevance` (CP-2's first arrival) | **2 failed** | `…EVERY_ROW_FIELD_IS_BOUNDED…`, `…NOT_MAKE_IT_MANDATORY` |
| `lane` | **2 failed** | same two |
| `tier` | **2 failed** | same two |
| `cost` | **4 failed** | + `…BUILD_PREVIOUS_USES_THE_SAME_DEFINITION…`, `…a_forged_ROW_VALUE_cannot_defeat_the_budget` |
| `salience` (R18-B's vehicle) | **1 failed** | `…NOT_MAKE_IT_MANDATORY` only |

**A fixture chosen for convenience answered a different question than the one being asked** — the
sentence R18-B wrote about the builder's `members: ['ghost']`, reproduced by R18-B one section
later against its own prediction. B18-2's blast radius at CP-2 is **2 tests, and 4 for `cost`**, not
1.

The second failure is not an anchor bug and I will not inflate it into one:
`test_EVERY_ROW_FIELD_IS_BOUNDED__not_only_the_id` (`:765`) deliberately asserts that
`{"relevance": 9999}`, `{"lane": …}`, `{"tier": …}` and `{"cost": …}` are **refused**, because
nothing writes them today. A contract change must change that test. But it means the delta ships
**two** tests whose stated subject is *"CP-2 adds `relevance`"* and both go red the moment it does,
one of them with a message indistinguishable from a regression.

### 1b · ✅ **P18-B2 — HELD**

> *B18-1 was closed by rewording: neutering its assertion to `assert True` will still leave both
> drift injections RED (the assertion contributes 0 of 2). **Falsified if either goes GREEN.***

`assert set(ROW_REQUIRED) <= emitted <= set(ROW_FIELDS), (…)` is byte-identical in this delta. The
neuter removes the whole statement (asserted absent from the file afterwards) and replaces it with
`assert True`:

```
injection                  assertion ON                       assertion NEUTERED
required-not-emitted       RED                                RED
  ON : ContractViolation … Accepted: every row carries ['admitted_against', …, 'salience']
  OFF: ContractViolation … Accepted: every row carries ['admitted_against', …, 'salience']   <- identical
emitted-not-allowed        RED                                RED
  ON : ContractViolation … Accepted: one of ['admitted_against', …, 'owning_service']
  OFF: ContractViolation … Accepted: one of ['admitted_against', …, 'owning_service']        <- identical

control (neuter only, no drift): ('GREEN', '')
```

**Both stay RED. The assertion still contributes 0 of 2. HELD.** The control proves the neuter is
inert on its own, so "both red" is the assertion's contribution and not the neuter's. Here too the
antecedent did not occur — B18-1 was not reworded, it was left alone — and RUNSTATE carries it
openly, which is the honest handling.

**Both predictions HELD; neither was tested against a fix.** A prediction that survives because the
delta declined the subject is evidence about the register, not about the model of the codebase that
produced it. I say so rather than bank it.

---

## Verdicts

| # | claim | verdict |
|---|---|---|
| 1 | settle P18-B1 and P18-B2 | **BOTH HELD**, each by one command, each on an untouched subject. §1. And **R18-B's own published control for P18-B1 was wrong**: it measured `salience`, not the `relevance` the prediction names — the real count is **2**, and **4** for `cost` |
| 2 | the three restored holes have tests; each reds for the reason it names; the probe error is not repeated | **2 OF 3 ARE EXCELLENT; THE THIRD GUARDS A DIFFERENT SITE.** G9's test reds on **both** mutations — the downgrade *and* the deletion the builder's original probe used — and the deletion message is `rows_of lost C-12's field PATH: 'kind'`, the exact half that read green before. G22's test's vehicle now isolates the clause: with it removed the doors report **`DID NOT RAISE`**, so no other refusal fires first. **But `dict(r)`: the finding named `surface.py:72` (`rows_of`) and the test guards `manifest.py:448` (`validate_document`) — a site that ALREADY had a red-able test.** Neutering `surface.py:72` leaves **`134 passed`** → **B19-1** |
| 3 | four raise sites got guards; find the sixth, with your own denominator | **All four red individually, executed.** My denominator is **92** (68 `raise` by AST + 24 structural), **73 red-able (79%)**, 19 silent. The sixth: **`surface.py:305`** — `OrderBy`'s key-pair shape. `134 passed` without it, and it then constructs a **mutable list** ordering key and a **tuple subclass whose `__iter__` decides its own ranking** → **B19-4**. And `contract.py:381`, which R18-B bucketed *real*, is **measurably redundant with M5** — my first probe conflated two vehicles and I re-measured |
| 4 | B18-10 — a fifth exported door, now four rounds old; is the CP-2 scoping still honest? | **UNCHANGED, fifth round.** A fifth exported row-reading door served `{'id':'x','kind':'gadget','cost':10**9}` as `['x:gadget']` with **`134 passed`** and **gate exit 0**, while `rows_of` refuses the same row. **Scoping still honest but thinner than it reads**: no importer of `agentruntime` exists outside the package — but `chat_messages.runtime_variant` already carries a `CHECK (… IN ('legacy','agentruntime'))` and `instrument.RUNTIME_AGENTRUNTIME` is already defined. The socket is built; only the plug is missing → **B19-8** |
| 5 | the record: commit message and RUNSTATE now claim the same three holes; has anything else drifted? | **THE THREE HOLES AGREE — B18-3 IS CLOSED.** Both name G9, G22, `dict(r)`. **But the sentence they agree on is false**: *"All three now have tests, and each reds when the check it names is neutered"* — the third does not (**B19-2**). And **two open findings were dropped**: B18-8 and B18-11 are unfixed, unmentioned in the commit message, and absent from RUNSTATE's `Open, carried` list — **B17-8's failure mode, third round** (**B19-3**). One more, mild: RUNSTATE files A's `13/24` beside B's `63/87` under *denominators*; A's is a **closure** figure over 24 findings, B's is a mechanical **red-ability census** — not comparable (**B19-11**) |
| 6 | convergence, and a new prediction | **Closure 4 clean of 11 = 36%; 41% with the partial at half** — `14, 10, 8, 27, 54, 25–37, 22–28,` **`36–41`**. Introduced **2** code/guard findings on **82** changed lines = **2.4 / 100** (4.9 with the record findings). **Executed-vs-argued in my scope: 4 : 3 — executed 4/4 correct, argued 0/3 correct.** Prediction in §6c |

**Overall: FAIL** — on **B19-1**, which is the run's most-repeated failure recurring for the
**seventh** time and this time inside the delta whose entire subject is *"my probe was wrong three
times"*: R18-B gave the file **and the line** and the mutation, and the guard landed on the sibling
site one module over — one that a pre-existing test already covered, so the delta's coverage of the
named property is **zero** and the register says **closed**. And on **B19-2**, the record asserting
that closure in both places.

**Three things in this delta are genuinely good and belong first.** G9's test is *stronger than the
finding asked for*: it reds on the downgrade **and** on the deletion, and it asserts the field
**path** (`declarations[0].kind`), not the field — so the half that read green through the builder's
original probe is now the half that reds. G22's test **fixed the probe rather than the symptom**:
its member resolves, so the clause is isolated and its removal reports `DID NOT RAISE` rather than a
refusal for another reason. And **B18-3 is closed**: two records, one status, three holes, and the
failure is written down in RUNSTATE in the builder's own words rather than minimised.

---

## Falsifiers, stated before the search

| claim | what would have falsified it |
|---|---|
| P18-B1 | the CP-2 injection yielding `0 failed` |
| P18-B2 | either drift injection going GREEN with the assertion neutered |
| 2 | each new test staying GREEN when the clause it names is neutered; or reddening on the clause's *neighbour* only |
| 3 | every remaining silent site being redundant with a guard that already reds, shown by execution |
| 4 | any importer of `agentruntime` outside the package; the injected door being refused by suite or gate |
| 5 | the two records naming the same three holes **and** every open finding appearing in the register |
| 6 | closure rising while introduced-per-line fell |

---

## 2 — the five new tests, one vehicle at a time

Each clause neutered **alone**, full suite after, per-test verdict recorded.

| clause neutered | C12 test | TOOL test | COPY test | STAGE test | GEN test | suite |
|---|---|---|---|---|---|---|
| `check_row`'s re-raise **DOWNGRADED** (R18-B's mutation) | 🔴 RED | 🔴 RED | GREEN | GREEN | GREEN | `2 failed` |
| `check_row`'s re-raise **DELETED** (the builder's original probe) | 🔴 RED | GREEN | GREEN | GREEN | GREEN | `1 failed` |
| the tool-with-members clause removed (`contract.py:368`) | GREEN | 🔴 RED | GREEN | GREEN | GREEN | `1 failed` |
| **`rows_of`'s `dict(r)` → `out.append(r)` (`surface.py:72`)** | GREEN | GREEN | **GREEN** | GREEN | GREEN | **`134 passed`** |
| `validate_document`'s `[dict(r) for r in rows]` (`manifest.py:448`) | GREEN | GREEN | 🔴 RED | GREEN | GREEN | `2 failed` |
| `Filter` field-emptiness (`surface.py:185`) | GREEN | GREEN | GREEN | 🔴 RED | GREEN | `1 failed` |
| `OrderBy` keys non-empty (`surface.py:302`) | GREEN | GREEN | GREEN | 🔴 RED | GREEN | `1 failed` |
| `TakeWhileBudget` cost_field (`surface.py:391`) | GREEN | GREEN | GREEN | 🔴 RED | GREEN | `1 failed` |
| `pipeline = list(pipeline)` (`surface.py:524`) | GREEN | GREEN | GREEN | GREEN | 🔴 RED | `1 failed` |

### 2a · ✅ the C-12 test and the tool test both exercise the clause they claim

```
G9a  re-raise DOWNGRADED : RED  — C12 test reds; TOOL test reds (its expected class moved too)
G9b  re-raise DELETED    : RED  — E   AssertionError: rows_of lost C-12's field PATH: 'kind'
G22  clause REMOVED      : RED  — E   Failed: DID NOT RAISE <class 'ContractViolation'>
```

`DID NOT RAISE` is the answer to the probe question: with the clause gone **nothing else refuses**,
so the stock-fixture confusion (M5 firing first) is genuinely gone rather than papered over. And the
C-12 test reds on *both* mutations, which no verifier asked for — deletion reds it on the **path**
half, which is the half the builder's own probe could not see.

### 2b · 🔴 **B19-1 — the `dict(r)` guard landed on the sibling site**

R18-B's finding, verbatim: *"**G48** `dict(r)` (`surface.py:72`) | `out.append(r)` | caller mutation
of a returned row reaches the source document"*. Two different copies exist, and they are
independent — measured, not read:

```
CONTROL
  rows_of           : caller mutation reached the SOURCE document -> False
  validate_document : caller mutation reached the SOURCE document -> False

surface.py:72  dict(r) REMOVED   (the site the FINDING named)
  rows_of           : caller mutation reached the SOURCE document -> True     <- the defect, restored
  validate_document : caller mutation reached the SOURCE document -> False
  suite: 134 passed                                                            <- nothing notices

manifest.py:448 copy REMOVED     (the site the NEW TEST guards)
  rows_of           : caller mutation reached the SOURCE document -> False
  validate_document : caller mutation reached the SOURCE document -> True
  suite: 2 failed — ['test_A_ROWS_OWN_GET_CANNOT_SMUGGLE_A_ROW_PAST_THE_VALIDATOR',
                     'test_THE_ROW_COPY_IS_WHAT_LEAVES_THE_VALIDATOR']
```

The new test `test_THE_ROW_COPY_IS_WHAT_LEAVES_THE_VALIDATOR` (`:2079`) calls `validate_document`,
so it guards `manifest.py:448`. **And that site already had a red-able test** — run alone on the
same mutation:

```
pre-existing test alone (…ROWS_OWN_GET_CANNOT_SMUGGLE…): 1 failed, 133 deselected
```

So the delta's third guard adds **zero** coverage at the site it duplicates and **zero** at the site
the finding named. `rows_of` is the door `SurfaceAssembler`, `discover` and `declarations` all stand
behind — the module's own comment eight lines above `surface.py:72` says so, and says that door was
historically "the weaker of the two". It is weaker again, and the register says the hole is closed.

**Reachability: guard-only today; production-reachable at CP-2** (a consumer that mutates a row it
was handed edits the manifest the drift gate later compares). **Introduced by the graded delta:
YES** — the test and the claim are both new in `7bb963db9`.

### 2c · 🟡 **B19-5 — one test standing for three properties, with an indistinguishable message**

`test_A_STAGE_MUST_NAME_THE_FIELD_IT_READS__and_the_order_it_ranks_by` carries three sequential
`pytest.raises`. Each clause reds it individually (table above) so the coverage is real — but the
reader cannot tell which:

| state | message |
|---|---|
| all three clauses removed | `E   Failed: DID NOT RAISE <class 'ValueError'>` |
| `OrderBy` + `TakeWhileBudget` removed, `Filter` intact | `E   Failed: DID NOT RAISE <class 'ValueError'>` |
| `TakeWhileBudget` alone removed | `E   Failed: DID NOT RAISE <class 'ValueError'>` |

Identical in all three. The same file, 400 lines above (`:1667`), states the rule this breaks:
*"Two mechanisms, two assertions — the pattern this file learned the hard way when one
`pytest.raises` was made to stand for both and stopped being able to tell them apart."* A `match=`
per raise, or three tests. **Reachability: guard-only. Introduced: YES.**

---

## 3 — the census, my denominator, and the sixth

### 3a · derived mechanically, and I did not inherit 87

I re-ran the enumeration from scratch rather than adopting R18-B's number. **68 `raise` statements**
across all eight modules by AST, each replaced with `pass` at its own indent, one at a time, full
membrane suite after each: **55 red-able, 13 silent.** To that I added **24 structural invariants
that carry no `raise`** — two defensive copies, three materialisations, the C-12 re-raise *class*,
three exception-hierarchy edges, `MappingProxyType`, the `ROW_REQUIRED` literal, `_row`'s
self-check, three `check_document_rows` call sites, six exact-type pins, the two §6.4 stamps, and
the rebuilt-document return — each with its own anchored edit: **18 red-able, 6 silent.**

### **73 / 92 red-able (79%).** 19 silent: **6 real** · **3 real-but-unexported** · **1 carried** · **2 dead** · **1 latent at CP-4** · **5 redundant** · **1 low**

| bucket | sites |
|---|---|
| 🔴 **real, reachable through an exported door** | `contract.py:221` + its `type(key) is not str` pin, `contract.py:255` + its members pin (**B18-8**), **`surface.py:305`** (**B19-4**), **`surface.py:72`** (**B19-1**) |
| 🔴 **real, but `canon` is uncalled and unexported** | `canon.py:60`, `canon.py:71`, `canon.py:84` (**B18-11**) |
| 🟡 carried | `manifest.py:310` (the `exists`→`load` race) |
| 🟡 dead handlers (B17-4) | `manifest.py:245`, `manifest.py:428` |
| 🟡 latent at CP-4 | `surface.py:389` — a negative budget is unreachable while no row may carry `cost` |
| 🟢 **redundant, measured** | `contract.py:381` (M5 refuses the same input — §3c), `manifest.py:408`, `manifest.py:409` `rows = list(rows)`, `surface.py:595` `rows = list(rows)`, `surface.py:43` `_is_exactly(rows, list)` |
| 🟢 low | `manifest.py:297` (no manifest location) |

R18-B derived 87 and 24-silent; I derive 92 and 19-silent, and **the silent *sets* agree almost
exactly** — the four raise sites this delta guarded (`contract.py:368`, `surface.py:185`, `:302`,
`:391`) moved from silent to red-able, and everything else is the same subject counted differently.
Two independent mechanical censuses converging on the same silent set is the first coverage number
in this run that is not a measurement of who looked hardest. **It should be a script in CI.**

### 3b · 🔴 **B19-4 — the sixth: `OrderBy`'s key-pair shape** (`surface.py:305`)

`134 passed` with the clause removed, and what it then constructs decides the ranking:

```
CONTROL
  list pair ['id','asc']     REFUSED     -> ValueError: keys[0] is not a (field, direction) pair
  tuple SUBCLASS Flip        REFUSED     -> ValueError: keys[0] is not a (field, direction) pair
  3-tuple                    REFUSED     -> ValueError: keys[0] is not a (field, direction) pair

CLAUSE REMOVED
  list pair ['id','asc']     CONSTRUCTED -> effective_keys=(['id','asc'],)
  tuple SUBCLASS Flip        CONSTRUCTED -> effective_keys=(('id','asc'), ('id','asc'))
  3-tuple                    REFUSED     -> ValueError: too many values to unpack (expected 2)
```

Two distinct defects, one clause. A **list** pair puts a **mutable** ordering key inside a stage the
module's own section header calls *"data, not closures"* — anything holding the stage can re-point
the ranking after validation. A **tuple subclass whose `__iter__` decides what it yields** is
`§0.14.1`'s whole subject at the one place the run has already paid for it: `field, direction =
pair` reads it once, `effective_keys()` reads it again, and the surface is ordered by whatever the
second read says. This is `OrderBy(keys=())`'s sibling **in the same constructor** — B18-6 got a
test in this delta and the clause eight lines below it did not.

**Reachability: guard-only today; production-reachable at CP-2** (`OrderBy` is what every
rank-dependent stage consumes). **Introduced: no.** R18-B listed `surface.py:305` in a bucket and
never named it; this is the execution.

### 3c · 🟢 `contract.py:381` is redundant — and my first probe said otherwise

My first probe gave a skill a pattern-invalid member **and** gave a row that same string as its
`id`, so removing the clause simply moved the refusal to the id check. That is the conflated
vehicle. Re-measured with every row id valid:

```
_ID pattern: ^[a-z][a-z0-9_]*$
CONTROL             member 'a b c' -> ContractViolation: s0.members[0]: not a declaration id
CLAUSE 381 REMOVED  member 'a b c' -> UnresolvedReference: s0 references 'a b c', which is not admitted
```

M5 refuses the same input with a message naming the same thing. **Redundant, measured** — and
recorded here because a verifier's wrong probe is the same defect as a builder's.

### 3d · 🟡 **B19-12 — `_ID` has no length bound**

`^[a-z][a-z0-9_]*$` accepts a **300-character** declaration id end-to-end: `admit()` → `build()` →
a written row, in the **control**. An id is the membership key for every `AllowList`/`DenyList` and
is what the model is shown. Not an unguarded check — a **missing** one. **Adversarial-only
(a Python caller). Introduced: no.**

---

## 4 — B18-10, fifth round

```
  the fifth door served : ['x:gadget']
  rows_of               : ContractViolation: x.declarations[0].cost: is a field the contract does not define
  suite                 : 134 passed
  gate                  : exit 0 | agentruntime-membrane-gate OK - 8 module(s), …
```

A `summarise_rows` appended to `surface.py`, imported in `__init__.py` and added to `__all__`,
reading `r['id']` and `r['kind']` directly. It serves a row that fails the closed schema; `rows_of`
refuses the identical row. Nothing in the suite or the gate requires a row-reader to stand behind
`check_row`. **Unchanged, fifth round.**

**On the scoping.** Repo-wide, the only references to `agentruntime` outside the package are
`scripts/agentruntime-membrane-gate.py` and `.github/workflows/lint-foundation.yml` — **no importer,
so not production-reachable today** and CP-2 ownership stays defensible. But the claim is thinner
than the register makes it sound: `db/migrate.py:367-368` already ships
`runtime_variant TEXT NOT NULL DEFAULT 'legacy' CHECK (runtime_variant IN ('legacy','agentruntime'))`
with an index on it, and `instrument.py:100` already defines `RUNTIME_AGENTRUNTIME`. Every write
path passes `RUNTIME_LEGACY`. **The socket is built and wired; the one thing missing is the import.**
→ **B19-8. Reachability: structural, production-reachable at CP-2.**

---

## 5 — the record

### 5a · ✅ **B18-3 is closed** — the three holes agree

| record | holes named |
|---|---|
| `7bb963db9` commit message | C-12 re-raise (deleted vs downgraded) · tool with **resolving** members · `dict(r)` |
| `RUNSTATE:1766-1772` table | C-12 fields at `check_row`'s re-raise · a tool with **resolving** members · `dict(r)` |

Same three, in the same order, each with the probe error named. RUNSTATE also carries the
self-indictment (*"the record contradicted itself, and that is the worst thing in this block"*)
rather than minimising it. **B18-3: closed.**

### 5b · 🔴 **B19-2 — the sentence they now agree on is false**

Commit message: *"All three now have tests, and each reds when the check it names is neutered."*
Measured in §2b: neutering `surface.py:72`, the check the third finding names, leaves
**`134 passed`**. Both records therefore carry one identical false closure. This is worse than
R18's split in one respect — a contradiction is *visible* to the next reader, and an agreed-upon
falsehood is not. **Reachability: process. Introduced: YES.**

### 5c · 🔴 **B19-3 — two open findings dropped from the register**

RUNSTATE's `Open, carried` line names: the outage ordering residual · T10 · route 25 · W4/W7 ·
`G01`/`G12` · B18-1 · B18-2 · B18-10 · `rows_of`'s document-stamp gap · the two contradictory
comments. **B18-8 and B18-11 appear nowhere** — not in the commit message, not in the block, not in
the carried list. Both are unfixed, measured here:

| dropped finding | status on this artifact |
|---|---|
| **B18-8** — a `str` **subclass** key/member walks past `contract.py:221` / `:255` | 🔴 **OPEN** — all four sites (both raises, both `type(...) is str` pins) **silent** in my census |
| **B18-11** — `canon` uncalled and unexported; `nfc()`'s docstring carries the refuted claim | 🔴 **OPEN** — the docstring still reads *"two `digest` values for one visibly identical document"* **verbatim** at `canon.py:42`; zero non-comment call sites in the package |

This is **B17-8** — *"a finding that is neither closed nor carried has been forgotten"* — in its
**third** consecutive round, and this time in the very block written to fix the previous instance of
it. **Reachability: process. Introduced: YES.**

### 5d · 🟡 **B19-11 — one drift in the numbers**

RUNSTATE's *Denominators* table reads *"R18-B measures 63/87 red-able; R18-A measures 13/24 in its
scope."* B's is a mechanical red-ability census (neuter every site, count what reds). A's `13/24` is
labelled **"Closure 13 of 24 = 54%"** in its own §6 verdict row and *"Red-able **and closed**"* in
its §5 heading — a closure figure over a hand-built list of findings-plus-newly-tightened-facts.
Placing them side by side under one heading implies a comparability that does not exist, and it
flatters the smaller denominator. (A's verdict is also internally inconsistent — *"the lowest
normalised rate of the series"* at its line 33, *"the second-lowest ever"* at its line 528; RUNSTATE
copied the second, so this one is A's, not the record's.) **Reachability: process. Introduced: YES,
mildly.**

### 5e · nothing else drifted

I checked every other quantitative claim in the R18 block against both verdicts: *7 of 7 fixes with
a red-able test* ✓ (A `:87`), *`introduced` 0.74/100* ✓ (A `:507`), *the true number is 5, never 2*
✓ (A `:394`), *68 raise sites + 19 structural = 87* ✓ (B `:298-300`), *B's scope was test-only, zero
source lines* ✓ (verified: the diff is empty for `app/agentruntime/` and the gate script). The
`2266 tests pass` claim is outside my scope and I did not verify it.

---

## 6 — convergence, and the prediction

### 6a · closure of R18-B's eleven findings

| R18-B finding | now |
|---|---|
| **B18-1** the subset gate contributes 0 of 2 | 🔴 **OPEN** — **P18-B2 HELD**; carried in RUNSTATE, correctly |
| **B18-2** the eleventh guard reds on CP-2's first operation | 🔴 **OPEN** — anchor byte-identical; **P18-B1 HELD**; blast radius is **2 tests, 4 for `cost`**, not 1 |
| **B18-3** two records, different holes | ✅ **CLOSED** — same three in both, with the probe error named (residual **B19-2**) |
| **B18-4** all three "unreproduced" holes reproduce | 🟡 **PARTIAL** — G9 ✅ (reds on **both** mutations), G22 ✅ (`DID NOT RAISE`), **`dict(r)` ✗** (**B19-1**) |
| **B18-5** `Filter` must name its field | ✅ **CLOSED** — reds alone, `1 failed` |
| **B18-6** `OrderBy(keys=())` | ✅ **CLOSED** — reds alone (residual **B19-4**, its sibling eight lines below) |
| **B18-7** `pipeline = list(pipeline)` | ✅ **CLOSED** — reds alone |
| **B18-8** a `str` subclass key/member | 🔴 **OPEN** — four silent sites, **and dropped from the register** (**B19-3**) |
| **B18-9** `rows_of`'s document gap at four exported doors | 🔴 **OPEN** — carried |
| **B18-10** a fifth exported door | 🔴 **OPEN** — fifth round, re-measured §4 |
| **B18-11** `canon` uncalled; the refuted docstring | 🔴 **OPEN** — verbatim unchanged, **and dropped from the register** |

**4 clean of 11 = 36%; 41% with the partial at half.**
Series: `14, 10, 8, 27, 54, 25–37, 22–28,` **`36–41`**.

### 6b · introduced, per changed line, and the executed-vs-argued ratio

The delta touched **exactly one file in my scope**: `test_cp1_membrane.py`, **+82 / −0 = 82 changed
lines**, all test. **Zero source lines** in `agentruntime/`; **zero** in the gate script.

| definition | count | per 100 changed lines |
|---|---|---|
| code/guard findings introduced (**B19-1**, **B19-5**) | 2 | **2.4** |
| + record findings (**B19-2**, **B19-3**, **B19-11**) | 5 | **6.1** |

Series on the code definition: `150, 4.9, 4.4, 1.1, 4.7, 2.5,` **`2.4`**. It is flat, and R18-B's
warning applies again with force: **two consecutive deltas in this scope have changed no source
line at all**, so the denominator normalises against work that could not introduce a source defect.
Raw introduced across eleven rounds: `2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2` — **still no direction.**

### **Executed vs argued — 4 : 3, and the argued ones are 0/3 correct**

| load-bearing claim in the graded delta | established by | correct? |
|---|---|---|
| deleting the C-12 wrapper preserves the class and reads green; downgrading loses `.field_path` at three doors | **EXECUTION** (probe reported) | ✅ |
| `members: ['ghost']` trips M5 before the clause; a **resolving** member separates them | **EXECUTION** | ✅ |
| `dict(r)` reproduces | **EXECUTION** | ✅ |
| the four newly-guarded checks (`Filter.field`, `OrderBy.keys`, `TakeWhileBudget.cost_field`, `pipeline = list(pipeline)`) each red | **EXECUTION** | ✅ |
| *"All three now have tests, and each reds when **the check it names** is neutered"* | **ARGUMENT** — the named site (`surface.py:72`) was never neutered | ❌ **B19-1 / B19-2** |
| the `Open, carried` list is the set of open findings | **ARGUMENT** | ❌ **B19-3** |
| A's `13/24` is a denominator of the same kind as B's `63/87` | **ARGUMENT** | ❌ **B19-11** |

**Executed 4/4 correct. Argued 0/3 correct.** R18-A measured this axis at 1:1 and found the same
polarity; at n=7 it is unchanged and it is now the only metric in this run that has separated true
claims from false ones every time it has been applied. **A rate cannot see it, and both rates in
this verdict are flat.** Steer by this and by the mechanical census in CI.

### 6c · 🔮 **the prediction, and what falsifies it**

> **P19-B1.** R20's delta will close **B19-1** at the site I named — a test that reds when
> `surface.py:72`'s `out.append(dict(r))` becomes `out.append(r)` — and **the class will survive**.
> On R20's artifact, neutering `manifest.py:409` (`validate_document`'s `rows = list(rows)`) and
> `surface.py:595` (`_narrow`'s `rows = list(rows)`) **one at a time** will each still leave
> `tests/test_cp1_membrane.py` at **`0 failed`**.
>
> **Falsified if** either neutering reds. **Confirmed if** both stay green. Today both are GREEN,
> measured in §3a's census. The class is *"a defensive copy or materialisation with no test"*; the
> delta guarded the third of its three members and the run's record on siblings is 1-of-N, six times
> running.

> **P19-B2** *(secondary, one command).* The silent-site count will not fall by more than the number
> of findings this verdict names. Re-running my census on R20's artifact will report **≥ 16 silent
> of ~92** (today: 19). **Falsified if** it reports ≤ 15 — which would mean the census was
> mechanised rather than mined one finding at a time, and would be the best outcome available.

---

## Bypass table

| property the delta claims | bypass found | evidence | reachability |
|---|---|---|---|
| C-12's structured fields survive `check_row`'s re-raise | **none** — reds on downgrade **and** deletion, asserting the PATH | 2 mutations × 5 tests, suite each time | — |
| a tool with **resolving** members is refused at three doors | **none** — clause removed ⇒ `DID NOT RAISE`, nothing else fires | 1 mutation, 3 doors | — |
| `dict(r)` now has a test that reds when the check it names is neutered | **yes** — the named site (`surface.py:72`) neutered ⇒ `134 passed` | 2 sites × behaviour probe × suite | guard-only → prod at CP-2 |
| the new copy test adds coverage | **yes** — `manifest.py:448` already had a red-able test | pre-existing test alone: `1 failed` | — |
| `Filter`/`OrderBy`/`TakeWhileBudget`/`pipeline` are guarded | **none** — each reds alone | 4 mutations, `1 failed` each | — |
| …and the failure names which one | **yes** — identical `DID NOT RAISE <class 'ValueError'>` for all three | 3 states | guard-only |
| `ROW_REQUIRED ⊆ emitted ⊆ ROW_FIELDS` gates the writer | **yes, unchanged** — 0 of 2 with the assertion neutered | 2 injections × ON/OFF + control | guard-only |
| the eleventh guard serves *"what CP-2 and CP-4 need"* | **yes, unchanged and wider than recorded** — 2 tests red per field, 4 for `cost` | 5 field injections | guard-only, CI-blocking at CP-2 |
| `OrderBy` keys are `(field, direction)` pairs | **yes** — a mutable list pair and a self-deciding tuple subclass both construct | behaviour probe, `134 passed` | guard-only → prod at CP-2 |
| every row-reader goes through `check_row` | **yes** — a fifth exported door serves an invalid row | injected door, suite + gate green | structural |
| the record names every open finding | **yes** — B18-8 and B18-11 absent | census + docstring read | process |

## Red-ability table — **my own denominator, derived mechanically**

| | count |
|---|---|
| `raise` statements enumerated by AST across 8 modules | **68** |
| structural invariants with no `raise`, each with its own anchored edit | **24** |
| **denominator** | **92** |
| red-able (the membrane suite fails when the site is neutered) | **73 — 79%** |
| silent | **19** |

Bucketed in §3a. R18-B: 63/87 (72%). The rise is the four sites this delta guarded plus a
differently-cut structural set; **the silent sets agree**, which is the useful part.

## Sibling table — *a correction applied to one member of a set*

| correction | members | applied to | missed |
|---|---|---|---|
| **a defensive copy of a validated row** | `manifest.py:448` ✅ (already had one), **`surface.py:72`** ✗ | **0 of 1 new** | 🔴 **B19-1** |
| re-raise preserving the C-12 class | `validate_document` ✅, `build` ✅, `check_row` ✅ | **3 of 3** | — ✅ |
| a stage parameter must be non-empty as well as well-typed | `TopK.k` ✅, `Filter.field` ✅, `OrderBy.keys` ✅, `TakeWhileBudget.cost_field` ✅, **`OrderBy` pair shape** ✗ | **4 of 5** | 🔴 **B19-4** |
| exact-type pins against a `str` subclass | stages ✅, **row keys** ✗, **row members** ✗ | 1 of 3 | 🔴 **B18-8**, dropped |
| materialise before validating | `validate_document.rows` ✅, `rows_of` ✅, **`assemble.pipeline`** ✅ | **3 of 3** | — ✅ |
| a gate that must not red on its own legitimate branch | the `REQUIRED_SET` gate ✅, **the eleventh guard** ✗ | 1 of 2 | 🔴 **B18-2** |
| deleting a refuted claim | the call-site comment ✅, **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 **B18-11**, dropped |
| two mechanisms, two assertions | the ranking tests ✅, **the new stage test** ✗ | 1 of 2 | 🟡 **B19-5** |
| a finding gets exactly one recorded status | commit message ✅, RUNSTATE ✅ | **2 of 2, agreeing** | — ✅ (but on a false sentence: **B19-2**) |
| every open finding appears in the register | 9 carried, **B18-8** ✗, **B18-11** ✗ | 9 of 11 | 🔴 **B19-3** |
| document-level validity at the consumer doors | `rows_of`, `declarations`, `discover`, `SurfaceAssembler` | **0 of 4** | 🔴 **B18-9** |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| property | test | reds? | for the right reason? |
|---|---|---|---|
| C-12's PATH survives `check_row`'s re-raise | `…SURVIVE_EVERY_RE_RAISE` | ✅ ×2 mechanisms | ✅ — **the best guard in this delta** |
| a tool with **resolving** members is refused | `…STILL_A_TOOL_WITH_MEMBERS` | ✅ | ✅ — `DID NOT RAISE`, no other refusal fires |
| `validate_document` returns copies | `…LEAVES_THE_VALIDATOR` + a pre-existing test | ✅ | 🟡 duplicate of an existing guard |
| **`rows_of` returns copies** | **none** | **n/a** | 🔴 **B19-1** — the site the finding named |
| a filter names the field it reads | `…MUST_NAME_THE_FIELD…` | ✅ | 🟡 message cannot distinguish (**B19-5**) |
| an order_by names at least one field | same test | ✅ | 🟡 same |
| a budget names the field it accumulates | same test | ✅ | 🟡 same |
| **an order_by key is a `(field, direction)` pair** | **none** | **n/a** | 🔴 **B19-4** |
| a generator pipeline is materialised | `…NOT_A_SILENT_NO_OP` | ✅ | ✅ |
| naming a field does not make it mandatory | `…NOT_MAKE_IT_MANDATORY` | ✅ ×3 | 🔴 **also reds on the legitimate path (B18-2)** |
| the writer's keys sit between REQUIRED and ALLOWED | `…ACTUALLY_EMITS` | **NO** (0 of 2) | 🔴 **B18-1** |
| a row key / member may not be a `str` subclass | **none** | **n/a** | 🔴 **B18-8**, dropped |
| a declaration id has a bounded length | **none** | **n/a** | 🟡 **B19-12** |
| document-level validity at the consumer doors | **none** | **n/a** | 🔴 **B18-9**, carried |
| a fifth row-reading door | **none** | **n/a** | 🔴 **B18-10**, fifth round |
| `canon` is called by something | **none** | **n/a** | 🔴 **B18-11**, dropped |

## Reachability verdict on every finding

| # | finding | bucket | introduced by the graded delta |
|---|---|---|---|
| **B19-1** | the `dict(r)` guard landed on `manifest.py:448`; `surface.py:72` — the named site — is silent at `134 passed`, and the duplicated site already had a test | guard-only → **prod-reachable at CP-2** | **YES** |
| **B19-2** | both records claim *"each reds when the check it names is neutered"*; false for the third | process | **YES** |
| **B19-3** | B18-8 and B18-11 open, unfixed, absent from the register — B17-8, third round | process | **YES** |
| **B19-4** | `surface.py:305` unguarded: a mutable list pair and a self-deciding tuple subclass both become ordering keys | guard-only → **prod-reachable at CP-2** | no |
| **B19-5** | one test stands for three clauses with an identical message, against the file's own stated rule | guard-only | **YES** |
| **B19-8** | a fifth exported row-reading door passes suite and gate — B4, fifth round; `runtime_variant` already ships the socket | structural | no |
| **B19-11** | A's `13/24` (closure) filed beside B's `63/87` (census) as one kind of number | process | **YES**, mildly |
| **B19-12** | `_ID` has no length bound; a 300-character id is written to a row in the control | adversarial-only | no |
| **B18-1** | the subset gate contributes 0 of 2 — **P18-B2 HELD** | guard-only | no (carried) |
| **B18-2** | the eleventh guard reds on CP-2's first operation — **P18-B1 HELD**, and on 2 tests, 4 for `cost` | guard-only (**CI-blocking at CP-2**) | no (carried) |
| **B18-8** | a `str` subclass key/member walks past four silent sites | adversarial-only | no |
| **B18-9** | `rows_of`'s document gap, four exported doors, 5/5 shapes | **production-reachable** (at CP-2) | no (carried) |
| **B18-11** | `canon` uncalled and unexported; `nfc()`'s docstring carries the refuted claim verbatim | doc / adversarial-only | no |

**1 production-reachable · 2 adversarial-only · 6 guard-only/structural · 4 process · total 13 ·
introduced 2 (code/guard) / 5 (with the record).**

---

## What I would fix first

1. **B19-1** — a test that reds when `surface.py:72` becomes `out.append(r)`, and **correct both
   records**. The finding gave the file, the line and the mutation; the fix went one module over to
   a site that was already covered. Until this is done, `dict(r)` is recorded closed and is not.
2. **B19-3** — put B18-8 and B18-11 back in the register. Two rounds ago the failure was two records
   disagreeing; this round it is two records agreeing about a subset. **The register needs a
   mechanical source**: the union of every open finding across the verdicts, generated, not typed.
3. **B18-2**, one line — anchor the eleventh guard's probe on `ROW_FIELDS = MappingProxyType({` and
   insert after it. And **decide `test_EVERY_ROW_FIELD_IS_BOUNDED`'s four ranking rows now**, because
   they are the second test that goes red on `relevance` and the first thing CP-2 will hit.
4. **B19-4** and **B18-8** — `OrderBy`'s pair shape and the two `str`-subclass pins. Both are
   §0.14.1's own subject reaching a **row** or a **ranking**, and all six sites are silent.
5. **The census, in CI.** Two independent verifiers have now enumerated it mechanically (87 and 92)
   and **agree on the silent set**. That is the first coverage number in this run that is not a
   property of who looked hardest — and it will stay a verdict artifact until it is a script.
   With it, **B18-10 / B4** becomes expressible: every function that reads a row field calls
   `check_row`, or is `check_row`, or is reached only via `rows_of`.

---

**Files touched by this verifier: this file only.** `git status` over `services/chat-service/`,
`scripts/`, `contracts/` and `docs/plans/` is **empty**; the real-tree suite is `134 passed` and the
gate exits 0 at finish; nothing committed. All injections were made in a fresh full-layout replica
under the session scratchpad and restored from my own pristine copy. **No `git checkout` was used at
any point.**

`git rev-parse HEAD` = `5b531e22ae93f52cc45f55741b3016b76d754691` — **unmoved.**
