# CP-1 · round 22 · V-CODE · Verifier A — the instrument

`git rev-parse HEAD` **at start**: `c37459826de3c410654123e7351200afcccc8085`
Graded delta: `1569ce443` + `93af52373`, diffed against `9818c7bc5`.

**Method.** Every measurement ran in a scratch tree materialised with
`git archive c37459826 | tar -x` — two on Windows (`t1`, `t2`) and one inside **WSL Ubuntu with
CPython 3.12**, which is the closest reproduction of the CI job available to me. Every patch was
restored from **my own byte snapshot with an equality assert**. No `git checkout`. No tracked file
written except this one. The live tree was read only: `git status --porcelain -- services/ scripts/
contracts/ .github/` was empty at start, mid-round and at finish.

Baseline, live tree, before anything: `python -m pytest tests/ --ignore=tests/e2e` →
**2270 passed** (R21 measured 2266; the delta adds 2 tests plus 2 elsewhere).

---

# 0 · THE CENSUS VERDICT

> R21 found the mechanism sound, the gate unfinished, and **five ≤10-line fixes**. All five shipped.
> This is the grading of those five.

## **Verdict: three of five fixes work. Two of the five are now each other's defect, and the job
## STILL CANNOT PASS — for a new reason this delta introduced.**

| R21 fix | shipped? | verdict |
|---|---|---|
| F1 `atexit` + SIGINT/SIGTERM restore | ✅ | **HALF** — 3 of 5 Linux kills clean; **0 of 6 Windows external kills reach it** |
| F2 AST digest in the row id | ✅ | **HALF** — closes reorder 98/98; **breaks the id across interpreters, 0/68** |
| F3 `-r requirements-test.txt` in CI | ✅ | **works for its stated purpose** (install rc=0, selftest OK) — **and the job still exits 1**, because of F2 |
| F4 `assert` → `raise SystemExit` | ✅ | **TRUE**, and red-able (mutant N5) |
| F5 a test that the census is wired | ✅ | **the sibling of the finding** — it asserts the *install* step, not that the census **runs** |

Two independent convergences I want on the record before the defects, because they are real:

* I reproduced R21-A's allowlist enumeration **exactly**, on my own harness, over my own
  denominator: **91 subsets** (k=1: 13, k=2: 78). `0/13` red alone; **exactly one minimal red pair**,
  `{canon::_norm::…::1, canon::_norm::…::4}`; **2 of 13 rows false**. Two verifiers, two harnesses,
  the same number to the member. That is the second measurement in twenty-two rounds with that
  property.
* **F2 does exactly what it was written to do.** Enumerated over all 98 same-class same-function
  sibling pairs in the package: **98/98 detected, 0 digest collisions**, including **6/6** of the
  pairs where both members are allowlisted SILENT. R21-A's Case B is **CLOSED**.

---

## 0.1 · Item 1 — kill it four ways

**Linux (the CI platform), five kills, in `~/cen` on CPython 3.12:**

| kill | rc | tree afterwards |
|---|---|---|
| `SIGINT` at 25 s | 130 | **CLEAN** |
| `SIGTERM` at 25 s | 130 | **CLEAN** |
| `SIGKILL` at 25 s | −9 | **DAMAGED** — `contract.py:249` `raise ContractViolation(…)` → `pass` |
| crash *inside the loop* (`RuntimeError` raised in `_suite_is_green`, site 12) | 1 | **CLEAN** |
| hard crash (`os._exit(9)` in `_suite_is_green`, site 12) | 9 | **DAMAGED** — `contract.py:221` → `pass` |

**3 of 5 clean.** F1 works on POSIX for every kill a handler can see. That is a genuine fix and it
is the first time in this run that a "4 of 4 left damage" finding came back with a majority clean.

**Windows (where the builder measured the original 4/4, and where the developer runs it):**

| kill | rc | tree afterwards |
|---|---|---|
| `os.kill(pid, SIGTERM)` at 25 s | 15 | **DAMAGED** — `canon.py:60` → `pass`, **an allowlisted SILENT site** |
| `Popen.terminate()` at 40 s | 1 | **DAMAGED** — `contract.py:218` → `pass` |
| `Popen.kill()` (incidental, ending my §0.5 concurrency run) | 1 | **DAMAGED** — `contract.py` |
| `CTRL_C_EVENT` → `CREATE_NEW_PROCESS_GROUP` | — | **IGNORED**; the census ran on for 90 s |
| `taskkill /PID` (no `/F`) | — | **no effect at all** |
| `taskkill /F /PID` | 1 | handler never ran |

I probed this separately with a target that logs on handler entry and on `atexit`:
**six external kill mechanisms, zero reached the handler; the log read `['armed']` every time.**
The control — `signal.raise_signal(SIGTERM)` inside the process — printed `HANDLER RAN`, rc=130. So
the handler is **correctly registered and correct**; it is simply **unreachable from outside on
Windows**. There is no way for one process to send SIGTERM to another there: `os.kill(pid, SIGTERM)`
and `Popen.terminate()` are both `TerminateProcess`, which runs no handler and no `atexit`.

**Falsifiable, and I am marking it UNVERIFIED rather than claiming it:** a human pressing Ctrl-C in
the console delivers `CTRL_C_EVENT`, which *is* routed to `SIGINT`. I tried to deliver a genuine one
with `FreeConsole`/`AttachConsole`/`GenerateConsoleCtrlEvent`; both attempts returned success and the
target survived with no handler entry. **I could not verify the Windows SIGINT path.** What I did
verify is that every *programmatic* kill bypasses it.

### What `atexit` not running on SIGKILL costs, and whether it is acceptable

The cost is exact and I measured its distribution rather than asserting it: the residue is a
`raise → pass` in a **tracked source file**. **13 of 68 sites (19 %) are SILENT**, so roughly one
kill in five lands where the suite cannot see the damage — and one of my three Windows kills landed
on `canon.py:60`, which is an allowlisted SILENT row. The suite then reddens blaming a test, or
worse, does not redden at all.

**It is not acceptable as it stands, and more signal handlers cannot fix it** — SIGKILL is
uncatchable by construction, and so is a segfault in a C extension. The only place an uncatchable
kill can be caught is **the next run**:

> Write a sentinel file naming the site about to be neutered **before** the first write, delete it
> after the last, and refuse to start when it exists. ~4 lines. It converts "the tree is quietly
> broken" into "the census refuses and tells you which file to restore."

Nothing like it exists today: no lock, no marker, no pre-flight tree-clean check. R21-A asked for it
(§0.6 item 4) and it did not ship.

**The better answer, which closes three findings at once, is one level up:** run the census in a
throwaway `git worktree` instead of in the live tree. Then a SIGKILL damages a directory nobody
reads, §0.5's concurrency hazard disappears, and the carried "probe modules in the live tree"
finding stops being reproduced by the instrument built to end it. ~6 lines. **This is the highest-
leverage change on the board and I recommend it over every other census fix.**

---

## 0.2 · Item 2 — reorder, rename, reindent, message

**Enumerated over all 68 sites, not over four chosen cases.** For each edit class I computed the
row-id delta directly from the census's own `_sites`.

| edit | *should* it move a row? | *does* it? | denominator |
|---|---|---|---|
| **reorder** two same-class same-function siblings | **YES** — that is what the row is for | **YES**, 98/98 pairs; **6/6** where both are allowlisted SILENT; **0** digest collisions | 98 pairs |
| **rename a function** | **NO** — nothing about the guarding changed | **YES**, 68/68 rows. Renaming any one of **8** functions rewrites **all 13** allowlist rows | 68 |
| **reindent a raise** | **NO** | **NO**, 0/68 — `ast.dump(include_attributes=False)` carries no `lineno`/`col_offset` | 68 |
| **change a message string** | **NO** — the census explicitly does not measure whether a guard is *right* | **YES**, 68/68; **13/13** allowlist rows relocate on a pure reword | 68 |

**Two of four are right; two are wrong in the same direction.** The digest pinned the row to the
refusal's *text* when the question was its *identity*. Every refusal in this package carries a C-12
message that is a paragraph, and those paragraphs are rewritten constantly — the delta itself
rewrites two. A pure reword of a SILENT site emits:

```
NEWLY SILENT  <new digest>  <- a refusal nothing checks; guard it or record it deliberately
NOW GUARDED   <old digest>  <- good news: drop it from the allowlist in the same change
```

**Both sentences are false.** Nothing was guarded and nothing was unguarded. R21-A recorded exactly
this pair of false sentences for the reorder case (§0.4 Case A); the digest did not fix it, it
**widened its trigger** from "a reorder" to "any edit to any message".

And the digest still does not carry the thing that *is* the refusal's identity: **its guarding
context**. Reindenting a `raise` out of its `if` block turns a conditional refusal into an
unconditional one and moves no row. *(Argued, not executed: I expect the selftest to red first
because the suite would not be green before injection — but the id, which is what item 2 asks
about, does not move.)*

---

## 0.3 · Item 3 — the CI green state. **EXECUTED. It still cannot pass.**

I ran **the job's own steps** in WSL Ubuntu on **CPython 3.12.3** — the version
`actions/setup-python@v7` is pinned to — in a fresh venv, on a `git archive` of the frozen commit.

**Step 1, `Install chat-service deps`:**

```
$ python -m pip install --quiet -r requirements.txt -r requirements-test.txt
INSTALL_RC=0
```

**F3 works for its stated purpose.** The selftest that previously died now passes:
`agentruntime-census selftest OK - 68 raise sites, fires on a guarded one`. R21-A's §0.5b is closed.

**Step 2, `Refusal census`:**

```
$ python scripts/agentruntime-census.py
agentruntime-census selftest OK - 68 raise sites, fires on a guarded one
NEWLY SILENT  canon.py::_norm::NotCanonicalisable::1::18e3609d   <- guard it or record it deliberately
… 12 more …
NOW GUARDED   canon.py::_norm::NotCanonicalisable::1::86a97b10   <- good news: drop it from the allowlist
… 12 more …
agentruntime-census: 68 sites, 13 silent, 55 red
RETURNCODE = 1
```

**Every one of the 13 allowlist rows is reported as both newly-silent and now-guarded. rc = 1.**

*(My first WSL run printed `CENSUS_RC=0`. That was argument mangling in **my** harness, not a census
defect; re-measured with a Python driver: `RETURNCODE = 1`. I am recording the correction because a
verifier reporting a false finding is the same failure as a builder reporting a false fix.)*

### The cause, proven at the id level rather than inferred

`hashlib.sha256(ast.dump(child).encode("utf-8")).hexdigest()[:8]` — and **`ast.dump` output is not
stable across CPython versions.** 3.13 omits a `Call`'s empty `keywords`; 3.12 emits `keywords=[]`.
Every one of the 68 sites is `raise Exc(...)`, i.e. a `Call`. Measured:

| comparison | result |
|---|---|
| site ids identical between 3.13 (builder's Windows) and 3.12 (CI's pin) | **0 of 68** |
| the same ids **with the digest stripped** | **68 of 68 identical** |
| committed allowlist rows that **exist** under 3.12 | **0 of 13** |
| committed allowlist rows that exist under 3.13 | 13 of 13 |

**The digest is the sole cause**, and the allowlist was generated on an interpreter CI does not run.

**The second failure mode is worse than the first.** The old one was inert and said so
(`SELFTEST FAIL`, rc=1). This one passes the selftest, produces a complete and correct-looking
census, and then instructs the maintainer — **thirteen times, in CI** — to *"drop it from the
allowlist in the same change."* Following the gate's own instruction deletes the entire allowlist,
which is the record this effort's closure criterion is defined against.

**Falsifier, stated both ways.** If `ubuntu-latest` + `setup-python@v7` at `3.12` resolved to an
interpreter whose `ast.dump` matched 3.13's, I am wrong; it does not, and the measurement above is
on a real 3.12.3. And in the other direction: regenerating the allowlist on 3.12 makes the job green
**and makes every developer on 3.13 red**. **There is no interpreter on which both are green.** The
fix is to hash something version-stable — `ast.unparse(node)`, or the site's own source slice — not
`ast.dump`.

**The shape of this is the run's signature failure.** F2 and F3 were written to close two findings
from the same verdict, and **each is the other's defect**. Neither was run in the CI shape
*together* — which is verbatim what F3's own commit message says it exists to prevent: *"I wired a
gate whose green state was unreachable and did not run it in its CI shape before shipping it."*
It shipped again, one commit later, in the same file.

---

## 0.4 · Item 4 — what it still cannot say

**My own measurement of the boundary first.** 91 subsets, exhaustive at k ≤ 2 over the 13 rows:

| k | subsets | RED |
|---|---|---|
| 1 | 13 | **0** |
| 2 | 78 | **1** — `{canon::_norm::…::1, canon::_norm::…::4}` |
| **total** | **91** | **1 minimal pair → 2 of 13 rows false as written** |

That is R21-A's number, reproduced independently. R21-B's 5 came from asking a different question.
**Both are right, and that is the finding.**

### Is it fixable? Partly — and the two halves have different owners

**"Guarded by a same-class sibling" is MECHANICALLY DECIDABLE, and it is the census's job.** The
census already neuters one site at a time; neutering a site *together with* each same-class
same-function sibling is **6 extra suite runs** on today's package (98 such pairs exist across the
package; only 6 involve two allowlisted rows). It is not a column a human writes — it is a **second
measurement**, and the census is the only party that can run it.

**"Dead" / "unreachable" is NOT mechanically decidable.** `manifest.py::validate_document::
UntrustedRow::6` is an `except UntrustedRow` arm whose only callee raises `ContractViolation`,
caught by the handler above it. That is a reachability claim over the call graph. It is a
**judgement**, and a judgement needs a provenance, not a checkbox.

### If a third column is the answer, here it is

| column | who writes it | value |
|---|---|---|
| 1 · status | **the census** | `SILENT` — *neutering this site alone does not red the suite* |
| 2 · masking | **the census** | `MASKED-BY <sibling site id>` — measured by the pair sweep above |
| 3 · disposition | **a human, in a verdict** | `UNREACHABLE <verdict-id>` / `ACCEPTED <verdict-id>` |

**What the generator must refuse**, or the column is decoration:

1. a column-3 entry on a row id the census did not itself emit (a stale hand-edit);
2. a row asserted `UNREACHABLE` that the census can red by neutering it **alone** — a contradiction,
   and it must fail the build;
3. a `MASKED-BY` pointing at a site id that no longer exists.

**But the cheapest correct fix is not a third column at all.** The file's header says *"Every line
is a claim that nothing checks."* That asserts more than the measurement supports, which is exactly
why two verifiers asking different questions got 2 and 5. Change the sentence to what was actually
measured —

> *"Neutering this site **alone** does not red `tests/test_cp1_membrane.py`."*

— and **2 of 13 stop being false**, because the claim now matches the experiment. A claim that
matches its measurement cannot be refuted by asking a different question. That is one line, and it
should land before any column does.

**The honest boundary, stated plainly:** a red/silent census answers *"does the suite notice this
check is gone."* It cannot answer *"is this refusal right"*, *"is it reachable"*, or *"is it
needed."* Those are the verdicts' job, the docstring already says so, and the allowlist's header is
the one place the file forgets it.

---

## 0.5 · Item 5 — concurrency. **Still true. Slightly worse.**

Same tree, `t1`, 20 membrane-suite runs during one census, plus a control:

| | result |
|---|---|
| control, no census running | **3 of 3 GREEN** (`136 passed`) |
| during a census | **16 of 20 RED** (R21 measured 15/20) |
| failures per red run | 1–6, different every time, non-deterministic |
| when my driver killed the census at the end | **`contract.py` left damaged** — a sixth Windows kill data point, collected by accident |

**Is it the census's problem to solve? Yes — but not by making the census concurrency-safe.** It
mutates the artifact under test on purpose; that is its mechanism, not a bug. What *is* its problem
is that it does so **silently and unlocked**. Two things it owes, in order of value:

1. **Run out of tree** (`git worktree add` / run / remove). This makes the question moot, and it also
   closes §0.1's SIGKILL cost and the carried "probe modules in the live tree" finding. ~6 lines.
2. Failing that, **a sentinel file** — so a second census refuses to start, and so a *human* reading
   `DID NOT RAISE` in the membrane suite can find out why. R21-A lost three measurement cycles to
   this; I lost none, only because I read his verdict first. **That is not a property a tool should
   depend on.**

---

## 0.6 · The gate is still not a gate — and F5 landed on the sibling of the finding

R21-A §0.6 item 1 asked, in these words: *"Add `test_the_census_actually_RUNS_in_ci` (one line, the
precedent is in the same file)."* What shipped asserts the **install step**. Enumerated over 12
defeat shapes against `test_THE_CENSUS_IS_WIRED_AND_ITS_GREEN_STATE_IS_REACHABLE`:

| # | defeat | gate test |
|---|---|---|
| N1 | drop `-r requirements-test.txt` (the R21 fix itself) | **RED** ✅ |
| N2 | delete the whole `agentruntime-census:` job | **RED** ✅ |
| N3 | drop `atexit.register` from the census | **RED** ✅ |
| N4 | **delete the signal-handler loop** (`for sig in ():`) | **GREEN** ❌ |
| N5 | restore-guarantee back to `assert` | **RED** ✅ |
| N6 | strip the digests from the allowlist rows | **RED** ✅ |
| N7 | **keep the job, delete the `Refusal census` step** | **GREEN** ❌ |
| N8 | **keep the step, replace the command with `echo skip`** | **GREEN** ❌ |
| N9 | **run the census with `--write`** (self-regenerating, always green) | **GREEN** ❌ |
| N10 | empty the allowlist of every row | RED ✅ |
| N11 | **neuter the census's selftest** (`return 0` always) | **GREEN** ❌ |
| N12 | census never restores (drop `path.write_bytes(raw)`) | RED ✅ |

**7 of 12.** The five that get through are the five that matter: **N7/N8/N9/N11 all leave the census
absent, stubbed, self-regenerating or unproven while the test stays green.** The precedent twenty
lines away, `test_the_gate_actually_RUNS_in_ci`, asserts the literal string
`"- agentruntime-membrane-gate"` for exactly this reason and its docstring says why.

**N4 is the sharpest.** `assert 'atexit.register' in src and 'SIGTERM' in src`. Delete the entire
signal-handler loop and the test stays green — because **`SIGTERM` also appears at
`scripts/agentruntime-census.py:131`, in the comment that describes the mechanism**
(*"the restore is also registered with `atexit` and on SIGINT/SIGTERM"*). A gate assertion satisfied
by the prose that documents the thing it is checking. That is the fourth weak string-oracle in this
package and the first one shipped in a gate written to end weak gates.

**Still not shipped from R21-A §0.6:** item 3 (site-**inventory** diff — a *deleted* refusal still
prints `NOW GUARDED … good news`), item 4 (pre-flight / crash marker), item 5 (the vocabulary
split), item 7 (record the pair result). `timeout-minutes` is still absent on the census job, in a
repository that ships a `timeout-discipline-lint`.

**And one sibling of the delta's own lesson, one file over.** `93af52373` fixed
`ambient.write_text` with the reason *"the only reliable answer is to stop calling it on anything
whose bytes matter."* `scripts/agentruntime-census.py:225` still writes the allowlist — a file under
`contracts/` — with `ALLOWLIST.write_text(...)`, in a script whose own docstring opens with
*"It reads and writes BYTES."* Measured: `Path.write_text` emits CRLF on this platform, and the
working-tree allowlist **is CRLF today** (`git ls-files --eol` → `i/lf w/crlf`).
**Reachability: low** — `.gitattributes` `text=auto eol=lf` normalises it at commit, so it produces
no committed diff. I am ranking it as a sibling miss, not a live defect, and recording it because it
is the ninth instance of the fix landing on the named member rather than the set.

---

# 1 · OVERALL VERDICT

## **FAIL** — 8 findings introduced, 1 finding genuinely closed, 5 carried untouched.

**What closed, and I do not want it lost in the FAIL:** F2 closes R21-A's Case B **completely and
provably** (98/98, 0 collisions), and F3 closes R21-A §0.5b (the install step now works). F4 is
correct and red-able. That is three of five fixes doing real work.

**What did not:** the job still cannot pass, the gate still does not assert that the census runs, and
the delta touched **no file** under `services/chat-service/app/services/` or
`tests/test_cp0_instrument.py` — so every finding from R21 §2 is carried verbatim.

| claim (builder's, from the commits + comments) | falsifier | verdict |
|---|---|---|
| D1 "the restore is registered with `atexit` and on SIGINT/SIGTERM", so a killed run restores | a kill that leaves damage | **HALF** — 3/5 clean on Linux; **0 of 6 Windows external kills reach the handler**; SIGKILL and `os._exit` damage by construction |
| D2 "a short hash … pins the row to the refusal rather than to its position" | a semantics-preserving edit that moves a row, or a reorder that does not | **HALF** — reorder 98/98 ✅; **rename 68/68 and reword 68/68 move rows they should not**; guarding context still not carried |
| D3 "`requirements.txt` has no pytest … so the first version could never pass" (⇒ this one can) | executing the job's steps | **FALSE** — install rc=0, **census rc=1, 26 drift lines**, `0/13` allowlist rows exist under the pinned 3.12 |
| D4 "NOT `assert` — it vanishes under `python -O`" | a mutant that survives | **TRUE** — N5 reds |
| D5 "THE CENSUS IS WIRED AND ITS GREEN STATE IS REACHABLE" (the test's own name) | the census absent or vacuous with the test green | **FALSE on both halves** — N7/N8/N9/N11 green; and the green state is *not* reachable (D3) |
| D6 "it cannot prove the census MEASURES correctly, only that it is wired" | — | **TRUE, and it does not prove wired either** — it proves *installed* |
| D7 (carried) "the door is bounded … **the recorder must be this turn's**" | a carried recorder accepted | **FALSE**, re-executed — see §2.2 |
| D8 (carried) W4 "Driven at 9/9 shapes, full suite at baseline" | reverting the token leaving the suite green | **NO ARTIFACT** — revert → **137 passed**, 6th round |

---

# 2 · FINDINGS

Reachability stated for every one.

### A22-1 · The row id is not stable across CPython versions — `scripts/agentruntime-census.py:92`

```python
digest = hashlib.sha256(ast.dump(child).encode("utf-8")).hexdigest()[:8]
```

`ast.dump` is a debugging repr, not a canonical form, and its output changed in 3.13. **0 of 68 ids
survive the version change; 68/68 survive it with the digest stripped.** The committed allowlist was
generated on 3.13; CI pins 3.12.
**Reachability: CERTAIN, and it is a CI-red on every push today.** Fix: hash `ast.unparse(node)` or
the source slice.

### A22-2 · The CI job cannot be green — `.github/workflows/lint-foundation.yml:157–167`

Executed end-to-end on 3.12: install rc=0, census **rc=1**, 13 `NEWLY SILENT` + 13 `NOW GUARDED`.
The failure mode is worse than the one it replaced because it looks like a real result and its
instruction — repeated 13× — is *"drop it from the allowlist"*.
**Reachability: CERTAIN.** Consequence if obeyed: the closure record is deleted.

### A22-3 · The Windows kill path is entirely uncovered — `scripts/agentruntime-census.py:140–144`

`signal.signal(SIGTERM, …)` registers on Windows and **can never be delivered by another process**.
Six external mechanisms, zero handler entries; the control proves the handler itself is fine.
**Reachability: CERTAIN on the platform where the original 4/4 was measured.** 3 of 3 real Windows
kills left a `raise → pass` in a tracked file, one of them on an allowlisted SILENT site.

### A22-4 · The gate test asserts the install step, not the run step — `test_cp1_membrane.py:2120`

N7 (delete the `Refusal census` step), N8 (`echo skip`), N9 (`--write`), N11 (neuter the selftest)
are all **green**. The precedent that would have caught all four is 1,900 lines up in the same file.
**Reachability: CERTAIN — one line of YAML, and the sibling of the finding that asked for it.**

### A22-5 · A gate assertion satisfied by a comment — `test_cp1_membrane.py:2137`

`assert 'atexit.register' in src and 'SIGTERM' in src` stays green with the whole signal-handler
loop deleted, because `SIGTERM` occurs at `agentruntime-census.py:131` **in a comment**.
**Reachability: gate coverage, false GREEN** — the only direction that matters.

### A22-6 · A pure reword relocates every allowlist row, with two false sentences

68/68 digests change on a message edit; 13/13 allowlist rows relocate. The output is
`NEWLY SILENT … guard it` + `NOW GUARDED … good news`, and **both are false**. A rename does the
same for all 13 rows at once (8 functions carry them).
**Reachability: process, and frequent** — every C-12 message in this package is a paragraph under
active revision; the delta itself rewrites two.

### A22-7 · SIGKILL / hard-crash damage has no next-run detector

No lock, no marker, no pre-flight tree-clean check. 19 % of sites are SILENT, so ~1 uncatchable kill
in 5 leaves damage the suite cannot see. **Reachability: CERTAIN; measured 3 times this round.**
Two fixes, both ≤6 lines; the worktree one closes A22-8 as well.

### A22-8 · Concurrency, unchanged — 16 of 20

Control 3/3 green. R21 measured 15/20; I measured **16/20**. **Reachability: certain, and it already
destroyed one verifier's baselines.** Not fixed, not acknowledged in the delta.

### A22-9 · `ALLOWLIST.write_text` — the sibling of `93af52373`, one file over

`agentruntime-census.py:225`, in a script whose docstring opens *"It reads and writes BYTES."* The
working-tree allowlist is CRLF today. **Reachability: LOW** — `.gitattributes` normalises at commit.
Recorded as a sibling miss, ranked accordingly.

### A22-10 · Carried verbatim — the delta touched none of these

`git diff --stat 9818c7bc5 c37459826 -- services/chat-service/app/services/ tests/test_cp0_instrument.py`
is **empty**.

| item | site | rounds open |
|---|---|---|
| A21-1/A21-2 — the carried-recorder hazard, unfalsifiable at this seam | `instrument.py:579`, `test_cp0_instrument.py:2908/3381` | **3rd** |
| A21-3 — exact-type bound, strictness unmeasured (`isinstance` is green 137/137) | `instrument.py:580` | 2nd |
| A21-4 — W4's `s.body[:1]` has no test | `test_cp0_instrument.py:2284` | **6th** |
| A21-5 — a `With` inside a `Try` re-admits the whole body (`s.body`, not `s.body[:1]`) | `test_cp0_instrument.py:2257` | 2nd |
| A21-6 — three weak oracles, byte-identical | `:3242`, `:3297`, `:3376` | **6th** |
| T11d — the SQL matcher resolves the literal, not the constant | `stream_service.py:6297` | 4th |
| probe modules written into the live `app/` tree (6 writers hardcode `"app"`; `_TURN_SCOPE_ROOT = "app"` sits at `:2151`) | `:3047`, `:3077`, `:3230`, `:3279`, `:3308`, `:24` | 4th |
| `:531` "Ask the turn's **RECORDER** first" vs `:542` "Read from the **FLAG** first" | `instrument.py:531, 542` | **8th** |
| the recorder is inert at its only call site | `voice_stream_service.py:422` | 3rd |

---

# 2.1 · Item 2 of my section — **the shape that would red W4 exists, and it is one assertion**

**First, the baseline, re-measured on the frozen tree.** Revert `s.body[:1]` → `s.body`:

```
SHIPPED (s.body[:1])   rc=0  137 passed
REVERTED (s.body)      rc=0  137 passed
```

**0/1 red-able**, sixth round. Now the shape. Enumerated over **9** probes — 3 arm positions × 3
`try` tails — evaluated against the shipped helper *and* its negation in one process, with no probe
file written anywhere:

| arm position | `except-pass` | `finally` | `else` |
|---|---|---|---|
| **first** in the try body | 1 vs 1 — no | 1 vs 1 — no | 1 vs 1 — no |
| **second** | **0 vs 1 — YES** | **0 vs 1 — YES** | **0 vs 1 — YES** |
| **third** | **0 vs 1 — YES** | **0 vs 1 — YES** | **0 vs 1 — YES** |

**6 of 9 shapes discriminate the rule from its negation.** The test is:

```python
def test_a_try_body_arm_AFTER_another_statement_is_not_unconditional(self):
    """W4: a `try` is entered unconditionally, so its FIRST statement runs. The second runs only
    if the first did not raise — which is the whole reason the `try` is there."""
    fn = ast.parse(
        "async def probe(c):\n"
        "    try:\n"
        "        prelude()\n"          # may raise
        "        arm_turn_surface()\n"
        "    except Exception:\n"
        "        pass\n"               # swallows, and the turn continues UNARMED
    ).body[0]
    pred = lambda c: _called_name(c) == "arm_turn_surface"
    assert list(_unconditional_calls(fn.body, pred)) == []
    # ...and the other half: first position still counts.
    ok = ast.parse("async def p(c):\n    try:\n        arm_turn_surface()\n"
                   "    except Exception:\n        pass\n").body[0]
    assert len(list(_unconditional_calls(ok.body, pred))) == 1
```

Executed: **passes on the shipped rule, fails on the revert.** It writes no file into `app/`, so it
also does not reproduce the carried probe-module finding — unlike the six existing probe tests.
**There is no reason this does not exist. It is nine lines and the enumeration above found six
distinct shapes that would have carried it.**

# 2.2 · Item 3 of my section — the recorder hazard, **confirmed unfalsifiable, third round**

Re-executed independently on the frozen tree, one process, `contextvars.copy_context()`:

```
_O_K()                                       -> True    (a PASSING test at :2934 asserts this is True)
turn B, no recorder                          -> False   (the shipped test asserts False)
turn A's recorder, asked directly            -> True    (the shipped test asserts True)
catalogue_outage_registered(rec_a) in turn B -> True    (THE HAZARD — the composition never written)
```

**The two executions differ in no ContextVar. They differ only in a source comment** — `_O_K`'s says
*"same turn"*, the new test's says *"turn B"*. `_O_K` makes the exact call the carried test omits and
asserts it must be `True`; the delta's own comment calls that same result *"U-2's founding defect
verbatim"*. A test that drove the hazard would red a passing test. **Confirmed: unfalsifiable at
this seam.** The shipped test asserts around it, which is why it is green on 4 of 4 mutants that
break its stated subject.

### Exactly what V-LIVE would have to observe

Not "read the source again." A runtime observation, and it is small:

1. In `voice_stream_response`, stamp a **turn token** (a `uuid4`) into a ContextVar at
   `arm_turn_surface()` (`:242`-adjacent) and log `(token, id(recorder))` at the read site
   `voice_stream_service.py:422`.
2. Drive **three** shapes against a live gateway: (a) two concurrent voice requests for one session;
   (b) one request whose turn is re-entered (a retry / reconnect on the same task); (c) a request
   that records an outage and never arms (`O_J`).
3. **The question, in one sentence:** *does any `AdvertisedToolsRecorder` object id ever appear
   under two distinct turn tokens?*

* **If NO** — the design premise holds ("each request runs in its own task and therefore its own
  context copy"), `_O_K`'s assertion is right, the parameter is correct-by-construction for its one
  caller, and **A21-1/A21-2 close as non-defects.**
* **If YES** — `_O_K` asserts U-2's founding defect as the requirement, and the bound has to become a
  turn token on the recorder, which the design explicitly rejected.

Nothing in the source can decide it: the distinguishing input does not exist in the ContextVars.
**Third round carried. It is the only open item on this seam that more V-CODE cannot move.**

# 2.3 · Item 4 of my section — the three weak oracles, T11d, probe modules

**The three oracles are byte-identical**, `:3242`, `:3297`, `:3376`, all
`pytest.raises(AssertionError, match="withheld_tools")`. Re-measured, not asserted: inside the gated
test the two no-vacuity guards at **`:1697` and `:1701`** both carry `withheld_tools` in their
message, so the oracle is satisfied by a gate that fired for a reason unrelated to the probe.
R20-A's recommended phrase *"persists the column with no recorder-derived argument"* occurs
**exactly once** in the file — it is the assertion that should be matched.
**Reachability: production** — a one-token refactor at a live site makes two of them green over an
unmeasured probe. **Sixth round. It is three string literals.**

**T11d** (`stream_service.py:6297`): the matcher resolves the literal, not the constant; the file is
not in the delta. Carried, 4th. *(Read, not re-driven.)*

**Probe modules in the live tree**: 6 writers hardcode `parents[1] / "app"` (`:24`, `:3047`, `:3077`,
`:3230`, `:3279`, `:3308`) while `_TURN_SCOPE_ROOT = "app"` sits at `:2151`. Carried, 4th — and
**the census now performs the same class of mutation on the same tree, 68 times per run, on
purpose**, which is what made §0.5 cost 16 of 20 runs.

---

# 3 · TABLES

## 3.1 · Bypass table

| # | bypass | executed | result |
|---|---|---|---|
| B1 | run the census on the interpreter CI pins | ✅ ubuntu 3.12 | **rc=1, 26 drift lines, 0/13 rows recognised** |
| B2 | SIGKILL the census | ✅ | `contract.py:249` → `pass` |
| B3 | hard-crash inside the loop (`os._exit`) | ✅ | `contract.py:221` → `pass` |
| B4 | kill the census on Windows, any of 6 ways | ✅ ×6 | **0 reach the handler**; 3 real kills → 3 damaged trees |
| B5 | delete the `Refusal census` STEP, keep the job | ✅ N7 | gate test **GREEN** |
| B6 | replace the census command with `echo skip` | ✅ N8 | **GREEN** |
| B7 | run the census with `--write` (always regenerates ⇒ always rc=0) | ✅ N9 | **GREEN** |
| B8 | neuter the census's own selftest | ✅ N11 | **GREEN** |
| B9 | delete the whole signal-handler loop | ✅ N4 | **GREEN** — the comment satisfies the assertion |
| B10 | reword one C-12 message | ✅ 68/68 | row relocates; two false sentences |
| B11 | rename a function | ✅ 68/68 | all rows in it relocate |
| B12 | reorder two SILENT same-class siblings | ✅ 98 pairs | **CAUGHT 98/98** — closed |
| B13 | read the tree while a census runs | ✅ 20 runs | **16/20 RED** |
| B14 | revert W4's token | ✅ | **137 passed** |
| B15 | delete `canon.py:60` (an allowlisted "nothing checks it" line) | ✅ k≤2 sweep | silent alone; the pair reds → the line is **false as written** |

## 3.2 · Red-ability table — **my denominator**

| space | denominator | red-able |
|---|---|---|
| **A · the new gate test** — 12 enumerated defeat shapes over the workflow, the census and the allowlist | **12** | **7/12**. The 5 misses (N4, N7, N8, N9, N11) are all *"the census is absent, stubbed, self-regenerating or unproven"* |
| **B · the census as a kill-safe instrument** — 5 Linux kills + 6 Windows mechanisms | **11** | **5/11 survive cleanly** (Linux SIGINT/SIGTERM/exception + 2 Windows no-ops); 3 real Windows kills and 2 Linux hard kills damage the tree |
| **C · the allowlist's per-line claim** — all subsets of size ≤2 | **91** | **2/13 lines refuted**, 1 minimal red pair — identical to R21-A |
| **D · row-id stability** — 4 edit classes over all 68 sites | **68 × 4 = 272** | **2/4 classes correct** (reorder ✅ 98/98, reindent ✅ 0/68); 2/4 wrong (rename 68/68, reword 68/68) |
| **E · W4** — the one token | **1** | **0/1** shipped; **6/9** enumerated shapes would red it (§2.1) |
| **F · the carried recorder** — its stated subject | 4 semantic mutants (R21) | **0/4**, unchanged; the hazard re-executed live |

## 3.3 · Sibling table

| fix landed at | the sibling one token away | status |
|---|---|---|
| CI installs pytest (F3) | the **interpreter version** the ids are hashed on (F2) — each is the other's defect | **open**, A22-1/A22-2 |
| a test that the census's **deps** are installed (F5) | a test that the census **runs** — the precedent is in the same file | **open**, A22-4 |
| `atexit` + SIGINT/SIGTERM (F1) | SIGKILL, `os._exit`, and **all of Windows** | **open**, A22-3/A22-7 |
| `ambient.write_text` → `write_bytes` (`93af52373`) | `ALLOWLIST.write_text`, in the census's own file | **open**, A22-9 |
| the digest pins the row to the statement | it does not pin it to the **guarding context**; it does pin it to the **prose** | **open**, A22-6 |
| `Try` → `s.body[:1]` | `With`/`AsyncWith` → still `s.body`; a `With` inside a `Try` re-opens it | **open**, A21-5 |
| the **type** of the recorder | the **turn** of the recorder — what the comment promises | **open**, A21-2 |

## 3.4 · Guard table

| guard | exists | fires | fires for the right reason |
|---|---|---|---|
| census `--selftest`, both directions | ✅ | ✅ | ✅ — and it passes on 3.12 now |
| census restore on a completed run | ✅ | ✅ | ✅ (bytes, `SystemExit` not `assert`) |
| census restore on SIGINT/SIGTERM (POSIX) | ✅ | ✅ | ✅ |
| census restore on SIGKILL / `os._exit` | ❌ | — | — |
| census restore on **any** Windows external kill | ❌ | — | — |
| census next-run crash detector / lock | ❌ | — | — |
| census site-**set** comparison (a deleted refusal) | ❌ | — | — (still prints `NOW GUARDED … good news`) |
| census row id stable across interpreters | ❌ | job reds every run | ❌ |
| census row id stable across a reword / rename | ❌ | reds with two false sentences | ❌ |
| census row id stable across a reorder | ✅ | ✅ | ✅ **98/98 — closed** |
| a test that the census **runs** in CI | ❌ | — | — |
| a test that the census's deps install | ✅ | ✅ | ✅ |
| `'SIGTERM' in src` | ✅ | only on a full-file rewrite | ❌ — a comment satisfies it |
| `timeout-minutes` on the census job | ❌ | — | — |
| W4 rule test | ❌ | — | — (6 shapes available, §2.1) |
| terminal-write probe oracles ×3 | ✅ | ✅ | ❌ **6th round** |
| recorder **turn** bound | ❌ | — | — |

## 3.5 · Reachability verdict on every finding

| finding | reachable? |
|---|---|
| A22-1 id not version-stable | **CERTAIN** — CI reds on every push; 0/68 ids portable |
| A22-2 job cannot be green | **CERTAIN** — executed on the pinned interpreter |
| A22-3 Windows kills uncovered | **CERTAIN** — 3 real kills, 3 damaged trees, 1 on a SILENT site |
| A22-4 gate asserts install, not run | **CERTAIN** — one line of YAML; 4 green bypasses |
| A22-5 assertion satisfied by a comment | **gate coverage, false GREEN** |
| A22-6 reword/rename relocate rows | **process, frequent** — two false sentences each time |
| A22-7 no next-run crash detector | **CERTAIN** — ~1 kill in 5 lands invisible |
| A22-8 concurrency 16/20 | **CERTAIN, and it has already happened twice in this run** |
| A22-9 `ALLOWLIST.write_text` | **LOW** — `.gitattributes` normalises at commit |
| A21-1/2 carried recorder | **LATENT** — unreachable via the only wired caller; **whether it is a defect is the V-LIVE question**, §2.2 |
| A21-3 exact-type bound | **none today** — no subclass, no reload, no mock |
| A21-4 W4 untested | **gate coverage** — the rule can drift either way unnoticed; **6/9 shapes would red it** |
| A21-5 `With`-in-`Try` residue | **gate coverage, false GREEN** |
| A21-6 weak oracles | **production** — a one-token refactor at a live site |
| T11d / probe modules / `:531`–`:542` | as recorded in R19–R21; **untouched** |

---

# 4 · EXECUTED vs ARGUED

**42 load-bearing claims. 34 executed, 8 argued. Ratio 34 : 8 — 81 %.**

Every execution ran over an **enumerated** or **exhaustive** space:

| space | denominator | complete over |
|---|---|---|
| kill matrix | 5 Linux + 6 Windows mechanisms | every kill primitive available on each platform |
| id stability | 68 sites × 4 edit classes; 98 sibling pairs | every `raise` in the package; every same-class same-function pair |
| cross-interpreter portability | 68 × 2 interpreters | every site, 3.12 vs 3.13 |
| allowlist honesty | **91 subsets** (13 + 78) | all subsets of size ≤ 2 of the 13 |
| gate-test red-ability | 12 defeat shapes | workflow × census × allowlist |
| W4 | **9 shapes** | 3 arm positions × 3 `try` tails, both rule variants |
| concurrency | 20 runs + 3 controls | — |
| CI job | 2 steps | the job's own steps, on its pinned interpreter |

Suite invocations: **91** membrane runs for the subset sweep, **20 + 3** for concurrency, **12** for
the mutants, **~136** inside 2 full census runs on Linux and ~5 partial ones, **2** whole-file
`test_cp0_instrument.py` runs (137 each), **1** whole chat-service suite (2270), **1** full CI-shape
census.

**The 8 argued claims, named so they can be attacked:**

1. WSL Ubuntu + CPython 3.12.3 ≈ `ubuntu-latest` + `setup-python@v7` `3.12`. Close, not the runner.
2. **The Windows SIGINT path is UNVERIFIED** — my `AttachConsole` delivery failed twice; I am not
   claiming Ctrl-C is broken, only that no programmatic kill reaches the handler.
3. The site-**inventory** defect (a deleted refusal prints `NOW GUARDED … good news`) — read from
   `agentruntime-census.py:238-244`, not re-executed. *Indirect evidence: the CI-shape run emitted
   that exact message for 13 sites nothing had guarded.*
4. "Guarded by a same-class sibling" is mechanically decidable at ~6 extra runs — a design argument.
5. "Dead / unreachable" is **not** mechanically decidable — a design argument.
6. Running the census in a `git worktree` closes A22-7, A22-8 and the probe-module finding — a design
   argument; not built.
7. A reindent that moves a `raise` between blocks would red the selftest before the id question
   arises — reasoned, not executed.
8. T11d is unchanged — read from the diff, not re-driven.

**And the standing caveat R21-A paid three cycles for, which I paid nothing for only because he
wrote it down:** an execution is only as frozen as its tree. Every number above came from a scratch
tree; the one time I ran a suite and a census in the same tree on purpose, **16 of 20 runs lied.**

---

# 5 · CONVERGENCE

**Raw.** Eight load-bearing claims in scope (§1). **Closed: 2** (D4; and D2's reorder half, which is
complete and provable). **Refuted: 3** (D3, D5, D8). **Half: 2** (D1, D2). **Carried unfalsifiable:
1** (D7).

**Findings introduced by this delta: 8** (A22-1 … A22-8; A22-9 is a sibling miss I am ranking as
low). **Findings closed by this delta: 1** — R21-A's Case B, the silent-staleness-on-reorder, closed
completely at 98/98. R21-A §0.5b (the install step) is also genuinely fixed, but it was the *first*
half of a two-part failure whose *second* half the same delta created, so I am not counting it as a
closure.

**The series, raw:** `2,1,2,1,3,2,4,3,2,2,2,5,13,` **`8`**.

**The series carries no signal and this round proves it again.** R21's 13 was 9 census findings on a
brand-new artefact; my 8 is 8 census findings on the *same* artefact one revision later. What moved
is the **polarity** and the **shape**, and both are worse in the way that matters:

* **The delta's five fixes are 2 clean, 2 half, 1 sibling.** The two halves (F1, F2) each fixed the
  case a verifier *named* and left the case one token over — Windows for F1, the interpreter and the
  message for F2. **That is the run's most-repeated failure, and this is instance nine.**
* **F2 and F3 are each other's defect.** Two fixes from one verdict, landed in one commit, and their
  interaction was never run. The commit message for F3 narrates that exact failure as the reason F3
  exists.
* **The census's own red-ability is 7/12**, and every one of the 5 misses leaves the instrument
  *absent or vacuous* while the gate is green. The instrument built to end vacuous gates is, by its
  own test, defeatable by deleting the step that runs it.

**On the termination question.** R21-A said he would support closing CP-1 against the census once
the five fixes landed. **They landed and I cannot support it yet, on the same criterion he stated.**
His condition was that the census *runs* — and executed on the interpreter CI pins, it exits 1 with
26 false drift lines and **0 of 13** allowlist rows recognised. Closing against it today would
define "closed" in terms of a file the gate itself instructs you to delete.

**But the distance is now small and I want to be precise about it, because "not yet" for a
twenty-third round is its own failure mode.** Four changes, none over ten lines:

1. **`ast.unparse` instead of `ast.dump`** in the digest, and regenerate. Closes A22-1 and A22-2 and
   makes the job green. *This one is the whole blocker.*
2. **Assert the census RUNS**: `assert "run: python scripts/agentruntime-census.py" in job` — and
   drop the `'SIGTERM' in src` substring assertion, which a comment satisfies. Closes A22-4, A22-5.
3. **Run in a `git worktree`.** Closes A22-7, A22-8, and the 4-round-old probe-module finding.
4. **Fix the allowlist header sentence** to what was measured. Closes 2 of 13 false lines at a
   stroke, and it is the only fix on this list that makes the *claim* smaller rather than the code
   bigger.

With those four, the census measures what it says, runs where it must, and cannot be defeated by
deleting a step. **I would support closing CP-1 against it at that point**, and I am recording the
condition in executable terms so the next round is a check and not a debate.

**Carried into whatever comes next, in priority order:**

1. The four census changes above.
2. **The V-LIVE question, third round** (§2.2) — three probes, one sentence, and no amount of source
   reading will settle it. `_O_K` currently *asserts* one answer while the delta's comment *assumes*
   the other.
3. **Write W4's test** — §2.1 has it, executed, 9 lines, 6/9 shapes available. Sixth round at 0/1.
4. **Fix the three weak oracles** — three string literals. Sixth round.
5. **Narrow `With` the way `Try` was narrowed**, or say in the docstring why they differ.
6. **Point the probe writers at `_TURN_SCOPE_ROOT`** — 4th round, and now urgent for the same reason
   the census is: the live tree is being mutated by two mechanisms.
7. **Resolve `:531` vs `:542`** — 8th round. One of the two sentences is false.

---

`git rev-parse HEAD` **at finish**: `c37459826de3c410654123e7351200afcccc8085` — **unmoved.**
`git status --porcelain -- services/ scripts/ contracts/ .github/` at finish: **empty.**
No tracked file was written except this verdict. No `git checkout` was used; every patch was applied
in a scratch tree and restored from my own byte snapshot with an equality assert.
