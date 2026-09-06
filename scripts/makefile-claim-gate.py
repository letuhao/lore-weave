#!/usr/bin/env python3
"""makefile-claim-gate — the Makefile's PASS lines must not claim more than they ran.

`make ci-local` ends by printing **"All local CI gates PASS"**. Derived 2026-08-30, it runs:

    15 lints (the LINTS list) + 4 Go contract suites + eventgen-validate + cargo check

The repo has **117 discovered gates**, and `gate-wiring-gate --run-all` — the thing CI actually
runs as its gate suite — was RED on two of them at the time this was written. So the sentence a
developer reads before pushing claimed a green gate suite it never invoked, and named the wrong
noun while doing it: those are LINTS, not gates.

**This is T48k's defect in a Makefile.** That row found `plan-final-verification` reporting
*"every gate is green"* while running 6 of 113, and fixed it by making the sentence say what it
ran. The same sentence was sitting one directory up the whole time.

WHAT IT CHECKS, AND WHY EACH HALF
─────────────────────────────────
  1 COUNTED    a message of the form "All <N> <things> PASS" must have N equal to the length of
               the list the target iterates. `lint` prints "All 15 L1.K lints PASS" with 15
               TYPED IN; add a lint and the message is wrong on the commit that adds it.
  2 SCOPED     a message may not call something a "gate suite" / "CI gates" unless the target
               invokes the gate runner. Renaming the noun is the cheap half of honesty and the
               half that rots first.

Both are needed. A message can carry a correct number and still overclaim its subject, which is
exactly what "All local CI gates PASS" did: 15 is a true count of lints and none of them is a
gate.

Usage
    python scripts/makefile-claim-gate.py --selftest
    python scripts/makefile-claim-gate.py
"""
from __future__ import annotations

import argparse
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAKEFILE = os.path.join(ROOT, "Makefile")

#: Words that promise the GATE suite rather than a lint sweep. A target using one of these must
#: invoke the runner; the runner is the only thing that iterates all 117.
GATE_WORDS = ("ci gates", "all gates", "gate suite", "every gate")
#: What invoking the gate suite looks like.
RUNNER = "gate-wiring-gate.py --run-all"


def invokes_runner(src: str) -> bool:
    """Does the Makefile RUN the gate runner, or merely NAME it?

    Found by biting. The first version asked `RUNNER not in src`, and the honesty note this
    same cycle added to `ci-local` — "CI runs them via scripts/gate-wiring-gate.py --run-all
    (415s). This target does not." — contains that exact string. **The check was satisfied by
    a sentence saying the opposite of what it tests for**, and bite A silently passed.

    A recipe line is TAB-indented and is not an `@echo` or a comment. Mentioning the runner in
    prose proves nothing; invoking it is a command.
    """
    for line in src.split(chr(10)):
        if RUNNER not in line:
            continue
        body = line.lstrip("	")
        if line.startswith("	") and not body.lstrip("@").startswith(("echo", "#")):
            return True
    return False

OK, MISCOUNTED, OVERCLAIMED, ERROR = "OK", "MISCOUNTED", "OVERCLAIMED", "ERROR"


def lints_in(src: str) -> list[str]:
    """The LINTS list, following backslash continuations."""
    lines = src.split(chr(10))
    idx = [n for n, l in enumerate(lines) if l.startswith("LINTS")]
    if not idx:
        return []
    names: list[str] = []
    n = idx[0]
    while True:
        body = lines[n].split(":=", 1)[-1] if n == idx[0] else lines[n]
        names += [t for t in body.replace("\\", "").split() if t]
        if not lines[n].rstrip().endswith("\\"):
            break
        n += 1
    return names


def claims_in(src: str) -> list[tuple[int, str]]:
    """Every `All … PASS` line, with its number when it carries one."""
    out = []
    for line in src.split(chr(10)):
        m = re.search(r"All\s+(\d+)?\s*([^\"']*?)\s*PASS", line)
        if m and "echo" in line:
            out.append((int(m.group(1)) if m.group(1) else 0, line.strip()))
    return out


def verdict(src: str | None) -> dict:
    """Pure. The Makefile's own PASS sentences against what its targets iterate."""
    if not src:
        return {"verdict": ERROR, "reason": "no Makefile to read — an unreadable input is "
                                            "never a pass"}
    lints = lints_in(src)
    claims = claims_in(src)
    if not claims:
        return {"verdict": OK, "reason": "no `All … PASS` claim in the Makefile"}

    miscounted = [c for n, c in claims if n and lints and n != len(lints) and "lint" in c.lower()]
    if miscounted:
        return {"verdict": MISCOUNTED, "claims": miscounted, "lints": len(lints), "reason":
                f"a PASS line names a count that is not the {len(lints)} lint(s) the target "
                f"iterates. The number is typed, so it is wrong on the commit that adds a lint"}

    overclaimed = [c for _n, c in claims
                   if any(w in c.lower() for w in GATE_WORDS) and not invokes_runner(src)]
    if overclaimed:
        return {"verdict": OVERCLAIMED, "claims": overclaimed, "reason":
                "a PASS line promises the GATE suite while the Makefile never invokes the "
                "runner. 15 lints is a true count of lints and none of them is a gate — T48k's "
                "defect, one directory up"}
    # `claim_count`, NOT `claims`: the failing branches put a LIST under `claims` and main()
    # iterates it. Returning an int under the same key crashed the OK path -- and the selftest
    # drives verdict() rather than main(), so it never saw it. T48ac's shape once more: the
    # pure function was right and the wiring around it was not.
    return {"verdict": OK, "lints": len(lints), "claim_count": len(claims), "reason":
            f"{len(claims)} PASS claim(s), each counting the {len(lints)} lint(s) it runs and "
            f"none promising a gate suite it does not invoke"}


def _main_rc() -> int:
    """Run main() with stdout muted — the success path has to be exercised, not just parsed."""
    import contextlib
    import io as _io
    with contextlib.redirect_stdout(_io.StringIO()):
        return main([])


def _selftest() -> int:
    good = chr(10).join(["LINTS := \\", "\ta \\", "\tb", "lint:",
                         '\t@echo "All 2 L1.K lints PASS"'])
    miscount = good.replace("All 2", "All 7")
    overclaim = good.replace("All 2 L1.K lints PASS", "All local CI gates PASS")
    withrunner = overclaim.replace("lint:", "lint:" + chr(10)
                                   + "\tpython scripts/gate-wiring-gate.py --run-all")
    #: THE CASE THAT BIT. The runner named inside an @echo, not invoked — which is exactly the
    #: shape of the honesty note this cycle added to `ci-local`, and it made bite A pass.
    mentions = overclaim.replace(
        "lint:", "lint:" + chr(10)
        + '\t@echo "CI runs it via scripts/gate-wiring-gate.py --run-all. This does not."')
    with open(MAKEFILE, encoding="utf-8") as fh:
        real = fh.read()

    cases = [
        ("a counted claim matching its list is OK", verdict(good), OK),
        ("THE TYPED NUMBER: a count that does not match the list is MISCOUNTED",
         verdict(miscount), MISCOUNTED),
        ("THE WRONG NOUN: promising a gate suite without invoking the runner",
         verdict(overclaim), OVERCLAIMED),
        ("...and the SAME sentence is fine once the target actually runs the runner — a case "
         "the check was not written against",
         verdict(withrunner), OK),
        ("MENTIONING the runner in an @echo is not INVOKING it — this exact false negative "
         "let bite A pass, because the honesty note names the very command it disclaims",
         verdict(mentions), OVERCLAIMED),
        ("...and invokes_runner tells the two apart",
         (invokes_runner(withrunner), invokes_runner(mentions)), (True, False)),
        ("no Makefile is ERROR, never a pass", verdict(None), ERROR),
        ("a Makefile with no claim at all is OK", verdict("LINTS := \\" + chr(10) + "\ta"), OK),
        ("the LINTS parser follows continuations", len(lints_in(good)), 2),
        ("...and returns [] when there is no list", lints_in("all:" + chr(10) + "\t@echo hi"), []),
        ("the REAL Makefile parses and its list is non-empty", len(lints_in(real)) > 0, True),
        ("THE WIRING: main() runs clean on the real Makefile — the OK branch CRASHED with "
         "'int object is not iterable' because it reused the `claims` key the failing branches "
         "fill with a list, and a selftest that drives verdict() alone could not see it",
         _main_rc(), 0),
    ]
    failures = 0
    print("makefile-claim-gate - selftest (offline)")
    for label, got, want in cases:
        actual = got["verdict"] if isinstance(got, dict) and "verdict" in got else got
        ok = actual == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {actual}")
    print(chr(10) + "  all checks passed" if not failures
          else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args(argv)
    if args.selftest:
        return _selftest()
    try:
        with open(MAKEFILE, encoding="utf-8") as fh:
            src = fh.read()
    except OSError:
        src = None
    v = verdict(src)
    print(f"[makefile-claim-gate] lints {len((lints_in(src) if src else []))} · "
          f"claims {len(claims_in(src)) if src else 0}")
    print(f"[makefile-claim-gate] {'OK' if v['verdict'] == OK else 'FAIL'} — "
          f"{v['verdict']}: {v['reason']}")
    for c in v.get("claims", []):
        print(f"    {c}")
    return 0 if v["verdict"] == OK else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
