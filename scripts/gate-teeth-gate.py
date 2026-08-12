#!/usr/bin/env python
"""D-QC-GATE-TEETH — a gate wired into CI must be able to FAIL.

Why this exists
---------------
The QC sweep of 2026-07-31 found 63 named gate scripts with 18 wired, fixed that, and then
found the harder version of the same bug one layer down: *wired* is not *enforcing*. Two of
the scripts sitting in the "gate" pile could not return non-zero under any input —
`fe-door-scan.py` has no exit path at all, `timeout-discipline-lint.sh` ends in an
unconditional `exit 0` after printing its findings as advisory WARNs. Wiring those would have
read as +2 gates in the workflow file while enforcing exactly nothing, and a green CI would
have been evidence for a rule nothing checked.

That is the same shape as every other finding this cycle — a guarantee asserted somewhere
with nothing in code behind it — so it gets the same treatment: a rule, and a gate for it.

Two tiers, deliberately
-----------------------
HARD — every gate script CI invokes must contain a reachable non-zero exit. This is cheap,
mechanical, and green today. A new advisory-only "gate" reds here immediately.

RATCHET — a gate should also carry a PROOF that it goes red: a built-in selftest (the repo's
existing convention, e.g. `[emit-0013] SELFTEST PASS — flags a missing-0013 emit script,
passes one with 0013 (non-vacuous)`), or a test file that drives it. Most do not yet, so this
is a ratchet rather than a wall: the count may not grow, and lowering it is recorded. Making
this HARD today would mean ~40 findings and a red build with no path to green, which is how
gates get commented out instead of fixed.

    python scripts/gate-teeth-gate.py          # exit 1 on a toothless gate / ratchet drift
    python scripts/gate-teeth-gate.py --list   # the full inventory with each verdict
"""
from __future__ import annotations

import ast
import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: Shown in place of a workflow name for gates the runner executes.
RUNNER_LABEL = "gate-wiring-gate --run-all"

#: Gates CI runs that carry no red-ability proof yet. Ratcheted — see the module docstring.
#: 2026-07-31: 54 CI-invoked gates, 7 proven (4 selftest + 3 test files) ⇒ 47.
#: MEASURED, not estimated — the first value here was a guess of 43 and the gate rejected it
#: on its own first run, which is the behaviour you want from a ratchet.
#: 2026-08-06: 46 -> 45. `meta-write-discipline-lint.sh` gained a self-test in the rewrite
#: that made it fast enough to run at all (74s -> 9.2s), and the new
#: `tier-capability-gate.py` shipped with one. The ratchet asked for this itself
#: ("Progress — lower NO_PROOF_BASELINE to 45"), which is the direction it exists to force.
#:
#: 2026-08-10: 45 -> 55, and this is the ONE direction this number is normally forbidden to
#: move, so the reason has to carry it. **Nothing got worse; the scope got honest.** The gate
#: discovered its subjects by regexing workflows for a literal `scripts/<name>` path, which
#: was complete only while every gate was named in a workflow. `gate-wiring-gate --run-all`
#: ended that, and this gate never learned — measured, 58 seen against ~100 executed. The
#: ~40 gates riding the runner were not exempt and not proven; they were INVISIBLE, and the
#: ratchet was reporting a subset as the whole. Widening discovery to the runner's own list
#: (see `_runner_discovered`) is what moved 45 -> 55.
#:
#: Two things kept the number from being worse, and neither is bookkeeping: the three gates
#: added the same day all shipped a `--self-test`, and `migration-idempotency-validator.sh`'s
#: proof was found to be real but DELEGATED to its `.py` (see `DELEGATES_PROOF`). Every one
#: of the 55 is now a gate CI genuinely runs whose red-ability nothing demonstrates — which
#: is a worklist, where the old 45 was a number that could not see its own subject.
#:
#: 2026-08-10 (same day, second move): 55 -> 51. The four `dp-slice{1,5b,5c,5d}-bite-gate`
#: harnesses gained a `--self-test`, and they were the right four to take first: a BITE
#: HARNESS with broken machinery prints `bitten: N/N` and is believed, so it launders a
#: vacuous result as evidence for every guard it names. What each proves is the machinery,
#: not the guards — the four-way verdict (`classify`, split out so it can be checked on
#: synthetic transcripts without a 30s cargo run), byte-exact read/write through CRLF
#: (`V1-F8`), the restore check firing on a corrupted file, and every leg's anchor still
#: existing in its target. Both arms bitten: breaking `classify`'s `missing` branch and
#: rotting one leg anchor each turn the self-test red.
#:
#: 2026-08-10 (third move): 51 -> 48. `db-safety-gate`, `doc-language-gate` and
#: `language-bias-gate` — chosen as the three gates that READ A CORPUS and could therefore
#: silently read NOTHING. That failure mode is invisible by construction: a walk that reaches
#: no files and a clean tree produce byte-identical output, exit 0 included. So each self-test
#: has a **reach** family alongside its detectors — every `SEARCH_DIRS` entry must exist (a
#: renamed directory is skipped silently, retiring the gate over that whole tree) and the walk
#: must clear a floor. Demonstrated, not argued: with `services/` renamed, `db-safety-gate`
#: still exits 0 with 1558 test files unguarded, and `doc-language-gate` reports a BETTER
#: number (505/8678 vs 995/10821) with `/docs/` — the rule's entire subject — out of scope.
#:
#: Every detector arm has a false-positive twin, because a language gate that cries wolf is
#: switched off within a day: accented English (`Soufflé`, `naïve`, `Gödel`), CJK domain terms,
#: `self.name.lower()` behind the ML-2 lookbehind, and a `WHERE`-scoped DELETE all have to come
#: back clean from the same code path that reds without them.
#:
#: The `language-bias-gate` arm found real decay: **7 of its 44 baseline rows named code that
#: no longer existed** (four ML-2 offenders fixed, two ML-5 rows given `ensure_ascii=False`).
#: A fingerprint whose subject is gone is a standing exemption for a line nobody has written
#: yet. Pruned to 37, and the same run surfaced that the gate had been RED on `main` since
#: 2026-08-01 over two live ML-2 violations — fixed at the source rather than baselined.
#:
#: 2026-08-10 (fourth move): 48 -> 47, and NOT because a gate gained a proof. **A gate that
#: already had one was being reported as unproven.** `deferral-gate.py` ships a `--self-test`
#: with eleven bite cases, and the docstring stripper deleted 87% of its source (40246 -> 5421
#: chars) before the search ran — `_PY_DOCSTRING` pairs up ANY two triple-quote marks, so the
#: text between two unrelated ones vanishes with them. Python is now PARSED
#: (`_py_selftest_proof`): the AST knows which strings are docstrings, so the same two shapes
#: are decided correctly. Measured across all 97 — one gate GAINED certification, none lost.
#: A detector that misses an existing proof is a false accusation, and this file's own
#: `_SELFTEST` note says the cost: pressure to bolt on a second, redundant proof to satisfy a
#: regex. It also inflates this baseline, so the worklist contained a gate already finished.
#: 2026-08-11 (fifth move): 47 -> 43, the SECURITY-ADJACENT batch —
#: `injection-coverage-lint`, `meta-sensitive-read-bypass-lint`, `pii-classify-lint`,
#: `test-dsn-coverage-gate`. All four are corpus walkers, so each got a REACH family beside
#: its detectors: the silent-nothing path is the whole risk here and it is different in each
#: one. `pii-classify` grandfathers every migration below 018, so a renumbering leaves it
#: inspecting zero files and printing `PASS`. `test-dsn-coverage` derives its unarmed set from
#: the gating set, so an empty walk yields no gating variables, no unarmed ones, and the line
#: *"every gating variable is armed in CI"* — the exact false clean it exists to prevent, one
#: level up. `injection-coverage` skips a missing `SCAN_DIRS` entry with a bare `continue`, so
#: renaming a service directory retires the lint over that whole service silently. And
#: `meta-sensitive-read` already guarded the zero-tables case but not its grep ROOTS.
#:
#: Two real defects fell out, neither visible on a green run:
#:   * `test-dsn-coverage`'s `READ` regex put `os\.environ\[` in the list of function NAMES and
#:     then demanded another bracket, so it required `os.environ[[`. **`os.environ["X_TEST_Y"]`
#:     was never detected** — a subscript-gated suite was invisible to the gate whose subject
#:     is invisible suites. Found by the self-test on its first run, because the case was
#:     written from the docstring's CLAIM rather than from the code.
#:   * `injection-coverage`'s BASELINE — a list of tracked injection holes — had no shrink arm.
#:     A row whose file is deleted, or whose module has since adopted the sanitizer, stood as a
#:     security exemption over nothing. Both directions now red.
#:
#: Also pinned rather than fixed: `RETRIEVED_TEXT`'s markers are `\b`-anchored and `_` is a
#: word character, so `retrieved_docs` / `retrieved_chunks` do not match. Widening is a
#: heuristic decision whose false positives become BASELINE rows — i.e. exemptions — so the
#: limit is now a measured self-test case instead of a surprise.
#:
#: 2026-08-12: 43 -> 41. `capacity-budget-lint.sh` and `service-acl-matrix-lint.sh`, the two
#: smallest of the 43, each gained a REAL `--selftest` — extracted predicate, both directions
#: cased, and the bare invocation runs the selftest BEFORE the lint so the proof executes on
#: every CI run rather than on request. The ratchet asked for this itself and refused to pass
#: until the number followed, which is the whole point of it.
#:
#: **The trap this number invites, stated so the next person does not walk into it.** Proof
#: detection here is STRUCTURAL — a `def self_test` / `selftest() {` in executable text. It
#: cannot tell a real self-test from an empty one, so 41 stub functions would clear this
#: baseline to zero and prove NOTHING, converting an honest gap into false coverage. That is
#: strictly worse than 41, because a gap invites work and a false pass silences review. Each
#: of the two above was bitten six-step before it was counted: the name anchor dropped (a
#: prefix match), membership forced true, and each alternative of the meta-write detector
#: removed one at a time — the last of those because blanking the whole pattern reds on the
#: FIRST case and says nothing about the other two. Both also gained REACH FLOORS: a walk that
#: reaches zero services now exits 2 instead of printing PASS (`BDR-82`).
#: 2026-08-12 (b): 41 -> 40. `dependency-registry-lint.sh`, and it is the case that most needed
#: a proof: in its DEFAULT mode it prints violations and exits 0, so "it passed" and "it found
#: 49 problems" were the same observable. A disarmed gate can still be shown to BITE — the mode
#: is a policy decision (DEFERRED 082), the predicate is a rule, and the proof is of the rule.
#: Two defects fell out of writing it: the violation counter incremented once per GREP BLOCK,
#: so it reported **2** against a real **49** for months; and the reach floor added alongside
#: it was itself unreachable, because `set -euo pipefail` kills the script at the failing
#: `find` before the floor can speak. The bite found the second one.
#: 2026-08-12 (c): 40 -> 39. `language-rule-lint.sh`, enforcing the LOCKED I3 amendment. Its
#: `run_lint` now takes the config AND the services root, so the selftest drives the WHOLE gate
#: against a synthetic tree — both its rules live in loops rather than functions, and proving
#: `detect_lang` alone would have said nothing about either. Two findings came out of the
#: writing, both in code added minutes earlier: a reach floor placed ABOVE the violation report
#: turned a real PRR-16 finding into a misuse exit 2; and a second floor on directories walked
#: was strictly SHADOWED (a comparison needs a directory to exist, so `scanned == 0` implies
#: `compared == 0`) — deletable with the suite green, so it was deleted rather than kept as
#: decoration.
#: 2026-08-12 (d): 39 -> 38. `admin-command-registry-lint.sh`, and the proof is only half the
#: story: measured while writing it, **that gate has ZERO SUBJECTS** — `// ADMIN-SQL:` and
#: `// ADMIN-RPC:` occur 0 times across `services/`, and `func (… *AdminHandler)` occurs 0
#: times. It walked the tree, matched nothing, and printed *"no orphan ADMIN-SQL/RPC markers"*,
#: which reads as verified coverage of a convention this repo does not write. NOT resolved by
#: making it red — zero markers is the TRUE state, and failing on the truth is cry-wolf. The
#: gate now prints the subject count and says outright that nothing was compared; the coverage
#: gap is tracked as `GT-ADMIN-NO-SUBJECT`. A proof that the rule bites and a statement that it
#: has nothing to bite are two different facts, and this baseline only ever counted the first.
#: 2026-08-12 (e): 38 -> 37. `dep-pinning-lint.sh`, where the proof was the smaller half again.
#: Measured while writing it: the gate was scanning **89% foreign trees** — 600 of 675 `go.mod`
#: and 288 of 324 `Dockerfile` under `.claude/worktrees/` (agent scratch copies of this repo),
#: 136 of 153 `requirements*.txt` in worktrees / `site-packages` / `vendor`. It excluded
#: `node_modules` and `.venv` and nothing else, so 1440 "judged" dependency lines were mostly
#: other people's. Real counts: 75 / 17 / 3 / 36, and 176 lines.
#:
#: And the exclusion it did have was the WRONG SHAPE: `-not -path '*/target/*'` filters find's
#: RESULTS while find still DESCENDS into every pruned directory. Four scans each walked two
#: complete Rust build trees. `-prune` instead: **51-76s -> 13s**, identical counts. This is the
#: same latency class that once took `admin-command-registry-lint` to a 900s timeout under
#: `--run-all` — a gate red for a reason unrelated to what it checks.
#:
#: Also collapsed a warn arm that fired on **36 of 36** subjects (zero digest-pinned FROMs exist
#: anywhere) from 36 identical lines to one ratio. A warning on everything is a warning on
#: nothing; the ratio still moves the day someone pins one. `GT-DOCKER-WARN-100PCT`.
#: 2026-08-12 (f): 37 -> 35. `read-audit-query-type-drift-lint.sh` +
#: `transitions-validation-lint.sh`, and each shipped a different way of passing over nothing.
#:
#: The drift gate is ONE STRING COMPARISON between two grep outputs, and **two empty sets are
#: equal**. Break either pattern — a renamed constraint, a reformatted YAML — and both sides
#: collapse to "", the equality holds, and it printed *"PASS — CHECK == YAML SSOT (0 ids)"*.
#: A drift detector reporting agreement because it parsed nothing is the purest form of the
#: defect it exists to catch, and the `(0 ids)` in its own success line was the tell.
#:
#: The transitions gate opened with `if [[ ! -f "$target" ]]; then echo "nothing to lint";
#: exit 0; fi` — **one `git mv` from permanently green**, silently, with a cheerful message.
#: The file existing today is the only reason it never bit. A vanished subject is a finding.
#: 2026-08-12 (g): 35 -> 34. `projection-coverage-lint.sh`, whose real gap was not the proof:
#: its 12-row ALLOWLIST had no shrink arm, so an exemption was permanent by default. Nothing
#: red when an allowlisted event was deregistered, and nothing red when one GAINED a projection
#: and the row's reason expired — `npc.said`'s row states its own retirement trigger in PROSE
#: (*"when the actor/NPC track ships an emitter, this row must be replaced"*) with no mechanism
#: to notice. Both directions now red, mirroring `deferral-gate`'s `PROSE_ONLY` shrink and
#: `dp-oracle-coverage`'s `NO_PRODUCER` arms. Measured clean on landing: 0 stale, 0 expired.
#:
#: Its docstring also claimed *"5/14 registered events are projected"* while the gate reported
#: **4/16** — claim rot in the header of a gate. The ratio is printed at runtime now and no
#: longer restated where nothing measures it.
#: 2026-08-12 (h): 34 -> 33. `runbook-drift-check.sh`. Its `KNOWN_LOGICAL` allowlist described
#: itself as *"canonical platform names that aren't yet services/ dirs"* and was measured **91%
#: dead**: of 23 names, **19 ARE services/ dirs** (they shipped — the real source of truth
#: covers them) and 2 more are cited by no runbook. Exactly TWO were load-bearing. That is not
#: only dead weight: any of the 21 would have silently satisfied a stale runbook reference,
#: which is the drift this gate exists to detect. Trimmed to two, with both shrink arms so it
#: cannot regrow silently — the same pair added to `projection-coverage-lint` an hour earlier,
#: which is now the third allowlist in this repo to need them.
#:
#: Its trailing `exit 0` after the python block was CHECKED rather than assumed: `set -e`
#: aborts on a python exit 1 first, so drift was reported. Not every suspicious line is a bug.
#: 2026-08-12 (i): 33 -> 32. `tracing-completeness-lint.sh`, the second DISARMED gate found on
#: this board: default `warn` mode printed **49** violations and exited 0, so "it passed" and
#: "49 handlers have no tracing" were the same observable. Its header promised *"flip to error
#: mode in cycle 33+"* — measured, that flip is in **no** deferral row and **no** handoff line.
#: A prose promise several cycles overdue with nothing to wake it (`dependency-registry-lint` at
#: least has `DEFERRED 082`).
#:
#: **Armed with a RATCHET rather than a flip.** Flipping today reds the build on 49 pre-existing
#: violations — a migration, not a lint change. A falling baseline catches the thing that
#: actually matters day to day: a NEW untraced handler reds immediately, in warn mode, today.
#: Both directions are bitten, because a ratchet that only reds upward never falls.
#: Also 48s -> 2s: it ran one or two `grep` processes per file across 707 files; `git grep`
#: does the same work in two.
#: 2026-08-12 (j): 32 -> 31. `observability-inventory-lint.sh`. A carefully-maintained gate — its
#: header records two `NV-4` findings it already survived — that nonetheless opened with
#: `if [[ ! -f "$inventory" ]]; then echo "skipping"; exit 0; fi`. **One `git mv` from
#: permanently green**, and the second gate on this board with that exact line
#: (`transitions-validation` was the first). Now exit 2.
#:
#: Its EMITTED side also had no floor. The declared side fails loudly when it empties — every
#: emitted symbol becomes undeclared — but if the literal regex stops matching or the roots
#: move, `emitted` is empty, the comparison loop runs zero times and it prints PASS. Measured
#: reach: 1086 files scanned, 46 emitted literals, 100 declared.
#:
#: Reported rather than enforced: **54 of the 100 declared metrics are emitted nowhere in code**
#: (`GT-OBS-UNEMITTED`). Planned or rot — this gate cannot tell which, and stating the number
#: beats implying zero.
#: 2026-08-12 (k): 31 -> 30. `slo-latency-lint.py` — and this one was already GOOD: a missing
#: config exits 2, an empty `endpoints:` exits 2, it prints its count. The first gate on this
#: board whose reach was sound before I touched it, which is worth recording because the run's
#: other twelve were not. It gained 14 self-test cases and one `GT-F5` shrink arm on
#: `LATENCY_HEAVY` (measured: all four names real, 0 dead rows — the arm lands while the answer
#: is still zero, which is the right moment).
#:
#: The case worth keeping: `p95_ms: true`. **`True` IS an `int` in Python**, so without the
#: explicit `isinstance(p95, bool)` guard a boolean sails through as the number 1 — a positive
#: number, and a passing SLO. The guard was already there; nothing proved it was load-bearing
#: until its own bite arm removed it and watched the case go red.
#: 2026-08-12 (l): 30 -> 29. `alert-rule-validator.sh`. **Third dead exemption list on this
#: board**: `PRE_SLI_GRANDFATHER` held 38 names and **14 of them (36%) referred to alerts that
#: no longer exist anywhere on disk**. Dead weight, and worse — a dead row silently
#: re-grandfathers its alert the day the name comes back, so the list could disarm the very
#: checks (`sli_ref`, registry membership, runbook) it is an exception to. Trimmed to 24, with
#: the `GT-F5` shrink arm.
#:
#: Reach floor too: `os.walk` on a missing or renamed alerts directory yields nothing, so
#: `checked` stayed 0, `problems` stayed empty, and it printed *"0 alerts validated"* and exited
#: 0. The count was right there in the success line — the same tell as
#: `read-audit-drift`'s "(0 ids)".
#: 2026-08-12 (m): 29 -> 28. `dashboard-validator.sh`, closing `GT4`. Its reach floor already
#: existed and `GRANDFATHERED` was legitimately empty — but the TEMPLATE exemption was **wider
#: than its stated reason**: `check_dashboard "$f" 2>/dev/null` swallowed all NINE rules while
#: the comment justified exactly one ("uid `_template` is intentionally non-kebab-case"). A
#: template that lost its `timezone`, or stopped being valid JSON, was waved through under a
#: justification that did not cover it. Narrowed to the uid rule; measured first, and it reds
#: nothing today.
#:
#: **Two of its four bite arms FAILED on the first run, and both were right to.** The narrowed
#: exemption and the new shrink arm had NO CASE: the probe tree contained no template entry, and
#: the hardcoded exemption path resolved against the real repo, so disabling either rule changed
#: nothing. Rules added ten minutes earlier, already deletable with the suite green. Fixed by
#: parameterising `LW_TEMPLATE_FILES` — and `+x` rather than `-n`, because a probe wanting NO
#: exemptions passes an empty string and `-n` would hand it the production default.
#:
#: Same root as the third finding: `DASH_ROOT` was read at script LOAD, so every probe ran
#: against the real `dashboards/` tree and passed by accident. A self-test that never reaches
#: its own fixture is worse than none — it reports coverage of inputs it never read.
NO_PROOF_BASELINE = 16

#: Scripts CI invokes that are NOT gates and are exempt from the HARD rule, with the reason.
NOT_A_GATE = {
    # Emits a report consumed by a later step / a human; failure is not its job.
    "runbook-index-generator.sh": "generator, not a checker",
}

#: A script whose only failure mode is an external tool's exit code under `set -e`.
#: Accepted as a failure path, but named here so it is a decision and not an accident.
DELEGATES_FAILURE = {
    "lint-contract.sh": "spectral-cli returns non-zero on an error-severity finding",
}

#: A THIN WRAPPER whose red-ability proof lives in the file it execs, named here with the
#: target so the claim is reviewable. The sibling of `DELEGATES_FAILURE`, and it exists for
#: the same reason: the alternative was adding a no-op line to the wrapper so its executable
#: text contains `--self-test`, which is precisely the "bolt on a second, redundant proof to
#: satisfy a regex" pressure this file's own `_SELFTEST` comment warns about. A named row
#: with a target is a decision; a no-op that games the detector is a silencer.
DELEGATES_PROOF = {
    "migration-idempotency-validator.sh":
        "a 10-line wrapper around migration-idempotency-validator.py, which carries the "
        "`--self-test` (8 checks, each proven to fire on its own bad shape) and is what "
        "`$@` forwards to",
}

# A non-zero exit, in every form these scripts actually use. The first version of this
# regex looked for a LITERAL `return 1` / `^exit 1` and reported THIS FILE as toothless —
# it exits via `rc = 1 … return rc`, and shell gates commonly end `echo …; exit 1` or
# `exit "$violations"`. A detector that cannot see its own failure path is the same bug it
# was written to catch, so it is pinned by a test.
_PY_FAIL = re.compile(
    r"sys\.exit\(\s*(?!0\s*\))"          # sys.exit(<anything but literal 0>)
    r"|raise\s+SystemExit"
    r"|return\s+[1-9]\b"                  # return 1
    r"|^\s*(?:rc|code|status|exit_code|failures|violations)\s*=\s*[1-9]",
    re.M,
)
_SH_FAIL = re.compile(r"\bexit\s+(?!0\b)[\"'$\w]", re.M)
_SET_E = re.compile(r"^\s*set\s+-\w*e", re.M)
# MERGE 2026-08-02: `gate-wiring-gate.py` arrived from main carrying a real, working proof —
# a `self_test()` function behind a `--self-test` flag, verified red-able — and the previous
# pattern (`SELFTEST`) reported it as UNPROVEN purely because it spells the word with a
# separator. A detector that misses an existing proof is a false accusation, and the pressure
# it creates is to bolt on a second, redundant proof to satisfy a regex.
#
# But the separator must NOT simply be made optional. Measured: a bare `SELF[-_ ]?TEST` also
# certified `context-inspector-checklist-gate.py`, which has no self-test at all — it matched
# the words "for gate self-tests" inside an argparse `help=` string. `_executable_text` strips
# docstrings and comments, not string literals, so a MENTION would have counted as a PROOF.
# That is this file's own warning ("a gate must never be its own witness") re-committed one
# level out. So the separator spellings are accepted only in the two shapes that are proofs
# rather than prose: a `def self_test` and a `--self-test` CLI flag.
# 2026-08-10 — THE BARE `SELFTEST` ALTERNATIVE IS GONE, and it was the hole the
# paragraph above describes, left open in the one branch it did not narrow. It
# certified `dp-oracle-bite-gate.py`, which has no self-test at all: the match was
# the string literal `"SELFTEST FAIL"`, which that harness uses to read the
# COVERAGE GATE'S OUTPUT. A mention counted as a proof — fourth occurrence of that
# shape here — and the cost was not cosmetic: the false certification kept a BITE
# HARNESS off the worklist, and a bite harness with broken machinery prints
# `bitten: 19/19` and is believed. Found by `--verify-proofs` on its first run.
#
# So all three alternatives are now SHAPES rather than words: a Python `def`, a
# shell `selftest()` function, or a CLI flag. Measured: narrowing costs exactly one
# certification, the phantom one.
_SELFTEST = re.compile(
    r"def\s+self[-_]?test\b"              # python:  def self_test / def selftest
    r"|\bself[-_]?test\s*\(\s*\)\s*\{"    # shell:   selftest() {
    r"|--self[-_]?test\b",                # either:  a CLI flag
    re.I,
)
#: Just the CLI flag, for the AST path where "is this a docstring" is already decided.
_FLAG_ONLY = re.compile(r"--self[-_]?test\b", re.I)

_PY_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_HASH_COMMENT = re.compile(r"(?m)^\s*#.*$")


def _py_selftest_proof(src: str) -> bool:
    """Does this Python source DEFINE or EXPOSE a self-test? Parsed, not regexed.

    # Why the regex had to go

    `_executable_text` strips docstrings with a non-greedy match between *any*
    two triple-quote marks (see `_PY_DOCSTRING`), with no idea which ones open a
    docstring. It pairs them up across the whole file, so the text between two
    unrelated quotes disappears with them. On `deferral-gate.py`
    that deleted **87% of the source** (40246 -> 5421 chars), `def self_test`
    included, and the gate was reported as carrying no proof while shipping a
    `--self-test` with eleven bite cases.

    That is a FALSE ACCUSATION, and this file's own `_SELFTEST` comment names
    the damage: *"the pressure it creates is to bolt on a second, redundant
    proof to satisfy a regex."* It also inflates `NO_PROOF_BASELINE`, so the
    worklist contains gates that are already done.

    The AST knows what a docstring is, so ask it. A proof is either a
    `def self_test` / `def selftest`, or a `--self-test` / `--selftest` string
    that is **not** a docstring — the same two shapes as before, decided
    correctly. Syntax errors fall back to the regex path rather than crashing
    the gate on a file it merely cannot parse.
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return False

    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and \
                re.fullmatch(r"self[_-]?test", node.name, re.I):
            return True
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings and _FLAG_ONLY.search(node.value):
            return True
    return False


def _py_selftest_flag(src: str) -> str | None:
    """The self-test flag this Python file actually ACCEPTS, from the AST.

    Split from the proof check because `--verify-proofs` needs the spelling, not
    a yes/no — and because reading it any other way put the two out of step the
    moment the proof moved to the AST. `deferral-gate.py` was certified via the
    parser while `_selftest_flag` still went through the corrupted stripper,
    which had deleted the flag along with 87% of the file: certified as proven,
    and reported as exposing nothing to run. **The proof and the runner have to
    read the same thing**, which is the adjacent-decision shape — each half
    correct on its own.

    A docstring is excluded for the same reason as in the proof: a file
    documenting `--self-test` while implementing `--selftest` would otherwise be
    handed the wrong spelling and answer `exit 2`, which reads as a broken
    self-test rather than a bad guess (`BDR-75`).
    """
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    docstrings: set[int] = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) \
                and body and isinstance(body[0], ast.Expr) \
                and isinstance(body[0].value, ast.Constant) \
                and isinstance(body[0].value.value, str):
            docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings:
            m = _FLAG_ONLY.search(node.value)
            if m:
                return m.group(0)
    return None


def _executable_text(path: Path, src: str) -> str:
    """`src` with docstrings and full-line comments removed.

    A gate must PRINT its selftest, not merely mention one. This file claimed a "built-in
    selftest" on its first run purely because the word appears in its own module docstring —
    the identical mistake `enforcement-claims-gate.py` made when it satisfied its own check by
    naming contracts in its docstring. A claim in prose is exactly what these gates exist to
    reject, so the search runs over what actually executes."""
    if path.suffix == ".py":
        src = _PY_DOCSTRING.sub("", src)
    return _HASH_COMMENT.sub("", src)

#: What makes a script an ENFORCEMENT gate rather than something else CI happens to run.
#: Without this the scan swept in 30 perf rigs (`perf/w1-capacity.sh`, `perf/soak.sh`, …),
#: which are load harnesses, not checkers — counting them as toothless gates would have
#: buried the two REAL findings under noise and made the baseline meaningless.
_IS_GATE = re.compile(r"(?:-|_)(?:lint|gate|validator|check|scan|enforcer|drift|guard)s?"
                      r"(?:-\w+)?\.(?:py|sh)$")


def _runner_discovered() -> list[str]:
    """Gates reachable through `gate-wiring-gate.py --run-all`.

    # Why this exists — the scope was a NAME LIST while coverage had moved to a PREDICATE

    `ci_invoked_scripts()` below finds a gate by regexing workflows for a literal
    `scripts/<name>` path. That was complete when every gate was named in a
    workflow. It has not been since `gate-wiring-gate` introduced `--run-all`,
    whose own docstring says the runner exists precisely so *"a gate written
    tomorrow runs in CI the day it lands, with nobody remembering to add a
    line"* — and this gate kept counting the names.

    Measured 2026-08-10: **58 gates seen here, ~100 discovered by the runner.**
    Three gates added that same day (`dp-oracle-coverage-gate`,
    `dp-oracle-bite-gate`, `db-ensure-bite-gate`) were invisible to the teeth
    ratchet on arrival. `NV-3`, default-uncovered, in the gate whose entire job
    is ensuring a gate can fail.

    Discovery is DELEGATED to `gate-wiring-gate` rather than re-implementing its
    predicate here: two copies of "what is a gate" is the drift this repo has a
    standard about, and the runner's list is the authoritative one because it is
    the list CI actually executes.
    """
    spec = importlib.util.spec_from_file_location(
        "gate_wiring_gate", ROOT / "scripts" / "gate-wiring-gate.py"
    )
    if spec is None or spec.loader is None:
        return []
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not mod.runner_in_ci():
        # No workflow invokes the runner, so it grants no coverage. Falling back
        # to name-matching alone is correct here, not a hole.
        return []
    skip = set(mod.EXEMPT) | set(mod.NEEDS_STACK) | set(mod.TOO_SLOW)
    out = []
    for n in mod.discovered():
        if n in skip:
            continue
        rel = n[len("scripts/"):]
        # A pytest target under scripts/ is a TEST OF a gate, not a gate — the
        # same exclusion `ci_invoked_scripts` applies. `gate-wiring-gate`'s
        # predicate accepts `_gate` as a separator, so `test_generation_guard_gate.py`
        # is a gate to IT and a test to us. Omitting this filter reported two
        # pytest files as "toothless": they assert rather than `sys.exit(1)`,
        # which is correct for a test and meaningless as a gate verdict.
        name = Path(rel).name
        if name.startswith("test_") or "/tests/" in rel:
            continue
        out.append(rel)
    return out


def ci_invoked_scripts() -> dict[str, list[str]]:
    """{script relpath: [workflow names]} for every enforcement gate CI runs."""
    out: dict[str, list[str]] = {}
    for wf in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        text = wf.read_text(encoding="utf-8", errors="ignore")
        for m in re.finditer(r"scripts/([\w./-]+\.(?:py|sh))", text):
            rel = m.group(1)
            name = Path(rel).name
            # A pytest target under scripts/ is a TEST of a gate, not a gate.
            if name.startswith("test_") or "/tests/" in rel:
                continue
            if not _IS_GATE.search(name):
                continue
            out.setdefault(rel, [])
            if wf.name not in out[rel]:
                out[rel].append(wf.name)
    # ...and everything the runner executes, which no workflow names.
    for rel in _runner_discovered():
        out.setdefault(rel, [])
        if RUNNER_LABEL not in out[rel]:
            out[rel].append(RUNNER_LABEL)
    return out


def has_failure_path(path: Path) -> bool:
    src = path.read_text(encoding="utf-8", errors="ignore")
    if path.name in DELEGATES_FAILURE:
        return True
    if path.suffix == ".py":
        return bool(_PY_FAIL.search(src))
    if _SH_FAIL.search(src):
        return True
    # A shell gate whose real check is an embedded Python heredoc: under `set -e` the
    # heredoc's `sys.exit(1)` aborts the script, so the trailing `exit 0` is unreachable on
    # failure. `runbook-verification-lint.sh` is exactly this and was flagged toothless until
    # the shape was checked instead of assumed — measured: set -e → rc=1, without it → rc=0.
    return bool(_SET_E.search(src) and _PY_FAIL.search(src))


def teeth_proof(rel: str, path: Path) -> str | None:
    """How this gate proves it can go red, or None."""
    src = path.read_text(encoding="utf-8", errors="ignore")
    # This file is the ANALYZER: the word "selftest" is its vocabulary, so it matched its own
    # `return "built-in selftest"` string and certified itself. Third instance of that shape in
    # one cycle (enforcement-claims-gate named contracts in its docstring; the S12 gate greened
    # on its own motivating example). A gate must never be its own witness.
    # Python is PARSED (see `_py_selftest_proof`); shell still uses the regex,
    # where there is no docstring notion to get wrong.
    if path.name != Path(__file__).name:
        if path.suffix == ".py":
            if _py_selftest_proof(src):
                return "built-in selftest"
        elif _SELFTEST.search(_executable_text(path, src)):
            return "built-in selftest"
    if path.name in DELEGATES_PROOF:
        target = ROOT / "scripts" / (path.stem + ".py")
        # The claim must still be TRUE: the named target has to exist and carry the
        # proof. A row here that outlived its target would be an exemption nobody
        # could check, which is the shape every register in this repo reds on.
        if target.exists() and _SELFTEST.search(_executable_text(target, target.read_text(
                encoding="utf-8", errors="ignore"))):
            return f"delegated selftest in {target.name}"
    stem = path.stem.replace("-", "_")
    for cand in (
        ROOT / "scripts" / f"test_{stem}.py",
        path.parent / f"test_{path.stem}.py",
        ROOT / "scripts" / "tests" / f"test_{stem}.py",
    ):
        if cand.exists():
            return f"test file {cand.relative_to(ROOT).as_posix()}"
    return None


#: The two spellings a self-test flag is written in here, most specific first.
#: READ FROM THE FILE, never guessed — a probe that assumed `--self-test` for
#: everything reported six gates as broken that were simply spelled `--selftest`,
#: and every one of those reds looked exactly like a finding (`BDR-56`).
_FLAGS = ("--self-test", "--selftest")


def _selftest_flag(src: str) -> str | None:
    """The flag THIS file actually accepts, or None."""
    for flag in _FLAGS:
        if flag in src:
            return flag
    return None


def verify_proofs(invoked: dict) -> int:
    """RUN every advertised self-test and require exit 0.

    # Why a string match is not a proof

    `teeth_proof` certifies a gate when its executable text contains
    `def self_test` or a `--self-test` flag. That is a claim the file makes
    about itself, and nothing checks it: rename the function and leave the
    argparse flag, and the gate still certifies while `--self-test` raises
    `NameError`. Measured by doing exactly that — the count stayed at 49 and
    `--list` still printed *built-in selftest*.

    So the number this file publishes rests on **41 self-tests nobody runs**,
    which is the shape its own docstring is about one level out: a proof that
    cannot fail is a claim wearing the costume of evidence.

    # Honest limits, both stated rather than discovered later

    * A `test file <path>` proof is NOT executed here — those run with the
      pytest suite, and shelling out to pytest per gate would make this mode
      cost minutes rather than seconds. They are counted and named in the
      output so the gap is visible instead of implied.
    * Exit 0 means the self-test RAN and passed. It does not mean the arms
      inside it are non-vacuous — that is what the six-step bite is for, and
      no runner can substitute for it.

    Measured 2026-08-10: 41 gates, 47s total, of which one (`actor-hub-figures`)
    is 23s. That is ~3% of a `--run-all` sweep.
    """
    import concurrent.futures
    import subprocess

    targets: list[tuple[str, Path, str]] = []
    deferred_to_pytest: list[str] = []
    for rel in sorted(invoked):
        path = ROOT / "scripts" / rel
        if not path.exists() or path.name in NOT_A_GATE:
            continue
        proof = teeth_proof(rel, path)
        if proof is None:
            continue
        if proof.startswith("test file"):
            deferred_to_pytest.append(rel)
            continue
        # A delegated proof lives in the sibling `.py`; run THAT, since the
        # wrapper does not take the flag.
        run_path = path
        if proof.startswith("delegated"):
            run_path = ROOT / "scripts" / (path.stem + ".py")
        raw = run_path.read_text(encoding="utf-8", errors="ignore")
        # Python via the AST, so the runner and `teeth_proof` read the SAME
        # thing; shell via the regex over stripped text, where there is no
        # docstring notion to get wrong.
        flag = (_py_selftest_flag(raw) if run_path.suffix == ".py"
                else _selftest_flag(_executable_text(run_path, raw)))
        if flag is None:
            print(f"FAIL — scripts/{rel} is certified '{proof}' and exposes no self-test "
                  f"flag to run. The certification matched text that is not a flag.")
            return 1
        targets.append((rel, run_path, flag))

    def run(t: tuple[str, Path, str]) -> tuple[str, int, str]:
        rel, run_path, flag = t
        # A POSIX-relative path against `cwd=ROOT`, NOT the absolute one. Git
        # Bash on Windows receives `D:\Works\...` as an escape soup
        # (`D:Workssource...`) and answers "No such file or directory" — exit
        # 127, which reads exactly like a broken self-test. Four gates were
        # reported as failing before the path was the thing at fault.
        arg = run_path.relative_to(ROOT).as_posix()
        cmd = ([sys.executable, arg, flag] if run_path.suffix == ".py"
               else ["bash", arg, flag])
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=600, cwd=ROOT)
        except subprocess.TimeoutExpired:
            return rel, 124, "timed out after 600s"
        tail = (r.stdout + r.stderr).strip().splitlines()
        return rel, r.returncode, tail[-1] if tail else "(no output)"

    broken: list[tuple[str, int, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for rel, rc, tail in pool.map(run, targets):
            if rc != 0:
                broken.append((rel, rc, tail))

    if broken:
        print("FAIL — a gate certified as PROVEN has a self-test that does not pass:\n")
        for rel, rc, tail in broken:
            print(f"   scripts/{rel}  exit {rc}\n      {tail[:160]}")
        print("\n   The teeth ratchet counts these as red-ability proofs. A self-test that "
              "crashes\n   or fails is not a proof — fix it, or drop the claim and raise "
              "NO_PROOF_BASELINE.")
        return 1

    # A FLOOR, because everything above is a loop over a list that could be empty.
    # `verify_proofs({})` printed "0 advertised self-test(s) RAN and passed" and
    # exited 0 — `NV-3`, *the scope never reaches it*, in the guard written this
    # session to fix that exact shape in three other gates. Found by /review-impl.
    #
    # It is load-bearing beyond itself: `language-bias-gate`'s baseline-staleness
    # arm lives in ITS `--self-test`, so this step is the only thing that runs it
    # in CI. A vacuous pass here silently retires that arm too.
    if len(targets) < 30:
        print(f"FAIL — only {len(targets)} self-test(s) to run (floor 30, measured 42). "
              f"Discovery or certification collapsed; a run with nothing to verify reports "
              f"success indistinguishably from a healthy one.")
        return 1

    print(f"gate-teeth-gate --verify-proofs: {len(targets)} advertised self-test(s) RAN and "
          f"passed.")
    if deferred_to_pytest:
        print(f"  {len(deferred_to_pytest)} proof(s) are pytest files, run by the python "
              f"suite rather than here: {', '.join(deferred_to_pytest)}")
    return 0


def main() -> int:
    want_list = "--list" in sys.argv
    invoked = ci_invoked_scripts()

    if "--verify-proofs" in sys.argv:
        return verify_proofs(invoked)

    missing_file: list[str] = []
    toothless: list[str] = []
    unproven: list[str] = []
    rows: list[tuple[str, str, str]] = []

    for rel in sorted(invoked):
        path = ROOT / "scripts" / rel
        if not path.exists():
            missing_file.append(rel)
            continue
        name = path.name
        if name in NOT_A_GATE:
            rows.append((rel, "exempt", NOT_A_GATE[name]))
            continue
        fails = has_failure_path(path)
        proof = teeth_proof(rel, path)
        if not fails:
            toothless.append(rel)
        if proof is None:
            unproven.append(rel)
        rows.append((rel, "OK" if fails else "TOOTHLESS", proof or "— no red-ability proof"))

    if want_list:
        print(f"{len(invoked)} gate script(s) invoked by CI\n")
        for rel, verdict, note in rows:
            print(f"  [{verdict:9}] {rel:46} {note}")
        return 0

    rc = 0
    if missing_file:
        print("FAIL — CI invokes a script that does not exist:")
        for r in missing_file:
            print(f"   {r}   (workflows: {', '.join(invoked[r])})")
        rc = 1

    if toothless:
        print("FAIL — gate wired into CI with NO reachable non-zero exit "
              "(it can never report a violation):")
        for r in toothless:
            print(f"   scripts/{r}   (workflows: {', '.join(invoked[r])})")
        print("\n   Give it an `exit 1` on findings, or move it out of the gate steps and")
        print("   record it in NOT_A_GATE with the reason.")
        rc = 1

    if len(unproven) != NO_PROOF_BASELINE:
        verb = "grew to" if len(unproven) > NO_PROOF_BASELINE else "dropped to"
        print(f"\n{'FAIL' if len(unproven) > NO_PROOF_BASELINE else 'NOTE'} — gates without a "
              f"red-ability proof {verb} {len(unproven)} (baseline {NO_PROOF_BASELINE}).")
        if len(unproven) > NO_PROOF_BASELINE:
            new = [r for r in unproven]
            print("   A gate is not proven by passing; it is proven by going red on a bad input.")
            print("   Add a selftest block or scripts/test_<name>.py for the new gate(s):")
            for r in new[-8:]:
                print(f"     scripts/{r}")
        else:
            print(f"   Progress — lower NO_PROOF_BASELINE to {len(unproven)} in {Path(__file__).name}.")
        rc = 1

    if rc == 0:
        proven = len(invoked) - len(unproven)
        print(f"gate-teeth-gate: PASS — {len(invoked)} CI-invoked gate(s), every one able to "
              f"return non-zero.")
        print(f"  {proven} carry a red-ability proof; {len(unproven)} held at baseline.")
    return rc


if __name__ == "__main__":
    sys.exit(main())
