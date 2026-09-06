> **Provenance note, added on re-emission.** The original of this file was written to
> `…\scratchpad\r26-b\docs\specs\2026-08-03-agent-runtime-unification\verification\CP-1-round26-v-code-b.md`
> and was destroyed when that worktree was removed. The coordinator asked for it to be re-emitted here.
> **The body below is verbatim from the original — no section is a reconstruction, nothing was
> re-graded, and no measurement was re-run for this re-emission.** The two probe paths, the two HEAD
> hashes and every number are as measured at the time. The only text not in the original is this note.

# CP-1 · round 26 · V-CODE **Verifier B** — the membrane

| | |
|---|---|
| **Worktree** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\r26-b` |
| **Scratch directory** | `C:\Users\NeneScarlet\AppData\Local\Temp\claude\d--Works-source-lore-weave\f169eff6-bff5-4d6e-9ab7-c5df09bea346\scratchpad\scratch-b` |
| **`git rev-parse HEAD` at start** | `55871f6f3ba1e881bd704e5caf6dd30dd4a1820a` |
| **`git rev-parse HEAD` at finish** | `55871f6f3ba1e881bd704e5caf6dd30dd4a1820a` |
| **`git status --porcelain` at finish** | *(empty, before this file was written)* |
| **Byte integrity** | 7 subject files compared **as bytes** against `git show HEAD:<path>` — all `BYTE-IDENTICAL`. Not `read_text()`. |
| **Line endings** | Checked **per file**, not assumed: `contract.py` 0 CRLF / 496 LF · `manifest.py` 0/450 · `surface.py` 0/735 · `canon.py` 0/109 · `test_cp1_membrane.py` 0/3626. **All LF**, as in R25. |
| **Baseline** | `tests/test_cp1_membrane.py` → **152 passed** · `agentruntime-membrane-gate.py` → **OK, 8 modules, 0 external imports** |
| **Isolation** | Every mutation ran in a **throwaway byte-exact mirror** under `scratch-b/mirrors/`, built from `git ls-files`, written with `write_bytes`, asserted with `read_bytes() == b`. **Nothing was written outside `scratch-b` or this file.** No file was observed changing under me. |
| **Census** | **NOT** run whole (~25 min). I re-drove the **7 allowlisted SILENT rows** individually with my own neuterings and my own drivers, and re-derived the raise-site sets across both commits with my own AST walk. Stated deliberately; the 61 RED rows are the builder's number and I did not check them. |

## VERDICT: **FAIL**

Six of the seven graded items moved genuinely and measurably. **My own two R25 predictions were both falsified** — P1 printed `NARROWED`, P2 printed `0 of 9` — and I record that first because it is the strongest evidence in this verdict that the delta did real work.

The FAIL is driven by two findings, and the first is decisive on its own:

1. **F7's guard is satisfied by a different clause than the one it names.** `test_EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS` claims 6 defects × 6 doors = 0 of 36 SERVED. Its sixth door column is green because the **declaration-loss guard** fires on every cell, not because any document check runs. Change one identifier so the loss guard cannot fire and **5 of 5 cells SERVE**. `build(previous=)` runs **no document check at all** — 10 of my 13 document defects pass it — and it is the door that *manufactures* §6.4's origin stamps. The finding F7 closed is still open at the one door where provenance is created rather than read. **Fifth "a control satisfied by the wrong clause" in this run, committed inside the repair for the finding it closes, in the same delta that names that exact failure class two paragraphs earlier.**
2. **B2's registry gate reads two of the three registries.** The tool branch is guarded by `if snapshot.exists()` on a path that **does not exist in this repository**. 315 of 334 ids — 94.3% of the corpus, and the entire kind whose max length 38 is the number `ID_MAX_LEN`'s justification cites — are silently absent, and the gate's own anti-vacuity assertion (`>= 15`) passes at 19. I proved by a four-state experiment that the branch is **unwired, not broken**. Consequently B3's headline sentence — *"the constant is asserted against the measurement that justifies it"* — is **false**: the measurement that runs sees 19 ids, longest 19.

---

## 1 · The falsifier per claim, and what happened when I ran it

| # | claim | **my falsifier** | executed | result |
|---|---|---|---|---|
| **F7** | `check_document` is one definition for six doors; 24/24 → 0/36 | *"find a door that takes a manifest DOCUMENT and does not call `check_document`; or find a cell in the guard's own matrix that is green for another reason"* | 13 document defects × 7 doors = **91 cells**; then the guard's own `build` column re-driven in two states | **BOTH.** `build(previous=)` serves **10 of 13**; the guard's `build` column is **loss-gated** (§2) |
| **B2** | `-` admitted; a gate runs `_ID` over the three live registries | *"count the ids the gate actually sees; move a registry and see whether the vacuity assertion notices"* | corpus re-derived; 4-state wiring experiment | **19 of 334 seen.** Threshold 15 passes at 19 (§3) |
| **B1** | the string term narrowed to `__all__`; `Load`, scope-aware shadowing, `rglob`, duplicates | *"re-run my 11 dead shapes; then enumerate the LIVE shapes the narrowing now reds on"* | 24 shapes, 22 executed + rglob executed separately | dead **10/11** (was 3/11) ✅ · live **4/11 clean**, **7 false positives** (§5) |
| **B3** | vehicles are literals; the constant is asserted against the measurement | *"neuter `== 64` and sweep — if the literals alone pin it, the assert is redundant; and check that the measurement is measured"* | 3 mirrors + §3 | R25's F4 **CLOSED** ✅; the assert is **redundant**; the *measurement* is **not measured** (§4) |
| **B4** | both `check_contract` pins exact-typed; id bound at `AllowList`/`DenyList`/`Filter`-on-`id`; field-name doors deliberately open | *"the stated harm is unmatchability, not id-ness — enumerate every operand door and drive `not_in`"* | 13 doors + `discover(kind=)` | id half **5/5 ✅**; **5 further `not_in` doors remove NOTHING and register NOTHING** (§6) |
| **B5** | `except` clauses deleted; a guard asserts `check_row`'s raise **closure** | *"make `check_row` raise a second class with the suite green"* | 4 injections, each with a behavioural drive | **4 of 4 defeats, 152 passed each time** (§7) |
| **7 SILENT** | the 7 carry my R25 classification; same sites, new ids | *"re-derive the sites myself; neuter each and drive it"* | 7 neuterings + drives; git-diff; AST re-derivation | **6 of 7 classifications reproduce.** Sites confirmed. **One annotation — mine — is measurably false** (§8) |

---

## 2 · F7 — the guard's sixth column, and the door nobody consolidated

### 2a · My 91-cell matrix (13 document defects × 7 doors)

```
                                 rows_of  declarations  discover  SurfaceAssembler  validate_document  build(previous=)  load(path=)
manifest_version MISSING            UR         UR          UR           UR                 UR             *SERVED*          UR
manifest_version 999                UR         UR          UR           UR                 UR             *SERVED*          UR
manifest_version '1' (str)          UR         UR          UR           UR                 UR             *SERVED*          UR
manifest_version True (bool)     *SERVED*   *SERVED*    *SERVED*     *SERVED*           *SERVED*          *SERVED*       *SERVED*
contract_version 'banana'           UR         UR          UR           UR                 UR             *SERVED*          UR
contract_version MISSING            UR         UR          UR           UR                 UR             *SERVED*          UR
contract_version None               UR         UR          UR           UR                 UR             *SERVED*          UR
contract_version 1.0 (float)        UR         UR          UR           UR                 UR             *SERVED*          UR
contract_version str-subclass       UR         UR          UR           UR                 UR             *SERVED*        n/a¹
unknown top-level key 'lane'        UR         UR          UR           UR                 UR             *SERVED*          UR
declarations MISSING                UR         UR          UR           UR                 UR                UR             UR
doc is a LIST                       UR         UR          UR           UR                 UR                UR             UR
doc is a dict SUBCLASS              UR         UR          UR           UR                 UR                UR           n/a¹
```
¹ JSON round-trip normalises the subclass, so the cell is not applicable rather than a hole.

**The five READ doors are genuinely fixed** — 12 of 13 defects refused at all five, which is the F7 claim and it holds. **`build(previous=)` is the seventh door and it runs no document check**, 10 of 13.

### 2b · The harm, driven

```
build([admit(book_list)], previous={"manifest_version": 999,
                                    "contract_version": "banana",
                                    "lane": "legacy",
                                    "declarations": [{... "contract_version": "0.0.1" ...}]})
  -> ACCEPTED, and emits:
     {"manifest_version": 1, "contract_version": "1.0.0",
      "declarations": [{... "contract_version": "0.0.1", "admitted_against": "1.0.0" ...}]}

the SAME document at the read doors:
     rows_of           REFUSED  UntrustedRow: manifest carries ['lane'], which the format does not define
     validate_document REFUSED  UntrustedRow: manifest carries ['lane'], which the format does not define
```

`previous` is where `origin[r["id"]] = r["contract_version"]` comes from. §6.4's re-admission queue is derived by comparing every row against `contract_version`. **The provenance the whole checkpoint is built on is harvested, at this one door, out of a document the reader cannot make claims about — and re-emitted stamped `manifest_version: 1`.** `rows_of`'s own docstring names this exact harm: *"a row read out of a document this reader cannot make claims about is a row with no provenance."*

### 2c · Why the guard is green — the fifth wrong-clause control

The guard's door is `lambda d: build([admit(_tool("book_get"))], previous=d)` while `good = build([admit(_tool("book_list"))], previous=None)`. `admitted` and `previous` name **different declarations**, so `lost = set(origin) - {r["id"] for r in rows}` is non-empty and the **declaration-loss guard** raises `UntrustedRow` before anything document-shaped is looked at.

```
THE TEST'S OWN DOOR  -> build([book_GET], previous=d)
   manifest_version missing     refused: ['book_list'] are in the previous manifest and not in this build...
   manifest_version 999         refused: ['book_list'] are in the previous manifest and not in this build...
   contract_version missing     refused: ['book_list'] ...
   contract_version banana      refused: ['book_list'] ...
   an undefined top-level key   refused: ['book_list'] ...

SAME DOOR, admitted == previous (the loss guard cannot fire):
   manifest_version missing     *** SERVED ***
   manifest_version 999         *** SERVED ***
   contract_version missing     *** SERVED ***
   contract_version banana      *** SERVED ***
   an undefined top-level key   *** SERVED ***
```

**One identifier separates a guard that binds nothing from a guard that reds on 5 of 5 cells.** The delta's own §"reversion prover" section names this class — *"a control satisfied by a different clause than the one it names (A6's dead-token vehicle was being caught by the literal clause)"* — and then ships it in the flagship fix of the same delta. The published ratio 0/36 is really **0/30 genuine + 6 cells decided elsewhere**.

### 2d · The level ABOVE it — asked for, and here it is, with the part that is *not* a finding

Two candidates. Only one is a defect:

* **`build(previous=)` (above)** — a document door on the WRITE side, with its own three hand-written clauses (`type(previous) is dict`, `"declarations" in previous`, `type(_prev_rows) is list`) where the read side has four. **This is the F7 shape exactly, and it is open.**
* **Three hand-written document CONSTRUCTORS and a fourth key-set literal in the validator** — `build`'s return (`manifest.py:281`), `_empty()` (`:338`), `validate_document`'s return (`:426`), and `check_document`'s `{"manifest_version","contract_version","declarations"}` (`contract.py:384`). At the ROW level this repository has `ROW_FIELDS` as data plus `test_THE_REQUIRED_SET_IS_WHAT_THE_WRITER_ACTUALLY_EMITS` as a drift gate. **At the DOCUMENT level there is one validator and no `ROW_FIELDS` equivalent.** — *But I executed the drift and it is caught*: a 4th key in `build`'s literal reds **24 tests**, in `_empty()` **4 tests**, a wrong `manifest_version` **24 tests**, and widening the validator's key set **1 test**. The writers are held by round-trip rather than by a shared definition. **Structural concern, not a defect. Recorded so it is not re-found as one.**

**Reachability of 2a–2c:** `build` is in `__all__`. Through `generate()` it is unreachable (`previous=load(...)`, which validates). Through the exported `build()` it is reachable **in plain JSON, with no adversary** — the identical reachability class as the original F7 finding, which this board judged in scope for CP-1.

---

## 3 · B2 — the alphabet is right and the gate that proves it reads 19 of 334 ids

### 3a · The probe I was asked to run

```
$ python -c "...from app.agentruntime.contract import _ID; from app.services.intent_workflows import _COMPILED; ..."
0 of 9
```

**P2 falsified. `-` is admitted and every workflow id now passes.** I re-derived the full corpus myself: **334 ids, 0 refused, longest 38** (`tool` 315 / max 38, `skill` 10 / max 11, `workflow` 9 / max 19). The alphabet decision and its migration argument are **sound and correct**.

### 3b · The gate that is supposed to keep it sound

```
gate looks for: <repo>\services\chat-service\tests\fixtures\tools-list.snapshot.json
exists -> False                                    <-- the tool branch never runs
real file at :  <repo>\contracts\agent-runtime-baseline\tools-list.snapshot.json   True

CORPUS THE GATE ACTUALLY RUNS OVER: {'workflow': 9, 'skill': 10}  total 19
vacuity guard  n >= 15 -> True   (PASSES)
longest        = (19, 'autonomous-drafting')
tool ids that EXIST but are NOT in the corpus: 315   max len 38
```

The docstring says *"the property is stated over the **real registries**"*; the delta says *"a gate that runs `_ID` over **the three live registries**"*. It runs over **two**. And the anti-vacuity assertion — written into this delta precisely to stop *"a registry moved and this gate would pass over nothing"* — is **calibrated below the collapse that has already happened**: 19 ≥ 15.

### 3c · Unwired, not broken — four states, executed

| state | result |
|---|---|
| as shipped (tool branch dead, 19 ids) | **1 passed** |
| tool snapshot copied to the path the gate reads (334 ids) | **1 passed** |
| wired + one tool id `_ID` refuses (`Book_List_V2`) | **1 failed** ✅ the branch works |
| **unwired + the same bad tool id in the REAL snapshot** | **1 passed** ❌ invisible |

The logic is correct. The path is wrong. **The gate's conclusion is currently true and the gate does not establish it for 94.3% of its stated corpus** — the fifth "a test satisfied by something other than the property" in this run, and the third of those to be committed inside the repair for the finding it closes.

**Reachability: TODAY, in the instrument.** Not a production defect. It is the *only* mechanism standing between CP-4 and a repeat of the exact failure B2 exists to prevent.

### 3d · What else does admitting `-` let in?

Enumerated, and the answer is **very little, and none of it harmful**: `a-`, `a---b`, and `-` adjacent to `_`. An id still cannot start with `-`. The one substantive consequence is **confusables**: `entity-triage` and `entity_triage` are now two admissible, distinct, duplicate-check-passing ids that a human reads as the same declaration. Nothing in the package normalises `-`↔`_`. **LOW; recorded, not charged.** The migration argument (`-` is safe as a dict key, an allow-list member, a sort key and prompt text) is correct — I checked each of those four uses.

---

## 4 · B3 — `ID_MAX_LEN == 64`: the right guard, the wrong sentence

**R25's F4 is CLOSED.** Sweeping the constant with the whole suite:

| `ID_MAX_LEN` | 63 | **64** | 100 | 1 000 000 |
|---|---|---|---|---|
| suite, `== 64` intact | — | **green** | — | **3 failed** |
| suite, `== 64` **neutered to `>= 0`** | **1 failed** | green | **1 failed** | — |

The guarded interval was `[≈20, ∞)`; it is now exactly `{64}`. **And the literal vehicles pin it on their own**: with `assert ID_MAX_LEN == 64` neutered, both 63 and 100 still red on the same test, because `"a"*64` must pass and `"a"*65` must fail. So the assertion is **redundant, not brittle** — it adds no red-ability, and the vehicles below it are the real guard. Answering the question as asked: *not* a brittle replacement for a self-derived bound; a correct guard with a decorative line on top.

**But the sentence around it is false.** *"the constant is asserted against the measurement that justifies it (334 real ids, longest 38, none over 64)"*. That measurement lives in `test_THE_ALPHABET_ADMITS_EVERY_ID_…`'s `longest[0] <= ID_MAX_LEN`, and §3 shows it evaluates over **19 ids, longest 19** — 3.4× short of the evidence quoted. The number 64 is defensible (I re-derived 334/38/0 myself, in §3a). **The claim that a running test defends it is not.**

---

## 5 · B1 — the narrowing works, and it traded 8 false negatives for 7 false positives

**P1 falsified: the probe prints `NARROWED`.** The prescription was taken. My 11 R25 shapes, re-run, plus 13 more:

| # | shape | R25 | **R26** |
|---|---|---|---|
| 1 | bare dead import *(control)* | CAUGHT | CAUGHT |
| 2 | bare word in the **docstring** | **MISSED** | **CAUGHT** ✅ |
| 3 | name in backticks in a docstring | CAUGHT | CAUGHT |
| 4 | shadowed by an unrelated **attribute** (`c.re`) | **MISSED** | **CAUGHT** ✅ |
| 5 | reused as a **local** | **MISSED** | **CAUGHT** ✅ |
| 6 | dead `__`-prefixed alias | **MISSED** | **CAUGHT** ✅ |
| 7 | **second** import of a doubled name | **MISSED** | **CAUGHT** ✅ |
| 8 | shadowed by a later **module-level assignment** | **MISSED** | **MISSED** ❌ |
| 9 | name in an unrelated message string | **MISSED** | **CAUGHT** ✅ |
| 10 | name only in a **comment** | CAUGHT | CAUGHT |
| 11 | dead import in a **sub-package** | **MISSED** | **CAUGHT** ✅ *(executed via `rglob` over a real temp sub-package)* |

**Dead-import shapes: 10 of 11 (91%), was 3 of 11 (27%).** That is a real and large improvement and it is the best-executed fix in this delta.

The cost, which the delta does not count:

| live-code shape | gate |
|---|---|
| side-effect-only dotted import | silent ✅ |
| re-export through `__all__` | silent ✅ |
| used only in a nested function | silent ✅ |
| comprehension variable of the same name | silent ✅ |
| **used only in a string annotation** | **RED** ❌ — *and this was clean in R25; the narrowing is a **regression** here* |
| **`__all__ += [...]` (AugAssign)** | **RED** ❌ |
| **`__all__.extend([...])`** | **RED** ❌ |
| **`try: import ujson as json / except ImportError: import json`** | **RED** ❌ — the duplicate-import clause, new this round, on the most common legitimate double-import idiom in Python |
| **platform-conditional double import** | **RED** ❌ |
| **`if TYPE_CHECKING: import re` + string annotation** | **RED** ❌ |
| **a genuine outer use in a function that has a NESTED param of the same name** | **RED** ❌ — `_binds_locally` uses `ast.walk(fn)`, which descends into nested functions, so the "scope-aware shadowing" is scope-*unaware* in the inward direction |

**My denominator: 10/11 dead caught · 4/11 live-code shapes clean · 7 false-positive shapes.** `MUST_NOT_CATCH` carries **3** entries and covers 3 of my 11. The delta publishes the catch improvement and no false-positive count.

**Reachability: none fire today** — `app/agentruntime/` is 8 flat stdlib-only modules with no `TYPE_CHECKING`, no conditional import and a plain `__all__` assignment. *(Argued: I inspected rather than exhaustively executed this.)* The first CP-2 module with a `TYPE_CHECKING` import reds a gate on correct code, and the tempting repair is to loosen the term that was just narrowed.

**Red-ability, with the defect actually restored:** I reverted the string term to the real blanket — `for el in ast.walk(tree): used.update(el.value.split())`, **`.split()` included**, because the delta records that one of its own reversions omitted it. First I confirmed the reversion **restores the defect** (`_dead_imports('"""…re…"""\nimport re\n') == []` → `True`), *then* ran the suite: **1 failed**, `test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON`. **The `MUST_CATCH` control is real.**

---

## 6 · B4 — the id half is closed; the harm it names is not

The 5 id-comparand doors are bounded, both `check_contract` pins are `type(x) is str`, and the hyphenated spelling still constructs at every door. **That half is clean and independently red-able (§9).**

The stated harm is *"under `not_in` an unmatchable operand removes **nothing** and registers **nothing**, which is the silent deny-list this package exists to make impossible, arriving through a typo instead of through a rule."* **That harm is a property of unmatchability, not of the `id` field.** Executed over a 2-row surface:

| comparand door | constructs? | kept | records |
|---|---|---|---|
| `AllowList.names` / `DenyList.names` (300 chars) | refused ✅ | — | — |
| `Filter(field="id", op=eq/in/not_in)` (300 chars) | refused ✅ | — | — |
| **`Filter(field="lifecycle", op="not_in", value=("admited",))`** | YES | **both rows** | **0** ❌ |
| **`Filter(field="kind", op="not_in", value=("toool",))`** | YES | **both rows** | **0** ❌ |
| **`Filter(field="members", op="not_in", value=("a"*300,))`** | YES | **both rows** | **0** ❌ |
| **`Filter(field="owning_service", op="not_in", …)`** | YES | **both rows** | **0** ❌ |
| **`Filter(field="contract_version", op="not_in", value=("banana",))`** | YES | **both rows** | **0** ❌ |
| `Filter.field` = an undefined field name | YES | `()` | 2 — **loud** ✅ |
| `OrderBy` key field = undefined | YES | `ValueError` ✅ | — |
| `TakeWhileBudget.cost_field` = undefined | YES | `ValueError` ✅ | — |
| `discover(kind="a"*300)` | YES | 0 of 2 | 2 — **loud** ✅ |

**Five further doors exhibit the exact stated harm, verbatim: removes nothing, registers nothing.** A typo in a deny-list on `lifecycle` is a silent no-op today.

### Grading the DECISION, not the code

The written reason is: *"the field-name doors are deliberately NOT bounded — `OrderBy`'s field and `TakeWhileBudget.cost_field` name a ROW FIELD, not an id, and bounding them to `ROW_FIELDS` is a different claim whose answer changes at CP-2 (which adds `relevance`)."*

**For the three field-NAME doors that reason is correct and I would not change it.** Bounding them to `ROW_FIELDS` today makes CP-2's `relevance` a breaking change at the stage layer, for a failure that is already **loud** (`Filter.field` narrows to zero *with* 2 records; the other two raise). Honestly stated, correctly scoped, and the right call.

**The problem is that the sentence's scope conceals a second omission.** The five rows above are **operand** doors, not field-name doors. The stated reason does not cover them and no other sentence does. And two of them — `lifecycle` and `kind` — have **closed vocabularies already declared in `contract.py` as `LIFECYCLES` and `KINDS` frozensets**, which the code comment cites *as the reason not to bound them*:

> *"Only `field == "id"` — the other fields are not ids and bounding them to `_ID` would be a different claim. `lifecycle` and `kind` have their own closed vocabularies at the row."*

That is backwards. A closed vocabulary **at the row** is exactly what makes the **comparand** checkable at construction, and the id door was fixed at CP-1 on the argument that *"the parameter is in the tree today and the vehicle is a config read that returned the wrong string."* The identical argument applies, the vocabulary is already imported-adjacent, and it was not done. **Twin fixed at one end — the thirteenth instance.** Reachability **CP-2** (a configured pipeline), the same as the half that *was* fixed.

---

## 7 · B5 — can I make `check_row` raise a second class without the guard noticing? **Four ways.**

The guard records a class only from `ast.Raise` whose `.exc` is a **`Call`**, and recurses only into callees spelled as a **bare `Name` defined in `contract.py`**.

| # | injection into `check_row` | suite | closure guard |
|---|---|---|---|
| **B5a** | `raise UntrustedRow` — a bare class, no parentheses | **152 passed** | blind: `.exc` is a `Name` |
| **B5b** | `_e = UntrustedRow(...)` then `raise _e` | **152 passed** | blind: `.exc` is a `Name` |
| **B5c** | `_RAISERS["x"](row["id"])` — a raise behind a non-`Name` callee | **152 passed** | blind: `n.func.id` is `None` |
| **B5d** | `canon.digest(object())` — a raise from **another module** | **152 passed** | blind: the walker parses only `contract.py` |

Each verified **behaviourally**, not just structurally:

```
B5a:  check_row now raises UntrustedRow (a SECOND class)
        validate_document -> UntrustedRow  | the deleted `except UntrustedRow` would have caught this
        rows_of           -> UntrustedRow  | the deleted `except UntrustedRow` would have caught this
B5d:  check_row raises NotCanonicalisable  - from ANOTHER module the closure walker never parses
```

B5d is the strongest, because it is **the state `contract.py` was actually in for seven rounds** — `check_row` calling `canon.*`. The guard's stated purpose is *"widening `check_row` to raise a second class fails here — where the answer is 'then the handler comes back, deliberately'"*. It does not. The consequence is real: the deleted handlers converted a flat refusal into a C-12 refusal carrying `.declaration_id` / `.field_path` / `.accepted`, and that structure is what silently disappears.

**The behavioural half of the same test is sound** — 12 overlay + 6 whole shapes, all `ContractViolation`, and it is a good test. It is the **AST closure** half, which is the half the delta chose over asserting the deletion, that binds four fewer shapes than it claims.

**Reachability: no such raise exists today** — the deletions are correct on the current source, verified by both halves. The guard is what was supposed to keep that true.

---

## 8 · The seven SILENT rows — sites confirmed, classification re-driven, one annotation false

**Same sites, new ids — verified, not accepted.** `canon.py` is **byte-identical** between `HEAD~1` and `HEAD` (`git diff --stat` empty), and all three of its allowlist digests moved (`be8fd1f7→417da3eb`, `795ce436→94328cec`, `1598291a→15c0d4e9`). Since the file did not change, the churn is **provably the instrument** (the `JoinedStr` blanking), not the site. For `manifest.py` I re-derived the raise sets across both commits: `validate_document` went from 7 `UntrustedRow` raise-call sites to **1** — the document check moved to `check_document` — so `::5 → ::1` is a re-ordinalisation of the surviving `declarations` check, which my drive below confirms behaviourally. **6 of 7 ids changed; `surface.py::TakeWhileBudget::ValueError::1::3130a968` is unchanged.** The delta's account of the churn is correct.

All seven re-driven with my own neuterings and drivers:

| row | recorded | **my re-drive** | verdict |
|---|---|---|---|
| `canon::_norm::NC::1` (float) | SIBLING | neutered → suite green; `digest(1.5)` still refused, by `::4`'s fall-through with a different message | ✅ holds |
| `canon::_norm::NC::2` (non-`str` key) | UNCHECKED, *"the digest depends on insertion order"* | neutered → suite green; `digest({1:"a",2:"b"})` = `digest({2:"b",1:"a"})` = `2fd78ca852fd` | **UNCHECKED holds; the REASON is FALSE** ❌ |
| `canon::_norm::NC::4` (fall-through) | UNCHECKED | neutered → suite green; `digest(object())` returns a digest | ✅ holds |
| `manifest::generate::UR::1` (no location) | UNCHECKED | faithful neuter (`and False`) → suite **green**; `manifest_path()` → `None`, `generate()` → **`AttributeError`**, a documented refusal becoming a crash | ✅ holds, **+ an unrecorded residual** |
| `manifest::generate::UR::2` (race) | UNREACHABLE deterministically | neutered → suite green; needs a concurrent `unlink` | ✅ holds |
| `manifest::validate_document::UR::1` | SIBLING (partial) | neutered → suite green; `"nope"`→`ContractViolation`, `{"a":1}`→`ContractViolation`, **`None`→`TypeError`, `5`→`TypeError`** | ✅ holds, residual reproduced exactly |
| `surface::TakeWhileBudget::VE::1` | UNCHECKED | neutered → suite green; `budget=-1` **constructs**; driven with a preceding `OrderBy` it is then caught by `_narrow`'s cost-type check, because **no row carries an integer cost field until CP-2/CP-4** | ✅ holds, **harm unreachable today** |

### 8a · The false annotation is **mine**

> `# UNCHECKED — neutered, digest({1: "a"}) returns a digest. A non-string key has no stable
> # ordering across runs, so that digest depends on insertion order and nothing says so.`

I wrote that sentence in `CP-1-round25-v-code-b.md` §9. I did not execute the ordering half. `_norm` passes non-`str` keys through `nfc` unchanged and `canonical_bytes` then calls `json.dumps(..., sort_keys=True)`, which **sorts them** — so the digest is stable and the stated reason is wrong. The builder copied it verbatim into `contracts/agentruntime-census-silent.txt`, a **committed contract file**, under a header that says *"deciding WHY a row is here still needs a person and a verdict id"* and names me as that person.

**A verifier's unexecuted sentence became a committed record.** That is my defect, not the builder's, and it is the exact failure mode this round's standard describes pointed the other way. *(The row's classification — UNCHECKED — is unaffected and correct. The residual is genuinely worse than recorded in a way neither of us measured: mixed-type keys, e.g. `{1:"a","b":2}`, make `sort_keys=True` raise a `TypeError`.)*

### 8b · Should any of the four UNCHECKED have been CLOSED in this delta?

**Yes — three of the four, and each is a one-line test:**

```python
with pytest.raises(NotCanonicalisable): canon.digest({1: "a"})
with pytest.raises(NotCanonicalisable): canon.digest(object())
with pytest.raises(ValueError):         TakeWhileBudget("s", "r", budget=-1)
```

The fourth (`generate::UR::1`) needs an `ambient.module_anchor` monkeypatch — three lines, and the suite already patches `ambient` elsewhere. **In a delta whose own thesis is *"a fix without a red-able test is not a closed finding"*, four refusals were classified rather than closed at a total cost of ~6 lines.** Classification is progress over the previous header; it is not closure, and the allowlist is where rows have gone to sit for six consecutive rounds.

---

## 9 · Red-ability table, with **my own** denominator

Every reversion below was re-derived by me and run in a fresh byte-exact mirror. **Where the reversion could have failed to restore the defect, I proved the defect restored *before* reading the suite result** (B1 — `.split()` included, per the delta's own warning that one of its reversions omitted exactly that).

| # | reversion | suite | failing test(s) |
|---|---|---|---|
| **F7a** | `rows_of` drops `check_document` | **4 failed** | `test_EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS`, `test_the_EXPORTED_row_reader_refuses_a_malformed_document`, `test_a_document_without_declarations_is_refused`, *+ the import gate (now-dead import)* |
| **F7b** | `validate_document` drops `check_document` | **5 failed** | `…_STAMPS`, `test_THE_DOCUMENT_IS_EXACTLY_A_DICT…`, `test_THE_DOCUMENT_SCHEMA_IS_CLOSED_TOO`, `test_the_DOCUMENT_stamps_are_validated…`, *+ the import gate* |
| **F7c** | *(the `build(previous=)` half)* | **no reversion exists** — there is nothing to revert | **§2c** |
| **B1a** | string term re-widened to `.split()` over every literal · **defect confirmed restored first** | **1 failed** | `test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON` |
| **B2a** | `-` removed from the alphabet | **2 failed** | `test_THE_ALPHABET_ADMITS_EVERY_ID…`, `test_A_KEY_IS_BOUNDED_ON_BOTH_SIDES…` |
| **B2b** | *(the tool branch)* | **already in its degraded state, green** | **§3c** |
| **B3a** | `ID_MAX_LEN = 1_000_000` | **3 failed** | `test_ID_MAX_LEN_IS_THE_NUMBER…`, `test_A_KEY_IS_BOUNDED…`, `test_CHECK_ROW_RAISES_EXACTLY_ONE_CLASS` |
| **B3b** | `ID_MAX_LEN = 100`, `== 64` **neutered** | **1 failed** | `test_ID_MAX_LEN_IS_THE_NUMBER…` — **the literals pin it alone** |
| **B3c** | `ID_MAX_LEN = 63`, `== 64` **neutered** | **1 failed** | same |
| **B4a** | `_require_names` drops the `_ID` bound | **1 failed** | `test_A_KEY_IS_BOUNDED_ON_BOTH_SIDES…` |
| **B4b** | `Filter`-on-`id` drops the `_ID` bound | **1 failed** | same — **both halves independently red-able** |
| **B5a–d** | four second-class raises injected into `check_row` | **152 passed ×4** | **none — 0 of 4** |
| **D1** | `build` emits a 4th top-level key | **24 failed** | writer-side drift is caught by round-trip |
| **D2** | `build` emits `manifest_version: 2` | **24 failed** | ″ |
| **D3** | `_empty()` emits a 4th key | **4 failed** | ″ |
| **D4** | `check_document`'s key set gains `lane` | **1 failed** | `test_EVERY_DOOR_READS…` |
| **S1–S7** | the 7 SILENT sites neutered one at a time | **152 passed ×7** | **0 of 7 — SILENT confirmed independently** |

| space | builder's number | **my denominator** | executed |
|---|---|---|---|
| document defects × doors | 6 × 6 = **0 of 36 SERVED** | **18 of 91**, of which 16 real (2 are JSON-normalisation artefacts). **10 of 13 at `build(previous=)`; 1 of 13 at all seven** | ✅ |
| cells in the F7 guard that bind the document check | 36 | **30** — the 6 `build` cells are decided by the loss guard | ✅ |
| ids the B2 registry gate reads | "the three live registries" | **19 of 334 (5.7%)**, 2 kinds of 3 | ✅ |
| corpus collapse the vacuity guard tolerates | *(none stated)* | **94.3%** — threshold 15, actual 19, full 334 | ✅ |
| dead-import shapes caught | *(none published)* | **10 of 11 (91%)**, was 3 of 11 | ✅ |
| live-code shapes the import gate is silent on | 3 (`MUST_NOT_CATCH`) | **4 of 11 — 7 false-positive shapes**, 1 of them a regression | ✅ |
| ways to make `check_row` raise a second class | 0 implied | **4 of 4 attempted, all green** | ✅ |
| id-comparand doors bounded | 5 | **5 of 5** ✅ | ✅ |
| operand doors where `not_in` removes nothing and registers nothing | *(not claimed)* | **5** | ✅ |
| `ID_MAX_LEN` values the suite accepts | implied 64 | **exactly `{64}`** (was `[≈20, ∞)`) ✅ | ✅ |
| real ids over 64 / failing the alphabet | 0 / 0 | **0 of 334 / 0 of 334** ✅ | ✅ |
| SILENT rows still silent alone | 7 | **7 of 7 confirmed** | ✅ |
| SILENT classifications reproducing | 7 | **6 of 7** — one annotation measurably false | ✅ |

---

## 10 · Bypass table — *can the property be defeated with the guard GREEN?*

| # | property | bypass | executed | reachable today |
|---|---|---|---|---|
| F7 | *"one document definition for every door"* | **YES** — `build(previous=)` runs none; 10 of 13 defects pass; origin stamps harvested from a document every read door refuses | ✅ | **exported `build()`, plain JSON.** Not via `generate()` |
| F7 | *"0 of 36 cells"* | **YES** — the 6 `build` cells are green via the declaration-loss guard; one identifier flips them to 5 of 5 SERVED | ✅ | today, in the guard |
| F7 | `check_document`'s own `manifest_version` clause | **YES** — `!=` not `type(x) is`; `manifest_version: true` (or `1.0`, or `1+0j`) passes **all seven doors**, and `validate_document` **launders** it to `1` in its return | ✅ | **today, plain JSON on disk, through `load()`** |
| B2 | *"a gate over the three live registries"* | **YES** — the tool branch never runs; a tool id `_ID` refuses is invisible; the vacuity assertion passes at 19 | ✅ | today, in the instrument |
| B3 | *"asserted against the measurement that justifies it"* | **YES** — the measurement evaluates 19 ids, longest 19, not 334/38 | ✅ | today |
| B4 | *"an unmatchable operand must not silently remove nothing"* | **YES** — 5 `Filter(op="not_in")` doors on non-id fields | ✅ | CP-2 (a configured pipeline) |
| B5 | *"widening `check_row` fails at the closure guard"* | **YES ×4** — bare-class raise, raise of a bound name, non-`Name` callee, cross-module raise | ✅ | today, by an ordinary edit |
| B1 | *"a dead import cannot be hidden"* | **1 shape** — a name rebound by a later module-level assignment | ✅ | today (benign; no such import exists) |
| B1 | *"the gate does not red on correct code"* | **YES ×7** — string annotation, `__all__ +=`, `__all__.extend()`, `try/except ImportError`, platform-conditional, nested-param shadowing, `TYPE_CHECKING` | ✅ | **CP-2**; none fire on today's 8 modules |

---

## 11 · Sibling table — for every fix, is its twin fixed too?

| # | fix landed at | its twin | twin fixed? | executed |
|---|---|---|---|---|
| F7 | `rows_of` + `validate_document` document check | **`build(previous=)`** — the 7th document door | ❌ **NO** (§2) | ✅ |
| F7 | `contract_version` pinned with `type(x) is not str` | **`manifest_version`, six lines above, pinned with `!=`** | ❌ **NO** (§10) — *twin fixed at one end inside one function* | ✅ |
| F7 | the guard's 5 read-door columns | the guard's **`build` column** | ❌ **NO** — green via the loss guard | ✅ |
| B1 | the AST half (`Load`, shadowing, `rglob`, duplicates) | the **false-positive** half | ❌ **NO** — 7 new FP shapes, 1 a regression | ✅ |
| B2 | the alphabet | the **gate's corpus** | ❌ **NO** — 2 registries of 3, 19 ids of 334 | ✅ |
| B3 | the literal vehicles | the **measurement** the docstring cites | ❌ **NO** — the measurement runs over 19 | ✅ |
| B4 | `check_contract` id pin | `check_contract` member pin | ✅ **YES** | ✅ |
| B4 | `AllowList`/`DenyList` bound | `Filter`-on-`id` bound (eq/in/not_in) | ✅ **YES**, independently red-able (`B4a`/`B4b`) | ✅ |
| B4 | the `id` operand door | **the `lifecycle`/`kind`/`members`/… operand doors**, same stated harm | ❌ **NO** — 5 doors (§6) | ✅ |
| B4 | the field-name doors | *(deliberately open)* | ✅ **decision graded SOUND** (§6) | ✅ |
| B5 | the two deleted `except` clauses | the **closure guard** meant to hold them dead | ❌ **NO** — 4 of 4 defeats | ✅ |
| S | the 3 SILENT rows classified | the 4 UNCHECKED rows **closeable in ~6 lines** | ❌ **NO** — recorded, not closed | ✅ |

**Score: 3 of 12 pairs fixed at both ends.** Every failure is *one level out* from where R25 pointed — the fourteenth time this run has recorded that shape, and this round it appears **inside the two fixes the delta describes as changing an axis rather than a list.**

---

## 12 · Guard table

| guard | binds the property, or the nearest proxy? |
|---|---|
| `test_EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS` | **the property for 5 of 6 doors; VACUOUS for the sixth.** 30 of 36 cells genuine; the `build` column is decided by the declaration-loss guard, and `build` runs no document check at all. Independently red-able at both real halves (`F7a`/`F7b`) |
| `test_THE_ALPHABET_ADMITS_EVERY_ID_THIS_REPOSITORY_ALREADY_DECLARES` | **a proxy over 5.7% of its stated corpus.** The logic is correct and reds when wired; the path is wrong, and the anti-vacuity assertion it ships with passes in the collapsed state |
| `test_ID_MAX_LEN_IS_THE_NUMBER_THE_DOCSTRING_ARGUES_FOR` | **the property.** Literal vehicles pin `ID_MAX_LEN` to exactly `{64}`; R25's F4 is closed. The `== 64` line is redundant with them, not brittle |
| `test_A_KEY_IS_BOUNDED_ON_BOTH_SIDES_OF_THE_COMPARISON` | **the property, for the 5 doors it names**, both halves independently red-able. Scoped to `field == "id"` while the harm it states is unmatchability |
| `test_A_STR_SUBCLASS_KEY_OR_MEMBER_IS_NOT_A_STR` | **the property**, now at all four pins including `check_contract`'s two — the R25 F5 twin, closed |
| `test_AN_IMPORT_IS_A_CLAIM_ABOUT_WHAT_A_MODULE_DEPENDS_ON` | **the property, with a real injection control.** `MUST_CATCH` reds on the restored `.split()` defect. `MUST_NOT_CATCH` is short by 7 |
| `test_CHECK_ROW_RAISES_EXACTLY_ONE_CLASS…` | **two halves, one sound and one not.** The 18 driven shapes bind behaviour and are good. The AST closure — the half chosen *over* asserting the deletion — is blind to 4 of 4 second-class shapes I tried |
| `contracts/agentruntime-census-silent.txt` | **7 of 7 rows confirmed SILENT by my own neuterings.** Sites confirmed across the digest churn (`canon.py` byte-identical, 3 ids moved). One annotation false — **mine** |

---

## 13 · Reachability verdict on every finding

| id | finding | severity | **production-reachable today?** |
|---|---|---|---|
| **B26-F1** | F7's guard is loss-gated at `build(previous=)`; that door runs **no** document check and harvests §6.4's origin stamps from an unreadable document | **HIGH** | **No — zero production importers.** Reachable through the exported `build()` in plain JSON; unreachable through `generate()`. **Measurable today, in one command** — the criterion this board declared |
| **B26-F2** | B2's registry gate reads 2 of 3 registries, 19 of 334 ids; the anti-vacuity assertion passes in the collapsed state | **HIGH** (instrument) | **Live today.** The conclusion is currently true (I measured it); the gate is the only thing standing between CP-4 and a repeat |
| **B26-F3** | B5's closure guard defeated 4 ways, suite green | **MED-HIGH** | No such raise exists today. Reachable by an ordinary edit at any time; B5d is the state the file held for 7 rounds |
| **B26-F4** | `check_document`'s `manifest_version` uses `!=`; `true` / `1.0` pass all 7 doors and are **laundered** to `1` | **MED** | **YES, in the sense that matters** — plain JSON on disk through `load()`. No production caller today |
| **B26-F5** | B4's comparand bound scoped to `id`; 5 `not_in` doors remove nothing and register nothing | **MED** | **No — CP-2** (a configured pipeline), identical to the half that was fixed |
| **B26-F6** | B1 traded 8 false negatives for 7 false-positive shapes; 1 is a regression; 1 dead shape still missed | **MED** | **No** — 0 fire on today's 8 modules. First CP-2 `TYPE_CHECKING` or conditional import reds correct code |
| **B26-F7** | the allowlist's annotation for `canon::_norm::NC::2` is measurably false — and the sentence is **mine**, unexecuted, now in a committed contract file | **LOW-MED** (method) | n/a. The row's classification is unaffected |
| **B26-F8** | 4 UNCHECKED rows recorded rather than closed; 3 are one-line tests | **LOW-MED** | Dead debt. ~6 lines to close all four |
| **B26-F9** | 3 hand-written document constructors + a 4th key-set literal; no document-level `ROW_FIELDS` | **INFO** | **Not a defect** — drift is caught by round-trip (24 / 24 / 4 / 1 tests red). Structural only |
| **B26-F10** | both my R25 predictions falsified (`NARROWED`, `0 of 9`) | **INFO** (method) | n/a. Recorded because it is the delta's best evidence |

---

## 14 · Convergence

| round | this verifier's independent findings | composition |
|---|---|---|
| R25 (me) | 10 | 3 instrument holes · 2 measurable-today-unnamed · 4 twins · 1 method |
| **R26 (me)** | **10** | **2 instrument holes · 1 vacuous guard column · 4 twins · 2 method (one against myself)** |

**The count is flat and the character has changed, in both directions.**

*Better:* every single one of my R25 findings that the delta targeted **moved, measurably, and reds under my own reversion**. Both of my written predictions were falsified. `ID_MAX_LEN`'s guarded interval went from `[≈20, ∞)` to exactly `{64}`. The dead-import gate went from 3 of 11 to 10 of 11 with a real injection control. The alphabet is right and I re-derived its corpus myself: 0 of 334 refused. `check_contract`'s two pins are closed. The 5 id-comparand doors are closed and independently red-able. **This is the largest genuine movement in the six rounds I can compare against.**

*Not better, and structurally so:* **two of the three flagship fixes ship a guard that does not bind what it claims.** F7's matrix has a vacuous column; B2's gate has a dead branch. Both are the delta's own named failure classes — *"a control satisfied by a different clause than the one it names"* and *"a test satisfied by a comment"* — and both were committed **inside the repair for the finding they close**, in a delta whose §"what this does NOT establish" says *"every claim settled by an enumeration I chose has been short, five rounds running."* That prediction was correct about this delta. **Six fixes shipped a new enumeration; two of them are short, and it is the same two that were promoted as changing an axis.**

The one thing that has converged is the **membrane's behaviour**: the five read doors, the row definition, the id bound, the pins, the copy depth. What has not converged is the **relationship between a fix and its guard**, and R26 is the third consecutive round where the fixes are better than the instruments that certify them.

**Recommendation: CP-1 does not close on this delta.** B26-F1 is a one-line call plus a one-identifier change to the guard's fixture. B26-F2 is a path. B26-F3 is three more `isinstance` branches in the closure walker plus a cross-module note. B26-F4 is `type(doc.get("manifest_version")) is not int or … != MANIFEST_VERSION`. None is a design question. **B26-F5 is the only one that is a decision**, and it should be made explicitly rather than inherited from a sentence about field-name doors.

---

## 15 · My prediction for R27 — settleable by one command

**P1 (primary) — the `build(previous=)` door will be fixed and the guard's vacuity will not.** I predict the repair for B26-F1 adds `check_document` to `build()` and leaves the guard driving `admitted != previous`, so the `build` column stays satisfiable by the declaration-loss guard. On the next round's tree, from the repo root:

```
python -c "import pathlib;s=pathlib.Path('services/chat-service/tests/test_cp1_membrane.py').read_text('utf-8');b=s.split('EVERY_DOOR_READS_THE_DOCUMENTS_OWN_STAMPS')[1][:3500];print('LOSS-GUARD-FREE' if 'book_get' not in b else 'STILL LOSS-GATED')"
```

**I predict it prints `STILL LOSS-GATED`.** If it prints `LOSS-GUARD-FREE`, I was wrong and B26-F1 is closed at both ends. *(Stated because the tempting repair is the one at the site I pointed at — `build` — and the guard is the half that made the finding invisible.)*

**P2 (secondary) — the corpus path will be fixed and the vacuity threshold will not be re-derived.** I predict the `>= 15` floor survives, or is replaced by another number below 300, leaving a gate that still cannot see a registry disappearing:

```
python -c "import pathlib,re;s=pathlib.Path('services/chat-service/tests/test_cp1_membrane.py').read_text('utf-8');b=s.split('THE_ALPHABET_ADMITS_EVERY_ID')[1][:3000];m=re.search(r'>=\s*(\d+)',b);print(m.group(1) if m else 'none')"
```

**I predict a number below 300.** The honest floor is `len(corpus['tool']) >= 300` per kind, or an assertion that all three keys are present — not a total.

---

## 16 · Executed vs argued

| | count |
|---|---|
| **Executed** claims (a command was run and its output is quoted or tabulated above) | **28** |
| **Argued** claims (reasoned, not executed) | **4** |
| ratio | **28 / 32 = 88 % executed** |

The four argued claims, named so they can be attacked:

1. That the 7 import-gate false-positive shapes are **unreachable in `app/agentruntime/` today**. I read all 8 modules and found no `TYPE_CHECKING`, no `try/except ImportError`, no conditional import and a plain `__all__` assignment — but I did not run a mechanical check for their absence.
2. That `build(previous=)`'s hole is **unreachable through `generate()`**. Reasoned from `generate` passing `previous=load(path=target)`, which validates; I did not drive `generate` end to end against a poisoned file.
3. That the **field-name-door decision is right for CP-2**. The failure modes are executed (§6); that `relevance` arriving at CP-2 makes a `ROW_FIELDS` bound a breaking change is a judgement about unbuilt code.
4. That my neutering of `canon::_norm::NC::4` (`return repr(value)`) has the **same reachability** as the census's. The row's SILENT status and the fact that a digest is produced are executed; the specific downstream harm depends on the neutering chosen, and mine is my own.

**Nothing else in this verdict rests on a claim I did not run.**

---

## 17 · What I could not determine

* Whether the **whole** shipped census (68 sites, ~25 min) reproduces 7 silent / 61 red end to end. I re-drove the **7 allowlisted rows** individually with a stronger instrument (each reports whether the suite reds and what the neutered code then does), and I re-derived the raise-site sets across both commits. **The 61 RED rows are the builder's number and I did not check them.** Stated deliberately.
* Whether the digest churn has moved rows in **earlier** rounds. I proved it for this commit (`canon.py` byte-identical, 3 ids moved) and did not sweep the history.
* Verifier A's half — A1's whitelist, A2's taint walk, A3/A4/A5/A6/A7, and the allowlist regeneration as a whole. Out of my scope by assignment.
* Whether `manifest_version: true` (**B26-F4**) can reach a consumer that behaves differently for it. It is accepted and laundered to `1`; whether any *future* reader distinguishes formats is not answerable from CP-1's code.
* Whether the two `contract_version` cells I marked `n/a` at `load(path=)` hide a real hole. JSON normalises both a `str` subclass and a `dict` subclass on the way to disk, so the file door cannot express them — but a caller reaching `validate_document` with an in-memory document can, and there both are refused.
