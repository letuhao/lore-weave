#!/usr/bin/env python3
"""events_allowlist.yaml integrity — rule 2 of outbox-event-emit-lint.

Split out because the check is a YAML walk and bash is the wrong tool for it;
the shell gate calls this and folds the result into its own verdict.

This is the leg both headers claimed and neither had. What it checks, stated
exactly rather than aspirationally:

  * every `table:` has a CREATE TABLE in migrations/meta or the per-reality set
  * every `event_name` is unique across the file (two tables claiming one event
    is an outbox routing collision)
  * every `op` is INSERT / UPDATE / DELETE
  * no duplicate `table:` rows
  * the file declares at least one entry — an empty allowlist would satisfy
    every rule above while permitting nothing, which is the vacuous pass

What it deliberately does NOT check: the `owner:` field. Measured 2026-08-12,
13 of its 18 distinct values are prose ("admin-cli (cycle 36)", "shard health
agent (per-shard sidecar; cycle TBD L7)"), so an owner→service arm would report
documentation as drift. The service-map derivation the headers describe needs a
machine-readable emits column that does not exist — GT-OUTBOX-SERVICEMAP.

Exit 0 clean · 1 violations · 2 cannot run (missing/unparseable/empty).
"""
from __future__ import annotations

import collections
import os
import re
import subprocess
import sys


#: Measured 2026-08-12: 5 of 18 distinct `owner:` values name a real
#: `services/<name>` directory; the other 13 are prose. Named so the ratchet
#: above can move in both directions and say WHICH owner changed.
#: Overridable so the self-test's synthetic trees can drive the ratchet. Their
#: `services/` dirs do not contain the real owners, so the production default
#: made every unrelated probe red -- a new rule firing inside cases that are
#: about something else, which is the fifth time this board has hit that shape.
#: `+x` (set) rather than truthiness: a probe asserting ZERO resolvable owners
#: passes "0", and a truthiness test would hand it the production default.
OWNERS_RESOLVABLE = (int(os.environ["LW_OWNERS_RESOLVABLE"])
                     if "LW_OWNERS_RESOLVABLE" in os.environ else 5)
KNOWN_RESOLVABLE = (
    "auth-service", "migration-orchestrator", "publisher",
    "usage-billing-service", "world-service",
)


def declared_tables(root: str) -> set[str]:
    dirs = [os.path.join(root, "migrations", "meta"),
            os.path.join(root, "contracts", "migrations", "per_reality")]
    dirs = [d for d in dirs if os.path.isdir(d)]
    if not dirs:
        return set()
    out = subprocess.run(
        ["grep", "-rhoiE", "CREATE TABLE +(IF NOT EXISTS +)?[a-z_][a-z0-9_]*", *dirs],
        capture_output=True, text=True).stdout
    return {re.sub(r"(?i).*create table +(if not exists +)?", "", ln).strip()
            for ln in out.splitlines() if ln.strip()}


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: allowlist.py <events_allowlist.yaml> <repo_root>", file=sys.stderr)
        return 2
    path, root = argv[0], argv[1]
    try:
        import yaml
    except ImportError:
        print("[outbox-emit] PyYAML not installed — cannot check the allowlist", file=sys.stderr)
        return 2
    try:
        with open(path, encoding="utf-8") as fh:
            doc = yaml.safe_load(fh) or {}
    except (OSError, yaml.YAMLError) as e:
        print(f"[outbox-emit] allowlist unreadable: {e}", file=sys.stderr)
        return 2

    entries = doc.get("entries")
    if not isinstance(entries, list) or not entries:
        print("[outbox-emit] allowlist has no `entries:` — an empty allowlist permits "
              "nothing while satisfying every rule below", file=sys.stderr)
        return 2

    known = declared_tables(root)
    if not known:
        print("[outbox-emit] found 0 CREATE TABLE statements — the migration trees are "
              "missing or renamed, so the table check would pass over nothing", file=sys.stderr)
        return 2

    problems: list[str] = []
    seen_tables = collections.Counter()
    seen_events = collections.Counter()
    n_events = 0

    for i, row in enumerate(entries):
        if not isinstance(row, dict):
            problems.append(f"entries[{i}] is not a mapping")
            continue
        table = row.get("table")
        if not table:
            problems.append(f"entries[{i}] has no `table:`")
        else:
            seen_tables[str(table)] += 1
            if str(table) not in known:
                problems.append(
                    f"table {table!r} has no CREATE TABLE in the migrations — the allowlist "
                    f"permits writes to something that does not exist")
        for ev in (row.get("events") or []):
            n_events += 1
            if not isinstance(ev, dict):
                problems.append(f"{table}: an events entry is not a mapping")
                continue
            op = ev.get("op")
            if op not in ("INSERT", "UPDATE", "DELETE"):
                problems.append(f"{table}: op {op!r} is not INSERT/UPDATE/DELETE")
            name = ev.get("event_name")
            if not name:
                problems.append(f"{table}: an events entry has no `event_name`")
            else:
                seen_events[str(name)] += 1

    for t, n in sorted(seen_tables.items()):
        if n > 1:
            problems.append(f"table {t!r} appears in {n} entries — one row per table")
    for name, n in sorted(seen_events.items()):
        if n > 1:
            problems.append(f"event_name {name!r} is claimed by {n} entries — an outbox "
                            f"routing collision")

    # ── the MECHANISM for GT-OUTBOX-SERVICEMAP (a ratchet, both directions) ──
    # See the module docstring. `OWNERS_RESOLVABLE` is the measured share of
    # `owner:` values naming a real `services/<name>` directory; the rest are
    # prose. The derivation both headers advertise is only buildable when that
    # number is high, so it is the honest wake-up signal for the row.
    owners = sorted({str(e.get("owner", "")).strip()
                     for e in entries if isinstance(e, dict) and e.get("owner")})
    resolvable = sorted(o for o in owners
                        if os.path.isdir(os.path.join(root, "services", o)))
    if len(resolvable) > OWNERS_RESOLVABLE:
        problems.append(
            f"GT-OUTBOX-SERVICEMAP may be DISCHARGEABLE: {len(resolvable)} of {len(owners)} "
            f"`owner:` values now name a real services/ dir (was {OWNERS_RESOLVABLE}). "
            f"If owners are machine-resolvable, build the derivation the headers promise and "
            f"delete the row — then raise OWNERS_RESOLVABLE. New: "
            f"{sorted(set(resolvable) - set(KNOWN_RESOLVABLE))}")
    elif len(resolvable) < OWNERS_RESOLVABLE:
        problems.append(
            f"an `owner:` that used to name a real service no longer does "
            f"({len(resolvable)} of {len(owners)}, was {OWNERS_RESOLVABLE}). The allowlist is "
            f"decaying toward prose, which is what makes the cross-check underivable. Gone: "
            f"{sorted(set(KNOWN_RESOLVABLE) - set(resolvable))}")

    if problems:
        print("[outbox-emit] FAIL — events_allowlist.yaml integrity:")
        for p in problems:
            print(f"    {p}")
        return 1

    print(f"[outbox-emit] allowlist ok — {len(entries)} table(s), {n_events} event(s), "
          f"checked against {len(known)} declared table(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
