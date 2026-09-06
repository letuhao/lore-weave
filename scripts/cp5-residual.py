#!/usr/bin/env python3
"""CP-5 exit · classify the WHOLE failure corpus, and name what is left.

`CP-5.md` §7: *"the residual (§1, 5.0%) is either classified or declared out of scope with a
reason."* §1 states it as **18 sessions / 30 calls**, unclassified.

🔴 **THIS DOES NOT TRY TO REPRODUCE THAT NUMBER, AND THAT IS THE POINT.** Every member measured
during this checkpoint came back a different size from §1 — the error contract had **no genuine
member at all** (41 of 41 were suspensions), completeness was **87 sessions** rather than invisible,
and the argument supplier's dominant case was a value the runtime OWES rather than one the model
forgot. A residual computed by subtracting §1's own figures would inherit every one of those
errors. So the corpus is classified from scratch, by the same predicates the rows were built
against, and the residual is whatever survives.

**Denominator from the data, never typed.** Every failed `tool_call` lands in exactly one class,
and the script asserts that before printing anything.

    python scripts/cp5-residual.py [--json OUT]

Read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict

PG = os.environ.get("CP5_PG_CONTAINER", "infra-postgres-1")

SQL = r"""
SELECT m.session_id::text, tc->>'tool', coalesce(tc->>'error',''),
       coalesce(tc->>'call_outcome',''), (tc ? 'task')::text,
       coalesce((tc->'result')::text,'')
FROM chat_messages m, LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE (tc->>'ok') = 'false'
"""

#: Ordered — the FIRST match wins, so the classes are mutually exclusive by construction and a
#: call cannot be counted twice. Order matters: a suspension carries no message, so it must be
#: tested before "no message at all" or it would land there.
CLASSES: tuple[tuple[str, str, object], ...] = (
    # 🔴 **FIRST, AND IT IS THE TYPED TRUTH RATHER THAN A REGEX OVER PROSE.** Once a row carries
    # `call_outcome`, whether it was a tool FAILING is a recorded fact, not something to infer from
    # its wording. This class exists because of what the first pass found: **CP-5.4's own refusal
    # message landed in the RESIDUAL** — the runtime's new prose entered the corpus and the
    # classifier did not know it, so our own improvement read as an unclassified failure. That is
    # the "52% of the corpus is our own breaker" problem one generation later, and a text-matching
    # classifier will keep re-acquiring it. Reading the field cannot drift.
    ("typed non-failure (5.5 / 5.7 / 5.8 / 5.10)",
     "the row says what it was: deferred, or refused by the runtime. The tool did not fail.",
     lambda tool, err, task, res, outcome="": outcome in ("deferred", "refused")),
    ("deferred / suspension (5.5)",
     "a call that stopped to ask a human — not a failure at all",
     lambda tool, err, task, res, outcome="": task == "true" or (
         not err.strip() and (tool.endswith("confirm_action") or "propose" in tool
                              or tool in ("propose_edit", "book_chapter_delete",
                                          "glossary_adopt_standards")))),
    ("our own breaker (5.7)",
     "the runtime refused to dispatch; the tool never ran",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"already called|already ran this turn|already FAILED|keeps being called|"
         r"has been called with no |STOP calling", err, re.I))),
    ("identifier resolution (5.3)",
     "a NAME sent where an opaque id is required",
     lambda tool, err, task, res, outcome="": bool(re.search(r"must be a (real )?UUID|hexadecimal UUID",
                                                 err, re.I))),
    ("argument supplier (5.4)",
     "a required argument absent — the runtime's to give, or the model's to write",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"missing required|required argument|is required|missing/blank required|"
         # The JSON-Schema wording, which the first pass missed entirely and which is how the
         # federated Go tools phrase it: `validating root: required: missing properties: [...]`.
         r"required: missing properties|pass project_id or book_id|"
         # CP-5.4's OWN refusal wording. The first pass put it in the residual: the runtime's new
         # prose entered the corpus and the classifier did not know it, so our own improvement
         # read as an unclassified failure.
         r"is NOT yours to invent|needs book_id", err, re.I))),
    ("precondition (5.8)",
     "the state the tool requires was not there",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"no project in scope|project not found|not found or not accessible|not open|"
         r"no active|permission|forbidden|not authoris|not authoriz|blocked:|"
         r"not accessible|no embedding model configured|call .+ first|"
         r"must be in scope|only the .+ owner|has no chapters yet", err, re.I))),
    ("unknown / phantom tool (5.10)",
     "a name that is not a tool",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"unknown tool|no such tool|is not a tool|tool not found|unknown subagent",
         err, re.I))),
    # §1's own CONDITIONAL members, which the first pass had no class for at all — so their
    # traffic landed in the residual and made it look four times larger than it is.
    ("concurrency (conditional)",
     "a versioned write lost a race — §1 sized this at ONE session",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"changed since you read it|409|version conflict|stale version", err, re.I))),
    ("empty change / uniqueness (conditional)",
     "a write that would change nothing, or would duplicate something that exists",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"no fields to update|nothing to update|no changes|already exists", err, re.I))),
    ("consent — the human said NO (conditional)",
     "not a failure: the gate worked and the answer was no",
     lambda tool, err, task, res, outcome="": bool(re.search(r"denied by user|user denied", err, re.I))),
    ("closed vocabulary / shape",
     "a value outside a declared enum, or a validation error on shape",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"validation error|invalid arguments|must be one of|not a valid|expected .* got|"
         # The Go JSON-Schema validator's own phrasing. `required: missing properties` is claimed
         # EARLIER by 5.4, so this catches only the genuine shape errors: a wrong type, or a
         # property the schema does not define.
         r"badly formed|unparseable|^validating |unexpected additional properties", err, re.I))),
    ("not found (subject)",
     "the thing named does not exist — an id that is well-formed but dead",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"not found|does not exist|no entity|entity not found|no live row", err, re.I))),
    ("upstream / transport",
     "the far side failed or was unreachable — not a contract member (C-7 retryable_transient)",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"timeout|timed out|connection|unavailable|502|503|504|internal error|"
         r"failed to connect|EOF|provider error", err, re.I))),
    ("planner / model refusal",
     "the runtime asked a model to produce something and it declined",
     lambda tool, err, task, res, outcome="": bool(re.search(
         r"could not produce|nothing to plan|try rephrasing|refused|compile blocked",
         err, re.I))),
)


def rows():
    cmd = ["docker", "exec", PG, "psql", "-U", "loreweave", "-d", "loreweave_chat",
           "-At", "-R", "\x1e", "-F", "\x1f", "-c", SQL]
    out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                         check=True).stdout
    for rec in out.split("\x1e"):
        parts = rec.strip("\n").split("\x1f")
        if len(parts) != 6:
            continue
        yield parts


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--show", type=int, default=12, help="residual examples to print")
    args = ap.parse_args()

    calls = Counter()
    sessions = defaultdict(set)
    residual: list[tuple[str, str]] = []
    total = 0
    all_sessions = set()

    for sid, tool, err, outcome, task, res in rows():
        total += 1
        all_sessions.add(sid)
        for name, _why, pred in CLASSES:
            if pred(tool, err, task, res, outcome):
                calls[name] += 1
                sessions[name].add(sid)
                break
        else:
            calls["RESIDUAL"] += 1
            sessions["RESIDUAL"].add(sid)
            residual.append((tool, err[:150]))

    assert sum(calls.values()) == total, (
        f"{sum(calls.values())} classified != {total} failures — a call reached no class and no "
        f"residual, so the coverage figure would describe a set the query did not return"
    )

    print(f"corpus: {total} failed calls across {len(all_sessions)} sessions "
          f"(denominator from the query, never typed)\n")
    print(f"{'class':<32} {'calls':>7} {'sessions':>9} {'% sessions':>11}")
    for name, why, _ in CLASSES:
        s = len(sessions[name])
        print(f"  {name:<30} {calls[name]:>7} {s:>9} {100*s/len(all_sessions):>10.1f}%")
    rs = len(sessions["RESIDUAL"])
    print(f"  {'RESIDUAL':<30} {calls['RESIDUAL']:>7} {rs:>9} {100*rs/len(all_sessions):>10.1f}%")

    print(f"\n🔴 RESIDUAL — {calls['RESIDUAL']} calls / {rs} sessions "
          f"({100*rs/len(all_sessions):.1f}% of sessions):")
    for tool, err in Counter(residual).most_common(args.show):
        print(f"   {tool[0]:<34} {tool[1]!r}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"total_calls": total, "total_sessions": len(all_sessions),
                       "by_class": {n: {"calls": calls[n], "sessions": len(sessions[n])}
                                    for n, _, _ in CLASSES},
                       "residual": {"calls": calls["RESIDUAL"], "sessions": rs,
                                    "examples": [list(t) for t in residual[:60]]}},
                      fh, ensure_ascii=False, indent=2)
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
