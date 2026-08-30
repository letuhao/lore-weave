#!/usr/bin/env python3
"""Generate the `/goal` prompt for `docs/plans/2026-08-30-runstate-leftovers.md`.

WHY A SECOND GENERATOR AND NOT A SECOND HAND-WRITTEN PROMPT
------------------------------------------------------------
Exactly the reasons `goal-prompt.py` gives for the first one, which are not hypothetical
here: that file's docstring records a goal prompt that named a finished row and held a
session on the wrong task for ten batches, and a hand-written version that overflowed the
4000-character budget — where the natural repair under time pressure is to cut from the
bottom, and the bottom is the STOP list.

So the queue is DERIVED from the plan's checkboxes on every run. A row that gets ticked
leaves the prompt without anyone editing this file.

WHY IT IMPORTS RATHER THAN COPIES
----------------------------------
`RULES`, `CYCLE` and `DISCIPLINE` are the same thirteen rules and the same cycle contract;
they did not stop being true when the plan they were written for was archived. Copying them
would create the drift this repo keeps finding — two homes for one rule, one of them going
stale silently. They are imported from `goal-prompt.py`, which stays their single home.

What is NOT imported is `GRANTS` and `STOP_BLOCK`: those name that plan's rows, its stop
conditions and its ⏸ checkpoints, none of which exist here. Reusing them would tell a session
to stop on things that are finished and archived.

    python scripts/goal-prompt-leftovers.py            # print `/goal <condition>`
    python scripts/goal-prompt-leftovers.py --check    # budget, queue coverage, RESUME
    python scripts/goal-prompt-leftovers.py --selftest # prove each check can go red
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "docs" / "plans" / "2026-08-30-runstate-leftovers.md"

#: `/goal` refuses anything longer. A hard interface limit, not a style guide. Measured on the
#: CONDITION only — the `/goal ` prefix is the command, not part of what is counted.
BUDGET = 4000
MIN_HEADROOM = 150
PREFIX = "/goal "

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*\s+—\s+\*\*(.+?)\*\*",
                    re.MULTILINE)
RESUME_RE = re.compile(r"^RESUME:\s*(.+?)(?=\n\n)", re.MULTILINE | re.DOTALL)


def _invariants() -> tuple[str, str]:
    """`RULES` and `CYCLE` from goal-prompt.py — one home, imported rather than copied.

    ⚠️ **`DISCIPLINE` is deliberately NOT imported.** Its last line reads *"Keep the four plan
    gates green (verify, row-honesty, progress-block --check, acceptance --floor)"*, and all
    four resolve their subject through `plan_location.py`, which knows exactly one document:
    the ARCHIVED refactor plan. They are blind to this one. Carrying that sentence over would
    tell a session its work is verified by four gates that never read it — the T49 defect
    pointed at a different document instead of at nothing.
    """
    src = REPO / "scripts" / "goal-prompt.py"
    spec = importlib.util.spec_from_file_location("_gp", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.RULES, mod.CYCLE


#: This plan's own stop list. Shorter than the refactor's because this plan has no ⏸
#: checkpoints and no ⛔ stop conditions — but the SHAPE is kept, because the shape is what
#: makes a long autonomous run safe, and the one part whose incompleteness is dangerous
#: rather than untidy.
STOP_BLOCK = """STOP — these three, nothing else:
· a PO decision is owed. Two already are, and are NOT rows: the 32 causal labels (a signature; --score refuses an assistant) and §19's merge-to-main steps (the PO deferred these — do not start them).
· a write to a non-throwaway DB. lw-iso IS authorised for L2 and L7; the dev store (5555/7688) is READ-ONLY, and a DROP there is never authorised.
· a sealed decision (§22, §23) proves wrong.
NOT reasons: a row finishing, a green suite, a commit landing, an empty queue, wanting to check in, or a row turning out already done — that last is a RESULT: tick it with the measurement, take the next row."""

DISCIPLINE = """NO "BLOCKED", NO "DEFERRED". A row may be unfinished; it may not be undecided. Decide it, spec it in docs/specs/2026-08-13-knowledge-refactor-open-decisions.md, keep building. No prose-only cycles. Commit every cycle.
NOTHING AUDITS THIS PLAN. verify/row-honesty/progress-block/acceptance all resolve through plan_location.py, which knows only the ARCHIVED refactor — they will stay green whatever you do here. The row's own BITE is the entire verification; there is no second net. Keep gate-wiring-gate --run-all green: that one reads the code."""

SCOPE = """SCOPE: nothing here blocks anything, and several rows may be smaller than written."""


def rows() -> list[tuple[str, str, str]]:
    text = PLAN.read_text(encoding="utf-8")
    return [(m.group(1), m.group(2), m.group(3)) for m in ROW_RE.finditer(text)]


def resume() -> str:
    text = PLAN.read_text(encoding="utf-8")
    m = RESUME_RE.search(text)
    return " ".join(m.group(1).split()) if m else ""


def condition() -> str:
    rules, cycle = _invariants()
    open_rows = [(rid, title) for mark, rid, title in rows() if mark != "x"]
    queue = "\n".join(f"· {rid} — {t}" for rid, t in open_rows)
    return "\n".join([
        "Run the GOAL in docs/plans/2026-08-30-runstate-leftovers.md — \"every leftover the "
        "knowledge-architecture run state left behind is FIXED or DECIDED IN WRITING, and a "
        "command proves which\".",
        "",
        f"QUEUE ({len(open_rows)} open, work the row RESUME names first):",
        queue,
        "",
        f"RESUME: {resume()}",
        "",
        SCOPE,
        "",
        cycle,
        "",
        DISCIPLINE,
        "",
        "RULES:",
        rules,
        "",
        STOP_BLOCK,
    ])


def check() -> int:
    bad = 0
    cond = condition()
    n = len(cond)
    head = BUDGET - n
    print(f"[goal-leftovers] condition {n} chars, budget {BUDGET}, headroom {head}")
    if n > BUDGET:
        print(f"[goal-leftovers] ERROR — over budget by {n - BUDGET}. Shorten the plan's "
              f"RESUME line or a row title. NEVER truncate: the bottom is the STOP list.")
        bad = 1
    elif head < MIN_HEADROOM:
        print(f"[goal-leftovers] WARN — headroom {head} < {MIN_HEADROOM}; the next RESUME "
              f"edit may break the command.")

    all_rows = rows()
    if not all_rows:
        print("[goal-leftovers] ERROR — the plan yielded NO rows. A queue that parses to "
              "nothing looks like a finished plan and is a broken regex.")
        return 1
    # Every open row must reach the OUTPUT, asserted against the emitted text rather than the
    # deriver — biting the derivation back to a literal is exactly how the first generator
    # reported "5 hand-back rows" while the output had lost one.
    missing = [rid for mark, rid, _ in all_rows if mark != "x" and f"· {rid} —" not in cond]
    if missing:
        print(f"[goal-leftovers] ERROR — open row(s) absent from the emitted queue: {missing}")
        bad = 1
    else:
        print(f"[goal-leftovers] every open row reaches the output "
              f"({sum(1 for m, _, _ in all_rows if m != 'x')} of {len(all_rows)})")

    r = resume()
    if not r:
        print("[goal-leftovers] ERROR — the plan has no RESUME line; the prompt would not "
              "say which row to start.")
        bad = 1
    elif not any(r.startswith(rid) for _, rid, _ in all_rows):
        print(f"[goal-leftovers] ERROR — RESUME names no row in this plan: {r[:60]!r}")
        bad = 1
    else:
        print(f"[goal-leftovers] RESUME resolves to a real row")

    # The invariants must actually have been imported, not silently defaulted to "".
    rules, cycle = _invariants()
    if not all((rules.strip(), cycle.strip())):
        print("[goal-leftovers] ERROR — an invariant block imported EMPTY from goal-prompt.py")
        bad = 1
    for name, block in (("RULES", rules), ("CYCLE", cycle), ("DISCIPLINE", DISCIPLINE)):
        if block.strip() not in cond:
            print(f"[goal-leftovers] ERROR — {name} did not reach the emitted condition")
            bad = 1
    if not bad:
        print("[goal-leftovers] OK")
    return bad


def selftest() -> int:
    """Each check driven to RED on a plan that triggers it. A checker whose failure arms have
    never run is a checker that reports OK for one reason."""
    import tempfile
    global PLAN
    real = PLAN
    cases = []

    def run(name, body, expect_bad):
        global PLAN
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "p.md"
            p.write_text(body, encoding="utf-8")
            PLAN = p
            import contextlib
            import io as _io
            buf = _io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = check()
            PLAN = real
        ok = (rc != 0) == expect_bad
        cases.append((name, ok, buf.getvalue().strip().split("\n")[-1]))

    GOOD = ("RESUME: L1 — do the thing.\n\n"
            "- [ ] **L1** — **a real row** with words after it.\n")
    run("a well-formed plan passes", GOOD, False)
    run("NO ROWS is an error, not an empty queue",
        "RESUME: L1 — x.\n\nnothing here\n", True)
    run("an open row missing from the output is an error",
        GOOD.replace("- [ ] **L1**", "- [ ] **L1x**"), True)
    run("a plan with no RESUME is an error",
        "- [ ] **L1** — **a real row** here.\n", True)
    run("a RESUME naming no row in this plan is an error",
        "RESUME: L9 — a row that is not here.\n\n"
        "- [ ] **L1** — **a real row** here.\n", True)
    run("a ticked row does not need to reach the queue",
        "RESUME: L1 — do the thing.\n\n"
        "- [ ] **L1** — **a real row** here.\n"
        "- [x] **L2** — **a finished row** here.\n", False)

    PLAN = real
    for name, ok, last in cases:
        print(f"  {'ok  ' if ok else 'FAIL'} {name}")
        if not ok:
            print(f"       last line: {last}")
    bad = sum(1 for _, ok, _ in cases if not ok)
    neg = sum(1 for n, _, _ in cases if "error" in n or "not" in n)
    print(f"\ngoal-prompt-leftovers --selftest: "
          f"{'OK' if not bad else 'FAILED'} ({len(cases)} cases, {neg} of them negative)")
    return 1 if bad else 0


def main(argv: list[str]) -> int:
    if "--selftest" in argv:
        return selftest()
    if "--check" in argv:
        return check()
    print(PREFIX + condition())
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
