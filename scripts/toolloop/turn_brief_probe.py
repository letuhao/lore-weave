#!/usr/bin/env python
"""Did the turn brief reach the author? Read from the store, not from the runner's summary.

DQ-T71, owner 2026-08-31. The brief is a server-composed account of what a turn's calls actually
did, appended to the message the author reads. This asks the only question that matters after a
live run: on turns that HELD a call which did not happen, does the persisted assistant message
say so?

    THE INVARIANT, restated as a contingency table. Every row with a non-`done` call must carry
    the brief; no row without one may carry it.

🔴 IT READS THE PERSISTED CONTENT, which is the half a runner summary cannot see. The brief is
appended to `full_content` before `_persist_terminal_assistant`, so the store is where the claim
is falsifiable; a batch file records what the harness observed, and the two disagreeing would
itself be a finding.

🔴 AND IT SKIPS `finish_reason='streaming'`, WHICH IT LEARNED THE EXPENSIVE WAY. Run against a
batch still in flight it reported one violation — a turn holding a failed call whose content was
EMPTY — and the row was a mid-turn CHECKPOINT that `_persist_terminal_assistant` upserts by
msg_id at every tool boundary. The brief is appended at the FINISH, so a checkpoint legitimately
has none, and re-probing that same session after the batch ended showed the brief present. A
probe that reads a row the turn has not finished writing measures the clock, and this one would
have reported a defect in the fix it exists to verify.

Usage:  python scripts/toolloop/turn_brief_probe.py --since 30m
        python scripts/toolloop/turn_brief_probe.py --sessions <id> <id> ...
"""
from __future__ import annotations

import argparse
import json
import subprocess

#: The server's own sentences. Kept as literals rather than imported so this probe cannot pass by
#: reading the same constant the code under test writes with - it must match the SHIPPED text.
REFUSAL_HALF = "in this turn did not run:"
SUCCESS_HALF = "Already completed in this turn:"

#: The call outcomes the brief is required to speak about. `deferred` is the pending card and is
#: deliberately excluded: asking the user is a success state, and the suspend line covers it.
NOT_DONE = ("failed", "refused")

SQL = """
SELECT jsonb_build_object(
  'session_id', m.session_id::text,
  'created_at', m.created_at::text,
  'outcomes', (SELECT jsonb_agg(e->>'call_outcome') FROM jsonb_array_elements(m.tool_calls) e),
  'tools', (SELECT jsonb_agg(e->>'tool') FROM jsonb_array_elements(m.tool_calls) e),
  'has_refusal_half', position({refusal} in coalesce(m.content,'')) > 0,
  'has_success_half', position({success} in coalesce(m.content,'')) > 0,
  'tail', right(coalesce(m.content,''), 320)
)
FROM chat_messages m
WHERE m.role='assistant' AND jsonb_typeof(m.tool_calls)='array'
  AND jsonb_array_length(m.tool_calls) > 0
  AND m.finish_reason <> 'streaming'
  AND {where}
ORDER BY m.created_at;
"""


def _rows(where: str) -> list[dict]:
    sql = SQL.format(where=where,
                     refusal=f"'{REFUSAL_HALF}'", success=f"'{SUCCESS_HALF}'")
    p = subprocess.run(["docker", "exec", "-i", "infra-postgres-1", "psql", "-U", "loreweave",
                        "-d", "loreweave_chat", "-tAf", "-"],
                       input=sql, capture_output=True, text=True)
    if p.returncode != 0:
        raise SystemExit(p.stderr.strip()[:400])
    return [json.loads(line) for line in p.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="30m", help="a postgres interval, e.g. 30m / 2h")
    ap.add_argument("--sessions", nargs="*", default=None)
    ap.add_argument("--show", type=int, default=3, help="how many tails to print")
    a = ap.parse_args()

    if a.sessions:
        ids = ",".join(f"'{s}'" for s in a.sessions)
        where = f"m.session_id::text IN ({ids})"
        scope = f"{len(a.sessions)} named sessions"
    else:
        where = f"m.created_at > now() - interval '{a.since}'"
        scope = f"the last {a.since}"

    rows = _rows(where)
    tbl = {(True, True): [], (True, False): [], (False, True): [], (False, False): []}
    for r in rows:
        held = any(o in NOT_DONE for o in (r.get("outcomes") or []) if o)
        tbl[(held, bool(r["has_refusal_half"]))].append(r)

    print(f"assistant turns with tool calls in {scope}: {len(rows)}\n")
    print(f"{'':28s} {'brief PRESENT':>14s} {'brief ABSENT':>14s}")
    print(f"{'held a failed/refused call':28s} {len(tbl[(True, True)]):14d} "
          f"{len(tbl[(True, False)]):14d}   <- must be 0")
    print(f"{'every call done/deferred':28s} {len(tbl[(False, True)]):14d} "
          f"{len(tbl[(False, False)]):14d}")
    print(f"{'':28s} {'':>14s}   ^- must be 0")

    carded = [r for r in rows if r["has_success_half"]]
    print(f"\ncarded turns naming what already landed: {len(carded)}")

    for label, key in (("VIOLATION - held a refusal, said nothing", (True, False)),
                       ("VIOLATION - no refusal, yet briefed", (False, True)),
                       ("the brief, as the author reads it", (True, True))):
        for r in tbl[key][:a.show]:
            print(f"\n  {label}\n    session {r['session_id']}  outcomes={r['outcomes']}")
            print(f"    ...{r['tail'][-240:]!r}")

    bad = len(tbl[(True, False)]) + len(tbl[(False, True)])
    if not rows:
        print("\nNO TURNS IN SCOPE - this proves nothing. Run a batch first.")
        return 2
    if not tbl[(True, True)]:
        print("\nNO TURN IN SCOPE HELD A FAILED CALL - the invariant was never exercised, so a "
              "clean table here is vacuous. Run a scenario whose tool actually refuses.")
        return 2
    print(f"\n{'VIOLATIONS: ' + str(bad) if bad else 'CLEAN'}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
