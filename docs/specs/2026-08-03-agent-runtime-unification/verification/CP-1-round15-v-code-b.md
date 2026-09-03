# CP-1 · round 15 · V-CODE · **Verifier B** — the membrane, and the sentence beside the fix

`git rev-parse HEAD` **at start:** `cba800fa81f4a663ae363e9f871a953745ec393b`
`git rev-parse HEAD` **at finish:** `cba800fa81f4a663ae363e9f871a953745ec393b`

No tracked file was modified except this verdict. No `git checkout` was run. Nothing was committed.
`git status --porcelain` over `services/`, `scripts/` and this spec directory is **empty at finish**.

**Method.** Every injection is **source surgery**: the real function's source is read with
`inspect.getsource`, exactly one anchor line per edit is replaced, and the result is `exec`'d with
the module's **live** `__dict__` as its globals — so a later `monkeypatch.setattr(manifest,
"CONTRACT_VERSION", …)` is seen by the injected function exactly as by the original. The new object
is rebound at **every** binding from an out-of-tree pytest plugin at `pytest_configure`, i.e. before
the test module's `from app.agentruntime import …` runs. Four self-checks:

1. the injected function must differ from the original in `co_code` **or** `co_consts` — both are
   printed per run, and a run where neither differs **aborts** with `INJECTION IS A NO-OP`;
2. `new_fn.__globals__ is mod.__dict__` is asserted, so the injected copy cannot silently miss a
   monkeypatched module global;
3. the defining-module binding and the **test module's own binding** are both printed at
   `pytest_collection_finish`, and the run raises `SystemExit` if either did not take;
4. the rebind loop captures the original object **before** it iterates `sys.modules`, because the
   defining module is itself one of the modules being rewritten.

Check 2 and check 4 each caught a false measurement in this session before it reached a table.
Copy-globals made `C2_outer_previous_isinstance` read **1 failed** when it is in truth **113
passed**; the un-captured original made the `generate()` rebind stop after one module. Both are
recorded because a verifier's harness is a measurement instrument and this run has a standard about
instruments that report what they were expected to.

**Every silent (green) injection below was proven to restore a real defect in a standalone
in-process probe first.** A green row whose weakening restores nothing is not a finding; two of my
candidate rows (`D6`, and `D2` in the form I first wrote it) failed that test and are reported as
what they are rather than as findings.

**Baselines I measured myself, at start and at finish:**

| | |
|---|---|
| `python -m pytest tests/test_cp1_membrane.py -q` (from `services/chat-service`) | **113 passed**, 1 warning, ~6 s |
| `python scripts/agentruntime-membrane-gate.py` (repo root) | **exit 0** |

113, the same count as R14: the delta adds assertions and fixtures, no new test function.

**Scope.** R14's delta: `contract.py` +88 (`ROW_FIELDS`, `ROW_REQUIRED`, `check_row_shape`),
`manifest.py` ±17 (`validate_document` calls it; `r["members"]` replaces the defaulted read),
`surface.py` −39/+4 (`rows_of`'s inline bound deleted, replaced by the call),
`test_cp1_membrane.py` ±48.

---

## Verdicts

| # | Claim under test | Verdict |
|---|---|---|
| 1 | *`check_row_shape` is one definition for both doors* | **FAIL — it is one definition of a row's SHAPE, and the two doors still disagree about a row's VALIDITY, in the more dangerous direction.** `rows_of` applies no contract clause, so **nine** classes of row reach the consumer that `load()` refuses: bad `kind`, bad `lifecycle`, an `id` matching no `_ID`, **`id: ""`**, duplicate ids, a skill with `members: []`, a tool *with* members, a row missing **both** §6.4 stamps, and `members: ['ghost']`. All measured, all plain JSON. And there is a **third door**: the writer. `build`/`_row`/`generate` never pass their own output through `check_row_shape`, so a `_row` that gains a field writes a document `load()` and the CI gate then refuse — measured. `build(previous=)` is a fourth, with its own weaker row definition |
| 2 | *the boxed claim: a hand-typed well-typed `cost` is the hand-edited-manifest threat, whose **only** answer is §6.4.2's digest* | **HALF SOUND, HALF FALSE — and the refutation is in the builder's own comment, 25 lines above the code that contradicts it.** The second half is **correct and worth keeping**: no value bound distinguishes a forged `cost` from a real one, and shipping one would be a vacuity failure. The first half is false. A cheaper mechanism exists, does not weaken §6.1 layer 3 — it *strengthens* it — and **the round built it and then exempted the four fields the threat rides on**. `contract.py:109-112` says `lane`/`tier`/`cost`/`relevance` "are therefore **refused today on purpose** … a door that accepted them would be letting an unbuilt capability in through the back." `contract.py:135-138` accepts all four. Measured: removing those four entries costs **nothing** — `build`, `rows_of`, `validate_document` and the committed manifest all still pass — and the hand-typed `cost` is then **REFUSED**. Second mechanism, the package's own C-0 precedent: **derive, never author**. Full grading in §2 |
| 3 | *`members` is required* | **PASS on the named class, and two survivors.** Measured: absent / `null` / `0` / `false` are now **refused at both doors** — R14 §3 is genuinely **CLOSED**. Survivors: `manifest.py:415` still reads `r.get("members", ()) or ()` (now dead, still readable, still contradicting the rule 44 lines below it), and a **skill carrying `members: []`** is served to all four consumer doors as a declaration referencing nothing, because `rows_of` runs no contract clause. **And the fix is unguarded** — deleting the required check leaves the suite at 113 and turns two exported doors into an uncaught `KeyError` |
| 4 | *the 5th/6th TOCTOUs and the `r.get("id")`/`r["id"]` split* | **Re-measured. Two NARROWED to closed, two UNCHANGED — and this is the round's real, unadvertised win.** The **6th** (`dict(r)`, `manifest.py:472`) is **CLOSED**: `check_row_shape`'s `type(row) is not dict` refuses the subclass. `validate_document`'s **`id` split** is **CLOSED** for the same reason — a plain `dict` has one storage. The **5th** (`{**doc}`) is **OPEN, unchanged** — validated `manifest_version=1`/`contract_version='1.0.0'`, returned `999`/`'banana'`. `build`'s **`id` split** is **OPEN, unchanged** — `build` is the one row-reader the delta did not reach. Both closures are **incidental and untested**: weakening one line restores the 6th end-to-end with the suite green |
| 5 | *the P4 test on a `generate()`-landing mechanism* | **CONFIRMED OPEN, fourth consecutive round.** I built §6.4's mechanism inside `generate()`, proved it real on disk before running the suite (2 rows, `QUEUE=['book_get']`, drains to `[]`, `validate_document` OK, `load()` OK) and ran the suite with `[G] test module tests.test_cp1_membrane.generate is-injected=True` printed: **113 passed** |
| 6 | *convergence, and: trend or single point?* | **SINGLE POINT, and the round's own delta is the evidence.** R14's no-new-TOCTOU result did not repeat: `check_row_shape` reads the **mutable module global `ROW_FIELDS` twice**, two lines apart, check-read then use-read. And findings **introduced by the graded delta rose 2 → 4**, including a **named guard the delta deleted** (`rows_of`'s non-empty-`id` refusal: REFUSED pre-delta, ACCEPTED at HEAD, measured against the R14 artifact's own source in one process). **But the closure rate rose for the first time in the series: ~8% → ~27%.** Full table, method and confounders in §6 |

---

## Falsifiers, stated before the search

| # | What would have made the claim false | How I searched |
|---|---|---|
| 1 | Every exported path to a consumer passing through `check_row_shape`, and no row existing that one door accepts and the other refuses | Enumerated every caller of `rows_of` / `validate_document` / `check_row_shape` mechanically, then drove 15 row shapes through **both** doors in one process and diffed the answers; then asked the same question of the **writer** by giving `_row` a plausible CP-4 field |
| 2 | No mechanism existing that refuses a hand-typed `cost` without weakening re-validation; or removing the four ranking fields from `ROW_FIELDS` breaking a real path | **Executed the counterfactual**: popped the four entries and re-ran `build([admitted])`, `rows_of`, `validate_document` and the committed manifest; then re-read §6.4.2 and §0.14.1c for what the digest actually claims |
| 3 | Absent / `null` / `0` / `false` `members` still reaching a consumer, or no site left that serves an empty `members` as "no members" | Ran all seven `members` shapes through both doors; swept every `.get(k, default)` left in the package; asked the contract-clause question separately from the shape question |
| 4 | A plain-JSON vehicle for either TOCTOU; or the delta failing to narrow either | Built the dict-subclass row and the dict-subclass document, ran both against HEAD, then weakened the single line each closure depends on and re-ran |
| 5 | The P4 test reddening with a faithful `generate()`-landing mechanism | Built it, **proved it real on disk before running the suite**, rebound at every binding with the test module's own binding asserted |
| 6 | The delta introducing no new read-twice site, and `introduced` falling again | Read-twice sweep of every line the delta wrote, including the module globals it introduced; classified this round's findings by the mechanism required to trigger them; ran the R14 open set as probes |

---

## 1 — one definition of a SHAPE, and three doors that still disagree

### 1a · ✅ what genuinely became one definition

Both doors now call `contract.check_row_shape`, and the *shape* answers agree. Measured, both doors,
plain JSON round-tripped through `json.dumps`/`json.loads`:

| row | `rows_of` | `validate_document` / `load` |
|---|---|---|
| undefined key `weight: 999` | REFUSED | REFUSED |
| `cost: 1.5` (float) | REFUSED | REFUSED |
| `lane: {"a": 1}` | REFUSED | REFUSED |
| `members` absent / `null` / `0` / `false` | REFUSED | REFUSED |
| `members: [""]`, `[None]` | REFUSED | REFUSED |
| a `dict` **subclass** row | REFUSED | REFUSED |

That is a real consolidation and it closes R14 §1c and §3. It is the round's best work and it is
stated first.

### 1b · 🔴 the two doors still disagree about VALIDITY, and the weak one faces the consumer

`rows_of` runs `check_row_shape` and **nothing else**. `validate_document` runs `check_row_shape`
**plus** `check_contract`, the stamp syntax check, the duplicate check and M5. So the door that
`SurfaceAssembler`, `discover`, `declarations` and `rows_of` all sit behind is the **weaker** of the
two — and `surface.py:52-54`'s own comment says why that matters: *"`SurfaceAssembler` and
`discover` are both exported and neither went through `load`."* Measured, plain JSON:

| row | `rows_of` | `validate_document` |
|---|---|---|
| `kind: "nonsense"` | **ACCEPTED** | REFUSED |
| `lifecycle: "??"` | **ACCEPTED** | REFUSED |
| `id: "!!! HAND TYPED !!!"` (matches no `_ID`) | **ACCEPTED** | REFUSED |
| **`id: ""`** | **ACCEPTED** | REFUSED |
| duplicate ids | **ACCEPTED** | REFUSED |
| a **skill** with `members: []` | **ACCEPTED** | REFUSED |
| a **tool** *with* members | **ACCEPTED** | REFUSED |
| a row missing **both** §6.4 stamps | **ACCEPTED** | REFUSED |
| `members: ['ghost']` | **ACCEPTED** at all four doors | REFUSED (`UnresolvedReference`) |

R14 §1d was *"`load()` blesses a document every consumer door refuses"* — irritating. This round
inverted it: **the consumer doors now bless rows `load()` refuses.** That is the direction that
leaks. `members: ['ghost']` reaching the wire — the sentence quoted verbatim in R14's graded commit
message — is measured again here at `rows_of`, `declarations`, `discover` and
`SurfaceAssembler(…).assemble()`, third consecutive round. **Production-reachable.**

`ROW_REQUIRED` is the mechanical statement of the gap: it is `{id, kind, owning_service, lifecycle,
members}`, and `validate_document` additionally requires `contract_version` and `admitted_against`.
A row carrying **exactly** `ROW_REQUIRED` passes `rows_of` and fails `load()` — measured.

### 1c · 🔴 **the third door is the WRITER**, and Q1 asks for it by name

`build` / `_row` / `generate` never pass their output through `check_row_shape`. Measured — `_row`
given one plausible CP-4 field (`deprecates`):

```
build() with the extra field        -> ACCEPTED   (and generate() writes it to disk)
validate_document on what it wrote  -> REFUSED[UntrustedRow]
rows_of on what it wrote            -> REFUSED[ContractViolation]
```

The generator is *"the only writer this code has"* (`manifest.py:328-337`) and it is the only row
producer that does not consult the one definition of a row. The failure lands **after** the file is
written — at the next `load()`, or in CI at `agentruntime-membrane-gate.py`. This is precisely the
"discovered late" shape Q2's second half asks about, and it is three characters of code to close:
`check_row_shape(row, "…")` on `_row`'s return. **Production-reachable** — the trigger is an
ordinary refactor, and CP-4 adding a row field is a scheduled one.

### 1d · 🔴 the fourth door: `build(previous=)`

`build` validates `previous`'s rows with its own weaker inline definition (`isinstance(r, dict)`,
`r.get("id")`, `r.get("contract_version")`). Measured — one previous-row carrying an **undefined
key**, a **dict-valued field** and an **int key**:

```
build(previous=…)  -> ACCEPTED
rows_of(the same row) -> REFUSED[ContractViolation]
```

Through `generate()` this is unreachable (`previous` comes from `load()`). Through the **exported**
`build()` it is reachable in plain JSON, and `build`'s docstring says exactly why that matters:
*"`previous` is caller-supplied … A writer that trusts its argument is the write-end of the boundary
`UntrustedRow` describes."* **Production-reachable.**

### 1e · 🔴 the exception type: still two, and one of them is new

```
issubclass(ContractViolation, ValueError)   -> False
issubclass(ContractViolation, UntrustedRow) -> False
rows_of(row with an undefined key) -> ContractViolation
rows_of({}) (no `declarations` list) -> ValueError
```

`rows_of` — exported, in `__all__` — now raises **two unrelated exception types** depending on which
part of the document is wrong, and **neither is `UntrustedRow`**, whose docstring is verbatim this
case. It is also a **breaking change at an exported door**: before the delta every `rows_of` refusal
was a `ValueError`, and the test suite's own `pytest.raises(ValueError, …)` around it had to be
widened this round to keep passing. R14 recorded the exception-class divergence as its §1d; the
delta unified the *predicate* and left the *class* split, which is the half a caller writes code
against. **Production-reachable.**

### 1f · 🔴 the document container at `rows_of` is still untyped

```
rows_of(<plain object exposing only .get>) -> ACCEPTED, assembles a surface
rows_of(<dict subclass>)                   -> ACCEPTED
```

Every row-level decision is now `type(x) is …`; the container that supplies the rows is not typed at
all. R14 §1e, unchanged. **Adversarial-input only.**

---

## 2 — grading the boxed claim

> A hand-typed but well-typed `cost` is the **hand-edited-manifest** threat, whose only answer is the
> document digest recorded in §6.4.2 and **deliberately not taken**. Pretending a value bound closes
> it would be worse than leaving it open, because it would look closed.

### 2a · ✅ the second sentence is sound, and I want to say so plainly

It is correct, and it is the harder half to get right. `1000000000` is a well-typed integer and no
predicate over the value distinguishes a forged cost from a real one. A range bound, a magnitude
bound, a "plausible cost" heuristic — each would be a gate with no subject, which is the exact
vacuity failure this document has a standard about and which §0.14.1c already convicts elsewhere in
this design (*"satisfied today only in the degenerate sense that **every** such pipeline is
rejected… that is **not** evidence the rule works"*). **A builder who declines to ship a check that
cannot fail is doing the right thing, and this one is.** Nothing below retracts that.

### 2b · 🔴 the word **"only"** is false, and the disproof is 25 lines above the code

`contract.py:109-112`, in the graded delta, in the builder's own hand:

> `lane`, `tier`, `cost` and `relevance` are therefore **refused today on purpose** — §0.14.1c
> records them as UNBUILT with CP-2/CP-4 owning their producers, and **a door that accepted them
> would be letting an unbuilt capability in through the back.**

`contract.py:135-138`, in the same dict literal:

```python
    "lane": (str,),
    "tier": (str,),
    "cost": (int,),
    "relevance": (int,),
```

Measured: `rows_of` and `validate_document` **both ACCEPT** a row carrying all four. The comment
describes the design that closes the threat; the code four lines down opens it. This is not a
missed idea — **the builder wrote the answer down and then did not take it.** The second comment
block (`:121-134`) argues the opposite of the first, and both shipped, so a reader of this file
cannot tell which rule is in force without executing it.

### 2c · ✅ **the cheaper mechanism, named and executed**

Q2 asks for a mechanism cheaper than a document digest that does not weaken §6.1 layer 3. There are
two, and the first is four deleted dict entries.

**Mechanism 1 — remove the four ranking fields from `ROW_FIELDS`.** §0.14.1c states the fact that
makes it free: *"**None of the three fields rule 1 names can appear on a manifest row, and nothing
produces `relevance` at all.**"* Nothing in this repository writes them (`grep` for
`admitted_against` outside the package: zero hits; `_row` emits seven keys, none of them these).
Executed, with the four entries popped at runtime:

```
ROW_FIELDS now: ['admitted_against','contract_version','id','kind','lifecycle','members','owning_service']
build([admitted]) still OK          : ACCEPTED
rows_of(build output) still OK      : ACCEPTED
the committed empty manifest OK     : ACCEPTED
hand-typed cost now                 : REFUSED[ContractViolation]
```

It costs **nothing real** and it **strengthens** §6.1 layer 3 rather than trading it away: the
accepted set is strictly smaller, every remaining row is still fully re-validated, and no format
changes, so `load()`, the M1 drift gate and every reader are untouched. Compare the digest's own
recorded costs (§6.4.2): *"it **changes the manifest format**, so it changes the M1 drift gate,
`load()`, and every reader"*, and *"**a recomputed digest passes**"*. The digest is a **weaker**
answer to this threat than the mechanism the round already built.

**Mechanism 2 — derive, never author.** This package's own C-0 rule, `contract.py:52-54`:

> `owning_service` is absent **BY DESIGN** — C-0 requires it **derived, never authored**. **A field a
> declaration can state is a claim about ownership, not a fact about it.**

`cost` is that sentence with one noun changed. It is a *fact about a declaration* — §0.14.1a shows
the legacy runtime already computing it (`_tool_tokens(td)`), from the tool definition, not from an
authored field. Derived at generation or recomputed at assembly, a hand-typed `cost` is not merely
*detected*, it is **inert** — strictly stronger than tamper-evidence, and it needs no new format.
The design that closes this is already written down twice in this package.

### 2d · 🔴 what "leaving it open" actually cost, measured with a control

The threat is not hypothetical at this artifact. Three rows, one budget:

| | surface |
|---|---|
| rows carry a hand-typed `"cost": 1000000000` on `book_list` | **`('book_get',)`** — 2 of 3 withheld |
| CONTROL, every row `"cost": 1` | `('book_get', 'book_list', 'book_zz')` |

And sharper, because `relevance` now decides identity rather than volume —
`OrderBy(("relevance","desc"))` then `TopK(k=1)`:

| | survivor |
|---|---|
| hand-typed `relevance: 9999` on `book_list` | **`('book_list',)`** |
| hand-typed `relevance: 9999` on `book_zz` | **`('book_zz',)`** |
| CONTROL, every `relevance: 1` | `('book_get',)` |

A hand-typed integer selects **which single declaration the model sees**. That is arm E's shape,
reached through the row. **Production-reachable, third consecutive round.**

### 2e · the grade, stated as the prompt asks

**The sentence is a principled limit wrapped around a rationalisation, and the two can be separated
cleanly.** *"No value bound closes a well-typed `cost`"* — **true, keep it, and keep refusing to
ship one.** *"…whose **only** answer is the digest"* — **false**, and the round's own commit proves
it, because the mechanism that closes it is the mechanism the round built. What makes this more than
a scoping quibble is that the sentence was used to justify a change in the **permissive** direction:
"leaving it open" would have been declining to name the four fields. Naming them is opening it, in
the one delta whose thesis is that an undefined field is refusable.

### 2f · does refusing an undefined field break a legitimate forward path, discovered late?

| forward path | breaks? | discovered when |
|---|---|---|
| CP-2's `relevance`, CP-4's `lane`/`tier`/`cost` | **no** — pre-carved | n/a. This is the mitigation the round chose, and it is the finding |
| a CP-4 row field added to `_row` only | **YES** | **LATE** — `build`/`generate` accept and write it; `load()` and CI refuse it afterwards (§1c, measured) |
| a CP-4 producer writing exactly `ROW_REQUIRED` | **YES** | **LATE** — passes `rows_of`, fails `load()` (§1b, measured) |
| an external row producer | n/a | none exists (`grep`: zero hits outside the package) |

So the honest answer to Q2's second half: **the closed schema is the right design and the two late
paths it creates are both in the WRITER, both measured, and both closed by one call.** Refusing
undefined fields does not need the four carve-outs to be safe; it needs `check_row_shape` on
`_row`'s return.

---

## 3 — `members` is required: the class closed, two survivors

Measured, seven shapes, both doors:

| row | `rows_of` | `validate_document` |
|---|---|---|
| `members` **absent** | REFUSED ✅ | REFUSED ✅ |
| `members: null` / `0` / `false` | REFUSED ✅ | REFUSED ✅ |
| `members: []` | ACCEPTED | ACCEPTED |
| `members: []` on a **skill** | **ACCEPTED** 🔴 | REFUSED |
| `members: ['ghost']` | **ACCEPTED** 🔴 | REFUSED |
| `members: "book_x"` | REFUSED | REFUSED |

**R14 §3 is CLOSED** — the four shapes that were served as "this declaration references nothing" are
now refused at both doors. That is a real closure and it is the round's second-best result.

**Survivor 1 (documentation).** `manifest.py:415` still reads `members=tuple(r.get("members", ()) or
())`. It is now unreachable, and it is the exact spelling the delta's own comment at `:459-460`
condemns, left in place 44 lines above it. A reader who greps for the pattern finds it and concludes
the rule is not in force.

**Survivor 2 (behaviour).** A **skill** carrying `members: []` reaches all four consumer doors as a
declaration that references nothing — `check_contract`'s clause *"a skill or workflow with no members
references nothing and can never resolve"* is a contract clause, and `rows_of` runs no contract
clause. Same root as §1b. **Production-reachable.**

**And the fix is unguarded.** Removing the `ROW_REQUIRED` loop leaves the suite at **113 passed**;
the defect it restores is an uncaught **`KeyError`** escaping `rows_of` and `validate_document`,
because `check_row_shape:180` dereferences `row["members"]` unconditionally. The required check is
load-bearing for `check_row_shape`'s own safety and nothing asserts it.

---

## 4 — the TOCTOUs and the `id` split, re-measured against this round

### 4a · ✅ the 6th (`dict(r)`, `manifest.py:472`) is **CLOSED** — narrower

```
validate_document(<dict-subclass row whose .get('id') lies>) -> REFUSED[UntrustedRow]
    "<no id>.declarations[0]: is a LyingRow. Accepted: a plain JSON object"
```

`check_row_shape`'s `type(row) is not dict` refuses the only vehicle. R14 §2a **CLOSED**, and it was
not claimed — the round's second unadvertised win.

### 4b · ✅ `validate_document`'s `id` split is **CLOSED** — narrower, same cause

`r.get("id", "")` at `:397` and `r["id"]` at `:454`/`:472` can no longer disagree: a plain `dict` has
one storage. R14 §4b **CLOSED**.

### 4c · 🔴 but both closures rest on one untested line, and weakening it restores the 6th in full

Injection `D3` (`type(row) is not dict` → `isinstance`), suite **113 passed**, proven live first:

```
validate_document(dict-subclass row) -> ACCEPTED
   contract-checked id: 'book_list'   RETURNED id: '!! HAND TYPED !!'
   rows_of(returned) -> ['!! HAND TYPED !!']
```

Two findings' closure is carried entirely by a line no test can see. **Guard-only.**

### 4d · 🔴 the 5th (`{**doc}`, `manifest.py:472`) is **OPEN, unchanged**

```
validate_document(<dict-subclass document>) -> ACCEPTED
   validated: manifest_version=1  contract_version='1.0.0'
   RETURNED : manifest_version=999 contract_version='banana'
```

`contract_version` is §6.4's queue comparand. `doc` is still only `isinstance`-checked at `:356`
while every row is now exact-typed — the asymmetry is now *inside one function*. **Adversarial-input
only, unchanged.**

### 4e · 🔴 `build`'s `id` split is **OPEN, unchanged**

`manifest.py:227` `r.get("id")` vs `:236` `origin[r["id"]]`, with `isinstance(r, dict)` two lines
above. `build` is the one row-reader the delta did not reach (§1d). **Adversarial-input only,
unchanged.**

### 4f · the read-twice sweep, delta only

| site | check-read | use-read | verdict |
|---|---|---|---|
| `contract.py:157` → `:160` → `:174` → `:180` (**new**) | `row.get("id")` | `for key in row`, `row.items()`, `row["members"]` | ✅ safe — `type(row) is not dict` at `:158` guarantees one storage; four reads all rest on it, and it is untested (§4c) |
| `contract.py:164` → `:175` (**new**) | `key not in ROW_FIELDS` | `ROW_FIELDS[key]` | 🔴 **NEW read-twice site.** `ROW_FIELDS` is a **plain mutable `dict`** while `ROW_REQUIRED` beside it is a `frozenset`. Two reads of a mutable module global, two lines apart. I mutated it at runtime with no complaint while measuring §2c |
| `surface.py:56` → `:61` (**new**) | `check_row_shape(r, …)` | `dict(r)` | ✅ safe — same reason |
| `manifest.py:392` → `:472` (**new call**) | `check_row_shape(r, …)` | `dict(r)` | ✅ **closes the 6th** (§4a) |
| `manifest.py:363`,`:369` → `:472` | `doc.get(k)` | `{**doc}` | 🔴 §4d, the fifth — **OPEN** |
| `manifest.py:227` → `:236` | `r.get("id")` | `origin[r["id"]]` | 🔴 §4e — **OPEN** |
| `manifest.py:294` → `:301` → `:302` | `ambient.exists` | `load()` then `ambient.exists` | 🔴 R12 §5 — unchanged, third read of the same fact |

**A new read-twice site WAS introduced this round.** Mild, adversarial-only, and it breaks R14's
streak at one — which is the evidence Q6 asks for.

---

## 5 — the guard axis: 2 of 4 delta elements red, and an existing test made vacuous

Baseline **113 passed**, measured by me at start and finish. Every silent row was proven to restore
a real defect in a standalone probe **before** the suite was run.

### Red-ability table — baseline **113 passed**

| injection | what it models | proven live by | suite |
|---|---|---|---|
| `D1_unknown_key_refusal_removed` | **the delta's thesis** — `key not in ROW_FIELDS` removed | undefined keys admitted at both doors | **1 failed** ✅ `:673` |
| `D5_members_element_check_removed` | the `members` element bound removed | `[""]`, `[None]` admitted | **1 failed** ✅ `:673` |
| `D8_rowsof_shape_call_removed` | the **surface half** of the delta reverted | every shape admitted at the door | **1 failed** ✅ `:673` |
| `D7_vdoc_shape_call_removed` | **the manifest half of the delta reverted** | `weight: 999`, `cost: 1.5`, `lane: {…}` all **ACCEPTED by `load()`** and refused by `rows_of` — *the two-definitions defect the round is named for, restored* | **113 passed** 🔴 |
| `D2_required_check_removed` | `ROW_REQUIRED` removed | a row with no `members` → uncaught **`KeyError`** out of both exported doors | **113 passed** 🔴 |
| `D3_row_type_isinstance` | the row type bound weakened | **the 6th TOCTOU restored in full**: checked `'book_list'`, returned `'!! HAND TYPED !!'`, `rows_of` accepts it | **113 passed** 🔴 |
| `D4_field_type_isinstance` | the per-field bound weakened | **§0.14.1 restored at the row, driven to arm E**: a `str`-subclass `id` with a lying `__eq__` made `AllowList(names=('NOTHING_MATCHES_THIS',))` **keep the row** — an unlisted declaration on the wire | **113 passed** 🔴 |
| `D6_key_type_check_removed` | the non-string key bound removed | **restores nothing for a plain key** — `7 not in ROW_FIELDS` catches it anyway. Load-bearing only for a `str`-**subclass** key | **113 passed** — *not counted as a finding* |
| `C4_doc_return_original` | **R13's** `{**doc, …[dict(r)…]}` fix reverted | the test's own `Smuggler` vehicle is now refused by `check_row_shape` first, so `:643`'s `except UntrustedRow: return` fires and the assertion is never reached | **113 passed** 🔴 |
| `C1_lost_check_removed` | rounds 1–14 canary | `book_get` dropped silently | **2 failed** ✅ |
| `C3_declarations_key_check_removed` | **R14's** fix, one round on | missing key served as empty | **1 failed** ✅ |
| `C2_outer_previous_isinstance` | **R13's** fix, two rounds on | `previous` subclass accepted | **113 passed** 🔴 |
| `G_grandfathering_in_generate` | §6.4 lands in the **only real writer** | 2-row file on disk, `QUEUE=['book_get']`, drains, `validate_document` OK, `load()` OK | **113 passed** 🔴 |

### 5a · 🔴 the round's central claim is guarded on exactly one of its two halves

`D7` is the finding of this section. The delta's thesis is *"one definition for **both** doors"*, and
**the `validate_document` half is deletable with the suite green** — and deleting it restores, in
plain JSON, the precise defect R14 recorded as §1d. The `rows_of` half has three red-able tests. The
test written for the delta (`:661-676`) exercises only `rows_of`.

### 5b · 🔴 the delta made an existing test vacuous

`test_A_ROWS_OWN_GET_CANNOT_SMUGGLE_A_ROW_PAST_THE_VALIDATOR` (`:612-648`) guards R13's
`return {**doc, "declarations": [dict(r) for r in rows]}`. Its vehicle is a `dict` **subclass**
whose `.get` appends a row mid-validation. `check_row_shape` now refuses that subclass **before** the
`.get` is ever called, so the test takes its `except UntrustedRow: return` at `:643` and asserts
nothing. Measured at HEAD, unmodified: the vehicle is `REFUSED[UntrustedRow]`. And `C4` — reverting
the fix the test exists for — is **113 passed**.

This is not a regression in behaviour; the behaviour improved. It is a regression in **coverage**,
created by the graded delta, and it is invisible because a test with an early `return` reports the
same green as a test that ran.

### 5c · 🔴 the loosened assertion was split — and the door half was re-loosened in a new spelling

`:1469-1495`. The comment is admirably direct about the previous round's failure, and the **budget
half is genuinely fixed**: `_narrow` is now called directly with `pytest.raises(ValueError,
match="plain integer")`, which no longer confuses the two guards. But the **door half** reads:

```python
with pytest.raises((ValueError, _CV)):
    SurfaceAssembler(doc).assemble(...)
```

Accepting `ValueError` *or* `ContractViolation` is the same alternation as `"plain integer|plain
scalar"`, spelled as a type tuple: with the door's bound downgraded, `rows_of` admits the row and
`_narrow` raises `ValueError` downstream, and the assertion cannot tell the two apart. Measured —
`D4` (the door's bound weakened to `isinstance`) is **113 passed**. The comment above it says *"Both
guards genuinely do stay, so both are asserted — separately."* **The door assertion still does not
assert the door.** This is the second consecutive round in which this specific assertion describes a
property it does not check.

### 5d · 🔴 the guard the delta DELETED — measured against the R14 artifact in one process

`rows_of` used to carry, with a §0.14.1 rationale attached:

```python
if not _is_exactly(r.get("id"), str) or not r.get("id"):
    raise ValueError(f"declarations[{i}].id is {r.get('id')!r}; a declaration id must be a
        non-empty plain string. An id with a custom __eq__ decides membership in every allow-list
        and deny-list it is compared against (§0.14.1).")
```

`check_row_shape` reproduces the *type* half and **not the non-empty half**. Reconstructed the
pre-delta `rows_of` from `b30db5b8`'s own source and ran both in one process:

| row | pre-delta (R14) | HEAD (R15) |
|---|---|---|
| `id: ""` | **REFUSED** | **ACCEPTED** 🔴 |
| `id: 7` | REFUSED | REFUSED ✅ |
| `id` absent | REFUSED | REFUSED ✅ |
| `id: "!!! HAND TYPED !!!"` | ACCEPTED | ACCEPTED |

Two of three preserved and one lost, under a comment that describes the change as consolidation. The
builder's standing record includes *"a guard loosened while the comment beside it claimed it had not
been"*; this is that shape again, and the vehicle is plain JSON. **Production-reachable, introduced
by the graded delta.**

---

## Bypass table

| property asserted | path that defeats it | evidence | reachability |
|---|---|---|---|
| one definition of a valid row, for both doors | `rows_of` runs no contract clause — 9 row classes reach the consumer that `load()` refuses | `surface.py:60` vs `manifest.py:392-462` — executed, both doors | **production-reachable** |
| " | the **writer** never calls it: `_row` + a field → `build`/`generate` accept and write, `load` and the gate refuse | `manifest.py:106-153`, `:264-268` — executed | **production-reachable** |
| " | `build(previous=)` has its own weaker definition — undefined key, dict value, int key all accepted | `manifest.py:226-236` — executed | **production-reachable** |
| an undefined field is refused | the **four ranking fields are defined**, and the comment 25 lines above says they are refused | `contract.py:109-112` vs `:135-138` — executed | **production-reachable** |
| `members: ['ghost']` no longer travels | M5 is a contract clause; `rows_of` runs none | `contract.py:180-184` — executed, 4 doors | **production-reachable** |
| a hand-typed `cost` is unclosable without a digest | popping four dict entries refuses it and breaks nothing | `contract.py:135-138` — **executed counterfactual** | **production-reachable** |
| a hand-typed value cannot pick the survivor | `OrderBy(relevance desc) → TopK(1)` returns whichever row carries the hand-typed integer | `surface.py:354`,`:618` — executed with a control | **production-reachable** |
| a declaration id is a non-empty string at the door | `id: ""` refused pre-delta, accepted at HEAD | `surface.py` `b30db5b8` vs `contract.py:113` — executed, one process | **production-reachable, introduced this round** |
| an exported door refuses with one, documented class | `ContractViolation` ∉ `ValueError`, ∉ `UntrustedRow`; `rows_of` raises both it and bare `ValueError` | `contract.py:31`, `surface.py:44` — executed | **production-reachable, introduced this round** |
| `rows_of` validates what reaches it | the **document** is untyped — any object with `.get` assembles a surface | `surface.py:40` — executed | adversarial-input only |
| a validator returns what it validated | `{**doc}` re-reads: validated `1`/`'1.0.0'`, returned `999`/`'banana'` | `manifest.py:363` vs `:472` — executed | **adversarial-input only** |
| a declaration cannot silently leave the manifest | `.get("id")`/`["id"]` disagree in `build` | `manifest.py:227`/`:236` — executed | **adversarial-input only** |
| the row bound's exactness is guarded | `D3`/`D4`: `isinstance` restores the 6th TOCTOU and arm E at the row, suite green | §5 — executed, proven live | n/a (test defect) |
| the manifest half of the delta is guarded | `D7`: deletable, 113 passed, restores the named defect | §5a — executed | n/a (test defect) |
| R13's `{**doc, …}` fix is guarded | `C4`: the test's vehicle is now refused earlier, so the test early-returns | §5b — executed | n/a (test defect) |
| the P4 test reds when the mechanism lands | a mechanism landing in **`generate()`** — proven draining, loadable, on disk | §7 — executed, **113 passed** | n/a (test defect) |
| `generate`'s `exists`→`load` re-check covers a concurrent regeneration | the file is back by the third `exists()` | `manifest.py:294-306` — R12 §5, unchanged | **production-reachable** |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| element of this round's delta | is there a test? | can it red? | for the reason it names? |
|---|---|---|---|
| `contract.py:164` — an undefined key is refused | **YES** — `:661-676` | **YES** — `D1` → 1 failed | **YES** — `{"weight": 999}` is what reds it |
| `contract.py:180` — the `members` element bound | **YES** — `:661-676` | **YES** — `D5` → 1 failed | **YES** |
| `surface.py:60` — `rows_of` calls it | **YES** | **YES** — `D8` → 1 failed | **YES** |
| **`manifest.py:392` — `validate_document` calls it** | **NO** | n/a | **n/a — `D7` silent, and it is the delta's whole thesis** |
| `contract.py:170` — `ROW_REQUIRED` | **NO** | n/a | n/a — `D2` silent; removal is an uncaught `KeyError` |
| `contract.py:158` — the row is **exactly** a `dict` | **NO** | n/a | n/a — `D3` silent, the 6th TOCTOU restored |
| `contract.py:176` — the field type is **exact** | **NO** | n/a | n/a — `D4` silent, arm E restored at the row |
| `contract.py:161` — keys are strings | **NO** | n/a | n/a — redundant for plain keys; live only for a `str` subclass |
| **`contract.py:113`** — a declaration `id` is **non-empty** | **NO — the guard itself was deleted** | n/a | **NO — regression, §5d** |
| `test_cp1_membrane.py:1481` — the **door's** bound | **YES** | **NO** — `(ValueError, _CV)` accepts the downstream refusal too | **NO — re-loosened in a new spelling, §5c** |
| `test_cp1_membrane.py:1476` — the **budget's** bound | **YES** | **YES** | **YES — genuinely repaired this round** ✅ |
| `test_cp1_membrane.py:612` — R13's `{**doc, …}` fix | **YES, and it is now VACUOUS** | **NO** — `C4` → 113 passed | **NO — §5b** |
| `manifest.py:195` (**R13's** fix), two rounds on | **NO** | n/a | n/a — `C2` silent |
| `test_cp1_membrane.py:493-509` — P4 partial re-admission | **YES** (it *is* the test) | on `build`-landing only | **NO** — green on a `generate()`-landing mechanism, 4th round |
| `scripts/…-gate.py:361` — discards `validate_document`'s return | **NO** | n/a | — R13 §1f, unchanged |

## Sibling table — *a correction applied to one member of a set*

| fix shipped this round | sibling I looked for | also fixed? |
|---|---|---|
| `check_row_shape` at `rows_of` and `validate_document` | the **writer** — `_row`/`build`/`generate`, the one producer of rows | ❌ **NO** — §1c |
| " | `build(previous=)`, the fourth row-reader in the package | ❌ **NO** — §1d |
| " | the **contract clauses**, so the two doors agree on validity and not only on shape | ❌ **NO** — §1b, 9 classes |
| " | the **exception class** — `UntrustedRow` is the package's documented refusal for this boundary | ❌ **NO** — `ContractViolation` is neither that nor `ValueError`; §1e |
| " | the **`{**doc}`** half of `:472`, the sibling of the `dict(r)` half it just closed | ❌ **NO** — §4d, fourth round |
| " | the **document** container at `rows_of`, now the only untyped thing in a fully exact-typed function | ❌ **NO** — §1f |
| the schema is closed to undefined fields | **not carving out the four fields the finding was about** | ❌ **NO** — §2b, and the comment above them says so |
| `members` is required | `r.get("members", ()) or ()` at `manifest.py:415`, the spelling the delta's own new comment condemns 44 lines below | ❌ **NO** — §3 |
| " | `members: []` on a **skill** — the same "references nothing", at the door | ❌ **NO** — §3 |
| the loosened `match=` was split into two assertions | the **door** half of the split, which accepts either exception | ❌ **NO** — §5c |
| `rows_of`'s bound moved into `check_row_shape` | the **non-empty `id`** clause of the guard being moved | ❌ **NO — LOST**, §5d |
| the delta got three red-able tests | a test for the half that lives in `manifest.py` | ❌ **NO** — §5a |
| " | a test for the **exactness** of the two type bounds, not their presence | ❌ **NO** — `D3`/`D4` silent, second round |
| " | a test for **R13's** and **R14's** fixes, one and two rounds on | ❌ partial — `C3` reds (R14's), `C2` silent (R13's) |

---

## 6 — convergence: trend or single point

**How I classified.** R13's buckets and R14's rule, unchanged, applied to my own findings by the
mechanism required to trigger them:

* **production-reachable (P)** — the vehicle is a plain value or an ordinary event: hand-typed JSON,
  a missing key, an ordinary refactor, a real race. No custom dunder anywhere in it.
* **adversarial-input only (A)** — the vehicle is *code*: a `dict`/`str`/`int` subclass, a forged
  dunder. Whoever supplies one is already running in the process.
* **guard-only (G)** — no runtime trigger: *"this fix is deletable and the suite stays green"*,
  *"this test cannot red"*, *"the comment beside the code says the opposite of the code"*.

**The "introduced" column, same rule as R14:** a finding counts iff **reverting the graded delta
closes it**. Not "the fix was incomplete", not "the fix guarded the wrong property". I ran the revert
for R15's four; R9–R14 are carried from each verdict's own text.

### The controlled series — Verifier B only

| round | production-reachable | adversarial-input only | guard-only | total | **introduced by the graded delta** |
|---|---|---|---|---|---|
| 9 | 4 | 5 | 2 | 11 | **2** (derived) |
| 10 | 12 | 5 | 1 | 18 | **1** (derived) |
| 11 | 9 | 7 | 5 | 21 | **2** (derived) |
| 12 | 3 | 7 | 7 | 17 | **1** (derived) |
| 13 | 3 | 3 | 3 | 9 | **3** (executed) |
| 14 | 8 | 4 | 9 | 21 | **2** (executed) |
| **15** | **11** | **3** | **10** | **24** | **4** (executed) |

R15's four: the **deleted non-empty-`id` guard** (§5d, revert restores it), the **`ContractViolation`
exception change at an exported door** (§1e, revert restores `ValueError`), the **four ranking fields
admitted beside a comment saying they are refused** (§2b, the delta wrote both), and the **vacuous
`Smuggler` test** (§5b, revert restores its vehicle). The re-loosened door assertion (§5c) is *not*
counted — reverting gives R14's assertion, which is also green — and saying so is the point of
having a rule.

### Closure — what the delta closed, not what a verifier found

R14-B left **15** distinct findings open. Re-run as probes against this artifact:

| R14-B finding | now |
|---|---|
| §1c `validate_document`/`load` bound no row field (P) | **CLOSED** ✅ |
| §3 `.get("members", ()) or ()` — absent/`null`/`0`/`false` (P) | **CLOSED** ✅ |
| §2a the 6th TOCTOU, `dict(r)` (A) | **CLOSED** ✅ (incidental, untested) |
| §4b `validate_document`'s `id` split (A) | **CLOSED** ✅ (incidental, untested) |
| §1d two definitions / wrong exception class (P) | **PARTIAL** — shape unified, validity and exception class still split (§1b, §1e) |
| §5 the loosened `:1461` regex (G) | **PARTIAL** — budget half repaired ✅, door half re-loosened (§5c) |
| §1a `members: ['ghost']` at four doors (P) | **OPEN** |
| §1b hand-typed `cost` steers the budget (P) | **OPEN** |
| §1e the document container at `rows_of` (A) | **OPEN** |
| §2b the 5th TOCTOU, `{**doc}` (A) | **OPEN** |
| §4a `build`'s `id` split (A) | **OPEN** |
| R12 §5 `generate`'s `exists`→`load` race (P) | **OPEN** |
| §5 the unguarded strengthenings (G) | **OPEN** |
| §1f the gate discards the return (G) | **OPEN** |
| §7 P4 test green on `generate()`-landing (G) | **OPEN** |

| transition | open in this scope | closed by the next delta | rate |
|---|---|---|---|
| R11-B → R12 | 21 | 3 | **14%** |
| R12-B → R13 | 17 | 1 + 2 partial | **~9–12%** |
| R13-B → R14 | 12 | 1 | **~8%** |
| **R14-B → R15** | **15** | **4 + 2 partial** | **~27–40%** |

### The ruling Q6 asks for: **single point, not trend**

R14's result was *"the first round in four with no new TOCTOU"*. It did not repeat.

* **A new read-twice site WAS introduced** (§4f): `check_row_shape` reads the **mutable module global
  `ROW_FIELDS`** at `:164` and again at `:175`, while `ROW_REQUIRED` two lines away is a `frozenset`.
  Mild and adversarial-only — but the claim under test is *"no new TOCTOU"*, not *"no severe one"*,
  and one data point that does not repeat is a point.
* **`introduced` rose 2 → 4**, and the series now reads 2, 1, 2, 1, 3, 2, **4** — a sequence with no
  direction, which is what a single point looks like when you plot enough of them.
* **The confounder, stated before the conclusion:** R15's delta is ~90 changed lines against R14's
  ~41 and R13's 2, and `introduced` has tracked delta size all three rounds (3 findings from 2 lines,
  2 from 41, 4 from 90). Normalised per changed line, R15 is the *best* of the three. That is a real
  defence and I am recording it rather than making the reader find it.
* **What WOULD settle it**, named as the prompt asks: (i) **three consecutive rounds at
  `introduced == 0`**, since two points cannot distinguish a trend from alternation; (ii) the
  read-twice sweep run **by the builder, before the commit, with its result in the commit message** —
  which converts the number from a verifier's measurement of the builder into the builder's
  measurement of themselves, and is the only version of it that can be improved deliberately;
  (iii) `introduced` reported **per changed line**, so a round cannot buy a good number by shipping
  less.

### What the numbers say

* **The closure rate rose for the first time in the series — 14%, ~10%, ~8%, ~27%.** That is the
  round's genuine result and it should be said before anything else in this section. Four findings
  closed against one in each of the two previous rounds. **Two of the four were not aimed at** — the
  6th TOCTOU and `validate_document`'s `id` split both fell out of `type(row) is not dict`. That is
  what a *structural* fix does and it is the argument for preferring one, which this round made and
  which the numbers now support.
* **The production-reachable count rose 8 → 11, and three of those eleven are R14's, unclosed.** The
  rise is not effort: `members: ['ghost']` (third round), the hand-typed `cost` (third round) and
  `generate`'s race (fourth round) are carried, and two of the new ones (§5d, §1e) were **created by
  this delta**.
* **The termination condition remains unmet, but for the first time the gap narrowed.** Discovery in
  this scope is ~24 and closure is 4–6. At R14 it was 21 against 1. The number to watch is whether
  27% survives one more round or reverts to 8%, because a structural fix closes a batch once and then
  the next delta has to find another structure.
* **Grading the round's chosen answer, which the prompt asks for directly.** Replacing a value bound
  with a schema bound was **the right move**, it is the first change in four rounds that closed
  findings it did not aim at, and the reasoning behind it (§1's docstrings) is correct. **The
  execution has one systematic flaw and it is the same one six rounds have recorded:** the fix was
  applied at *the two doors a verifier named* and not to *the set of row-readers*, which is four. And
  the one place the round reasoned its way to the correct general rule — *"a door that accepted them
  would be letting an unbuilt capability in through the back"* — it then wrote four exceptions to it,
  four lines down, and the exceptions are exactly the fields the open finding rides on.

---

## 7 — the P4 test: `generate()` still invisible, fourth round

`tests/test_cp1_membrane.py:433-509`. **CONFIRMED OPEN, unchanged from R12, R13 and R14.**

I built §6.4's mechanism inside `generate()` — a declaration failing a breaking amendment stays in
the runtime carrying its origin stamp and its old `admitted_against`; the queue is the rows whose
`admitted_against` is not the document's version — and proved it real **before** running the suite:

```
[G] gen1 (1.0.0): [('book_get','1.0.0','1.0.0'), ('book_list','1.0.0','1.0.0')]  queue = []
[G] gen2 (2.0.0): [('book_get','1.0.0','1.0.0'), ('book_list','1.0.0','2.0.0')]  QUEUE = ['book_get']
[G] rows ON DISK: ['book_get','book_list'] | validate_document: OK | load(): ['book_get','book_list']
[G] gen3 (both re-admitted): QUEUE = []  <- DRAINS
[G] MECHANISM PROVEN REAL ON DISK
```

**Suite: 113 passed**, with `[G] test module tests.test_cp1_membrane.generate is-injected=True`
printed. The test's only exit is `build`'s refusal, and the mechanism does not touch `build`, so it
takes its `except UntrustedRow: return` at `:499` on a runtime where §6.4's queue is live, on disk,
and draining. The docstring at `:471-486` is explicit that a verifier already measured this twice;
the assertion still cannot see it.

---

## What I would fix first

1. **Delete the four ranking fields from `ROW_FIELDS` (§2b, §2c).** Four lines removed. Measured to
   break nothing, to refuse the hand-typed `cost`, and to make `contract.py:109-112` true. This is
   the answer to the round's own question and the round already wrote it down.
2. **Call `check_row_shape` on `_row`'s return (§1c).** One line. It closes the writer door and it
   converts CP-4's field addition from a late failure into an immediate one with a C-12 field path.
3. **Run the contract clauses at `rows_of`, or stop calling it one definition (§1b).** Nine row
   classes reach the consumer that `load()` refuses, and the consumer-facing door is the weak one.
   If the split is deliberate, the docstring should say *shape*, because it currently says *row*.
4. **Restore the non-empty `id` clause (§5d), and make `check_row_shape` raise `UntrustedRow`
   (§1e).** The first is a guard this delta deleted; the second is the class this boundary's own
   docstring names, and the change is source-compatible with the pre-delta `ValueError` only if
   `UntrustedRow` is chosen deliberately.
5. **Test the manifest half (§5a).** `D7` is deletable with the suite green, and it is the half the
   round is named for. One assertion: `pytest.raises(UntrustedRow)` on `validate_document` with
   `{"weight": 999}`.
6. **Repair the door assertion at `:1481` (§5c) and the vacuous test at `:612` (§5b).** The first
   should be `pytest.raises(ContractViolation)` with no alternation; the second needs a vehicle that
   survives `check_row_shape` — a plain-`dict` row and a `declarations` list the validator can be
   made to re-read — or its early `return` should be an explicit `pytest.skip` so a reader can see it
   is not asserting.
7. **`ROW_FIELDS` should be a `MappingProxyType` or a `frozenset` of names plus a lookup (§4f).**
   `ROW_REQUIRED` beside it is already immutable; the asymmetry is the whole finding.
8. **Assert the queue through `generate()` (§7).** Fourth round. The mechanism's only plausible
   landing site is still the one function the test never calls.
