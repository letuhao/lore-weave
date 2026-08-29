#!/usr/bin/env python3
"""graph-store-migrated-gate — refuse to read "the backend is configured" as "the data is there".

T54d is the argument, and it is the same shape `soak-armed-gate` exists for, one layer up.
Measured on dev 2026-08-24, reads only:

    infra/.env:17           KNOWLEDGE_GRAPH_BACKEND=age
    dev Neo4j (7688)        8 033 nodes across 10 labels, 4 249 relationships, 433 projects
    dev AGE (knowledge-pg)  1 graph registered, 0 graphs with entities, 0 entities
    migration Neo4j -> AGE  none in the tree

Every gate in the repo was green. `port-adoption-gate` read `backend declarations 0/0 non-age`
and was RIGHT — the declaration is what it checks. `soak-armed-gate` verifies dual-write ARMING
and says so. `knowledge-graph-backend-live-smoke` writes a row and reads it back, so it proves
the round trip and passes perfectly against a store that holds nothing else. **Not one of them
asks whether the store the service is about to read has anything in it**, because each is asking
about wiring and this is a question about DATA.

WHAT THIS ASKS
──────────────
Given two censuses — the declared backend's store and the other one — does the declared store
hold the projects the other store holds? A deployment mid-cutover has an answer; a deployment
that flipped a variable and never moved the data has a different one, and they are not
distinguishable from either census alone.

THE VERDICTS, AND WHY A SKIP IS NOT A PASS
──────────────────────────────────────────
`env-gated tests skip and the green suite lies` is a known failure class here, so the readings
are distinct and named rather than collapsing into pass/fail:

    MIGRATED        the declared store holds every project the other one does   -> PASS
    PARTIAL         it holds some but not all                                   -> FAIL
    EMPTY_DECLARED  the other store has projects and the declared one has none  -> FAIL  (T54d)
    BOTH_EMPTY      neither store holds anything                                -> INDETERMINATE
    ONE_STORE       only one store is reachable, so there is nothing to compare -> INDETERMINATE
    DISARMED        no census was supplied at all                               -> INDETERMINATE

`BOTH_EMPTY` is INDETERMINATE and not a pass on purpose: a fresh deployment is legitimately
empty, and a gate that called that "migrated" would go green on exactly the state it exists to
catch, one deployment earlier.

Run:
    python scripts/graph-store-migrated-gate.py --selftest
    python scripts/graph-store-migrated-gate.py \
        --declared age \
        --declared-census age.json --other-census neo4j.json

A census is `{"<project_id>": <node count>}`. Producing one is deliberately NOT this script's
job: reading it requires a live engine, credentials and a driver per backend, and a gate that
opened database connections could not be run offline in CI — which is where the selftest below
has to work.
"""
from __future__ import annotations

import argparse
import json
import sys

#: A project with this many nodes or fewer in the declared store, while the other store has
#: it, counts as NOT migrated. Zero rather than a fraction: partial rows are a real state
#: (a migration interrupted mid-project) and it is not this gate's job to guess a threshold
#: for "enough". Present-with-something is the question; completeness is `verify`'s.
PRESENT = 0


def verdict(declared: dict | None, other: dict | None) -> tuple[str, str]:
    """Compare two per-project node censuses. Returns `(verdict, human reason)`.

    Pure on purpose. The live half of this question needs two drivers and two sets of
    credentials; the DECISION needs neither, and keeping them apart is what lets every reading
    below be exercised offline — including the three that no live stack can produce on demand.
    """
    if declared is None and other is None:
        return ("DISARMED", "no census supplied for either store — nothing was compared")
    if declared is None or other is None:
        which = "declared" if declared is None else "other"
        return ("ONE_STORE", f"only one census was supplied (the {which} store is missing), "
                             f"so there is nothing to compare against")

    declared_has = {p for p, n in declared.items() if n > PRESENT}
    other_has = {p for p, n in other.items() if n > PRESENT}

    if not declared_has and not other_has:
        return ("BOTH_EMPTY", "neither store holds any project — a fresh deployment is "
                              "legitimately empty, and calling that MIGRATED would go green "
                              "on the state this gate exists to catch")
    if other_has and not declared_has:
        return ("EMPTY_DECLARED",
                f"the other store holds {len(other_has)} project(s) and the declared store "
                f"holds NONE — every graph read would answer from an empty store (T54d)")
    if not other_has:
        # T48y measured this on iso: `MIGRATED — the declared store holds all 0 project(s) the
        # other store does`, passing the proof's STORE leg. The verdict was defensible (an
        # emptied old store IS the post-migration shape) and the CLAIM was not: it is
        # word-for-word what a store nobody ever populated elsewhere produces, and what an
        # empty census file produces. An ABSENT census already reads ONE_STORE — "nothing to
        # compare against" — and `{}` carries exactly the same comparison evidence, so it must
        # not read as the success of a comparison. Non-blocking, like ONE_STORE: a sole-store
        # deployment is legitimate. NAMED, so nobody reads it as a verified migration.
        return ("SOLE_STORE",
                f"the other store holds NO projects, so NOTHING was compared. The declared "
                f"store holds {len(declared_has)} project(s) — which is the post-migration "
                f"shape AND what a store that never had a second one looks like. These are "
                f"not distinguishable from censuses alone")
    missing = sorted(other_has - declared_has)
    if missing:
        shown = ", ".join(missing[:5]) + (f" …+{len(missing) - 5} more" if len(missing) > 5 else "")
        return ("PARTIAL",
                f"{len(missing)} of {len(other_has)} project(s) are absent from the declared "
                f"store: {shown}")
    return ("MIGRATED",
            f"the declared store holds all {len(other_has)} project(s) the other store does "
            f"— a comparison over {len(other_has)} project(s), not over none")


#: Which readings block. `BOTH_EMPTY`/`ONE_STORE`/`DISARMED` do not — they mean the comparison
#: did not happen, and a gate that failed on "I could not look" would be turned off within a
#: week. They are printed as INDETERMINATE so a run that proves nothing never reads as a pass.
FAILING = {"EMPTY_DECLARED", "PARTIAL"}
INDETERMINATE = {"BOTH_EMPTY", "ONE_STORE", "DISARMED", "SOLE_STORE"}


def _load(path: str | None) -> dict | None:
    if not path:
        return None
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: a census is an object of project_id -> node count")
    return {str(k): int(v) for k, v in data.items()}


def _selftest() -> int:
    """Every reading, including the three a live stack cannot produce on demand.

    ⚠️ The derivation case is dev — Neo4j full, AGE empty — so it is deliberately NOT the only
    case here. A detector validated on the example that motivated it is green by construction:
    the inverse (a COMPLETED migration) and the partial middle are what say the comparison is
    directional rather than just noticing a zero somewhere.
    """
    full = {"p1": 10, "p2": 5}
    cases = [
        ("dev as measured — declared AGE empty, Neo4j full", {}, full, "EMPTY_DECLARED"),
        ("an emptied other store is SOLE_STORE, not the success of a comparison",
         full, {}, "SOLE_STORE"),
        ("...and an all-ZERO census reads the same as an empty one — a different input shape "
         "reaching the same absence of evidence",
         full, {"p1": 0, "p2": 0}, "SOLE_STORE"),
        ("both stores hold the same projects", full, full, "MIGRATED"),
        ("half the projects moved", {"p1": 10}, full, "PARTIAL"),
        ("a project present but EMPTY in the declared store is not migrated",
         {"p1": 10, "p2": 0}, full, "PARTIAL"),
        ("a fresh deployment", {}, {}, "BOTH_EMPTY"),
        ("the declared store has MORE than the other — not this gate's complaint",
         {"p1": 10, "p2": 5, "p3": 1}, full, "MIGRATED"),
        ("no other census", full, None, "ONE_STORE"),
        ("no declared census", None, full, "ONE_STORE"),
        ("nothing at all", None, None, "DISARMED"),
    ]
    failures = 0
    print("graph-store-migrated-gate - selftest (offline)")
    for label, dec, oth, want in cases:
        got, _ = verdict(dec, oth)
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}: expected {want}, got {got}")

    # Two properties rather than examples, because the table above could satisfy a
    # verdict function that simply memorised its own rows.
    checks = [
        ("EMPTY_DECLARED and BOTH_EMPTY are DISTINCT readings of a zero",
         verdict({}, full)[0] != verdict({}, {})[0]),
        ("THE T48z PROPERTY: an ABSENT other census and an EMPTY one carry the same "
         "comparison evidence, so NEITHER may read as the success of a comparison",
         verdict(full, None)[0] in INDETERMINATE and verdict(full, {})[0] in INDETERMINATE),
        ("...and MIGRATED now states how many projects it compared, never 'all 0'",
         "not over none" in verdict(full, full)[1]),
        ("only EMPTY_DECLARED and PARTIAL block",
         FAILING == {"EMPTY_DECLARED", "PARTIAL"}
         and not (FAILING & INDETERMINATE)),
        ("a reading is never both blocking and indeterminate",
         all(verdict(d, o)[0] in FAILING or verdict(d, o)[0] in INDETERMINATE
             or verdict(d, o)[0] == "MIGRATED"
             for d, o in [({}, full), (full, {}), ({}, {}), (None, None), ({"p1": 1}, full)])),
        ("every verdict carries a non-empty reason",
         all(verdict(d, o)[1].strip()
             for d, o in [({}, full), (full, {}), ({}, {}), (None, None), ({"p1": 1}, full)])),
    ]
    for label, ok in checks:
        failures += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {label}")

    print(chr(10) + "  all checks passed" if not failures else chr(10) + f"  {failures} FAILED")
    return 1 if failures else 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--declared", default="age",
                    help="the backend the deployment DECLARES (for the message only)")
    ap.add_argument("--declared-census", help="JSON: project_id -> node count, declared store")
    ap.add_argument("--other-census", help="JSON: project_id -> node count, the other store")
    args = ap.parse_args(argv)

    if args.selftest:
        return _selftest()

    got, why = verdict(_load(args.declared_census), _load(args.other_census))
    if got in FAILING:
        print(f"[graph-store-migrated-gate] FAIL — {got}: {why}")
        print(f"  the deployment declares `{args.declared}`. Flipping the variable moves every "
              f"graph read to that store;\n  it does not move the data. Run the migration "
              f"(`python -m app.db.migrations.neo4j_to_age`) or\n  change the declaration.")
        return 1
    label = "INDETERMINATE" if got in INDETERMINATE else "OK"
    print(f"[graph-store-migrated-gate] {label} — {got}: {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
