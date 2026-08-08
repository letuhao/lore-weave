#!/usr/bin/env python3
"""DP-R3 coverage gate — runs `dp-clippy` over the workspace and ratchets.

WHAT THIS GUARDS
================
`DP-R3` forbids a raw storage client (`sqlx::PgPool`, `redis::Client`, …) in any
crate that does not declare `[package.metadata.dp] dp-crate = true`. The lint
that decides this lives in `lints/dp-clippy/`; this gate is what makes its
verdict binding on CI rather than on whoever remembers to run it.

The repo does not satisfy DP-R3 today, and pretending otherwise was never an
option: a baseline records what is known-red, the gate fails when a crate gets
WORSE or a NEW crate goes red, and it also fails when a baselined crate turns
clean — so the baseline shrinks toward empty instead of ageing into wallpaper.

THREE FAILURE MODES, AND WHY EACH IS CHECKED SEPARATELY
======================================================
Each of these was MEASURED on this repo, not anticipated:

1. NEW RED / WORSE RED — the point of the gate.

2. UNCHECKED IS NOT CLEAN. A single `cargo dylint -- --workspace` invocation
   reported exactly three red crates (`service-http`, `world-gen`, `meta-rs`).
   Linting `services/world-service` on its own immediately produced FIVE more
   errors, in a crate that is a workspace member and was in the `--workspace`
   selection. Whatever the cause — a unit that failed before it was scheduled,
   feature unification, cargo's own `--keep-going` semantics — the run SILENTLY
   omitted a crate and the omission looked exactly like cleanliness. So every
   member must be positively accounted for: either it produced findings, or
   cargo emitted an artifact proving it compiled. A member that did neither is
   re-linted alone, and if it still cannot be accounted for the gate FAILS.
   Silence is not a verdict.

3. NO LINT LOADED. `cargo dylint --all` prints `Warning: No libraries were
   found.` and EXITS 0 when the library name, path or toolchain is wrong. A
   gate reading that exit code would report DP-R3 enforced everywhere while
   enforcing it nowhere. `lints/dp-clippy/run-lint.sh` asserts a library is
   loaded before it will run; this gate goes through that script for exactly
   that reason, and refuses to interpret its own success otherwise.

WHY THE MEMBER LIST IS DERIVED, NOT WRITTEN DOWN
================================================
Members come from `cargo metadata`, so a crate added tomorrow is covered the
day it lands. An enumerated list here would be default-uncovered (`NV-3`) — the
shape this repo has shipped repeatedly, most recently as a lint keyed on a
hardcoded list of crate names instead of the manifest marker it documented.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINT_DIR = REPO / "lints" / "dp-clippy"
LIBS = LINT_DIR / "libs"
BASELINE = REPO / "contracts" / "dp" / "dp-clippy-baseline.json"

# The lint's own message, used to attribute a diagnostic to DP-R3 rather than to
# an unrelated compile error. Matched on the rule id, which is the one part of
# the sentence that exists to be matched.
RULE_TAG = "(DP-R3)"


def cargo_metadata() -> dict:
    out = subprocess.run(
        ["cargo", "metadata", "--no-deps", "--format-version", "1"],
        cwd=REPO, capture_output=True, text=True,
    )
    if out.returncode != 0:
        sys.exit(f"cargo metadata failed:\n{out.stderr}")
    return json.loads(out.stdout)


def members(meta: dict) -> dict[str, Path]:
    """name -> manifest dir, for every workspace member."""
    return {
        p["name"]: Path(p["manifest_path"]).parent
        for p in meta["packages"]
    }


def declares_marker(manifest_dir: Path) -> bool:
    """Mirror of the lint's own manifest read.

    Deliberately a SEPARATE implementation from the lint's (`V.2`: a mechanical
    oracle by a different method). If the two ever disagree about which crates
    are exempt, that disagreement is itself the finding — an exemption only one
    of them honours is how a rule quietly stops applying.
    """
    text = (manifest_dir / "Cargo.toml").read_text(encoding="utf-8", errors="replace")
    try:
        import tomllib
        data = tomllib.loads(text)
    except Exception:
        return False
    return (
        data.get("package", {})
        .get("metadata", {})
        .get("dp", {})
        .get("dp-crate")
        is True
    )


def lint_env() -> dict:
    env = dict(os.environ)
    # dylint REFUSES a relative path ("DYLINT_LIBRARY_PATH contains ..., which
    # is not absolute"), so resolve rather than pass through.
    env["DYLINT_LIBRARY_PATH"] = str(LIBS.resolve())
    return env


def assert_lint_loaded() -> None:
    """Failure mode 3. Never interpret a green run from an absent lint."""
    if not LIBS.is_dir() or not any(LIBS.iterdir()):
        sys.exit(
            "NO LINT LIBRARY. Build it first:\n"
            "    cd lints/dp-clippy && ./run-lint.sh --self-test\n"
            "Refusing to run: `cargo dylint` exits 0 when it finds no lints, so "
            "proceeding here would report DP-R3 clean without checking anything."
        )
    out = subprocess.run(
        ["cargo", "dylint", "list"],
        cwd=LINT_DIR, capture_output=True, text=True, env=lint_env(),
    )
    if "dp_clippy" not in out.stdout:
        sys.exit(
            "NO LINT LOADED — `cargo dylint list` does not name dp_clippy.\n"
            f"  stdout: {out.stdout.strip()!r}\n"
            f"  stderr: {out.stderr.strip()!r}\n"
            "A run in this state EXITS 0 having linted nothing."
        )


def run_lint(args: list[str], cwd: Path) -> tuple[dict[str, int], set[str], str]:
    """Return (findings per package, packages that produced an artifact, stderr)."""
    proc = subprocess.run(
        ["cargo", "dylint", "--all", "--", *args, "--all-features",
         "--keep-going", "--message-format=json"],
        cwd=cwd, capture_output=True, text=True, env=lint_env(),
    )
    findings: dict[str, int] = {}
    compiled: set[str] = set()
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        pkg = pkg_name(msg.get("package_id", ""))
        if msg.get("reason") == "compiler-artifact" and pkg:
            compiled.add(pkg)
        elif msg.get("reason") == "compiler-message":
            body = msg.get("message") or {}
            if RULE_TAG in (body.get("message") or "") and pkg:
                findings[pkg] = findings.get(pkg, 0) + 1
                compiled.add(pkg)
    return findings, compiled, proc.stderr


def pkg_name(package_id: str) -> str:
    """`path+file:///…/crates/dp-kernel#0.1.0` -> `dp-kernel`.

    Cargo has used several package-id syntaxes; this handles the two that
    appear on the toolchains this repo pins, and returns "" rather than
    guessing when it recognises neither — an unattributed finding is loud
    (it can match no member) instead of silently credited to the wrong crate.
    """
    if not package_id:
        return ""
    head = package_id.split("#")[0]
    tail = package_id.split("#")[-1]
    # `…#dp-kernel@0.1.0` — the name is after the fragment.
    if "@" in tail and not tail[0].isdigit():
        return tail.split("@")[0]
    # `path+file:///…/crates/dp-kernel#0.1.0` — the name is the last path segment.
    return head.rstrip("/").split("/")[-1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write-baseline", action="store_true",
                    help="record the current red set as the baseline")
    ap.add_argument("--self-test", action="store_true",
                    help="check this gate's own invariants without compiling")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    assert_lint_loaded()

    meta = cargo_metadata()
    member_dirs = members(meta)
    exempt = {n for n, d in member_dirs.items() if declares_marker(d)}

    print(f"[dp-clippy] {len(member_dirs)} workspace members, "
          f"{len(exempt)} declaring dp-crate = true: {sorted(exempt)}")

    findings, compiled, stderr = run_lint(["--workspace"], REPO)

    # Failure mode 2 — a member that neither compiled nor reported is UNCHECKED.
    # Re-lint it alone before believing anything about it.
    unaccounted = sorted(set(member_dirs) - compiled - set(findings))
    if unaccounted:
        print(f"[dp-clippy] {len(unaccounted)} member(s) unaccounted for in the "
              f"workspace pass; re-linting individually: {unaccounted}")
    still_unchecked = []
    for name in unaccounted:
        f2, c2, _ = run_lint(["-p", name], REPO)
        if name in f2:
            findings[name] = f2[name]
        elif name not in c2:
            still_unchecked.append(name)

    # An exempt crate that still reports findings means the two independent
    # readers of the marker disagree (V.2).
    contradictions = sorted(set(findings) & exempt)

    if args.write_baseline:
        BASELINE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if BASELINE.exists():
            existing = json.loads(BASELINE.read_text(encoding="utf-8")).get("blocked", {})
        BASELINE.write_text(
            json.dumps({
                "known_red": dict(sorted(findings.items())),
                "blocked": dict(sorted(existing.items())),
            }, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"[dp-clippy] baseline written: {len(findings)} red crate(s), "
              f"{len(still_unchecked)} unchecked {sorted(still_unchecked)} "
              f"(blocked/ rows are NOT auto-written — each needs a named blocker)")
        return 0

    if not BASELINE.exists():
        sys.exit(f"no baseline at {BASELINE.relative_to(REPO)} — "
                 f"run with --write-baseline once, and commit it")
    doc = json.loads(BASELINE.read_text(encoding="utf-8"))
    known = doc["known_red"]
    # name -> the crate whose DP-R3 findings make this one unlintable.
    #
    # A crate that fails to compile cannot have its dependents checked, so a
    # red low-level crate HIDES every finding in everything above it. That is a
    # fact about today's tree, not a permission: each row names its blocker,
    # and the gate below verifies the blocker is STILL RED. The moment the
    # blocker is fixed the excuse expires and the row must go — which is what
    # stops this register becoming the quiet place where coverage goes to die.
    blocked = doc.get("blocked", {})

    fails: list[str] = []
    for name in sorted(still_unchecked):
        blocker = blocked.get(name)
        if blocker is None:
            fails.append(
                f"UNCHECKED: `{name}` produced neither findings nor a compiler "
                f"artifact, and no `blocked` row explains why. Unchecked is not "
                f"clean — see failure mode 2.")
        elif blocker not in findings:
            fails.append(
                f"EXPIRED EXCUSE: `{name}` is recorded as blocked by "
                f"`{blocker}`, but `{blocker}` has no DP-R3 findings now. "
                f"Delete the row and let `{name}` be checked.")
    for name, blocker in sorted(blocked.items()):
        if name not in still_unchecked:
            fails.append(
                f"BLOCKED STALE: `{name}` is checkable now (was blocked by "
                f"`{blocker}`). Delete its row — the register shrinks or it rots.")
    for name in contradictions:
        fails.append(
            f"MARKER DISAGREEMENT: `{name}` declares dp-crate = true but the "
            f"lint still reported {findings[name]} finding(s) in it.")
    for name, n in sorted(findings.items()):
        if name in exempt:
            continue
        prev = known.get(name)
        if prev is None:
            fails.append(f"NEW RED: `{name}` has {n} DP-R3 finding(s) and is not "
                         f"in the baseline. Route it through the `dp` SDK, or — "
                         f"if it IS the data plane — declare the marker.")
        elif n > prev:
            fails.append(f"WORSE: `{name}` went {prev} -> {n} DP-R3 finding(s).")
    for name, prev in sorted(known.items()):
        now = findings.get(name, 0)
        if now == 0:
            fails.append(f"BASELINE STALE: `{name}` is clean now (was {prev}). "
                         f"Delete its row — the baseline shrinks or it rots.")
        elif now < prev:
            fails.append(f"BASELINE STALE: `{name}` improved {prev} -> {now}. "
                         f"Lower its row so the ratchet holds the gain.")

    total = sum(n for k, n in findings.items() if k not in exempt)
    print(f"[dp-clippy] {total} DP-R3 finding(s) across "
          f"{len([k for k in findings if k not in exempt])} crate(s)")
    for name, n in sorted(findings.items()):
        mark = "exempt" if name in exempt else f"{n} finding(s)"
        print(f"    {name}: {mark}")

    if fails:
        print("\nFAIL:")
        for f in fails:
            print(f"  - {f}")
        if stderr.strip():
            print("\n(cargo stderr tail)")
            print("\n".join(stderr.strip().splitlines()[-8:]))
        return 1
    print("[dp-clippy] OK — matches the baseline exactly")
    return 0


def self_test() -> int:
    """Invariants of this file that do not need a compile.

    Cheap enough to run in the shared gate sweep, where a full dylint pass
    would not fit.
    """
    fails = []

    cases = {
        "path+file:///d/repo/crates/dp-kernel#0.1.0": "dp-kernel",
        "path+file:///d/repo/crates/dp#dp@0.1.0": "dp",
        "registry+https://github.com/rust-lang/crates.io-index#serde@1.0": "serde",
        "": "",
    }
    for pid, want in cases.items():
        got = pkg_name(pid)
        if got != want:
            fails.append(f"pkg_name({pid!r}) = {got!r}, want {want!r}")

    if not LINT_DIR.is_dir():
        fails.append(f"lint crate missing: {LINT_DIR}")
    runner = LINT_DIR / "run-lint.sh"
    if not runner.is_file():
        fails.append(f"runner missing: {runner}")
    elif "--all-features" not in runner.read_text(encoding="utf-8"):
        fails.append("run-lint.sh no longer passes --all-features; meta-rs's "
                     "sqlx-pg module would go unlinted (NV-3 at the feature level)")

    if BASELINE.exists():
        data = json.loads(BASELINE.read_text(encoding="utf-8"))
        if "known_red" not in data:
            fails.append("baseline has no known_red key")
        for name, n in data.get("known_red", {}).items():
            if not isinstance(n, int) or n <= 0:
                fails.append(f"baseline row {name!r} = {n!r}; a row means "
                             f"'this many findings are waiting', so 0 is a "
                             f"deleted row, not a recorded one")

    for f in fails:
        print(f"FAIL: {f}")
    if fails:
        return 1
    print("[dp-clippy-gate] self-test OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
