# CP-1 · round 22 · V-CODE **B — the membrane**

**Artifact:** `c37459826de3c410654123e7351200afcccc8085` at start **and** at finish — it did not move.
Graded delta `1569ce443` + `93af52373`, diffed against `9818c7bc5`.
`git status --porcelain` **empty** at start and at finish. **No `git checkout` at any point**; every
injection was patched and restored as BYTES from my own scratchpad snapshot, and **14/14 files are
byte-identical to that snapshot** at finish (8 package modules, 2 contracts, 2 scripts, the suite,
the workflow).

---

# ▶ THE CENSUS VERDICT — **it now runs green in CI, and 3 of the 5 fixes are half-fixes**

The five fixes shipped. I graded each against the thing it claims to close, over an enumerated space.
**Two closed. One closed on Linux and is dead code on the platform every previous kill was measured
on. Two are half-fixed at the sibling, which is this run's signature failure — now inside the
instrument built to forbid it.**

| # | prompt item | verdict | the number |
|---|---|---|---|
| 1 | kill it four ways | 🔴 **3 of 5 termination modes still leave a neutered production module in a tracked file** | executed, 7 kill runs |
| 2 | reorder / rename / reindent / message | 🔴 **1 of 4 correct.** A one-character message edit moves **13/13** allowlist rows | executed, enumerated over all 13 |
| 3 | the CI green state | ✅ **REACHABLE — I executed the job's steps and it exits 0** | clean venv, `68/13/55`, 9 m 48 s |
| 4 | what it still cannot say | 🔴 **not the honest boundary — it is the boundary of a `bool`** | see §0.4 |
| 5 | concurrency | 🔴 **WORSE: 20/20, up from 15/20** (control 0/20) | executed |

## 0.1 · Item 1 — kill it four ways. **I killed it five, and 3 of 5 damage the tree.**

Every run: `git archive`-free, live tree, all 8 package files byte-compared against a pre-run
snapshot, then restored by me.

| # | termination mode | how it reaches the process | rc | tree afterwards |
|---|---|---|---|---|
| K1 | **SIGINT**, delivered in-process (`raise_signal`) — the Linux `Ctrl-C` / `kill -INT` path | the registered handler runs | **130** | ✅ **CLEAN** |
| K2 | **SIGTERM**, delivered in-process — the Linux `kill` / CI-timeout path | the registered handler runs | **130** | ✅ **CLEAN** |
| K3 | **crash inside the loop** (`MemoryError` injected at the 6th `_suite_is_green()`) | `finally` + `atexit` | 1 | ✅ **CLEAN** |
| K4 | **SIGKILL-equivalent: `TerminateProcess`** — `Popen.kill()`, `taskkill /F`, an OOM-killer, a lost runner, **and `os.kill(pid, SIGTERM)` on Windows** | nothing runs | 1 / 15 | 🔴 **`admission.py` left as `pass`** |
| K5 | **`TerminateProcess` at 9 s — inside `--selftest`, before `census()` exists** | nothing runs | 1 | 🔴 **`contract.py:218` left as `pass`** |

Reproduced K4 three separate times (two in the kill matrix, once more as a side effect of §0.5's
concurrency run). **`git status` showed the damage every time**, which is the one mercy.

### 🔴 B22-3 — the snapshot is **not** taken before the first write, and the comment says it is

`census.py:121` heads the block: **"SNAPSHOT EVERY FILE BEFORE THE FIRST WRITE, AND RESTORE ON ANY
EXIT."** The snapshot is at `census.py:132`, inside `census()`. **The first write is at
`census.py:193`, inside `_selftest()`** — and `main()` at `census.py:216` runs `_selftest()` *first*.
So the first ~15 seconds of every census run, in CI and locally, has **no snapshot, no `atexit`
registration and no signal handler at all**. K5 is that window, executed: a hard kill at 9 s leaves
`contract.py:218`'s `raise ContractViolation` as `pass`, and nothing in the process would ever have
restored it. The sentence in the comment is false as written, and it is false about the function that
runs first.

### 🔴 B22-4 — the `assert` → `SystemExit` fix landed at one of two sites, and the other runs first

R21 found the restore guarantee was an `assert`, removed by `-O`. The delta replaced it at
`census.py:160`. **`census.py:198` is still `assert probe.read_bytes() == raw`** — in `_selftest()`.
Executed, by corrupting the selftest's own restore so the guarantee has something to catch:

```
python     (assert active): rc=1  contract.py LEFT DRIFTED: True   AssertionError: restore changed the probe file
python -O  (assert removed): rc=0  contract.py LEFT DRIFTED: True   "agentruntime-census selftest OK - 68 raise sites, fires on a guarded one"
```

**Under `python -O` the census prints `selftest OK`, exits 0, and leaves a production module modified
in the tracked tree.** That is the exact defect R21 recorded, at the sibling of the line that was
fixed. **Ninth time this run a pair has been half-fixed.**

### 🔴 B22-6 — on Windows, the `SIGTERM` registration is unreachable code

`os.kill(pid, SIGTERM)` on Windows is `TerminateProcess`, not a signal delivery; there is no
mechanism that can deliver SIGTERM to a Windows process. So `signal.signal(signal.SIGTERM, …)` at
`census.py:141` **can never fire on the platform where all four of R21's kills, and all five of
mine, were measured.** It is real on `ubuntu-latest`, where CI runs — so the fix is not vacuous, but
the builder cannot test it locally and did not say so. (`CREATE_NEW_PROCESS_GROUP` also *disables*
`CTRL_C_EVENT` delivery, which is why my first SIGINT attempt was silently a `TerminateProcess`; I
report K1/K2 through `signal.raise_signal` for that reason, and label the substitution.)

### **"`atexit` does not run on SIGKILL — what does that cost, and is it acceptable?"**

**Cost, measured, not argued:** a `raise → pass` in a tracked production module. The suite then reds
**blaming a test** — R21 measured that; §0.5 reproduces it 20 times over. In CI the workspace is
ephemeral so the cost is ~0; the entire cost lands on the developer and on **every other process
sharing the checkout**.

**Not acceptable — and it does not have to be accepted, because the hazard is removable for less
code than the machinery that fails to mitigate it.** The current block is **24 lines** (`snapshot`,
`_restore_all`, `atexit`, the signal loop, `SystemExit`) and covers **2 of the 5** termination modes
I executed. Neutering a **scratch tree** instead of the live one covers **5 of 5**, needs no signal
handling at all, and closes item 5 in the same change. Executed both variants so the builder does not
have to guess which:

| candidate scratch tree | baseline suite | neutered in the copy | live tree |
|---|---|---|---|
| `shutil.copytree(services/chat-service)` — 0.3 s, 3.8 MB | 🔴 **20 failed, 116 passed** — 20 tests are repo-anchored (`_REPO/.github/…`) | — | untouched |
| **`git archive HEAD` + untar, repo-depth** — 31.9 s, 213 MB | ✅ **136 passed** | ✅ **2 failed, 134 passed** | ✅ **byte-identical** |

**32 seconds of setup against a 9 m 48 s run.** The cheap version does not work and the working
version costs 5% of the runtime. This is the carried finding *"probe modules are written into the
live `app/` tree"* — the census reproduced it, and then hardened **around** it instead of removing
it.

## 0.2 · Item 2 — reorder, rename, reindent, message. **1 of 4 correct.**

`ast.dump(child)` excludes attributes (executed: `'lineno' in ast.dump(...)` → `False`), so the
digest is over structure and constants, not position. Enumerated with the census's **own** `_sites`
over the **whole** package (68 sites re-derived independently: `{admission 4, canon 4, contract 18,
manifest 17, surface 25}` — the fifth convergence).

| mutation | **should** it move a row? | **does** it? | what the gate prints |
|---|---|---|---|
| **reorder two siblings** (`TakeWhileBudget.__post_init__` ::1↔::2 — a semantically null swap of two adjacent `if`-blocks) | **NO** — nothing about guarding changed | 🔴 **YES**, 2 rows churn | `NEWLY SILENT …::2::955d7989` + **`NOW GUARDED …::1::955d7989`** — the second is **FALSE**, and its remediation text is *"good news: drop it from the allowlist"* |
| **rename a function** (`check_row_shape` → `check_row_shape_v2`) | **NO** | 🔴 **YES — all 7 rows in the function at once**, 2 of them allowlisted | 2 `NEWLY SILENT` + 2 **false** `NOW GUARDED` |
| **reindent a raise** (wrap it one level deeper) | **NO** | ✅ **NO** | nothing — the one it gets right |
| **change a message string** (one character, applied to each allowlisted raise in turn) | **NO** — prose is not a guard | 🔴 **YES — 13 of 13** | 13 `NEWLY SILENT` + 13 **false** `NOW GUARDED` |

**The hash did not make the id correct. It moved the error from silent to loud and added a third
case.** The ordinal was silently stale on a reorder; the hash is *loudly wrong* on a reorder, *and*
loudly wrong on a rename, *and* loudly wrong on the single most frequent edit in this package —
these raises are three-to-six-line explanatory paragraphs that get rewritten every round.

The consequence is not noise, it is laundering. A delta that edits refusal prose produces 2·k false
gate lines whose stated remedy is *regenerate the allowlist*; and `--write` is the one operation that
can absorb a **real** new hole without anyone reading it. **The gate's cry-wolf rate is now
proportional to how much the builder writes**, and this builder writes a great deal.

**What a correct id looks like** — and it is *not* "hash more things". The id must be
position-independent **and** prose-independent: `module::qualname::ExcClass::sha(ast.dump(<the raise
with every `ast.Constant` of type `str` erased>))`, with a counter appended only when two raises are
identical after erasure. Reindent ✅ (already), reorder ✅ (digest carries the row), message ✅ (erased),
rename — still moves, and *should*, because a qualname is part of the address the allowlist points a
reader at.

## 0.3 · Item 3 — **the CI green state is REACHABLE. Executed, in the job's shape.**

Fresh venv → `pip install --quiet -r requirements.txt -r requirements-test.txt` (rc=0, pytest 9.1.1)
→ `python scripts/agentruntime-census.py`:

```
agentruntime-census selftest OK - 68 raise sites, fires on a guarded one
agentruntime-census: 68 sites, 13 silent, 55 red
real 9m47.936s      CENSUS RC=0        git status --porcelain: (empty)
```

**PASS**, and the fifth independent reproduction of `68/13/55`. Two disclosures:

* I ran it on **win32**, not `ubuntu-latest`. What differs — line endings, path separators — cannot
  reach the result: `ast.dump` is line-ending-blind, and the ids I re-derived match the committed
  allowlist exactly.
* **9 m 48 s for one job.** `lint-foundation.yml:9` states the workflow's acceptance target as
  *"Total wall-clock target ≤ 3 min"*. This one job is **3.3× the whole workflow's budget**, and it
  is serial by construction (one full suite run per site × 68). Not a defect; a cost nobody has
  written down. The scratch-tree change in §0.1 makes it parallelisable, which is a second reason to
  make it.

## 0.4 · Item 4 — **2 vs 5 is not a boundary. It is a `bool`.**

R21-A measured **2** by enumerating all 378 subsets of size ≤3 and finding exactly one minimal red
pair (`{canon::1, canon::4}`). R21-B (me) measured **5** by probing, per site, whether the *guarded
condition* is still refused. **Both are right, and they are answers to two different questions**
because the word `SILENT` names two different oracles:

* A asked **"is this row false against the census's own definition?"** — *the suite does not notice
  this site being removed*. Under that definition a masking pair is 2 false rows, because the suite
  *does* notice, jointly.
* B asked **"is this row false against the sentence a maintainer will act on?"** — *nothing checks
  it, so deleting it is free*. Under that definition sibling-masking and dead code both make the row
  false, and there are 5.

**Is it fixable? Mostly — and the residue is much smaller than "the honest limit of a red/silent
census".** `not red(s)` collapses **three** distinct facts:

| collapsed fact | correct action | decidable by a machine? |
|---|---|---|
| **UNGUARDED** — neutering makes the system *accept* what it refused | write a test | ✅ |
| **MASKED / DEGRADED** — still refused, by a sibling, with a worse class or a worse C-12 payload | fix the **test's assertion**, not the code | ✅ |
| **DEAD** — neutering changes nothing at all | **delete the handler** | ⚠️ partially |

**The instrument already produces the evidence that separates all three, and throws it away:
`_suite_is_green() -> bool` at `census.py:112`.** That is the whole defect. It runs the suite, gets
node ids, exception classes, C-12 `declaration_id`/`field_path`/`reason`/`accepted` and messages, and
returns one bit.

### The third column, what it is and who writes it

**Column 3 — `effect ∈ {accepts, refuses-differently, no-observable-change}`. Written by the census,
from a differential it already runs.** Change the return type to the observation set — pytest gives
it for free (`--tb=line`, or a 10-line `conftest` hook collecting `(nodeid, repr(excinfo.value))`) —
and compare neutered against control:

* the set gains a **passing** case where the control raised → **UNGUARDED**
* the set is **different but still refusing** → **MASKED/DEGRADED**; the finding is the oracle, and
  the row's remedy is *tighten the `match=`*, not *write a guard*
* the set is **identical** → **no observable change under this corpus** → a DEAD candidate

This one change re-scores every disputed row without a judgement call, and it makes A's 2 and my 5
the *same* number reported in two columns instead of two verifiers disagreeing in prose.

**Column 4 — `static ∈ {reachable, unreachable-handler}`. Written by a ~20-line AST pass, and it is
the only thing that can *prove* DEAD.** "Identical under this corpus" is corpus-relative and always
will be — that part **is** the honest boundary. But the two rows in dispute are not a general
liveness question: they are `except UntrustedRow` arms (`manifest.py:244-246`, `:427-428`) whose
`try` body calls only in-package functions, and this package is a closed membrane by construction
(that is what `ambient.py` is *for*). So the raise-class set of every callee is enumerable, and
"`ContractViolation` subclasses `UntrustedRow` and is caught by the arm above" is a **proof**, not a
heuristic. Where the `try` body is not closed, column 4 says `unknown` and column 3's DEAD stays a
candidate. Fail-open on the column, never on the row.

**Who writes them:** the **census**, both of them — not a human, not the verdicts. Cost:
`coverage`/observation plumbing is free; the AST pass is 20 lines; `requirements-test.txt` would need
nothing new. **What stays human, correctly:** whether an `UNGUARDED` refusal is *worth* guarding.
That is a design judgement and it belongs in the verdicts.

**So: not the honest boundary.** The honest boundary is exactly one sentence wide — *"no input in the
corpus distinguishes this site"* — and everything else the two verifiers disagreed about is
mechanisable from data the instrument already has in hand and discards.

## 0.5 · Item 5 — **concurrency is WORSE, and yes it is the census's problem**

| | red |
|---|---|
| **CONTROL** — 20 concurrent suite runs, no census | **0 / 20** |
| **TREATMENT** — 20 concurrent suite runs during a census | 🔴 **20 / 20** (`1 failed, 135 passed` each) |

R21 measured 15/20; I measure **20/20**. Nothing in the delta addressed it. And killing the census at
the end of that run left `admission.py` neutered for the fourth time in this verdict.

**Is it the census's problem?** **Yes, unambiguously.** The census is the only party writing into a
resource it does not own — the shared working tree — for 10 minutes at a time, and every other reader
of that tree is a victim with no way to detect it (the failure surfaces as a *test* failing). A
verifier's baselines are the cheapest casualty; a developer's `git status`, a watch-mode runner and a
pre-commit hook are the others. **The fix is the same one line of design as item 1: §0.1's
repo-depth scratch tree, executed above at 32 s.** One change closes items 1 and 5 and deletes 24
lines of signal handling.

## 0.6 · And the census's only test is defeated by a comment, **5 of 5**

`test_THE_CENSUS_IS_WIRED_AND_ITS_GREEN_STATE_IS_REACHABLE`
(`services/chat-service/tests/test_cp1_membrane.py:2120`) is 4 assertions, all substring or regex
gates over source text. Its docstring says *"This is a shape check and says so… **What it forbids is
the two things that were actually wrong.**"* Executed over the **enumerated** set of its own
assertions, each disabled the way a person would actually disable it:

| # | the mechanism, disabled realistically | test |
|---|---|---|
| 1 | `run: … -r requirements.txt  # requirements-test.txt dropped` | 🔴 **PASSES** |
| 2 | `# atexit.register(_restore_all)  DISABLED` | 🔴 **PASSES** |
| 3 | `for sig in (signal.SIGINT,):` — SIGTERM removed from the handler tuple | 🔴 **PASSES** (`SIGTERM` survives in the docstring at `census.py:131`) |
| 4 | `print("restore changed")  # was: raise SystemExit(...)` | 🔴 **PASSES** |
| 5 | every allowlist digest rewritten to `::deadbeef` | 🔴 **PASSES** — the assertion is `re.search(r'::[0-9a-f]{8}$')`, a **shape**, so it cannot tell a correct hash from a wrong one |

**5 of 5.** It reds only on wholesale *deletion*: dropping the install flag (1 failed), deleting both
handler statements (1 failed), reverting `SystemExit` to `assert` (1 failed), stripping the suffixes
entirely (1 failed) — 4/4 confirmed, so the test is not inert, it is **shaped exactly like the
sentence it was written from**. Disclosing "shape check" is not disclosing "green while the mechanism
is gone", and the specific claim *"what it forbids is the two things that were actually wrong"* is
**refuted 5/5**. Both new tests are also filed under `class TestStageKindsAreDataNotClosures`
(`:1637`), a class about generator pipelines.

---

# OVERALL: **FAIL**

Not because the census does not work — it works, it reproduced for the fifth time, and **its CI green
state is now reachable, which I executed**. It fails because **3 of the 5 fixes are half-fixes at the
sibling**, because **the test written to stop that is green over every realistic disablement**,
because **the fix that shipped in production is justified by a mechanism this repository does not
have**, and because **the register was not written at all this round.**

## Per-claim verdicts, each with its falsifier

| # | claim under test | the falsifier I ran | verdict |
|---|---|---|---|
| 1 | a killed census restores the tree | 5 termination modes on the live tree, byte-compared to a pre-run snapshot | 🔴 **FAIL — 3 of 5 damage** |
| 2 | the snapshot precedes the first write | locate both; kill at 9 s | 🔴 **FAIL — `_selftest` writes first, unprotected** |
| 3 | the restore guarantee survives `-O` | corrupt the selftest's restore, run with and without `-O` | 🔴 **FAIL at `:198`** — `-O` → rc 0, "OK", drifted tree |
| 4 | the row id pins the row to the refusal, not its position | 4 mutation classes over all 68 sites / all 13 rows | 🔴 **FAIL — 1 of 4; 13/13 rows move on a message edit** |
| 5 | the CI job's green state is reachable | clean venv, both requirements files, the job's exact command | ✅ **PASS — rc 0, `68/13/55`, 9 m 48 s** |
| 6 | `generate()` writes LF on every platform | revert `write_bytes` → `write_text`, run the suite | ✅ **PASS, and the guard reds** (`1 failed, 135 passed`) |
| 7 | *"the M1 drift gate is a byte-equality check"* | run the gate against a fully-CRLF manifest; `git diff` it | 🔴 **REFUTED — rc 0, empty diff** |
| 8 | the census has a test that forbids the two things that were wrong | disable each of its 4 assertions realistically | 🔴 **FAIL — 5 of 5 pass** |
| 9 | the census does not corrupt concurrent runs | 20 control + 20 treatment | 🔴 **FAIL — 0/20 vs 20/20** |
| 10 | `dict(r)` is shallow at all four doors | identity + post-validation mutation + cross-door | 🔴 **CONFIRMED OPEN**, 3rd round |
| 11 | B18-8 open | downgrade both pins + a control | 🔴 **OPEN, 5th round** |
| 12 | B18-11 open | AST sweep for `canon.<attr>` over the package | 🔴 **OPEN, 5th round** |
| 13 | B18-10 open | add a fifth exported door, run suite **and** gate | 🔴 **OPEN, 8th round** |
| 14 | `surface.py:305` open | 5 key-pair vehicles, control + neutered | 🔴 **OPEN, 4th round** |
| 15 | `_ID` has no length bound | 300-char id through `admit → generate → validate_document` | 🔴 **OPEN, 4th round** |
| 16 | the `Open, carried` register is trustworthy | read R21's RUNSTATE block | 🔴 **FAIL — the line is ABSENT** |

---

## 2 · `generate()`'s newline is pinned, the guard reds — **and every consequence it claims is false**

### The half that passes

`ambient.write_text` now goes through `path.write_bytes(text.encode("utf-8"))`
(`services/chat-service/app/agentruntime/ambient.py:90`). Reverting that one expression to
`path.write_text(text, encoding="utf-8")` reds the suite: **`1 failed, 135 passed`**. ✅ The fix is
correct, and it is one of only two claims in this delta with a clean red-able test.

### 🔴 B22-1 — the reason published beside it is false, in three places

> `ambient.py:76`  — *"**The M1 drift gate is a byte-equality check**, so the same declarations
> written on two developers' machines are two different documents to it, and `canon.digest` — the
> thing that decides whether the catalog changed — hashes bytes."*
> `test_cp1_membrane.py:2158` — the same sentence, in the new test's docstring.
> `test_cp1_membrane.py:2172` — *"the M1 drift gate **compares bytes**"*, in the assertion message.
> `RUNSTATE` (R21 block) — *"**the M1 drift gate compares bytes**."*

**`scripts/agentruntime-membrane-gate.py:356-366` is a `dict` comparison**: it does
`json.loads(MANIFEST.read_text(...))` and then `if doc != expected`. Executed — I rewrote
`contracts/agent-runtime-manifest.json` entirely in CRLF and ran the gate:

```
GATE, LF   manifest: (0, 'agentruntime-membrane-gate OK - 8 module(s), 0 allowed external import(s), 2 single-sited type(s)')
GATE, CRLF manifest: (0, 'agentruntime-membrane-gate OK - 8 module(s), 0 allowed external import(s), 2 single-sited type(s)')
load() on the CRLF manifest: {'manifest_version': 1, 'contract_version': '1.0.0', 'declarations': []}
```

**Line endings cannot reach M1.** And the second half is false too: `.gitattributes:4` is
`* text=auto eol=lf`, so the CRLF write produces `git status` → ` M` but **`git diff --stat` →
empty** (executed). The commit is a no-op; the repository could never hold the two different
documents the sentence describes. `canon.digest` (`canon.py:100`) hashes `canonical_bytes()` of an
in-memory object and is **never applied to the manifest file** — 0 call sites anywhere in the package.

**Reachability: the defect is the claim, and the claim is in production source.** The fix is right,
the guard reds, and a maintainer who reads `ambient.py` now believes M1 catches this. It does not —
so if `write_bytes` is ever reverted, the *only* thing that catches it is the unit test whose own
message asserts the false mechanism. This is the "false claim in three places" pattern the census's
own docstring cites as the reason the census exists, committed in the same delta.

### The sweep — every `write_text`/`read_text` in the package and its two scripts

| site | pins bytes? | does it matter? |
|---|---|---|
| `ambient.py:90` `write_text` → `write_bytes` | ✅ fixed | the only writer the package has (verified: `manifest.py:324` is the sole call) |
| **`ambient.py:67` `read_text`** — the sibling three lines above | ❌ **universal-newline translation on read** | the reader silently **launders** a CRLF manifest into LF. Harmless today *because* M1 is a dict compare — but it means the write side is strict and the read side is permissive, and if anyone ever makes M1 the byte check the docstring claims, the reader defeats it |
| **`scripts/agentruntime-census.py:225` `ALLOWLIST.write_text(...)`** | ❌ **not fixed** | 🔴 **B22-7.** The docstring at `ambient.py:84-87` names *"the census script I wrote to end this class of failure"* as one of the three places, and says *"the only reliable answer is to stop calling it on anything whose bytes matter."* **1 of the 3 named places was fixed.** `contracts/agentruntime-census-silent.txt` is **CRLF in the working tree today** (952 B on disk, 936 B in the blob); only `.gitattributes eol=lf` keeps the commit clean — an external net the docstring does not know about |
| `census.py:236` `ALLOWLIST.read_text().splitlines()` + `.strip()` | n/a | normalises, so the *compare* is immune. That is why the artifact churns without the gate noticing |
| `membrane-gate.py:100,159,210,278` `read_text` for `ast.parse` | n/a | AST is line-ending blind |
| `membrane-gate.py:356` `MANIFEST.read_text` | n/a | feeds `json.loads`; §above |
| `membrane-gate.py:464-524` `p.write_text` (selftest fixtures) | n/a | temp files, no artifact |
| `canon.py:90-97` `json.dumps(...).encode("utf-8")` | ✅ explicit bytes | correct |

**Sweep verdict: 1 of 2 halves of the ambient boundary pinned, and 1 of the 3 places the fix's own
docstring names.**

## 3 · `dict(r)` is shallow at 4/4 doors — re-measured, and I ran the fix

**Re-measured, unchanged (3rd round):**

```
rows_of            members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
declarations       members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
discover           members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
validate_document  members IS the source list: True   after source mutation: ['t0', 'GHOST_NEVER_ADMITTED']
rows_of & discover share ONE members list: True   ...mutating one changed the other AND the source
a returned row accepts an undefined key: True (type: dict)
```

### Deep copy, or a frozen row? **Neither alone — and the schema change I was told would be needed is already there.**

* A **deep copy** closes the aliasing and leaves the row a plain mutable `dict`: `row["injected"]=1`
  is still accepted (executed), so a row that passed no clause is still constructible — just no
  longer corrupting.
* A **freeze alone** hands back a frozen view *over the caller's list*.
* `ROW_FIELDS["members"]` is **already `(list, tuple)`** (`contract.py:176`). R21-B expected a schema
  decision here; there isn't one. So the right shape — rebuild from what was checked, `members` as a
  `tuple`, matching `Declaration`'s own `frozen=True, slots=True, members: tuple[str, ...]` — is a
  genuine one-liner at each producer.

**Executed at BOTH siblings** (`surface.py:72` `out.append(dict(r))` and `manifest.py:448`
`[dict(r) for r in rows]`), each becoming `{**dict(r), "members": tuple(r["members"])}`:

```
rows_of / declarations / discover / validate_document   alias=False,  members = ('t0',) after source mutation
cross-door shared list: False
SUITE: 1 failed, 135 passed
```

**The one failure is the interesting part.**
`TestP4NoColumnIsBoundToAConstantAtTheWriteBoundary::test_validate_document_does_not_MUTATE_what_it_validates`
(`test_cp1_membrane.py:1156`) asserts the returned document `== ` the input, and `('t0',) != ['t0']`.
**The test that guards "a validator returns what it validated" passes today precisely *because* the
validator returns the caller's own object, and reds on the copy.** It cannot distinguish *returned an
equal copy* from *returned the same object* — which is the entire finding, sitting inside its own
guard. So the closure is **2 production lines + 1 expectation**, and the expectation change is itself
the closed finding.

⚠️ `surface.py:72` and `manifest.py:448` are **siblings**. Nine times this run a pair has been
half-fixed. **Both, or neither.**

Reachability: guard-only today (zero importers) → **production-reachable at the commit CP-2.1
imports the package**.

## 4 · B18-8, B18-11, B18-10, `surface.py:305`, `_ID` — all five carried, all five OPEN

### B18-8 — **5th round**, and the census is still structurally blind to it

| injection | suite |
|---|---|
| `type(key) is not str` → `not isinstance(key, str)` (`contract.py:220`) | **136 passed** |
| `type(m) is not str or not m` → `isinstance` (`contract.py:254`) | **136 passed** |
| **both at once** | **136 passed** |
| *control:* `type(row) is not dict` → `isinstance` at both reads (`:216`, `:217`) | **2 failed, 134 passed** |

1 of 3 exact-type pins is guarded. The control matters: this is a gap **in a family**, not an absent
convention. And the census says nothing about any of it — it measures `raise` statements; this is a
**condition**, and D1 from R21 is untouched by the delta.

### B18-11 — **5th round**

```
contract.py   canon imports at [21]   canon.<attr> uses: []
manifest.py   canon imports at [27]   canon.<attr> uses: []
'canon' in __all__: False
nfc() docstring still names manifest.load as a door: True
```

Two dead imports, **zero** attribute uses in the package, not exported, and the refuted docstring at
`canon.py:42` still verbatim two rounds after the code it describes recorded its own refutation.

### B18-10 — **8th round**

```
peek in __all__: True   importable: True
the new door serves an unvalidated row: ['TYPED BY HAND!!']
SUITE: (0, '136 passed')
GATE : (0, 'agentruntime-membrane-gate OK - 8 module(s), 0 allowed external import(s), 2 single-sited type(s)')
```

### `surface.py:305` — **4th round**, 5 vehicles, control vs neutered

| vehicle | control | site neutered |
|---|---|---|
| `(["cost2","asc"],)` | `ValueError: keys[0] is not a (field, direction) pair` | 🔴 **ACCEPTED** — `effective_keys() = (['cost2','asc'], ('id','asc'))` |
| `(("cost2","asc","x"),)` | refused | `ValueError: too many values to unpack` |
| `(("cost2",),)` | refused | `ValueError: not enough values to unpack` |
| `(7,)` | refused | `TypeError: cannot unpack non-iterable int` |
| `("ab",)` | refused | `ValueError: keys[0]: unknown direction 'b'` |

Load-bearing for **exactly one** vehicle; Python's unpack masks the other four, which is *why* the
census reads it silent. A test written to close it **must use the list pair** or it will pass with
the clause deleted — and this is precisely the row my predecessor predicted would be "closed" by a
test that changes no behaviour.

### `TakeWhileBudget` floor (allowlist row 13) and `_ID` — **4th round**

```
budget=-1  / -1e9   CONTROL -> ValueError    NEUTERED -> ACCEPTED, TakeWhileBudget(budget=-1, …)
_ID.match(300 chars): True | admit+generate OK | written id length: 300 | validate_document round-trip: 300
```

## 5 · **The register must be generated from the verdicts.** Here is the design.

### First, the measurement that makes it urgent

R20's `Open, carried` dropped six rows. **R21's RUNSTATE block contains no `Open, carried:` line at
all** — `awk` over the whole R21 section (`:1993-2075`): zero hits. So the failure mode escalated
from *loses rows* to *not written*. Five consecutive rounds. Two hand corrections have been applied
and neither held. **A third correction is not a fix; the correcting is the defect surface.**

### The design

**Source of truth: one machine-readable block per verdict file. Never the RUNSTATE.** Each V-CODE
verdict ends with a fenced `yaml` block; `docs/plans/…-RUNSTATE.md`'s `Open, carried` becomes a
**generated region between two sentinel comments**, regenerated by `scripts/agentruntime-findings.py`
and byte-compared in CI — the same shape the repo already runs twice
(`contracts/agentruntime-census-silent.txt`, the M1 manifest). Third instance, nothing new to learn.

```yaml
- id: B22-4                      # the MINTING name. Not the identity.
  anchor: scripts/agentruntime-census.py::_selftest
  axis: harness                  # CLOSED vocabulary
  round: 22
  verifier: B
  status: open                   # open | closed | refuted | superseded
  closed_by: null                # commit sha + test node id, REQUIRED when status != open
  evidence: executed             # executed | argued
  reach: harness                 # prod | guard-only | adversarial | process | harness
  subject: "the assert->SystemExit fix landed at :160 and not at :198"
```

**The id.** `B22-4` is a *label*, not the identity — labels are why B18-9 and B20-1 were confused for
each other on the coincidence of the phrase *"four doors"*. **Identity is `(anchor, axis)`**:

* `anchor` = `repo/relative/path.py::symbol` — the artifact and the symbol, not the sentence. For
  process findings the anchor is the artifact itself
  (`docs/plans/2026-08-04-agent-runtime-RUNSTATE.md::Open,carried`).
* `axis` from a **closed** vocabulary: `aliasing · type-pin · bound · dead-code · false-claim ·
  harness · oracle · process · structural`. Free text here re-opens the paraphrase drift that lost a
  row.

Two verifiers who measure the same defect at the same symbol on the same axis produce the **same
key**, and the generator **merges** them instead of minting a second row. Note deliberately: identity
is **not** a hash of prose — I measured this round that hashing prose moves 13/13 rows on a
one-character edit, and a register whose ids churn when a verifier rewords is the same failure one
level up.

### What the generator **refuses** (this is what makes it a gate, not a formatter)

1. **A row that was `open` in round *N-1* and is absent in round *N*.** Carrying forward is the
   generator's job. *Dropping* requires an explicit `status: closed|refuted|superseded` **in a
   verdict** — never in the RUNSTATE. This alone forbids all six rows lost in R20 and the whole of
   R21's omission.
2. **A verdict file with no findings block.** Missing must red; it must never default to empty. R21's
   failure was omission, and a generator that treats absent as `[]` reproduces it silently.
3. **`status: closed` with `closed_by: null`**, or a sha that does not exist, or a sha that does not
   touch `anchor`'s file, or a `test_node_id` that pytest cannot collect. *"A fix without a red-able
   test is not a closed finding"* becomes checkable: the generator verifies the node id **exists**;
   the census verifies it **reds**.
4. **A closure signed by the party that shipped the fix.** The generator reads only
   `verification/*.md`; the RUNSTATE is output-only. This is the run's central failure — five
   self-measurements wrong in the flattering direction — and it is mechanically enforceable at zero
   judgement cost.
5. **Two rows with the same `(anchor, axis)` and different ids** — forces the merge instead of the
   silent duplicate.
6. **An `axis` outside the vocabulary**, or a round number that skips (a skip means a verdict was not
   parsed, which must be loud).

**What it does not do:** decide whether a finding is real, or rank it. It refuses to let one
disappear **without a signed reason**. The judgement stays in the verdicts, which is where it belongs
and where it has actually been reliable.

**Cost:** ~60 lines plus one YAML block per verdict — smaller than the census, and unlike the census
it has an obvious red-able test (delete a row from round *N-1*'s block → generator exits 1).

**Its own falsifier, and the honest catch:** run it retroactively over R18–R21 and it must reproduce
**B18-1, B18-2, B18-9, B19-5, T10 and route 25** as `open`. It cannot, because those verdicts have no
block. So **one hand transcription is required, once** — and that transcription is the last
hand-typed register this run should ever contain. Any later hand edit to the generated region must
red the byte-compare.

---

## Bypass table

| guard | bypass | executed | reachable |
|---|---|---|---|
| the census's kill-safety | `TerminateProcess` (incl. `os.kill(pid, SIGTERM)` on Windows) | ✅ ×3 | **any hard kill, any OOM** |
| the census's kill-safety | kill during `_selftest()`, before the snapshot exists | ✅ | **the first ~15 s of every run** |
| the census's restore guarantee | `python -O` — the `assert` at `:198` | ✅ rc 0 + drifted tree | operator |
| the census's row id | edit the raise's own message string | ✅ **13/13 rows** | **every prose delta** |
| the census's row id | reorder two siblings (semantically null) | ✅ false `NOW GUARDED` | any refactor |
| the census's row id | rename the enclosing function | ✅ 7 rows at once | any refactor |
| the census's "closed = SILENT→RED" | weaken the **condition**, leave the `raise` | ✅ 3 patches, 136 passed | **any future fix** (B18-8) |
| the census test's `requirements-test.txt` clause | disable the install, keep the word in a comment | ✅ | any edit |
| the census test's `atexit`/`SIGTERM` clause | comment the call out; drop SIGTERM from the tuple | ✅ ×2 | any edit |
| the census test's `SystemExit` clause | downgrade to `print`, keep the words in a comment | ✅ | any edit |
| the census test's digest clause | write `::deadbeef` on every row | ✅ | `--write` on a stale tree |
| the census's byte-restore, for everyone else | run any suite concurrently | ✅ **20/20** | **any parallel process** |
| M1 drift | a CRLF manifest | ✅ rc 0 | latent (harmless; the docstring says otherwise) |
| `check_row_shape`'s `key` / `m` pins | a `str` subclass | ✅ ×3 | adversarial (B18-8) |
| four doors' "returns what it validated" | mutate the shared `members` list afterwards | ✅ 4/4 + cross-door | guard-only → **CP-2** |
| `OrderBy`'s key-pair shape | a 2-element **list** | ✅ | guard-only → CP-2 |
| `TakeWhileBudget`'s floor | `budget=-1` | ✅ | guard-only → CP-2 |
| `_ID` | a 300-character id | ✅ end-to-end | adversarial |
| four exported doors | add a fifth | ✅ suite **and** gate green | structural, 8th round |

## Red-ability table — **my denominator, derived from the delta**

The delta makes **10 checkable claims**. That is my denominator; it comes from the two commits' own
comments, docstrings and CI text, not from what happens to be tested.

| # | claim the delta makes | test that would red it | red-able? |
|---|---|---|---|
| 1 | a killed census restores the tree | — | ❌ **none**, and the claim is **false for 3 of 5 modes** |
| 2 | every file is snapshotted **before the first write** | — | ❌ none, and **false** |
| 3 | the restore guarantee is not removable by `-O` | the `raise SystemExit` substring assertion | 🟡 comment-defeatable, and **false at `:198`** |
| 4 | a row id pins the row to the refusal, not its position | the `::[0-9a-f]{8}$` regex | 🟡 **shape only** — `::deadbeef` passes; the claim is 3/4 wrong |
| 5 | the CI job's green state is reachable | the `requirements-test.txt` substring assertion | 🟡 comment-defeatable — **but the claim is TRUE, executed** |
| 6 | the census is wired into CI | `'agentruntime-census' in wf` | 🟡 comment-defeatable |
| 7 | `generate()` writes LF on every platform | `assert b"\r\n" not in raw` | ✅ **clean — reverting reds it** |
| 8 | pinning the newline did not change what is stored | `load(path)["declarations"][0]["id"] == "book_list"` | ✅ clean |
| 9 | the M1 drift gate is a byte-equality check | — | ❌ none, and **REFUTED by execution** |
| 10 | the census now has a test | the test exists | ✅ trivially |

**Cleanly red-able: 2 of 10 (7, 8). Weak/comment-defeatable: 4. No test at all: 3. Two of the ten
claims are false and one is refuted.**

For **my** findings the denominator is **9**, and **red-able today: 0 of 9** — every one is an
injection I wrote and none has a committed test. The one exception in spirit: B22-1's fix *is*
guarded (claim 7); it is the fix's stated **reason** that no test can red, because no test asserts a
docstring.

## Sibling table

| rule | applied to | missed | verdict |
|---|---|---|---|
| stop calling `write_text` on anything whose bytes matter | `ambient.write_text` ✅ | **`census.py:225`** ✗ · **`ambient.read_text`** ✗ | 1 of 3 named | 🔴 B22-7 |
| the restore guarantee must not be an `assert` | `census.py:160` ✅ | **`census.py:198`** ✗ | 1 of 2 | 🔴 B22-4 |
| snapshot before the first write | `census()` ✅ | **`_selftest()`** ✗ — and it runs first | 1 of 2 | 🔴 B22-3 |
| a returned row is rebuilt from what was checked | the row `dict` ✅ · both doc stamps ✅ | **`members`, the list itself** ✗ at both producers | 2 of 3 | 🔴 B20-1 |
| an exact-type pin against a `str` subclass | `row` ✅ | **`key`** ✗ · **`m`** ✗ | 1 of 3 | 🔴 B18-8 |
| a narrowing parameter has a floor | `TopK.k >= 1` ✅ · `cost_field` ✅ | **`budget >= 0`** ✗ | 2 of 3 | 🔴 allowlist row 13 |
| a stage parameter's shape is bounded | `keys` tuple ✅ · `field` ✅ · `direction` ✅ | **the pair, for a list** ✗ | 3 of 4 | 🔴 B19-4 |
| the doc-level clauses run at every door | `validate_document` ✅ | `rows_of` ✗ `declarations` ✗ `discover` ✗ | 1 of 4 | 🔴 B18-9 |
| a deleted claim's docstring goes with it | the call-site comment ✅ | **`nfc()`'s docstring** ✗ | 1 of 2 | 🔴 B18-11 |
| a harness must not leave the tree dirty | happy path ✅ · SIGINT ✅ · SIGTERM (Linux) ✅ · crash ✅ | **`TerminateProcess`** ✗ · **the selftest window** ✗ | 4 of 6 | 🔴 B22-3/6 |

## Guard table

| behaviour | guarded by | strength |
|---|---|---|
| the manifest is written LF | `:2155` `assert b"\r\n" not in raw` | ✅ **reds on revert** |
| the manifest still round-trips | `:2178` `load(...)["declarations"][0]["id"]` | ✅ |
| the census job installs a pytest | `:2136` substring | 🟡 comment-defeatable |
| the census restores on a kill | `:2141` substring | 🔴 **green with both handlers disabled** |
| the restore guarantee is not an `assert` | `:2145` substring | 🔴 green with the raise downgraded to a `print` |
| the ids are content-addressed | `:2150` regex on **shape** | 🔴 green over `::deadbeef` ×13 |
| the census's ids are *correct* | — | ❌ none |
| the census does not corrupt concurrent runs | — | ❌ none, and it does, 20/20 |
| M1 rejects a CRLF manifest | — | ❌ none — **and it does not reject it** |
| a non-string row key / a malformed member is refused **as the named clause** | sibling, same class | 🟡 refused, named clause untested |
| an `OrderBy` key-pair is a 2-tuple | — | ❌ none for the **list** vehicle |
| `budget >= 0` | — | ❌ none |
| `_ID` length | — | ❌ none |
| a validator returns a **copy** | `:1156` — asserts `==`, which the aliasing satisfies | 🔴 **the guard requires the defect** |

## Reachability verdict on **every** finding

| id | finding | class | production-reachable today? |
|---|---|---|---|
| **B22-1** | the LF fix's stated reason is false in 3 places; M1 is a `dict` compare (rc 0 on a CRLF manifest) and `git diff` is empty; `canon.digest` never touches the file | **false claim in production source** | **YES** — it is committed prose that misdirects the next reader |
| **B22-2** | the census's only test passes under 5 of 5 realistic disablements; *"what it forbids is the two things that were wrong"* is refuted 5/5 | instrument / test | **YES** |
| **B22-3** | the snapshot/`atexit`/signal block does not cover `_selftest()`, which writes first; kill at 9 s leaves `contract.py:218` neutered | harness / tree | **YES — executed** |
| **B22-4** | `assert` → `SystemExit` fixed at `:160`, not `:198`; under `-O` the selftest prints OK, exits 0, drifted tree | harness | **YES — executed** |
| **B22-5** | the id moves 13/13 allowlist rows on a message edit; a null reorder prints a **false** `NOW GUARDED`; a rename moves 7 | **instrument correctness** | **YES** — it is the proposed closure criterion |
| **B22-6** | `signal.signal(SIGTERM, …)` is unreachable on Windows; 3 of 5 termination modes damage the tree | harness / portability | **YES** locally; the fix is real on CI |
| **B22-7** | `census.py:225` still `write_text`s a committed contract artifact — 1 of the 3 places the fix's own docstring names; the working-tree file is CRLF today | sibling / artifact | **YES** (masked by `.gitattributes`, not by code) |
| **B22-8** | 20/20 concurrent suite runs red during a census (control 0/20; R21 measured 15/20) — a **regression**, and the census kill left the tree neutered a 4th time | harness / shared resource | **YES — executed** |
| **B22-9** | R21's RUNSTATE block carries **no `Open, carried:` line at all** — 5th consecutive round, now by omission | process | **YES** |
| B20-1 | `dict(r)` shallow at 4/4 doors, cross-door sharing; **2-line fix executed**, 1 test expectation | correctness | guard-only → **prod at CP-2** |
| B18-8 | 2 of 3 exact-type pins downgrade silently — **5th round** | adversarial | no |
| B18-10 | a fifth exported door, suite **and** gate green — **8th round** | structural | no |
| B18-11 | `canon` dead: 2 imports, 0 uses, refuted docstring verbatim — **5th round** | dead code / doc | no |
| B19-4 | `surface.py:305` — a 2-element **list** becomes an ordering key — **4th round** | guard-only | no |
| B19-12 | `_ID` unbounded; 300 chars end-to-end — **4th round** | adversarial | no |
| B21-1/2 | 5 of 13 allowlist rows mis-recorded; 2 are unreachable handlers | instrument | **YES**, untouched by the delta |
| B18-9 | doc-level stamps checked at 1 of 4 doors | structural | guard-only → CP-2 |

**Introduced this round: 9** (B22-1 … B22-9). **Carried, re-measured open: 8.**
**Closed by this delta: 2** — the CI green state (executed) and the CRLF write (guard reds).
**Half-closed: 3** — kill-safety, `-O`, id stability.

## Executed vs argued

| | count |
|---|---|
| **executed** — code I ran and read the output of | **26** |
| **argued** — reasoned, labelled, not run | **4** |

Executed: a full census in a **clean CI-shaped venv** (`68/13/55`, rc 0, 9 m 48 s) · an independent
re-derivation of all 68 ids with the census's own `_sites` · **7 kill runs across 5 termination
modes**, each byte-compared against a pre-run snapshot · the `-O` selftest experiment (with and
without) · **4 mutation classes enumerated over all 68 sites and all 13 allowlist rows** · **5
realistic disablements + 4 hard reverts of every assertion in the new test** (9/9 of its enumerated
assertion space) · the LF revert · the M1 gate against a CRLF manifest, plus `load()`, `git status`
and `git diff` on it · the allowlist blob-vs-worktree byte comparison · `dict(r)` at 4 doors +
cross-door + post-validation mutation + undefined-key · **the 2-line `dict(r)` fix at both siblings,
with the failing test identified** · `_ID` at 300 chars end-to-end · the `canon` AST sweep · **3
B18-8 injections + a control** · the fifth-door injection against suite **and** gate · 5 `OrderBy`
vehicles × control/neutered · `TakeWhileBudget` × control/neutered · **20 control + 20 concurrent
suite runs** · both scratch-tree candidates (`copytree` 20-red, `git archive` 136-green + correct
neutering).

Argued, and labelled: the third-column design (§0.4); the generated-register design (§5); that the
job behaves identically on `ubuntu-latest` (I ran the steps in a clean venv on win32 and named what
differs); whether the `TerminateProcess` cost is "acceptable" — a judgement, though the alternative I
recommend is executed.

**Not one finding rests on an argument**, and every execution is over an **enumerated** space — all
68 sites, all 13 allowlist rows, all 4 mutation classes, all 5 assertion clauses, all 5 termination
modes, all 5 key-pair vehicles, all 3 exact-type pins, both scratch-tree candidates — not a chosen
sample.

## Convergence

| | value |
|---|---|
| findings **introduced** by me, round 22 | **9** |
| B-scope `introduced` series, r10→r22 | `2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2, 5, 9, 9` |
| carried findings re-measured **open** | **8** |
| carried findings **closed** by this delta | **2** (first non-zero in three rounds) · half-closed 3 |
| my denominator, delta claims | **10** · cleanly red-able **2**, weak 4, none 3, **false 2 + refuted 1** |
| my denominator, my findings | **9** · red-able **0** |

**The series is flat at 9, and the composition changed.** Last round 7 of 9 were about the census
because the census was new. This round **6 of 9 are still about the census** — but they are no longer
first-grading findings, they are **half-fixes of the five fixes it shipped**. That is a different and
worse signal: the instrument is not settling. And the two genuine closures (CI green, the LF write)
are the first non-zero closure count in three rounds, so the loop is not dead — it is **converging on
the artifacts with a red-able test and diverging on everything else**, which is exactly what a
criterion of *"a fix without a red-able test is not a closed finding"* would predict if it were being
applied. It is not yet being applied to the instrument itself.

## ▶ My new falsifiable prediction

> **If the census is adopted as CP-1's closure criterion unchanged, the first delta that touches
> `app/agentruntime/` will churn `contracts/agentruntime-census-silent.txt` for a reason unrelated to
> guarding, and the gate's output will contain at least one FALSE `NOW GUARDED` line.** Concretely:
> the allowlist diff will show ≥ 3 rows whose `module::qualname::ExcClass::ordinal` prefix is
> **unchanged** and whose 8-hex digest **changed**, and neither the commit message nor the RUNSTATE
> will enumerate which sites moved or why.

**Falsifier (either half refutes me):** the next delta touches a raise site and (a) produces **zero**
allowlist churn, **or** (b) produces churn in which every moved row is named with its old digest, its
new digest and a control-vs-neutered probe showing the guarded condition's behaviour before and
after.

**Secondary, cheap to check:** **the two half-fixes in `_selftest()` — the `assert` at `census.py:198`
and the unprotected snapshot window — will be fixed at one of the two and not both.** That would be
the tenth instance.

**Standing from R21, and I re-affirm it:** the closure at `surface.py::OrderBy.__post_init__::
ValueError::3` will be written against a 3-tuple or a scalar and will pass with the clause deleted,
because I re-measured this round that 4 of its 5 vehicles are masked by Python's own unpack.

---

`git rev-parse HEAD` at finish: **`c37459826de3c410654123e7351200afcccc8085`** — unmoved.
`git status --porcelain`: **empty**. All 14 files I touched are **byte-identical** to my pre-run
scratchpad snapshot. The only tracked file this verdict wrote is itself. Nothing was committed.
