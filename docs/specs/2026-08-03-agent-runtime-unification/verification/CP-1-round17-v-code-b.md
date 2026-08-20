# CP-1 · round 17 · V-CODE · **Verifier B — the membrane**

**Artifact:** `6761cf013891b9c88c338750985553fd08bf9b0e`
`git rev-parse HEAD` **at start:** `6761cf013891b9c88c338750985553fd08bf9b0e`
`git rev-parse HEAD` **at finish:** `6761cf013891b9c88c338750985553fd08bf9b0e` — **unmoved.**

**Graded delta:** `869c5be52` against `d23ea5592`.
**Scope:** `services/chat-service/app/agentruntime/` (`contract.py`, `manifest.py`, `surface.py`),
`scripts/agentruntime-membrane-gate.py`, `services/chat-service/tests/test_cp1_membrane.py`.

**Method.** Every claim below was **executed**, never read. All injections were made in a fresh
scratch tree at `scratchpad/r17b/`, rebuilt from scratch with the **real repo layout**
(`services/chat-service/`, `scripts/`, `contracts/`, `.github/workflows/`) so that the 19
repo-path-dependent tests run rather than being deselected — the scratch baseline is
**`128 passed`, identical to the real tree**, and no test was excluded from any measurement.
Every injection was asserted **present in the file** before its result was trusted; every
`ROW_FIELDS`/`ROW_REQUIRED` patch was applied to **every binding** and the binding list printed.
**No `git checkout` was used at any point.** Final state: all eleven scope files verified
**byte-identical by md5** to the snapshot I took at start; `git status` over the scope is empty.

**Baseline:** `128 passed`; membrane gate **green** (`8 module(s), 0 allowed external import(s),
2 single-sited type(s)`).

---

## Verdicts

| # | claim | verdict |
|---|---|---|
| 1 | `ROW_REQUIRED` is a literal gated against the writer's real output; **execute** the migration — can CP-2 add `relevance` to a non-empty manifest without erasing origin stamps? | **The migration claim is TRUE and I proved it by doing it — and the gate written to protect it is FALSE for the exact case it names.** Executed as a **source edit**, not a monkeypatch: old-schema manifest on disk with **distinct** origins `0.9.0`/`0.8.0`, `relevance` added to `ROW_FIELDS` + emitted by `_row`, then the *ordinary* `generate(path=existing)` — **no `rm`, no `bootstrap`** — round-trips and **origins survive** (`ORIGIN STAMPS SURVIVED: True`). **R16-B's B2 is CLOSED.** But the new gate asserts `emitted == ROW_REQUIRED`, which is red on the **OPTIONAL** branch its own failure message prescribes → **B17-1** |
| 2 | `build` preserves C-12's structured fields; sweep for the same shape elsewhere — any `except` naming a class that has since gained a subclass | **B3 CLOSED and red-able (G28 RED) — but the sibling sweep missed the fifth member, and its own fix created a dead handler.** AST sweep over the whole service: 2 in-scope handlers. `check_row`'s **own** C-12 re-raise (`contract.py:298-300`) is the third re-raise in the set and is **unguarded** — downgrading it destroys `.field_path` at **every** door with the suite fully green → **B17-3**. And `check_row` raises **only `ContractViolation`** (18/18 shapes measured), so `except UntrustedRow` at `manifest.py:244` is now **dead** → **B17-4** |
| 3 | `canon.nfc()` deleted as a normalisation whose stated harm was not real — confirm or refute; did it remove a door §0.14.2 needs? | **CONFIRMED, and no needed door was removed — but the deletion went to the call site and not to the claim.** `digest(NFD) == digest(NFC)` → **True**; the stated harm cannot occur. **But `canon.nfc()` is now uncalled** (AST: zero call sites in the package) and **its own docstring still asserts the refuted claim verbatim** — *"two `digest` values for one visibly identical document"* — where it is the function's entire stated reason to exist → **B17-2** |
| 4 | Four previously-unguarded checks got tests — verify each reds for the reason it names, and find the fifth | **THREE of the four did. The fourth did not, and the claim that it did is false.** duplicate ids (G12 **RED**), `previous.declarations` a list (G31 **RED**), document closed schema (G37 **RED**) — all three genuinely red. **`dict(r)` at `rows_of` has no test**: G48 is **GREEN**, and the hole is **real** (caller mutation of a returned row reaches the source document, measured) → **B17-5**. The **fifth** is **B17-3**; a **sixth** is `check_contract`'s tool-with-members clause → **B17-6** |
| 5 | `rows_of` still runs no document-level stamp check — recorded OPEN, owner CP-2. Is that scoping honest? | **Honest as to reachability, unchanged as to fact.** Re-measured: **5 of 5** document shapes accepted by `rows_of` **and by `SurfaceAssembler`** that `validate_document` refuses. Repo-wide grep confirms **nothing outside the package imports it** — so not reachable today, and CP-2 ownership is defensible. **But three other R16-B findings were dropped from the carried register entirely** while still open → **B17-8** |
| 6 | Convergence, same buckets, per changed line. **R16-B predicted the rate would fall back on the next site-by-site delta. Settle it.** | **THE PREDICTION HELD, on both readings.** Closure **54% → 25–37%** (fell, as R16-B's *written* prediction said). Introduced per 100 changed lines **1.1 → 4.7** (rose 4.3×, as the prompt's paraphrase said). **9 findings (1 P / 1 A / 7 G); introduced = 2.** Full analysis in §6 |

**Overall: FAIL** — on **B17-1**, and on a **third consecutive self-measurement error**, this time a
**negative existence claim I refuted by construction** (§7).

**But the headline of this delta is TRUE, and it should be said first.** R16-B's B2 was the most
serious finding of the previous round — a scheduled, unmigratable brick — and it is **closed**,
verified by performing the migration end-to-end rather than by reading the diff. That is the second
round running in which the builder's substantive fix survives execution.

---

## Falsifiers, stated before the search

| claim | what would have falsified it |
|---|---|
| 1 | origin stamps changing across a schema-forward regeneration; any consumer door refusing an old-schema row; **or** the optional branch being unrepresentable |
| 2 | an `except` whose catch set silently widened; a re-raise that drops the C-12 class with no test seeing it |
| 3 | `digest(NFD) != digest(NFC)`; a live caller of `nfc()`; a §0.14.2 door with no other answer |
| 4 | any of the four staying green when its check is removed; no fifth existing |
| 5 | an importer outside the package; `rows_of` refusing a document shape it previously accepted |
| 6 | closure rising **and** the per-line introduction rate falling — either alone leaves the prediction half-settled |

---

## 1 — the migration question, **executed**

### 1a · ✅ the claim is TRUE — performed, not argued

The prompt says *execute*, so nothing here is monkeypatched. `relevance` was added to
`ROW_FIELDS` **as a source edit** to `contract.py`, and `_row` was edited to **emit** it — i.e. CP-2's
actual change, including its producer, per §0.14.1c. Injections verified present in the file
(`VERIFY contract.py has relevance : True`, `VERIFY manifest.py _row emits it : True`,
`VERIFY ROW_REQUIRED untouched : True`).

The manifest on disk was written under the **old 7-field schema** with **deliberately distinct**
origin stamps, so that "the origins survived" is falsifiable rather than a tautology against the
live constant:

```
ON DISK row0 keys : ['admitted_against','contract_version','id','kind','lifecycle','members','owning_service']
ON DISK origins   : {'book_get': '0.9.0', 'book_list': '0.8.0'}
```

Then, against the schema-advanced code:

```
OLD-SCHEMA FILE  load()             -> OK
OLD-SCHEMA FILE  rows_of()          -> OK
OLD-SCHEMA FILE  SurfaceAssembler   -> OK
OLD-SCHEMA FILE  declarations()     -> OK

generate(path=existing)             -> OK          <- the ORDINARY route. No `rm`. No `bootstrap`.
  row0 keys after migration         : [...,'owning_service','relevance']
  origins after migration           : {'book_get': '0.9.0', 'book_list': '0.8.0'}
  *** ORIGIN STAMPS SURVIVED        : True ***
  re-load of the migrated file      -> OK, origins = {'book_get': '0.9.0', 'book_list': '0.8.0'}
```

Every one of R16-B's four measured failures is reversed: the catalog is readable, `generate(path=)`
does not raise, `bootstrap` is not needed, and `rm` — the route that erased history — is not on the
path. **B2 is CLOSED**, and the value bound still holds (`relevance: "7"` → `ContractViolation`).

### 1b · 🔴 **B17-1 — the gate reds on the branch its own message prescribes**

`test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS__and_no_more`
(`test_cp1_membrane.py:1055`) asserts:

```python
emitted = set(build(...)["declarations"][0])
assert emitted == set(ROW_REQUIRED)
```

and its failure message instructs: *"decide whether it is **REQUIRED** … or **OPTIONAL** (add it to
`ROW_FIELDS` only)."* I executed **all three** branches of that instruction, plus a control, each
against the full 128-test suite:

| branch | what was edited | suite |
|---|---|---|
| (a) no decision — `_row` only | writer emits an undefined field | **35 failed** |
| (b) decision = **REQUIRED** — `_row` + `ROW_FIELDS` + `ROW_REQUIRED` | | **14 failed** |
| (c) decision = **OPTIONAL** — `_row` + `ROW_FIELDS` | *exactly what the message prescribes* | **2 failed** |
| (d) **control** — optional field the writer does **not** emit | `ROW_FIELDS` only | **128 passed** ✅ |

Branch (c)'s failures are contaminated by the field *name* — `test_EVERY_ROW_FIELD_IS_BOUNDED`
hard-codes `{"relevance": 9999}` as a shape that must be refused. Re-run with a neutral name
(`salience`) to isolate the mechanism:

```
(d') OPTIONAL, writer does NOT emit it  -> 128 passed
(c') OPTIONAL, writer DOES emit it      -> 1 failed
     FAILED ... test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS__and_no_more
```

**There is exactly one failure and it is the gate itself.** `emitted == set(ROW_REQUIRED)` is,
restricted to writer-emitted fields, *precisely* the constraint `ROW_REQUIRED = frozenset(ROW_FIELDS)`
expressed — the one this delta exists to remove. It was **moved from the definition into the test**,
not removed. The optional tier is expressible only for a field **nothing writes**, and the fields
CP-2 and CP-4 need are writer-emitted by construction: §0.14.1c assigns them *producers*.

So the comment at `contract.py:196-199` — *"adding an OPTIONAL field to `ROW_FIELDS` is now
expressible, **which is what CP-2 and CP-4 need**"* — is true of the general case and **false of the
case it names**. A gate that reds identically on "no decision" and on "decision made correctly"
carries no information about which occurred; it is an unconditional tripwire on writer-schema
growth, which is a defensible thing to have and is not what the docstring claims it is.

**Reachability: guard-only, CI-blocking at CP-2.** The runtime is correct (§1a). **Introduced by the
graded delta: YES** — the test is new in `869c5be52`.

---

## 2 — the exception hierarchy, and the sibling the sweep missed

### 2a · ✅ B3 is closed and red-able

`manifest.py:234-243` now catches `ContractViolation` before `UntrustedRow` and re-raises the same
class. **G28** (replacing that clause with an unrelated exception) is **RED**. The new test asserts
the class *and* `.field_path`/`.accepted` rather than only the refusal. Correct fix, correct guard.

### 2b · 🔴 **B17-3 — the FIFTH re-raise, and it is the one nothing tests**

The correction *"re-raise preserving the C-12 class"* has **three** members in this package, not two:

| site | re-raises `ContractViolation` as itself? | guarded? |
|---|---|---|
| `manifest.validate_document` `:425` | ✅ | ✅ **G42 RED** |
| `manifest.build` `:241` (this delta) | ✅ | ✅ **G28 RED** |
| **`contract.check_row` `:298-300`** | ✅ | 🔴 **G9 GREEN** |

`check_row` wraps `check_contract`'s violation to re-stamp the field path. Downgrading it to a flat
`UntrustedRow` leaves the suite at **`128 passed`**, and the behaviour probe shows it is **not**
redundant:

```
control : G9  bad-kind at rows_of  class=ContractViolation  has field_path=True
G9      : G9  bad-kind at rows_of  class=UntrustedRow       has field_path=False
```

Because `check_row` is the **shared** definition, this one site loses C-12's structured fields at
**all four** doors simultaneously — strictly more reach than the `build` site the delta fixed.
The round whose premise is *"at the set, not at the named door"* fixed the door a verifier named and
left the function both doors call. **Reachability: guard-only** (today's behaviour is correct).
**Introduced: no** — pre-existing; it is the member this delta's own sibling sweep should have found.

### 2c · 🔴 **B17-4 — the fix made the handler below it dead, and the comment still calls it live**

AST sweep, whole service, every `except` naming a class that has since gained a subclass — two
in-scope hits, both `except UntrustedRow` (`manifest.py:244`, `manifest.py:427`), each now also
catching `ContractViolation` and `UnresolvedReference`. With the new narrower clause ahead of it, the
residual catch set of `:244` is `{UntrustedRow, UnresolvedReference}`. Measured over 18 row shapes:

```
classes check_row raised over 18 shapes: {'ContractViolation': 18}
can check_row raise UnresolvedReference? False
```

`UnresolvedReference` comes from `check_document_rows`, which is called **outside** this `try`. So
`except UntrustedRow` at `:244` is **unreachable**, while its body's comment still explains the live
path (*"`previous` is caller-supplied, so it is checked here…"*). Low severity, but it is a handler
that a future reader will maintain believing it runs. **Reachability: guard-only / dead code.**
**Introduced: YES** — reverting the delta removes the narrower clause and makes it live again.

---

## 3 — `canon.nfc()`: the deletion **confirmed**, the claim **left standing**

### 3a · ✅ the deletion was right, and no needed door was removed

```
digest(NFD) == digest(NFC)  : True
```

R16-B's B5 is **confirmed**: the stated harm cannot occur, `canon.digest` normalises internally, and
removing the call changes no accept/reject outcome. §0.14.2 door (a) is answered by `canon.digest`,
exactly as the new comment says. **No door was lost.**

### 3b · 🔴 **B17-2 — the false claim was deleted at the call site and kept at the definition**

```
call sites of canon.nfc() in the package : NONE — the function is uncalled
nfc() docstring still claims two digests : True
```

`canon.nfc` (`canon.py:37-48`) is now **dead code**, and its docstring still asserts, verbatim, the
claim `contract.py:285-293` was written to refute:

> *"an NFD spelling loaded and validated and produced **two `digest` values for one visibly identical
> document**."*

R16-B's remedy was explicit: *"delete the `canon.nfc()` call **and the comment**, or make it
normalise the stored value and point the comment at `Filter(field="owning_service")`."* The first
half of the first option was taken. The refuted sentence now survives in the **one place a reader
looks to find out what the function is for** — and the function is the only thing §0.14.2's door (a)
is exported for. The real residual R16-B named (an un-normalised `owning_service` differing under
`Filter(field="owning_service", op="eq")`; the row does still store NFD — verified) remains
undocumented anywhere.

**Reachability: adversarial-input only / documentation.** **Introduced: no** — this is B5 carried
with a new residual, and by R16-B's own rule (a finding counts as introduced iff reverting closes it)
reverting restores the call but not the truth of the docstring.

---

## 4 — the four tests, and the fifth

### 4a · three of four, verified by removing the check each names

| check | test | mutation | result |
|---|---|---|---|
| duplicate declaration ids | `test_A_DUPLICATE_DECLARATION_ID_IS_REFUSED_AT_EVERY_DOOR` | G12 | **RED** ✅ |
| `previous.declarations` is a list | `test_A_MALFORMED_PREVIOUS_IS_NOT_AN_EMPTY_ONE` | G31 | **RED** ✅ |
| the document's closed schema | `test_THE_DOCUMENT_SCHEMA_IS_CLOSED_TOO` | G37 | **RED** ✅ |
| **`dict(r)` at `rows_of`** | **none exists** | **G48** | 🔴 **GREEN** |

Each of the three reds **for the reason it names** — I removed the specific check, not a neighbour.

### 4b · 🔴 **B17-5 — the fourth check did not get a test, and the round says it did**

`git diff` shows **five** new test methods; none covers the `dict(r)` copy. G48
(`out.append(dict(r))` → `out.append(r)`) leaves the suite at **`128 passed`**, and the hole is real:

```
control : G48 caller mutation reaches the doc's row -> False
G48     : G48 caller mutation reaches the doc's row -> True
```

This is the **fourth** self-measurement in this run to read in the flattering direction, in the round
whose entire subject is self-measurement. **Reachability: guard-only** (the copy is present and
correct); the property it protects is production-reachable.

### 4c · 🔴 **B17-6 — a sixth unguarded check, on nobody's list**

`check_contract`'s *tool has no members* clause (`contract.py:367`). G22 leaves the suite green, and:

```
control : G22 tool with a resolving member -> ContractViolation
G22     : G22 tool with a resolving member -> ACCEPT ['t0', 't1']
```

A tool whose members **resolve** is accepted — M5 does not catch it, because the reference is valid.
Load-bearing, untested, and it is one of the nine classes R15 claimed closed. **Reachability:
guard-only.** **Introduced: no.**

---

## 5 — `rows_of` and the document level

Re-measured, all five shapes, three doors:

| document shape | `rows_of` | `SurfaceAssembler` | `validate_document` |
|---|---|---|---|
| no `manifest_version` | **ACCEPT** | **ACCEPT** | UntrustedRow |
| `manifest_version: 999` | **ACCEPT** | **ACCEPT** | UntrustedRow |
| `contract_version: "banana"` | **ACCEPT** | **ACCEPT** | UntrustedRow |
| no `contract_version` | **ACCEPT** | **ACCEPT** | UntrustedRow |
| undefined top-level key | **ACCEPT** | **ACCEPT** | UntrustedRow |

**5 of 5 divergent**, unchanged from R16. Repo-wide grep: **no module outside the package imports
`agentruntime`** — the only external reference is the gate script. So it is **not reachable today**,
and recording it OPEN with owner CP-2 is **honest**. **Reachability: production-reachable at CP-2.**

### 5a · 🔴 **B17-8 — but three still-open findings left the register without being closed**

RUNSTATE's *"Open, carried"* list names the outage hole, `rows_of`'s document check, `generate`'s
race, the untyped container, and the six read-twice sites. It does **not** name R16-B's **B4**, **B7**
or **B8**. All three are still open; I re-measured each:

* **B4 — the consolidation is a state, not a gate.** I appended a fifth exported row-reading door to
  `surface.py`. It served `{'id':'x','kind':'gadget','cost':10**9}` — a row failing three clauses and
  the closed schema — as `['x:gadget']`, with **`128 passed`** and **gate exit 0**. Unchanged.
* **B7 — document stamps re-read.** G44 **GREEN**. Unchanged (and still unexploitable: the `Lying`
  subclass is refused at the door by `type(doc) is dict`).
* **B8 — the P4 route loop short-circuits** (`test_cp1_membrane.py:537-545` raises on the first
  non-empty route). Unchanged.

A finding that is neither closed nor carried has been *forgotten*, and the register is the only place
that would have said so.

---

## Red-ability table — **my own denominator, derived from the tree**

I did not inherit R16-B's 30. I enumerated every `raise`-site in the membrane doors by AST
(`contract.py` 18, `manifest.py` 17, `surface.rows_of` 1) and added the structural invariants that
have no `raise` (schema contents, `MappingProxyType`, the exception hierarchy, the rebuilt return,
the `dict(r)` copy, each door's call to `check_row`). **48 guards.** Baseline `128 passed`; every
mutation applied to a restored-pristine tree with the injection asserted present first.

| # | guard mutated | result |
|---|---|---|
| G1 | shape: `type(row) is dict` → `isinstance` | **RED** |
| G2 | shape: unknown-key refusal removed | **RED** |
| G3 | shape: required-field loop removed | **RED** |
| G4 | shape: value exact-type → `isinstance` | **RED** |
| G5 | shape: empty-`id` refusal removed | **RED** |
| G6 | shape: members-element check removed | 🟡 GREEN — *redundant* (`check_contract` catches) |
| G7 | shape: non-string-key refusal removed | 🟡 GREEN — *redundant* (`key not in ROW_FIELDS`) |
| G8 | `check_row`: contract clauses not run | **RED** |
| G9 | **`check_row`: C-12 class downgraded on re-raise** | 🔴 **GREEN — real hole (B17-3)** |
| G10 | `check_row`: §6.4 stamp syntax check removed | **RED** |
| G11 | `check_row`: `owning_service` not fed back | **RED** |
| G12 | set: duplicate-id check removed | **RED** *(new this delta)* |
| G13 | set: M5 unresolved-reference removed | **RED** |
| G14 | `ROW_FIELDS`: four ranking fields restored | **RED** |
| G15 | `ROW_FIELDS`: `MappingProxyType` → `dict` | **RED** |
| G16 | `ROW_REQUIRED`: back to a 5-element subset | **RED** |
| G17 | **`ROW_REQUIRED` re-derived from `ROW_FIELDS`** (the reverted state) | 🔴 **GREEN — and see §7** |
| G18 | hierarchy: `UntrustedRow` not a `ValueError` | **RED** |
| G19 | hierarchy: `ContractViolation` not an `UntrustedRow` | **RED** |
| G20 | hierarchy: `UnresolvedReference` not an `UntrustedRow` | **RED** |
| G21 | C-0: owner-not-derivable refusal removed | **RED** |
| G22 | **C: tool-with-members refusal removed** | 🔴 **GREEN — real hole (B17-6)** |
| G23 | C: skill/workflow-with-no-members removed | **RED** |
| G24 | writer door: `_row`'s `check_row` removed | **RED** |
| G25 | writer: `isinstance(admitted, Admitted)` removed | **RED** |
| G26 | writer: P4 origin carry → the live constant | **RED** |
| G27 | 4th door: `build(previous=)` → shape only | **RED** |
| G28 | **build: the new `except ContractViolation` removed** | **RED** *(B3's fix, guarded)* |
| G29 | build: outer `previous` type check removed | **RED** |
| G30 | build: missing-`declarations`-key check removed | **RED** |
| G31 | build: `previous.declarations` is-a-list removed | **RED** *(new this delta)* |
| G32 | build: the loss guard removed | **RED** |
| G33 | build: set-level check removed | **RED** |
| G34 | generate: bootstrap gate removed | **RED** |
| G35 | generate: `exists`→`load` re-check removed | 🟡 GREEN — *carried (R12 §5)* |
| G36 | 5th TOCTOU: `type(doc) is dict` → `isinstance` | **RED** |
| G37 | doc: closed-schema check removed | **RED** *(new this delta)* |
| G38 | doc: `manifest_version` check removed | **RED** |
| G39 | doc: `contract_version` check removed | **RED** |
| G40 | doc: `declarations` exact-type → `isinstance` | 🟡 GREEN — *redundant* |
| G41 | doc: `rows = list(rows)` removed | 🟡 GREEN — *redundant* |
| G42 | doc: C-12 class downgraded on re-raise | **RED** |
| G43 | doc: returns `{**doc}` again | **RED** |
| G44 | doc: stamps re-read from the caller's object | 🟡 GREEN — *carried (B7)* |
| G45 | consumer door: `rows_of` → shape only | **RED** |
| G46 | consumer door: `rows_of` set-clauses removed | **RED** |
| G47 | `rows_of`: `_is_exactly` → `isinstance` | 🟡 GREEN — *redundant* |
| G48 | **`rows_of`: no `dict(r)` copy** | 🔴 **GREEN — real hole (B17-5)** |

### **37 / 48 red-able (77%).** 11 unguarded: **5 redundant**, **2 carried**, **4 real holes**
(G9, G17, G22, G48).

The delta moved this from R16-B's 22/30 (73%) to 77% on a **larger, independently derived**
denominator — three of the four gaps it targeted are now genuinely red. That is real progress and
the ratio understates it.

---

## 6 — convergence, and **the prediction**

### 6a · which prediction was actually made

The prompt asks me to settle *"that the introduction rate would rise again on the next site-by-site
delta."* R16-B's written text (`CP-1-round16-v-code-b.md:608-614`) discusses the series
`14, 10, 8, 27, 54` — which is **closure** — and says *"the **rate** should fall back the moment a
round ships a site-by-site delta again."* **The prediction as written is about closure falling; the
prompt's paraphrase is about introduction rising.** These are different claims and I settle both,
because settling the one that was actually made is the point of having made it.

**This delta is site-by-site**: 43 added lines in `agentruntime/`, of which **8 are non-comment
source**, spread across four unrelated sites (`ROW_REQUIRED`, the `nfc` call, `build`'s handler, and
five tests). It is the smallest structural surface of the series.

### 6b · **both readings HELD**

| reading | R16 | R17 | prediction |
|---|---|---|---|
| **closure rate** (as written by R16-B) | **54%** | **25%** clean · **37%** counting partials at half | **HELD — fell** |
| **introduced per 100 changed lines** (the prompt's paraphrase) | **1.1** | **4.7** | **HELD — rose 4.3×** |

Closure, re-measured against this artifact by probing every R16-B finding:

| R16-B finding | now |
|---|---|
| B1 `rows_of` accepts 5 document shapes `load()` refuses | **OPEN** (re-measured 5/5) |
| B2 closed schema, no optional tier, no migration | **CLOSED** ✅ (migration executed, origins survived) — new residual **B17-1** |
| B3 `build` destroys C-12's fields | **CLOSED** ✅ and red-able (G28) |
| B4 consolidation is a state, not a gate | **OPEN** (fifth door re-injected: suite + gate green) |
| B5 `canon.nfc()` dead guard, false comment | **PARTIAL** — call deleted; claim survives at the definition (**B17-2**) |
| B6 8 of 30 guards unguarded | **PARTIAL** — 3 of 4 load-bearing gaps now red; `dict(r)` still green (**B17-5**) |
| B7 document-stamp rebuild unguarded | **OPEN** (G44 green) |
| B8 P4 route loop short-circuits | **OPEN** (unchanged) |

**2 clean closures, 2 partials, 4 open** of 8 → **25%** clean, **37%** with partials at half.
Series: `14, 10, 8, 27, 54, ` **`25–37`**.

Raw introduced fell (3 → 2); **per changed line it rose sharply** (`150, 4.9, 4.4, 1.1, 4.7`). R16-B
argued the per-line normalisation is the one that cannot be gamed by shipping less — and it is the
one that moved against the builder here, on a delta that shipped an eighth of R16's volume. Applying
that standard when it is unflattering is the only thing that made stating it worth anything.

**What this settles.** R16-B's confounder is **confirmed**: the closure step-change at R15–R16 tracked
*delta structure*, not an improving process. Two structural deltas produced 27% and 54%; the next
site-by-site delta produced 25–37% and a 4.3× rise in the per-line introduction rate. `introduced`
reads `2, 1, 2, 1, 3, 2, 4, 3, 2` — still no direction raw, across nine rounds.

**What would still settle the trend question**, unchanged where nothing has made it obsolete:

1. Three consecutive rounds at `introduced == 0`. R17 is not one of them.
2. The read-twice sweep in the commit message **with its definition**. **This round did it correctly**
   — see §7 — and it is the first builder self-measurement in three rounds to survive independent
   re-run.
3. **New this round:** a **structural** gate. **B4 is now three rounds old.** Both the product's
   door-count property and this metric are produced by verifiers enumerating by hand; I derived a
   48-guard denominator the builder did not have, and a fifth door still walks past suite and gate.
   Until enumeration is mechanised, every convergence number in this series — including mine — is a
   measurement of how hard the verifier looked.

---

## 7 — independent re-run of the builder's two measurement claims

### Claim 1 — *"Red-ability, with a denominator taken from the two verdicts rather than from what I wrote: 10 of 11. The eleventh is declared unguarded with its reason."*

**The arithmetic is defensible. The eleventh's *reason* is false, and I refuted it by construction.**

The builder's stated reason (`test_AN_OPTIONAL_FIELD_IS_EXPRESSIBLE`'s docstring) is:

> *"Reverting `ROW_REQUIRED` to `frozenset(ROW_FIELDS)` leaves it GREEN, because **the derivation runs
> at import and a runtime patch of `ROW_FIELDS` cannot re-trigger it.** The property … **has no subject
> until an optional field exists, which is CP-2.**"*

The first sentence is true of a *monkeypatch* — G17 is indeed **GREEN**, and I confirm it. The
conclusion drawn from it is not. Re-**executing the module source** with one field injected into
`ROW_FIELDS` re-runs the derivation, and separates the two states exactly:

```
--- CURRENT tree (literal ROW_REQUIRED) ---
  ROW_FIELDS has salience   : True
  ROW_REQUIRED has salience : False
  RESULT: row WITHOUT the new field validates -> OPTIONAL TIER HOLDS (test GREEN)

--- G17 injected (ROW_REQUIRED = frozenset(ROW_FIELDS)) ---
  ROW_FIELDS has salience   : True
  ROW_REQUIRED has salience : True
  RESULT: ContractViolation: t0.row.salience: is missing -> NO OPTIONAL TIER (test RED)
```

**The property has a subject today.** It takes ~10 lines of stdlib, and module re-execution is
already an established idiom in this very suite (`test_cp1_membrane.py:1424` copies the package and
re-imports it in a subprocess for the import-depth test).

This is the **third consecutive round** in which a builder self-measurement reads in the flattering
direction — and it is a new species. R15's and R16's were *counting* errors. This one is a **negative
existence claim** — *no guard is possible* — asserted from a single failed attempt. The prompt asked
Verifier A to try to refute the analogous negative claim about `instrument.py`; the same standard
applies here, and the claim does not survive it. **Declaring a gap with a reason is better than
hiding it, and it is not a substitute for trying the obvious second approach.**

Combined with **B17-5** (`dict(r)` claimed guarded, measured unguarded), the honest form is
**9 of 11, with the eleventh guardable today.**

### Claim 2 — *"six same-fact read-twice sites, each safe only by an exact-type pin"*

**CONFIRMED — exactly.** My own sweep (reads only, `ast.Load`, writes excluded; `obj[key]` and
`obj.get(key)` on named objects within one scope):

| file | function | site | n | mechanism |
|---|---|---|---|---|
| contract.py | `check_row` | `row['id']` | 3 | uniform |
| contract.py | `check_document_rows` | `r['id']` | 4 | uniform |
| manifest.py | `build` | `r['id']` | 3 | uniform |
| manifest.py | `validate_document` | `doc['manifest_version']` | 2 | uniform |
| surface.py | `discover` | `row['kind']` | 2 | uniform |
| surface.py | `_narrow` | `row['id']` | 2 | uniform |

**6 same-fact sites; 0 mixed-mechanism.** The builder now reports **both numbers with the definition
attached**, which is precisely what R16-B asked for, and it reproduces independently on the first
attempt. **This is the claim the previous two rounds got wrong, and this round gets it right.** It
should be said as plainly as the failures.

---

## Bypass table

| property the delta claims | bypass found | evidence | reachability |
|---|---|---|---|
| CP-2 can add `relevance` to a non-empty manifest without erasing origins | **none** — the ordinary `generate(path=)` round-trips with origins intact | executed as a source edit, distinct stamps | — |
| an OPTIONAL field is expressible, "which is what CP-2 and CP-4 need" | **yes** — expressible only if the **writer does not emit it**; CP-2's field has a producer | 4 branches × full suite, isolated with a neutral name | guard-only, CI-blocking at CP-2 |
| `build` preserves C-12's structured fields | **none at `build`** | G28 RED | — |
| the C-12 class survives every re-raise | **yes** — `check_row`'s own re-raise drops it at all four doors | G9 GREEN + behaviour probe | guard-only |
| `except UntrustedRow` at `build` is the live fallback | **it is dead** — `check_row` raises only `ContractViolation` | 18/18 shapes | guard-only |
| `canon.nfc()`'s stated harm was not real | **none** — confirmed | `digest(NFD)==digest(NFC)` | — |
| §0.14.2 door (a) still answered | **none** — `canon.digest` answers it | executed | — |
| four previously-unguarded checks got tests | **yes** — `dict(r)` did not | G48 GREEN + mutation probe | guard-only |
| the eleventh guard has no subject until CP-2 | **yes** — module re-execution guards it today | executed, both states | guard-only |
| the read-twice sweep returns 6 / 0 | **none** — reproduced exactly | independent AST sweep | — |

## Sibling table — *a correction applied to one member of a set*

| correction | members | applied to | missed |
|---|---|---|---|
| re-raise preserving the C-12 class | `validate_document`, `build`, **`check_row`** | 2 of 3 guarded | 🔴 **`check_row` `contract.py:298`** — **B17-3** |
| a test for each unguarded load-bearing check | dup ids, `previous.declarations`, doc schema, **`dict(r)`** | **3 of 4** | 🔴 **`dict(r)`** — **B17-5** |
| deleting a refuted claim | the call-site comment, **`nfc()`'s own docstring** | 1 of 2 | 🔴 **`canon.py:37-48`** — **B17-2** |
| the optional tier | definition ✅, runtime ✅, **the gate** ✗, the comment ✗ | 2 of 4 | 🔴 **B17-1** |
| a narrower `except` before a broader one | `validate_document` ✅, `build` ✅ | 2 of 2 | — (but both leave a dead clause — **B17-4**) |
| document-level validity at the consumer door | `manifest_version`, `contract_version`, closed doc schema | 0 of 3 at `rows_of` | **all 3** — carried B1 |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| property | test | reds? | for the right reason? |
|---|---|---|---|
| C-12 preserved at `build` | `…the_fourth_door` | ✅ G28 | ✅ |
| C-12 preserved at `check_row` | **none** | **n/a** | 🔴 **B17-3** |
| duplicate ids refused at every door | `…AT_EVERY_DOOR` | ✅ G12 | ✅ |
| `previous.declarations` is a list | `…NOT_AN_EMPTY_ONE` | ✅ G31 | ✅ |
| document schema is closed | `…CLOSED_TOO` | ✅ G37 | ✅ |
| `rows_of` returns copies | **none** | **n/a** | 🔴 **B17-5** |
| `_row`'s output == `ROW_REQUIRED` | `…ACTUALLY_EMITS` | ✅ | 🔴 also reds on the legitimate optional path — **B17-1** |
| naming a field does not make it mandatory | `…IS_EXPRESSIBLE` | **NO** (G17 green) | 🔴 declared unguardable; **is guardable** — §7 |
| tool-with-members refused | **none** | **n/a** | 🔴 **B17-6** |
| a fifth row-reading door | **none** | **n/a** | 🔴 B4, third round |
| document-level validity at `rows_of` | **none** | **n/a** | 🔴 B1, carried |

## Reachability verdict on every finding

| # | finding | bucket | introduced by the graded delta |
|---|---|---|---|
| **B17-1** | the `REQUIRED_SET` gate reds on the OPTIONAL branch its own message prescribes; the tier is inexpressible for writer-emitted fields | guard-only (**CI-blocking at CP-2**) | **YES** |
| **B17-2** | `canon.nfc()` is uncalled; its docstring still carries the refuted claim | adversarial-only / doc | no (B5 carried, partly fixed) |
| **B17-3** | the fifth re-raise — `check_row`'s C-12 class — unguarded at all four doors | guard-only | no |
| **B17-4** | `except UntrustedRow` at `manifest.py:244` is dead; its comment says otherwise | guard-only / dead code | **YES** |
| **B17-5** | `dict(r)` claimed guarded, measured unguarded; the hole is real | guard-only | no (the claim is new) |
| **B17-6** | `check_contract`'s tool-with-members clause unguarded | guard-only | no |
| **B17-7** | the eleventh guard declared unguardable is guardable today (§7) | guard-only | **YES** (the declaration is new) |
| **B17-8** | B4/B7/B8 left the carried register while still open | guard-only / process | no |
| **B17-9** | `rows_of` runs no document-level check — 5/5 shapes | **production-reachable** (at CP-2) | no |

**1 production-reachable · 1 adversarial-only · 7 guard-only · total 9 · introduced 2.**

*(B17-7 and B17-1 are counted separately: the first is a false claim about guardability, the second a
gate that contradicts its own remedy. Merging them would understate `introduced`, and the rule is
applied against the builder here, so it must be applied consistently.)*

---

## What I would fix first

1. **B17-1 + B17-7 together** — replace `assert emitted == set(ROW_REQUIRED)` with
   `assert set(ROW_REQUIRED) <= emitted` (the writer must emit every required field) and add the
   module-re-execution test from §7, which guards the optional tier **today**. That converts the
   round's declared gap into a real guard and stops the gate from blocking the migration it exists
   to enable — the two halves are one change.
2. **B17-3** — one clause: guard `check_row`'s re-raise the way `validate_document`'s and `build`'s
   are now guarded. It is the member of the set with the widest reach and the only one untested.
3. **B17-5** — one test for `dict(r)`, and correct the record that says it has one.
4. **B17-2** — delete `canon.nfc()`, or repoint its docstring at `Filter(field="owning_service")`,
   which is the door that is actually open.
5. **B4, three rounds old** — the AST gate in `agentruntime-membrane-gate.py`: every function in the
   package that reads a row field calls `check_row`, or is `check_row`, or is reached only via
   `rows_of`. Until that exists, §6's convergence numbers measure the verifier, not the tree.

---

**Files touched by this verifier: this file only.** All eleven scope files verified **byte-identical
by md5** to the snapshot taken at start; `git status` over `services/chat-service/`, `scripts/` and
`contracts/` is **empty**; suite `128 passed` and gate exit 0 on the real tree at finish; nothing
committed. All injections were made in `scratchpad/r17b/`, a fresh full-layout replica.

`git rev-parse HEAD` = `6761cf013891b9c88c338750985553fd08bf9b0e` — **unmoved.**
