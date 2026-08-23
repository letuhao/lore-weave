#!/usr/bin/env python3
"""Emit the `/goal` condition for the blocked-tool loop.

    python scripts/toolloop/goal_prompt.py --check && python scripts/toolloop/goal_prompt.py

The DURABLE half — objective, unit, method, evidence, stop — is the constant below: one home,
edited once. The CHANGING half is the QUEUE, read at emit time from the same two contracts the
gate writes, so a tool that reaches `proven` leaves the queue by itself and no session is ever
pointed at finished work.

QUEUE is emitted LAST because it is the elastic section. `/goal` caps the condition at 4000
characters, and whatever sits at the bottom is what silently stops being true when a draft
overflows — losing open items is recoverable, losing STOP is not.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"
PROBLEMS = ROOT / "contracts" / "tool-resolution-problems.json"
BUDGET = 4000

DURABLE = """\
Clear every tool still reading `blocked` in contracts/tool-deep-dive-ledger.json.

OBJECTIVE. A tool is done when `python scripts/toolloop/gate.py conclude --tool X --state proven \
<batch>` passes all its bars and `gate.py audit` stays clean. Blocked -> proven only. Never \
weaken a bar, a scenario or an expectation to fit; if a bar is wrong, say so and leave it failing.

UNIT. ONE tool per cycle. Do not open the next until this one is proven, or re-blocked on a \
DIFFERENT named cause — which moves it to another problem and is recorded as such.

METHOD, every cycle, in order:
1 INVESTIGATE BEFORE THEORISING. Read what actually happened: `docker logs infra-chat-service-1`, \
the run's tool calls in loreweave_chat.chat_messages.tool_calls (args, ok, error, per \
session_id), the batch JSON under docs/eval/toolloop/2026-08-14/, and the store diffs it records. \
Absence of a log line is not absence of the event — prove the channel works first.
2 BRAINSTORM THE CAUSE. Use domain knowledge to say what really happened, list the candidates, \
and name the one the evidence supports. Write the theory down BEFORE touching code, and say what \
would refute it.
3 FIX the named cause.
4 PROVE IT WITH A REAL RUN. scripts/toolloop/fe_runner.py, K=5, live, through the provider layer \
against gemma-4-26b-a4b-qat. Reading the code and finding it correct is not proof.
5 IF IT DID NOT WORK, do not guess again — return to 1 with the new logs and metrics. Keep \
pursuing until the cause is NAMED, however many cycles that takes.

EVIDENCE. A real run proves a fix; code that looks right does not. Every failed attempt is \
RECORDED beside the original, never silently retried until it passes — re-running a stochastic \
near-miss until it goes green is gaming the gate, not evidence. A guard needs a falsifier proven \
RED on the original defect. Run the whole suite, not the subset you touched. Verify the deployed \
image contains your change before diagnosing anything from its behaviour.

STOP. Never write to the dogfood book: one throwaway fixture per scenario, provisioned and torn \
down. A read-only TOOL does not make a read-only TURN — the turn is bounded by the whole \
advertised surface plus every standing approval. Auth only via /v1/auth/login using git-ignored \
docs/dev/LOCAL_TEST_ENV.md; never scrape a token, never invent a credential. SELECT before any \
DML. Everything goes through the provider layer; there is no local model. DQs get a \
RECOMMENDATION from you and are DECIDED BY THE OWNER — never decide one yourself to unblock a \
tool. Report honestly: if a tool cannot move, say why and leave it blocked."""


def blocked_rows() -> list[tuple[str, str]]:
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    prob = json.loads(PROBLEMS.read_text(encoding="utf-8"))
    prob_of = {t: p["id"].split("-")[0] for p in prob["problems"] for t in p.get("tools", [])}
    rows = [
        (prob_of[t], t)
        for t, e in led["tools"].items()
        if isinstance(e, dict) and e.get("state") != "proven" and t in prob_of
    ]
    # Group by problem so a cycle can see siblings, then alphabetical within it.
    return sorted(rows, key=lambda r: (int(r[0][1:]), r[1]))


def build() -> tuple[str, list[tuple[str, str]]]:
    rows = blocked_rows()
    queue = "\n".join(f"  {p:4s} {t}" for p, t in rows)
    nxt = f"{rows[0][1]} ({rows[0][0]})" if rows else "NOTHING BLOCKED — verify with gate.py audit"
    body = (
        f"{DURABLE}\n\n"
        f"QUEUE, {len(rows)} blocked, read from the ledger at emit time:\n{queue}\n\n"
        f"NEXT: {nxt}. Re-derive this list every session; do not trust a copy."
    )
    return "/goal " + body, rows


def check(text: str, rows: list[tuple[str, str]]) -> int:
    warns, errs = [], []
    if not rows:
        warns.append("WARN: the queue is EMPTY — confirm with problem_remaining.py before pasting")
    if len(text) > BUDGET:
        errs.append(f"OVER BUDGET: {len(text)} > {BUDGET} — the QUEUE section is "
                    f"{len(rows)} rows; shorten DURABLE, never cut upward from the bottom")
    # 🔴 THIS CHECK MUST NOT READ WHAT THE QUEUE READ. The first version recomputed `missed`
    # from the same two contracts `blocked_rows()` uses, so it could never disagree with itself
    # — a control that agrees with its seed by construction is theatre. `problem_remaining.py`
    # derives `still_blocked` independently and is the runstate's own arithmetic, so a
    # disagreement means one of the two is wrong and the prompt must not be pasted either way.
    try:
        import subprocess
        out = subprocess.run([sys.executable, str(ROOT / "scripts" / "toolloop" /
                                                  "problem_remaining.py")],
                             capture_output=True, text=True, cwd=str(ROOT), timeout=120).stdout
        head = next((ln for ln in out.splitlines() if "still_blocked=" in ln), "")
        theirs = int(head.split("still_blocked=")[1].split()[0]) if head else None
        if theirs is None:
            errs.append("CHECK COULD NOT READ problem_remaining.py's headline")
        elif theirs != len(rows):
            errs.append(f"DISAGREEMENT: problem_remaining.py says still_blocked={theirs}, "
                        f"this QUEUE has {len(rows)} — one of them is wrong, do not paste")
    except Exception as e:  # noqa: BLE001 — a broken check must be loud, not silent
        errs.append(f"CHECK COULD NOT RUN: {e!r}")
    for w in warns:
        print(w)
    for e in errs:
        print(e)
    print(f"{len(text)} / {BUDGET} characters, {len(rows)} tool(s) in QUEUE")
    return 1 if errs else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    text, rows = build()
    if a.check:
        return check(text, rows)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
