#!/usr/bin/env python3
"""TOOL-V2 LOOP · one tool at a time, and a tool is a FEATURE, not a migration.

    python scripts/toolv2-loop.py --status          # coverage, from the SSOT
    python scripts/toolv2-loop.py --next            # the next tool, with WHY it is next
    python scripts/toolv2-loop.py --record NAME --state proven --note "..." [--evidence ...]

**THE LOOP, AS THE PO DEFINED IT (2026-08-10).** One iteration is a complete development cycle for
ONE tool:

    convert -> RUN IT AND PROVE IT -> if it fails, INVESTIGATE and fix the architecture or the
    backend, across services if that is where the defect is -> run again -> proven ends the
    iteration; still broken means the tool is SKIPPED WITH A REASON and the loop moves on.

🔴 **THE CORRECTION THAT PRODUCED THIS DESIGN, RECORDED BECAUSE IT WAS MINE.** I first scoped the
loop as *convert what already has evidence, and record the rest as having no subject* — 84 tools
verifiable, 235 not. That treats EVIDENCE AS SOMETHING ONLY HISTORY CAN PROVIDE. **The loop makes
evidence**: it runs the tool. So a tool with no recorded traffic is not out of scope, it merely has
no reproducer for free. What survives from that measurement is the ORDER, not the exclusion.

**Why one at a time.** A batch converts what is easy and hides what is hard behind an aggregate.
Attention is the scarce resource here, and every finding this checkpoint produced came from looking
at ONE population closely — never from a sweep.

**Every denominator comes from the SSOT** (`contracts/agent-runtime-baseline` + the local tools +
the live corpus), never from this file. The ledger records CONCLUSIONS; it never defines the set.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "services" / "chat-service"))

LEDGER = ROOT / "contracts" / "agent-runtime-toolv2-ledger.json"
BASELINE = ROOT / "contracts" / "agent-runtime-baseline" / "tools-list.snapshot.json"
MANIFEST = ROOT / "contracts" / "agent-runtime-manifest.json"
PG = os.environ.get("CP5_PG_CONTAINER", "infra-postgres-1")

#: A tool's terminal states. `proven` and `blocked` both END an iteration — the difference is
#: whether the tool works, not whether we tried.
STATES = ("pending", "converting", "proving", "proven", "blocked")
TERMINAL = ("proven", "blocked")


def psql(db: str, sql: str) -> str:
    p = subprocess.run(
        ["docker", "exec", PG, "psql", "-U", "loreweave", "-d", db, "-At", "-F", "\x1f", "-c", sql],
        capture_output=True, text=True, encoding="utf-8")
    if p.returncode != 0:
        raise SystemExit(f"psql {db}: {p.stderr.strip()}")
    return p.stdout


def catalogue() -> dict[str, dict]:
    """🔴 **THE UNION, AND IT RAISES RATHER THAN DEGRADING.** A partial catalogue produced four
    separate false findings in CP-5 — including a role that read as never used and a guard that
    accused the producer of hand-writing a row it had just derived."""
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    cat = {t["name"]: t for t in doc["tools"]}
    try:
        from app.services.local_tools import local_tool_defs
        for d in local_tool_defs():
            fn = d.get("function", d)
            cat[fn["name"]] = d
    except Exception as exc:  # noqa: BLE001
        raise SystemExit(f"cannot read chat-service's own tools ({exc}); the loop's denominator "
                         f"would silently exclude them")
    return cat


def admitted() -> set[str]:
    if not MANIFEST.exists():
        return set()
    return {r["id"] for r in json.loads(MANIFEST.read_text(encoding="utf-8"))["declarations"]
            if r.get("lifecycle") in ("admitted", "deprecated")}


def usage() -> dict[str, dict]:
    """Calls, successes and sessions per tool, from the live corpus."""
    sql = """
    SELECT tc->>'tool', count(*), count(*) FILTER (WHERE (tc->>'ok')='true'),
           count(DISTINCT m.session_id)
    FROM chat_messages m, LATERAL jsonb_array_elements(m.tool_calls) tc
    WHERE tc->>'tool' IS NOT NULL GROUP BY 1
    """
    out: dict[str, dict] = {}
    for line in psql("loreweave_chat", sql).splitlines():
        parts = line.split("\x1f")
        if len(parts) != 4:
            continue
        name, calls, ok, sessions = parts
        out[name] = {"calls": int(calls), "ok": int(ok), "sessions": int(sessions)}
    return out


def ledger() -> dict:
    if not LEDGER.exists():
        return {"ledger_version": 1, "tools": {}}
    return json.loads(LEDGER.read_text(encoding="utf-8"))


def save(doc: dict) -> None:
    LEDGER.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def queue(cat: dict, use: dict, done: dict) -> list[tuple[str, str, dict]]:
    """The next tools, in the order the MEASUREMENT justifies — with the reason attached.

    The order is not a preference. A tool that is CALLED and never succeeds arrives with a
    reproducer already in the corpus, so its iteration starts at *investigate* instead of at
    *construct a failing case*. A tool nobody has ever called has to have its first call built
    before anything can be proven, which is strictly more work for strictly less evidence.
    """
    rows = []
    for name in sorted(cat):
        if done.get(name, {}).get("state") in TERMINAL:
            continue
        u = use.get(name, {"calls": 0, "ok": 0, "sessions": 0})
        if u["calls"] and u["ok"] == 0:
            rows.append((name, "called and NEVER succeeded — a reproducer already exists", u))
        elif u["ok"]:
            rows.append((name, "has recorded successes — a shape can be verified from real results",
                         u))
        else:
            rows.append((name, "never called — its first invocation has to be constructed", u))
    rank = {"called and NEVER succeeded — a reproducer already exists": 0,
            "has recorded successes — a shape can be verified from real results": 1,
            "never called — its first invocation has to be constructed": 2}
    rows.sort(key=lambda r: (rank[r[1]], -r[2]["sessions"], -r[2]["calls"], r[0]))
    return rows


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--next", action="store_true")
    ap.add_argument("--top", type=int, default=8)
    ap.add_argument("--record", metavar="TOOL")
    ap.add_argument("--state", choices=STATES)
    ap.add_argument("--note")
    ap.add_argument("--evidence", action="append", default=[])
    args = ap.parse_args()

    cat, adm, use = catalogue(), admitted(), usage()
    doc = ledger()
    tools = doc.setdefault("tools", {})

    if args.record:
        if args.record not in cat:
            print(f"{args.record!r} is not in the catalogue — the ledger may not invent a tool")
            return 1
        if not args.state:
            print("--record needs --state")
            return 1
        row = tools.setdefault(args.record, {})
        row["state"] = args.state
        if args.note:
            row["note"] = args.note
        if args.evidence:
            row.setdefault("evidence", []).extend(args.evidence)
        row["admitted"] = args.record in adm
        save(doc)
        print(f"{args.record}: {args.state}")
        return 0

    total = len(cat)
    by_state = {s: 0 for s in STATES}
    for name in cat:
        by_state[tools.get(name, {}).get("state", "pending")] += 1
    concluded = by_state["proven"] + by_state["blocked"]

    print(f"catalogue (SSOT)          {total}")
    print(f"  admitted through rung 2 {len(adm & set(cat))}")
    for s in STATES:
        print(f"  {s:<22}  {by_state[s]}")
    print(f"\nLOOP PROGRESS  {concluded}/{total} tools have a CONCLUSION "
          f"({concluded / total * 100:.1f}%)")
    print("  the loop ends when every tool is `proven` or `blocked` — not when every tool is "
          "converted.\n  A blocked tool is a finished iteration with an honest outcome, and is "
          "never a silent skip.")

    if args.next or not args.status:
        q = queue(cat, use, tools)
        print(f"\nNEXT {min(args.top, len(q))} of {len(q)} remaining:")
        for name, why, u in q[:args.top]:
            print(f"  {name:<34} {u['sessions']:>4} sess {u['calls']:>5} calls "
                  f"{u['ok']:>5} ok   {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
