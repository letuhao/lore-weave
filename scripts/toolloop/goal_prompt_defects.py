#!/usr/bin/env python3
"""Emit the `/goal` condition for the PLATFORM DEFECT loop.

    python scripts/toolloop/goal_prompt_defects.py --check && python scripts/toolloop/goal_prompt_defects.py

Sibling of goal_prompt.py, which drives the blocked-TOOL loop. One generator per goal.

The DURABLE half is the constant below. The CHANGING half is the QUEUE, read at emit time from
`defect_class` and `state` on the ledger's own defect rows, so a defect that reaches `fixed`
leaves the queue by itself.

WHY THE ORDER IS CONTRACT FIRST, and it is the owner's evidence not mine: GPT-4 mini failed on
architecture v1 as well. Model swapped, architecture held constant, still failed — which isolates
the architecture as the cause. Classified 2026-08-25: 41 contract / 19 instrument / 11 model /
7 infra. A `contract` defect is one a STRONGER MODEL FAILS IDENTICALLY.

QUEUE is emitted LAST because it is the elastic section and `/goal` caps the condition at 4000
characters. Losing open items to an overflow is recoverable; losing STOP is not.
"""
from __future__ import annotations

import argparse
import collections
import re
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
BUDGET = 4000
#: How many contract defects to NAME. The rest are counted and pointed at, never silently dropped.
#: Lowered 6 -> 3 when the ANTI-CHEAT and RUN-ENDS sections were added: QUEUE is the elastic
#: section precisely so the durable half never gets cut to fit, and the full list is one query
#: away (`defect_class == contract`). Losing a name here is recoverable; losing a rule is not.
NAMED = 3
#: Characters of each named defect's invariant to show. Enough to RECOGNISE the row, not to
#: understand it — a row that needs more than this has narration where its invariant should be.
#: Lowered 64 -> 48 on 2026-08-25 when three defects closed and the rows that surfaced behind them
#: carry LONGER NAMES, pushing the emitted condition to 4032/4000. QUEUE is the elastic section
#: exactly so a budget overflow is paid for here and never by trimming a rule.
EXCERPT = 48

DURABLE = """\
Close the platform's CONTRACT defects in contracts/tool-deep-dive-ledger.json — the ones a \
stronger model fails identically.

OBJECTIVE. A defect is DONE when its invariant is NAMED, enforced at ONE chokepoint, a falsifier \
is proven RED on an ORIGINAL instance, the WHOLE owning suite is green, and the fix is shown by a \
LIVE run through the real chat path. Then `state: fixed` with the evidence on the row.

THE RUN ENDS ONLY WHEN `python scripts/toolloop/goal_prompt_defects.py --check` reports no open \
contract defect, or says every one left is DQ-blocked. NOTHING ELSE ENDS IT. One defect fixed is \
ONE CYCLE, never the run: the moment a row reaches `fixed`, open the next one IN THE SAME TURN.

NEVER STOP FOR — asking whether to go on; offering to redirect or hand back; "want me to…", \
"unless you…", or "next I'll…" followed by silence; a finished cycle; a green suite; \
a long report; a tidy stopping point. Any turn that has not moved a row to `fixed` \
MUST END IN A TOOL CALL, not in prose. Reporting is not progress. The DERIVED count is.

BLOCKED IS NOT STOPPED. A defect needing an owner decision gets its DQ recorded on the row and \
you MOVE TO THE NEXT ONE. Stop only when --check itself says everything left is blocked, then \
paste its output.

UNIT. ONE defect per cycle — a floor on rigour, not a cap on effort. DO NOT BATCH ON A BROKEN \
PLATFORM: a batch measures the platform, not the fix, which is why GPT-4 mini failed v1.

METHOD, in order. 1 INVESTIGATE BEFORE THEORISING: `docker logs infra-<svc>-1`, tool calls in \
loreweave_chat.chat_messages.tool_calls, the batch JSON under \
docs/eval/toolloop/, the store diffs. Read what happened, then reason. 2 NAME THE INVARIANT AND \
FIX THE CLASS: one cause under 15 names is one cause; prefer a registration-time gate that FAILS \
THE BUILD; check FIRST whether the mechanism EXISTS and is merely EMPTY. 3 RUN THE \
CONTROL THAT COULD REFUTE YOU, before writing the fix — measure PRECISION and RECALL, and record \
what you rejected. 4 DEPLOY AND VERIFY BY CONTENT: sha256 from INSIDE the container vs the host; \
restart ai-gateway on a description change. 5 PROVE IT LIVE: real provider, K>=5, throwaway \
fixture.

EVIDENCE. Proven by a RUN, never by the code looking right, never by a helper test alone — assert \
the CALL SITE. Run the whole owning suite SERIALLY. A failed attempt is RECORDED, not quietly \
retried. Every fix states what it does NOT cover.

ANTI-CHEAT. Never weaken a bar, a scenario or an expectation to fit; if a bar is wrong, say so and \
leave it RED. A baseline may only SHRINK — never re-freeze one larger to go green. Never split a \
defect to inflate the count, and never re-scope to something trivial: a re-scope must name a \
DIFFERENT cause. Never write `fixed` when the live run exercised only part of the fix — say which \
part is unproven. Re-derive every number you rely on; a ledger claim is a lead, not a fact.

SAFETY. Never write to the dogfood book: one throwaway fixture per scenario, torn down. A \
read-only TOOL does not make a read-only TURN. Auth only via /v1/auth/login using git-ignored \
docs/dev/LOCAL_TEST_ENV.md; never scrape a token, never invent a credential. SELECT before any \
DML. Everything through the provider layer; there is no local model. DQs get a RECOMMENDATION \
from you and are DECIDED BY THE OWNER — never decide one yourself to unblock a defect."""


#: A deferred question NAME, matched whole. `DQ-T4` and `DQ-T45` are different
#: questions and one is a prefix of the other, so a bare substring test conflates them.
_DQ_TOKEN = re.compile(r"DQ-T\d+")


def _open_dq_names(led: dict) -> set[str]:
    """The deferred questions that are STILL WAITING on the owner.

    🔴 **`blocked_by_dq` BEING PRESENT WAS TREATED AS THE ROW BEING BLOCKED, AND THAT IS WRONG
    THE MOMENT A DQ IS ANSWERED.** The field records WHICH question a row waits on; it does not
    record whether the answer has arrived. Nothing ever cleared it, so an answered decision left
    its rows sorted to the bottom, excluded from NEXT, and counted as decision-blocked forever —
    and the terminating check reported *"every open contract defect is DQ-blocked"* while real,
    unblocked work sat in the queue.

    Measured the day this was found: DQ-T45, DQ-T56 and DQ-T60 had been answered and DQ-T61
    withdrawn, and every row pointing at them still read as blocked.

    This is the staleness the goal-prompt command exists to prevent, one level up: *an item that
    gets finished leaves the queue by itself*. A row is blocked only while its question is
    genuinely open, so answering one releases its rows with no second edit — and therefore no
    second place to forget.
    """
    dqs = led.get("deferred_questions") or {}
    return {name for name, q in dqs.items()
            if isinstance(q, dict) and q.get("state") == "open"}


def rows() -> tuple[list[tuple[str, str]], dict]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    still_open = _open_dq_names(led)
    counts: collections.Counter = collections.Counter()
    contract: list[tuple[str, str]] = []
    for k, v in (led.get("defects") or {}).items():
        if not isinstance(v, dict) or v.get("state") != "open":
            continue
        cls = v.get("defect_class") or "unclassified"
        counts[cls] += 1
        if cls == "contract":
            # Several rows carry their substance under neither `invariant` nor `what`. Falling
            # through the whole row beats emitting a blank line into a 4000-char budget.
            inv = next((str(v[f]) for f in
                        ("invariant", "what", "measured", "status", "severity") if v.get(f)), "")
            # A row waits on its DQ only while that DQ is still open. `blocked_by_dq` may name
            # several in prose ("DQ-T56 (and DQ-T53 for the root cause)"), so the names are
            # TOKENISED and the row is blocked if ANY of them is still open — releasing a row
            # whose second question is unanswered would send the next session at work it cannot
            # finish.
            #
            # 🔴 TOKENISED, NOT `in`. My first version asked `any(dq in str(named) ...)` and it
            # was silently inert: `DQ-T4` is an OPEN question and a SUBSTRING of DQ-T40, T41,
            # T43, T44, T45, T46, T47, T48 and T49 — so every row waiting on a DQ-T4x read as
            # blocked no matter what its own question's state was, and the repair would have
            # changed nothing while looking correct. Same for DQ-T5 against T50-T59 and DQ-T6
            # against T60. Found by asking which open DQ each row actually matched.
            named = v.get("blocked_by_dq")
            mentioned = set(_DQ_TOKEN.findall(str(named or "")))
            blocked = bool(mentioned & still_open)
            contract.append((v.get("queue_group") or 4, blocked,
                             not v.get("queue_anchor"), k,
                             " ".join(inv.split())[:EXCERPT],
                             named if blocked else None))
    # DQ-blocked LAST and never NEXT: they cannot be closed without an owner decision, and a
    # resume pointer aimed at one sends the next session to wait rather than to work. Within a
    # group the ANCHOR sorts first — otherwise the next session starts on whichever row happens
    # to sort alphabetically, which is not a priority.
    contract.sort(key=lambda r: (r[1], r[0], r[2], r[3]))
    return contract, counts


def build() -> tuple[str, list[tuple[str, str]], dict]:
    contract, counts = rows()
    head = (f"QUEUE, derived. open: {counts['contract']} contract · {counts['instrument']} "
            f"instrument · {counts['model']} model · {counts['infra']} infra"
            + (f" · {counts['unclassified']} UNCLASSIFIED (classify before queueing)"
               if counts.get("unclassified") else "")
            + ". Contract first; the full list is `defect_class == contract` in the ledger.")
    free = [r for r in contract if not r[1]]
    if free:
        named = "\n".join(
            f"  [g{g}] {k}{' — BLOCKED ' + dq if dq else ''}\n    {inv}"
            for g, _b, _a, k, inv, dq in contract[:NAMED])
        nxt = f"NEXT. {free[0][3]}  (group {free[0][0]})"
    else:
        # TERMINAL STATE — every contract row is blocked, so naming three of them with their
        # invariants spends the budget on work nobody can start. Overflowed at 4025/4000 chars
        # the first time this state was reached, and the skill's own warning is that the
        # natural repair (cutting upward from the bottom) silently drops open items.
        #
        # The OPEN ITEMS here are the DECISIONS. List them instead: one line each, every
        # blocking question and how many rows wait on it — which is both shorter and the only
        # thing a resuming session can act on.
        waiting: dict[str, int] = {}
        for _g, _b, _a, _k, _inv, dq in contract:
            if dq:
                waiting[dq] = waiting.get(dq, 0) + 1
        named = "  " + " · ".join(
            f"{dq}({n})" for dq, n in sorted(waiting.items(), key=lambda x: (-x[1], x[0])))
        nxt = ("NEXT. No unblocked contract work. Every open contract row waits on a decision "
               "above; take those first.")
    return f"/goal {DURABLE}\n\n{head}\n{named}\n\n{nxt}\n", contract, counts


def check(text: str, contract: list, counts: dict) -> int:
    bad = []
    if len(text) > BUDGET:
        bad.append(f"OVER BUDGET: {len(text)} > {BUDGET} chars. Shorten the SOURCE, never cut "
                   f"upward from the bottom — STOP sits above QUEUE for that reason.")
    if counts.get("unclassified"):
        bad.append(f"{counts['unclassified']} open defect(s) have no `defect_class` and cannot "
                   f"be queued. Classify them in the ledger, not here.")
    if not contract:
        bad.append("no contract defect is open — is that true, or did the class field drift?")
    if contract and all(r[1] for r in contract):
        bad.append("every open contract defect is DQ-blocked; NEXT would point at a decision, "
                   "not at work.")
    for w in bad:
        print(f"CHECK: {w}", file=sys.stderr)
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text, contract, counts = build()
    if a.check:
        return check(text, contract, counts)
    print(text, end="")
    print(f"\n[{len(text)} / {BUDGET} chars]", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
