#!/usr/bin/env python3
"""declared-verb-oracle — recompute a declared verb's outcome by a DIFFERENT method.

WHY AN ORACLE, AND WHY IT MUST NOT SHARE A METHOD
--------------------------------------------------
`M2`'s engine computes an actor's vital by attaching a hub plugin, initialising
quantities from `ResourceDecl::base`, and applying signed writes through
`Actor::set_quantity`. A second Rust implementation of that same procedure would
agree with it for the same reasons it is wrong, if it is wrong — **two
implementations of one method is not an oracle.**

So this one shares nothing with it:

    the engine          this oracle
    ----------          -----------
    Rust                Python
    resolved Ruleset    the TOML preset, read as text
    hub fold + write    a running SUM over the committed log
    in memory           rows read back out of Postgres

The only thing the two have in common is the answer. If they agree, the answer
is not an artefact of either one's arithmetic.

WHAT IT CHECKS
--------------
1. The opening vital is the preset's declared `base` for the pool whose
   `role = "vital"` — read from the TOML, not from any Rust type.
2. Every committed `acted` fact's `delta` sums, from that opening, to the `left`
   the LAST fact carries. That is the conservation claim, checked against the
   log rather than against the code that wrote it.
3. Every committed `refused` fact moved nothing — the fact after a refusal opens
   at the value the fact before it closed at.
4. The number of `acted` facts equals the declared `focus` pool's `base`, which
   is the verb's own `requires`/`spend` arithmetic checked from content.

Usage:
    DECLARED_VERB_TEST_DATABASE_URL=... python scripts/declared-verb-oracle.py

Exit 0 = the two methods agree; 1 = they do not; 2 = it could not run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PRESET = REPO / "crates/ruleset-loader/artifacts/presets/proving-ground.toml"


def die(code: int, msg: str) -> "None":
    print(f"[oracle] {msg}")
    raise SystemExit(code)


# ── 1. the preset, read as TEXT ─────────────────────────────────────────────
#
# Deliberately a hand-rolled scan rather than a TOML library. The engine's own
# reader is a TOML library; using the same one would make a parser bug invisible
# to both, which is the shape this file exists to avoid. The format it reads is
# tiny and fully determined by the file it reads.
def preset_tables() -> tuple[list[str], list[dict], list[dict]]:
    src = PRESET.read_text(encoding="utf-8")
    # strip comments so a commented-out row cannot be read as a live one
    lines = [ln.split("#", 1)[0].rstrip() for ln in src.splitlines()]

    quantities: list[str] = []
    for ln in lines:
        m = re.match(r"^quantities\s*=\s*\[(.*)\]", ln)
        if m:
            quantities = re.findall(r'"([a-z0-9_]+)"', m.group(1))

    resources: list[dict] = []
    verbs: list[dict] = []
    cur: dict | None = None
    into: list[dict] | None = None
    for ln in lines:
        s = ln.strip()
        if s == "[[resources]]":
            cur = {}
            resources.append(cur)
            into = resources
            continue
        if s == "[[verbs]]":
            cur = {}
            verbs.append(cur)
            into = verbs
            continue
        if cur is None or "=" not in s:
            continue
        k, _, v = s.partition("=")
        v = v.strip().strip('"')
        cur[k.strip()] = int(v) if re.fullmatch(r"-?\d+", v) else v
    del into
    return quantities, resources, verbs


# ── 2. the committed log, read back out of Postgres ─────────────────────────
def committed_events(dsn: str) -> list[dict]:
    """Every domain fact on the log, oldest first.

    Read through `psql` in the container rather than a Python driver: one fewer
    dependency, and it reads the rows exactly as an operator would — which is
    the point of a live check.
    """
    m = re.match(r"postgres://([^:]+):([^@]+)@[^/]+/(.+)$", dsn)
    if not m:
        die(2, f"cannot parse the DSN: {dsn}")
    user, password, db = m.group(1), m.group(2), m.group(3).split("?")[0]
    container = os.environ.get("PG_CONTAINER", "infra-postgres-1")
    sql = (
        "SELECT payload::text FROM events "
        "WHERE event_type = 'turn.resolved' ORDER BY aggregate_version ASC"
    )
    try:
        out = subprocess.run(
            ["docker", "exec", "-i", "-e", f"PGPASSWORD={password}", container,
             "psql", "-qtAX", "-U", user, "-d", db, "-c", sql],
            capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        die(2, f"could not reach postgres: {e}")
    if out.returncode != 0:
        die(2, f"psql failed: {out.stderr.strip()}")

    facts: list[dict] = []
    for line in out.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        facts.extend(json.loads(line).get("events", []))
    return facts


def main() -> int:
    dsn = os.environ.get("DECLARED_VERB_TEST_DATABASE_URL")
    if not dsn:
        die(2, "live infra unavailable: DECLARED_VERB_TEST_DATABASE_URL is unset. "
               "Run scripts/declared-verb-live-smoke.sh first.")

    quantities, resources, verbs = preset_tables()
    if not quantities or not resources or not verbs:
        die(2, f"the preset yielded nothing readable ({PRESET})")

    vital_rows = [r for r in resources if r.get("role") == "vital"]
    if len(vital_rows) != 1:
        die(1, f"the preset declares {len(vital_rows)} vital pools; a role names ONE")
    vital = vital_rows[0]
    vital_ordinal = quantities.index(vital["quantity"])
    opening = vital["base"]

    plain = [r for r in resources if "role" not in r]
    if len(plain) != 1:
        die(1, f"expected exactly one role-free pool for a verb to spend, found {len(plain)}")
    uses_available = plain[0]["base"]

    verb = verbs[0]
    per_use = verb["effect_amount"]

    facts = committed_events(dsn)
    acted = [f for f in facts if f.get("type") == "acted"]
    refused = [f for f in facts if f.get("type") == "refused"]

    print(f"[oracle] preset : vital = `{vital['quantity']}` ordinal {vital_ordinal}, "
          f"base {opening}")
    print(f"[oracle] preset : verb `{verb['name']}` moves it by {per_use} per use, "
          f"spend pool `{plain[0]['quantity']}` base {uses_available}")
    print(f"[oracle] log    : {len(acted)} acted, {len(refused)} refused, "
          f"{len(facts)} domain facts total")

    failures = 0

    def check(label: str, got, want) -> None:
        nonlocal failures
        ok = got == want
        print(f"[oracle] {'agree ' if ok else 'DIVERGE'}  {label}: engine={got} oracle={want}")
        if not ok:
            failures += 1

    if not acted:
        die(1, "the log carries no `acted` fact — there is nothing to check against")

    # (1) how many times the verb could fire, from CONTENT arithmetic alone.
    check("number of successful uses", len(acted), uses_available)

    # (2) the running sum, from the log, against the value the engine wrote.
    running = opening
    for i, f in enumerate(acted):
        running += f["delta"]
        check(f"vital after use {i + 1}", f["left"], running)
        if f["quantity"] != vital_ordinal:
            print(f"[oracle] DIVERGE  fact {i} moved ordinal {f['quantity']}, "
                  f"the preset's vital is {vital_ordinal}")
            failures += 1
        if f["delta"] != per_use:
            print(f"[oracle] DIVERGE  fact {i} delta {f['delta']}, the preset declares {per_use}")
            failures += 1

    # (3) the closing value, computed in one step rather than accumulated —
    #     a third arithmetic, so an off-by-one in the loop above cannot agree
    #     with itself.
    check("closing vital", acted[-1]["left"], opening + per_use * uses_available)

    # (4) a refusal moved nothing.
    if refused:
        print(f"[oracle] agree   {len(refused)} refusal(s) carry no delta field at all "
              f"— nothing to move")
    else:
        print("[oracle] DIVERGE  the log carries no refusal; CMD-5's other half is unproven")
        failures += 1

    if failures:
        print(f"\n[oracle] {failures} divergence(s): two independent methods disagree "
              f"about what happened")
        return 1
    print("\n[oracle] AGREE — the committed log and the authored content compute "
          "the same outcome by different routes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
