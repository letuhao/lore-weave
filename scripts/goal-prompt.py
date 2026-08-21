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

    python scripts/goal-prompt.py              # print `/goal <condition>`, ready to paste
    python scripts/goal-prompt.py --check      # budget, hand-backs, queue coverage
    python scripts/goal-prompt.py --selftest   # prove each of those can go red

WHAT `--check` ACTUALLY CHECKS, and why each one exists
-------------------------------------------------------
Audited 2026-08-14 against the hand-written original, which was green-looking and had two
defects that only measurement found:

- **Hand-backs are DERIVED.** The literal list was missing **T35** — and T35 was the RESUME.
  The prompt would have started a long autonomous run on a row carrying a ⏸ POST-REVIEW
  checkpoint while naming four *other* rows as the only reasons to stop. A stop list is the
  one part of this prompt whose incompleteness is dangerous rather than untidy.
- **Every open row is in a lane, or excused in writing.** `QC-5` was open, listed as a
  checkpoint, and named by no run — a long run would have worked A→B→C→D and never heard of
  it. Unreachable is invisible in exactly the way finished is.
- **Derived is asserted against the EMITTED TEXT.** Biting the derivation back to a literal
  left `--check` reporting "5 hand-back rows" while the output had lost T35, because it was
  asking the deriver instead of reading the result.
- **Headroom is reported.** At 96 % of budget the number that predicts the next outage is how
  much room the RESUME line has left, so it is printed rather than discovered.

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
#:
#: ⚠️ Measured on the CONDITION only. The `/goal ` prefix below is the command, not part of
#: what gets counted — charging the condition for it would silently cost six characters of a
#: budget that is already 94 % spent.
BUDGET = 4000

#: Headroom below this and the next RESUME edit breaks the command. Reported by `--check` as a
#: WARNING rather than a failure: a prompt at 98 % is still correct today, and failing on it
#: would block a session for a problem that has not happened yet. But it is the number that
#: predicts the next outage, so it is printed rather than left to be discovered.
MIN_HEADROOM = 150

#: Emitted ahead of the condition so the output is ONE paste rather than a paste plus a typed
#: command. Retyping the command is the same failure as retyping the condition, one token
#: smaller.
PREFIX = "/goal "

#: The QUEUE, as sequenced by the spec sections named beside it. Rows are filtered against the
#: plan's checkboxes on every run, so a finished row leaves the queue without anyone editing
#: this list — the staleness the 08-14 audit was about.
QUEUE: list[tuple[str, str, list[str]]] = [
    ("A identity", "§6.1", ["T35", "T32", "T33", "QC-6"]),
    ("B caches", "§6.6/6.5", ["T39", "T40", "T51"]),
    ("C vector", "§3.1", ["QC-3", "T25"]),
    ("D close", "§6.3/6.4", ["T44", "T45", "T46", "T47", "T48", "T49"]),
    # 🔴 QC-5 had NO LANE. It was open, listed as a ⏸ checkpoint, and named by no run — so a
    # long run following this queue would never have reached it. Found by the coverage check
    # below, which is why that check exists rather than a promise to remember.
    ("E critic", "§2.1", ["QC-5"]),
]

#: Rows that END a run — DERIVED from the plan, never hand-listed.
#:
#: 🔴 The hand-written version was missing **T35**, and T35 was the RESUME. The prompt would
#: have sent a long autonomous run at a row carrying a ⏸ POST-REVIEW checkpoint while telling
#: it to stop only for four other rows — straight through a hand-back the plan requires. A
#: stop list is the one part of this prompt whose incompleteness is dangerous rather than
#: merely untidy, so it is the last thing that should have been a literal.
#:
#: `⛔` = the row's own text declares a stop condition. `⏸` = a POST-REVIEW checkpoint.
#: Attribution reuses `plan-progress-block.owner_of`, so a marker written inside another row's
#: evidence block does not leak — the same defect that credited T39 with 16/24 blocks.
STOP_KINDS = {"⏸": "a ⏸ POST-REVIEW checkpoint", "⛔": "a stop condition fires"}

#: Open rows deliberately absent from QUEUE, each with the reason. Anything open and NOT here
#: and NOT in a lane is an ORPHAN: a row a long run following this prompt never reaches. QC-5
#: was exactly that — open, listed as a checkpoint, and in no lane.
QUEUE_EXCLUDED = {
    "T17": "§1.3 says its ceiling should not reach zero; it moves opportunistically",
}

RULES = """1 Measure DATA on the real stack (5555/7688); run CODE on lw-iso (base+20000).
2 A number that reads as success is guilty until checked. RUN it, don't read it.
3 A criterion that cannot fail is not a criterion; validate a detector on a case it was NOT derived from, else it is green by construction.
4 A switch has a TIER before a name: deploy ceiling, per-book work.settings, or run param.
5 A gate's number moves in the SAME COMMIT as the code that moved it. So does a scope list.
6 Anything that WRITES goes to a throwaway DB. Dev Postgres and Neo4j are READ-ONLY — a count is a read, a MERGE is not. EXCEPT the GRANTS below, which are authorised.
7 Glossary migrations are an append-only ledger: new step, never edit.
8 MEASURE THE BATCH BEFORE BUILDING IT. Three times this week it killed the batch; that was the result.
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
Commit and push every cycle. Keep the four plan gates green (verify, row-honesty, progress-block --check, acceptance --floor)."""

#: What the PO authorised on 2026-08-21, verbatim enough to act on. This block exists because a
#: goal prompt whose STOP list re-blocks work that was just approved sends a whole session back
#: to the same four questions — which is exactly what fifteen consecutive stop-hook firings were.
GRANTS = """GRANTS (PO 2026-08-21) — authorised; rule 6 and the ⏸ rows do not bar these:
· SOAK: `docker compose up -d knowledge-service` from infra/. Config is right (infra/.env:12);
  the CONTAINER is stale. Arms dual-write. Verify with soak-armed-gate.
· RECANON: `recanon_honorifics --apply` on the dev graph. Dry (1819/1/6) → apply → dry (0).
· QC-3 SIGNED OFF: adopt halfvec_hnsw; MED-2 → migration ticket, MED-3 accept-and-document.
· QC-5 CLAUSE 1 → 1a planted violation attributed (C14 3/3) + 1b re-drafts canon-consistent
  (C15 9/9). Spec in §2.1, re-run."""

STOP_BLOCK = """STOP — these five, nothing else:
· a stop condition fires: {stops}
· a ⏸ POST-REVIEW checkpoint GRANTS does not already decide: {pauses}
· a sealed decision proves wrong
· a PO decision is owed that GRANTS does not cover
· a write to a non-throwaway DB that GRANTS does not authorise
NOT reasons: a row finishing, a green suite, a commit landing, a bug you didn't write, or wanting to check in."""

ROW_RE = re.compile(r"^- \[([ x~])\] \*\*([A-Za-z0-9.\-]+)\*\*", re.MULTILINE)


_HEADING = re.compile(r"^\s{0,4}#{3,4} ")


def _owner_of():
    """`plan-progress-block.owner_of`, imported rather than reimplemented.

    That rule is already audited and selftested — a second copy here would be the "one home"
    violation this repo keeps finding, and the two would disagree the first time either moved.
    """
    import importlib.util
    path = Path(__file__).resolve().parent / "plan-progress-block.py"
    spec = importlib.util.spec_from_file_location("_ppb", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.owner_of


def stop_markers(plan: str) -> dict[str, str]:
    """`{row: '⏸' | '⛔' | '⏸⛔'}` for every OPEN row that declares a hand-back.

    Read off the plan, because the hand-written list was missing T35 — the RESUME row — and a
    stop list that is missing an entry is worse than no stop list: it reads as complete.

    A marker only counts for the row that OWNS the line it sits on. The plan is a
    chronological journal, so a row's span carries other rows' evidence blocks, and scanning
    the raw span would attribute their checkpoints here — the same positional defect that
    credited T39 with 16/24 blocks.
    """
    owner_of = _owner_of()
    lines = plan.split(chr(10))
    rows = [(n, m) for n, m in ((n, ROW_RE.match(l)) for n, l in enumerate(lines)) if m]
    known = [m.group(2) for _, m in rows]
    out: dict[str, str] = {}
    for i, (n, m) in enumerate(rows):
        if m.group(1) != "~":
            continue
        row = m.group(2)
        end = rows[i + 1][0] if i + 1 < len(rows) else len(lines)
        owner, inherited, marks = row, None, set()
        for line in lines[n:end]:
            if _HEADING.match(line):
                owner, named = owner_of(line, known, inherited, row)
                if named:
                    inherited = owner
            if owner != row:
                continue
            # ⚠️ `⏸` IS OVERLOADED and the plan says which meaning is which. Line 1209:
            # *"QC-3, QC-5, QC-7 — the three ⏸ POST-REVIEW checkpoints"*. T35 also carries a
            # ⏸, and it means *"DEFERRED with a mechanism"* — a historical parking note, not a
            # hand-back. The first cut matched the glyph alone and made **T35 a checkpoint**,
            # which would have stopped a long run on the RESUME row for nothing. Over-stopping
            # is the failure the run policy exists to prevent, so the marker must carry the
            # plan's own phrase.
            if "⏸" in line and "POST-REVIEW" in line.upper():
                marks.add("⏸")
            if "stop condition" in line.lower():
                marks.add("⛔")
        if marks:
            out[row] = "".join(sorted(marks))
    return out


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
    stops = stop_markers(plan)
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
        live = [f"{r}{stops.get(r, '')}" for r in rows if state.get(r) != "x"]
        if live:
            lines.append(f"{name} {spec}  " + " → ".join(live))
    lines += [
        "",
        "T17 is NOT the head of the queue, ever again (§1.3). Its FLOOR is what matters.",
        "",
        CYCLE,
        "",
        "RULES",
        RULES,
        "",
        DISCIPLINE,
        "",
        GRANTS,
        "",
        STOP_BLOCK.format(
            stops=", ".join(r for r, k in stops.items() if "⛔" in k) or "none open",
            pauses=", ".join(r for r, k in stops.items() if "⏸" in k) or "none open",
        ),
        "",
        "RESUME: " + resume_line(plan),
        "",
    ]
    return "\n".join(lines)


def orphans(plan: str) -> list[str]:
    """Open rows that no QUEUE lane names and `QUEUE_EXCLUDED` does not excuse.

    🔴 QC-5 was one: open, carrying a ⏸ checkpoint, and named by no run. A long run following
    this prompt would have worked A → B → C → D and stopped, having never heard of it. An
    unreachable task is invisible in exactly the way a finished one is, which is why this is a
    check and not a habit.
    """
    state = row_states(plan)
    queued = {r for _, _, rows in QUEUE for r in rows}
    return [r for r, st in state.items()
            if st == "~" and r not in queued and r not in QUEUE_EXCLUDED]


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    plan = PLAN.read_text(encoding="utf-8")
    out = build(plan)
    bad = orphans(plan)
    if bad:
        print(f"goal-prompt: UNREACHABLE — {bad} are open and in no QUEUE lane.",
              file=sys.stderr)
        print("  Add each to a lane, or to QUEUE_EXCLUDED with the reason. A queue that omits "
              "an open row sends a long run past it silently.", file=sys.stderr)
        return 1
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
        marks = stop_markers(plan)
        pct = 100 * len(out) / BUDGET
        print(f"[goal-prompt] OK — {len(out)}/{BUDGET} chars ({pct:.0f}% used, "
              f"{BUDGET - len(out)} spare); RESUME is {len(resume_line(plan))} of it")
        # 🔴 Assert against the EMITTED TEXT, not against what was derived a line earlier.
        # Found by biting the derivation back to a literal: `build` lost T35's ⏸ while this
        # line still reported "5 hand-back row(s) derived", because it was asking the deriver
        # rather than reading the output. A check that cannot see what the emitter actually
        # did is the inject-at-the-chokepoint shape — it proves the chokepoint, not the wiring.
        # ⚠️ The row must appear WITH ITS MARKER. An earlier cut allowed `or r not in out` as
        # a fallback and was toothless: biting T35's ⏸ out of the queue left this green,
        # because the bare string "T35" still appears in the RESUME line and in rule 12's
        # `T35d`. A check satisfied by an incidental substring is not checking anything.
        unrendered = [r for r in marks
                      if r not in QUEUE_EXCLUDED and f"{r}{marks[r]}" not in out]
        if unrendered:
            print(f"goal-prompt: DERIVED BUT NOT EMITTED — {unrendered}", file=sys.stderr)
            return 1
        print(f"[goal-prompt] {len(marks)} hand-back row(s) derived AND emitted: "
              + ", ".join(f"{r}{k}" for r, k in marks.items()))
        print(f"[goal-prompt] every open row is in a lane or excused "
              f"({len(QUEUE_EXCLUDED)} excused: {', '.join(QUEUE_EXCLUDED)})")
        if BUDGET - len(out) < MIN_HEADROOM:
            print(f"[goal-prompt] WARN — only {BUDGET - len(out)} chars of headroom "
                  f"(floor {MIN_HEADROOM}). The RESUME line is {len(resume_line(plan))} of the "
                  "total and grows every cycle; the next edit is the one that breaks this.")
        return 0
    print(PREFIX + out)
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
              "- [~] **T33** — open, and this row declares a stop condition\n")
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

    # ④ HAND-BACKS ARE DERIVED. The literal this replaced was missing T35 — the RESUME row —
    # so the prompt would have started a long run on a row carrying a ⏸ checkpoint while
    # listing four other rows as the only reasons to stop.
    marked = chr(10).join([
        "**RESUME: x**",
        "- [~] **T33** — open",
        "  ### 🔴 T33a — carries a stop condition",
        "- [~] **T40** — open, no marker anywhere",
    ])
    got = stop_markers(marked)
    check("a stop condition is READ off the row", got.get("T33") == "⛔", str(got))
    check("a row with no marker is not invented", "T40" not in got, str(got))

    # A marker inside ANOTHER row's evidence block must not leak — the positional defect that
    # credited T39 with 16/24 blocks, reproduced here on the more dangerous field.
    leak = chr(10).join([
        "**RESUME: x**",
        "- [~] **T39** — open, and the journal lands under it",
        "  ### ✅ QC-3a — a ⏸ POST-REVIEW checkpoint belonging to QC-3",
        "- [~] **QC-3** — open",
    ])
    lk = stop_markers(leak)
    check("another row's ⏸ does not leak into the row above it", "T39" not in lk, str(lk))

    # `⏸` IS OVERLOADED. The plan uses it for POST-REVIEW checkpoints AND for 'deferred with
    # a mechanism'. Matching the glyph alone made T35 — the RESUME row — a checkpoint, which
    # would stop a long run immediately for nothing.
    overload = chr(10).join([
        "**RESUME: x**",
        "- [~] **QC-3** — open",
        "  ### 🔴 QC-3a — ⏸ POST-REVIEW checkpoint, present evidence and WAIT",
        "- [~] **T35** — open",
        "  ### 🔴 T35z — ⏸ DEFERRED with a mechanism, not merely unstarted",
    ])
    ov = stop_markers(overload)
    check("a ⏸ POST-REVIEW line IS a hand-back", ov.get("QC-3") == "⏸", str(ov))
    check("a ⏸ DEFERRED line is NOT", "T35" not in ov, str(ov))

    # ⑤ AN OPEN ROW IN NO LANE IS AN ERROR. QC-5 was exactly this, and nothing said so.
    stray = chr(10).join([
        "**RESUME: x**", "- [~] **T32** — queued", "- [~] **T99** — in no lane",
    ])
    check("an open row in no lane is reported", "T99" in orphans(stray), str(orphans(stray)))
    real_plan = PLAN.read_text(encoding="utf-8")
    check("an EXCLUDED row is not reported",
          all(r not in orphans(real_plan) for r in QUEUE_EXCLUDED))
    check("the real plan has no orphans today", orphans(real_plan) == [], str(orphans(real_plan)))

    # ⑥ The output must be ONE paste: command included.
    check("the emitted text carries the /goal prefix", PREFIX.strip() == "/goal")
    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
