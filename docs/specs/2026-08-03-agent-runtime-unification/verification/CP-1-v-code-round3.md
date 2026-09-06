# CP-1 · V-CODE — verdict, round 3 (fix delta)

**Artifact:** `2f24eea11fbc2c7ac087e1a41f6c0a0b04d28c62`. `git rev-parse HEAD` verified before the
audit and again immediately before this verdict was written — **HEAD did not move**. All artifact
paths (`app/agentruntime/**`, `scripts/agentruntime-membrane-gate.py`,
`contracts/agent-runtime-manifest.json`, `tests/test_cp1_membrane.py`) are clean in `git status`.

**Scope.** The fix delta `7f50949dc..HEAD` over `services/chat-service/`, `scripts/` and
`ARCHITECTURE.md` — three files: `surface.py` (+36/-14), `agentruntime-membrane-gate.py` (+97),
`test_cp1_membrane.py` (+133/-45). Item **1.4's P4 half is out of scope** and not graded; I confirm
only that **nothing changed there** (`git diff --stat 7f50949dc..HEAD -- app/services/ app/db/
app/routers/` is empty; `RUNTIME_AGENTRUNTIME` still has one definition and one test reference, no
producer). Round 2's F3 stands verbatim.

**Method.** Source read, plus static analysers and in-memory mutation. **No tracked file was
edited.** Where I needed a mutation I read the real source into a *string*, mutated it, and executed
it as a synthetic module — for the suite runs, injected via a pytest plugin living in a scratchpad
directory (`sys.modules["app.agentruntime.surface"]` rebound in `pytest_configure`). I ran
`agentruntime-membrane-gate.py` (exit 0), its `--selftest` (exit 0), and
`pytest tests/test_cp1_membrane.py` (**62 passed**, up from 61). I read rounds 1 and 2 and treated
every finding in them as a claim to re-test.

---

## 1 · Verdict

**Overall: FAIL.**

| # | claim | round 2 | round 3 |
|---|---|---|---|
| 1.1 | manifest generated, starts empty | PASS | **PASS** — unchanged, re-confirmed |
| 1.2 | import-graph gate | PASS | **PASS** — unchanged, gate still wired at `lint-foundation.yml:94` |
| 1.3 | discovery reads the manifest only | PASS (mechanism) | **PASS (mechanism)** — M3's test is materially better and still has no subject (§4) |
| 1.4 | construction IS validation; **P4** | FAIL | **FAIL** — P4 untouched and out of scope. M4's *disclosure* is honest; §6.1 layer 2's new scan does not deliver what the row still concludes (§3) |
| 1.5 | unresolvable reference fails generation | PASS | **PASS** — unchanged |
| 1.6 | C-0 identity, owner derived | PASS w/ residual | **PASS w/ residual** — unchanged |
| 1.7 | every narrowing registers | FAIL (vacuous gate) | **FAIL** — the vacuity is genuinely closed, but the fix is **not** what its docstring claims, and it left a **third** silent-drop copy in the exported API |

**The two changes are real but both are narrower than stated.** Round 2's vacuity finding on 1.7 is
closed — the new conservation check *does* go red on a real defect, which I proved by mutation. Its
docstring's claim that it "cannot be defeated by a new function shape" is false, and I have six
counterexamples. The forgery scan exists and fires, on exactly the three shapes its author enumerated
and on nothing else — ten other working shapes pass it, including a one-line `getattr`.

---

## 2 · The falsifier — what would have made each of these PASS, and what I did instead

1. **1.7 / the conservation law.** It would pass if a silent narrowing anywhere in the module broke
   the arithmetic. Method: injected six silent narrowings, four by executing a mutated synthetic
   module, two by running the **whole 62-test suite** against a mutated `surface.py`. **Four of six
   went undetected; two of those left the entire suite green.**
2. **`rows_of` unification.** It would pass if `grep` found exactly one reader of `declarations`.
   Method: `grep -rn 'get(["'"'"']declarations'` repo-wide, then executed all three readers on three
   malformed documents. **Found a third, and it is the exported one.**
3. **The forgery scan.** It would pass if the shapes a determined bypass would actually use were
   detected. Method: ran the gate's own `_forgery_violations_in` over 13 probe files, then executed
   the two most likely forgeries against the real `Admitted` to confirm they work rather than merely
   go unseen. **10 of 13 undetected; 2 executed and produced usable `Admitted` objects.**
4. **M3's non-vacuity floor.** It would pass if the floor guarded the side of the comparison that can
   cause a false green. Method: executed the test's own expression and substituted 315 fictional
   names. **The assertion is identical.**
5. **The prose.** Method: took every enforcement verb added to §3 and §6.1 in this delta and looked
   for the mechanism. **Two of the three ✅ rows overstate; layer 2's conclusion overstates.**

---

## 3 · Question by question

### Q1 · Can the conservation law fire? — **YES, and here is what it misses**

`tests/test_cp1_membrane.py:432-501`. Round 2's vacuity is **genuinely closed**: the check now
executes the module instead of parsing it, and I proved it red-able two ways.

Mutations injected into a string copy of `surface.py`, run against the full suite:

| mutation | conservation test | whole suite |
|---|---|---|
| **H** — `_narrow` drops the last row without recording | **RED** | 5 failed / 57 passed |
| **R** — `rows_of` drops the first row silently | **RED** | 4 failed / 58 passed |
| **F** — `discover` skips a row that has no `kind` key | green | **62 passed** |
| **G** — `assemble` drops when `rules` is empty | green | **62 passed** |

**G is the finding.** `assemble` is the checkpoint's core mechanism — *"the single assembly point.
The only place a declaration can be removed"* (`surface.py:116`). Under G,
`SurfaceAssembler(doc).assemble(pass_number=1)` returns **1 of 3 names with `withheld=()`** — a
silent narrowing at the one place the design says a silent narrowing is inexpressible — and **all 62
tests pass.** The reason is that the conservation law drives `assemble` on exactly **one call shape**:
one rule, one pass, one 3-row fixture. A drop on the `rules == ()` branch is never evaluated. That is
the eight-frame legacy defect the test's own docstring cites — *"inside a branch that stage does not
take"* — reproduced in the gate written to prevent it.

F is the same class one level down: the fixture's rows all carry a `kind`, so a drop keyed on its
absence is never exercised.

**Its enumeration is by parameter name, and here is what that misses.** The filter is
`inspect.isfunction(fn) and not name.startswith("_") and params[0] == "manifest_doc"`, over
`vars(surface)` only. Executed against synthetic modules, each containing one silent drop:

| shape | enumerated? |
|---|---|
| `def prune(doc, ...)` — first parameter named `doc` | **no** |
| `def narrow(rows, ...)` — takes rows, i.e. **the shape `_narrow` itself has** | **no** |
| `def _prune(manifest_doc)` — leading underscore | **no** |
| `SurfaceAssembler.offer(self, manifest_doc)` — a method, not a module-level function | **no** |
| `discover(..., owner="book-service")` — a new defaulted keyword that filters unconditionally | **yes** |

The parameter-name filter means the enumeration covers exactly the functions that take a *whole
manifest document*. The narrowing primitive in this package takes **rows**, not a document, so the
most natural next narrowing helper — a sibling of `_narrow` — is invisible **by construction**, and so
is anything on the class, anything private, and anything whose author picked a different parameter
name. It also parses one module: a drop added to `manifest.py`, `narrowing.py` or a new file is out of
scope, exactly as it was in v2 (round 2's second limit on F1 is not closed).

The docstring at `:452-454` therefore asserts three things that are false:

> "That cannot be defeated by **how an AST renders** ✅, **by a new function shape** ❌, or **by a
> helper written in a style the classifier did not anticipate** ❌ — a silent drop breaks the
> arithmetic whatever it looks like ❌."

and `:467-469`'s *"a narrowing helper added tomorrow is covered the day it is written"* holds only for
a helper whose first parameter is spelled `manifest_doc`.

**Assessment:** a real gate that fires on real defects, over-claimed by its own comment. Not vacuous.
Not the conservation law it says it is — it is a conservation law sampled at five points.

### Q2 · Is there exactly one `rows_of`? — **NO. There is a third copy, and it is the exported one.**

`grep -rn 'get(["'"'"']declarations'` over the repo returns four readers. Three are in the package:

| site | behaviour on `{}` | behaviour on `{"declaratons": [...]}` (typo) |
|---|---|---|
| `surface.py:39` `rows_of` | `ValueError` | `ValueError` |
| `manifest.py:190` `validate_document` | `UntrustedRow` | `UntrustedRow` |
| **`manifest.py:222` `declarations()`** | **`[]` — silent** | **`[]` — silent** |

Executed. `manifest.declarations({})` → `[]`; `declarations({"declarations": None})` → `TypeError`
from `list(None)`. This is round 2's **F2 verbatim**, in a different function, and it is the *worse*
location of the two:

- `declarations` is exported — `__init__.py:38` and `__all__` at `:51`.
- **`rows_of` is not exported** — `"rows_of" in app.agentruntime.__all__` is `False` and
  `hasattr(pkg, "rows_of")` is `False`. So the package's public "give me the rows" API is the silent
  one, and the strict one is not reachable from `app.agentruntime`.
- `declarations()` has no docstring, no test, and no caller anywhere in `services/chat-service`
  (`grep` for `declarations(` excluding the `def`: nothing). It is exported, untested, unused, and
  carries the defect.

The `rows_of` docstring (`surface.py:29`) says *"🔴 **ONE PLACE**, because two hand-written copies of
this drifted inside a single commit"* — written while a third copy sat in a sibling module of the same
package, exported by the same `__init__.py`. This repository has a standing rule about exactly this:
consolidation claimed in a docstring is not consolidation; count the call sites per consumer. The
count was two.

Nothing outside the package reads `declarations` today, so this is latent rather than live — but it is
the same silent-empty conflation, in the API a CP-2 consumer would reach for first.

### Q3 · The forgery scan — what it detects, and what it misses

**What it detects** (`scripts/agentruntime-membrane-gate.py:173-224`), in any `*.py` under the repo
except `admission.py`, and only in files whose raw text contains `"agentruntime"` or `"Admitted"`:

- an `ast.ImportFrom` alias, `ast.Name` id, or `ast.Attribute` attr equal to `_TOKEN` or
  `_AdmissionToken`;
- a call to `object.__setattr__(...)`.

I ran the gate's own `_forgery_violations_in` over 13 probes:

| shape | detected |
|---|---|
| `from app.agentruntime.admission import _TOKEN` (self-test #1) | **yes** |
| `from app.agentruntime.admission import _AdmissionToken` (self-test #2) | **yes** |
| `object.__setattr__(a, 'declaration', None)` (self-test #3) | **yes** |
| `getattr(m, "_TOKEN")` | **no** |
| `m.__dict__["_TOKEN"]` | **no** |
| `vars(m)["_TOKEN"]` | **no** |
| `getattr(m, "_TOK" + "EN")` | **no** |
| token taken from `admit.__globals__` by a runtime key search — **no private name appears at all** | **no** |
| `from .admission import _TOKEN` in a **new module inside the package** | **no** |
| `object.__setattr__` in a package-relative helper | **no** |
| file 2 of a two-file split, naming only a public re-export | **no** |
| `Surface(names=..., pass_number=1, withheld=())` outside the package | **no** |
| subclass of `Admitted` | **no** (though a *working* subclass needs `object.__setattr__`, which is caught — verified: without it, `FrozenInstanceError`) |

Two of the undetected shapes I then **executed against the real class**, so these are working
forgeries and not merely unseen text:

```
tok = getattr(adm, "_TOKEN");  Admitted(d, "1.0.0", tok)
   -> Admitted(glossary_search),  isinstance True,
      build([forged])["declarations"] -> ['glossary_search']

key = [k for k in adm.admit.__globals__ if k.endswith("OKEN")][0]
Admitted(d, "1.0.0", adm.admit.__globals__[key])   -> works
```

Three structural holes are worth naming separately:

1. **The substring guard is an accidental exemption for the highest-privilege location.**
   `:182` returns early unless the source text contains `"agentruntime"` or `"Admitted"`. A new module
   **inside `app/agentruntime/`** using relative imports contains neither string, so
   `from .admission import _TOKEN` there is not scanned at all. The scan's declared boundary is
   "outside the module that defines it"; its actual boundary is "outside the package's own naming
   conventions".
2. **It matches symbol names, so one line of indirection defeats it entirely.** A public
   re-export — `def token(): return _TOKEN` in a helper — moves the private name into a file the guard
   skips, and the file that then forges the `Admitted` names only `token`. `_construction_sites`
   (`:143`) cannot backstop this: it scans `PACKAGE.rglob` only, so a second `Admitted(...)` call
   *outside* the package is not counted.
3. **It forbids the honest negative test.** The scan covers `tests/`. Any committed test proving the
   documented bypasses work would red CI — which is why round 2, and this round, had to execute them
   in memory. The gate ensures the boundary `admission.py:16-22` documents can never be backed by a
   test in the tree. (Docstring prose is safe: it parses to `ast.Constant`.)

Minor: `:216`'s exclusion is `"/.venv/" in rel` against a path with no leading slash, so a repo-root
`.venv/` would be scanned. It does not exist here, so no live effect.

**Does its self-test prove it red-able, or only the shapes its author thought of?** The latter,
demonstrably. `forgery_cases` at `:376-381` contains exactly three entries and they are exactly the
three shapes that pass; the negative case probes only "a module that never touches agentruntime". The
self-test never exercises `_forgery_scan` itself — not the `_ADMISSION_REL` exemption, not the walk,
not the exclusion prefixes — only the per-file helper on temp files. This is a real improvement on
round 2's F4 (a described capability now exists and is watched going red), and it is a strictly
smaller capability than the row it was written to make true.

### Q4 · M3's rewrite — is the floor real, and would a genuine leak fail it?

`tests/test_cp1_membrane.py:224-260`. Executed the test's own expressions:

```
legacy_tools  : 315   (floor: >= 300)   ['book_audio_generate', 'book_chapter_bulk_create', ...]
legacy_skills :  10   (floor: non-empty) ['book', 'co_write', 'composition', ...]
legacy_wf     :   9   (floor: non-empty) ['entity-triage', 'canon-check', 'kg-build', ...]
```

**The floor is real for what it guards, and it guards the wrong side.** The assertion is
`surfaced & set(names) == ∅`, and `surfaced = {r["id"] for r in discover(doc)}` is **`set()`** —
the committed manifest is empty. `∅ ∩ X = ∅` for every `X`. I substituted 315 fictional names:
**the assertion is identical.** The floor proves the right-hand side is populated; nothing asserts
that the left-hand side has a subject, and the left-hand side is what makes it trivially true.

**Would it fail if a legacy declaration genuinely leaked?** **Yes** — `glossary_search` is among the
315, so a leaked row or a leaking code path in `discover` would land in `surfaced` and fire the
assertion. The check is armed *in principle* and has *no subject at CP-1*, which is the same standing
as round 2's NV-3 — but it is a materially better test: the names are now real, read from source, and
the check becomes live the moment CP-4 admits a row. This is progress, not closure, and §3's ✅ (below)
records it as closure.

Two accuracy notes on the docstring:

- *"reads the three legacy registries"* — two of them. Skills (`skill_registry.LOADABLE_SKILL_CODES`)
  and workflows (`intent_workflows._COMPILED`) are live imports. **Tools are read from
  `contracts/agent-runtime-baseline/tools-list.snapshot.json`**, a frozen artifact produced manually
  by `scripts/freeze-tool-catalog.py` with no drift gate against the live registry. 315 of the 334
  names — 94% — come from a committed snapshot.
- *"the names are read from the legacy source rather than typed here, so the test stays honest as
  those registries change"* — false for the tools. A tool added to the legacy registry tomorrow is
  absent from this test until someone re-freezes the snapshot.
- `snapshot.get("tools") or snapshot` (`:243`) falls back to iterating a dict's **keys** if the shape
  ever changes, producing `TypeError: string indices must be integers` rather than a clear failure.

### Q5 · The artifact as it stands — does the prose still overstate?

**§3's gate table: yes, in two of the three ✅ rows — and the table cells themselves were not edited.**
The amendment is an appended block (`ARCHITECTURE.md:849-864`); `:840-844`'s cells still read
*"manifest row count == admitted count"*, *"a test that **seeds** a legacy-only declaration"*, and
*"refuses to boot"* verbatim. A reader who reads the table finds the original claims.

| row | amendment says | what exists |
|---|---|---|
| M1 | ✅ *"now true, and it was not"* | The gate compares the file to `build([])`. There is no admitted count and nothing to compare one against. The amendment's own prose says so accurately, then marks the cell ✅. **Overstated by the tick, honest in the sentence.** |
| M3 | ✅ *"now true… with a non-vacuity floor so an empty registry cannot pass it silently"* | The test does **not** seed, and the floor does not close the vacuity — it guards the populated side of an intersection whose other side is empty. **Overstated.** |
| M4 | 🔴 *"STILL FALSE, and it is not CP-1's to make true"* | Correct, and the right call. **The most honest cell in the document.** |
| M5 | ✅ | Correct. |

The amendment's closing lesson — *"a correction applied to the clause a verifier quoted, and not to
the other places making the same claim, leaves the document more misleading than before"* — is the
right lesson, and it was applied by appending a note under an unedited table rather than by fixing the
cells. A reader who checks one cell still finds it inaccurate and may stop.

**§6.1 layer 2: closer, still overstates.** `ARCHITECTURE.md:1035` now discloses the scan's real
scope — *"`_TOKEN`, `_AdmissionToken` and `object.__setattr__` in any module mentioning
`agentruntime`, everywhere except `admission.py` itself"* — which is an accurate description of the
implementation, including the substring guard. That is a genuine correction of round 2's F4. But the
row's premise and conclusion are unchanged and both are false:

- premise: *"a bypass **must** either name a private symbol or call `object.__setattr__`"* — it must
  not; `getattr(m, "_TOKEN")` does neither, and it works;
- conclusion: *"so a deliberate bypass is **loud in the diff that introduces it**" —* ten of the
  thirteen shapes I probed are silent, two of them executed successfully against the real class.

The accurate statement is: *the gate makes the three most obvious bypass spellings loud in a diff.*

---

## 4 · Findings

### F1 · A silent drop at the single assembly point leaves the entire suite green
`services/chat-service/app/agentruntime/surface.py:115-131`, gate at `tests/test_cp1_membrane.py:492-498`

`assemble` is evaluated by the conservation law on exactly one call shape (one rule, `pass_number=1`,
a 3-row fixture). Injecting `if not rules: kept = kept[:1]` yields
`assemble(pass_number=1)` → **1 of 3 names, `withheld=()`** — and **62/62 tests pass**. Proven by
running the real suite against an in-memory mutated module.

### F2 · The `rows_of` unification left a third copy, and it is the exported one
`services/chat-service/app/agentruntime/manifest.py:222`, exported at `__init__.py:38`/`:51`

`declarations({})` → `[]`, silently — round 2's F2 in a new location. `rows_of` is **not** exported,
so the package's public row-reader is the silent one. `declarations()` has no docstring, no test and
no caller.

### F3 · The conservation law's enumeration is blind to four function shapes
`services/chat-service/tests/test_cp1_membrane.py:470-475`

Filtered by `params[0] == "manifest_doc"` over `vars(surface)` only. A helper taking `rows` — the
shape of `_narrow`, the module's own narrowing primitive — a private helper, a method, or a helper
whose first parameter has another name are all invisible. Each proven by execution. Only `surface.py`
is examined; `manifest.py` and `narrowing.py` are not.

### F4 · The forgery scan detects three spellings, not a class of bypass
`scripts/agentruntime-membrane-gate.py:173-224`

10 of 13 probed shapes undetected; two executed and produced usable `Admitted` objects. The
substring guard at `:182` exempts package-relative modules — the highest-privilege location in the
repo. One line of public re-export defeats the whole scan, and `_construction_sites` cannot backstop
it outside the package. The self-test proves exactly the three shapes its author enumerated.

### F5 · The forgery scan forbids the honest negative test
The scan covers `tests/`. A committed test demonstrating the documented bypasses would red CI, so the
boundary `admission.py:12-26` honestly documents can never be evidenced by a test in the tree.

### F6 · M3's non-vacuity floor guards the wrong side of the intersection
`services/chat-service/tests/test_cp1_membrane.py:249-254`

`surfaced` is `set()`; the assertion is identical with 315 fictional names — proven by substitution.
Tools come from a frozen snapshot, not the live registry, contradicting the docstring at `:232-234`.

### F7 · Round-2 findings re-tested and still open
F3 (P4 — out of scope, unchanged), F5 (all six round-1 residuals: `_TOKEN` importable,
`object.__setattr__` on a live instance, subclassing, `Surface` constructible outside the package,
duplicate id reported as an unresolved reference at `manifest.py:127`, `source_path` authored),
F6 (a configured-but-absent manifest reads as empty at `manifest.py:52-54`). None were in scope of
this delta; none were addressed.

---

## 5 · Vacuity (NV) — this delta only

| # | check | armed? |
|---|---|---|
| NV-4 | conservation law (`tests:432`) | **YES, partially.** Fires on drops in `_narrow` and `rows_of` (both proven RED). Blind to drops on unexercised branches of the functions it *does* call (F, G) and to four function shapes it never calls. Round 2's total vacuity is closed |
| NV-8 | forgery scan (`gate:173-224`) | **YES for three spellings.** Its self-test fires on those three and only those. No realistic input distinguishes a determined bypass from clean code |
| NV-3 | M3 three-kind test (`tests:224`) | **STILL NO SUBJECT.** Real names, real floor, empty left-hand side. Armed for CP-4; today `∅ ∩ X` |
| NV-9 | `rows_of` refusal (`surface.py:39`) | **YES** — executed on three malformed documents via both callers; and **not** applied by the third reader (F2) |

---

## 6 · The bypass table (delta items only)

| item | the path that defeats it, or the search that found none |
|---|---|
| 1.7 · "every narrowing registers" | **Two paths, both executed.** (a) `assemble` on a branch the single fixture never drives — 62/62 green with 2 of 3 declarations silently dropped and `withheld=()`. (b) `manifest.declarations()` (`manifest.py:222`), exported, returns `[]` for a malformed document with no record — round 2's F2, relocated. Plus four function shapes the enumeration cannot see (F3) |
| §6.1 layer 2 · "loud in a diff" | **Ten paths.** `getattr(m, "_TOKEN")` and a runtime key search over `admit.__globals__` both executed and both produced usable `Admitted` objects while the scan reported clean. A package-relative import of the token is not scanned at all (substring guard). A one-line public re-export moves the private name out of scanned territory |
| M3 · "seeds a legacy declaration of each kind" | **No code path found** — `discover` reads one parameter, `grep -rn agentruntime` finds no importer or bridge. The *test* cannot fail today: substituting 315 fictional names changes nothing |
| M1 / `rows_of` unification | **One reader remains unconverted** (`manifest.py:222`), found by `grep -rn 'get(["'"'"']declarations'` and confirmed by executing all three readers on `{}`, `{"declarations": None}` and a key typo |

---

## 7 · Summary for the record

Round 2's two FAILs were addressed with real code, and both fixes are smaller than their prose.

- **1.7's gate is no longer vacuous** — I made it go red twice on real defects, which round 2 could
  not. It is not the shape-independent conservation law it claims to be: it is that law sampled at
  five points against one fixture, and a silent drop at the single assembly point survives the whole
  suite.
- **The `rows_of` unification fixed the two copies a verifier named and missed the third**, which is
  the one the package exports. The docstring announcing "ONE PLACE" was written over a count of two.
- **The forgery scan is a genuine new capability** where round 2 found only a sentence, and its
  self-test is the right instinct. It detects three spellings of a bypass, not a bypass; `getattr`
  with a string literal walks through it and works.
- **§3's table cells were not edited** — an amendment was appended beneath them — and two of its three
  ✅ marks record as closed what is measurably still open. §6.1 layer 2 now describes its mechanism
  accurately and still concludes more than the mechanism supports.

The recurring shape across all three rounds is unchanged and is worth stating once more plainly: each
fix is correct at the layer the previous verifier named, and the claim written above it is one layer
wider than the fix.
