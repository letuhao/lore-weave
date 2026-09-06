#!/usr/bin/env python3
"""causal-coverage-gate — what the causal pass covers, over a denominator the DESIGN chose.

THE QUESTION, AND THE NUMBER THAT WAS RETRACTED FOR ANSWERING IT WRONG
----------------------------------------------------------------------
`D-T33-CAUSAL-COVERAGE-UNMEASURED` asks *"the bite is one book, the graph is eight projects:
does the pass produce useful causal edges across the whole corpus, not just where it was
pointed."* §4.3 already retracted one answer — a global `0.34 %` that divided by residue from
ad-hoc runs which never touched the causal pipeline. **A ratio over a denominator the design
did not choose is worse than no ratio**, because it looks like a measurement.

So this reports THREE numbers and never one, because they answer different questions and
conflating them is exactly how `0.34 %` happened:

* **REACH** — projects holding at least one ordered edge, over projects holding any event.
  An OPERATIONS fact, not a quality one: the causal pass is triggered by
  `POST /internal/.../causal-edges`, so a project without edges is one nobody ran it on.
  Reporting this as "coverage" is the retracted number's exact mistake.
* **YIELD** — edges over CANDIDATE PAIRS, in the projects where it ran. The candidate set is
  the design's own: `infer_causal_edges` slides a 12-event window with stride 6 over
  `list_events_in_order`, and `parse_edges` keeps only pairs inside one window. A pair that
  never shared a window was never offered to the model, and counting it would repeat §4.3.
* **CONSISTENCY** — edges that lie OUTSIDE any window. This is the assertion with teeth: the
  pass structurally cannot emit one, so a non-zero means either something else wrote ordered
  edges, or the ordering moved underneath them.

⚠️ **The candidate set is computed from the corpus NOW; the edges were emitted against the
corpus THEN.** Adding events shifts window boundaries, so YIELD is approximate and drifts as
a project grows. Named here rather than presented as exact.

⚠️ **`event_order` may be NULL and those events STILL COUNT.** `list_events_in_order` sorts
`coalesce(event_order, INT64_MAX)` then title, so null-order events are in the window like any
other. Filtering them out of the denominator was the first thing this script got wrong: it
reported 3 edges as "unexplained by any window" when the truth was that their endpoints had
been excluded from the denominator. Measuring the wrong denominator is the failure this file
exists to avoid, and it happened once while writing it.

    python scripts/causal-coverage-gate.py             # the three numbers
    python scripts/causal-coverage-gate.py --selftest  # each arm driven to red
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections import defaultdict

#: `list_events_in_order`'s null sentinel — null-order events sort LAST but are still in the
#: list, and therefore still in a window.
NULL_ORDER_SENTINEL = 9223372036854775807

#: `infer_causal_edges._WINDOW` / `._STRIDE`. Mirrored rather than imported so this script
#: runs without the service on the path; the selftest pins the pair so a drift is visible.
WINDOW, STRIDE = 12, 6

#: The invariant with teeth. The pass keeps a triple only when both ids are in one window, so
#: an edge outside every window cannot have come from it.
MAX_UNEXPLAINED_EDGES = 0


def ratio(name: str, num: int, den: int, den_name: str) -> str:
    """A percentage that CANNOT be printed without saying what it divided by.

    The signature is the guard: there is no way to format a ratio here and leave the
    denominator out, which is the shape §4.3 retracted. A zero denominator prints `n/a`
    rather than a division error or, worse, a 0 % that reads like a finding.
    """
    if not den_name.strip():
        raise ValueError("a ratio must name its denominator")
    if den <= 0:
        return f"{name}: n/a — the denominator ({den_name}) is empty"
    return f"{name}: {num}/{den} = {num / den * 100:.2f}%  of {den_name}"


def _cypher(stmt: str, cols: str, *, port: int, db: str, graph: str) -> list[list[str]]:
    sql = (f"LOAD 'age'; SET search_path = ag_catalog, public; "
           f"SELECT * FROM cypher('{graph}', $$ {stmt} $$) AS ({cols});")
    proc = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "loreweave_dev")})
    if proc.returncode != 0:
        raise SystemExit("[causal-coverage-gate] REFUSED — the store did not answer:\n  "
                         + proc.stderr.strip()[:400])
    return [ln.split("|") for ln in proc.stdout.strip().split("\n")[2:] if ln and "|" in ln]


def candidate_pairs(rows: list[tuple[int, str, str]]) -> set[tuple[str, str]]:
    """Every ordered pair the sliding window would offer the model, for one project.

    `rows` must already be sorted the way `list_events_in_order` sorts:
    `(coalesce(event_order, SENTINEL), title)`. Pairs are directed forward, matching
    `parse_edges`' `order_index[a] < order_index[b]` filter — a backward pair is not a
    candidate because the pass would drop it.
    """
    out: set[tuple[str, str]] = set()
    for start in range(0, len(rows), STRIDE):
        window = rows[start:start + WINDOW]
        for i, a in enumerate(window):
            for b in window[i + 1:]:
                out.add((a[2], b[2]))
    return out


def collect(*, port: int, db: str, graph: str):
    edges: set[tuple[str, str, str]] = set()
    for rel in ("CAUSES", "PRECEDES"):
        # AGE does not parse `[r:CAUSES|PRECEDES]`; one query per type, which is also how
        # `merge_causal_edges` writes them.
        for a, b, p in _cypher(
                f"MATCH (a:Event)-[:{rel}]->(b:Event) "
                f"RETURN a.id AS a, b.id AS b, a.project_id AS p",
                "a agtype, b agtype, p agtype", port=port, db=db, graph=graph):
            edges.add((a.strip().strip('"'), b.strip().strip('"'), p.strip().strip('"')))

    by_project: dict[str, list[tuple[int, str, str]]] = defaultdict(list)
    for p, eo, title, eid in _cypher(
            "MATCH (e:Event) RETURN e.project_id AS p, e.event_order AS eo, "
            "e.title AS t, e.id AS i",
            "p agtype, eo agtype, t agtype, i agtype", port=port, db=db, graph=graph):
        raw = eo.strip().strip('"')
        order = int(raw) if raw and raw != "null" else NULL_ORDER_SENTINEL
        by_project[p.strip().strip('"')].append(
            (order, title.strip().strip('"'), eid.strip().strip('"')))
    for p in by_project:
        by_project[p].sort(key=lambda r: (r[0], r[1]))
    return edges, by_project


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--port", type=int, default=25556)
    ap.add_argument("--db", default="loreweave_knowledge_vectors")
    ap.add_argument("--graph", default="g_shared")
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    edges, by_project = collect(port=args.port, db=args.db, graph=args.graph)
    if not by_project:
        raise SystemExit("[causal-coverage-gate] REFUSED — no events at all. An empty store "
                         "reports the same 0 as a broken query.")
    ran = {p for _a, _b, p in edges}

    print("[causal-coverage-gate] the causal pass, three numbers, each with its denominator")
    print("  " + ratio("REACH   ", len(ran), len(by_project),
                       "projects holding any event (an OPERATIONS fact: the pass is "
                       "operator-triggered, so a project without edges is one nobody ran)"))

    total_cand = total_hit = unexplained = 0
    print(f"\n  {'project':<40} {'events':>7} {'candidates':>11} {'edges':>6} {'yield':>8}")
    for p in sorted(ran):
        rows = by_project.get(p, [])
        cand = candidate_pairs(rows)
        mine = {(a, b) for a, b, pp in edges if pp == p}
        hit = len(mine & cand)
        unexplained += len(mine - cand)
        total_cand += len(cand)
        total_hit += hit
        pct = f"{hit / len(cand) * 100:.2f}%" if cand else "n/a"
        print(f"  {p:<40} {len(rows):>7} {len(cand):>11} {len(mine):>6} {pct:>8}")

    print("\n  " + ratio("YIELD   ", total_hit, total_cand,
                        f"CANDIDATE PAIRS — pairs sharing one {WINDOW}-event window "
                        f"(stride {STRIDE}) in a project where the pass ran"))
    print(f"  CONSISTENCY: {unexplained} of {len(edges)} edge(s) lie outside every window")
    print("  (the candidate set is the corpus NOW; the edges were emitted against the corpus "
          "THEN, so YIELD drifts as a project grows)")

    if unexplained > MAX_UNEXPLAINED_EDGES:
        print(f"\n[causal-coverage-gate] FAIL — {unexplained} edge(s) outside every window "
              f"(ceiling {MAX_UNEXPLAINED_EDGES}). `parse_edges` keeps a triple only when "
              f"both ids share a window, so the pass cannot have emitted these: either "
              f"something else wrote ordered edges, or the ordering moved under them.")
        return 1
    print(f"\n[causal-coverage-gate] OK — every ordered edge is explained by the window "
          f"algorithm that emits them (ceiling {MAX_UNEXPLAINED_EDGES}).")
    return 0


def selftest() -> int:
    fails = []

    def check(name, ok, got=None):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -> {got}"))
        if not ok:
            fails.append(name)

    r = [(1, "a", "A"), (2, "b", "B"), (3, "c", "C")]
    c = candidate_pairs(r)
    check("a short list yields every FORWARD pair and no backward one",
          c == {("A", "B"), ("A", "C"), ("B", "C")}, c)

    # THE CONTROL. Null-order events are NOT excluded: list_events_in_order sorts them last
    # and the window contains them. Filtering them out is the mistake this file made once,
    # and it turned 0 unexplained edges into 3.
    with_null = [(1, "a", "A"), (NULL_ORDER_SENTINEL, "z", "Z")]
    check("a NULL-order event is still a candidate",
          ("A", "Z") in candidate_pairs(with_null), candidate_pairs(with_null))

    far = [(i, str(i), f"E{i}") for i in range(30)]
    c = candidate_pairs(far)
    check("two events 20 apart never share a window", ("E0", "E20") not in c)
    check("...but two events 5 apart do", ("E0", "E5") in c)
    check("the window/stride pair matches infer_causal_edges", (WINDOW, STRIDE) == (12, 6),
          (WINDOW, STRIDE))

    # A ratio must NAME its denominator — the retracted 0.34 % printed a number alone.
    ok = False
    try:
        ratio("X", 1, 2, "   ")
    except ValueError:
        ok = True
    check("a ratio with no denominator NAME is refused", ok)
    check("a zero denominator prints n/a rather than 0%",
          "n/a" in ratio("X", 0, 0, "things"), ratio("X", 0, 0, "things"))
    check("a real ratio carries its denominator in the string",
          "of things" in ratio("X", 1, 4, "things"), ratio("X", 1, 4, "things"))

    print(f"\ncausal-coverage-gate --selftest: {'OK' if not fails else 'FAILED'} "
          f"(8 cases, 3 of them negative)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
