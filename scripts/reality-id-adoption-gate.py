#!/usr/bin/env python3
"""`3E` — the `RealityId` adoption ratchet.

WHAT THIS GUARDS
================
`DP-A12` / `DP-R1` want a reality addressed by `dp::RealityId`, a newtype whose
constructor is `pub(crate)` to `dp` and whose only source is
`SessionContext::bind`. Game-layer services still pass a bare `Uuid` in **76**
places. This gate is what makes that number go one direction.

The figure has been corrected three times, and each correction narrowed it to
something truer: 457 (the plan, stale) -> 884 (every MENTION, including SQL
column names and comments) -> 178 (real typed sites, all crates) -> 84 (the two
game-layer crates) -> **76**, which is those two crates' `src/`. The last eight
are in `tests/`, and a test fixture is not production adoption debt: those
adopt when the code they exercise does. `src/` only, so the number measures the
thing the ratchet is for.

WHY A RATCHET AND NOT A SWEEP (run-state §0.6c, sealed)
=======================================================
84 sites in one commit is unreviewable and unbisectable. A baseline records the
count per crate; the gate fails when a count goes UP, and fails when it goes
DOWN without the baseline being lowered — so a migration cannot be undone
silently and a gain cannot be forgotten. Same shape as
`contracts/dp/dp-clippy-baseline.json`, which this repo already runs.

WHY IT COULD NOT HAVE SHIPPED EARLIER
=====================================
A crate adopts `RealityId` by RECEIVING one. Until `5A` the only
`dp::ControlPlane` implementor was a `#[cfg(test)]` double, so no production
code could hold a `RealityId` at all — a gate demanding adoption would have been
demanding a forgery. `5A` (`crates/meta-rs/src/control_plane.rs`) is the
producer, and it is why this file exists now rather than two slices ago.

SCOPE — DERIVED FROM A LOCKED RULE, NOT A LIST
==============================================
`01_scope_and_boundary.md` §4: a service that reads or writes an aggregate in a
per-reality database is game-layer and uses the SDK. `DPA-SCOPE` names exactly
two: `world-service` and `commit-service`.

**`dp-kernel`'s 73 sites are NOT in scope, and cannot be.** It carries
`[package.metadata.dp] dp-crate = true` — it IS the data plane — and
`RealityId::new_verified` is `pub(crate)` to `dp`, so the kernel structurally
cannot construct one. Counting it would be counting sites that can never fall.
The gate reads the marker rather than hardcoding that exclusion, so a crate that
declares itself data-plane tomorrow leaves scope the same way.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
BASELINE = REPO / "contracts" / "dp" / "reality-id-baseline.json"

# `reality_id: Uuid`, `&Uuid`, `Option<Uuid>`, and the PATH-QUALIFIED forms
# (`uuid::Uuid`, `::uuid::Uuid`) — a FIELD or PARAMETER still typed as a bare
# uuid. Deliberately NOT every mention of the string: `reality_id` also names a
# SQL column, a log key and a serde field, and none of those is something
# `RealityId` replaces. Measured: the loose count is 884 and the real subject is
# 178, of which 76 are in scope.
#
# THE PATH-QUALIFIED ALTERNATIVE IS NOT DECORATION. The first version required
# `Uuid` immediately after the colon, and the very first bite — which wrote
# `reality_id: uuid::Uuid` — walked straight past it and the gate reported OK.
# Measured afterwards: zero qualified sites exist in scope today, so the
# baseline was never wrong. The hole was `NV-3` all the same — DEFAULT-UNCOVERED
# for anything written tomorrow, and a bite is the only reason it was found
# before someone relied on it.
SITE = re.compile(r"reality_id\s*:\s*(?:&\s*)?(?:Option\s*<\s*)?(?:::)?(?:\w+::)*Uuid(?![A-Za-z0-9_])")

# The game-layer services, per DPA-SCOPE's reading of the LOCKED §4.
IN_SCOPE = ("services/world-service", "services/commit-service")


def is_dp_crate(crate_dir: Path) -> bool:
    """Does this crate declare itself the data plane?

    Read rather than hardcoded, so the exclusion tracks the marker. A crate
    that IS the data plane cannot hold a `RealityId` — the constructor is
    private to `dp` — so demanding adoption of it would be demanding the
    impossible.
    """
    manifest = crate_dir / "Cargo.toml"
    if not manifest.is_file():
        return False
    try:
        import tomllib
        data = tomllib.loads(manifest.read_text(encoding="utf-8", errors="replace"))
    except Exception:
        return False
    return (
        data.get("package", {}).get("metadata", {}).get("dp", {}).get("dp-crate") is True
    )


def count_sites(root: Path) -> tuple[int, list[str]]:
    """Bare-uuid sites under `root`, and where they are."""
    total = 0
    where: list[str] = []
    for path in sorted(root.rglob("*.rs")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        hits = 0
        for line in text.replace("\r", "").splitlines():
            stripped = line.lstrip()
            # A commented-out signature is not a call site. The same stripper
            # `gate-wiring-gate` needed after prose in a source file certified
            # three deferrals as mechanised.
            if stripped.startswith("//"):
                continue
            hits += len(SITE.findall(line))
        if hits:
            total += hits
            where.append(f"{path.relative_to(REPO).as_posix()}: {hits}")
    return total, where


def measure() -> dict[str, int]:
    out: dict[str, int] = {}
    for rel in IN_SCOPE:
        crate = REPO / rel
        if not crate.is_dir():
            continue
        if is_dp_crate(crate):
            # Not a silent skip: a game-layer service declaring itself the data
            # plane is a scope change someone must see.
            print(f"[reality-id] {rel} declares dp-crate = true; out of scope")
            continue
        n, _ = count_sites(crate / "src")
        out[rel] = n
    return out


def self_test() -> int:
    """Invariants that need no tree walk."""
    fails = []

    hits = [
        ("    reality_id: Uuid,", 1),
        ("    reality_id: &Uuid,", 1),
        ("    reality_id: Option<Uuid>,", 1),
        ("fn f(reality_id: Uuid) {}", 1),
        # The form that escaped the first version, and the reason it is here.
        ("    reality_id: uuid::Uuid,", 1),
        ("    reality_id: ::uuid::Uuid,", 1),
        ("    reality_id: Option<uuid::Uuid>,", 1),
        # Must NOT match — these are what the loose count wrongly swept in.
        ('    "reality_id" => v,', 0),
        ("    reality_id: RealityId,", 0),
        ("    SELECT reality_id FROM t", 0),
        ("    reality_id: i64,", 0),
    ]
    for line, want in hits:
        got = len(SITE.findall(line))
        if got != want:
            fails.append(f"SITE on {line!r} matched {got}, want {want}")

    if not BASELINE.exists():
        fails.append(f"no baseline at {BASELINE.relative_to(REPO)}")
    else:
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        if "sites" not in data:
            fails.append("baseline has no `sites` key")
        for k, v in data.get("sites", {}).items():
            if not isinstance(v, int) or v < 0:
                fails.append(f"baseline row {k!r} = {v!r}; a count is a non-negative int")
        if all(v == 0 for v in data.get("sites", {}).values()):
            fails.append(
                "every baseline row is 0 — adoption is COMPLETE, so delete this gate "
                "and its baseline rather than leaving a ratchet with nothing to ratchet"
            )

    for f in fails:
        print(f"FAIL: {f}")
    if fails:
        return 1
    print("[reality-id-adoption-gate] self-test OK")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--list", action="store_true", help="show every site")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    current = measure()

    if args.list:
        for rel in IN_SCOPE:
            crate = REPO / rel / "src"
            if crate.is_dir():
                _, where = count_sites(crate)
                for w in where:
                    print(w)

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"sites": dict(sorted(current.items()))}, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[reality-id] baseline written: {sum(current.values())} site(s)")
        return 0

    if not BASELINE.exists():
        sys.exit(f"no baseline at {BASELINE.relative_to(REPO)} — run --write-baseline once")
    known = json.loads(BASELINE.read_text(encoding="utf-8"))["sites"]

    fails = []
    for rel, n in sorted(current.items()):
        prev = known.get(rel)
        if prev is None:
            fails.append(
                f"UNTRACKED: `{rel}` has {n} bare `reality_id: Uuid` site(s) and no baseline "
                f"row. Add one, or route the reality through `dp::RealityId`.")
        elif n > prev:
            fails.append(
                f"REGRESSION: `{rel}` went {prev} -> {n} bare `reality_id: Uuid` site(s). "
                f"A reality is addressed by `dp::RealityId`, obtained from "
                f"`SessionContext::bind` — see crates/meta-rs/src/control_plane.rs.")
        elif n < prev:
            fails.append(
                f"BASELINE STALE: `{rel}` improved {prev} -> {n}. Lower its row so the "
                f"ratchet holds the gain; otherwise the next regression is invisible.")
    for rel in sorted(known):
        if rel not in current:
            fails.append(f"BASELINE STALE: `{rel}` is gone from the tree — delete its row")

    total = sum(current.values())
    print(f"[reality-id] {total} bare `reality_id: Uuid` site(s) across "
          f"{len(current)} in-scope crate(s)")
    for rel, n in sorted(current.items()):
        print(f"    {rel}: {n}")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("[reality-id-adoption-gate] OK — matches the baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
