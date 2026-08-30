#!/usr/bin/env python3
"""Emit the `/goal` condition for the WHOLE-LEDGER defect loop (every class, not just contract).

    python scripts/toolloop/goal_prompt_all_defects.py --check && \
        python scripts/toolloop/goal_prompt_all_defects.py

Third sibling. `goal_prompt.py` drives the blocked-TOOL loop; `goal_prompt_defects.py` drives the
CONTRACT-only defect loop; this one drives every open defect regardless of class. One generator
per goal — they are not merged, because merging them would mean one QUEUE serving three different
finish lines and no session could tell which one it was running.

WHY THIS EXISTS, and it is the owner's decision of 2026-08-28: fourteen deferred questions were
answered in one sitting, and the work they release does NOT sit in one class. T33 is infra,
T54/T55/T59 are model, T57/T58 are platform, T50/T51/T52 are instrument, and only the rest are
contract. A contract-only goal would have left most of those decisions unbuilt while reporting
itself finished — the exact staleness the goal-prompt command exists to prevent.

CONTRACT STILL SORTS FIRST inside the queue, on the owner's original evidence: GPT-4 mini failed
architecture v1 too — model swapped, architecture held constant, still failed — so a `contract`
defect is one a STRONGER MODEL FAILS IDENTICALLY. That is an ordering, not a filter; nothing is
excluded any more.

QUEUE is emitted LAST because it is the elastic section and `/goal` caps the condition at 4000
characters. Losing open items to an overflow is recoverable; losing STOP is not.
"""
from __future__ import annotations

import argparse
import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
BUDGET = 4000
#: How many rows to NAME. The rest are counted and pointed at, never silently dropped.
#: 3 -> 2 on 2026-08-28: this goal's row KEYS are longer than the contract-only sibling's (they
#: carry a class tag) and the condition landed at 4162/4000. QUEUE is the elastic section exactly
#: so an overflow is paid for HERE and never by trimming a rule.
NAMED = 2
#: Characters of each named row's invariant to show. Enough to RECOGNISE the row, not to
#: understand it — a row needing more than this has narration where its invariant should be.
EXCERPT = 24
#: Class order inside the queue. Contract first (see the module docstring); the rest follow by how
#: directly they block a user-visible behaviour. A class missing here sorts last, never vanishes.
CLASS_ORDER = ("contract", "platform", "infra", "model", "instrument")

DURABLE = """\
Close EVERY open defect in contracts/tool-deep-dive-ledger.json — all classes, not just contract.

OBJECTIVE. A defect is DONE when its invariant is NAMED, enforced at ONE chokepoint, a falsifier \
is proven RED on an ORIGINAL instance, the WHOLE owning suite is green, and the fix is shown by a \
LIVE run through the real chat path. Then `state: fixed` with evidence on the row.

THE RUN ENDS ONLY WHEN `goal_prompt_all_defects.py --check` reports no open defect, or says every \
one left is DQ-blocked, AND `gate.py audit` is clean. NOTHING ELSE ENDS IT. One defect fixed is \
ONE CYCLE, never the run: the moment a row reaches `fixed`, open the next one IN THE SAME TURN.

THE OWNER'S DECISIONS ARE THE WORK. Each ruling sits under `answer_*` on its DQ row. READ IT \
BEFORE BUILDING and build it AS WORDED. If it cannot be built, the question goes BACK CORRECTED \
with the measurement showing why — never substitute a mechanism quietly.

NEVER STOP FOR — asking whether to go on; offering to hand back; "want me to…" then silence; a \
finished cycle; a green suite; a long report; a tidy stopping point. Any turn that has not moved \
a row to `fixed` MUST END IN A TOOL CALL. Reporting is not progress.

BLOCKED IS NOT STOPPED. A defect needing a decision gets its DQ recorded and you MOVE ON.

UNIT. ONE defect per cycle — a floor on rigour, not a cap on effort. DO NOT BATCH ON A BROKEN \
PLATFORM: a batch measures the platform, not the fix.

METHOD, in order. 1 INVESTIGATE BEFORE THEORISING: `docker logs infra-<svc>-1`, \
chat_messages tool_calls/advertised/withheld, batch JSON, store diffs. Read, then \
reason. 2 NAME THE INVARIANT AND FIX THE CLASS at ONE chokepoint — prefer the \
place that DESTROYS the information; check FIRST whether the mechanism exists and is merely \
EMPTY. 3 RUN THE CONTROL THAT COULD REFUTE YOU before writing the fix — measure cost and RECALL, \
record what you rejected. 4 DEPLOY AND VERIFY BY CONTENT: sha256 from INSIDE the container; \
restart ai-gateway on a description change. 5 PROVE IT LIVE: real provider, K>=5, throwaway \
fixture.

EVIDENCE. Proven by a RUN, never by the code looking right, never by a helper test alone — assert \
the CALL SITE. A CLEAN ARM PROVES NOTHING UNTIL YOU SHOW IT REACHED THE PATH: a scenario that \
auto-approves never suspends. VERIFY THE VARIED INPUT REACHED THE MODEL. Run the whole owning \
suite SERIALLY. A failed attempt is RECORDED, not quietly retried. Every fix states what it does \
NOT cover.

CHECK YOUR OWN INSTRUMENT BEFORE REPORTING ITS ANSWER. A census returning a shocking number is \
usually measuring itself — a key-name scan called 82 rows unproven where 7 was true.

ANTI-CHEAT. Never weaken a bar, a scenario or an expectation to fit; if a bar is wrong, leave it \
RED and say so. A baseline may only SHRINK. Never split a defect to inflate the count. Never \
write `fixed` when the live run exercised only part of the fix — say which part is unproven. A \
row that STOPPED REPRODUCING is not fixed: no fix, no credit. When your own control refutes your \
own row, WITHDRAW IT and record what misled you. Re-derive every number; a ledger claim is a \
lead, not a fact.

SAFETY. Never write to the dogfood book: one throwaway fixture per scenario, torn down. A \
read-only TOOL does not make a read-only TURN. Auth only via /v1/auth/login using git-ignored \
docs/dev/LOCAL_TEST_ENV.md; never scrape a token or invent a credential. SELECT before any DML. \
Every open DQ gets a RECOMMENDATION from you and is DECIDED BY THE OWNER — never decide or close \
one yourself to unblock a defect."""


#: A deferred question NAME, matched whole. `DQ-T4` and `DQ-T45` are different questions and one
#: is a prefix of the other, so a bare substring test conflates them — the inert-repair bug this
#: generator's sibling records at length.
_DQ_TOKEN = re.compile(r"DQ-T\d+")


def _open_dq_names(led: dict) -> set[str]:
    """The deferred questions STILL WAITING on the owner.

    `blocked_by_dq` records WHICH question a row waits on, never whether the answer arrived. A
    row is blocked only while its question is genuinely open, so answering one releases its rows
    with no second edit — and therefore no second place to forget.

    🔴 AND `state` IS NOT WHERE THE ANSWER ARRIVES. The owner writes a ruling into an `answer_*`
    field; flipping `state` is a separate bookkeeping act that nobody is obliged to perform, and
    on 2026-08-30 FOUR rulings — DQ-T44, T53, T58, T64 — had been sitting behind `state: open`
    with their answers written. This function called all four "waiting on the owner", every row
    they block read as DQ-blocked, and the generator printed "NEXT. No unblocked work. Every open
    row waits on a decision above" while seven rows had a ruling ready to build.

    A queue that reports no work while work exists is worse than a wrong queue: nobody looks
    again. So ANSWERED means answered — the presence of a ruling releases the rows, exactly as
    flipping `state` would, and the two no longer have to agree for the queue to be right.
    """
    dqs = led.get("deferred_questions") or {}
    return {name for name, q in dqs.items()
            if isinstance(q, dict) and q.get("state") == "open" and not _has_ruling(q)}


def _has_ruling(q: dict) -> bool:
    """Has the owner written a ruling on this question, whatever its `state` says?

    Keyed on the FIELD PREFIX the owner actually uses (`answer_2026_08_28`), because that is what
    the ledger contains — not on a status word this loop would then have to keep in sync.
    """
    return any(str(k).startswith("answer") for k in q)


def rows() -> tuple[list[tuple], collections.Counter]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    still_open = _open_dq_names(led)
    counts: collections.Counter = collections.Counter()
    out: list[tuple] = []
    for k, v in (led.get("defects") or {}).items():
        if not isinstance(v, dict) or v.get("state") != "open":
            continue
        cls = v.get("defect_class") or "unclassified"
        counts[cls] += 1
        # Several rows carry their substance under neither `invariant` nor `what`. Falling
        # through the whole row beats emitting a blank line into a 4000-char budget.
        inv = next((str(v[f]) for f in
                    ("invariant", "what", "measured", "status", "severity") if v.get(f)), "")
        # `blocked_by_dq` may name several in prose ("DQ-T56 (and DQ-T53 for the root cause)"),
        # so the names are TOKENISED and the row is blocked if ANY is still open — releasing a
        # row whose second question is unanswered sends the next session at work it cannot
        # finish.
        named = v.get("blocked_by_dq")
        mentioned = set(_DQ_TOKEN.findall(str(named or "")))
        blocked = bool(mentioned & still_open)
        rank = CLASS_ORDER.index(cls) if cls in CLASS_ORDER else len(CLASS_ORDER)
        out.append((blocked, rank, v.get("queue_group") or 4,
                    not v.get("queue_anchor"), k, cls,
                    " ".join(inv.split())[:EXCERPT], named if blocked else None))
    # DQ-blocked LAST and never NEXT: they cannot be closed without an owner decision, and a
    # resume pointer aimed at one sends the next session to wait rather than to work.
    out.sort()
    return out, counts


def build() -> tuple[str, list[tuple], collections.Counter]:
    all_rows, counts = rows()
    total = sum(counts.values())
    by_class = " · ".join(f"{counts[c]} {c}" for c in CLASS_ORDER if counts.get(c))
    extra = " · ".join(f"{n} {c}" for c, n in sorted(counts.items()) if c not in CLASS_ORDER)
    head = (f"QUEUE, derived. {total} open: {by_class}"
            + (f" · {extra}" if extra else "")
            + ". Contract sorts first; nothing is excluded.")
    free = [r for r in all_rows if not r[0]]
    if free:
        named = "\n".join(f"  [{cls}] {k}\n    {inv}"
                          for _b, _r, _g, _a, k, cls, inv, _dq in all_rows[:NAMED])
        nxt = f"NEXT. {free[0][4]}  ({free[0][5]})"
    else:
        # TERMINAL STATE — every row is blocked, so naming three of them with their invariants
        # spends the budget on work nobody can start. The OPEN ITEMS here are the DECISIONS:
        # one line each, every blocking question and how many rows wait on it.
        waiting: dict[str, int] = {}
        for _b, _r, _g, _a, _k, _cls, _inv, dq in all_rows:
            if dq:
                waiting[dq] = waiting.get(dq, 0) + 1
        named = "  " + " · ".join(f"{dq}({n})" for dq, n in
                                  sorted(waiting.items(), key=lambda x: (-x[1], x[0])))
        nxt = ("NEXT. No unblocked work. Every open row waits on a decision above; "
               "take those first.")
    return f"/goal {DURABLE}\n\n{head}\n{named}\n\n{nxt}\n", all_rows, counts


def check(text: str, all_rows: list, counts: collections.Counter) -> int:
    bad = []
    if len(text) > BUDGET:
        bad.append(f"OVER BUDGET: {len(text)} > {BUDGET} chars. Shorten the SOURCE, never cut "
                   f"upward from the bottom — STOP sits above QUEUE for that reason.")
    if counts.get("unclassified"):
        bad.append(f"{counts['unclassified']} open defect(s) have no `defect_class`. They are "
                   f"still QUEUED (this goal excludes nothing) but they sort last and their "
                   f"class should be set in the ledger, not here.")
    if not all_rows:
        bad.append("no defect is open at all — is that true, or did the state field drift?")
    if all_rows and all(r[0] for r in all_rows):
        bad.append("every open defect is DQ-blocked; NEXT would point at a decision, not work.")
    for w in bad:
        print(f"CHECK: {w}", file=sys.stderr)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text, all_rows, counts = build()
    if a.check:
        return check(text, all_rows, counts)
    print(text, end="")
    print(f"\n[{len(text)} / {BUDGET} chars]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
