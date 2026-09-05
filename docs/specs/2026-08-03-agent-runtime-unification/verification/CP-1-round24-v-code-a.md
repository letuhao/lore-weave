# CP-1 · round 24 · V-CODE · Verifier A — the instrument

`git rev-parse HEAD` **at start: `b5d81e54ad6fed9134758b02e8d4bb66e1691a25`**
Graded delta `714d8b7c8`, diffed against `9b77caed7`.

**Method note, stated first because it changed my answer.** The prompt warned that two verifiers
sharing one worktree had been observed rewriting each other's files. I did not measure in the shared
tree. I created two detached worktrees at the frozen sha
(`scratchpad/wt-a`, `scratchpad/wt-b`), took byte snapshots of every file I patched, restored from
those snapshots, and verified each restore by sha256. **Both worktrees end at 0 modified and 0
untracked files.** That was the right call: see §7.

---

# 0 · THE ANSWER, IN ONE PARAGRAPH

I was asked to find the ninth bypass. **I found nineteen**, over an enumerated space of 21
disable-class mutations, all executed. But the bypasses are not the finding. I ran the census
itself, to completion, on a clean checkout of the frozen artifact, and it reports

```
agentruntime-census: 68 sites, 0 silent, 68 red        RC=1
NOW GUARDED   canon.py::_norm::NotCanonicalisable::1::50f6dc36  <- good news: drop it from the allowlist…
…  (×13)
```

**The graded delta breaks the census.** The guard it added to `test_cp1_membrane.py` is itself run
by the census, 68 times, inside a mirror that has no `.git`; it dies there with
`CalledProcessError`, so `_suite_is_green()` returns `False` for *every* input and every site reads
RED. The 55 RED / 13 SILENT partition on which **both** R23 verdicts rest, and which B's "close CP-1
at the 55 RED sites" scope is defined against, **is not reproducible at the frozen artifact.** The
instrument's selftest — the thing built to catch exactly this — passes, because its positive control
also runs in the mirror and therefore also fires on an untouched file.

**Verdict: FAIL. I do not support closing CP-1 against the census at any scope**, because at this
sha the census does not produce an answer to close anything against.

---

# 1 · ITEM 1 — THE GUARDS NOW EXECUTE. THEY STILL LIE.

## 1.1 · Is the write-watch measuring the property, or the next proxy for it?

**The next proxy, and the proxy is on the wrong noun.**

The property is *"no write lands in the live tree."* The measurement is *"no call to
`pathlib.Path.write_bytes` receives a path with `_REPO` in `.parents`."* Those differ on two axes,
and I executed both.

**Axis 1 — the API.** `Path.write_bytes` is one of many ways to write a file. Executed
(`census_sweep.py`, 10 runs):

| # | mutation | guard | reality |
|---|---|---|---|
| N02 | live neuter+restore through `open(path,"wb")` | **GREEN** | 68 live-tree writes |
| N09 | live neuter+restore through `write_text` — *the version the docstring says was the first one* | **GREEN** | 68 live-tree writes |

**Axis 2 — the noun.** The watch identifies the target by *path*. Change the inode instead and the
path stays innocent. `_mirror()` copies 13,582 files with `shutil.copyfile`; replacing that with
`os.link` is a one-token change and a plausible "this copy takes two minutes" optimisation.
Executed (`n04_proof.py`), all four of the guard's assertions evaluated live:

```
sites enumerated              : 68
A1  writes seen into live tree: 0      -> assertion PASSES
A2  after == before           : True   -> assertion PASSES
A3  results non-empty         : True   -> assertion PASSES
A4  every suite cwd outside   : True   -> assertion PASSES  (…\Temp\lw-census-5smqdq19\services\chat-service)

REALITY: moments at which a LIVE tracked source file was mutated mid-run: 68 of 68
   distinct live files damaged: ['admission.py','canon.py','contract.py','manifest.py','surface.py']
```

**All four assertions green while every one of the 68 neuterings mutated a tracked production
module.** This is not an adjacent failure — it is the *exact* pair of defects `_mirror()`'s docstring
says it exists to end, restored verbatim: a SIGKILL in that window leaves `raise → pass` in a
tracked file, and a concurrent suite run reads the neutered source.

**Axis 3 — the subject.** The guard calls `census()`. `main()` calls `_selftest()` **and**
`census()`. Nothing exercises `_selftest`, which is where the live-tree work actually happens today
(`agentruntime-census.py:235` — `_suite_is_green()` with no `cwd`, i.e. the **live** tree).

| # | mutation | guard | reality |
|---|---|---|---|
| N07 | `_selftest()` appends bytes to the live `canon.py` | **GREEN** | the live package is written |

And this is not hypothetical: at the frozen artifact, `_selftest()` runs the whole membrane suite in
the live tree, which writes `services/chat-service/.pytest_cache/` and
`app/agentruntime/__pycache__/*.pyc` — **inside the very directory the docstring says is never
touched.** Both are gitignored, which is precisely why `git status`, the before/after hash of
`*.py`, and the `write_bytes` watch are all three blind to them.

### The controls, for fairness — they all fire

| # | control | result |
|---|---|---|
| N01 | `pkg, cs = PKG, mirror/_CS_REL` (live neuter via `write_bytes`) | **RED** ✅ |
| N05 | `_mirror` → `_mirrorX` — *the R23 control that never fired* | **RED** ✅ |
| N06 | mirror placed inside the repo (`mkdtemp(dir=ROOT)`) | **RED** ✅ |
| N08 | the suite is run against the live chat-service (`cs = CS`) | **RED** ✅ |

**4/4.** The rewrite is a real improvement over source-text matching, and R23's dead control is now
alive. That is the honest credit. The docstring's claim — *"It reds when the mirror is removed, when
it is bypassed, and when it is renamed"* — is **true for "removed" and "renamed" and false for
"bypassed": 4 of 5 bypass shapes are green.**

## 1.2 · The fix's own honesty — a docstring describing a test that was not written

> *"So this **runs the thing**: it drives `census()` over a **two-site fixture package** with a real
> neutering loop…"* — `test_cp1_membrane.py:2136`

There is no fixture package. `census()` takes one parameter (`verbose`) and always enumerates the
real 8-module, 68-site package; the test asserts `len(before) >= 6`. **The sentence describes the
test that should have been written, in the voice of the test that was.** Had it been written as
described, §2 below would not exist — a two-site fixture would not have recursed.

## 1.3 · The CI half — 15 of 16 enumerated disable shapes are green

`wf_sweep.py` + addendum, 25 executed runs over a mutation space enumerated from the *structural
degrees of freedom the guard reads*: workflow triggers, job keys, step keys, and run-string content.

| # | mutation | guard |
|---|---|---|
| M01 | step-level `if: false` — the job has no `if`, so the job-level check passes | **GREEN** ❌ |
| M02 | step-level `if: github.event_name == 'schedule'` | **GREEN** ❌ |
| M03 | **job-level** `continue-on-error: true` (only *steps* are checked) | **GREEN** ❌ |
| M04 | `needs:` a job that is itself `if: false` | **GREEN** ❌ |
| M05 | workflow `on:` loses `pull_request` — never runs on a PR | **GREEN** ❌ |
| M06 | workflow `on:` becomes `workflow_dispatch` only | **GREEN** ❌ |
| M07b | **the entire run line is a shell comment**: `run: "# python scripts/agentruntime-census.py"` | **GREEN** ❌ |
| M16 | `run: "true # python scripts/agentruntime-census.py"` | **GREEN** ❌ |
| M08 | `run: echo python scripts/agentruntime-census.py` | **GREEN** ❌ |
| M09 | `run: python scripts/agentruntime-census.py --help` (argparse exits 0) | **GREEN** ❌ |
| M10 | `run: … \| cat` — a single pipe; exit status is `cat`'s | **GREEN** ❌ |
| M11 | `run: … &` — backgrounded, step exits 0 | **GREEN** ❌ |
| M12 | `run: set +e; …; true` | **GREEN** ❌ |
| M13 | a nonexistent interpreter name | **GREEN** ❌ |
| M14 | the step becomes `uses: ./.github/actions/noop`, a decoy `echo` keeps the filename | **GREEN** ❌ |
| M15 | `--selftest --help` | RED ✅ |
| C01–C07 | step deleted / job renamed / `--write` / `\|\| true` / job `if: false` / step `continue-on-error` / no `requirements-test.txt` | **RED ✅ 7/7** |

**M07b is the finding.** R23's fix moved from *substring over the workflow's text* to *YAML parse* —
and the third instance of "a test satisfied by a comment" was the stated reason for it. But the
`run:` **value** is still read as a substring, so the comment simply moved one level down, from a
YAML comment into a shell comment inside the parsed scalar. **Fourth instance, inside the repair for
the third.** The rule the run states in capitals is not "parse the YAML"; it is *don't ask whether
someone typed a word.*

The shape that closes M07b–M16 at once is the same one R23-A proposed and did not get: **the CI step
must be `run: python scripts/agentruntime-census.py` exactly** — an equality, not a membership test —
plus `assert "if" not in step`, `assert not job.get("continue-on-error")`, `assert "needs" not in
job`, and `assert "pull_request" in wf["on"]`. Five lines; all five are single-key lookups on data
the test already has parsed.

## 1.4 · **The ninth bypass is not a bypass. The delta broke the instrument.**

`census()` runs `tests/test_cp1_membrane.py` with `cwd = <mirror>/services/chat-service`. That file
now contains the new guard. The guard loads `scripts/agentruntime-census.py` from `_REPO` — which,
inside the mirror, **is the mirror** — and calls `census()`, which calls `_mirror()`, which runs
`git ls-files` with `cwd = ROOT`. A mirror is a plain copy of tracked files. It has no `.git`.

Executed (`recursion_probe.py`), on a **pristine** mirror with nothing neutered:

```
mirror built in 44.9s   .git present: False
git ls-files -z  (cwd = mirror root)  ->  rc=128  'fatal: not a git repository …'
pytest tests/test_cp1_membrane.py     (cwd = mirror/services/chat-service)
      E  subprocess.CalledProcessError: Command '['git','ls-files','-z']' returned non-zero exit status 128
      1 failed, 136 passed
_suite_is_green(mirror/services/chat-service) -> False
```

`_suite_is_green` is the entire definition of RED-vs-SILENT. It is now a constant. Executed
end-to-end, `python scripts/agentruntime-census.py -v` on a clean worktree at the frozen sha:

```
agentruntime-census: 68 sites, 0 silent, 68 red
RC=1
```

with thirteen `NOW GUARDED … <- good news: drop it from the allowlist in the same change` lines.
That is, word for word, the failure `_shape_digest`'s own docstring records as the worst one this
instrument has produced:

> *"The gate then printed thirteen `NEWLY SILENT` and thirteen `NOW GUARDED` lines and instructed
> the maintainer, thirteen times, to delete the allowlist. **That is worse than the failure it
> replaced**, because the previous one was obviously broken and this one is plausible."*

Reintroduced, from the other direction, by the commit written to make the instrument honest.

**And the selftest passes.** `_selftest`'s negative control runs in the live tree (a real repo →
green); its **positive** control — "neutering a guarded refusal reds the suite" — runs in the
mirror, where the suite is red for every input. Measured directly above: a mirror with **no**
neutering is already red. So `fired = not _suite_is_green(mirror/_CS_REL)` is `True`
unconditionally, and the harness prints `selftest OK - 68 raise sites, fires on a guarded one` while
being incapable of *not* firing. **A selftest whose whole purpose is "prove both directions" now
proves one direction by construction.**

Reachability: **CERTAIN, production CI.** The job is blocking, has no `continue-on-error`, and
`RUNNER_TEMP`/`/tmp` on a GitHub runner is not inside a git repository either. Every PR that touches
this repo fails this job, with a 13-line instruction to delete the allowlist.

Secondary cost, measured: each of the census's 68 suite runs now builds nothing but still pays the
inner test's failure path (~12–16 s vs ~2 s before), so the gate's wall-clock went from ≈3 min to
≈17 min — and if the recursion is fixed by giving the mirror a `.git`, each of the 68 runs would
build a **13,582-file mirror of its own** (44.9 s measured), i.e. ≈1 hour. **Whatever the fix is, it
must not be "make the inner census work."**

---

# 2 · ITEM 2 — THE NON-INJECTIVE ID

## 2.1 · First, a correction to the framing

**The full id *is* injective.** Measured over all 68 sites: `68 sites, 68 distinct full ids, 0
collisions`. What is not injective is the **shape digest** — 54 distinct over 68 — and that is not
the same claim.

The load-bearing fact is sharper and worse than "non-injective":

> **For 8 of the 68 sites, in 4 groups, the id's uniqueness rests entirely on the ORDINAL — i.e. on
> the site's position in the file.** That is exactly the property the digest was introduced to
> remove.

| group | n | allowlisted |
|---|---|---|
| `canon.py::_norm::NotCanonicalisable::50f6dc36` (the **float** refusal and the **set** refusal) | 2 | 1 |
| `contract.py::check_contract::ContractViolation::7aefcf3d` | 2 | 0 |
| `surface.py::OrderBy.__post_init__::ValueError::85310b4a` | 2 | 0 |
| `surface.py::TakeWhileBudget.__post_init__::ValueError::85310b4a` | 2 | 1 |

Executed (`reorder_probe.py`) — swap the two statements in `TakeWhileBudget.__post_init__`:

```
ALLOWLIST ROW      surface.py::TakeWhileBudget.__post_init__::ValueError::1::85310b4a
  named BEFORE ->  'take_while_budget needs a non-negative budget'
  names  AFTER ->  'take_while_budget must name the field it accumulates'
  SAME REFUSAL? -> False
IDS THAT CHANGED AT ALL: added=[] removed=[]
```

The `_sites` docstring says the digest exists so that *"a reorder shows up as one row leaving and one
arriving instead of as nothing at all."* **For these 8 sites nothing arrives and nothing leaves.**

**Where I disagree with my own instinct, and side with R23-A.** R23-A's B10 measured
`0 of the 6 both-SILENT pairs collide`, and that defence holds: the census compares *silent sets*,
not id sets, so a mixed SILENT/RED collision still produces output. I verified the composition — of
the 8 colliding sites, 2 are allowlisted (silent) and 6 are RED, and no group is both-silent. So the
**rc** consequence today is nil.

The residual consequence is not nil, and it is the one this run keeps paying for. On a mixed pair a
reorder prints `NEWLY SILENT ::2` **and** `NOW GUARDED ::1 <- good news: drop it from the allowlist
in the same change`. Nothing was guarded. The maintainer is instructed, in the gate's own words, to
record a closed finding that never closed. **Misattributed, not invisible** — which is the strictly
worse of the two, and the register the prompt says has lost rows in six consecutive rounds is
downstream of exactly this instruction.

## 2.2 · **"A stable id and a prose-blind id are incompatible, choose" — REFUTED, by measurement**

The trade was never stable-vs-prose-blind. It is **statement-local vs injective**: no function of a
`raise` statement alone can separate two statements that are identical modulo their strings. The fix
is to widen the digest's *scope* to the nearest enclosing branch test — **a condition is code, not
prose**, so blanking string literals inside it keeps the id exactly as prose-blind as it is today.

Executed (`id_variants.py`), five candidate ids × three enumerated edit classes over all 68 sites.
"distinct" is measured with the **ordinal removed**, so `68` means *injective without any positional
component at all*:

| variant | distinct | colliding sites | prose churn | rename churn |
|---|---:|---:|---:|---:|
| **V2** statement only — the **shipped** digest, ordinal removed | 64 | **8** | 0 | 64/64 |
| **V3** + enclosing branch TEST (strings blanked) | **68** | **0** | **0** | 68/68 |
| **V4** + enclosing branch TEST (strings **and names** blanked) | **68** | **0** | **0** | 68/68 |
| V5 + branch ARM only (no condition text) | 65 | 6 | 0 | 65/65 |
| V7 + previous sibling statement | 64 | 8 | 0 | 64/64 |

*prose churn* = ids that moved after rewording **every** string literal in the package. *rename
churn* = ids that moved after renaming every local. Note the last column: renaming moves ~100 % of
ids under the **shipped** digest too, because the statement itself contains names — so
context-widening costs **nothing new** on that axis.

**Grade: an injective id IS achievable, and it does not reintroduce prose-churn.** V4 is the one to
build: it separates all four groups using only the *shape* of the guard, so it survives renaming the
condition's identifiers as well. It inherits the shipped digest's version-stability because it uses
the same mechanism (`ast.unparse`, not `ast.dump`).

**What the gate needs — and this is the part that matters more than which variant wins.** The
ordinal must be **removed**, not supplemented. While the ordinal is in the id, an id can be
unique-but-positional and *the gate cannot tell the two apart* — which is why this survived to round
24 with three verifiers reporting "68 distinct ids". Then add two lines to `_selftest`:

```python
bare = {sid.rsplit("::", 2)[0] + "::" + sid.rsplit("::", 1)[1] for sid, _ in sites}
if len(bare) != len(sites):
    print(f"SELFTEST FAIL: {len(sites) - len(bare)} site(s) are separated only by position")
    return 1
```

That makes the property **checkable forever** instead of re-derivable by a verifier once a round. If
a genuinely indistinguishable pair ever appears, the gate says so; today it says nothing.

---

# 3 · MY SECTION

## 3.1 · W4, **8th round** — the test, re-stated in applicable form, and executed

`test_cp0_instrument.py:2284`. The delta touched nothing here:
`git diff --stat 9b77caed7 714d8b7c8 -- services/chat-service/app/ .../test_cp0_instrument.py` is
**empty**.

Four cells, executed in `wt-b` by byte patch and byte restore (`w4_probe.py`):

```
1  shipped  / file as-is         rc=0   137 passed
2  REVERTED / file as-is         rc=0   137 passed          <- 0/1 red-able, eighth round
3  shipped  / + proposed test    rc=0   139 passed
4  REVERTED / + proposed test    rc=1   1 failed, 138 passed
       FAILED …::TestW4TryBodyArmIsNotUnconditional::test_a_try_body_arm_AFTER_another_statement_is_not_unconditional
restore sha ok: True
```

Applicable form — 30 lines, appended at end of file, no new import, **writes no file into `app/`**
(unlike the six existing probe tests, so it does not reproduce the 6-round-old probe-module
finding), and asserting **both** directions so it also reds if `Try` is narrowed to nothing:

```python
class TestW4TryBodyArmIsNotUnconditional:
    """W4 - a `try` is entered unconditionally, so its FIRST statement runs. The SECOND runs only
    if the first did not raise, which is the whole reason the `try` is there. `s.body[:1]` at
    :2284 is that rule and it has never had a test; reverting it to `s.body` leaves this file
    fully green, measured for eight consecutive rounds."""

    @staticmethod
    def _pred(c):
        return (getattr(c.func, "id", None) or getattr(c.func, "attr", None)) == "arm_turn_surface"

    def test_a_try_body_arm_AFTER_another_statement_is_not_unconditional(self):
        import ast as _a
        late = _a.parse(
            "async def p(c):\n"
            "    try:\n"
            "        prelude()\n"
            "        arm_turn_surface()\n"
            "    except Exception:\n"
            "        pass\n").body[0]
        assert list(_unconditional_calls(late.body, self._pred)) == [], (
            "an arm that is the SECOND statement of a `try` body is reachable only if the first "
            "did not raise, so it is not unconditional; `s.body` (the revert) accepts it"
        )

    def test_a_try_body_arm_that_is_the_FIRST_statement_still_counts(self):
        import ast as _a
        first = _a.parse(
            "async def p(c):\n"
            "    try:\n"
            "        arm_turn_surface()\n"
            "    except Exception:\n"
            "        pass\n").body[0]
        assert len(list(_unconditional_calls(first.body, self._pred))) == 1, (
            "a `try` body is ENTERED unconditionally, so its first statement runs; narrowing "
            "`Try` to nothing would make this gate blind to the only shape it should accept"
        )
```

**Eighth round. Two verifiers have now written it, executed it, and shown it red on the revert.
There is no remaining reason for it not to exist.**

## 3.2 · The recorder hazard, **5th round** — the V-LIVE observation, one sentence

Re-executed independently on the frozen tree with the file's own API (`recorder_probe.py`):

```
_O_K()                                       -> True    (a PASSING test at :2934 asserts this is True)
turn B, no recorder                          -> False   (the shipped test asserts False)
turn A's recorder, asked directly            -> True
catalogue_outage_registered(rec_a) in turn B -> True    <- THE HAZARD; no test writes this line
```

Byte-identical to R23-A's measurement and still unfalsifiable at this seam: the two executions differ
in **no ContextVar**, only in which recorder object the reader holds, and
`type(recorder) is AdvertisedToolsRecorder` (`instrument.py:580`) is the only bound. A test that drove
the hazard would red `_O_K`, which passes.

> **The sentence a CP-2 harness can implement:** stamp a fresh `uuid4` **turn token** into a
> ContextVar at every `arm_turn_surface()` and log `(token, id(recorder))` at the read site
> `voice_stream_service.py:422`; **the harness passes if and only if no `AdvertisedToolsRecorder`
> object id ever appears under two distinct turn tokens.** Drive it against two concurrent voice
> requests on one session, one turn re-entered by retry/reconnect, and one `O_J` shape (records and
> never arms). **If NO** — the design premise holds and this closes as a non-defect. **If YES** —
> `_O_K` asserts U-2's founding defect as the requirement.

**Fifth round, and it remains the only open item on this seam that more V-CODE cannot move.**

## 3.3 · The weak oracles (**8th**), T11d (**6th**), the probe writers (**6th**), the mirrors

**The three weak oracles — measured over the ENUMERATED assertion space, not a hand-picked pair.**
`oracle_probe.py` walks every `pytest.raises(..., match=...)` in the file, resolves the gated callee,
and counts the callee's `assert` messages containing the match token:

```
oracle@line          match   gated callee                                              matching asserts
      3242  withheld_tools   test_EVERY_TERMINAL_WRITE_BINDS_THE_DRAINED_VALUE…        2  <-- CANNOT BIND THE PROBE
      3297  withheld_tools   (same callee)                                             2  <-- CANNOT BIND THE PROBE
      3312  could not be parsed  (same callee)                                         1
      3376  withheld_tools   (same callee)                                             2  <-- CANNOT BIND THE PROBE
```

The second matching message is the callee's own **no-vacuity anchor guard** at `:1700` — *"only N
bind(s) of `withheld_tools` were found: … The gate's anchor stopped matching."* So each of the three
oracles is satisfied by a gate that fired **because its own anchor broke**, not because the probe was
detected. Reachability: **production** — a one-token refactor at a live SQL site breaks the anchor
and turns two of them green over an unmeasured probe. *(Line correction: R23-A cited `:3374`; the
`with` is at `:3376`. File byte-unchanged.)*

**The fix is three string literals — and the file already demonstrates it eight lines away**, at
`:3312`, where `match="could not be parsed"` binds uniquely (count 1).

**T11d, 6th round.** `stream_service.py:6297` — the orphan-stamp branch interpolates
`f"       {instrument.segment_merge_sql('withheld_tools')} "` into the SQL and the matcher resolves
the literal rather than the constant. Byte-unchanged in the delta. *(Read and located; not
re-driven — the gating mechanics were driven in R20/R22 and the file has not moved since.)*

**The probe writers, 6th round.** Seven writers hardcode `parents[1] / "app"` — `:24`, `:2085`,
`:3047`, `:3077`, `:3230`, `:3279`, `:3308` — while `_TURN_SCOPE_ROOT = "app"` sits at `:2151` and
only **two** sites use it (`:1626`, `:2295`). Counts re-derived this round, unchanged. Reachability:
**CERTAIN**; every run writes untracked modules into `app/agentruntime/`, `app/routers/` and
`app/services/`, and a kill in that window leaves them behind.

**The unremoved mirrors — 6.71 GB is now 7.37 GB, and they are no longer inert.** Measured:

```
mirrors: 108     bytes: 7,916,089,890   (7.37 GB)
```

`_mirror()` has no `rmtree`, on any path. And I measured, accidentally and then deliberately, that a
mirror is not merely disk waste: `agentruntime-membrane-gate._forgery_scan` walks `REPO.rglob("*.py")`,
so **a mirror inside the repo makes the membrane suite RED** (6 forgery violations reported against
`lw-census-*/services/chat-service/app/agentruntime/admission.py`), which makes `_selftest` fail with
`SELFTEST FAIL: the suite is not green before any injection`, which makes the census un-runnable. That
is the reachability verdict for N06, and it upgrades this item from cosmetic to **blocking**. One line
fixes it: `shutil.rmtree(mirror, ignore_errors=True)` in a `finally` around `census()`'s body.

---

# 4 · TABLES

## 4.1 · Bypass table — **21 disable-class mutations, 19 bypasses, all executed**

| # | bypass | executed | result |
|---|---|---|---|
| **The write-watch (`test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE`)** | | | |
| A1 | live neuter+restore via `open(path,"wb")` | ✅ N02 | **GREEN** ❌ |
| A2 | live neuter+restore via `write_text` | ✅ N09 | **GREEN** ❌ |
| A3 | `shutil.copyfile` → `os.link`: the mirror **is** the live tree | ✅ N04 | **GREEN** ❌ — 68/68 live files mutated |
| A4 | `_selftest()` writes into the live package | ✅ N07 | **GREEN** ❌ |
| A5 | live neuter via `os.replace` of a temp file | ✅ N03 | RED — but my temp file used `write_bytes` in the live dir; **not an independent negative** |
| A6 | mirror removed for the package | ✅ N01 | RED ✅ |
| A7 | `_mirror` renamed (R23's dead control) | ✅ N05 | RED ✅ |
| A8 | mirror inside the repo | ✅ N06 | RED ✅ |
| A9 | suite run against the live chat-service | ✅ N08 | RED ✅ |
| **The CI guard (`test_THE_CENSUS_IS_WIRED_TO_RUN_IN_CI`)** | | | |
| B1 | step-level `if: false` | ✅ M01 | **GREEN** ❌ |
| B2 | step-level `if:` on an impossible event | ✅ M02 | **GREEN** ❌ |
| B3 | **job**-level `continue-on-error: true` | ✅ M03 | **GREEN** ❌ |
| B4 | `needs:` a skipped job | ✅ M04 | **GREEN** ❌ |
| B5 | `on:` drops `pull_request` | ✅ M05 | **GREEN** ❌ |
| B6 | `on:` becomes `workflow_dispatch` | ✅ M06 | **GREEN** ❌ |
| B7 | **the run line is a shell comment** | ✅ M07b | **GREEN** ❌ (4th comment instance) |
| B8 | `true # …` | ✅ M16 | **GREEN** ❌ |
| B9 | `echo …` | ✅ M08 | **GREEN** ❌ |
| B10 | `--help` | ✅ M09 | **GREEN** ❌ |
| B11 | `… \| cat` (single pipe) | ✅ M10 | **GREEN** ❌ |
| B12 | `… &` | ✅ M11 | **GREEN** ❌ |
| B13 | `set +e; …; true` | ✅ M12 | **GREEN** ❌ |
| B14 | nonexistent interpreter | ✅ M13 | **GREEN** ❌ |
| B15 | `uses:` a composite + a decoy `echo` | ✅ M14 | **GREEN** ❌ |
| B16 | `--selftest --help` | ✅ M15 | RED ✅ |
| B17 | C01–C07 (delete step / rename job / `--write` / `\|\| true` / job `if` / step `continue-on-error` / no pytest) | ✅ ×7 | **RED ✅ 7/7** |
| **The instrument itself** | | | |
| C1 | run `census()` inside a mirror (what the census does 68×) | ✅ | **`_suite_is_green` = False, unconditionally** |
| C2 | run the census to completion, clean tree, frozen sha | ✅ | **68 sites, 0 silent, 68 red, rc=1, 13 false NOW GUARDED** |
| C3 | run the mirror suite with **nothing** neutered | ✅ | **RED** — the selftest's positive control is vacuous |
| C4 | reorder two same-key same-shape raises | ✅ | id set unchanged; the allowlisted row renames its subject |
| C5 | reword every string in the package, 5 id variants | ✅ ×5 | **0 ids move in all five** |
| C6 | rename every local, 5 id variants | ✅ ×5 | ~100 % move in all five, **shipped included** |
| **Carried** | | | |
| D1 | revert W4's `s.body[:1]` | ✅ | **137 passed** — 8th round |
| D2 | append the proposed W4 test, then revert | ✅ | **1 failed, 138 passed** |
| D3 | hand turn A's recorder to turn B | ✅ | **True** — 5th round |
| D4 | enumerate the oracle-binding space | ✅ | **3 of 4 oracles cannot bind their probe** |

## 4.2 · Red-ability table — **my denominator**

My denominator is the **enumerated disable-class mutation space of the two guards the delta added**,
because those two guards are the delta. Not a sample: the space was enumerated from the structural
degrees of freedom each guard reads (write APIs × target-selection × subject for the watch; workflow
triggers × job keys × step keys × run-string content for the CI half).

| subject | denominator | red-able | rate |
|---|---:|---:|---:|
| the write-watch, disable-class | **5** | 1 (and that one only because my mutation supplied a live `write_bytes`) | **0–1 / 5** |
| the write-watch, controls | 4 | 4 | 4/4 ✅ |
| the CI guard, disable-class | **16** | 1 | **1 / 16** |
| the CI guard, controls | 7 | 7 | 7/7 ✅ |
| **the two new guards, disable-class, combined** | **21** | **2** | **2 / 21 = 9.5 %** |
| W4's `s.body[:1]` (8th round) | 1 | 0 | **0/1** |
| **the census itself** — can it distinguish a guarded refusal from an unguarded one? | 68 | **0** | **0/68** — every site reads RED, including all 13 it allowlisted as SILENT |

The last row is the one that decides the verdict. An instrument with 0/68 discrimination is not a
gate that can be bypassed; it is a gate with no subject.

## 4.3 · Sibling table — *"a fix landing on the sibling of the site a verifier named"*

| the named site | the sibling the fix did not reach | round |
|---|---|---|
| `'python scripts/…' in job` defeated by a **YAML comment** | the same string defeated by a **shell comment inside the parsed `run:` scalar** (M07b) | **now** |
| step-level `continue-on-error` (asserted) | **job**-level `continue-on-error` (M03) | now |
| **job**-level `if` (asserted) | **step**-level `if` (M01/M02) | now |
| `--write`, `--selftest`, `\|\|` (blocked) | `\|`, `&`, `;`, `set +e`, `--help`, `echo`, a nonexistent binary | now |
| `census()`'s write path (watched) | `_selftest()`'s write path (N07), and `.pytest_cache`/`__pycache__` in the live package | now |
| `Path.write_bytes` (watched) | `open`, `write_text` — and `os.link`, which keeps the API and moves the inode | now |
| `_shape_digest` fixes the reorder failure | the 8 sites where the shapes are equal, i.e. the only ones a reorder can hurt | now |
| the mirror ends the live-tree write | the mirror is never removed, and one inside the repo reds the membrane suite | 2nd |
| `_TURN_SCOPE_ROOT` (2 users) | 7 writers hardcoding `"app"` | 6th |
| `match="could not be parsed"` binds uniquely at `:3312` | `match="withheld_tools"` at `:3242`, `:3297`, `:3376` does not | 8th |

## 4.4 · Guard table

| guard | asserts | executes? | can it fail? | verdict |
|---|---|---|---|---|
| `test_THE_CENSUS_DOES_NOT_WRITE_INTO_THE_LIVE_TREE` | no live-tree `Path.write_bytes`; `after == before`; results non-empty; suite cwd outside repo | **YES** — real `census()`, 68 sites | yes, 4/4 controls | **real, and a proxy on the API rather than the inode; 4/5 bypass shapes green; its docstring describes a two-site fixture package that does not exist; and running it inside a mirror is what breaks the census** |
| `test_THE_CENSUS_IS_WIRED_TO_RUN_IN_CI` | job exists; no job-level `if`; a `run` mentions the script; no `--write`/`--selftest`/`\|\|`; no step `continue-on-error`; pytest installed | parses YAML | yes, 7/7 controls | **15/16 disable shapes green; the `run:` value is still a substring test, so the comment defect moved down one level** |
| `_selftest()` — enumeration ≥ 50 | live package | yes | yes | real |
| `_selftest()` — "the suite is green before any injection" | live tree | yes | yes | real; and it is what caught **my own** litter |
| `_selftest()` — "neutering a guarded refusal reds the suite" | mirror | yes | **NO** | **VACUOUS** — measured true over an unmodified mirror |
| `census()` — RED/SILENT per site | mirror | yes | — | **CONSTANT `RED`, 68/68** |

## 4.5 · Reachability verdict on every finding

| id | finding | site | reachability |
|---|---|---|---|
| **A24-1** | the census reports 68 red / 0 silent, rc=1, and 13 false `NOW GUARDED` lines | `test_cp1_membrane.py:2145`, `agentruntime-census.py:87` | **CERTAIN — production CI, blocking job, every PR** |
| **A24-2** | `_selftest`'s positive control fires on an unmodified file | `agentruntime-census.py:239–256` | **CERTAIN** — it is the shipped path |
| **A24-3** | the write-watch is keyed on the API and the path, not the inode; `os.link` → 68/68 live files mutated with all 4 assertions green | `test_cp1_membrane.py:2160–2175` | **production** — a one-token "optimisation" of a 2-minute copy |
| **A24-4** | `open`/`write_text`/`_selftest` write paths are unwatched | same | **production** |
| **A24-5** | 15 of 16 CI disable shapes green; incl. a **shell comment** (4th instance) | `test_cp1_membrane.py:2205–2230` | **production** — one line of YAML |
| **A24-6** | the guard's docstring describes a two-site fixture package that does not exist | `test_cp1_membrane.py:2136` | documentation; **but it is the design that would have prevented A24-1** |
| **A24-7** | 8 sites separated by position alone; the `_sites` docstring's claim is false of them | `agentruntime-census.py:154–163` | **latent** — no rc consequence today (no both-silent group); on a mixed pair a reorder emits a false `NOW GUARDED` |
| **A24-8** | an injective, prose-blind, ordinal-free id is achievable (68/68, 0 prose churn) — *not a defect, a refutation of the framing* | — | n/a |
| **A24-9** | 108 mirrors / 7.37 GB never removed; one inside the repo reds the membrane suite and blocks the census | `agentruntime-census.py:86` | **CERTAIN** (disk) / **CERTAIN** (blocking, measured) |
| **A24-10** | the census's wall-clock went ≈3 min → ≈17 min; a naive fix makes it ≈1 h | `agentruntime-census.py:213` | **CERTAIN** |
| carried | W4 `s.body[:1]` has no test, 0/1 red-able | `test_cp0_instrument.py:2284` | **production** — the gate accepts a conditional arm |
| carried | the carried-recorder hazard | `instrument.py:579–580`, `voice_stream_service.py:422` | **undecidable from source — 5th round; needs V-LIVE** |
| carried | three weak oracles cannot bind their probe | `test_cp0_instrument.py:3242, 3297, 3376` | **production** |
| carried | T11d resolves the literal, not the constant | `stream_service.py:6297` | production |
| carried | 7 probe writers hardcode `"app"` | `test_cp0_instrument.py:24, 2085, 3047, 3077, 3230, 3279, 3308` | **CERTAIN**, consequence moderate |
| carried | `:531` "Ask the turn's RECORDER first" vs `:542` "Read from the FLAG first" | `instrument.py:531, 542` | **10th round**, documentation |

## 4.6 · Falsifier per claim

| claim | falsifier |
|---|---|
| the delta breaks the census | run `python scripts/agentruntime-census.py` on a clean checkout of `b5d81e54a`; a non-`68 red / 0 silent` result falsifies me |
| the selftest's positive control is vacuous | build a mirror with `_mirror()`, change **nothing**, run the membrane suite there; rc=0 falsifies me |
| the write-watch is a proxy | apply `shutil.copyfile → os.link` and run the guard; a RED falsifies me |
| 15/16 CI disable shapes are green | re-run `wf_sweep.py`; any RED in the GREEN column falsifies me |
| 8 sites are separated by position alone | drop the ordinal from the id and count distinct ids; 68 falsifies me (measured: 64) |
| an injective prose-blind id is achievable | re-run `id_variants.py`; V3/V4 showing <68 distinct or >0 prose churn falsifies me |
| W4 is 0/1 red-able | revert `s.body[:1]` → `s.body` and run the file; any failure falsifies me |
| the recorder hazard | `catalogue_outage_registered(rec_a)` in a fresh turn returning `False` falsifies me |
| the three oracles cannot bind their probe | show the callee has exactly one reachable `AssertionError` message containing `withheld_tools` |
| **the whole verdict** | it rests on one number I can be wrong about: `_suite_is_green` inside a mirror. It is measured twice, by two independent routes (a direct probe and a full census run), on a tree verified clean by `git status --untracked-files=all` = 0 |

---

# 5 · EXECUTED vs ARGUED

| | count |
|---|---:|
| claims **executed** | **31** |
| claims **argued from reading only** | **4** |
| **ratio** | **31 : 4 (89 % executed)** |

Executed: 25 workflow mutations, 10 census-script mutations, the `os.link` four-assertion proof, the
mirror-recursion probe, two full census runs, one full live membrane-suite run, four W4 cells, the
68-site id enumeration, 5 id variants × 3 edit classes, the reorder probe, the oracle-space
enumeration, the recorder probe, the mirror inventory. **Total distinct process executions: 52.**

Argued from reading only: T11d (`stream_service.py:6297`, file byte-unchanged for 6 rounds); the
`:531`/`:542` comment contradiction; the claim that GitHub runners' temp dir is not a git repo
(reasoned from the runner layout, measured only on Windows and on this machine's `/tmp`); and the
CI-consequence chain for A24-1 (I measured rc=1 locally and reasoned that a blocking job with rc=1
fails the check).

**A note on my own denominator.** R23-A reported 29 bypasses at a ratio it did not have to defend
against a wrong-answer finding. I want to be explicit that **19 green bypasses is the less important
half of this verdict.** A bypass is a claim about what a *future* editor could do. A24-1 is a claim
about what the artifact does **now**, and I would trade all nineteen for it.

---

# 6 · CONVERGENCE

Findings introduced per round, this run: `2, 1, 2, 1, 3, 2, 4, 3, 2, 2, 2, 5, …, 9 (R23-A), 10
(R24-A)`.

**Seventeen rounds, no convergence — and the trend is the wrong way.** The delta under grade is 163
lines in one test file, the smallest of the run bar one, and it produced the highest finding count of
the run. R23-A recorded exactly this shape twelve rounds ago ("the maximum on the *smallest* delta")
and the census was built to end it.

| measure | R22 | R23 | **R24 (mine)** |
|---|---|---|---|
| findings introduced | 5 | 9 | **10** |
| of which make the artifact produce a **wrong answer today** | 0 | **0** (R23-A's own words) | **2** (A24-1, A24-2) |
| bypasses measured green | 8 | 8 | **19** |
| disable-class red-ability of the newest guards | — | — | **2/21 = 9.5 %** |
| carried items closed | — | 6 of 9 | **0 of 6** |
| rounds W4 has been open | 6 | 7 | **8** |
| rounds the recorder hazard has been open | 3 | 4 | **5** |
| GB of unremoved mirrors | — | 6.71 | **7.37** |

**Where the divergence lives, and it is not where three rounds of prompts have assumed.** The
census was built on the observation that exactly one measurement converged — the AST enumeration of
68 sites. That is still true: three verifiers and now a fourth agree on 68, member for member. But
the census does not gate on the enumeration. **It gates on `_suite_is_green`, which converged with
nobody, was never itself enumerated, and is now a constant.** Every round has graded the census's
*id*; no round until this one ran the census and read its output. The single highest-value change
available is not a better digest and not a tighter guard — it is a CI step that prints the census's
own summary line and a test that asserts `0 < silent < 68`.

## 6.1 · **Do I support closing CP-1 against the census? No — at no scope.**

R23-A supported closing against the census with two checks. R23-B qualified that to the 55 RED sites
only. **Both scopes are defined by a partition the artifact no longer produces.** At `b5d81e54a` the
census's answer is `68 red, 0 silent` — it does not have 55 RED sites and 13 SILENT ones; it has 68
undifferentiated ones and an exit code of 1. Closing a finding against it today would mean recording
"this named site moved SILENT → RED" for thirteen sites that moved because the instrument stopped
working.

**What would change my answer**, in order:

1. Fix A24-1 so `_suite_is_green` is a function of its input again, and **re-run the census**; if it
   reproduces `55 red, 13 silent` against the committed allowlist, the partition is restored.
2. Add the assertion that makes A24-2 impossible: `_selftest` must check that the **unmodified**
   mirror is green *before* it checks that a neutered one is red. Two lines, and it is the difference
   between a selftest and a formality.
3. Add the `0 < silent < 68` band assertion to the CI step. An all-red and an all-silent census both
   read as "the gate ran" today.
4. Then, and only then, the id (§2.2) and the bypasses (§4.1), which are real but are about the
   next editor rather than about this artifact.

Steps 1–3 are together under 20 lines. **I would grade a delta containing only those three as a
stronger round than this one.**

---

# 7 · THE VERIFICATION METHOD AS A SOURCE OF CONTAMINATION — TWO NEW OBSERVATIONS

The prompt asked B to judge this. I have two measurements to contribute.

**7.1 · I contaminated my own worktree, caught it, and it changed a conclusion.** My N06 mutation
(`mkdtemp(dir=ROOT)`) left an `lw-census-*` directory inside `wt-a`. My sweep restored the script's
bytes and the package's bytes and verified both by sha — and still left the mirror, because I had
snapshotted *files*, not the *directory listing*. The next thing I ran was the full census, which
reported `SELFTEST FAIL: the suite is not green before any injection`, and for several minutes I had
a false root cause. `git status --untracked-files=all` found it. **A byte-snapshot of the files you
patch is not a snapshot of the tree you patched.** The rule I would add: verify a restore with
`git status --untracked-files=all` = 0, not only by sha.

**7.2 · The shared worktree was rewritten under me, again — this time the census's own suite.**
At session start `D:\Works\source\lore-weave\services\chat-service\tests\test_cp1_membrane.py`
hashed `2994774d…`; at session end it hashes `fceea74b…` and `git status` reports ` M`. I never
touched the shared tree. The diff, verbatim:

```diff
@@ -2142,6 +2142,8 @@ class TestStageKindsAreDataNotClosures:
         import pathlib
+        if not (_REPO / ".git").is_dir():
+            pytest.skip("no .git: this is a census mirror, not the live tree")
```

Three things follow. **(a)** A24-1 was found independently by a concurrent process during this
window, which is corroboration I did not arrange. **(b)** It is *not* in the frozen artifact and my
verdict grades the frozen artifact; the census at `b5d81e54a` is broken. **(c)** Grading the patch
anyway, because it will land: it is the right *shape* — the guard's subject is the live run and there
is no live tree inside a mirror — but it is a **silent skip**, and this run has a note that
skip-by-default suites rot. It needs a companion assertion that the skip is reachable *and* that the
non-skip path ran at least once per suite invocation, or the census's 68 inner runs will report a
green suite while the guard has silently evaporated, which is the vacuous-green shape one level
further down. It also does not address A24-2: the selftest's positive control is still satisfied by
an unmodified mirror only *because* the suite was red there; with the skip it becomes satisfied only
if the neutering really reds — so the skip **fixes** A24-2 as a side effect, and nothing in the patch
says so or tests it.

**7.3 · And at the moment I finished, the shared tree contained a live bypass injection.**
`git status` on `D:\Works\source\lore-weave` reports ` M scripts/agentruntime-census.py`, six
insertions I did not make:

```diff
-    pkg, cs = mirror / _PKG_REL, mirror / _CS_REL
+    pkg, cs = PKG, mirror / _CS_REL
-            path.write_bytes(_neutered(src, node).encode("utf-8"))
+            (_tmp := pathlib.Path(_tf.mkdtemp()) / "x").write_bytes(…) or _sh.copyfile(_tmp, path)
```

That is the live package neutered through `shutil.copyfile` — **the same bypass class I measured as
N02/N04**, being exercised by the concurrent verifier at this instant. I did **not** restore it: I
hold no snapshot of it, and reverting another verifier's in-flight mutation is the contamination
hazard running in the other direction. It is recorded here so that whoever reads the shared tree next
knows the file is mid-experiment and is not the artifact. It also corroborates A24-3/A24-4
independently.

**Is the method itself a source of contamination? Yes, measurably, three times in one session, and
it is cheap to stop.** Two detached worktrees cost ~90 s each to create and made every measurement in
this verdict reproducible in isolation. **Neither verifier should measure in the shared tree again**,
and no verdict that measured in it during this window — including any that reports the census's
RED/SILENT partition — should be trusted without a re-run in a private checkout.

---

# 8 · SUMMARY OF FINDINGS

| id | finding | site | severity |
|---|---|---|---|
| **A24-1** | **the graded delta breaks the census: 68 red / 0 silent / rc=1 / 13 false `NOW GUARDED` lines**, because the guard it added recurses into `census()` inside a mirror that has no `.git` | `test_cp1_membrane.py:2145`; `agentruntime-census.py:87` | **BLOCKING** |
| **A24-2** | `_selftest`'s positive control fires on an unmodified mirror — the harness cannot **not** fire | `agentruntime-census.py:250` | **BLOCKING** |
| **A24-3** | the write-watch is keyed on the write API and the path, not the inode: a hardlinked mirror mutates 68/68 live files with all four assertions green | `test_cp1_membrane.py:2160` | high |
| **A24-4** | `open(...,'wb')`, `write_text`, and everything `_selftest` does are unwatched | `test_cp1_membrane.py:2160` | high |
| **A24-5** | 15 of 16 enumerated CI disable shapes green, incl. a shell comment (**4th** comment instance, inside the repair for the 3rd) | `test_cp1_membrane.py:2205` | high |
| **A24-6** | the guard's docstring describes a two-site fixture package that does not exist — and that design would have prevented A24-1 | `test_cp1_membrane.py:2136` | medium |
| **A24-7** | 8 of 68 sites are separated by position alone; `_sites`' docstring claims otherwise | `agentruntime-census.py:154` | medium (latent) |
| **A24-8** | *refutation:* an injective, prose-blind, **ordinal-free** id is achievable — 68/68 distinct, 0 prose churn, ~15 lines | — | — |
| **A24-9** | 108 mirrors / **7.37 GB** never removed; one inside the repo reds the membrane suite and blocks the census | `agentruntime-census.py:86` | high |
| **A24-10** | the census's wall-clock ≈3 min → ≈17 min, and a naive fix makes it ≈1 h | `agentruntime-census.py:213` | medium |

Carried, unchanged, none closed: **W4 (8th, 0/1 red-able)**, the carried-recorder hazard (5th),
**the three weak oracles (8th)**, T11d (6th), the seven probe writers (6th), the `:531`/`:542`
contradiction (**10th**).

---

`git rev-parse HEAD` **at finish: `b5d81e54ad6fed9134758b02e8d4bb66e1691a25`** — unchanged.

Both measurement worktrees ended at `git status --porcelain --untracked-files=all` = **0** and were
removed. **My footprint on the shared worktree is exactly one file: this verdict.** The two
modifications `git status` shows there at this instant — `test_cp1_membrane.py` (+2) and
`agentruntime-census.py` (+6/−3) — are a concurrent process's and are documented in §7.2–7.3; I have
not touched, restored, or committed either. Nothing is committed.
