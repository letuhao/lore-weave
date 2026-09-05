# CP-1 · round 14 · V-CODE · **Verifier B** — the membrane, which is converging

`git rev-parse HEAD` **at start:** `b30db5b8099a93fdf7ba7fafcb19a62747604672`
`git rev-parse HEAD` **at finish:** `b30db5b8099a93fdf7ba7fafcb19a62747604672`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.
`git status --porcelain` over `services/`, `scripts/` and this spec directory is empty at finish.

**Method.** Every injection is **source surgery**: the real function's source is read with
`inspect.getsource`, exactly one anchor line per edit is replaced, and the result is `exec`'d in the
module's **live** `__dict__` — identical signature, messages and globals except for the injected
line. The new object is rebound at **every** binding from an out-of-tree pytest plugin at
`pytest_configure`, i.e. **before** the test module's `from app.agentruntime import …` runs. Three
self-checks, carried forward from R12/R13:

1. the injected function must differ from the original in `co_code` **or** `co_consts` — both are
   printed per run, and a run where neither differs **aborts** with `INJECTION IS A NO-OP`;
2. `app.agentruntime.<mod>.<name> is <injected>` **and** `app.agentruntime.<name> is <injected>` are
   asserted at configure time; the run aborts if either fails;
3. a `pytest_collection_finish` hook prints whether **the test module's own binding** is the
   injected object and raises `SystemExit` if it is not.

**Every row in every table below was run with `rebound at 3 binding(s)` and
`[INJECT] test module tests.test_cp1_membrane.<name> is-injected=True` printed.** Every *silent*
(green) injection was additionally **proven to restore a real defect in a standalone in-process
probe first** — a green row whose weakening restores nothing is not a finding, and R13 measured one
of those.

**Baselines I measured myself, at start and at finish:**

| | |
|---|---|
| `python -m pytest tests/test_cp1_membrane.py -q` (from `services/chat-service`) | **113 passed**, 1 warning, ~6 s |
| `python scripts/agentruntime-membrane-gate.py` (repo root) | **exit 0** — selftest OK, 8 modules, 2 single-sited types |

113, not R13's 111: the delta adds exactly two tests.

**Scope.** R13's delta. In `app/agentruntime/` it is **two changes**: `build`'s
`"declarations" not in previous` refusal (`manifest.py:206-211`) and `rows_of`'s per-field bound
plus per-row copy (`surface.py:54`, `:64-91`). In `tests/test_cp1_membrane.py` it is **two new
tests** (`:652-679`) and **one loosened regex** (`:1461`).

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *Every row field is now bounded (`rows_of`); the production-reachable set is closed* | **FAIL, and the failure is in the round's own chosen scope.** The bound refuses **exotic** values and admits **every plain scalar** — and R13's two production-reachable vehicles were plain scalars. Measured: a hand-typed `"cost": 1000000000` still steers `TakeWhileBudget` (surface `('book_get',)` vs control `('book_get','book_list','book_zz')`), a hand-typed `"relevance": "zzz"` still steers `OrderBy` and `Filter`, and **`members: ['ghost']` — M5's whole subject, named verbatim in the commit message — still reaches the wire at all four doors**, because `'ghost'` is a non-empty string. The door that still admits every operand is **`validate_document`/`load`**, which got no bound at all |
| 2 | *The 5th and 6th TOCTOUs are still OPEN; does `rows_of`'s bound make either reachable in plain JSON?* | **CONFIRMED OPEN, both, re-measured. And the answer to the question is NO — the bound strictly NARROWS both; on this axis the triage is safe.** Executed the reverse experiment: pre-R14 `rows_of` **ACCEPTED** a laundered exotic-valued row, R14 **REFUSES** it. Plain JSON cannot drive either TOCTOU at all, and I proved why rather than asserting it: `json.loads` yields exactly-`dict` at both levels, and a plain `dict` has **one** storage, so `.get` / `__getitem__` / `dict()` cannot disagree. Reachability **adversarial-input only** stands for both. **But the triage moved a different finding across the line** — see §2d and claim 6 |
| 3 | *`.get("declarations", [])` is refused; find the remaining shape of the same class* | **PARTIAL PASS — the named site is genuinely closed (red-able, §5 F/E1), and the class survives twice in the function whose job is M5.** `manifest.py:407` `tuple(r.get("members", ()) or ())` and `:451` `r.get("members", ()) or ()`: a row with **no `members` key** is validated as declaring none and M5 checks nothing, and `members: null` / `0` / `false` all collapse to `()` — measured, all **ACCEPTED** by `validate_document`, while `rows_of` **REFUSES** three of the four. Two validators, two answers, one package |
| 4 | *The `r.get("id")` / `r["id"]` split, recorded OPEN* | **CONFIRMED OPEN, unchanged in both functions, and `rows_of`'s new bound does not touch it.** In `build` it still silently deletes a declaration — measured, `book_get` gone, loss guard silent. In `validate_document` the returned row still carries an `id` that passed no clause — measured, contract-checked `'book_list'`, returned `'!! HAND TYPED !!'` — and `rows_of` **still accepts it**, because a hand-typed string is a non-empty plain string |
| 5 | *The P4 test on a `generate()`-landing mechanism* | **CONFIRMED OPEN, unchanged from R12 and R13.** I built the mechanism, proved it live on disk (2 rows, `QUEUE=['book_get']`, drains to `[]`, `validate_document` OK, `load()` OK) and ran the suite: **113 passed**. **And the builder's claim that it reds on `build()`-landing mechanisms HOLDS** — I built one and measured **2 failed**, with the P4 test failing at `:504` for its own stated reason (`queue is NON-EMPTY (['book_get'])`), not by proxy |
| 6 | *Convergence, with this round added and the new column* | **In B's scope the production-reachable count ROSE, 3 → 8, and the closure rate is unchanged at ~8–11% for the third consecutive round.** But the new column is the one that answers the question, and it is the round's one genuine win: **findings introduced by the graded delta fell 3 → 2, and for the first time in three rounds the delta introduced NO new TOCTOU.** Full table, method and confounders in §6 |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Every value a row can carry in plain JSON being refused by `rows_of`, or every admitted value being unable to reach a narrowing decision | Enumerated the JSON value space against the bound (`str/int/bool/null/float/list/dict/huge int/negative int`), then drove each **admitted** class end-to-end through `TakeWhileBudget`, `OrderBy` and `Filter` with a control run |
| 2 | A `json.loads` document producing a row or a document on which `.get` and `dict()`/`{**}` disagree; **or** `rows_of` accepting a laundered row it refused before the round | Printed `type(...) is dict` at both levels on `json.loads` output; then ran R13's laundered rows through **both** the shipped `rows_of` and a reconstructed pre-R14 `rows_of` in one process |
| 3 | No `.get(k, default)` left in the package that serves a missing or malformed value as an empty/absent one | Mechanical sweep of every `.get(x, y)` in all 8 modules, then executed each surviving site against 7 shapes through `validate_document` **and** `rows_of` |
| 4 | The split permitting nothing a consumer can act on, in either function, after the new bound | Drove it separately in `build` (origin/loss) and in `validate_document` (contract/dedupe/return), then fed the returned row back into `rows_of` |
| 5 | The P4 test reddening with a faithful `generate()`-landing mechanism live; or *failing* to red with a `build()`-landing one | Built both, proved the `generate()` one real on disk **before** running the suite, then injected each at every binding |
| 6 | The closure rate rising above ~10%, or the delta introducing as many defects as R13's did | Re-ran every R13-B open finding as a probe and recorded closed / partial / open; classified this round's findings by the mechanism required to trigger them |

---

## 1 — the row bound: it refuses the exotic and admits the hand-typed

`surface.py:64-91`. The bound is `_is_exactly(val, (str, bool, int, type(None)))` per field, with a
`members` clause. Measured, the whole JSON value space:

| JSON value | `rows_of` |
|---|---|
| `str`, `int`, `bool`, `null`, huge `int`, negative `int` | **ADMITTED** |
| `float`, `list`, `dict` | refused ✅ |

That is a real bound on §0.14.1's *adversarial* class and it is proven live (§5, E2/E2a/E2c). It is
not a bound on the class R13 §1d and §1e reported, and both of those were the round's stated scope.

### 1a · 🔴 `members: ['ghost']` still travels to the wire — all four doors, plain JSON

The commit message: *"`members` was unbounded at four exported doors, so `members:['ghost']`
travelled to the wire."* The bound requires members to be *a plain list of non-empty strings*.
`'ghost'` is a non-empty string. Executed on a document round-tripped through
`json.dumps`/`json.loads`:

```
rows_of(doc)                                    -> ACCEPTED  members ['ghost']
declarations(doc)                               -> ACCEPTED  members ['ghost']
discover(doc, kind='tool', log=NarrowingLog())  -> ACCEPTED  members ['ghost']
SurfaceAssembler(doc).assemble(pass_number=1)   -> ACCEPTED  names ('book_list',)
```

M5 — *"a reference is a foreign key into the manifest; resolve it or do not declare it"* — is
enforced in `build` and in `validate_document`, and **not** at the door the round just bounded. The
fix bounds the *type* of the foreign key and never asks whether it resolves, which is the entire
content of the finding. **Production-reachable.**

### 1b · 🔴 a hand-typed `cost` still decides which declarations the model sees — plain JSON

R13 §1d's vehicle was `'cost': 1000000000` and `'relevance': 'zzz'` — **plain scalars**, which is
why it was classified production-reachable in the first place. Executed, three rows, one budget:

| | surface |
|---|---|
| rows carry the hand-typed `"cost": 1000000000` on `book_list` | **`('book_get',)`** — 2 of 3 withheld |
| CONTROL, every row `"cost": 1` | `('book_get', 'book_list', 'book_zz')` |

`validate_document` accepts the document; `rows_of` accepts every row; `TakeWhileBudget` reads
`row.get(stage.cost_field)` (`surface.py:618`) and cuts. Same for the ranking:
`OrderBy(keys=(("relevance","desc"),))` over hand-typed `relevance` values ordered
`['zzz','mmm','aaa']`, and `Filter(field="relevance", op="eq", value="zzz")` kept exactly the row
whose hand-typed value matched. **Production-reachable, unchanged from R13.**

### 1c · 🔴 the door that still admits every operand: `validate_document` / `load`

Q1 asks which door still admits an operand. It is the one the round did not touch.

| door | bounds a row field? |
|---|---|
| `rows_of` | yes — exotic refused |
| `declarations`, `discover`, `SurfaceAssembler` | yes, via `rows_of` |
| **`validate_document`** — exported, and the M1 drift gate's only call | **no** — the 7 contract fields, nothing else |
| **`load`** — exported | **no**, it returns `validate_document`'s output |
| **the drift gate** (`scripts/agentruntime-membrane-gate.py:361`) | **no**, and it still **discards** `validate_document`'s return (R13 §1f, unchanged) |

Measured: `{"cost": 1.5}`, `{"lane": {"a":1}}`, `{"tier": [1]}` on a row are all **ACCEPTED** by
`validate_document` and `load`, and **refused** by all three assembler-side doors. The gate is
protected today only by `doc != build([])` byte-equality over `declarations: []`, which is total and
vacuous now and evaporates at CP-4 — R13's observation, unchanged.

### 1d · 🔴 **NEW, introduced by this round:** two definitions of a valid row, and the wrong exception

This is the finding the round created. `load()` blesses a document that every consumer door then
refuses — and refuses with a bare **`ValueError`**, which is **not** an `UntrustedRow`:

```
"cost": 1.5   validate_document / load: ACCEPTED   rows_of / declarations / SurfaceAssembler: ValueError
"lane": {...} validate_document / load: ACCEPTED   rows_of / declarations / SurfaceAssembler: ValueError
issubclass(ValueError, UntrustedRow) or issubclass(UntrustedRow, ValueError)  ->  False
```

`UntrustedRow` is the package's documented refusal for *"a manifest row that did not come from an
admission, on either side of the file"* — that docstring is exactly this case — and the package's
own P4 test catches it by name (`test_cp1_membrane.py:499`). A caller that reads the catalog through
`load()` and handles `UntrustedRow` now takes an uncaught `ValueError` from the next call.

And structurally it is the defect `rows_of`'s **own docstring** is about: *"two hand-written copies
of this drifted inside a single commit… the identical malformed input, two answers."* The round
added a second, stricter definition of a valid row next to the existing one instead of moving the
existing one. **Production-reachable** — a hand-edited or mis-generated manifest is the stated
purpose of the door.

### 1e · 🔴 the top-level document is not bounded at `rows_of`

`rows_of` calls `manifest_doc.get("declarations")` and never checks what `manifest_doc` is. Executed:

```
rows_of(<dict subclass>)                      -> ACCEPTED
rows_of(<plain object exposing only .get>)    -> ACCEPTED
SurfaceAssembler(<object whose .get answers differently each call>).admitted_count = 1, names = ('book_list',)
```

Every row-level type decision in the function is `_is_exactly`; the container that supplies the rows
is not typed at all. **Adversarial-input only** for the lying-`.get` variant; the missing bound is
the finding.

---

## 2 — the fifth and sixth TOCTOUs: confirmed, and the plain-JSON question answered

### 2a · ✅ the sixth (`dict(r)`, `manifest.py:463`) is still there — re-measured

```
validate_document      -> ACCEPTED
contract checked id    -> 'book_list'   (what .get answered)
RETURNED row           -> {'id': '!!! HAND TYPED !!!', 'kind': 'nonsense', 'owning_service': '!!',
                           'lifecycle': '??', 'contract_version': 'banana',
                           'admitted_against': None, 'members': ['nope']}
returned row type      -> dict
rows_of(returned)      -> ACCEPTED ['!!! HAND TYPED !!!']
declarations(returned) -> ACCEPTED ['!!! HAND TYPED !!!']
```

**Reachability confirmed as I gave it: adversarial-input only.** It needs a `dict` subclass whose
`.get` disagrees with its storage; `json.loads` cannot make one.

### 2b · ✅ the fifth (`{**doc}`, `manifest.py:463`) is still there — re-measured

```
validate_document -> ACCEPTED
validated         -> manifest_version=1,   contract_version='1.0.0'
RETURNED          -> manifest_version=999, contract_version='banana'
```

`contract_version` is §6.4's queue comparand, the exact field the comment six lines above calls out.
**Adversarial-input only** — a `dict`-subclass *document*.

### 2c · **The answer to Q2: NO. And I ran the experiment in the direction that could have said yes.**

Plain JSON cannot drive either one, and the reason is structural rather than incidental:

```
type(json.loads(doc))            -> dict   exactly dict: True
type(row)                        -> dict   exactly dict: True
{**doc} divergence possible?     -> False  (validated value == returned value)
dict(r) divergence possible?     -> False  (validated row == returned row)
```

A plain `dict` has **one** storage. `.get`, `__getitem__`, `__contains__`, `dict()` and `{**}` all
read it, and there is no user code between them. A TOCTOU needs two readers that can be made to
disagree, and plain JSON supplies only one.

**And the `rows_of` bound moves both findings the *safe* way, measured rather than argued.** I
reconstructed the pre-R14 `rows_of` (the same function minus the field loop and the copy) and ran
both against the same laundered documents in one process:

| laundered row (out of `validate_document`) | pre-R14 `rows_of` | R14 `rows_of` |
|---|---|---|
| storage holds **plain scalars** (`kind:'nonsense'`, `contract_version:'banana'`, …) | ACCEPTED | ACCEPTED |
| storage holds an **exotic value** (`cost: SneakyCost(int)`) | **ACCEPTED** | **REFUSED** ✅ |

So R13's own §1b regression — *"the `dict(r)` half laundered a row `rows_of` used to refuse"* — is
**partially undone** by this round: the launder now only carries plain scalars through. That is the
one place the round did more than it claimed, and it is worth saying plainly because the rest of this
verdict says less.

### 2d · 🔴 but a finding *did* cross the line this round — the other way

Q2's warning is about the triage moving something into the production-reachable column. It did not
move a *TOCTOU* there. It **created** a production-reachable finding (§1d: `load()` and the four
doors now disagree about what a valid row is, and disagree with the wrong exception class), and it
**left three of the four production-reachable findings it named as its scope open** (§1a, §1b, §3).
The triage is not unsafe in the way Q2 anticipated. It is unsafe in that **the round's commit message
asserts a set closed that is measurably not closed**, and a reader of that message has no way to tell.

### 2e · the read-twice sweep, delta only

| site | check-read | use-read | verdict |
|---|---|---|---|
| `surface.py:72` → `:90` (**new**) | `r.items()` | `dict(r)` | ✅ safe — `_is_exactly(r, dict)` at `:56` guarantees one storage. The safety is entirely load-bearing on that line, which has no test of its own beyond the field loop |
| `surface.py:58` → `:90` (**new**) | `r.get("id")` | `dict(r)["id"]` | ✅ same reason |
| `manifest.py:206` → `:212` (**new**) | `"declarations" not in previous` | `(previous or {}).get("declarations", [])` | ✅ closed — `type(previous) is not dict` at `:193` means `__contains__` cannot lie. Measured: a `__contains__`-lying `previous` is refused at `:193` |
| `manifest.py:350`,`:367` → `:463` | `doc.get(k)` | `{**doc}` | 🔴 **§2b, the fifth — OPEN** |
| `manifest.py:389…:438` → `:463` | `r.get(k)` | `dict(r)` | 🔴 **§2a, the sixth — OPEN** |
| `manifest.py:225` → `:234` | `r.get("id")` | `origin[r["id"]]` | 🔴 §4a — OPEN |
| `manifest.py:389` → `:446`,`:447` | `r.get("id","")` | `r["id"]` | 🔴 §4b — OPEN |
| `manifest.py:292` → `:299` → `:300` | `ambient.exists` | `load()` then `ambient.exists` | 🔴 R12 §5 — unchanged, third read of the same fact |

**No new TOCTOU was introduced this round.** That is the first round in four for which that is true.

---

## 3 — `.get("declarations", [])`: the named site closed, the class alive in the M5 function

`manifest.py:206-211` is a real fix and it reds (§5, E1). The sweep over every `.get(k, default)` in
the package leaves seven sites; two of them are the same class:

```
manifest.py:407:  members=tuple(r.get("members", ()) or ()),
manifest.py:451:  for m in r.get("members", ()) or ():
```

Executed, plain JSON, through both validators:

| row | `validate_document` | `rows_of` |
|---|---|---|
| `members` key **ABSENT** | **ACCEPTED**, members read as absent | **ACCEPTED** |
| `members: null` | **ACCEPTED**, read as `()` | REFUSED |
| `members: 0` | **ACCEPTED**, read as `()` | REFUSED |
| `members: false` | **ACCEPTED**, read as `()` | REFUSED |
| `members: {}` | **ACCEPTED**, read as `()` | REFUSED |
| `members: []` | ACCEPTED | ACCEPTED |
| `members: "book_x"` | refused (contract) | REFUSED |

Four malformed values are served as *"this declaration references nothing"* by the function whose
own comment says *"M5 again, on the read side: a member that resolved at generation can be broken by
an edit."* A row that **had** members and whose `members` was edited to `null` loads clean and M5
checks nothing. And the absent-key case passes **both** validators, because `rows_of`'s field loop
iterates `r.items()` — **a key that is not present is never visited, so `members` is bounded only
when it is there**. **Production-reachable.**

The correct spelling is the one the round just wrote eleven lines up: `.get` with no default, then a
type check.

---

## 4 — the `id` split: what it permits now

### 4a · 🔴 in `build` — still silently deletes a declaration. `manifest.py:225` vs `:234`

A previous-row whose `.get("id")` answers `book_get` and whose `["id"]` answers `book_list`:

```
build ACCEPTED. rows: ['book_list']
the name `book_get` never entered `origin`; the loss guard is SILENT: True
```

Unchanged from R12 and R13. The round's new `"declarations" not in previous` check sits two lines
above and does not see it. **Adversarial-input only.**

### 4b · 🔴 in `validate_document` — and `rows_of`'s new bound does not narrow it

```
validate_document ACCEPTED; contract-checked id 'book_list'; RETURNED id = '!! HAND TYPED !!'
rows_of(returned) -> ['!! HAND TYPED !!']
```

`_ID = ^[a-z][a-z0-9_]*$` never saw that string, and the new field bound cannot help: the bound asks
whether the value is a plain scalar, and a hand-typed id is one. **Adversarial-input only.**

### 4c · `rows_of` itself now has the same shape — and it is safe, for one reason

`rows_of` checks `r.get("id")` at `:58` and copies via `dict(r)` at `:90`. Measured: a `dict`
subclass whose `.get("id")` lies is **REFUSED at `:56`** by `_is_exactly(r, dict)` before either read
happens. The new copy inherits its safety wholly from that line, and that line's coverage is
incidental (§5).

---

## 5 — the guard axis: 2 of 2 delta elements red, 4 of 4 strengthenings silent

Baseline **113 passed**, measured by me at start and finish. Every silent row was proven to restore
a real defect in a standalone probe **before** the suite was run; the "proven live by" column is that
measurement.

| # | delta element | proven live by | suite |
|---|---|---|---|
| E1 | `manifest.py:206` `"declarations" not in previous` **removed** | `previous={"manifest_version":1}` accepted, loss guard disabled | **1 failed** ✅ `:678` |
| E2 | `surface.py:72` field loop **removed** | every exotic value admitted at the door | **1 failed** ✅ `:668` |
| E2a | scalar bound `_is_exactly` → **`isinstance`** | `SneakyCost(int)` **ACCEPTED at the door**; a `str` subclass with a lying `__eq__` on a row field made `Filter(value='THIS-MATCHES-NOTHING')` **keep the row** — §0.14.1 re-opened, at the row | **113 passed** 🔴 |
| E2b | the `members` clause **removed** | over-reds (`members` falls through to the scalar branch) | 15 failed ✅ |
| E2c | members `_is_exactly` → **`isinstance`** | a `list` subclass whose `__iter__` yields `'ghost'` **ACCEPTED**, members reach the consumer as `['ghost']` | **113 passed** 🔴 |
| E2d | the per-row `dict(r)` copy **removed** | rows become **aliases into the caller's document** — a consumer mutating its row rewrote the manifest row (`cost=999999`, `aliased: True`); with the copy, `cost=1`, `aliased: False` | **113 passed** 🔴 |
| E2e | the non-string key check **removed** | an `int` key **ACCEPTED** | **113 passed** 🔴 |
| — | **CONTROL** `rows_of`'s `id` bound removed (pre-R14) | `id: ""`, **`id` absent**, and **`id: 7`** all ACCEPTED — the field loop does not cover them | **113 passed** 🔴 |
| — | **CONTROL** `if lost:` → `if False:` (rounds 1–13 canary) | `book_get` dropped silently | **2 failed** ✅ |
| — | **CONTROL** `type(previous) is not dict` → `isinstance` (**R13's** fix) | `FalsyDict(<real 2-row doc>)` **ACCEPTED**, `book_get` **silently gone** | **113 passed** 🔴 |
| — | **CONTROL** `type(rows) is not list` → `isinstance` (**R12's** M4) | `validate_document` accepts a `list` subclass | **113 passed** 🔴 |

**The honest reading.** The claim *"every fix has a red-able test"* is **true for the two delta
elements as written** — E1 and E2 both red at the new tests, which is the second consecutive round
with red-able guards for its own delta. But:

* **All four strengthenings are silent, and three of them are the property the bound exists for.**
  E2a and E2c restore §0.14.1 at the row — the exact class `_is_exactly` was written for — and the
  suite does not move. The new test at `:661` iterates `{"lane": {...}}`, `{"cost": [1]}`,
  `{"relevance": 1.5}`, `{"tier": {1,2}}`, `{"members": "not-a-list"}`, `{"members": [""]}`,
  `{"members": [None]}`: **seven shapes, none of which is a subclass.** It guards the *presence* of a
  check and not the *exactness* the check was written for — the same gap R13 measured in the
  `previous` test one round earlier, now reproduced inside the test written after that finding.
* 🔴 **The round LOOSENED an existing guard.** `test_cp1_membrane.py:1461` was
  `pytest.raises(ValueError, match="plain integer")` and is now `match="plain integer|plain scalar"`.
  That alternation is why E2a is green: with the door bound weakened, the `SneakyCost` row passes
  `rows_of` and is caught downstream by `_narrow`'s own check, and the test cannot tell the two
  apart. The comment above it says *"Both guards stay"* — the test can no longer prove that.
* **The per-row `dict(r)` is a real strengthening with no test.** E2d proves it: without it, every
  consumer holds a live alias into the caller's document. Worth recording as the round's one
  unadvertised improvement.
* **R12's and R13's fixes are still unguarded** — one and two rounds on, both still 113 passed.

---

## Bypass table

| property asserted | path that defeats it | evidence | reachability |
|---|---|---|---|
| every row field is bounded | the bound refuses exotic values and admits **every plain scalar**; a hand-typed `cost` cut 2 of 3 declarations, control kept 3 | `surface.py:84`; `surface.py:618`,`:354`,`:226` — executed with a control | **production-reachable** |
| `members: ['ghost']` no longer travels to the wire | `'ghost'` is a non-empty string; M5 is not enforced at the door | `surface.py:75-83` — executed, 4 doors | **production-reachable** |
| a row reaching a consumer passed every clause | `validate_document` / `load` bound no field beyond the 7 contract ones; the drift gate calls only that and **discards the return** | `manifest.py:384-453`; gate `:361` — executed | **production-reachable** |
| one definition of a valid row | `load()` accepts `"cost": 1.5`; `rows_of`/`declarations`/`SurfaceAssembler` raise **`ValueError`**, not `UntrustedRow` | `manifest.py:345` vs `surface.py:84` — executed | **production-reachable, introduced this round** |
| a missing key is not an empty one | `r.get("members", ()) or ()` ×2 — absent / `null` / `0` / `false` all served as "no members" by the M5 function | `manifest.py:407`,`:451` — executed, 7 shapes | **production-reachable** |
| `rows_of` validates what reaches it | the **document** is not typed — any object with `.get` assembles a surface | `surface.py:39` — executed | adversarial-input only |
| a validator returns what it validated | `{**doc}` re-reads the stamps: `contract_version` validated `'1.0.0'`, returned `'banana'` | `manifest.py:367` vs `:463` — executed | **adversarial-input only** |
| " | `dict(r)` re-reads storage: returned a plain `dict` carrying a row that passed no clause; `rows_of` accepts it | `manifest.py:389…:438` vs `:463` — executed | **adversarial-input only** |
| a declaration cannot silently leave the manifest | `.get("id")` / `["id"]` disagree in `build` — `book_get` gone, guard silent | `manifest.py:225`/`:234` — executed | **adversarial-input only** |
| the returned row's `id` passed the contract | contract checks `r.get("id","")`, the return carries `r["id"]`; `rows_of` accepts the hand-typed string | `manifest.py:389` vs `:463` — executed | **adversarial-input only** |
| `generate`'s `exists`→`load` re-check covers a concurrent regeneration | the file is back by the third `exists()` | `manifest.py:292-304` — R12 §5, unchanged | **production-reachable** |
| the bound's exactness is guarded | E2a / E2c: `isinstance` restores §0.14.1 at the row, suite green | §5 — executed, 2 controls red | n/a (test defect) |
| the P4 test reds when the mechanism lands | a mechanism landing in **`generate()`** — proven draining, loadable, on disk | §7 — executed, **113 passed** | n/a (test defect) |

## Red-ability table — baseline **113 passed**, measured by me at start and finish

| injection | what it models | proven live by | suite |
|---|---|---|---|
| `E1_declarations_key_check_removed` | delta element 1 removed | `previous={"manifest_version":1}` accepted, loss guard off | **1 failed** ✅ |
| `E2_field_bound_removed` | delta element 2 removed | every exotic value admitted | **1 failed** ✅ |
| `E2a_field_bound_isinstance` | delta element 2 **weakened to `isinstance`** | `SneakyCost` admitted; a lying `__eq__` on a row field decided the surface | **113 passed** 🔴 |
| `E2b_members_clause_removed` | the `members` clause removed | falls through to the scalar branch | 15 failed ✅ |
| `E2c_members_isinstance` | members **weakened to `isinstance`** | `list` subclass yields `'ghost'` to the consumer | **113 passed** 🔴 |
| `E2d_per_row_copy_removed` | the copy **removed** | rows alias the caller's document (`aliased: True`) | **113 passed** 🔴 |
| `E2e_key_type_check_removed` | the key bound removed | `int` key admitted | **113 passed** 🔴 |
| `G2_grandfathering_in_generate` | §6.4 lands in the **only real writer** | 2-row file on disk, `QUEUE=['book_get']`, drains, `load()` OK | **113 passed** 🔴 |
| `G3_grandfathering_in_build` | §6.4 lands in `build` | queue `['book_get']` | **2 failed** ✅ — P4 test fails at `:504` for its own reason |
| `CONTROL_rowsof_id_bound_removed` | the pre-R14 `id` bound | `id: ""` / absent / `7` all admitted | **113 passed** 🔴 |
| `CONTROL_lost_check_removed` | rounds 1–13 canary | `book_get` dropped silently | **2 failed** ✅ |
| `CONTROL_outer_previous_isinstance` | **R13's** fix, one round on | `FalsyDict(<real doc>)` accepted, `book_get` gone | **113 passed** 🔴 |
| `CONTROL_row_type_isinstance` | **R12's** M4, two rounds on | `list` subclass accepted | **113 passed** 🔴 |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| element of this round's delta | is there a test? | can it red? | for the reason it names? |
|---|---|---|---|
| `manifest.py:206` — `"declarations" not in previous` exists | **YES** — `:672-679` | **YES** — E1 → **1 failed** | **YES** — the missing key is what reds it |
| `surface.py:72` — a per-field bound exists | **YES** — `:652-669` | **YES** — E2 → **1 failed** | **YES** for *presence* |
| `surface.py:84` — the bound is **exact-typed** | **NO** — 7 shapes, no subclass | n/a | n/a — E2a silent, §0.14.1 restored at the row |
| `surface.py:76` — `members` is **exact-typed** | **NO** | n/a | n/a — E2c silent |
| `surface.py:73` — keys are strings | **NO** | n/a | n/a — E2e silent |
| `surface.py:90` — the per-row `dict(r)` copy | **NO** | n/a | n/a — E2d silent, and it is a genuine strengthening |
| `surface.py:58` — the `id` bound (pre-R14, now load-bearing for `dict(r)`) | **NO** | n/a | n/a — control silent for `id: ""`, absent, and `7` |
| `test_cp1_membrane.py:1461` — the budget's own cost check | **YES** | **YES** | **NO — LOOSENED this round** to `plain integer\|plain scalar`, so it can no longer tell the door's guard from the budget's |
| `manifest.py:463` (**R12/R13's** fix) — `dict(r)` / `{**doc}` | **NO** | n/a | n/a — §2a, §2b still open |
| `manifest.py:193`,`:380` (**R12/R13's** fixes) | **NO**, one and two rounds on | n/a | n/a — both controls silent |
| `test_cp1_membrane.py:493-509` — the P4 partial re-admission | **YES** (it *is* the test) | **YES** on `build`-landing — measured, fails at `:504` for its stated reason | **NO** — still green on a `generate()`-landing mechanism |
| `scripts/…-gate.py::_manifest_drift`, `::SINGLE_SITED` | **NO** probe in the selftest (R12 §6b) | yes, by hand | — |

## Sibling table — *a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `rows_of` bounds every row field | the **same bound in `validate_document`/`load`**, the exported door the M1 gate calls | ❌ **NO** — §1c, and the mismatch is itself a new finding (§1d) |
| " | the **exception class**: every other refusal on this boundary is `UntrustedRow` | ❌ **NO** — bare `ValueError` at three exported doors |
| " | **M5 resolvability**, which is what `members: ['ghost']` was about | ❌ **NO** — §1a, `'ghost'` still travels |
| " | the **plain-scalar** operands, which were R13 §1d's actual vehicle | ❌ **NO** — §1b, the budget still cuts on a hand-typed integer |
| " | the **document** container — every row-level decision is `_is_exactly`, the container is untyped | ❌ **NO** — §1e |
| " | a test for the bound's **exactness**, not its presence | ❌ **NO** — E2a/E2c/E2e silent; and `:1461` was loosened |
| `build` refuses a missing `declarations` key | `r.get("members", ()) or ()` ×2 — the identical "missing key served as empty", in the M5 function, 200 lines down the same file | ❌ **NO** — §3 |
| " | `build`'s per-row `.get("id")` / `["id"]` split, two lines below the new check | ❌ **NO** — §4a |
| the two delta elements got a test each | a test for the **five** fixes R12 shipped and the **two** R13 shipped | ❌ **NO** — both controls still 113 passed |
| the two OPEN TOCTOUs were triaged as adversarial | building the return from the values each clause passed on — the pattern `_row` already uses at `manifest.py:150` | ❌ **NO** — §2a, §2b, third round open |
| the P4 test drives a partial re-admission | a mechanism landing anywhere but `build()` | ❌ **NO** — §7, still green |

---

## 6 — convergence, with the new column

**How I classified.** Same three buckets and the same rule R13 stated, applied to my own findings by
the mechanism required to trigger them, not by severity:

* **production-reachable (P)** — the vehicle is a plain value or an ordinary event: hand-typed JSON,
  a missing key, an ordinary refactor, a real filesystem race, a caller passing an ordinary wrong
  argument. No custom dunder anywhere in it.
* **adversarial-input only (A)** — the vehicle is *code*: a `dict`/`list`/`str`/`int` subclass, a
  forged dunder, a metaclass. Whoever supplies one is already running in the process.
* **guard-only (G)** — no runtime trigger at all: *"this fix is deletable and the suite stays
  green"*, *"this test cannot red"*, *"the commit message's claim is false"*.

**The new column, and the rule I used for it.** A finding counts as *introduced by the previous
round's fixes* iff **reverting the graded delta closes it** — i.e. the defect's vehicle is a line
that delta wrote. Not "the fix was incomplete", not "the fix guarded the wrong property": those are
different failures and folding them in would inflate the column until it stopped measuring anything.
For R13 and R14 I ran the revert; for R9–R12 I classified from each verdict's own text, and I mark
those as derived rather than executed.

### The controlled series — Verifier B only, the membrane and the bounds

| round | production-reachable | adversarial-input only | guard-only | total | **introduced by the graded delta** |
|---|---|---|---|---|---|
| 9 | 4 | 5 | 2 | 11 | **2** (derived — the migration backfill; `validate_document` mutating its argument) |
| 10 | 12 | 5 | 1 | 18 | **1** (derived) |
| 11 | 9 | 7 | 5 | 21 | **2** (derived — the auto-armed sink; the scope-`else` → `withheld_json` `KeyError`) |
| 12 | 3 | 7 | 7 | 17 | **1** (derived — the 4th TOCTOU: R11's `rows = list(rows)` against `return doc`) |
| 13 | 3 | 3 | 3 | 9 | **3** (executed — the 5th and 6th TOCTOUs and §1c, all three vehicles being R12's `:452`) |
| **14** | **8** | **4** | **9** | **21** | **2** (executed — §1d's `load`/doors divergence; the loosened `:1461` regex) |

### The other controlled series — Verifier A only, the instrument (R13's figures, carried)

| round | production-reachable | adversarial-input only | guard-only | total |
|---|---|---|---|---|
| 9 | 13 | 0 | 4 | 17 |
| 10 | 17 | 0 | 9 | 26 |
| 11 | 22 | 0 | 7 | 29 |
| 12 | 13 | 3 | 5 | 21 |

*(A's R13 and R14 figures are not mine to report; this table is R13-B's, unchanged.)*

### Closure — what the delta closed, not what a verifier found

R13-B left **12** distinct findings open. Re-run as probes against this artifact:

| R13-B finding | now |
|---|---|
| §2b `.get("declarations", [])`, 2 shapes (P) | **CLOSED** ✅ |
| §1d unknown keys steering a budget (P) | **OPEN** — exotic values refused, R13's plain-scalar vehicle unchanged |
| §1e four doors, `members:['ghost']`, `kind:'nonsense'` (P) | **OPEN** |
| §2c `generate`'s `exists`→`exists` race (P) | **OPEN** |
| §1b the 6th TOCTOU (A) | **OPEN**, narrowed to plain scalars |
| §1c self-mutation during validation (A) | **OPEN** |
| §2a the 5th TOCTOU (A) | **OPEN** |
| §3a `build` id split (A) | **OPEN** |
| §3b `validate_document` id split (A) | **OPEN** |
| §1f the gate discards the return (G) | **OPEN** |
| §4 P4 test green on `generate()`-landing (G) | **OPEN** |
| §5 the two unguarded strengthenings (G) | **OPEN** |

| transition | open in this scope | closed by the next delta | rate |
|---|---|---|---|
| R11-B → R12 | 21 | 3 | **14%** |
| R12-B → R13 | 17 | 1 + 2 partial | **~9–12%** |
| **R13-B → R14** | **12** | **1** | **~8%** |

### What the numbers say

* **The production-reachable count rose, 3 → 8, and I have to state the confounder before the
  conclusion.** R13's delta was two lines and R13's scope was those two lines plus the open set;
  R14's delta is ~41 lines and **explicitly claims to close the production-reachable set**, so I
  measured that set directly. Some of the rise is my effort. But **three of the eight are R13's own
  production-reachable findings, unclosed**, and one is **new, created by this round's fix**. Those
  four are not effort.
* **The closure rate is now measured at three consecutive rounds: 14%, ~10%, ~8%.** It is not rising.
  At 8% the eleven findings left open take another two dozen rounds. This is the third round in which
  the same conclusion is reached from independent data.
* **The new column is the one number that moved the right way, and it is the round's real result.**
  Findings introduced by the graded delta: 2 → 1 → 2 → 1 → 3 → **2**, and — more importantly — the
  read-twice sweep of the delta (§2e) found **no new TOCTOU**, the first round in four for which
  that is true. R13's delta created two TOCTOUs in two lines; R14's created none in forty. The
  builder has stopped adding to the column that is not falling. Both of R14's introduced findings
  are of a milder class: a validator/consumer disagreement and a loosened test regex, neither of
  which laundered anything.
* **So the loop's termination condition is now visible and it is not met.** Discovery is running at
  roughly 20 findings per round in this scope and closure at 1. The number that would say the loop
  terminates is closure ≥ discovery, and the *introduced* column reaching zero is a precondition for
  that, not a substitute. The introduced column is nearly there. The closure column has not moved in
  three rounds.
* **Grading the choice of scope, which the prompt asks for directly.** Fixing only the
  production-reachable set was the right call — R11 convicted the everything-at-once cadence and
  R13 measured the two columns diverging. **The execution of that choice failed:** of the four
  production-reachable findings R13-B recorded, the round closed **one** — the one-line one — and
  the commit message asserts the other three closed by name (`members:['ghost']` is quoted in it
  verbatim). A correct scope choice reported as complete when it is 25% complete is worse than the
  wrong scope choice reported honestly, because the next round's prompt will not re-list them.

---

## 7 — the P4 test: `generate()` still invisible, `build()` confirmed red

`tests/test_cp1_membrane.py:493-509`. **Confirmed OPEN, unchanged from R12 and R13.**

I built §6.4's mechanism inside `generate()` — a declaration failing a breaking amendment stays in
the runtime carrying its origin stamp and its old `admitted_against`; the queue is the rows whose
`admitted_against` is not the document's version — and proved it real **before** running the suite:

```
gen1 (1.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','1.0.0')   queue = []
breaking amendment to 2.0.0 (CONTRACT_VERSION rebound in BOTH contract and manifest); book_get NOT re-admitted
gen2 (2.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','2.0.0')   QUEUE = ['book_get']
rows ON DISK: ['book_get','book_list']    queue on disk: ['book_get']
validate_document(on-disk): OK            load(): ['book_get','book_list']
gen3  book_get re-admitted                                              QUEUE = []   ← drains
```

**Suite: 113 passed**, with `[G2] test module tests.test_cp1_membrane.generate is-injected=True`
printed. The mechanism does not touch `build()`, so `build`'s loss refusal — the test's only exit —
never fires, and the test takes its `except UntrustedRow: return` at `:499` on a runtime where
§6.4's queue is live, on disk, and draining.

**And the builder's claim that it reds on `build()`-landing mechanisms HOLDS.** I built one (carry
the lost rows forward instead of raising) and measured **2 failed**, with the P4 test itself failing
at `:504`:

```
AssertionError: §6.4's re-admission queue is NON-EMPTY (['book_get']) — the grandfathering mechanism has LANDED.
```

That is the test failing for its own stated reason, not by proxy on `build`'s refusal — a genuine
improvement over R11, and it is worth recording that this half of the claim is true. The exposure to
`generate` remains zero.

---

## What I would fix first

1. **Move the row bound into `validate_document`, and delete the second copy (§1c, §1d).** One
   definition of a valid row, one exception type, in the function the drift gate calls. Today the
   package has two, they disagree in plain JSON, and the stricter one raises the wrong class.
2. **Bound the row fields the narrowing stages actually read, or reject unknown keys (§1b).** The
   bound as shipped stops an adversary and does not stop a text editor, and R13's finding was about
   the text editor. A hand-typed integer still decides which declarations the model sees.
3. **Enforce M5 at `rows_of`, or stop claiming `members:['ghost']` is closed (§1a).** The four doors
   have the `ids` set in hand; resolvability is three lines.
4. **`r.get("members")` with no default, twice (§3).** Same line, same file, same class the round
   just fixed 200 lines up — and one of the two sites is M5's read-side enforcement.
5. **Test the bound's *exactness*, and restore `:1461` (§5).** Add one `dict`-subclass row and one
   `int`-subclass field to `:661`, and split the loosened alternation back into two assertions. As
   shipped, the next refactor that spells `isinstance` re-opens §0.14.1 at the row silently, and the
   one test that could have noticed was widened this round to accept either answer.
6. **Build `validate_document`'s return from the values each clause passed on (§2a, §2b).** Third
   round open, three findings, one closure, and the pattern is at `manifest.py:150`.
7. **Assert the queue through `generate()` (§7).** The mechanism's only plausible landing site is
   still the one function the test never calls.
