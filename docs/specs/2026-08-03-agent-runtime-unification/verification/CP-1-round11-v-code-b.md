# CP-1 · round 11 · V-CODE · **Verifier B** — the bounds, the pipeline, and the P4 test

`git rev-parse HEAD` **at start:** `2c63496b4535eb37d0f98296933179984575b5a7`
`git rev-parse HEAD` **at finish:** `2c63496b4535eb37d0f98296933179984575b5a7`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.
Every injection came from **out-of-tree pytest plugins** in the session scratchpad that rebind
package callables at `pytest_configure` — i.e. **before** the test module's
`from app.agentruntime import build` runs — plus standalone scripts driving the public API against
`tempfile` paths and a faked `ambient`. Nothing was run against the live system.

**Baselines I measured myself:**

| | |
|---|---|
| `python -m pytest tests/test_cp1_membrane.py -q` | **109 passed**, 1 warning, 8.08s |
| `python -m pytest tests/test_cp0_instrument.py -q` | **92 passed**, 1 warning, 2.95s |
| both together | **201 passed** |
| `python scripts/agentruntime-membrane-gate.py` (from repo root) | **exit 0** — selftest OK, 8 modules, 2 single-sited types |

**A method note, because I made this round's own mistake on myself first.** My first set of
injections was hand-written replacement functions. Five of them reddened the suite — and every one
of those reds was an **artifact of my rewrite changing an error message or a parameter name**, not of
the defect I injected (`test_over_registration_is_refused_too` matches `"lost -1"`;
`test_the_EXPORTED_row_reader_refuses_a_malformed_document` matches `"malformed"`;
`test_CONSERVATION_…` enumerates by the parameter name `manifest_doc`). A sixth was an artifact of
exec'ing into a **copy** of the module globals, which froze `CONTRACT_VERSION` and reddened the P4
test for my reason rather than the injected one. So every number below comes from **source surgery**:
the real function's source is read with `inspect.getsource`, exactly one line is removed or replaced,
and the result is exec'd in the module's **live** `__dict__` — byte-identical in signature, message
and globals. **Two controls from rounds 1–10 (`kind_set_by_equality`, `lost_check_removed`) red the
suite under the same harness**, which is what makes a green result below evidence rather than a
broken rig. Each injection was then separately proven to *reproduce its defect* before I reported it
silent.

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *`pipeline = list(pipeline)` closes the TOCTOU for `assemble`* | **PASS for `assemble`, FAIL for the package.** Both R10 findings are closed and executed. But the fix has **no test** (removing the line leaves 109/109 green), and the **identical shape survives in four other places**, one of which — `validate_document` — lets a row violating *every* clause it enforces reach the consumer |
| 2 | *`rows_of` now validates row shape, so the row side is bounded* | **PARTIAL FAIL.** R10's headline (a forged `id` defeating `AllowList`) is genuinely closed at the assembler door. **`kind` is still unbounded and reaches two decisions**, the sort key still chooses the `TopK` victim, and three doors reach rows without `rows_of` at all. No test |
| 3 | *The P4 defect-assertion test now reds when §6.4's grandfathering lands* | **PASS — third time, and this time it is true**, measured by building the mechanism. **With two named residuals**: it reds for the wrong reason on a message reword or an exception-type change, and it stays **green** for two mechanisms equally faithful to §6.4 (gated on the amendment; landed in `generate()`) — both proven to be real, draining, loadable queues |
| 4 | *`previous={"declarations": None}` is refused* | **PASS for that literal shape, FAIL for the fact it stands for.** **Seven** other `previous` shapes are accepted with the loss guard silently disabled — including `previous={}` and a real document with the `declarations` key **missing**, which is the exact shape `rows_of` refuses **by name** four files away. No test |
| 5 | *`_seen`'s `#` prefix means the two namespaces cannot meet* | **FAIL.** `catalogue`/`pass` are closed — measured, both orders. But `#catalogue`, `#pass` and `#declaration` collide **identically**, and the fix's stated premise (*"a `#` prefix cannot appear in an id"*) is **not true of the string this set is keyed on**: `record_withheld` is fed live catalogue tool names, never contract ids. No test |
| 6 | *There is exactly one place that knows the scope enum, and `"*"` cannot mint a `tool` key* | **FAIL on the first half, PASS with a residual on the second.** There are **three** places in `instrument.py` alone, and **the second one crashes on the scope the first one just invented**: `withheld_json():683` raises **`KeyError: 'tool'`** on every unrecognised-scope row `absorb`'s `else` records — the P0, **fourth recurrence**, now on every terminal write |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Any object that still yields different values to `validate_pipeline` and to the loop; **or** any other place in the package where a caller-supplied iterable is consumed twice, or a value read once to check and again to use | Re-executed R10's `TwoFaced` and the bare generator; then enumerated every parameter annotated `Iterable`/`Sequence`, every `.get(k)`-then-`[k]` pair, and every `x in y` / `y[x]` pair in the package, and executed a probe per site |
| 2 | Any row field that reaches a narrowing, a `{tool, stage, reason, pass}` record, `Surface.names` or `canon.digest` without an exact-type bound; any public door that reaches rows without `rows_of` | Enumerated every row-side read in `surface.py` (`id`, `kind`, `cost`, `r[field]`, `row.get(self.field)`) and drove a forged value through each; then walked `__all__` for row-readers |
| 3 | The test staying **green** with §6.4's mechanism built and draining; **or** reddening on a change that is not the mechanism landing | Built the carry-forward myself, proved it produces `queue=['book_get']` and drains to `[]` and that `validate_document`/`load` accept the carried document, then injected it at `pytest_configure`; then built four variants — two that red without the mechanism, two that keep it green with the mechanism live |
| 4 | Any `previous` shape that is malformed and still accepted with the loss guard disabled | Enumerated 16 shapes across both `or` idioms (outer `previous or {}`, inner `or []`), the missing key, the wrong container types, and a `list` subclass lying about `__len__` |
| 5 | Any pair `(tool, stage, pass)` and `("#"+scope, stage, pass)` that are equal; any two genuinely different rows that dedupe to one | Executed both key namespaces in both arrival orders for `catalogue`/`pass`, for `#`-prefixed ids, and for the unknown-scope branch; then traced what string actually reaches `record_withheld` on live paths |
| 6 | A second consumer of `SCOPE_*` anywhere; any row shape `absorb` records that a later consumer cannot read; a `tool: "*"` reaching the column | Grepped every `SCOPE_` reference in both files, executed each dispatch against all three scopes plus a fourth and a missing one, and ran the `"*"` translation through the real `absorb` |

---

## 1 — the TOCTOU is closed at `assemble`, and the same shape survives four places

### 1a · both of R10's findings are **CLOSED** — executed

`surface.py:511`, `pipeline = list(pipeline)` before `validate_pipeline`.

| probe | R10 | now |
|---|---|---|
| `assemble(pipeline=TwoFaced(honest, rogue))` — a 4-line class holding a lambda | narrowed to `('t3',)`, law balanced, `validate_pipeline` silent | **iterated ONCE** (`n == 1`); the rogue never ran; `names == ('t0','t1','t2','t3')` |
| `assemble(pipeline=(s for s in [Filter(... keep only t0)]))` — the accidental form | pipeline silently no-op'd, `('t0','t1','t2','t3')` | **`('t0',)`** — the pipeline ran |

### 1b · 🔴 the fix has **no test**

Source surgery removing exactly `pipeline = list(pipeline)` and nothing else: **109 passed.** The line
R10 called *"this round's most serious finding"* and *"the thing I would fix first"* shipped
ungated. Proven live: under the injection, the generator pipeline again returns all four names.

### 1c · 🔴 `validate_document` iterates `declarations` TWICE, and it is `isinstance`-checked — `manifest.py:339` / `:342` / `:408`

```python
rows = doc.get("declarations")
if not isinstance(rows, list):            # not `_is_exactly`, unlike rows_of:42
for i, r in enumerate(rows):              # :342  iteration #1 — the contract + both stamps
for r in rows:                            # :408  iteration #2 — M5
```
Executed with a `list` subclass whose second `__iter__` yields one extra row:

| measured | value |
|---|---|
| iterations of the list | **2** |
| what iteration #1 validated | `['t0']` |
| what the **returned document** hands a consumer | `['t0', 'TYPED BY HAND!!']` |
| the smuggled row's clauses | `id`, `kind`, `owning_service`, `lifecycle`, `contract_version` (`"banana"`), `admitted_against` (`null`) — **all invalid** |
| `validate_document` | **ACCEPTED** |

This is `UntrustedRow`'s own sentence — *"a row typed in by hand reached the assembler having passed
no clause"* — reached **through the validator itself**, and it is the exact shape the round fixed one
file over. `rows_of` got `_is_exactly`; the function whose entire job is validation did not. The M1
drift gate calls `validate_document`, and it is exported in `__all__`.

**And the per-row reads disagree too.** `r.get("id", "")` is what the contract validates; `r["id"]`
is what the duplicate-id set is keyed on. Measured with a `dict` subclass (`isinstance` accepts one):
the contract validated `t0`, the dedupe set recorded `SOMETHING_ELSE`, and `members` stored on the
row (`['ghost']`, an unresolved reference) was never the value M5 checked.

### 1d · 🔴 `build`: `isinstance(_prev_rows, list)` is checked, `_prev_rows or []` is used — `manifest.py:190` / `:200`

A `list` subclass whose `__len__` returns `0` while `list.__iter__` yields two rows:

```
len(ll) = 0 ; list.__len__(ll) = 2
build([book_list], previous={"declarations": ll})  ->  ['book_list']   # ACCEPTED
```
`isinstance` says list, `or []` says empty — **the loss guard is disabled and `book_get` leaves
silently.** The check and the use consult different protocols. Same reachability class as the
`{"declarations": None}` residual this round *did* fix.

### 1e · 🔴 `generate`: `ambient.exists(target)` is checked, then `load()` reads the path **again** — `manifest.py:268` / `:307`

Executed with an `exists` that answers `True` then `False` (a real operator action — the code's own
comment calls deleting the manifest *"the ordinary reaction to a drift gate going red"*):

```
generate([book_list], path=...)   ->  ACCEPTED, and it WROTE
rows: ['book_list']        book_get: SILENTLY GONE
exists() calls on the same path: 2        bootstrap=: never passed
```
`load()` returned `_empty()`, so `previous.declarations == []`, so `origin` was empty, so the loss
guard had nothing to compare. **`bootstrap=` — the flag added specifically to stop a missing file
restamping origins — never fired, because the caller did not pass it and did not have to.**

### 1f · minor, recorded

`OrderBy.sort` checks `field not in r` and then uses `r[field]` (`surface.py:320`/`:326`) — a `dict`
subclass makes the check pass and the use raise a bare `KeyError`, not the module's `ValueError`.
Fail-loud, so it is a residual and not a bypass.

---

## 2 — `rows_of` bounds the `id`, and stops

R10's headline is genuinely closed. `SurfaceAssembler` over a row whose `id` is a `str` subclass with
`__eq__ → True` is now **REFUSED** at construction (`declarations[0].id is 'zz'; a declaration id
must be a non-empty plain string`), so `AllowList` can no longer be defeated through the row.

### 2a · 🔴 `kind` is unbounded and reaches **two** decisions

| door | probe | measured |
|---|---|---|
| `discover(kind="skill")` — the module's **second removal path** | a row whose `kind` is a `str` subclass with `__eq__ → True` | kept **both** rows (`['t0','t1']`) and registered **`[]`** |
| `Filter(field="kind", op="eq", value="tool")` | a row whose `kind` has `__eq__ → True` | `names == ('t0',)` — the row decided the filter |
| the same with `op="in"` | " | `('t0',)` |

The first is R10 §2c's `AllowList` shape reproduced one field over, in the function whose own
docstring says *"filtering is narrowing"*: **a declaration the query did not ask for went out with no
record**, and the conservation law structurally cannot see it because nothing was dropped.

### 2b · 🔴 the sort key still chooses the survivor

A row `rank` that is an `int` subclass with `__lt__ → False`: `OrderBy(("rank","asc")) + TopK(k=1)`
kept **`t1`** rather than `t0` (`rank=0`). Arbitrary logic decided which declaration reached the
model. `rows_of` bounds `id` and `_narrow` bounds `cost`; every other sortable column is open.

### 2c · the doors that do not go through `rows_of`

| door | in `__all__`? | validates rows? |
|---|---|---|
| `SurfaceAssembler`, `discover`, `declarations` | yes | **yes**, via `rows_of` |
| `validate_document(doc)` | yes | its own, `isinstance`-based, twice-iterated — see §1c |
| `build(previous=…)` | yes | `id` truthiness + `contract_version` syntax only |
| `OrderBy.sort(rows)`, `Filter/AllowList/DenyList.keep(row)` | yes | **no** — executed: `AllowList(names=("aa",)).keep({"id": SneakyId("zz")})` → `True`; `DenyList` → `False` |
| `Surface(names=…, …)` | yes | **no** — `Surface(names=(object(),), …)` constructs |

Also measured: `rows_of` accepts a row whose `kind` is a bare `object()`.

---

## 3 — the P4 defect-assertion test. **It reds. Here is exactly when, and exactly when it does not.**

`tests/test_cp1_membrane.py:480-481` — the whole round-11 delta to this file (+12 lines, 9 of them
comment) is the three lines R10's verdict prescribed, verbatim:

```python
with pytest.raises(UntrustedRow, match="IS NOT BUILT"):
    build([admit(_tool("book_list"))], previous=after)
```

### 3a · I built the mechanism, and **proved it is a real queue before running it**

§6.4's carry-forward, out of tree: a row present in `previous` and absent from `admitted` stays in the
runtime carrying the stamp it was last checked against; `contract_version` never moves;
`admitted_against` is the live value only for rows this build admitted.

```
gen 1 (1.0.0)   book_get ('1.0.0','1.0.0')  book_list ('1.0.0','1.0.0')   queue = []
breaking amendment to 2.0.0; book_get NOT re-admitted
gen 2 (2.0.0)   book_get ('1.0.0','1.0.0')  book_list ('1.0.0','2.0.0')   QUEUE = ['book_get']   ← non-empty, 2 rows, the row STAYED
gen 3           book_get re-admitted                                       QUEUE = []            ← drains
validate_document(gen 2): OK
```

### 3b · ✅ **the test REDS** — measured

Injected at `pytest_configure`: **2 failed, 107 passed.**

```
FAILED …::test_THE_QUEUE_IS_EMPTY_BY_CONSTRUCTION__P4_IS_NOT_SATISFIED_HERE   (line 480)
FAILED …::test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST
```
Failure: `Failed: DID NOT RAISE <class 'app.agentruntime.manifest.UntrustedRow'>` at **line 480** —
the new assertion, the right line, the right reason. **Round 9's and round 10's claim is finally
true.** This is the third attempt and the first that survives the measurement.

### 3c · 🔴 it reds for the **wrong** reason on two changes that are not the mechanism landing

| injection | is the mechanism present? | result |
|---|---|---|
| the refusal's **wording** changed to *"…IS NOT IMPLEMENTED"*, loss guard otherwise intact | **no** | **2 failed** — including the P4 test |
| the refusal raises a **different exception type** with the words *"IS NOT BUILT"* intact | **no** | **2 failed** — including the P4 test |

The assertion is coupled to a message substring and an exception class. A wording change to
`manifest.py:224-229` reds the test CP-4 will be graded against while §6.4 is exactly as unbuilt as
before.

### 3d · 🔴 it stays **GREEN** for two mechanisms that are equally faithful to §6.4

Both proven to be real, draining, `load()`-able queues before I ran them.

| mechanism | why it is faithful | suite |
|---|---|---|
| **grandfather only on a breaking amendment** — carry a missing row forward iff its `admitted_against` differs from the live constant; a row missing under an *unchanged* contract is a caller that forgot one, and still refuses | §6.4's table is literally *"a **breaking** amendment → prior declarations enter a re-admission queue"*, and *"a backward-compatible amendment → prior admissions stand"*. The test's `after` was built at 2.0.0 and `CONTRACT_VERSION` is still 2.0.0, so **no amendment has occurred at the assertion** | **109 passed** 🔴 |
| **the carry-forward lands in `generate()`** — the only thing that will ever write the real manifest — leaving `build()`'s refusal as a low-level invariant | §6.4.1 argues the grandfathered row cannot be re-checked by `load()`, so the decision belongs where the document is assembled, not in the pure row builder | **109 passed** 🔴 |

Measured for the second: `generate()` on the same path across a real amendment wrote a **2-row file**
with `queue == ['book_get']` on disk, `load()` accepted it, and generation 3 drained it to `[]` — the
full §6.4 lifecycle, live, through the real writer, **with the whole suite green.**

**Why.** The new assertion does not observe the queue. It asserts *the refusal in `build()`* — which
is the same assertion `test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST` already makes, on the
same call shape, with the same `match=`. That is why the two tests red together and why they red
together on a wording change. The test therefore detects **"`build()`'s loss refusal was removed"**,
which is a proxy for the mechanism landing and not the mechanism landing. Its docstring's claim —
*"it turns red the day the grandfathering mechanism lands"* — is true of the mechanism as R10's
verdict framed it, and false of the two above.

**The closure, and it is small:** assert the *queue*, not the refusal — drive one amendment, take the
document `build` produces (or refuses), and assert `[r for r in doc["declarations"] if
r["admitted_against"] != doc["contract_version"]] == []` **on a carry-forward call**, so any
mechanism that puts a row in the queue by any route reds it, and no wording change does.

---

## 4 — `previous`: one shape closed, seven open

`build([book_list], previous=<shape>)` where `book_get` is in `<shape>` and not in the build. If the
loss guard is live it refuses.

| shape | result |
|---|---|
| `{"declarations": None}` ← **R10's named residual** | **REFUSED** ✅ |
| `{"declarations": (…,)}` (tuple) / `{"declarations": {…}}` (dict) | REFUSED ✅ |
| a real 2-row document (control) | REFUSED ✅ |
| `previous={}` — **the key is MISSING** | **ACCEPTED, guard silent** 🔴 |
| `{"manifest_version": 1, "contract_version": "1.0.0"}` — a real document minus `declarations` | **ACCEPTED, guard silent** 🔴 |
| `previous=[]` — the **rows** passed instead of the document | **ACCEPTED, guard silent** 🔴 |
| `previous=()` / `0` / `False` / `""` | **ACCEPTED, guard silent** 🔴 |
| `previous=[{…},{…}]` — the same mistake, non-empty | `AttributeError: 'list' object has no attribute 'get'` 🔴 |
| `previous="banana"` | `AttributeError` 🔴 |
| `{"declarations": <list subclass lying about __len__>}` | **ACCEPTED, guard silent** 🔴 (§1d) |

Two things worth stating plainly:

1. **The fix closed the inner `or []` and left the outer `or {}`.** Every silent row above reaches the
   same state through `(previous or {})` instead of through `.get(…, []) or []`. One operator over,
   same line, same fact.
2. **`previous={}` is the shape `rows_of` refuses by name.** Its docstring: *"A missing key is a
   **broken document**, not an empty catalog… serving it as empty erases the difference between
   'nothing is admitted' and 'we could not read the catalog'."* `validate_document:339` refuses it
   too. `build` serves it as empty and disables the only guard standing in for the missing §6.4
   mechanism.
3. Passing the rows instead of the document — a realistic slip — is a **silent guard-disable** when
   the list is empty and an **`AttributeError`** when it is not. Which of the two you get depends on
   data, not on the mistake.

---

## 5 — `_seen`: the two names it was told about are closed; the namespace still meets

### 5a · ✅ the R10 §6c collision is closed for `catalogue` and `pass`

Both orders, both scopes, measured — both records survive:

```
declaration id 'catalogue' first -> [('declaration','catalogue'), ('catalogue', None)]
scope row      'catalogue' first -> [('catalogue', None), ('declaration','catalogue')]
declaration id 'pass'      first -> [('declaration','pass'),      ('pass', None)]
scope row      'pass'      first -> [('pass', None),      ('declaration','pass')]
```

### 5b · 🔴 and it meets again one character over

The key is `(tool, stage, pass)` vs `("#"+scope, stage, pass)`. They are equal iff
`tool == "#"+scope`. Executed:

| arrival order | recorded |
|---|---|
| tool `#catalogue`, then the `catalogue` scope row | `[('declaration','#catalogue')]` — **the scope row is gone** |
| the `catalogue` scope row, then tool `#catalogue` | `[('catalogue', None)]` — **the declaration row is gone** |
| same for `#pass` and `#declaration` | identical |

**Whichever arrives first silently suppresses the other** — the R10 §6c defect, unchanged, at
`#`-prefixed names.

**The premise of the fix is false of the string the set is keyed on.** The comment at
`instrument.py:544-548` says *"a `#` prefix cannot appear in an id, so the two namespaces can no
longer meet."* That is true of `contract._ID` (`^[a-z][a-z0-9_]*$`). But `record_withheld(tool, …)`
is **never fed a contract id**. Its live callers pass live catalogue tool names —
`stream_service.py:1401` and `:1413` (`name` from the turn's catalog index), `tool_surface.py:266`
and `:427`, `tool_discovery.py:499` — and `absorb` passes `row["tool"]` verbatim from a sink those
callers write. None of those strings pass through `_ID`. The prefix narrows the collision from two
ordinary English words to one `#`-prefixed provider-supplied name; it does not remove it, and the
sentence claiming it does is the load-bearing part.

### 5c · the unknown-scope branch shares the namespace with itself

Three genuinely different malformed sink rows at the same stage and pass — `scope: "turn"`,
`scope: None`, and no `scope` key — produce **two** records: the last two both normalise to
`"unknown"` and the second is deduped away. The branch written so that *"an unrecognised row is
recorded rather than dropped"* drops one.

---

## 6 — the scope enum. **Not one place. Three — and the second crashes on what the first invents.**

### 6a · 🔴 `KeyError: 'tool'`, the **fourth** recurrence, on every terminal write — `instrument.py:683`

`absorb`'s `else` (`instrument.py:602-606`) was changed to *record* an unrecognised scope rather than
crash. The row it records has a `scope` that is neither `catalogue` nor `pass`, and **no `tool` key**.
`withheld_json()` — the function that *calls* `absorb`, on every terminal path — then filters:

```python
if w.get("scope") in (SCOPE_CATALOGUE, SCOPE_PASS)
or w["tool"] not in by_pass.get(w.get("pass"), set())     # :683
```

Executed three ways, all on a recorder with one recorded pass:

| path | result |
|---|---|
| `absorb([{"scope": "turn", …}])` then `withheld_json()` | **`KeyError: 'tool'`** |
| `absorb([{…no scope key…}])` then `withheld_json()` | **`KeyError: 'tool'`** |
| `bind_sink([{"scope": "turn", …}])` then `withheld_json()` — **the real production shape** | **`KeyError: 'tool'`** |
| control — `catalogue`, `pass`, `declaration` | all three survive `withheld_json()` |

`absorb`'s own comment says: *"That is the third time this shape has landed here, so the branch stops
trusting the shape."* It is the fourth. The crash moved one function down the same call, and the
blast radius is exactly what that comment warns of: `withheld_json()` runs on every terminal path, so
**one malformed sink row no longer loses a record — it kills the whole terminal write.** The fix
records the row and then hands it to a consumer that cannot read it. It is R10 §6a repaired at the
producer and re-created at the consumer, which is this run's recurring shape stated in the prompt.

### 6b · the places that know the enum

| site | scopes handled |
|---|---|
| `instrument.absorb:584-606` | all three + an else | 
| `instrument.withheld_json:683` | **`catalogue`, `pass`** — everything else is assumed to carry `tool` 🔴 |
| `instrument.catalogue_outage_registered:354` | `catalogue` only (correct for its question) |
| `stream_service.py:2354` | mints a `SCOPE_PASS` literal dict; still no module-level minting function, unlike the other two scopes |
| `stream_service.py:6995` | the `"*"` translation |

### 6c · the legacy `"*"` translation — **PASS**, with a residual on the adjacent line

Executed the real list comprehension and drained it through the real `absorb`:

```
translated row        : {'tool': '*', 'stage': 'pass_offered_no_tools', 'reason': 'none', 'scope': 'pass'}
what reaches the column: [{'segment': …, 'scope': 'pass', 'stage': 'pass_offered_no_tools', 'reason': 'none', 'pass': 1}, …]
any row with tool='*'  : False        ✅
```
The dict spread does carry `tool: "*"` forward, but `absorb` routes on `scope` and
`record_pass_withheld` never writes a `tool`. **The sentinel cannot reach the column on this path.**

🔴 **But the other `absorb` call, eleven lines above it, has no translation.**
`_advertised.absorb(_surface_sink)` at `stream_service.py:6987` takes the sink verbatim:

```
absorb([{'tool': '*', 'stage': 'pass_offered_no_tools', 'reason': 'none'}])
 -> [{'segment': …, 'scope': 'declaration', 'tool': '*', …}]     any row with tool='*': True
```
`tool: '*'` in the column — the sentinel §0.14.3 rejects **by name**. Latent (it needs a catalogue
entry literally named `*`, and the sink's writers pass live tool names), but it is the same
one-member-of-a-set shape: the translation was consolidated onto one of the two adjacent drains.

---

## Bypass table

| property asserted | path that defeats it | evidence |
|---|---|---|
| what `validate_pipeline` checks is what `assemble` runs | **none found** — `TwoFaced` iterated once; the generator pipeline ran | `surface.py:511` — executed |
| a document `validate_document` returns has been validated | **`declarations` is `isinstance`-checked and iterated twice** — a `list` subclass returned one row to the validator and two to the consumer, the second violating every clause | `manifest.py:339,342,408` — executed |
| the row a validator checked is the row it registered | `r.get("id")` validates, `r["id"]` keys the duplicate set; `members` read twice | `manifest.py:346-406` — executed |
| a declaration cannot silently leave the manifest | **`previous={}`, a doc without `declarations`, `[]`, `()`, `0`, `False`, `""`, and a `__len__`-lying list** all disable the guard | `manifest.py:189-200` — executed, 7 shapes |
| " | **`generate()`'s `exists`→`load` race** — the file vanishing between two calls drops a row **and writes**, with `bootstrap=` never passed | `manifest.py:268,307` — executed |
| the row side is bounded | **`kind`** — a forged `__eq__` made `discover(kind=…)` keep an unrequested declaration **with no record**, and matched a `Filter` it should not | `surface.py:658`, `:198-203` — executed |
| " | the **sort key** still chooses the `TopK` survivor | `surface.py:326` — executed |
| " | R10's `AllowList`/`row["id"]` defeat — **CLOSED at the assembler**; still open on `AllowList.keep`/`DenyList.keep` called directly | `surface.py:57` — executed |
| the P4 test reds when the mechanism lands | **two faithful mechanisms leave it green** (gated on the amendment; landed in `generate()`), both proven draining | §3d — executed, 109 passed each |
| the P4 test cannot red for the wrong reason | **a message reword and an exception-type change both red it** with the mechanism absent | §3c — executed |
| the `_seen` namespaces cannot meet | **`#catalogue` / `#pass` / `#declaration`** collide identically; the premise is false of the string the set is keyed on | `instrument.py:468,549` — executed |
| there is one place that knows the scope enum | **`withheld_json:683` is a second one, and it raises `KeyError: 'tool'`** on the row `absorb:602` just recorded — on every terminal write | executed 3 ways |
| `"*"` cannot mint a `tool` key | **none found** on the `_adv_ev` path ✅; the **sink** drain 11 lines up has no translation and does mint one | `stream_service.py:6987` vs `:6995` — executed |

## Red-ability table — baseline **109 passed** (membrane) / **201 passed** (both suites), measured by me

All injections by source surgery into live module globals. **Every one was separately proven to
reproduce its defect** before being reported silent.

| injection | what it models | proven live by | suite |
|---|---|---|---|
| `pipeline_not_materialised` | **this round's headline fix** deleted | generator pipeline → all 4 names again | **109 passed** 🔴 |
| `pass_number_unbounded` | `_plain(pass_number, int, …)` deleted | `pass_number=1.5` accepted; `canon.digest` → `NotCanonicalisable` | **109 passed** 🔴 |
| `rows_of_no_row_validation` | the row-shape check deleted | `AllowList(names=('aa',))` → `('aa','zz')`, **defeated** | **109 passed** 🔴 |
| `rows_of_isinstance` | `_is_exactly(rows, list)` → `isinstance` | a `list` subclass accepted | **109 passed** 🔴 |
| `discover_kind_unbounded` | `_plain(kind, str, …)` deleted | forged `__eq__` kept all 4, recorded `[]` | **109 passed** 🔴 |
| `discover_pass_number_unbounded` | `_plain(pass_number, …)` deleted | record `pass: 2.5`; `canon.digest` raises | **109 passed** 🔴 |
| `build_previous_declarations_unchecked` | R10 §4's residual re-opened | `previous={"declarations": None}` accepted | **109 passed** 🔴 |
| `seen_no_hash_prefix` | the `#` prefix deleted | id `catalogue` + scope row → **one** record | **201 passed** 🔴 |
| `absorb_else_reads_tool` | the P0 restored — `row["tool"]` unconditional | `absorb({"scope":"turn"})` → `KeyError: 'tool'` | **201 passed** 🔴 |
| **`grandfathering_landed`** | **§6.4's mechanism LANDS (R10's framing)** | queue `['book_get']` → `[]`, `validate_document` OK | **2 failed** ✅ — incl. the P4 test, at line 480 |
| `p4_refusal_reworded` | the refusal's wording changes, mechanism absent | — | **2 failed** 🔴 wrong reason |
| `p4_refusal_wrong_type` | the refusal's exception class changes, mechanism absent | — | **2 failed** 🔴 wrong reason |
| `grandfather_on_amendment` | **the mechanism lands, gated on a breaking amendment** | queue `['book_get']` → `[]`, `validate_document` OK | **109 passed** 🔴 |
| `grandfather_in_generate` | **the mechanism lands in the only real writer** | 2-row file on disk, queue on disk → drains, `load()` OK | **109 passed** 🔴 |
| `CONTROL_kind_set_by_equality` | rounds 1–10 gate | metaclass forgery accepted | **1 failed** ✅ |
| `CONTROL_lost_check_removed` | rounds 1–10 gate | `book_get` dropped silently | **2 failed** ✅ |

**Nine of nine elements of round 11's delta in my scope are SILENT.** The two controls prove the
harness reds. The round added exactly **three** new tests (`git diff` against
`a43c24f`), all three in `test_cp0_instrument.py` and all three in Verifier A's scope; the entire
change to `test_cp1_membrane.py` is +12 lines, nine of them comment, and the three code lines are
the P4 assertion. **Every fix written for my six questions except the P4 assertion shipped ungated** —
in a round whose stated premise was *"grade the guards, not the mechanism."*

## Guard table — *can it fail? does it fail for the reason it names?*

| guard added this round | can it fail? | does it fail for the reason it names? |
|---|---|---|
| `pipeline = list(pipeline)` (`surface.py:511`) | **NO** — no test exists | n/a |
| `rows_of` row-shape validation (`surface.py:54-62`) | **NO** | n/a |
| `_is_exactly(rows, list)` (`surface.py:42`) | **NO** | n/a |
| `_plain(pass_number, …)` in `assemble` (`:498`) | **NO** | n/a |
| `_plain(kind, …)` / `_plain(pass_number, …)` in `discover` (`:642`, `:649`) | **NO** | n/a |
| `previous.declarations is not a list` refusal (`manifest.py:190-199`) | **NO** | n/a |
| `#` prefix on scoped `_seen` keys (`instrument.py:549`) | **NO** | n/a |
| `absorb`'s `else` records rather than crashes (`instrument.py:602-606`) | **NO** | n/a — **and the row it records crashes `withheld_json`** |
| the `_legacy`→`absorb` re-route (`stream_service.py:6994-6998`) | **NO** (no unit test reaches it) | n/a |
| **the P4 carry-forward assertion (`test_cp1_membrane.py:480`)** | **YES** — measured RED on the built mechanism, at the right line | **PARTLY.** It reds on a message reword and on an exception-type change with the mechanism absent, and stays green for two mechanisms that are live and draining. It detects *"the loss refusal was removed"*, which is a proxy for the event it names |

## Sibling table — *the recurring failure in this run is a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `pipeline = list(pipeline)` — check-what-you-run at `assemble` | `validate_document`'s twice-iterated, `isinstance`-checked `declarations` | ❌ **NO** — §1c, and it admits a row that passed no clause |
| " | `build`'s `_prev_rows or []` after an `isinstance` check | ❌ **NO** — §1d |
| " | `generate`'s `exists`→`load` re-read | ❌ **NO** — §1e |
| `rows_of` bounds `row["id"]` (R10 §2c) | the other row fields that reach a decision: `kind`, the sort key | ❌ **NO** — §2a, §2b |
| `_is_exactly(rows, list)` in `rows_of` | the same decision in `validate_document:339` | ❌ **NO** — §1c |
| `_plain(pass_number)` / `_plain(kind)` on the two named doors | — | ✅ **YES** — R10 §2a/§2b closed, all four operands executed |
| `previous={"declarations": None}` refused | the **outer** `or {}` — `{}`, a doc without the key, `[]`, `()`, `0`, `False`, `""` | ❌ **NO** — §4, seven shapes |
| the P4 test driven onto the carry-forward path | the same test surviving a mechanism that lands anywhere but `build()`'s refusal | ❌ **NO** — §3d |
| `#` prefix so the namespaces cannot meet | ids that **start with `#`**, and whether `record_withheld` is even fed contract ids | ❌ **NO** — §5b |
| `absorb`'s `else` stops reading `row["tool"]` | **`withheld_json:683`, which reads `w["tool"]` on the row `absorb` just wrote** | ❌ **NO** — §6a, and it is the same crash |
| the `"*"` translation routed through one dispatch | the **other** `absorb` call on the adjacent line, which has no translation | ❌ **NO** — §6c |
| every fix above | **a test** | ❌ **NO** — 9 of 9 silent |

## What I would fix first

1. **`withheld_json:683` (§6a).** `KeyError: 'tool'` on every terminal write, from a row this round's
   own fix creates. It is a dead turn, it is the fourth recurrence, and the two halves are eleven
   lines apart in one file. Make the filter `w.get("tool")`-safe and keep unrecognised rows, the same
   way `catalogue` and `pass` are kept.
2. **Give this round's nine fixes a test each (red-ability table).** Every one is a one- or two-line
   assertion and I have executed the probe for each; the fixes are real and *entirely* unguarded, and
   this repository's own history says an unguarded fix is reverted.
3. **Assert the queue, not the refusal, in the P4 test (§3d).** As written it detects the removal of
   `build()`'s loss guard. Two faithful §6.4 mechanisms — one of them landing in the only function
   that will ever write the real manifest — leave it green, and it is the record CP-4 is graded
   against.
4. **`validate_document`: `_is_exactly` and one materialisation (§1c).** It is `rows_of`'s fix, in the
   function whose job is validation, on the path the M1 drift gate uses. A row violating every clause
   it enforces currently reaches the consumer.
5. **Bound `kind` in `rows_of` (§2a), and close the outer `or {}` in `build` (§4).** Both are the
   exact sibling of a fix that shipped this round, one field and one operator away.
