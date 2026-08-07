#!/usr/bin/env python3
"""migration-manifest-gate — a migration file the orchestrator never applies.

THE INCIDENT, measured 2026-08-08 (`1b7gap-H1`)
-----------------------------------------------
`contracts/migrations/manifest.yaml` is the ordered list the migration
orchestrator applies. It ended at `0013`. Six migrations — `0014` through
`0019` — had shipped since, and **not one was registered**, so the orchestrator
had been applying an eight-month-old schema: the writer lease, the ruleset
digest, both projection drops and the whole `channels` registry could not exist
in a real per-reality database. `0019_channels` in particular was written,
reviewed, live-smoked 46 times, gated pre-commit, and **applied by nothing**.

The part that makes this a gate rather than a fix: **the gap was already
tracked.** A comment in the manifest names `D-MANIFEST-0009-0012-UNREGISTERED`
and explains that four files are deliberately unregistered. Six more drifted
straight past that row while it sat there. That is the project's own lesson in
its purest form — *intent is not a mechanism*, and a row that describes a hole
does not notice the hole getting bigger.

WHAT IT CHECKS
--------------
  R1  every `per_reality/<id>.up.sql` has a manifest entry, or an `UNREGISTERED`
      row below stating WHY and what would wake it up
  R2  every manifest entry names a file that exists (the phantom direction —
      an entry for a deleted migration makes the orchestrator fail at deploy)
  R3  every `.up.sql` has a matching `.down.sql`
  R4  versions strictly increase, and `dependencies` reference earlier ids
      (the orchestrator checks this at RUNTIME, which is too late to be a
      pre-commit signal; checking it here is cheap and catches the edit)
  R5  the `UNREGISTERED` list SHRINKS — an id that is now registered must lose
      its row, or this gate reds. An exclusion that outlives its reason is how
      `D-MANIFEST-0009-0012-UNREGISTERED` came to cover six files it never named.

Run: ``python scripts/migration-manifest-gate.py`` — wired pre-commit.
``--self-test`` runs the non-vacuity cases alone.
Exit 0 = every migration is accounted for; 1 = findings; 2 = misuse.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MANIFEST = REPO / "contracts/migrations/manifest.yaml"
MIGRATIONS = REPO / "contracts/migrations/per_reality"

# Deliberately unregistered, each with the reason and the trigger that would end
# it. This list must SHRINK. Adding a row is a decision; leaving one after the
# id is registered is a finding (R5).
UNREGISTERED = {
    "0009_canon_projection": "applied by the projection/test harnesses directly, not the "
                             "orchestrator's migrate path (D-MANIFEST-0009-0012-UNREGISTERED). "
                             "Wakes up when canon projection is provisioned per reality.",
    "0010_canon_projection_indexes": "see 0009 — same harness, same deferral row.",
    "0011_archive_state": "see 0009 — same harness, same deferral row.",
    "0012_events_outbox_prune_index": "see 0009 — same harness, same deferral row.",
}


def parse_manifest(text: str) -> list[dict]:
    """A tiny reader for the manifest's fixed shape.

    Deliberately not PyYAML: this gate runs pre-commit on every machine, and a
    gate that cannot run because a dependency is missing is a gate that gets
    removed. The shape is `- id: "x"` / `version: N` / `dependencies: [...]`,
    which is a stable contract stated in the manifest's own header.
    """
    out: list[dict] = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#"):
            continue
        m = re.match(r'-\s*id:\s*"([^"]+)"', s)
        if m:
            out.append({"id": m.group(1), "version": None, "dependencies": []})
            continue
        if not out:
            continue
        m = re.match(r"version:\s*(\d+)", s)
        if m:
            out[-1]["version"] = int(m.group(1))
        m = re.match(r"dependencies:\s*\[(.*)\]", s)
        if m:
            out[-1]["dependencies"] = re.findall(r'"([^"]+)"', m.group(1))
    return out


def check(manifest_text: str, on_disk: set[str],
          downs: set[str], unregistered: dict[str, str]) -> list[str]:
    findings: list[str] = []
    entries = parse_manifest(manifest_text)
    ids = [e["id"] for e in entries]

    if not entries:
        return ["MISUSE — no migration entries parsed out of the manifest. A comparison "
                "against nothing agrees with anything."]

    # R1 — a file with no entry and no reasoned exclusion.
    for stem in sorted(on_disk):
        if stem not in ids and stem not in unregistered:
            findings.append(
                f"R1 {stem}.up.sql exists and the orchestrator will never apply it — no manifest "
                f"entry, and no UNREGISTERED row saying why. This is the 1b7gap-H1 defect: six "
                f"migrations shipped unregistered while a comment tracked four.")

    # R2 — an entry naming a file that is not there.
    for stem in ids:
        if stem not in on_disk:
            findings.append(f"R2 the manifest declares `{stem}` and "
                            f"per_reality/{stem}.up.sql does not exist — the orchestrator will "
                            f"fail at deploy, not here.")

    # R3 — no down migration.
    for stem in sorted(on_disk):
        if stem not in downs:
            findings.append(f"R3 {stem}.up.sql has no {stem}.down.sql — nothing can reverse it.")

    # R4 — ordering, and dependencies that point forward or nowhere.
    seen: list[str] = []
    prev = None
    for e in entries:
        if e["version"] is None:
            findings.append(f"R4 `{e['id']}` has no version.")
        elif prev is not None and e["version"] <= prev:
            findings.append(f"R4 `{e['id']}` version {e['version']} does not exceed the previous "
                            f"entry's {prev}.")
        else:
            prev = e["version"]
        for dep in e["dependencies"]:
            if dep not in seen:
                findings.append(f"R4 `{e['id']}` depends on `{dep}`, which is not declared "
                                f"before it.")
        seen.append(e["id"])

    # R5 — the exclusion list must shrink.
    for stem in sorted(unregistered):
        if stem in ids:
            findings.append(f"R5 `{stem}` is UNREGISTERED here and IS in the manifest. The "
                            f"exclusion outlived its reason — delete the row.")
        elif stem not in on_disk:
            findings.append(f"R5 `{stem}` is UNREGISTERED here and has no file. Delete the row.")
    return findings


def self_test() -> int:
    bad = []
    good_manifest = (
        'migrations:\n'
        '  - id: "0001_initial"\n    version: 1\n    dependencies: []\n'
        '  - id: "0002_events"\n    version: 2\n    dependencies: ["0001_initial"]\n')
    disk = {"0001_initial", "0002_events"}
    downs = set(disk)

    if check(good_manifest, disk, downs, {}):
        bad.append(f"reds on a clean input: {check(good_manifest, disk, downs, {})}")

    cases = {
        "R1 a file with no entry (the actual 1b7gap-H1 defect)":
            (good_manifest, disk | {"0003_orphan"}, downs | {"0003_orphan"}, {}),
        "R2 an entry with no file":
            (good_manifest + '  - id: "0009_ghost"\n    version: 9\n    dependencies: []\n',
             disk, downs, {}),
        "R3 an up with no down":
            (good_manifest, disk, {"0001_initial"}, {}),
        "R4 a version that does not increase":
            (good_manifest.replace("version: 2", "version: 1"), disk, downs, {}),
        "R4 a dependency declared later":
            (good_manifest.replace('dependencies: []', 'dependencies: ["0002_events"]', 1),
             disk, downs, {}),
        "R5 an exclusion that is now registered":
            (good_manifest, disk, downs, {"0002_events": "stale reason"}),
        "R5 an exclusion whose file is gone":
            (good_manifest, disk, downs, {"0099_vanished": "stale reason"}),
    }
    for label, args in cases.items():
        if not check(*args):
            bad.append(f"BLIND to: {label}")

    # A file that IS excluded must NOT red — the exclusion has to work, or the
    # list is decoration and the next author deletes the gate instead.
    if check(good_manifest, disk | {"0004_harness"}, downs | {"0004_harness"},
             {"0004_harness": "applied by the harness"}):
        bad.append("a REASONED exclusion still reds — the escape hatch does not work")

    if bad:
        print("migration-manifest-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"migration-manifest-gate: SELF-TEST PASS — {len(cases)} case(s) each red (an "
          f"unregistered file, a phantom entry, a missing down, a non-increasing version, a "
          f"forward dependency, and an exclusion that outlived its reason), and a reasoned "
          f"exclusion does NOT red (non-vacuous in both directions)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    if self_test() != 0:
        return 2

    if not MANIFEST.is_file() or not MIGRATIONS.is_dir():
        print(f"migration-manifest-gate: MISUSE — {MANIFEST} or {MIGRATIONS} is absent",
              file=sys.stderr)
        return 2

    on_disk = {p.name[:-len(".up.sql")] for p in MIGRATIONS.glob("*.up.sql")}
    downs = {p.name[:-len(".down.sql")] for p in MIGRATIONS.glob("*.down.sql")}
    findings = check(MANIFEST.read_bytes().decode("utf-8"), on_disk, downs, UNREGISTERED)

    if findings:
        print(f"migration-manifest-gate: {len(findings)} finding(s)\n")
        for f in findings:
            print("  " + f)
        print("\nA migration the orchestrator never applies is a schema change that does not")
        print("happen. 0014-0019 shipped that way for months, past a comment that tracked four")
        print("other files by name -- a row is not a mechanism.")
        return 1

    registered = len(parse_manifest(MANIFEST.read_bytes().decode("utf-8")))
    print(f"migration-manifest-gate: OK — {len(on_disk)} migration(s) on disk, {registered} "
          f"registered, {len(UNREGISTERED)} deliberately excluded with a stated reason, every "
          f"up has a down, versions strictly increase and no dependency points forward")
    return 0


if __name__ == "__main__":
    sys.exit(main())
