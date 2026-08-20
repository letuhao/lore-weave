# CP-1 · round 13 · V-CODE · **Verifier B** — the manifest and the bounds

`git rev-parse HEAD` **at start:** `5ce95de376b68bfced83b1ae39d0ce8885f461b2`
`git rev-parse HEAD` **at finish:** `5ce95de376b68bfced83b1ae39d0ce8885f461b2`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.

**Method.** Every injection is **source surgery**: the real function's source is read with
`inspect.getsource`, exactly one anchor line is replaced, and the result is `exec`'d in the module's
**live** `__dict__` — identical signature, messages and globals except for the injected line. The new
object is rebound at **every** binding from an out-of-tree pytest plugin at `pytest_configure`, i.e.
**before** the test module's `from app.agentruntime import …` runs. Three self-checks, carried
forward from R12 because R11's builder measured an inert probe:

1. the injected function must differ from the original in `co_code` **or** `co_consts` — both are
   printed per run, and a run where neither differs **aborts** with `INJECTION IS A NO-OP`;
2. `app.agentruntime.manifest.<name> is <injected>` **and** `app.agentruntime.<name> is <injected>`
   are asserted at configure time; the run aborts if either fails;
3. a `pytest_collection_finish` hook prints whether **the test module's own binding** is the injected
   object, and raises `SystemExit` if it is not. **Every row in every table below was run with
   `[INJECT] test module tests.test_cp1_membrane.<name> is-injected=True` printed.**

**Baselines I measured myself, at start and at finish:**

| | |
|---|---|
| `python -m pytest tests/test_cp1_membrane.py -q` (from `services/chat-service`) | **111 passed**, 1 warning, ~7.5 s |
| `python scripts/agentruntime-membrane-gate.py` (repo root) | **exit 0** — selftest OK, 8 modules, 2 single-sited types |

111, not R12's 109: the delta adds exactly two tests, and they are the first two tests this run has
added to `test_cp1_membrane.py` in three rounds.

**Scope.** R12's delta plus the findings R12 recorded OPEN. In `app/agentruntime/` the delta is
`manifest.py` **only**, and it is **two code changes**: the outer `previous` type check
(`manifest.py:193-197`) and `validate_document`'s return (`manifest.py:452`). In
`tests/test_cp1_membrane.py` it is **two new tests** (`:612-657`).

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *`validate_document` returns what it validated* | **FAIL — and the fix is a net regression on the shape it was written for.** R12's exact vehicle is closed ✅, but `[dict(r) for r in rows]` copies each row's **storage**, while every validation read goes through `r.get(…)`. A `dict`-subclass row whose `.get` answers valid and whose storage holds `kind:"nonsense"`, `contract_version:"banana"`, `admitted_against:null` is **ACCEPTED**, and the returned row is a **plain `dict`** carrying all of it. **`rows_of` refuses that row before the fix and accepts it after** — measured on three variants: the fix **laundered** a fail-loud into a served row |
| 2 | *The outer `previous` is checked; find the fifth TOCTOU* | **PARTIAL PASS on `previous` (6 of 8 R12 shapes closed, the 2 plain-`dict` ones remain), FAIL on the class — I found the fifth AND the sixth, both introduced by this round's own two-line fix.** `{**doc}` re-reads `manifest_version`/`contract_version` through `__getitem__` after validating them through `.get`: measured **`contract_version` validated as `"1.0.0"` and returned as `"banana"`** — §6.4's queue comparand, the exact field the line 15 above it calls out. `dict(r)` is the sixth (§1). Full read-twice sweep of all 8 modules is tabulated in §2c |
| 3 | *The `r.get("id")` / `r["id"]` split, recorded OPEN* | **CONFIRMED OPEN, and it is narrower in `validate_document` and unchanged in `build`.** In `build` it still silently deletes a declaration: measured, `book_get` gone with the loss guard silent. In `validate_document` the duplicate half is now *closed by accident* (the return reads the same `[…]` storage the dedupe set does), and what remains is a row whose **returned** `id` passed no clause — measured: contract-checked `'book_list'`, returned `'!! HAND TYPED !!'`, and `rows_of` accepts it |
| 4 | *The P4 test is still green if the mechanism lands in `generate()`* | **CONFIRMED OPEN, unchanged from R12.** I built it, proved it live (2 rows on disk, `QUEUE=['book_get']`, drains to `[]`, `validate_document` OK, `load()` OK) and ran the suite: **111 passed.** And **yes, `generate()` is the likely landing site** — §6.4.1's own argument puts it there, it is the only function that will ever write the real manifest, and it is the only one that can carry a row forward without `build`'s loss refusal firing |
| 5 | *Every fix in this round's `app/agentruntime/` delta has a test that reds* | **PASS on the two fixes as written — 2 of 2 red, against R12's 5 of 5 silent. FAIL on their strengthening halves — 2 of 2 silent.** Removing either fix reds the suite ✅. Weakening `type(previous) is not dict` → `isinstance` is **111 passed** while restoring R12's headline `FalsyDict` defect live; removing the per-row `dict(r)` copy is **111 passed** and is *safer* than what shipped |
| 6 | *Convergence, measured* | **In the membrane scope both counts are now falling for the first time (prod 4→12→9→3→3; adversarial 5→5→7→7→3). In the instrument scope the production-reachable count is NOT falling (13→17→22→13) and is ~93% of that scope's findings.** The loop is converging where the fixes are going and not where they are not. And the closure rate is the number that should worry the board: **~9% of R12's membrane findings were closed by R13's delta.** Full table, method and confounders in §6 |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | No value reaching a consumer of `validate_document`'s **return** that differs from the value the function checked — through `load`, `declarations`, `rows_of`, `SurfaceAssembler`, `discover` or the drift gate | Enumerated every read the validation loop performs (`.get`, `in`, `[…]`) and asked, per read, which protocol the **return** expression uses; then executed one vehicle per divergent pair, plus a plain-JSON pass for unknown keys |
| 2 | Every value in the package read once to **check** and again to **use** being read through the same protocol over an exact-typed container | Mechanical sweep of all 8 modules: every `.get(k)`-then-`[k]`, every `in`-then-`[…]`, every value iterated twice, every `x or y` after a type check, every second filesystem probe, and every `return` of a container a copy of which was validated |
| 3 | The `id` split permitting nothing a consumer can act on | Drove it separately in `build` (origin/loss) and in `validate_document` (contract/dedupe/M5/return), with the crafted row in each position |
| 4 | The P4 test reddening with a faithful `generate()`-landing mechanism live | Built it, proved a real draining queue on disk **before** running the suite, then injected at every binding |
| 5 | Any element of the delta whose removal leaves the suite green, or whose *strengthening* has no red-able probe | One injection per changed line, plus a weakened variant per line, each proven live in a standalone probe first |
| 6 | The two counts moving together, or the production-reachable count falling | Classified every finding in the 8 verdict files of rounds 9–12 by the **mechanism the verifier used to trigger it**, not by severity |

---

## 1 — `validate_document` returns what it validated. It returns something worse.

`manifest.py:452`, the round's headline fix:

```python
return {**doc, "declarations": [dict(r) for r in rows]}
```

### 1a · ✅ R12's exact vehicle is closed — executed

R12's `Appender` (a row whose `.get("members")` appends a hand-typed row to the caller's plain list)
now yields `validate_document → ['book_list']`. The materialised `rows` is what the return is built
from, so a mutation of the *original* list no longer reaches a consumer. The new test at
`test_cp1_membrane.py:612-649` is a faithful red-able guard for it (§5).

### 1b · 🔴 **THE SIXTH TOCTOU, AND THE FIX IS THE VEHICLE.** `manifest.py:373-437` vs `:452`

Every validation read in the loop goes through **`r.get(…)`** (`:378`, `:379`, `:388`, `:396`,
`:427`) or **`in`/`[…]`** (`:395`, `:435`). The return goes through **`dict(r)`**, and CPython's
`dict(mapping)` takes the fast path over a `dict` subclass's *internal storage* — it does not call an
overridden `get`. Measured directly:

```
P0  dict(subclass-with-lying-get) -> {'id': '!! HAND TYPED !!', 'kind': 'nonsense'}   (.get says book_list)
```

So a row whose `.get`/`__contains__`/`__getitem__` answer with a valid row while its storage holds a
hand-typed one is validated on one value and returned on the other:

| measured | value |
|---|---|
| `validate_document(doc)` | **ACCEPTED** |
| what the contract checked | `id='book_list'`, `kind='tool'`, `owning_service='book-service'`, `lifecycle='draft'`, both stamps `'1.0.0'` |
| what the **returned** row carries | `{'id': '!!! HAND TYPED !!!', 'kind': 'nonsense', 'owning_service': '!!', 'lifecycle': '??', 'contract_version': 'banana', 'admitted_against': None, 'members': ['nope']}` |
| type of the returned row | **`dict`** — nothing exotic survives |
| `rows_of(returned)` | `['!!! HAND TYPED !!!']` |
| `declarations(returned)` — the only row reader in `__all__` | `['!!! HAND TYPED !!!']` |

**And this is the part that makes it a regression rather than a residual.** `rows_of` bounds the row
*type* exactly (`surface.py:55`, `_is_exactly(r, dict)`). Before this round's fix that bound caught
the subclass. Three variants, one probe:

| `validate_document` returns | returned row type | `rows_of(returned)` |
|---|---|---|
| `return doc` — **before this round** | `LyingRow` | **REFUSED** — *"declarations[0] is a LyingRow, not a plain object"* ✅ |
| `{**doc, "declarations": rows}` — the copy without the per-row `dict()` | `LyingRow` | **REFUSED** ✅ |
| `{**doc, "declarations": [dict(r) for r in rows]}` — **what shipped** | `dict` | **ACCEPTED** `['!!! HAND TYPED !!!']` 🔴 |

The per-row `dict(r)` is the only one of the three on which the smuggled row reaches a consumer. It
converted a fail-loud into a served row, and it is the half of the fix that has **no test** (§5).
Reachability: **adversarial-input only** — it needs a `dict` subclass, which is code, not a text
editor. `load()` cannot produce one (`json.loads` yields plain dicts), so this is reachable only
through the exported `validate_document(doc)` / `declarations(doc)` with a caller-constructed
document.

### 1c · 🔴 the mutation class R12 named is not closed, only redirected — `manifest.py:452`

R12's sentence was *"a row's own `.get()` is user code the validator calls inside its own loop"*. The
fix moved the **target** of that mutation and left the class. A row that mutates **itself** on the
last read the loop performs:

```python
def get(self, k, d=None):
    v = dict.get(self, k, d)
    if k == "members" and not self.fired:      # the LAST read; id/kind already validated
        self.fired = True
        dict.__setitem__(self, "id", "!!! HAND TYPED !!!")
        dict.__setitem__(self, "kind", "nonsense")
        dict.__setitem__(self, "owning_service", "!!")
    return v
```

| measured | value |
|---|---|
| `validate_document` | **ACCEPTED** |
| returned row | `{'id': '!!! HAND TYPED !!!', 'kind': 'nonsense', 'owning_service': '!!', …}` |
| `declarations(returned)` | `[('!!! HAND TYPED !!!', 'nonsense')]` |

`dict(r)` runs *after* the loop, so anything user code changes during validation is what leaves.
**Adversarial-input only.** The closure that holds both 1b and 1c is to build the return from values
captured *at the moment each clause passed* — the pattern `_row` already uses (`manifest.py:150`,
`list(d.members)` stored and M5 checking the stored copy), which R12 §1e named as the correct one.

### 1d · 🔴 the door that reaches a consumer with **plain JSON** — unknown keys, `manifest.py:373-442`

The one shape here that needs no subclass at all, and therefore the only **production-reachable** one
in §1. `validate_document` validates the seven known fields and rejects nothing else; `dict(r)`
copies the whole row. Measured, on a document that round-tripped through `json.dumps`/`json.loads` —
i.e. exactly what a text editor leaves and `load()` reads:

```
P8 returned row: {'id': 'book_list', …, 'cost': 1000000000, 'relevance': 'zzz'}
P8 unknown TOP-LEVEL key survives: True
P8 the hand-typed `cost` steered a real budget stage
```

`TakeWhileBudget` reads `row.get(stage.cost_field)` (`surface.py:590`), `OrderBy.sort` reads
`r[field]` (`surface.py:326`) and `Filter.keep` reads `row.get(self.field)` (`surface.py:198`) — all
three consume row keys **the validator never looked at**. A hand-typed `cost` on one row therefore
decides which declarations a budget cuts. That is arm E reached through a column nobody validated.
`UntrustedRow`'s own docstring is *"a row typed in by hand reached the assembler having passed no
clause"*; seven of its clauses now pass, and the row still carries whatever else was typed.
**Production-reachable** — a text editor is a writer this code does not have, which is the membrane's
own premise.

### 1e · the doors that never call `validate_document` at all — R12 §2, unchanged, re-measured

| door | a row with `kind:"nonsense"`, `lifecycle:"??"`, `owning_service:"!!"`, `contract_version:"banana"`, `admitted_against:null`, `members:["ghost"]` |
|---|---|
| `rows_of(doc)` | **ACCEPTED** |
| `declarations(doc)` — in `__all__` | **ACCEPTED** |
| `discover(doc, kind=…, log=…)` | **ACCEPTED** |
| `SurfaceAssembler(doc).assemble(pass_number=1)` | **ACCEPTED** — `names=('book_list',)`, on the wire |

Only `id` and the row type are bounded (`surface.py:54-62`). The unresolvable member `ghost` — M5's
whole subject — reaches the assembler on all four. **Production-reachable**: these are four exported
functions that take a document directly, and nothing in the package requires the document to have
come through `load`.

### 1f · the fix has **no consumer that reads its return** outside the package

`grep` over `services/` and `scripts/`: the only external caller of `validate_document` is
`scripts/agentruntime-membrane-gate.py:361`, and it **discards the return value**, comparing the
original `doc` on the next line. The function's own docstring says it is *"separate from `load` so …
the M1 drift gate can call it"* — and the one caller that motivated the fix does not consume it.
Inert today (the gate's `doc` is `json.loads` output), recorded because a fix whose only caller
ignores it cannot be validated by that caller either.

---

## 2 — the fifth TOCTOU, and the whole read-twice sweep

### 2a · 🔴 **THE FIFTH.** `{**doc}` re-reads the document stamps it validated — `manifest.py:350-361` vs `:452`

`isinstance(doc, dict)` at `:343` accepts a subclass. The stamps are validated through
`doc.get("manifest_version")` and `doc.get("contract_version")`; the return spreads `{**doc}`, which
goes through `keys()`/`__getitem__`. Executed against a `dict` subclass whose `get` answers the valid
values and whose storage holds the invalid ones:

| measured | value |
|---|---|
| `validate_document(doc)` | **ACCEPTED** |
| what it validated | `manifest_version=1`, `contract_version='1.0.0'` |
| what it **returned** | `manifest_version=999`, **`contract_version='banana'`** |

The comment at `manifest.py:358-361` says of exactly this field: *"§6.4's re-admission queue is
derived by comparing every row against it, so an unreadable value empties the queue in silence."*
Six lines of code later the function hands that unreadable value to its caller. This read-twice pair
**did not exist before this round** — `return doc` returned the same object the validation read from.
**Adversarial-input only** (a `dict` subclass document).

### 2b · the outer `previous` — 6 of R12's 8 shapes closed, and the 2 survivors are the plain ones

`manifest.py:193`. Executed, all ten shapes:

| shape R12 measured | now |
|---|---|
| `FalsyDict(<real 2-row doc>)` — R12's headline row | **REFUSED** ✅ |
| `[]`, `()`, `0`, `False`, `""`, `"not a doc"` | **REFUSED** ✅ (6 shapes) |
| a bare `dict` **subclass** carrying the real rows | **REFUSED** ✅ |
| **`{}`** — the key missing | **ACCEPTED, guard silent, `book_get` gone** 🔴 |
| **a real document minus `declarations`** | **ACCEPTED, guard silent, `book_get` gone** 🔴 |
| control: the real 2-row document | **REFUSED** ✅ |

The two survivors are the two that need **no subclass**: `(previous or {}).get("declarations", [])`
at `:201` still serves a missing key as an empty catalog. That is the third live copy of the defect
`rows_of`'s own docstring is entirely about — *"a missing key is a **broken document**, not an empty
catalog"* — and `rows_of` spells the correct form eleven lines away (`surface.py:39-46`: `.get` with
**no default**, then `_is_exactly`). Reachability: not reachable through `generate()` (`load()`
always returns a document with the key), so **production-reachable by caller error** through the
exported `build(previous=…)`, not by an adversary.

### 2c · the full read-twice sweep — all 8 modules

Q2 asks for the fifth or for a statement that I searched every read-twice. I searched every one; here
is the sweep, so the negative results are checkable too.

| site | check-read | use-read | verdict |
|---|---|---|---|
| `manifest.py:350`,`:356` → `:452` | `doc.get(k)` | `{**doc}` → `keys()`/`__getitem__` | 🔴 **§2a, the fifth** |
| `manifest.py:378…:427` → `:452` | `r.get(k)` | `dict(r)` → internal storage | 🔴 **§1b, the sixth** |
| `manifest.py:378` → `:435`,`:437` | `r.get("id","")` | `r["id"]` | 🔴 §3 (narrowed) |
| `manifest.py:395` | `"lifecycle" in r` | `r["lifecycle"]` | 🔴 same class, `__contains__` vs `__getitem__` |
| `manifest.py:214` → `:223` | `r.get("id")` | `origin[r["id"]]` | 🔴 §3, silently deletes a declaration |
| `manifest.py:216` → `:223` | `r.get("contract_version")` | the same local `stamp` | ✅ one read |
| `manifest.py:193` → `:201` | `type(previous) is dict` | `(previous or {})` | ✅ closed — exact `dict`, so `__bool__` cannot lie |
| `manifest.py:202` → `:212` | `type(_prev_rows) is list` | `list(_prev_rows)` | ✅ closed (R12) |
| `manifest.py:369` → `:371` | `type(rows) is list` | `list(rows)` | ✅ closed (R12) |
| `manifest.py:281` → `:288` → `:289` | `ambient.exists` | `load()` then `ambient.exists` again | 🔴 R12 §5, unchanged — a **third** read of the same fact; the window where a second writer replaces the file is still open, and that is the only one of the three causes its comment names where a second writer exists |
| `manifest.py:331` → `:333` | `ambient.exists` | `ambient.read_text` | ✅ fail-loud (`FileNotFoundError`) |
| `manifest.py:61` → `generate:281` | `ambient.exists(candidate)` | `ambient.exists(target)` | ✅ subsumed by the row above |
| `manifest.py:224` | `admitted` iterated | once | ✅ |
| `surface.py:39` → `:54` → `:63` | `_is_exactly(rows, list)` | loop, then `list(rows)` | ✅ exact `list`, cannot yield two sequences |
| `surface.py:55` → `:57` | `_is_exactly(r, dict)` | `r.get("id")` ×3 | ✅ exact `dict` |
| `surface.py:320` → `:326` | `field not in r` | `r[field]` | ✅ rows are exact `dict` post-`rows_of` |
| `surface.py:511` → `:514` → `:527` | `list(pipeline)` before `validate_pipeline` | the same list | ✅ closed (r6) |
| `surface.py:582` → `:612` | `rows = list(rows)` | `rows.index(row)` | ⚠️ residual: `index` dispatches `__eq__`; two equal rows credit the record to the first. Not a bypass |
| `surface.py:658` → `:663` | `row.get("kind") == kind` | `row.get("kind")` in the reason | ✅ exact `dict` |
| `admission.py:117` → `:118` | `check_contract(declaration)` | `Admitted(declaration, …)` | ✅ same object, and `Declaration` is `frozen+slots` (R12 §1e: a property shadow is unsettable) |
| `manifest.py:102` → `:103`,`:150` | `check_contract(d)` | `identity_of(d)`, `list(d.members)` | ✅ R12 §1e measured fail-loud: `_row` stores `list(d.members)` and M5 checks the **stored** copy — **this is the pattern `validate_document` still lacks** |
| `contract.py:130` → `:142` | `d.members` truthiness | `enumerate(d.members)` | ✅ frozen slots tuple |
| `canon.py:75` | `value[k]` inside `for k in value` | one read | ✅ |
| `narrowing.py`, `ambient.py` | — | — | ✅ no read-twice |

---

## 3 — the `r.get("id")` / `r["id"]` split: what it still permits

### 3a · 🔴 in `build` — **it silently deletes a declaration.** `manifest.py:214` vs `:223`

`isinstance(r, dict)` at `:214` accepts a subclass; `r.get("id")` is the presence test and
`origin[r["id"]]` is the key. A previous-row whose `.get("id")` answers `book_get` (truthy, passes)
and whose `["id"]` answers `book_list`:

```
P6 build ACCEPTED. rows: [('book_list', '1.0.0')]
P6 book_get SILENTLY GONE: True
```

`origin` never learns the name `book_get`, so `lost = set(origin) - {…}` is empty and the loss guard
— the only stand-in §6.4 has — never fires. Unchanged from R12. **Adversarial-input only.**

### 3b · in `validate_document` — the duplicate half closed *by accident*, the return half open

R12 reported the dedupe set being keyed on a different value from the contract check. That half is
now **closed as a side effect** of the new return: both `:435` and `dict(r)` read the same storage,
so two rows whose storage ids collide are caught (measured: `duplicate declaration id 'book_list'`).

What remains is the direction that matters more. The contract validates `r.get("id","")`; the
**returned** row carries `r["id"]`:

```
P7 ACCEPTED; contract-checked id was 'book_list'; RETURNED row id = '!! HAND TYPED !!'
P7 rows_of(returned): ['!! HAND TYPED !!']
```

`_ID = ^[a-z][a-z0-9_]*$` never saw that string. **Adversarial-input only.** The same split exists
one line over as `"lifecycle" in r` / `r["lifecycle"]` (`:395`), which nothing has yet exercised.

---

## 4 — the P4 test and a mechanism landing in `generate()`

`tests/test_cp1_membrane.py:493-503`. **Confirmed OPEN, unchanged from R12.**

I built the mechanism §6.4 describes — a declaration that fails a breaking amendment stays in the
runtime carrying its origin stamp, and the queue is the rows whose `admitted_against` is not the
document's version — inside `generate()`, and proved it real **before** running the suite:

```
gen1 (1.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','1.0.0')   queue = []
breaking amendment to 2.0.0; book_get NOT re-admitted
gen2 (2.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','2.0.0')   QUEUE = ['book_get']
rows ON DISK: ['book_get','book_list']    queue on disk: ['book_get']
validate_document(on-disk): OK            load(): ['book_get','book_list']
gen3  book_get re-admitted                                              QUEUE = []   ← drains
```

**Suite: 111 passed**, with `test module tests.test_cp1_membrane.generate is-injected=True` printed.
The full §6.4 lifecycle — fills on a breaking amendment, survives a real write, reloads, drains — and
the test CP-4 will be graded against does not notice.

**Is `generate()` the likely landing site? Yes, and it is the *only* one that works.** Three
independent reasons:

1. `build()` **refuses** to lose a row (`manifest.py:236-242`), and that refusal is what §6.4's
   mechanism exists to replace. A mechanism landing in `build` has to delete the refusal that the
   sibling test `test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST` guards. A mechanism landing
   in `generate` has to touch nothing — it filters `previous` before the call and re-appends after.
   The path of least resistance is the one outside `build`.
2. `manifest.py:232-234`'s own comment places the mechanism at the row-disappearing moment, and the
   only place a row can disappear across a **persisted** generation is `generate`.
3. `generate` is the only function that will ever write the real manifest, so it is the only place a
   queue can be *observed* between two runs.

The test's exposure to `generate` is zero: it calls `build` twice and takes the
`except UntrustedRow: return` exit at line 496. The second residual R12 recorded — that line 496
returns green on **any** `UntrustedRow` from `build`, whatever raised it — is unchanged.

---

## 5 — the guard axis: 2 of 2 red, and 2 of 2 strengthenings silent

Baseline **111 passed**, measured by me. Every injection was proven to reproduce (or not reproduce)
its defect in a standalone probe **first**; the "proven live by" column is that measurement.

| # | delta element | proven live by | suite |
|---|---|---|---|
| F1 | `:193` outer `previous` check **deleted** | `FalsyDict`/`[]`/`7` accepted, `book_get` gone | **1 failed** ✅ `:656` |
| F1a | `:193` `type(previous) is not dict` → **`isinstance`** | `FalsyDict(<real 2-row doc>)` **ACCEPTED**, `book_get` **SILENTLY GONE** — R12's headline shape restored | **111 passed** 🔴 |
| F2 | `:452` → `return doc` (pre-round) | R12's appender: validator saw 1 row, consumer got 2 | **1 failed** ✅ `:647` |
| F2a | `:452` → `{**doc, "declarations": rows}` (no per-row copy) | *no defect restored* — the lying row is returned as a `LyingRow` and `rows_of` **REFUSES** it; strictly **safer** than what shipped | **111 passed** 🔴 |
| F2b | `:452` → `{**doc, "declarations": doc.get("declarations")}` | the original container back | **1 failed** ✅ |
| — | **CONTROL** `if lost:` → `if False:` | `book_get` dropped silently | **2 failed** ✅ |
| — | **CONTROL** `:369` `type(rows) is not list` → `isinstance` (R12's M4 — a fix from **last** round) | `validate_document` accepts a `list` subclass | **111 passed** 🔴 |

**The honest reading, both halves.** The claim *"every fix in this round has a red-able test"* is
**true for this round's `app/agentruntime/` delta as written** — a real change from R12's 5 of 5
silent, and the first two tests added to this file in three rounds. But:

* **F1a is the row that matters.** The whole content of the R12 finding was a container that lies
  (`FalsyDict.__bool__`). `type(…) is dict` catches it; `isinstance` does not; the test at `:657`
  iterates `([], "not a doc", 7, ("declarations", []))` — **four non-`dict` shapes and no subclass**.
  So the test guards the *presence* of a check and not the property the check was written for, which
  is the fifth instance of this run's "fix the member, not the set" pattern reappearing **inside the
  test for the fix for the fourth instance**.
* **F2a says the per-row `dict(r)` is not defence in depth — it is the defect** (§1b). It is the only
  variant on which the smuggled row reaches a consumer, and it has no test.
* **R12's own fixes are still unguarded.** `type(rows) is not list` at `:369` was R12's M4; a round
  later it is still silent under injection. The delta added tests for *this* round's two lines and
  none for the five R12 measured.

---

## Bypass table

| property asserted | path that defeats it | evidence | reachability |
|---|---|---|---|
| a document `validate_document` returns has been validated | a `dict`-subclass row whose `.get` lies; `dict(r)` copies storage — and the result is a **plain dict** `rows_of` then accepts | `manifest.py:378…:427` vs `:452` — executed, 3 variants | **adversarial-input only** |
| " | a row that mutates **itself** on the last read the loop performs | `manifest.py:452` — executed | **adversarial-input only** |
| " | a `dict`-subclass **document**: `contract_version` validated `'1.0.0'`, returned `'banana'` | `manifest.py:356` vs `:452` — executed | **adversarial-input only** |
| a row reaching a consumer passed every clause | **plain hand-typed JSON**: unknown row keys survive validation and steer `TakeWhileBudget` / `OrderBy` / `Filter` | `manifest.py:373-442`, `surface.py:590`,`:326`,`:198` — executed through `json.dumps`/`loads` | **production-reachable** |
| " | `rows_of` / `declarations` / `discover` / `SurfaceAssembler` never call `validate_document`; only `id` and the row type are bounded | `surface.py:54-62` — executed, 4 doors, `members:['ghost']` on the wire | **production-reachable** |
| a declaration cannot silently leave the manifest | `previous={}` or a document minus `declarations` — `.get("declarations", [])` serves a missing key as empty | `manifest.py:201` — executed | **production-reachable by caller error** |
| " | a previous-row whose `.get("id")` and `["id"]` disagree — `book_get` gone, guard silent | `manifest.py:214`/`:223` — executed | **adversarial-input only** |
| " | `generate`'s race when the file **reappears** between `exists` and `exists` | `manifest.py:281-293` — R12 §5, unchanged | **production-reachable** (a concurrent regeneration, the first cause its own comment names) |
| the returned row's `id` passed the contract | contract checks `r.get("id","")`, the return carries `r["id"]` | `manifest.py:378` vs `:452` — executed | **adversarial-input only** |
| the P4 test reds when the mechanism lands | a mechanism landing in **`generate()`** — proven draining, loadable, on disk | §4 — executed, **111 passed** | n/a (test defect) |
| the delta's fixes are guarded | the two **strengthenings** are not: `type(…) is dict` and `dict(r)` | §5 — executed, 2 controls red | n/a (test defect) |

## Red-ability table — baseline **111 passed**, measured by me at start and finish

| injection | what it models | proven live by | suite |
|---|---|---|---|
| `F1_outer_previous_check_removed` | delta element 1 removed | `FalsyDict`, `[]`, `7` accepted; `book_get` gone | **1 failed** ✅ |
| `F1a_outer_previous_isinstance` | delta element 1 **weakened to `isinstance`** | `FalsyDict(<real doc>)` accepted, `book_get` **silently gone** | **111 passed** 🔴 |
| `F2_return_doc` | delta element 2 removed (pre-round state) | R12's appender: 1 validated, 2 served | **1 failed** ✅ |
| `F2a_return_rows_uncopied` | delta element 2 **weakened**: no per-row `dict()` | *no defect restored* — `rows_of` refuses the row this variant returns | **111 passed** 🔴 |
| `F2b_return_doc_with_original_rows` | the original container, spelled differently | the appender again | **1 failed** ✅ |
| `G2_grandfathering_in_generate` | §6.4 lands in the **only real writer** | 2-row file on disk, `QUEUE=['book_get']`, drains, `load()` OK | **111 passed** 🔴 |
| `CONTROL_lost_check_removed` | rounds 1–12 gate | `book_get` dropped silently | **2 failed** ✅ |
| `CONTROL_row_type_isinstance` | **R12's own M4 fix**, one round on | `validate_document` accepts a `list` subclass | **111 passed** 🔴 |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| fix in this round's `app/agentruntime/` delta | is there a test? | can it red? | for the reason it names? |
|---|---|---|---|
| `manifest.py:193` — the outer `previous` check exists | **YES** — `test_cp1_membrane.py:651-657` | **YES** — F1 → **1 failed at `:656`**, *DID NOT RAISE* | **PARTIALLY.** It reds on the check's *absence*. It stays green when the check is weakened to `isinstance`, which re-opens R12's `FalsyDict` — the shape the finding actually was |
| `manifest.py:193` — the check is **exact-typed** | **NO** | n/a | n/a — F1a is silent, defect proven live |
| `manifest.py:452` — the return is built from `rows` | **YES** — `test_cp1_membrane.py:612-649` | **YES** — F2/F2b → **1 failed at `:647`** | **YES** — it names the appended row and that is what reds it |
| `manifest.py:452` — the per-row `dict(r)` copy | **NO** | n/a | n/a — and F2a shows the copy is the **only** variant on which the smuggled row reaches a consumer (§1b) |
| `manifest.py:369` — `type(rows) is not list` (**R12's** fix) | **NO**, one round later | n/a | n/a — still silent |
| `manifest.py:203`,`:212`,`:281-293` (**R12's** other fixes) | **NO**, one round later | n/a | n/a |
| `test_cp1_membrane.py:493-503` — the P4 partial re-admission | **YES** (it *is* the test) | **YES** on `build`-landing mechanisms (R12 measured 2) | **NO** — still green for a `generate()`-landing mechanism (§4); still reds on an exception-class change with the mechanism absent |
| `scripts/…-gate.py::_manifest_drift`, `::SINGLE_SITED` | **NO** probe in the selftest (R12 §6b) | yes | — |

## Sibling table — *a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `validate_document` returns the rows it validated | the **document stamps** — `{**doc}` re-reads `contract_version` through `__getitem__` after validating through `.get` | ❌ **NO** — §2a, the fifth TOCTOU, introduced by this fix |
| " | the **row values** — `dict(r)` re-reads storage after validating through `.get` | ❌ **NO** — §1b, the sixth, introduced by this fix, and it launders a row `rows_of` used to refuse |
| " | the **mutation class** R12 named: user code the validator calls inside its own loop | ❌ **NO** — §1c, redirected to self-mutation |
| " | the pattern that works, ten lines away in the same file: `_row` stores `list(d.members)` and M5 checks the **stored** copy | ❌ **NO** — the return still recomputes from the container |
| " | `isinstance(doc, dict)` at `:343` / `isinstance(r, dict)` at `:374` — the round applied `type(…) is` to the inner containers and left `isinstance` on both the document and every row | ❌ **NO** |
| " | the drift gate, the caller the docstring names — it **discards** the return | ❌ **NO** — §1f |
| the outer `previous` is type-checked | `.get("declarations", [])` at `:201` — the same "serve a missing key as empty" `rows_of`'s docstring is about, eleven lines away and spelled correctly there | ❌ **NO** — §2b, 2 shapes |
| " | `build`'s per-row `r.get("id")` / `r["id"]` split | ❌ **NO** — §3a, `book_get` still silently gone |
| the two fixes got a test each | a test for the five fixes **R12** measured silent | ❌ **NO** — `CONTROL_row_type_isinstance` still 111 passed |
| " | a test for each fix's **strengthening**, not just its presence | ❌ **NO** — F1a and F2a both silent |
| the P4 test drives a partial re-admission | a mechanism landing anywhere but `build()` | ❌ **NO** — §4, still green |

---

## 6 — convergence, as a measurement

**How I classified.** I enumerated every distinct defect finding in the eight verdict files of rounds
9–12 (both verifiers) — every red-circle item, every bypass-table row, every FAIL/PARTIAL row, every
"fix first" entry — **160 findings**, and placed each in one bucket **by the mechanism the verifier
had to supply to trigger it**, not by severity and not by how the verifier described it:

* **production-reachable (P)** — the vehicle is a plain value or an ordinary event: hand-typed JSON, a
  missing key, `{}`, `None`, `True`, a `float`, a bare generator, a caller passing an ordinary wrong
  argument, an **ordinary refactor**, a client disconnect, a pooled thread, a real filesystem race, a
  real amendment, a stale cache, a wrong doc/SSOT row. No custom `__eq__`, `__bool__`, `__iter__`,
  `__hash__`, `get`, metaclass or `object.__setattr__` anywhere in it.
* **adversarial-input only (A)** — the vehicle is *code*: a `dict`/`list`/`str`/`int`/`tuple`
  subclass, a forged dunder, a metaclass, a rogue class, a private-symbol import. Whoever supplies
  one is already running in the process.
* **guard-only (G)**, disclosed separately because it has **no runtime trigger at all** and folding
  it into either column would corrupt both: *"this fix is deletable and the suite stays green"*,
  *"this test cannot red"*, *"the commit message's claim is false"*. Real findings; not inputs.

**Two confounders, stated before the numbers, because ignoring them would make this an impression
again.** (i) Raw per-round totals track **verifier effort and delta size**, not defect density —
R11's delta was large and R13's is two lines. (ii) The two verifiers have **structurally different
scopes**: A grades `instrument.py` / `stream_service.py` / `knowledge_client.py`, B grades
`app/agentruntime/` and the bounds. So the series that actually controls for both is **B-only, same
role, same package, five consecutive rounds**, and that is the one to read.

### The two counts per round — all findings, both verifiers

| round | production-reachable | adversarial-input only | guard-only | total |
|---|---|---|---|---|
| 9 | 17 | 5 | 6 | 28 |
| 10 | 29 | 5 | 10 | 44 |
| 11 | 31 | 7 | 12 | 50 |
| 12 | 16 | 10 | 12 | 38 |
| **13 (B only)** | **3** | **3** | **3** | **9** |

### The controlled series — Verifier B only, the membrane and the bounds

| round | production-reachable | adversarial-input only | guard-only | total |
|---|---|---|---|---|
| 9 | 4 | 5 | 2 | 11 |
| 10 | 12 | 5 | 1 | 18 |
| 11 | 9 | 7 | 5 | 21 |
| 12 | 3 | 7 | 7 | 17 |
| **13** | **3** | **3** | **3** | **9** |

### The other controlled series — Verifier A only, the instrument

| round | production-reachable | adversarial-input only | guard-only | total |
|---|---|---|---|---|
| 9 | 13 | 0 | 4 | 17 |
| 10 | 17 | 0 | 9 | 26 |
| 11 | 22 | 0 | 7 | 29 |
| 12 | 13 | 3 | 5 | 21 |

### What the numbers say

* **In the membrane scope, both counts are falling, and R12→R13 is the first round in which the
  adversarial count fell** (7 → 3) — it had risen or held for four rounds. The production-reachable
  count fell 12 → 9 → 3 → 3. This is the answer the builder cannot see from inside: **its own
  package is converging.** The exact-type sweep, the materialise-before-iterate pattern, the closed
  `STAGE_KINDS` set and the stage-parameter bounds are why.
* **In the instrument scope the production-reachable count is not falling** — 13 → 17 → 22 → 13,
  four rounds, no trend — and it is **93% of that scope's findings** (65 of 70). Verifier A has
  reported essentially **zero** adversarial-input findings in four rounds; every one of its findings
  is a client disconnect, an ordinary refactor, a stale cache, a pooled thread or a real turn.
  *(I did not re-measure A's findings; I classified what its verdicts report, which is what Q6
  asks.)*
* **So "is the loop converging?" has two different answers, and the split is the finding.** The
  fixes are exact-type checks and materialisations in `app/agentruntime/`. Those act **only** on the
  adversarial bucket, and that bucket is the one that is emptying. The bucket that is not emptying is
  the one nothing in three deltas has addressed.
* **The number that should decide the round, though, is the closure rate, not the counts.** Counts
  reward a verifier for looking harder. Closure measures the loop.

| transition | findings the prior round left open, in this scope | closed by the next delta | rate |
|---|---|---|---|
| R11-B → R12 | 21 | 3 (R11 §1c, §1d, §1e — R12-B verified each closed) | **14%** |
| R12-B → R13 | 17 | 1 confirmed (R12 §1b's vehicle) + 2 partial (6 of 8 `previous` shapes; the dedupe half of the id split) | **~9–12%** |

**At 10% per round the six findings R12 recorded OPEN take another twenty rounds.** That is the
convergence measurement, and it is not a count of what a verifier found — it is a count of what a
delta closed.

* **And one measurement runs the other way.** Of the three defects the builder has *introduced* with
  its own fixes across R11–R13 — R11's auto-armed sink thrown away by the arming it was meant to
  survive, R12's `ContextVar` outliving its turn, and R13's `dict(r)` laundering a row `rows_of` used
  to refuse (§1b) — **two are production-reachable**. Each round's fix is adding to the column that
  is not falling.

**What this implies for the board.** Four consecutive FAILs are **not** a stalled loop in the
membrane: that scope's numbers are genuinely descending, and this round is the first with red-able
tests for its own delta. But the descent is in the adversarial column, the closure rate is ~10% per
round, and the instrument scope shows no trend at all. The measurable exit condition is a delta that
**closes a plain-value route** and one that **raises the closure rate above the discovery rate** —
§1d, §1e and §2b are three plain-value routes, each a one-line change, and none of them has been
touched in three rounds.

---

## What I would fix first

1. **Build `validate_document`'s return from the values each clause passed on, not from the
   container (§1b, §1c, §2a).** Three findings, one closure, and the pattern already exists ten lines
   up in `_row`. Today the function whose entire job is validation returns a document in which the
   contract version, the row ids, the kinds and the owners can all differ from what it checked — and
   the `dict(r)` half **launders** a row `rows_of` refused before this round.
2. **Reject unknown keys, or bound the keys the narrowing stages read (§1d).** The only
   production-reachable route in §1, and it steers a budget with a hand-typed integer.
3. **`.get("declarations")` with no default in `build`, matching `rows_of` (§2b).** Two shapes, one
   line, and the correct spelling is eleven lines away in the same repository.
4. **Give the two shipped fixes a test for their *property*, not their presence (§5).** Add
   `FalsyDict` to the `:655` loop and a lying-`get` row to the `:612` test. Both are three lines, and
   without them the next refactor that spells `isinstance` reintroduces R12's headline finding
   silently.
5. **Assert the queue through `generate()` (§4).** The mechanism's only plausible landing site is the
   one function the test never calls.
