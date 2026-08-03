#!/usr/bin/env python3
"""actor-hub-figures — every number the actor-hub docs claim, MEASURED.

WHY THIS EXISTS
---------------
The stale-figure defect recurred **five times** in one round, each time inside
the commit that recorded the previous recurrence:

  D-343  the handoff block shipped in the feature commit carried four numbers
         that same commit superseded.
  D-350  the fix advanced 270 -> 279 while its own VERIFY line said 281.
  D-351  the next fix advanced 279 -> 281 while its own VERIFY line said 283.
  D-353  the row declaring the remedy *"every number is now derived by a script
         that reads the artifacts"* was written while **no such script existed**.
  D-359  the first version of THIS script then refused its own commit: the
         handoff said `D-353` while the run-state had reached `D-358`.

WHAT A REVIEW THEN FOUND IN THIS SCRIPT, AND WHAT CHANGED
---------------------------------------------------------
The first version measured **six** quantities and compared **two**, while the
documents claimed *"every figure in this block is emitted by this script, which
`--check`s them"*. **That is `D-353`'s defect one level up — a mechanism claimed
rather than verified — inside the mechanism written to end it.** It also:

  * crashed with a raw ``FileNotFoundError`` when ``cargo`` was absent, in a hook
    triggered by the **repo-wide** ``SESSION_HANDOFF.md`` — so a frontend or
    Python contributor on any of 47 services could not commit a handoff update;
  * passed **silently** when a marker string moved, reporting *"the docs agree"*
    against zero subjects;
  * had a RUN-STATE arm whose window contained **no** matching claim at all;
  * missed ``_index.md``, the file with the worst record for this exact defect
    (stale twice, `D-347` and `D-350`);
  * counted a FAILING ``cargo test`` as zero passes and then told the developer
    to rewrite the doc to match a broken build;
  * had no ``--self-test`` of its own, unlike both sibling gates;
  * and was named ``actor-hub-figures.py`` -- **which `gate-wiring-gate`'s
    filename predicate does not recognise**, so `--run-all` never executed it and
    the degradation message's promise *"CI checks it"* was FALSE. Renamed to
    ``-gate.py``, which is the shape that predicate keys on. A promise about
    another mechanism is a claim like any other.

Every one of those is fixed below, and each has a case in ``--self-test``.

    python scripts/actor-hub-figures-gate.py            # measure + check (the default)
    python scripts/actor-hub-figures-gate.py --print    # measurements only, never fails
    python scripts/actor-hub-figures-gate.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

CRATES = ["actor-hub", "entity-existence", "ruleset-core", "game-rules", "ruleset-loader"]
CONTRACTS = [
    "docs/specs/2026-08-02-actor-hub/2026-08-02-actor-hub.md",
    "docs/specs/2026-08-02-actor-hub/2026-08-02-engine-substrate.md",
]
SEAMS = "docs/specs/2026-08-02-actor-hub/2026-08-02-seams-and-triggers.md"
RUN_STATE = "docs/plans/2026-08-02-actor-substrate-RUN-STATE.md"
HANDOFF = "docs/sessions/SESSION_HANDOFF.md"
INDEX = "docs/specs/2026-08-02-actor-hub/_index.md"

# The blocks whose figures are CURRENT-STATE claims. A decision record is
# supposed to contain the numbers that were true when it was written, so the
# scan is bounded to the block a session rewrites — see `D-358`, which is what
# the first version of this check got wrong in the other direction.
#
# `end` is a marker, not a character count. A fixed 4000-char window put the
# RUN-STATE arm's subjects OUTSIDE it, so half the check had nothing to compare.
SCOPES: tuple[tuple[str, str, str], ...] = (
    (HANDOFF, "## ▶ GAME TIER", "\n---\n"),
    (RUN_STATE, "> # ▶▶ NEXT SESSION STARTS HERE", "\n---\n"),
    # The SLICE BOARD's own summary block. A stop-audit found it STALE at
    # round seven -- "81 findings over five rounds" when the count was 123 over
    # seven -- because the check covered the header and the handoff and not the
    # board two screens below them. **A figure outside a checker's scope is a
    # figure nobody is reading**, which is `_index.md`'s defect one file along.
    (RUN_STATE, "### 6-BUILD", "| # | Slice |"),
    (INDEX, "# Actor Hub", "\n## Read this to REUSE"),
)


class Unmeasurable(Exception):
    """A figure that cannot be measured HERE — never a reason to block a commit."""


def _cargo_passed(args: list[str], run=None, which=None) -> int:
    """Passing tests, or `Unmeasurable` if the toolchain is absent or the build is red.

    **Never raises a bare OSError, and never reports 0 for a broken build.** The
    first version did both: no `cargo` gave a raw traceback inside a pre-commit
    hook that fires on the repo-wide handoff, and a failing suite summed to 0,
    after which the script told the developer *"do not advance the number"* —
    i.e. to rewrite the doc to match a broken build.
    """
    if (which or shutil.which)("cargo") is None:
        raise Unmeasurable("cargo is not on PATH")
    out = (run or (lambda a: subprocess.run(
        ["cargo", "test", *a], cwd=REPO, capture_output=True, text=True)))(args)
    if "test result: FAILED" in out.stdout or out.returncode != 0:
        raise Unmeasurable("the test run is not green, so its count means nothing")
    return sum(int(m) for m in re.findall(r"test result: ok\. (\d+) passed", out.stdout))


def _max_id(path: str, prefix: str, read=None) -> int:
    text = read(path) if read else (REPO / path).read_text(encoding="utf-8", errors="replace")
    ids = [int(x) for x in re.findall(rf"\*\*{prefix}-(\d+)\*\*", text)]
    if not ids:
        raise Unmeasurable(f"no bold {prefix}- id in {path}")
    return max(ids)


def _hook_gate_scripts(read=None) -> int:
    """Distinct `scripts/*.py|sh` the pre-commit hook invokes, comments excluded."""
    text = read() if read else (REPO / ".githooks/pre-commit").read_text(
        encoding="utf-8", errors="replace")
    body = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#"))
    return len(set(re.findall(r"scripts/([A-Za-z0-9_-]+\.(?:py|sh))", body)))


def measure() -> dict[str, object]:
    out: dict[str, object] = {}
    for name, fn in (
        ("rust_tests", lambda: _cargo_passed(sum([["-p", c] for c in CRATES], []))),
        ("dp_kernel_lib_tests", lambda: _cargo_passed(["-p", "dp-kernel", "--lib"])),
        ("max_decision_id", lambda: _max_id(RUN_STATE, "D")),
        ("max_seam_id", lambda: _max_id(SEAMS, "S")),
        ("hook_gate_scripts", _hook_gate_scripts),
    ):
        try:
            out[name] = fn()
        except Unmeasurable as e:
            out[name] = {"unmeasurable": str(e)}
    lines = [len((REPO / c).read_text(encoding="utf-8").splitlines()) for c in CONTRACTS]
    out["contract_lines"] = dict(zip([c.rsplit("/", 1)[-1] for c in CONTRACTS], lines))
    out["contract_hub_lines"], out["contract_substrate_lines"] = lines
    return out


# Every claim shape this script governs, and the measurement it must equal.
# **A claim shape with no subject anywhere is itself a finding** — see `_check`.
CLAIMS: tuple[tuple[str, str, str], ...] = (
    (r"\*\*(\d+) passed, 0 failed\*\*", "rust_tests", "passing tests"),
    (r"`dp-kernel --lib` \*\*(\d+)\*\*", "dp_kernel_lib_tests", "dp-kernel lib tests"),
    (r"`D-1`\.\.`D-(\d+)`", "max_decision_id", "the highest decision id"),
    (r"`S-11`\.\.`S-(\d+)`", "max_seam_id", "the highest seam id"),
    (r"the \*\*(\d+)\*\*\s*\n?gate scripts", "hook_gate_scripts", "hook gate scripts"),
    (r"\*\*(\d+)\*\* gate scripts", "hook_gate_scripts", "hook gate scripts"),
    # F5 — `contract_lines` was measured, printed as JSON and **never compared**,
    # while the block one line above it says "every figure above is emitted by
    # this script, which --checks them". Six measured, five compared, in the
    # commit whose message states the defect as "six measured, TWO compared".
    (r"the two contracts are \*\*(\d+)\*\* and", "contract_hub_lines", "the hub contract's lines"),
    # `>?` because the RUN-STATE header is written entirely as a blockquote, so
    # the wrap puts `> ` between "and" and the number. The coverage arm caught
    # this immediately: "NO DOCUMENT claims the substrate contract's lines".
    (r"and\s*\n?>?\s*\*\*(\d+)\*\*\s*\n?>?\s*lines", "contract_substrate_lines", "the substrate contract's lines"),
)


def _claimable(block: str) -> str:
    """The block with everything that is NOT a live claim blanked out.

    **F6 — a quoted historical figure, a fenced example and an HTML comment each
    refused a commit.** These blocks are precisely where this project writes
    *"the handoff said X at round seven"*, and the board block does exactly that
    today. Blanking preserves offsets so nothing else shifts.

    Blockquote lines (`>`) are NOT blanked: the RUN-STATE header is written
    entirely as a blockquote, so blanking them would empty the scope — which the
    coverage assertion would then catch, but by making the gate useless rather
    than correct.
    """
    out, in_fence = [], False
    for line in block.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            out.append(" " * len(line))
            continue
        if in_fence or stripped.startswith("<!--") or "said **" in line or "read it (*" in line:
            out.append(" " * len(line))
            continue
        out.append(line)
    return "\n".join(out)


def _scope_text(doc: str, start_marker: str, end_marker: str, read=None) -> str | None:
    """The current-state block, or None if its anchor has moved.

    `read` is injectable so `--self-test` can drive this and `_check` for real
    instead of reimplementing their logic — the defect that let twelve
    production rules be deleted with the self-test green.
    """
    try:
        text = read(doc) if read else (REPO / doc).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    i = text.find(start_marker)
    if i < 0:
        return None
    j = text.find(end_marker, i + len(start_marker))
    return text[i:j] if j > 0 else text[i:]


def _check(m: dict[str, object], scopes=None, read=None) -> tuple[list[str], list[str]]:
    """(blocking problems, non-blocking notes)."""
    problems: list[str] = []
    notes: list[str] = []
    seen: set[str] = set()
    scopes = scopes if scopes is not None else SCOPES

    for doc, start_marker, end_marker in scopes:
        block = _scope_text(doc, start_marker, end_marker, read=read)
        if block is None:
            # **A moved anchor is a FINDING, not a silent pass.** The first
            # version set the text to "" and reported "the docs agree" against
            # zero subjects — a check whose scope never reaches it (NV-3).
            problems.append(
                f"{doc}: the marker `{start_marker}` is gone, so this document was NOT checked"
            )
            continue
        block = _claimable(block)
        for pattern, key, label in CLAIMS:
            want = m.get(key)
            for claimed in re.findall(pattern, block):
                # Keyed on the PATTERN, not the key: two rows share
                # `hook_gate_scripts`, so a dead pattern with a live sibling was
                # invisible to the coverage arm written to catch exactly that.
                seen.add(pattern)
                if isinstance(want, dict):
                    # **A figure this MACHINE cannot measure is a SKIP, not a
                    # block.** The hook fires on the repo-wide `SESSION_HANDOFF`,
                    # which this project's SESSION phase mandates updating on
                    # essentially every commit across 47 services — so refusing
                    # a commit because the contributor has no Rust toolchain is
                    # the cry-wolf failure this round spent four rounds learning,
                    # aimed at people who never touched the actor hub.
                    #
                    # CI has the toolchain and enforces there. Every sibling gate
                    # in this repo degrades the same way, with a printed reason.
                    notes.append(
                        f"{doc}: claims {claimed} for {label} — NOT CHECKED here "
                        f"({want['unmeasurable']}); CI checks it"
                    )
                elif int(claimed) != want:
                    problems.append(
                        f"{doc}: claims {claimed} for {label}, measured {want}"
                    )

    # A claim shape that matches NOTHING anywhere is a rule with no subject.
    # Half of the first version's check was exactly this and nobody noticed,
    # because a vacuous arm and a passing arm look identical from outside.
    for pattern, key, label in CLAIMS:
        if pattern not in seen and not isinstance(m.get(key), dict):
            problems.append(
                f"NO DOCUMENT claims {label}: this arm of the check has no subject "
                "and proves nothing (docs/standards/non-vacuity.md, NV-3)"
            )
    return problems, notes


def self_test() -> int:
    """Every rule against input that violates it AND input that must not trip it.

    **It drives `_check` and `main` — the REAL functions.** The first version
    reimplemented the matching loop inline, so it tested a copy of the code: a
    review deleted twelve production rules one at a time, `main()`'s
    `if problems:` among them, and this self-test stayed **green for all twelve**.
    A self-test that does not call the thing it tests is the purest form of the
    defect this whole file exists to prevent.
    """
    failures = 0
    m = {"rust_tests": 283, "dp_kernel_lib_tests": 315, "max_decision_id": 372,
         "max_seam_id": 18, "hook_gate_scripts": 38,
         "contract_hub_lines": 202, "contract_substrate_lines": 157,
         "contract_lines": {"a.md": 202, "b.md": 157}}

    def check_block(name: str, text: str, expect_problems: int, expect_notes: int = 0) -> None:
        """Drive the REAL `_check` over one synthetic document."""
        nonlocal failures
        problems, notes = _check(m, scopes=(("<probe>", "@@", "@@END"),),
                                 read=lambda _: f"@@\n{text}\n@@END")
        # The coverage arm reports every claim shape with no subject anywhere;
        # a single-block probe cannot carry them all, so they are filtered out
        # and covered by their own case below.
        real = [x for x in problems if not x.startswith("NO DOCUMENT")]
        ok = len(real) == expect_problems and len(notes) == expect_notes
        failures += 0 if ok else 1
        detail = f"expected {expect_problems}p/{expect_notes}n, got {len(real)}p/{len(notes)}n"
        print(f"  {'ok ' if ok else 'FAIL'} {name}: {detail}")
        if not ok:
            for x in real + notes:
                print(f"        {x}")

    check_block("a correct test count passes", "**283 passed, 0 failed**", 0)
    check_block("a stale test count is caught", "**281 passed, 0 failed**", 1)
    check_block("a correct decision range passes", "`D-1`..`D-372`", 0)
    check_block("a stale decision range is caught", "`D-1`..`D-353`", 1)
    check_block("a stale dp-kernel count is caught", "`dp-kernel --lib` **300**", 1)
    check_block("a stale seam range is caught", "`S-11`..`S-15`", 1)
    check_block("a stale gate-script count is caught", "the **37**\ngate scripts", 1)
    check_block("a stale contract line count is caught", "the two contracts are **200** and **157** lines", 1)
    check_block("correct contract line counts pass", "the two contracts are **202** and **157** lines", 0)

    # F6 — a QUOTED historical figure must not block. These blocks are exactly
    # where this project writes "it said X at round seven".
    check_block("a quoted historical figure is not a claim",
                "> Round 5's handoff said **281 passed, 0 failed**, superseded at round 6.", 0)
    check_block("a fenced example is not a claim",
                "```\nAt the seal the log ran `D-1`..`D-353`.\n```", 0)
    check_block("an HTML comment is not a claim",
                "<!-- was: **281 passed, 0 failed** -->", 0)

    # An unmeasurable figure is a NOTE, not a block -- production behaviour, which
    # the inline copy asserted the OPPOSITE of and nothing noticed.
    unmeasurable = {**m, "rust_tests": {"unmeasurable": "cargo is not on PATH"}}
    problems, notes = _check(unmeasurable, scopes=(("<probe>", "@@", "@@END"),),
                             read=lambda _: "@@\n**283 passed, 0 failed**\n@@END")
    real = [x for x in problems if not x.startswith("NO DOCUMENT")]
    if real or len(notes) != 1:
        failures += 1
        print(f"  FAIL an unmeasurable figure must be a NOTE, not a block: {real} / {notes}")
    else:
        print("  ok  an unmeasurable figure is a NOTE, not a block")

    # A moved anchor is a FINDING, not a silent pass.
    problems, _ = _check(m, scopes=(("<probe>", "NO SUCH MARKER", "@@END"),),
                         read=lambda _: "@@\n**281 passed, 0 failed**\n@@END")
    if not any("marker" in x for x in problems):
        failures += 1
        print("  FAIL a moved anchor did not produce a finding")
    else:
        print("  ok  a moved anchor is a finding, not a silent pass")

    # The coverage arm: a claim shape with no subject anywhere.
    problems, _ = _check(m, scopes=(("<probe>", "@@", "@@END"),),
                         read=lambda _: "@@\nnothing here\n@@END")
    if not any(x.startswith("NO DOCUMENT") for x in problems):
        failures += 1
        print("  FAIL the coverage arm did not fire on a block with no claims")
    else:
        print("  ok  a claim shape with no subject anywhere is a finding")

    # `main()` must actually FAIL on a problem. Driven for real with a seeded
    # stale measurement -- the first version short-circuited before the
    # `if problems:` branch, so deleting that branch left the suite green.
    import contextlib
    import io as _io
    stale = {**m, "rust_tests": 1}
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        rc = main(argv=[], measure_fn=lambda: stale)
    if rc == 0:
        failures += 1
        print("  FAIL main() returned 0 with a seeded stale measurement")
    else:
        print("  ok  main() returns non-zero when a figure disagrees")
    with contextlib.redirect_stdout(_io.StringIO()), contextlib.redirect_stderr(_io.StringIO()):
        rc_ok = main(argv=[], measure_fn=lambda: measure())
    if rc_ok != 0:
        failures += 1
        print("  FAIL main() returned non-zero on the real, agreeing documents")
    else:
        print("  ok  main() returns zero when everything agrees")

    # The measurement helpers' guards, each driven directly.
    def guard(name: str, fn, want: str) -> None:
        nonlocal failures
        try:
            fn()
        except Unmeasurable as e:
            ok = want in str(e)
            failures += 0 if ok else 1
            print(f"  {'ok ' if ok else 'FAIL'} {name}: {e}")
            return
        failures += 1
        print(f"  FAIL {name}: no Unmeasurable raised")

    guard("an absent cargo is Unmeasurable, never a crash",
          lambda: _cargo_passed([], which=lambda _: None), "not on PATH")

    class _Red:
        returncode = 101
        stdout = "test result: FAILED. 3 passed; 1 failed"

    guard("a RED build is Unmeasurable, never a count of zero",
          lambda: _cargo_passed([], which=lambda _: "cargo", run=lambda _: _Red()), "not green")
    guard("a document with no bold id is Unmeasurable",
          lambda: _max_id("x", "D", read=lambda _: "no ids here"), "no bold D- id")

    # The hook scan must ignore COMMENTED invocations, or a documented-but-
    # disabled gate would be counted as wired.
    live = _hook_gate_scripts(read=lambda: '"$PY" "$ROOT/scripts/a-gate.py"\n# scripts/b-gate.py\n')
    if live != 1:
        failures += 1
        print(f"  FAIL the hook scan counted a commented invocation: got {live}, want 1")
    else:
        print("  ok  the hook scan ignores commented invocations")

    # Every document this script MUST govern is actually in SCOPES. Iterating
    # SCOPES alone cannot notice a deleted row -- it just iterates one fewer.
    governed = {d for d, _, _ in SCOPES}
    for required in (HANDOFF, RUN_STATE, INDEX):
        if required not in governed:
            failures += 1
            print(f"  FAIL {required} is not in SCOPES, so nothing checks its figures")
    if len(SCOPES) < 4:
        failures += 1
        print(f"  FAIL SCOPES has {len(SCOPES)} entries; the slice board block is one of four")
    if governed >= {HANDOFF, RUN_STATE, INDEX} and len(SCOPES) >= 4:
        print(f"  ok  all {len(SCOPES)} required blocks are in scope")

    # And the REAL documents must each carry at least one governed claim.
    for doc, start_marker, end_marker in SCOPES:
        block = _scope_text(doc, start_marker, end_marker)
        if block is None:
            failures += 1
            print(f"  FAIL {doc}: its own marker does not resolve")
            continue
        subjects = sum(len(re.findall(pat, _claimable(block))) for pat, _, _ in CLAIMS)
        if subjects == 0:
            failures += 1
            print(f"  FAIL {doc}: its block contains NO claim this script governs")
        else:
            print(f"  ok  {doc}: {subjects} claim(s) in scope")

    if failures:
        print(f"\nactor-hub-figures --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nactor-hub-figures --self-test: every rule bites, and none cries wolf")
    return 0


def main(argv: list[str] | None = None, measure_fn=None) -> int:
    """`measure_fn` is injectable so `--self-test` can drive THIS function with a
    seeded stale measurement. The first version short-circuited before the
    `if problems:` branch, so deleting that branch left the suite green."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--print", action="store_true", dest="print_only",
                    help="measurements only; never fails")
    ap.add_argument("--check", action="store_true",
                    help="accepted for compatibility; checking is the default")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args(argv)

    if args.self_test:
        return self_test()

    m = (measure_fn or measure)()
    print(json.dumps(m, indent=2, default=str))
    if args.print_only:
        return 0

    problems, notes = _check(m)
    for n in notes:
        print(f"actor-hub-figures: NOTE — {n}")
    if problems:
        print(f"\nactor-hub-figures: {len(problems)} disagreement(s)\n", file=sys.stderr)
        for p in problems:
            print("  " + p, file=sys.stderr)
        print(
            "\nA figure that disagrees with this script is wrong by construction. "
            "READ the measurement above; do not advance the number.",
            file=sys.stderr,
        )
        return 1

    print("\nactor-hub-figures: every governed figure agrees with the artifacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
