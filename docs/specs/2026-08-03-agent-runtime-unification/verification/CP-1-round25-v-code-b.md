# CP-1 · round 25 · V-CODE **Verifier B** — the membrane

| | |
|---|---|
| **Worktree** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\r25-b` |
| **`git rev-parse HEAD` at start** | `c181a35253aea18f5da827163274964e8ecda4b9` |
| **`git rev-parse HEAD` at finish** | `c181a35253aea18f5da827163274964e8ecda4b9` |
| **`git status --porcelain` at finish** | *(empty — byte-clean)* |
| **Baseline** | `tests/test_cp1_membrane.py` → **144 passed** · `agentruntime-membrane-gate.py` → **OK, 8 modules, 0 external imports** |
| **Isolation** | Every mutation ran in a **throwaway `git ls-files` mirror**, never in the worktree. No file was observed changing under me. |
| **Census** | **NOT** run whole (≈20 min). Instead I ran a **targeted census with my own instrument** over an enumerated 13-row space (the 4 claimed-moved + all 9 remaining SILENT) which additionally reports **which test reds** — something the shipped census cannot say. Stated deliberately. |

## VERDICT: **FAIL**

Not because the five graded items are wrong. **All five guards red for the reason they name, and this is the first round in this series where I can say that of every graded item** — items 1, 3, 4 and 5 are clean on their own terms and item 2's guard is clean on the terms it actually states.

The FAIL is driven by three things, in order:

1. **F1** — the repair for B18-11 ships a gate I defeated with **one word of prose**. I restored the exact seven-round defect (`from . import canon` in `contract.py`, zero call sites) **with the suite green**. That is the fourth "a test satisfied by a comment" in this run, and it is inside the repair for the finding it closes.
2. **F3** — the delta's headline evidence sentence, *"Zero NEWLY SILENT is the half that matters: the digest did not churn"*, is **false for 1 of the 4 rows**. The conclusion survives (I executed it); the stated evidence does not.
3. **F2** — measurable today, discovered today: **9 of 9 real workflow ids fail `_ID`'s alphabet.** Six rounds went into the *length* half of that regex while the *alphabet* half refuses 100% of one declaration kind's real ids at CP-4.

---

## 1 · The falsifier per claim, and whether the guard reds for its own reason

Every reversion below was **re-derived by me**, not inherited. Each ran in a fresh mirror; the "first `E` line" column is the actual pytest output.

| # | claim | **my falsifier** | executed reversion | result | reds for **its own reason**? |
|---|---|---|---|---|---|
| **1** | `members` copied at both doors | *"revert either copy to `dict(r)` and the guard stays green, or reds naming something other than `members`"* | `R1a` `surface.rows_of`: `{**r,"members":list(...)}` → `dict(r)` | **RED**, 1 failed / 143 passed. `E AssertionError: rows_of handed back the source document's own 'members' list; dict(r) is a shallow copy and members is the only mutable value a row carries` | **YES** — names the door, the field and the mechanism |
| **1** | ″ | ″ | `R1b` `manifest.validate_document` half only | **RED**. `E … validate_document handed back the source document's own 'members' list …` | **YES** — the sibling half is independently red-able |
| **1** | ″ | ″ | `R1c` both doors | **RED** at `rows_of` first | **YES** |
| **2** | `ID_MAX_LEN=64` driven at the id **and** the member spelling | *"remove the quantifier and only one spelling reds, so the other is decorative"* | `R2a` `{0,63}` → `*` | **RED**, `E Failed: DID NOT RAISE ContractViolation` at the **id** assertion | **YES** for the id half |
| **2** | ″ | ″ | `R2h` **member spelling isolated**: a separate unbounded `_ID_MEMBER` used only at `check_contract:398`, id bound left intact | **RED**, `DID NOT RAISE` — and by elimination only `match="not a declaration id"` can be the failing assertion | **YES** — both spellings are independently red-able. The delta's "driven at both" is **true** |
| **3** | `OrderBy` key-pair shape | *"neuter `ValueError::3` and the chosen vehicle still raises from Python's own unpacking, proving nothing"* | census neutering of `surface.py::OrderBy.__post_init__::ValueError::3::b3926159` + a **15-vehicle enumeration** (§4) | **RED**, exactly `test_A_KEY_PAIR_THAT_IS_NOT_A_PAIR_IS_REFUSED__and_the_vehicle_is_a_LIST`; the 2-element list is genuinely accepted when neutered | **YES** — and **5 of my 15 vehicles** survive the neutering, so the space is larger than the delta's "the one vehicle", but the chosen one is valid |
| **4** | B18-8 str-subclass key **and** member | *"one pin is decorative — neuter it alone and nothing reds"* | `R4a` key pin `type(key) is not str` → `not isinstance(...)` | **RED**, `DID NOT RAISE` (first `pytest.raises`, the key pin) | **YES** |
| **4** | ″ | ″ | `R4b` member pin only | **RED**, `DID NOT RAISE` (second `pytest.raises`) | **YES** — both pins independently red-able |
| **5** | B18-11 dead imports | *"re-add a dead import and the gate stays green"* | `R5a` `from . import canon` back into `contract.py` | **RED**, `E AssertionError: ['contract.py:27 imports canon, which it never uses']` | **YES** — names file, line and symbol |
| **5** | ″ | ″ | `R5b` `import re` back into `manifest.py` (the THIRD one) | **RED**, `['manifest.py:23 imports re, which it never uses']` | **YES** |

**Bystander check:** in all ten reversions **exactly one test** failed and it was the named guard. No reversion produced a collateral red. Item 1's guard names its door in the message; items 2 and 4 report only `DID NOT RAISE`, so I isolated each pin/spelling separately rather than trusting a shared failure — which is what makes those rows say `YES` rather than `CANNOT DETERMINE`.

---

## 2 · Bypass table

*Can the property be defeated with the guard GREEN?*

| # | property | bypass found | executed | reachable today |
|---|---|---|---|---|
| 1 | rows never alias the source document's `members` | **none** — 504-cell enumeration (§5) found 0 leaks and 0 aliases at 5 doors | ✅ | — |
| 2 | *"an id is a key, and a key is bounded"* | **YES** — set `ID_MAX_LEN = 1_000_000`. Suite **green**. The bound is guarded only from below (§3) | ✅ | at CP-2/CP-4, by an ordinary edit |
| 2 | the bound applies *"everywhere an id is a key"* | **YES** — 7 of 7 stage-parameter doors accept a 300-char key (`AllowList.names`, `DenyList.names`, `Filter.value`, `Filter.field`, `OrderBy` field, `discover(kind=)`, `TakeWhileBudget.cost_field`) | ✅ | CP-2 (a configured pipeline) |
| 3 | `OrderBy` refuses a non-pair | **none** — all 15 vehicles refused in the shipped state | ✅ | — |
| 4 | *"a `str` subclass is not a `str`"* | **YES** — `check_contract` uses `isinstance`, so a subclass id **and** member pass `admit()` (§6) | ✅ | CP-2 (`admit` is exported) |
| 5 | *"a module may not import a name it does not use"* | **YES, and decisively** — re-add `from . import canon` **and** change one docstring word from `` `x` `` to a bare token containing `canon`: gate **GREEN**, 1 passed (§7) | ✅ | **today** — these docstrings are rewritten every round |

---

## 3 · `ID_MAX_LEN = 64` — the number a person chose

### Is 64 defensible? **Yes — and this is the first time anyone in this run has measured it.**

I read the three legacy registries the suite itself calls the future declaration corpus (`tools-list.snapshot.json`, `LOADABLE_SKILL_CODES`, `intent_workflows._COMPILED`) — **334 ids**:

| kind | n | max len | p99 | mean | **> 64** |
|---|---|---|---|---|---|
| tool | 315 | **38** | 37 | 22.7 | **0** |
| skill | 10 | 11 | 11 | 8.2 | **0** |
| workflow | 9 | 19 | 16 | 12.8 | **0** |

`DECLARATION-BACKLOG.md`'s longest backticked id is 28 chars. **Nothing in the tree exceeds 64**, and 64 is 1.68× the observed maximum. The docstring's claim — *"longer than every identifier this repository declares"* — is **TRUE**, executed.

### Is the number itself guarded? **No — only from below.** (F4)

Sweep of `ID_MAX_LEN`, whole membrane suite each time:

| value | 9 | 12 | 32 | **64** | 300 | 10 000 | 1 000 000 |
|---|---|---|---|---|---|---|---|
| suite | 9 failed | 1 failed | **green** | **green** | **green** | **green** | **green** |

The guard derives `at_limit`/`over` **from `ID_MAX_LEN` itself**, so the guarded interval is `[≈20, ∞)`. This is the *derive-your-denominator-from-the-SSOT* failure applied to a constant: the test proves "a bound exists", never "the bound is small enough to be the bound the docstring argues for". Falsifier for anyone who disagrees: `ID_MAX_LEN = 1_000_000` → 144 passed.

### Is it enforced everywhere an id is a key? **On one side of every comparison only.** (F6)

The docstring enumerates four places. Executed:

| the key | row side | **comparand side** |
|---|---|---|
| `AllowList`/`DenyList` membership | bounded ✅ | **`names=("a"*300,)` ACCEPTED** ❌ |
| `OrderBy` tie-break | bounded ✅ (the tie-break reads `row["id"]`) | `OrderBy(keys=(("a"*300,"asc"),))` accepted, but `sort()` then refuses the missing field — contained |
| M5 foreign key (`members`) | bounded ✅ | n/a |
| the prompt surface (`Surface.names`) | bounded ✅ | n/a |
| *(not in the docstring)* `Filter.value` / `Filter.field` / `discover(kind=)` / `TakeWhileBudget.cost_field` | — | **all accept 300 chars** ❌ |

Consequence, stated at its true size: an over-long `AllowList` name can never match a bounded row, so it narrows to zero — **loudly**, because the drop registers. This is an **asymmetry, not a leak**. Reachability: **CP-2**.

### What happens at CP-2/CP-4 when real ids arrive? — **F2, and it is not the length.**

```
workflow ids failing ^[a-z][a-z0-9_]*$ : 9 of 9
  entity-triage · canon-check · kg-build · build-a-book · translation-pass · autonomous-drafting · chapter-compose · …
```

**Every real workflow id uses hyphens.** At CP-4, `check_contract` refuses 100% of the workflow kind, and the message it prints is *"not a stable identifier … at most 64 characters"* — i.e. the clause that will actually fire is the alphabet, and the message leads with the length. `ARCHITECTURE.md` C-0 specifies *"id"* and no alphabet; `^[a-z][a-z0-9_]*$` is a builder choice that silently excludes an entire existing namespace. Tools (315) and skills (10) pass the alphabet cleanly, so the blast radius is exactly one kind — but it is 9/9 of it.

**This was one command away from the measurement that justified 64**, over the same corpus, and was not made. **Reachable: CP-4. Measurable: today (measured above).**

---

## 4 · Item 3 — `OrderBy`'s vehicle space, with my own denominator

The delta claims *"a 3-tuple / 1-tuple / 2-char `str` all raise from Python's own unpacking and prove nothing"*, and that a 2-element **list** is *"the one vehicle the unpacking does not mask"*. I enumerated **15** vehicles and executed both states.

| vehicle | shipped | `ValueError::3` **neutered** | verdict |
|---|---|---|---|
| 2-tuple (legal control) | accepted | accepted | control holds |
| **2-element list** | refused ::3 | **ACCEPTED** | ✅ valid vehicle *(the builder's)* |
| **list subclass with a lying `__iter__`** | refused ::3 | **ACCEPTED** | ✅ valid — **and the strongest**: it is the TOCTOU class the check exists for |
| **generator-materialised list** | refused ::3 | **ACCEPTED** | ✅ valid |
| **2-element dict** | refused ::3 | **ACCEPTED** (unpacks its keys) | ✅ valid |
| **namedtuple(2)** | refused ::3 | **ACCEPTED** | ✅ valid |
| 3-tuple / 1-tuple / 0-tuple | refused ::3 | `too many/not enough values to unpack` | masked by unpacking |
| 2-char `str` / `str` subclass | refused ::3 | `unknown direction 'b'` | masked by `DIRECTIONS` |
| 2-element `set` | refused ::3 | `unknown direction 'id'` | masked by `DIRECTIONS` |
| `bytes` / `bytearray` / `range` | refused ::3 | `field is a int … must be a plain str` | masked by `_plain` |

**My denominator: 15 vehicles, 5 valid, 10 masked** — by three different siblings, not one. The delta named 1 of the 5 and named the masking mechanism as unpacking alone when it is in fact unpacking **plus** `DIRECTIONS` **plus** `_plain`. The claim is **directionally right and under-counted**; the guard is sound. The vehicle chosen is the *weakest* of the five that work — a plain list has no custom dunders, so it demonstrates the shape check but not the "container that decides its own iteration" harm the error message names. The list-subclass vehicle would demonstrate both.

---

## 5 · Item 4 — the one-level copy, verified rather than accepted, at every door

**Claim under test:** *"`check_row` bounds `members` to a `list`/`tuple` of `str`, so one level is the whole depth."*

**Enumerated space:** 7 `ROW_FIELDS` keys × 9 payload types (`list`, `dict`, `set`, `bytearray`, `tuple_of_list`, `str`-subclass, `list_containing_list`, `list_containing_dict`, `tuple_containing_str`) × 8 doors (`check_row`, `check_row_shape`, `rows_of`, `validate_document`, `declarations`, `discover`, `SurfaceAssembler`, `build(previous=)`) = **504 cells, all executed.**

| result | count |
|---|---|
| a **mutable** value accepted past `check_row` at any door | **0** |
| a mutable value accepted by `check_row_shape` **alone** (`members` as `list`/`tuple` of `str`) | 2 — and both are refused one layer up by `check_contract` for the fixture's `kind` |
| a `str`-subclass accepted as a row **value** at any door | **0** |

**Aliasing, executed on the shipped-legal shape** (a skill + a tool, live document):

| door | aliased row identity | aliased mutable field |
|---|---|---|
| `rows_of` | none | **none** |
| `validate_document` | none | **none** |
| `declarations` | none | **none** |
| `discover` | none | **none** |
| `SurfaceAssembler._rows` | none | **none** |

**Is there any path where a row reaches a consumer without `check_row` having run?** Enumerated all seven exported row-serving doors: `rows_of` (calls it), `validate_document` (calls it), `declarations` (→ `rows_of`), `discover` (→ `rows_of`), `SurfaceAssembler.__init__` (→ `rows_of`), `build(previous=)` (calls it per row), `_row` (calls it on its own output). `build()`'s output rows are freshly constructed by `_row` and alias nothing caller-supplied; `Surface` carries only `tuple[str]` and record dicts. **No such path.**

**Is there any other mutable value a row can carry?** `ROW_FIELDS` types are `(str,)` for six keys and `(list, tuple)` for `members`; `check_row_shape` enforces `type(val) is w` and `type(m) is str` per element. **`members` is the one mutable value — CONFIRMED by execution, not accepted.** One residual, benign: a `members` **tuple** arriving in-memory is returned as a `list` (JSON cannot produce one, so this is unreachable through `load()`).

---

## 6 · The sibling table — for every fix, is its twin fixed too?

| # | fix landed at | its twin | twin fixed? | executed |
|---|---|---|---|---|
| 1 | `surface.rows_of` copy | `manifest.validate_document` copy | ✅ **YES** — both, and both independently red-able (`R1a`/`R1b`). Grep confirms **exactly 2** copy sites in the package | ✅ |
| 2 | `_ID` at `check_contract` id | `_ID` at `check_contract` members | ✅ **YES** — `R2h` isolates the member spelling and it reds | ✅ |
| 2 | row-side id bound | **comparand-side bound** (`AllowList`/`DenyList`/`Filter`/`discover`/`TakeWhileBudget`) | ❌ **NO — 7 of 7 unbounded** (F6) | ✅ |
| 2 | the id **length** clause | the id **alphabet** clause | ❌ **NO — 9/9 workflow ids unadmittable** (F2) | ✅ |
| 4 | `check_row_shape` key pin | `check_row_shape` member pin | ✅ **YES** — `R4a`/`R4b` isolate both | ✅ |
| 4 | `check_row_shape`'s `type(x) is str` | **`check_contract`'s `isinstance(d.id, str)` / `isinstance(m, str)`** | ❌ **NO** (F5) — `admit(Declaration(id=SubStr("book_list")))` **succeeds** | ✅ |
| 5 | `contract.py` dead import | `manifest.py` dead imports (`canon`, `re`) | ✅ **YES** — property gate found the third | ✅ |
| 5 | the gate's **AST** term | the gate's **string-literal** term | ❌ **NO** (F1) — the term the gate leans on is the one that blinds it | ✅ |

**Score: 4 of 8 pairs fixed at both ends.** The four unfixed twins are all *one level out* from where the reviewer pointed — the same shape this run has recorded eleven times.

---

## 7 · F1 — the dead-import gate, enumerated and defeated

The gate treats a name appearing in **any** whitespace-delimited token of **any** string literal as "used". I enumerated **15 shapes** (11 genuinely-dead + 4 live controls) and ran the gate's own algorithm on each.

| # | shape | gate |
|---|---|---|
| 1 | bare dead import *(control)* | **CAUGHT** |
| 2 | name is a **bare word in the module docstring** | **MISSED** |
| 3 | name in a docstring **inside backticks** | CAUGHT *(backticks make it a different token)* |
| 4 | name shadowed by an unrelated **attribute** access (`c.re`) | **MISSED** |
| 5 | name reused as a **local variable** | **MISSED** |
| 6 | dead **`__`-prefixed alias** | **MISSED** *(excluded by the gate's own `startswith("__")`)* |
| 7 | **second** dead import of a name imported twice | **MISSED** *(`bound` is a dict keyed by name)* |
| 8 | name shadowed by a later **assignment** | **MISSED** |
| 9 | name appears in an **unrelated message string** | **MISSED** |
| 10 | name appears only in a **comment** | CAUGHT *(comments are not in the AST — the one place the looseness does not reach)* |
| 11 | *live* import used only in a nested function | ok |
| 12 | ***live* side-effect-only import** (`import app.agentruntime.canon`) | **FALSE POSITIVE** |
| 13 | *live* import re-exported via `__all__` | ok |
| 14 | *live* import used only in a string annotation | ok |
| 15 | dead import in a **sub-package** (`glob("*.py")` is non-recursive) | **MISSED** |

**My denominator: 3 of 11 dead-import shapes caught (27%).** The looseness is *mostly* in the safe direction (8 false negatives), **but not exclusively** — shape 12 reds correct code. Reachability of the FP: no side-effect import exists today; a registration import is a plausible CP-2 pattern. **LOW today.**

### And the part that makes this a FAIL, not a note

The gate's subject module survives **only because its prose happens to use backticks.** Executed:

> **`R5d`** — re-add `from . import canon` to `contract.py` **and** change one docstring phrase from `*name the field path rejected …*` to `canon name the field path rejected …`
> → `test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON` : **1 passed.**
>
> **`R5e`** — re-add `import re` to `manifest.py` **and** add `_NOTE = "the manifest is not parsed with re at all"`
> → **1 passed.**

**The exact seven-round B18-11 defect is fully restorable with the gate green, by editing prose.** Not adversarial prose — *ordinary* prose, in files whose docstrings are rewritten every round. The delta's own celebration — *"a property finds the class"* — is true of the AST half and false of the term that decides the answer.

**I also tested the obvious repair and it is wrong.** Deleting the string-literal term outright reds the gate on **~30 re-exports in `__init__.py`**, which are "used" only via the `__all__` string list:

```
E AssertionError: ['__init__.py:25 imports Admitted, which it never uses',
                   '__init__.py:25 imports admit, …', '__init__.py:26 imports CONTRACT_VERSION, …', …]
```

So the term is load-bearing **for exactly one construct**. The correct narrowing is: `used |= {elements of a module-level __all__ list}` — not every token of every string. That closes shapes 2 and 9 and costs nothing. Stated as a prescription because I executed the naive version and it fails.

---

## 8 · F3 — the four rows, and the sentence that is false about one of them

**Independently confirmed, by my own targeted census (13 neuterings, each reporting the failing test):**

| row | census | failing test | delta's claim |
|---|---|---|---|
| `contract.py::check_row_shape::ContractViolation::2` | **RED** | `test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR` | ✅ holds |
| `contract.py::check_row_shape::ContractViolation::7` | **RED** | `test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR` | ✅ holds |
| `surface.py::OrderBy.__post_init__::ValueError::3` | **RED** | `test_A_KEY_PAIR_THAT_IS_NOT_A_PAIR_IS_REFUSED__and_the_vehicle_is_a_LIST` | ✅ holds |
| `contract.py::check_contract::ContractViolation::7` | **RED** | `test_AN_ID_IS_A_KEY_AND_A_KEY_IS_BOUNDED` | ✅ holds — **but see below** |

Each reds via **exactly one** test. So *"four rows left the allowlist because a guard arrived"* is **substantively true**. The evidence offered for it is not.

### The digest DID churn — for exactly the fourth row

| | allowlist row **before** | site id **now** |
|---|---|---|
| `check_row_shape::CV::2` | `…::3e304e0c` | `…::3e304e0c` — unchanged |
| `check_row_shape::CV::7` | `…::559cf0a3`¹ | unchanged |
| `OrderBy::VE::3` | `…::b3926159` | unchanged |
| **`check_contract::CV::7`** | **`…::6899e25d`** | **`…::179f246e`** ← **CHANGED** |

¹ `559f0a3`/`559cf0a3` per the file; unchanged either way.

**Cause:** the `_ID` fix rewrote that refusal's message from a plain string to an **f-string interpolating `ID_MAX_LEN`**. `_shape_digest` blanks `ast.Constant` string nodes — but an f-string is a `JoinedStr` whose `FormattedValue` carries a bare `ast.Name('ID_MAX_LEN')`, which the blanking does not erase. The digest moved.

**Why it matters:** the census reported that row as *"NOW GUARDED — drop it from the allowlist"* for a row whose id had simply ceased to exist. It **is** also genuinely red (I executed it), so the outcome is right; but *"the digest did not churn, so no allowlist row moved for a reason other than a guard arriving"* is **false for 1 of 4**, and the mechanism that made it false — an f-string is not prose-blind — is a live hole in an instrument the delta's own §"three holes" section does not list. Any future fix that puts a constant's *name* into a refusal message will silently relocate that row.

**Reachability: today, in the instrument.** Not a production defect.

---

## 9 · The 9 SILENT rows — classified, which the census says still needs a person

Method: neuter each site in a mirror, then **drive the input that should reach it** and compare behaviour against the shipped state. All nine executed.

| row | classification | evidence |
|---|---|---|
| `canon::_norm::NotCanonicalisable::1` (float) | **SIBLING** | neutered, `digest(1.5)` still refuses — via `::4`, the fall-through, with a different message |
| `canon::_norm::NotCanonicalisable::2` (non-`str` dict key) | **UNCHECKED** | neutered, `digest({1:"a"})` → `'7cf958f5…'`. A digest whose key ordering is insertion-dependent, silently produced |
| `canon::_norm::NotCanonicalisable::4` (fall-through) | **UNCHECKED** | neutered, `digest(object())` → `'04d3fc18…'` |
| `manifest::build::UntrustedRow::4` | **UNREACHABLE — dead code** | `check_row` can raise **only** `ContractViolation` (AST call-closure over `contract.py` **and** 25 executed malformed rows → 25/25 `ContractViolation`). The `except UntrustedRow` at `manifest.py:246` can never fire |
| `manifest::generate::UntrustedRow::1` | **UNCHECKED** | fires when `manifest_path()` returns `None`; I reproduced it by anchoring `ambient.module_anchor` outside any marker. **This is the flattened-image case `manifest_path`'s own docstring exists for** |
| `manifest::generate::UntrustedRow::2` | **UNREACHABLE deterministically** | needs a concurrent `unlink` between `exists()` and `load()` |
| `manifest::validate_document::UntrustedRow::5` | **SIBLING (partial)** | neutered, `declarations="nope"` still refuses — `list("nope")` yields chars and `check_row` refuses them. Residual: `declarations=None`/`5` become an **uncaught `TypeError`**, converting a documented refusal into a crash |
| `manifest::validate_document::UntrustedRow::6` | **UNREACHABLE — dead code** | same proof as `build::UR::4`; `manifest.py:429` |
| `surface::TakeWhileBudget::ValueError::1` | **UNCHECKED** | neutered, `TakeWhileBudget(budget=-1)` **constructs** |

**Tally: 4 UNCHECKED · 2 SIBLING · 3 UNREACHABLE (2 of them provably dead `except` clauses).**
The allowlist header says this distinction *"still needs a person and a verdict id."* **This verdict is that person; the id is `CP-1-round25-v-code-b`.** Two rows should not be in an allowlist at all — they should be deleted from the source, because an `except` that cannot fire is not a refusal.

---

## 10 · Item 5 (both verifiers) — the transfer

**The load-bearing fact, checked myself:** repo-wide grep for `agentruntime` across `*.py|*.toml|*.yaml|*.json|*.sh|Dockerfile*`, excluding the package and `docs/`. The **only** Python import of `app.agentruntime` outside the package is `scripts/agentruntime-membrane-gate.py:347` (the gate's own smoke import) and `tests/`. `app/db/migrate.py:368` and `app/services/instrument.py:100` carry the *string* `"agentruntime"` as a `runtime_variant` label with **no dispatch** (`runtime_variant` defaults to `RUNTIME_LEGACY` and is only stamped onto chunks). **CONFIRMED: zero production importers.**

| transferred item | criterion honestly applied? | measurable **today**? |
|---|---|---|
| catalogue-outage ordering residual | ✅ **YES** — it needs a turn, and no turn can be placed on this surface | No |
| **B18-10 — a fifth exported door** *as a leak* | ✅ **YES** — a door with no caller cannot be measured as a leak | Not as a leak |
| **`rows_of` runs no document-level stamp check** | ❌ **NO — criterion substituted** | **YES, and here it is** |

The stated criterion is *"an item whose **measurement** has no SUBJECT until a later checkpoint's code exists."* The reason recorded for this transfer is *"production-reachable **at** CP-2, not today."* Those are different predicates, and the item was moved on the second while the nine kept items were judged on the first.

**Executed today, 6 document-level defects × 6 doors = 36 cells:**

| document defect | `rows_of` | `declarations` | `discover` | `SurfaceAssembler` | `validate_document` | `build(previous=)` |
|---|---|---|---|---|---|---|
| `manifest_version` missing | **SERVED** | **SERVED** | **SERVED** | **SERVED** | refused | refused |
| `manifest_version: 999` | **SERVED** | **SERVED** | **SERVED** | **SERVED** | refused | refused |
| `contract_version: "banana"` | **SERVED** | **SERVED** | **SERVED** | **SERVED** | refused | refused |
| `contract_version` missing | **SERVED** | **SERVED** | **SERVED** | **SERVED** | refused | refused |
| unknown top-level key `lane` | **SERVED** | **SERVED** | **SERVED** | **SERVED** | refused | refused |

**Four exported doors serve rows from a document whose own stamps they never read** — including `contract_version`, which `validate_document`'s own comment calls *"§6.4's queue COMPARAND"*. This is the nine-classes finding **one level up**: the ROW definition was consolidated across doors and the DOCUMENT definition was not. It runs in one command, today.

**Verdict on the transfer: 2 of 3 honest, 1 criterion-substituted.** Not a board-clearing — the two genuinely unbuilt items are correctly scoped, and the reasoning for them is sound. But the third was moved on a predicate the board did not state, and it is the one that is measurable now.

---

## 11 · Guard table

| guard | binds the property, or the nearest proxy? |
|---|---|
| `test_THE_ROW_COPY_IS_NOT_SHALLOW__…` | **the property.** Asserts list **identity** and then writes through it, at 3 doors. Red-able at each half separately |
| `test_AN_ID_IS_A_KEY_AND_A_KEY_IS_BOUNDED` | **a proxy.** Binds *"a bound derived from `ID_MAX_LEN` exists"*, not *"the bound is 64"* — `ID_MAX_LEN = 1_000_000` is green. Both **spellings** are genuinely bound |
| `test_A_KEY_PAIR_THAT_IS_NOT_A_PAIR_IS_REFUSED__…LIST` | **the property**, via 1 of 5 valid vehicles — the weakest of the five, but valid, and it carries a positive control |
| `test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR` | **the property**, for the 2 pins it names. Scoped to `check_row_shape`; the same claim's 2 sites in `check_contract` are unbound |
| `test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON` | **a proxy, and a defeatable one.** 3 of 11 shapes; blinded by one prose word; 1 false-positive class |
| `scripts/agentruntime-census.py` | **the property** — my independent re-derivation reproduces 68 sites and all 9 allowlist digests exactly. One hole: an f-string interpolating a `Name` is not prose-blind (F3) |

---

## 12 · Reachability verdict on every finding

| id | finding | severity | **production-reachable today?** |
|---|---|---|---|
| **F1** | dead-import gate defeated by one prose word; B18-11 restorable green | **HIGH** (instrument) | The *gate hole* is live **today**. The *dead import* it would hide is not a production defect |
| **F2** | 9/9 real workflow ids fail `_ID`'s alphabet | **HIGH** | **No — CP-4.** Measurable today (measured). Blocks the workflow kind entirely on arrival |
| **F3** | `check_contract::CV::7` digest churned; delta's evidence sentence false for 1 of 4 | **MED-HIGH** (instrument) | Live **today** in the census. Conclusion unaffected |
| **F4** | `ID_MAX_LEN` guarded only from below; `1_000_000` is green | **MED** | No code path today. Reachable by an ordinary edit at any time |
| **F5** | `check_contract` uses `isinstance` — a `str`-subclass id/member passes `admit()` | **MED** | **No — CP-2** (`admit` exported, no importers). Contained at `_row` by `type(m) is str` |
| **F6** | id bound on the row side only; 7/7 comparand doors unbounded | **MED** | **No — CP-2** (needs a configured pipeline) |
| **F7** | transfer of `rows_of`'s document check used a substituted criterion; 24/24 cells SERVED | **MED** | **No** (no importers) — but **measurable today**, which is what the criterion asks |
| **F8** | 2 of the 9 SILENT rows are provably unreachable `except` clauses | **LOW-MED** | Dead code today. `manifest.py:246`, `manifest.py:429` |
| **F9** | dead-import gate false-positives a side-effect-only import | **LOW** | No such import exists. CP-2 pattern |
| **F10** | the round prompt's CRLF warning is wrong for these files — all four subjects are **LF** (0 CRLF bytes) | **INFO** (method) | n/a. Recorded so the next round does not spend time normalising |

---

## 13 · Red-ability table, with **my own** denominator

| space | builder's number | **my denominator** | executed |
|---|---|---|---|
| membrane fixes red-able by exact reversion | 7/7 | **10/10** (I split items 1, 2 and 4 into per-door / per-spelling / per-pin reversions) | ✅ |
| census rows moved SILENT→RED | 4 | **4/4 confirmed**, each via exactly **one** named test | ✅ |
| rows still SILENT | 9 | **9/9 confirmed**, and **classified**: 4 unchecked · 2 sibling · 3 unreachable | ✅ |
| `OrderBy` vehicles | "the one vehicle" | **5 of 15 valid**, masked by **3** different siblings (not 1) | ✅ |
| dead-import shapes caught | *(none published)* | **3 of 11** (27%), **+1 false-positive class** | ✅ |
| `members` depth — mutable values a row can carry | 1 (`members`) | **1 of 63** field×payload combinations, over **504 cells**, **0 aliases at 5 doors** | ✅ |
| doors validating the ROW | "every row-reader" | **7 of 7** ✅ | ✅ |
| doors validating the **DOCUMENT** | *(not claimed)* | **2 of 6** — 24/24 malformed-document cells SERVED | ✅ |
| id bound enforced on the comparand side | *(implied "everywhere")* | **0 of 7** | ✅ |
| `ID_MAX_LEN` values the suite accepts | *(implied: 64)* | **`[≈20, ∞)`** — 1 000 000 is green | ✅ |
| real declaration ids exceeding 64 | *(implied 0)* | **0 of 334** ✅ — first executed defence of the number |
| real declaration ids failing the **alphabet** | *(not measured)* | **9 of 334, and 9 of 9 workflows** | ✅ |

---

## 14 · Convergence

| round | independent findings, this verifier's half |
|---|---|
| R20–R23 | *(prior verdicts: 2–5 per round, no convergence)* |
| R24 | *(prior verdict)* |
| **R25 (me)** | **10** — but the composition changed materially |

**This is the first round in the series where every graded guard reds for the reason it names.** Ten reversions, ten single-test reds, zero bystanders. The delta's core arithmetic (68/9/59, 4 moved, 0 newly silent) reproduced exactly under my own instrument. That is real convergence on the *membrane*.

It has **not** converged on the *instruments*, and the reason is structural rather than accidental: three of my ten findings (F1, F3, F9) are holes in tools the builder wrote and measured with themselves, exactly as the delta's own "what this does NOT establish" section predicted. **A round is still finding a new hole per instrument.**

Two of the remaining findings (F2, F7) are of a kind this run has not produced before: **things measurable today that no board row names.** F2 in particular was one command from the measurement that justified `ID_MAX_LEN`, over the same corpus, and would have been found by asking *"what does this regex do to the real data"* instead of *"is the length bounded"*. That is a **scope** failure rather than an execution failure — a better sign than the pair-fixed-at-one-end failures, and a different one.

**Recommendation:** CP-1 does not close on this delta. F1 is a two-line narrowing (`used |= set of module-level __all__ elements`, not every token of every string) with a known-wrong naive form I already executed. F3 is a one-line digest fix (blank `FormattedValue` sub-expressions too, or unparse `JoinedStr` to a placeholder). **F2 is not a CP-1 fix — it is a CP-4 blocker that should be on the board today**, because the decision (rename 9 persisted workflow ids, or widen the alphabet) is a design decision with a migration attached, and discovering it at CP-4 means discovering it inside the admission of the first workflow.

---

## 15 · My prediction for R26 — settleable by one command each

**P1 — the gate will not be narrowed correctly.** I predict the repair for F1, if any, will not scope the string-literal term to `__all__`. On the next round's tree:

```
python -c "import pathlib;s=pathlib.Path('services/chat-service/tests/test_cp1_membrane.py').read_text('utf-8');b=s.split('AN_IMPORT_IS_A_CLAIM')[1][:2500];print('NARROWED' if '__all__' in b else 'STILL BLANKET')"
```

**I predict it prints `STILL BLANKET`.** If it prints `NARROWED`, I was wrong and F1 is closed. *(Stated because the naive repair — deleting the term — reds 30 re-exports, which makes the wrong repair the tempting one.)*

**P2 — F2 will still be open, and the number is 9 of 9.** On the next round's tree, from `services/chat-service`:

```
python -c "import sys;sys.path.insert(0,'.');from app.agentruntime.contract import _ID;from app.services.intent_workflows import _COMPILED;print(sum(1 for w,_ in _COMPILED if not _ID.match(w)),'of',len(_COMPILED))"
```

**I predict it prints `9 of 9`.**

---

## 16 · Executed vs argued

| | count |
|---|---|
| **Executed** claims (a command was run and its output is quoted or tabulated above) | **23** |
| **Argued** claims (reasoned, not executed) | **3** |
| ratio | **23 / 26 = 88 % executed** |

The three argued claims, named so they can be attacked:

1. That `R2h` and `R4a`/`R4b` fire on the *specific* assertion I attribute them to. Established **by elimination** (each mutation touches exactly one code path, and the other assertions are provably unaffected), not by capturing the assertion index. A `-vv` capture would settle it.
2. That F9's false-positive class is unreachable today. I verified no side-effect-only import exists; that it is a *plausible CP-2 pattern* is judgement.
3. That F2's consequence at CP-4 is "the workflow kind cannot be admitted". The measurement (9/9 fail `_ID`) is executed; that CP-4 will use these exact ids rather than renamed ones is inferred from the suite's own fixture, which reads them from the live registry and calls them the legacy workflow declarations.

**Nothing in this verdict rests on a claim I did not run**, except where the sentence says so.

## 17 · What I could not determine

* Whether the shipped **whole** census (68 sites, ≈20 min) reproduces green end to end. I ran a **13-row targeted subset** with a stronger instrument instead, chosen because it answers *which test reds* — which the whole run cannot. The 55 rows I did not neuter are RED per the builder and I did not check them.
* Verifier A's half (the 8 cells, the 17 CI shapes, W4, the weak oracles, T11d, the probe writers). Out of my scope by assignment.
* Whether the digest churn in F3 has affected any **earlier** round's "NOW GUARDED" line. I checked the two most recent commits touching the allowlist; the pattern (an f-string interpolating a `Name`) could have moved rows before and I did not sweep the history.
