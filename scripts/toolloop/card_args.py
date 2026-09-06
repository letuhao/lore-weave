#!/usr/bin/env python
"""What a confirm card WOULD apply, read without approving it.

🔴 THE GAP THIS CLOSES. This loop never approves a Tier-A/W card — that is a standing safety
rule — so for every carded tool the evidence records `left_suspended: true`, an empty `answer`,
and a store that is unchanged. All of which is correct, and none of which says WHAT THE MODEL
WAS ABOUT TO DO. A card that reads "rename this world" and carries `description: ""` looks
identical in the evidence to one that carries only a name, and the store cannot tell them apart
because neither was applied.

That matters because the whole world/map update family declares the same contract — "provide
only the fields you want to change; omitted fields are left unchanged" — and this repo has paid
for breaking it before (CP-5.11: optional view fields whose omission silently cleared them, then
the legacy upsert doing the same with worse consequences). A model that helpfully fills every
optional field would blank an author's description, MOVE a pin (x/y are ABSOLUTE), or redraw a
region's outline, and the card that obtained consent would say only "rename".

MEASURED 2026-08-21, batch 31, using exactly this query — and the answer was reassuring:

    world_update      -> {"name": "The Ashen Reach …", "world_id": "…"}      no `description`
    world_map_update  -> {"name": "The Drowned Coast …", "map_id": "…"}      no `image_ref`,
                                                                            no guessed
                                                                            `expected_version`
    world_move_book   -> {"book_id": "…", "world_id": "…"}                   no `clear_world`

Four of four, five of five, five of five. The model does not pad optional fields. That is a
NEGATIVE result and it is worth as much as a defect would have been: it retires a hypothesis the
batch was built around, and it retires it with the actual proposed arguments rather than an
inference from an unchanged store.

WHERE IT COMES FROM. chat-service persists a suspended run in `chat_suspended_runs`, and
`pending_tool_call` holds the tool call the model proposed, verbatim, including its args. Reading
it is a SELECT — no approval, no side effect, nothing applied.

Usage:
    python scripts/toolloop/card_args.py --since 2h
    python scripts/toolloop/card_args.py --tool world_update
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

CHAT_DB = "loreweave_chat"
PG = ["docker", "exec", "infra-postgres-1", "psql", "-U", "loreweave", "-d", CHAT_DB, "-t", "-A"]


def _q(sql: str) -> list[str]:
    r = subprocess.run([*PG, "-c", sql], capture_output=True, text=True)
    if r.returncode != 0:
        print(f"psql failed: {r.stderr.strip()[:300]}", file=sys.stderr)
        return []
    return [ln for ln in r.stdout.strip().splitlines() if ln]


def cards(since: str = "2 hours", tool: str | None = None) -> list[dict]:
    """The tool calls sitting behind unapproved cards, newest first."""
    where = f"created_at > now() - interval '{since}'"
    if tool:
        # Bound the LIKE to the tool NAME field rather than the whole blob, so a tool mentioned
        # inside another call's arguments does not masquerade as its own card.
        where += f" AND pending_tool_call->>'name' = '{tool}'"
    rows = _q(f"SELECT pending_tool_call::text FROM chat_suspended_runs WHERE {where} "
              f"ORDER BY created_at DESC LIMIT 200")
    out = []
    for raw in rows:
        try:
            out.append(json.loads(raw))
        except ValueError:
            continue
    return out


def proposed_args(card: dict) -> tuple[str, dict]:
    """(tool name, the args the model actually proposed).

    The payload nests: {"name": tool, "args": {"kind": "tool_approval", "tier": …,
    "tool": …, "args": {THE REAL ARGS}}}. Reaching for the outer `args` gives the card
    envelope — the tier and the kind — not what would be written, which is the mistake this
    helper exists to stop anyone making twice.
    """
    name = card.get("name") or ""
    env = card.get("args") or {}
    inner = env.get("args")
    return name, (inner if isinstance(inner, dict) else {})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2 hours", help="postgres interval, e.g. '2 hours'")
    ap.add_argument("--tool", help="only cards for this tool")
    ap.add_argument("--fields", action="store_true",
                    help="summarise WHICH argument names each tool proposed, across all cards")
    a = ap.parse_args()

    found = cards(a.since, a.tool)
    if not found:
        print("no suspended cards in that window — a card expires, and a torn-down fixture takes "
              "its run with it, so read this while the batch is fresh")
        return 0

    if a.fields:
        seen: dict[str, dict[str, int]] = {}
        for c in found:
            name, args = proposed_args(c)
            per = seen.setdefault(name, {})
            for k in args:
                per[k] = per.get(k, 0) + 1
        for name in sorted(seen):
            total = sum(1 for c in found if proposed_args(c)[0] == name)
            fields = ", ".join(f"{k}×{n}" for k, n in sorted(seen[name].items()))
            print(f"{name}  ({total} card(s)): {fields}")
        return 0

    for c in found:
        name, args = proposed_args(c)
        print(f"{name}: {json.dumps(args, ensure_ascii=False)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
