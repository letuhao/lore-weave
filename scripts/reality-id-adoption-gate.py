#!/usr/bin/env python3
"""`3E` — the `RealityId` adoption ratchet.

WHAT THIS GUARDS
================
`DP-A12` / `DP-R1` want a reality addressed by `dp::RealityId`, a newtype whose
constructor is `pub(crate)` to `dp` and whose only source is
`SessionContext::bind`. Game-layer services still pass a bare `Uuid`. This gate
is what makes that number go one direction.

THREE CATEGORIES, because one number was answering three questions
==================================================================
    ADOPTABLE       5   must reach zero — a reality that CAN bind, addressed raw
    exempt         52   the reality cannot be accepting commands (provisioning,
                        frozen, being dropped) — see STRUCTURALLY_EXEMPT
    input boundary  4   the raw value a bind CONSUMES; it cannot already be the
                        verified thing the bind produces

Only the first is debt. The other two are ratcheted against GROWTH but will
never reach zero, and mixing them into one figure is how a gate becomes a
number nobody can act on (`BDR-55`).

The figure has been corrected five times, and each correction narrowed it to
something truer: 457 (the plan, stale) -> 884 (every MENTION, including SQL
column names and comments) -> 178 (real typed sites, all crates) -> 84 (the two
game-layer crates) -> 76 (their `src/`; a test fixture is not production
adoption debt) -> the split above, after `3E-NAMING-INCONSISTENCY` found the
regex was matching a NAME rather than the property. Two defects, opposite
directions, both live:

  * it required the spelling `reality_id`, and `commit-service` spells the field
    `reality` — so that crate reported **0 adoptable, 0 exempt**, completely
    adopted, while carrying five real sites including four on the spine's live
    write path;
  * its tail accepted `reality_id: Uuid::from_u128(0x42)`, a struct LITERAL,
    which is not a typed site at all — eleven of those were inflating `exempt`.

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
# `reality` AS WELL AS `reality_id`, and `(?!:)` on the tail. Both were found by
# `3E-NAMING-INCONSISTENCY` and both are the same defect in opposite directions:
# the regex was matching a NAME where the property is "a reality addressed as a
# bare uuid".
#
#   * **The name.** `commit-service` spells its field `reality`, so the crate
#     reported **0 adoptable, 0 exempt** — completely adopted — while carrying
#     seven bare sites, four of them on the spine's live write path
#     (`epoch_commit.rs`). A whole in-scope service was invisible.
#     `BDR-55` says the fix is never to RENAME the field so the regex matches;
#     it is to make the regex measure the property.
#
#   * **The tail.** `reality_id: Uuid::from_u128(0x42)` is a struct LITERAL, not
#     a type annotation, and the old tail `(?![A-Za-z0-9_])` accepted it because
#     the next character is a colon. Measured: **10 such lines**, every one of
#     them a test fixture inside an exempt file — so they were inflating the
#     `exempt` baseline with sites that are not sites. A count that includes
#     things that are not its subject is not a measurement.
SITE = re.compile(
    r"\breality(?:_id)?\s*:\s*(?:&\s*)?(?:Option\s*<\s*)?(?:::)?(?:\w+::)*Uuid(?![A-Za-z0-9_:])"
)

# What turns a raw uuid INTO a verified one. A parameter of a function whose
# body reaches one of these is a bind's INPUT, and a bind's input cannot already
# be its own output.
BIND_MARKERS = ("SessionContext::bind", "MetaControlPlane")

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
    # `.rs` ON PURPOSE, like the `ceilings.rs` row below: these reason about one
    # FILE's subject, not a directory's. `src/server/` will hold the GEO_001
    # routes, which act on realities that ARE open and bindable and must be held
    # to `dp::RealityId` — a directory prefix here would exempt them in advance.
    "services/world-service/src/provision_flow.rs": (
        "the provisioning FLOW, shared by the CLI worker and the HTTP route; same "
        "subject as `provisioner`, extracted so neither restates the other. Its "
        "`existing_registration` READS `reality_registry` to discover whether the "
        "reality exists at all and in what state — a question that necessarily "
        "precedes any bind, since `SessionContext::bind` needs the answer."
    ),
    "services/world-service/src/server/handlers/realities.rs": (
        "the provisioning route's handler. Its request is `ProvisionRequest`, "
        "already exempt for creating the reality; its response reports realities "
        "in states `bind` REFUSES — the `already_provisioned` arm returns whatever "
        "status the registry holds, including `archived` and `soft_deleted`. A "
        "`RealityId` there would assert the control plane accepts commands for a "
        "world that was torn down, which is the forged assertion, not the fix."
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
    # `.rs` ON PURPOSE, unlike the directory-family rows above. These are PREFIX
    # matches, so a bare `.../bin/ceilings` would also exempt a `ceilings_v2.rs`
    # or `ceilings_live_writer.rs` written tomorrow — measured, all three matched.
    # The rows above name DIRECTORIES whose whole subject is one thing; this row
    # reasons about ONE FILE's behaviour, so it may only cover that file.
    # `check_self_minted` would still demand a sibling mint its own reality, but
    # an exemption must not widen by default and lean on a second check to narrow
    # it back (/review-impl).
    "services/commit-service/src/bin/ceilings.rs": (
        "MINTS its own reality and registers it nowhere. `dp::RealityId` asserts "
        "that the control plane confirmed this reality exists and accepts "
        "commands; this harness invents a uuid three lines before use precisely "
        "so the run cannot touch any real world's rows, so no `reality_registry` "
        "row exists and `SessionContext::bind` would refuse it. Adoption would "
        "mean forging that assertion, or provisioning a world — which would make "
        "an append-throughput measurement depend on the meta stack and change "
        "what it measures. The self-minted half of this reason is CHECKED below."
    ),
}

# ─────────────────────────────────────────────────────────────────────────────
# SELF-MINTED — the exemption reasons that rest on "this code INVENTS its
# reality", and are therefore checkable rather than prose.
#
# WHY THIS EXISTS (`BDR-55`, and it is the charge this row had to answer)
# ----------------------------------------------------------------------
# `§0.6e` row 3 allowed a reasoned exemption for `ceilings.rs` and said in the
# same breath: **not a third category invented to make the number zero.** The
# test of that is not how good the prose is — it is whether the exemption can
# ever go WRONG and say so.
#
# `provisioner`'s reason is *"there is no bind that could precede the thing
# being created"*. `ceilings`' is the same shape, and unlike the others it
# names a property of the file that a future edit can falsify: the harness
# holds a reality **nothing handed it**. The moment it gains one — a
# `--reality` flag, an env var, a uuid parsed from text — that reality came
# from somewhere that could have bound it first, and the exemption is void.
#
# So this is not a new classification (the sites still count as `exempt`, under
# the same ratchet). It is the reason being MECHANISED, which is the difference
# `deferral-gate` draws between a row and a mechanism.
SELF_MINTED: dict[str, str] = {
    "services/commit-service/src/bin/ceilings.rs": (
        "an append-throughput harness against a throwaway Postgres; its "
        "`reality` is `Uuid::new_v4()` at the top of each mode"
    ),
}

# What the mint looks like. Absent ⇒ the reason no longer describes the code.
MINT = "Uuid::new_v4()"

# A reality the file did NOT mint. Any of these means something upstream handed
# it one, and something upstream could have bound it.
#
# `Uuid::parse_str` is in the list because it is the only way a uuid enters this
# codebase from text — argv, env or a config file — and a parsed uuid is by
# definition external. Narrow scope keeps that from over-reaching: this pattern
# is applied ONLY to files under a `SELF_MINTED` prefix.
EXTERNAL_REALITY_SOURCE = re.compile(r"--reality\b|REALITY_ID|Uuid::parse_str")

# ─────────────────────────────────────────────────────────────────────────────
# INPUT BOUNDARY — the raw value a bind CONSUMES, which cannot already be the
# verified thing the bind produces.
#
# A THIRD CATEGORY, and `3E-NAMING-INCONSISTENCY` is why it is not a row in the
# dict above. `embedding_queue/live/config` used to sit there with a reason that
# began *"A DIFFERENT KIND of exemption from the six above"* — a comment marking
# a distinction the data structure did not make. `commit-service`'s `args.reality`
# is the same category, and the note predicting that ended:
#
#     "The alternative was renaming the field to `reality` so the regex stopped
#      matching, which would have moved the number without moving the property."
#
# It had already happened. `commit-service` spells it `reality`, the regex never
# matched, and the crate reported clean.
#
# **Most of this category is now detected by PROPERTY, not listed here.** A
# `reality: Uuid` parameter of a function whose body reaches `SessionContext::bind`
# or `MetaControlPlane` IS a bind input, mechanically — and stops being one the
# moment the body no longer binds. That covers `reality_bind::bind_reality` and
# `embedding_queue::bind_reality` with no entry at all.
#
# What remains here is the case with no enclosing function to read: a value
# parsed from argv or the environment into a STRUCT, where the binding happens
# somewhere else entirely. Curated, reasoned, and ratcheted like the rest.
INPUT_BOUNDARY: dict[str, str] = {
    "services/world-service/src/embedding_queue/live/config": (
        "the ENV INPUT the bind consumes, not a reality the code addresses. "
        "`EMBEDDING_REALITY_ID` is text read before any database is open; "
        "`embedding_queue::bind_reality` is what turns it into a verified "
        "`dp::RealityId`, so it cannot already be one. Everything downstream of "
        "that call now takes `dp::RealityId`."
    ),
    "services/world-service/src/server/handlers/actor_control": (
        "the HTTP INPUT the bind consumes. The sites are wire DTO fields — "
        "`GrantRequest`/`RevokeRequest`/`CreateActorRequest` and the two "
        "responses — carrying a uuid decoded from a request body before any "
        "control-plane call exists. The handler is now a thin adapter: it "
        "decodes and hands the uuid straight to `actor_control_flow`, which "
        "binds. See that entry for where the verified type takes over."
    ),
    "services/world-service/src/actor_control_flow": (
        "the module that MINTS the verified id, so its entry points cannot "
        "already hold one. `bind_reality(reality_id: Uuid)` is the boundary "
        "itself — `dp::RealityId` has no public constructor, and this is the "
        "call that produces one. `create_actor`, `preview_grant` and `grant` "
        "each take the raw uuid BECAUSE their first statement binds it, and "
        "everything downstream of that call takes `&dp::RealityId`: "
        "`open_reality_pool` and `actor_registry`'s four functions all do. "
        "`revoke` and `current_driver` are the two that take a raw uuid and "
        "never bind, and both are DELIBERATE and documented on the function. "
        "Revoke: refusing to revoke a driver in a frozen world would strand a "
        "player as the driver of a reality under maintenance, so it stays "
        "available where grant is refused — which means it has no bind to "
        "obtain a verified id from. `current_driver` (RA2): asking WHO drives "
        "an actor in a frozen world is legitimate and often the first question "
        "when working out why the world was frozen, so refusing it would make "
        "the audited read useless in the situation that most needs it."
    ),
    "services/world-service/src/bin/actor_control": (
        "the CLI INPUT the bind consumes, exactly as `spine_args` below. "
        "`Args::reality_id` is parsed from argv before any connection exists, "
        "and `actor_control_flow::bind_reality` is what turns it into a "
        "verified `dp::RealityId` — so the field cannot already hold one. The "
        "worker holds no other reality reference: every operation it performs "
        "goes through the flow module."
    ),
    "services/commit-service/src/spine_args": (
        "the CLI INPUT the bind consumes. `Args::reality` is parsed from argv "
        "before any connection exists, and `reality_bind::bind_reality` is what "
        "turns it into a verified `dp::RealityId` — so the field cannot already "
        "hold one. Listed rather than property-detected because it is a struct "
        "field with no enclosing function whose body could be read for a bind."
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


def boundary_for(rel_path: str) -> str | None:
    """The reason this path is a curated INPUT BOUNDARY, or `None`."""
    for prefix, reason in INPUT_BOUNDARY.items():
        if rel_path.startswith(prefix):
            return reason
    return None


def blank_line_comments(text: str) -> str:
    """Blank `//` lines, keeping offsets so match positions stay meaningful."""
    out = []
    for line in text.replace("\r", "").split("\n"):
        out.append(" " * len(line) if line.lstrip().startswith("//") else line)
    return "\n".join(out)


def is_bind_input(text: str, off: int) -> bool:
    """Is the site at `off` a PARAMETER of a function that performs a bind?

    This is the input-boundary category detected by PROPERTY rather than by a
    path list — the thing `3E-NAMING-INCONSISTENCY` asked for. The claim it
    makes is narrow and mechanical: *a bind's input cannot already be its own
    output.*

    It is non-vacuous in the direction that matters. Delete the
    `SessionContext::bind` call from `bind_reality`'s body and the parameter
    stops being a boundary and becomes adoptable debt — the classification
    follows what the function DOES, not where it lives or what it is called.

    LIMIT, stated: it reads the enclosing function's body textually. A bind
    performed in a helper the function calls is not seen, so such a site is
    counted as ADOPTABLE. Under-exempting is the safe direction — it leaves
    something to read rather than quietly excusing it.

    # The site must be INSIDE the function this finds

    `rfind("fn ")` walks backwards to the nearest preceding `fn`, which for a
    declaration that is not in any function — a struct field, a trait item, a
    `const` — lands on whatever function happens to sit above it. Without the
    containment check at the end, a `pub reality: Uuid` struct field placed
    after `bind_reality` INHERITED its classification and was silently excused.
    Found by `/review-impl` on a synthetic pair; not live in the tree at the
    time, and it would have been the first file to put a struct under a binding
    function. **A gate whose exemption leaks to the next declaration is the
    "quietly deciding it is done" shape `BDR-55` is about**, in the gate written
    to fix a measurement defect.
    """
    fn = text.rfind("fn ", 0, off)
    if fn < 0:
        return False
    # The site is inside the parameter list, so the `(` precedes it. Walk to the
    # matching `)`, then to the `{` that opens the body, then brace-match.
    open_paren = text.find("(", fn)
    if open_paren < 0 or open_paren > off:
        return False
    depth, i = 0, open_paren
    while i < len(text):
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    body_open = text.find("{", i)
    if body_open < 0:
        return False
    depth, j = 0, body_open
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    # CONTAINMENT: the site must lie inside this function — in its parameter
    # list (`open_paren..i`) or its body (`body_open..j`). Anything past `j` is
    # a different declaration that merely follows this function in the file.
    if not (open_paren < off < i or body_open < off < j):
        return False
    body = text[body_open:j]
    return any(m in body for m in BIND_MARKERS)


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


def count_sites(root: Path) -> tuple[dict[str, int], list[str], set[str]]:
    """`({adoptable, exempt, boundary}, per-file lines, prefixes that matched)`."""
    counts = {"adoptable": 0, "exempt": 0, "boundary": 0}
    where: list[str] = []
    used: set[str] = set()
    for path in sorted(root.rglob("*.rs")):
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # A commented-out signature is not a call site. The same stripper
        # `gate-wiring-gate` needed after prose in a source file certified three
        # deferrals as mechanised.
        text = blank_line_comments(raw)
        matches = list(SITE.finditer(text))
        if not matches:
            continue
        rel = path.relative_to(REPO).as_posix()
        struct_reason = exemption_for(rel)
        bound_reason = boundary_for(rel)
        per = {"adoptable": 0, "exempt": 0, "boundary": 0}
        for m in matches:
            if struct_reason is not None:
                per["exempt"] += 1
            elif bound_reason is not None or is_bind_input(text, m.start()):
                per["boundary"] += 1
            else:
                per["adoptable"] += 1
        for k, v in per.items():
            counts[k] += v
        tags = ", ".join(f"{v} {k}" for k, v in per.items() if v)
        where.append(f"{rel}: {tags}")
        for prefix in STRUCTURALLY_EXEMPT:
            if rel.startswith(prefix) and per["exempt"]:
                used.add(prefix)
        for prefix in INPUT_BOUNDARY:
            if rel.startswith(prefix) and per["boundary"]:
                used.add(prefix)
    return counts, where, used


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
        counts, _, used = count_sites(crate / "src")
        out[rel] = counts
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
        # `3E-NAMING-INCONSISTENCY`: the SAME property, spelled without `_id`.
        ("    pub reality: Uuid,", 1),
        ("fn f(reality: Uuid) {}", 1),
        ("    reality: Option<uuid::Uuid>,", 1),
        # Must NOT match — these are what the loose count wrongly swept in.
        ('    "reality_id" => v,', 0),
        ("    reality_id: RealityId,", 0),
        ("    reality: RealityId,", 0),
        ("    SELECT reality_id FROM t", 0),
        ("    reality_id: i64,", 0),
        # A struct LITERAL is not a type annotation. Ten of these were being
        # counted as adoption sites before `3E`.
        ("            reality_id: Uuid::from_u128(0x42),", 0),
        ("            reality: Uuid::new_v4(),", 0),
        # ...and a word merely ENDING in `reality` is a different field.
        ("    unreality: Uuid,", 0),
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
            if not isinstance(v, dict) or set(v) != {"adoptable", "exempt", "boundary"}:
                fails.append(
                    f"baseline row {k!r} = {v!r}; each row is "
                    f"{{'adoptable': int, 'exempt': int, 'boundary': int}} since `3E` added "
                    f"the input-boundary category")
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
    # BOTH tables are isolated. The first version of this block cleared only
    # `STRUCTURALLY_EXEMPT`, and the moment a second table existed its two real
    # entries were phantoms against the synthetic `used` set — so the
    # false-positive arm reded and said the hygiene check was broken when the
    # FIXTURE was. A self-test that does not control all of its inputs is
    # measuring the tree it happens to be run in.
    saved_x, saved_b = dict(STRUCTURALLY_EXEMPT), dict(INPUT_BOUNDARY)
    try:
        STRUCTURALLY_EXEMPT.clear()
        INPUT_BOUNDARY.clear()
        STRUCTURALLY_EXEMPT["a/b"] = "x" * MIN_REASON
        if check_exemption_hygiene({"a/b"}):
            fails.append("hygiene reded on a well-formed, matched exemption (false positive)")
        if not check_exemption_hygiene(set()):
            fails.append("PHANTOM arm did NOT red on an exemption matching nothing")
        STRUCTURALLY_EXEMPT["a/b"] = "too short"
        if not check_exemption_hygiene({"a/b"}):
            fails.append("REASON arm did NOT red on a short reason")

        # ...and the same two arms for the NEW table, so it is not covered only
        # by resemblance to the old one.
        STRUCTURALLY_EXEMPT.clear()
        INPUT_BOUNDARY["c/d"] = "y" * MIN_REASON
        if check_exemption_hygiene({"c/d"}):
            fails.append("hygiene reded on a well-formed INPUT BOUNDARY (false positive)")
        if not check_exemption_hygiene(set()):
            fails.append("PHANTOM arm did NOT red on an INPUT BOUNDARY matching nothing")
        INPUT_BOUNDARY["c/d"] = "short"
        if not check_exemption_hygiene({"c/d"}):
            fails.append("REASON arm did NOT red on a short INPUT BOUNDARY reason")

        # And the overlap arm: one prefix cannot be both categories.
        INPUT_BOUNDARY.clear()
        STRUCTURALLY_EXEMPT["e/f"] = "z" * MIN_REASON
        INPUT_BOUNDARY["e/f"] = "z" * MIN_REASON
        if not any("AMBIGUOUS" in p for p in check_exemption_hygiene({"e/f"})):
            fails.append("AMBIGUOUS arm did NOT red on a prefix in both tables")
    finally:
        STRUCTURALLY_EXEMPT.clear()
        STRUCTURALLY_EXEMPT.update(saved_x)
        INPUT_BOUNDARY.clear()
        INPUT_BOUNDARY.update(saved_b)

    # And the classifier itself, which is the new load-bearing decision.
    if exemption_for("services/world-service/src/provisioner.rs") is None:
        fails.append("provisioner.rs classified ADOPTABLE; it creates the reality")
    if exemption_for("services/world-service/src/embedding_queue/mod.rs") is not None:
        fails.append("embedding_queue classified exempt; it runs against ACTIVE realities")

    # THE INPUT-BOUNDARY PROPERTY, on synthetic source, in BOTH directions.
    #
    # The pair differs by one line — whether the body binds — and that is the
    # whole claim. If both answered the same, the detector would be reading
    # something other than what it says it reads.
    binds = (
        "pub async fn bind_reality(pool: &Pool, reality: Uuid) -> Result<dp::RealityId, E> {\n"
        "    let plane = MetaControlPlane::new(reader, store);\n"
        "    plane.go()\n"
        "}\n"
    )
    does_not_bind = (
        "pub async fn append_turn(pool: &Pool, reality: Uuid) -> Result<(), E> {\n"
        "    sqlx::query(\"INSERT ...\").execute(pool).await\n"
        "}\n"
    )
    m = SITE.search(binds)
    if not (m and is_bind_input(binds, m.start())):
        fails.append(
            "a `reality: Uuid` parameter of a function that BINDS was not detected as an "
            "input boundary — the property detector is not reading the body")
    m = SITE.search(does_not_bind)
    if not m or is_bind_input(does_not_bind, m.start()):
        fails.append(
            "a `reality: Uuid` parameter of a function that does NOT bind was called an "
            "input boundary — the detector excuses everything, which is worse than a list")
    # A site in no function at all (a struct field) must not be property-excused;
    # that is precisely why `spine_args` needs a curated row.
    bare_struct = "pub struct Args {\n    pub reality: Uuid,\n}\n"
    m = SITE.search(bare_struct)
    if m and is_bind_input(bare_struct, m.start()):
        fails.append("a bare struct field was treated as a bind parameter")

    # ...and the SAME struct placed AFTER a binding function, which is the case
    # the fixture above cannot reach: with nothing before it, `rfind("fn ")`
    # returns -1 and the containment logic is never exercised. `NV-1` — the
    # subject could not vary in the direction that fails. This is the shape
    # `/review-impl` found live in the detector.
    struct_after_fn = (
        "pub async fn bind_reality(p: &Pool, reality: Uuid) -> Result<dp::RealityId, E> {\n"
        "    let plane = MetaControlPlane::new(reader, store);\n"
        "    plane.go()\n"
        "}\n"
        "\n"
        "pub struct TurnRow {\n"
        "    pub reality: Uuid,\n"
        "}\n"
    )
    hits = list(SITE.finditer(struct_after_fn))
    if len(hits) != 2:
        fails.append(f"the struct-after-fn fixture parsed {len(hits)} site(s), expected 2")
    else:
        if not is_bind_input(struct_after_fn, hits[0].start()):
            fails.append("the binding function's own PARAMETER stopped being a boundary")
        if is_bind_input(struct_after_fn, hits[1].start()):
            fails.append(
                "a struct field AFTER a binding function was excused as a bind input — the "
                "exemption leaks past the function's closing brace to the next declaration")

    # THE SELF-MINTED ARMS, on a synthetic tree. Four states of one file, and
    # the classification must differ between them — otherwise the check is
    # reading something other than what it claims (`NV-1`).
    import tempfile

    saved_sm = dict(SELF_MINTED)
    try:
        SELF_MINTED.clear()
        SELF_MINTED["svc/bin/bench"] = "x" * 40
        STRUCTURALLY_EXEMPT["svc/bin/bench"] = "y" * MIN_REASON
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "svc" / "bin" / "bench.rs"
            src.parent.mkdir(parents=True)

            src.write_text("fn c1() { let reality = Uuid::new_v4(); }\n", encoding="utf-8")
            clean = check_self_minted(root)
            if clean:
                fails.append(
                    f"self-minted reded on a file that mints and reads nothing: {clean}")

            # ...and each way the claim can become false.
            src.write_text("fn c1() { let reality = args.reality; }\n", encoding="utf-8")
            if not any("CLAIM FALSE" in p for p in check_self_minted(root)):
                fails.append("MINT arm did NOT red when `Uuid::new_v4()` disappeared")

            src.write_text(
                'fn c1() { let reality = Uuid::new_v4(); let _ = flag("--reality"); }\n',
                encoding="utf-8")
            if not any("CLAIM VOID" in p for p in check_self_minted(root)):
                fails.append("EXTERNAL arm did NOT red on a `--reality` flag")

            src.write_text(
                "fn c1() { let reality = Uuid::parse_str(&s).unwrap(); }\n", encoding="utf-8")
            if not any("CLAIM VOID" in p for p in check_self_minted(root)):
                fails.append("EXTERNAL arm did NOT red on a parsed uuid")

            # A line that only MENTIONS the flag in a comment is prose, not an
            # input — the distinction `deferral-gate` had to learn the hard way.
            src.write_text(
                "// takes no --reality flag, by design\n"
                "fn c1() { let reality = Uuid::new_v4(); }\n",
                encoding="utf-8")
            if check_self_minted(root):
                fails.append(
                    "a `--reality` mention in a COMMENT voided the claim; comments are prose")

            src.unlink()
            if not any("PHANTOM" in p for p in check_self_minted(root)):
                fails.append("PHANTOM arm did NOT red when the claim matched no file")

            # ...and the claim guarding an exemption that is not there.
            del STRUCTURALLY_EXEMPT["svc/bin/bench"]
            if not any("ORPHAN" in p for p in check_self_minted(root)):
                fails.append("ORPHAN arm did NOT red on a claim with no matching exemption")
    finally:
        SELF_MINTED.clear()
        SELF_MINTED.update(saved_sm)
        STRUCTURALLY_EXEMPT.pop("svc/bin/bench", None)

    # ── `IN_SCOPE` vs §4, proven on a synthetic tree ──────────────────────────
    #
    # Every arm here is UNREACHABLE on the real repo: `IN_SCOPE` matches the
    # dp-dependent set exactly today, so nothing in this tree can distinguish a
    # working arm from a deleted one. That is precisely the condition under
    # which an arm quietly stops working, so the arms are exercised against
    # sources built to differ by one fact each.
    saved_scope = IN_SCOPE
    try:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            svc = root / "services"

            def manifest(name: str, with_dp: bool) -> None:
                d = svc / name
                d.mkdir(parents=True, exist_ok=True)
                dep = 'dp = { path = "../../crates/dp" }\n' if with_dp else 'serde = "1"\n'
                (d / "Cargo.toml").write_text(
                    f'[package]\nname = "{name}"\n\n[dependencies]\n{dep}',
                    encoding="utf-8")

            manifest("alpha", True)
            manifest("beta", False)
            manifest("gamma", False)
            (root / SCOPE_DOC_REL).parent.mkdir(parents=True, exist_ok=True)
            doc = root / SCOPE_DOC_REL
            doc.write_text(
                f"# 01\n\nBoundary rule: if a service touches a per-reality database, "
                f"{BOUNDARY_RULE_ANCHOR}.\n",
                encoding="utf-8")

            def scope_problems(entries: tuple[str, ...]) -> list[str]:
                globals()["IN_SCOPE"] = entries
                return check_in_scope_matches_the_boundary_rule(root)

            if scope_problems(("services/alpha",)):
                fails.append(
                    "the CLEAN synthetic tree reds — IN_SCOPE names exactly the dp-dependent "
                    f"service: {scope_problems(('services/alpha',))}")

            if not any("NOT IN SCOPE" in p for p in scope_problems(())):
                fails.append(
                    "a service depending on `dp` and absent from IN_SCOPE did NOT red — this is "
                    "the arm that catches a new game-layer service inheriting zero enforcement")

            if not any("NO LONGER USES THE SDK" in p for p in scope_problems(("services/beta",))):
                fails.append(
                    "an IN_SCOPE entry that exists but does not depend on `dp` did NOT red — "
                    "this is the silent-narrowing arm the STRUCTURALLY_EXEMPT preamble warns of")

            if not any("PHANTOM" in p for p in scope_problems(("services/nope",))):
                fails.append("an IN_SCOPE entry matching no directory did NOT red")

            # The doc side, both ways: reworded, then absent.
            doc.write_text("# 01\n\nNo boundary rule here any more.\n", encoding="utf-8")
            if not any("BOUNDARY RULE MOVED" in p for p in scope_problems(("services/alpha",))):
                fails.append(
                    "§4's clause was removed from the document and nothing red — the constant "
                    "would go on enforcing a rule the LOCKED doc stopped making")
            doc.unlink()
            if not any("UNREADABLE" in p for p in scope_problems(("services/alpha",))):
                fails.append("the document was deleted and nothing red")
            doc.write_text(
                f"# 01\n\nBoundary rule: {BOUNDARY_RULE_ANCHOR}.\n", encoding="utf-8")

            # The antecedent, spelled forward: a per-reality DB without the SDK.
            (svc / "beta" / "src").mkdir(parents=True, exist_ok=True)
            leak = svc / "beta" / "src" / "conn.rs"
            leak.write_text('fn c() { connect("reality_7f2a_db"); }\n', encoding="utf-8")
            if not any("BOUNDARY RULE VIOLATED" in p for p in scope_problems(("services/alpha",))):
                fails.append(
                    "a service naming a per-reality database WITHOUT the `dp` SDK did NOT red — "
                    "that is the second door into kernel state that Option (c) exists to forbid")

            # ...and the same words in a comment are prose about the rule.
            leak.write_text('// connects to reality_7f2a_db one day\nfn c() {}\n', encoding="utf-8")
            if any("BOUNDARY RULE VIOLATED" in p for p in scope_problems(("services/alpha",))):
                fails.append("a per-reality DB name in a COMMENT was treated as a connection")
            leak.unlink()

            # The reach floor, and that it is SEPARABLE from the arms above.
            for name in ("beta", "gamma"):
                (svc / name / "Cargo.toml").unlink()
            if not any("REACH FLOOR" in p for p in scope_problems(("services/alpha",))):
                fails.append(
                    "the manifest walk fell to 1 and the floor did not red — a walk that reaches "
                    "nothing is byte-identical to a clean tree")
    finally:
        globals()["IN_SCOPE"] = saved_scope

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
    both = [("EXEMPTION", STRUCTURALLY_EXEMPT), ("INPUT BOUNDARY", INPUT_BOUNDARY)]
    for kind, table in both:
        for prefix, reason in sorted(table.items()):
            if len(reason) < MIN_REASON:
                problems.append(
                    f"UNREASONED {kind}: `{prefix}` has a {len(reason)}-char reason "
                    f"(minimum {MIN_REASON}). State WHY the reality it addresses cannot "
                    f"accept commands; an exemption nobody has to justify is one nobody "
                    f"reviews.")
            if prefix not in used:
                problems.append(
                    f"PHANTOM {kind}: `{prefix}` matches no file with a bare "
                    f"`reality: Uuid` site of that category. Either the code moved, or it "
                    f"was migrated and this entry outlived its subject — delete it. A "
                    f"prefix left behind silently exempts whatever is written there next.")
    # An overlap would make the classification order-dependent, and the order is
    # an implementation detail nobody reading the two tables can see.
    for prefix in sorted(set(STRUCTURALLY_EXEMPT) & set(INPUT_BOUNDARY)):
        problems.append(
            f"AMBIGUOUS: `{prefix}` is in BOTH tables. A site is structurally unable to "
            f"bind, or it is the raw input to a bind — not both, and which one the gate "
            f"picks would depend on dict order.")
    return problems


def check_self_minted(root: Path = REPO) -> list[str]:
    """Is every `SELF_MINTED` claim still true of the code it is about?

    Three arms, and the middle one is the whole point:

    * the prefix must be an actual exemption — a claim about a row that is not
      there excuses nothing and reads as if it does;
    * the file must still MINT (`Uuid::new_v4()`), and must contain no
      **external** reality source. Gaining one is the event that voids the
      reason, because a reality handed to you is a reality something could have
      bound first;
    * the prefix must match a file at all — the phantom arm, for the same
      reason `check_exemption_hygiene` has one.

    `root` is a parameter so the arms can be proven on synthetic files rather
    than on whatever this tree happens to contain (`BDR-71`: a safety check
    hardcoded to `REPO` is a safety check nobody can test).
    """
    problems: list[str] = []
    for prefix, claim in sorted(SELF_MINTED.items()):
        if prefix not in STRUCTURALLY_EXEMPT:
            problems.append(
                f"ORPHAN SELF-MINTED CLAIM: `{prefix}` is not in STRUCTURALLY_EXEMPT, so this "
                f"check is guarding an exemption that does not exist.")
        seen = 0
        for path in sorted(root.rglob("*.rs")):
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if not rel.startswith(prefix):
                continue
            seen += 1
            try:
                text = blank_line_comments(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
            if MINT not in text:
                problems.append(
                    f"SELF-MINTED CLAIM FALSE: `{rel}` is exempt because it mints its own "
                    f"reality ({claim}), and `{MINT}` no longer appears in it. Either the "
                    f"reality now comes from somewhere that could have bound it — in which "
                    f"case pay the adoption debt — or the reason needs rewriting to say what "
                    f"is actually true.")
            found = sorted({m.group(0) for m in EXTERNAL_REALITY_SOURCE.finditer(text)})
            if found:
                problems.append(
                    f"SELF-MINTED CLAIM VOID: `{rel}` is exempt because nothing hands it a "
                    f"reality, and it now reads one from outside: {found}. A reality that "
                    f"arrives from argv, the environment or a parse came from a caller that "
                    f"could have bound it first, so `dp::RealityId` is obtainable here and "
                    f"the exemption no longer holds. Adopt it, or replace this row with a "
                    f"reason that survives the new input.")
        if seen == 0:
            problems.append(
                f"PHANTOM SELF-MINTED CLAIM: `{prefix}` matches no `.rs` file. The harness "
                f"moved or was deleted and the claim outlived it.")
    return problems


# ─────────────────────────────────────────────────────────────────────────────
# `IN_SCOPE` vs THE RULE IT CLAIMS TO ENCODE
#
# `IN_SCOPE` is annotated *"the game-layer services, per DPA-SCOPE's reading of
# the LOCKED §4"*, and until now **nothing compared it to §4**. That is the gap
# `G3` named: a constant that cites a document is a citation, not a check, and
# this gate's own `STRUCTURALLY_EXEMPT` preamble already says what the danger is
# — *"the alternative on the table was editing `IN_SCOPE` to drop
# `world-service`, which would have made the same 62 sites vanish with nothing
# to read."* A narrowing of `IN_SCOPE` is the cheapest way to make this gate
# report clean, and it was the one edit no mechanism could see.
#
# WHY THE CHECK LIVES HERE AND NOT IN THE RUST ORACLE
# ---------------------------------------------------
# `crates/dp/tests/spec_oracle_scope.rs` covers the same document, and covers
# §2.4/§3b instead. `dp-oracle-coverage-gate` counts Rust readers, so a Rust
# test reading THIS Python tuple would be an arm whose subject is not the thing
# it names (`BDR-79`). The consumer of §4 is this file; the check belongs beside
# the constant it guards.
#
# THE HONEST LIMIT
# ----------------
# §4's antecedent is *"reads or writes any aggregate in a per-reality
# database"*, which is a runtime property. Two static proxies stand in, and
# they are proxies:
#   * declaring the `dp` SDK as a Cargo dependency — the consequent of §4, and
#     the only door §2.1 permits;
#   * naming a `reality_<id>_db` database — the antecedent, spelled directly.
# A service that touched a per-reality database through neither would be
# invisible. That service would also be violating §2.1's "the SDK is the only
# door", which `dp-clippy`'s `forbid_raw_kernel_client` is the mechanism for.
SCOPE_DOC_REL = "docs/03_planning/LLM_MMO_RPG/06_data_plane/01_scope_and_boundary.md"

# The exact clause `IN_SCOPE` encodes. Anchored so that rewording §4 reds here
# rather than leaving this gate quietly enforcing a rule the doc stopped making.
BOUNDARY_RULE_ANCHOR = "it is a game-layer service and uses the DP SDK"

# How a service says "I touch a per-reality database" without the SDK naming it.
PER_REALITY_DB = re.compile(r"reality_[A-Za-z0-9_{}]*_db\b|reality_db_name")


def dp_dependent_services(root: Path = REPO) -> tuple[set[str], int]:
    """`({service dirs declaring the dp SDK}, manifests examined)`.

    The count is returned so the caller can enforce a reach floor: a glob that
    matches nothing and a tree with no game-layer services produce the same
    empty set, which is `NV-3` — the scope never reaching its subject.
    """
    found: set[str] = set()
    seen = 0
    for manifest in sorted((root / "services").glob("*/Cargo.toml")):
        seen += 1
        try:
            import tomllib
            data = tomllib.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        deps = {}
        for table in ("dependencies", "dev-dependencies", "workspace"):
            v = data.get(table)
            if isinstance(v, dict):
                deps.update(v if table != "workspace" else v.get("dependencies", {}) or {})
        if "dp" in deps:
            found.add(manifest.parent.relative_to(root).as_posix())
    return found, seen


def check_in_scope_matches_the_boundary_rule(root: Path = REPO) -> list[str]:
    """Does `IN_SCOPE` still say what `01_scope_and_boundary.md` §4 says?

    `root` is a parameter so the arms are provable on a synthetic tree rather
    than on whatever this repo happens to contain (`BDR-71`).
    """
    problems: list[str] = []

    doc = root / SCOPE_DOC_REL
    if not doc.is_file():
        problems.append(
            f"BOUNDARY RULE UNREADABLE: `{SCOPE_DOC_REL}` does not exist. `IN_SCOPE` cites it as "
            f"the authority for which services are game-layer; with the document gone the "
            f"constant is an unsourced list.")
    else:
        text = doc.read_text(encoding="utf-8", errors="replace")
        if BOUNDARY_RULE_ANCHOR not in text:
            problems.append(
                f"BOUNDARY RULE MOVED: `{SCOPE_DOC_REL}` no longer contains §4's clause "
                f"\"{BOUNDARY_RULE_ANCHOR}\". `IN_SCOPE` is derived from that sentence, so it is "
                f"now enforcing a rule the LOCKED document stopped making. Re-read §4 and "
                f"re-derive the constant, or update this anchor deliberately.")

    declared = set(IN_SCOPE)
    dp_users, manifests = dp_dependent_services(root)

    # REACH FLOOR. Separable from every arm below on purpose: the tree has 5
    # service manifests, so a floor of 3 catches a glob pointed at nothing
    # without ever pre-empting a real finding (the `BDR-56` collision).
    if manifests < 3:
        problems.append(
            f"REACH FLOOR: examined only {manifests} `services/*/Cargo.toml` manifest(s) (floor 3, "
            f"measured 5). The walk is pointed at nothing, and every arm below would report clean "
            f"forever — a walk that reaches nothing is byte-identical to a clean tree.")

    for svc in sorted(dp_users - declared):
        problems.append(
            f"GAME-LAYER SERVICE NOT IN SCOPE: `{svc}` declares the `dp` SDK as a dependency, so "
            f"by §4 it is a game-layer service — and `IN_SCOPE` does not list it, so this gate "
            f"has never counted a single adoption site in it. A service can be added to the "
            f"kernel and inherit zero enforcement.")

    for svc in sorted(declared - dp_users):
        if not (root / svc).is_dir():
            problems.append(
                f"PHANTOM IN_SCOPE ENTRY: `{svc}` is listed as a game-layer service and no such "
                f"directory exists. The service moved or was renamed and the constant outlived it.")
        else:
            problems.append(
                f"IN_SCOPE ENTRY NO LONGER USES THE SDK: `{svc}` is listed as game-layer and its "
                f"Cargo manifest does not depend on `dp`. Either it stopped being game-layer — in "
                f"which case removing it is a deliberate, reviewable edit — or it is reaching the "
                f"kernel by a door §2.1 forbids.")

    # §4 SPELLED FORWARD, not just backward. The clause is an implication: touch
    # a per-reality database ⇒ use the SDK. The arms above check the consequent;
    # this one checks the antecedent, and it is the direction that catches a
    # service quietly opening its own connection to `reality_<id>_db`.
    for path in sorted((root / "services").rglob("*.rs")):
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:
            continue
        # This gate NAMES the pattern, and comments about a rule are not code
        # that breaks it — the distinction `deferral-gate` had to learn.
        try:
            body = blank_line_comments(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            continue
        if not PER_REALITY_DB.search(body):
            continue
        svc = "/".join(rel.split("/")[:2])
        if svc not in dp_users:
            problems.append(
                f"BOUNDARY RULE VIOLATED: `{rel}` names a per-reality database and `{svc}` does "
                f"not depend on the `dp` SDK. §4: \"if a service reads or writes any aggregate in "
                f"a per-reality database, {BOUNDARY_RULE_ANCHOR}\". This is the shape §2.1 locks "
                f"Option (c) to prevent — a second door into kernel state.")

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
                _, where, _ = count_sites(crate)
                for w in where:
                    print(w)

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        BASELINE.write_text(
            json.dumps({"sites": {k: dict(sorted(v.items())) for k, v in sorted(current.items())}},
                       indent=2) + "\n",
            encoding="utf-8",
        )
        # SUM THE ROW, not a hand-listed pair. The first version added
        # `adoptable + exempt` and was silently 4 short the day a third category
        # existed — the same "enumerated list goes stale" shape this gate's own
        # docstring is about, in its summary line.
        tot = sum(sum(v.values()) for v in current.values())
        print(f"[reality-id] baseline written: {tot} site(s)")
        return 0

    if not BASELINE.exists():
        sys.exit(f"no baseline at {BASELINE.relative_to(REPO)} — run --write-baseline once")
    known = json.loads(BASELINE.read_text(encoding="utf-8"))["sites"]

    fails = (check_exemption_hygiene(used) + check_self_minted()
             + check_in_scope_matches_the_boundary_rule())

    for rel, counts in sorted(current.items()):
        prev = known.get(rel)
        if prev is None:
            fails.append(
                f"UNTRACKED: `{rel}` has {counts['adoptable'] + counts['exempt']} bare "
                f"`reality_id: Uuid` site(s) and no baseline row. Add one, or route the "
                f"reality through `dp::RealityId`.")
            continue
        # ADOPTABLE — the ratchet that is supposed to reach zero.
        for kind, verb in (
            ("adoptable", "ADOPTABLE"),
            ("exempt", "EXEMPT"),
            ("boundary", "INPUT BOUNDARY"),
        ):
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
    boundary = sum(v["boundary"] for v in current.values())
    print(f"[reality-id] {adoptable} ADOPTABLE + {exempt} structurally exempt + "
          f"{boundary} input-boundary = {adoptable + exempt + boundary} bare "
          f"`reality[_id]: Uuid` site(s) across {len(current)} in-scope crate(s)")
    for rel, counts in sorted(current.items()):
        print(f"    {rel}: {counts['adoptable']} adoptable, {counts['exempt']} exempt, "
              f"{counts['boundary']} boundary")
    if adoptable == 0:
        print("    (adoptable is ZERO — every remaining site is on a path that cannot bind, "
              "or is the raw input a bind consumes)")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        return 1
    print("[reality-id-adoption-gate] OK — matches the baseline exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
