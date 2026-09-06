# CP-1 · round 21 · V-CODE · Verifier A — the instrument

`git rev-parse HEAD` **at start**: `9818c7bc57c8381a4dddbbfcc88cbaadc5e89f06`
Graded delta: `3caac262d` + `ad4e69030`, diffed against `b73e086ca`.
Method: every measurement below ran in a scratch tree materialised with
`git archive 9818c7bc5 | tar -x` (pristine HEAD bytes, repo-depth), patched and restored from my own
byte snapshot with an equality assert. **No `git checkout`. No tracked file written except this one.**

---

# 0 · THE CENSUS VERDICT

> `scripts/agentruntime-census.py` is the first artefact of this run whose purpose is to make *"a
> finding is closed"* mechanical. If it is wrong, every future closure is wrong.

**Verdict: the MECHANISM is sound and exactly reproducible. As SHIPPED it is not yet a gate.**
Nine defects, six of them executed to a wrong output or a wrong tree state.

**What is right, and I want it on the record before the defects.** I reproduced it byte for byte on
a pristine tree: **68 sites, 13 silent, 55 red, `rc=0`, and the emitted silent set is `diff`-identical
to `contracts/agentruntime-census-silent.txt`.** The selftest fires in both directions. The
enumeration is complete over the package as it stands today (§0.1). Neutered one at a time against
the **whole** chat-service suite — 2,266 tests, not the one file — **all 13 stay silent, 0 new
failures**: no line of the allowlist is silent for a harness-scope reason. That is a real result and
it is the first measurement in twenty-one rounds that another party can rerun and get the same number.

| # | census question | verdict | evidence |
|---|---|---|---|
| Q1 | shapes it cannot see | **complete today, one live blind spot** | 63-shape + AST enumeration, §0.1 |
| Q2 | is the allowlist honest | **11 of 13 hold; 2 are FALSE** | 378-subset enumeration + the float proof, §0.2 |
| Q3 | does it fail closed | **closed on both named shapes; OPEN on a third** | 4 kills, 3 census runs, §0.3 |
| Q4 | is the id stable | **NO — and one failure mode is silent** | 2 semantics-preserving reorders, §0.4 |
| — | is the gate itself gated | **NO, twice** | §0.5 |

## 0.1 · Q1 — what it cannot see

**Enumerated, not argued.** An AST sweep of `app/agentruntime/` for every refusal-shaped construct:

| shape | in the package today | census sees it |
|---|---|---|
| `ast.Raise` in a globbed module | **68** | ✅ (its subject) |
| `ast.Raise` in `__init__.py` | 0 | ❌ explicitly skipped |
| `ast.Raise` in a subpackage | 0 (`glob` == `rglob` today) | ❌ `PKG.glob("*.py")` is not recursive |
| `ast.Assert` | 0 | ❌ — and pytest does not run `-O`, so an `assert` *is* a refusal |
| `sys.exit` / `os._exit` / `os.abort` | 0 | ❌ |
| `raise` sharing its line (`if x: raise …`) | 0 | ⚠️ `_neutered` would replace the **whole line**, deleting the `if` |
| `except` with no re-raise | 1 (`admission.py:128`) | ❌ (contains no allowlisted site) |
| a refusal expressed as a `return None` | not statically decidable | ❌ |

So **no refusal in this package escapes the subject today**, and the "raise inside a lambda /
comprehension" the prompt asks about is not a Python shape at all — `raise` is a statement. The
reachable equivalent is a refusal expressed as an *expression* (`d[k]`, `next(it)`, `int(s)`,
`unicodedata.normalize`), of which the package has many and the census has none.

**The blind spot that is live right now, not prospective:** the census globs
`app/agentruntime/*.py`. **The only new refusal in the graded delta is `instrument.py:580` — a
`raise TypeError` in `app/services/`.** The commit that shipped the gate also shipped the first
refusal the gate cannot see, and nothing in the repo notices that asymmetry.

**And the one that bites: `pass`-substitution does not ISOLATE a site.** Where a later sibling
catches the same case with the same exception class, neutering the earlier one changes nothing the
oracle can detect, and the census records it SILENT while it is fully guarded. **Executed** — §0.2.
This directly defeats the docstring's headline claim, *"the sibling has its own id and its own row"*:
two sites are not independent when one shadows the other.

## 0.2 · Q2 — the allowlist's honesty, over an ENUMERATED space

**The false line, proven.** `canon.py::_norm::NotCanonicalisable::1` (`canon.py:60`, the float
refusal) is on the allowlist, which states *"every line is a claim that nothing checks"*.
`tests/test_cp1_membrane.py:1584` checks it:

```python
with pytest.raises(canon.NotCanonicalisable, match="float"):
    canon.digest({"score": 0.1})
```

Neutered `canon.py:60` with the census's own `_sites`/`_neutered`, ran the canon class:
**`8 passed`**. The fallback at `canon.py:84` emits `f"{path}: {type(value).__name__} has no canonical
form"` → `"$.score: float has no canonical form"` → the oracle's `match="float"` is satisfied.
The refusal is checked; the allowlist says nothing checks it. `::4`, the masking fallback, carries the
identical false claim.

**Direction of harm.** A maintainer reading the allowlist is told deleting `canon.py:60` is free. It
is not: C-12 requires a refusal to name the field, the reason and what would be accepted, and the
specific *"float is not canonicalisable … represent it explicitly, where the choice is visible"*
collapses to *"float has no canonical form"*. Green CI, degraded contract, allowlist unchanged.

**The enumerated search.** I did not hand-pick the pair. I enumerated **every subset of the 13
allowlisted sites of size 1, 2 and 3 — 13 + 78 + 286 = 377 — plus the all-13 case (378 runs of the
census's own suite)**, neutering each subset *simultaneously*:

| k | subsets | RED |
|---|---|---|
| 1 | 13 | 0 |
| 2 | 78 | **1** — `{canon::1, canon::4}` |
| 3 | 286 | **11** — all supersets of that pair |
| 13 | 1 | 1 (superset) |
| **total** | **378** | **13** |

**Exactly one minimal red pair exists.** So the masking is localised: **2 of 13 allowlist lines are
false as written, 11 hold at k≤3.** This is the number a hand-picked sample cannot produce, and it is
the number the allowlist should carry.

**The harness-reason check the prompt asked for — clean.** No allowlisted site sits inside a `try`
whose handler swallows it; the package's single non-re-raising handler (`admission.py:128`) contains
no allowlisted site. And **E3**: each of the 13 neutered alone against the **entire** chat-service
suite (`tests/ --ignore=tests/e2e`, 2,266 tests, 14 full-suite runs) produced **0 new failures in
13/13**. Nothing is silent because the census reads one file.

**One row states a different fact than its vocabulary allows.**
`manifest.py::validate_document::UntrustedRow::6` is the `except UntrustedRow as exc: raise
UntrustedRow(...)` arm of a loop whose only callee, `contract.check_row`, raises `ContractViolation`
— caught by the handler immediately above it. That row is not *"a refusal nothing checks"*; it is **a
handler nothing can enter**. The allowlist has one word for "unguarded" and "unreachable", and a
future reader closing findings off it cannot tell which he is looking at.

## 0.3 · Q3 — fail closed?

**Killed mid-run (`TerminateProcess`: no `finally`, no `atexit` — exactly a CI timeout, an OOM, a
Ctrl-Break or a lost runner). 4 kill points, 4 of 4 left damage:**

| killed after | tree afterwards |
|---|---|
| 12 s | `admission.py:91` `raise TypeError(…)` → `pass` |
| 20 s | `canon.py:60-64` `raise NotCanonicalisable(…)` → `pass` (**an allowlisted SILENT site**) |
| 30 s | `canon.py:84` → `pass` |
| 45 s | `contract.py:236-238` → `pass` |

There is no lock, no pre-flight "is the tree clean", no crash marker. **13 of 68 sites (19 %) are
SILENT, so ~1 kill in 5 leaves damage the suite cannot see** — my sample put 1 of 4 there.

**And that is where it fails OPEN.** `raw = path.read_bytes()` is read **inside** the per-file loop,
so a re-run after a crash adopts whatever is on disk as "the original". Executed, with the crash left
on the allowlisted `surface.py::TakeWhileBudget.__post_init__::ValueError::1`:

```
agentruntime-census selftest OK - 67 raise sites, fires on a guarded one
NOW GUARDED   surface.py::TakeWhileBudget.__post_init__::ValueError::1  <- good news: drop it from the allowlist in the same change
agentruntime-census: 67 sites, 12 silent, 55 red      rc=1
PROOF: TakeWhileBudget(budget=-5) CONSTRUCTED - the refusal is gone and CI said OK
```

The refusal was **deleted**, and the gate congratulates you and instructs you to delete the evidence.
It cannot tell the two apart because **it never compares the site SET, only the silent set**: a
vanished key is absent from `results` and absent from `silent`, so it can only surface through
`now_red`, whose message assumes the opposite cause. The selftest's floor is `len(sites) < 50`, so
**18 refusals can be deleted before it objects**, and the `68 sites` line is printed, never asserted.
One line fixes it: record the inventory and diff it.

**A syntactically broken module — stops, does not skip.** `ast.parse` raises `SyntaxError`, uncaught,
`rc=1`, tree intact. Fails closed. The traceback names `ast.py:50`, not the census's contract.

**Concurrency — the hazard is measured, not hypothesised.** The census holds a tracked source file
mutated for essentially its whole runtime. On my own isolated copy, with a census running:
**15 of 20 membrane-suite runs went RED.** This is not a thought experiment: **during this round it
corrupted 7 of my first 8 baseline measurements in the shared live tree**, producing a different
random refusal failure each run (`DID NOT RAISE` on stage kinds, on budgets, on document shape), and
I spent three measurement cycles chasing a "flaky suite" that was a second agent's census. Two other
observations from that window belong here: the live tree contained a probe module injected into
`app/agentruntime/surface.py` (`summarise_rows`, written with CRLF — the very `write_text` defect the
census docstring says it fixed), and a snapshot I took mid-census captured a neutered `contract.py`
and produced two deterministic false failures until I rebuilt from `git archive`.

**Minor:** the `agentruntime-census` job is the only job in `lint-foundation.yml` with **no
`timeout-minutes`**, in a repository that ships a `timeout-discipline-lint`.

## 0.4 · Q4 — is the id stable?

`module::qualname::ExcClass::ordinal` is stable against edits **elsewhere in the file** — the property
the docstring claims and correctly contrasts with line numbers. It is **not** stable against
reordering **inside its own function**, because the ordinal is positional: the id names *"the n-th
raise of class C in F"*, not a refusal. Two semantics-preserving reorders, both run through the real
census:

**Case A — swap two independent `if` branches with different status** (`_norm`'s float refusal `::1`,
SILENT ↔ the set refusal `::3`, RED). Disjoint types, nothing guarded differently:

```
census rc=1
NEWLY SILENT  canon.py::_norm::NotCanonicalisable::3  <- a refusal nothing checks; guard it or record it deliberately
NOW GUARDED   canon.py::_norm::NotCanonicalisable::1  <- good news: drop it from the allowlist in the same change
```

Fails closed — and **both sentences are false**. Nothing was guarded and nothing was unguarded; two
blocks moved. A maintainer told "good news" will look for the test that closed `::1` and find none.

**Case B — swap two SILENT siblings of one class in one function:**

```
census rc=0
agentruntime-census: 68 sites, 13 silent, 55 red
```

**Silent.** The allowlist's rows now name different physical sites and the gate says nothing. That is
precisely *"an allowlist that goes stale silently"* — the failure the ordinal was chosen to prevent,
relocated from line numbers to positions. A future round that closes a finding by hoisting a check
earlier will get a false "NOW GUARDED" on a site nobody touched.

## 0.5 · The gate is not itself gated — twice

**(a) It is not wired-in-tested.** `test_cp1_membrane.py:217` —
`test_the_gate_actually_RUNS_in_ci` — asserts `"- agentruntime-membrane-gate" in wf`, with the reason
in its own docstring: *"an import-graph gate is worth exactly what CI runs, and six legs of this very
workflow once failed on main for weeks."* **The census has no equivalent.** Delete the
`agentruntime-census:` job from `lint-foundation.yml` and every test in the repository stays green.
The precedent, the mechanism and the stated reason are twenty lines above it in the same file.

**(b) The CI job cannot pass.** Its only install step is
`pip install -r requirements.txt` in `services/chat-service`. That file (37 lines) contains **no
pytest** — pytest and pytest-asyncio live in `requirements-test.txt`, which is never installed. The
census's entire oracle is `subprocess.run([sys.executable, "-m", "pytest", …]).returncode == 0`.
Executed with pytest unavailable:

```
SELFTEST FAIL: the suite is not green before any injection      rc=1
```

It fails **closed** and is **inert**: it can never certify anything, and it misdiagnoses itself as a
red suite. *Falsifier:* if `ubuntu-latest` + `actions/setup-python@v7` ships pytest in the image this
is wrong — but `setup-python` installs a bare interpreter, and `tests/conftest.py` additionally needs
`pytest-asyncio` for `pytest.ini`'s `asyncio_mode = auto`. **This is the one census claim I could not
execute on the real runner**, and it is stated as falsifiable for that reason.

## 0.6 · What to change, cheapest first

1. Add `test_the_census_actually_RUNS_in_ci` (one line, the precedent is in the same file).
2. `-r requirements-test.txt` in the census job, plus `timeout-minutes:`.
3. Record and diff the **site inventory**, not only the silent set — a vanished site must print
   `SITE GONE`, never `NOW GUARDED`.
4. Pre-flight: refuse to run on a package that does not `ast.parse` **and** does not match a recorded
   digest; write a crash marker before the first neuter and refuse to start if it exists.
5. Split the allowlist's one word into `UNGUARDED` and `UNREACHABLE`, and re-derive
   `validate_document::UntrustedRow::6`.
6. Either key on a normalised body digest instead of an ordinal, or accept positional ids and say so
   in the file — Case B is currently undetectable.
7. Record the pair result: the file's claim is per-line and 2 of 13 lines are false at k=2.

---

# 1 · OVERALL VERDICT

## **FAIL** — 13 findings introduced, 9 of them in the gate itself, 4 in the delta.

The delta's two production changes are, in one sentence each: a type bound that is correct and
untested at the strictness it claims; and a one-token rule with no test at all whose commit message
says it was driven at 9/9.

| claim (builder's, from the commit + comments) | falsifier | verdict |
|---|---|---|
| C1 "the census mechanises the one measurement that converged" | a different silent set on a rerun | **TRUE — reproduced exactly**, 68/13/55, allowlist `diff`-identical |
| C2 "every line is a claim that nothing checks" | a test that reds when the line is removed | **FALSE for 2 of 13**, 378-subset enumeration |
| C3 "a restore that changes the artifact is not a restore" (bytes) | a byte diff after a run | **TRUE** for a completed run; **FALSE across a crash** (§0.3) |
| C4 "the sibling has its own id and its own row" | a site whose status depends on a sibling | **FALSE** — `canon::1` is masked by `canon::4` |
| C5 "NOT the line number … an allowlist keyed on line numbers goes stale silently" | a stale allowlist with `rc=0` | **HALF-TRUE** — Case B is stale at `rc=0` |
| C6 "the door is bounded and the contract is stated instead of assumed: **the recorder must be this turn's**" | a carried recorder accepted | **FALSE** — `type() is` cannot express "this turn's"; executed, the carried recorder returns `True` |
| C7 "my test asserted the *fresh* case; the **carried** case … was the one it never drove" | the new test failing when the carried semantics break | **STILL TRUE OF THE NEW TEST** — 0 of 4 carried-recorder mutants red it |
| C8 "`type(...) is` because five argument types crashed this door" | `isinstance` passing the suite | **UNMEASURED** — `isinstance` is green on 137/137 |
| C9 W4 "Driven at 9/9 shapes, full suite at baseline" | reverting the token leaving the suite green | **NO ARTIFACT** — revert → **137 passed** |

---

# 2 · FINDINGS

Reachability is stated for every one.

### A21-1 · The recorder-door test describes its own subject and cannot drive it — `test_cp0_instrument.py:3381`

The test is named `…__and_a_CARRIED_recorder_is_the_new_failure_mode` and its docstring says the
carried case *"was the one it never drove."* It still never drives it. Its `_carried` helper builds
turn A's outage, builds `rec_a`, arms turn B — and then calls
`instrument.catalogue_outage_registered()` **with no recorder**, asserting `False`, and
`rec_a.catalogue_outage()`, asserting `True`. The composition that is the defect —
`catalogue_outage_registered(rec_a)` after turn B is armed — is never written.

**Executed** (`exp_recorder.py`, on the frozen tree):

```
turn B, no recorder          -> False   (the shipped test asserts this is False)
turn B, turn A's recorder    -> True    (the hazard; the test never calls it)
HAZARD LIVE
```

Both of the test's assertions hold with the door's recorder branch **deleted**.

**Reachability: LATENT, not production.** The only caller that passes a recorder,
`voice_stream_service.py:422`, constructs `_voice_advertised` at `:242` inside
`voice_stream_response` (lines 215–839) and it never escapes that frame — no attribute store, no
module global, no container. The other two callers (`stream_service.py:5642`, `:8176`) pass nothing
and take the `None` path unchanged. The hazard needs a *future* caller that retains a recorder.

### A21-2 · The carried case is the same execution as `_O_K`, which a passing test asserts must be `True`

This is the sharpest thing I found, and it is the reason A21-1 is not an oversight.

`test_THE_RECORDER_IS_THE_SECOND_WITNESS`'s `_O_K` (`:2908`) and the new test's `_carried` (`:3403`)
are **alpha-equivalent** in statements 0–4 — AST-compared, differing only in the local name
`rec` vs `rec_a`:

| stmt | `_O_K` | `_carried` |
|---|---|---|
| 0 | `arm_turn_surface()` | identical |
| 1 | `record_catalogue_unavailable(stage=…, reason=…)` | identical |
| 2 | `rec = AdvertisedToolsRecorder()` | `rec_a = …` (α-equivalent) |
| 3 | `rec.absorb(surface_withheld.get())` | α-equivalent |
| 4 | `arm_turn_surface()`  *# comment: "same turn"* | identical  *# comment: "turn B"* |
| 5 | `return catalogue_outage_registered(rec)` → **asserted `True`** | returns the door **without** the recorder |

The two states are distinguished **only by a comment**. `_O_K` makes the exact call the new test
omits and asserts it must be `True`; the delta's own comment calls that same result *"U-2's founding
defect verbatim"*. A test that drove the hazard would red `_O_K`. **The carried case is
unfalsifiable at this seam**, which is why the shipped test asserts around it.

**This is the claim I am not allowed to settle, and here is its concrete form.** Whether the carried
case is a defect at all turns on the design's premise — *"each request runs in its own task and
therefore its own context copy."* If the premise holds, `_O_K` and "turn B" are the same reachable
state, `_O_K`'s assertion is right, and the parameter is correct-by-construction for its one caller.
If it fails, the delta ships U-2's founding defect and `_O_K` asserts the defect as the requirement.
**Nothing in the source can decide it**: the distinguishing input does not exist in the ContextVars.

**What would answer it, and who owns it — V-LIVE, not V-CODE.** An instrumented run of
`voice_stream_response` that (a) stamps a token on the context at `arm_turn_surface()` and logs it at
`:422` across two concurrent requests and one re-entered turn, and (b) records whether any
`AdvertisedToolsRecorder` object is reachable from two distinct token values. That is a runtime
observation, and this is the **third** round it has been carried as the blocker.

**The corollary for the delta:** `type(recorder) is AdvertisedToolsRecorder` **cannot** express *"the
recorder must be this turn's"*. The comment states a contract the code does not carry. The bound that
would carry it is a turn token on the recorder — which the design explicitly rejected ("passed rather
than held in a ContextVar"). *A guarantee claimed in a comment is not a guarantee.*

### A21-3 · The type bound is exact-type, and nothing measures the strictness — `instrument.py:579`

`type(recorder) is not AdvertisedToolsRecorder`. Executed: it rejects a **subclass** and a
**pre-`importlib.reload` instance of the same class**, with the message *"got a
AdvertisedToolsRecorder"* — which names the right class and refuses it, a debugging dead end.
**No legitimate caller crashes today**: no subclass exists in the repo, no test reloads
`app.services.instrument`, no test passes a mock. **Reachability: none today.** But `isinstance`
passes 137/137 (mutant M4), so the difference between the shipped bound and the loose one is
unmeasured — the comment's stated reason ("five argument types crashed this door") is satisfied by
either.

### A21-4 · W4's `s.body[:1]` has **no test**; the "9/9" left no artifact — `test_cp0_instrument.py:2284`

**Executed:** reverted the one token to `s.body` — the exact pre-delta state that *"every round a
verifier measured the cost"* of — and ran the file: **137 passed.** Restored: **137 passed.** The
only `try`-shape test, `test_an_ARM_INSIDE_A_TRY_BODY_is_not_CONDITIONAL_either` (`:3192`), puts the
arm **first**, which both rules accept. `grep` for `body[:1]`, `W4`, `precedes it` finds the comment
and nothing else.

The commit message says *"Driven at 9/9 shapes, full suite at baseline."* **The file cannot
distinguish the rule from its negation.** This is the sixth self-measurement in this run that exists
only as a sentence. **Reachability: the gate's own coverage** — a change to the rule in either
direction ships unnoticed.

### A21-5 · What the narrowing left: a `with` inside a `try` re-admits the whole body

**Enumerated**, 7 containers × 3 inner wrappers × 3 arm positions = **63 shapes**, each evaluated
against the pre-delta and post-delta helper:

* **18 shapes narrowed** — the fix does what it says for a `try` body's direct statements.
* **18 shapes still report a non-first arm as unconditional.** 12 of those are correct (a bare
  function body, or a `with` at top level: an exception there propagates and the turn dies, so there
  is no unarmed narrowing — the asymmetry with `try` is defensible and I am not calling it a bug).
* **6 are not.** `_unconditional_calls` recurses into a `With` with `s.body`, **not** `s.body[:1]`, so
  a `with` as the first statement of a `try` re-opens the full-body acceptance:

```python
async def probe(c):
    try:
        with d:
            prelude()          # may raise
            arm()              # reported UNCONDITIONAL
    except Exception:
        pass                   # swallows, and the turn continues UNARMED
```

That is route-18's hazard verbatim, surviving one nesting level in, across `try/except-pass`,
`try/finally` and `try/else`. **Reachability: the gate's coverage — a false GREEN**, the only
direction that matters, since every other residue makes the gate stricter.

### A21-6 · The three weak oracles — 5th round. **Fix them; do not delete the tests.**

`:3242`, `:3297`, `:3376`, all `pytest.raises(AssertionError, match="withheld_tools")`, byte-identical
to R19/R20 (+ the delta's line shift). **Measured**, not asserted: inside the gated test
(`test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE__not_a_literal_None`, `:1474-1708`) **two other
assertions carry `withheld_tools` in their message** — `:1695` and `:1700`, the two no-vacuity guards
— so the oracle is satisfied by a gate that fired for a reason unrelated to the probe. R20-A's
recommended phrase, *"persists the column with no recorder-derived argument"*, occurs **exactly once**
in the file.

**Worth fixing, not deleting.** The three tests are the *only* coverage that the terminal-write gate
is module-general (`agentruntime`, `routers`, `services`), and `app/agentruntime/` is where CP-2
lands — deleting them re-opens T8. The fix is three string literals and it converts "the gate fired"
into "the gate saw my probe." **Reachability: production** — a one-token refactor at a live site
makes two of them green over an unmeasured probe.

### A21-7 · Carried, untouched by the delta

| item | site | rounds open | delta touched it? |
|---|---|---|---|
| **T11d** — the SQL matcher resolves the literal, not the constant | `stream_service.py:6297` | 3rd | no — `stream_service.py` is not in the diff |
| **probe modules written into the live `app/` tree** (`_lwprobe_*`, 6 writers hardcode `"app"`; `_TURN_SCOPE_ROOT` already exists) | `test_cp0_instrument.py:3043/3078/3238/3293/3308/3370` | 3rd | no |
| **`:531` vs `:542`** — *"Ask the turn's RECORDER first"* against *"Read from the FLAG first"*, in one comment block | `instrument.py:531, 542` | **7th** — and the delta added a **third** instruction block after them | no |
| **the recorder is still inert at its only call site** (R20-A carried #2) | `voice_stream_service.py:422` | 2nd | no |

The probe-module finding is no longer theoretical for a second reason: **the census makes the same
class of mutation to the live tree, on purpose, 68 times per run** (§0.3).

---

# 3 · TABLES

## 3.1 · Bypass table

| # | bypass | executed | result |
|---|---|---|---|
| B1 | a guarded refusal masked by a same-class fallback | ✅ neuter `canon.py:60` | census says SILENT, test passes → **allowlist licenses the deletion** |
| B2 | remove a refusal the allowlist calls silent, then rerun the census | ✅ | `NOW GUARDED … drop it from the allowlist`, `rc=1`, damage re-persisted |
| B3 | reorder two same-class SILENT raises | ✅ | `rc=0` — allowlist silently names different sites |
| B4 | delete the census job from the workflow | ✅ grep | no test asserts it; suite green |
| B5 | run the census job with only `requirements.txt` | ✅ pytest shim | `SELFTEST FAIL`, `rc=1` — inert, never passes |
| B6 | kill the census; commit | ✅ ×4 | 4/4 leave a `raise → pass` in a tracked file |
| B7 | read the tree while a census runs | ✅ 20 runs | **15/20 RED** |
| B8 | write the refusal as `assert` / `sys.exit` / a subpackage / `__init__.py` | ✅ AST sweep | invisible; 0 today, 0 guards against tomorrow |
| B9 | `isinstance` instead of `type() is` on the recorder door | ✅ mutant M4 | **GREEN**, 137/137 |
| B10 | break the carried-recorder semantics (M2/M6/M7) | ✅ 3 mutants | new test **GREEN** on all three |
| B11 | revert W4's token | ✅ | **137 passed** |
| B12 | arm inside a `with` inside a `try` with a swallowing handler | ✅ 63-shape enumeration | reported unconditional → **false GREEN** |
| B13 | fire the terminal-write gate for any reason at all | ✅ message count | 3 oracles satisfied by `:1695`/`:1700` |

## 3.2 · Red-ability table — **my denominator**

**Space A: the recorder door.** 7 mutants over the two lines the delta added, plus the whole door.
Denominator 7, run against (i) the new test alone and (ii) the whole 137-test file.

| mutant | new test | whole file |
|---|---|---|
| M1 delete the TYPE BOUND (pre-delta) | **RED** | RED |
| M2 delete the RECORDER READ (the parameter's whole point) | GREEN | RED |
| M3 delete BOTH (parameter inert) | **RED** | RED |
| M4 exact-type → `isinstance` | GREEN | **GREEN** |
| M5 `TypeError` → `ValueError` | **RED** | RED |
| M6 message loses `(recorder=)` | GREEN | **GREEN** |
| M7 invert the recorder read (a real outage reports `False`) | GREEN | RED |

**New test: 3/7.** Split by subject: **3 of 3 type-bound mutants** red it; **0 of 4** mutants that
break the *carried-recorder* semantics — its stated subject — red it. Two mutants (M4, M6) are
invisible to the entire 137-test file.

**Space B: W4.** Denominator 1 (the token). **0/1.**

**Space C: the census's own claims.** Denominator 13 allowlist lines × 378 enumerated subsets.
**2/13 lines refuted.**

**Space D: the census as a gate.** Denominator 6 defeat shapes attempted (B2–B7). **6/6 succeeded**;
2 of the 6 exit 0 or exit 1-with-a-false-message.

## 3.3 · Sibling table

| fix landed at | the sibling one token away | status |
|---|---|---|
| `Try` → `s.body[:1]` | `With`/`AsyncWith` → still `s.body`; and a `With` **inside** a `Try` re-opens it | **open**, A21-5 |
| the type of the recorder | the *turn* of the recorder — the thing the comment promises | **open**, A21-2 |
| `canon._norm::3` (guarded) | `::1` and `::4`, guarded-but-recorded-silent | **open**, §0.2 |
| `check_row_shape::7` members-are-non-empty-strings | `check_contract::7` members-match-`_ID` — the same rule, both silent | both on the allowlist |
| membrane gate: `test_the_gate_actually_RUNS_in_ci` | the census job — no equivalent | **open**, §0.5 |
| census: bytes restored on the happy path | bytes across a crash — the same failure the docstring narrates | **open**, §0.3 |

## 3.4 · Guard table

| guard | exists | fires | fires for the right reason |
|---|---|---|---|
| census `--selftest` (both directions) | ✅ | ✅ | ✅ |
| census site-count floor | ✅ `< 50` | only below 50 | ❌ — 18 deletions pass |
| census site-**set** comparison | ❌ | — | — |
| census pre-flight tree-clean | ❌ | — | — |
| census wired-in-CI test | ❌ | — | — |
| census CI job deps | ❌ (`requirements.txt`, no pytest) | job always red | ❌ |
| recorder type bound | ✅ | ✅ on 5 types | ✅ (but strictness unmeasured) |
| recorder **turn** bound | ❌ | — | — |
| W4 rule test | ❌ | — | — |
| terminal-write probe oracles ×3 | ✅ | ✅ | ❌ 5th round |
| membrane suite as a census oracle | ✅ | ✅ | ⚠️ message-level, so a fallback masks a sibling |

## 3.5 · Reachability verdict on every finding

| finding | reachable in production? |
|---|---|
| §0.2 false allowlist line (`canon::1`/`::4`) | **process** — licenses a real deletion; the C-12 message degrades, CI green |
| §0.3 fail-open after a crash | **certain** — 4/4 kills leave damage, 19 % of it invisible; measured |
| §0.3 concurrency | **certain, and it already happened this round** — 15/20 |
| §0.4 silent staleness on reorder | **process** — the allowlist decays with no signal |
| §0.5 job not wired-in-tested | **certain** — one line of YAML |
| §0.5 job cannot pass | **certain if `setup-python` has no pytest** — stated falsifiable |
| A21-1 / A21-2 carried recorder | **latent** — unreachable via the only wired caller (the recorder never leaves its frame); reachable via any future caller. **Whether it is a defect at all is the V-LIVE question** |
| A21-3 exact-type bound | **none today** — no subclass, no reload, no mock |
| A21-4 W4 untested | **gate coverage** — the rule can drift either way unnoticed |
| A21-5 `with`-in-`try` residue | **gate coverage, false GREEN** — the only dangerous direction |
| A21-6 weak oracles | **production** — a one-token refactor at a live site |
| A21-7 T11d / probes / `:531`-`:542` | as recorded in R19-A / R20-A; **untouched** |

---

# 4 · EXECUTED vs ARGUED

**32 load-bearing claims in this verdict. 27 executed, 5 argued.** Ratio **27 : 5 (84 %)**.

Every execution ran over an **enumerated** space or an **exhaustive** one, never a chosen sample:

| space | denominator | complete over |
|---|---|---|
| census reproduction | 68 sites | every `raise` in the package |
| allowlist honesty | **378 subsets** | all subsets of size ≤ 3 of the 13, + all-13 |
| harness-scope check | 13 × 2,266 tests | every non-e2e test in chat-service |
| refusal shapes | 8 construct classes × 8 modules | every `.py` under `app/agentruntime/` (`rglob`) |
| W4 | **63 shapes** | 7 containers × 3 wrappers × 3 arm positions |
| recorder door | 7 mutants | every line the delta added, plus the whole door |
| kill points | 4 | 12/20/30/45 s |
| concurrency | 20 runs | — |
| id stability | 2 reorders | one per status-pairing class (differing, identical) |

Suite invocations: **≈ 500** membrane runs (68 census + 378 subsets + 20 concurrency + probes),
**14** whole-suite runs (2,266 tests each), **≈ 20** `test_cp0_instrument.py` runs (137 each), and
**11** end-to-end census runs.

**The 5 argued claims, named so they can be attacked:**

1. The CI job cannot pass — the pytest-absence is executed, the *runner image* is not (§0.5b).
2. `validate_document::UntrustedRow::6` is unreachable — read from the class hierarchy, not driven.
3. The `with`-at-top-level residue is *correct* rather than a defect — a design argument about
   whether a propagating exception ends the turn.
4. The three weak oracles are worth fixing rather than deleting — a judgement about T8's value.
5. A `raise` sharing its line would be mis-neutered — the shape does not exist today, so I could not
   execute it on the real package.

**And the standing caveat, which cost me three cycles this round:** *executed* is not enough on a
shared tree. My first eight baseline measurements were executed, reproducible-looking, and wrong,
because another process was mutating the artifact. **An execution is only as frozen as its tree.**

---

# 5 · CONVERGENCE

**Raw.** Nine load-bearing claims in scope A (§1). **Closed: 1** (C1 — the census reproduces exactly).
**Refuted: 4** (C2, C4, C6, C9). **Half: 2** (C3, C5). **Unmeasured: 2** (C7 still true of the new
test, C8 never measured).

**Findings introduced by this delta: 13** — nine in the census (§0.1 blind spot, §0.2 false lines,
§0.3 fail-open, §0.3 concurrency, §0.4 id, §0.5a not wired-in-tested, §0.5b job cannot pass, §0.2
one-word-two-facts, the missing `timeout-minutes`) and four in the delta proper (A21-1/2 counted as
one, A21-3, A21-4, A21-5).

**Findings closed by this delta: 1** — the door no longer accepts an arbitrary object, and the five
crashing types are genuinely driven. That is real and I do not want it lost in the FAIL.

**The series, raw:** `2,1,2,1,3,2,4,3,2,2,2,5,` **`13`**.

I agree with R20-A that `introduced` carries no signal, and this round is the proof: 9 of my 13 are
about a **brand-new artefact being graded for the first time**, so the jump measures novelty, not
deterioration. **Excluding the census, the delta introduced 4 — the second-highest of the run, on
~30 production lines.** The two numbers that carry signal are polarity (4 refuted of 9) and
enumerated-space coverage (§4), and both got worse in the direction that matters: **the delta's two
production changes are 3/7 and 0/1 red-able**, and the one that is 0/1 shipped with a "9/9" in its
commit message.

**On the termination question, which R20 answered and R21 kept open.** R20's recommendation was
*close against the mechanised census*. **That recommendation is not yet executable.** The census as
shipped cannot run in CI (§0.5b), is not asserted to be in CI (§0.5a), certifies two false lines
(§0.2), goes stale silently under reorder (§0.4) and re-persists its own crash damage (§0.3). Five of
those are ≤ 10 lines each. **Fix those five and the recommendation becomes executable, and I would
support it** — the mechanism is right and its convergence property is real. Closing against it today
would freeze an allowlist with two false claims into the definition of "closed".

**Carried into whatever comes next, in priority order:**

1. **§0.6 items 1–4** — the census cannot be the closure mechanism until it runs, is asserted to run,
   fails closed across a crash, and reports a deleted site as deleted.
2. **The V-LIVE question, third round.** Whether one context ever serves two turns decides whether
   A21-1/A21-2 are a defect or a non-event — and `_O_K` currently *asserts* one answer while the
   delta's comment *assumes* the other. **No amount of source reading will settle it.**
3. **Write W4's test**, or revert the token. One token, five rounds, still 0/1.
4. **Narrow `With` the way `Try` was narrowed**, or state in the docstring why they differ.
5. **Fix the three weak oracles** — three string literals, 5th round.
6. **Point the probe writers at `_TURN_SCOPE_ROOT`**, 3rd round — now urgent, because the census
   normalises live-tree mutation.
7. **Resolve `:531` vs `:542`**, 7th round. One of the two sentences is false and the comment now has
   three instructions where it needs one.

---

`git rev-parse HEAD` **at finish**: `9818c7bc57c8381a4dddbbfcc88cbaadc5e89f06` — **unmoved.**
`git status --porcelain -- services/ scripts/ contracts/ .github/` at finish: **empty**. (Mid-round it
was not: `app/agentruntime/surface.py` carried another agent's injected `summarise_rows` probe and
`contract.py` was momentarily neutered — recorded in §0.3. I neither touched nor reverted either;
the other party restored them.) No tracked file was written except this verdict. No `git checkout` was
used; every patch was restored from my own byte snapshot with an equality assert.
