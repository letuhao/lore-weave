# Non-Vacuity — a check must be ABLE to fail, and you must have watched it

> **Status:** LOCKED 2026-07-29. Rules `NV-1..NV-6`.
> **Scope:** every gate, lint, test, `const` assertion, validator, and axiom in this repo.
>
> **Why this file exists, and it is the whole argument:** three separate design documents already
> cite *"the repo's non-vacuity discipline"* as though it were a standard —
> [`27:322`](../03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md),
> [`27:504`](../03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md),
> [`34:497`](../03_planning/LLM_MMO_RPG/34_when_the_world_runs.md) — and **it had no authoritative
> home**. A grep of this index and `CLAUDE.md` for *non-vacuity / vacuous / unfalsifiable / bite-test*
> returned **zero hits**.
>
> That is the repo's own `rule + SoT + gate + test` meta-pattern **with the SoT missing**. The
> consequence is measurable: the same defect shipped **twenty-seven times** (§4), each fixed locally in the
> place it happened, because the next person had no page to read. This is that page.

---

## 1. NV-1 — the rule

> **NV-1. A check that cannot fail is not a check. It is a claim, wearing the costume of evidence.**
>
> Before a gate, test, assertion or validator is considered done, **make the thing it guards wrong and
> watch it go red.** Then put it back. Record the failure text.

The asymmetry that makes this urgent, and the reason it outranks "add more tests":

> **A vacuous check is WORSE than no check at all.** No check is honest about its absence — someone
> reading the file sees nothing and knows nothing is guarded. A vacuous check reports **coverage**.
> It is read as a settled question, it silences review, and it survives precisely because it is
> always green.

---

## 2. NV-2..NV-5 — the four shapes, each with a real occurrence

Every instance in §4 is one of these four. They are listed in order of how hard they are to see.

### NV-2 — the subject cannot vary

The check runs, on the right thing, and the thing is structurally incapable of the state that would
fail it.

> **Occurrence.** `QTY-A12` requires `const _: () = assert!(size_of::<T>() <= BUDGET)`. `QTY-A6`, two
> sections away in the same document, made array width a **runtime** per-reality constant — which puts
> the payload behind a pointer, so `size_of::<Box<[i32]>>()` is **16 bytes for `n = 3` and for
> `n = 500`, on every target, forever.** The assertion compiles, always passes, and can never fire.
> *(Reversed: `35 §4.2`.)*

**Tell:** you cannot describe, concretely, an input that reddens it.

### NV-3 — the scope never reaches it

The check is genuinely capable of failing, and never runs on the code that would fail it. Almost
always caused by an **enumerated list where a rule was needed** — *default-uncovered*.

> **Occurrence A.** `hot-path-gate.py` scoped both its checks to a hand-listed set of step files. A
> **new** file — the `resources.rs` that `Q2` will add — is not on the list, so it could declare the
> exact banned map and the gate would say nothing. *(Fixed: declaration check now covers whole
> directories, so a new file is guarded the day it is created.)*
>
> **Occurrence B.** The publisher live smoke hand-picked **2 of 16** per-reality migrations, so every
> column added after `0005` was invisible to it. It had been **red for two days** against a schema two
> migrations behind production, and nobody knew. *(Fixed: the helper globs the directory.)*

**Tell:** the scope is a list of names rather than a predicate. Ask *"what happens to a file created
tomorrow?"* — if the answer is "nothing", the polarity is wrong.

### NV-4 — an adjacent decision defeats it

The check is real, in scope, and runs — and a **different** rule elsewhere makes its subject
permanently conforming, or makes conforming impossible. **This is the hardest to see, because both
decisions are individually correct.**

> **Occurrence.** `QTY-A11` said the decoder should accept a short array and fill the tail from
> defaults. `RulesetStore::get` re-digests the **decoded** value (deliberately — *"this checks the
> decoder too"*). Together: an old artifact decodes wide, re-encodes to different bytes, hashes
> differently, and **the store rejects its own file**. The axiom written to stop a reality becoming
> `Unloadable` would have made every reality `Unloadable`. *(Corrected: `35 §6.3`.)*

**Tell:** you changed a rule to *enable* something a checker inspects. Re-read the checker.

### NV-5 — the escape hatch cannot reach its reason

An exemption mechanism whose window is narrower than the justification it is meant to carry, so the
pragma silently does nothing and the finding is reported **with and without it**.

> **Occurrence — three times, three gates.** `closed-set-gate`, `zero-digest-gate` and
> `db-safety-gate` each shipped a **fixed one-line-above** pragma window. In `zero-digest-gate` the
> one live finding's real justification sat **eleven lines up**, so the bite-test that "proved" the
> pragma worked reported the finding either way. *(All three now walk the contiguous comment block
> upward.)*

**Tell:** the window is measured in lines. A reason worth exempting for is longer than one line, and a
narrow window pushes authors toward a terse pragma or toward `--no-verify`.

---

## 3. NV-6 — the obligation, and what counts as discharging it

> **NV-6. The bite-test is not optional and its OUTPUT is the deliverable.** *"I added a test"* is not
> evidence. *"I broke X, the check said Y, I put X back"* is.

| | Required |
|---|---|
| **A new gate / lint** | a `--self-test` that fails if the checker reports nothing on a broken fixture, **and** one run against the **real** tree with a real violation injected. A fixture-only proof does not show the scope is right (NV-3). |
| **A new test** | run it against the un-fixed code first, or revert the fix and re-run. Paste the failure. |
| **A `const` assertion** | make the guarded thing exceed the bound and paste the compile error. |
| **A pragma / exemption path** | remove the pragma, confirm the finding returns, restore it. This is the only proof the window reaches (NV-5). |
| **An axiom that constrains code** | name the check that would go red if a future edit broke it. If none exists, **that missing check is itself the finding** — it does not become true by being written down. |

**Where the output goes:** the VERIFY evidence string, the commit message, and — for anything
load-bearing — a line in the test or gate saying what was broken and what it said. A bite-proof
recorded nowhere has to be re-done by the next reader, which means it will not be.

### 3.1 The question to ask, in order

1. **Can I state an input that reddens this?** (no ⇒ NV-2)
2. **Will it run on code written tomorrow?** (no ⇒ NV-3)
3. **Did I just change a rule this checker depends on?** (yes ⇒ NV-4)
4. **Can the exemption carry a real reason?** (no ⇒ NV-5)
5. **Have I watched it fail?** (no ⇒ NV-6)

---

## 4. The register — twenty-seven occurrences, one caught by a test

Kept because the count is the argument. **Twenty-six of the twenty-seven were found by a human or an agent
reading carefully.** The other was caught by clippy — not by the test suite, which was green
throughout, but by a linter that happened to constant-fold the expression. That is the exception NV-1
predicts the shape of: a vacuous check is invisible to *testing* by construction, and only something
that inspects the check itself can see it.

| # | Occurrence | Shape | Found by | Status |
|---|---|---|---|---|
| 1 | `closed-set-gate` pragma window | NV-5 | review | fixed |
| 2 | `zero-digest-gate` pragma window (justification 11 lines up) | NV-5 | bite-test of the bite-test | fixed |
| 3 | `db-safety-gate` pragma window | NV-5 | blocked a commit | fixed 2026-07-29 |
| 4 | `hot-path-gate` scope default-unguarded | NV-3 | self-review, 12-case matrix | fixed 2026-07-28 |
| 5 | publisher live smoke: 2 of 16 migrations | NV-3 | running it | fixed 2026-07-29 |
| 6 | `QTY-A6` ⊥ `QTY-A12` | NV-4 | red team (3 of 4 agents, independently) | A6 reversed |
| 7 | `QTY-A11` ⊥ `store.get` re-digest | NV-4 | reading the code to build it | corrected 2026-07-29 |
| 8 | LOCKED layer order is unfalsifiable ([`27 §9.5`](../03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md)) | NV-2 | stress test | **open** |
| 9 | replay-correctness is vacuous ([`27:408`](../03_planning/LLM_MMO_RPG/27_extensibility_stress_test.md)) | NV-2 | stress test | **open** — F3 |
| 10 | artifact-matches-code test was HALF a test (a deleted field still passed) | NV-2 | deleting a field to see | fixed `4ac03cace` |
| 11 | `hot-path-gate`'s `LOOKUP_SCOPE` named three files a refactor then renamed — the read check matched **nothing** and reported OK | NV-3 | reading the gate while moving the files it named | fixed 2026-07-29 (`S2`) — directory prefixes |
| 12 | `assert!(!FORBIDDEN_KEYS.is_empty())` on a `const` — folded at compile time, could never fail | NV-2 | **clippy** (`const_is_empty`) | fixed 2026-07-29 (`S1a`) |
| 13 | `crate-purity-gate` R3 stripped `//` with a line regex, so a `//` **inside a string literal** ate the violation after it — the check never saw the code | NV-3 | `/review-impl` | fixed 2026-07-29 — one shared `gatelib.strip_comments` |
| 14 | the same gate's R2 checked only **direct** external deps, so an I/O crate added to `ruleset-core` reached the laws past R1 and R2 | NV-3 | `/review-impl` | fixed 2026-07-29 — widened to the workspace closure |
| 15 | the shared stripper was string-blind under `keep_strings=True` — the fork `hot-path-gate` runs — so a `//` inside a string ate the rest of the line and its findings with it | NV-3 | `/review-impl`, reviewing the FIX for row 13 | fixed 2026-07-29 |
| 16 | `db-safety-gate`'s shell selector was `"test" in base`, while the **same file's** `RE_THROWAWAY` had always accepted `smoke` — **six** DB-dropping smoke scripts were default-uncovered | NV-4 | writing a seventh and finding the gate silent on it | fixed 2026-07-29 (`Q1 B2a`) |
| 17 | `db-safety-gate`'s **file-level** pragma window `lines[:60]` — row 3 fixed the *inline* pragma window in this very file and left its sibling alone | NV-5 | the exemption landed at line 69 and was discarded | fixed 2026-07-29 (`Q1 B2a`) |
| 19 | four **meta** lints existed and **none was wired into pre-commit** — `service-acl-matrix-lint` was RED for a whole commit and nothing said so | NV-3 | `/review-impl`'s standards gate, running it by hand | 3 wired 2026-07-29; `meta-write-discipline` left out at ~74s, CI's job |
| 20 | **six `lint-foundation` legs RED on `main` since ≥2026-07-26, blocking, ignored** — `raw-sql-lint`, `injection-coverage-lint`, `language-bias-gate`, `pagination-cap-lint`, `dep-pinning-lint`, `capacity-budget-lint`. The gates ran, blocked and reported; nobody read the result | NV-3 (degenerate) | `gh run list` during the drift audit row 19 prompted | `scripts/gate-wiring-gate.py` + `.github/workflows/gates.yml` 2026-07-29; each failure now carries a `KNOWN_RED` row naming a deferral, and a row that turns GREEN fails the run |
| 21 | the drift audit's own first number — *"26 of 58 gates run nowhere"* — was **wrong**: `lint-foundation.yml` wires lints as matrices of BARE NAMES and a path-only search saw none of them. True figure: **3** | NV-3, committed BY the check | re-deriving it before writing it down | fixed same run; `_is_wired` matches stems as well as paths |
| 22 | **`deferral-gate` satisfied its own requirement by existing.** It demands every tracked deferral be named by non-comment source; its own `PROSE_ONLY` dict keys are string literals in a `.py` file, so on the first run every prose-only row reported STALE — *"the id is now named by scripts/deferral-gate.py"*. A registry that mechanises a debt by declaring it has no mechanism | NV-2, self-inflicted | running it once, before believing it | fixed 2026-07-29 — the gate excludes its own file |
| 23 | **a docstring is not a comment, and the stripper did not know.** The same gate stripped only LINE comments and certified **three** prose-only deferrals as MECHANISED: `D-META-LIVE-SMOKE-NOT-IN-CI` + `D-PUBLISHER-SMOKE-NOT-IN-CI` (whose sole non-`#` mention in the tree is `gate-wiring-gate`'s **module docstring**, where they are stated as a scope *limit*) and `D-GAME-WS-EDGE-CONTROLS` (three **JSDoc** headers). The first version had shipped a comment calling block comments "a known and stated limit" — the limit was the bug | NV-3 | bite-testing the discriminator instead of trusting it | fixed 2026-07-29 — `_strip` removes triple-quoted and `/* */` spans; the self-test reds if either arm is removed |
| 24 | **the two-segment id predicate could not see `D-START`.** Requiring `D-<WORD>-<WORD>` is what keeps `READ-ONLY`/`LOAD-BEARING` out (the naive version reported `D-ONLY` 54 times), but single-segment ids exist on the platform track and would have been **silently skipped inside a governed block** | NV-3 | comparing strict vs loose predicates on the real file | fixed 2026-07-29 — the shape is now ENFORCED: an unparseable backticked `D-…` inside a block FAILS with a rename instruction, so the hole is loud instead of confessed |
| 25 | **`RLS-I1` monotonicity was computed against a default.** `load_reality` returned `(Ruleset, RulesetDigest)` — reading the binding and **throwing its EPOCH away** — and `Island::new` then hardcoded `RulesetEpoch(1)`. A reality durably bound at epoch 5 ran on an island claiming epoch 1, so a redelivered switch to epoch **3** was `3 > 1` and **accepted**, moving the island onto rules the reality had already moved past. The guard written to prevent exactly that, defeated by the constructor | NV-4 | auditing `B2` against `B1b` immediately after both shipped — *"what connects the two epoch counters?"*, answer: **nothing** | fixed 2026-07-29 — the epoch travels WITH the rules (`load_reality` returns the binding) and `Island::new` takes it as a REQUIRED parameter, so the hole is a compile error at all 20 call sites |
| 26 | **`epoch-emit-trigger-gate` was VACUOUS while its self-test passed.** Its tree walk used a bare `git ls-files`, which cannot see a file that has not been `git add`ed — so a Go producer dropped into `admin-cli` and a string-only one into `game-server` were **both reported GREEN**. The self-test was green throughout because it only exercises the regexes in memory. **The identical defect had been fixed in `deferral-gate` hours earlier and was not carried across** — a sibling gate copied the shape without the fix | NV-3 | the tree-level bite, which is why `NV-6` demands it *as well as* the fixture — nothing else could have shown it | fixed 2026-07-30 — `--cached --others --exclude-standard`, plus a self-test arm that writes a real untracked probe file and fails if the walk cannot see it, so a third copy cannot repeat it |
| 27 | **`eventgen-validate` said PASS over a generated tree that is not in the repository.** `d0a5eecf4` committed the four BARRELS that name `ruleset_epoch_activated_v1` — `rust/mod.rs`, `python/__init__.py`, `ts/index.ts`, `registry_generated.go` — and left the three per-event modules they import **untracked**. The gate asked `git diff`, which compares the working tree to the index **for tracked files only**: a file git has never heard of is not a difference. Its subject was "files git already knows about", the one set that cannot contain the bug. Nothing consumes the Rust/TS/Python bindings yet, so nothing was red — which is why it would have stayed broken until the first consumer was wired in, on a machine where the file had never been generated. **This is row 26's untracked-blindness, recorded the previous day, in a third gate** | NV-3 | re-reading `git status` at a session boundary and asking why three generated files were still `??` after the commit that generated them | fixed 2026-07-30 — generation now goes to a temp dir and `diff -r` covers content + orphans + missing, plus an on-disk-minus-`git ls-files` check written in the POSITIVE direction (the `--others --exclude-standard` form would go vacuous the moment the tree were gitignored — NV-4). All four arms bite-tested; arm 4 red on the real defect before the fix |
| 18 | migration 033's append-only trigger was an ORIGIN trigger, so `session_replication_role = replica` (`pg_restore --disable-triggers`, logical-replication apply) skipped it — the UPDATE rewrote a bound digest and the DELETE removed the epoch | NV-3 | probing the guard in the one mode that turns triggers off, before writing the test that asserts it | fixed 2026-07-29 (`Q1 B2a`) — `ENABLE ALWAYS` |

**Three of the fifteen (1, 2, 3) are the same defect in three sibling files.** That is the strongest
evidence for this page existing: each was fixed correctly, in place, by someone who had just
understood it — and the understanding did not travel.

**Rows 11 and 12 both landed on 2026-07-29, the day after this page was written, and both are worth
the ink.** Row 11 is NV-3 *committed by a refactor*: the gate was correct, and moving the files it
named emptied its scope in silence — a check can be broken by an edit that never touches it, which is
why the scope must be a predicate over a directory rather than a list of names. Row 12 is blunter:
the author had this standard actively in mind, was writing the file that argues against vacuous
checks, and still wrote one — **caught by a linter, not by intent.** Intent is not a mechanism. That
is the case for §6's honest gap: until something *checks*, this page is a discipline, and disciplines
are what this register is a list of failures of.

**Rows 13 and 14 sharpen NV-3 past "an enumerated list".** Neither was a list. Row 13's scope was the
*text the checker got to see* — a stripper handed it code with the violation already removed. Row 14's
was the *dependency depth it walked*. Both are the same question asked structurally rather than
lexically: **is there an input that reaches the guarded thing without passing the guard?** Row 13 also
carries a second lesson worth more than the fix — the gate had two correct sibling implementations in
the same directory, and the buggy one was the newly written copy. The duplication was not a tidiness
complaint; **it was the defect.** All three now share `scripts/gatelib.py`.

**Row 15 is the one that should change how this page is read.** It is row 13's *fix*, reviewed: the
shared stripper solved the `//`-inside-a-string problem on one fork of a two-fork function and shipped
it broken on the other — the fork the most safety-critical consumer actually runs. Two tells were
sitting there: the raw-string arm immediately above already handled it correctly (**sibling arms
disagreeing**), and the self-test exercised only one value of the flag (**half a function tested**).

So the register now contains a defect, its fix, and a defect *in* the fix. That is not a story about
one careless afternoon — six of these landed in a single day, every one NV-3, every one found by
reading rather than by running. **§6's "not yet mechanical" is no longer a footnote; it is the finding.**
The cheapest real step is a lint that reds when a boolean-forked function's tests only ever pass one
value of the fork.

**Rows 16 and 17 are both in `db-safety-gate.py`, and row 17 is row 3 again — in the same file, twenty
lines away.** Row 3 fixed the *inline* pragma window; the *file-level* pragma kept its own arbitrary
`lines[:60]` and discarded an exemption written at line 69, beside the line it explained. Row 16 is
the sibling-disagreement shape one level up: the gate's own throwaway vocabulary (`test|smoke|audit|…`)
had accepted `smoke` since the file was written, while the selector deciding *which files to read* only
accepted `test` — so a correct decision in one half silently narrowed the scope in the other. **Six
scripts, every one of them dropping a database, had never been looked at.** The first attempt to fix it
by reusing that vocabulary wholesale was also wrong, and instructively: in a *database name* `audit`
means "disposable", in a *file name* it means "operates on audit data", and the reuse pulled a
production retention cron into the test-file scope. Same word, opposite meaning, one directory apart.

**Row 18 is the first entry found by attacking a guard before writing its test**, and it argues for
doing that by default. The trigger was correct against every client; the bypass was a documented
one-line GUC that ordinary use never sets and every `pg_restore` does. Nothing in the test suite would
ever have supplied it — the "input that reaches the guarded thing without passing the guard" was a
*session mode*, not a value. The same probe paid twice: it also proved that the `epoch >= 1` CHECK,
which the gapless trigger shadows for every input a client can send, is reachable in exactly that mode
— so a constraint that looked like dead SQL is the one thing still standing when the triggers are off.
**Ask of every guard: what turns this off, and who does that routinely?**

**Row 19 is the degenerate case, and it is the one to remember.** The gate was written, correct, and
would have caught the defect on its first run — it had simply never been *attached to anything*. It sat
in `scripts/` beside seventeen siblings that ARE in `.githooks/pre-commit`, so the directory listing
made it look enforced. A check nobody runs is not a weaker check; it is **the same as not having one**,
with the added cost that its existence answers *"is this covered?"* with a yes.
**"There is a lint for that" is not enforcement — grep the hook.**

**Rows 20 and 21 are the sting in row 19's tail, and they invert its lesson.** Chasing row 19 produced
an audit that said *26 of 58 gates run nowhere*. It was **wrong** — the workflow wires its lints as a
matrix of bare names, and the audit searched for paths (row 21). The true figure was three. What the
corrected look found instead was **worse**: six of those gates were wired, blocking, and had been
**failing on `main` for four days** (row 20). The mechanism was never the problem. Nobody was reading
the output.

So the rule to carry forward is not *"wire your gates"* — that was already done. It is:

> **A red gate nobody acts on is worse than an unwired one.** An unwired gate is silent, and silence
> is at least honest. A red gate that stays red for four days teaches the whole team that red is the
> normal colour, and the next real failure arrives into an audience that has stopped looking.

That is why `KNOWN_RED` rows must name a deferral **and fail when they turn green**: an
acknowledgement list that only grows is how "we know about that one" becomes "we do not look at any of
them."

---

## 5. What this is NOT

* **Not "write more tests."** A vacuous test makes the count go up and the coverage go down.
* **Not a coverage percentage.** Line coverage says the code ran, never that a wrong answer would have
  been noticed.
* **Not an argument against green suites.** A green suite that has been *watched to go red* is the
  goal. The objection is to green that was never anything else.
* **Not retroactive blame.** Rows 8 and 9 are open and recorded as open. A known-vacuous check with a
  row is honest; the failure mode is the unrecorded one.

---

## 6. Enforcement status

**Discipline, not yet mechanical** — and that is stated rather than hidden, per this document's own
rule. No script detects a vacuous check today; NV-6's obligation is carried by review, by the
`--self-test` convention every gate in `scripts/` now follows, and by `/review-impl`.

The honest gap: a gate that never fires looks identical to a gate with nothing to find. The cheapest
mechanical step would be requiring every `scripts/*-gate.py` to expose `--self-test` and running them
all in pre-commit — partial, because it proves the checker bites on a *fixture*, not that its scope is
right (NV-3). Recorded as a known gap rather than claimed as solved.
