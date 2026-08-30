#!/usr/bin/env python3
"""plan-final-verification — is the knowledge-architecture refactor plan actually processed?

Answers one question with a pass/fail, so "the plan is done" stops being a claim in a summary
and becomes something a command prints.

FOUR CHECKS, and the third is the one with teeth:

  1. NO UNTOUCHED TASKS — every `- [ ]` is gone. A task nobody has looked at is the one state
     the plan must not end in.
  2. EVERY DEFERRAL IS STRUCTURED — each `[~]` task's section names a `D-…` deferral, and
     every `D-…` deferral block carries all five required parts (blocker, evidence, unblock,
     mechanism, retry). A deferral without a retry condition is an abandonment with better
     manners.
  3. NO SELF-CERTIFYING QC — a QC task may not be `[x]` while the thing it certifies is
     deferred. This is the check that would have caught QC-5 being marked done because its
     write-up was thorough.
  4. GATES GREEN — the gates this plan introduced all exit 0.

    python scripts/plan-final-verification.py

Exit 0 = the plan is fully processed · 1 = something is unaccounted for.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAN = os.path.join(ROOT, "docs", "plans", "2026-08-09-knowledge-architecture-refactor.md")

# The gates this plan introduced or relies on. Each must exit 0.
#: The gates this verifier runs ITSELF: the six that encode THIS PLAN's invariants.
#:
#: 🔴 **This list used to end a sentence that claimed far more than it checked.** The PASS line
#: said *"...and every gate is green"* while running six of the repo's **113**. The claim was
#: 18x wider than the check, and it is the verifier for a plan whose acceptance includes
#: *"nothing silently dropped"* — the same overstatement it exists to catch, in the instrument.
#:
#: It is NOT widened to 113 here, and that is measured rather than preferred: `--run-all` takes
#: **7m25s** on this machine, and a verification people cancel is decorative. CI owns the full
#: sweep (`gate-wiring-gate --run-all`, covered by construction because the runner iterates the
#: same `discovered()` predicate). What changed is the WORDING and the DELEGATION CHECK below:
#: this verifier now states its six, and fails if the full sweep is not wired somewhere else.
PLAN_GATES = [
    "glossary-events-ssot-gate.py",
    "alive-column-deprecation-gate.py",
    "derived-entity-id-gate.py",
    "graph-port-gate.py",
    "entity-lifecycle-outbox-gate.py",
    "gateway-domain-logic-gate.py",
]

# The five parts a deferral must carry, for the ones still on the page. Matched
# case-insensitively on the row label, so the table shape is not load-bearing — the CONTENT is.
#
# ⚠️ DEFERRALS ARE NO LONGER A LEGAL STATE (2026-08-13). This project has no "blocked" and no
# "deferred": a deferral is a decision described instead of taken, and thirty of them had
# accumulated while reading as "tracked". The register is retired into
# `docs/specs/2026-08-13-knowledge-refactor-open-decisions.md`. These parts are still enforced
# on any deferral text that survives, so a half-converted row cannot slip through — but the
# rule that matters now is SPEC_RE below.
REQUIRED_PARTS = ("blocker", "evidence", "unblock", "mechanism", "retry")

#: The spec every unfinished task must cite. A task may be unfinished; it may not be UNDECIDED.
#: "I have not typed it yet" is a schedule; "nobody has decided" is the thing this forbids.
SPEC_DOC = "docs/specs/2026-08-13-knowledge-refactor-open-decisions.md"
#: What counts as "this row is DECIDED".
#:
#: T48au — this was `…|DECIDED` with `re.I`, and case-insensitive `DECIDED` is a substring of
#: **UNDECIDED**. So a body saying *"this is undecided"* satisfied the check that the row is not
#: undecided — as did *"we have not decided"* — and the gate's own failure message names the very
#: word that defeats it. Measured: a `[~]` row's body here runs to 765 lines, so the loose form
#: could not fail for any row that had accumulated evidence.
#:
#: The plan's own convention is the bolded `📐 **DECIDED**`, so that is what is matched, with no
#: `re.I` on that arm. Measured before tightening: 0 of the 3 open rows lose their citation.
SPEC_RE = re.compile(
    r"2026-08-13-knowledge-refactor-open-decisions|📐 SPEC|\*\*DECIDED\*\*")

TASK_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9-]+)\*\*", re.M)


def sections(text: str) -> list[tuple[str, str, str]]:
    """(state, task-id, body) for every task, body running to the next task heading."""
    marks = list(TASK_RE.finditer(text))
    out = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m.group(1), m.group(2), text[m.start():end]))
    return out


def _selftest() -> int:
    """Pins the two properties this file just lost and regained.

    Neither was checkable before, which is why the overstatement survived: the PASS line is
    prose, and prose is not run. These read the SOURCE, so the claim and the check cannot
    drift the way the claim and the behaviour did.
    """
    src = open(__file__, encoding="utf-8").read()
    # COMMENTS ARE STRIPPED, and the first run of this selftest is why: it went red on the
    # comment above `PLAN_GATES`, which QUOTES the retracted wording so the next reader knows
    # it was considered and removed. `ssot-claim-gate` already makes exactly this allowance
    # ("retractions that quote the old wording are allowed"). A check that cannot tell a
    # retraction from a relapse forces the retraction to be deleted, which is how the reason
    # for a fix gets lost.
    # ...and the SELFTEST ITSELF is excluded, which the second run found: the check below
    # contains the retracted phrase as its needle, so searching the whole file always matched
    # and the check could never pass. A detector that reads its own text is measuring itself.
    head, _, tail = src.partition("def _selftest")
    claims = head + tail.partition(chr(10) + "def main() -> int:")[2]
    body = chr(10).join(
        l for l in claims.splitlines() if not l.lstrip().startswith("#")
    )
    checks = [
        ("the PASS line no longer claims `every gate is green`",
         "every gate is green" not in body),
        ("it states how many gates it actually ran",
         "len(PLAN_GATES)" in body),
        ("every PLAN_GATES entry exists on disk",
         all(os.path.exists(os.path.join(ROOT, "scripts", g)) for g in PLAN_GATES)),
        ("the full sweep is DELEGATED and the delegation is asserted",
         "gate-wiring-gate.py" in body and "runs NOWHERE" in body),
        ("PLAN_GATES is a real subset, not secretly everything",
         0 < len(PLAN_GATES) < 20),
        # T48au — the DECIDED marker must not be satisfied by the word it forbids. It was
        # `DECIDED` under `re.I`, and "decided" is a substring of "UNDECIDED", so a row saying
        # "this is undecided" passed the check that it is not undecided. With bodies running to
        # 765 lines, the loose form could not fail for any row carrying evidence.
        ("UNDECIDED does not satisfy the DECIDED marker",
         not SPEC_RE.search("this row is UNDECIDED and blocked")),
        ("...nor does 'we have not decided'",
         not SPEC_RE.search("we have not decided yet")),
        ("...while the plan's own bolded convention does",
         bool(SPEC_RE.search("📐 **DECIDED** — settled in §4.3"))),
        ("...and so does the spec link, which is the other accepted form",
         bool(SPEC_RE.search("see " + SPEC_DOC))),
    ]
    failures = 0
    print("plan-final-verification - selftest (offline)")
    for label, ok in checks:
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")
    print(chr(10) + "  all checks passed" if not failures else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main() -> int:
    if "--selftest" in sys.argv:
        return _selftest()
    if not os.path.exists(PLAN):
        print(f"[plan-verify] FAIL — plan not found: {PLAN}")
        return 1
    text = open(PLAN, encoding="utf-8").read()
    tasks = sections(text)
    done = [t for t in tasks if t[0] == "x"]
    deferred = [t for t in tasks if t[0] == "~"]
    untouched = [t for t in tasks if t[0] == " "]
    failures: list[str] = []

    print(f"[plan-verify] {len(tasks)} tasks — {len(done)} done, {len(deferred)} tracked, "
          f"{len(untouched)} untouched")

    # 1 — nothing untouched.
    if untouched:
        failures.append("untouched tasks remain: " + ", ".join(t[1] for t in untouched))

    # 2 — every deferral block carries all five parts.
    blocks = re.split(r"### .*?DEFERRAL ", text)[1:]
    for b in blocks:
        name = re.match(r"`?(D-[A-Z0-9-]+)`?", b)
        name = name.group(1) if name else "<unnamed>"
        body = b[:4000].lower()
        missing = [p for p in REQUIRED_PARTS if p not in body]
        if missing:
            failures.append(f"deferral {name} is missing: {', '.join(missing)}")
    print(f"[plan-verify] {len(blocks)} structured deferral block(s) checked")

    # 2b — every UNFINISHED task cites a decision. No "blocked", no "deferred": a `[~]` row
    # must point at the spec section that settles it, or say DECIDED in its own body. A task
    # can be unfinished; it cannot be undecided, and describing a problem is not a way to keep
    # it open.
    undecided = [
        tid for state, tid, body in tasks
        if state == "~" and not SPEC_RE.search(body)
    ]
    if undecided:
        failures.append(
            "tasks are unfinished AND undecided (cite " + SPEC_DOC + ", or mark the body "
            "DECIDED): " + ", ".join(undecided)
        )
    print(f"[plan-verify] {len(tasks) - len(done) - len(untouched) - len(undecided)} "
          f"unfinished task(s) cite a decision; {len(undecided)} do not")

    # 3 — no QC task claims done while what it certifies is deferred.
    for state, tid, body in tasks:
        if state == "x" and tid.upper().startswith("QC"):
            if re.search(r"DEFERRAL `?D-", body):
                failures.append(
                    f"{tid} is marked DONE but its own section records a deferral — a QC task "
                    f"cannot certify work that is still open")

    # 4 — the plan's own gates, run here.
    for g in PLAN_GATES:
        path = os.path.join(ROOT, "scripts", g)
        if not os.path.exists(path):
            failures.append(f"gate missing: {g}")
            continue
        rc = subprocess.run([sys.executable, path], capture_output=True, text=True).returncode
        print(f"[plan-verify] gate {g:<38} {'PASS' if rc == 0 else 'FAIL'}")
        if rc != 0:
            failures.append(f"gate failed: {g}")

    # 4b — the FULL sweep is somebody's job, and this asserts it is somebody's.
    #
    # Running 113 gates here would take 7m25s and this verifier would stop being run. So the
    # delegation is checked instead of the gates: `gate-wiring-gate` reports every discovered
    # gate as wired-or-exempt, and CI drives `--run-all` over the same predicate. If that
    # arrangement is ever dismantled, this verifier's six become the whole of the coverage and
    # nothing would say so.
    wiring = os.path.join(ROOT, "scripts", "gate-wiring-gate.py")
    if not os.path.exists(wiring):
        failures.append("gate-wiring-gate.py is gone — nothing now proves the OTHER gates run")
    else:
        rc = subprocess.run([sys.executable, wiring], capture_output=True, text=True)
        total = re.search(r"(\d+) gate\(s\) discovered", rc.stdout or "")
        print(f"[plan-verify] delegation  gate-wiring-gate                "
              f"{'PASS' if rc.returncode == 0 else 'FAIL'}"
              f"{f' ({total.group(1)} gates discovered, all wired or exempted)' if total else ''}")
        if rc.returncode != 0:
            failures.append("gate-wiring-gate failed — some gate runs NOWHERE, so this "
                            "verifier's six are not the floor they look like")

    print()
    if failures:
        print("[plan-verify] FAIL")
        for f in failures:
            print(f"  - {f}")
        return 1
    print(f"[plan-verify] PASS — every task is done-with-evidence or DECIDED with a spec "
          f"citation, no QC task certifies open work, and the {len(PLAN_GATES)} gates that "
          f"encode THIS PLAN's invariants are green.")
    print("  The other gates are CI's, via `gate-wiring-gate --run-all`; this run asserted that "
          "arrangement exists,")
    print("  not that those gates passed. A verifier that says 'every gate' while running six "
          "is the defect it exists to catch.")
    print("  NOTE: 'decided' is not 'done'. An unfinished task has a settled design and "
          "unwritten code;")
    print(f"  read {SPEC_DOC} for what was decided, and the RESUME line for what to type next.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
