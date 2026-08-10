#!/usr/bin/env python3
"""CP-5 exit · derive the ESSENTIAL TOOL SET from the journey the PO named.

    "essential tools is not only tool_list and tool_load, it should be considered as search tool
     and the important workflow is plan tools too, so we will ship that user can use to write book
     with co-writer agent"  — PO, 2026-08-10

So "essential" is defined by a **user journey**, not by a tool's novelty: the set a person needs to
write a book with the co-writer agent. That makes CP-5's exit reachable — these tools already exist
and are already federated; they have simply never been admitted **through** the contract.

🔴 **THE SET IS DERIVED, NOT TYPED**, the same rule as every other denominator on this board. The
ROLES come from the journey; the MEMBERS come from live session usage. The rule is stated so it can
be argued with:

    a tool is ESSENTIAL if it serves one of the journey's roles AND it is the highest-reach tool
    for that role in real sessions (`chat_messages.tool_calls`, denominator = sessions, never calls)

Session reach rather than call count, for the reason §1 gives: ranking by calls ranks a handful of
pathological loops — the top 3 sessions alone held 28.3% of every failed call.

    python scripts/cp5-essential-set.py [--top N] [--json OUT]

Read-only.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PG_CONTAINER = os.environ.get("CP5_PG_CONTAINER", "infra-postgres-1")

#: The journey, decomposed. Each role is a step a person actually takes to write a book with the
#: co-writer agent; the predicate says which catalogue tools can serve it. Roles are the judgement
#: call and are stated here in the open; MEMBERSHIP is then measured.
ROLES: tuple[tuple[str, str, object], ...] = (
    ("discover", "find out which tools exist at all",
     lambda n: n in ("tool_list", "tool_load")),
    ("search", "find a thing by text when you do not know its id",
     lambda n: n in ("book_search", "glossary_search")),
    ("read", "read what is already written",
     lambda n: n in ("book_list", "book_read")),
    ("write", "create and save chapter prose",
     lambda n: n in ("book_chapter_create", "book_chapter_save_draft")),
    ("plan", "turn a goal into an ordered, checkable spec",
     lambda n: n.startswith("plan_")),
    # 🔴 **`compose_prose`, NOT `composition_write_prose` — and getting this wrong produced a false
    # finding.** The first version named only `composition_*` tools and reported the compose role
    # as having NO qualifying tool, i.e. *"the step where the co-writer produces prose has never
    # been taken"*. It has: `compose_prose` runs it, at 100% success. It was invisible because it
    # is a chat-service-LOCAL tool and the frozen snapshot holds only the 315 FEDERATED ones —
    # so the derivation was reading a catalogue that excludes the 9 tools this service implements
    # itself, which §4's *"all 324"* explicitly includes.
    ("compose", "the co-writer actually producing prose",
     lambda n: n in ("compose_prose", "composition_write_prose", "composition_get_prose")),
    ("canon", "the glossary the co-writer must stay consistent with",
     lambda n: n.startswith("glossary_")),
)

USAGE_SQL = """
SELECT tc->>'tool',
       count(DISTINCT m.session_id),
       count(*),
       count(*) FILTER (WHERE (tc->>'ok') = 'true')
FROM chat_messages m, LATERAL jsonb_array_elements(m.tool_calls) tc
WHERE tc->>'tool' IS NOT NULL
GROUP BY 1
"""


def psql(db: str, sql: str) -> str:
    cmd = ["docker", "exec", PG_CONTAINER, "psql", "-U", "loreweave", "-d", db,
           "-At", "-F", "\x1f", "-c", sql]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise RuntimeError(f"psql {db}: {p.stderr.strip()}")
    return p.stdout


def usage() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for line in psql("loreweave_chat", USAGE_SQL).splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        name, sessions, calls, ok = parts
        out[name] = {"sessions": int(sessions), "calls": int(calls), "ok": int(ok)}
    return out


def catalogue() -> set[str]:
    """The FEDERATED snapshot **plus the tools chat-service implements itself.**

    §4 scopes rung 2 to *"all 324"* — 315 federated and 9 local — and the snapshot holds only the
    315. Deriving over the snapshot alone made `compose_prose` invisible and produced a false
    finding that the co-writer's prose step had never been taken.
    """
    doc = json.loads((ROOT / "contracts" / "agent-runtime-baseline"
                      / "tools-list.snapshot.json").read_text(encoding="utf-8"))
    federated = {(t.get("function", t)).get("name") for t in doc["tools"]}
    sys.path.insert(0, str(ROOT / "services" / "chat-service"))
    try:
        from app.services.composer import COMPOSE_PROSE_NAME
        from app.services.tool_discovery import (
            FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME,
        )
        local = {COMPOSE_PROSE_NAME, FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME}
    except Exception as exc:  # a partial catalogue is worse than a loud one
        raise SystemExit(f"cannot read chat-service's local tools ({exc}); the derived set would "
                         f"silently exclude them, which is how the compose role read as empty")
    return federated | local


def admitted() -> dict[str, str]:
    path = ROOT / "contracts" / "agent-runtime-manifest.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r["lifecycle"] for r in doc.get("declarations", [])}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=2,
                    help="members per role, by session reach (default 2)")
    ap.add_argument("--json", help="write the derived set here")
    args = ap.parse_args()

    cat, use, live = catalogue(), usage(), admitted()
    # 🔴 A FLOOR, DERIVED FROM THE DATA. Without one the rule admitted `plan_compile` on **1
    # session and 0% success** simply because it ranked second in its role — noise wearing the
    # shape of a member. The floor is 1% of the sessions that make tool calls at all, so it moves
    # with the corpus instead of being a number someone typed.
    total_sessions = int(psql("loreweave_chat",
                              "SELECT count(DISTINCT session_id) FROM chat_messages "
                              "WHERE tool_calls IS NOT NULL").strip() or 0)
    floor = max(2, total_sessions // 100)
    print(f"corpus: {total_sessions} sessions with tool calls · a member needs >= {floor}")
    chosen: dict[str, list[dict]] = {}
    gaps: list[str] = []
    for role, why, pred in ROLES:
        cands = [
            {"tool": n, "sessions": use.get(n, {}).get("sessions", 0),
             "calls": use.get(n, {}).get("calls", 0),
             "ok_pct": (round(100 * use[n]["ok"] / use[n]["calls"], 1)
                        if use.get(n, {}).get("calls") else None),
             "lifecycle": live.get(n, "not registered")}
            for n in sorted(cat) if pred(n)
        ]
        cands.sort(key=lambda c: (-c["sessions"], c["tool"]))
        chosen[role] = [c for c in cands[:args.top] if c["sessions"] >= floor]
        if not chosen[role]:
            # 🔴 A ROLE WITH NO QUALIFYING TOOL IS A FINDING, NOT AN EMPTY LIST. It says the
            # journey has a step no recorded session has ever taken — which is either the wrong
            # tools for the role, or a step of the product that is not live yet. Either way it is
            # reported rather than silently dropped.
            gaps.append(role)
        print(f"\n{role.upper():<10} — {why}")
        for c in cands[:args.top + 3]:
            mark = "*" if c in chosen[role] else " "
            print(f"  {mark} {c['tool']:<34} {c['sessions']:>4} sessions  "
                  f"{c['calls']:>5} calls  ok={c['ok_pct']}%  [{c['lifecycle']}]")

    members = sorted({c["tool"] for v in chosen.values() for c in v})
    served = [m for m in members if live.get(m) in ("admitted", "deprecated")]
    print(f"\nESSENTIAL SET ({len(members)} tools, * rows above):")
    print(f"  {members}")
    print(f"\nadmitted through the contract: {len(served)}/{len(members)} — {served}")
    print(f"REMAINING for CP-5's exit: {sorted(set(members) - set(served))}")
    if gaps:
        print(f"\n🔴 ROLES WITH NO QUALIFYING TOOL: {gaps} — the journey names a step that no "
              f"recorded session has taken. Either the role maps to the wrong tools, or that part "
              f"of the product is not live yet. It is NOT coverage.")
    if args.json:
        pathlib.Path(args.json).write_text(
            json.dumps({"roles": chosen, "members": members, "admitted": served},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nwritten: {args.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
