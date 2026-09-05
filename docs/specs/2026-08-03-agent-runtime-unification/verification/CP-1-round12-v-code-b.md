# CP-1 · round 12 · V-CODE · **Verifier B** — the membrane's bounds and the manifest

`git rev-parse HEAD` **at start:** `9c8df7800af7a297ea8fe758ded20714f70ad611`
`git rev-parse HEAD` **at finish:** `9c8df7800af7a297ea8fe758ded20714f70ad611`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.
`git status --porcelain` was clean at start and at finish.

**Method.** Every injection is **source surgery**: the real function's source is read with
`inspect.getsource`, exactly one anchor is replaced, and the result is `exec`'d in the module's
**live** `__dict__` — identical signature, messages and globals except for the injected line. The new
object is then rebound at **every** binding (`app.agentruntime.manifest`, the package re-export
`app.agentruntime`, and any other module holding the name), from an out-of-tree pytest plugin at
`pytest_configure` — i.e. **before** the test module's `from app.agentruntime import build` runs.

**Three self-checks on the harness, because R11's builder measured an inert probe:**

1. the injected function must differ from the original in **both** `co_code` and `co_consts` (a
   message-only edit changes only the latter — my first `G4` run aborted with `INJECTION IS A NO-OP`
   because I had only compared `co_code`);
2. `app.agentruntime.<name> is <injected>` is asserted at configure time, and the run **aborts** if
   it is not;
3. a `pytest_collection_finish` hook prints whether **the test module's own binding** is the injected
   object. Every row below was run with `test module tests.test_cp1_membrane.<name>
   is-injected=True` printed. This is the check that was missing in R11.

**Baselines I measured myself, twice, at start and at finish:**

| | |
|---|---|
| `python -m pytest tests/test_cp1_membrane.py -q` | **109 passed**, 1 warning, ~8s |
| `python scripts/agentruntime-membrane-gate.py` (repo root) | **exit 0** — selftest OK, 8 modules, 2 single-sited types |

**Two controls prove the harness reds** (`CONTROL_lost_check_removed` → 2 failed;
`CONTROL_origin_ignored` → 2 failed). Every injection reported *silent* below was **separately proven
to reproduce its defect** in a standalone probe before I reported it.

**Scope.** R11's delta. In `app/agentruntime/` that delta is **`manifest.py` only** — `git show
b6ca48859 -- services/chat-service/app/agentruntime/` touches no other file — and in
`tests/test_cp1_membrane.py` it is **one test** (the P4 assertion rewrite).

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *Three TOCTOUs were closed in `manifest.py`* | **PASS on the three, FAIL on the class — the fourth is in the function that was just fixed.** `validate_document` validates a **materialised copy** and `return doc` hands back the **original container**. A row's own `.get()` — user code the validator calls inside its own loop — appends a hand-typed row to that original. `validate_document` **ACCEPTS**, and `rows_of`/`declarations()` hand the consumer **both** rows. **No container subclass is required.** Two more: `build`'s **outer** `previous or {}` (R11 §4, unchanged, 8 shapes), and both functions' per-row `r.get("id")` / `r["id"]` split |
| 2 | *`rows_of` validates row shape* | **PARTIAL FAIL, unchanged from R11.** `kind` still reaches two decisions unbounded — executed. The door that does not go through `rows_of` and matters most is **`validate_document`**: it is `__all__`, it is what the M1 drift gate calls, and per §1 it returns a document it did not validate |
| 3 | *The P4 test now performs a partial re-admission and reds when §6.4 lands* | **PASS, and it is a real improvement** — measured RED on **two** mechanisms, including the "gated on a breaking amendment" one that was **green** in R11. **Two residuals survive:** it is still **GREEN** for a mechanism landing in `generate()` (proven live: a 2-row file on disk, queue `['book_get']`, drains to `[]`, `load()` accepts), and it still **REDS for the wrong reason** on an exception-type change with the mechanism absent |
| 4 | *Every fix in `app/agentruntime/` this round has a test that reds* | **FAIL — 5 of 5 silent, plus 2 combinations. 109 passed on every one.** The commit message says *"every fix in this round has a test proven red before moving on"*. For this package that is **not true**: the delta adds **zero** tests to `test_cp1_membrane.py` — its only change is the P4 rewrite. Two of the five fixes are additionally **unobservable in principle** |
| 5 | *`generate`'s `exists`→`load` re-check* | **PASS on reachability, FAIL on the reason it names.** It fires on `rm`/deploy-delete (executed). It does **not** fire on *"a concurrent regeneration"* — the **first** cause its own comment lists — because the file is back by the time the third `exists()` runs: measured, row silently gone, **and it wrote**, `bootstrap=` never passed |
| 6 | *The membrane gate: selftest coverage and `SINGLE_SITED`* | **PASS on `SINGLE_SITED` (still 1 site each — measured), PARTIAL on the selftest.** `_selftest` calls **three** of the gate's **five** checks. `_manifest_drift` and the `SINGLE_SITED` count have **no probe** — I drove both by hand and both red, so they are unwatched rather than broken |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Any value in `manifest.py`, `surface.py`, `contract.py`, `admission.py`, `canon.py` or `ambient` read once to **check** and again to **use**, where the two reads can disagree — by container protocol, by `dict`/`list` subclass, by mutation from user code the checker itself calls, or by a second filesystem probe | Enumerated every `.get(k)`-then-`[k]` pair, every `x or y` after an `isinstance`/`type` check, every value iterated twice, and every `return` of a container the function validated a copy of; drove a probe per site |
| 2 | Any row field reaching a narrowing, a `Surface`, or `canon.digest` without an exact-type bound; any exported door reaching rows without `rows_of` | Re-executed R11's `kind`/sort-key probes against the frozen artifact; walked `__all__` for row readers |
| 3 | The test staying **green** with a faithful §6.4 mechanism built and draining; or reddening on a change that is not the mechanism landing | Built **three** mechanisms (unconditional carry-forward in `build`; carry-forward gated on a breaking amendment; carry-forward in `generate`), proved the third produces a real, draining, `load()`-able queue on disk, and injected each at every binding; then injected a reword and an exception-type change with the mechanism **absent** |
| 4 | Any element of the delta whose removal leaves the suite green — **after** the removal is proven to reproduce a defect | One injection per changed line plus the two combinations that restore R11 §1c/§1d, each proven live in a standalone probe first |
| 5 | The added check being unreachable, or firing for a cause other than the ones it names, or missing one it does name | Drove `ambient.exists` through three scripted sequences (True→False; True→False→True; steady) against a real temp file |
| 6 | A gate check with no selftest probe; `SINGLE_SITED` being stale | Parsed `_selftest`'s call graph; counted construction sites; drove `_manifest_drift` and the single-sited count by hand against a **scratch copy** of the package and a scratch manifest |

---

## 1 — three TOCTOUs closed, and the fourth is in the function that was just fixed

### 1a · the three named ones are genuinely closed — executed

| R11 finding | probe now | result |
|---|---|---|
| §1d `build`: `isinstance` + `_prev_rows or []` | `previous={"declarations": <list subclass, `__len__`→0, 2 real rows>}` | **REFUSED** ✅ (`manifest.py:193`) |
| §1c `validate_document`: `isinstance` + twice-iterated | a `list` subclass yielding an extra row on its 2nd `__iter__` | **REFUSED** ✅ (`manifest.py:360`) |
| §1e `generate`: `exists`→`load` | `exists` answering True then False | **REFUSED** ✅ (`manifest.py:280`) — see §5 for the half it misses |

### 1b · 🔴 **THE FOURTH.** `validate_document` validates a copy and returns the original — `manifest.py:362` vs `:434`

```python
rows = list(rows)          # :362  the copy that gets validated
...
return doc                 # :434  the ORIGINAL container is what the caller gets
```

`rows_of` gets this right one file over — `surface.py:63` is `return list(rows)`, the validated value.
`validate_document` returns `doc`, whose `declarations` is still the object the caller handed in.

Executed, **with a plain `list` and plain `dict`s in the result** — the only subclass is the *vehicle*,
which deletes itself:

```python
class Appender(dict):
    def get(self, k, default=None):
        if k == "kind" and smuggled not in original:
            original.append(smuggled)     # a plain list, mutated from inside loop 1
            original[0] = dict(self)      # the vehicle removes itself
        return dict.get(self, k, default)
```

| measured | value |
|---|---|
| `validate_document(doc)` | **ACCEPTED** |
| rows it validated | `['book_list']` |
| rows the **returned document** carries | `['book_list', 'TYPED BY HAND!!']` |
| types in the returned document | `['dict', 'dict']` — nothing exotic survives |
| `rows_of(returned doc)` | `['book_list', 'TYPED BY HAND!!']` |
| **`declarations(returned doc)`** — the only row reader in `__all__` | `['book_list', 'TYPED BY HAND!!']` |
| the smuggled row's clauses | `kind: "nonsense"`, `owning_service: "!!"`, `lifecycle: "??"`, `contract_version: "banana"`, `admitted_against: null` — **all invalid** |

This is `UntrustedRow`'s own sentence — *"a row typed in by hand reached the assembler having passed
no clause"* — reached **through the validator**, on the code that was written this round to stop
exactly that. The fix moved the iteration behind a copy and left the **return**; `r.get(...)` is user
code, and it runs *between* the copy and the return. The one-line closure is
`return {**doc, "declarations": rows}`.

A second, simpler vehicle reaches the same state: a `dict` **subclass** as the document, whose
`get("declarations")` answers differently on the second call — `isinstance(doc, dict)` at
`manifest.py:334` accepts one, while `type(rows) is not list` at `:360` refuses the subclass one line
down. **The round applied `type(...) is` to the inner container and `isinstance` to the outer one.**
Measured: `validate_document` ACCEPTED, `declarations(out)` → `['book_list', 'TYPED BY HAND!!']`.

### 1c · 🔴 the **outer** `previous or {}` — `manifest.py:192`. R11 §4, unchanged

The comment added this round at `:189` says the materialisation is *"for the same reason … `_prev_rows
or []` over a container that lies about `__len__`"*. One line up, `(previous or {})` is the same
idiom over the **document**, and it was not touched. R11's *"what I would fix first"* item 5 named it.

`build([book_list], previous=<shape>)` where `book_get` is in `<shape>` and not in the build:

| shape | result |
|---|---|
| `FalsyDict(<a real 2-row document>)` — a `dict` subclass whose `__bool__` is `False` | **ACCEPTED, guard silent** 🔴 |
| `{}` — the key missing | **ACCEPTED, guard silent** 🔴 |
| a real document minus `declarations` | **ACCEPTED, guard silent** 🔴 |
| `[]` — the rows passed instead of the document | **ACCEPTED, guard silent** 🔴 |
| `()` / `0` / `False` / `""` | **ACCEPTED, guard silent** 🔴 |
| control: the real 2-row document | **REFUSED** ✅ |

The `FalsyDict` row is the point: it is a **container that lies**, which is the exact class the
round's own comment says it fixed, one operator away from the line it fixed.

### 1d · 🔴 the per-row reads still disagree — `build` and `validate_document`

`isinstance(r, dict)` (`manifest.py:205`, `:365`) accepts a subclass, and both functions read the
same field twice through two different protocols.

| site | check | use | measured |
|---|---|---|---|
| `build:205` / `:214` | `r.get("id")` is the presence test | `origin[r["id"]]` is the key | a row whose `.get("id")`→`book_get` and `["id"]`→`book_list`: **ACCEPTED**; `book_get` **SILENTLY GONE** and `book_list`'s origin **forged to `0.0.1`** from the crafted row |
| `validate_document:369` / `:426`,`:428` | `r.get("id","")` is contract-checked | `r["id"]` keys the duplicate set | **ACCEPTED**; contract validated `'book_list'`, the dedupe set was keyed on `'SOMETHING_ELSE'` |
| `validate_document:387` / `:431` | `r.get("members")` for the contract | `r.get("members", ())` for M5 | reads disagree; **fail-loud** (`UnresolvedReference`) — residual, not a bypass |

### 1e · what I attacked and could **not** break (recorded, because a falsifier that finds nothing is evidence)

| attack | result |
|---|---|
| a `Declaration` **subclass** with an alternating `id` property (`check_contract` reads it, `_row` re-reads it) | **BLOCKED** — `frozen=True, slots=True` makes the property shadow unsettable: `AttributeError: property 'id' has no setter` |
| a `tuple` subclass as `members` with a two-faced `__iter__` (read **3×** across `admit`→`_row`→M5) | **FAIL-LOUD** — `_row` stores `list(d.members)` and M5 checks the **stored** copy. This is the correct pattern, and it is the one `validate_document` lacks |
| `ambient.exists`→`read_text` in `load()` | fail-loud (`FileNotFoundError`) — residual |

---

## 2 — `rows_of` bounds the `id`, and stops. R11 §2 is unchanged

Not a delta item, re-measured because Q2 asks:

| door | probe | measured |
|---|---|---|
| `Filter(field="kind", op="eq", value="tool")` | a row whose `kind` is a `str` subclass with `__eq__ → True` | kept **both** rows — the row decided the filter (`surface.py:198-200`) |
| `discover(kind="tool")` — the module's second removal path | same row | kept **`t0`**, a declaration whose `kind` is `'skill'`; the drop it caused was **registered against `t1`**, the row that genuinely did not match (`surface.py:658`, `:663`) |
| `rows_of` | the same row | **ACCEPTED** — only `id` and the row type are bounded (`surface.py:54-62`) |
| `AllowList.keep({"id": SneakyId("zz")})` / `DenyList.keep(...)` | forged `__eq__` | `True` / `False` — defeated, called directly |

**The door that does not go through `rows_of`, and it is the one that matters:** `validate_document`.
It is in `__all__`, it is what `_manifest_drift` calls, and by §1b it returns a document it did not
validate. The smuggled row lands precisely because `rows_of` bounds `id` and nothing else — my
smuggled row has a plain-`str` id and a `kind` of `"nonsense"`, and `rows_of` passes it through.

---

## 3 — the P4 test. It is better than R11's, and two residuals survive

`tests/test_cp1_membrane.py:493-503`. The assertion is now about the **outcome**: amend to `3.0.0`,
perform a **partial** re-admission, and if `build` returns rather than refusing, raise if the queue
is non-empty.

### 3a · ✅ it REDS on the mechanism, at the right line, for the right reason — measured twice

| mechanism, built and injected at **every** binding | suite | where |
|---|---|---|
| **`G1`** unconditional carry-forward in `build()` | **1 failed** ✅ | `test_cp1_membrane.py:503` — `AssertionError: §6.4's re-admission queue is NON-EMPTY (['book_get'])` |
| **`G1b`** carry-forward **gated on a breaking amendment** — §6.4's literal wording, and **GREEN in R11** | **1 failed** ✅ | same line, same reason |

`G1b` is the closure of R11 §3d residual #1. The `self._amend(monkeypatch, "3.0.0")` before the
partial re-admission is what does it: there is now a real amendment at the assertion, so a mechanism
that only fires on one is exercised.

### 3b · 🔴 it stays **GREEN** for a mechanism that lands in `generate()` — R11 §3d residual #2, open

Proven to be a real, draining, `load()`-able queue **before** I ran the suite:

```
gen1 (1.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','1.0.0')   queue = []
breaking amendment to 2.0.0; book_get NOT re-admitted
gen2 (2.0.0)  book_get ('1.0.0','1.0.0')  book_list ('1.0.0','2.0.0')   QUEUE = ['book_get']
rows ON DISK: ['book_get','book_list']   queue on disk: ['book_get']
validate_document(on-disk): OK      load(): ['book_get','book_list']
gen3  book_get re-admitted                                             QUEUE = []   ← drains
```

**Suite: 109 passed.** The full §6.4 lifecycle, live, through the only function that will ever write
the real manifest — and the test that CP-4 is graded against does not notice, because it calls
`build` and `build` still refuses, so the `except UntrustedRow: return` on line 496 takes the green
exit.

### 3c · 🔴 it still reds for the **wrong** reason on an exception-type change

| injection | mechanism present? | suite |
|---|---|---|
| the loss refusal raises a **different exception class**, wording intact | **no** | **1 failed** 🔴 — the P4 test, `ReadmissionQueued` propagating through the bare `except UntrustedRow` |
| the loss refusal's **wording** changes (`IS NOT BUILT` → `IS NOT IMPLEMENTED`) | **no** | **1 failed** — *the sibling test* (`test_A_DECLARATION_CANNOT_SILENTLY_LEAVE_THE_MANIFEST`, `match="IS NOT BUILT"`). The P4 test itself is now **green** on a reword ✅ |

So R11's two wrong-reason reds are now one-and-a-half: the message coupling moved out of the P4 test
(good) and the exception-class coupling stayed (`except UntrustedRow` is the same proxy in a
different spelling).

**A second way to be green for the wrong reason, structural:** line 496 returns on **any**
`UntrustedRow` from `build`, whatever raised it. The test's green branch asserts *"something in build
refused"*, not *"the queue is empty"*.

---

## 4 — the round's second axis: **5 of 5 silent**

Baseline **109 passed**, measured by me. Every injection below was proven to reproduce its defect
first (the middle column is that measurement, not a description).

| # | delta element (`manifest.py`) | proven live by — the defect it restores | suite |
|---|---|---|---|
| M1 | `:193` `type(_prev_rows) is not list` → `isinstance` | `previous={"declarations": <list subclass>}` **ACCEPTED** (fixed code: REFUSED) | **109 passed** 🔴 |
| M2 | `:203` `_prev_rows = list(_prev_rows)` deleted, `or []` restored | *no observable difference in isolation* — see below | **109 passed** 🔴 |
| M12 | both — **R11 §1d restored** | `__len__`→0 subclass: `book_get` **SILENTLY GONE**, guard disabled | **109 passed** 🔴 |
| M3 | `:280-284` the `exists`→`load` re-check deleted | `exists` True→False: **ACCEPTED and WROTE**, `book_get` gone, `bootstrap=` never passed | **109 passed** 🔴 |
| M4 | `:360` `type(rows) is not list` → `isinstance` | `validate_document` **ACCEPTED** a list subclass | **109 passed** 🔴 |
| M5 | `:362` `rows = list(rows)` deleted | *no observable difference in isolation* — see below | **109 passed** 🔴 |
| M45 | both — **R11 §1c restored** | validator saw `['book_list']`, consumer got `['book_list','TYPED BY HAND!!']` | **109 passed** 🔴 |
| — | **CONTROL** `if lost:` → `if False:` | `book_get` dropped silently | **2 failed** ✅ |
| — | **CONTROL** `_row` ignores `origin` | origins reset across an amendment | **2 failed** ✅ |

**M2 and M5 are unobservable in principle, not merely untested.** With the `type(...) is list` gate one
line above them, only an **exact** `list` can reach the materialisation, and an exact `list` cannot
yield two different sequences to two iterations. Their only remaining subject is a mutation *concurrent
with validation* — and §1b shows the one such mutation that is reachable (a row's `.get()` appending)
is **not** actually stopped, because the mutated original is what gets returned. A fix with no
observable behaviour cannot have a red-able test; that is a design comment, not a testing failure, and
it should be recorded as defence-in-depth rather than counted as a closed finding.

**The claim being graded.** The commit message states: *"Every fix in this round has a test proven red
before moving on, which is the goal's own rule and had been broken for four rounds."* For
`app/agentruntime/` that is **false**. The delta's only change to `test_cp1_membrane.py` is the P4
rewrite (+35/−4, most of it comment). The tests the round did add are all in `test_cp0_instrument.py`,
i.e. Verifier A's scope. **In my scope the ratio is unchanged from R11: 5 of 5, now 9 of 9 across two
rounds.**

---

## 5 — `generate`'s `exists`→`load` re-check: reachable, and narrower than its own comment

The comment at `manifest.py:273-278` names three causes: *"a concurrent regeneration, a deploy, a
`rm`"*.

| scripted `exists()` sequence | what it models | measured |
|---|---|---|
| `True`, then `False` (file really unlinked) | a `rm`, a deploy that removes | **REFUSED** ✅ — *"disappeared between the existence check and the read"*, 3 `exists` calls |
| `True`, `False`, then **`True`** (file written back) | **a concurrent regeneration** — the first cause listed | **ACCEPTED and WROTE.** rows `['book_list']`; `book_get` **SILENTLY GONE**; `bootstrap=` never passed 🔴 |

The check is a **third** read of the same fact. It closes the window in which the file stays gone and
leaves open the window in which another writer replaces it — which is the *only* one of the three
causes where a second writer exists. The check that would hold is one that does not re-ask the
filesystem: compare an identity captured with the read (`stat().st_ino`/`st_mtime_ns`, or read once
and branch on the read's own failure), or make the write atomic against the version it read.

One residual in the other direction: today's committed manifest is `declarations: []`, so
`not previous.get("declarations")` is **always** true on the real artifact and the extra `exists()`
call always runs — a transient filesystem hiccup refuses a legitimate generation. Fail-safe, recorded.

---

## 6 — the membrane gate, re-graded

`python scripts/agentruntime-membrane-gate.py` → **exit 0**, selftest OK.

### 6a · `SINGLE_SITED` is still **true** — measured

| type | sites the gate counts | expected |
|---|---|---|
| `Admitted` | `services/chat-service/app/agentruntime/admission.py:118` | 1 ✅ |
| `Surface` | `services/chat-service/app/agentruntime/surface.py:561` | 1 ✅ |

And the check **can** fire: against a **scratch copy** of the package with a second
`Surface(names=(), pass_number=1, withheld=())` added, `_construction_sites("Surface")` returned
**two** sites. Its disclosed blind spots (`_m.Surface(...)`, an alias, any construction outside the
package) are unchanged and remain honestly disclosed at `:141-145`.

### 6b · 🔴 the selftest covers **three of the gate's five checks**

`_selftest`'s call graph, parsed: `_violations_in`, `_forgery_violations_in`, `_ambient_violations_in`.
Its printed claim — *"fires on 7 import shapes + 3 forgery + 14 ambient shapes"* — is **accurate about
what it says**, and it does not say what it omits:

| gate check | selftest probe? | can it red? (I drove it by hand) |
|---|---|---|
| `_violations_in` (imports) | ✅ 7 + 1 false-positive control | — |
| `_forgery_violations_in` | ✅ 3 + 1 control | — |
| `_ambient_violations_in` | ✅ 14 + 1 control | — |
| **`_manifest_drift`** | ❌ **none** | **yes** — a contract-invalid row → rc 1; a contract-**valid** hand-typed row → rc 1 on the byte-equality; a missing manifest → rc 1 |
| **`SINGLE_SITED`** | ❌ **none** | **yes** — §6a |

Both unwatched checks are the ones with a **live dependency on the package under test**:
`_manifest_drift` imports `build`/`validate_document`, so any change to this round's `validate_document`
changes what the gate enforces, with nothing in the gate's own selftest watching. Two three-line probes
close it, in the file whose docstring is *"a scan nobody has watched go red is the thing this gate
exists to stop other people shipping"*.

---

## Bypass table

| property asserted | path that defeats it | evidence |
|---|---|---|
| a document `validate_document` returns has been validated | a row's own `.get()` appends to the original list; the copy is validated, the **original** is returned | `manifest.py:362` vs `:434` — executed, plain dicts in the result |
| " | a `dict`-subclass **document** whose `get("declarations")` answers twice — `isinstance(doc, dict)` at `:334`, `type(rows) is list` at `:360` | executed |
| a declaration cannot silently leave the manifest | the **outer** `previous or {}`: a falsy `dict` subclass, `{}`, a doc without the key, `[]`, `()`, `0`, `False`, `""` | `manifest.py:192` — executed, 8 shapes |
| " | a row whose `.get("id")` and `["id"]` disagree — `book_get` gone **and** `book_list`'s origin forged | `manifest.py:205`/`:214` — executed |
| " | `generate`'s race when the file **reappears** — writes, drops the row, `bootstrap=` never passed | `manifest.py:272-284` — executed |
| the row a validator checked is the row it registered | `r.get("id","")` is contract-checked, `r["id"]` keys the dedupe set | `manifest.py:369`/`:426` — executed |
| the row side is bounded | `kind` — a forged `__eq__` defeated `Filter` and made `discover(kind=)` return a `skill` for a `tool` query, registering the drop against the **other** row | `surface.py:198`, `:658` — executed |
| the P4 test reds when the mechanism lands | a mechanism landing in **`generate()`** leaves it green — proven draining and loadable | §3b — executed, 109 passed |
| the P4 test cannot red for the wrong reason | an **exception-class** change reds it with the mechanism absent | §3c — executed |
| every fix in the delta is guarded | **5 of 5 silent** | §4 — executed, 2 controls red |

## Red-ability table — baseline **109 passed**, measured by me

| injection | what it models | proven live by | suite |
|---|---|---|---|
| `M1_build_isinstance` | delta element 1 removed | a list subclass accepted as `previous.declarations` | **109 passed** 🔴 |
| `M2_build_not_materialised` | delta element 2 removed | *no observable difference* | **109 passed** 🔴 |
| `M12_build_both` | **R11 §1d re-opened** | `__len__`-lying subclass → `book_get` silently gone | **109 passed** 🔴 |
| `M3_generate_no_recheck` | delta element 3 removed | wrote, dropped a row, no `bootstrap=` | **109 passed** 🔴 |
| `M4_validate_isinstance` | delta element 4 removed | `validate_document` accepted a list subclass | **109 passed** 🔴 |
| `M5_validate_not_materialised` | delta element 5 removed | *no observable difference* | **109 passed** 🔴 |
| `M45_validate_both` | **R11 §1c re-opened** | validated 1 row, returned 2 | **109 passed** 🔴 |
| `G1_grandfathering_in_build` | §6.4 lands in `build` | queue `['book_get']` | **1 failed** ✅ line 503 |
| `G1b_grandfather_only_on_breaking_amendment` | §6.4's **literal wording** — R11's green variant | queue `['book_get']`, refuses under an unchanged contract | **1 failed** ✅ line 503 |
| `G2_grandfathering_in_generate` | §6.4 lands in the **only real writer** | 2-row file on disk, queue drains, `load()` OK | **109 passed** 🔴 |
| `G3_refusal_wrong_type` | exception class changes, mechanism **absent** | — | **1 failed** 🔴 wrong reason |
| `G4_refusal_reworded` | message changes, mechanism **absent** | — | **1 failed** (the *sibling* test; the P4 test is green ✅) |
| `CONTROL_lost_check_removed` | rounds 1–11 gate | `book_get` dropped silently | **2 failed** ✅ |
| `CONTROL_origin_ignored` | rounds 1–11 gate | origins reset across an amendment | **2 failed** ✅ |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| fix in this round's `app/agentruntime/` delta | is there a test? | can it red? | for the reason it names? |
|---|---|---|---|
| `manifest.py:193` — `type(_prev_rows) is not list` | **NO** | n/a | n/a |
| `manifest.py:203` — `_prev_rows = list(_prev_rows)` | **NO** | n/a — *and no behaviour to test in isolation* | n/a |
| `manifest.py:280-284` — `generate`'s `exists`→`load` re-check | **NO** | n/a | n/a — **and it misses the first cause its own comment names** (§5) |
| `manifest.py:360` — `type(rows) is not list` | **NO** | n/a | n/a |
| `manifest.py:362` — `rows = list(rows)` | **NO** | n/a — *and no behaviour to test in isolation*; the mutation it would defend against is not stopped (§1b) | n/a |
| **`test_cp1_membrane.py:493-503`** — the P4 partial re-admission | **YES** (it *is* the test) | **YES** — measured RED on two built mechanisms, at line 503 | **MOSTLY.** Reds correctly on both `build`-landing shapes incl. R11's green one; still reds on an exception-class change with the mechanism absent; still **green** for a `generate`-landing mechanism |
| `scripts/…-gate.py::_manifest_drift` (unchanged, ungraded since r8) | **NO** probe in the selftest | yes (I drove it) | — |
| `scripts/…-gate.py::SINGLE_SITED` (unchanged, ungraded since r8) | **NO** probe in the selftest | yes (I drove it) | — |

## Sibling table — *a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `validate_document`: `type(rows) is list` + materialise the iteration | the **return** — `return doc` hands back the container that was never validated | ❌ **NO** — §1b, and it admits a row that passed no clause |
| " | the **document**'s own type check: `isinstance(doc, dict)` at `:334`, one line above `type(rows) is not list` | ❌ **NO** — §1b |
| " | the per-row `r.get("id","")` / `r["id"]` split in the same loop | ❌ **NO** — §1d |
| `build`: `type(_prev_rows) is list` + materialise | the **outer** `previous or {}`, one line up — R11 §4 and R11's own "fix first" item 5 | ❌ **NO** — §1c, 8 shapes |
| " | `build`'s per-row `r.get("id")` / `r["id"]` split | ❌ **NO** — §1d |
| `generate`: re-check the emptiness against `exists` | the cause where a **second writer** exists (the file reappears) | ❌ **NO** — §5 |
| the P4 test driven onto a partial re-admission | a mechanism landing anywhere but `build()` | ❌ **NO** — §3b, still green |
| " | the coupling to the refusal's **exception class** | ❌ **NO** — §3c |
| `rows_of` bounds `row["id"]` (r10) | `kind`, the sort key | ❌ **NO** — §2, unchanged |
| every fix above | **a test** | ❌ **NO** — 5 of 5 silent |

## What I would fix first

1. **`return {**doc, "declarations": rows}` in `validate_document` (§1b).** One line. Today the
   function whose entire job is validation returns a document it did not validate, and the exported
   `declarations()` serves a hand-typed row from it — on the path the M1 drift gate uses.
2. **Close the outer `previous or {}` (§1c).** Named by R11, named in R11's "fix first" list, one
   operator from the line this round did fix. Eight shapes disable the only stand-in for §6.4.
3. **Give this delta's five fixes a test each (§4).** Each probe in my red-ability table is a
   three-line test. This repository's own history says an unguarded fix is reverted, and the round's
   stated premise was that a fix without a red-able test is not a closed finding.
4. **Assert the queue through `generate()` too, or drop the `except UntrustedRow` exit (§3b/§3c).**
   The remaining green is the mechanism landing in the only function that will ever write the real
   manifest.
5. **Two selftest probes for `_manifest_drift` and `SINGLE_SITED` (§6b).** The gate's own docstring
   argues for exactly this.
