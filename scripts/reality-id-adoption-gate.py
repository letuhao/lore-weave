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

# ─────────────────────────────────────────────────────────────────────────────
# STRUCTURALLY EXEMPT — code whose subject is a reality that is NOT accepting
# commands, and which therefore CANNOT hold a `dp::RealityId`.
#
# WHY THIS SPLIT EXISTS (measured 2026-08-09)
# -------------------------------------------
# This gate reported 73 sites for `world-service` in a way that reads as debt.
# All 73 were classified and **62 of them cannot be paid** — not "hard",
# *cannot*. `dp::RealityId` asserts a specific fact: the control plane confirmed
# this reality EXISTS and ACCEPTS COMMANDS. `MetaControlPlane` refuses
# `Provisioning`, `Frozen`, `Archived`, `SoftDeleted` and `Dropped`. And the code
# below is precisely the code whose job is realities in those states.
#
# A ratchet whose target is unreachable is a CEILING wearing a ratchet's name.
# Left as one number, 73 could never reach zero, and a figure nobody can act on
# is how a gate becomes background noise — which `gate-wiring-gate`'s own
# preamble names as worse than no gate.
#
# WHAT AN EXEMPTION IS NOT
# ------------------------
# Not a hole. Exempt files are still counted, still baselined, and still FAIL on
# growth — the exemption changes which ratchet a file is under, never whether it
# has one. Every entry carries a reason, checked for length, the same shape
# `dp-clippy-gate` uses for `plane = "platform"`. And an entry matching no file
# is itself a failure: a phantom exemption is a claim about code that is not
# there.
#
# THE HONEST LIMIT, SAID OUT LOUD: this is a curated list, so it is only as good
# as its reasons. What it is NOT is a silent narrowing — the alternative on the
# table was editing `IN_SCOPE` to drop `world-service`, which would have made the
# same 62 sites vanish with nothing to read.
STRUCTURALLY_EXEMPT: dict[str, str] = {
    "services/world-service/src/provisioner": (
        "CREATES the reality. `ProvisionRequest.reality_id` is documented "
        "\"caller-generated\", and `register_pending` INSERTs the row with "
        "status=provisioning — a status the control plane refuses. There is no "
        "bind that could precede the thing being created."
    ),
    "services/world-service/src/deprovisioner": (
        "DROPS the reality's database. Its subject is a world being torn down, "
        "which by definition no longer accepts commands."
    ),
    "services/world-service/src/reality_seeder": (
        "seeds a reality that is not yet open. The seeder runs between "
        "provisioning and activation, so a capability for it cannot exist yet — "
        "and `lifecycle_transitioner` is the thing that eventually makes the "
        "reality bindable."
    ),
    "services/world-service/src/bin/provision": (
        "the provisioner's CLI entry point; same subject, same reason."
    ),
    "services/world-service/src/rebuild": (
        "rebuilds projections against realities in ANY state, deliberately. "
        "`rebuild/mod.rs`: \"the reality MUST stay frozen and an operator "
        "inspects the dead letter.\" Rebuilding a FROZEN reality is the normal "
        "case, not the exception."
    ),
    "services/world-service/src/bin/replay-aggregate": (
        "operator replay tool; same as rebuild — it runs against whatever state "
        "the reality is in, which is usually frozen precisely because someone is "
        "replaying it."
    ),
    "services/world-service/src/orphan_scan": (
        "scans for orphaned rows across realities regardless of state; "
        "`orphan_scan.rs` lists \"frozen\" among the statuses it handles."
    ),
    # A DIFFERENT KIND of exemption from the six above, and worth the distinction.
    "services/world-service/src/embedding_queue/live/config": (
        "the ENV INPUT the bind consumes, not a reality the code addresses. "
        "`EMBEDDING_REALITY_ID` is text read before any database is open; "
        "`embedding_queue::bind_reality` is what turns it into a verified "
        "`dp::RealityId`, so it cannot already be one — a bind's input cannot be "
        "its own output. Everything downstream of that call now takes "
        "`dp::RealityId`. The alternative was renaming the field to `reality` so "
        "the regex stopped matching, which would have moved the number without "
        "moving the property; this says what is true instead."
    ),
}

# An exemption reason must actually say something. Same discipline as
# `dp-clippy-gate`'s 40-char floor on a `plane = \"platform\"` claim: an
# exemption nobody has to justify is an exemption nobody reviews.
MIN_REASON = 60


def exemption_for(rel_path: str) -> str | None:
    """The reason this path is structurally exempt, or `None` if it is adoptable.

    Prefix match, so a family (`reality_seeder/*`) is one entry rather than
    seven that can drift apart.
    """
    for prefix, reason in STRUCTURALLY_EXEMPT.items():
        if rel_path.startswith(prefix):
            return reason
    return None


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


def count_sites(root: Path) -> tuple[int, int, list[str], set[str]]:
    """`(adoptable, exempt, per-file lines, exemption prefixes that matched)`."""
    adoptable = 0
    exempt = 0
    where: list[str] = []
    used: set[str] = set()
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
        if not hits:
            continue
        rel = path.relative_to(REPO).as_posix()
        reason = exemption_for(rel)
        if reason is None:
            adoptable += hits
            where.append(f"{rel}: {hits}  [ADOPTABLE]")
        else:
            exempt += hits
            where.append(f"{rel}: {hits}  [exempt]")
            for prefix in STRUCTURALLY_EXEMPT:
                if rel.startswith(prefix):
                    used.add(prefix)
    return adoptable, exempt, where, used


def measure() -> tuple[dict[str, dict[str, int]], set[str]]:
    out: dict[str, dict[str, int]] = {}
    used_all: set[str] = set()
    for rel in IN_SCOPE:
        crate = REPO / rel
        if not crate.is_dir():
            continue
        if is_dp_crate(crate):
            # Not a silent skip: a game-layer service declaring itself the data
            # plane is a scope change someone must see.
            print(f"[reality-id] {rel} declares dp-crate = true; out of scope")
            continue
        adoptable, exempt, _, used = count_sites(crate / "src")
        out[rel] = {"adoptable": adoptable, "exempt": exempt}
        used_all |= used
    return out, used_all


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
            if not isinstance(v, dict) or set(v) != {"adoptable", "exempt"}:
                fails.append(
                    f"baseline row {k!r} = {v!r}; each row is "
                    f"{{'adoptable': int, 'exempt': int}} since the 2026-08-09 split")
                continue
            for kind, n in v.items():
                if not isinstance(n, int) or n < 0:
                    fails.append(f"baseline {k!r}.{kind} = {n!r}; a count is a non-negative int")
        # ADOPTABLE only. `exempt` will never be zero by construction — these are
        # sites that cannot adopt — so gating the gate's own retirement on the
        # total would mean it can never retire, which is the same "unreachable
        # target" defect the split exists to fix.
        rows = data.get("sites", {})
        if rows and all(
            isinstance(v, dict) and v.get("adoptable") == 0 for v in rows.values()
        ):
            print(
                "[reality-id] NOTE — adoptable is 0 everywhere. The ratchet now guards only "
                "against REGRESSION, which is still worth having; but if no bindable path "
                "ever gains a bare site again, this gate has finished its job and the "
                "exemptions have become the whole story."
            )

    # THE EXEMPTION ARMS, on synthetic input rather than on the tree — so they
    # are proven to fire regardless of what the tree currently contains.
    saved = dict(STRUCTURALLY_EXEMPT)
    try:
        STRUCTURALLY_EXEMPT.clear()
        STRUCTURALLY_EXEMPT["a/b"] = "x" * MIN_REASON
        if check_exemption_hygiene({"a/b"}):
            fails.append("hygiene reded on a well-formed, matched exemption (false positive)")
        if not check_exemption_hygiene(set()):
            fails.append("PHANTOM arm did NOT red on an exemption matching nothing")
        STRUCTURALLY_EXEMPT["a/b"] = "too short"
        if not check_exemption_hygiene({"a/b"}):
            fails.append("REASON arm did NOT red on a short reason")
    finally:
        STRUCTURALLY_EXEMPT.clear()
        STRUCTURALLY_EXEMPT.update(saved)

    # And the classifier itself, which is the new load-bearing decision.
    if exemption_for("services/world-service/src/provisioner.rs") is None:
        fails.append("provisioner.rs classified ADOPTABLE; it creates the reality")
    if exemption_for("services/world-service/src/embedding_queue/mod.rs") is not None:
        fails.append("embedding_queue classified exempt; it runs against ACTIVE realities")

    for f in fails:
        print(f"FAIL: {f}")
    if fails:
        return 1
    print("[reality-id-adoption-gate] self-test OK")
    return 0


def check_exemption_hygiene(used: set[str]) -> list[str]:
    """Every exemption must be justified and must match something.

    Two arms, and the second is the one that rots. A PHANTOM exemption — an
    entry matching no file — is a claim about code that is not there: it
    survives a deletion, a rename or a migration, and silently widens the moment
    a new file happens to match its prefix. `migration-manifest-gate` carries the
    same check for the same reason.
    """
    problems: list[str] = []
    for prefix, reason in sorted(STRUCTURALLY_EXEMPT.items()):
        if len(reason) < MIN_REASON:
            problems.append(
                f"UNREASONED EXEMPTION: `{prefix}` has a {len(reason)}-char reason "
                f"(minimum {MIN_REASON}). State WHY the reality it addresses cannot "
                f"accept commands; an exemption nobody has to justify is one nobody "
                f"reviews.")
        if prefix not in used:
            problems.append(
                f"PHANTOM EXEMPTION: `{prefix}` matches no file with a bare "
                f"`reality_id: Uuid` site. Either the code moved, or it was migrated "
                f"and this entry outlived its subject — delete it. A prefix left "
                f"behind silently exempts whatever is written there next.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--list", action="store_true", help="show every site")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    current, used = measure()

    if args.list:
        for rel in IN_SCOPE:
            crate = REPO / rel / "src"
            if crate.is_dir():
                _, _, where, _ = count_sites(crate)
                for w in where:
                    print(w)

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"sites": {k: dict(sorted(v.items())) for k, v in sorted(current.items())}},
                       indent=2) + "\n",
            encoding="utf-8",
        )
        tot = sum(v["adoptable"] + v["exempt"] for v in current.values())
        print(f"[reality-id] baseline written: {tot} site(s)")
        return 0

    if not BASELINE.exists():
        sys.exit(f"no baseline at {BASELINE.relative_to(REPO)} — run --write-baseline once")
    known = json.loads(BASELINE.read_text(encoding="utf-8"))["sites"]

    fails = check_exemption_hygiene(used)

    for rel, counts in sorted(current.items()):
        prev = known.get(rel)
        if prev is None:
            fails.append(
                f"UNTRACKED: `{rel}` has {counts['adoptable'] + counts['exempt']} bare "
                f"`reality_id: Uuid` site(s) and no baseline row. Add one, or route the "
                f"reality through `dp::RealityId`.")
            continue
        # ADOPTABLE — the ratchet that is supposed to reach zero.
        for kind, verb in (("adoptable", "ADOPTABLE"), ("exempt", "EXEMPT")):
            now, was = counts[kind], prev.get(kind)
            if was is None:
                fails.append(f"BASELINE SHAPE: `{rel}` has no `{kind}` row; rewrite the baseline")
            elif now > was:
                if kind == "adoptable":
                    fails.append(
                        f"REGRESSION ({verb}): `{rel}` went {was} -> {now}. A reality on a "
                        f"path that CAN bind is addressed by `dp::RealityId`, obtained from "
                        f"`SessionContext::bind` — see services/commit-service/src/reality_bind.rs.")
                else:
                    fails.append(
                        f"REGRESSION ({verb}): `{rel}` went {was} -> {now}. Exempt does not "
                        f"mean unbounded — these files may not GROW new bare sites either. If "
                        f"the new code is on a bindable path it belongs outside the exemption.")
            elif now < was:
                fails.append(
                    f"BASELINE STALE ({verb}): `{rel}` improved {was} -> {now}. Lower its row "
                    f"so the ratchet holds the gain; otherwise the next regression is invisible.")

    for rel in sorted(known):
        if rel not in current:
            fails.append(f"BASELINE STALE: `{rel}` is gone from the tree — delete its row")

    adoptable = sum(v["adoptable"] for v in current.values())
    exempt = sum(v["exempt"] for v in current.values())
    print(f"[reality-id] {adoptable} ADOPTABLE + {exempt} structurally exempt "
          f"= {adoptable + exempt} bare `reality_id: Uuid` site(s) "
          f"across {len(current)} in-scope crate(s)")
    for rel, counts in sorted(current.items()):
        print(f"    {rel}: {counts['adoptable']} adoptable, {counts['exempt']} exempt")
    if adoptable == 0:
        print("    (adoptable is ZERO — every remaining site is on a path that cannot bind)")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("[reality-id-adoption-gate] OK — matches the baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
