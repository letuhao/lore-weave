#!/usr/bin/env python3
"""crate-purity-gate — a law must not be ABLE to read a file (IMP-D2).

THE RULE THIS ENFORCES
----------------------
26_implementation_architecture.md, IMP-D2:

  > "`game-rules` must not depend on `ruleset-loader`. Laws take a resolved
  >  `Rules` by reference (RLS-A12) and know nothing about where it came from.
  >  **A law that can read a file is a law that can be slow, fallible, and
  >  untestable.**"

IMP-Q2 asked crate-or-module and answered *"leaning crate, because the gate is
the point"*. This is that gate. Without it, `game-rules` being a crate only
means a violation needs one extra line in a Cargo.toml.

WHY IT IS NOT ONE RULE
----------------------
The first draft was a single rule — *"transitive deps must be a subset of
{ruleset-core, sim-core}"* — and design review killed it. `Side` and
`EncounterOutcome` derive `serde::Serialize` (they cross the wire as committed
event payloads) and `ruleset-core` pulls `blake3`, so a whole-tree allowlist
would have to enumerate serde's and blake3's own trees. That is brittle against
a patch bump, and a gate that reds on an innocent version bump teaches the next
author to widen it rather than read it.

Worse, it would have been aimed at the wrong thing. **The threat is a law that
can reach a FILE, not a law that can hash.** So:

  R1  workspace-internal transitive deps  ⊆ allowlist    DENY-by-default
  R2  external deps of the workspace closure ⊆ allowlist DENY-by-default
  R3  no I/O-capable std path in src/                    DENY-by-default
  R4  no known async/IO runtime in the transitive tree   denylist (see below)

R1 is transitive on purpose: `game-rules -> ruleset-core -> ruleset-loader`
is a real violation that a direct-deps check would wave through. R1 also answers
*"what about a sibling crate written tomorrow?"* with **refused**, which is the
polarity the repo keeps getting wrong (docs/standards/non-vacuity.md, NV-3).

R3 is the rule that actually states IMP-D2, because it is about the CAPABILITY
rather than the dependency list: a law that reads a file has to name a path to
do it. A crate could import nothing at all and still call `std::fs::read`.

R4 is the only default-ALLOW rule here, and it is written down as such rather
than dressed up. It is belt-and-braces for the case where an allowed external
crate grows an async runtime underneath it.

SERDE IS ALLOWED, FORMATS ARE NOT
---------------------------------
Doc 26 says the laws carry "no serde of external formats". A `derive` is a trait
impl, not a format. R2's allowlist has `serde` and does NOT have `serde_json`,
`toml` or `bincode` — the distinction is enforced by omission, which is what
deny-by-default buys.

R2 covers the external deps of `game-rules` AND of every workspace crate it
reaches, because direct-only left a hole: `reqwest` added to `ruleset-core` would
pass R1 (that crate is allowed) and pass a direct-only R2, leaving only R4's
default-ALLOW denylist between an I/O crate and the laws. It stops short of the
full transitive tree on purpose — serde's and blake3's own trees are brittle to
enumerate and a gate that reds on a patch bump gets widened rather than read. The
boundary is "every crate we write, plus what it directly pulls in": the part a
human in this repo actually decides.

NON-VACUITY
-----------
`--self-test` runs every rule against synthetic inputs that violate it and fails
if any rule reports nothing. That proves each rule BITES; it does not prove the
scope is right, which is why R1/R3 are written as predicates over a whole crate
rather than over a list of files (NV-3). See docs/standards/non-vacuity.md.

    python scripts/crate-purity-gate.py
    python scripts/crate-purity-gate.py --self-test
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# S2 — the ONE shared source stripper. This gate's own hand-rolled version was the
# buggy one (a `//` inside a string literal ate the violation after it), which is
# exactly why three copies became one.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from gatelib import strip_comments  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# ── the policy ───────────────────────────────────────────────────────────────

# Crates that must stay pure, and what each may reach.
#
# Adding a crate here is how a new pure boundary gets enforced. Adding a NAME to
# one of the sets is a decision that needs a reason in the comment beside it —
# the sets are deny-by-default precisely so that widening them is visible in a
# diff instead of happening by accident.
PURE_CRATES: dict[str, dict[str, set[str]]] = {
    "game-rules": {
        # R1 — workspace-internal, TRANSITIVE.
        "workspace": {
            "ruleset-core",  # the resolved rules; no I/O of its own
            "sim-core",      # DetRng + EntityId; zero dependencies
        },
        # R2 — external deps of game-rules AND of every workspace crate it
        # reaches. Direct-per-crate, not the whole transitive tree (see the
        # reasoning at the R2 check).
        "external": {
            "serde",   # derive/trait ONLY, on Side + EncounterOutcome. NOT a
                       # format crate: serde_json / toml / bincode stay out, and
                       # their absence from this set is what refuses them.
            "blake3",  # pulled in via `ruleset-core`, which hashes the canonical
                       # bytes. Pure compute — no fs, no net, no clock. Listed
                       # rather than silently tolerated: it IS reachable from the
                       # laws, so someone decided that, and the decision is here.
        },
    },
    # Feature #1 of the game tier (2026-08-02). The fold is a function of
    # (actor, declarations, rows) with one correct answer, so the same argument
    # that made `game-rules` a crate applies verbatim: a hub that can read a
    # file is a hub that can be slow, fallible and unreplayable.
    #
    # `game-rules` is DELIBERATELY ABSENT from the workspace set below. The hub
    # sits beneath the features and combat is a feature; a dependency in that
    # direction becomes a cycle the day combat is rewritten as a plugin. Its
    # absence here is what refuses it — R1 is deny-by-default.
    "actor-hub": {
        "workspace": {
            "ruleset-core",      # MAX_DECLARED_QUANTITIES, ModifierOp, the declared substrate
            "sim-core",          # EntityId; zero dependencies
            "entity-existence",  # GoneState — the shipped existence enum, leaf-extracted
        },
        "external": {
            "serde",   # derive ONLY, on GoneState, which crosses the wire as a
                       # platform status envelope. Same distinction as above:
                       # serde_json / toml / bincode stay out by omission.
            "blake3",  # via ruleset-core, as for game-rules.
        },
    },
    # ── the two the gate was NOT looking at, added 2026-08-06 ────────────────
    #
    # Both were already clean — measured: zero I/O-capable std paths, and
    # dependency lists of `{}` and `{sim-core, blake3}`. Clean is not the point.
    # `PURE_CRATES` is an ENUMERATED LIST, and R3 scans `crates/<name>/src` for
    # exactly the names in it, so everything absent was **default-uncovered**
    # (`NV-3`) — including the kernel, which is the one crate in the tree whose
    # purity the whole determinism argument rests on.
    #
    # The gate's own header says R1 is transitive so that a sibling crate
    # written tomorrow is refused. That polarity was right for R1 and never
    # applied to R3: a `std::fs::read` inside `sim-core` reached no allowlist,
    # widened no dependency set, and would have shipped green.
    #
    # Found by a PO question — *"is there anywhere a module that may not touch
    # the DB reaches down to it, and how is that guarded?"* — not by any check.
    # `DP-A2` — the CP/DP split. Policy lives in a thin control-plane SERVICE;
    # hot-path reads and writes happen in a data plane embedded as a LIBRARY,
    # and "the control plane is never on the hot path of a player action".
    #
    # That is a purity claim about this crate, and it was guarded by nothing
    # until 2026-08-13 — `crates/dp` was simply never listed here, so a `tokio`
    # or a dependency on `dp-control-plane` would have put the control plane on
    # the hot path with the whole suite green. The crate's own Cargo.toml argues
    # the point and cites `S2.3`; an argument in a comment is not a check.
    #
    # `dp-control-plane` is DELIBERATELY ABSENT from the workspace set: the SDK
    # reaching the control plane is the exact thing DP-A2 forbids, so its
    # absence here is what refuses it.
    "dp": {
        # R1 — workspace-internal, TRANSITIVE. Empty on purpose.
        "workspace": set(),
        # R2 — external. `uuid` opens nothing, reads nothing, spawns nothing.
        "external": {"uuid"},
    },
    "sim-core": {
        # ZERO, and the emptiness is the assertion. `Cargo.toml` carries the
        # same claim in prose (*"determinism is the product, and every
        # dependency is a determinism liability to audit"*); this is where that
        # sentence becomes a thing that can fail. Adding ANY dependency to the
        # kernel now reds here and has to be argued in this diff.
        "workspace": set(),
        "external": set(),
    },
    "ruleset-core": {
        "workspace": {
            "sim-core",  # `RulesetDigest` ALONE (F1-D1) — the kernel CARRIES
                         # the digest, this crate COMPUTES it
        },
        "external": {
            "blake3",  # the canonical-bytes hash. Pure compute: no fs, no net,
                       # no clock. Same entry the two crates above already carry
                       # it under, because they reach it transitively through
                       # here — which is why its absence from THIS set would
                       # have been the inconsistency.
        },
    },
}

# R3 — capabilities a law may not have. The rule is the CAPABILITY, not the
# crate: a law that can read a file must name a path to do it.
BANNED_STD = {
    r"\bstd::fs\b": "filesystem access — a law that can read a file is fallible and slow (IMP-D2)",
    r"\bstd::net\b": "network access — same, plus nondeterministic latency",
    r"\bstd::process\b": "subprocess — an escape hatch around every rule here",
    r"\bstd::env\b": "environment — a law whose result depends on ambient config is not replayable",
    r"\bSystemTime\b": "wall clock — RLS-D13: nothing wall-clock-derived may enter the rules",
    r"\bInstant\b": "monotonic clock — same; a law is a function of state, not of when it ran",
    r"\bstd::io\b": "io — a law neither reads nor writes",
}

# R4 — the default-ALLOW half, stated plainly. Names matched against the whole
# transitive tree, so an allowed crate that grows one of these underneath it is
# still caught.
IO_RUNTIMES = {
    "tokio", "async-std", "smol", "sqlx", "redis", "reqwest", "hyper", "tonic",
    "rusqlite", "mio", "socket2",
}

SRC_GLOB = "**/*.rs"


class Finding:
    def __init__(self, rule: str, crate: str, detail: str, where: str = ""):
        self.rule, self.crate, self.detail, self.where = rule, crate, detail, where

    def __str__(self) -> str:
        loc = f" [{self.where}]" if self.where else ""
        return f"  {self.rule}  {self.crate}{loc}: {self.detail}"


# ── metadata ─────────────────────────────────────────────────────────────────

def load_metadata() -> dict:
    out = subprocess.run(
        ["cargo", "metadata", "--format-version", "1"],
        cwd=REPO, capture_output=True, text=True,
    )
    if out.returncode != 0:
        print("crate-purity-gate: `cargo metadata` failed:", file=sys.stderr)
        print(out.stderr[-2000:], file=sys.stderr)
        sys.exit(2)
    return json.loads(out.stdout)


def _index(meta: dict):
    """(pkg id -> name, pkg id -> node, workspace member names)."""
    name_of = {p["id"]: p["name"] for p in meta["packages"]}
    nodes = {n["id"]: n for n in meta.get("resolve", {}).get("nodes", [])}
    members = {name_of[i] for i in meta.get("workspace_members", [])}
    return name_of, nodes, members


def _runtime_deps(node: dict) -> list[str]:
    """Normal (runtime) deps only — build/dev deps are not linked into the lib.

    A dev-dependency on `ruleset-loader` in this crate's own tests would NOT be
    an IMP-D2 violation: the shipped law still cannot reach a file. Encoding
    that distinction rather than assuming it is the same discipline IMP-D4
    demanded for `BTreeMap<EntityId, _>`.
    """
    out = []
    for d in node.get("deps", []):
        kinds = d.get("dep_kinds") or [{"kind": None}]
        if any(k.get("kind") is None for k in kinds):
            out.append(d["pkg"])
    return out


def transitive_runtime(root_id: str, nodes: dict) -> set[str]:
    seen, stack = set(), [root_id]
    while stack:
        cur = stack.pop()
        for dep in _runtime_deps(nodes.get(cur, {"deps": []})):
            if dep not in seen:
                seen.add(dep)
                stack.append(dep)
    return seen


# ── the four rules ───────────────────────────────────────────────────────────

def check_deps(meta: dict, policy: dict[str, dict[str, set[str]]]) -> list[Finding]:
    """R1, R2, R4 — pure function of metadata, so the self-test can drive it."""
    findings: list[Finding] = []
    name_of, nodes, members = _index(meta)
    id_of = {}
    for pid, nm in name_of.items():
        id_of.setdefault(nm, pid)

    for crate, allow in policy.items():
        if crate not in id_of:
            findings.append(Finding("R1", crate, "not in the workspace — policy names a crate that does not exist"))
            continue
        root = id_of[crate]
        closure = {name_of[i] for i in transitive_runtime(root, nodes)}

        # R1 — workspace-internal, transitive, deny-by-default.
        for dep in sorted(closure & members):
            if dep not in allow["workspace"]:
                findings.append(Finding(
                    "R1", crate,
                    f"reaches workspace crate `{dep}` (transitively). IMP-D2: the laws take a "
                    f"resolved &Rules and must not reach the loader or the host. Allowed: "
                    f"{sorted(allow['workspace'])}"))

        # R2 — external deps of EVERY workspace crate the closure reaches, not
        # just of `crate` itself.
        #
        # `/review-impl` found the hole in the direct-only version: adding
        # `reqwest` to `ruleset-core` passes R1 (ruleset-core is allowed) and
        # passes a direct-only R2 (game-rules does not declare it), leaving only
        # R4's denylist — which is default-ALLOW, so any I/O crate not on that
        # list would have reached the laws unchallenged.
        #
        # Still not the whole transitive tree: serde's and blake3's own trees are
        # out of scope on purpose, because enumerating them is brittle against a
        # patch bump and a gate that reds on an innocent version bump teaches the
        # next author to widen it. The boundary is "every crate WE write plus what
        # it directly pulls in" — the part a human here actually decides.
        for ws_crate in sorted({crate} | (closure & members)):
            ws_id = id_of.get(ws_crate)
            if ws_id is None:
                continue
            for dep in sorted(name_of[d] for d in _runtime_deps(nodes.get(ws_id, {"deps": []}))):
                if dep not in members and dep not in allow["external"]:
                    via = "" if ws_crate == crate else f" (via `{ws_crate}`)"
                    findings.append(Finding(
                        "R2", crate,
                        f"reaches external dependency `{dep}`{via}. Add it to PURE_CRATES with a "
                        f"reason, or drop it. Allowed: {sorted(allow['external'])}"))

        # R4 — the default-allow denylist, over the whole tree.
        for dep in sorted(closure & IO_RUNTIMES):
            findings.append(Finding(
                "R4", crate, f"an I/O runtime (`{dep}`) is in the transitive tree"))

    return findings


def check_source(text: str, where: str, crate: str) -> list[Finding]:
    """R3 — the capability scan. Pure function of the text, so it self-tests."""
    findings = []
    stripped = strip_comments(text, keep_strings=False)
    for pat, why in BANNED_STD.items():
        if re.search(pat, stripped):
            findings.append(Finding("R3", crate, f"{pat.strip(chr(92)+'b')} — {why}", where))
    return findings


def scan_sources(policy: dict) -> list[Finding]:
    findings = []
    for crate in policy:
        src = REPO / "crates" / crate / "src"
        if not src.is_dir():
            findings.append(Finding("R3", crate, f"no source directory at {src.relative_to(REPO)}"))
            continue
        # Whole DIRECTORY, never a file list — a module added tomorrow is
        # covered on its first line (NV-3).
        for f in sorted(src.glob(SRC_GLOB)):
            findings += check_source(
                f.read_text(encoding="utf-8"), str(f.relative_to(REPO)).replace("\\", "/"), crate)
    return findings


# ── self-test ────────────────────────────────────────────────────────────────

def _fake_meta(extra_ws: list[str], extra_ext: list[str]) -> dict:
    """A synthetic workspace: game-rules -> ruleset-core -> <extras>."""
    def pkg(n): return {"id": f"id-{n}", "name": n}
    names = ["game-rules", "ruleset-core", "sim-core"] + extra_ws + extra_ext
    ws = ["game-rules", "ruleset-core", "sim-core"] + extra_ws

    def dep(n): return {"pkg": f"id-{n}", "dep_kinds": [{"kind": None}]}
    return {
        "packages": [pkg(n) for n in names],
        "workspace_members": [f"id-{n}" for n in ws],
        "resolve": {"nodes": [
            {"id": "id-game-rules", "deps": [dep("ruleset-core")] + [dep(n) for n in extra_ext]},
            {"id": "id-ruleset-core", "deps": [dep("sim-core")] + [dep(n) for n in extra_ws]},
            {"id": "id-sim-core", "deps": []},
        ] + [{"id": f"id-{n}", "deps": []} for n in extra_ws + extra_ext]},
    }


def self_test() -> int:
    policy = {"game-rules": {"workspace": {"ruleset-core", "sim-core"}, "external": {"serde", "blake3"}}}
    fails = []

    # ── DP-A2, the CP/DP split ────────────────────────────────────────────────
    # "Hot-path reads and writes happen in a data plane embedded as a LIBRARY …
    # the control plane is never on the hot path of a player action."
    #
    # The mutation harness proves this gate REFUSES an I/O dependency on
    # `crates/dp`. This proves the row that makes it do so still exists —
    # deleting `"dp"` from PURE_CRATES silently retires DP-A2's only guard, and
    # every other case here would stay green, because they all drive `policy`
    # above rather than the shipped table.
    #
    # The SECOND half of DP-A2 — the SDK must not reach the control plane — is
    # enforced by CARGO, not by this gate: `dp-control-plane` depends on `dp`,
    # so the reverse edge is a cycle and metadata refuses it. Recorded here
    # because "enforced by construction" is a claim, and this is where a reader
    # finds out which half is which.
    dp = PURE_CRATES.get("dp")
    if dp is None:
        fails.append("DP-A2: `dp` is not in PURE_CRATES — the data plane's purity, "
                     "which is an INVARIANT, is guarded by nothing")
    elif dp["external"] != {"uuid"} or dp["workspace"] != set():
        fails.append(
            f"DP-A2: `dp`'s allowed set widened to workspace={sorted(dp['workspace'])} "
            f"external={sorted(dp['external'])}. It is the SDK on the hot path; every "
            f"addition needs its own argument, in the row.")

    # R1 must bite on a TRANSITIVE workspace dep — the case a direct-deps check
    # would wave through. This is the whole reason the walk is transitive.
    f = check_deps(_fake_meta(["ruleset-loader"], []), policy)
    if not any(x.rule == "R1" for x in f):
        fails.append("R1 did not bite on a transitive `ruleset-loader`")

    # R2 must bite on a new direct external dep.
    f = check_deps(_fake_meta([], ["toml"]), policy)
    if not any(x.rule == "R2" for x in f):
        fails.append("R2 did not bite on a direct external `toml`")

    # …and on one reached VIA an allowed workspace crate. This is the hole the
    # direct-only version left: `reqwest` on `ruleset-core` passes R1 and a
    # direct-only R2, leaving only R4's default-ALLOW denylist between an I/O
    # crate and the laws.
    via = _fake_meta([], [])
    via["packages"].append({"id": "id-hyper", "name": "hyper"})
    for nd in via["resolve"]["nodes"]:
        if nd["id"] == "id-ruleset-core":
            nd["deps"].append({"pkg": "id-hyper", "dep_kinds": [{"kind": None}]})
    via["resolve"]["nodes"].append({"id": "id-hyper", "deps": []})
    f = check_deps(via, policy)
    if not any(x.rule == "R2" for x in f):
        fails.append("R2 did not bite on an external dep reached VIA an allowed workspace crate")

    # R4 must bite on a runtime anywhere in the tree.
    f = check_deps(_fake_meta([], ["tokio"]), policy)
    if not any(x.rule == "R4" for x in f):
        fails.append("R4 did not bite on `tokio`")

    # The clean case must be SILENT — otherwise the three above prove nothing.
    f = check_deps(_fake_meta([], ["serde"]), policy)
    if f:
        fails.append(f"the clean workspace produced findings: {[str(x) for x in f]}")

    # R3 must bite on each banned capability, and must NOT bite on a comment
    # that merely mentions one (the gate's own docs would otherwise red it).
    for pat in BANNED_STD:
        probe = {"\\bstd::fs\\b": "std::fs::read(p)", "\\bstd::net\\b": "std::net::TcpStream",
                 "\\bstd::process\\b": "std::process::exit(1)", "\\bstd::env\\b": "std::env::var(\"X\")",
                 "\\bSystemTime\\b": "SystemTime::now()", "\\bInstant\\b": "Instant::now()",
                 "\\bstd::io\\b": "std::io::stdin()"}[pat]
        if not check_source(f"fn f() {{ {probe}; }}", "probe.rs", "game-rules"):
            fails.append(f"R3 did not bite on {probe}")
    if check_source("// a law must never call std::fs::read\n", "probe.rs", "game-rules"):
        fails.append("R3 bit on a COMMENT mentioning std::fs — it would red its own documentation")

    # ── the four cases /review-impl found the naive line-regex getting wrong ──
    if not check_source('fn f() { let p = format!("{}//{}", a, b); std::fs::write(p, x); }',
                        "probe.rs", "game-rules"):
        fails.append("R3 MISSED a violation after a `//` inside a STRING LITERAL — the string "
                     "truncated the line and hid it. That is a way to defeat the rule.")
    if check_source("/* a law must never call std::fs::read */\n", "probe.rs", "game-rules"):
        fails.append("R3 bit on a BLOCK comment mentioning std::fs")
    if check_source('fn f() { let s = "std::fs::read is banned here"; }', "probe.rs", "game-rules"):
        fails.append("R3 bit on a STRING LITERAL naming the capability — a message about the "
                     "rule is not a use of it")
    if not check_source("fn f<'a>(p: &'a str) { std::fs::read(p); }", "probe.rs", "game-rules"):
        fails.append("R3 MISSED a violation in a function carrying a LIFETIME — the `'a` was "
                     "mistaken for a char literal and ate the rest of the line")

    if fails:
        print("crate-purity-gate SELF-TEST FAILED — the gate cannot fail, so it is not a gate:")
        for x in fails:
            print(f"  - {x}")
        return 1
    print("crate-purity-gate: self-test OK — R1 (transitive), R2, R3 (7 capabilities, "
          "comment-immune) and R4 all bite, and the clean case is silent")
    return 0


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--self-test", action="store_true",
                    help="prove every rule can fail, against synthetic violations")
    args = ap.parse_args()
    if args.self_test:
        return self_test()

    findings = check_deps(load_metadata(), PURE_CRATES) + scan_sources(PURE_CRATES)
    if findings:
        print(f"crate-purity-gate: {len(findings)} finding(s) — IMP-D2 is violated\n")
        for f in findings:
            print(f)
        print("\nA law that can read a file is a law that can be slow, fallible and untestable.")
        print("If a dependency is genuinely pure, add it to PURE_CRATES in this file WITH A REASON.")
        return 1

    crates = ", ".join(sorted(PURE_CRATES))
    print(f"crate-purity-gate: OK — {crates} reach no loader, no host, no I/O capability")
    return 0


if __name__ == "__main__":
    sys.exit(main())
