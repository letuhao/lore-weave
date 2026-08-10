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
NO_PROOF_BASELINE = 48

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
_PY_DOCSTRING = re.compile(r'("""|\'\'\')(?:.|\n)*?\1')
_HASH_COMMENT = re.compile(r"(?m)^\s*#.*$")


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
    if path.name != Path(__file__).name and _SELFTEST.search(_executable_text(path, src)):
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
        flag = _selftest_flag(_executable_text(run_path,
                                               run_path.read_text(encoding="utf-8",
                                                                  errors="ignore")))
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
