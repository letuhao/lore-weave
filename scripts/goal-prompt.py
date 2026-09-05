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
#: ⚠ WIDENED by `C1` (2026-08-22). It required a BACKTICKED id, and 30 of 51
#: boards in this repo write a BOLDED one — `| **1** | … | **DONE** |`. Those
#: boards parsed as EMPTY, and a board whose rows are invisible is
#: indistinguishable from a board with none open. `2026-08-02-actor-substrate`
#: — the sibling whose METHOD a whole run copied — carries 218 bolded pipe-rows
#: and read as zero.
ROW_TABLE = re.compile(r"^\|\s*(~~)?\s*(?:`([A-Za-z0-9.\-/]+)`|\*\*([A-Za-z0-9.\-/]+)\*\*)", re.MULTILINE)

#: Format C -- the MARKER FIRST board: `| `[x]` **S0** | what | evidence |`.
#:
#: `C1` of the world-in-a-running-reality board. `ROW_TABLE` reads an id out of
#: cell 0 and `row_states` looks for state in cells 1+, so a board that puts the
#: TICK BOX in cell 0 and the id after it is invisible to both halves at once.
#: 17 rows across two game-track boards.
#:
#: This is the ONLY one of three measured dialect families that got a widening.
#: The other two are refused on their measurement -- see `OR-5`.
ROW_MARKER_FIRST = re.compile(
    r"^\|\s*`?(\[[ x~]\])`?\s*\*\*([A-Za-z0-9.\-/]+)\*\*\s*\|", re.MULTILINE
)

#: A cell is a STATUS cell only if it BEGINS with one of these, after stripping
#: emphasis and whitespace.
#:
#: ⚠ The "begins with" part is `C1`'s third gap and it is the one that silently
#: CLOSED rows. The old reader asked `"[x]" in line`, so a row whose PROSE
#: mentioned a marker was read as carrying it: row `B2` of the space-producers
#: board quoted `[x] manual, [ ] automated` while describing a half-proven
#: thing and was ticked out of its own queue, and so was the row describing
#: THIS defect. A parser that cannot tell a marker from a MENTION of a marker
#: does not merely miss work — it reports work as finished.
#: SYMBOL markers may match as a PREFIX -- a glyph is unambiguous.
DONE_SYMBOLS = ("[x]", "✅", "🅿", "⏭️")
OPEN_SYMBOLS = (("[~]", "~"), ("[ ]", " "), ("⬜", " "))

#: WORD markers must be UPPERCASE in the source and end at a non-letter.
#:
#: ⚠ The first version of this widening allowed any case, and it reintroduced
#: the very bug it was fixing one layer over: `| **8** | Open register | **DONE
#: for this pass** |` read as OPEN because cell 1 begins with the word "Open",
#: and `| `R-57` | OpenMW's preload() ... |` read as OPEN because of "OpenMW".
#: Three false opens on one closed board. A board writing "Open register" as a
#: TITLE is not marking status; a board marking status writes `**DONE**`.
#:
#: `🔴` was in this list too and is now gone: in this repo it is a SEVERITY
#: glyph in finding tables, not a state, and `⬜` already covers the open case in
#: the same tables.
DONE_WORDS = ("DONE", "COMPLETE", "CLOSED", "PARKED", "WAIVED", "APPLIED", "SUPERSEDED", "N/A")
OPEN_WORDS = (("TODO", " "), ("OPEN", " "), ("BLOCKED", " "), ("DOING", "~"), ("PARTIAL", "~"))

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


def _cells(line: str) -> list[str]:
    """A table row's cells, emphasis and whitespace stripped from each edge."""
    return [c.strip().strip("*").strip() for c in line.strip().strip("|").split("|")]


def _cell_state(cell: str) -> str | None:
    """The state a cell DECLARES, or `None` if it merely mentions one.

    Symbols match as a prefix; WORDS must be uppercase and end at a non-letter.
    The test is never `in`. See `DONE_SYMBOLS` and `DONE_WORDS` for what each
    half of that cost before it was made.
    """
    c = cell.lstrip("`*_ ").strip()
    if not c:
        return None
    for mark in DONE_SYMBOLS:
        if c.startswith(mark):
            return "x"
    for mark, state in OPEN_SYMBOLS:
        if c.startswith(mark):
            return state
    # A word marker is UPPERCASE in the source and is a whole word.
    head = c.split()[0].rstrip(".,;:!)") if c.split() else ""
    if head and head == head.upper():
        for mark in DONE_WORDS:
            if head == mark:
                return "x"
        for mark, state in OPEN_WORDS:
            if head == mark:
                return state
    return None


def row_states(plan: str) -> dict[str, str]:
    """`{row_id: ' '|'x'|'~'}`. The plan's own marks are the truth.

    `x` = done. `~` = open/in-flight. ` ` = not started. Both open kinds are
    queued; only `x` leaves.
    """
    cb = {m.group(2): m.group(1) for m in ROW_CHECKBOX.finditer(plan)}

    tbl: dict[str, str] = {}
    for line in plan.split("\n"):
        # Format C first: its cell 0 holds BOTH the marker and the id, so
        # ROW_TABLE would read the marker as the id if it matched at all.
        if mf := ROW_MARKER_FIRST.match(line):
            tbl[mf.group(2)] = {"[x]": "x", "[~]": "~", "[ ]": " "}[mf.group(1)]
            continue
        m = ROW_TABLE.match(line)
        if not m:
            continue
        rid = m.group(2) or m.group(3)
        # A STRUCK id is done however the rest of the row reads -- the strike is
        # on the id itself, which is not a cell that can be mentioned.
        if m.group(1):
            tbl[rid] = "x"
            continue
        # PARKED FIRST, and the order is a bug this comment marks. A parked row
        # carries no tick box -- that is what parked MEANS -- so when this test
        # ran after the state branches it was unreachable behind their
        # `continue`, and a row the PO had parked would have headed the queue.
        # The selftest caught it on the first run.
        cells = _cells(line)
        state = None
        for cell in cells[1:]:
            state = _cell_state(cell)
            if state is not None:
                break
        if state is not None:
            tbl[rid] = state
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
    # `r in states` is the BOARD test, and leaving it out was a real defect.
    #
    # `_row_order` walks every table row in the file, and a plan's drift
    # register, sealed-decision table and OPEN register all put a backticked id
    # in the first cell. Those rows carry no state marker, so `row_states` never
    # records them — and `states.get(r) != "x"` is True for a row it has never
    # heard of, so all of them entered the queue. Measured on the plan that was
    # generating its own goal: 1 real open row, 16 queued, with a drift-log
    # entry and a sealed decision presented to a long autonomous run as work.
    #
    # `stop_markers` had this right (`if row not in states: continue`) under a
    # comment stating the rule in as many words. **The discipline was known,
    # written down, and applied to one of the two functions that needed it** —
    # which is `NV-3` at the level of a rule rather than a check: correct in the
    # place someone was looking, default-uncovered in the place they were not.
    order = [
        r for r in _row_order(plan)
        if r in states and states[r] != "x" and r not in excluded
    ]

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

    # ─── `C1` (2026-08-22). Three MEASURED gaps in this reader, each an arm.
    #
    # 1. A BOLDED id. 30 of 51 boards in this repo write one, and every one of
    #    them parsed as an EMPTY board — including `2026-08-02-actor-substrate`,
    #    the sibling whose method a whole run copied, at 218 bolded pipe-rows.
    bold = (
        "| **1** | measure the thing | **DONE** | evidence |\n"
        "| **2** | build the thing | ⬜ OPEN | |\n"
    )
    got = row_states(bold)
    check("a BOLDED id is a row", set(got) == {"1", "2"}, str(got))

    # 2. The open-square marker. 27 open rows across three boards carried it as
    #    their ONLY mark and were invisible to this tool — including every row
    #    that two other board rows were written to close.
    check("an open-square marker reads as OPEN, not absent", got.get("2") == " ", str(got))

    # 3. A MENTION is not a MARKER, and this arm matters most: the old reader
    #    asked `"[x]" in line`, so a row DESCRIBING a half-proven thing was
    #    ticked and left its own queue. It happened twice in one day — the
    #    second time to the row describing this very defect.
    #
    # ⚠ The first version of this arm put the mention in cell 0 -- the ID cell,
    #   which the reader skips anyway -- so it passed for the wrong reason. The
    #   BITE caught it: reverting `startswith` to `in` left the suite green.
    #   The real defect had the mention in the DESCRIPTION cell, which IS
    #   scanned, so that is where it goes.
    q1 = "| `Q1` | its status cell ticks the MANUAL leg and quotes `[x] manual, [ ] automated` | `[ ]` | |\n"
    q2 = "| `Q2` | the vocabulary is `[x]`, ✅, ⬜ and PARKED | `[ ]` | |\n"
    got = row_states(q1 + q2)
    check("a row that MENTIONS a marker is still open", got == {"Q1": " ", "Q2": " "}, str(got))

    # The near-miss in the OTHER direction: a real status cell that carries prose
    # after its marker must still be read. A rule demanding a bare cell would
    # silently drop every board that explains itself — most of them.
    verbose = "| `R1` a thing | ✅ **DONE 2026-08-22 — see §3.4, 3 bites** | evidence |\n"
    got = row_states(verbose)
    check("a verbose status cell still reads as done", got == {"R1": "x"}, str(got))

    # `C1` of the world-in-a-running-reality board -- format C, the MARKER-FIRST
    # board. Cell 0 holds the tick box AND the id, so `ROW_TABLE` (which reads an
    # id from cell 0) and the status scan (which starts at cell 1) were BOTH
    # blind to it at once. 17 rows across two game-track boards, four of them
    # open -- including a PO checkpoint.
    mfirst = ("| `[x]` **S0** | this RUN-STATE | written |\n"
              "| `[~]` **S6** | red team | in flight |\n"
              "| `[ ]` **S9** | SESSION + COMMIT | |\n")
    got = row_states(mfirst)
    check("a MARKER-FIRST row is read, id and state both",
          got == {"S0": "x", "S6": "~", "S9": " "}, str(got))


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

    # ②b A REGISTER row is not a slice. Drift logs, sealed-decision tables and
    # OPEN registers all put a backticked id in the first cell and carry NO
    # state marker — and `states.get(r) != "x"` was True for every one of them,
    # so a plan with a filled-in drift log queued its own drift log. Measured
    # live: 1 open row, 16 queued.
    #
    # The board row here is LAST on purpose. With it first, a bug that queued
    # everything after it would still put `B1` at the head and the arm would
    # pass on the right answer for the wrong reason.
    registers = (
        "**RESUME: `B1` — the only real row.**\n"
        "## §3 BOARD\n"
        "| `B0` shipped | `[x]` | evidence |\n"
        "| `B1` open | `[ ]` | |\n"
        "## §4 OPEN\n"
        "| `EO-1` | a debt row with no tick box | its mechanism |\n"
        "## §5 DRIFT\n"
        "| `ED-D1` | a near-miss worth recording |\n"
        "| `ED-1` | a sealed decision |\n"
    )
    rq = build(registers, "p.md").split("QUEUE")[1].split("CYCLE")[0]
    check("a drift-register row is not queued", "ED-D1" not in rq, rq.strip())
    check("a sealed-decision row is not queued", "ED-1" not in rq, rq.strip())
    check("an OPEN-register row is not queued", "EO-1" not in rq, rq.strip())
    check("...and the real board row still is", "B1" in rq, rq.strip())

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
