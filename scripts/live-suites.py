#!/usr/bin/env python3
"""`DFO-6` — run the live Rust suites, one database each.

`cargo test --workspace` against ONE database is a trap: `rebuilder_live`
applies `0002`, which DROPs `events` and takes `content_sha256`, the channel
columns, `ruleset_digest` and the turn counters with it. Every suite that runs
after it fails against a schema someone else dropped, and those failures read
like code defects. Measured once as *"2505 passed / 1 failed"* and once as six
channel failures that were nothing of the kind.

This reads `contracts/testing/live-suites.yaml`, gives every backing store its
OWN database, applies the schema each suite declares, and runs the suites one
at a time.

    python scripts/live-suites.py --list
    python scripts/live-suites.py                    # everything runnable here
    python scripts/live-suites.py --only world-rebuilder commit-dataflow
    python scripts/live-suites.py --filter dp-kernel

Endpoints come from the environment, defaulting to the dev compose stack:
`LS_PG_CONTAINER`, `LS_PG_HOSTPORT`, `LS_PG_USER`, `LS_PG_PASSWORD`,
`LS_REDIS_URL`.

Exit 0 iff every suite it ran passed. A suite it could not run is reported and
does NOT count as a pass — the whole point of this file is that a green line
should mean something happened.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# How a live suite announces that it did nothing. TWO spellings, because the
# tree already has two: 16 suites write `SKIP …` and the five dp-kernel ones
# write `[skip] …`. Accepting both beats churning five files to make a log
# prefix uniform — but a suite with NEITHER is invisible to this runner, so
# `live-suite-registry-gate.py` requires one of them in every registered target.
SKIP_LINE = re.compile(r"\s*(SKIP\b|\[skip\])", re.IGNORECASE)

REPO = Path(__file__).resolve().parent.parent
REGISTRY = REPO / "contracts" / "testing" / "live-suites.yaml"

# DEFAULTS TO THE pgvector POSTGRES, and that is not a preference.
#
# `0006_projections` declares `VECTOR(1536)`. On a stock image the extension is
# absent, the migration dies, and FOUR suites fail with an error that has
# nothing to do with their subject. Measured: against `infra-postgres-1`
# (postgres:18-alpine) world-embedding / replay-aggregate / rebuilder /
# provisioner-reentry all failed on `could not access file "vector"`; against
# `infra-knowledge-pg-1` (loreweave/postgres-knowledge:18, pgvector 0.8.6) all
# four passed, unchanged. This is `DFO-6`'s own cause (a), and it cost the
# previous run three wrongly eliminated hypotheses.
PG_CONTAINER = os.environ.get("LS_PG_CONTAINER", "infra-knowledge-pg-1")
PG_HOSTPORT = os.environ.get("LS_PG_HOSTPORT", "localhost:5556")
PG_USER = os.environ.get("LS_PG_USER", "loreweave")
PG_PASSWORD = os.environ.get("LS_PG_PASSWORD", "loreweave_dev")
REDIS_URL = os.environ.get("LS_REDIS_URL", "redis://127.0.0.1:6399/0")

SCHEMA_DIRS = {
    "per_reality": REPO / "contracts" / "migrations" / "per_reality",
    "meta": REPO / "migrations" / "meta",
}
THROWAWAY_MARKERS = ("test", "smoke", "scratch", "throwaway", "sandbox")


def slug(env: str) -> str:
    s = env.lower()
    for cut in ("loreweave_test_", "_test_database_url", "_url"):
        s = s.replace(cut, "")
    return s.strip("_") or "db"


def dev_db(suite_id: str, env: str) -> str:
    return f"ls_{suite_id.replace('-', '_')}_{slug(env)}_smoke"


def psql(db: str, *args: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    cmd = ["docker", "exec"]
    if stdin is not None:
        cmd.append("-i")
    cmd += [PG_CONTAINER, "psql", "-U", PG_USER, "-d", db, "-v", "ON_ERROR_STOP=1", "-q", *args]
    return subprocess.run(cmd, input=stdin, capture_output=True)


def provision(db: str, schema: str) -> list[str]:
    """Drop, create, migrate. Returns the migrations that did NOT apply.

    A failed migration is RETURNED, never swallowed. Two of the per-reality set
    need pgvector, which no local postgres image here carries — that is
    `DFO-6`'s own cause (a), and a runner that hid it would reproduce the bug it
    exists to fix.
    """
    if not any(m in db for m in THROWAWAY_MARKERS):
        raise SystemExit(f"REFUSING to create `{db}`: it carries no throwaway marker")
    subprocess.run(
        ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", "postgres", "-q",
         "-c", f"DROP DATABASE IF EXISTS {db}", "-c", f"CREATE DATABASE {db}"],
        capture_output=True, check=True,
    )
    if schema in ("self", "none"):
        return []
    d = SCHEMA_DIRS[schema]
    failed = []
    for f in sorted(d.glob("*.up.sql")):
        r = psql(db, stdin=f.read_bytes())
        if r.returncode != 0:
            first = (r.stderr.decode(errors="replace").strip().splitlines() or [""])[0]
            failed.append(f"{f.name}: {first[:90]}")
    if schema == "per_reality":
        # `events` is RANGE-partitioned on `recorded_at` and the migrations
        # create only dated partitions. A live suite appends whatever timestamp
        # its fixture chose, so without a catch-all every append dies with
        # `no partition of relation "events" found for row` — measured here as
        # 6 of 9 failures in `integration_channel_writer`, which reads like a
        # writer-fencing bug and is not one.
        #
        # This is HARNESS setup, not schema: production creates real monthly
        # partitions. `foundation-ci.yml` does the same thing for its own
        # dp_kernel_test leg, and this is that step, applied uniformly.
        r = psql(db, "-c", "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT")
        if r.returncode != 0:
            first = (r.stderr.decode(errors="replace").strip().splitlines() or [""])[0]
            failed.append(f"events_p_default: {first[:90]}")
    return failed


def first_failure_reason(stdout: list[str], stderr: list[str]) -> str:
    """The first thing cargo said about WHY, not how many.

    Panics carry their message on the line after `panicked at <loc>:`; a build
    failure never reaches a panic at all and lives on stderr. Both are covered,
    because a suite that did not compile reports `0 passed` exactly like a suite
    whose assertion failed, and reading the first as the second is the
    wrong-reason red this repo keeps paying for.
    """
    for i, ln in enumerate(stdout):
        if "panicked at" in ln:
            msg = stdout[i + 1].strip() if i + 1 < len(stdout) else ""
            return (msg or ln.strip())[:400]
    # A `#[test] -> Result` that returns Err prints `Error: …` and never
    # panics. Missing this shape reported `declared_verb_live` as having no
    # reason at all, which sent the diagnosis back to running it by hand.
    for ln in stdout:
        if ln.startswith("Error:"):
            return ln.strip()[:400]
    for ln in stderr:
        if ln.startswith("error") or "error[" in ln:
            return f"BUILD/RUN: {ln.strip()[:380]}"
    return ""


def plan(suites: list[dict]) -> list[tuple[dict, dict[str, str], list[str]]]:
    out = []
    for s in suites:
        env: dict[str, str] = {}
        dbs: list[str] = []
        for n in s["needs"]:
            if n["kind"] == "redis":
                env[n["env"]] = REDIS_URL
            elif n["kind"] == "postgres-admin":
                env[n["env"]] = f"postgres://{PG_USER}:{PG_PASSWORD}@{PG_HOSTPORT}/postgres"
            else:
                db = dev_db(s["id"], n["env"])
                env[n["env"]] = f"postgres://{PG_USER}:{PG_PASSWORD}@{PG_HOSTPORT}/{db}"
                dbs.append(db)
        out.append((s, env, dbs))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--list", action="store_true", help="print the plan and stop")
    ap.add_argument("--only", nargs="*", default=None, help="run these suite ids")
    ap.add_argument("--filter", default=None, help="run suites whose id contains this")
    args = ap.parse_args()

    try:
        import yaml
    except ImportError:
        print("pyyaml is not installed", file=sys.stderr)
        return 2
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    suites = reg["suites"]
    if args.only:
        suites = [s for s in suites if s["id"] in args.only]
    if args.filter:
        suites = [s for s in suites if args.filter in s["id"]]
    if not suites:
        print("no suite matched — `--list` shows the ids", file=sys.stderr)
        return 2

    planned = plan(suites)

    if not args.list:
        # PREFLIGHT. Say what this endpoint cannot do BEFORE running anything,
        # so a pgvector failure is never read as a defect in the suite that
        # tripped over it. Silence here is how "environmental" became a habit.
        probe = subprocess.run(
            ["docker", "exec", PG_CONTAINER, "psql", "-U", PG_USER, "-d", "postgres", "-tAc",
             "SELECT 1 FROM pg_available_extensions WHERE name='vector'"],
            capture_output=True, text=True,
        )
        if probe.returncode != 0:
            print(f"cannot reach postgres in `{PG_CONTAINER}`: "
                  f"{probe.stderr.strip().splitlines()[-1] if probe.stderr.strip() else '?'}",
                  file=sys.stderr)
            return 2
        if probe.stdout.strip() != "1":
            print(
                f"!! `{PG_CONTAINER}` has NO pgvector. `0006_projections` declares VECTOR(1536),\n"
                f"   so it will not apply and any suite needing a projection table will fail for\n"
                f"   THAT reason and not its own. Point LS_PG_CONTAINER / LS_PG_HOSTPORT at an\n"
                f"   image that has it (loreweave/postgres-knowledge:18 does).\n",
                file=sys.stderr,
            )

    if args.list:
        for s, env, dbs in planned:
            ci = "CI" if s.get("ci") else "  "
            print(f"{ci} {s['id']:28s} -p {s['package']} --test {s['target']}")
            for k, v in env.items():
                print(f"       {k} = {v.rsplit('/', 1)[-1] if 'postgres://' in v else v}")
        print(f"\n{len(planned)} suite(s); {sum(len(d) for _, _, d in planned)} database(s)")
        return 0

    results: list[tuple[str, str, str]] = []
    for s, env, _dbs in planned:
        sid = s["id"]
        print(f"\n=== {sid} ===", flush=True)
        skipped_migrations: list[str] = []
        try:
            for n in s["needs"]:
                if n["kind"] in ("redis", "postgres-admin"):
                    continue
                db = dev_db(sid, n["env"])
                bad = provision(db, n["schema"])
                if bad:
                    skipped_migrations += [f"{db}: {b}" for b in bad]
        except subprocess.CalledProcessError as e:
            results.append((sid, "SETUP-FAILED", e.stderr.decode(errors="replace")[:160]))
            print(f"  setup failed: {e}", flush=True)
            continue

        for m in skipped_migrations:
            print(f"  !! migration did not apply — {m}", flush=True)

        cmd = ["cargo", "test", "-p", s["package"]]
        if s.get("features"):
            cmd += ["--features", ",".join(s["features"])]
        # `--nocapture`, and it is load-bearing rather than verbose.
        #
        # cargo swallows a PASSING test's output entirely. Every live suite in
        # this tree announces its skip with `eprintln!("SKIP …")` from a test
        # that then returns Ok — so without this the announcement never leaves
        # the harness and the runner cannot tell "ran" from "did nothing".
        # Measured: the bite (misname a suite's env var, watch the verdict) came
        # back PASS twice — once before scanning stderr, and AGAIN after, which
        # is what proved the stream was never the cause.
        cmd += ["--test", s["target"], "--", "--nocapture"]
        r = subprocess.run(cmd, cwd=REPO, env={**os.environ, **env},
                           capture_output=True, text=True)
        out = r.stdout.splitlines()
        err = r.stderr.splitlines()
        tail = [ln for ln in out if ln.startswith(("test result:", "SKIP", "running"))]
        for ln in tail:
            print(f"  {ln}", flush=True)

        # BOTH streams. This read stdout only, and every suite in the tree
        # announces its skip with `eprintln!` — so the detection was dead on
        # arrival and the runner called a suite that did nothing a PASS. Caught
        # by biting it (rename a suite's env var in the registry, watch the
        # verdict): it stayed PASS. The comment below was already written,
        # warning about exactly this, before the code that defeated it.
        skipped = any(SKIP_LINE.match(ln) for ln in out + err)
        verdict = "PASS" if r.returncode == 0 else "FAIL"
        if verdict == "PASS" and skipped:
            verdict = "SKIPPED"

        # A COUNT IS NOT A REASON — the same lesson `DFO-8` cost three wrongly
        # eliminated hypotheses to learn. `test result: FAILED. 0 passed; 4
        # failed` tells an operator nothing they can act on, and the panic
        # message was in this buffer the whole time.
        detail = "; ".join(tail[-1:])
        if verdict == "FAIL":
            why = first_failure_reason(out, r.stderr.splitlines())
            detail = why or detail
            print(f"  WHY: {why}", flush=True)
        results.append((sid, verdict, detail))

    print("\n" + "=" * 78)
    width = max(len(r[0]) for r in results)
    for sid, verdict, detail in results:
        print(f"{verdict:12s} {sid:{width}s}  {detail[:90]}")
    failed = [r for r in results if r[1] not in ("PASS",)]
    passed = len(results) - len(failed)
    print(f"\n{passed} passed, {len(failed)} not-passed, of {len(results)} suite(s)")
    # A SKIPPED suite is NOT a pass. The single most likely way this file could
    # lie is by running every suite with the wrong variable set and reporting a
    # clean sweep of skips.
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
