#!/usr/bin/env python3
"""dp-aggregate-gate — ONE aggregate name binds ONE tier and ONE scope.

**This file used to BE the check. It is now the RUNNER for it, and the reason is
the whole story of slice 1.**

`V1-F1` established that the type system cannot hold this property: each
monomorphisation is individually consistent and the contradiction lives *across*
them, which is the one comparison a type checker never makes. The conclusion
drawn was *"so check it over the source"* — and the source check was a
hand-rolled Rust lexer, in Python, here.

**Three rounds of cold-start refutation broke that lexer eleven times.** Round 1
found the property unguarded. Round 2 got six spellings of a generic past the
first implementation. Round 3 got four more past the rewrite — and its verdict
is the one that settled the design:

    R6's closure argument is sound as a statement about Rust; its three
    implementations are not. "What the impl binds" is `impl_generics()`, which
    drops parameters two ways; "the right-hand side of `type Tier`" is a
    `re.search` over text that still contains string literals; "the impl exists"
    is a hand-rolled lexer that does not know one Rust literal form.

Each of those four is a fact about **Rust's grammar** that a partial
reimplementation of that grammar got wrong: the `>` of `->` in an `Fn` bound
closing the generic list, `r#T2` not matching an identifier pattern, a
`#[doc = "type Tier = T2;"]` attribute read instead of the real associated type,
and `cr#".."#` C-strings desyncing quote parity so an impl vanished **silently**.

Patching the eleventh was not a strategy; the seventh already wasn't. So the
check moved to where the grammar is already correct — **`syn`, in
`crates/dp/tests/aggregate_contract.rs`** — and every one of round 3's
reproductions is caught there by `R6` with no special case, because a doc
attribute is an `Attribute`, `r#T2` and `T2` are one `Ident`, and `Fn() -> u8`
is a `TypeBareFn` inside a `TraitBound`.

**Two checks for one property, one of them known-defeatable, is the mirror
defect this repo already has a gate about** (`projection-table-mirror-gate`).
So there is one implementation, and this file exists only to give it the
pre-commit and CI wiring it already had.

Run: ``python scripts/dp-aggregate-gate.py`` — wired pre-commit and, via
`gate-wiring-gate --run-all`, in `gates.yml` on every branch.
Exit 0 = clean; 1 = findings; 2 = the check could not be run.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
TEST = "one_aggregate_name_binds_one_tier_and_one_scope"
CONTRACT = REPO / "crates" / "dp" / "tests" / "aggregate_contract.rs"

CARGO = ["cargo", "test", "-q", "-p", "dp", "--test", "aggregate_contract"]


def run_contract(extra: list[str] | None = None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            CARGO + (extra or []), cwd=REPO, capture_output=True, text=True,
            encoding="utf-8", errors="replace",
        )
    except OSError as e:
        return 2, f"cannot run cargo: {e}"
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def self_test() -> int:
    """Prove the runner is pointed at a check that EXISTS and CAN FAIL.

    A runner's self-test has exactly two things to establish, and the second is
    the one `V2-F1` was about: it is not enough that the subject is green, it
    must be **capable of red**. So this plants the original `V1-F1` escape in
    the tree, requires the contract to fail on it, and removes it.

    That is slower than asserting on strings and it is the only version worth
    having: the previous self-test here re-implemented the rules inline and
    stayed green while the real path was gutted.
    """
    bad = []

    if not CONTRACT.is_file():
        print(f"dp-aggregate-gate: SELF-TEST FAIL — {CONTRACT} does not exist", file=sys.stderr)
        return 1
    src = CONTRACT.read_bytes().decode("utf-8")
    for needed in ("fn " + TEST, "syn::parse_file", "FIXTURE_DIR"):
        if needed not in src:
            bad.append(f"the contract no longer contains {needed!r}")

    probe = REPO / "crates" / "dp" / "tests" / "_gate_selftest_probe.rs"
    if probe.exists():
        bad.append(f"{probe.name} already exists — refusing to overwrite it")
    else:
        probe.write_bytes(
            b"//! Transient self-test probe, written and removed by "
            b"scripts/dp-aggregate-gate.py.\n"
            b"use dp::{DpAggregate, Scope, Tier};\n"
            b"pub struct SelfTestWallet<T, S>(core::marker::PhantomData<(T, S)>);\n"
            b"impl<T: Tier, S: Scope> DpAggregate for SelfTestWallet<T, S> {\n"
            b"    type Tier = T;\n"
            b"    type Scope = S;\n"
            b"    type Id = u64;\n"
            b"    const TYPE_NAME: &'static str = \"self_test_wallet\";\n"
            b"}\n"
        )
        try:
            code, out = run_contract()
            if code == 0:
                bad.append("the contract ACCEPTED the V1-F1 generic escape — it cannot fail")
            elif "R6" not in out:
                bad.append("the contract reddened without naming R6 — right answer, wrong rule")
        finally:
            probe.unlink(missing_ok=True)

    if bad:
        print("dp-aggregate-gate: SELF-TEST FAIL")
        for b in bad:
            print("  " + b)
        return 1
    print("dp-aggregate-gate: SELF-TEST PASS — the contract exists, parses with `syn`, and REDS "
          "by R6 on a planted V1-F1 generic escape (proved by running it, not by reading it)")
    return 0


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()

    code, out = run_contract(["--", "--nocapture"])
    if code == 0:
        line = next((ln for ln in out.splitlines() if ln.startswith("aggregate-contract:")), "")
        print(line or "dp-aggregate-gate: OK")
        return 0

    # A compile/toolchain failure is NOT a finding about the tree, and saying so
    # is the `V1-F7` lesson: "the guard is weak" and "the harness broke" are two
    # different sentences and must not share one.
    if "error[E" in out or "could not compile" in out:
        print("dp-aggregate-gate: the contract could not be BUILT — this is a toolchain or "
              "compile failure, not a finding about aggregates:", file=sys.stderr)
        print("\n".join(out.strip().splitlines()[-25:]), file=sys.stderr)
        return 2

    print(out.strip())
    print("\ndp-aggregate-gate: the contract FAILED — see the findings above. The check lives in "
          "crates/dp/tests/aggregate_contract.rs and is enforced over a real Rust AST.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
