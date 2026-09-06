# CP-1 · round 23 · V-CODE **B — the membrane**

**Artifact:** `9b77caed789e9f2737f849d63b1485a65bcbd8a4` at start **and** at finish — it did not move.
Graded delta `bc1452f4c`, diffed against `c37459826`.
`git status --porcelain` **empty** at start and at finish. **No `git checkout` at any point**; every
injection was patched and restored as BYTES from my own scratchpad snapshot, and **14/14 files are
byte-identical to that snapshot** at finish (8 package modules, 2 contracts, 2 scripts, the suite,
the workflow).

---

# ▶ THE CENSUS VERDICT — **the four things that made it unusable are genuinely fixed. Its ID is not injective, and its own test is green over its own removal.**

R22-A named the distance to closure as four ≤10-line changes. All four shipped, and — unusually for
this run — **the four that were executable closures actually closed.** I killed it six ways and the
tree stayed clean every time; twenty concurrent suite runs went green against a control of twenty
green; the ids are identical across both interpreters this repo pins; a reworded message no longer
moves a row. Those are the first four closures in this run that survived an independent enumeration.

What did not close is one level in: **the id the allowlist is keyed on is not a function of the
site.** And the test written to protect all of it is green under eight of eight realistic
disablements *and* under one of its own three controls.

| # | prompt item | verdict | the number |
|---|---|---|---|
| 1 | kill it every way | ✅ **6 of 6 termination modes leave the live tree byte-clean** | executed, 6 kill runs + a full census |
| 2 | reorder / reindent / rename / reword | 🟡 **2 clean, 1 by design, 1 half** — reword-in-place 0/64 ✅, but **15 of 17 f-strings move on a boundary edit** and **3 of 43 null reorders move NOTHING** | executed, enumerated |
| 3 | version stability | ✅ **68/68 ids identical on 3.12 and 3.13; 13/13 allowlist rows exist under both** | executed, 2 interpreters |
| 4 | green while the census does not run | 🔴 **8 of 8 bypasses green, and 1 of 3 controls fails to red** | executed |
| 5 | the allowlist header | 🟡 **¶1 is true of all 13. The retraction landed in 1 of 3 places, and one of its two stated reasons is REFUTED** | executed |

## 0.1 · Item 1 — I killed it six ways. **The live tree survived all six.**

Every run: the census launched against the live tree, killed at a chosen offset spanning all four
phases (selftest suite, mirror copy, selftest neuter, census neuter loop), then all eight package
modules **and** the allowlist byte-compared against a pre-run snapshot I took myself, plus
`git status`.

| # | termination mode | t | rc | live tree afterwards |
|---|---|---|---|---|
| K1 | `taskkill /F` — TerminateProcess, during the selftest's live-suite run | 5 s | 1 | ✅ **CLEAN** |
| K2 | `taskkill /F` — during the mirror copy | 30 s | 1 | ✅ **CLEAN** |
| K3 | **`taskkill /F /T`** — the whole process tree, child pytest included | 75 s | 1 | ✅ **CLEAN** |
| K4 | `Popen.kill()` — inside the census neuter loop | 150 s | 1 | ✅ **CLEAN** |
| K5 | `CTRL_BREAK_EVENT` to a new process group | 60 s | 3221225786 | ✅ **CLEAN** |
| K6 | **`os.kill(pid, SIGTERM)`** — which on Windows *is* TerminateProcess | 100 s | 15 | ✅ **CLEAN** |

**6 of 6.** R21 measured 4 of 4 kills damaging the tree; R22 measured 3 of 5. The mechanism is right
and it is right for the right reason: there is no handler to miss, because there is nothing to
restore. `census()` and `_selftest()` both write only inside a `tempfile.mkdtemp()` copy. **This
closes B22-3, B22-4, B22-6 and the four-round-old "probe modules are written into the live tree"
finding together**, and it deletes 24 lines rather than adding any. It is the best change this run
has produced.

The full census confirms it end to end:

```
agentruntime-census selftest OK - 68 raise sites, fires on a guarded one
agentruntime-census: 68 sites, 13 silent, 55 red      rc=0      433 s (7 m 13 s)
git status --porcelain: (empty)   all 8 package modules byte-identical to my pre-run snapshot
```

**Sixth independent reproduction of `68/13/55`**, and the runtime is down from R22's 9 m 48 s.

### What the mirror does **not** reproduce

| thing | reproduced? | does it matter here? |
|---|---|---|
| **untracked files** | ❌ — `git ls-files` lists the index only | **latent.** An untracked new module in `app/agentruntime/` is not censused; an untracked new test that would move a site SILENT→RED is not seen, so a developer who writes the closing test and has not `git add`ed it gets the **old** answer |
| **file modes** | ❌ — `shutil.copyfile` drops permission bits; 25 tracked files are `100755` | no — none of the 25 is on the suite's path (enumerated) |
| **submodules** | n/a — `.gitmodules` absent | no |
| **symlinks** | n/a — 0 entries of mode `120000` in the index | no |
| **`.git`** | ❌ | no — nothing on the suite's path shells out to git (the suite reads `_REPO/...` as plain files, and all of those are tracked; I ran the suite in a mirror: **136 passed**) |
| **a dirty index** | partially — content comes from the **working tree**, membership from the **index** | 🔴 **B23-10.** The docstring says it measures *"what is about to be committed."* It does neither: it includes **unstaged** modifications, which will not be committed, and excludes **untracked** files, which may be. In CI (`actions/checkout`) working tree == HEAD, so the sentence is only wrong locally — where it is the pre-commit gate the same sentence claims it is |

### 🔴 B23-6 — the mirror is never deleted. **214 MB × 2 per run, forever.**

`_mirror()` is `tempfile.mkdtemp()` with no cleanup, and it is called **twice** per full run — once in
`_selftest()` and once in `census()`. Measured: **36–43 s, 13,579 files, 213.8 MB each.** Before my
census this machine held 8 leaked mirrors from the builder's own runs; after my census and the kill
matrix, **20 directories totalling 4.4 GB** (`du -shc`). A script whose docstring calls it a
pre-commit gate leaks 427 MB per commit. `finally: shutil.rmtree(mirror, ignore_errors=True)` is two
lines. The second call is also redundant with the first: 36 s of a 433 s run, 8% of the runtime, for
a copy that already exists.

### 🔴 B23-12 — the baseline and the measurements are taken on **two different subjects**

`census.py:235` is `if not _suite_is_green():` — **no `cwd`**, so it defaults to `CS`, the **live**
tree. Every one of the 68 measurements, and the selftest's own probe, run in the **mirror**
(`:213`, `:250`). The gate that decides "the suite is green before any injection" and the experiment
that decides SILENT vs RED therefore stand on different trees, and nothing checks that they agree.
Executed today: live `136 passed`, mirror `136 passed` — they do agree. I then tried to force a
divergence by removing a support file from the mirror only and **failed to produce one** (the suite
does not depend on it), so I am recording this as a structural asymmetry with a **negative** result
attached, not as a demonstrated hazard. The one-word fix is `_suite_is_green(mirror / _CS_REL)`.

## 0.2 · Item 2 — reorder, reindent, rename, reword. **Enumerated; two clean, one by design, one half.**

68 sites re-derived independently with the census's **own** `_sites`
(`{admission 4, canon 4, contract 18, manifest 17, surface 25}` — the sixth convergence), then every
edit class applied in memory and the ids re-derived.

| mutation | **should** it move a row? | **does** it? | n |
|---|---|---|---|
| **reindent** (wrap the raise one level deeper in `if True:`) | NO | ✅ **NO** | 0 / 68 |
| **reword IN PLACE** (substitute characters inside an existing literal chunk) | NO | ✅ **NO** | 0 / 64 (4 N/A) |
| **rename** the enclosing function | yes — the qualname is the address the allowlist points a reader at | ✅ yes | 68 / 68 |
| **reword AT A BOUNDARY** (append text after an f-string's last interpolation) | NO | 🔴 **YES** | **15 / 17**, displacing **3 allowlisted rows** |
| **reorder** two same-class `if …: raise` blocks (semantically null) | — disputed, see below | 🟡 40 moved / **3 moved NOTHING** | 43 pairs enumerated |

**R22's headline defect is closed.** A one-character message edit moved 13/13 rows then; a
content-only reword moves **0 of 64** now. That is real and it was the most frequent edit in the
package.

### 🔴 B23-2 — the digest is blind to prose *content*, not to prose *segmentation*

The digest blanks each `ast.Constant` of type `str` **individually**. An f-string is a `JoinedStr`
whose literal chunks are separate `Constant` nodes, so **adding or removing a chunk changes the node
count** and moves the row. Concretely, extending

```python
raise ContractViolation(row["id"], f"{where}.{exc.field_path}", exc.reason, exc.accepted) from exc
```

to `f"{where}.{exc.field_path} (row {i})"` adds one `Constant` and relocates the row. **15 of the 17
raise sites whose f-string ends on an interpolation move**, and **3 allowlisted rows are among them**
(`check_row_shape::2`, `::3`, `check_row::1` and three more in `contract.py`). This is not a rare
edit — it is how you add context to a message. Fix: collapse each `JoinedStr` to a single blanked
`Constant` before hashing. Two lines.

### 🔴 B23-1 — the id is **not injective**, and the docstring's *"98/98 pairs, 0 collisions"* is false

Blanking every string literal makes `raise ValueError("<anything>")` unparse to `raise
ValueError('\x00')`. So:

* **68 sites collapse to 54 distinct digests.**
* `85310b4a` covers **9** sites; `0fb853fb` covers 4.
* **4 groups share `(module, qualname, ExcClass, digest)` — 8 sites — and 2 of the groups contain an
  allowlisted row:**

| group | members | allowlisted |
|---|---|---|
| `canon.py::_norm::NotCanonicalisable` | `::1::50f6dc36` · `::3::50f6dc36` | ✅ `::1` |
| `contract.py::check_contract::ContractViolation` | `::5::7aefcf3d` · `::6::7aefcf3d` | — |
| `surface.py::OrderBy.__post_init__::ValueError` | `::2::85310b4a` · `::5::85310b4a` | — |
| `surface.py::TakeWhileBudget.__post_init__::ValueError` | `::1::85310b4a` · `::2::85310b4a` | ✅ `::1` |

For those 8 sites the digest contributes **zero** disambiguation and the id degenerates to exactly
the pre-delta ordinal id. I executed the consequence — a null swap of `TakeWhileBudget`'s two
`if …: raise` blocks (surface.py:388 ↔ 390):

```
BEFORE   surface.py::TakeWhileBudget.__post_init__::ValueError::1::85310b4a
   names: raise ValueError('take_while_budget needs a non-negative budget')
AFTER a null swap:
   id set identical: True   |  row still present: True
   the SAME id now names: raise ValueError('take_while_budget must name the field it accumulates')
```

**The allowlisted row survives the swap and points at a different refusal.** That is verbatim the
failure `census.py:154-159` says the digest was added to prevent: *"Reordering two same-class raises
that are BOTH silent produced rc=0 and an allowlist pointing at the wrong sites."*

**The honest limit of this finding:** today the two members of each pair have *different* silent/red
status, so the census would still print a `NEWLY SILENT`/`NOW GUARDED` pair and exit 1 — the gate
catches the swap by **status**, not by **id**. So the defect is latent, not live. What is *not*
latent is that `module::qualname::ExcClass::ordinal::digest` is not a key, and "a finding is closed"
is defined as "**this named site** moved SILENT → RED".

**The fix is smaller than the bug:** drop the ordinal and append a counter only on a genuine digest
collision — `module::qualname::ExcClass::digest[::n]`. Three lines. It makes the id injective, and it
makes a null reorder move **nothing**, which also settles the reorder dispute: my predecessor said a
null reorder should not move a row, the builder's docstring says it should. **Neither position is
reachable while the ordinal is in the id** — the builder's "it does move" is an artifact of the
ordinal, not of the digest, and it is exactly why 3 of 43 pairs move nothing at all.

### 🔴 B23-3 — *"a digest blind to prose"* blanks more than prose. **It blanks the contract.**

The prompt asks whether blindness to a message that changes what the refusal *means* matters. It
does, and not hypothetically. `_shape_digest` blanks **every** string constant in the statement, and
in this package many of them are not prose:

* **field-path literals.** `ContractViolation(d.id, 'members', …)` → `ContractViolation(d.id,
  'source_path', …)` mis-attributes the violation to the wrong field. The digest does not move.
* **`row['id']`** — a subscript key. `row['id']` → `row['kind']` changes which value is reported as
  the offender. The digest does not move.
* **the C-12 payload itself.** I enumerated **13 raise sites** that pass a *literal* string as
  `reason` or `accepted` — the two fields C-12 promises are structured rather than prose, e.g.
  `ContractViolation('', where, f'is a {type(row).__name__}', 'a plain JSON object')` and
  `ContractViolation(d.id, 'members', 'a tool has no members; …', 'an empty members tuple')`.

So the digest is blind to a class of change that alters what a consumer of `ContractViolation` reads
programmatically. **Does it matter for the census's job?** Partly. If the site is RED, the suite is
the oracle and the census's blindness costs nothing. If the site is SILENT — and 13 are — then
*nothing* checks the payload and the id cannot see it change either. The two blind spots are the
same 13 rows. That is worth one sentence in the docstring, which currently claims only that prose is
erased.

## 0.3 · Item 3 — **version stability: PASS, with a bounded caveat, executed on three interpreters**

| interpreter | sites | ids vs 3.13 | allowlist rows present |
|---|---|---|---|
| **3.13.12** (my census, and a second CI job) | 68 | — | **13 / 13** |
| **3.12.10** (the census job pins this) | 68 | ✅ **IDENTICAL, 68/68** | **13 / 13** |
| 3.11.14 | — | ❌ **crashes** | — |

The defect that made the previous gate print a plausible lie — *0 of 68 ids portable, 0 of 13 rows
existing, 13 false `NEWLY SILENT` + 13 false `NOW GUARDED`* — is **closed** for the two interpreters
this repository actually uses. `ast.unparse` is stable where `ast.dump` was not.

On 3.11, `_shape_digest` raises `ValueError: Unable to avoid backslash in f-string expression part`
— the blanked `'\x00'` lands inside an f-string expression, which PEP 701 legalised in 3.12. **The
repo pins 3.12 everywhere, so this is out of scope as a defect**, and it fails *loudly*, which is
the right failure. But the docstring's unqualified *"stable across interpreters"* is bounded at
3.12+ and does not say so. One word.

## 0.4 · Item 4 — **green while the census does not run: 8 of 8. And a control failed.**

The delta's own comment says: *"Deleting the `Refusal census` step, replacing it with `echo skip`, or
switching it to `--write` all left this test GREEN, measured. Both halves are asserted now."* Two of
those three are now caught. **The comment is not** — for the third time in this run.

Enumerated over the test's seven assertions, each defeated the way a person would actually do it:

| # | mechanism | test | what actually happens |
|---|---|---|---|
| B1 | `if: false` on the step | 🔴 **GREEN** | the census **never runs** |
| B2 | `run: python scripts/agentruntime-census.py --selftest` | 🔴 **GREEN** | `--write` is forbidden; `--selftest` is not. **The allowlist is never compared.** rc=0 always |
| B3 | `continue-on-error: true` | 🔴 **GREEN** | drift cannot fail CI |
| B4 | run line **commented out**, `run: echo skip` | 🔴 **GREEN** | a comment satisfies the substring — **3rd time this run** |
| B5 | job-level `if: github.event_name == 'schedule'` | 🔴 **GREEN** | the job never runs on a PR |
| B6 | `census()` neuters the LIVE package, spelled `ROOT / _PKG_REL` | 🔴 **GREEN** | see below |
| B7 | `getattr(atexit, 'register')(…)` | 🔴 **GREEN** | `'atexit.register' not in src` holds while atexit **is** registered |
| B8 | all 13 digests rewritten to `::deadbeef` | 🔴 **GREEN** | the assertion is `re.search(r'::[0-9a-f]{8}$')`, a **shape** |

Controls, to prove the test is not inert:

| # | control | test | verdict |
|---|---|---|---|
| C1 | the run line deleted outright | ✅ red | correct |
| C2 | `--write` in the job | ✅ red | correct |
| C3 | **`def _mirror` renamed to `def _mirrorX`** | 🔴 **GREEN** | — |

**C3 is the one that matters.** `assert "_mirror" in src` is a **substring**, and `_mirrorX` contains
`_mirror`; the word also survives in the docstring. Executed:

```
C3  python scripts/agentruntime-census.py --selftest
    rc = 1   NameError: name '_mirror' is not defined. Did you mean: '_mirrorX'?
```

**The test written to protect the census is green over a census that cannot start.**

### 🔴 B23-5 — the live-tree-write guard forbids a *spelling*, not a *behaviour*

`assert "PKG.glob" not in _census_body` forbids one expression. I replaced the mirror with the live
tree without using it — `pkg, cs = ROOT / _PKG_REL, ROOT / _CS_REL`, one token changed — and executed
the consequence:

```
B6  live-tree files neutered WHILE RUNNING:      ['admission.py']
B6  live-tree files left DIRTY after a hard kill: ['admission.py']
B6  the test:                                     GREEN
```

**The single fix that closes four findings this round is guarded by a string literal.** The
assertion that would actually hold is executable and short: run `census()` against a fixture, then
assert every live package file is byte-identical afterwards. And the workflow half should parse the
YAML — assert the step exists, has no `if:`, no `continue-on-error:`, and that its `run` is *exactly*
`python scripts/agentruntime-census.py` — instead of five substring searches over a blob that a
comment satisfies.

## 0.5 · Item 5 — the allowlist header. **True of all 13. Landed in 1 of 3 places. One reason refuted.**

**¶1 is now true.** *"Refusal sites the suite does not notice being removed ON THEIR OWN"* is exactly
what the instrument measures — it neuters one site at a time — and I reproduced 13 silent
independently. For all 13 rows the header now claims precisely what the experiment supports. That is
a genuine repair of my own R21/R22 finding, and I record it as closed.

**Then the same file retracts the retraction.** The committed artifact, lines 1–10:

```
 1  # Refusal sites the suite does not notice being removed ON THEIR OWN.
 3  # 🔴 The header used to say 'a refusal nothing checks', and two verifiers measured
 4  # that false for 2 of these 13 rows: …
 9  # Generated by scripts/agentruntime-census.py --write. Every line is a claim that
10  # nothing checks; adding one is a decision, and removing one is a closed finding.
```

**Line 9–10 re-asserts the retracted sentence verbatim, five lines below the retraction.** And
`census.py:304` prints it at runtime:

```python
print(f"NEWLY SILENT  {s}  <- a refusal nothing checks; guard it or record it deliberately")
```

That line is what a maintainer actually reads when the gate fires. **1 of 3 places.** Tenth pair in
this run fixed at one end, and this one is inside the artifact whose entire purpose is to stop
claiming more than the experiment supports.

### 🔴 B23-9 — *"or because it is UNREACHABLE"* is **refuted by execution**, in both cited rows

The header gives two reasons a row can be SILENT: a same-class sibling reds first, **or the site is
unreachable**. The second reason traces to B21-1/B21-2, which named two `except UntrustedRow` arms as
unreachable handlers. Both are **reachable**, and I drove them:

```python
class Evil:
    def __repr__(self): raise UntrustedRow("a bare UntrustedRow, raised by the caller's __repr__")
row = {..., "members": [Evil()]}
```

```
manifest.validate_document(doc) -> *** THE SECOND ARM FIRED *** re-raised from manifest.py line 428
manifest.build([], previous=doc) -> *** THE SECOND ARM FIRED *** re-raised from manifest.py line 245
```

The `try` body is `check_row(r, …)`, which interpolates caller-supplied values into f-strings — so it
calls `__repr__` on user objects, and a user object can raise any exception, including a bare
`UntrustedRow` (which is not a `ContractViolation`, so the first arm does not catch it). **The
membrane is not closed on the exception axis, and `manifest.py:426` documents that it calls user code
on purpose.** The word `UNREACHABLE` should come out of the header, and the claim out of the
RUNSTATE, unless someone can produce a proof I could not refute in ten minutes.

*Minor, in the same header:* *"two verifiers measured that false for 2 of these 13 rows."* R21-A
measured **2**; R21-B (me) measured **5**. One verifier measured 2. The published number is the
smaller one.

---

# ▶ THE TWO DESIGNS R22-B PRODUCED — **grade the design, not the intention. Do not build either as specified.**

My predecessor specified both. I am grading them, and both are wrong in their load-bearing claim.

## Design 1 · `effect ∈ {accepts, refuses-differently, no-observable-change}` — 🔴 **NOT computable from what pytest reports**

The design says: *"pytest gives it for free (`--tb=line`, or a 10-line `conftest` hook collecting
`(nodeid, repr(excinfo.value))`)."* I wrote that hook and ran it:

```
HOOK nodeid=test_a_passing_pytest_raises  outcome=passed  call.excinfo=None
HOOK nodeid=test_a_real_failure           outcome=failed  call.excinfo=<ExceptionInfo ValueError('this one fails')>
```

**`call.excinfo` is `None` for a passing test, including a passing `pytest.raises`.** pytest reports
the exception a test *failed* on; it does not report the exception a `pytest.raises` block
successfully caught. So:

* **the CONTROL run yields nothing.** Every test passes; every refusal in this suite is caught inside
  a `pytest.raises`. There is no "the control raised" set to diff against.
* the enum **is** computable for a **RED** site, from the neutered run alone: `DID NOT RAISE` →
  `accepts`; a `match=` failure or a wrong class → `refuses-differently`. That half is real and worth
  ~10 lines.
* it is **not** computable for a **SILENT** site, because a silent site's neutered run is green and
  reports nothing — **and the SILENT rows are the entire 2-vs-5 disagreement the column was designed
  to settle.**

**Verdict: build the RED half; the SILENT half as specified measures nothing.** What would work is
one level down and cheaper than 68 suite runs: instrument the *package*, not the suite. A single
control run under `sys.monitoring`'s `RAISE` events (3.12+, and the repo pins 3.12) records
`(nodeid, module, lineno, ExcClass)` for **every** raise, caught or not. From one 11-second run you
get: which of the 68 sites are never reached by any test (a corpus-relative DEAD candidate, honestly
labelled), and for a neutered site, **which sibling raised in its place, by name**. That is strictly
more than the three-way enum, it answers the disputed rows, and it does not require the suite to fail
to be observable. Say it in the verdicts as a design; do not ship it as a claim until someone runs it.

## Design 2 · `static ∈ {reachable, unreachable-handler}` — 🔴 **NOT decidable here, and its two worked examples are both wrong**

The design says: *"the two rows in dispute are `except UntrustedRow` arms whose `try` body calls only
in-package functions, and this package is a closed membrane by construction … So the raise-class set
of every callee is enumerable, and '`ContractViolation` subclasses `UntrustedRow` and is caught by
the arm above' is a **proof**, not a heuristic."*

**§0.5 refutes it by execution: both arms fire.** The `try` body is not closed, because it
interpolates caller-supplied values into f-strings and therefore calls `__repr__` on user objects —
a dunder, dispatched dynamically, outside the package, able to raise anything. A ~20-line AST pass
that enumerates in-package `raise` statements would label both arms `unreachable-handler` and **be
wrong on both**.

That is the part that makes this worse than a merely weak instrument: **the design's stated remedy
for `unreachable-handler` is "delete the handler."** Shipping it as specified would have told a
maintainer to delete two live defensive arms from the module that exists to be defensive — and the
column would have been labelled a *proof*.

**Verdict: do not build `static` as a proof.** A dead-code claim in this package must be
*dynamically* falsified before it is believed, and the vehicle is four lines (an object whose dunder
raises). If the column ships at all it must be `unknown` by default and may only ever say
`unreachable` when the try body's transitive callees touch no caller-supplied object — which, in a
membrane whose whole job is handling caller-supplied objects, is almost nothing.

**The pattern both designs share, and it is the one the prompt warned about:** each was specified
from a reading of the code and neither was executed before being written down as a mechanism. The
last three instruments in this run were shipped and then found to be measuring something adjacent.
These two were caught one step earlier, which is the improvement — *provided they are not built as
written*.

---

# OVERALL: **FAIL**

Not because the delta failed — **four findings closed for real and I could not break any of them**:
the kills (6/6), the concurrency (20/20 green against a 20/20 green control), version stability
(68/68 across both pinned interpreters), and the content-reword churn (0/64). That is the first
substantial closure count in this run, all four verified by an independent enumeration rather than
asserted.

It fails because **the id the whole closure criterion rests on is not a key** — 54 digests for 68
sites, and a null reorder that leaves an allowlisted row naming a different refusal; because **the
test written to protect all of it is green under 8 of 8 realistic disablements and under a control
that renames the function it is testing**; because **the single fix that closed four findings is
guarded by a string literal, and I executed the live-tree damage it lets through**; because **the
retraction in the allowlist header is contradicted by the same file and by the gate's own runtime
output**; and because **the two rows the header calls UNREACHABLE are reachable, which I executed in
both.**

## Per-claim verdicts, each with its falsifier

| # | claim under test | the falsifier I ran | verdict |
|---|---|---|---|
| 1 | a killed census leaves the live tree clean | 6 termination modes × byte-compare of 9 files against a pre-run snapshot | ✅ **PASS — 6 of 6 clean** |
| 2 | the census no longer interferes with concurrent runs | 20 treatment + 20 control suite runs | ✅ **PASS — 20/20 green vs 20/20 green** |
| 3 | the ids are stable across interpreters | derive all 68 on 3.11 / 3.12 / 3.13 | ✅ **PASS on 3.12↔3.13 (68/68, 13/13)**; crashes below 3.12, out of scope, undocumented |
| 4 | the CI job's green state is reachable | full run in the job's shape | ✅ **PASS — rc 0, `68/13/55`, 433 s** |
| 5 | a reworded message keeps its row | 68 sites × content-only substitution | ✅ **PASS — 0 of 64** |
| 6 | …and keeps it when the message is *extended* | 68 sites × append after the last interpolation | 🔴 **FAIL — 15 of 17, 3 allowlisted rows** |
| 7 | reindenting does not move a row | 68 sites × wrap in `if True:` | ✅ **PASS — 0 of 68** |
| 8 | *"reordering moves a row — 98/98 pairs, 0 collisions"* | 43 same-class adjacent `if: raise` pairs | 🔴 **REFUTED — 3 move nothing; 4 collision groups, 8 sites, 2 allowlisted** |
| 9 | the id pins the row to the refusal, not its position | null swap of `TakeWhileBudget`'s two blocks | 🔴 **FAIL — identical id set; the row names a different refusal** |
| 10 | the CI test asserts the census RUNS | 8 realistic disablements + 3 controls | 🔴 **FAIL — 8/8 green, and C3 green over a `NameError`** |
| 11 | the census cannot write into the live tree | re-spell the write, run it, kill it | 🔴 **FAIL — `admission.py` neutered and left dirty, test GREEN** |
| 12 | the allowlist header claims only what the experiment supports | read all three places the claim lives | 🟡 **¶1 true for 13/13; retracted claim survives at line 9 and `census.py:304`** |
| 13 | 2 of the 13 rows are SILENT because the handler is UNREACHABLE | drive a bare `UntrustedRow` through a caller `__repr__` | 🔴 **REFUTED — both arms fire (`manifest.py:245`, `:428`)** |
| 14 | the mirror measures "what is about to be committed" | inventory index vs working tree vs untracked | 🔴 **FAIL — wrong in both directions** |
| 15 | the mirror is cheap | time it, count temp dirs, `du` | 🔴 **36–43 s and 214 MB × 2 per run, never deleted; 4.4 GB accumulated** |
| 16 | `effect` is computable from what pytest reports | a `pytest_runtest_makereport` hook over a passing `pytest.raises` | 🔴 **REFUTED — `call.excinfo is None`** |
| 17 | `static` is decidable here | §0.5's vehicle | 🔴 **REFUTED — both "unreachable" arms are reachable** |
| 18 | `dict(r)` is shallow at all four doors | identity + post-call mutation + cross-door | 🔴 **CONFIRMED OPEN, 4th round** |
| 19 | its one test *requires* the defect | the full 2×2 | 🔴 **CONFIRMED — the truth table is inverted** |
| 20 | B18-8 open | 3 injections + a control | 🔴 **OPEN, 6th round** |
| 21 | B18-11 open | AST sweep | 🔴 **OPEN, 6th round** |
| 22 | B18-10 open | a fifth exported door vs suite **and** gate | 🔴 **OPEN, 9th round** |
| 23 | `surface.py:305` open | 5 vehicles × control/neutered | 🔴 **OPEN, 5th round** |
| 24 | `_ID` unbounded | 300 chars end-to-end | 🔴 **OPEN, 5th round** |
| 25 | R22's `Open, carried` is trustworthy | audit against both R22 verdicts | 🔴 **FAIL — 2 open findings absent, one raised by BOTH verifiers** |

---

## 2 · `dict(r)` is shallow at 4/4 doors — and I can now name exactly what the rewritten test must assert

**Re-measured, unchanged (4th round), now including `discover`:**

```
rows_of            members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
declarations       members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
validate_document  members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
discover           members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
cross-door: rows_of and declarations share ONE members list: True
```

The 2-line fix at both siblings (`surface.py:72`, `manifest.py:448`) remains as measured last round.
**The prompt asks what the rewritten test must assert. Here is the 2×2 that decides it, executed:**

| | **TODAY** (aliased) | **FIXED** (rebuilt) |
|---|---|---|
| **the current test** — `assert good == snap; assert out == snap` | 🔴 **GREEN** | ✅ red |
| **the proposed test** | ✅ red | 🔴 **GREEN** |

**The current test's truth table is the exact inverse of the correct one.** It is not weak; it
*requires* the defect. Confirmed, 4th round.

**What the rewritten test must assert — three clauses, and the third is load-bearing:**

1. **Keep** `good == snapshot` — the validator must not edit its input in place. (Already there, and
   already correct.)
2. **Identity separation.** For every returned row, every `list`/`dict`-valued field must satisfy
   `v is not src[k]`. This is the direct falsifier of aliasing and it names the field in the message.
3. 🔴 **Post-call independence — this is the clause that must replace `assert out == snap`.** Mutate
   the caller's own input *after* the call, then assert the returned document is unchanged:

   ```python
   for r in good["declarations"]:
       if isinstance(r.get("members"), list):
           r["members"].append("GHOST_NEVER_ADMITTED")
   assert json.loads(json.dumps(out)) == snapshot
   ```

**Why the JSON round-trip and not `==`:** `assert out == snap` reds under the tuple fix for the wrong
reason — `('t0',) != ['t0']` — which is precisely why the current test blocks the fix. Comparing
through a JSON round-trip makes clause 3 **red under the defect and green under *either* remedy**
(deep copy or tuple rebuild), so the test asserts the property rather than the implementation choice.
Clause 2 alone would over-constrain a future fix that returned an immutable view; clause 3 alone
would miss a shallow-copied nested `dict`. Both, and neither is `==`.

**Closure cost: 2 production lines + 1 test rewritten.** ⚠️ `surface.py:72` and `manifest.py:448` are
siblings. **Both, or neither.**

Reachability: guard-only today (zero importers) → **production-reachable at the commit CP-2.1 imports
the package.**

## 3 · The five carried findings — all five re-measured, all five OPEN

### B18-8 — **6th round.** 1 of 3 exact-type pins is guarded, and the control proves it is a family

| injection (`contract.py`) | suite |
|---|---|
| `type(key) is not str` → `not isinstance(key, str)` (`:220`) | **136 passed** |
| `type(m) is not str or not m` → `isinstance` (`:254`) | **136 passed** |
| **both at once** | **136 passed** |
| *control:* the row pin → `isinstance` (`:216`, `:217`) | **2 failed, 134 passed** |

### B18-11 — **6th round**

```
contract.py   canon imported at [21]   canon.<attr> uses: []
manifest.py   canon imported at [27]   canon.<attr> uses: []
'canon' in __init__: False
canon.py nfc() docstring still names manifest.load as a door: True
```

Two dead imports, **zero** attribute uses, not exported, and the refuted docstring verbatim three
rounds after the code it describes recorded its own refutation.

### B18-10 — **9th round**

```
a fifth exported door serving an unvalidated row: [{'TYPED BY HAND': 1}]
SUITE: 136 passed        GATE: rc 0, 'agentruntime-membrane-gate OK - 8 module(s), …'
```

### `surface.py:305` — **5th round**, 5 vehicles, control vs neutered

| vehicle | control | site neutered |
|---|---|---|
| `(["cost2","asc"],)` | `ValueError: keys[0] is not a (field, direction) pair` | 🔴 **ACCEPTED** — `keys = (['cost2','asc'],)` |
| `(("cost2","asc","x"),)` | refused | `ValueError: too many values to unpack` |
| `(("cost2",),)` | refused | `ValueError: not enough values to unpack` |
| `(7,)` | refused | `TypeError: cannot unpack non-iterable int` |
| `("ab",)` | refused | `ValueError: keys[0]: unknown direction 'b'` |

Load-bearing for **exactly one** vehicle. A closure written against a 3-tuple or a scalar passes with
the clause deleted. **Fifth round, and the standing prediction stands.**

### `TakeWhileBudget` floor (allowlist row 13) and `_ID` — **5th round**

```
budget=-1 / -1e9   CONTROL -> ValueError    NEUTERED -> ACCEPTED, TakeWhileBudget(budget=-1, …)
_ID.match(300 chars): True | admit+build OK | written id length: 300 | validate_document round-trip: 300
```

## 4 · The record audit — **R22's `Open, carried` exists (an improvement) and is lossy (a regression to R20's mode)**

R21's block had **no** `Open, carried` line at all. R22's has one, with 11 entries. Audited against
both R22 verdicts:

| finding | raised by | delta touched it? | in R22's `Open, carried`? |
|---|---|---|---|
| B18-8, B18-11, B18-10, `surface.py:305`, `_ID`, `dict(r)`, the 3 weak oracles, T11d, the probe writers, W4, the recorder hazard | A + B | no | ✅ **all 11 present** |
| B22-3 / B22-4 / B22-6 (snapshot window, `-O`, Windows SIGTERM) · A22-1/2/3/7/8 | A + B | ✅ closed by the mirror | ✅ correctly dropped |
| **`ALLOWLIST.write_text` — `census.py:280`** | 🔴 **A22-9 *and* B22-7 — BOTH verifiers, independently** | ❌ **not touched** | 🔴 **ABSENT** |
| **the M1 "byte-equality" claim, still in `ambient.py:76` + `test_cp1_membrane.py:2185`, `:2199`** | B22-1 | ❌ **not touched** | 🔴 **ABSENT** |
| B22-2 (the census test green over every realistic disablement) | B | rewritten — **and still 8/8 green** | 🔴 absent, treated as closed |

Verified by execution, not by reading:

```
scripts/agentruntime-census.py:280   ALLOWLIST.write_text(...)          <- unchanged
contracts/agentruntime-census-silent.txt   worktree 1438 B, 23 CRLF | blob 1415 B
services/chat-service/app/agentruntime/ambient.py:76
    "**The M1 drift gate is a byte-equality check**, so the same declarations written …"
```

The RUNSTATE *narrates* the M1 refutation — *"the reason I published for it was false in every place
I published it"* — in the past tense, while **the false sentence is still in production source and in
two test assertions**, and it is not on the carried list. **A finding acknowledged in prose and left
out of the register is the same loss as one dropped in silence, with a better alibi.**

**Verdict on item 4: the register's failure mode oscillated rather than converged.** R20 lost six
rows; R21 wrote no line; R22 wrote a line and lost two — one of them the only finding in this run
that **both** independent verifiers reported. **Sixth consecutive round.** Three hand corrections
have now been applied and none held. My predecessor's generated-register design (a YAML block per
verdict, `(anchor, axis)` identity, a generator that refuses to drop a row open in *N−1* without a
signed `status`) is the one design from R22 I would build **as written** — and I note that its first
refusal clause, *"a row open in N−1 and absent in N"*, catches exactly the two rows lost this round,
and its clause *"a closure signed by the party that shipped the fix"* catches B22-2.

---

## Bypass table

| guard | bypass | executed | reachable |
|---|---|---|---|
| the census's kill-safety | — | ✅ 6 modes tried | 🟢 **none found** |
| the census's non-interference | — | ✅ 20 treatment + 20 control | 🟢 **none found** |
| the census's row id | extend an f-string message past its last interpolation | ✅ **15/17, 3 allowlisted** | **any message edit** |
| the census's row id | swap two same-class raises in a collision group | ✅ **id set identical, row re-points** | any refactor (latent) |
| the census's "SILENT means alone" | — | ✅ 13/13 reproduced | 🟢 **none found for ¶1** |
| the census's "or UNREACHABLE" | an object whose `__repr__` raises | ✅ **both arms fired** | adversarial, and it is the header's own claim |
| the CI test's "the census RUNS" | `if: false` · `--selftest` · `continue-on-error` · a **comment** · a job-level `if` | ✅ ×5 | any edit |
| the CI test's live-tree clause | spell the write `ROOT / _PKG_REL` | ✅ **live tree neutered + left dirty** | any edit |
| the CI test's atexit clause | `getattr(atexit, 'register')` | ✅ | any edit |
| the CI test's digest clause | `::deadbeef` ×13 | ✅ | `--write` on a stale tree |
| the CI test's `_mirror` clause | rename it `_mirrorX` | ✅ **census dies with `NameError`, test GREEN** | any refactor |
| the census's own artifact | `census.py:280` `write_text` on Windows | ✅ 1438 B vs 1415 B | masked by `.gitattributes`, not by code |
| four doors' "returns what it validated" | mutate the shared `members` list afterwards | ✅ 4/4 + cross-door | guard-only → **CP-2** |
| `check_row_shape`'s `key` / `m` pins | a `str` subclass | ✅ ×3 + control | adversarial (B18-8) |
| `OrderBy`'s key-pair shape | a 2-element **list** | ✅ | guard-only → CP-2 |
| `TakeWhileBudget`'s floor | `budget=-1` | ✅ | guard-only → CP-2 |
| `_ID` | a 300-character id | ✅ end-to-end | adversarial |
| four exported doors | add a fifth | ✅ suite **and** gate green | structural, 9th round |

## Red-ability table — **my denominator, derived from the delta's own text**

The delta makes **14 checkable claims**, taken from its own docstrings, comments, CI text and
allowlist header — not from what happens to be tested.

| # | claim the delta makes | test that would red it | red-able? |
|---|---|---|---|
| 1 | the census never writes into the live tree | `"PKG.glob" not in _census_body` | 🟡 **spelling only — B6 GREEN over live-tree damage** |
| 2 | a killed census leaves the tree clean | — | ❌ none, **though the claim is TRUE (6/6)** |
| 3 | the mirror ends the concurrency interference | — | ❌ none, **though the claim is TRUE (20/20)** |
| 4 | the digest is stable across interpreters | — | ❌ none — nothing derives ids on a second interpreter |
| 5 | a reworded message keeps its row | — | ❌ none, and **false at a boundary (15/17)** |
| 6 | reordering moves a row, 98/98 pairs, **0 collisions** | — | ❌ none, and **REFUTED (3/43, 4 groups)** |
| 7 | reindenting does not move a row | — | ❌ none; the claim is TRUE |
| 8 | a rename is visible in the prefix | — | ❌ none; the claim is TRUE |
| 9 | the CI job RUNS the census | substring | 🟡 **5 bypasses green** |
| 10 | the CI job does not `--write` | `'--write' not in job` | ✅ **clean — C2 reds** |
| 11 | atexit is gone and not needed | `"atexit.register" not in src` | 🟡 `getattr` bypass green |
| 12 | the header claims only what the experiment supports | — | ❌ none, and **contradicted in the same file + at `census.py:304`** |
| 13 | the mirror measures "what is about to be committed" | — | ❌ none, and **false in both directions** |
| 14 | the ids are content-addressed | `re.search(r'::[0-9a-f]{8}$')` | 🟡 **shape only — `::deadbeef` ×13 passes** |

**Cleanly red-able: 1 of 14** (claim 10). **Weak/defeatable: 4.** **No test at all: 9.** **Two claims
are false and two are refuted by execution.**

For **my own** findings the denominator is **12**, and **red-able today: 0 of 12** — every one is an
injection or a probe I wrote, and none has a committed test.

## Sibling table

| rule | applied to | missed | verdict |
|---|---|---|---|
| stop writing into a resource the instrument does not own | `census()` ✅ · `_selftest()` ✅ | — | **2 of 2** ✅ **first clean row in this table in five rounds** |
| stop calling `write_text` on anything whose bytes matter | `ambient.write_text` ✅ | **`census.py:280`** ✗ · `ambient.read_text` ✗ | 1 of 3 | 🔴 B22-7 / A22-9, **2nd round** |
| the retracted claim comes out everywhere it was published | the allowlist header ¶1 ✅ | **the same file, line 9** ✗ · **`census.py:304`** ✗ | 1 of 3 | 🔴 B23-8 |
| a false claim comes out of the source that carries it | the RUNSTATE narrative ✅ | **`ambient.py:76`** ✗ · **`test_cp1_membrane.py:2185`, `:2199`** ✗ | 1 of 4 | 🔴 B22-1, **2nd round** |
| the id survives an edit that does not change the guard | reindent ✅ · reword-content ✅ | **f-string segmentation** ✗ · **the ordinal** ✗ | 2 of 4 | 🔴 B23-1 / B23-2 |
| a guard asserts the behaviour, not the spelling | `'--write' not in job` ✅ | **`"PKG.glob"`** ✗ · **`"_mirror"`** ✗ · **`"atexit.register"`** ✗ · the run substring ✗ | 1 of 5 | 🔴 B23-4 / B23-5 |
| a temp resource is released | — | **both `_mirror()` calls** ✗ | 0 of 2 | 🔴 B23-6 |
| a comment describing machinery goes with the machinery | the docstring of `_mirror` ✅ | **`census.py:191-201`** ✗ · **the module docstring's "asserts the bytes back"** ✗ | 1 of 3 | 🔴 B23-7 |
| a returned row is rebuilt from what was checked | the row `dict` ✅ · both doc stamps ✅ | **`members`** ✗ at both producers | 2 of 3 | 🔴 B20-1 |
| an exact-type pin against a `str` subclass | `row` ✅ | **`key`** ✗ · **`m`** ✗ | 1 of 3 | 🔴 B18-8 |
| a narrowing parameter has a floor | `TopK.k >= 1` ✅ · `cost_field` ✅ | **`budget >= 0`** ✗ | 2 of 3 | 🔴 allowlist row 13 |
| a stage parameter's shape is bounded | `keys` tuple ✅ · `field` ✅ · `direction` ✅ | **the pair, for a list** ✗ | 3 of 4 | 🔴 B19-4 |
| the doc-level clauses run at every door | `validate_document` ✅ | `rows_of` ✗ `declarations` ✗ `discover` ✗ | 1 of 4 | 🔴 B18-9 |
| a deleted claim's docstring goes with it | the call-site comment ✅ | **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 B18-11 |
| an "unreachable handler" is proven, not asserted | — | **`manifest.py:245`** ✗ · **`:428`** ✗ | 0 of 2 | 🔴 B23-9 |

## Guard table

| behaviour | guarded by | strength |
|---|---|---|
| the CI job does not `--write` | `:2145` `'--write' not in job` | ✅ **reds** |
| the manifest is written LF | `:2155` `assert b"\r\n" not in raw` | ✅ reds on revert (carried PASS) |
| the census job runs the census | `:2141` substring | 🔴 **green under 5 bypasses** |
| the census does not write into the live tree | `:2166` `"PKG.glob" not in _census_body` | 🔴 **green while it neuters `admission.py`** |
| the census uses a mirror at all | `:2160` `"_mirror" in src` | 🔴 **green over `NameError`** |
| atexit is not registered | `:2160` `"atexit.register" not in src` | 🔴 **green under `getattr`** |
| the ids are content-addressed | `:2178` regex on **shape** | 🔴 green over `::deadbeef` ×13 |
| the ids are *correct* / injective | — | ❌ none, **and they are not injective** |
| the ids are stable across interpreters | — | ❌ none (the claim is true today) |
| a killed census leaves the tree clean | — | ❌ none (the claim is true today, 6/6) |
| the census does not corrupt concurrent runs | — | ❌ none (the claim is true today, 20/20) |
| the mirror is released | — | ❌ none, **and it is not** |
| the allowlist header and the gate's output agree | — | ❌ none, **and they contradict each other** |
| a "SILENT because UNREACHABLE" row really is | — | ❌ none, **and both are reachable** |
| a validator returns a **copy** | `:1156` — asserts `==`, which the aliasing satisfies | 🔴 **the guard requires the defect** |
| a non-string row key / malformed member refused **as the named clause** | sibling, same class | 🟡 named clause untested |
| an `OrderBy` key-pair is a 2-tuple | — | ❌ none for the **list** vehicle |
| `budget >= 0` · `_ID` length | — | ❌ none |

## Reachability verdict on **every** finding

| id | finding | class | production-reachable today? |
|---|---|---|---|
| **B23-1** | the id is not injective — 54 digests / 68 sites, 4 collision groups, 2 with an allowlisted row; a null swap re-points a row; *"0 collisions"* refuted | **instrument correctness** | **YES** — it is the proposed closure criterion |
| **B23-2** | extending an f-string message moves 15/17 such sites, 3 allowlisted | instrument / process | **YES** — every message edit |
| **B23-3** | the digest blanks field-path literals and the literal C-12 `reason`/`accepted` at 13 sites | instrument / contract | **YES**, and it overlaps exactly the 13 silent rows |
| **B23-4** | the CI test: 8/8 bypasses green; control C3 green over a `NameError` | instrument / test | **YES** |
| **B23-5** | the live-tree-write guard forbids a spelling — executed: `admission.py` neutered and left dirty, test GREEN | harness / tree | **YES — executed** |
| **B23-6** | 2 × 214 MB mirrors per run, never deleted; 4.4 GB accumulated | harness / resource | **YES — measured** |
| **B23-7** | `census.py:191-201` and the module docstring describe removed machinery (snapshot, `atexit`, SIGINT/SIGTERM, "asserts the bytes back") | **false claim in production source** | **YES** — committed prose that misdirects the next reader |
| **B23-8** | the header's retraction landed 1 of 3 places; `census.py:304` prints the retracted sentence at runtime | instrument / claim | **YES** |
| **B23-9** | both "UNREACHABLE" handlers fire (`manifest.py:245`, `:428`) — refutes B21-1/2, the allowlist header, the RUNSTATE, **and design 2** | **false claim, published** | **YES — executed both** |
| **B23-10** | the mirror reproduces neither untracked files nor modes; *"what is about to be committed"* is wrong in both directions | harness / claim | **YES** locally |
| **B23-11** | 2 open R22 findings absent from `Open, carried`, one raised by **both** verifiers; the M1 falsehood is narrated as past tense and is still in source | process | **YES** |
| **B23-12** | `_selftest`'s baseline runs in the live tree, all 68 measurements in the mirror; nothing checks they agree (divergence **not** reproduced) | harness | **latent — negative result recorded** |
| B22-1 | the M1 byte-equality claim still in `ambient.py:76` + 2 test assertions | false claim | **YES**, 2nd round |
| B22-7 | `census.py:280` `write_text` on a committed artifact; worktree CRLF | sibling / artifact | **YES** (masked by `.gitattributes`), 2nd round |
| B20-1 | `dict(r)` shallow at 4/4 doors; its guard requires the defect (2×2 executed) | correctness | guard-only → **prod at CP-2** |
| B18-8 | 2 of 3 exact-type pins downgrade silently — **6th** | adversarial | no |
| B18-10 | a fifth exported door, suite **and** gate green — **9th** | structural | no |
| B18-11 | `canon` dead: 2 imports, 0 uses, refuted docstring — **6th** | dead code / doc | no |
| B19-4 | `surface.py:305` — a 2-element **list** becomes an ordering key — **5th** | guard-only | no |
| B19-12 | `_ID` unbounded; 300 chars end-to-end — **5th** | adversarial | no |
| B18-9 | doc-level stamps checked at 1 of 4 doors | structural | guard-only → CP-2 |

**Introduced this round: 12** (B23-1 … B23-12). **Carried, re-measured open: 8.**
**Closed by this delta: 4** — the kills, the concurrency, version stability, content-reword churn.
**Half-closed: 3** — the id, the CI test, the allowlist header.

## Executed vs argued

| | count |
|---|---|
| **executed** — code I ran and read the output of | **38** |
| **argued** — reasoned, labelled, not run | **5** |

Executed: a **full census** (rc 0, `68/13/55`, 433 s, live tree byte-identical — 6th reproduction) ·
an independent re-derivation of all 68 ids with the census's **own** `_sites` · **6 kill runs across
6 termination modes**, each byte-compared against my own pre-run snapshot · **20 concurrent suite
runs during a census + 20 control runs** · id derivation on **three interpreters** and the 3.12↔3.13
diff · the **digest-collision enumeration** over all 68 sites · **four edit classes** — reindent
×68, rename ×68, reword-in-place ×68, reword-at-a-boundary ×68 — plus **43 enumerated reorder pairs**
· the **null swap** proving an allowlisted row re-points · the **13 literal-C-12-payload** sites ·
**8 CI-test bypasses + 3 controls** · the `NameError` under control C3 · **the live-tree damage B6
lets through**, with a hard kill · `dict(r)` at **4 doors** + cross-door + the full **2×2** of two
tests × two implementations · **3 B18-8 injections + a control** · the `canon` AST sweep · the
fifth-door injection against suite **and** gate · **5 `OrderBy` vehicles × control/neutered** ·
`TakeWhileBudget` × control/neutered · `_ID` at 300 chars end-to-end · a **`pytest_runtest_makereport`
hook** over a passing `pytest.raises` · **both "unreachable" handlers driven live** · the allowlist
worktree-vs-blob byte comparison · the mirror's cost, contents, leak count and suite run · the
mirror's untracked/mode/submodule/symlink inventory · the live-vs-mirror baseline divergence attempt
(**negative**, recorded as such).

Argued, and labelled: the `sys.monitoring` alternative to design 1 (I did not build it); that the job
behaves identically on `ubuntu-latest` (I ran it on win32 and named what differs); the recommendation
to adopt the generated-register design; the adjudication of whether a null reorder *should* move a
row; the ranking of which six changes come first.

**Not one finding rests on an argument**, and every execution is over an **enumerated** space — all
68 sites, all 13 allowlist rows, 4 edit classes, 43 reorder pairs, 8 assertion bypasses + 3 controls,
6 termination modes, 5 key-pair vehicles, 3 exact-type pins, 3 interpreters, 4 doors, 2 handlers —
not a chosen sample.

## Convergence

| | value |
|---|---|
| findings **introduced** by me, round 23 | **12** |
| B-scope `introduced` series, r10→r23 | `2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2, 5, 9, 9, 12` |
| carried findings re-measured **open** | **8** |
| carried findings **closed** by this delta | **4** — the first time in this run that more than two closed and survived an independent enumeration · half-closed 3 |
| my denominator, delta claims | **14** · cleanly red-able **1**, weak 4, none 9, **false 2 + refuted 2** |
| my denominator, my findings | **12** · red-able **0** |

**The count went up and the meaning went down.** Nine of my twelve are about the census, and — unlike
last round — they are no longer half-fixes of the fixes. They are **one level deeper**: the
instrument's *observable behaviour* is now correct (it does not write, does not interfere, does not
drift across interpreters), and what fails is its *identity function* and its *self-guard*. That is
what convergence looks like from the inside when it is happening: the surface defects stop and the
structural ones become legible. **Four closures that survived enumeration is the first genuine signal
in fifteen rounds**, and it happened on the round where the fix **deleted** 24 lines instead of
adding a mitigation.

Against that: **the self-guard got worse, not better.** R22 measured its census test green under 5 of
5 disablements; the rewritten test is green under 8 of 8 **and** under one of its own controls. The
test grew from 4 assertions to 7 and its bypass count grew from 5 to 9. **A guard that is rewritten
in response to a bypass measurement and comes back weaker is the one thing in this run that has not
improved once**, and it is the reason I cannot support closure yet.

## ▶ Do I support closing CP-1 against the census?

**Partly, and I will say exactly where the line is.**

* ✅ **I support the census as the closure criterion for the RED half** — *"this named site moved
  SILENT → RED"* — for the 55 red sites. The instrument runs, reproduces, does not damage its
  subject, does not interfere with other readers, and is interpreter-stable across both pinned
  versions. All four verified independently.
* 🔴 **I do not support it for the SILENT half**, because the id is not injective for 4 same-function
  groups (2 containing an allowlisted row), because 3 allowlisted rows relocate on an ordinary
  message edit, and because one of the header's two stated reasons for a row being silent is refuted
  by execution.
* 🔴 **I do not support closing CP-1 this round**, because the instrument's guard is green over the
  instrument's own removal, executed.

**Distance to my support — six changes, all ≤15 lines, none of them design work:**

1. `module::qualname::ExcClass::digest[::n]` — drop the ordinal, append a counter only on a real
   collision. **~3 lines.** Makes the id a key; makes a null reorder move nothing. (B23-1)
2. Collapse each `JoinedStr` to one blanked `Constant` before hashing. **~2 lines.** (B23-2)
3. Replace `"PKG.glob" not in _census_body` with an **executed** post-condition — run `census()`
   against a fixture, assert every live package file is byte-identical after — and parse the workflow
   YAML instead of five substring searches (step exists · no `if:` · no `continue-on-error:` · `run`
   is *exactly* the census command). **~15 lines.** (B23-4, B23-5)
4. `finally: shutil.rmtree(mirror, ignore_errors=True)`, and reuse one mirror for both phases.
   **~3 lines.** (B23-6)
5. Delete `census.py:191-201`; make `census.py:304` and the allowlist's line 9 say what line 1 says.
   **~4 lines.** (B23-7, B23-8)
6. Remove *"or because it is UNREACHABLE"* from the header and the claim from the RUNSTATE — I
   refuted it for both cited rows in ten minutes. **1 line.** (B23-9)

## ▶ My new falsifiable prediction

> **The next delta that edits a refusal message in `app/agentruntime/` will churn
> `contracts/agentruntime-census-silent.txt` for a reason unrelated to guarding, and the churn will
> be in `contract.py`.** Concretely: the allowlist diff will contain ≥ 1 row whose
> `module::qualname::ExcClass::ordinal` prefix is **unchanged** and whose 8-hex digest **changed**,
> the edited raise will be an f-string that ended on an interpolation, and neither the commit message
> nor the RUNSTATE will name which site moved or why. I name `contract.py` because 13 of the 17
> boundary-sensitive f-strings live there and 3 allowlisted rows are among them.

**Falsifier (either half refutes me):** the next delta edits a raise message and (a) produces **zero**
digest churn, **or** (b) produces churn in which every moved row is named with its old digest, its new
digest, and a control-vs-neutered probe showing the guarded condition before and after.

**Secondary, cheap to check, and it is the run's signature:** **the two `except UntrustedRow` arms at
`manifest.py:245` and `:428` will be annotated or fixed at one of the two and not both** — or the
word `UNREACHABLE` will come out of the allowlist header while `census.py:304` keeps printing *"a
refusal nothing checks."* Eleventh and twelfth instances of the same pair failure.

**Standing from R21 and R22, re-affirmed on a fifth measurement:** the closure at
`surface.py::OrderBy.__post_init__::ValueError::3` will be written against a 3-tuple or a scalar and
will pass with the clause deleted, because 4 of its 5 vehicles are masked by Python's own unpack.

---

`git rev-parse HEAD` at finish: **`9b77caed789e9f2737f849d63b1485a65bcbd8a4`** — unmoved.
`git status --porcelain`: **empty**. All 14 files I touched are **byte-identical** to my pre-run
scratchpad snapshot, verified by `cmp` at finish. Every mirror I created was removed by me. The only
tracked file this verdict wrote is itself. Nothing was committed.
