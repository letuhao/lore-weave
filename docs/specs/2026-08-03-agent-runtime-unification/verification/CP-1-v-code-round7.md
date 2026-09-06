# CP-1 · V-CODE round 7 — item 1.4, P4 half only

**Artifact:** `1ab136b1c16c68a3889ddaab932343e11b3f58c1` (verified at start and again before writing
this verdict; HEAD did not move).

**Scope:** item 1.4's P4 half — *no instrument column is bound to a constant at any INSERT* — and the
tests that arrived with the current fix. 1.1, 1.2, 1.3, 1.5, 1.6, 1.7, 1.8, 1.9 and 1.4's M4 half are
not re-graded. Everything below was produced by **executing** the package against temp paths; no
tracked file was modified.

---

## 1 · Verdict

| item | verdict |
|---|---|
| **1.4 · P4 half** | **FAIL** |

The mechanism the fix claims is **real and it works**: driven through `generate()` against a real file
across a simulated contract amendment, two rows carry two different stamps. That is more than either
previous attempt achieved, and the builder's correction — *the manifest is this checkpoint's write
boundary* — remains right.

It fails on four independent grounds, any one of which is sufficient:

1. **The mechanism has no guard.** Deleting `previous=` from `generate()` — the only path that will
   ever write the real manifest — leaves **89/89 tests green**. The round-6 defect, restored,
   undetected. (§4, REGRESS=A.)
2. **The re-admission queue cannot drain.** The carry is keyed on `id` alone and never updates, so a
   declaration that *is* re-admitted under the new contract keeps its old stamp forever. The queue was
   permanently **empty**; it is now permanently **non-empty**. Neither state answers §6.4's question.
   (§3.)
3. **The fail-open erasure survives untouched.** Regenerating to a fresh path — or after `rm` of the
   manifest, the ordinary reaction to a drift FAIL — restamps every row with the current constant and
   silently empties the queue. Nothing detects it. (§3.2.)
4. **The test that names §6.4's queue is vacuous.** It is green with the *entire* carry mechanism
   removed, because it hand-mutates its own fixture and then filters it. (§4.)

Two smaller findings: `"99.0.0"` is still accepted by the stamp validator, contradicting the in-code
comment that says all four of round 6's inputs are now rejected (§5); and the write side never applies
the stamp check the read side gained, so `build(previous=…)` emits `7` and `"banana"` as stamps and
produces a document `load()` refuses (§5.2).

---

## 2 · The falsifier

I set out to make the fix **false** in three specific ways, and stated in advance what each would look
like:

* **F1 — the stamps still cannot differ in a real sequence.** Falsified: they can. Round 7 does not
  repeat round 6's finding.
* **F2 — the M1 drift gate still forces a restamp.** Falsified for the specific interaction round 6
  named; *not* falsified for the general one — see §3.2.
* **F3 — the mechanism is unguarded, so the next edit re-breaks it silently.** **Confirmed by
  execution.** This is the finding.

A fourth falsifier arrived unplanned, from asking what the queue is *for*: **F4 — the queue must be
able to reach empty when the migration is done.** Confirmed broken (§3).

Had F3 and F4 both come back clean, this would have been a PASS on the P4 half regardless of the
`"99.0.0"` residue.

---

## 3 · Question 1 and 2 — the real sequence, and what the M1 interaction became

### 3.1 Two rows CAN carry different stamps — through `generate()`, not just `build()`

Driven against a temp path, with `CONTRACT_VERSION` rebound in both modules that bind it by name
(`contract.py:20`, and `manifest.py:29`'s `from .contract import CONTRACT_VERSION`):

```
gen1 @ 1.0.0 : book_list -> "1.0.0"
--- contract amended to 2.0.0 ---
gen2 @ 2.0.0 : book_get  -> "2.0.0"    book_list -> "1.0.0"      # doc-level contract_version -> "2.0.0"
```

The file on disk holds two different values. `manifest.py:192` (`previous=load(path=target) if target
and ambient.exists(target) else None`) does carry the prior stamp across a regeneration, and
`manifest.py:161-165` + `:130` apply it. **The claim in the docstring at `manifest.py:144-159` is
true as far as it goes.** Round 6's specific finding is closed.

### 3.2 The M1 interaction: resolved for the case named, moved for the case that matters

Round 6's mechanism was: *the M1 drift gate forces regeneration; regeneration restamps; therefore the
queue is empty whenever CI is green.* Executed against the gate as it stands:

* `scripts/agentruntime-membrane-gate.py:350` computes `expected = build([])` — **no `previous`, no
  admitted input**. The right-hand side is the hard-coded empty document.
* At CP-1 the committed manifest *is* empty, so the gate passes and **the stamp has no subject in the
  committed artifact at all** — zero rows. The gate cannot exercise the carry either way.
* After an amendment the doc-level `contract_version` in `build([])` moves (executed: `build([])`
  returns `contract_version: "2.0.0"` once the constant is bumped), so the gate does still red and
  still forces a regeneration. **That forced regeneration no longer restamps** — §3.1 proves it. For
  this one interaction, resolved.
* But the gate will red unconditionally the moment CP-4 admits anything (`doc != build([])` for any
  non-empty manifest), so it must be rewritten then — and whether its replacement passes `previous=`
  is an open question deferred to CP-4, not answered here. The gate itself models the wrong call:
  `build([])` with no `previous` is exactly the shape that loses stamps.

### 3.3 The queue is derivable — and cannot drain

`§6.4` exists so that a breaking amendment *"puts prior declarations into a re-admission queue without
leaving the runtime."* A queue is a work list. Executed, continuing the sequence above:

```
re-admit book_list under contract 2.0.0        -> stamp stays "1.0.0";  queue == ["book_list"]
re-admit book_list CHANGED (owner book-service -> library-service)
                                               -> owner column updates to "library-service"
                                                  stamp stays "1.0.0";  queue == ["book_list"]
```

The row's owning service is re-derived and rewritten from the live admission, while the stamp — the
field whose whole purpose is to say what that admission checked against — is taken from the file.
`manifest.py:130` reads `(carried or {}).get(d.id, admitted.contract_version)`: **`carried` wins
unconditionally whenever the id is present**, so `admitted.contract_version` is discarded for every
row that already exists. There is no code path anywhere in the package that updates a stamp for an
existing id — `_row` is the only writer of the field, and `carried` shadows it.

The consequence is the mirror of the defect being fixed. Before: the queue was permanently empty, so
the migration could never find work. Now: once an amendment lands, the queue permanently names every
pre-amendment id, **including the ones already re-admitted**, so the migration can never finish. The
docstring's sentence — *"§6.4's re-admission queue is exactly the rows whose stamp is not current"* —
is true only until the first re-admission, after which the queue reports work that has already been
done, forever. A stale field and an unmovable field are the same failure: the reader cannot act on
either.

The only way to clear a stamp is to drop the row from `admitted`, regenerate, re-add it, and
regenerate again — a two-step dance nobody has written down, and one that is indistinguishable from
§3.4's silent erasure.

**Secondary, and it points at the same hole:** `ARCHITECTURE.md:1434` requires *"every declaration
carries `contract_version` **+** `admitted_against`"* — two fields. The row carries one.
`test_the_row_does_not_carry_a_write_time_constant_at_all`
(`tests/test_cp1_membrane.py:450-456`) now *rejects* the return of the second one. The pair is what
makes the queue drainable (one moves on re-admission, one records the origin); collapsing it to one
field is why nothing can move.

### 3.4 The erasure that survives

```
generate([...], path=<fresh path>) @ 2.0.0  ->  every row stamped "2.0.0"
```

`generate()` takes `previous=None` whenever the target does not exist (`manifest.py:192`). So a fresh
checkout that writes to a new location, a manifest deleted and regenerated, or any caller that reaches
`build()` directly without `previous=` (which is what the drift gate itself does at
`agentruntime-membrane-gate.py:350`) restamps the whole file with the current constant. Round 6's
outcome, verbatim, reachable by an ordinary operation, with **no test and no gate that notices**. The
default on `build(..., previous=None)` is the caller-supplied-value-defeats-the-safe-default shape.

---

## 4 · Question 4 — red-ability, tested by the shape that will actually occur

I injected four regressions through a `pytest_configure` plugin that rebinds the callables **before**
the test module imports them, so `from app.agentruntime import build, generate` picks up the regressed
version. No tracked file was touched. Baseline: 89 passed.

| injection | what it models | result |
|---|---|---|
| **A** — `generate()` drops `previous=`, writes `build(admitted)` | **the production write path reverting to round 6's behaviour** | **89 passed — GREEN** |
| **B** — `_row` ignores `carried` | the first fix, restamping every row | 1 failed (`test_two_rows_CAN_carry_different_stamps`) |
| **C** — `validate_document` loses the stamp block | round 6's read side | 1 failed (`test_the_stamp_is_VALIDATED_not_merely_present`) |
| **D** — the whole `previous`/`carried` mechanism removed | the fix never happened | 1 failed (`test_two_rows_CAN_carry_different_stamps`) |

**A is the finding, and it is exactly the trap the mandate names.** The injection the builder's test
proves red-ability against is at `build()`; the branch that matters — `manifest.py:192`, the only line
that will ever supply `previous` in practice — is unguarded. Both `generate()` call sites in the suite
(`tests/test_cp1_membrane.py:90`, `:379`) write to a **fresh `tmp_path`**, so line 192's `previous=`
argument is evaluated to `None` in every test that exists. The carry-through-`generate()` path has
zero coverage, and deleting it costs nothing.

**D additionally proves `test_the_readmission_queue_is_derivable_from_the_file_alone`
(`tests/test_cp1_membrane.py:425-432`) is vacuous.** It survives the removal of the entire mechanism
it is named after, because it calls `build()` with no `previous`, hand-mutates one row's stamp, and
then filters the dict it just mutated. It exercises a list comprehension written three lines above it.
Its assertion is `queue == ["book_get"] or queue == ["book_list"]` — a disjunction that accepts either
answer — narrowed only by `len(queue) == 1`, which restates the fixture. This is the
seed-and-control-agree shape: the test cannot tell a working queue from a broken one.

`test_two_rows_CAN_carry_different_stamps` (`:400-423`) is a genuine behaviour gate for the `build()`
half and needs no literal — that part is well built, and it is the test round 6's finding demanded.
`test_the_stamp_is_VALIDATED_not_merely_present` (`:434-448`) executes the real validator and is
red-able (C). `test_the_row_does_not_carry_a_write_time_constant_at_all` (`:450-456`) is an
absence-of-a-key shape gate: it fires only if the old field name returns, says nothing about any
value, and — see §3.3 — now guards against the shape §6.4 specifies.

---

## 5 · Question 3 — is the stamp validated?

Partly. Executed against `validate_document` (`manifest.py:263-270`):

```
None            rejected      "1.0"           rejected      " 1.0.0"     rejected
"banana"        rejected      1.0 (float)     rejected      "1.0.0 "     rejected
"1.0.0-beta"    rejected      old field name  rejected      "\n1.0.0"    rejected
"99.0.0"        ACCEPTED      "0.0.0"         ACCEPTED
```

Three of round 6's four inputs are now rejected, including the old field name substituted for the new
one. The regex is anchored, so the whitespace and prerelease variants fail too — this is a real check,
not a `str()` cast.

**`"99.0.0"` is still accepted**, and the comment at `manifest.py:259-262` states that a verifier fed
this `null`, `"banana"`, `"99.0.0"` and the old field name and *"all four were accepted"* — written in
the past tense, immediately above the fix, which reads as all four now being rejected. One is not.
`_VERSION` (`manifest.py:33`) is a **syntax** check, not a validity check: any well-formed triple
passes, including a version that never existed. The direction is mostly safe (a bogus stamp lands
*in* the queue, not out of it), and a shape check cannot in principle catch a hand-typed `"1.0.0"` on
a row that was never admitted. The finding is the overstated comment, not the regex.

### 5.2 The write side does not apply the check the read side gained

`build()`'s `previous` is caller-supplied and **entirely unvalidated** — `manifest.py:161-165` requires
only that `admitted_against` be truthy. Executed:

```python
build([admit(tool("book_list")), admit(tool("book_get"))],
      previous={"declarations": [{"id": "book_list", "admitted_against": "banana"},
                                 {"id": "book_get",  "admitted_against": 7}]})
# -> rows carry "banana" and the integer 7
```

`load()` then refuses the document `build()` produced. `generate()` is protected only incidentally,
because it sources `previous` from `load()`; the exported `build()` (`__init__.py:37`) is not.
`admission.py:35-37` states layer 3 as *"the writer re-runs the contract on every row it writes and
the reader on every row it loads."* For the stamp, only the reader does.

---

## 6 · Question 5 — other values fixed by the build rather than by the thing being written

Enumerated over every value the package writes or defaults.

| value | `file:line` | ruling |
|---|---|---|
| `admitted_against`, **new** row | `manifest.py:130` → `admitted.contract_version` → `check_contract`'s only success return | **Not P4's shape.** One terminal condition: every row admitted during one build genuinely was checked against that build's contract. The constant becomes information the moment it is frozen into the file. |
| `admitted_against`, **existing** row | `manifest.py:130`, `carried` branch | **A defect, but the opposite one.** Bound to the file's previous content rather than to the admission being written; the live `admitted.contract_version` is discarded. §3.3. |
| doc-level `contract_version` | `manifest.py:177` | Document-scoped and correct — it *is* the build's version. But **unvalidated on read**: executed, `contract_version: "banana"` and a missing/`99` `manifest_version` all pass `validate_document`. Caught today only because the drift gate demands byte-equality with `build([])`; that equality does not survive CP-4. |
| `manifest_version` | `manifest.py:176` | One terminal condition (one format). Not P4. Unvalidated on read, as above. |
| `_empty()` | `manifest.py:202-205` | **Unchanged since round 6.** A missing manifest is reported as `{manifest_version: 1, contract_version: <current>, declarations: []}` — the running build's constants asserted about an artifact that does not exist, and a reader cannot tell "no manifest" from "an empty manifest this build produced". One terminal condition, so not P4's classic shape; it is the same instinct. |
| `lifecycle=r.get("lifecycle", "draft")` | `manifest.py:254` | **Unchanged since round 6, and confirmed live.** Executed: a row with **no** `lifecycle` key passes `validate_document`, and the document is returned *with the key still missing* — so the default is supplied by the validator for the duration of the check and by nothing at all thereafter. C-0 names lifecycle state as part of identity; a row can omit it and be admitted on read. This is the P4 shape at the read half of the same boundary: a column value fixed by the code rather than by the thing being validated. `lifecycle` has no reader in `surface.py`, which is why nothing has noticed. |
| `source_path=f"services/{owning_service}/"` | `manifest.py:253` | A synthesised path for re-derivation, not a stored value. Correctly rejects a row naming an underivable owner. Not P4. |
| `owning_service` | `manifest.py:108` → `identity_of` → `derive_owning_service` | Derived from the row's own data every time, including on re-admission (executed: it updates when the source path changes, while the stamp does not). Correct. |

---

## 7 · Bypass table — P4 half only

| what P4 asserts | the path that defeats it |
|---|---|
| the stamp can differ between rows | **none in `build()`/`generate()`** — executed across an amendment against a real file; two stamps, two values. Searched by driving the public API, not by reading it. |
| the stamp records what *this* admission checked against | `manifest.py:130` — `carried` shadows `admitted.contract_version` for any id already in the file, permanently and unconditionally. |
| §6.4's queue is derivable from the file alone | derivable, yes. **Non-drainable** — §3.3. And erasable in one ordinary operation — §3.4. |
| the mechanism is defended | `manifest.py:192` — **no test exercises it**; both `generate()` call sites in the suite use a fresh `tmp_path`. Removing the argument leaves 89/89 green (REGRESS=A). |
| the stamp is validated | `manifest.py:264` — shape only; `"99.0.0"` and `"0.0.0"` accepted. The write end applies no stamp check at all (§5.2). |

---

## 8 · Method

* `git rev-parse HEAD` before and after: `1ab136b1c16c68a3889ddaab932343e11b3f58c1`, unchanged.
* Read: `manifest.py`, `contract.py`, `admission.py`, `ambient.py`, `__init__.py`,
  `scripts/agentruntime-membrane-gate.py` (`_manifest_drift`), `ARCHITECTURE.md` §6.4,
  `tests/test_cp1_membrane.py`.
* Executed: a probe driving `generate()` / `build()` / `load()` / `validate_document` against temp
  paths across a simulated amendment (both bindings of `CONTRACT_VERSION` rebound); a re-admission
  sequence including a materially changed declaration; a fresh-target regeneration; the full stamp
  input matrix; the `previous=` poisoning case.
* Red-ability: four regressions injected via an out-of-tree pytest plugin at `pytest_configure`,
  rebinding the callables before test collection. Baseline and all four runs recorded in §4. **No
  tracked file was edited**, and no injected change was reverted with `git checkout`.
* Not run: the live system, per the standing prompt.
