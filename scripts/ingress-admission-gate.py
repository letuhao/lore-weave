#!/usr/bin/env python3
"""IAS-D3 gate — the call-site half of the admission proof token.

`Island::submit` takes `Admitted<D>`, whose field is private, so a caller
cannot assemble one: that is the TYPE half, and it is what makes an admission
bypass a compile error in a release build. But `Admitted::admit` must be `pub`
(admission lives in `commit-service`, a different crate from `sim-core`, so
Rust visibility alone cannot restrict it), and `Admitted::unchecked` exists
under the `test-util` feature for kernel tests that drive the scheduler with no
rules pipeline.

This gate covers what the type system cannot:

  * `Admitted::admit` may only be called from the sanctioned admission module.
    A second minter elsewhere would restore the very bypass IAS-D3 removed —
    silently, and with a name that reads like it did the right thing.
  * `Admitted::unchecked` may only appear in tests and benches. In a service
    source file it is a bypass wearing the test escape hatch.
  * `features = ["test-util"]` may only appear as a DEV dependency. Enabling it
    for a normal dependency would hand a shipped binary the unchecked mint and
    quietly delete the compile-time guarantee, while every test stayed green.

Exit 0 clean, 1 on a finding. Wired into `.githooks/pre-commit`.
"""

from __future__ import annotations

import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The one module allowed to mint a production token.
ADMIT_ALLOWED = {"services/commit-service/src/admission.rs"}

# Crates that are THEMSELVES test tooling, so `test-util` is their normal
# dependency rather than a leak into a shipped artifact. Each entry needs a
# reason; the point of the gate is that this list stays short and argued.
TESTUTIL_NORMAL_DEP_ALLOWED = {
    # `crates/sim` is the sim-core test/chaos harness (`publish = false`); its
    # binaries ARE the measurement tooling, so they need the mint at build
    # time and cannot take it from [dev-dependencies]. Nothing ships from here.
    "crates/sim/Cargo.toml": "sim-core test/chaos harness — publish = false, ships nothing",
}

RE_ADMIT = re.compile(r"\bAdmitted::admit\s*\(")
RE_UNCHECKED = re.compile(r"\bAdmitted::unchecked\s*\(")
# `sim-core = { path = ..., features = [... "test-util" ...] }`
RE_TESTUTIL = re.compile(r'features\s*=\s*\[[^\]]*"test-util"')


def rel(path: str) -> str:
    return os.path.relpath(path, REPO).replace("\\", "/")


def is_test_or_bench(p: str) -> bool:
    return (
        "/tests/" in p
        or p.endswith("_test.rs")
        or "/benches/" in p
        or "/src/bin/bench.rs" in p
        or "/src/bin/stress.rs" in p
    )


def rust_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", "target", "node_modules", ".claude", "dist"}
        ]
        for f in files:
            if f.endswith(".rs"):
                yield os.path.join(root, f)


def cargo_files():
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", "target", "node_modules", ".claude", "dist"}
        ]
        for f in files:
            if f == "Cargo.toml":
                yield os.path.join(root, f)


def main() -> int:
    findings: list[str] = []

    for path in rust_files():
        p = rel(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("//"):
                continue  # a doc/comment mention is documentation, not a call
            if RE_ADMIT.search(line) and p not in ADMIT_ALLOWED:
                findings.append(
                    f"  {p}:{n}  [second-minter]  Admitted::admit outside the admission module\n"
                    f"      → route this through admission; a second mint point restores the bypass"
                )
            if RE_UNCHECKED.search(line) and not is_test_or_bench(p):
                findings.append(
                    f"  {p}:{n}  [unchecked-in-service]  Admitted::unchecked outside a test/bench\n"
                    f"      → the test escape hatch is not an admission path"
                )

    for path in cargo_files():
        p = rel(path)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        # Split at [dev-dependencies]; anything before it is a normal dep.
        head = re.split(r"^\[dev-dependencies\]", text, maxsplit=1, flags=re.M)[0]
        if RE_TESTUTIL.search(head) and p not in TESTUTIL_NORMAL_DEP_ALLOWED:
            findings.append(
                f"  {p}  [test-util-as-normal-dep]  'test-util' enabled outside [dev-dependencies]\n"
                f"      → a shipped binary would gain Admitted::unchecked and lose the compile-time guarantee"
            )

    if findings:
        print("ingress-admission-gate: FAIL")
        for f in findings:
            print(f)
        print(
            "\n  IAS-D3 (docs/03_planning/LLM_MMO_RPG/22_ingress_and_admission.md):\n"
            "  the island accepts only a token admission mints."
        )
        return 1

    print("ingress-admission-gate: OK — admission is the sole minter")
    return 0


if __name__ == "__main__":
    sys.exit(main())
