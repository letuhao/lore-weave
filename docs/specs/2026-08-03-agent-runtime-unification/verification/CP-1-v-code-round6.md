# CP-1 · V-CODE round 6 — item 1.4, P4 half only

**Artifact:** `96b910aa045309fc01653cf41daea50968486da3`. Verified with `git rev-parse HEAD` before
starting and again before writing this verdict — **unchanged**. No tracked file was edited; every
revert and amendment below was executed against a copy of the tree in a scratch directory
(`git status` over `services/chat-service`, `contracts/`, `scripts/` and this spec directory is
clean apart from this file).

**Scope:** item 1.4's P4 half — *no instrument column is bound to a constant at any INSERT* — and
the two tests that arrived with it. 1.1, 1.2, 1.3, 1.5, 1.6, 1.7 and 1.4's M4 half are not re-graded.

**Change under audit:** `git diff c90837da0..HEAD -- services/chat-service/` — three files, 66 added
lines, of which 42 are comment and docstring. The functional change is one dictionary entry.

---

## 1 · Verdict

| | |
|---|---|
| **1.4 · P4 half** | **FAIL** |

The reported violation was real and the diagnosis of *where* it lives is correct — the manifest is
this checkpoint's write boundary and `_row` is its INSERT. The repair is not. **`admitted_against`
is bound to the same module constant that `contract_version` was bound to**; the only thing that
changed is *when* the constant is read — at `admit()` instead of at `build()`. In a single process,
and there is no other kind of process here, those are the same value. P4's subject exists, was
correctly located, and is still constant-bound.

The two tests are genuinely red-able (executed, below), but they are green over the residual defect
because the only condition that separates the two read times is a `monkeypatch` — a mutation of a
module constant mid-process that no production path performs and that the package's own design makes
otherwise impossible.

### The falsifier

What I looked for that would have made this a PASS:

1. **A row whose `admitted_against` differs between two rows of the same manifest, or between two
   manifests, without a test harness mutating a constant.** Executed: it does not exist. Every row of
   every manifest, in every process, carries `CONTRACT_VERSION` verbatim.
2. **A carrier that lets an admission decision outlive the process that made it** — so "checked
   against 1.0.0" can still be true when the build says 2.0.0. Executed: `Admitted` refuses
   `pickle`, `copy` and `deepcopy` by design, so admission and generation are necessarily
   same-process; the only durable carrier is the manifest file, and `generate()` overwrites it.
3. **A regeneration under an amended contract that preserves a prior row's stamp.** Executed against
   a source-edited copy: it does not.
4. **Any reader, anywhere, of `admitted_against`.** Searched the whole tree; there is none, and
   `validate_document` accepts the field absent, `null`, `"banana"` or `"99.0.0"` without comment.

Had any one of 1–3 held, the P4 half would have passed on the *mechanism* even with the test
weaknesses noted in §5.

---

## 2 · Every field written at the boundary, and what fixes its value

`_row` (`services/chat-service/app/agentruntime/manifest.py:101-127`) — executed, not read off:

```
row keys: ['admitted_against', 'id', 'kind', 'lifecycle', 'members', 'owning_service']
{"id":"book_get",    "kind":"tool",  "owning_service":"book-service", "lifecycle":"admitted", "admitted_against":"1.0.0", "members":[]}
{"id":"book_list",   "kind":"tool",  "owning_service":"book-service", "lifecycle":"admitted", "admitted_against":"1.0.0", "members":[]}
{"id":"world_setup", "kind":"skill", "owning_service":"chat-service", "lifecycle":"draft",    "admitted_against":"1.0.0", "members":["book_list","book_get"]}
```

| field | source | varies with the thing written? | correct? |
|---|---|---|---|
| `id` | `ident.id` ← `declaration.id` | **yes** | yes |
| `kind` | `d.kind` | **yes** | yes |
| `owning_service` | `identity_of` → `derive_owning_service(d.source_path)` | **yes** (`book-service` / `chat-service` above) | yes — and derived, per C-0 |
| `lifecycle` | `ident.lifecycle` ← `d.lifecycle` | **yes** (`admitted` / `draft` above) | yes |
| `members` | `list(d.members)` | **yes** | yes |
| **`admitted_against`** | `admitted.contract_version` ← `admit()` ← **`check_contract()` returns the module constant** (`contract.py:141`) | **NO — identical on every row of every manifest** | **no. This is the finding.** |

Document level, `build()` (`manifest.py:146-150`):

| field | source | varies? | correct? |
|---|---|---|---|
| `manifest_version` | `MANIFEST_VERSION` | no | **yes** — it is the schema version of the document this build writes, one value per document, reachable from one terminal condition |
| `contract_version` | `CONTRACT_VERSION` | no | **yes at this granularity** — it stamps the generator, which is a property of the build. It is also the *only* surviving half of §6.4's required pair (see §4) |
| `declarations` | the rows | yes | yes |

So exactly one field remains constant-bound where it should not be, and it is the one the diff was
written to fix.

### Why it is still constant-bound

`admit()` (`admission.py:117-118`) sets `Admitted.contract_version` from the return value of
`check_contract`, and `check_contract` (`contract.py:92-141`) has **one success return**:

```python
    return CONTRACT_VERSION            # contract.py:141
```

reached by every tool, skill and workflow, every lifecycle, every owner — i.e. from many terminal
conditions, which is precisely the discriminator P4 turns on. Executed:

```
CONTRACT_VERSION           = 1.0.0
check_contract() returns   = 1.0.0
Admitted.contract_version  = ['1.0.0']
row admitted_against       = ['1.0.0']
distinct values across rows: {'1.0.0'}
-> per-row value varies with the declaration? False
```

The fix moved the read of the constant one call earlier in the same call chain. The value did not
become evidence about a declaration; it became the same build constant, sampled sooner. The test at
`test_cp1_membrane.py:398` states this outright and treats it as a precondition:
`assert a.contract_version == _c.CONTRACT_VERSION`.

---

## 3 · Does `admitted_against` carry the version it was CHECKED against?

**No — not in any sense that survives the test harness.** The test establishes it with
`monkeypatch.setattr(_c, "CONTRACT_VERSION", "9.9.9")` between `admit()` and `build()`. Verified
independently what that mechanism actually rests on:

```
Admitted.contract_version (captured at admit) = 1.0.0
identity_of(d).contract_version (read at write) = 9.9.9
check_contract(d) called again now             = 9.9.9
```

Two separate accidents make the test green:

* `identity_of` reads `contract.CONTRACT_VERSION` as a module global **at call time**, while
  `manifest.py:28` did `from .contract import CONTRACT_VERSION` — an early value binding. The
  divergence the test observes is a difference in *import style* between two modules, not a recorded
  fact about a declaration. (`build()`'s own document-level `contract_version` stays `"1.0.0"` under
  the same monkeypatch, for that reason.)
* `check_contract` is re-read on every call, so "the version at admit time" is only ever "the value
  of a global at one moment", not a property of the declaration.

**Would it hold across processes or across time? No, and the package forbids the attempt:**

```
pickle:   TypeError: Admitted is not serialisable; re-admit from the declaration instead.
copy:     TypeError: Admitted is not copyable; it would duplicate an admission decision.
deepcopy: TypeError: Admitted is not copyable; it would duplicate an admission decision.
```

`Admitted.__reduce__` (`admission.py:90`) is a deliberate M4 defence, and its consequence here is
structural: an `Admitted` cannot leave the process that produced it, so **admission and generation
are always the same process**, and `admitted.contract_version` is always the constant that process
was built with. There is no admission ledger, no persisted decision, nothing else that carries an
admission across a build. The one carrier that does cross time is the manifest row itself — and the
next section is about what happens to it.

---

## 4 · Is §6.4's re-admission queue computable? No.

§6.4 (`ARCHITECTURE.md:1078-1093`) requires: *every declaration carries `contract_version` +
`admitted_against`*; a backward-compatible amendment leaves prior admissions standing; a **breaking**
one moves prior declarations into a re-admission queue *without removing them from the runtime*.

Executed the whole scenario on a scratch copy with `CONTRACT_VERSION` **source-edited** to `"2.0.0"`
(a real amendment, not a monkeypatch), starting from a manifest written by the 1.0.0 build:

```
stale file, queue = rows whose admitted_against != current: ['book_list']
after regeneration: [{"id":"book_list", …, "admitted_against":"2.0.0", …}]
queue after regeneration: []
```

The queue is non-empty for exactly as long as the manifest is stale — and the M1 drift gate makes
staleness a red build. Same copy, same amendment, gate run before regenerating:

```
FAIL: manifest drift - the committed file is not what the generator produces
     expected {'manifest_version': 1, 'contract_version': '2.0.0', 'declarations': []}
     found    {'manifest_version': 1, 'contract_version': '1.0.0', 'declarations': []}
agentruntime-membrane-gate: 1 violation(s)
```

`scripts/agentruntime-membrane-gate.py:239-285`, wired at `.github/workflows/lint-foundation.yml:94`.
So: amend the contract → CI reds → regenerate to green CI → every `admitted_against` is rewritten to
the new constant → **the queue is empty at every point where the build is green.** The condition the
builder's own comment describes as the consequence of the old code (*"the queue is permanently
empty — a migration that can never find work"*) is unchanged by the fix. It has moved from being
caused by the write expression to being caused by regeneration, which the drift gate compels.

**Stated plainly, what is still missing:**

1. **A value that can differ.** Nothing derives `admitted_against` from anything but the current
   build. Even a stale row survives only until the next `generate()`, and CI requires that call.
2. **A record that an amendment happened, and whether it was breaking.** There is no amendment
   ledger, no `breaking` flag, no semver comparison anywhere in the package — `CONTRACT_VERSION` is
   an opaque string, compared only with `==` and never parsed. `1.0.0 → 1.1.0` and `1.0.0 → 2.0.0`
   are indistinguishable to every line of code in `app/agentruntime/`. §6.4's rule keys entirely on
   that distinction.
3. **The second half of §6.4's required pair.** The table says *every declaration carries
   `contract_version` + `admitted_against`* — two per-declaration stamps, one current, one
   historical. The fix removed the per-row `contract_version` and left one, and
   `test_the_row_does_not_carry_a_write_time_constant_at_all` now *forbids* restoring it under that
   name. The document-level `contract_version` covers "current" at document granularity only; a
   per-row comparison has nothing to compare against inside the row. No note in the diff reconciles
   this with §6.4.
4. **A lifecycle state the queue could be expressed in.** §6.4 requires queued declarations to stay
   *in the runtime*. `LIFECYCLES` (`contract.py:26`) is `{draft, admitted, deprecated, retired}` —
   there is no state meaning "admitted, awaiting re-admission", so a queued declaration has nowhere
   to be recorded without either lying about its lifecycle or leaving the manifest.

A queue could be *derived* from the field's shape — `[r for r in rows if r["admitted_against"] !=
CONTRACT_VERSION]` type-checks and runs. It returns `[]` on every manifest this system can produce.

---

## 5 · Are the two tests red-able, and are they honest?

**Red-able: yes, both, executed.** Reverted `manifest.py:125` to `"contract_version":
ident.contract_version` in a scratch copy of the tree and ran the class:

```
FAILED …::test_a_row_records_the_version_it_was_ADMITTED_against       — KeyError: 'admitted_against'
FAILED …::test_the_row_does_not_carry_a_write_time_constant_at_all     — AssertionError: 'contract_version' in {...}
2 failed, 67 deselected
```

Baseline at HEAD: `69 passed` for the whole file, `2 passed` for the class; the membrane gate is
green (`selftest OK — fires on 7 import shapes + 3 forgery shapes`).

**Could either pass over a wrong fix?** Injected both shapes the prompt names, separately:

| injected wrong fix | test 1 | test 2 | caught? |
|---|---|---|---|
| `"admitted_against": ident.contract_version` — right name, write-time constant | **FAIL** | pass | yes, by test 1 |
| `"admitted_version": admitted.contract_version` — right value, wrong name | **FAIL** (KeyError) | pass | yes, by test 1 |
| field removed entirely | **FAIL** (KeyError) | pass | yes, by test 1 |

So the pair is not trivially defeated by a mis-named or mis-sourced field. Test 2 alone is a pure
shape assertion (`"contract_version" not in row`) and passes over every one of the above; it is
load-bearing only as a regression latch against re-adding the old key.

**Where they are not honest:**

* **Neither reads the value back.** Both assert on the in-memory dict from `build()`. Nothing in
  either test calls `generate()` → `load()`, and nothing anywhere validates the field —
  `validate_document` (`manifest.py:200-236`) constructs its probe `Declaration` from `id`, `kind`,
  `owning_service`, `lifecycle`, `members` and never looks at `admitted_against`. Executed against
  the real package:

  ```
  field absent   : ACCEPTED
  garbage value  : ACCEPTED   admitted_against = "banana"
  old field name : ACCEPTED   contract_version = "0.0.1-bogus"   (and no admitted_against at all)
  future version : ACCEPTED   admitted_against = "99.0.0"
  null           : ACCEPTED   admitted_against = null
  ```

  and through `load()` from disk, and through the exported `declarations()`. §6.1 layer 3 is
  described as existing because *"a row typed straight into the JSON was served to the assembler
  having passed no clause"* — for this field, that is still true. A hand-typed row claiming the
  current version is exactly the row a re-admission queue must not skip, and it is accepted.
* **Test 1 hardcodes `"1.0.0"`** rather than capturing `a.contract_version`. Executed on the copy
  with `CONTRACT_VERSION` source-edited to `"2.0.0"`: `test_a_row_records_the_version_it_was_
  ADMITTED_against` **fails** over correct code. The guard goes red on the very event it exists to
  instrument — a contract amendment.
* **The gate's subject does not occur at CP-1.** `_manifest_drift` compares the committed file to
  `build([])`, and with zero declarations the row shape is never constructed. The change to `_row`
  has no CI coverage outside these two tests; the drift gate would not have noticed it either way.
* **Vacuity (NV):** the condition test 1 constructs — two contract versions live in one process —
  is reachable *only* through `monkeypatch`, because `Admitted` cannot cross a process boundary and
  no production path mutates `CONTRACT_VERSION`. The test does not sample a rare real state; it
  manufactures the sole state in which the fixed code and the broken code differ. Per this run's own
  standard, a check whose subject cannot occur in production is a finding even when the code under
  it is correct.

---

## 6 · Did the fix introduce anything?

| surface | result |
|---|---|
| `validate_document` (`manifest.py:200-236`) | unaffected by the rename — it never read `contract_version` and does not read `admitted_against`. **A new field that nothing validates**, on the read end of the boundary whose docstring says every row is re-checked. |
| M1 drift gate (`scripts/agentruntime-membrane-gate.py:239-285`) | green. `build([])` still equals the committed `{"manifest_version":1,"contract_version":"1.0.0","declarations":[]}`; the gate never sees a row, so the shape change is invisible to it. Executed: gate passes at HEAD. |
| `load()` / `declarations()` / `rows_of()` | pass rows through untouched; no key lookup on either name. No breakage, no validation. |
| anything else reading a manifest row | searched the tree for `agent-runtime-manifest`, `LOREWEAVE_AGENT_RUNTIME_MANIFEST`, `contract_version` and `admitted_against`: the only code readers are `manifest.py` and the gate. There is no JSON schema for this contract in `contracts/`. No consumer broke. |

**Two things the fix did introduce:**

1. **`Identity.contract_version` is now dead** (`contract.py:73`, set at `contract.py:157`). Its only
   remaining production reader was `_row`. Grep for `identity_of` / `Identity(`: `manifest.py:100`
   uses `ident.id`, `ident.owning_service`, `ident.lifecycle` and nothing else; the sole surviving
   reference to the field is `test_cp1_membrane.py:443`,
   `assert ident.id and ident.owning_service and ident.lifecycle and ident.contract_version` — a
   truthiness assertion standing in for a value check. Round 2's finding was *"`Admitted.
   contract_version` remains a dead field"*. The fix made `Admitted.contract_version` live and made
   `Identity.contract_version` dead. The same dead field is present, one type over, with a docstring
   at `contract.py:147-151` explaining why it is kept.
2. **Four hand-built row fixtures now describe a row the writer cannot produce** —
   `test_cp1_membrane.py:113`, `:135`, `:284` (and the `planted` row in the M3 positive control) all
   carry `"contract_version": "1.0.0"` and no `admitted_against`, and all still pass. That is direct
   evidence for the point above: nothing on the read side distinguishes the old shape from the new.
   It is also this run's recurring erratum-not-applied-everywhere pattern, in the same commit that
   names it.

---

## 7 · The general question — the same error elsewhere in P4's scope

I swept every value-producing site in `app/agentruntime/` mechanically (AST walk over every `ast.Dict`
and every keyword argument in all six modules, classifying each value as a literal, a module-level
constant name, or derived) and then read the two shapes the AST sweep structurally cannot see —
`return` statements and `.get(k, default)` defaults. Results:

**Yes. The same error is one call further up, and it is what makes the fix ineffective.**

* **`contract.py:141` — `return CONTRACT_VERSION`.** This is `check_contract`'s only success return.
  It is reached from every terminal condition the function has — tool, skill and workflow; every
  lifecycle; every owner; members present or absent. By the discriminator P4 turns on (*a literal
  reachable from more than one terminal condition is the defect; one terminal condition is not*),
  **this is the defect**, and `_row`'s `admitted_against` merely relays it. The builder reasoned from
  where the property was expected to live — first "a DB INSERT", then "the manifest row" — and in
  both cases stopped at the write expression rather than following the value to its source. The
  value's source is a constant one frame away, and it always was.
* **`contract.py:157` — `Identity(contract_version=CONTRACT_VERSION)`.** Unchanged, now with no
  production reader; the docstring added at `contract.py:147-151` documents the constant rather than
  removing it.
* **`manifest.py:171-174` — `_empty()`.** Returns a document stamped `manifest_version` +
  `contract_version` for a file that **does not exist**. `load()` of an absent manifest therefore
  returns a document asserting conformance to the current contract with the current schema version,
  for an artifact nothing wrote. One terminal condition (file absent), so not P4's classic shape —
  but it is a build constant asserted about a nonexistent thing, and it is indistinguishable from a
  real empty manifest generated by that build. Verified by execution.
* **`manifest.py:222-224` — read-side defaults.** `lifecycle=r.get("lifecycle", "draft")` validates a
  row that names no lifecycle *as* `draft` and then serves the row still missing the key (executed:
  accepted, served as-is). `source_path=f"services/{r.get('owning_service','')}/"` reconstructs a
  path that never existed in order to re-derive an owner from it. Neither is P4, both are values
  supplied by the code rather than by the row.

**Clean, checked and reported as such:** `surface.py:238` binds `stage="discovery_kind_filter"` as a
literal, but that stage is reachable from exactly one terminal condition (the kind filter's else
branch) and its `reason` is formatted from the row's actual kind — correct by P4's own
discriminator. `_narrow` takes `stage`/`reason` from the rule and `pass_number` from its argument;
`Narrowing.as_record()` has constant *keys* and no constant values; `Surface(...)` derives all three
fields. `manifest.py`'s remaining literals are `encoding`, `indent`, `ensure_ascii`, `parents`,
`exist_ok` — I/O options, not instrument values.

---

## 8 · Bypass table

| claim | path that defeats it, or the search that found none |
|---|---|
| *no instrument column is bound to a constant at the write boundary* | **`manifest.py:125` → `admission.py:117` → `contract.py:141`.** `admitted_against` is `CONTRACT_VERSION`, read one call earlier. Executed: identical on every row of every manifest. |
| *a row records the version it was CHECKED against* | **`contract.py:141` is re-read on every call**, so "at admit time" means "the global's value at that instant", and `admission.py:90` (`__reduce__` raises) makes admission and generation necessarily same-process. Executed all three round-trip refusals. |
| *§6.4's re-admission queue is now computable* | **`scripts/agentruntime-membrane-gate.py:239-285` + `manifest.py:159-168`.** The drift gate reds until the manifest is regenerated, and regeneration rewrites every stamp to the current constant. Executed on a source-amended copy: queue `['book_list']` before, `[]` after. Plus: no breaking/compatible signal exists anywhere, and `LIFECYCLES` has no queued state. |
| *the new tests are red-able* | **No defeating path — confirmed by execution**, not by reading. Reverted the fix in a scratch copy: both fail. Injected two wrong fixes: test 1 catches both. |
| *the new tests are honest* | **`manifest.py:200-236` never reads the field**, and neither test round-trips through `generate()`/`load()`. `test_cp1_membrane.py:402` hardcodes `"1.0.0"` and reds on a genuine amendment (executed). Test 1's subject exists only under `monkeypatch`. |
| *the fix broke no reader* | **Searched and found none.** Whole-tree grep for `agent-runtime-manifest`, the env override, `contract_version` and `admitted_against`; the only code touching manifest rows is `manifest.py` and the gate; no schema file exists in `contracts/`. Four test fixtures still use the removed name and pass, which is itself the evidence. |

---

## 9 · The honest statement

The builder's correction of *where* P4 applies is right, and it is the harder half of the problem:
the manifest is a write boundary and "there is no DB INSERT" was not a reason to stop looking. What
did not follow is the second step. `admitted_against` is not the version a declaration was checked
against; it is the build's own constant, read at `admit()` instead of at `build()`, and there is no
process in which those two moments can carry different values. The property P4 states — *an
instrument column must record something the writer measured, not something the writer is* — is not
yet true of any field in this manifest.
