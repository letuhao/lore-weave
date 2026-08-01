#!/usr/bin/env python3
"""Feed the kind ledger from the extraction history it never had. DRY-RUN by default.

An entity's kind used to be decided by whichever extraction batch named it first and was
never revisited. Measured on one book: 173 of 1,531 stored entities held a kind the model
disagreed with by majority -- including the protagonist, filed as `species` because that
answer arrived on the book's very first run.

The evidence that would have prevented it exists: every parse this platform has ever cached
sits in translation-service's `extraction_raw_outputs`. This script aggregates it per
(name, kind_code) and posts the counts to glossary-service, which records them and re-resolves
with `domain.ResolveKind`.

**It carries no resolution policy of its own.** Reimplementing the estimator here is the
mirror-the-producer defect this repo shipped twice in one day; the script posts counts and Go
decides. That is also why `--apply` only changes what glossary does with the same numbers.

    python scripts/backfill-entity-kind-votes.py --book <uuid>            # dry run
    python scripts/backfill-entity-kind-votes.py --book <uuid> --apply    # re-kind + emit
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict

DEFAULT_TRANSLATION_DSN = os.environ.get(
    "TRANSLATION_DB_URL",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_translation",
)
DEFAULT_GLOSSARY_URL = os.environ.get("GLOSSARY_INTERNAL_URL", "http://localhost:8211")
INTERNAL_TOKEN = os.environ.get("INTERNAL_SERVICE_TOKEN", "")


def gather(dsn: str, book_id: str) -> list[dict]:
    """(name, kind_code) -> how many times extraction proposed it, over every cached parse.

    Reads `batch_idx >= 0` only: a negative index is a stage-1 SWEEP row, which holds
    MENTIONS rather than typed entities and has no kind to vote with.
    """
    import asyncio

    import asyncpg  # imported late so --help works without a driver installed

    async def run() -> list:
        conn = await asyncpg.connect(dsn, timeout=10)
        try:
            return await conn.fetch(
                "SELECT parsed_entities FROM extraction_raw_outputs "
                "WHERE book_id = $1 AND batch_idx >= 0", book_id)
        finally:
            await conn.close()

    tally: dict[str, Counter] = defaultdict(Counter)
    for row in asyncio.run(run()):
        raw = row["parsed_entities"]
        ents = json.loads(raw) if isinstance(raw, str) else (raw or [])
        for e in ents or []:
            name, kind = e.get("name"), e.get("kind_code")
            if name and kind:
                tally[name][kind] += 1
    return [
        {"name": name, "kind_code": kind, "votes": n}
        for name, kinds in tally.items()
        for kind, n in kinds.items()
    ]


def post(base: str, book_id: str, votes: list[dict], apply_: bool) -> dict:
    body = json.dumps({"votes": votes, "apply": apply_}).encode()
    req = urllib.request.Request(
        f"{base}/internal/books/{book_id}/kind-votes", data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    req.add_header("X-Internal-Token", INTERNAL_TOKEN)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            return json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as e:
        print(f"glossary returned {e.code}: {(e.read() or b'').decode()[:400]}", file=sys.stderr)
        raise SystemExit(1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", required=True, help="book_id (UUID)")
    ap.add_argument("--apply", action="store_true",
                    help="actually re-kind. Without it, votes are recorded and the changes "
                         "are PREVIEWED but no entity moves.")
    ap.add_argument("--dsn", default=DEFAULT_TRANSLATION_DSN)
    ap.add_argument("--glossary", default=DEFAULT_GLOSSARY_URL)
    args = ap.parse_args()

    if not INTERNAL_TOKEN:
        print("INTERNAL_SERVICE_TOKEN is not set", file=sys.stderr)
        raise SystemExit(2)

    votes = gather(args.dsn, args.book)
    names = len({v["name"] for v in votes})
    print(f"observations: {sum(v['votes'] for v in votes)} across {names} names "
          f"({len(votes)} name/kind pairs)")

    res = post(args.glossary, args.book, votes, args.apply)
    print(f"matched {res['entities_touched']} entities, {res['unmatched']} rows matched nothing")
    changes = res.get("changes") or []
    moves = [c for c in changes if c.get("to") and c["to"] != c["from"]]
    conflicts = [c for c in changes if c.get("conflict")]
    print(f"\n{'APPLIED' if res['applied'] else 'WOULD CHANGE'}: {len(moves)} kind(s)")
    for c in sorted(moves, key=lambda c: (c["from"], c["to"]))[:60]:
        tag = " (refinement)" if c.get("refinement") else ""
        print(f"   {c['name']:14s} {c['from']:14s} -> {c['to']}{tag}")
    if len(moves) > 60:
        print(f"   ... and {len(moves) - 60} more")
    stuck = res.get("blocked_by_duplicate") or []
    if stuck:
        print("")
        print(f"BLOCKED: {len(stuck)} move(s) the dedup key refused. The target kind already")
        print("holds an entity with that name, so the operation the data calls for is a MERGE")
        print("of two rows, not a re-kind of one:")
        for c in stuck[:20]:
            print(f"   {c['name']:14s} {c['from']:14s} -> {c['to']} (needs merge)")
    if conflicts:
        print(f"\nrecorded {len(conflicts)} unresolved disagreement(s) (led, but under the "
              f"switch threshold):")
        for c in conflicts[:20]:
            print(f"   {c['name']:14s} holds {c['from']:14s} · model leans {c['conflict']}")
    if not res["applied"]:
        print("\nDRY RUN — re-run with --apply to move them.")


if __name__ == "__main__":
    main()
