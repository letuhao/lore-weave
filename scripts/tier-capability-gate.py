#!/usr/bin/env python3
"""tier-capability-gate — the transport tier owns no database of record (I3).

THE RULE THIS ENFORCES
----------------------
`CLAUDE.md`'s language rule, amended and LOCKED 2026-05-29:

  > **TypeScript** for gateway/BFF + realtime transport.

That is a statement about a TIER, not a taste in languages. The gateway is the
edge and the realtime service is a transport; neither owns durable state. A
transport that owns a database of record stops being a transport — it becomes a
second writer with its own copy of the truth, reachable from outside, and the
`api-gateway-bff` invariant ("all external traffic through the gateway") turns
from a funnel into a fork.

WHY IT EXISTS, MEASURED
-----------------------
Asked by the PO on 2026-08-06: *"is there anywhere a module that may not touch
the DB reaches down and writes to it, and how is that guarded?"*

The answer for this tier was **clean in fact, unguarded in mechanism**: zero of
the five TypeScript services declares any database driver, and nothing would
have noticed if one did. `scripts/language-rule-lint.sh` maps a service to a
LANGUAGE and stops there; `crate-purity-gate` covers Rust crates and cannot see
a `package.json`. So the boundary held because nobody had crossed it.

The same question found the same shape twice more the same hour (the kernel
outside `PURE_CRATES`; `meta-write-discipline-lint.sh` unwired for being slow).
An unguarded true statement is one commit from being a false one.

WHAT IS AND IS NOT A DATABASE
-----------------------------
`ioredis` is DELIBERATELY NOT on the denylist, and the distinction is the whole
judgement in this file: `game-server` reaches Redis as a **message bus** (the
`reality:*:cell:*:proposals` stream it XADDs a signed proposal to) and as a
rate-limit/ticket cache. That is the architecture, not a bypass of it — the
proposal goes ON the bus precisely so the authoritative side decides. A store of
record is different: it answers "what is true", and for this tier the answer to
that always comes from another service.

If Redis is ever used as a store of record from this tier, this gate will not
catch it. Stated rather than glossed: the denylist is a NAME check, and a name
check cannot see intent. What it does catch is the cheap, likely mistake —
someone adds `pg` because a lookup was easier inline than through a service,
which is exactly the move a PO correction stopped on 2026-08-06.

WHAT IT CHECKS
--------------
  R1  a `typescript` service declares no DB driver in its package.json
      (dependencies AND devDependencies — a test that talks to a database from
      the transport crosses the same boundary, and a devDependency is how it
      would arrive first)
  R2  no `typescript` source imports one either — belt to R1's braces, since a
      workspace hoist can make a package importable without declaring it
  R3  the scan HAS A SUBJECT: it must find TS services, and it must find their
      manifests. A scan over nothing passes trivially and reports success,
      which is worse than no gate (`NV-3`).

Exit 0 = clean; 1 = findings; 2 = misuse.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
LANG_RULE = REPO / "contracts" / "language-rule.yaml"
SERVICES = REPO / "services"

# The tier this gate governs. Read off the language rule rather than hardcoded
# per service, so a TS service added tomorrow is in scope on its first commit —
# the polarity an enumerated list gets wrong.
GOVERNED_LANG = "typescript"

# Packages that ARE a database of record. Grouped by why, because a denylist
# with no reasons is a list nobody can extend correctly.
DB_PACKAGES: dict[str, str] = {
    # Postgres
    "pg": "Postgres driver",
    "pg-promise": "Postgres driver",
    "pg-native": "Postgres driver",
    "postgres": "Postgres driver (postgres.js)",
    "@vercel/postgres": "Postgres driver",
    "@neondatabase/serverless": "Postgres driver",
    # ORMs / query builders — a DB client with a nicer face
    "typeorm": "ORM",
    "prisma": "ORM",
    "@prisma/client": "ORM",
    "sequelize": "ORM",
    "drizzle-orm": "ORM",
    "knex": "query builder over a DB driver",
    "kysely": "query builder over a DB driver",
    "mikro-orm": "ORM",
    "@mikro-orm/core": "ORM",
    # Other stores of record
    "mysql": "MySQL driver",
    "mysql2": "MySQL driver",
    "mongodb": "MongoDB driver",
    "mongoose": "MongoDB ODM",
    "sqlite3": "SQLite driver",
    "better-sqlite3": "SQLite driver",
    "neo4j-driver": "graph store driver",
    "cassandra-driver": "Cassandra driver",
}

# Import forms an ES/TS module can use to reach one of the above.
IMPORT_RE = re.compile(
    r"""(?:from\s+|require\(\s*|import\(\s*)['"]([^'"]+)['"]""", re.MULTILINE
)


class Finding:
    def __init__(self, rule: str, service: str, detail: str, where: str = ""):
        self.rule, self.service, self.detail, self.where = rule, service, detail, where

    def __str__(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"  {self.rule}  {self.service}{loc}: {self.detail}"


def governed_services() -> list[str]:
    """Service names the language rule maps to the governed tier.

    Parsed with a line regex rather than a YAML library: this file is a flat
    `name: lang` map under one `services:` key, the repo ships no yaml dep for
    scripts, and `language-rule-lint.sh` reads it the same way. If it ever grows
    nesting, R3's subject check is what notices — the parse would return nothing
    and the gate would FAIL rather than pass over an empty list.
    """
    if not LANG_RULE.is_file():
        print(f"tier-capability-gate: MISUSE — no language rule at {LANG_RULE}", file=sys.stderr)
        sys.exit(2)
    out = []
    for line in LANG_RULE.read_text(encoding="utf-8").splitlines():
        stripped = line.split("#", 1)[0].strip()
        if not stripped or ":" not in stripped:
            continue
        name, _, lang = stripped.partition(":")
        if lang.strip() == GOVERNED_LANG:
            out.append(name.strip())
    return sorted(out)


def declared_packages(pkg_json: Path) -> dict[str, str]:
    """Every declared dependency name -> which section declared it."""
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"tier-capability-gate: MISUSE — cannot parse {pkg_json}: {e}", file=sys.stderr)
        sys.exit(2)
    found = {}
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        for name in (data.get(section) or {}):
            found[name] = section
    return found


def scan() -> tuple[list[Finding], dict[str, int]]:
    findings: list[Finding] = []
    stats = {"services": 0, "manifests": 0, "sources": 0}

    for svc in governed_services():
        root = SERVICES / svc
        if not root.is_dir():
            # `missing` is a legal state in the language rule (scheduled, not on
            # disk). language-rule-lint owns that check; this gate simply has
            # nothing to scan.
            continue
        stats["services"] += 1

        # ── R1 — the manifest ────────────────────────────────────────────────
        pkg = root / "package.json"
        if pkg.is_file():
            stats["manifests"] += 1
            for name, section in declared_packages(pkg).items():
                if name in DB_PACKAGES:
                    findings.append(Finding(
                        "R1", svc,
                        f"declares `{name}` ({DB_PACKAGES[name]}) in {section}. This tier is "
                        f"gateway/BFF + realtime transport (I3): it calls services, it does not "
                        f"own a store of record",
                        f"services/{svc}/package.json",
                    ))

        # ── R2 — the source ──────────────────────────────────────────────────
        for f in sorted(root.rglob("*.ts")):
            s = str(f).replace("\\", "/")
            if "/node_modules/" in s or "/dist/" in s:
                continue
            stats["sources"] += 1
            text = f.read_text(encoding="utf-8", errors="replace")
            for spec in IMPORT_RE.findall(text):
                # `pg/lib/x` and `@prisma/client` both resolve to a denied root.
                root_pkg = spec if spec.startswith("@") and spec.count("/") <= 1 else spec.split("/")[0]
                if root_pkg in DB_PACKAGES:
                    findings.append(Finding(
                        "R2", svc,
                        f"imports `{spec}` ({DB_PACKAGES[root_pkg]}) — a store of record reached "
                        f"from the transport tier",
                        str(f.relative_to(REPO)).replace("\\", "/"),
                    ))
    return findings, stats


def selftest() -> int:
    """The gate's own teeth, on synthetic input — no repo state involved."""
    cases = [
        ("a plain Postgres driver", {"dependencies": {"pg": "^8"}}, True),
        ("an ORM in devDependencies", {"devDependencies": {"prisma": "^5"}}, True),
        ("a scoped ORM client", {"dependencies": {"@prisma/client": "^5"}}, True),
        ("the bus, which is NOT a store of record", {"dependencies": {"ioredis": "^5"}}, False),
        ("ordinary transport deps", {"dependencies": {"colyseus": "^0.17", "express": "^4"}}, False),
    ]
    bad = []
    for label, manifest, want_finding in cases:
        names = set()
        for sect in ("dependencies", "devDependencies"):
            names |= set(manifest.get(sect) or {})
        got = bool(names & set(DB_PACKAGES))
        if got != want_finding:
            bad.append(f"{label}: expected finding={want_finding}, got {got}")

    imports = [
        ("import pg", "import { Client } from 'pg';", True),
        ("require pg subpath", "const x = require('pg/lib/client');", True),
        ("scoped client", "import c from '@prisma/client';", True),
        ("the bus", "import Redis from 'ioredis';", False),
        ("a relative module named pg-ish", "import x from './pgutil.js';", False),
    ]
    for label, src, want in imports:
        hit = False
        for spec in IMPORT_RE.findall(src):
            root_pkg = spec if spec.startswith("@") and spec.count("/") <= 1 else spec.split("/")[0]
            if root_pkg in DB_PACKAGES:
                hit = True
        if hit != want:
            bad.append(f"import {label}: expected {want}, got {hit}")

    if bad:
        print("tier-capability-gate: SELFTEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print(f"tier-capability-gate: SELFTEST PASS — {len(cases)} manifest + {len(imports)} import "
          f"case(s); it flags a driver, a devDependency and a scoped client, and does NOT flag "
          f"the message bus or a relative path (non-vacuous in both directions)")
    return 0


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    if selftest() != 0:
        return 2

    findings, stats = scan()

    # ── R3 — the scan must have had a subject ────────────────────────────────
    if stats["services"] == 0:
        print("tier-capability-gate: FAIL — the language rule named no on-disk "
              f"`{GOVERNED_LANG}` service. A scan over nothing passes trivially.", file=sys.stderr)
        return 1
    if stats["manifests"] == 0:
        print(f"tier-capability-gate: FAIL — found {stats['services']} governed service(s) and "
              "not one package.json. The manifest check read nothing.", file=sys.stderr)
        return 1

    if findings:
        print(f"tier-capability-gate: {len(findings)} finding(s) — I3, the transport tier owns no "
              "database of record")
        print()
        for f in findings:
            print(f)
        print()
        print("The gateway is the edge and the realtime service is a transport; neither owns")
        print("durable state. If a lookup is needed, it belongs behind a service call — see")
        print("SEALED-SUBJECT: the answer to 'who drives this actor' goes through the kernel")
        print("path, not through a connection opened at the edge.")
        return 1

    print(f"tier-capability-gate: OK — {stats['services']} {GOVERNED_LANG} service(s), "
          f"{stats['manifests']} manifest(s), {stats['sources']} source file(s); none owns a "
          f"database of record ({len(DB_PACKAGES)} driver/ORM names checked)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
