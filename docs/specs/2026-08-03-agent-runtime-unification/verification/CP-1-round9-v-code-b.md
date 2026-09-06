# CP-1 · round 9 · V-CODE · **Verifier B** — 1.8a's operand bounds, and P4's code changes

`git rev-parse HEAD` **at start:** `86ae725929215cbb20201308db1120b0855f1222`
`git rev-parse HEAD` **at finish:** `86ae725929215cbb20201308db1120b0855f1222`
Working tree clean throughout; no tracked file modified except this verdict. No `git checkout` was run.
All injections were made from an **out-of-tree pytest plugin** (`inject_b.py`, in the session scratchpad)
that rebinds callables at `pytest_configure`, plus standalone scripts driving the public API against
`tempfile` paths. Nothing was run against the live system.

**Baseline I measured myself:** `python -m pytest tests/test_cp1_membrane.py -q` from
`services/chat-service` → **104 passed, 1 warning, 7.09s**.
`python scripts/agentruntime-membrane-gate.py` → **exit 0** (selftest OK, 8 modules, 2 single-sited types).

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *Every stage parameter is bounded by exact type; membership is by identity; `TopK(k=0)` refused; both list kinds reject empty `names`* | **FAIL** — two operands still unbounded, and the identity fix was applied to one of the two membership tests |
| 2 | *`build()` refuses to write a manifest that loses a declaration present in `previous`* | **PASS with a named cost** — reachable through the real writer; it breaks no *legitimate* operation, but it hardens an existing brick (see 2c) |
| 3 | *The migration backfill is safe* | **FAIL** — it launders a bogus stamp into a permanent origin, and it repairs only one of the two legacy shapes this run shipped |
| 4 | *Document-level stamps and `lifecycle` are validated on read* | **PASS** — verified by execution; breaks no row the generator produces. One residual: `validate_document` now **mutates** its argument while its docstring says otherwise |
| 5 | *The P4 defect-assertion test is honest* | **PARTIAL FAIL** — (a) holds; **(b) does not: it passes when the amendment helper does not amend** |
| 6 | *`contract_version` varies between rows, is carried across regeneration, and is gated* | **PASS** — confirmed by execution through `generate()` across three generations, and red-able three ways |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Any constructor call — no private symbol, no `object.__setattr__` — that puts a caller-controlled `__eq__`/`__lt__`/`__contains__`/`__hash__`/`__index__` into the narrowing decision, or two distinguishable stages hashing alike | Enumerated **every** field of the six kinds and asked "is this `_plain`-checked?", then executed 20 probe shapes through `Filter/OrderBy/TopK/TakeWhileBudget` + `SurfaceAssembler.assemble` |
| 2 | A `generate()` sequence that drops a row without raising; **or** a legitimate op (bootstrap, `build([])`, repair of a stale file) that the refusal now blocks | Drove `generate()` twice against one temp path with a shrinking admitted set; drove `build([])`, `build([], previous=<non-empty>)`, `bootstrap=True`, and five invalid-`previous` shapes |
| 3 | A document accepted **now** that round-8's reader rejected, whose acceptance changes a later decision; or a legacy shape the backfill does not reach | Built each historical row shape from `git show` of the actual commits, fed each through `validate_document`/`load`/`generate` |
| 4 | Any lifecycle value `_row()` can emit that `validate_document` then rejects; any document stamp still unread | Generated all four `LIFECYCLES` + a skill through `generate()` and re-read via `load()`; fed `None`/absent stamps |
| 5 | The test passing while (i) `build` raised, (ii) `_amend` no-op'd, (iii) the queue had nothing in it to look at; or staying green when the queue becomes satisfiable | Four plugin injections, each isolating one of those |
| 6 | Two rows unable to carry different origins through `generate()`; or deleting the carry leaving the suite green | Three real writes to one path across two amendments; then `carry_removed` and `generate_drops_previous` injections |

---

## 1 — the operand bounds: **a seventh operand, an eighth, and a route the fix's own sibling opened**

`_plain()` (`surface.py:82-101`) is exact-type and cannot be defeated. It is simply **not applied to
two of the operands**, and the round-8 identity fix was applied to one membership test and not the other.

### B1 · `Filter.op` is unbounded — `surface.py:127`, consumed at `surface.py:158-162`

```python
if self.op not in self.OPS:      # `in` on a tuple → `==`, dispatched to the operand
```
There is no `_plain(self.op, str, "op")`. Executed:

* `Filter("s","r", field="id", op=SneakyOp("regex"), value=("t0",))` where `SneakyOp(str).__eq__`
  returns `other == "in"` → **constructed**, spelled `'regex'`, and `assemble` returned `('t0',)`.
* `op` need not even be a string: `class OpObj: __eq__ = lambda s,o: True` → **constructed**, and
  `keep()`'s `if self.op == "eq"` then runs caller code once per row to pick the branch.

The operand also decides **which validation branch runs**: `__post_init__:143` asks `self.op == "eq"`,
so the object chooses whether it is checked as a scalar or as a tuple-of-scalars.

### B2 · `OrderBy`'s `direction` is unbounded — `surface.py:256`, consumed at `surface.py:280`

`field` gets `_plain(field, str, …)`; `direction` gets only `if direction not in self.DIRECTIONS`.
Executed:

* `OrderBy(keys=(("lane", SneakyDir("NONSENSE")),))` — a `str` subclass whose `__eq__` returns `True`
  — **constructed while spelled `'NONSENSE'`**, and `sort()` ran its `__eq__` to compute
  `reverse=`, producing `['t3','t2','t1','t0']` instead of ascending.
* A non-`str` `DirObj()` is accepted identically.
* End-to-end: `assemble(pipeline=[OrderBy(keys=(("lane", Flip()),)), TopK(k=2)])` → caller code
  chose which two of four declarations reached the model (`names=('t2','t3')`).
* **Downstream:** the resulting narrowing record carries the live object —
  `ordered_by == [['lane', <Flip object>], ['id','asc']]`. Measured: that record is **neither
  `json.dumps`-able nor `canon.digest`-ible**. A `{tool, stage, reason, pass}` record that cannot be
  persisted is the silence §0.3 forbids, arriving from a legal constructor call.

This is the exact operand §0.14.1a rule 6 exists to make legible: *rank* is what a budget cuts on.

### B3 · `Filter.SCALARS` is checked by `==`, not by `is` — **the sibling the metaclass fix missed**

`surface.py:365` was correctly rewritten to `any(type(s) is k for k in STAGE_KINDS)` with a comment
explaining that a metaclass defeats a set/tuple membership test. **The identical shape was left in
place two functions above**, at `surface.py:144` and `surface.py:150`:

```python
if type(self.value) not in self.SCALARS:                                   # :144
elif ... any(type(v) not in self.SCALARS for v in self.value):             # :150
```

Executed — a class whose **metaclass** `__eq__` returns `True`:

| probe | result |
|---|---|
| `Filter(op="eq", value=RegexishForged())` → `assemble` | **accepted**; the instance's `__eq__` ran, `names=('t3',)` |
| `Filter(op="in", value=(ForgedElem(),))` (forged **element** of a real tuple) | **accepted**; `names=('t0','t2')` |
| `Filter(op="in", value=RegexishForged())` | blocked — `type(...) is tuple` is exact, so only the element path is open |

`test_THE_OPERAND_IS_BOUNDED_NOT_ONLY_THE_OPERATOR` and `test_a_METACLASS_cannot_forge_membership…`
both exist and both pass; neither crosses the two ideas. The fix and its own precedent are 200 lines
apart in one file.

### B4 · content-addressability — §0.14.1's *second stated justification* is defeated by B3

```python
class Twin(str, metaclass=StrForge):        # metaclass __eq__ → True ; instance __eq__ → True
    ...
honest = Filter("s","r", field="id", op="eq", value="t0")
forged = Filter("s","r", field="id", op="eq", value=Twin("t0"))
```
Measured: `canon.digest(asdict(honest)) == canon.digest(asdict(forged))` → **True**, while
`assemble` returned `('t0',)` for one and `('t0','t1','t2','t3')` for the other.
**Two entirely different narrowings, one digest** — verbatim the failure the docstring at
`surface.py:56-57` says data prevents and closures do not. `test_every_kind_is_CONTENT_ADDRESSABLE`
(line 1196) samples six well-behaved stages and cannot see it.

### B5 · the row side of the same comparison is `isinstance`, not exact — `surface.py:533`

`SurfaceAssembler(manifest_doc)` is public and takes any dict. `cost` is checked with
`isinstance(cost, int)`; executed with `class SneakyCost(int): __radd__ → 0`, a 9999-cost row was
kept under `budget=1`. `OrderBy.sort` compares row values with no bound at all: a row value with a
custom `__lt__` chose the `TopK` victim. Weaker than B1–B4 (rows loaded through `load()` are JSON,
so plain types), but the assembler's own entry point does not require that provenance.

### Not found (searched, and each was executed)

`tuple` subclass for `names` / `Filter.value` · `__iter__` object for `names` · `Filter` subclass
through `assemble` · `_Narrowing` base as a stage · `__init_subclass__` · `__class_getitem__`
(`Filter` is not subscriptable) · rebinding `.keep` on an instance (slots) · `TopK(k=True)` ·
`stage`/`reason` as `str` subclasses. All blocked.

`object.__setattr__` on a genuine stage **does** re-open everything (`value`, `op`, `k` swapped
post-construction, `k=0` forced, surface narrowed to zero). I do **not** count this as a new hole:
the gate's `_forgery_scan` flags `object.__setattr__` in any module touching `agentruntime`, so it is
the same layer-2 detection boundary `admission.py:27-34` discloses. It is worth one line of doc: the
`_require_names` docstring says *"rejected at construction, not at use"* without that qualifier, and
`admission.py` sets the precedent for stating it.

---

## 2 — `build()`'s refusal to lose a declaration

**2a · reachable in the way it will actually occur — YES.** Not only from a hand-built `previous`.
Driven through the real writer:

```
generate([book_list, book_get], path=p, bootstrap=True)
generate([book_list],           path=p)
→ UntrustedRow("['book_get'] are in the previous manifest and not in this build …")
→ file byte-identical afterwards (measured: True)
```
`generate()` populates `previous` from `load(path=target)`, so the refusal sits on the production
branch, not only on the exported `build()`.

There is also no hole in `origin`'s construction: `build()` raises `UntrustedRow` on any `previous`
row lacking a syntactically valid `contract_version` (`manifest.py:191-198`) **before** the `lost`
comparison, so every previous id is guaranteed to be in `origin`. A row cannot slip past by being
malformed.

**2b · legitimate operations.** Measured:

| operation | result |
|---|---|
| `bootstrap=True` on a fresh path | OK, 1 row |
| the drift gate's `build([])` (`agentruntime-membrane-gate.py:365`) | OK — `previous=None`, unaffected |
| `build([], previous=<non-empty>)` | raises — correct by §1, and the gate never does this |
| gate end-to-end | exit 0 |

**2c · the cost, and it is real.** `generate()` ignores `bootstrap=` when the file exists
(`manifest.py:257-267`), so **any** invalid committed manifest is unreadable *and* unwritable at once
— the very trap the round-9 backfill was written to escape. Measured on five shapes:

| `previous` shape | `generate()` | `generate(bootstrap=True)` |
|---|---|---|
| `contract_version: "banana"` | `UntrustedRow` | `UntrustedRow` |
| row missing `lifecycle` | `UntrustedRow` | `UntrustedRow` |
| row missing `admitted_against` | `UntrustedRow` | `UntrustedRow` |
| document `contract_version: "banana"` | `UntrustedRow` | `UntrustedRow` |
| row missing `contract_version` | **OK** (the round-9 backfill) | **OK** |

One shape of five is repairable. For the other four the only route is `rm`, and `rm` + `bootstrap=True`
restamps every origin — the erasure `bootstrap` exists to prevent, reached by a different door.
Round 9 did not create this; it fixed one instance of it and left the class.

---

## 3 — the migration backfill: **it does launder a bogus stamp into an origin**

`manifest.py:375-377`:
```python
if "contract_version" not in r and isinstance(r.get("admitted_against"), str):
    r = {**r, "contract_version": r["admitted_against"]}
```

**3a · a document accepted now that would have been rejected before, in a way that matters.** Yes.
Executed:

```
row: {… "admitted_against": "99.0.0"}      # no contract_version
validate_document → ACCEPTED, origin becomes '99.0.0'
```
Round 8 rejected this row outright (`contract_version` was required and unbackfilled). The comment at
`manifest.py:363-368` correctly discloses that `"99.0.0"` survives the *syntax* check and argues the
direction is safe because a bogus stamp lands the row **in** the queue. That argument covers
`admitted_against` and **does not cover `contract_version`**, because the origin is not a queue
comparand — it is carried forward forever. Measured end-to-end through the real writer:

```
generate(bootstrap=True); hand-edit the row to {admitted_against: "99.0.0"}, drop contract_version
amend to 2.0.0; generate(path=same)
→ origin='99.0.0'   admitted_against='2.0.0'
```
A generation that never existed is now the permanent, carried, gated origin of that declaration, and
`build()`'s `lost` guard actively **preserves** it. The one field §6.4 says *cannot move* has been
made settable from a text editor — the same class of defect (`UntrustedRow`: *"a row typed in by hand
reached the assembler having passed no clause"*) that this whole boundary exists to close.

**3b · the sibling the backfill does not reach.** `git show` of this run's own commits gives **three**
row shapes, not two:

| era | commits | row carries | reachable today? |
|---|---|---|---|
| **A** | `0488549bd` … `2165df23a` | `contract_version` **only** | **NO** — `load()` raises; `generate()` raises with **and** without `bootstrap=True` |
| **B** | `8dd31c3dc` … `1ab136b1c` | `admitted_against` **only** | yes — this is what round 9 fixed |
| **C** | current | both | yes |

Measured for era A: `UntrustedRow: declarations[0].admitted_against is None`, and both `generate()`
forms refuse. `manifest.py:371` says *"every manifest this run produced before today became
unreadable AND unwritable at once"* — the repair was written for the half the builder was looking at.
Era A is arguably the safer thing to leave bricked (adopting an origin as an admission stamp *would*
invent information, where the reverse does not), but the asymmetry is undisclosed and the docstring
reads as though the class were closed.

**3c · `validate_document` mutates its argument.** `rows[i] = r` at `manifest.py:376` edits the
caller's list. The docstring at `manifest.py:302` says *"Returns it unchanged, or raises."* Measured:
`doc` before ≠ `doc` after. The M1 drift gate reads the file, calls `validate_document(doc)`, then
compares `doc != build([])` (`agentruntime-membrane-gate.py:356-366`) — so **the gate compares a
document it silently repaired**. Inert today (the committed manifest is `declarations: []`); from
CP-4 on, drift in exactly the `contract_version` field is invisible to the gate that exists to catch
hand edits.

---

## 4 — document stamps and `lifecycle` on read

Verified by execution, not by reading:

* `generate()` of five declarations spanning **all four** lifecycles (`draft`, `admitted`,
  `deprecated`, `retired`) plus a skill with members → `load()` returns all 5 rows, all four
  lifecycles intact. **Requiring `lifecycle` breaks no row the generator produces.**
* `lifecycle: null` → `UntrustedRow … unknown lifecycle None`. Absent key → `UntrustedRow`.
* Document stamps: `contract_version: "banana"`/`None` and `manifest_version: 99`/`None` all raise.
* Red-able: `lifecycle_default_restored` → 1 failed; `doc_stamps_unvalidated` → 1 failed.

Searched and found **nothing**: I suspected §0.14.2 door (a) was still open because `canon.nfc()` at
`manifest.py:346` normalises only the value fed into `check_contract` and the row keeps its NFD
spelling. Measured — `canon.digest` of the NFD and NFC documents are **equal**, because `canon._norm`
NFC-normalises every string it hashes. No defect; the `nfc()` call there is belt-and-braces.

---

## 5 — **is the P4 defect-assertion test honest? Partly. It can pass for another reason.**

`test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE`
(`tests/test_cp1_membrane.py:432-456`). Driven, one injection per failure mode:

| injection (models…) | P4 test | honest? |
|---|---|---|
| `queue_satisfiable` — `_row` stamps `admitted_against="0.9.0"`, i.e. the grandfathering mechanism lands | **RED**, on assertion 1: `assert ['book_get','book_list'] == []` | ✅ requirement **(a)** holds |
| `build_returns_no_rows` — the queue comprehension has nothing to iterate | **RED**, on assertion 2: `assert set() == {'2.0.0'}` | ✅ covered, though only incidentally — assertion 1 alone is vacuous over zero rows |
| **`amend_is_a_noop`** — `_amend` rebinds nothing | **GREEN — 1 passed in 0.11s** | ❌ **requirement (b) FAILS** |
| `build` raising | pytest reports an error, not a pass | ✅ |

**The defect.** Assertion 2 is
`{r["admitted_against"] for r in after["declarations"]} == {after["contract_version"]}`. When the
amendment is a no-op every value is `"1.0.0"` and the set equality holds trivially — it is assertion 1
restated, contributing nothing. So the only half of the test that involves an amendment **cannot
distinguish "`admitted_against` tracked the amendment" from "no amendment happened"**, which is
precisely the failure mode the round-9 prompt names, and precisely the shape the standing rules call
*"a check whose seed and control agree"*.

The suite as a whole survives this — `test_two_rows_CAN_carry_different_stamps` and
`test_generate_CARRIES_THE_ORIGIN…` both red under `amend_is_a_noop` — but the load-bearing test for
the FAIL record does not, and the FAIL record is the thing CP-4 will be graded against.

**Two one-line closures**, both inside the existing test:
```python
assert len(doc["declarations"]) == 2                 # assertion 1 stops being vacuous over zero rows
assert after["contract_version"] == "2.0.0"          # the amendment is proved to have happened
```

Everything else about the test is sound: it names the defect, its comparand is the document's own
stamp rather than a literal, it is driven through the real `build()` rather than a mutated fixture,
and it reds the day the mechanism lands.

---

## 6 — the PO transfer, graded as a **code claim**

RUNSTATE:1155 / ARCHITECTURE.md:331,1570 — *`contract_version` genuinely varies between rows, is
carried across regeneration, and is gated.* Verified independently of the tests, through the real
writer, three generations onto one path:

```
generate([book_list], bootstrap=True)              # CONTRACT_VERSION 1.0.0
amend 2.0.0 ; generate([book_list, book_get])
amend 3.0.0 ; generate([book_list, book_get, book_new])

on disk: origins  {book_list: '1.0.0', book_get: '2.0.0', book_new: '3.0.0'}
         admitted_against {'3.0.0'}      document contract_version '3.0.0'
```
**All three assertions in the claim hold.** Varies: three distinct values on one document. Carried:
across two real writes through `load()`→`build(previous=…)`. Gated: measured below.

| removal | reds |
|---|---|
| `carry_removed` (`_row` ignores `origin`) | `test_two_rows_CAN_carry_different_stamps`, `test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE` |
| `generate_drops_previous` (`previous=` deleted from the production writer) | `test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE` |
| `lost_check_removed` | `test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST`, `test_the_WRITE_side_validates_previous_too` |

Round 8's finding that the production branch was dead to the suite is repaired: deleting `previous=`
from `generate()` now reds.

**The one qualification, from §3:** "gated" is true of *loss* and of *recomputation*; it is not true
of *fabrication*. `validate_document`'s backfill lets a hand-edited file choose an origin
(`"99.0.0"`), and the carry then makes it permanent. The PO decision is unaffected — this is a bug in
the field CP-1 kept, not an argument about which field belongs where.

---

## Bypass table

| property asserted | path that defeats it | evidence |
|---|---|---|
| every stage parameter is bounded by exact type | **`Filter.op`** is not `_plain`-checked; a `str` subclass or any object with `__eq__` is accepted and steers `keep()`'s branch | `surface.py:127`, `:158` — executed |
| " | **`OrderBy` direction** is not `_plain`-checked; reaches `reverse=(direction == "desc")` | `surface.py:256`, `:280` — executed, sort order inverted and the `ordered_by` record made unserialisable |
| membership is by identity, so a metaclass cannot forge it | true of `STAGE_KINDS`; **false of `Filter.SCALARS`**, which is still `type(x) in <tuple>` | `surface.py:144`, `:150` — executed, `op="eq"` and `op="in"`-element both forged |
| a closure is not content-addressable, data is | a metaclass-forged `str` subclass hashes identically to the plain string and narrows differently | `canon.digest` equal, surfaces `('t0',)` vs all four — executed |
| the ranking/budget consume plain values | row-side `cost` is `isinstance(int)`; row sort values are unbounded; `SurfaceAssembler(dict)` is public | `surface.py:533`, `:280` — executed |
| `TopK(k=0)` refused / empty `names` refused / subclasses refused / tuple subclasses refused | **none found** — 9 shapes executed, all blocked | see §1 "Not found" |
| a declaration cannot silently leave the manifest | **none found** — the `origin` map is populated from a validated `previous`, so no malformed row can slip the comparison | executed |
| the origin generation cannot be restated by the writer | **it can be fabricated by the reader**: a hand-edited row with only `admitted_against` adopts it as origin, and the carry makes it permanent | `manifest.py:375-377` — executed through `generate()` |
| `validate_document` "returns it unchanged" | it mutates `rows[i]`; the M1 drift gate compares a document it repaired | `manifest.py:376` vs gate `:356-366` — executed |

## Red-ability table — baseline **104 passed** (measured by me, `-q`, 7.09s)

| injection | what it models | result |
|---|---|---|
| `queue_satisfiable` | §6.4's grandfathering mechanism lands | 3 failed / 101 passed — incl. the P4 defect test, on assertion 1 |
| `amend_is_a_noop` | the amendment helper stops amending | 2 failed / 102 passed — **the P4 defect test still PASSES** |
| `build_returns_no_rows` | the queue has nothing to look at | 10+ failed — P4 test reds on assertion 2 |
| `carry_removed` | `_row` ignores `origin` | 2 failed / 102 passed |
| `generate_drops_previous` | `previous=` deleted from the production writer | 1 failed / 103 passed |
| `lost_check_removed` | the round-9 loss refusal deleted | 2 failed / 102 passed |
| `backfill_removed` | the round-9 migration deleted | 1 failed / 103 passed |
| `lifecycle_default_restored` | `r.get("lifecycle","draft")` restored | 1 failed / 103 passed |
| `doc_stamps_unvalidated` | document stamps read from nowhere again | 1 failed / 103 passed |
| `plain_is_a_noop` | the exact-type operand bound removed | 1 failed / 103 passed |
| `kind_set_by_equality` | `type(s) in _KIND_SET` restored | 1 failed / 103 passed |
| `topk_zero_allowed` | the `k >= 1` check removed | 1 failed / 103 passed |
| `empty_names_allowed` | `_require_names` neutered | 2 failed / 102 passed |
| `filter_value_unbounded` | `Filter.value`'s SCALARS check removed | 1 failed / 103 passed |

Every element of the round-9 delta is red-able. **No injection was silent.** The suite's weakness is
not deadness — it is that three properties (B1, B2, B3) were never asserted at all, so there is
nothing to red.

## Sibling table — *the recurring failure in this run is a correction applied to one member of a set*

| fix shipped | sibling I looked for | also fixed? |
|---|---|---|
| identity membership in `validate_pipeline` (`any(type(s) is k …)`) | the **other** two membership tests over caller data: `Filter.SCALARS`, `Filter.OPS`/`OrderBy.DIRECTIONS` | ❌ **NO** — `SCALARS` forgeable (B3), `OPS`/`DIRECTIONS` operands unbounded (B1, B2) |
| `_plain()` applied to `stage`, `reason`, `field`, `cost_field`, `k`, `budget`, `keys[i] field` | the remaining two operands: `Filter.op`, `OrderBy` direction | ❌ **NO** |
| `TopK(k=0)` refused because the default is the failure | the same audit on `TakeWhileBudget(budget=0)` — default is 0 and it keeps exactly one row | ✅ intentional (`budget >= 0`, first row always kept) — checked, not a defect |
| both list kinds reject empty `names` | `OrderBy(keys=())` | ✅ fixed (`"must name at least one field"`) |
| era-B manifest (`admitted_against` only) made readable | **era-A** manifest (`contract_version` only) — the shape `0488549bd`…`2165df23a` shipped | ❌ **NO** — still unreadable *and* unwritable |
| `bootstrap=` so a missing file is not permission to restamp | the four *other* invalid-`previous` shapes, for which `bootstrap=True` is also refused and `rm` is the only route | ❌ **NO** — one of five repairable |
| `generate()` carries `previous` (the dead production branch) | `build()`'s exported path — same carry | ✅ both covered and both red-able |
| row-level stamps validated on read | the **document**-level stamps | ✅ fixed this round |
| `contract_version` validated on read (`_VERSION`) | the write side (`previous` is caller-supplied) | ✅ fixed (`manifest.py:191-198`) |
| P4 asserted as a FAIL by a test | the same test proving its own amendment took effect | ❌ **NO** — §5 |

## What I would fix first

1. `_plain(self.op, str, "op")` and `_plain(direction, str, …)` — two lines, closes B1 and B2.
2. `SCALARS`/`OPS`/`DIRECTIONS` membership by `is`, matching `STAGE_KINDS` — closes B3 and B4.
   `_KIND_SET` (`surface.py:348`) is now referenced only by a comment; either delete it or reuse the
   pattern that replaced it.
3. Two assertions inside the P4 defect test (§5) — otherwise the FAIL record CP-4 will be graded
   against rests on a check that passes when nothing happened.
4. Decide `admitted_against`-as-origin explicitly: either refuse a row missing `contract_version`
   whose `admitted_against` is not the document's own stamp, or record the laundering as a disclosed
   residual next to the `"99.0.0"` one — it is materially different, because the origin is carried.
