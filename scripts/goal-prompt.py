#!/usr/bin/env python3
"""Generate a `/goal` condition from a plan or RUN-STATE. Any plan, any agent.

WHY THIS EXISTS
---------------
`/goal` takes a **4000-character** condition and it gets retyped every session.
Retyping is where two failures live, and both have happened:

- **It goes stale.** A goal prompt naming a finished row sends a session at the
  wrong task. In the repo this tool came from, one row held the RESUME pointer
  for ten consecutive batches after it had shipped.
- **It overflows silently.** The first hand-written version was 4819 characters.
  `/goal` refused it, which was luck: the natural repair under time pressure is
  to cut from the bottom, and the bottom is the STOP list — the half that makes
  a long autonomous run safe.

So the invariant half (the cycle contract, the stop shape, the budget) is a
constant here — one home, edited once — and the variable half (which rows are
open, what comes next) is read off the plan every time. **A row that gets ticked
leaves the queue by itself.**

    python scripts/goal-prompt.py --plan docs/plans/X.md            # print it
    python scripts/goal-prompt.py --plan docs/plans/X.md --check    # audit it
    python scripts/goal-prompt.py --selftest                        # prove it bites

WHAT WAS DE-BIASED, AND WHY IT MATTERS
--------------------------------------
This started as a tool for ONE plan in ONE repo, and nine things were welded to
it: the plan path, a literal lane→row QUEUE, a literal excluded row, thirteen
rules naming specific ports and services, a discipline block naming specific
gates, a STOP list naming specific decision ids, a hardcoded goal sentence, an
import of a helper script that does not exist everywhere, and a row syntax
(`- [~] **T35**`) that only one family of plans uses.

Every one of those is now either **derived from the plan** or **declared by the
plan**, and the tool runs with **zero configuration** against a plan it has
never seen. That is the point: a tool that only works on the plan it was written
for is a tool that gets rewritten, and the rewrite is where the staleness this
file exists to prevent comes back.

THE TWO HOMES, and why there is no config file
----------------------------------------------
1. **Here** — what is true of every long run: never truncate, stop only for the
   listed reasons, a finished row leaves the queue.
2. **The plan** — what is true of THIS run: the goal sentence, the lanes, the
   repo's own rules. Declared in an optional ```goal-prompt fenced block.

A third home — a `goal-prompt.yaml` somewhere — was considered and rejected. The
rules for a run belong beside the run, or they drift from it; and a file an
agent has to FIND is a file an agent will not find.

⚠️ **It never truncates.** Over budget is an ERROR naming the section sizes,
because a prompt silently cut to fit is a prompt whose last section is missing.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

#: `/goal` refuses anything longer. Not a style guide — a hard interface limit.
#:
#: ⚠️ Measured on the CONDITION only. The `/goal ` prefix is the command, not
#: part of what gets counted — charging the condition for it would silently cost
#: six characters of a budget that is usually nearly spent.
BUDGET = 4000

#: Headroom below this and the next edit breaks the command. A WARNING, not a
#: failure: a prompt at 98% is still correct today, and failing on it would block
#: a session for a problem that has not happened. But it is the number that
#: predicts the next outage, so it is printed rather than discovered.
MIN_HEADROOM = 150

#: Emitted ahead of the condition so the output is ONE paste rather than a paste
#: plus a typed command. Retyping the command is the same failure as retyping the
#: condition, one token smaller.
PREFIX = "/goal "

# ─── the invariant half ──────────────────────────────────────────────────────
#
# Nothing below names a service, a port, a row id or a repo. If you find
# yourself wanting to add one, it belongs in the plan's ```goal-prompt block.

CYCLE = (
    "CYCLE: READ the row + what it cites -> BUILD -> BITE -> VERIFY -> EVIDENCE -> ADVANCE. "
    "No step skipped. No bite output or no pasted evidence => FAILS CLOSED: the row stays open "
    "with a written reason, never ticked.\n"
    "BITE = break the guarded thing, watch it go RED for the RIGHT reason, restore it "
    "byte-exact, paste both outputs. A test you added is not evidence; a test you watched fail "
    "is."
)

RULES = (
    "1 A number that reads as success is guilty until checked. RUN it, do not read it.\n"
    "2 A check that cannot fail is not a check. Prove it can go red before trusting it green.\n"
    "3 Measure the row BEFORE building it. The measurement often kills the row, and that is "
    "the result.\n"
    "4 A claim without a command behind it is a memory. Re-measure; do not recall.\n"
    "5 Anything that WRITES goes to a throwaway database. A count is a read; an INSERT is not.\n"
    "6 A gate's baseline moves in the SAME COMMIT as the code that moved it.\n"
    "7 Tick the box in the commit that does the work.\n"
    "8 Do NOT fan out subagents per list element. Group by file or domain, or stay solo.\n"
    "9 Record the near-misses as they happen. A run that ends with an empty drift log is "
    "dishonest, not clean."
)

DISCIPLINE = (
    'NO "BLOCKED" that means "I would have to build it". A row may be unfinished; it may not '
    "be undecided. Decide it, write down the decision, keep going.\n"
    "No prose-only cycles. Editing the plan is a STEP of a cycle, never a cycle of its own.\n"
    "Commit every cycle. Keep the repo's gates green; a gate you disabled is a gate that "
    "failed."
)

STOP_HEAD = "STOP — these, and nothing else:"
STOP_TAIL = (
    "NOT reasons to stop: a row finishing, a green suite, a commit landing, a bug you did not "
    "write, context filling, or wanting to check in."
)

#: The two universal stops. A plan adds its own via `po_decisions:`.
STOP_ALWAYS = [
    "a sealed decision turns out to be wrong",
    "an action is destructive or irreversible and was not authorised",
]

# ─── reading a plan ──────────────────────────────────────────────────────────

#: Format A — the checkbox list: `- [~] **T35** — …`
ROW_CHECKBOX = re.compile(r"^\s*[-*]\s*\[([ x~])\]\s*\*\*([A-Za-z0-9.\-]+)\*\*", re.MULTILINE)

#: Format B — the board table: `| \`P7\` the caller … | \`[x]\` | evidence |`
#:
#: Two formats rather than one because plans in the wild use both, and a tool
#: that reads only the author's own dialect is the bias this file exists to
#: remove. Detection is by COUNT, not by guessing: whichever yields more rows
#: wins, and a tie goes to the checkbox form because it is unambiguous.
ROW_TABLE = re.compile(r"^\|\s*(~~)?\s*`([A-Za-z0-9.\-]+)`", re.MULTILINE)

#: Where "what comes next" is written. Several spellings, because plans differ
#: and the alternative is each plan editing the tool.
RESUME_PATTERNS = [
    re.compile(r"^\*\*RESUME:\s*(.+?)\*\*\s*$", re.MULTILINE),
    re.compile(r"^RESUME:\s*(.+?)\s*$", re.MULTILINE),
    re.compile(r"^>?\s*\*\*▶\s*(?:DO\s+)?NEXT[^*]*\*\*\s*[—:-]?\s*(.+?)\s*$", re.MULTILINE),
]

#: The plan's own declarations. Optional — everything has a derived default.
DECL_BLOCK = re.compile(r"```goal-prompt\s*\n(.*?)```", re.DOTALL)


def _strip_md(text: str) -> str:
    """Plain text out of markdown, so the prompt reads as prose.

    Links keep their LABEL and lose their target: a goal condition is read by a
    model with no filesystem, so a path in it is noise that costs budget.
    """
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*|`|~~|__", "", text)
    return re.sub(r"\s+", " ", text).strip()


def row_states(plan: str) -> dict[str, str]:
    """`{row_id: ' '|'x'|'~'}`. The plan's own marks are the truth.

    `x` = done. `~` = open/in-flight. ` ` = not started. Both open kinds are
    queued; only `x` leaves.
    """
    cb = {m.group(2): m.group(1) for m in ROW_CHECKBOX.finditer(plan)}

    tbl: dict[str, str] = {}
    for line in plan.split("\n"):
        m = ROW_TABLE.match(line)
        if not m:
            continue
        rid, struck = m.group(2), bool(m.group(1))
        # PARKED FIRST, and the order is the bug this comment marks. A parked row
        # carries no tick box — that is what parked MEANS — so when this test ran
        # after the state branches it was unreachable behind their `continue`,
        # and a row the PO had parked would have headed the queue. The selftest
        # caught it on the first run.
        if "🅿" in line or "PARKED" in line:
            tbl[rid] = "x"
        # A struck-through id, a tick box, or a ✅ all mean the same thing. Read
        # all three: a board that says `~~DF1a~~ ✅ CLOSED` and a board that says
        # `| P7 | [x] |` are the same statement in two dialects.
        elif struck or "✅" in line or "[x]" in line:
            tbl[rid] = "x"
        elif "[~]" in line:
            tbl[rid] = "~"
        elif "[ ]" in line:
            tbl[rid] = " "
    return cb if len(cb) >= len(tbl) else tbl


def declarations(plan: str) -> dict[str, object]:
    """The plan's optional ```goal-prompt block.

    A tiny key: value / key: [list] / key: | block reader rather than a YAML
    dependency — this script must run on a bare checkout, and a tool that needs
    `pip install` before it can print a sentence will not be run.
    """
    m = DECL_BLOCK.search(plan)
    if not m:
        return {}
    out: dict[str, object] = {}
    key, buf = None, []
    for raw in m.group(1).split("\n"):
        if key and (raw.startswith("  ") or not raw.strip()):
            buf.append(raw[2:] if raw.startswith("  ") else "")
            continue
        if key:
            out[key] = "\n".join(buf).rstrip()
            key, buf = None, []
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        k, v = k.strip(), v.strip()
        if v == "|":
            key, buf = k, []
        elif v.startswith("[") and v.endswith("]"):
            out[k] = [x.strip() for x in v[1:-1].split(",") if x.strip()]
        else:
            out[k] = v
    if key:
        out[key] = "\n".join(buf).rstrip()
    return out


def stop_markers(plan: str, states: dict[str, str]) -> dict[str, str]:
    """`{row: '⏸' | '⛔' | '⏸⛔'}` for every OPEN row that declares a hand-back.

    Read off the plan, never hand-listed. In the repo this came from the
    hand-written list was missing the RESUME row itself — so the prompt would
    have sent a long run at a row carrying a checkpoint while naming four OTHER
    rows as the only reasons to stop. **A stop list that is missing an entry is
    worse than no stop list, because it reads as complete.**

    ⚠️ `⏸` is OVERLOADED in real plans: it marks both "POST-REVIEW checkpoint"
    (a genuine hand-back) and "deferred with a mechanism" (a historical note).
    Matching the glyph alone made the RESUME row a checkpoint and would have
    stopped a long run immediately for nothing. So the line must carry the WORD
    as well as the glyph.
    """
    out: dict[str, str] = {}
    lines = plan.split("\n")
    positions: list[tuple[int, str, str]] = []
    for n, line in enumerate(lines):
        if m := ROW_CHECKBOX.match(line):
            positions.append((n, m.group(2), "list"))
        elif m := ROW_TABLE.match(line):
            positions.append((n, m.group(2), "table"))
    for i, (n, row, kind) in enumerate(positions):
        # Only rows the BOARD tracks. A drift register or an open-row table also
        # puts a backticked id in its first cell, and those are not slices — a
        # long run cannot "stop at" a row that was never in the queue.
        if row not in states or states.get(row) == "x":
            continue
        # A TABLE row is ONE line. A checkbox row owns everything up to the next
        # row, because that dialect keeps its evidence beneath the row.
        #
        # 🔴 Not cosmetic. With the span running to the next match, the LAST
        # table row in a file absorbed everything after it — including the
        # RESUME line — so a RESUME reading "the ⏸ POST-REVIEW checkpoint" turned
        # a drift-register row into a hand-back. Found by running this tool on
        # the plan it was generating a goal for, which is the only reason it was
        # found at all: it needs a marker AFTER the last row to show up.
        end = n + 1 if kind == "table" else (
            positions[i + 1][0] if i + 1 < len(positions) else len(lines))
        marks = set()
        for line in lines[n:end]:
            up = line.upper()
            if "⏸" in line and ("POST-REVIEW" in up or "CHECKPOINT" in up):
                marks.add("⏸")
            if "STOP CONDITION" in up or "⛔" in line:
                marks.add("⛔")
        if marks:
            out[row] = "".join(sorted(marks))
    return out


def resume_line(plan: str) -> str:
    """What the plan says comes next, quoted rather than restated.

    Quoting is the one way this prompt cannot disagree with the plan about the
    next task. When a plan says nothing, that is reported as a fact rather than
    invented — an invented next step is exactly the drift the tool prevents.
    """
    for pat in RESUME_PATTERNS:
        m = pat.search(plan)
        if m and _strip_md(m.group(1)):
            return _strip_md(m.group(1))
    return ""


def queue(plan: str, states: dict[str, str], decl: dict[str, object]) -> list[str]:
    """The open rows, in the order the plan lists them.

    Derived by DEFAULT: board order is an ordering the author already chose, and
    a second hand-kept list is a second thing to go stale. A plan that needs
    lanes declares them; a plan that does not gets its board back.
    """
    excluded = set(decl.get("excluded", []) or [])
    lanes = decl.get("lanes")
    stops = stop_markers(plan, states)
    order = [r for r in _row_order(plan) if states.get(r) != "x" and r not in excluded]

    if not lanes:
        return [f"{r}{stops.get(r, '')}" for r in order]

    out, seen = [], set()
    for lane in str(lanes).split("\n"):
        if not lane.strip():
            continue
        name, _, rows = lane.partition("=")
        live = [f"{r.strip()}{stops.get(r.strip(), '')}"
                for r in rows.split(",") if r.strip() and states.get(r.strip()) != "x"]
        seen.update(r.strip() for r in rows.split(",") if r.strip())
        if live:
            out.append(f"{name.strip()}  " + " -> ".join(live))
    return out


def _row_order(plan: str) -> list[str]:
    """Row ids in the order they appear, de-duplicated, first mention wins."""
    seen, order = set(), []
    for line in plan.split("\n"):
        m = ROW_CHECKBOX.match(line) or ROW_TABLE.match(line)
        if m and m.group(2) not in seen:
            seen.add(m.group(2))
            order.append(m.group(2))
    return order


def orphans(plan: str, states: dict[str, str], decl: dict[str, object]) -> list[str]:
    """Open rows that no declared lane names and no exclusion excuses.

    Only meaningful when a plan declares lanes. In that repo one row was open,
    carried a checkpoint, and was named by no lane — a long run would have
    worked through every lane and never heard of it. **An unreachable task is
    invisible in exactly the way a finished one is**, which is why this is a
    check and not a habit.
    """
    if not decl.get("lanes"):
        return []
    excluded = set(decl.get("excluded", []) or [])
    named = {r.strip()
             for lane in str(decl["lanes"]).split("\n")
             for r in lane.partition("=")[2].split(",") if r.strip()}
    return [r for r, st in states.items()
            if st != "x" and r not in named and r not in excluded]


def build(plan: str, plan_path: str = "the plan") -> str:
    states = row_states(plan)
    decl = declarations(plan)
    stops = stop_markers(plan, states)
    q = queue(plan, states, decl)
    resume = resume_line(plan)

    goal = decl.get("goal") or f"finish the open rows in {plan_path}"
    lines = [
        f"Run the GOAL in {plan_path} — \"{goal}\".",
        "",
        "RUN LONG. Do not hand back between rows. Stop ONLY for the STOP list. Otherwise: "
        "finish the row, commit, take the next one.",
        "",
    ]
    if q:
        lines += ["QUEUE (the plan sets this order, not preference)"]
        lines += q if decl.get("lanes") else ["  " + " -> ".join(q)]
        lines.append("")
    if decl.get("note"):
        lines += [str(decl["note"]), ""]

    lines += [CYCLE, "", "RULES", str(decl.get("rules") or RULES), "",
              str(decl.get("discipline") or DISCIPLINE), "", STOP_HEAD]

    for s in STOP_ALWAYS:
        lines.append(f"- {s}")
    if any("⛔" in k for k in stops.values()):
        lines.append("- a stop condition fires: "
                     + ", ".join(r for r, k in stops.items() if "⛔" in k))
    if any("⏸" in k for k in stops.values()):
        lines.append("- a checkpoint is reached: "
                     + ", ".join(r for r, k in stops.items() if "⏸" in k))
    if decl.get("po_decisions"):
        lines.append("- a decision is owed to the human: "
                     + ", ".join(decl["po_decisions"]))  # type: ignore[arg-type]
    if decl.get("stop"):
        for extra in str(decl["stop"]).split("\n"):
            if extra.strip():
                lines.append(f"- {extra.strip()}")
    lines += [STOP_TAIL, ""]

    # An absent RESUME is STATED, never invented. A goal prompt that made up a
    # next step would be the exact drift this tool exists to prevent, and it
    # would be invisible — it reads like the plan said it.
    lines.append("RESUME: " + (resume or
                 "the plan names no next step — read its board and pick the first open row."))
    return "\n".join(lines)


# ─── cli ─────────────────────────────────────────────────────────────────────

def _discover() -> Path | None:
    """The single most-recently-modified RUN-STATE, when exactly one is obvious.

    A convenience, never a guess presented as fact: with zero or several
    candidates it returns None and the caller demands `--plan`. Picking one of
    five plans by mtime and printing a 4000-character goal for it is precisely
    the wrong-task failure this file opens with.
    """
    cands = sorted((REPO / "docs" / "plans").glob("*RUN-STATE.md"),
                   key=lambda p: p.stat().st_mtime, reverse=True)
    return cands[0] if len(cands) == 1 else None


def main() -> int:
    ap = argparse.ArgumentParser(description="Emit a /goal condition from a plan.")
    ap.add_argument("--plan", help="path to the plan or RUN-STATE")
    ap.add_argument("--check", action="store_true", help="audit budget, stops and coverage")
    ap.add_argument("--selftest", action="store_true", help="prove each check can go red")
    args = ap.parse_args()

    if args.selftest:
        return selftest()

    path = Path(args.plan) if args.plan else _discover()
    if not path:
        print("goal-prompt: --plan is required (no single obvious RUN-STATE to default to).",
              file=sys.stderr)
        return 2
    if not path.exists():
        print(f"goal-prompt: no such plan: {path}", file=sys.stderr)
        return 2

    plan = path.read_text(encoding="utf-8")
    states = row_states(plan)
    if not states:
        print(f"goal-prompt: {path} has no rows this tool can read.", file=sys.stderr)
        print("  Expected `- [~] **ID** …` or a board table whose first cell is `ID`.",
              file=sys.stderr)
        return 2

    rel = path.as_posix()
    try:
        rel = path.resolve().relative_to(REPO).as_posix()
    except ValueError:
        pass
    out = build(plan, rel)
    decl = declarations(plan)

    bad = orphans(plan, states, decl)
    if bad:
        print(f"goal-prompt: UNREACHABLE — {bad} are open and in no lane.", file=sys.stderr)
        print("  Add each to a lane, or to `excluded:` with the reason. A queue that omits an "
              "open row sends a long run past it silently.", file=sys.stderr)
        return 1
    if len(out) > BUDGET:
        # Never truncate: the section that would be lost is at the bottom, and
        # the bottom is STOP.
        print(f"goal-prompt: OVER BUDGET — {len(out)} chars, /goal takes {BUDGET}.",
              file=sys.stderr)
        r = resume_line(plan)
        print(f"  RESUME is {len(r)} of it; the queue is {sum(len(x) for x in queue(plan, states, decl))}. "
              "Shorten the RESUME line in the plan, or tick what is done.", file=sys.stderr)
        return 1

    if args.check:
        marks = stop_markers(plan, states)
        openn = sum(1 for s in states.values() if s != "x")
        print(f"[goal-prompt] OK — {len(out)}/{BUDGET} chars "
              f"({100 * len(out) / BUDGET:.0f}% used, {BUDGET - len(out)} spare)")
        print(f"[goal-prompt] {openn} open of {len(states)} row(s); "
              f"queue is {'lane-declared' if decl.get('lanes') else 'derived from board order'}")
        # 🔴 Assert against the EMITTED TEXT, not against what was derived a line
        # earlier. A check that asks the deriver instead of reading the output
        # proves the deriver, not the wiring — and the row must appear WITH its
        # marker, or an incidental substring elsewhere satisfies it.
        missing = [r for r in marks if f"{r}{marks[r]}" not in out]
        if missing:
            print(f"goal-prompt: DERIVED BUT NOT EMITTED — {missing}", file=sys.stderr)
            return 1
        print(f"[goal-prompt] {len(marks)} hand-back row(s) derived AND emitted"
              + (": " + ", ".join(f"{r}{k}" for r, k in marks.items()) if marks else ""))
        if not resume_line(plan):
            print("[goal-prompt] WARN — the plan names no next step; the prompt says so rather "
                  "than inventing one, but a RESUME line would be better.")
        if BUDGET - len(out) < MIN_HEADROOM:
            print(f"[goal-prompt] WARN — only {BUDGET - len(out)} chars of headroom "
                  f"(floor {MIN_HEADROOM}). The next edit is the one that breaks this.")
        return 0

    print(PREFIX + out)
    return 0


def selftest() -> int:
    fails: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f" — {detail}" if detail and not cond else ""))
        if not cond:
            fails.append(name)

    print("goal-prompt · selftest")

    # ① Both dialects, because reading only one is the bias this file removes.
    cb = "- [x] **T1** — done\n- [~] **T2** — open\n"
    check("checkbox rows are read", row_states(cb) == {"T1": "x", "T2": "~"}, str(row_states(cb)))
    tbl = ("| `P1` a thing | `[x]` | evidence |\n"
           "| `P2` another | `[ ]` | |\n"
           "| ~~`P0`~~ | ✅ **CLOSED** | done |\n")
    got = row_states(tbl)
    check("board-table rows are read", got == {"P1": "x", "P2": " ", "P0": "x"}, str(got))
    check("a struck-through id counts as done", got.get("P0") == "x", str(got))

    # A parked row must not read as open — it would head the queue.
    parked = "| `X1` a thing | 🅿 PARKED by the PO | |\n| `X2` b | `[ ]` | |\n"
    ps = row_states(parked)
    check("a PARKED row is not queued", ps.get("X1") == "x" and ps.get("X2") == " ", str(ps))

    # ② A ticked row must LEAVE the queue — the whole reason this is generated.
    plan = ("**RESUME: `T2` — do the next thing.**\n"
            "- [x] **T1** — done\n- [~] **T2** — open\n- [~] **T3** — open\n")
    out = build(plan, "p.md")
    q = out.split("QUEUE")[1].split("CYCLE")[0]
    check("a ticked row drops out of the queue", "T1" not in q, q.strip())
    check("open rows stay", "T2" in q and "T3" in q, q.strip())
    check("the RESUME line is quoted from the plan", "do the next thing" in out)
    check("markdown is stripped from it", "`T2`" not in out.split("RESUME:")[-1])

    # ③ An absent RESUME is STATED, not invented.
    noresume = build("- [~] **T9** — open\n", "p.md")
    check("a missing RESUME is declared, not fabricated",
          "names no next step" in noresume, noresume.split("RESUME:")[-1])

    # ④ The budget check must be able to go red, or it is decoration.
    over = build("**RESUME: " + "x" * 5000 + "**\n- [~] **T2** — open\n", "p.md")
    check("the budget check can go red", len(over) > BUDGET, str(len(over)))

    # ⑤ Hand-backs are DERIVED, and `⏸` is overloaded — the glyph alone made the
    # RESUME row a checkpoint and would have stopped a long run for nothing.
    marked = ("- [~] **A1** — open\n"
              "  note: this row declares a stop condition\n"
              "- [~] **A2** — open, ⏸ POST-REVIEW checkpoint here\n"
              "- [~] **A3** — open, ⏸ DEFERRED with a mechanism\n"
              "- [~] **A4** — open, nothing here\n")
    st = row_states(marked)
    mk = stop_markers(marked, st)
    check("a stop condition is read off the row", mk.get("A1") == "⛔", str(mk))
    check("a ⏸ POST-REVIEW line IS a hand-back", mk.get("A2") == "⏸", str(mk))
    check("a ⏸ DEFERRED line is NOT", "A3" not in mk, str(mk))
    check("a row with no marker is not invented", "A4" not in mk, str(mk))
    check("a done row cannot be a hand-back",
          "T1" not in stop_markers("- [x] **T1** — done, stop condition\n",
                                   {"T1": "x"}), "")

    # ⑤b A TABLE row owns ONE LINE, and a row the board does not track is not a
    # hand-back at all. Both halves of a defect found by running this tool on a
    # real plan: the last table row's span ran to EOF, swallowed a RESUME line
    # reading "the ⏸ POST-REVIEW checkpoint", and reported a DRIFT-REGISTER row
    # as a reason to stop a long run. Over-stopping is the failure the run policy
    # exists to prevent, so a false hand-back is not a cosmetic bug.
    # The tracked row must be LAST, or the bug is not reachable: only the final
    # row's span runs to EOF. A first draft of this fixture put a drift row after
    # it, the mutation did not red, and the arm was decoration. Bitten, fixed.
    spanning = chr(10).join([
        "| `B2` another | `[x]` | done |",
        "| `D1` a drift row, tracked by nothing |",
        "| `B1` a slice | `[ ]` | |",
        "",
        "**RESUME: `B1` — and this line mentions a ⏸ POST-REVIEW checkpoint.**",
    ])
    sp = row_states(spanning)
    mk = stop_markers(spanning, sp)
    check("a table row does not absorb the lines after it", "B1" not in mk, str(mk))
    check("a row the board does not track is not a hand-back", "D1" not in mk, str(mk))
    # …and a marker ON a table row's own line still counts, or the fix above
    # would have been "never see anything", which passes both arms for free.
    onrow = "| `B3` a slice ⏸ POST-REVIEW checkpoint | `[ ]` | |"
    check("a marker on the row's OWN line still counts",
          stop_markers(onrow, row_states(onrow)).get("B3") == "⏸",
          str(stop_markers(onrow, row_states(onrow))))

    # ⑥ Derived markers must reach the EMITTED TEXT.
    emitted = build(marked, "p.md")
    check("a derived stop marker is emitted", "A1⛔" in emitted and "A2⏸" in emitted,
          emitted.split(STOP_HEAD)[-1])

    # ⑦ The plan can override, and an absent block must not crash.
    decl_plan = ("```goal-prompt\n"
                 "goal: the thing is done and proven\n"
                 "po_decisions: [OD-1, OD-2]\n"
                 "excluded: [T3]\n"
                 "lanes: |\n"
                 "  A first = T2\n"
                 "  B later = T4\n"
                 "rules: |\n"
                 "  1 only this rule\n"
                 "```\n"
                 "**RESUME: go**\n- [~] **T2** — open\n- [~] **T3** — open\n- [~] **T4** — open\n")
    d = declarations(decl_plan)
    check("a declared goal is read", d.get("goal") == "the thing is done and proven", str(d))
    check("a declared list is read", d.get("po_decisions") == ["OD-1", "OD-2"], str(d))
    check("a declared block is read", str(d.get("rules")).strip() == "1 only this rule", str(d))
    do = build(decl_plan, "p.md")
    check("the declared goal reaches the prompt", "the thing is done and proven" in do)
    check("declared lanes are used", "A first" in do and "B later" in do, do)
    check("a declared rule replaces the default", "only this rule" in do and "guilty until" not in do)
    check("po decisions reach STOP", "OD-1, OD-2" in do, do.split(STOP_HEAD)[-1])
    check("an excluded row is not queued", "T3" not in do.split("CYCLE")[0].split("QUEUE")[-1])
    check("no declaration block is fine", declarations("- [~] **T1**\n") == {})

    # ⑧ An open row in no lane is an ERROR — but only when lanes exist, or every
    # plan without them would report every row.
    stray = decl_plan.replace("- [~] **T4** — open", "- [~] **T4** — open\n- [~] **T99** — stray")
    check("an open row in no lane is reported",
          "T99" in orphans(stray, row_states(stray), declarations(stray)))
    check("no lanes means no orphan noise",
          orphans(plan, row_states(plan), {}) == [])

    # ⑨ One paste, command included.
    check("the emitted text carries the /goal prefix", PREFIX.strip() == "/goal")

    print("\n  all checks passed" if not fails else f"\n  {len(fails)} failure(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
