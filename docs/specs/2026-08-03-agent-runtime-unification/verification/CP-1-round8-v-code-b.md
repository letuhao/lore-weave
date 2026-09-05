# CP-1 · round 8 · V-CODE — Verifier B, item 1.4's P4 half

**Artifact:** `73241817cb7424069862e9ea2df9db09b8b4e35a` — `git rev-parse HEAD` verified at start and
again immediately before writing this file; unchanged. No tracked file was modified. Nothing was run
against the live or deployed system. No `git checkout` was run on any file.

**Scope:** item 1.4's P4 half only — *no instrument column is bound to a constant at the write
boundary* — the four grounds round 7 returned FAIL on, and the tests that arrived with the current
fix. Verifier A's items are not touched.

**Baseline, measured here:** `python -m pytest tests/test_cp1_membrane.py -q` from
`services/chat-service` → **98 passed, 1 warning**.

---

## 1 · Verdict

| item | verdict |
|---|---|
| **1.4 · P4 half** | **FAIL** |

Two of round 7's four grounds are genuinely closed, and the closure is real work, executed and
confirmed: `generate()`'s carry now has a test that dies when the argument is deleted (round 7's
headline finding — **REGRESS=A now reds**), and the write side validates `previous` (**REGRESS=D
reds**). The `"99.0.0"` overstatement is corrected in place rather than papered over. §6.4.1 is a
real improvement to the spec: it names two fields, defines them, and marks a clause UNBUILT.

It fails on one ground that subsumes the rest, and it is **P4's own shape, for the fourth time, on
the field the fix was built around**.

> **`admitted_against` is bound to the write-time module constant, and the queue it computes is the
> empty set by construction.**

`row.admitted_against` ← `admitted.contract_version` ← `admit()` → `check_contract()` → **`return
CONTRACT_VERSION`**. `doc.contract_version` ← `manifest.CONTRACT_VERSION`, the same literal imported
by name. §6.4.1 defines the queue as `admitted_against != <document contract_version>`. Both sides of
that comparison are the same module constant read inside one process, so the predicate is
**unsatisfiable**.

Measured, not argued:

* 500 randomised in-process `build()` calls with randomised `previous` origins: **0/500 produced a
  non-empty queue**; the set of `admitted_against` values ever emitted is **`{'1.0.0'}`** — character
  for character the measurement that condemned the *first* fix in round 6 (*"a verifier printed
  `{'1.0.0'}` across all of them"*).
* A real three-generation sequence through `generate()` against **one** path across a breaking
  amendment: `QUEUE = []` at gen1, `QUEUE = []` at gen2, `QUEUE = []` at gen3 (§3).
* **REGRESS=E** — `_row` writes `"admitted_against": CONTRACT_VERSION`, the round-6 defect verbatim
  moved one field over — leaves **98/98 green** (§6). The suite cannot distinguish the shipped code
  from the defect it was written to reject, because in production **there is no difference**: the two
  expressions cannot take different values (§3.3).

Round 6 rejected *"the constant read moved one call earlier"* as a non-fix. `admitted.contract_version`
**is that same expression**. The field that changed behaviour is `contract_version`, the one §6.4.1
says **never moves**; the field that must move, and on which the whole work-list claim rests, still
cannot.

Three further findings, each independently sufficient:

2. **The queue can drain but cannot fill.** A declaration not re-admitted is *absent* from the next
   manifest, not queued — which is the UNBUILT half. So the only reachable queue state is empty
   (§3.2). The one test that shows a non-empty queue **appends the row by hand** after `build()`
   returns, and stays green with the entire origin-carry mechanism removed (**REGRESS=B**) (§6.2).
3. **`bootstrap=` gates a door that is not the one people walk through.** It is on `generate()`,
   which has **zero call sites outside the test suite**. The exported `build()` still defaults
   `previous=None` with no gate, and `build([])`-with-no-previous is the *only* shape any code in
   this repository actually calls (`scripts/agentruntime-membrane-gate.py:365`). A file that exists
   with `"declarations": []` also walks straight past the flag (§5).
4. **A manifest written by the previous version of this code cannot be read at all**, and there is
   no recovery that is not the erasure `bootstrap=` exists to prevent (§7.2).

---

## 2 · The falsifiers, stated before the search

| # | falsifier — what would make the claimed fix FALSE | how I searched | outcome |
|---|---|---|---|
| **F1** | The queue cannot reach a non-empty state through any code path, so "it drains" is untestable | drove `generate()` three generations against one path across an amendment; then 500 randomised `build()`s | **CONFIRMED.** 0/500 non-empty; queue `[]` at every generation |
| **F2** | `admitted_against` is still a constant — it just reads it through one more attribute | traced the expression to its terminal; injected the literal constant (REGRESS=E) and ran the suite | **CONFIRMED.** 98/98 green; `{'1.0.0'}` across all rows |
| **F3** | `contract_version` is not the ORIGIN — some ordinary operation resets it | absent-for-one-generation, `bootstrap=True`, bare `build()`, empty-`declarations` file | **CONFIRMED.** Four routes, three ungated |
| **F4** | The mechanism is still unguarded — round 7's REGRESS=A is still green | repeated A plus seven more injections through an out-of-tree plugin | **FALSIFIED.** A now reds. This ground is genuinely closed |
| **F5** | The write-side `previous` validation does not reject what a real corrupt file carries | ten malformed `previous` shapes through the exported `build()` | **CONFIRMED (partial).** Five accepted, three raise the wrong exception type |
| **F6** | Rejecting makes a legitimate operation impossible | replayed round-5-format and round-7-format manifests through `load()` / `generate()` | **CONFIRMED.** Both are unreadable and unrecoverable without erasure |

Had F1 and F2 both come back clean, this would have been a PASS on the P4 half notwithstanding F3,
F5 and F6.

---

## 3 · Question 1 — does the queue DRAIN, and can it also FILL?

Executed against one temp path, `CONTRACT_VERSION` rebound in **both** modules that bind it by name
(`contract.py:20` and `manifest.py:29`'s `from .contract import CONTRACT_VERSION`).

### 3.1 The real sequence

```
gen1 @ 1.0.0 (bootstrap=True) : admit book_list, book_get
    book_get   origin='1.0.0'  admitted_against='1.0.0'
    book_list  origin='1.0.0'  admitted_against='1.0.0'      QUEUE = []

--- contract AMENDED to 2.0.0 (breaking) ---

gen2 @ 2.0.0 : re-admit book_list ONLY (book_get not offered)
    book_list  origin='1.0.0'  admitted_against='2.0.0'      QUEUE = []
    book_get present in file? False

gen3 @ 2.0.0 : re-admit BOTH
    book_get   origin='2.0.0'  admitted_against='2.0.0'      QUEUE = []
    book_list  origin='1.0.0'  admitted_against='2.0.0'      QUEUE = []
```

**Drain: yes.** `book_list`'s `admitted_against` moves 1.0.0 → 2.0.0 on re-admission while its origin
holds at 1.0.0. That is real, it is new this round, and it is what round 7's ground 2 asked for.

**Fill: no, by any path.** Two independent reasons, and each alone is fatal:

* **The un-re-admitted declaration is gone, not queued.** `book_get` is simply absent from gen2. This
  is §6.4.1's UNBUILT clause showing up as the reason the mechanism has no subject — see §8.
* **Even a carried row could not queue**, because every row `_row` writes takes `admitted_against`
  from the same constant the document header takes `contract_version` from. §3.3.

### 3.2 gen3 is a second finding on its own: the origin was ERASED

`book_get` originated in 1.0.0. It sat out **one** regeneration. On its return it reports
`origin='2.0.0'`. So `contract_version` does not record the generation a declaration originated in —
it records *the oldest generation in an unbroken chain of consecutive presence in the file*. And the
operation that breaks the chain is precisely the operation §6.4 says must **queue** the declaration
rather than drop it. The UNBUILT half is not adjacent to the origin field; it is the thing that
destroys it.

### 3.3 The queue predicate is unsatisfiable — brute-forced

```
500 randomised in-process builds, randomised `previous` origins, no module patching
  builds with a NON-EMPTY queue: 0/500
  distinct admitted_against values ever emitted: {'1.0.0'}
```

The only way to make the two sides differ is to hold an `Admitted` across an amendment. Executed:

```
held.contract_version = '3.0.0' ; contract amended to 4.0.0 ; build([held])
  -> admitted_against='3.0.0', doc contract_version='4.0.0', QUEUE = ['book_list']
```

— and that is unreachable in production, executed both ways:

* `CONTRACT_VERSION` is a module-level literal; `git grep 'CONTRACT_VERSION *='` over
  `services/chat-service/app` and `scripts` returns exactly **one** line, `contract.py:20`. Nothing
  assigns to it. It cannot change within a process.
* An `Admitted` cannot cross a process boundary: `pickle` → `TypeError`, `copy` → `TypeError`,
  `deepcopy` → `TypeError` (by design, `admission.py:90-97`).

So `admit()` and `build()` always read the same value, and **for every document `build()` emits in
production the queue is `[]` by construction.** This is a stronger statement than round 7's: round 7
found the queue permanently *non-empty*; round 8 has returned it to permanently *empty*, which is the
original round-6 outcome, reached by a different route.

---

## 4 · Question 2 — is `contract_version` genuinely the origin?

**Can a row's origin change?** Four routes, executed:

| route | result | gated? |
|---|---|---|
| absent from `admitted` for one regeneration, then re-admitted | `1.0.0` → **`2.0.0`** | **no gate at all** |
| `generate(..., bootstrap=True)` on a fresh path | every origin = live constant | by the flag (§5) |
| exported `build(admitted)` with `previous` omitted | every origin = live constant | **no** |
| existing file whose `declarations` is `[]` | every origin = live constant | **no** (§5) |

**Two rows with different origins AND different admissions?** Yes on the document, no from the
writer. `build()` will emit `{'book_list': ('0.5.0', '1.0.0')}` when fed a `previous` naming an older
origin — but `admitted_against` is the live constant on every row it writes, so the *second* axis
only ever varies in a document that something other than `build()` assembled. A four-distinct-stamp
document (`('0.5.0','1.0.0')` + `('0.1.0','0.1.0')`) passes `validate_document` — the shape is
representable; the writer cannot produce it.

**Origin NEWER than admission?** Yes, and **nothing rejects it**:

```python
build([admit(tool("book_list"))],
      previous={"declarations": [{"id": "book_list", "contract_version": "9.9.9"}]})
# -> {'book_list': ('9.9.9', '1.0.0')}
validate_document(...)  -> ACCEPTED
load(path=...)          -> ACCEPTED
```

A declaration claiming it originated in a generation newer than the one it was last checked against
is arithmetically impossible, and it survives the writer, the reader and the round trip. Both stamps
are validated **independently for syntax**; their relationship — the only thing that makes them a
pair — is checked nowhere. §6.4.1 says the pair exists *because* one moves and one does not; nothing
enforces the ordering that statement implies.

---

## 5 · Question 3 — the way around `bootstrap=`

`bootstrap=` does work for the case it names: `generate()` on an absent path raises `UntrustedRow`
and writes nothing (confirmed; **REGRESS=F** reds when the gate is removed). Four ways past it,
executed:

| bypass | result |
|---|---|
| **the exported `build()`** — `previous: dict \| None = None`, in `__all__` (`__init__.py:62`) | every origin restamped, **no flag, no gate, no test** |
| **the only real caller in the repo** — `scripts/agentruntime-membrane-gate.py:365` computes `expected = build([])` | the exact ungated shape; round 7 named it and it is unchanged |
| **a file that exists but is empty of rows** — `{"manifest_version":1,"contract_version":"1.0.0","declarations":[]}` | `generate()` **WROTE**, every origin reset to the live constant. `bootstrap` not passed |
| **a file containing only `{"declarations": []}`** (no `manifest_version`, no `contract_version`) | `generate()` **WROTE**, every origin reset. Doc-level fields are unvalidated, so this is a legal manifest |
| **per-row**: any id present in the file but absent from `previous.declarations` | origin reset for that row alone, **ungated by construction** — the flag is all-or-nothing, the erasure is per-row |

Two shapes *do* stop: a zero-byte file raises `JSONDecodeError` (not `UntrustedRow` — a caller
catching the package's own exception type does not catch it), and `null` raises `UntrustedRow`.

**The load-bearing point:** `generate()` has **zero call sites outside `tests/`**. `grep` over
`services/chat-service` excluding tests finds only its own definition. The flag guards a door nobody
opens, while the door everyone opens — `build()` — kept the fail-open default. This is the
correction-applied-to-one-member-of-a-set shape, at full size.

---

## 6 · Question 4 — red-ability, by the shape that will occur

Eight regressions injected through an **out-of-tree pytest plugin** that rebinds the callables at
`pytest_configure`, before the test module is collected and therefore before its
`from app.agentruntime import build, generate, …` executes. Both `app.agentruntime.manifest.<name>`
and `app.agentruntime.<name>` are rebound so `generate()`'s internal call and the test's imported
name both see the injection. **No tracked file was edited and nothing was reverted.**

**Baseline: 98 passed.**

| inj | what it models | result | test that fired |
|---|---|---|---|
| **A** | `generate()` drops `previous=` — round 7's headline finding, the production write path reverting | **1 failed / 97** | `test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE` |
| **B** | `_row` ignores the carried origin — every row restamped | 3 failed / 95 | `…different_stamps`, `…queue_DRAINS…`, `…REAL_WRITE` |
| **C** | `validate_document` loses the stamp block — round 6's read side | 1 failed / 97 | `test_BOTH_stamps_are_VALIDATED_not_merely_present` |
| **D** | `build()` drops the write-side validation of `previous` | 1 failed / 97 | `test_the_WRITE_side_validates_previous_too` |
| **E** | **`admitted_against` bound to the write-time module constant — P4's named defect, verbatim, on the field §6.4.1 calls "always the live value"** | **98 passed — GREEN** | — |
| **F** | the `bootstrap` gate removed — the fail-open erasure restored | 1 failed / 97 | `test_a_MISSING_manifest_is_not_permission_to_restamp` |
| **G** | both stamps frozen from the file — round 7's non-draining queue | 3 failed / 95 | `…queue_DRAINS…`, `…NOT_re_admitted`, `…REAL_WRITE` |
| **H** | the ORIGIN column restated as the write-time constant | 3 failed / 95 | `…different_stamps`, `…queue_DRAINS…`, `…REAL_WRITE` |

### 6.1 E is the finding

E is not merely undetected — it is **behaviourally identical to the shipped code in production**, per
§3.3. That is the whole problem: the builder's fix and the defect the fix rejects differ only in
which name the same constant is read through. The suite cannot tell them apart because there is
nothing to tell apart. Rounds 6 and 7 both condemned exactly this, in the builder's own words at
`manifest.py:167-170`:

> *the constant read moved one call earlier and that was called a fix … Same constant, same value on
> every row. **A field that cannot differ between two rows records nothing about either.***

`admitted_against` cannot differ from the document header it is compared against. It records nothing.

### 6.2 `test_the_queue_names_exactly_the_rows_that_were_NOT_re_admitted` is still vacuous

Round 7 called this test vacuous. The rewrite removed the `or`-disjunction — a real improvement — but
**kept the hand-built row**, moved from a mutation to an append:

```python
after = build([admit(_tool("book_list"))], previous=first)
after["declarations"].append({**[r for r in first["declarations"] if r["id"] == "book_get"][0]})
queue = sorted(... if r["admitted_against"] != after["contract_version"])
assert queue == ["book_get"]
```

The only queued row is the one the test appended. Measured: the test is **green under REGRESS=B**
(origin-carry removed entirely) and **green under REGRESS=E** (the P4 defect). Its docstring says it
derives *"from a document that genuinely holds two generations — not from a fixture this test mutated
three lines earlier"*; the document holds two generations because the test put the second one there
three lines earlier. It is the standing rules' *fixture it mutated itself*, and it is the only test
in the class that claims a non-empty queue.

### 6.3 Per-test ruling

| test | red-able by the occurring shape? | can it pass over the defect it names? |
|---|---|---|
| `test_two_rows_CAN_carry_different_stamps` | yes (B, H) | no — genuine gate on the origin half |
| `test_the_queue_DRAINS_when_a_declaration_is_RE_ADMITTED` | yes (B, G, H) | **yes — green under E.** It asserts `admitted_against == "2.0.0"`, which the write-time constant also satisfies |
| `test_the_queue_names_exactly_the_rows_that_were_NOT_re_admitted` | **no** — green under B and E | **yes.** Hand-appended fixture; §6.2 |
| `test_generate_CARRIES_THE_ORIGIN_ACROSS_A_REAL_WRITE` | **yes (A)** — round 7's ground 1, closed | its `admitted_against` assertion is `{"2.0.0"}`, also green under E |
| `test_a_MISSING_manifest_is_not_permission_to_restamp` | yes (F) | yes for the empty-`declarations` file, which it does not cover (§5) |
| `test_the_WRITE_side_validates_previous_too` | yes (D) | yes for five shapes it does not cover (§7) |
| `test_BOTH_stamps_are_VALIDATED_not_merely_present` | yes (C) | executes the real validator; sound for what it covers |
| `test_the_row_carries_BOTH_fields_because_ONE_of_them_cannot_move` | **shape only** — asserts both keys equal `CONTRACT_VERSION` on a first build | yes — green under E and under every constant-binding defect. Its own docstring concedes *"on a first admission the two coincide"* |

---

## 7 · Question 5 — the write-side validation

### 7.1 Does `build()` reject everything a real corrupted manifest could carry?

Ten shapes through the exported `build()`:

| `previous` shape | result |
|---|---|
| a list / a string / an int | **`AttributeError: 'list' object has no attribute 'get'`** — the wrong exception type; `(previous or {}).get(...)` is unguarded. A caller catching `UntrustedRow` does not catch this |
| `declarations` a dict, or a string | `UntrustedRow` ✔ (by accident — the message says "has no id") |
| row with `admitted_against: 7` | **ACCEPTED** (not carried, so never checked — harmless today, and a trap the moment anyone carries it) |
| **duplicate ids, second one arbitrary** | **ACCEPTED — the last wins silently.** `('8.8.8', '1.0.0')`. `build()` rejects duplicate ids in its *output* rows but not in `previous` |
| row `id` is the integer `5` | **ACCEPTED** — `r.get("id")` is truthy, so `origin[5]` is written and silently never matched |
| origin for an id that is not admitted | **ACCEPTED**, silently dropped |
| **round-7 format: `admitted_against` only, no row `contract_version`** | `UntrustedRow` — see 7.2 |

And the **doc-level** `contract_version` — the right-hand side of the queue predicate — is still not
validated at all, on either side:

```
validate_document, contract_version='banana'  -> ACCEPTED
validate_document, contract_version missing   -> ACCEPTED
validate_document, manifest_version=99        -> ACCEPTED
validate_document, manifest_version missing   -> ACCEPTED
queue over a doc whose contract_version is 'banana': ['book_list']  <- every row queued, from an unvalidated field
```

Both *operands* of §6.4's mechanism are now validated per row; the *comparand* is not. The one
unvalidated field is the one that can silently move the whole queue.

### 7.2 Does rejecting make a legitimate operation impossible? **Yes — upgrade.**

| a manifest written by | `load()` | `generate()` | `generate(bootstrap=True)` |
|---|---|---|---|
| **round 7's code** (`admitted_against` only) | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` — the flag is ignored because the file **exists** |
| **round 5's code** (row `contract_version` only) | `UntrustedRow` | `UntrustedRow` | `UntrustedRow` |

A manifest produced by the immediately preceding version of this very code is **unreadable and
unwritable**. `generate()` reads `previous` through `load()`, which raises before `build()` is
reached, so there is no path that upgrades the file in place. `bootstrap=True` does not help: it is
only consulted when the file is *absent*. The sole recovery is `rm` the manifest and pass
`bootstrap=True` — **the exact erasure `bootstrap=` was added to prevent**. The safety mechanism
forces the unsafe operation on every format change, and `manifest_version` — the field whose entire
job is to make a format change survivable — is unvalidated, unread, and unbranched-on.

---

## 8 · Question 6 — is §6.4.1's UNBUILT assignment to CP-4 honest?

**Honest in what it names. Dishonest in what it scopes, and the sentence two paragraphs above it is
false as built.**

*Honest:* the clause is stated plainly, in the right place, with the right mechanism (*"making it
stay requires the generator to carry rows that are not in `admitted`, and that changes what the M1
drift gate is comparing"*). That is correct and it is the first time this run has named it. CP-4 is
also the right home for the drift-gate rewrite.

*Not honest as scoped,* on three measured grounds:

1. **It is not one clause of the section — it is the only clause that can put anything in the
   queue.** Executed (§3.1): the un-re-admitted declaration is *absent*, and absence is the only
   outcome the writer has. Every other sentence in §6.4.1 describes what to do with a queue that
   `build()` cannot produce. Deferring it defers the mechanism, not a refinement of it.
2. **The adjacent sentence is false.** §6.4.1 states: *"The queue is `admitted_against != <document
   contract_version>`. It empties **exactly when** every declaration has been re-checked, which is
   the only behaviour that makes it a work list rather than a label."* Measured: it is empty
   **always** — 0/500 randomised builds, `[]` at all three generations of a real amendment
   sequence, and `{'1.0.0'}` as the entire value set of `admitted_against`. "Exactly when" is a
   biconditional; only one direction holds. By the section's own standard — *a label, not a work
   list* — what is built is a label. Marking one clause UNBUILT while the neighbouring clause
   overstates a mechanism the code cannot run is the failure §0.14 keeps repeating, inside the
   subsection written to end it.
3. **The justification is the reasoning the builder has already been wrong with, three times.**
   *"No amendment has occurred and the manifest is empty, so this has no subject today"* is the same
   move as *"P4 has no subject at CP-1 because the new runtime reaches no DB INSERT"*, which
   `manifest.py:125-127` and the test class docstring both record as an error. Emptiness is not
   absence of subject; §3.3 shows the queue is unsatisfiable **by construction**, not by
   circumstance, and that is a property of the code today, measurable today, and measured above.

**Ruling: a deferral of the half that makes the mechanism mean anything** — with an honest label on
it. The honest label is worth something and I am not discounting it; it is not worth a PASS, because
the thing shipped alongside it is a field that cannot differ from its own comparand, which is P4.

---

## 9 · Bypass table

| what the property asserts | the path that defeats it |
|---|---|
| no column is bound to a constant at the write boundary | **`manifest.py:149`** — `admitted_against` ← `admitted.contract_version` ← `check_contract()` → `return CONTRACT_VERSION`. Terminal condition: one. Value set across 500 builds: `{'1.0.0'}` |
| §6.4's queue is a work list that empties when the migration is done | **unsatisfiable** — both sides of the predicate are the same module constant read in one process. 0/500 non-empty. Searched by brute force and by tracing the expression to its terminal, not by reading |
| a breaking amendment queues prior declarations *without leaving the runtime* | the un-re-admitted row is **absent** from the next manifest. Disclosed UNBUILT (§8) |
| `contract_version` records the generation a declaration ORIGINATED in | one regeneration in which the declaration is absent resets it (`gen3: book_get origin='2.0.0'`, originated 1.0.0). Ungated |
| a missing manifest is not permission to restamp | `bootstrap=` covers `generate()`, which **has no caller**. Exported `build()` still defaults `previous=None`; `build([])` at `agentruntime-membrane-gate.py:365` is the only shape called anywhere; a file with `"declarations": []` walks past the flag; per-row erasure is ungated |
| both stamps are validated | per-row **syntax** only, independently. `"99.0.0"` and `"0.0.0"` still accepted (correctly disclosed now). The **document-level** `contract_version` — the comparand — accepts `"banana"` and accepts being missing |
| the write side re-runs the contract on every row it writes | `previous` as a non-dict raises `AttributeError`, not `UntrustedRow`; duplicate ids in `previous` silently last-wins; a non-string row id is accepted |
| the mechanism is defended by tests | **REGRESS=E — 98/98 green.** Round 7's REGRESS=A now reds: **that ground is genuinely closed** |
| a manifest can be read across a version change | **no.** Round-5 and round-7 formats are unreadable, unwritable, and unrecoverable except by `rm` + `bootstrap=True` |

---

## 10 · Sibling table

The recurring failure named in the prompt is a correction applied to one member of a set.

| fix shipped | the sibling I looked for | also fixed? |
|---|---|---|
| `contract_version` freed from the write-time constant (carried from `previous`) | **`admitted_against`, the other half of the same pair** | **NO** — it is the constant, and REGRESS=E is green |
| `generate()` gated by `bootstrap=` against a missing file | the exported **`build()`**'s own `previous=None` default | **NO** — ungated, in `__all__`, and the only shape any caller uses |
| ditto | a file that **exists** but carries `"declarations": []` | **NO** — writes, restamps everything |
| ditto | **per-row** absence from `previous` | **NO** — ungated by construction; the flag is all-or-nothing |
| `validate_document` validates both row stamps | the **document-level** `contract_version`, the queue's comparand | **NO** — `"banana"` and absent both accepted |
| ditto | `manifest_version` — the field a format migration would branch on | **NO** — unvalidated, unread, and §7.2 is the consequence |
| `build()` validates `previous`'s row `contract_version` | `previous` itself being a non-dict | **NO** — `AttributeError`, wrong type, escapes an `except UntrustedRow` |
| ditto | duplicate ids inside `previous` | **NO** — silent last-wins, arbitrary origin injectable |
| a test now covers `generate()`'s carry (round 7 ground 1) | a test covering `generate()`'s refusal on an existing-but-empty file | **NO** |
| ditto | a test covering the drift gate's `build([])` shape | **NO** — `agentruntime-membrane-gate.py:365` unchanged since round 7 |
| the queue test's `or`-disjunction removed | the **hand-built row** that is the test's only queued entry | **NO** — mutation became an append; green under B and E |
| the `"99.0.0"` overstatement corrected in the comment | `lifecycle=r.get("lifecycle", "draft")` (`manifest.py:313`), round 7 §6 | **NO** — executed: a row with **no** `lifecycle` passes `validate_document` and is returned with the key still missing |
| ditto | `_empty()` (`manifest.py:255-258`), round 7 §6 | **NO** — executed: an absent manifest is still reported as the running build's constants (`contract_version: '1.0.0'`) asserted about an artifact that does not exist |

---

## 11 · What would close this

Not prescriptive, and stated only because "the field cannot differ" invites the same one-call-earlier
move a fourth time. The queue's two operands must be able to disagree **without any module being
patched**: that means the comparison's right-hand side has to be something the row was not written
from — a version recorded in the document at the time of a *previous* write, or a check that runs on
**read** against the reader's live `CONTRACT_VERSION` rather than against a header the same `build()`
just wrote. As long as both sides come out of one `build()` call, no test and no injection can
distinguish a working mechanism from a constant, because there is nothing to distinguish.

---

## 12 · Method

* `git rev-parse HEAD` at start and immediately before writing: `73241817cb7424069862e9ea2df9db09b8b4e35a`, unchanged. `git status --porcelain` over `services/`, `scripts/`, `contracts/` and the spec's `ARCHITECTURE.md`: clean.
* Read: `manifest.py`, `contract.py`, `admission.py`, `ambient.py`, `__init__.py`, `scripts/agentruntime-membrane-gate.py` (`_manifest_drift`), `ARCHITECTURE.md` §6.4 + §6.4.1, `tests/test_cp1_membrane.py` (class `TestP4NoColumnIsBoundToAConstantAtTheWriteBoundary`), `CP-1-v-code-round7.md`, `CP-1-ROUND8-V-CODE-PROMPT.md`.
* **Executed**, against temp paths only, both bindings of `CONTRACT_VERSION` rebound: a three-generation `generate()` sequence across a breaking amendment on one path; a 500-iteration randomised satisfiability sweep of the queue predicate; the `Admitted` cross-boundary matrix (`pickle`/`copy`/`deepcopy`); four origin-erasure routes; five `bootstrap=` bypasses; ten malformed-`previous` shapes through the exported `build()`; the round-5 and round-7 manifest-format replays through `load()` and `generate()`; the document-level field matrix through `validate_document`; the `lifecycle` and `_empty()` siblings.
* **Red-ability:** eight regressions through an out-of-tree `pytest_configure` plugin, rebinding callables in both `app.agentruntime.manifest` and `app.agentruntime` before collection. Baseline **98 passed**, measured here. No tracked file edited; no `git checkout` run.
* Not run: the live or deployed system, per the standing prompt.
