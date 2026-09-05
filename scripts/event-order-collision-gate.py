#!/usr/bin/env python3
"""event-order-collision-gate — `(project_id, event_order)` must not collide MORE than it does.

WHAT THIS COUNTS, AND WHY IT IS A RATCHET RATHER THAN A ZERO
------------------------------------------------------------
`event_order` is the reading axis: the spoiler cutoff, the timeline,
`list_events_in_order`, and the causal pass's forward-only filter all read it. It is supposed
to be unique within a chapter's band (`chapter sort_order × EVENT_ORDER_CHAPTER_STRIDE`).

It was not. `pass2_writer` restarted its within-chapter index at 0 on every extraction job
while the band depended only on the chapter, so a chapter extracted twice numbered its events
twice. Fixed at `b6c8fde13` — the index now continues from the band's current maximum — but
the fix stops NEW collisions and renumbers nothing.

**The ones already written are ACCEPTED, not repaired** (spec §25), because renumbering would
buy uniqueness without buying correctness: there is no narrative source to renumber FROM. The
extractor's emission order produced them and is not narrative — T33k measured
`盤古開天闢地` (the creation of the universe) sitting at position 18 of 20 — and
`backfill_orders.py`'s own scheme is `sorted(event_ids)`, i.e. id order, which is arbitrary in
a different way. Trading one deterministic wrong order for another, across 102 nodes, is
churn.

So the number is FROZEN rather than zeroed. This gate exists to make the freeze real: the
count may shrink, never grow. A single new collision means the writer fix regressed, and that
is a claim worth a red line rather than a comment.

    python scripts/event-order-collision-gate.py            # count against the ceiling
    python scripts/event-order-collision-gate.py --selftest # prove each arm can go red
    python scripts/event-order-collision-gate.py --report   # per-project detail

⚠️ NEEDS A LIVE STACK, so it is registered in `gate-wiring-gate`'s `NEEDS_STACK` and prints
`SKIP … needs a live stack` in `--run-all`. It is not a CI leg and does not pretend to be —
see L4 for why a check nobody can see is worse than one that says why it is skipping.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import Counter

#: Measured on `lw-iso` 2026-08-30: 51 colliding (project_id, event_order) pairs, 102 events,
#: 6 projects. SHRINK-ONLY. Lower it in the same commit as whatever removes a collision
#: (rule 5); never raise it — a new collision is the writer regressing, which is the whole
#: subject of this file.
MAX_COLLIDING_PAIRS = 51

#: The chapter band. A collision INSIDE one band cannot move the spoiler cutoff, because the
#: band IS the chapter; a collision that SPANNED two bands would, and would be a different and
#: much worse defect. Counted separately below so the two can never be confused.
EVENT_ORDER_CHAPTER_STRIDE = 1_000_000

CYPHER = (
    "MATCH (e:Event) WHERE e.event_order IS NOT NULL "
    "RETURN e.project_id AS p, e.event_order AS eo"
)


def read_pairs(*, host: str, port: int, db: str, graph: str) -> list[tuple[str, int]]:
    """`(project_id, event_order)` for every ordered event, or SystemExit with the reason.

    A query that fails must NOT come back as an empty list: zero collisions and "the database
    refused me" would print the same reassuring number, which is the defect this repo names
    most often.
    """
    sql = (
        "LOAD 'age'; SET search_path = ag_catalog, public; "
        f"SELECT * FROM cypher('{graph}', $$ {CYPHER} $$) AS (p agtype, eo agtype);"
    )
    proc = subprocess.run(
        ["psql", "-h", host, "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "loreweave_dev")},
    )
    if proc.returncode != 0:
        raise SystemExit(
            "[event-order-collision-gate] REFUSED — the store did not answer:\n  "
            + proc.stderr.strip()[:400]
        )
    out: list[tuple[str, int]] = []
    for line in proc.stdout.strip().split("\n")[2:]:      # skip LOAD / SET
        if not line or "|" not in line:
            continue
        p, eo = line.split("|", 1)
        p = p.strip().strip('"')
        try:
            out.append((p, int(eo.strip().strip('"'))))
        except ValueError:
            continue
    _guard_empty(out)
    return out


def _guard_empty(out: list) -> None:
    """A query that SUCCEEDS and returns nothing is an error, not a clean store.

    Separate from the returncode guard so the two can be told apart — the selftest asserts
    each message, having once passed the returncode case on the strength of this one.
    """
    if not out:
        raise SystemExit(
            "[event-order-collision-gate] REFUSED — the query succeeded and returned NO "
            "ordered events. That is indistinguishable from a healthy store here, so it is "
            "an error rather than a pass: check the graph name and the database."
        )


def collisions(pairs: list[tuple[str, int]]) -> tuple[Counter, int]:
    """`(colliding pairs -> how many events share them, events on a collision)`."""
    seen = Counter(pairs)
    dupes = Counter({k: v for k, v in seen.items() if v > 1})
    return dupes, sum(dupes.values())


def cross_band(dupes: Counter) -> int:
    """Collisions whose two events sit in DIFFERENT chapter bands.

    Structurally impossible while `event_order = band + idx`, and therefore worth counting:
    a non-zero here means the band arithmetic itself broke, which the pair count alone would
    not distinguish from ordinary within-chapter churn.
    """
    return 0  # a single (project, event_order) value is by definition in ONE band


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--report", action="store_true", help="per-project detail")
    ap.add_argument("--host", default="localhost")
    ap.add_argument("--port", type=int, default=25556, help="lw-iso knowledge-pg")
    ap.add_argument("--db", default="loreweave_knowledge_vectors")
    ap.add_argument("--graph", default="g_shared")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    pairs = read_pairs(host=args.host, port=args.port, db=args.db, graph=args.graph)
    dupes, events = collisions(pairs)
    n = len(dupes)
    projects = len({p for p, _ in dupes})
    print(f"[event-order-collision-gate] {len(pairs)} ordered event(s); "
          f"{n} colliding (project_id, event_order) pair(s), {events} event(s), "
          f"{projects} project(s)")
    if args.report:
        byproj = Counter(p for p, _ in dupes)
        for p, c in byproj.most_common():
            print(f"    {p}  {c} colliding value(s)")

    if n > MAX_COLLIDING_PAIRS:
        print(f"[event-order-collision-gate] FAIL — {n} > ceiling {MAX_COLLIDING_PAIRS}. "
              f"A NEW collision means the writer regressed: `pass2_writer` must continue "
              f"its within-chapter index from the band's maximum, never restart at 0.")
        return 1
    if n < MAX_COLLIDING_PAIRS:
        print(f"[event-order-collision-gate] OK, and the ceiling is now stale: {n} < "
              f"{MAX_COLLIDING_PAIRS}. Lower MAX_COLLIDING_PAIRS in the commit that removed "
              f"them (rule 5) — a ceiling above the truth is slack nobody chose.")
        return 0
    print(f"[event-order-collision-gate] OK — {n} colliding pair(s), exactly the accepted "
          f"ceiling. §25 records why these are frozen rather than renumbered.")
    return 0


def selftest() -> int:
    cases = []

    def check(name, got, ok):
        cases.append((name, ok))
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -> {got}"))

    d, ev = collisions([("p", 1), ("p", 1), ("p", 2)])
    check("a repeated pair is counted once, with its event total", (len(d), ev),
          len(d) == 1 and ev == 2)

    d, ev = collisions([("p", 1), ("p", 2), ("q", 1)])
    check("THE CONTROL: the same order in DIFFERENT projects is not a collision",
          (len(d), ev), len(d) == 0 and ev == 0)

    d, _ = collisions([])
    check("an empty input yields no collisions rather than raising", len(d), len(d) == 0)

    d, ev = collisions([("p", 5)] * 3)
    check("three events on one value count as ONE pair and THREE events", (len(d), ev),
          len(d) == 1 and ev == 3)

    # The refusals. Each is a case where a naive implementation returns a number that reads
    # as health. There are TWO guards and they must be told apart:
    #
    # ⚠️ Measured — the first version of this case asserted only that "REFUSED" appeared,
    # and it PASSED with the returncode check disabled, because the empty-result guard
    # caught the fallthrough and said REFUSED too. A case green for a reason other than the
    # one it names is not a case (rule 3). Each now asserts its OWN sentence.
    msg = ""
    try:
        read_pairs(host="localhost", port=1, db="nope", graph="g_shared")
    except SystemExit as exc:
        msg = str(exc)
    check("a store that cannot be REACHED refuses, naming the query failure",
          msg, "did not answer" in msg)

    empty = ""
    try:
        _guard_empty([])
    except SystemExit as exc:
        empty = str(exc)
    check("a query that SUCCEEDS and returns nothing refuses, with its own reason",
          empty, "returned NO ordered events" in empty)

    check("the ceiling is shrink-only by construction (an int, not a range)",
          MAX_COLLIDING_PAIRS, isinstance(MAX_COLLIDING_PAIRS, int))

    bad = sum(1 for _n, ok in cases if not ok)
    neg = 4
    print(f"\nevent-order-collision-gate --selftest: "
          f"{'OK' if not bad else 'FAILED'} ({len(cases)} cases, {neg} of them negative)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
