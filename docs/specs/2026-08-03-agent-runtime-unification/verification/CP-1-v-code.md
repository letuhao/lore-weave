# CP-1 · V-CODE — verdict

**Artifact:** `083ed4c989b811ab0f7d64b8c7ead8f4b0e94ed2`, verified at the start of the audit and again
before this verdict was written. HEAD did not move; the four artifact paths
(`app/agentruntime/**`, `scripts/agentruntime-membrane-gate.py`,
`contracts/agent-runtime-manifest.json`, `tests/test_cp1_membrane.py`) are clean in
`git status`. Source read only; nothing was run against a live system and no tracked file was
edited.

---

## 1 · Verdict

**Overall: FAIL.**

| # | claim | verdict |
|---|---|---|
| 1.1 | manifest generated, starts empty | **FAIL** — "starts empty" holds and is checked; **"generated" is enforced by nothing**, there is no generator entry point, and the drift gate the code and `ARCHITECTURE.md:840` both name **does not exist** |
| 1.2 | import-graph gate, no legacy in the transitive imports | **PASS** — the current import graph is stdlib-only; a real AST import gate, allowlist-shaped, wired into CI, self-testing. One namespace-prefix hole named below |
| 1.3 | discovery reads the manifest only; zero rows for all three kinds | **PASS** (mechanism) — `discover` cannot reach anything but its dict argument. Its **tests are vacuous** (they assert `[] == []`); the real residual is that the dict is caller-supplied and never validated |
| 1.4 | construction IS validation; bypass impossible. P4 at every INSERT | **FAIL** — three usable bypasses, and `build()` performs **no `isinstance` check at all**, so the type does not gate the write. P4 has **zero subject**: the new runtime reaches no INSERT |
| 1.5 | an unresolvable reference fails generation | **PASS** — resolution precedes the write; nothing is written on failure; test executes it |
| 1.6 | C-0 identity, owner derived never authored | **PASS** with a named residual — there is no field to author, but the derivation input (`source_path`) is authored and validated against nothing |
| 1.7 | every narrowing registers `{tool, stage, reason, pass}` | **PASS** for the assembly path, which is the strongest thing in this checkpoint — with **two unregistered drop points** enumerated below that the structural test cannot see |

---

## 2 · The falsifier — what I looked for that would have made this FAIL

Stated before the findings, so the PASS rows are not unfalsifiable:

1. **Any import, call, or value read in `app/agentruntime/**` that originates in
   `tool_surface.py` / `tool_discovery.py` / `stream_service.py` or any other non-stdlib module.**
   Method: read all five modules line by line; `Grep '^(import|from) '` across the package
   (result: `re`, `json`, `dataclasses`, `pathlib`, `typing`, `__future__`, and five relative
   imports — nothing else); `grep -rn agentruntime` repo-wide to find every file that mentions the
   package (result: the gate, the workflow, the tests, two CP-0 files that only contain the *string*
   `"agentruntime"` as a `runtime_variant` enum value — `app/services/instrument.py:100`,
   `app/db/migrate.py:368` — and no importer). **Found none.** 1.2's claim about the *current* graph
   is true.
2. **A fallback / union / default-parameter reaching the legacy catalog.** Method: read every
   signature in the package. `SurfaceAssembler.__init__` takes one catalog argument with no default;
   `discover` takes one; `build` takes an iterable; `load` falls back to `{"declarations": []}`, i.e.
   in the *safe* direction. **Found none.**
3. **A way to obtain a usable `Admitted` without `admit()`.** Method: enumerated the eight documented
   Python bypasses against the actual class definition. **Found three that work** (§5).
4. **A drop point with no `{tool, stage, reason, pass}` record.** Method: enumerated every statement
   in the package that can reduce a row set (§4, finding F7). **Found two.**
5. **A gate present in the tree and absent from CI.** Method: read
   `.github/workflows/lint-foundation.yml` in full; `agentruntime-membrane-gate` is line 94 of the
   `p1-lints` matrix, executed at line 118 as `python scripts/${{ matrix.lint }}.py`, i.e. bare, so
   the script's default mode (which runs `_selftest()` first) is what CI runs. `scripts/gate-wiring-gate.py`
   independently requires every gate to be referenced by a workflow. **Not found — the gate runs.**
6. **A gate with no subject.** Method: for each check, asked what input makes it fire (§6). **Found
   two vacuous checks and one property with no subject at all** (P4).
7. **An INSERT binding an instrument column to a literal reachable from more than one terminal
   condition.** Method: searched the package for SQL/DB access of any kind. **There is none** — see
   F5.

---

## 3 · Findings

### F1 · `build()` does no type check — the "membrane in one signature" is duck typing
`services/chat-service/app/agentruntime/manifest.py:49-51`, `:63-70`

```python
def _row(admitted: Admitted[Declaration]) -> dict:
    d = admitted.declaration
```

`build()` iterates and calls `_row(a)`. There is no `isinstance(a, Admitted)` anywhere in the
package, and — by `admission.py:12-15`'s own account — **no type checker runs on this service**. So
the annotation is documentation. Any object exposing a `.declaration` attribute produces a manifest
row: `build([SimpleNamespace(declaration=Declaration(id="x", kind="tool", source_path="a/b"))])`
writes a full row that passed no contract clause — note it does not even need a valid `source_path`,
because `derive_owning_service` returns `""` and `_row` writes that empty string rather than raising.

The docstring at `manifest.py:65-68` — *"an unadmitted declaration cannot reach this function, because
the only way to hold the argument type is to have passed the contract check"* — is false at runtime.
This is the M4 guarantee restated in the one place it is load-bearing, and it is not enforced there.

**The test that should have caught it is green for the wrong reason.**
`tests/test_cp1_membrane.py:80-85` passes a bare `Declaration` and accepts
`pytest.raises((AttributeError, TypeError))`. It passes because a `Declaration` has no `.declaration`
attribute — an accident of duck typing, not a check. It would stay green while the `SimpleNamespace`
above succeeds. This is a test that **admits**.

### F2 · `_TOKEN` is importable; guarantee 1 of §6.1's table is false
`services/chat-service/app/agentruntime/admission.py:44-55`, `:70-75`

The token is a single-underscore module attribute. `from app.agentruntime.admission import _TOKEN`
is an ordinary import — `_` is a convention, `__all__` is not consulted by a targeted import, and the
membrane gate lints only files **inside** `PACKAGE` (`scripts/agentruntime-membrane-gate.py:55`,
`:169`), so an external module doing this is not linted by anything. `Admitted(d, "1.0.0", _TOKEN)`
from any module in the service yields a fully valid, indistinguishable `Admitted` with no contract
check. The docstring's *"module-private, never exported… nothing else can name"* and §6.1 row 1's
*"only `admit()` holds"* are both false. Name-mangling (`__token`) would not have fixed it either,
but it would at least have made the reach deliberate; a bare `_TOKEN` is reachable by autocomplete.

### F3 · An admitted object **can** be mutated — guarantee 2 is false
`admission.py:76-77` vs `tests/test_cp1_membrane.py:201-204`

`frozen=True` installs a `__setattr__` on the class. `object.__setattr__` bypasses it and writes the
slot descriptor directly — which is exactly what `Admitted.__init__` itself does at lines 76-77. So
`object.__setattr__(a, "declaration", other_declaration)` silently turns an admitted `book_list` into
an admitted anything. The test asserts only the normal-`setattr` half (`a.declaration = ...`).

### F4 · A forged instance **is** usable — guarantee 4 is weaker than stated
`admission.py:26-28`, `tests/test_cp1_membrane.py:216-223`

The claim is that `object.__new__(Admitted)` leaves every slot unset so the first read raises. True
for exactly two lines. Completing the forgery is `object.__setattr__(forged, "declaration", d)` and
the same for `contract_version` — after which the object is fully usable and passes `build()`.
Independently, **subclassing is not prevented**: `Admitted` is not final, defines no
`__init_subclass__`, and its slots are inherited, so a three-line subclass with its own `__init__`
produces a usable instance for which `isinstance(x, Admitted)` is true. The test suite tests neither
completion nor subclassing; the spec table names neither.

### F5 · P4 (1.4, second half) has no subject in CP-1
Method: the package contains no SQL, no DB driver, no `INSERT`, and — by M2 — cannot import one. The
only write it performs is `manifest.generate` → `Path.write_text` (`manifest.py:95`). **Zero INSERTs
are reachable from the new runtime**, so "no instrument column bound to a constant at any INSERT" is
vacuously true and untestable at this checkpoint. Per the vacuity rule in the prompt, a property whose
subject never occurs is a `FAIL` finding, not a pass.

The nearest analogue **does** exhibit the P4 shape and is worth recording now rather than at CP-4:
`manifest.py:57` writes `"contract_version": ident.contract_version`, and `identity_of`
(`contract.py:144-151`) hardcodes the module constant `CONTRACT_VERSION`. The value the admission
actually produced — `Admitted.contract_version`, set at `admission.py:108-109` from
`check_contract`'s return — is **never read by anything**; it is a dead field. Today both are
`"1.0.0"`, so the defect is invisible. The moment `CONTRACT_VERSION` bumps, every row in a regenerated
manifest claims the new version regardless of the version it was admitted under, and the column
becomes a constant reachable from every terminal condition — the exact literal-from-many-paths shape
P4 names.

### F6 · The M1 drift gate is claimed by two documents and exists in neither
`manifest.py:86-91` (*"The M1 gate (manifest row count == admitted count) is the drift check"*),
`ARCHITECTURE.md:840` (*"manifest row count == admitted count; drift reds CI"*).

Searched: `scripts/agentruntime-membrane-gate.py` (checks imports and construction sites only, never
opens the manifest); `grep -rn "agent-runtime-manifest"` repo-wide, which returns the spec, the
RUNSTATE, the package constant, and two test lines — **no gate, no generator invocation, no CI step**.
`grep -rn agentruntime` over `.github/workflows/` returns the one lint entry.

Consequences, all of which are the "generated, not hand-authored" half of 1.1:

- **No generator entry point exists.** `generate()` is a library function whose only callers are
  tests, and every test passes an explicit `path=tmp_path`. Nothing in the tree ever writes
  `contracts/agent-runtime-manifest.json`. The committed file *is* byte-identical to
  `json.dumps({"manifest_version": 1, "contract_version": "1.0.0", "declarations": []}, indent=2)`
  plus a newline, so it is **consistent with** generation — but a file consistent with generation and
  a file produced by generation are the two things the prompt says differ, and only the first is
  checkable here.
- **Nothing prevents hand-editing, and the read path never re-admits.** `load()` (`manifest.py:99-109`)
  is `json.loads` with no schema check; `SurfaceAssembler.__init__` (`surface.py:82`) and `discover`
  (`surface.py:137`) consume raw dicts. A row typed into the JSON file by hand is offered by the
  assembler having passed no clause of C-0, no owner derivation, and no M5 resolution. Admission is
  construction **on the write path only**; the read path has no membrane at all.
- The manifest is also **not registered** in the machine-contract table of `docs/standards/README.md`
  (grepped: no match), so `enforcement-claims-gate.py` — which `situations/S4-admission.md:601`
  identifies as the mechanism that would make the manifest governed — does not cover it.

### F7 · Two drop points in the new surface write no narrowing record
`surface.py:82` and `surface.py:130-140`

The enumeration the prompt asked for — **every** point in the new assembler at which a declaration can
leave the row set:

| # | site | can drop? | records `{tool, stage, reason, pass}`? |
|---|---|---|---|
| 1 | `SurfaceAssembler.__init__`, `manifest_doc.get("declarations", [])` — `surface.py:82` | yes: a doc with the key absent or misspelled yields zero rows | **no** — silent; `is_empty` reports it as "nothing admitted", which is a different fact |
| 2 | `assemble` rule loop — `surface.py:102-104` | delegates only | n/a |
| 3 | `_narrow` — `surface.py:119-127` | yes, the intended one | **yes**, in the same statement, all four fields, required by `NarrowingRule.__post_init__` |
| 4 | `assemble` → `Surface(names=…)` — `surface.py:105-109` | no (projection of `kept`) | n/a |
| 5 | `discover(doc, kind=…)` — `surface.py:140` | **yes** — returns only rows of one kind, dropping the other two | **no** — no log, no stage, no reason, no pass |
| 6 | `Surface(...)` constructed outside `app/agentruntime/` | yes — arbitrary `names` with empty `withheld` | **no** — the gate's `_construction_sites` scans `PACKAGE.rglob("*.py")` only (`gate:132-139`), and `Surface` is exported from `__init__.py:36`, so any consumer may build one |
| 7 | `build()` duplicate-id check — `manifest.py:76-78` | raises, does not drop | n/a (see F9) |
| 8 | `load()` on a missing file — `manifest.py:104-108` | yields zero rows | **no** — deliberate and fail-safe, but "manifest file missing" and "manifest empty" are indistinguishable downstream, which `Surface.is_empty`'s docstring claims to have closed for a different pair |

Sites 3 is genuinely excellent and is the reason 1.7 passes: `stage` and `reason` are **required
fields** of `NarrowingRule`, `__post_init__` rejects empties, and the record is written in the same
loop iteration that computes the removal. "Drop these and say nothing" is not expressible through the
rule API. That is a structural property, not a discipline, and it is the one thing in CP-1 that is
strictly stronger than what it replaces.

Sites 1, 5, 6 and 8 are the residual. Site 5 is the one to watch: `discover` is exported, is the M3
entry point, and drops two thirds of a mixed manifest with no record. It is defensible as a
*caller-specified projection* rather than a runtime narrowing decision — which is why 1.7 is graded
PASS — but the moment CP-4 uses `discover(kind=…)` to decide what the model sees, P1 is violated in
the new package by the same shape it was violated by eight times in the old one, and **no gate here
will notice**, because:

`tests/test_cp1_membrane.py:335-348` is the structural test for this property and it only collects
functions that *call* `.record`, asserting the set is `{"_narrow"}`. It says nothing about which
functions *drop*. It is green right now while `discover` drops rows silently. It is a shape gate over
half the invariant.

### F8 · Namespace-prefix hole in the membrane gate's internal-import test
`scripts/agentruntime-membrane-gate.py:81-83`

```python
return module.startswith(PACKAGE_MODULE) or module.startswith("agentruntime")
```

`PACKAGE_MODULE` is `"app.agentruntime"`. `startswith` on a dotted name without a trailing-dot guard
treats **any sibling whose name begins with the package name** as internal. A new file
`services/chat-service/app/agentruntime_bridge.py` that imports `app.services.tool_surface`, referenced
from inside the package as `from app.agentruntime_bridge import legacy_rows`, is classified internal at
line 83, is not scanned (`PACKAGE.rglob` covers the directory, not the sibling module), and the gate
prints OK. That is a complete defeat of M2 costing one well-chosen filename. The correct predicate is
`module == PACKAGE_MODULE or module.startswith(PACKAGE_MODULE + ".")`.

This is a hole in the *enforcement*, not a present violation — the current graph is clean — which is
why 1.2 remains PASS. It is the highest-value single fix in the checkpoint.

### F9 · A duplicate id is reported as an unresolved reference
`manifest.py:76-78`

```python
if dupes:
    raise UnresolvedReference(dupes[0], dupes[0])
```

A manifest with two rows sharing an id raises `UnresolvedReference("x", "x")`, whose message reads
*"x references 'x', which is not admitted"* — a true failure reported as a different, false cause.
Small, but it is the misattributed-blame shape, in a build step whose whole job is to stop bad data,
and `ContractViolation` exists two modules away with a `field_path`.

### F10 · Dead import
`manifest.py:23` imports `asdict`, which is never used. Cosmetic; noted only because the membrane
gate's value depends on its import list being read as meaningful.

---

## 4 · The bypass table

| # | claim | the path that defeats it, or the search that found none |
|---|---|---|
| 1.1 | manifest generated, starts empty | **Empty: confirmed** — `contracts/agent-runtime-manifest.json` is `"declarations": []`, asserted against the committed artifact at `tests/test_cp1_membrane.py:61-65`. **Generated: no path proves it and none prevents the opposite** — no generator invocation exists in the tree (searched: `grep -rn "agent-runtime-manifest"` repo-wide, `grep -rn "generate("` across the service; every caller is a test with `path=tmp_path`), `load()` does no validation, and the drift gate named at `manifest.py:90` and `ARCHITECTURE.md:840` is absent from `scripts/` and from every workflow. **Bypass: edit the JSON file.** F6 |
| 1.2 | no legacy in the transitive imports | **Searched, found none in the current graph.** Method: full read of all five modules; `Grep` for import statements across the package (stdlib + five relative imports, nothing else); repo-wide `grep -rn agentruntime` to find any bridge module (none). **Latent bypass in the gate:** a sibling module named with the `app.agentruntime` prefix is classified internal — `gate:83`. F8. Second, acknowledged in the gate's own docstring and correct to acknowledge: legacy *data* handed in through a normal argument is outside a static import gate — and that hole is real here, because `SurfaceAssembler(doc)` accepts any dict (F6) |
| 1.3 | discovery returns zero rows for a legacy declaration of each kind | **No path.** `discover` (`surface.py:130-140`) reads exactly one parameter and has no other name in scope; the module's only import is `.narrowing`. Confirmed by reading, not by test — **the tests for this item prove nothing** (§6, NV-3). The residual is 1.1's: the dict itself is unvalidated |
| 1.4 | producing an `Admitted` without the check is impossible | **Three paths, all working:** (a) `from app.agentruntime.admission import _TOKEN` → `Admitted(d, v, _TOKEN)` — F2; (b) `object.__new__` + two `object.__setattr__` calls, or `object.__setattr__` on an existing instance to swap its declaration — F3/F4; (c) subclass with its own `__init__` — F4. And the type never gates the write anyway: `build()` does no `isinstance` — F1. **P4: no INSERT exists to bind anything at** — F5 |
| 1.5 | an unresolvable reference fails generation | **Searched, found none.** `generate` (`manifest.py:92-96`) calls `build` **before** `write_text`, so a raise leaves no file; `build` (`:70-78`) resolves every member against the ids of the same batch. Executed by `tests/test_cp1_membrane.py:240-246`, which asserts `not p.exists()`. Residual: nothing re-resolves on the **read** path, so a hand-edited manifest with a dangling member is served |
| 1.6 | owning service derived, never authored | **No direct path** — `Declaration` (`contract.py:48-63`) has no owner field, asserted at `tests:259-260`; `_row` derives on every write (`manifest.py:55-57`). **Indirect path: `source_path` is authored and checked against nothing** — not against the filesystem, not against a service list, not against `contracts/language-rule.yaml` (which does enumerate the real services). `Declaration(id="x", kind="tool", source_path="services/book-service/anything")` admits with `owning_service="book-service"` from a service the code has never been in. The field is derived from a claim |
| 1.7 | every narrowing registers | **Two paths:** `discover`'s `kind` filter (`surface.py:140`) and the `.get("declarations", [])` default (`surface.py:82`) drop rows and write nothing. A third if a consumer constructs `Surface` directly, which the gate cannot see outside the package. The intended path (`_narrow`) is airtight and is the checkpoint's best work. F7 |

---

## 5 · The `Admitted[D]` boundary — what is actually prevented, and by what

§6.1 asks V-CODE to settle this independently. Settled:

| bypass | prevented? | by what |
|---|---|---|
| `Admitted(d, v)` — direct call | **yes** | the custom `__init__` raises when `_token is not _TOKEN`. A user-defined `__init__` survives `@dataclass` (`_set_new_attribute` does not overwrite a name already in `cls.__dict__`), including through the `slots=True` class rebuild |
| `dataclasses.replace(a, …)` | **yes** | routes through `__init__`, no token → `TypeError` |
| `copy.copy` / `copy.deepcopy` | **yes** | `__copy__` / `__deepcopy__` raise (`admission.py:84-88`) |
| `pickle.loads(pickle.dumps(a))` | **yes** | `__reduce__` raises (`:81-82`); `object.__reduce_ex__` honours it at every protocol |
| `a.declaration = x` | **yes** | `frozen=True`'s `__setattr__` |
| `a.__dict__[...] = x` | **yes** | `slots=True` — there is no `__dict__` |
| `model_construct` | n/a | not a pydantic model |
| **`from …admission import _TOKEN`** | **NO** | single-underscore module attribute; a plain import reaches it; the gate lints only files inside the package |
| **`object.__setattr__` on a forged or an existing instance** | **NO** | writes the slot descriptor directly, bypassing the frozen `__setattr__` — the class's own `__init__` uses this call at lines 76-77 |
| **subclassing** | **NO** | not final, no `__init_subclass__`, slots inherited; `isinstance` passes |
| a second construction site **inside the package** | **yes** | `SINGLE_SITED` in the gate, in CI. Bare-name `ast.Call` only — an aliased or attribute-qualified call would be missed |
| a construction site **outside the package** | **NO** | the gate never looks there. `Surface` in particular is exported and freely constructible |

**The honest statement.** `Admitted` prevents every *accidental* production — the direct call, the
copy, the pickle, the `replace`, the attribute assignment — and makes the naive `object.__new__`
forgery loud. It prevents no *deliberate* one: three separate two-to-three-line routes produce a fully
usable instance, and the one place the type is supposed to be load-bearing (`build()`) does not check
the type at all, so even a totally unrelated object with a `.declaration` attribute writes a manifest
row.

That is materially stronger than the 14-call-sites-against-58 validator it replaces, because the
default path is now correct and the wrong path must be written on purpose. It is **not** "impossible",
and §6.1's rows 1, 2 and 4 each overstate what the code does. Row 3 and row 5 are accurate; row 5 is
accurate only within `app/agentruntime/`.

---

## 6 · Vacuity (NV-1…6)

| check | realistic input that makes it fire? | armed? |
|---|---|---|
| **NV-1** membrane gate `_violations_in` over the real package | yes — five modules are scanned; adding any non-stdlib import reds it at the exact line. The `--selftest` (`gate:204-238`) fires the predicate on five bypass shapes and asserts silence on a legal module, and **default mode runs it before the lint**, which is what CI invokes | **armed** |
| **NV-2** `SINGLE_SITED` construction counting | yes — it counts two real sites today (`Admitted` ×1, `Surface` ×1); a second reds | **armed** |
| **NV-3** `test_an_empty_manifest_yields_zero_rows_for_every_kind` (`tests:155-157`) | **no.** It asserts `discover(empty_doc, kind=k) == []`. No legacy declaration participates; the assertion is `[] == []` and can fail only if `discover` invents rows. `test_a_real_legacy_tool_name_is_not_discoverable` (`:159-163`) reads the same empty committed manifest and is a restatement of NV-4 | **vacuous** — 1.3's mechanism is sound by construction, but nothing tests it |
| **NV-4** `test_the_committed_manifest_is_empty` | yes — reds the moment a row is committed. This is the load-bearing M1 assertion and it is on the artifact, not on what the generator would produce | **armed** |
| **NV-5** `test_the_gate_actually_RUNS_in_ci` (`tests:130-134`) | substring `"- agentruntime-membrane-gate"` against the whole workflow text. Green today for the right reason (line 94 is a real matrix entry), but it would stay green if the entry were **commented out**, since `# - agentruntime-membrane-gate` contains the string. `scripts/gate-wiring-gate.py` is a second net and searches workflow text the same way | **armed but shape-shaped** — this is the repo's own "forbidden string still present in a comment" defect, mirrored |
| **NV-6** `test_the_drop_and_the_record_are_the_same_statement` (`tests:335-348`) | fires if a **second** function calls `.record`. Does **not** fire if a function drops rows without recording — which is the state of the tree right now (`discover`) | **half-armed**, and the unarmed half is the half P1 is about |
| **P4** "no instrument column bound to a constant at any INSERT" | **no input exists** — the new runtime reaches no INSERT and cannot import a driver | **no subject** — F5 |
| M1 drift gate ("row count == admitted count", `ARCHITECTURE.md:840`) | would fire on a hand-edited manifest — but **the gate does not exist**; only a unit test over a `tmp_path` round-trip | **absent** — F6 |

On the empty-manifest question the prompt raises: M4, M5, C-0 and P1 are all tested against
manifests the tests **build themselves** from `admit()`ed declarations (`tests:73-79`, `:236-238`,
`:291-293`), so those gates execute the mechanism and are genuinely armed despite the committed
manifest being empty. Only M3's tests take the empty manifest as their input, and that is why they are
vacuous.

---

## 7 · What is well built

Briefly, per instruction. `_narrow` and `NarrowingRule` (`surface.py:29-40`, `:111-127`) are the real
thing: two required fields, a `__post_init__` that rejects empties, and a record written in the same
loop iteration as the removal. There is no API through which a caller can express a silent drop, which
is a different and better claim than "we remembered to log". `generate` resolving before writing
(`manifest.py:92-96`) so a failure leaves no artifact is the correct inversion of a fail-open runtime
check. The membrane gate is a genuine AST import gate — not a lint rule, not a naming convention, not
a comment — it is an allowlist with `ALLOWED_EXTERNAL = {}`, it runs its own self-test in the mode CI
invokes, and it is wired into `lint-foundation.yml` line 94. And the CP-1 code corrected two of its
own docstrings' overclaims (`surface.py:46-50`) rather than leaving them; the residual overclaims that
remain are in `admission.py` and `manifest.py`, and they are listed above.

The tests are mostly behaviour gates that execute the mechanism (`copy`/`pickle` are really invoked;
`generate` really writes to a tmp file; the membrane gate is really executed via
`importlib.util.spec_from_file_location`). Three exceptions are named in §6 and F1.
