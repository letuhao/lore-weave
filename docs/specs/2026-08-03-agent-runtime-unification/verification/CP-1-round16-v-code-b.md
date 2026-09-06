# CP-1 · round 16 · V-CODE · **Verifier B — the membrane**

**Artifact:** `d23ea559294ae2daa4fa1414d87b734d2e1e2479`
`git rev-parse HEAD` **at start:** `d23ea559294ae2daa4fa1414d87b734d2e1e2479`
`git rev-parse HEAD` **at finish:** `d23ea559294ae2daa4fa1414d87b734d2e1e2479` — **unmoved.**

**Graded delta:** `530ce3eff` against `cba800fa8`.
**Scope:** `services/chat-service/app/agentruntime/` (`contract.py`, `manifest.py`, `surface.py`),
`scripts/agentruntime-membrane-gate.py`, `services/chat-service/tests/test_cp1_membrane.py`.

**Method.** Every claim below was **executed**, never read. Injections were made in a fresh scratch
copy (`scratchpad/scratchtree/`, built from the working tree, not nested in a stale one) or by
patch-and-restore against an **md5-verified snapshot I took myself**. **No `git checkout` was used
at any point.** Every injection was verified live before its result was trusted — by
`inspect.getsource` on the *loaded* module, or by asserting the mutated text is present in the file
after the write. Final byte-exactness of all ten scope files was confirmed against the snapshot;
`git status` over the scope is empty.

**Baseline (pristine tree):** `123 passed` (`tests/test_cp1_membrane.py`); membrane gate **green**
(`selftest OK … 8 module(s), 0 allowed external import(s), 2 single-sited type(s)`).

---

## Verdicts

| # | claim | verdict |
|---|---|---|
| 1 | `check_row` at four doors, `check_document_rows` for the set; is there a fifth; does any path reach a consumer with a row `load()` would refuse? | **PASS on rows — FAIL on documents.** 4 row-readers, 4 `check_row` callers: the counts **match**. **0 of 23** row shapes diverge across all three doors (R15's nine classes are genuinely closed). But **5 of 9 document shapes** that `load()` refuses are **accepted** by `rows_of` → **B1**. And the consolidation is a **state, not a gate**: I added a fifth exported door and measured **123/123 green, gate green** → **B4** |
| 2 | The schema is closed to seven fields; **grade the cost**; verify the writer converts a late failure into an immediate one | **Builder's claim VERIFIED — but the cost is real, unnamed, and scheduled.** Counterfactual measured: with `check_row` on the writer, a new `_row` field fails at `contract.py:206` and **nothing is written**; without it, `generate()` **writes the bad row to disk** and it fails at the next `load()`. **But** `ROW_REQUIRED = frozenset(ROW_FIELDS)` admits no *optional* field, so growing the schema **bricks the existing manifest with no migration path** → **B2** |
| 3 | The exception hierarchy: is any caller's `except` catching more, or missing something? `UntrustedRow` becoming a `ValueError` is the half most likely to be wrong | **PASS on the `ValueError` half — FAIL at `build`.** Pre-delta `rows_of` raised a bare `ValueError` for a bad document; `UntrustedRow(ValueError)` keeps every caller's `except` working. **But** the new subclassing makes `manifest.py:234`'s `except UntrustedRow` swallow `ContractViolation` and re-raise it flat, **destroying C-12's structured fields** — verbatim the defect the same delta fixed 175 lines below → **B3** |
| 4 | The 5th TOCTOU claimed CLOSED; re-measure `build`'s `r.get("id")`/`r["id"]` split | **CONFIRMED CLOSED**, and the `id` split is **CLOSED too — narrower than the builder's own "still OPEN"**. `type(doc) is dict` refuses the lying subclass outright; the return is rebuilt from validated values. `build`'s reads are now **uniform-mechanism** (`r["id"]` ×3, no `.get()`) over a row pinned to exact `dict` by `check_row` one line above. Residual: safe *by an argument at a distance*, and the rebuild half is unguarded → **B7** |
| 5 | The P4 test now drives the queue through `generate()` as well as `build()`; verify it reds by **building the mechanism yourself**; check the `build()` half did not become the vacuous one | **PASS — verified at both landing sites.** I built §6.4's grandfathering twice and proved each live (fills to `['book_get']`, drains to `[]`). Variant A (in `build`) → test **RED**, and **both** halves non-empty. Variant B (in `generate()` only, §6.4.1's own named site, the one green for four rounds) → test **RED** via `generate()`. The `build()` half is **not** vacuous. Residual: the route loop **short-circuits**, so a rotted `build()` half is invisible → **B8** |
| 6 | Convergence, plus per changed line; is R15's closure rise a trend or a single point? | **8 findings (3 P / 1 A / 4 G); `introduced` = 3, down from 4 — and 1.1 per 100 changed lines against R15's 4.4.** Closure **~54%**, up from ~27%. **Two consecutive rises is not yet a trend**, and — as the prompt anticipates — **the answer is the same as last round's**, and I say so in §6 |

**Overall: FAIL** — on **B2** and **B3**, both production-reachable, both introduced by this delta.
This is nonetheless **by a wide margin the strongest delta of the series in this scope**: the row-level
consolidation is real and measured, and closure roughly doubled. §6 says so before the findings do.

---

## Falsifiers, stated before the search

| claim | what would have falsified it |
|---|---|
| 1 | a row-reader with no `check_row` call; a row accepted at one door and refused at another; a new door passing both suite and gate |
| 2 | a field added to `_row` that reaches disk; **or** a legitimate forward path (CP-2 `relevance`, CP-4 `lane`/`tier`/`cost`) that the closure breaks late |
| 3 | an `except` clause whose catch set changed; a door whose refusal class regressed |
| 4 | a plain-JSON or subclass vehicle that answers the validator and the consumer differently |
| 5 | the test staying green with a working §6.4 mechanism at *either* landing site; or either half being true for free |
| 6 | `introduced` rising; closure falling; the per-line normalisation reversing the raw count |

---

## 1 — the count, and the fifth door

### 1a · ✅ the counts match, and the row half is genuinely closed

AST enumeration of every function in `app/agentruntime/` that reads a manifest row by field name:

| row-reading **door** (validates and hands rows on) | calls `check_row`? |
|---|---|
| `manifest._row` (the **writer**) `manifest.py:147` | ✅ |
| `manifest.build(previous=)` `manifest.py:233` | ✅ |
| `manifest.validate_document` `manifest.py:408` | ✅ |
| `surface.rows_of` `surface.py:71` | ✅ |

**4 doors, 4 callers — no difference.** The other nine row-key readers are either the check itself
(`check_row`, `check_row_shape`, `check_document_rows`) or strictly downstream of `rows_of`
(`AllowList.keep`, `DenyList.keep`, `OrderBy.sort`, `assemble`, `_narrow`, `discover`). Every
consumer entry point — `SurfaceAssembler.__init__`, `discover`, `declarations` — routes through
`rows_of`. `narrowing.py` reads no row field.

**Measured, not counted.** 23 row shapes driven through all three read doors in one process:

```
case                 rows_of              validate_document    build(previous=)
valid                ACCEPT               ACCEPT               ACCEPT
unknown kind         ContractViolation    ContractViolation    UntrustedRow
empty id             ContractViolation    ContractViolation    UntrustedRow
tool w members       ContractViolation    ContractViolation    UntrustedRow
extra field cost     ContractViolation    ContractViolation    UntrustedRow
extra relevance      ContractViolation    ContractViolation    UntrustedRow
missing stamps       ContractViolation    ContractViolation    UntrustedRow
bad stamp            ContractViolation    ContractViolation    UntrustedRow
non-string key       ContractViolation    ContractViolation    UntrustedRow
dict field           ContractViolation    ContractViolation    UntrustedRow
row-level accept/refuse divergences across 3 doors: 0
```

**R15's nine classes are closed.** `members: ['ghost']` — three rounds on the wire — is refused at
`rows_of` by `check_document_rows`. The empty `id`, the unknown `kind`, the unknown `lifecycle`,
the skill with no members, the tool with members, the missing stamps: all refused at every door.
**This round's structural premise held for rows.** It should be said plainly, and it is the reason
this verdict's convergence numbers are the best of the series.

### 1b · 🔴 **B1 — `rows_of` is still the weaker door, one level up**

The row half closed; the **document** half did not. Nine document shapes, same two doors:

| document shape | `rows_of` | `validate_document` / `load()` |
|---|---|---|
| no `manifest_version` | **ACCEPT** | UntrustedRow |
| `manifest_version: 999` | **ACCEPT** | UntrustedRow |
| `contract_version: "banana"` | **ACCEPT** | UntrustedRow |
| no `contract_version` | **ACCEPT** | UntrustedRow |
| undefined top-level key | **ACCEPT** | UntrustedRow |
| `declarations` missing / `None` / `{}` | UntrustedRow | UntrustedRow |
| `declarations: []` | ACCEPT | ACCEPT |

**5 of 9 divergent.** `SurfaceAssembler(manifest_doc)` and `discover(manifest_doc)` are both
exported, both take a raw document, and **neither goes through `load()`** — which is the exact
sentence R15 wrote about rows. `contract_version` is §6.4's queue comparand and `manifest_version`
is the format gate; a caller who does `SurfaceAssembler(json.load(f))` rather than
`SurfaceAssembler(load())` gets a catalog with neither checked. The signatures invite exactly that.

**Reachability: production-reachable at CP-2.** No module outside `app/agentruntime/` imports the
package today (verified by repo-wide grep), so nothing is broken *now* — but `SurfaceAssembler` and
`discover` are the two entry points CP-2 wires, and this is the door they stand behind.
**Guard: none.**

### 1c · 🔴 **B4 — the consolidation is a state, not a gate**

The four doors are policed by **four hand-written tests that name four doors**
(`…the_consumer_door_is_not_the_weaker_one`, `…THE_WRITER_CHECKS_ITS_OWN_OUTPUT__the_third_door`,
`…BUILD_PREVIOUS_USES_THE_SAME_DEFINITION__the_fourth_door`, `…AN_EXPORTED_DOOR_REFUSES_WITH_ONE_
DOCUMENTED_CLASS`). There is **no structural test** that enumerates row-readers and asserts each
calls `check_row`, and `scripts/agentruntime-membrane-gate.py` does not check it either (it gates
imports, ambient purity, forgery, single-sited `Admitted`/`Surface`, and manifest drift).

**Executed.** I appended a fifth door to `surface.py` and exported it in `__all__`:

```python
def summarise(manifest_doc: dict) -> list[str]:
    rows = manifest_doc.get("declarations") or []
    return sorted(f"{r['id']}:{r['kind']}" for r in rows)
```

It served `{'id':'x','kind':'gadget','cost':10**9}` — a row failing three clauses and the closed
schema — as `['x:gadget']`. Result: **`123 passed`** and **membrane gate green, exit 0**.

This is the same enumeration failure the module already records against itself: `discover`'s
narrowing path survived because the structural test "collected the *callers of* `log.record` rather
than the *places rows are removed*" (`surface.py:649-652`). The lesson was written down and not
applied to `check_row`. **Reachability: guard-only** — but it is the mechanism by which a fifth
door arrives uncaught, and CP-2/CP-4 add readers.

---

## 2 — the closed schema: the claim verified, the cost measured

### 2a · ✅ the builder's claim is TRUE, and the counterfactual proves the guard load-bearing

Injected `"lane": "hot"` into `_row`'s dict (injection verified live via `inspect.getsource`):

| | `_row` | `build` | `generate` | file written? |
|---|---|---|---|---|
| **with** `check_row(row,"row")` | `ContractViolation` @ `contract.py:206` | `ContractViolation` | `ContractViolation` | **no** |
| **without** (guard removed) | OK | OK | OK | **YES — bad row on disk**, fails at the next `load()` @ `manifest.py:415` |

The writer-side check converts a late failure into an immediate one, exactly as claimed, and
`build`'s `check_document_rows` does **not** independently catch it — `_row`'s `check_row` is the
only writer-side schema guard. **Claim 2's stated half: PASS.**

The four ranking fields are genuinely gone: `cost`, `relevance`, `lane`, `tier` are each refused at
all three doors (§1a). R15's headline finding — the file arguing the rule and shipping its four
exceptions in the same literal — is **closed**.

### 2b · 🔴 **B2 — the cost the builder measured in the wrong direction**

Q2 asks whether refusing an undefined field "breaks a legitimate forward path in a way that will be
discovered late". The builder answered by measuring the **writer**. The late failure is on the
**reader**, and it is worse than late — it has **no migration path**.

`ROW_REQUIRED = frozenset(ROW_FIELDS)` (`contract.py:184`) means the schema has **no optional
tier**: every declared field is mandatory. `contract.py:165-168` *schedules* the additions — "§0.14.1c
owns the producers: CP-2 for `relevance`, CP-4 for `lane`/`tier`/`cost`."

**Executed.** Wrote a manifest under today's 7-field schema, then added `relevance` to `ROW_FIELDS`
and to `_row` (injection verified: `'relevance' in ROW_FIELDS: True | in ROW_REQUIRED: True`) and
re-read the **same file**:

```
load()             -> ContractViolation: …declarations[0].relevance: is missing
rows_of()          -> ContractViolation: …declarations[0].relevance: is missing
SurfaceAssembler   -> ContractViolation: …declarations[0].relevance: is missing
```

The whole catalog is unreadable. `load()`'s own docstring promises a missing catalog reads as
**empty** — "the fail-safe direction, and the one that matters". A *schema-advanced* catalog does
not read as empty; it **raises**, at every consumer door.

**And it cannot be migrated:**

```
generate(path=existing)                       -> ContractViolation  (generate calls load())
generate(path=existing, bootstrap=True)       -> ContractViolation  (bootstrap is the `else`
                                                 branch of `exists(target)`; the existing-file
                                                 branch is taken and it calls load())
rm manifest && generate(bootstrap=True)       -> OK
   … contract_version origin is now '1.0.0'   -> ORIGIN HISTORY ERASED
```

The only route forward is the one operation `generate`'s own docstring exists to prevent:
*"`previous` used to default to `None` whenever the target did not exist, so … deleting the
manifest — which is the ordinary reaction to a drift gate going red — restamped every row's origin
with the current constant and emptied §6.4's queue"* (`manifest.py:277-283`). **Measured: origin
erased.** `bootstrap` was built to make that deliberate; the closed schema makes it **compulsory**.

And §6.4's re-admission queue — the mechanism that exists so a declaration can stay in the runtime
while it is re-admitted under an amended contract, i.e. *precisely this scenario* — is recorded
**NOT BUILT** at `manifest.py:253`.

**Sub-finding.** The **document** schema is closed too (`validate_document:366`, `_extra`), so §6.4's
queue cannot be carried as a top-level manifest key without amending that closure as well. The
closure constrains the unbuilt mechanism's most natural shape.

**Reachability: latent today, production-reachable and scheduled.** The committed manifest is
`declarations: []`, so there is no row to fail — the defect has **no subject until CP-4 admits the
first row**, and then arrives at the first checkpoint that grows the schema. Both are on the plan.
**Guard: none** — no test covers a schema-forward read.

**This is not an argument against closing the schema.** The closure is right and §2a shows it works.
The finding is that it shipped without the optional tier, the regeneration path, or §6.4's queue that
would make it survivable — and the round's own comment block asserts the opposite: *"When a producer
is built, the field arrives **with it**, in the same change."* It cannot, for any manifest that
already has rows.

---

## 3 — the exception hierarchy

### 3a · ✅ the `ValueError` half is correct

Pre-delta (`cba800fa8`): `ContractViolation(Exception)`, `UntrustedRow(Exception)`,
`UnresolvedReference(Exception)` — three unrelated classes, and `rows_of` raised a **bare
`ValueError`** for a bad document. Post-delta all three are `ValueError` subclasses. Measured:

```
UntrustedRow        mro: ['ValueError','Exception','BaseException']   is ValueError: True
ContractViolation   mro: ['UntrustedRow','ValueError','Exception']    is ValueError: True
UnresolvedReference mro: ['UntrustedRow','ValueError','Exception']    is ValueError: True
```

**No caller's `except` stops working.** Every pre-delta refusal at that door was a `ValueError`
(bare) or is now one. The half the prompt flagged as "most likely to be wrong" is **right**.

### 3b · 🔴 **B3 — but the new subclassing broke the third door, and this delta introduced it**

`ContractViolation` is now a **subclass** of `UntrustedRow`, so `manifest.py:234`'s
`except UntrustedRow` — which pre-delta could not fire on it — now catches it and re-raises it
**flat**. Same bad row (`kind: 'gadget'`), three doors, one process:

| door | class | C-12 fields (`declaration_id`, `field_path`, `reason`, `accepted`) |
|---|---|---|
| `rows_of` | `ContractViolation` | **present** |
| `validate_document` | `ContractViolation` | **present** |
| `build(previous=)` | `UntrustedRow` | **ABSENT** |

`validate_document` handles this correctly 175 lines below (`manifest.py:409-416`), catching
`ContractViolation` **first** and re-raising the same class, with a comment stating exactly why:
*"Wrapping it in a bare `UntrustedRow` kept the sentence and threw away `.declaration_id` /
`.field_path` / `.accepted` — so the two doors refused the same row with two different classes
again … and C-12's structured promise survived only as prose."*

**The delta wrote that comment and left `build` without the same clause.** The round whose premise
is "at the set, not at the named door" fixed two of three doors, and the third is the one it added
`check_row` to in the same commit.

**Reachability: production-reachable** through the exported `build(previous=…)`, in plain JSON, no
adversary. **Guard: none** — `G26` (my mutation downgrading `validate_document`'s re-raise) reds,
but nothing covers `build`. **Introduced by the graded delta: YES** (revert restores unrelated
exception classes, so the catch does not fire).

---

## 4 — the TOCTOUs, re-measured

### 4a · ✅ the 5th is **CLOSED**

`type(doc) is not dict` at `manifest.py:359`. Executed against a `dict` subclass whose `.get`
returns `'1.0.0'` on the first two calls and `'banana'` afterwards:

```
validate_document -> UntrustedRow: <memory>: manifest is a Lying, not a plain JSON object.
```

Refused at the door — the vehicle never reaches the return. The return is additionally rebuilt from
validated values (`MANIFEST_VERSION`, `doc_version`, `[dict(r) for r in rows]`), so both halves of
R15 §4d are answered. **CONFIRMED CLOSED.**

### 4b · ✅ `build`'s `id` split is **CLOSED** — narrower than the builder's own record

The builder records this as still OPEN. Measured, it is not. `build`'s live reads are
`r["id"]` at `:237`, `:249`, `:264` and `r["contract_version"]` at `:237` — **uniform mechanism, no
`.get()`** (the `.get()` spellings survive only inside comments). And `check_row(r, …)` at `:233`
runs `check_row_shape`, which raises unless `type(row) is dict` — so every subsequent read is
against a **plain `dict` with one storage**. There is no vehicle.

**Residual, stated because the file has a standard about it.** This is safe *by an exact-type pin
established on a previous line* — the identical form `contract.py:226-229` dismisses in its own
neighbour (*"safe because of an argument three lines up is exactly what was said about the five
TOCTOUs this run has already paid for"*). It is safe; it is safe for the reason the file says is not
good enough. Both statements are true and the file should pick one.

### 4c · 🔴 **B7 — the document-stamp half of the `{**doc}` fix is unguarded**

`manifest.py:430-434` states this half was "LEFT UNDONE FOR FOUR ROUNDS" and is now closed. Executed:
I reverted **only** the two stamps at the return to a re-read —

```python
"manifest_version": doc.get("manifest_version"),
"contract_version": doc.get("contract_version"),
```

— and the suite was **green**: `2 passed` on the two tests that name the property, and `104 passed`
on the full scoped suite, identical to baseline. The fix's own stated value is carried entirely by
`type(doc) is dict` (which **is** guarded — my `G20` mutation reds). **Guard-only**, low severity:
the pin makes the re-read unexploitable today, but if the pin were ever loosened both defects return
together and only one of them has a test.

### 4d · the read-twice sweep — **my own, reads only**

The prompt notes the builder's first sweep counted writes as reads. Mine excludes `ast.Store`/`Del`
contexts and matches `obj[key]` and `obj.get(key)` on named objects within one scope:

| file | function | obj | key | n | mechanism | lines |
|---|---|---|---|---|---|---|
| contract.py | `check_document_rows` | `r` | `id` | 4 | uniform | 300, 301, 303, 307 |
| contract.py | `check_row` | `row` | `id` | 3 | uniform | 261, 273, 284 |
| manifest.py | `build` | `r` | `id` | 3 | uniform | 237, 249, 264 |
| manifest.py | `validate_document` | `doc` | `manifest_version` | 2 | uniform | 378, 380 |
| surface.py | `_narrow` | `row` | `id` | 2 | uniform | 610, 627 |
| surface.py | `discover` | `row` | `kind` | 2 | uniform | 671, 676 |

**6 read-twice sites; 0 mixed-mechanism.** Every one is safe, and every one is safe for the same
reason as §4b — an exact-`dict` pin earlier in the function or at the call site. `check_document_rows`
is the weakest of them: it pins nothing itself and relies on all three call sites having validated
first. It is not exported in `__all__`, so this is not a hole.

---

## 5 — the P4 test: verified by building the mechanism, at both landing sites

I built §6.4's grandfathering twice and **proved each live before trusting any test result**.

**Variant A — in `build()`** (carry rows present in `previous` and absent from `admitted` forward
verbatim, preserving their `admitted_against`). Proven working:

```
rows kept: ['book_get','book_list']    QUEUE: ['book_get']    DRAINS to: []
```

**Test result: RED.** `AssertionError: §6.4's re-admission queue is NON-EMPTY via generate()
(['book_get'])`. Both halves measured independently, without the loop's short-circuit:

```
queue via generate() = ['book_get']
queue via build()    = ['book_get']     -> the build() half is LOAD-BEARING
```

**Variant B — in `generate()` only**, §6.4.1's own named landing site and the one that stayed green
for four rounds, with `build`'s refusal left intact:

```
queue via generate() = ['book_get']   (mechanism proven on disk; file keeps book_get)
queue via build()    = None           (build still refuses — blind here, by design)
```

**Test result: RED.**

**Verdict: PASS.** The `build()` half did **not** become the vacuous one — it fires in variant A —
and the `generate()` half covers the site that four rounds missed. This is the first round the test
genuinely covers the set.

### 5a · 🔴 **B8 — but the route loop short-circuits, so the `build()` half is unpoliced**

`test_cp1_membrane.py:537-545` raises on the **first** non-empty route. I neutered
`_partial_via_build` to `return None` and, with variant A live, the test **still redded via
`generate()`** — so a `build()` half that rots is invisible, and in the pristine tree the whole
suite stays green either way. **Guard-only**; it is the "made vacuous by an improvement" class, on
the one test CP-4 will be graded against.

---

## Red-ability table — **my own baseline**, 30 guards in scope

Baseline in the scratch tree (repo-path-dependent tests deselected — gate script, committed
manifest, legacy modules; none of them cover a guard below): **`104 passed, 19 deselected`**.
Each mutation applied to a restored-pristine tree, injection asserted present, suite re-run.

| # | guard mutated | result |
|---|---|---|
| G1 | `check_row_shape`: `type(row) is dict` → `isinstance` | **RED** |
| G2 | `check_row_shape`: unknown-key refusal removed | **RED** |
| G3 | `check_row_shape`: required-field loop removed | **RED** |
| G4 | `check_row_shape`: value exact-type → `isinstance` | **RED** |
| G5 | `check_row_shape`: empty-`id` refusal removed | **RED** |
| G6 | `check_row_shape`: members-element check removed | 🟡 GREEN |
| G7 | `check_row`: contract clauses removed | **RED** |
| G8 | `check_row`: stamp syntax check removed | **RED** |
| G9 | `check_row`: `canon.nfc()` on `owning_service` removed | 🟡 GREEN |
| G10 | `check_document_rows`: duplicate-id check removed | 🟡 GREEN |
| G11 | `check_document_rows`: M5 unresolved-reference removed | **RED** |
| G12 | `ROW_FIELDS`: the four ranking fields **restored** | **RED** |
| G13 | `ROW_REQUIRED`: back to a 5-element subset | **RED** |
| G14 | **writer door**: `_row`'s `check_row` removed | **RED** |
| G15 | **4th door**: `build(previous=)` → shape only | **RED** |
| G16 | `build`: outer `previous` type check removed | **RED** |
| G17 | `build`: missing-`declarations`-key check removed | **RED** |
| G18 | `build`: `_prev_rows` list check removed | 🟡 GREEN |
| G19 | `build`: loss guard removed | **RED** |
| G20 | **5th TOCTOU**: `type(doc) is dict` → `isinstance` | **RED** |
| G21 | `validate_document` returns `{**doc}` again | **RED** |
| G22 | document closed-schema check removed | 🟡 GREEN |
| G23 | document `manifest_version` check removed | **RED** |
| G24 | document `contract_version` check removed | **RED** |
| G25 | `validate_document`: `rows = list(rows)` removed | 🟡 GREEN |
| G26 | `validate_document`: C-12 class downgraded on re-raise | **RED** |
| G27 | **consumer door**: `rows_of` → shape only (the R15 defect) | **RED** |
| G28 | **consumer door**: `rows_of` set-clauses removed | **RED** |
| G29 | `rows_of`: `_is_exactly(rows, list)` → `isinstance` | 🟡 GREEN |
| G30 | `rows_of`: serves the caller's row object (`out.append(r)`) | 🟡 GREEN |

**22 / 30 red-able (73%).**

### 🔴 **B6 — the builder's 14/14 is true, and its denominator is self-derived**

RUNSTATE:1596-1597 claims *"14/14 membrane guards … proven red-able before this commit"*. That is
**100% of the builder's own list**. My independent enumeration of the same scope finds **30**, of
which **8 have no test**. A self-derived total always reads *done* — this run has a standard about
exactly that.

Behaviour-probed on the pristine tree, the 8 split cleanly and **none is a hole**:

| unguarded | status |
|---|---|
| G10 duplicate ids | **load-bearing, untested** — refuses (`ContractViolation`); nothing else checks duplicates |
| G18 `previous.declarations` not a list | **load-bearing, untested** — refuses with the documented class |
| G22 document closed schema | **load-bearing, untested** — refuses; note the rebuilt return already prevents propagation |
| G30 `dict(r)` copy at `rows_of` | **load-bearing, untested** — verified the copy defeats caller-side mutation after assembly |
| G6, G25, G29 | **redundant** given the exact-`dict` row pin / `check_contract` — correctly not red-able |
| G9 `canon.nfc()` | **dead** → B5 |

### 🔴 **B5 — `canon.nfc()` at `contract.py:268` is a dead guard with a comment claiming a door it does not close**

The comment asserts §0.14.2 door (a): *"an NFD spelling would validate and store un-normalised —
**two `canon.digest` values for one visibly identical document**."* Both halves measured false:

* The row **still stores the NFD spelling** — at `rows_of` and at `validate_document`
  (`is NFC? False`). `nfc()` is applied only to a throwaway `f"services/{…}/"` handed to
  `check_contract`, whose derived owner is discarded. The stored value is never touched.
* `canon.digest` **already NFC-normalises internally** (`canon._norm`, `canon.py:66`). Measured:
  `canon.digest(NFD) == canon.digest(NFC)` → **True**. The stated harm cannot occur.

Removing the call changes no test (G9 green) and no accept/reject outcome. **Residual:** an
un-normalised `owning_service` *does* differ under `Filter(field="owning_service", op="eq")`, which
is a real narrowing operand — so there is a genuine (narrow) door here, and this guard is not on it.
**Reachability: adversarial-input only. Guard: none. Introduced by the graded delta: YES.**

---

## Bypass table

| property the delta claims | bypass found | evidence | reachability |
|---|---|---|---|
| one definition of a valid **row** at every door | **none** — 0/23 divergent across three doors | executed, one process | — |
| the door the consumer stands behind is not the weaker one | **document** level: 5/9 shapes accepted by `rows_of`, refused by `load()` | executed | **production-reachable at CP-2** |
| every row-reader calls `check_row` | a **fifth exported door** passes suite **and** gate | injected, `123 passed`, gate exit 0 | guard-only |
| one documented refusal class at every door | `build(previous=)` returns `UntrustedRow`, C-12 fields destroyed | executed, three doors, one row | **production-reachable** |
| a new row field fails immediately, "in the same change" | true for the **writer**; false for the **reader** — existing manifest unreadable and un-regenerable | executed end-to-end | **scheduled (CP-2/CP-4)** |
| the 5th TOCTOU is closed | **none** — subclass refused at the door | executed | — |
| §0.14.2 door (a) closed for `owning_service` | value still stored un-normalised; digest already normalised, so the stated harm is not real | executed | adversarial-only |
| P4 test reds when the mechanism lands | **none** — reds at both landing sites | mechanism built twice, proven live | — |

## Sibling table — *a correction applied to one member of a set*

| correction | members | applied to | missed |
|---|---|---|---|
| `check_row` (shape **and** clauses) at every row door | `_row`, `build(previous=)`, `validate_document`, `rows_of` | **all 4** ✅ | — |
| re-raise preserving the C-12 class | `validate_document`, `build`, (`check_row`) | 2 of 3 | **`build` `manifest.py:234`** 🔴 **B3** |
| exact-type pin on the container | row ✅, `declarations` list ✅, **document** at `validate_document` ✅ | 3 of 4 | **document at `rows_of`** (no vehicle, but no bound either) |
| document-level validity at the consumer door | `manifest_version`, `contract_version`, closed doc schema | 0 of 3 at `rows_of` | **all 3** 🔴 **B1** |
| the closed schema's forward path | writer ✅, reader ✗, regeneration ✗, §6.4 queue ✗ | 1 of 4 | 🔴 **B2** |

## Guard table — *is there a test? can it red? does it red for the reason it names?*

| property | test | reds? | for the right reason? |
|---|---|---|---|
| row-level one-definition at 4 doors | 4 named tests | ✅ G14/G15/G26/G27 | ✅ |
| **a fifth door** | **none** | **n/a** | 🔴 **B4** |
| document-level validity at `rows_of` | **none** | **n/a** | 🔴 **B1** |
| C-12 class preserved on re-raise | `validate_document` only | ✅ G26 | 🔴 not at `build` — **B3** |
| schema-forward read / regeneration | **none** | **n/a** | 🔴 **B2** |
| document stamps rebuilt, not re-read | claimed by 2 assertions | **NO** — re-read leaves suite green | 🔴 **B7** |
| P4 queue reds at either landing site | `test_THE_QUEUE_IS_EMPTY…` | ✅ both variants | ✅ — but `build()` half unpoliced, **B8** |
| §0.14.2 door (a) | **none** | **n/a** | 🔴 guard is dead — **B5** |

## Reachability verdict on every finding

| # | finding | bucket | introduced by the graded delta |
|---|---|---|---|
| **B1** | `rows_of` accepts 5 document shapes `load()` refuses | **production-reachable** (at CP-2) | no — pre-existing, one level up |
| **B2** | closed schema has no optional tier; growing it bricks the manifest with no migration path | **production-reachable**, scheduled | **YES** |
| **B3** | `build` destroys C-12's structured fields via the new subclassing | **production-reachable** | **YES** |
| **B4** | consolidation is a state, not a gate — fifth door passes suite + gate | guard-only | no |
| **B5** | `canon.nfc()` is a dead guard with a false comment | adversarial-input only | **YES** |
| **B6** | 8 of 30 guards not red-able; builder's denominator self-derived | guard-only | partly |
| **B7** | document-stamp rebuild unguarded | guard-only | no (revert makes it a defect, not a finding) |
| **B8** | P4 route loop short-circuits; `build()` half unpoliced | guard-only | no (same rule) |

**3 production-reachable · 1 adversarial-input only · 4 guard-only · total 8 · introduced 3.**

---

## Independent re-run of the builder's two pre-commit claims

**Claim 1 — "14/14 membrane guards proven red-able."** **TRUE for the builder's 14; incomplete as a
statement about the scope.** My own enumeration: **22/30 (73%)**. The 8 gaps are guard-debt, not
holes — four are load-bearing-but-untested, three are redundant given the exact-`dict` pin, one is
dead (B5). The finding is the **denominator**, not the arithmetic.

**Claim 2 — "the read-twice sweep returned 0 sites."** **TRUE under a mixed-mechanism definition; 6
sites under the broader one.** My sweep (reads only — `ast.Load` contexts, writes excluded, which is
the bug the builder's first version had) finds **6** same-fact-twice sites and **0** mixed-mechanism
pairs. All six are safe, and all six are safe *because an exact-type pin ran first* — the argument
the codebase elsewhere calls insufficient. The honest form of the claim is *"0 mixed-mechanism sites;
6 same-fact reads, each pinned."*

---

## 6 — convergence

### The controlled series — Verifier B only

| round | production-reachable | adversarial-input only | guard-only | total | **introduced by the graded delta** |
|---|---|---|---|---|---|
| 9 | 4 | 5 | 2 | 11 | 2 (derived) |
| 10 | 12 | 5 | 1 | 18 | 1 (derived) |
| 11 | 9 | 7 | 5 | 21 | 2 (derived) |
| 12 | 3 | 7 | 7 | 17 | 1 (derived) |
| 13 | 3 | 3 | 3 | 9 | 3 (executed) |
| 14 | 8 | 4 | 9 | 21 | 2 (executed) |
| 15 | 11 | 3 | 10 | 24 | 4 (executed) |
| **16** | **3** | **1** | **4** | **8** | **3** (executed) |

`introduced` rule, unchanged: a finding counts **iff reverting the graded delta closes it.** Ran the
revert reasoning for all eight; B7 and B8 are **not** counted (reverting turns each into an open
defect, which is worse, not closed) — and saying so is the point of having the rule.

### Per changed line — the normalisation R15-B asked for and this round owes

Delta in this scope: **269 added source lines** (`contract.py` +157, `manifest.py` +91,
`surface.py` +21), of which **134 are comment or blank** — this codebase carries its reasoning in
the file, so raw line counts flatter it.

| round | added source lines (B's scope) | introduced | **per 100 changed lines** |
|---|---|---|---|
| 13 | ~2 | 3 | 150 |
| 14 | ~41 | 2 | 4.9 |
| 15 | ~90 | 4 | 4.4 |
| **16** | **269** | **3** | **1.1** |

**The introduction rate is falling, and it is falling on the normalisation that cannot be gamed by
shipping less.** R16 shipped three times R15's volume and introduced fewer defects. That is the
strongest number in this verdict and it belongs before the findings.

### Closure

R15-B left **24** findings open. Re-run as probes against this artifact:

| R15-B finding | now |
|---|---|
| §1b two doors disagree about VALIDITY — nine classes | **CLOSED** ✅ (0/23 measured) |
| §1c the third door is the WRITER | **CLOSED** ✅ (counterfactual measured) |
| §1d the fourth door, `build(previous=)` | **CLOSED** for shape+validity ✅ / **PARTIAL** on class (B3) |
| §1e two exception classes at an exported door | **CLOSED** at `rows_of` ✅ / **PARTIAL** at `build` (B3) |
| §1f the document container at `rows_of` untyped | **NARROWED** — still untyped, but `declarations` is read once, so no vehicle; doc-level checks still absent (B1) |
| §2b the four ranking fields shipped beside a comment refusing them | **CLOSED** ✅ |
| §2f forward path discovered late | **OPEN and worse than stated** → B2 |
| §3 `members` survivors (`None`/`0`/`False`) | **CLOSED** ✅ |
| §4a/§4b the 6th TOCTOU and `validate_document`'s `id` split | **CLOSED** ✅ and now **guarded** (G1, G20) |
| §4c both closures rest on one untested line | **CLOSED** ✅ — the pin is now red-able (G20) |
| §4d the 5th TOCTOU, `{**doc}` | **CLOSED** ✅ |
| §4e `build`'s `id` split | **CLOSED** ✅ (narrower than the builder's own record) |
| §4f read-twice on the mutable `ROW_FIELDS` global | **CLOSED** ✅ (`MappingProxyType`, tested) |
| §5a the central claim guarded on one half | **CLOSED** ✅ (G14/G15/G27 all red) |
| §5b the vacuous `Smuggler` test | **CLOSED** ✅ (refusal asserted; live half reds under G21) |
| §5d the guard the delta DELETED (non-empty `id`) | **CLOSED** ✅ (G5 red; `id: ""` refused at every door) |
| §7 P4 test blind to the `generate()` landing | **CLOSED** ✅ (built and measured at both sites) |
| R14 §1a `members: ['ghost']` at four doors | **CLOSED** ✅ (third round carried, now closed) |
| R14 §1b hand-typed `cost` steers the budget | **CLOSED** ✅ |
| R12 §5 `generate`'s `exists`→`load` race | carried — re-check present, unchanged |
| §5 the unguarded strengthenings | **PARTIAL** — 8 of 30 still unguarded (B6) |

| transition | open in this scope | closed by the next delta | rate |
|---|---|---|---|
| R11-B → R12 | 21 | 3 | 14% |
| R12-B → R13 | 17 | 1 + 2 partial | ~9–12% |
| R13-B → R14 | 12 | 1 | ~8% |
| R14-B → R15 | 15 | 4 + 2 partial | ~27% |
| **R15-B → R16** | **24** | **13 + 5 partial** | **~54%** |

### The ruling Q6 asks for: **two points, still not a trend — and yes, this is the same answer as last round**

The prompt asks whether R15's closure rise was a trend or a single point, and instructs me to say so
if the answer is the same as last round's. **It is the same answer, and I am saying so.**

Closure now reads **14%, ~10%, ~8%, ~27%, ~54%** — two consecutive rises. R15-B's own ruling was
*"two points cannot distinguish a trend from alternation"*, and that objection applies verbatim to
three. The series `14, 10, 8, 27, 54` is consistent with a trend **and** with a step change caused by
one thing: **R15 and R16 are the first two rounds whose deltas were structural** (one definition, one
schema) rather than site-by-site. If that is the cause, the rate should fall back the moment a round
ships a site-by-site delta again — which is a prediction, and predictions are what distinguish a
trend from a run of luck.

`introduced` reads **2, 1, 2, 1, 3, 2, 4, 3** — still no direction raw. **Per changed line it does
have one**: 150, 4.9, 4.4, **1.1**. That is the number R15-B asked for and it is the first evidence
in this series that the *rate* is improving rather than the *count* being bought.

**What would settle it**, unchanged from R15-B because nothing has made it obsolete:

1. **Three consecutive rounds at `introduced == 0`.** R16 is not one of them.
2. **The read-twice sweep run by the builder pre-commit with its result in the commit message.** This
   round did it — and the result reported (`0`) is true only under the narrower of two definitions.
   The improvement is real; the definition needs to be in the message with the number.
3. **`introduced` per changed line.** Delivered above, first time in the series.
4. **New, and this round's own contribution:** the closure and introduction numbers are still
   produced by *verifiers enumerating by hand*. **B4 is that failure in miniature** — four doors
   policed by four tests naming four doors. Until a structural gate counts row-readers, both the
   product and its convergence metric are measured by enumeration, and enumeration is what this
   package has already been burned by twice (`discover`'s narrowing path; the fifth door I injected).

---

## What I would fix first

1. **B3** — one line: catch `ContractViolation` before `UntrustedRow` at `manifest.py:234` and
   re-raise the same class. It is the round's own pattern, already written 175 lines below.
2. **B2** — decide the optional tier now, before CP-4 writes the first row. Either split
   `ROW_REQUIRED` from `ROW_FIELDS`, or give `generate()` a schema-migration path that does not
   route through `load()`. Today the only forward route erases §6.4's origins, measured.
3. **B4** — an AST gate in `agentruntime-membrane-gate.py`: every function in the package that reads
   a row field must call `check_row`, or be `check_row` itself, or be reached only via `rows_of`.
   That converts this round's genuine achievement from a state into a property.
4. **B1** — either give `rows_of` the document-level checks, or make `SurfaceAssembler`/`discover`
   take something only `load()`/`validate_document` can produce.
5. **B5** — delete the `canon.nfc()` call and the comment, or make it normalise the **stored** value
   and point the comment at `Filter(field="owning_service")`, which is the real door.

---

**Files touched by this verifier: this file only.** All ten scope files verified byte-identical to
the snapshot taken at start (md5); `git status` over the scope is empty; nothing committed.

`git rev-parse HEAD` = `d23ea559294ae2daa4fa1414d87b734d2e1e2479` — **unmoved.**
