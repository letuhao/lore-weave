#!/usr/bin/env python
"""The account's standing tool approvals — controlled for the duration of a batch, then restored.

🔴 WHY A BATCH THAT IGNORES THIS MEASURES THE WRONG USER. The harness account carries 23 standing
`allow` rows, most stamped 2026-07-11, left behind by months of manual testing. Their effect is
total and silent: a Tier-A tool on that list NEVER raises an approval card and executes
immediately. Measured 2026-08-14 in batch 1 — "Please write a chapter" had
`book_chapter_save_draft` overwrite the existing chapter's prose on 3 of 3 runs with
`approvals: []` and no card, because of a decision made five weeks earlier for a different turn.

That is the same mechanism that overwrote a real chapter of the dogfood book on 2026-07-11 and
that auto-executed the outline write on 2026-08-13. So it is not noise to be cleaned up: it is one
of the two user states the loop has to be able to run in, and the harness has to CHOOSE which,
rather than inheriting whichever rows happen to be lying around.

    none      — clear every standing decision. A new user. The Tier-A gate is observable, and a
                write that lands without a card is unambiguously a gate defect.
    standing  — leave the account exactly as it is. The veteran user, and the state in which both
                real incidents happened.
    as-is     — do nothing and say so.

🔴 SNAPSHOT AND RESTORE, NEVER JUST DELETE. Since Track C a row can be a standing DENY, so a
teardown that deletes what it finds can quietly erase a user's "Never allow" — a harness revoking
a real safety decision. Every row is read first and put back verbatim, including its `decision`.

Scoped to the WHOLE BATCH rather than to a scenario: approvals are per-user and scenarios run
concurrently, so a per-scenario change would leak across the ones running beside it.
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.eval.tool_liveness import config as _tle_config  # noqa: E402
from scripts.eval.tool_liveness import oracle  # noqa: E402

DB = "loreweave_chat"
USER = _tle_config.USER_ID
MODES = ("none", "standing", "as-is", "allow-under-test")

# 🔴 `allow-under-test` EXISTS BECAUSE OF AN OWNER DECISION, 2026-08-22, AND ONLY BECAUSE OF IT.
#
# The predecessor loop's standing rule was absolute: "a card for a COST-BEARING or IRREVERSIBLE
# tool is NEVER approved." That is why ~10 tools carry a structurally unreachable DATA bar — the
# card is raised, the store never moves, and "the write lands" can never be shown. The owner
# reversed it: such a card MAY be approved when the target was created by the run's OWN THROWAWAY
# fixture and is torn down after. Never the dogfood book. Never a pre-existing object.
#
# What this mode does is NARROW ON PURPOSE. It grants a standing `allow` for the tools a batch
# names as `tool_under_test` and nothing else, so every OTHER advertised tool still raises a card.
# That distinction is load-bearing: a blanket allow would measure a user who had approved the whole
# catalogue, and a write by a neighbouring tool would then look like the tool under test working —
# which is exactly the confusion the 23 stale rows above caused in batch 1.
#
# It is the SECOND HALF of a pair and is useless alone. The default `none` arm shows the GATE
# HOLDS (card raised, store unchanged); this arm shows the WRITE LANDS (no card, tool executes,
# store moves). Neither sentence is provable from the other arm's evidence.


def snapshot() -> list[dict]:
    rows = oracle.db_query(
        DB, "SELECT tool_name, decision FROM user_tool_approvals "
            f"WHERE user_id='{USER}' ORDER BY tool_name")
    return [{"tool_name": r[0], "decision": r[1]} for r in rows if r and r[0]]


def clear() -> int:
    before = snapshot()
    oracle.db_query(DB, f"DELETE FROM user_tool_approvals WHERE user_id='{USER}'")
    return len(before)


def allow_only(tools: list[str]) -> int:
    """Clear every standing decision, then grant `allow` to exactly these tools and no others."""
    oracle.db_query(DB, f"DELETE FROM user_tool_approvals WHERE user_id='{USER}'")
    n = 0
    for t in sorted(set(tools)):
        safe = t.replace("'", "''")
        oracle.db_query(
            DB, "INSERT INTO user_tool_approvals (user_id, tool_name, decision) "
                f"VALUES ('{USER}', '{safe}', 'allow') "
                "ON CONFLICT (user_id, tool_name) DO UPDATE SET decision='allow'")
        n += 1
    return n


def restore(rows: list[dict]) -> int:
    """Put the account back exactly as it was found — decisions included."""
    oracle.db_query(DB, f"DELETE FROM user_tool_approvals WHERE user_id='{USER}'")
    for r in rows:
        t = r["tool_name"].replace("'", "''")
        d = (r["decision"] or "allow").replace("'", "''")
        oracle.db_query(
            DB, "INSERT INTO user_tool_approvals (user_id, tool_name, decision) "
                f"VALUES ('{USER}', '{t}', '{d}') "
                "ON CONFLICT (user_id, tool_name) DO UPDATE SET decision=EXCLUDED.decision")
    return len(rows)


class ApprovalState:
    """Context manager. Applies the mode, and restores on the way out no matter what."""

    def __init__(self, mode: str, tools: list[str] | None = None) -> None:
        if mode not in MODES:
            raise ValueError(f"approval mode must be one of {MODES}, got {mode!r}")
        if mode == "allow-under-test" and not tools:
            raise ValueError("allow-under-test needs the tools the batch is testing; granting "
                             "nothing would silently measure the `none` arm again and report it "
                             "as the approved one")
        self.mode = mode
        self.tools = list(tools or [])
        self.saved: list[dict] = []

    def __enter__(self) -> "ApprovalState":
        self.saved = snapshot()
        if self.mode == "none":
            clear()
            print(f"approvals: cleared {len(self.saved)} standing decision(s) for this batch "
                  "(restored on exit)")
        elif self.mode == "allow-under-test":
            n = allow_only(self.tools)
            print(f"approvals: allow-under-test — {len(self.saved)} standing decision(s) saved, "
                  f"replaced by `allow` for exactly {n} tool(s) under test.")
            print("           🔴 WRITES WILL LAND WITHOUT A CARD for these, against the run's OWN "
                  "throwaway fixture only. Restored on exit.")
            for t in sorted(set(self.tools)):
                print(f"           allow  {t}")
        else:
            print(f"approvals: {self.mode} — {len(self.saved)} standing decision(s) left in place")
        return self

    def __exit__(self, *exc) -> None:
        if self.mode in ("none", "allow-under-test"):
            n = restore(self.saved)
            print(f"approvals: restored {n} standing decision(s)")
        return None


def main() -> int:
    print(json.dumps(snapshot(), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
