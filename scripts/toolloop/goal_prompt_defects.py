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
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
BUDGET = 4000
#: How many contract defects to NAME. The rest are counted and pointed at, never silently dropped.
NAMED = 6

DURABLE = """\
Close the platform's CONTRACT defects in contracts/tool-deep-dive-ledger.json — the ones a \
stronger model fails identically.

OBJECTIVE. A defect is done when its invariant is NAMED, enforced at ONE chokepoint, a falsifier \
is proven RED on an ORIGINAL instance, the owning suite is green, and the fix is demonstrated by \
a LIVE run through the real chat path. Then `state: fixed` with the evidence on the row. Never \
weaken a bar, a scenario or an expectation to fit; if a bar is wrong, say so and leave it failing.

UNIT. ONE defect per cycle. DO NOT BATCH ON A BROKEN PLATFORM — a batch measures the platform, \
not the fix, which is why GPT-4 mini failed architecture v1. Do not open the next until this one \
is fixed, or re-scoped on a DIFFERENT named cause, and recorded as such.

METHOD, every cycle, in order:
1 INVESTIGATE BEFORE THEORISING. `docker logs infra-<svc>-1`, the run's tool calls in \
loreweave_chat.chat_messages.tool_calls (args, ok, error, per session_id), the batch JSON under \
docs/eval/toolloop/, and the store diffs it records. Read what happened, then reason.
2 NAME THE INVARIANT, AND FIX THE CLASS. One cause filed under 15 names is still one cause. \
Prefer a registration-time lint that FAILS THE BUILD over a per-tool repair.
3 RUN THE CONTROL THAT COULD REFUTE YOU, BEFORE writing the fix. For any detector or guard, \
measure PRECISION and RECALL on the recorded corpus and record the candidates you rejected.
4 DEPLOY AND VERIFY BY CONTENT — sha256 read from INSIDE the container against the host source; \
restart ai-gateway if a tool description changed; refresh the catalogue cache.
5 PROVE IT LIVE. Real provider, K>=5, throwaway fixture. Surfaced/called/store-moved, not vibes.

EVIDENCE. A fix is proven by a RUN, never by the code looking right, and never by a helper test \
alone — assert the CALL SITE. A failed attempt is RECORDED, not silently retried until it passes. \
Every fix states what it does NOT cover. Run the WHOLE owning suite, not the file you touched.

STOP. Never write to the dogfood book: one throwaway fixture per scenario, provisioned and torn \
down. A read-only TOOL does not make a read-only TURN. Auth only via /v1/auth/login using \
git-ignored docs/dev/LOCAL_TEST_ENV.md; never scrape a token, never invent a credential. SELECT \
before any DML. Everything through the provider layer; there is no local model. DQs get a \
RECOMMENDATION from you and are DECIDED BY THE OWNER — never decide one to unblock a defect. \
Report honestly: if a defect cannot move, say why and leave it open."""


def rows() -> tuple[list[tuple[str, str]], dict]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
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
            contract.append((v.get("queue_group") or 4, bool(v.get("blocked_by_dq")),
                             not v.get("queue_anchor"), k,
                             " ".join(inv.split())[:86], v.get("blocked_by_dq")))
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
    named = "\n".join(
        f"  [g{g}] {k}{' — BLOCKED ' + dq if dq else ''}\n    {inv}"
        for g, _b, _a, k, inv, dq in contract[:NAMED])
    free = [r for r in contract if not r[1]]
    nxt = (f"NEXT. {free[0][3]}  (group {free[0][0]})" if free else
           "NEXT. Every open contract defect is BLOCKED ON A DQ — take the owner's decisions "
           "first; there is no unblocked contract work left.")
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
