# CP-1 · round 18 · V-CODE · **Verifier B — the membrane**

**Artifact:** `2faa88bacd48340d6ba0ce87dcc8dd471f73c88d`
`git rev-parse HEAD` **at start:** `2faa88bacd48340d6ba0ce87dcc8dd471f73c88d`
`git rev-parse HEAD` **at finish:** `2faa88bacd48340d6ba0ce87dcc8dd471f73c88d` — **unmoved.**

**Graded delta:** `8a84f78e1` + `9453c9f86` against `6761cf013`.
**Scope:** `services/chat-service/app/agentruntime/`, `scripts/agentruntime-membrane-gate.py`,
`services/chat-service/tests/test_cp1_membrane.py`.

**Method.** Every claim below was **executed**. All injections were made in a fresh scratch replica
with the real repo layout (`services/chat-service/`, `scripts/`, `contracts/`, `.github/workflows/`)
so the repo-path-dependent tests run rather than being deselected — the scratch baseline is
**`129 passed`, identical to the real tree**, and no test was excluded from any measurement. Every
injection asserts its anchor count **before** writing and asserts the text **present in the file**
afterwards; a mismatched anchor aborts rather than silently producing an inert run. Restoration is
from **my own pristine copy**, never `git checkout`. Final state: all ten scope files verified
**byte-identical by md5** to the snapshot taken at start; `git status` over `services/chat-service/`,
`scripts/` and `contracts/` is empty.

**Baseline:** `129 passed`; membrane gate **green** (`8 module(s), 0 allowed external import(s),
2 single-sited type(s)`).

---

## Verdicts

| # | claim | verdict |
|---|---|---|
| 1 | `ROW_REQUIRED ⊆ emitted ⊆ ROW_FIELDS` replaced the equality — verify each half fires; check the optional tier end to end | **The round trip WORKS, executed — and NEITHER HALF FIRES.** The migration is real: an old-schema manifest with distinct origins `0.9.0`/`0.8.0`, `salience` added as **optional AND emitted**, the *ordinary* `generate(path=existing)` — **no `rm`, no `bootstrap`** — round-trips and **`ORIGIN STAMPS SURVIVED: True`**. B17-1's runtime half is closed and the gate no longer reds on it. **But the new assertion is a tautology**: both halves are pre-empted by `_row`'s own `check_row`, and neutering the assertion to `assert True` leaves **both** drift injections RED anyway → **B18-1** |
| 2 | The eleventh guard exists and re-executes the module source — does it red for the reason it names, and stay silent on an unrelated edit? | **BOTH HALVES OF THAT ARE TRUE — and it reds on the one path it exists to enable.** It reds for its stated reason on **three independent mechanisms** (literal → `frozenset(ROW_FIELDS)`; the required loop reading `ROW_FIELDS`; the literal unioned with `ROW_FIELDS`), each with the exact `salience: is missing` message. It is **GREEN on 4 of 4 unrelated edits** to `contract.py`. **But CP-2 adding `relevance` to `ROW_FIELDS` — the operation the docstring names — reds it**: `AssertionError: the schema literal moved; this probe is stale`. So does a pure reordering of `ROW_FIELDS` that changes no membership → **B18-2** |
| 3 | *"Two of the four unguarded holes did not reproduce."* Re-measure with your own probe | **ALL THREE REPRODUCE.** G9 (`check_row`'s C-12 re-raise): downgrading it loses `.field_path` at **all three** doors simultaneously, suite `129 passed`. G22 (tool with **resolving** members): removing the clause **ACCEPTS** `['t0','t1']` at `rows_of`, at `validate_document` and at `admit()`, suite `129 passed`. G48 (`dict(r)`): caller mutation reaches the source document, suite `129 passed`. **I can also show exactly how the builder's probe missed each** — §3 → **B18-4**. And the two records disagree about *which* two → **B18-3** |
| 4 | `rows_of` runs no document-level stamp check — re-test the scoping; reachable today by any exported path? | **5 of 5 shapes, and now measured at FOUR exported doors, not one.** `rows_of`, `declarations`, `discover` **and** `SurfaceAssembler` all accept every document `validate_document` refuses — all four are in `__all__`. Repo-wide: **nothing outside the package imports `agentruntime`** (only the gate script), so it is **not production-reachable today** and CP-2 ownership stays defensible — but "not reachable" rests on the absence of one import statement, not on the doors → **B18-9** |
| 5 | Find the fifth unguarded load-bearing check, with your own denominator | **Found, and it decides the surface.** `surface.py:185` — *a filter must name the field it reads*. Removing it leaves the suite at `129 passed`, and `Filter(field="")` then **narrows the surface to ZERO** (`names=[] withheld=4`) under `op="eq"` and to **NOTHING AT ALL** (`names=[t0,t1,t2,t3] withheld=0`) under `op="not_in"` → **B18-5**. Two more of the same weight: `OrderBy(keys=())` silently falls back to id-order, which its own docstring forbids by name (**B18-6**), and dropping `pipeline = list(pipeline)` makes a **generator pipeline a silent no-op** — verbatim the defect the comment above it says a verifier measured (**B18-7**). **My denominator: 87 guards, 63 red-able (72%)** |
| 6 | Convergence, and a prediction this run can settle | **Closure 22% clean / 28% with partials** — `14, 10, 8, 27, 54, 25–37,` **`22–28`**. 2 clean closures of 9 (**B17-1**, **B17-7**), both with residuals; **6 open, 1 partial**. Introduced 2 code findings on 79 changed lines = **2.5 per 100** (4 if the record findings count = 5.1). Prediction stated in §6, settleable by one command |

**Overall: FAIL** — on **B18-2**, which is **B17-1's exact defect recurring one test to the left,
inside the delta that fixed B17-1**; and on **B18-4**, a self-measurement wrong in the flattering
direction for the **fifth** consecutive round, this time a *non-reproduction* claim that fails on
all three of its subjects.

**Two things in this delta are genuinely good and belong first.** The optional-tier migration is
**real and I performed it**, not read: origins survive an ordinary schema-forward regeneration.
And the eleventh guard — the one the builder had declared impossible — is a **correctly built
guard**: it reds on three separate mechanisms of the property and is silent on four unrelated edits
to the same file. That is a better guard than the one it was asked for.

---

## Falsifiers, stated before the search

| claim | what would have falsified it |
|---|---|
| 1 | either half firing as an `AssertionError`; the migration losing an origin stamp; any consumer door refusing an old-schema row |
| 2 | the guard staying green under `ROW_REQUIRED = frozenset(ROW_FIELDS)`; reddening on an edit unrelated to the property |
| 3 | any of the three holes staying GREEN under my own mutation, or the behaviour probe showing no accept/reject change |
| 4 | an importer outside the package; any of the five shapes now refused at any of the four doors |
| 5 | every remaining unguarded site being redundant with a guard that already reds |
| 6 | closure rising while introduced-per-line fell |

---

## 1 — the subset gate, and the migration

### 1a · ✅ the optional tier round-trips end to end — **executed, not argued**

`salience` added to `ROW_FIELDS` **and emitted by `_row`** as a source edit (CP-2's real change,
including its producer per §0.14.1c), `ROW_REQUIRED` untouched. Injections verified present in the
file before anything was trusted:

```
ROW_FIELDS gains salience (OPTIONAL) : True
_row EMITS salience                  : True
ROW_REQUIRED untouched               : True
optional tier                        : ['salience']
```

The manifest on disk was written under the **old 7-field schema** with **deliberately distinct**
stamps, so "the origins survived" is falsifiable rather than a tautology against the live constant:

```
ON DISK row0 keys : ['admitted_against','contract_version','id','kind','lifecycle','members','owning_service']
ON DISK origins   : {'book_get': '0.9.0', 'book_list': '0.8.0'}

OLD-SCHEMA FILE  load()               -> OK
OLD-SCHEMA FILE  rows_of()            -> OK
OLD-SCHEMA FILE  declarations()       -> OK

generate(path=existing)               -> OK       <- the ORDINARY route. No `rm`. No `bootstrap`.
  row0 keys after migration           : [... ,'owning_service','salience']
  salience present in written rows    : True
  origins after migration             : {'book_get': '0.9.0', 'book_list': '0.8.0'}
  *** ORIGIN STAMPS SURVIVED          : True ***
  re-load of the migrated file        -> OK, origins = {'book_get': '0.9.0', 'book_list': '0.8.0'}
  rows_of on the migrated file        -> ['book_get', 'book_list']
```

**B17-1's runtime half is closed and its gate half is fixed** — the `<=` change does exactly what it
was asked to do. Full suite under the optional-and-emitted field: **`1 failed, 128 passed`**, and the
one failure is **not** this gate. It is the new eleventh guard (§2).

### 1b · 🔴 **B18-1 — neither half of the new assertion can fire**

`test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS__and_no_more`
(`test_cp1_membrane.py:1105-1128`) asserts `set(ROW_REQUIRED) <= emitted <= set(ROW_FIELDS)`.
`emitted` is the key set of `build(...)["declarations"][0]`, which is exactly the dict `_row`
produced — and `_row`'s last statement is `check_row(row, "row")`, whose shape half enforces
*precisely* those two inclusions. I drove both halves:

| injection | what the test reports |
|---|---|
| a REQUIRED field the writer does not emit | `ContractViolation: … salience: is missing` at **`contract.py:232`** |
| the writer emits a field the schema does not define | `ContractViolation: … is a field the contract does not define` at **`contract.py:224`** |

Neither is the assertion. The redundancy is measured, not inferred — I neutered the assertion to
`assert True` and re-ran both:

| injection | gate ON | gate OFF |
|---|---|---|
| required-not-emitted | RED (`ContractViolation`) | **RED (identical)** |
| emitted-not-allowed | RED (`ContractViolation`) | **RED (identical)** |

**The assertion contributes 0 of 2.** It becomes load-bearing only when `_row`'s own `check_row` is
*also* removed — with `G24` applied, both injections finally report
`AssertionError: the writer emits […]`. And the inclusion is not merely usually true, it is
*provably* true: brute-forcing all key subsets of `ROW_FIELDS ∪ {ghost}` through `check_row_shape`,

```
key-subsets enumerated                      : 256
accepted by check_row_shape                 : 1
accepted AND violating the subset inclusion : 0
```

The predecessor's finding was that `emitted == ROW_REQUIRED` was *"`frozenset(ROW_FIELDS)` moved
from the definition into the test"*. The replacement is `check_row_shape` moved from the definition
into the test — an assertion that restates the guard on the line above it. The comment at
`contract.py:195-199` still calls it *"a **gate** rather than a definition"*; it is neither, it is a
transcription. The old assertion was **wrong**; this one is **empty**, and empty is harder to notice.

**Reachability: guard-only.** **Introduced by the graded delta: YES** — reverting restores an
assertion that could fail.

---

## 2 — the eleventh guard

### 2a · ✅ it reds for the reason it names, on three mechanisms, and only for that reason

The prompt asks two questions and both answers are good. I did not settle for the one mutation the
builder wrote it against — I broke the same property three different ways:

| mutation of *"naming a field does not make it mandatory"* | result |
|---|---|
| `ROW_REQUIRED = frozenset(ROW_FIELDS)` (the reverted state) | **RED** — `t0.row.salience: is missing` |
| the required loop reads `sorted(ROW_FIELDS)` instead of `ROW_REQUIRED` | **RED** — identical message |
| `ROW_REQUIRED` literal unioned with `frozenset(ROW_FIELDS)` | **RED** — identical message |

…and stayed silent on every unrelated edit to the same file:

| unrelated edit to `contract.py` | result |
|---|---|
| add a module constant | **GREEN** |
| a trailing comment on `_ID` | **GREEN** |
| reword an unrelated docstring | **GREEN** |
| reformat the `KINDS` literal across lines | **GREEN** |

**That is a correctly built guard**, and it guards a property the builder had declared unguardable.
It should be said plainly: the round was asked to build something it had argued was impossible, and
what it built is stronger than the single mutation it was asked for.

### 2b · 🔴 **B18-2 — and it reds on the one path it exists to enable**

The probe's first statement is `assert src.count(anchor) == 1` over the anchor
`'    "members": (list, tuple),\n})'` — the **last entry** of the `ROW_FIELDS` literal. Adding a
field appends after `members`, so the anchor count goes to 0:

| the legitimate path | result |
|---|---|
| CP-2 adds `relevance` to `ROW_FIELDS` | 🔴 **RED** — `AssertionError: the schema literal moved; this probe is stale` |
| CP-2 adds `relevance` **with its producer** (§0.14.1c) | 🔴 **RED** — identical |
| `ROW_FIELDS` keys **reordered**, membership identical | 🔴 **RED** — identical |

The docstring says the property *"is what CP-2 and CP-4 need: `relevance`, `lane`, `tier` and `cost`
all arrive on rows that already exist"*. **The first of those four arrivals reds this test.** It is
the same sentence B17-1 was written about — *a gate that reds on the legitimate branch it exists to
enable* — recurring one test to the left inside the delta that fixed B17-1. Sixth instance of
applying a correction at the member a verifier named rather than at the class.

Severity is genuinely lower than B17-1's: the message is honest, names the cause and is one line to
fix. But the guard whose entire subject is *"a field can be added to `ROW_FIELDS`"* is **anchored to
a literal that adding a field to `ROW_FIELDS` destroys**, and the failure is indistinguishable from
a real regression until someone reads it.

**A robust anchor exists, so this is a defect and not a limit.** Anchoring on the literal's
**opening** (`ROW_FIELDS = MappingProxyType({`) and inserting after it survives an appended field,
a reorder, and a type change — the injection is still a source edit and the probe still separates
the two states exactly.

**Reachability: guard-only, CI-blocking at CP-2.** **Introduced: YES** — the test is new in
`9453c9f86`.

---

## 3 — claim 2 re-measured: **all three reproduce**

### 3a · the measurements

Control is the pristine artifact; each mutation restored from my own snapshot, injection asserted
present first, full suite run after.

| hole | mutation | behaviour | suite |
|---|---|---|---|
| **G9** `check_row`'s C-12 re-raise (`contract.py:298-300`) | downgrade to a flat `UntrustedRow` | `rows_of` / `validate_document` / `build(previous=)` **all three** go `ContractViolation, field_path='declarations[0].kind'` → `UntrustedRow, field_path=None` | **`129 passed`** |
| **G22** tool-with-members (`contract.py:367`) | remove the clause | a tool with a **resolving** member is **ACCEPTED**: `rows_of → ['t0','t1']`, `validate_document → ['t0','t1']`, `admit() → 't0'` | **`129 passed`** |
| **G48** `dict(r)` (`surface.py:72`) | `out.append(r)` | caller mutation of a returned row reaches the source document: `False → True` | **`129 passed`** |

### 3b · 🔴 **B18-4 — and I can show how each probe missed**

A non-reproduction is only worth as much as the probe behind it, so I reconstructed both.

**G9.** There are two ways to "break the re-raise" and they measure different things. *Deleting* the
wrapper lets the inner `ContractViolation` propagate — the class and `.field_path` survive, and the
probe reads GREEN:

```
G9b  wrapper DELETED : ContractViolation  field_path='kind'          <- looks preserved
G9a  class DOWNGRADED: UntrustedRow       field_path=None            <- the actual property
control              : ContractViolation  field_path='declarations[0].kind'
```

Deletion tests whether the wrapper is *necessary for the class*; the finding is whether the class is
*guarded*. **And even the deletion is a real loss**: the field path degrades from
`declarations[0].kind` to `kind` — C-12's whole requirement is *name the field path* — and the suite
is green for that too.

**G22.** The package's stock bad-member fixture is `members: ['ghost']`, which does not resolve. Run
that against the neutered clause and it *is* refused — by **M5**, not by the clause:

```
G22 applied, member 'ghost'  (unresolving) -> UnresolvedReference     <- reads as "still refused"
G22 applied, member 't1'     (resolving)   -> ACCEPT ['t0','t1']      <- the actual hole
```

R17-B's finding says **resolving** in its title. A probe that uses the unresolving fixture cannot see
it, and it will read as a clean refusal every time.

**G48** was recorded UNREPRODUCED in one record and is plainly reproducible in three lines.

### 3c · 🔴 **B18-3 — the two records name different holes**

* `9453c9f86`'s message: *"C-12's structured fields survive `check_row`'s re-raise at both doors,
  **and a tool carrying resolving members is refused at both**."*
* `RUNSTATE:1747`: *"two of B's four unguarded holes (C-12 fields at `check_row`'s re-raise;
  **`dict(r)`**) did not reproduce."*

Three distinct holes across two "two"s. Whichever is authoritative, **one open finding has no
recorded status at all** — which is precisely the B17-8 failure mode ("a finding that is neither
closed nor carried has been forgotten") recurring in the same document that carries B17-8's fix.
All three reproduce, so the practical answer is the same; the record integrity problem is not.

**Reachability: guard-only** for G9/G22/G48 (today's behaviour is correct at every door);
**process** for B18-3. **Introduced: no** for the holes; **YES** for the record.

---

## 4 — `rows_of` and the document level

| document shape | `rows_of` | `declarations()` | `discover()` | `SurfaceAssembler` | `validate_document` |
|---|---|---|---|---|---|
| no `manifest_version` | ACCEPT | ACCEPT | ACCEPT | ACCEPT | `UntrustedRow` |
| `manifest_version: 999` | ACCEPT | ACCEPT | ACCEPT | ACCEPT | `UntrustedRow` |
| `contract_version: "banana"` | ACCEPT | ACCEPT | ACCEPT | ACCEPT | `UntrustedRow` |
| no `contract_version` | ACCEPT | ACCEPT | ACCEPT | ACCEPT | `UntrustedRow` |
| undefined top-level key | ACCEPT | ACCEPT | ACCEPT | ACCEPT | `UntrustedRow` |

**5 of 5, at four exported doors** — R16-B and R17-B measured this at `rows_of` and
`SurfaceAssembler`; `declarations` and `discover` are in `__all__` too and diverge identically.
Repo-wide sweep for importers of `agentruntime` outside the package: **none** — the only references
are `scripts/agentruntime-membrane-gate.py` and the CI workflow that runs it.

**Verdict on the scoping: still honest, and one import statement from stopping being so.** Not
production-reachable today; owner CP-2 is defensible. But "the exported API of this package accepts
five malformed documents at four doors" is a different sentence from "one door has a gap", and the
register carries the second. → **B18-9. Reachability: production-reachable at CP-2.**

---

## 5 — the fifth unguarded check, and my denominator

### 5a · the denominator, derived mechanically

I did not inherit R17-B's 48. I enumerated **every `raise` in the package by AST** — all eight
modules, not the three the predecessor scoped — and neutered each one to `pass`, one at a time,
against the full suite: **68 sites.** To that I added **19 structural invariants that have no
`raise`** (the three C-12 re-raises as *class downgrades* rather than deletions, the `dict(r)` copy,
`MappingProxyType`, the `ROW_REQUIRED` literal, the three hierarchy edges, `_row`'s self-check, the
rebuilt document return, the two stamp re-reads, three materialisations, the P4 origin carry, two
exact-type pins, and the subset gate itself). **Denominator: 87.**

### **63 / 87 red-able (72%).** 24 unguarded: **13 real** · **3 carried** · **2 dead** · **2 latent at CP-4** · **3 redundant** · **1 low**

| bucket | sites |
|---|---|
| 🔴 **real, reachable through an exported door** | `contract.py:221`, `contract.py:255`, `contract.py:368` (G22), `contract.py:381`, `surface.py:185`, `surface.py:302`, `surface.py:305`, `check_row` C-12 downgrade (G9), `dict(r)` (G48), `pipeline = list(pipeline)` |
| 🔴 **real, but `canon` is uncalled and unexported** | `canon.py:60`, `canon.py:71`, `canon.py:84` |
| 🟡 carried | `manifest.py:310` (the `exists`→`load` race), document stamps re-read (B7), the subset gate (B18-1) |
| 🟡 dead handlers (B17-4) | `manifest.py:245`, `manifest.py:428` |
| 🟡 latent at CP-4 | `surface.py:389`, `surface.py:391` — refused today only because no row carries `cost`; `§0.14.1c` schedules it |
| 🟢 redundant | `manifest.py:408`, `rows = list(rows)`, `rows_of`'s `_is_exactly` |
| 🟢 low | `manifest.py:297` (no manifest location) |

### 5b · 🔴 **B18-5 — the fifth: `a filter must name the field it reads`** (`surface.py:185`)

Removing it leaves the suite at **`129 passed`**, and the construction it then admits decides the
whole surface:

```
control : Filter(field='') eq 'x'        CONSTRUCTION REFUSED  ValueError: a filter must name the field it reads
mutated : Filter(field='') eq 'x'        CONSTRUCTED -> names=[]                   withheld=4
mutated : Filter(field='') not_in ('x',) CONSTRUCTED -> names=['t0','t1','t2','t3'] withheld=0
control : Filter(field='owning_service') eq 'svc1' -> names=['t1'] withheld=3
```

A filter naming no field reads `row.get("")` — `None` on every row — so under `eq` it **withholds
the entire surface** and under `not_in` it **withholds nothing while registering as a narrowing**.
Both are arm E's shape: the model's surface decided by something nobody named, with a
`{tool, stage, reason}` record that reads like a policy. `Filter.field` is the operand
`_plain(self.field, str, "field")` was added for two rounds ago; the *emptiness* half of that
sentence has no test. **Reachability: guard-only today; production-reachable at CP-2.**
**Introduced: no.**

### 5c · 🔴 **B18-6** — `OrderBy(keys=())` (`surface.py:302`)

`129 passed` with the check removed, and `effective_keys()` then returns `(('id','asc'),)` — the
implicit tie-break alone. The class docstring, eight lines above, says *"a missing field is a
REJECTION, not a fallback: **silently falling back to id-order reorders the whole surface and cuts
different declarations**."* The guard against the exact case the docstring names is unguarded.
`OrderBy` is what every rank-dependent stage consumes. **Reachability: guard-only.** **Introduced: no.**

### 5d · 🔴 **B18-7** — `pipeline = list(pipeline)` (`surface.py`, `assemble`)

`129 passed` with the materialisation removed, and:

```
control : GENERATOR pipeline  names=['t1']                 withheld=3
mutated : GENERATOR pipeline  names=['t0','t1','t2','t3']  withheld=0
```

The comment directly above it says *"passing a bare **generator** made the entire pipeline a silent
no-op, a `Filter` keeping one declaration returning all four."* That is exactly what I measured, and
**there is no test for it** — the module records the defect and guards it, and nothing would notice
the guard leaving. **Reachability: guard-only.** **Introduced: no.**

### 5e · 🔴 **B18-8 — two sites R17-B marked *redundant* are not**

| site | R17-B | measured here |
|---|---|---|
| `contract.py:221` non-string key (its G7) | 🟡 redundant — *"`key not in ROW_FIELDS`"* | 🔴 **real**: a `str` **subclass** key whose `__eq__`/`__hash__` spell `"id"` **IS** in `ROW_FIELDS`, so only `type(key) is not str` stops it. Neutered → `ACCEPT ['t0']` |
| `contract.py:255` members element (its G6) | 🟡 redundant — *"`check_contract` catches"* | 🔴 **real**: `check_contract` uses `isinstance(m, str)`, which welcomes the subclass. Neutered, a **skill** row with a `str`-subclass member → `ACCEPT ['s0','t1']`. Only the *empty-string* half is redundant |

Both are the §0.14.1 class the module is built around — *a closure wearing a value's clothes* —
reaching a **row** rather than a stage. Adversarial-input only (a Python caller, not JSON), which is
why they read as redundant when the probe uses a plain scalar. **Introduced: no.**

### 5f · 🔴 **B18-10 — B4 is unchanged, fourth round**

I appended a fifth exported row-reading door to `surface.py` and added it to `__all__`. It served
`{'id':'x','kind':'gadget','cost':10**9}` — a row failing three clauses and the closed schema — as
`['x:gadget']`, with **`129 passed`** and **gate exit 0**. Nothing in the suite or the gate requires
a row-reader to go through `check_row`. **Reachability: structural.** **Introduced: no.**

### 5g · 🔴 **B18-11 — `canon` is now an uncalled module, and B17-2 is unchanged**

Zero call sites for anything in `canon.py` from the rest of the package, and `canon` is **not in
`__all__`** — B17-2 named `nfc()`; it is the whole module. `nfc()`'s docstring still asserts the
refuted claim **verbatim** (*"two `digest` values for one visibly identical document"*), unchanged
in this delta. Three of its four `raise` sites are unguarded, and the fourth matters:
`digest(object())` with the fallthrough removed returns
`04d3fc18…` — **the same digest as `digest(None)`**, because `_norm` then falls off the end and
returns `None`. A value with no canonical form silently hashing as `null` is a collision, not a
refusal. Not reachable through the package's exported API today. **Introduced: no.**

---

## 6 — convergence, and **the prediction**

### 6a · closure of R17-B's nine findings, re-measured against this artifact

| R17-B finding | now |
|---|---|
| **B17-1** gate reds on the OPTIONAL branch | ✅ **CLOSED** — round trip executed, origins survived, the gate is silent on it (residual **B18-1**, **B18-2**) |
| **B17-2** `canon.nfc()` uncalled, docstring carries the refuted claim | 🔴 **OPEN** — verbatim unchanged; now the whole module (**B18-11**) |
| **B17-3** `check_row`'s C-12 re-raise unguarded | 🔴 **OPEN** — reproduced; recorded UNREPRODUCED (**B18-4**) |
| **B17-4** `except UntrustedRow` at `manifest.py:244` dead | 🔴 **OPEN** — still green, still unreachable |
| **B17-5** `dict(r)` unguarded | 🔴 **OPEN** — reproduced |
| **B17-6** tool-with-members unguarded | 🔴 **OPEN** — reproduced with a **resolving** member |
| **B17-7** the eleventh guard is guardable today | ✅ **CLOSED** — built, red on 3 mechanisms, silent on 4 unrelated edits (residual **B18-2**) |
| **B17-8** open findings dropped from the register | 🟡 **PARTIAL** — some carried; **B4** and **B8** still unnamed, and a new record split (**B18-3**) |
| **B17-9** `rows_of` no document-level check | 🔴 **OPEN** — 5/5, now at four exported doors |

**2 clean of 9 = 22%; 28% with the partial at half.** Series: `14, 10, 8, 27, 54, 25–37,` **`22–28`**.

### 6b · introduced, per changed line

The delta touched **exactly one file in my scope**: `test_cp1_membrane.py`, `+74 / −5` = **79 changed
lines**, all test. No source file in `agentruntime/` and no line of the gate script changed.

| definition | count | per 100 changed lines |
|---|---|---|
| code/guard findings introduced (**B18-1**, **B18-2**) | 2 | **2.5** |
| + record findings (**B18-3**, and B18-4's claim) | 4 | **5.1** |

Series on the code definition: `150, 4.9, 4.4, 1.1, 4.7,` **`2.5`**. It fell, and I do not think that
means anything — a delta of 79 test lines and no source lines cannot introduce a source defect, so
the normalisation flatters a delta that shipped nothing to normalise. **Raw introduced reads
`2, 1, 2, 1, 3, 2, 4, 3, 2, 2` — still no direction across ten rounds.** The one number that moved
against the delta is the one that could: **red-ability on an independent denominator, 87 guards, 24
of them silent, and 13 of those are real.**

**What I would steer by.** Not either rate. R17-B ended on the observation that every convergence
number in this series measures how hard the verifier looked, and this round is the proof: I enlarged
the denominator from 48 to 87 by running the enumeration mechanically instead of by hand, and the
new sites produced **three** load-bearing holes nobody had named — one of which decides the entire
surface. Steer by **the mechanised guard census, run in CI**, and treat closure as commentary until
the denominator stops being a property of the verifier.

### 6c · 🔮 **the prediction, and what falsifies it**

R17-B's advance prediction held, so here is one of mine, chosen to be settleable by a command rather
than by judgement.

> **P18-B1.** R19's delta will fix **B18-2** at the anchor I named — re-spelling
> `test_NAMING_A_FIELD_DOES_NOT_MAKE_IT_MANDATORY`'s anchor — and the **class** will survive: running
> the CP-2 injection on R19's artifact (`relevance` added to `ROW_FIELDS` **and** emitted by `_row`,
> `ROW_REQUIRED` untouched) will still leave **at least one** test in `test_cp1_membrane.py` red.
>
> **Falsified if** that injection yields `0 failed` on R19's artifact. **Confirmed if** ≥ 1 failure
> remains. Today the count is **1**, and the control (optional, not emitted) is also **1** — both are
> the same test, so a fix at the anchor alone moves both to 0 and falsifies me.

> **P18-B2.** **B18-1 will be closed by rewording rather than by giving the assertion content.** On
> R19's artifact, neutering the subset assertion to `assert True` and re-running the two schema-drift
> injections will still leave **both RED** — i.e. the assertion will still contribute **0 of 2**.
>
> **Falsified if** either injection goes **GREEN** when the assertion is neutered, which is what it
> means for the gate to be the only thing guarding it. The obvious way to make me wrong is to assert
> the relationship against something `check_row` does not already enforce — e.g. that
> `ROW_REQUIRED` is a **strict** subset once an optional field exists, or that the writer's key set
> is stable across a `previous=` carry.

Both settle in one command each, against R19's artifact, with no interpretation.

---

## Bypass table

| property the delta claims | bypass found | evidence | reachability |
|---|---|---|---|
| `ROW_REQUIRED ⊆ emitted ⊆ ROW_FIELDS` gates the writer's schema | **yes** — neither half can fire; `check_row` pre-empts both | 2 injections × gate ON/OFF; 256-subset brute force | guard-only |
| CP-2 can add an optional-and-emitted field and re-generate | **none** — origins survived the ordinary `generate(path=)` | executed as a source edit, distinct stamps | — |
| the eleventh guard reds when `ROW_REQUIRED` is re-derived | **none** — reds on 3 independent mechanisms | 3 mutations, identical message | — |
| the eleventh guard is silent on unrelated edits | **none** — GREEN on 4 of 4 | 4 unrelated edits to `contract.py` | — |
| the eleventh guard guards *"what CP-2 and CP-4 need"* | **yes** — CP-2's first operation reds it | 3 legitimate-path injections | guard-only, CI-blocking at CP-2 |
| C-12's fields survive `check_row`'s re-raise (unreproduced) | **yes** — downgrade loses `field_path` at 3 doors | behaviour probe, suite `129 passed` | guard-only |
| a tool with resolving members is refused (unreproduced) | **yes** — clause removed → `ACCEPT ['t0','t1']` at 3 doors | behaviour probe, suite `129 passed` | guard-only |
| `rows_of`'s gap is one door's | **yes** — four exported doors, 5/5 shapes | executed at all four | prod-reachable at CP-2 |
| every row-reader goes through `check_row` | **yes** — a fifth exported door serves an invalid row | injected door, suite + gate green | structural |

## Sibling table — *a correction applied to one member of a set*

| correction | members | applied to | missed |
|---|---|---|---|
| a gate that must not red on its own legitimate branch | the `REQUIRED_SET` gate ✅, **the new eleventh guard** ✗ | 1 of 2 | 🔴 **B18-2** |
| re-raise preserving the C-12 class | `validate_document` ✅, `build` ✅, **`check_row`** ✗ | 2 of 3 | 🔴 **B18-4 / B17-3** |
| a stage parameter must be non-empty as well as well-typed | `TopK.k ≥ 1` ✅ (RED), **`Filter.field`** ✗, **`OrderBy.keys`** ✗, `TakeWhileBudget.budget/cost_field` ✗ | **1 of 5** | 🔴 **B18-5**, **B18-6** |
| exact-type pins against a `str` subclass | stages ✅, **row keys** ✗, **row members** ✗ | 1 of 3 | 🔴 **B18-8** |
| materialise before validating | `validate_document.rows` ✅, `rows_of` ✅, **`assemble.pipeline`** ✗ | 2 of 3 | 🔴 **B18-7** |
| deleting a refuted claim | the call-site comment ✅, **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 **B18-11 / B17-2** |
| a finding gets exactly one recorded status | commit message, RUNSTATE | disagree | 🔴 **B18-3** |
| document-level validity at the consumer doors | `rows_of`, `declarations`, `discover`, `SurfaceAssembler` | **0 of 4** | 🔴 **B18-9** |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| property | test | reds? | for the right reason? |
|---|---|---|---|
| naming a field does not make it mandatory | `…NOT_MAKE_IT_MANDATORY` | ✅ ×3 mechanisms | ✅ — **but also reds on the legitimate path (B18-2)** |
| the writer's keys sit between REQUIRED and ALLOWED | `…ACTUALLY_EMITS` | **NO** (0 of 2) | 🔴 **B18-1** — restates `check_row` |
| an optional-and-emitted field round-trips a real manifest | **none** | **n/a** | 🔴 the property is TRUE and nothing holds it |
| C-12 preserved at `check_row` | **none** | **n/a** | 🔴 **B18-4** |
| C-12 preserved at `validate_document` / `build` | ✅ / ✅ | ✅ / ✅ | ✅ |
| a tool has no members | **none** | **n/a** | 🔴 **B18-4** |
| `rows_of` returns copies | **none** | **n/a** | 🔴 **B18-4** |
| a filter names the field it reads | **none** | **n/a** | 🔴 **B18-5** |
| an order_by names at least one field | **none** | **n/a** | 🔴 **B18-6** |
| a pipeline is materialised before validation | **none** | **n/a** | 🔴 **B18-7** |
| `top_k` needs k ≥ 1 | ✅ | ✅ | ✅ *(the sibling that got one)* |
| a row key / member may not be a `str` subclass | **none** | **n/a** | 🔴 **B18-8** |
| document-level validity at the consumer doors | **none** | **n/a** | 🔴 **B18-9**, carried |
| a fifth row-reading door | **none** | **n/a** | 🔴 **B18-10**, fourth round |

## Reachability verdict on every finding

| # | finding | bucket | introduced by the graded delta |
|---|---|---|---|
| **B18-1** | the subset gate is a tautology; neither half fires, 0 of 2 | guard-only | **YES** |
| **B18-2** | the eleventh guard reds on CP-2's first operation, and on a pure reorder | guard-only (**CI-blocking at CP-2**) | **YES** |
| **B18-3** | commit message and RUNSTATE name different second unreproduced holes | process | **YES** |
| **B18-4** | all three "unreproduced" holes reproduce (G9, G22, G48); both probes reconstructed | guard-only | no (the claim is new) |
| **B18-5** | `Filter` must name its field — unguarded; empty field zeroes or no-ops the surface | guard-only → **prod-reachable at CP-2** | no |
| **B18-6** | `OrderBy(keys=())` unguarded — the silent id-order fallback its docstring forbids | guard-only | no |
| **B18-7** | `pipeline = list(pipeline)` unguarded — a generator pipeline is a silent no-op | guard-only | no |
| **B18-8** | two sites marked *redundant* are real: a `str` subclass key / member walks in | adversarial-only | no |
| **B18-9** | `rows_of`'s document gap is four exported doors wide, 5/5 shapes | **production-reachable** (at CP-2) | no |
| **B18-10** | a fifth exported row-reading door passes suite and gate — B4, fourth round | structural | no |
| **B18-11** | `canon` is uncalled and unexported; B17-2's docstring unchanged; `digest` fallthrough collides with `None` | doc / adversarial-only | no |

**1 production-reachable · 2 adversarial-or-doc · 7 guard-only/structural · 1 process · total 11 ·
introduced 2 (code) / 3 (with the record).**

---

## What I would fix first

1. **B18-2** — one line. Anchor the probe on `ROW_FIELDS = MappingProxyType({` and insert after it,
   not on the literal's last entry. The guard is good; its anchor is the one thing CP-2 must edit.
2. **B18-4** — the three holes, and the record. `check_row`'s re-raise guarded the way the other two
   now are; a test for the tool-with-**resolving**-member; a test for `dict(r)`. Then correct the
   two records so one finding has one status.
3. **B18-5 / B18-6 / B18-7** — three tests, one shape each. `Filter.field` and `OrderBy.keys` decide
   the surface; the generator no-op is written down in the module as a measured defect and has
   nothing holding it.
4. **B18-1** — either give the assertion content `check_row` does not already have, or delete it and
   say in the comment that `check_row` is the gate. A test that cannot fail is worse than no test,
   because it is counted.
5. **B18-10 / B4, fourth round** — the AST gate: every function in the package that reads a row field
   calls `check_row`, or is `check_row`, or is reached only via `rows_of`. **And the guard census
   itself**: 87 sites, neutered mechanically, run in CI. I derived 87 where the previous round
   derived 48 and the builder derived 11; until that enumeration is a script, every coverage number
   in this run — including mine — is a measurement of who looked hardest.

---

**Files touched by this verifier: this file only.** All ten scope files verified **byte-identical by
md5** to the snapshot taken at start; `git status` over `services/chat-service/`, `scripts/` and
`contracts/` is **empty**; suite `129 passed` and gate exit 0 on the real tree at finish; nothing
committed. All injections were made in a fresh full-layout replica under the session scratchpad and
restored from my own pristine copy. **No `git checkout` was used at any point.**

`git rev-parse HEAD` = `2faa88bacd48340d6ba0ce87dcc8dd471f73c88d` — **unmoved.**
