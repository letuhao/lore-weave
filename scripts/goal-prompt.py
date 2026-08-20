#!/usr/bin/env python3
"""Generate the `/goal` prompt for the knowledge-architecture refactor.

WHY THIS EXISTS
---------------
`/goal` takes a **4000-character** condition and it is retyped every session. Retyping is
where two failures live, and both have already happened here:

- **It goes stale.** The 08-14 audit found the run-state crediting T39 with 16/24 blocks it
  did not own, and a hand-written `T17 (13/20)` sitting six lines above a generated `12/20`.
  A goal prompt naming a finished row, or a count nobody recomputed, sends a session at the
  wrong task — which is exactly how T17 held the pointer for ten batches.
- **It overflows silently.** The first hand-written version was 4819 characters. `/goal`
  refused it, which was lucky: the natural repair under time pressure is to delete whatever
  is at the bottom, and the bottom is the STOP list.

So the invariant half (rules, cycle contract, stop shape) is a CONSTANT in this file — one
home, edited once — and the variable half (which rows are still open, what RESUME says) is
read off the plan every time. A row that gets ticked drops out of the queue by itself.

    python scripts/goal-prompt.py              # print the prompt
    python scripts/goal-prompt.py --check      # exit 1 if it would not fit
    python scripts/goal-prompt.py --selftest   # prove the budget check can fail

⚠️ **It never truncates.** Over budget is an ERROR naming the section sizes, because a prompt
silently cut to fit is a prompt whose last section is missing — and the last section is STOP.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PLAN = REPO / "docs" / "plans" / "2026-08-09-knowledge-architecture-refactor.md"

#: `/goal` refuses anything longer. Not a style guide — a hard interface limit.
BUDGET = 4000

#: The QUEUE, as sequenced by the spec sections named beside it. Rows are filtered against the
#: plan's checkboxes on every run, so a finished row leaves the queue without anyone editing
#: this list — the staleness the 08-14 audit was about.
QUEUE: list[tuple[str, str, list[str]]] = [
    ("A identity", "§6.1", ["T35", "T32", "T33", "QC-6"]),
    ("B caches", "§6.6/6.5", ["T39", "T40", "T51"]),
    ("C vector", "§3.1", ["QC-3", "T25"]),
    ("D close", "§6.3/6.4", ["T44", "T45", "T46", "T47", "T48", "T49"]),
]

#: Rows that END a run. `⛔` = a stop condition in the row itself; `⏸` = a POST-REVIEW
#: checkpoint. Both are hand-back points, and they are the ONLY ones besides a sealed decision
#: proving wrong, a PO decision, and a write that would reach a real database.
STOPS = {"T33": "⛔", "T49": "⛔", "QC-3": "⏸", "QC-5": "⏸"}

RULES = """1 Measure DATA on the real stack (5555/7688); run CODE on lw-iso (base+20000).
2 A number that reads as success is guilty until checked. RUN it, don't read it.
3 A criterion that cannot fail is not a criterion; validate a detector on a case it was NOT derived from, else it is green by construction.
4 A switch has a TIER before a name: deploy ceiling, per-book work.settings, or run param.
5 A gate's number moves in the SAME COMMIT as the code that moved it. So does a scope list.
6 Anything that WRITES goes to a throwaway DB. Dev Postgres and Neo4j are READ-ONLY — a count is a read, a MERGE is not.
7 Glossary migrations are an append-only ledger: new step, never edit.
8 MEASURE THE BATCH BEFORE BUILDING IT. Twice this week it killed the batch; that was the result.
9 An adapter that cannot honour an operation RAISES, naming its spec section. Never empty, never half-written, never silently truncated.
10 Do NOT fan out subagents per list element. No workflows, no AgentTool unless I ask.
11 Tick the box in the COMMIT THAT DOES THE WORK.
12 NAME THE ROW in every evidence-block heading (T35d, A11, QC-5) — positional attribution is what mis-credited T39.
13 A divergence RECORDED is not a divergence DIAGNOSED. Prove which side is wrong FROM THE WORKLOAD, not by analogy."""

CYCLE = """CYCLE: READ the sealed row + its spec § → BUILD → BITE → QC → EVIDENCE → ADVANCE. No step skipped. No bite output or no pasted evidence ⇒ FAILS CLOSED: row stays [~] with a five-element deferral, never [x].
QC is three controls, each getting output or an explicit "N/A because…": (a) gates green, a NEW gate needs --selftest (a hand-bite is invisible to CI); (b) live smoke vs REBUILT images if a service seam is crossed; (c) real-run data if the task produces data.
BITE = mutate by LINE NUMBER (exact-match replace silently no-ops on CRLF), watch it red for the RIGHT reason, restore, paste it."""

DISCIPLINE = """NO "BLOCKED", NO "DEFERRED". A task may be unfinished; it may not be undecided. Decide it, spec it in docs/specs/2026-08-13-knowledge-refactor-open-decisions.md, keep building.
No prose-only cycles. Editing the plan is step 5 of a cycle, never a cycle of its own.
Commit and push every cycle. Keep plan-final-verification, plan-row-honesty-gate, plan-progress-block --check and plan-acceptance --floor green."""

STOP_BLOCK = """STOP — these five, nothing else:
· a stop condition fires: {stops}
· a ⏸ POST-REVIEW checkpoint: {pauses}
· a sealed decision proves wrong
· a PO decision is owed: OD-1, OD-2, OD-3
· a write would touch a non-throwaway database
NOT reasons: a row finishing, a green suite, a commit landing, a bug you didn't write, or wanting to check in."""

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*", re.MULTILINE)


def row_states(plan: str) -> dict[str, str]:
    """`{row: ' '|'x'|'~'}`. The checkboxes are the truth; everything else is commentary."""
    return {m.group(2): m.group(1) for m in ROW_RE.finditer(plan)}


def resume_line(plan: str) -> str:
    """The plan's own RESUME line, stripped to plain text.

    Read rather than restated: it is regenerated beside the progress block, so quoting it is
    the one way this prompt cannot disagree with the plan about what comes next.
    """
    m = re.search(r"^\*\*RESUME:\s*(.+?)\*\*\s*$", plan, re.MULTILINE)
    if not m:
        raise SystemExit("goal-prompt: the plan has no **RESUME:** line to quote")
    text = m.group(1)
    text = re.sub(r"\*\*|`|~~", "", text)              # bold, code, strike
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)  # links keep their label
    return re.sub(r"\s+", " ", text).strip()


def build(plan: str) -> str:
    state = row_states(plan)
    lines = [
        'Run the GOAL in docs/plans/2026-08-09-knowledge-architecture-refactor.md — "the '
        'architecture is implemented correctly and a live run proves it."',
        "",
        "RUN LONG. Do not hand back between tasks. Stop ONLY for the STOP list. Otherwise: "
        "finish the row, commit, push, take the next one.",
        "",
        "QUEUE (the spec sets this order, not preference)",
    ]
    for name, spec, rows in QUEUE:
        # A ticked row leaves the queue on its own. The alternative — a hand-kept list — is
        # what the 08-14 audit found pointing at work that had shipped days earlier.
        live = [f"{r}{STOPS.get(r, '')}" for r in rows if state.get(r) != "x"]
        if live:
            lines.append(f"{name} {spec}  " + " → ".join(live))
    lines += [
        "",
        "T17 is NOT the head of the queue, ever again. §1.3 says its ceiling should not reach "
        "zero and A10 priced the rest at 1 module per port operation. Its FLOOR is what "
        "matters. Opportunistic, never the task.",
        "",
        CYCLE,
        "",
        "RULES",
        RULES,
        "",
        DISCIPLINE,
        "",
        STOP_BLOCK.format(
            stops=", ".join(r for r, k in STOPS.items() if k == "⛔" and state.get(r) != "x"),
            pauses=", ".join(r for r, k in STOPS.items() if k == "⏸" and state.get(r) != "x"),
        ),
        "",
        "RESUME: " + resume_line(plan),
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    plan = PLAN.read_text(encoding="utf-8")
    out = build(plan)
    if len(out) > BUDGET:
        # Never truncate. The section that would be lost is the one at the bottom, and the
        # bottom is STOP — the half that makes a long run safe.
        print(f"goal-prompt: OVER BUDGET — {len(out)} chars, /goal takes {BUDGET}.",
              file=sys.stderr)
        print(f"  RESUME line alone is {len(resume_line(plan))} chars. Shorten it in the plan; "
              "a RESUME that will not fit in a goal prompt is too long to be read anyway.",
              file=sys.stderr)
        return 1
    if "--check" in sys.argv:
        print(f"[goal-prompt] OK — {len(out)} chars, {BUDGET - len(out)} to spare")
        return 0
    print(out)
    return 0


def selftest() -> int:
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("goal-prompt · selftest")
    sample = ("**RESUME: `T35` — decide whether it CLOSES.**\n"
              "- [x] **T35** — done\n"
              "- [~] **T32** — open\n"
              "- [~] **T33** — open\n")
    out = build(sample)
    # Scoped to the QUEUE section, not the whole prompt: rule 12 names `T35d` as an example of
    # a well-formed heading, so a whole-document search reports a hit that means nothing. (The
    # first cut did exactly that and went red against correct code.)
    queue = out.split("QUEUE (")[1].split("T17 is NOT")[0]
    # ① A ticked row must LEAVE the queue. This is the whole reason the prompt is generated:
    # a hand-kept queue naming a finished row is what sent ten batches at T17.
    check("a ticked row drops out of the queue", "T35" not in queue, queue.strip())
    check("an open row stays", "T32" in queue and "T33" in queue)
    check("a stop marker rides along", "T33⛔" in queue)
    check("the RESUME line is quoted from the plan", "decide whether it CLOSES" in out)
    check("markdown is stripped from it", "`T35`" not in out.split("RESUME:")[-1])

    # ② The budget check must be able to FAIL, or it is decoration. A gate nobody has watched
    # go red is one of this plan's named failure modes.
    long_resume = "**RESUME: " + ("x" * 5000) + "**\n- [~] **T32** — open\n"
    over = build(long_resume)
    check("the budget check can go red", len(over) > BUDGET, f"{len(over)}")

    # ③ And the real prompt must currently fit, or the command is broken for its only user.
    real = build(PLAN.read_text(encoding="utf-8"))
    check("the REAL prompt fits today", len(real) <= BUDGET, f"{len(real)} > {BUDGET}")

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
