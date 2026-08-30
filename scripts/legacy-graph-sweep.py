#!/usr/bin/env python3
"""legacy-graph-sweep — census (and, on request, removal) of the pre-migration `g_<hex>` graphs.

WHAT THESE ARE, MEASURED RATHER THAN ASSUMED
---------------------------------------------
The declared deployment reads ONE graph, `g_shared`, keyed by `project_id` (§8.1). Beside it
on `lw-iso` sat **4355** per-project `g_<hex>` graphs, carried in the leftovers plan as
"pre-migration shape … isolated-stack residue".

Residue is right; pre-migration is not. Their contents say what they are:

    ["Entity"] {"name": "Kai", "user_id": "u-e3cb628932f4", "project_id": "p-e3cb628932f4"}
    ["Fact"]   {"content": "an outer disciple", …}

`u-…`/`p-…` are SYNTHETIC ids — not UUIDs — and "Kai / an outer disciple" is this repo's
standard integration fixture. Each test run creates a throwaway graph and never drops it. A
sample of 120 (seeded, reproducible): **109 synthetic, 11 empty, 0 real UUID project ids.**

⚠️ **A SAMPLE IS NOT A LICENCE TO DROP 4355 GRAPHS.** So the sweep classifies EVERY graph and
removes only the ones it can prove are safe — a graph holding a real UUID `project_id` is
KEPT and NAMED. Fail-safe by construction: the unclassifiable outcome is "keep", never "drop".

THE COST OF LEAVING THEM, ALSO MEASURED
----------------------------------------
68 MB is the boring half. The sharp half: a single ordinary maintenance query across them
**exceeds `max_locks_per_transaction`** —

    ERROR: out of shared memory
    HINT:  You might need to increase "max_locks_per_transaction".

so counting rows in one statement is impossible and this file batches. 4355 schemas is a
number at which routine DBA work starts failing, which is a better argument for the sweep
than disk.

    python scripts/legacy-graph-sweep.py             # census only — NEVER drops
    python scripts/legacy-graph-sweep.py --drop      # drop the proven-safe ones
    python scripts/legacy-graph-sweep.py --selftest

🔴 **`--drop` REFUSES ANY TARGET THAT IS NOT THE ISOLATED STACK.** The leftovers row is
explicit — *"iso only. Dropping a graph on the dev store is not authorised by this row"* — and
a destructive default is how a `DELETE FROM books` once wiped a real library here. The port
and database must both match `lw-iso`'s, and the check is a refusal rather than a warning.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

#: A real project id. Anything else — `p-e3cb628932f4`, an empty graph — is fixture residue.
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

#: The fixture shape the integration suites mint: `p-<hex>` / `u-<hex>`. A graph is droppable
#: only when EVERY id it holds matches this — "not a UUID" is not the same claim, and treating
#: it as one would make an id format nobody has invented yet into residue.
SYNTHETIC_RE = re.compile(r"^[pu]-[0-9a-f]{6,}$", re.I)

#: The ONLY target `--drop` will touch. Not configurable on purpose: a flag that lets a
#: caller point this at the dev store is the flag that gets passed by accident at 2am.
ISO_PORT, ISO_DB = 25556, "loreweave_knowledge_vectors"

#: The project REGISTRY lives on the other iso database, not beside the graphs.
#: Reading the wrong one returns empty and would make the whole store droppable.
REG_PORT, REG_DB = 25555, "loreweave_knowledge"

#: The graph the deployment actually reads. Never a candidate.
KEEP = "g_shared"

#: Schemas per batch. A single statement over 4355 exhausts the lock table (see the module
#: docstring); this is well under it and still only a handful of round trips.
BATCH = 200


def psql(sql: str, *, port: int, db: str) -> tuple[str, int]:
    r = subprocess.run(
        ["psql", "-h", "localhost", "-p", str(port), "-U", "loreweave", "-d", db,
         "-At", "-F", "|", "-c", sql],
        capture_output=True, text=True, encoding="utf-8",
        env={**os.environ, "PGPASSWORD": os.environ.get("PGPASSWORD", "loreweave_dev")})
    return r.stdout.strip(), r.returncode


def classify(project_ids: set[str], registered: set[str]) -> str:
    """`real` | `synthetic` | `empty` — and `real` is the only one that is kept.

    🔴 **THE REGISTRY IS THE AUTHORITY, NOT A PATTERN.** The first two versions of this
    guessed from the id's SHAPE, and both were wrong in a way a sample could not show:

      * `p-<hex>` only          -> called `p-inject` and `p-0e3d1764591e-second` REAL,
                                   because they are fixture ids that do not match the regex.
      * "anything not a UUID"   -> would have called an id format nobody has invented yet
                                   residue, and dropped it.

    `knowledge_projects` answers the actual question — *is this a project the product knows
    about?* — as a fact. 472 rows; `p-inject` is not one of them and
    `019fefde-2f6b-7017-87de-c6b390a170c3` is.

    The bias stays: an id NOT in the registry is only residue when the registry was read
    successfully. `census` refuses outright rather than treating an unreadable registry as
    "nothing is registered", which would classify the entire store as droppable.
    """
    ids = {p for p in project_ids if p and p != "null"}
    if not ids:
        return "empty"
    return "real" if any(p in registered for p in ids) else "synthetic"


def registered_projects(*, port: int, db: str) -> set[str]:
    """Every project id the product knows about. REFUSES rather than returning an empty set.

    An empty registry and an unreachable one look identical to a caller that only checks the
    length — and here they differ by 4213 graphs.
    """
    rows, rc = psql("SELECT project_id::text FROM knowledge_projects", port=port, db=db)
    if rc != 0:
        raise SystemExit("[legacy-graph-sweep] REFUSED — could not read knowledge_projects "
                         "on " + f"{db}:{port}" + ". Without the registry every graph looks "
                         "like residue:" + chr(10) + "  " + rows[:300])
    ids = {r.strip() for r in rows.split(chr(10)) if r.strip()}
    if not ids:
        raise SystemExit("[legacy-graph-sweep] REFUSED — the registry is EMPTY. That is "
                         "indistinguishable from a broken query, and it would classify "
                         "every graph in the store as droppable.")
    return ids


def census(*, port: int, db: str, registered: set[str]) -> dict[str, list[str]]:
    names, rc = psql(
        "SELECT n.nspname FROM pg_namespace n JOIN ag_catalog.ag_graph g ON g.name=n.nspname "
        f"WHERE g.name <> '{KEEP}' ORDER BY n.nspname", port=port, db=db)
    if rc != 0:
        raise SystemExit("[legacy-graph-sweep] REFUSED — could not list graphs:\n  " + names[:300])
    graphs = [n for n in names.split("\n") if n.strip()]
    out: dict[str, list[str]] = {"real": [], "synthetic": [], "empty": []}
    for i in range(0, len(graphs), BATCH):
        for g in graphs[i:i + BATCH]:
            rows, rc = psql(
                "LOAD 'age'; SET search_path = ag_catalog, public; "
                f"SELECT * FROM cypher('{g}', $$ MATCH (n) RETURN n.project_id $$) AS (p agtype);",
                port=port, db=db)
            if rc != 0:
                # A graph this cannot read is KEPT, and said out loud. Silently treating an
                # error as "empty" would drop exactly the graphs that are hardest to inspect.
                out["real"].append(g)
                continue
            vals = {v.strip().strip('"') for v in rows.split("\n")[2:] if v.strip()}
            out[classify(vals, registered)].append(g)
    return out


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--drop", action="store_true",
                    help="drop the proven-safe graphs. lw-iso ONLY; refuses anything else.")
    ap.add_argument("--port", type=int, default=ISO_PORT)
    ap.add_argument("--db", default=ISO_DB)
    ap.add_argument("--reg-port", type=int, default=REG_PORT)
    ap.add_argument("--reg-db", default=REG_DB)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()

    # 🔴 THE TARGET GUARD RUNS FIRST, BEFORE A SINGLE QUERY.
    #
    # It used to sit just above the DROP loop, after the census — and biting it proved
    # nothing: pointed at the dev store, the census failed to connect and the script exited
    # on "the store did not answer" while the guard never executed. A defence positioned
    # after the thing that fails first is a defence nobody has run.
    #
    # Fail-fast is also the honest order: refusing an unauthorised target should not require
    # 4355 successful queries against it first.
    if args.drop and (args.port, args.db) != (ISO_PORT, ISO_DB):
        raise SystemExit(
            f"[legacy-graph-sweep] REFUSED — --drop targets {args.db} on {args.port}, and the "
            f"only authorised target is the isolated stack ({ISO_DB} on {ISO_PORT}). The "
            f"leftovers row L7 says iso only; a DROP on the dev store is never authorised.")

    before, rc = psql("SELECT count(*) FROM ag_catalog.ag_graph", port=args.port, db=args.db)
    if rc != 0:
        raise SystemExit("[legacy-graph-sweep] REFUSED — the store did not answer:\n  " + before[:300])
    print(f"[legacy-graph-sweep] graphs BEFORE: {before}  (including {KEEP})")

    registered = registered_projects(port=args.reg_port, db=args.reg_db)
    print(f"  registry: {len(registered)} project(s) known to the product")
    buckets = census(port=args.port, db=args.db, registered=registered)
    print(f"  real project data (KEPT)  : {len(buckets['real'])}")
    print(f"  synthetic fixture ids     : {len(buckets['synthetic'])}")
    print(f"  empty                     : {len(buckets['empty'])}")
    for g in buckets["real"][:10]:
        print(f"    KEPT: {g}")

    droppable = buckets["synthetic"] + buckets["empty"]
    if not args.drop:
        print(f"\n[legacy-graph-sweep] census only — {len(droppable)} graph(s) would be "
              f"dropped by --drop. Nothing was changed.")
        return 0

    # 🔴 A DROP THAT FAILS MUST BE LOUD. The first version wrote
    # `dropped += 1 if rc == 0 else 0` and checked only `after == before - dropped` — so when
    # every single drop failed, `dropped` was 0, the arithmetic held (4356 == 4356 - 0) and
    # the script printed its summary and exited **0** having done nothing at all. Silent
    # success is a bug, not an environment problem, and it was mine.
    #
    # The cause was mundane: `drop_graph` lives in `ag_catalog` and the extension must be
    # loaded, so the bare call raised `function drop_graph(unknown, boolean) does not exist`
    # for all 4355. The reporting defect is the one worth the comment.
    dropped, failed = 0, []
    for i in range(0, len(droppable), BATCH):
        for g in droppable[i:i + BATCH]:
            out, rc = psql(
                "LOAD 'age'; SET search_path = ag_catalog, public; "
                f"SELECT drop_graph('{g}', true)", port=args.port, db=args.db)
            if rc == 0:
                dropped += 1
            else:
                failed.append((g, out.strip().split(chr(10))[0][:120]))

    after, _ = psql("SELECT count(*) FROM ag_catalog.ag_graph", port=args.port, db=args.db)
    print(f"{chr(10)}[legacy-graph-sweep] dropped {dropped} of {len(droppable)}; "
          f"graphs AFTER: {after}")

    if failed:
        print(f"[legacy-graph-sweep] FAIL — {len(failed)} drop(s) FAILED. A sweep that "
              f"removes nothing must not report success:")
        for g, why in failed[:5]:
            print(f"    {g}: {why}")
        return 1
    if int(after) != int(before) - dropped:
        print(f"[legacy-graph-sweep] FAIL — after ({after}) is not before ({before}) minus "
              f"dropped ({dropped}). Something else changed the graph list during the sweep.")
        return 1
    if dropped == 0 and droppable:
        print("[legacy-graph-sweep] FAIL — there were graphs to drop and none was dropped.")
        return 1
    return 0


def selftest() -> int:
    fails = []

    def check(name, ok, got=None):
        print(f"  {'ok  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -> {got}"))
        if not ok:
            fails.append(name)

    REG = {"019fefde-2f6b-7017-87de-c6b390a170c3", "0051bb79-6fec-434a-9549-7c3d897f4941"}

    check("a project the REGISTRY knows is real",
          classify({"019fefde-2f6b-7017-87de-c6b390a170c3"}, REG) == "real")
    check("a fixture id the registry does not know is residue",
          classify({"p-e3cb628932f4"}, REG) == "synthetic")
    check("no ids at all is EMPTY", classify(set(), REG) == "empty")
    check("a literal 'null' is not an id", classify({"null"}, REG) == "empty")

    # THE CASE THAT KILLED TWO EARLIER CLASSIFIERS. `p-inject` and
    # `p-0e3d1764591e-second` are fixture ids that no id-SHAPE rule got right: a
    # `p-<hex>` regex called them real, and "anything not a UUID" would have called a
    # future id format residue. The registry answers without guessing.
    check("`p-inject` is residue, though no id-shape rule could tell",
          classify({"p-inject"}, REG) == "synthetic")
    check("`p-…-second` likewise", classify({"p-0e3d1764591e-second"}, REG) == "synthetic")

    # The safety bias: ONE registered id among fixtures keeps the whole graph.
    check("one REGISTERED id among fixtures keeps the graph",
          classify({"p-abc", "019fefde-2f6b-7017-87de-c6b390a170c3"}, REG) == "real")

    # And the control that matters most: an EMPTY registry must never be usable, because
    # every graph would classify as residue and the sweep would drop the store.
    check("with an empty registry, a REAL project would look like residue",
          classify({"019fefde-2f6b-7017-87de-c6b390a170c3"}, set()) == "synthetic",
          "…which is why registered_projects() REFUSES an empty result rather than "
          "returning one")

    check("g_shared is never a candidate", KEEP == "g_shared")
    check("the drop target is not configurable to the dev store",
          (ISO_PORT, ISO_DB) == (25556, "loreweave_knowledge_vectors"))
    check("the registry is read from the OTHER iso database",
          (REG_PORT, REG_DB) == (25555, "loreweave_knowledge"))

    print(f"\nlegacy-graph-sweep --selftest: {'OK' if not fails else 'FAILED'} "
          f"(11 cases, 5 of them negative)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
