"""What a tool's calls actually RETURNED, across every call the platform has recorded.

DQ-T74, answered by the owner 2026-08-31: "STATE IT, DO NOT DEMOTE. A tool's verdict must say
what its calls actually returned -- 'proven (reachable; 0 of N calls returned ok)' -- so the
silent half is audible without re-opening part of the catalogue by side effect."

    THE INVARIANT THIS SERVES: `proven` means REACHABLE, not FUNCTIONAL, and a verdict that does
    not say which one it means is read as the stronger of the two.

THE DEFECT IT MAKES AUDIBLE. The LIVE bar is `called >= 1` with zero errored RUNS -- and a run
errors when the HARNESS fails, not when the tool returns an error. So a tool the model reaches
for and that refuses every single time passes it. Measured over the whole chat store: fourteen
`proven` tools had never once returned ok and never even reached a confirm card.

THE THREE OUTCOMES, and the middle one is why a naive count overstates by 6x:

    done       ok:true                      the tool ran and answered
    deferred   pending present              a Tier-A write held at a confirm card. THE GATE
                                            COUNTS THIS AS SUCCESS -- "the tool ran and its gate
                                            held" -- so it must NOT be counted as a failure. The
                                            first pass at this measurement tested only "never
                                            returned ok" and reported 68 tools; 57 of them were
                                            writes legitimately stopping at a card.
    failed     ok:false and not pending     an outright error

DERIVED, NEVER TYPED. `python scripts/toolloop/call_outcome.py` rewrites the contract from the
store. Nothing here decides anything: it reports what the calls returned, and the owner's ruling
was explicitly that the STATE does not change.
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "contracts" / "tool-call-outcomes.json"
LEDGER = ROOT / "contracts" / "tool-deep-dive-ledger.json"

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

#: Below this many recorded calls a zero-success record says more about the sample than the tool,
#: so the annotation reports the count without the "never" language.
MIN_CALLS_TO_SPEAK = 5

_SQL = """
SELECT c->>'tool' AS tool,
       count(*) FILTER (WHERE c->>'ok' = 'true')                        AS done,
       count(*) FILTER (WHERE c ? 'pending')                            AS deferred,
       count(*) FILTER (WHERE c->>'ok' = 'false' AND NOT (c ? 'pending')) AS failed
FROM chat_messages m, jsonb_array_elements(m.tool_calls) c
WHERE m.tool_calls IS NOT NULL AND c->>'tool' IS NOT NULL
GROUP BY 1
"""


def _psql(sql: str) -> str:
    from provision import CONTAINER, PG_USER  # noqa: PLC0415 — one home for the container name

    r = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", PG_USER, "-d", "loreweave_chat",
         "-q", "-At", "-F", "\t"],
        input=sql, capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=300,
    )
    if r.returncode != 0:
        raise SystemExit(f"psql failed: {r.stderr[:400]}")
    return r.stdout


def derive() -> dict:
    out: dict[str, dict] = {}
    for line in _psql(_SQL).splitlines():
        parts = line.split("\t")
        if len(parts) != 4 or not parts[0]:
            continue
        tool, done, deferred, failed = parts[0], int(parts[1]), int(parts[2]), int(parts[3])
        out[tool] = {"done": done, "deferred": deferred, "failed": failed,
                     "calls": done + deferred + failed}
    return dict(sorted(out.items()))


def load() -> dict:
    if not CONTRACT.exists():
        return {}
    try:
        return json.loads(CONTRACT.read_text(encoding="utf-8")).get("tools", {})
    except (OSError, ValueError):
        return {}


def outcome_for(tool: str) -> dict | None:
    """The recorded outcome counts for one tool, or None if it has never been called."""
    return load().get(tool)


def annotate(tool: str) -> str:
    """The parenthetical the owner's ruling requires, or "" when there is nothing to say.

    Deliberately says NOTHING for a tool that succeeds. The ruling is about making a silent
    failure audible, not about decorating every verdict -- an annotation on all 204 rows would be
    noise, and noise is how the last annotation nobody read got there.
    """
    o = outcome_for(tool)
    if not o or not o["calls"]:
        return ""
    if o["done"]:
        return ""
    if o["deferred"]:
        # A held card IS the tool working, by the gate's own rule. Say so rather than staying
        # silent, because "0 returned ok" on its own reads as a failure and this is not one.
        return (f" (reachable; 0 of {o['calls']} calls returned ok, "
                f"{o['deferred']} held at a confirm card)")
    if o["calls"] < MIN_CALLS_TO_SPEAK:
        return f" (reachable; 0 of {o['calls']} calls returned ok)"
    return (f" (reachable; 0 of {o['calls']} calls returned ok, and none reached a confirm "
            "card — this verdict means REACHABLE, not working)")


def _never_ok(tools: dict, ledger: dict) -> list[tuple[str, dict]]:
    """`proven` tools with zero successes and zero cards -- the row's own population."""
    proven = {k for k, v in (ledger.get("tools") or {}).items() if v.get("state") == "proven"}
    return sorted(
        ((t, o) for t, o in tools.items()
         if t in proven and o["done"] == 0 and o["deferred"] == 0 and o["calls"] >= 1),
        key=lambda kv: -kv[1]["calls"])


def stamp(ledger: dict, tools: dict) -> list[str]:
    """Write the annotated `verdict` onto every tool row that has a state. Returns the names
    whose verdict changed.

    THE RULING IS ABOUT THE ROWS THAT ALREADY EXIST. Annotating only future conclusions would
    leave every one of the tools the defect was found on saying exactly what it said before, and
    those are the rows a reader is being misled by today.

    STATE IS NEVER TOUCHED -- that is the other half of "STATE IT, DO NOT DEMOTE".
    """
    changed = []
    for name, row in (ledger.get("tools") or {}).items():
        state = row.get("state")
        if not state:
            continue
        want = state + annotate(name)
        if row.get("verdict") != want:
            row["verdict"] = want
            changed.append(name)
    return changed


def main() -> int:
    tools = derive()
    CONTRACT.write_text(
        json.dumps({"_derived_by": "scripts/toolloop/call_outcome.py",
                    "_what": "per-tool call outcomes from chat_messages.tool_calls; "
                             "done=ok:true, deferred=held at a confirm card, failed=ok:false",
                    "tools": tools}, indent=1, ensure_ascii=False) + "\n",
        encoding="utf-8")
    ledger = json.loads(LEDGER.read_text(encoding="utf-8"))
    # Write the contract BEFORE stamping, so `annotate` reads today's numbers rather than the
    # previous run's. A stamp built from a stale contract is the failure this whole row is about,
    # wearing different clothes.
    changed = stamp(ledger, tools)
    if changed:
        LEDGER.write_text(json.dumps(ledger, indent=1, ensure_ascii=False) + chr(10),
                          encoding="utf-8")
    print(f"verdict stamped on {len(changed)} tool row(s)")
    never = _never_ok(tools, ledger)
    print(f"{len(tools)} tools have recorded calls -> {CONTRACT}")
    print(f"\n`proven` tools with ZERO ok and ZERO cards: {len(never)}")
    for t, o in never:
        print(f"    {o['failed']:5} failed   {t}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
