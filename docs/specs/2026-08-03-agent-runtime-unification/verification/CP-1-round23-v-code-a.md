# CP-1 · round 23 · V-CODE · Verifier A — the instrument

`git rev-parse HEAD` **at start**: `9b77caed789e9f2737f849d63b1485a65bcbd8a4`
Graded delta: `bc1452f4c`, diffed against `c37459826`. `bc1452f4c..HEAD` is **docs only**
(the RUNSTATE plus this round's prompt), so the artifact under test is the delta.

**Method.** Every mutation ran in a **throwaway copy of the tracked tree**, built by calling the
census's own `_mirror()`. Every file was restored from **my own byte snapshot with an equality
assert**. No `git checkout`. No tracked file was written except this verdict. Baselines: the live
working tree was `git status --porcelain` **empty** at start, after the full census, after the
eight-kill matrix, and at finish.

**One contamination event, recorded because it is evidence.** Mid-round, the live tracked file
`contracts/agentruntime-census-silent.txt` was observed with all thirteen digests replaced by
`deadbeef`, and clean again on the next poll. **I did not write it** — every allowlist mutation I
performed was inside a mirror, and I hold the snapshots. It is a concurrent verifier patching the
live tree. None of my numbers were taken during that window (my k≤2 sweep resolved **13/13** rows and
my census runs completed before it), but R22-A's standing caveat now has a second instance:
*an execution is only as frozen as its tree.*

---

# 0 · THE CENSUS VERDICT

> R22-A named the distance to supporting closure as **four ≤10-line changes**. All four shipped.
> This is the grading of those four, and nothing here rests on the builder's own evidence.

## **Verdict: three of the four are fully real, the fourth is real in substance and comment-defeatable in form. The census now produces a correct, reproducible, version-portable answer, and it exits 0.**

| R22-A condition | shipped? | verdict |
|---|---|---|
| 1 · `ast.unparse` instead of `ast.dump`, and regenerate | ✅ | **TRUE** — 68/68 ids identical across 3.12/3.13, **13/13** allowlist rows resolvable under the pinned interpreter, census **rc=0** |
| 2 · assert the census **RUNS**; drop the comment-satisfiable substring | ✅ | **HALF** — N7/N8/N9 all closed, **measured**; and the replacement assertion is satisfied by a YAML `#` comment, **measured** |
| 3 · run out of the live tree | ✅ | **TRUE** — **8 of 8** kill mechanisms leave the tree byte-identical; **20 of 20** concurrent suite runs green |
| 4 · fix the allowlist header to what was measured | ✅ | **TRUE** — exhaustive k≤2 over 91 subsets: the new sentence is true of **13/13** rows |

**The headline number.** The census, run to completion on the live tree at the frozen commit:

```
agentruntime-census selftest OK - 68 raise sites, fires on a guarded one
agentruntime-census: 68 sites, 13 silent, 55 red
CENSUS_RC=0
```

**Zero `NEWLY SILENT` lines. Zero `NOW GUARDED` lines.** The 8 files of `app/agentruntime/` were
SHA-256-identical to my pre-run snapshot afterwards, and `git status --porcelain` was empty.
R22-A's A22-1 and A22-2 — *the whole blocker* — are **closed by execution**.

Two independent convergences before the defects:

* **Third harness, same members.** Exhaustive k≤2 over the 13 allowlist rows, **91 subsets**
  (13 + 78), run in a mirror: **0/13 red alone**, **exactly one** minimal red pair
  `{canon::_norm::…::1::50f6dc36, canon::_norm::…::4::1598291a}`, **2 of 13 rows implicated**.
  R21-A got this, R22-A reproduced it, and I reproduce it a third time **to the member**, on a
  different harness, against a *different digest scheme*. This is the only measurement in
  twenty-three rounds with that property.
* **R21-A's Case B is still closed.** Of the **6** same-key pairs where *both* members are
  allowlisted SILENT — the only pairs where a reorder can go silently stale — **0 collide** under
  the new digest. Enumerated, not sampled.

---

## 0.1 · Item 1 — "it no longer writes into the live tree". **Killed eight ways. 8/8 clean.**

The claim is now structural rather than defensive: `census()` neuters `mirror/…` and never touches
`PKG`. I did not take that on reading. Each run below was the **shipped script executed as
`__main__`**, allowed to enter the neutering loop (confirmed by its first `-v` site line), then
killed; the live tree was re-hashed after each.

| # | kill mechanism (Windows) | live tree afterwards |
|---|---|---|
| 1 | `kill -INT` (git-bash) | **UNCHANGED**, `git status` empty |
| 2 | `kill -TERM` | **UNCHANGED** |
| 3 | `kill -9` (the `SIGKILL` equivalent; no handler, no `atexit`) | **UNCHANGED** |
| 4 | `taskkill /PID` (WM_CLOSE) | **UNCHANGED** |
| 5 | `taskkill /F /PID` (`TerminateProcess`) | **UNCHANGED** |
| 6 | `taskkill /F /T /PID` (whole process tree, incl. the child pytest) | **UNCHANGED** |
| 7 | `Stop-Process -Id` | **UNCHANGED** |
| 8 | `Stop-Process -Id -Force` | **UNCHANGED** |
| — | **a full run to completion** | **UNCHANGED**, 8/8 files SHA-256-identical |

R22-A measured *six external kill mechanisms, zero reaching the handler, three real kills, three
damaged trees, one on an allowlisted SILENT site.* **That entire finding class is gone, and gone the
right way — by deleting the write, not by adding a handler.** Twenty-four lines of signal handling
went with it. A22-3 and A22-7 are **closed by removal**; there is nothing left to detect on the next
run.

**The interference claim, verified rather than accepted.** Twenty membrane-suite runs in the live
tree, sequentially, while a real census ran to completion:

| | result |
|---|---|
| R22-A, before the mirror | **16 of 20 RED** |
| **this round, during a live census** | **20 of 20 GREEN** (`136 passed` each) |

A22-8 is **closed, measured over the same denominator**.

**I tested the other direction too, and my own hypothesis was refuted.** `_selftest` still runs the
membrane suite in the **live** `services/chat-service`, and `test_cp0_instrument.py`'s six probe
writers still write `_lwprobe_*.py` into the live `app/agentruntime/`, `app/routers/` and
`app/services/`. I expected that to red the census's live selftest. Executed in a mirror, all three
probe locations: **membrane suite green in 3 of 3.** The reverse interference does **not** exist.
Recorded as a refuted prediction of mine, because a verifier reporting a false finding is the same
failure as a builder reporting a false fix.

### What the mirror does NOT reproduce — enumerated, and one correction of my own

`git ls-files -z` → `shutil.copyfile` for every `src.is_file()`.

| not reproduced | present in this repo today? | consequence |
|---|---|---|
| **`.git`** | — | `git rev-parse HEAD` inside the mirror → rc 128. **No test in the membrane suite runs git**, so zero effect today; a future git-touching test would fail *inside the census only* |
| **untracked files** | 0 right now | a brand-new, unstaged guard test is invisible to the census; `git add` puts it back in scope, and this is a pre-commit gate, so the window is narrow |
| **ignored paths** (253 top-level entries) | many | none — the suite runs on the ambient interpreter's site-packages |
| **file modes** (`copyfile` copies content only) | **25 tracked `100755` files** | POSIX exec bits lost in the mirror. Nothing in the membrane suite execs a file. **Latent** |
| **symlinks / gitlinks** (`is_file()` skips a symlink-to-dir and a submodule) | **0** — modes are `{100644: 13554, 100755: 25}`, no `120000`, no `160000`, no `.gitmodules` | **latent only** |
| **a tracked path deleted in the worktree** | 0 | silently omitted; the mirror would then match neither HEAD nor the index |
| **the index** | — | documented and deliberate: it copies **worktree** bytes, which is the right choice for a pre-commit gate |

> **Correction of my own harness.** My first pass reported *"20 tracked paths silently skipped"*.
> That was **my** bug, not the census's: I enumerated with `git ls-files` (which C-quotes the twenty
> CJK filenames under `lore-enrichment-service`) instead of `git ls-files -z` (which does not).
> Direct count settles it: **13 579 tracked paths → 13 579 files copied, 0 skipped.**

### Two things the mirror bought, and one it did not

**A23-6 · the mirror is never removed.** `tempfile.mkdtemp` at `scripts/agentruntime-census.py:86`;
there is no `rmtree`, no `TemporaryDirectory`, no `finally`, anywhere in the file — grepped.
`_selftest()` builds one and `census()` builds another, so **every run leaks two full copies of the
repository**: measured at **13 579 files / 214 MB / 44.7 s each**. I counted **37 on disk at
6.71 GB** before cleaning up. Reachability: **CERTAIN and unbounded** for the documented pre-commit
use; survivable but wasteful for one CI run. Fix: `TemporaryDirectory` or one `rmtree` in a
`finally`. Cost of the copy is also the run's new floor — ~90 s of pure I/O per invocation.

**A23-5 · the selftest's positive control is in the LIVE tree and its negative control is in the
MIRROR — so nothing asserts the unmodified mirror is green.** `_selftest()`:

* `:235` `if not _suite_is_green():` — **live tree**, no `cwd`.
* `:239–250` builds a mirror, neuters `contract.py::check_row_shape`, and asserts the suite goes red
  **in the mirror**.

If the mirror is ever unusable — a needed untracked file, a git-dependent test, a lost exec bit, a
long-path failure on Windows — the probe run goes red *for that reason*, `fired` is `True`, and the
**selftest passes**. `census()` then measures 68 sites against a broken tree, reads **68 RED**, and
prints thirteen `NOW GUARDED … good news: drop it from the allowlist in the same change` lines.
**That is R22's failure mode verbatim, relocated one layer down: a plausible lie instead of an
obvious break.** A check whose control and seed can agree is theatre.

I verified today's mirror *is* green — `136 passed` in an unmodified mirror — so the defect is
**latent, not live.** The fix is one line before the probe:

```python
if not _suite_is_green(mirror / _CS_REL):
    print("SELFTEST FAIL: the MIRROR is not green before any injection; the copy is incomplete")
    return 1
```

Without it the selftest cannot distinguish *"the probe fired"* from *"the mirror is broken"*, which
are the only two hypotheses it exists to separate.

---

## 0.2 · Item 2 — the digest. **Re-enumerated, 68 × 4. Two of four fixed; the docstring's own number is now false.**

Every edit class applied to **every one of the 68 sites** and the row-id set recomputed from the
census's own `_sites`. No hand-picked cases.

| edit | *should* it move a row? | *does* it? | denominator | R22 (`ast.dump`) |
|---|---|---|---|---|
| **reword** a message | **NO** | **NO — 0/68** ✅ | 68 | 68/68 ❌ |
| **reindent** a raise | **NO** | **NO — 0/68** ✅ | 68 | 0/68 ✅ |
| **rename** the enclosing function | it *is* the id's prefix — so **yes, and visibly** | **YES — 68/68**, via the prefix, not the digest | 68 | 68/68 |
| **reorder** two same-class same-function raises | **YES** | **94/98 pairs** — **4 collisions** | 98 pairs | 98/98, 0 collisions |

**A22-6 is closed: 0/68.** The pure-reword false-sentence pair is gone. This was the change with the
widest process cost — every refusal in this package carries a paragraph under active revision — and
it is genuinely fixed.

**A23-7 · but the docstring at `scripts/agentruntime-census.py:116` states, of the shipped digest:**
*"reordering two raises should move a row and does (98/98 pairs, 0 collisions — the one thing the
ordinal could not do)"*. **That number was measured on `ast.dump` and is false of `ast.unparse` with
strings blanked.** Measured on what shipped: **94/98, four collisions**, and here they are:

| collision | allowlisted? |
|---|---|
| `canon.py:60` ↔ `:80` (`_norm::NotCanonicalisable`) | **True / False** |
| `contract.py:368` ↔ `:374` (`check_contract::ContractViolation`) | False / False |
| `surface.py:302` ↔ `:318` (`OrderBy.__post_init__::ValueError`) | False / False |
| `surface.py:389` ↔ `:391` (`TakeWhileBudget.__post_init__::ValueError`) | **True / False** |

Each is a pair of same-class raises in one function differing **only in the message string**, which
the digest blanks by design.

**Reachability of the *defect*: LATENT.** The staleness Case B names requires a colliding pair whose
members are **both SILENT**; the census re-measures silence every run, so a collision between a
SILENT and a RED site still surfaces as one row flipping. I enumerated the 6 both-SILENT same-key
pairs: **0 of 6 collide.** It becomes live the moment a second member of a colliding pair goes
silent. **Reachability of the *claim*: CERTAIN and it is already false** — a self-measurement carried
forward unchanged onto a rewritten mechanism, which is the record's fifth instance of a number wrong
in the flattering direction.

### "A digest blind to prose is also blind to a message that changes what the refusal means"

**It matters, and it is acceptable — but not for the reason the docstring gives.** Three points, in
order of how much they cost:

1. **For the census's stated question it is exactly right.** The question is *"does the suite notice
   this check is gone"*, and removal-detection does not depend on wording. Pinning the row to the
   prose is what produced 13 relocations and 26 false sentences last round.
2. **It is not free.** A message rewritten from *"unsupported"* to *"not yet implemented"* changes
   what a caller may conclude, and the census's row does not move. That is inside the docstring's
   own *"what it does NOT do"* fence, and if a test asserts on the message the **suite** reds — a
   different guard, and the right one.
3. **The sharp edge is the collision, not the reword.** For the four pairs above, **swapping the two
   messages between the two branches** — the wrong refusal text on the wrong condition — produces a
   byte-identical id set *and* an identical SILENT/RED split. It is invisible to this instrument, by
   construction, and no reasonable version of this instrument would catch it. That should be one
   sentence in the docstring where *"0 collisions"* currently is.

---

## 0.3 · Item 3 — version stability. **The defect that printed a plausible lie is CLOSED.**

`_sites` run under three interpreters against the frozen package:

| comparison | R22 (`ast.dump`) | **this round (`ast.unparse`, strings blanked)** |
|---|---|---|
| ids identical 3.12 ↔ 3.13 | **0 of 68** | **68 of 68**, and in the same **order** |
| allowlist rows resolvable under 3.13 | 13/13 | **13/13** |
| allowlist rows resolvable under **3.12 — the CI pin** | **0/13** | **13/13** |

**A23-8 · and one new boundary, executed.** Under **CPython 3.11.14**, `_shape_digest` raises

```
ValueError: Unable to avoid backslash in f-string expression part
```

from `ast.unparse` on this package — the whole census dies with a traceback before printing
anything. `ast.unparse` is total only from 3.12 (PEP 701 lifted the f-string backslash restriction).
**Reachability: NONE in CI** (`setup-python@v7` pinned to `3.12`, and I read the job); **CERTAIN for
a developer on ≤3.11** running the documented pre-commit gate. One line of docstring, or a
`sys.version_info` guard in `_selftest`, closes it. I am ranking it low and recording it because the
previous version of this exact function shipped with an unmeasured interpreter assumption.

**What I could NOT execute, stated plainly.** I could not run the census end-to-end on 3.12: my
local 3.12 has `pytest` but not `json_repair`, so `conftest.py` fails to import and the census
correctly printed `SELFTEST FAIL: the suite is not green before any injection`, rc=1. That is my
environment, not the artifact — and it is worth noting that **the selftest refused rather than
producing 68 plausible rows**, which is the property R22-A said was missing. So:

* **EXECUTED:** the ids are identical on 3.12 and 3.13, and all 13 allowlist rows resolve on both.
  This is the entirety of A22-1 and it is closed.
* **ARGUED:** that the RED/SILENT *split* is also identical on `ubuntu-latest` + 3.12 with CI-
  installed deps. The split is decided by the suite's assertions, not by the interpreter's AST
  repr, so I expect it to hold — but I did not run it and I am not claiming it.

---

## 0.4 · Item 4 — "the CI test now asserts the census RUNS". **20 defeat shapes enumerated. 9 caught.**

Every shape was applied in a mirror and the single test run; the tree was restored from bytes and
re-verified green between each. **My denominator is 20**: R22-A's 12, minus 3 rendered moot by the
delta (the `SIGTERM` loop, the `assert`→`SystemExit` guard, the `atexit` direction — all inverted or
deleted), plus 11 I added by asking *"what else keeps the string and kills the check?"*

| # | defeat shape | gate test |
|---|---|---|
| N1 | drop `-r requirements-test.txt` | **RED** ✅ |
| N2 | delete the whole `agentruntime-census:` job | **RED** ✅ |
| N3 | re-add an `atexit.register` live-tree restore | **RED** ✅ |
| N6 | strip the digests from every allowlist row | **RED** ✅ |
| N10 | empty the allowlist of every row | **RED** ✅ |
| **N7** | **delete the `Refusal census` step, keep the job** | **RED** ✅ *(was GREEN in R22)* |
| **N8** | **replace the command with `echo skip`** | **RED** ✅ *(was GREEN)* |
| **N9** | **run the census with `--write`** | **RED** ✅ *(was GREEN)* |
| **N13** | **`census()` neuters the LIVE package again (`PKG.glob`)** | **RED** ✅ |
| N11 | neuter the census's own selftest (`return 0`) | **GREEN** ❌ *(unchanged, 2nd round)* |
| N12 | census never restores **inside the mirror** | **GREEN** ❌ *(**regressed** — was RED in R22)* |
| **N14** | **`census()` neuters the LIVE package, spelled `(ROOT / _PKG_REL).glob`** | **GREEN** ❌ |
| **N23** | **mirror built, then discarded: `pkg, cs = PKG, CS`** | **GREEN** ❌ |
| **N16** | **delete `_mirror()` entirely, leave its name in a comment** | **GREEN** ❌ |
| **N17** | **run it with `--selftest` only — never compares against the allowlist** | **GREEN** ❌ |
| **N18** | **append `\|\| true`** | **GREEN** ❌ |
| **N19** | **add `continue-on-error: true`** | **GREEN** ❌ |
| **N20** | **add `if: false`** | **GREEN** ❌ |
| **N21** | **delete the step, leave the command in a YAML `#` comment** | **GREEN** ❌ |
| **N22** | **delete the step, put the string in an unrelated later job** | **GREEN** ❌ |

**9 of 20.** Three of R22-A's five named misses are genuinely closed, and that is real work. What
replaced them:

**A23-1 · The assertion written to replace one a comment satisfied is satisfied by a comment.** The
test's own comment reads: *"`assert 'SIGTERM' in src` WAS SATISFIED BY A COMMENT … Match the call,
not the topic."* Ten lines later:

```python
assert 'python scripts/agentruntime-census.py' in job, (...)
```

`job` is `wf.split('agentruntime-census:')[1]` — raw YAML text to end of file. **N21: delete the
step, leave `      # run: python scripts/agentruntime-census.py`. GREEN.** And **N22: the string in
any job *below* it. GREEN** — today the census job is last, so `[1]` is the job; add one job after it
and its body joins the slice. `test_cp1_membrane.py:2141`.

**A23-4 · `assert "_mirror" in src` is the same defect, in the same expression.** **N16: delete the
whole `_mirror()` function, restore live-tree neutering, leave `# the _mirror helper was deleted` in
its place. GREEN.** The comment three lines above says *"Match the call, not the topic"* — and the
assertion matches the topic. `test_cp1_membrane.py:2159`.

**A23-3 · The delta's headline property is guarded by a spelling.**

```python
_census_body = src.split("def census")[1].split(chr(10) + "def ")[0]
assert "PKG.glob" not in _census_body
```

`PKG.glob` is caught (**N13 RED**). The **same live path**, spelled `(ROOT / _PKG_REL).glob("*.py")`,
is **N14 GREEN**; and simply assigning `pkg, cs = PKG, CS` after building and discarding the mirror
is **N23 GREEN**. Both neuter tracked production files under every kill in §0.1, with the gate green.
**"The instrument stops writing into its subject" is asserted by a substring, in the test that
convicts substrings.** `test_cp1_membrane.py:2168`.

**A23-2 · The `--write` blocklist is one flag long.** `assert '--write' not in job` closes exactly
the bypass R22-A named. Its four siblings — `--selftest` (runs the selftest and *never compares
against the allowlist*), `|| true`, `continue-on-error: true`, `if: false` — are **N17–N20, all
GREEN**. The fix enumerated the token the verifier wrote down and left the four one token over.
`test_cp1_membrane.py:2144`.

**All five misses that matter are the same shape as the five R22-A found, and four of them are inside
the assertions written to fix those five.** That is instance ten.

### The change that closes N17–N23 at once, and cannot be satisfied by a comment

```python
import yaml
job = yaml.safe_load(wf)["jobs"]["agentruntime-census"]
step = next(s for s in job["steps"] if s.get("run", "").strip()
            == "python scripts/agentruntime-census.py")
assert "if" not in step and not step.get("continue-on-error")
```

A parse cannot be satisfied by a comment, by a later job, by a trailing `|| true`, or by an extra
flag — the `run` must be *exactly* the command. And for A23-3, replace the substring with the
behaviour: monkeypatch `_mirror` to a tmp copy, call `census()`, assert the live package's bytes are
unchanged. Roughly eight lines together, and they turn 11 of my 11 misses into 2.

---

## 0.5 · Item 5 — the allowlist header. **True of 13 of 13. PASS.**

The old sentence — *"Every line is a claim that nothing checks"* — was refuted for 2 rows by two
verifiers asking two different questions. The new one claims exactly what the experiment does:
*"Refusal sites the suite does not notice being removed **ON THEIR OWN**"*, with a paragraph naming
the two reasons a row can be there (a same-class sibling reds first; the site is unreachable) and
saying the disposition still needs a person and a verdict id.

Exhaustive sweep in a mirror, **91 subsets**:

| k | subsets | RED | what it says about the header |
|---|---|---|---|
| 1 | 13 | **0** | **the new sentence is TRUE for 13 of 13 rows** |
| 2 | 78 | **1** — `{canon::_norm::…::1, canon::_norm::…::4}` | the **old** sentence stays false for 2 rows; the new one is untouched, because it says *alone* |
| **total** | **91** | **1 minimal pair** | |

**This is the only fix on R22-A's list that made the claim smaller instead of the code bigger, and it
is the one with the cleanest verdict.** The header now cannot be refuted by asking a different
question, because it states its own experiment. I also verified the **generator emits byte-identical
header text to the committed file**, so `--write` will not churn it.

**Carried, ranked LOW, 2nd round:** `ALLOWLIST.write_text` at `:280`, in a script whose docstring
opens *"It reads and writes BYTES."* `git ls-files --eol` still reads `i/lf w/crlf`;
`.gitattributes` normalises at commit, so it produces no committed diff. A22-9, unchanged.

---

# 1 · THE TWO DESIGNS R22-B PRODUCED — **grade the design, not the intention**

I am saying this now rather than after it ships, because the prompt is right that the last three
instruments in this run were shipped and then found to be measuring something adjacent.

## 1.1 · `effect ∈ {accepts, refuses-differently, no-observable-change}` — **NOT computable from what pytest already reports. Do not build it as specified.**

The census's only probe is *"is the existing suite green"*, and it reads exactly one bit of pytest:
the return code. Take the three labels in turn.

* On a **RED** site, pytest reports which tests failed and why, so a crude `refuses-differently`
  could be inferred from the failure repr. **But RED sites are not the ones anybody needs
  explained.**
* On a **SILENT** site — the 13 rows the column exists for — **pytest reports nothing at all.** Every
  test passes. `accepts` and `no-observable-change` are precisely the two hypotheses that produce an
  identical, empty observation. Distinguishing them needs an input that reaches the site; and if the
  suite contained such an input, the site would be RED, not SILENT.

**The design is informative exactly where it is unnecessary and silent exactly where it is needed.**
That is the same inversion as a coverage number that counts the lines you already trust.

**What IS computable, from a measurement the census can already afford.** Run the baseline suite
once under `coverage.py` with branch arcs and read the site's own line:

| label | mechanically decided by | cost |
|---|---|---|
| `NEVER-EXECUTED` | the `raise`'s line has **no** hit in the coverage data | **one** instrumented baseline run |
| `EXECUTED-AND-STILL-GREEN` | the line **is** hit, and neutering it alone keeps the suite green — the suite reaches the refusal and asserts nothing about it | free, the census already has it |
| `MASKED-BY <sibling id>` | the k=2 sweep over same-class same-function pairs | **6** extra suite runs on today's package (98 pairs exist; only 6 have both members allowlisted) |

All three are facts, all three come out of pytest and `coverage json`, and together they answer the
question `effect` was reaching for — *why is this row here* — without asking pytest for a signal it
does not emit. I would build this instead, and I would build the 6-run pair sweep first: it is the
cheapest, and it is the half R22-A already proved decidable.

## 1.2 · `static ∈ {reachable, unreachable-handler}` — **NOT decidable here. Do not build it as specified.**

`manifest.py::validate_document::UntrustedRow::6` is an `except UntrustedRow` arm whose only callee
raises `ContractViolation` **today**. Calling that `unreachable-handler` is a whole-program claim
over a Python call graph — duck typing, `getattr` dispatch, decorators, and test-time monkeypatching
all defeat it. Worse, it fails in the **safe-looking** direction: a row labelled `unreachable-handler`
stops being questioned, and the label goes stale silently the first time a callee grows a new
`raise`. That is the dead-field failure this package convicted `Identity` for.

**There is a decidable sub-case, and it should be the entire scope if anything ships:**

> **`NO-LOCAL-RAISER`** — no `raise E` (nor a subclass of `E`) occurs anywhere in the package, over
> the same 68-site enumeration the census already computes.

That is purely syntactic, package-local, and free. It is a **necessary** condition for
unreachability, never a sufficient one — and the name must say that. `unreachable-handler` is a
judgement wearing a mechanical name, and this run has now convicted three instruments for exactly
that substitution.

**And one rule without which either design is decoration**, which R22-A stated and I endorse
unchanged: **a row whose static column asserts unreachability, and which the census can red by
neutering it alone, is a contradiction and must fail the build.** That is the only line that makes
the label falsifiable. Add two more: reject a column entry on a row id the census did not itself
emit, and reject a `MASKED-BY` pointing at a site id that no longer exists.

---

# 2 · OVERALL VERDICT

## **PASS** — the graded delta is real. 9 findings introduced, **6 closed**, and **not one of the 9 makes the census produce a wrong answer today.**

This is the first delta in this run whose fixes I can certify by execution end to end. The four
changes were four ≤10-line changes and three of them are simply true. The instrument now:

* exits **0** on the frozen tree, with **zero** drift lines;
* survives **8 of 8** kill mechanisms with the tree byte-identical;
* leaves **20 of 20** concurrent suite runs green, against 16-of-20 red one revision ago;
* produces **identical ids on both interpreters in play**, with **13/13** allowlist rows resolvable
  under the CI pin;
* and carries a header sentence that is **true of 13 of 13 rows** under an exhaustive 91-subset
  sweep.

What is left is a **guard problem, not a measurement problem**: the gate test around the census can
be defeated eleven ways out of twenty, and five of those leave the census absent, stubbed, unproven
or writing into the live tree again. That is worth fixing and it does not make today's number wrong.

## 2.1 · Falsifier per claim

| claim (builder's, from the commit and the comments) | falsifier | verdict |
|---|---|---|
| D1 "the census never writes into the live one" | a kill, or a completed run, that leaves the tree changed | **TRUE** — 8 kill mechanisms + 1 full run, 9/9 byte-identical |
| D2 "it ends its interference with concurrent suite runs (16 of 20 went red)" | a red concurrent run | **TRUE** — 20/20 green, same denominator |
| D3 "the digest is stable across interpreters" | one id differing on 3.12 vs 3.13 | **TRUE** — 68/68, same order; 13/13 rows resolvable on both |
| D4 "a reworded message keeps its row" | a reword that moves a row | **TRUE** — 0/68 |
| D5 "reordering two raises should move a row and does (98/98 pairs, **0 collisions**)" | a same-key pair the digest cannot tell apart | **FALSE as written** — **94/98, 4 collisions**; the number was measured on the *previous* digest. **Defect latent**: 0 of the 6 both-SILENT pairs collide, so Case B stays closed |
| D6 "Both halves are asserted now" (the census RUNS, and not `--write`) | a workflow where the census does not run and the test is green | **FALSE** — N17, N18, N19, N20, N21, N22 all GREEN |
| D7 "the census writes neutered source into the LIVE tree … it must work in a throwaway mirror" — *as a **gate*** | a census that neuters the live tree with the test green | **FALSE as a gate** — N14 and N23 GREEN; N16 deletes `_mirror()` and stays green |
| D8 "what it observes is exactly 'alone'" (the allowlist header) | a row that reds when neutered alone | **TRUE** — 0/13 red alone over an exhaustive k=1, 1/78 at k=2 |
| D9 "Deciding WHY a row is here still needs a person and a verdict id" | a mechanical decision procedure | **TRUE**, and §1 grades the two proposed ones |
| D10 (carried) W4 "Driven at 9/9 shapes, full suite at baseline" | reverting the token leaving the suite green | **NO ARTIFACT** — revert → **137 passed**, **7th round** |
| D11 (carried) "the recorder must be this turn's" | a carried recorder accepted at the door | **FALSE**, re-executed — §3.2 |

---

# 3 · FINDINGS

Reachability stated for every one.

### A23-1 · The "the census RUNS" assertion is satisfied by a YAML comment — `test_cp1_membrane.py:2141`
`assert 'python scripts/agentruntime-census.py' in job` over raw YAML text. **N21** (step deleted,
command left in a `#` comment) and **N22** (string in a later job) are both **GREEN**, measured. The
assertion sits eleven lines under a comment that says *"Match the call, not the topic."*
**Reachability: gate coverage, false GREEN** — the only direction that matters. Fix: parse the YAML.

### A23-2 · The flag blocklist is one token — `test_cp1_membrane.py:2144`
`assert '--write' not in job` closes the named bypass. **N17 `--selftest`, N18 `|| true`,
N19 `continue-on-error: true`, N20 `if: false` — all GREEN.** `--selftest` is the sharpest: the job
runs, prints `selftest OK`, exits 0, and **never compares against the allowlist**.
**Reachability: gate coverage, false GREEN.**

### A23-3 · The delta's headline property is guarded by a spelling — `test_cp1_membrane.py:2168`
`assert "PKG.glob" not in _census_body`. **N13 RED** (the literal spelling), **N14 GREEN**
(`(ROOT / _PKG_REL).glob`), **N23 GREEN** (mirror built and discarded). Either mutant restores
live-tree neutering of tracked production files under every kill in §0.1, with the gate green.
**Reachability: gate coverage, false GREEN, on the one property the whole delta is about.**

### A23-4 · `assert "_mirror" in src` is defeated by a comment — `test_cp1_membrane.py:2159`
**N16 GREEN**: delete the entire `_mirror()` function, restore live-tree neutering, leave
`# the _mirror helper was deleted`. **Reachability: gate coverage, false GREEN.**

### A23-5 · The selftest's controls are in two different trees — `scripts/agentruntime-census.py:235, 239–256`
Positive control in the live tree, negative control in the mirror; **nothing asserts the unmodified
mirror is green**, so a broken mirror is indistinguishable from a firing probe and yields 68 RED and
thirteen `NOW GUARDED … good news` lines. Today's mirror **is** green (`136 passed`, executed).
**Reachability: LATENT — and its failure mode is R22's, one layer down.** One line fixes it.

### A23-6 · The mirror is never removed — `scripts/agentruntime-census.py:86`
`tempfile.mkdtemp` with no `rmtree`/`TemporaryDirectory`/`finally` anywhere in the file. **Two per
run** (`_selftest` + `census`), **13 579 files / 214 MB / 44.7 s each**; **37 on disk at 6.71 GB**
measured. **Reachability: CERTAIN and unbounded** for the documented pre-commit use.

### A23-7 · The digest docstring's own headline number is false of the shipped digest — `scripts/agentruntime-census.py:116`
Claims *"98/98 pairs, 0 collisions"*; measured **94/98, 4 collisions**, all four being same-class
same-function raises that differ only in message text. **Claim reachability: CERTAIN, already
false.** **Defect reachability: LATENT** — 0 of the 6 both-SILENT same-key pairs collide, so R21-A's
Case B remains closed. Fix: correct the number and state the collision class in one sentence.

### A23-8 · `_shape_digest` is not total below CPython 3.12 — `scripts/agentruntime-census.py:125`
`ast.unparse` raises `ValueError: Unable to avoid backslash in f-string expression part` on this
package under 3.11.14; the census dies with a traceback. **Reachability: NONE in CI** (pinned 3.12);
**CERTAIN for a developer on ≤3.11** running the documented pre-commit gate.

### A23-9 · Gate coverage regressed on the restore guarantee — `test_cp1_membrane.py`
**N12** (census never restores inside the mirror) was **RED** in R22 and is **GREEN** now: the
`raise SystemExit` assertion was deleted with its subject, and nothing replaced it. The consequence
is smaller than before — the damage is confined to a throwaway copy — but the *measurement* is not:
every site after the first is then neutered on an already-broken package. **Reachability: gate
coverage, false GREEN; the census's own drift output is the only remaining backstop.**
**N11** (neuter the census's selftest → `return 0`) remains GREEN, **2nd round**.

### A23-10 · Carried verbatim — the delta touched none of these
`git diff --stat c37459826 HEAD -- services/chat-service/app/services/ services/chat-service/tests/test_cp0_instrument.py`
is **empty**.

| item | site | rounds open |
|---|---|---|
| the carried-recorder hazard, unfalsifiable at this seam | `instrument.py:579`, `test_cp0_instrument.py:2908/2934` | **4th** |
| exact-type bound, strictness unmeasured | `instrument.py:580` | 3rd |
| **W4's `s.body[:1]` has no test** | `test_cp0_instrument.py:2284` | **7th** |
| a `With` inside a `Try` re-admits the whole body (`s.body`, not `s.body[:1]`) | `test_cp0_instrument.py:2256` | 3rd |
| **three weak oracles, byte-identical** | `:3242`, `:3297`, `:3374` | **7th** |
| T11d — the SQL matcher resolves the literal, not the constant | `stream_service.py:6297` | **5th** |
| probe modules written into the live `app/` tree — **7** writers hardcode `"app"` (`:24`, `:2085`, `:3047`, `:3077`, `:3230`, `:3279`, `:3308`) while `_TURN_SCOPE_ROOT = "app"` sits at `:2151` and only **2** sites use it (`:1626`, `:2295`) | as listed | **5th** |
| `:531` "Ask the turn's **RECORDER** first" vs `:542` "Read from the **FLAG** first" | `instrument.py:531, 542` | **9th** |
| the recorder is inert at its only call site | `voice_stream_service.py:422` | 4th |

---

## 3.1 · Item 2 of my section — **W4's test, re-stated so it can be applied, and what it costs**

**Baseline, re-measured on the frozen tree, in a mirror:**

```
SHIPPED  (s.body[:1])   rc=0   137 passed
REVERTED (s.body)       rc=0   137 passed
```

**0/1 red-able, seventh round.** The 9-shape enumeration re-executed against the shipped helper and
its negation in one process — 3 arm positions × 3 `try` tails, no probe file written anywhere:

| arm position | `except-pass` | `finally` | `else` |
|---|---|---|---|
| **first** in the try body | 1 vs 1 — no | 1 vs 1 — no | 1 vs 1 — no |
| **second** | **0 vs 1 — YES** | **0 vs 1 — YES** | **0 vs 1 — YES** |
| **third** | **0 vs 1 — YES** | **0 vs 1 — YES** | **0 vs 1 — YES** |

**6 of 9 discriminate.** Here is the test. I did not evaluate it in a REPL this time — I **appended
it to `test_cp0_instrument.py` in a mirror and ran the file**, on the shipped rule and on the revert:

```python
class TestW4TryBodyArmIsNotUnconditional:
    """W4: a `try` is entered unconditionally, so its FIRST statement runs. The SECOND runs only
    if the first did not raise - which is the whole reason the `try` is there. `s.body[:1]` is that
    rule and it has never had a test; the revert to `s.body` leaves the file 137-green."""

    def test_a_try_body_arm_AFTER_another_statement_is_not_unconditional(self):
        import ast as _a

        def pred(c):
            return (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) == "arm_turn_surface"

        late = _a.parse(
            "async def p(c):\n"
            "    try:\n"
            "        prelude()\n"
            "        arm_turn_surface()\n"
            "    except Exception:\n"
            "        pass\n").body[0]
        assert list(_unconditional_calls(late.body, pred)) == []
        first = _a.parse(
            "async def p(c):\n"
            "    try:\n"
            "        arm_turn_surface()\n"
            "    except Exception:\n"
            "        pass\n").body[0]
        assert len(list(_unconditional_calls(first.body, pred))) == 1
```

```
proposed test on SHIPPED   -> rc=0  1 passed, 137 deselected
  WHOLE FILE on SHIPPED    -> rc=0  138 passed
proposed test on REVERTED  -> rc=1  1 failed, 137 deselected
  WHOLE FILE on REVERTED   -> rc=1  1 failed, 137 passed
```

**What it costs.** 22 lines including the docstring; **0.33 s**; no import of anything the file does
not already import; **it writes no file into `app/`**, so unlike the six existing probe tests it does
not reproduce the 5-round-old probe-module finding. It asserts **both** directions, so it also fails
if someone narrows `Try` to nothing. **There is no remaining reason for this not to exist.**

## 3.2 · Item 3 of my section — the recorder hazard, **4th round, and the V-LIVE observation in one sentence**

Re-executed independently on the frozen tree, one process, `contextvars.copy_context()`:

```
_O_K()                                       -> True    (a PASSING test at :2934 asserts this is True)
turn B, no recorder                          -> False   (the shipped test asserts False)
turn A's recorder, asked directly            -> True    (the shipped test asserts True)
catalogue_outage_registered(rec_a) in turn B -> True    <- THE HAZARD; no test writes this line
```

Unchanged, byte for byte, and still unfalsifiable at this seam: the two executions differ in **no
ContextVar**, only in which recorder object the reader holds. A test that drove the hazard would red
`_O_K`, which passes today.

> **The sentence a CP-2 harness can implement:** stamp a fresh `uuid4` **turn token** into a
> ContextVar at every `arm_turn_surface()` and log `(token, id(recorder))` at the read site
> `voice_stream_service.py:422`; **the harness passes if and only if no `AdvertisedToolsRecorder`
> object id ever appears under two distinct turn tokens.**

Drive it against three shapes: two concurrent voice requests on one session; one request whose turn
is re-entered (retry/reconnect on the same task); and one that records an outage and never arms
(`O_J`). **If NO** — the design premise holds, `_O_K` is right, the parameter is correct-by-
construction for its one caller, and this closes as a non-defect. **If YES** — `_O_K` asserts U-2's
founding defect as the requirement, and the bound must become a turn token on the recorder, which the
design explicitly rejected. **Nothing in the source can decide it. Fourth round, and it is the only
open item on this seam that more V-CODE cannot move.**

## 3.3 · Item 4 of my section — the three weak oracles, T11d, the probe writers

**Three weak oracles, 7th round, byte-identical.** `test_cp0_instrument.py:3242`, `:3297`, `:3374`,
all `pytest.raises(AssertionError, match=...withheld_tools...)`. The two no-vacuity guards inside the
gated test both carry `withheld_tools` in their own message, so the oracle is satisfied by a gate
that fired for a reason unrelated to the probe. **Reachability: production** — a one-token refactor
at a live site makes two of them green over an unmeasured probe. **It is three string literals, and
R20-A named the phrase that occurs exactly once in the file.** *(Read and located this round; the
gating mechanics were re-driven in R20/R22 and the file is byte-unchanged since.)*

**T11d, 5th round.** `stream_service.py:6297` — the orphan-stamp branch now interpolates
`instrument.segment_merge_sql('withheld_tools')` into the SQL, and the matcher resolves the literal
rather than the constant. File unchanged in the delta. *(Read, not re-driven.)*

**Probe modules in the live tree, 5th round — and now the *last* mechanism doing it.** Seven writers
hardcode `parents[1] / "app"` (`:24`, `:2085`, `:3047`, `:3077`, `:3230`, `:3279`, `:3308`) while
`_TURN_SCOPE_ROOT = "app"` sits at `:2151` and only two sites use it (`:1626`, `:2295`). **The census
stopped mutating the live tree this round; `test_cp0_instrument.py` did not.** Executed this round:
those probes do **not** red the membrane suite (3/3 green in a mirror), so they no longer threaten
the census's live selftest — but they still write untracked modules into `app/agentruntime/`,
`app/routers/` and `app/services/` on every run, and a kill during that window still leaves them
behind. **Reachability: CERTAIN; consequence now cosmetic-to-moderate.**

---

# 4 · TABLES

## 4.1 · Bypass table

| # | bypass | executed | result |
|---|---|---|---|
| B1 | kill the census 8 different ways, mid-loop | ✅ ×8 | **live tree UNCHANGED 8/8** |
| B2 | run the census to completion, check the tree | ✅ | **byte-identical; rc=0; 0 drift lines** |
| B3 | run the membrane suite 20× during a live census | ✅ ×20 | **20/20 GREEN** (R22: 16/20 RED) |
| B4 | resolve every allowlist row on the interpreter CI pins | ✅ 3.12 | **13/13** (R22: 0/13) |
| B5 | compare all 68 ids across interpreters | ✅ 3.12/3.13 | **68/68 identical, same order** |
| B6 | run the digest under 3.11 | ✅ | **ValueError — the census dies** |
| B7 | reword a C-12 message | ✅ 68/68 | **row does not move** — closed |
| B8 | reindent a raise | ✅ 68/68 | row does not move |
| B9 | rename the enclosing function | ✅ 68/68 | row moves, **via the id prefix** — intended |
| B10 | reorder two same-class same-function raises | ✅ 98 pairs | **94/98**; 4 collisions; **0 of the 6 both-SILENT pairs collide** |
| B11 | neuter each allowlist row alone | ✅ 13 | **0 RED** — the header is true 13/13 |
| B12 | neuter every pair of allowlist rows | ✅ 78 | **1 RED pair**, 2 rows implicated |
| B13 | delete the `Refusal census` STEP | ✅ N7 | **RED** — closed |
| B14 | replace the command with `echo skip` | ✅ N8 | **RED** — closed |
| B15 | run the census with `--write` | ✅ N9 | **RED** — closed |
| B16 | **run it with `--selftest` only** | ✅ N17 | **GREEN** ❌ |
| B17 | **append `\|\| true`** | ✅ N18 | **GREEN** ❌ |
| B18 | **`continue-on-error: true`** / **`if: false`** | ✅ N19/N20 | **GREEN** ❌ ×2 |
| B19 | **delete the step, leave the command in a YAML comment** | ✅ N21 | **GREEN** ❌ |
| B20 | **put the command string in an unrelated later job** | ✅ N22 | **GREEN** ❌ |
| B21 | **neuter the live package, spelled `(ROOT / _PKG_REL).glob`** | ✅ N14 | **GREEN** ❌ |
| B22 | **build the mirror, discard it, neuter the live tree** | ✅ N23 | **GREEN** ❌ |
| B23 | **delete `_mirror()`, leave its name in a comment** | ✅ N16 | **GREEN** ❌ |
| B24 | census never restores inside the mirror | ✅ N12 | **GREEN** ❌ (was RED) |
| B25 | neuter the census's own selftest | ✅ N11 | **GREEN** ❌ (unchanged) |
| B26 | revert W4's `s.body[:1]` token | ✅ | **137 passed** — 7th round |
| B27 | append the proposed W4 test and revert the token | ✅ | **1 failed, 137 passed** — it reds |
| B28 | hand turn A's recorder to turn B | ✅ | **True** — the hazard, 4th round |
| B29 | write the probe module into the live-shaped `app/{agentruntime,routers,services}` and run the membrane suite | ✅ ×3 | **green 3/3** — my own hypothesis refuted |

## 4.2 · Red-ability table — **my denominator**

| space | denominator | red-able |
|---|---|---|
| **A · the gate test** — 20 enumerated defeat shapes over the workflow, the census source and the allowlist | **20** | **9/20.** The 11 misses cluster: 6 keep the string and kill the check (N17–N22), 3 restore live-tree writes (N14, N23, N16), 2 hollow the instrument (N11, N12) |
| **B · the census as a kill-safe instrument** — every kill primitive I could issue on this platform | **8** | **8/8 leave the tree byte-identical.** Nothing left to fix |
| **C · the census as a non-interfering instrument** | **20 concurrent runs** | **20/20 green** |
| **D · the allowlist's per-line claim** — all subsets of size ≤2 | **91** | **0/13 refuted at k=1** (the sentence now says *alone*); 1 minimal red pair, 2 rows, which refutes only the **old** wording |
| **E · row-id stability** — 4 edit classes over all 68 sites, plus every same-key pair | **68×4 = 272, +98 pairs** | **3/4 classes correct** (reword ✅ 0/68, reindent ✅ 0/68, rename ✅ by prefix); reorder **94/98**, 4 collisions, **0 of them live** |
| **F · cross-interpreter portability** | **68 × 2 interpreters** | **68/68 portable**; **13/13** rows resolvable on the pin |
| **G · W4** — the one token | **1** | **0/1** shipped, **7th round**; **6/9** enumerated shapes discriminate; the test is written and **executed red on the revert** |
| **H · the carried recorder** — its stated subject | 4 semantic mutants (R21) | **0/4**, unchanged; hazard re-executed live |

## 4.3 · Sibling table

| fix landed at | the sibling one token away | status |
|---|---|---|
| `--write` is forbidden in the CI job | `--selftest`, `\|\| true`, `continue-on-error`, `if: false` | **open**, A23-2 |
| the census command must appear in the job | …in a **comment**, or in a **later job** | **open**, A23-1 |
| `PKG.glob` may not appear in `census()` | **any other spelling of the same live path**, and `pkg, cs = PKG, CS` | **open**, A23-3 |
| `_mirror` must appear in the source | …as a **comment**, with the function deleted | **open**, A23-4 |
| the digest no longer moves on a reword | it now **collides** on two refusals that differ only by message | **open (latent)**, A23-7 |
| the mirror ends census→suite interference | `test_cp0_instrument.py`'s **7 probe writers** still mutate the live `app/` tree | **open**, 5th round |
| `atexit`/`SIGTERM` deleted with their subject | the `raise SystemExit` restore guarantee deleted too — and **N12 regressed to GREEN** | **open**, A23-9 |
| the selftest's negative control moved to the mirror | its **positive** control stayed in the live tree, so the mirror is never proven green | **open**, A23-5 |
| `ambient.write_text` → `write_bytes` (`93af52373`) | `ALLOWLIST.write_text`, in the census's own file | **open (low)**, A22-9, 2nd round |
| `Try` → `s.body[:1]` | `With`/`AsyncWith` → still `s.body` | **open**, 3rd round |
| the **type** of the recorder | the **turn** of the recorder | **open**, 4th round |

## 4.4 · Guard table

| guard | exists | fires | fires for the right reason |
|---|---|---|---|
| census `--selftest`, both directions | ✅ | ✅ | ⚠️ **its two controls run in two different trees** (A23-5) |
| the **mirror** is green before injection | ❌ | — | — |
| census leaves the live tree untouched — **behaviourally** | ✅ (by construction) | ✅ 9/9 | ✅ |
| census leaves the live tree untouched — **as a gate** | ⚠️ substring | only on the literal `PKG.glob` | ❌ N14/N23/N16 |
| census restore inside the mirror | ✅ | ✅ | ❌ **untested** — N12 GREEN |
| census row id stable across interpreters | ✅ | ✅ | ✅ 68/68, 13/13 |
| census row id stable across a reword / reindent | ✅ | ✅ | ✅ 0/68 each |
| census row id distinguishes a reorder | ✅ | ✅ | ⚠️ **94/98**; the 6 pairs that matter are 6/6 |
| census site-**set** comparison (a deleted refusal still prints `NOW GUARDED … good news`) | ❌ | — | — (R21-A item 3, still not shipped) |
| the mirror is cleaned up | ❌ | — | — (A23-6) |
| a test that the census **runs** in CI | ⚠️ substring | on a full deletion | ❌ N21/N22 |
| a test that the job is not disabled | ❌ | — | — N19/N20 |
| a test that the census's deps install | ✅ | ✅ | ✅ |
| the allowlist header matches its experiment | ✅ | ✅ | ✅ **13/13** |
| the allowlist is written as BYTES | ❌ | — | — (`write_text`, low) |
| `timeout-minutes` on the census job | ❌ | — | — (in a repo that ships a `timeout-discipline-lint`) |
| digest totality below 3.12 | ❌ | — | — (A23-8) |
| W4 rule test | ❌ | — | — **7th round**; §3.1 has it, executed |
| terminal-write probe oracles ×3 | ✅ | ✅ | ❌ **7th round** |
| recorder **turn** bound | ❌ | — | — **4th round** |

## 4.5 · Reachability verdict on every finding

| finding | reachable? |
|---|---|
| A23-1 "the census RUNS" satisfied by a comment / a later job | **gate coverage, false GREEN** — 2 executed bypasses |
| A23-2 the flag blocklist is one token | **gate coverage, false GREEN** — 4 executed bypasses |
| A23-3 live-tree neutering guarded by a spelling | **gate coverage, false GREEN, on the delta's headline property** — 2 executed bypasses |
| A23-4 `"_mirror" in src` satisfied by a comment | **gate coverage, false GREEN** |
| A23-5 the selftest's controls live in two trees | **LATENT** — today's mirror is green (executed); the failure mode is R22's, relocated |
| A23-6 the mirror is never removed | **CERTAIN, unbounded locally** — 37 dirs / 6.71 GB measured |
| A23-7 the docstring's `0 collisions` is false | **claim: CERTAIN and false. defect: LATENT** — 0 of 6 both-SILENT pairs collide |
| A23-8 `ast.unparse` not total below 3.12 | **NONE in CI** (pinned 3.12); **CERTAIN for a developer on ≤3.11** |
| A23-9 N12 regressed, N11 unchanged | **gate coverage, false GREEN** |
| A22-9 `ALLOWLIST.write_text` | **LOW** — `.gitattributes` normalises at commit; 2nd round |
| W4 `s.body[:1]` | **gate coverage** — the rule can drift either way unnoticed; the test exists and reds (executed) |
| three weak oracles | **production** — a one-token refactor at a live site; 7th round |
| carried recorder | **LATENT** — unreachable via the only wired caller; **whether it is a defect is the V-LIVE question**, §3.2 |
| T11d, probe writers, `:531` vs `:542` | as recorded in R19–R22; files byte-unchanged |

---

# 5 · EXECUTED vs ARGUED

**67 load-bearing claims. 58 executed, 9 argued. Ratio 58 : 9 — 87 %.**

Every execution ran over an **enumerated** or **exhaustive** space:

| space | denominator | complete over |
|---|---|---|
| kill matrix | **8** mechanisms | every kill primitive I could issue on this platform, incl. process-tree and `-9` |
| concurrency | **20** runs | R22-A's own denominator |
| id stability under edits | **68 × 4** + **98** sibling pairs | every `raise` in the package; every same-class same-function pair |
| cross-interpreter portability | **68 × 3** interpreters | every site, on 3.11 / 3.12 / 3.13 |
| allowlist honesty | **91 subsets** (13 + 78) | all subsets of size ≤ 2 of the 13 |
| gate-test red-ability | **20** defeat shapes | workflow × census source × allowlist |
| W4 | **9** shapes, then the real test in the real file | 3 arm positions × 3 `try` tails, both rule variants |
| mirror fidelity | **13 579** tracked paths, all git modes | the whole index |
| census end-to-end | **68** sites × 1 suite run each | the whole package, twice |

Suite invocations this round: **91** membrane runs for the k≤2 sweep, **20 + 1** for concurrency,
**~21** for the defeat matrix, **~140** inside two full census runs, **4** whole-file
`test_cp0_instrument.py` runs (137/137/138/138), plus 3 probe-interference runs.

**The 9 argued claims, named so they can be attacked:**

1. The RED/SILENT **split** is the same on `ubuntu-latest` + 3.12 with CI-installed deps as on my
   3.13. The **ids** are proven identical (68/68, 13/13); the split was not run, because my local
   3.12 lacks `json_repair`. *This is the one gap between my PASS and a CI-shape end-to-end.*
2. `shutil.copyfile` dropping the exec bit could matter on POSIX — 25 tracked `100755` files exist;
   nothing in the membrane suite execs a file, so I rank it latent. Not run on Linux.
3. Submodule and symlink skips are latent — read from `git ls-files -s` modes (`{100644, 100755}`
   only) and the absence of `.gitmodules`, not from a constructed case.
4. The ~430 MB-per-run mirror leak is survivable on a CI runner — not executed on a runner.
5. N19/N20 (`continue-on-error`, `if: false`) genuinely neutralise the job in GitHub Actions — YAML
   semantics, not executed on a runner. *(The gate test's GREEN is executed; the runner behaviour is
   not.)*
6. N12's consequence — that skipping the restore corrupts every subsequent site's measurement — is
   reasoned from the loop, not driven to a wrong census output.
7. The four digest collisions become live *"the moment a second member goes silent"* — reasoned;
   what I executed is that 0 of the 6 both-SILENT pairs collide today.
8. T11d is unchanged — read from the diff, not re-driven.
9. The three weak oracles' gating mechanics — located and read this round; the file is byte-unchanged
   since R22, whose driving I am relying on.

**And the standing caveat, now with a second instance.** R22-A wrote *"an execution is only as
frozen as its tree."* This round the live allowlist was observed rewritten to `deadbeef` and back by
a concurrent process. Every number above came from a mirror or from a window I verified clean; the
one thing I want on the record is that **the repo still has no lock, and two verifiers sharing a
worktree is now a measured hazard rather than a hypothetical one.**

---

# 6 · CONVERGENCE

**Raw.** Eleven load-bearing claims in scope (§2.1). **Closed: 6** (D1, D2, D3, D4, D8, D9).
**Refuted: 3** (D5 as written, D6, D7-as-a-gate). **No artifact: 1** (D10). **Carried unfalsifiable:
1** (D11).

**Findings introduced by this delta: 9** (A23-1 … A23-9).
**Findings closed by this delta: 6** — A22-1 (version stability), A22-2 (the job cannot be green),
A22-3 (Windows kills), A22-6 (reword relocation), A22-7 (no crash detector), A22-8 (concurrency).
A22-4 is **half** (3 of its bypasses closed, 6 new ones open); A22-5 is **not closed — reproduced
twice**; A22-9 carried.

**The series, raw:** `2,1,2,1,3,2,4,3,2,2,2,5,13,8,` **`9`**.

**And the series is, once again, the wrong instrument — but this time it hides a real inflection, so
I want to be exact about the shape rather than the count.**

* **Six closures against nine introductions is the first delta in this run with a positive ledger.**
  Every previous round closed 0 or 1.
* **Not one of my nine findings makes the census produce a wrong answer today.** Six are the gate
  test's red-ability, two are hygiene (a leaked temp dir, a false number in a docstring), one is an
  interpreter-envelope boundary CI does not touch. Compare R22, where **the instrument itself exited
  1 with 26 false drift lines**. The class of defect moved from *the measurement is wrong* to *the
  guard around the measurement is weak*, and that is the first genuine step-change in fifteen rounds.
* **The signature failure recurred, and it recurred in the fixes for it.** A23-1 and A23-4 are the
  comment-satisfiable-assertion defect **inside the two assertions written to replace the one a
  comment defeated**. A23-2 forbids the one flag a verifier named and permits its four siblings.
  A23-3 guards the delta's whole thesis with a substring. That is **instance ten**, and it is now
  concentrated entirely in one 60-line test.
* **The builder's self-measurement was wrong in the flattering direction again**, and it is the fifth
  time: `98/98, 0 collisions` was measured on the digest that was *replaced* and shipped as a property
  of the one that replaced it. The number is 94/98.

## 6.1 · **Do I support closing CP-1 against the census? Yes.**

R22-A stated four executable conditions and said he would support closure once they landed. I have
re-derived every one of them on my own harness, over my own denominators:

1. **`ast.unparse` + regenerate** — **verified**: 68/68 ids portable, 13/13 rows resolvable on the
   CI pin, census rc=0, zero drift lines.
2. **Assert the census runs; drop the comment-satisfiable substring** — **half**: N7/N8/N9 closed;
   the replacement is comment-satisfiable.
3. **Run out of tree** — **verified**: 8/8 kills clean, 20/20 concurrency green.
4. **Fix the header** — **verified**: true of 13/13 under an exhaustive 91-subset sweep.

**Three and a half of four, and — this is the part that decides it — the half that is missing is not
in the measurement.** The census's output is correct, reproducible across the interpreters in play,
byte-safe under every kill available, and non-interfering. The closure criterion *"a finding is
closed when this named site moved SILENT → RED"* is now **operable**, which is the thing that was not
true in any previous round.

**Two conditions, and they are checks, not debates:**

* **C1 — parse the YAML.** Replace the three substring assertions with
  `yaml.safe_load(wf)["jobs"]["agentruntime-census"]`, require a step whose `run` **equals**
  `python scripts/agentruntime-census.py`, and assert the step carries no `if` and no
  `continue-on-error`. Kills N17–N22 in one expression, and a comment cannot satisfy a parse.
* **C2 — assert the property, not the spelling.** Replace `"PKG.glob" not in _census_body` with:
  monkeypatch `_mirror` to a tmp copy, call `census()`, assert `app/agentruntime/*.py` bytes are
  unchanged. Kills N13/N14/N23 and cannot be defeated by a rename. *(And while there: one line
  asserting the **mirror** is green before the probe, closing A23-5.)*

**But closing CP-1 *against* the census is not the same as CP-1 being closed, and I want that
distinction on the record so it is not lost in a PASS.** Applied today, the criterion reads:
**13 rows still SILENT, none carrying a verdict id; 2 of them refutable at k=2; and the non-census
findings carried at rounds 4 through 9** — W4 at 0/1 for the **seventh** round with a written,
executed test sitting in §3.1; three string literals unchanged for the **seventh**; the recorder
hazard unfalsifiable for the **fourth**, needing one live observation nobody has made; `:531` vs
`:542` contradictory for the **ninth**.

**The instrument is ready. The subject is not. Those are now two separate sentences for the first
time, and that is the whole value of this delta.**

**Carried into whatever comes next, in priority order:**

1. **C1 and C2 above** — eight lines, and they take the gate test from 9/20 to 18/20 by my own
   enumeration.
2. **Write W4's test.** §3.1 has it, appended to the real file and executed red on the revert.
   **Seventh round at 0/1.**
3. **Fix the three weak oracles** — three string literals. **Seventh round.**
4. **The V-LIVE recorder question** (§3.2) — one sentence, three probes, and no amount of source
   reading will settle it. **Fourth round.**
5. **Correct the digest docstring's `98/98, 0 collisions`** to `94/98, 4 collisions, none of them
   between two SILENT rows` — one line, and it stops a false number propagating a sixth time.
6. **Clean up the mirror** (`TemporaryDirectory`), and **assert the mirror is green** in `_selftest`.
7. **Point the seven probe writers at `_TURN_SCOPE_ROOT`** — 5th round, and now the only mechanism
   still mutating the live tree.
8. **Resolve `:531` vs `:542`** — 9th round. One of the two sentences is false.

---

`git rev-parse HEAD` **at finish**: `9b77caed789e9f2737f849d63b1485a65bcbd8a4` — **unmoved.**
`git status --porcelain` at finish: **empty** (this verdict is the only file I wrote, and it is new).
No `git checkout` was used. Every mutation was applied inside a throwaway mirror and restored from my
own byte snapshot with an equality assert; the live `app/agentruntime/` was SHA-256-verified
identical to its pre-round snapshot after the full census and after all eight kills.
