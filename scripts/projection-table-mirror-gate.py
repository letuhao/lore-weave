#!/usr/bin/env python3
"""projection-table-mirror-gate — a list copied into four languages, checked in one.

THE DEFECT THIS EXISTS TO PREVENT
---------------------------------
The set of L3.A projection table names is written down FIVE times:

    contracts/migrations/per_reality/*.up.sql   the CHECK constraint  (SSOT #1)
    services/world-service/src/rebuild/mod.rs   PROJECTION_TABLES     (SSOT #2)
    services/admin-cli/.../projection_drift_check.go  allowedProjectionTables
    services/admin-cli/.../rebuild_projection.go      projectionTables
    services/integrity-checker/pkg/types/types.go     L3ATables
    services/integrity-checker/pkg/tablemap/...       specs (keys)
    contracts/integrity/config.yaml                   tables[].name

Each copy DECLARED itself a mirror in its own comment — "mirrors the CHECK
constraint", "Mirrors world_service::rebuild::PROJECTION_TABLES", "This MUST
match the projection_drift_table_name_allowlist CHECK". Exactly one of them had
a mechanism, and that mechanism read a SINGLE migration file, so when `0017`
narrowed the constraint from a DIFFERENT file the mirror test kept comparing
against `0007`'s ten names and stayed green.

Measured 2026-08-04, one day after `0017` shipped: FOUR of the copies still
named seven tables the database no longer had. One of them gates a
`TRUNCATE <table>`; one is a loaded production config that would have failed the
integrity-checker at startup. A comment saying "MUST match" is a claim. This is
the mechanism.

WHY A SCRIPT AND NOT THREE MORE UNIT TESTS
------------------------------------------
Because the defect is not in any one copy — it is in the RELATIONSHIP between
copies that no single language's test suite can see. A Go test cannot notice
that the Rust list moved; a Rust test cannot read the YAML. Adding a sixth copy
of the list to a sixth test would have been the same mistake once more.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

MIGRATION_DIR = REPO / "contracts" / "migrations" / "per_reality"
RUST_REBUILD = REPO / "services" / "world-service" / "src" / "rebuild" / "mod.rs"
GO_DRIFT = (REPO / "services" / "admin-cli" / "internal" / "commands"
            / "projection_drift_check.go")
GO_REBUILD = (REPO / "services" / "admin-cli" / "internal" / "commands"
              / "rebuild_projection.go")
GO_TYPES = (REPO / "services" / "integrity-checker" / "pkg" / "types" / "types.go")
GO_TABLEMAP = (REPO / "services" / "integrity-checker" / "pkg" / "tablemap"
               / "tablemap.go")
YAML_CONFIG = REPO / "contracts" / "integrity" / "config.yaml"

# Anchored on the constraint NAME. `0017` also contains
# `DELETE FROM projection_drift_state WHERE table_name IN (<the dropped seven>)`,
# and a pattern matching `table_name IN (` alone parses THAT and concludes the
# exact opposite of the truth. Rule R6 of the self-test holds this shut.
SQL_CONSTRAINT_RE = re.compile(
    r"ADD CONSTRAINT projection_drift_table_name_allowlist\s+"
    r"CHECK \(table_name IN \((.*?)\)\s*\)", re.S)
SQL_NAME_RE = re.compile(r"'([a-z_]+)'")


class LostSubject(Exception):
    """A source parsed to an EMPTY set.

    Raised rather than returned, because an empty set compares equal to another
    empty set: two mirrors that both failed to parse would agree perfectly and
    the gate would pass while reading nothing at all.
    """


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def _write(p: Path, text: str) -> None:
    """Write without newline translation.

    `Path.write_text` opens in text mode, so on Windows every `\\n` becomes
    `\\r\\n` — and the self-test writes a file, mutates it, and writes it BACK.
    Round-tripping through `write_text` therefore rewrites the line endings of
    every file the self-test touches, dirtying the working tree on a run that is
    supposed to leave no trace. Git normalises on commit so no content changes,
    which is exactly why it would have gone unnoticed.
    """
    with open(p, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def _names(where: str, found) -> set[str]:
    out = {m if isinstance(m, str) else m[0] for m in found}
    if not out:
        raise LostSubject(where)
    return out


def sql_effective() -> tuple[set[str], str]:
    """The constraint Postgres would be left holding after every migration."""
    body, src = None, ""
    for f in sorted(MIGRATION_DIR.glob("*.up.sql")):
        hits = SQL_CONSTRAINT_RE.findall(_read(f))
        if hits:
            body, src = hits[-1], f.name  # last in file, last file wins
    if body is None:
        raise LostSubject("SQL CHECK (no ADD CONSTRAINT found in any migration)")
    return _names(f"SQL CHECK ({src})", SQL_NAME_RE.findall(body)), src


def rust_projection_tables() -> set[str]:
    m = re.search(r"PROJECTION_TABLES: &\[&str\] = &\[(.*?)\];", _read(RUST_REBUILD), re.S)
    if not m:
        raise LostSubject("Rust PROJECTION_TABLES")
    return _names("Rust PROJECTION_TABLES", re.findall(r'"([a-z_]+)"', m.group(1)))


def _go_block(path: Path, decl: str, label: str, keys_only: bool = False) -> set[str]:
    m = re.search(re.escape(decl) + r"\{(.*?)\n\}", _read(path), re.S)
    if not m:
        raise LostSubject(label)
    # `keys_only` matters for tablemap.specs, whose VALUES are PK column names:
    # a blanket string scan there harvests `region_id`, `key`, `session_id` … and
    # reports each as a table the other mirrors are missing. Keys are anchored to
    # the start of a line so a column name can never be mistaken for one.
    pat = r'^\s*"([a-z_]+)":' if keys_only else r'"([a-z_]+)"'
    return _names(label, re.findall(pat, m.group(1), re.M))


def yaml_config_tables() -> set[str]:
    return _names("contracts/integrity/config.yaml",
                  re.findall(r"^\s*-\s*name:\s*([a-z_]+)\s*$", _read(YAML_CONFIG), re.M))


# Each row: (label, getter, relation, other-label, other-getter).
# `relation` is "==" (set equality) or "<=" (subset).
def _mirrors():
    sql = lambda: sql_effective()[0]  # noqa: E731
    return [
        ("admin-cli allowedProjectionTables",
         lambda: _go_block(GO_DRIFT, "var allowedProjectionTables = map[string]bool",
                           "admin-cli allowedProjectionTables"),
         "==", "the effective SQL CHECK", sql),
        ("integrity-checker types.L3ATables",
         lambda: _go_block(GO_TYPES, "var L3ATables = []string",
                           "integrity-checker types.L3ATables"),
         "==", "the effective SQL CHECK", sql),
        ("integrity-checker tablemap.specs",
         lambda: _go_block(GO_TABLEMAP, "var specs = map[string]TableSpec",
                           "integrity-checker tablemap.specs", keys_only=True),
         "==", "integrity-checker types.L3ATables",
         lambda: _go_block(GO_TYPES, "var L3ATables = []string",
                           "integrity-checker types.L3ATables")),
        ("contracts/integrity/config.yaml", yaml_config_tables,
         "<=", "integrity-checker types.L3ATables",
         lambda: _go_block(GO_TYPES, "var L3ATables = []string",
                           "integrity-checker types.L3ATables")),
        ("admin-cli projectionTables",
         lambda: _go_block(GO_REBUILD, "var projectionTables = map[string]struct{}",
                           "admin-cli projectionTables"),
         "==", "Rust PROJECTION_TABLES", rust_projection_tables),
    ]


def check() -> list[str]:
    findings: list[str] = []
    for label, get, rel, other_label, get_other in _mirrors():
        try:
            a, b = get(), get_other()
        except LostSubject as e:
            findings.append(
                f"  {e} parsed to NOTHING — the gate lost its subject. An empty set "
                f"agrees with every other empty set, so this is a failure, not a pass.")
            continue
        if rel == "==":
            for n in sorted(a - b):
                findings.append(f"  {label} has '{n}'; {other_label} does not")
            for n in sorted(b - a):
                findings.append(f"  {other_label} has '{n}'; {label} does not")
        else:
            for n in sorted(a - b):
                findings.append(f"  {label} names '{n}', which is not in {other_label}")
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test", action="store_true", help="prove every rule bites")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    findings = check()
    if findings:
        print(f"projection-table-mirror-gate: {len(findings)} finding(s)\n")
        print("\n".join(findings))
        print(
            "\nThe L3.A projection table list is written down in SQL, Rust, three Go\n"
            "declarations and a YAML config. Each copy's own comment calls itself a\n"
            "mirror. Change one, change them all — or delete the copy.")
        return 1
    names, src = sql_effective()
    print(f"projection-table-mirror-gate: OK — {len(_mirrors())} mirror(s) agree with "
          f"their source; the effective CHECK ({src}) names {len(names)}, "
          f"Rust PROJECTION_TABLES names {len(rust_projection_tables())}")
    return 0


# ── non-vacuity ──────────────────────────────────────────────────────────────

def self_test() -> int:
    failures = 0

    def case(label: str, cond: bool) -> None:
        nonlocal failures
        if cond:
            print(f"  ok   {label}")
        else:
            failures += 1
            print(f"  FAIL {label}")

    # R1 — the shipped tree agrees, or the gate cries wolf.
    case("the shipped tree reports nothing", not check())

    # R2..R5 — every mirror must be able to disagree. Mutate each source ON DISK,
    # run the REAL check, restore. Mutating a copy of the parsed set would test
    # the set-difference operator, not the gate.
    # The seeds name each mirror's LIVE contents, so they follow the shrinking:
    # `0018` moved every one of them onto `canon_projection`. A seed that no
    # longer occurs is reported as "could not be planted" and counts as a
    # FAILURE, never a skip — a bite that cannot be planted proves nothing, and
    # silently skipping it is how a self-test becomes decoration.
    seeds = [
        ("SQL CHECK",
         MIGRATION_DIR / "0018_drop_region_session_world_kv_projections.up.sql",
         "        'canon_projection'\n    ));",
         "        'canon_projection',\n        'ghost_projection'\n    ));"),
        ("Rust PROJECTION_TABLES", RUST_REBUILD,
         '    "canon_projection",\n];', '    "canon_projection",\n    "ghost_projection",\n];'),
        ("admin-cli allowedProjectionTables", GO_DRIFT,
         '\t"canon_projection": true,', '\t"ghost_projection": true,'),
        ("integrity-checker types.L3ATables", GO_TYPES,
         '\t"canon_projection",', '\t"ghost_projection",'),
        ("integrity-checker tablemap.specs", GO_TABLEMAP,
         '\t"canon_projection": {PKColumns: []string{"canon_entry_id"}},',
         '\t"ghost_projection": {PKColumns: []string{"canon_entry_id"}},'),
        ("contracts/integrity/config.yaml", YAML_CONFIG,
         "  - name: canon_projection", "  - name: ghost_projection"),
        ("admin-cli projectionTables", GO_REBUILD,
         '\t"canon_projection": {},', '\t"ghost_projection": {},'),
    ]
    for label, path, old, new in seeds:
        raw = path.read_bytes()
        src = _read(path)
        if src.count(old) != 1:
            failures += 1
            print(f"  FAIL {label}: seed not unique ({src.count(old)}) — "
                  f"the bite could not be planted, which is not a pass")
            continue
        _write(path, src.replace(old, new))
        try:
            bit = bool(check())
        finally:
            # Restore from BYTES. Reading through universal-newlines and writing
            # text back turns a CRLF working copy into LF, so a self-test that is
            # meant to leave no trace rewrote the line endings of every file it
            # touched. Git normalises on commit, so the content diff stayed
            # empty and nothing complained — the only tell was a `git status`
            # full of MM, noticed while staging this very commit.
            path.write_bytes(raw)
        case(f"a drifted {label} is reported", bit)

    # R6 — the SQL parser must not mistake 0017's `DELETE FROM ... WHERE
    # table_name IN (<the seven dropped names>)` for the constraint. If it did,
    # it would read the OPPOSITE of the truth and still look like it was working.
    try:
        names, src = sql_effective()
        case("the SQL parser ignores the DELETE's table_name IN (...) list",
             "region_projection" not in names and src.startswith("0018"))
    except LostSubject as e:
        failures += 1
        print(f"  FAIL SQL parse lost its subject: {e}")

    # R7 — a source that parses to nothing must FAIL, not silently agree with
    # another empty set. Blank the Rust list entirely.
    raw = RUST_REBUILD.read_bytes()
    src = _read(RUST_REBUILD)
    old = 'PROJECTION_TABLES: &[&str] = &['
    if src.count(old) != 1:
        failures += 1
        print("  FAIL R7: seed not unique")
    else:
        _write(RUST_REBUILD, src.replace(old, "PROJECTION_TABLES_RENAMED: &[&str] = &["))
        try:
            found = check()
            bit = any("lost its subject" in f for f in found)
        finally:
            RUST_REBUILD.write_bytes(raw)
        case("a source that parses to NOTHING is a finding, not a silent pass", bit)

    if failures:
        print(f"\nprojection-table-mirror-gate --self-test: {failures} rule(s) did not behave")
        return 1
    print("\nprojection-table-mirror-gate --self-test: every rule bites, and none cries wolf")
    return 0


if __name__ == "__main__":
    sys.exit(main())
