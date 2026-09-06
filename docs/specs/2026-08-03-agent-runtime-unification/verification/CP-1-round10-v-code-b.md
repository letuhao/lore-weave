# CP-1 · round 10 · V-CODE · **Verifier B** — 1.8a's bounds, and the manifest after the backfill was removed

`git rev-parse HEAD` **at start:** `a43c24fcc0d14fba34977c2c61506cf6380ba690`
`git rev-parse HEAD` **at finish:** `a43c24fcc0d14fba34977c2c61506cf6380ba690`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.
All injections came from **out-of-tree pytest plugins** (`inject_b.py`, `inject_b2.py`, in the session
scratchpad) that rebind package callables at `pytest_configure` — i.e. **before** the test module's
`from app.agentruntime import build` runs — plus standalone scripts driving the public API against
`tempfile` paths. Nothing was run against the live system.

**Baseline I measured myself:** `python -m pytest tests/test_cp1_membrane.py -q` from
`services/chat-service` → **109 passed, 1 warning, 7.24s**.
`python scripts/agentruntime-membrane-gate.py` → **exit 0** (selftest OK — 7 import shapes, 3 forgery,
14 ambient; 8 modules, 2 single-sited types).

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *`_is_exactly` is the single identity helper, used at every site that decides a type, and undefeatable* | **FAIL** — the helper itself is sound (four forgeries executed, all blocked), but `rows_of` still decides a type with `isinstance`, and **the identity check it powers is bypassed wholesale by a TOCTOU**: `validate_pipeline` and the assembly loop iterate the caller's `pipeline` twice |
| 2 | *`op`, `direction`, `field`, `cost_field`, `k`, `budget`, `names`, `keys`, `stage`, `reason` and the row-side `cost` are all bounded* | **FAIL** — every one of those eleven is genuinely closed (R9-B1…B5 re-executed, all refused). **Four other operands are not**: `assemble(pass_number=)`, `discover(kind=)`, `discover(pass_number=)`, and the row side beyond `cost` — including `row["id"]`, which defeats an `AllowList` silently |
| 3 | *The backfill is gone and `load()` is strict; `validate_document` no longer mutates, including nested* | **PASS** — verified by execution on all four shapes through four entry points; no mutation top-level, nested, or on the refusal path. One named residual: two public doors reach rows with **no** validation at all |
| 4 | *`build()` refuses to lose a declaration; the drift gate's `build([])` still works* | **PASS** — re-verified through `build()` and the real writer; gate exit 0 and `doc == build([])`. One residual on the exported path |
| 5 | *The P4 defect-assertion test now asserts the amendment took, so it cannot pass for the wrong reason* | **PARTIAL FAIL** — all five modes the prompt names are closed and measured RED. **It still passes for the wrong reason, and the reason is the opposite one: it stays GREEN when the grandfathering mechanism lands**, which is the one event its docstring and §0.14.1c both say it exists to catch |
| 6 | *§0.14.3's `pass` scope is true of the code for all three row shapes, including the DB column* | **PASS with three residuals** — all three shapes match the table exactly, executed key-set by key-set. The residuals are two dispatch sites over the scope enum that handle 3 of 3 and 2 of 3, and one shared dedupe namespace |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Any construction that makes `type(x) is y` answer wrongly (metaclass `__eq__`/`__hash__`, `__class__` property, `__instancecheck__`, `__class__` assignment); **or** any object that reaches `keep()`/`sort()` without passing the identity check at all; **or** a type decision in the package spelled some other way | Executed all four forgeries against `validate_pipeline`; then enumerated every `isinstance(` / `type(…) is` in the package by regex and asked of each whether the checked value and the *used* value are the same object |
| 2 | Any caller-supplied value that reaches a narrowing decision, a `{tool, stage, reason, pass}` record, `Surface.names`, `Surface.withheld`, `asdict`, or `canon.digest` without an exact-type bound | Enumerated every parameter of every public entry point (`Filter/AllowList/DenyList/OrderBy/TopK/TakeWhileBudget/__init__`, `SurfaceAssembler.__init__`, `.assemble`, `discover`, `rows_of`) **plus every row-side value the six kinds read**, and executed a probe per operand |
| 3 | A document `load()` accepts that round-9's reader would have refused; any shape of mutation — top-level, nested, or on the refusal path; a second door that reaches rows unvalidated | Rebuilt era A / era B / era C / the hand-edited `"99.0.0"` row, fed each through `validate_document`, `load()`, `generate()` and `generate(bootstrap=True)`; compared JSON bytes **and nested object identity** before/after; then walked `__all__` for row-readers |
| 4 | A `generate()`/`build()` sequence that drops a row without raising; a legitimate operation the refusal now blocks; the gate's `build([])` broken | Drove the loss through both `build()` and the real writer, checked the file bytes after the refusal; drove `build([])`, `build([], previous=…)`, four malformed `previous` shapes; ran the gate |
| 5 | The test passing while: the amendment did not happen, only one of the two bindings moved, there were zero or one rows, `build` raised, **or the mechanism the test exists to detect had actually landed** | Six injections, one per mode, each applied at `pytest_configure` so the test module binds the injected object; then a seventh modelling a real §6.4 queue, proven to produce and drain a non-empty queue before it was run against the suite |
| 6 | Any of the three shapes missing a field the table requires, carrying `tool` where the table forbids it, dropped by reconciliation, or unserialisable at the column; any consumer of the scope enum that does not handle all three | Executed all three record paths and compared key-sets against the table programmatically; then grepped every dispatch over `SCOPE_*` and fed each an unhandled value |

---

## 1 — the identity helper is sound; **the check it powers is bypassed before it runs**

### 1a · the helper cannot be defeated — verified by execution, not by reading

`_is_exactly` (`surface.py:82-94`) reads `type(value)`, which reads `ob_type` directly and dispatches
nothing. All four attacks executed:

| attack | result |
|---|---|
| metaclass `__eq__`/`__ne__`/`__hash__` returning `Filter`-equality | **REFUSED**. (`type(x) == Filter` → `True`; `type(x) is Filter` → `False`) |
| `@property def __class__(self): return Filter` | **REFUSED**. (`isinstance` → `True`; `type(x) is Filter` → `False`) |
| `__instancecheck__` on the metaclass | **REFUSED** |
| `instance.__class__ = Filter` (a real `ob_type` swap, matching `__slots__`) | **REFUSED** — `object layout differs` |

R9's B3/B4 are closed with it: a metaclass-forged `str` subclass is now refused as a `Filter.value`
both as a scalar and as a **forged element inside a real tuple**, so the digest collision that gave
two narrowings one content address is unreachable at construction.

### 1b · the site that still does not use it — `surface.py:40`

```python
rows = manifest_doc.get("declarations")
if not isinstance(rows, list):        # every other type decision in this file is exact
```
Executed: a `list` subclass whose `__iter__` returns a different list is accepted, and
`SurfaceAssembler`'s baseline — the denominator of the conservation law — becomes whatever `__iter__`
produced, not what `len(doc["declarations"])` says. Six further type decisions
(`surface.py:225,232,265,273,393`, and `_is_exactly`'s own `isinstance(want, tuple)` at `:94`) spell
`type(x) is y` inline rather than calling the helper. Those are behaviourally identical and I record
them only because the docstring's claim is *"One helper now, so there is nowhere for a fourth site to
disagree"* — there are six places that could, and one (`:40`) already does.

### 1c · 🔴 **THE CLOSED SET IS CHECKED ON ONE ITERATION AND USED ON ANOTHER** — `surface.py:484` vs `:497`

```python
validate_pipeline(pipeline)          # :484  — iteration #1
...
for stage in pipeline:               # :497  — iteration #2
```

`pipeline` is caller-supplied and never materialised. Nothing requires the two iterations to yield
the same objects. Executed — a class **never imported from this package**, four lines, holding a
lambda, exactly the shape `STAGE_KINDS` was written to make impossible:

```python
class TwoFacedPipeline:
    def __iter__(self):
        self.n += 1
        return iter(self.honest if self.n == 1 else self.rogue)   # six kinds, then a closure
```

| measured | value |
|---|---|
| `assemble(pass_number=1, pipeline=TwoFacedPipeline(...))` | **ACCEPTED** |
| `Surface.names` | `('t3',)` — chosen by the lambda |
| iterations of the pipeline | 2 |
| conservation law | **balanced** (4 admitted = 1 offered + 3 registered) |
| `withheld` | three records, `stage: 'rogue'`, `reason: 'because I said so'` |

The rogue stage narrowed, registered, balanced the law, and `validate_pipeline` said nothing —
because `validate_pipeline` inspected a *different* six objects. Every property §0.14.1 buys by
closing the kind set is restored to a closure by one `__iter__`, and it is reached through the
ordinary public signature with no private symbol and no `object.__setattr__`.

**And the accidental form is worse than the adversarial one.** A bare generator:

```python
assemble(pass_number=1, pipeline=(s for s in [Filter(..., op="eq", value="t0")]))
→ names ('t0','t1','t2','t3')   withheld ()
```
`validate_pipeline` consumed the generator, so the loop saw nothing: **the pipeline silently did not
run.** No exception, no record, a surface four times the size the caller asked for. The annotation
says `Sequence[object]`; the standing rules say a declared type is vacuous, and this is the
demonstration. One line — `pipeline = list(pipeline)` before `validate_pipeline` — closes both.

---

## 2 — the eleven named operands are bounded. **Four others are not.**

R9-B1…B5 re-executed against this artifact — every one **CLOSED**:

| R9 finding | probe | now |
|---|---|---|
| B1 `Filter.op` unbounded | `op=SneakyOp('regex')`, `op=OpObj()` | refused, `_plain(self.op, str, "op")` |
| B2 `OrderBy` direction unbounded | `direction=SneakyDir('NONSENSE')` | refused |
| B3 `SCALARS` by `==` | `value=Twin('t0')`; forged **element** of a real tuple | both refused |
| B4 digest collision | — | unreachable; construction refuses first |
| B5 row-side `cost` `isinstance` | `SneakyCost(int)` with `__radd__` under `budget=1` | refused |

### 2a · `assemble(pass_number=)` — `surface.py:480`

The only check is `if pass_number < 1`. It is not `_plain`-checked, and it reaches `Surface.pass_number`,
`NarrowingLog.record`, `Narrowing.as_record()["pass"]`, and **the `withheld_tools` database column**.

| probe | result |
|---|---|
| `pass_number=True` | **accepted**; `Surface.pass_number is True`; record `pass: True` |
| `pass_number=1.5` | **accepted**; record `pass: 1.5`; `json.dumps` ok; **`canon.digest` → `NotCanonicalisable`** |
| `pass_number=10**30` | accepted |
| object with `__lt__`→`False`, `__eq__`→`False` | fail-closed: the conservation law raises (`registered 0`) |
| object with `__lt__`→`False`, `__eq__`→`True` | **accepted**; a foreign log entry is matched, and `Surface.pass_number` is a live object |

`1.5` is verbatim R9-B2's shape one field over: *a `{tool, stage, reason, pass}` record that cannot
be content-addressed*, arriving from a legal call. `canon` refuses floats **precisely** so a
representation choice cannot be made invisibly — and the operand that reaches it has no bound.

### 2b · `discover(kind=)` — `surface.py:622`, and `discover(pass_number=)` — `:596`

`discover(kind=…)` is the module's **second removal path** (its own docstring says so). Its operand
is checked only for `is None`:

```python
if row.get("kind") == kind:     # `==`, dispatched to the operand
```
Executed with a `SneakyKind` whose `__eq__` runs `str(other).startswith("t")`:

* `__eq__` invoked **once per row** — arbitrary logic deciding a narrowing, which is the exact thing
  `Filter.value`'s bound exists to prevent, reached through the sibling function that bound never got.
* the record's `reason` is `f"… discovery asked for {kind!r}"`, so **`__repr__` writes caller-controlled
  text into the persisted reason**. Measured: `reason: "kind is 'skill', discovery asked for !!<caller code ran in the reason string>!!"`.
* `discover(pass_number=2.5)` → record `pass: 2.5` → `canon.digest` raises. Same failure as 2a, second door.

### 2c · the row side, beyond `cost`

R10 bounded the row-side `cost` (`surface.py:565`) and stopped there. The other three row-side reads
are unbounded, and one of them defeats a stage outright:

| read | site | measured |
|---|---|---|
| `r[field]` as a sort key | `:308` | a row value with a custom `__lt__` chose the `TopK(k=1)` survivor → `('t2',)` |
| `row.get(self.field)` compared to `value` | `:180-182` | a row value with `__eq__`→`True` matched `Filter(field="kind", op="eq", value="tool")` |
| **`row.get("id")`** | `:199` (`AllowList.keep`) | `AllowList(names=("aa",))` over a row whose `id` is a `str` subclass with `__eq__`→`True` **kept both rows** → `names=('aa','zz')`, `withheld=()` |

The third is the sharpest. `AllowList` is documented as *"Explicit set membership — the always-hot
core"*, and a declaration it does not name was offered to the model **with no record**. The
conservation law cannot see it: nothing was dropped, so nothing is missing. `row["id"]` also lands in
`Surface.names` and in every record's `tool` field. Rows loaded through `load()` are JSON and
therefore plain — but `SurfaceAssembler(dict)` does not require that provenance (see §3b).

---

## 3 — the backfill is gone, `load()` is strict, and `validate_document` does not mutate

**3a · no old-shape document is silently accepted.** Every historical shape, through every door:

| shape | `validate_document` | `load()` | `generate()` | `generate(bootstrap=True)` |
|---|---|---|---|---|
| era A — `contract_version` only | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` |
| era B — `admitted_against` only | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` |
| era C — both | ACCEPTED | ACCEPTED | OK | OK |
| hand-edited `admitted_against: "99.0.0"`, no origin | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` |

Round 9's headline finding — a hand-edited row laundering `"99.0.0"` into a permanent, carried origin
— is **closed at the source**. The direction chosen is the honest one: the era-A/era-B asymmetry R9
recorded is gone because *neither* is repaired now, and the justification (`declarations: []` is
committed, so the migration has no subject) is checkable and I checked it: the committed manifest is
`{'manifest_version': 1, 'contract_version': '1.0.0', 'declarations': []}`.

**3b · mutation — none, at any depth.** Measured on a document with a nested `members` list:

| property | result |
|---|---|
| JSON bytes identical after `validate_document` | **True** |
| same object returned (`out is doc`) | **True** |
| nested object identity preserved (`doc`, `declarations`, `declarations[0]`, `members`) | **True** |
| unchanged on the **refusal** path | **True** |

The M1 drift gate's `validate_document(doc)` → `doc != build([])` comparison therefore compares the
document it read. Confirmed against the real committed file: mutated → `False`, `doc == build([])` → `True`.

**3c · the residual: two public doors reach rows with no validation at all.** `load()` being strict
does not make the package strict. `declarations` and `SurfaceAssembler` are both in `__all__` and
neither calls `validate_document`:

```
declarations(<era-B doc>)                → ['book_get','book_list']       # load() refuses this doc
SurfaceAssembler(<era-B doc>).admitted_count → 2
SurfaceAssembler({"manifest_version": 99, "contract_version": "banana",
                  "declarations": [{"id": "typed_by_hand"}]}).assemble(pass_number=1)
                                          → names ('typed_by_hand',)
```
That is `UntrustedRow`'s own sentence — *"a row typed in by hand reached the assembler having passed
no clause"* — reached through the assembler's constructor rather than through the file. It is a
pre-existing property of the M2 door, not something round 10 broke, and `SurfaceAssembler`'s docstring
already says it takes any dict; I record it because the claim under test is about what is *accepted*,
and the strictness now lives on one of the three doors that read rows.

---

## 4 — `build()` refuses to lose a declaration

Re-verified after this round's changes, through both paths:

| operation | result |
|---|---|
| `build([book_list], previous=<2 rows>)` | `UntrustedRow: ['book_get'] are in the previous manifest …` |
| `generate([book_list], path=<2-row file>)` | refused, and **the file is byte-identical afterwards** |
| `build([])`, `previous=None` (the drift gate's call) | OK → `declarations: []` |
| `build([], previous=<2 rows>)` | refused — correct per §1, and the gate never does this |
| duplicate ids in `admitted` | refused (`UnresolvedReference`) |
| `previous` row whose `id` is a `str` subclass with `__eq__`→`False` | refused — **fail-closed**: the set difference reports a false loss rather than missing a real one |
| the gate end-to-end | **exit 0**; `doc == build([])` → `True`; `validate_document` did not mutate |

**The residual, on the exported path only:** `previous={"declarations": None}` and `previous={}` both
produce an empty `origin`, so the loss guard has nothing to compare and silently does not fire.
Unreachable through `generate()` — `load()` requires `declarations` to be a list — but `build()` is
exported and its `(previous or {}).get("declarations", []) or []` treats *"the key is `None`"* as
*"there was no previous"*, which are different facts. One line: refuse a `previous` whose
`declarations` is present and not a list, the same way `validate_document:328` already does.

The known structural cost is unchanged and worth restating: the gate's `expected = build([])` means
the drift check goes **permanently red on the first non-empty manifest** (CP-4). Correct today, and
it has no subject to be wrong about; it is not a round-10 regression.

---

## 5 — the P4 defect-assertion test: **five doors closed, and the sixth is the one that matters**

`test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE`
(`tests/test_cp1_membrane.py:432-469`). Every mode the prompt names, one injection each, applied at
`pytest_configure` so the test module binds the injected object:

| injection (models…) | P4 test | requirement |
|---|---|---|
| `amend_is_a_noop` — `_amend` rebinds nothing (**R9's finding**) | **RED** | ✅ closed by `assert after["contract_version"] == "2.0.0"` |
| `amend_contract_only` — only `contract.CONTRACT_VERSION` moves | **RED** | ✅ the header stays `1.0.0` |
| `amend_manifest_only` — only `manifest.CONTRACT_VERSION` moves | **RED** | ✅ `admitted_against` stays `1.0.0` |
| `build_returns_no_rows` — zero rows | **RED** | ✅ `assert len(...) == 2` |
| `build_returns_one_row` — a fixture that never had two | **RED** | ✅ |
| `build_raises` | error, not a pass | ✅ |

**Round 9's defect is genuinely repaired, and the repair is tight**: the two assertions added prove
*both* bindings moved, which is the exact failure the prompt says has produced a bogus measurement in
this run before.

### 🔴 5a · it still passes for the wrong reason — and the wrong reason is that **the defect is gone**

The docstring says: *"It turns red the day the grandfathering mechanism lands — which is exactly when
the claim above stops being true and this test should stop being here."* §0.14.1c's table repeats it
as the enforcement for the transferred P4 item: *"a test that asserts the defect, so it reds when the
mechanism lands."*

I built the mechanism §6.4 describes — a declaration that fails a breaking amendment **stays in the
runtime** carrying the stamp it was last checked against — and proved it is a real, draining queue
before running it against the suite:

```
gen 1 (1.0.0)                                   queue = []
breaking amendment; book_get is NOT re-admitted
gen 2 (2.0.0)  book_get ('1.0.0','1.0.0')       QUEUE = ['book_get']   ← non-empty, and the row stayed
               book_list('1.0.0','2.0.0')
gen 3, book_get re-admitted                     QUEUE = []             ← drains
```

Run against the exact call sequence the test makes:

```
len(doc['declarations']) == 2          → True
queue == []                            → True
after['contract_version'] == '2.0.0'   → True
len(after['declarations']) == 2        → True
{admitted_against} == {'2.0.0'}        → True
```

**Every assertion holds while the mechanism is live and draining.** Full suite under the strict
injection (one that validates `previous` exactly as `build()` does, so nothing else is perturbed):
**1 failed, 108 passed** — and the single failure is
`test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST`, i.e. the test whose *job* is to assert the
mechanism is unbuilt. The P4 defect-assertion test does not move.

**Why.** A queue entry requires a row present in `previous` and absent from `admitted`. The test only
ever calls `build` with **every** declaration re-admitted, so on its call sequence the queue is empty
whether the mechanism exists or not. Assertion 1 (`queue == []`) is therefore not a claim about the
mechanism — it is a restatement of *"a fresh admission stamps the live constant"*, which is true on
both sides of the transition. The test names the right defect; it drives the one path on which the
defect and its repair are indistinguishable.

**One closure, inside the existing test**, using the refusal that is already there:

```python
# the queue can only form on the carry-forward path; drive it, and assert the refusal that
# stands in for the missing mechanism. When the mechanism lands this raises no longer, and
# THIS is the line that reds.
with pytest.raises(UntrustedRow, match="IS NOT BUILT"):
    build([admit(_tool("book_list"))], previous=after)
```

### 5b · one more injection the test cannot see (for the record, not as a finding against it)

`build_ignores_previous` — the origin carry deleted — leaves the P4 test **GREEN**. That is correct
division of labour: `test_two_rows_CAN_carry_different_stamps` and
`test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE` both red on it. Noted only so the reader does
not mistake it for a second hole. `admitted_against_is_the_constant` — P4 in its purest form — leaves
the whole suite green, which is the intended behaviour of a test that asserts a defect.

---

## 6 — the `pass` scope, §0.14.3's table against the code and the column

Executed all three record paths and compared key-sets programmatically against the table:

| `scope` | table requires | code emits (minus `segment`) | verdict |
|---|---|---|---|
| `declaration` | `{scope, tool, stage, reason, pass}` | `{scope, tool, stage, reason, pass}` | **match** |
| `catalogue` | `{scope, stage, reason, pass}` + `count` only when known, **no `tool`** | `{scope, stage, reason, pass}`; `count` present only when passed | **match** |
| `pass` | `{scope, stage, reason, pass}`, **no `tool`** | `{scope, stage, reason, pass}` | **match** |

* **What reaches the column**: `withheld_json()` is what the INSERT receives, and it is
  JSON-serialisable for all three. Reconciliation drops a `declaration` row whose tool *was*
  advertised and keeps `catalogue` and `pass` unconditionally — correct, and executed.
* `count` is optional in fact, not only in the docstring: cold → absent, warm → `count: 17`.
* `pass: None` is reachable (a scope row before any `record_pass`) and lands in the column. Disclosed
  in the code as a correctness floor; consistent with the table, which does not forbid it.
* Every entry carries `segment`, which §0.14.3's table does not list. Additive, disclosed at F-48,
  and load-bearing for `segment_merge_sql` — not a discrepancy, but the table is the SSOT and does
  not mention it.

**The spec's table is true of the code.** Three residuals, all about the *enum* rather than the shape:

**6a · `absorb`'s `else` is a string-dispatch default over a three-valued enum** —
`instrument.py:575-576`:
```python
else:
    self.record_withheld(row["tool"], ...)      # unconditional row["tool"]
```
Executed: a sink row with a fourth scope (`{"scope": "turn", …}`) or with `scope` omitted →
**`KeyError: 'tool'`**. That is the *identical* crash `record_catalogue_withheld`'s own docstring
documents — *"the drain reads `_sw["tool"]` unconditionally, so the row this recorder was built to
carry raised `KeyError: 'tool'` the moment it arrived"* — re-created inside the function written to
fix it. And the blast radius is now **larger**: `withheld_json()` calls `absorb` unconditionally on
every terminal path, so one malformed sink row no longer loses a record, it fails the whole terminal
write. Fail toward the record: `else` should refuse the *row*, not the turn.

**6b · the second dispatch over the same enum handles 2 of 3** — `stream_service.py:6980-6986`:
```python
if _w.get("scope") == instrument.SCOPE_PASS or _w.get("tool") == "*":
    ...
_advertised.record_withheld(_w["tool"], ...)     # SCOPE_CATALOGUE lands here
```
`absorb` was taught all three scopes; this consumer of the same list was taught `pass` and the legacy
sentinel and **not `catalogue`**. Latent today — I traced both producers of `_adv_ev["withheld"]`
(`:2252` declaration-shaped, `:2353` `SCOPE_PASS`), and no catalogue row travels that path. It is the
run's recurring shape: the correction applied to one member of a set, with the unhandled member's
failure mode being the documented dead turn.

**6c · one `_seen` set, two key namespaces** — `instrument.py:462` keys on `(tool, stage, pass)`,
`instrument.py:538` on `(scope, stage, pass)`. They collide when a declaration id equals a scope name.
`catalogue` and `pass` both match the contract's `_ID` (`^[a-z][a-z0-9_]*$`) — measured, both legal.
Executed: with id `catalogue` and a shared stage at the same pass, **whichever arrives first
suppresses the other entirely** (declaration-first → only `['declaration']`; scope-first → only
`['catalogue']`). Not reachable today (no declaration is admitted, and the live scope rows use
`catalogue_fetch` / `pass_offered_no_tools`, which no declaration row uses), so I grade it latent —
but CP-4 admits ids, and the thing that gets silently dropped is the outage record the whole scope
extension exists to guarantee.

---

## Bypass table

| property asserted | path that defeats it | evidence |
|---|---|---|
| a stage is one of the six kinds, by identity | **`pipeline` is iterated twice** — `validate_pipeline` checks one iteration, `assemble` uses another. A rogue class holding a lambda narrowed, registered, and balanced the conservation law | `surface.py:484` vs `:497` — executed, `names=('t3',)` |
| a pipeline handed in is the pipeline that runs | a bare generator is consumed by `validate_pipeline`; the loop then sees nothing and **the whole pipeline silently no-ops** | executed — `Filter` keeping only `t0` yielded all four names |
| `type(x) is y` cannot be forged | **none found** — metaclass, `__class__` property, `__instancecheck__`, `__class__` assignment all blocked | executed, four probes |
| every operand reaching a narrowing decision is exact-typed | **`assemble(pass_number=)`** — only `< 1` is checked; `1.5` produces a record `canon.digest` refuses | `surface.py:480` — executed |
| " | **`discover(kind=)`** — `==` dispatched per row; `__repr__` writes caller text into the persisted `reason` | `surface.py:622,627` — executed |
| " | **`discover(pass_number=)`** — same canon failure, second door | `surface.py:596` — executed |
| the row side is bounded | only `cost` is. A row `id` with `__eq__`→`True` **defeated `AllowList`** and was offered with no record; row sort values chose the `TopK` victim; a row value matched a `Filter` it should not | `surface.py:199,308,180` — executed |
| the strictness of `load()` protects the assembler | `SurfaceAssembler(dict)` and `declarations(doc)` are in `__all__` and validate nothing — pure junk assembled and offered | executed |
| a declaration cannot silently leave the manifest | **none found** on the real path. `previous={"declarations": None}` disables the guard through the exported `build()` only | `manifest.py:189` — executed |
| the backfill / mutation defects of round 9 | **none found** — all four shapes refused at all four doors; no mutation at any depth or on the refusal path | executed |
| the P4 defect test cannot pass for the wrong reason | **it passes when the grandfathering mechanism has landed** — the state it exists to detect | §5a — executed, 1 failed / 108 passed, and the failure is a different test |
| §0.14.3's three row shapes | **none found** — all three match the table exactly at the column | executed, key-set by key-set |
| every consumer of the scope enum handles all three | `absorb`'s `else` → `KeyError: 'tool'`; `stream_service.py:6981` omits `catalogue`; `_seen` collides `catalogue`/`pass` with legal declaration ids | `instrument.py:575`, `:462`/`:538`, `stream_service.py:6981` — executed |

## Red-ability table — baseline **109 passed** (measured by me, `-q`, 7.24s)

| injection | what it models | result |
|---|---|---|
| `amend_is_a_noop` | **round 9's finding**: the amendment helper stops amending | 3 failed — **incl. the P4 defect test** ✅ repaired |
| `amend_contract_only` | only `contract.CONTRACT_VERSION` rebound | 1 failed — the P4 defect test |
| `amend_manifest_only` | only `manifest.CONTRACT_VERSION` rebound | 3 failed — incl. the P4 defect test |
| `build_returns_no_rows` | the queue has nothing to look at | 20 failed |
| `build_returns_one_row` | a fixture that never had two declarations | P4 test RED |
| `build_raises` | `build` unavailable | error, not a pass |
| **`grandfathering_landed_strict`** | **§6.4's mechanism LANDS and the queue drains** | **1 failed / 108 passed — the P4 defect test PASSES** 🔴 |
| `build_ignores_previous` | the origin carry deleted | 4 failed (P4 test green — correct, other tests own it) |
| `admitted_against_is_the_constant` | P4 in its purest form | 109 passed — correct for a defect-assertion suite |
| `plain_is_a_noop` | the exact-type operand bound removed | 3 failed |
| `is_exactly_by_equality` | the identity helper reverts to `in` | 1 failed |
| `kind_set_by_equality` | `type(s) in _KIND_SET` restored | 4 failed |
| `row_cost_isinstance` | the row-side `cost` bound reverts to `isinstance` | 2 failed |
| `lost_check_removed` | the loss refusal deleted | 1 failed |
| `doc_stamps_unvalidated` | document stamps read from nowhere again | 1 failed |
| `validate_document_mutates` | the validator edits nested rows again | 1 failed |
| `backfill_restored` | round 9's laundering path put back | 1 failed |

**No injection was silent.** Every element of the round-10 delta is red-able. The suite's weakness is
not deadness: it is that the properties in §1c, §2a–2c and §6a–6c were never asserted, so there is
nothing to red — and that the one test §0.14.1c names as P4's enforcement cannot fire on the event it
names.

## Sibling table — *the recurring failure in this run is a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `_plain` applied to `Filter.op` and `OrderBy` direction (R9-B1/B2) | the remaining unbounded operands: `assemble(pass_number=)`, `discover(kind=)`, `discover(pass_number=)` | ❌ **NO** — §2a, §2b |
| `_is_exactly` extracted so the identity check reaches every site | the site that decides a type with `isinstance`: `rows_of` (`surface.py:40`) | ❌ **NO** — §1b |
| the identity check made unforgeable | **whether the checked objects are the objects used** — `pipeline` is iterated twice | ❌ **NO**, and it voids the check entirely — §1c |
| the row-side `cost` bounded (R9-B5) | the other three row-side reads: sort key, filter comparand, **`id`** | ❌ **NO** — §2c, and `AllowList` is defeated by one of them |
| the backfill removed and `load()` made strict | the other two row-readers in `__all__`: `declarations(doc)`, `SurfaceAssembler(doc)` | ❌ **NO** — §3c (pre-existing, disclosed) |
| `validate_document` stopped mutating (top level) | **nested** objects, and the refusal path | ✅ **YES** — measured at both |
| era-B/era-A asymmetry resolved by removing the repair | the hand-edited `"99.0.0"` laundering | ✅ **YES** — refused at all four doors |
| the P4 test proves its amendment took | the same test proving it can red on the event it names | ❌ **NO** — §5a |
| `SCOPE_PASS` added to the recorder and to `absorb` | the **other** dispatch over the same enum (`stream_service.py:6981`), and `absorb`'s own `else` | ❌ **NO** — §6a, §6b |
| `SCOPE_PASS` added to the recorder | a module-level minting function, as `record_surface_withheld` / `record_catalogue_unavailable` have | ❌ **NO** — the pass row is a literal dict at `stream_service.py:2353`; 2 of 3 scopes have a function |
| per-`(scope, stage, pass)` dedupe for scope rows | that it shares `_seen` with `(tool, stage, pass)` | ❌ **NO** — §6c (latent) |
| `build()`'s `previous` validated on the write side | `previous={"declarations": None}` | ❌ **NO** — §4 residual |

## What I would fix first

1. **`pipeline = list(pipeline)` before `validate_pipeline` (`surface.py:484`).** One line. Without
   it every property §0.14.1 buys by closing the kind set is available to any caller, and the
   *accidental* form — a generator — silently disables the whole pipeline. This is the round's
   most serious finding.
2. **Drive the carry-forward path in the P4 defect test (§5a).** As written it cannot red on the one
   event its docstring, and §0.14.1c's enforcement column, both promise it reds on — and it is the
   record CP-4 will be graded against. Three lines, using the refusal already in the file.
3. **`_plain(pass_number, int, "pass_number")` and the two `discover` operands (§2a, §2b).** A record
   that `canon` refuses is a record that cannot be content-addressed, which is what §0.14.2 exists
   to prevent; `discover(kind=)` is a full closure escape hatch in the module's second removal path.
4. **Bound `row["id"]` where `AllowList`/`DenyList` read it (§2c)**, or state in the docstring that
   the always-hot core trusts the row. A stage that admits a name it does not list, silently, is the
   one failure the conservation law structurally cannot see.
5. **Make `absorb`'s `else` refuse the row, not the turn (§6a)**, and give `stream_service.py:6981`
   its `catalogue` branch (§6b). The unhandled case's failure mode is a dead turn, and it is the
   failure mode this exact code was written to remove.
