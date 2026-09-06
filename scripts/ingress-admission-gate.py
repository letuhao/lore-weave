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


def rel(path: str, repo: str = REPO) -> str:
    return os.path.relpath(path, repo).replace("\\", "/")


def is_test_or_bench(p: str) -> bool:
    return (
        "/tests/" in p
        or p.endswith("_test.rs")
        or "/benches/" in p
        or "/src/bin/bench.rs" in p
        or "/src/bin/stress.rs" in p
    )


def rust_files(repo: str = REPO):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", "target", "node_modules", ".claude", "dist"}
        ]
        for f in files:
            if f.endswith(".rs"):
                yield os.path.join(root, f)


def cargo_files(repo: str = REPO):
    for root, dirs, files in os.walk(repo):
        dirs[:] = [
            d
            for d in dirs
            if d not in {".git", "target", "node_modules", ".claude", "dist"}
        ]
        for f in files:
            if f == "Cargo.toml":
                yield os.path.join(root, f)


def check(repo: str = REPO, admit_allowed=ADMIT_ALLOWED,
          testutil_allowed=TESTUTIL_NORMAL_DEP_ALLOWED) -> int:
    """The REAL checker, parameterised so `--self-test` can drive it over a
    synthetic tree instead of re-implementing its rules."""
    findings: list[str] = []
    n_rs = n_toml = 0
    subjects = {"admit": 0, "unchecked": 0, "testutil": 0}
    admit_used: set[str] = set()
    testutil_used: set[str] = set()

    for path in rust_files(repo):
        n_rs += 1
        p = rel(path, repo)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        for n, line in enumerate(lines, 1):
            if line.lstrip().startswith("//"):
                continue  # a doc/comment mention is documentation, not a call
            if RE_ADMIT.search(line):
                subjects["admit"] += 1
                if p in admit_allowed:
                    admit_used.add(p)
                else:
                    findings.append(
                        f"  {p}:{n}  [second-minter]  Admitted::admit outside the admission module\n"
                        f"      → route this through admission; a second mint point restores the bypass"
                    )
            if RE_UNCHECKED.search(line):
                subjects["unchecked"] += 1
                if not is_test_or_bench(p):
                    findings.append(
                        f"  {p}:{n}  [unchecked-in-service]  Admitted::unchecked outside a test/bench\n"
                        f"      → the test escape hatch is not an admission path"
                    )

    for path in cargo_files(repo):
        n_toml += 1
        p = rel(path, repo)
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        # Split at [dev-dependencies]; anything before it is a normal dep.
        head = re.split(r"^\[dev-dependencies\]", text, maxsplit=1, flags=re.M)[0]
        if RE_TESTUTIL.search(text):
            subjects["testutil"] += 1
        if RE_TESTUTIL.search(head):
            if p in testutil_allowed:
                testutil_used.add(p)
            else:
                findings.append(
                    f"  {p}  [test-util-as-normal-dep]  'test-util' enabled outside [dev-dependencies]\n"
                    f"      → a shipped binary would gain Admitted::unchecked and lose the compile-time guarantee"
                )

    # ── SUBJECT FLOORS (GT-F3). Not a file count — zero files implies zero
    # subjects, so a file floor would be strictly shadowed. What can actually go
    # wrong is the TYPE being renamed: `Admitted` becomes something else, all
    # three patterns match nothing, and the gate reports that admission is the
    # sole minter of a token nobody mints. Measured 2026-08-12: 2 mint calls,
    # 85 unchecked calls, 5 `test-util` feature references.
    for key, what in (("admit", "Admitted::admit"),
                      ("unchecked", "Admitted::unchecked"),
                      ("testutil", "a `test-util` feature reference")):
        if subjects[key] == 0:
            print(f"ingress-admission-gate: ERROR — {n_rs} .rs / {n_toml} Cargo.toml scanned and "
                  f"NOT ONE contains {what}. The detector has no subject, so 'admission is the "
                  f"sole minter' is a claim about nothing (BDR-82).", file=sys.stderr)
            return 2

    # ── SHRINK ARMS (GT-F5). Both allowlists are single-row and load-bearing:
    # one names the ONLY sanctioned minter, the other the ONLY crate allowed to
    # take `test-util` as a normal dependency. A row that stops matching is a
    # standing waiver on that path.
    for row in sorted(set(admit_allowed) - admit_used):
        findings.append(
            f"  {row}  [dead-exemption]  ADMIT_ALLOWED names a file that mints nothing\n"
            f"      → the sanctioned minter moved; this row now waives that path for whatever "
            f"appears there next"
        )
    for row in sorted(set(testutil_allowed) - testutil_used):
        findings.append(
            f"  {row}  [dead-exemption]  TESTUTIL_NORMAL_DEP_ALLOWED names a manifest that does "
            f"not take test-util as a normal dep\n"
            f"      → reason: {testutil_allowed[row]}"
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

    print(f"ingress-admission-gate: OK — admission is the sole minter "
          f"({n_rs} .rs, {n_toml} Cargo.toml; {subjects['admit']} mint call(s), "
          f"{subjects['unchecked']} unchecked call(s), {subjects['testutil']} test-util ref(s))")
    return 0


# ── SELF-TEST ────────────────────────────────────────────────────────────────
ADMIT_SRC = "let t = Admitted::admit(d);\n"
UNCHECKED_SRC = "let t = Admitted::unchecked(d);\n"
TOML_DEV = '[dependencies]\nsim-core = { path = "../sim-core" }\n\n[dev-dependencies]\nsim-core = { path = "../sim-core", features = ["test-util"] }\n'
TOML_NORMAL = '[dependencies]\nsim-core = { path = "../sim-core", features = ["test-util"] }\n'


def self_test() -> int:
    import contextlib
    import io
    import tempfile

    failures = 0
    AD = "services/commit-service/src/admission.rs"
    SIM = "crates/sim/Cargo.toml"

    def probe(name, want, files, *, admit_allowed=None, testutil_allowed=None, seed=True):
        nonlocal failures
        with tempfile.TemporaryDirectory() as d:
            if seed:
                # every tree carries one of EACH subject, so the three floors stay
                # quiet and a probe tests exactly one rule
                files = {AD: ADMIT_SRC,
                         "crates/k/tests/t.rs": UNCHECKED_SRC,
                         SIM: TOML_NORMAL,
                         **files}
            for r, body in files.items():
                full = os.path.join(d, *r.split("/"))
                os.makedirs(os.path.dirname(full), exist_ok=True)
                with open(full, "w", encoding="utf-8") as fh:
                    fh.write(body)
            try:
                with contextlib.redirect_stdout(io.StringIO()), \
                        contextlib.redirect_stderr(io.StringIO()):
                    got = check(d,
                                {AD} if admit_allowed is None else admit_allowed,
                                {SIM: "the harness"} if testutil_allowed is None
                                else testutil_allowed)
            except Exception as e:  # noqa: BLE001
                failures += 1
                print(f"  FAIL {name}: raised {type(e).__name__}: {e}")
                return
        ok = got == want
        failures += 0 if ok else 1
        print(f"  {'ok  ' if ok else 'FAIL'} {name}: rc={got} (want {want})")

    print("ingress-admission-gate --self-test")

    probe("a sanctioned tree passes", 0, {})

    # rule 1 — the second minter
    probe("Admitted::admit outside the admission module fails", 1, {
        "services/other/src/mint.rs": ADMIT_SRC})
    probe("...but a COMMENT mentioning it does not", 0, {
        "services/other/src/mint.rs": "// let t = Admitted::admit(d);\n"})

    # rule 2 — the test escape hatch
    probe("Admitted::unchecked in a service source fails", 1, {
        "services/other/src/run.rs": UNCHECKED_SRC})
    probe("...but in tests/ it does not", 0, {"crates/k/tests/more.rs": UNCHECKED_SRC})
    probe("...nor in a _test.rs", 0, {"crates/k/src/thing_test.rs": UNCHECKED_SRC})
    probe("...nor in benches/", 0, {"crates/k/benches/b.rs": UNCHECKED_SRC})

    # rule 3 — test-util as a normal dependency
    probe("test-util as a NORMAL dep fails", 1, {"crates/other/Cargo.toml": TOML_NORMAL})
    probe("...but under [dev-dependencies] it does not", 0, {
        "crates/other/Cargo.toml": TOML_DEV})

    # the shrink arms
    probe("an ADMIT_ALLOWED row that mints nothing fails", 1, {},
          admit_allowed={AD, "services/ghost/src/admission.rs"})
    probe("a TESTUTIL_NORMAL_DEP_ALLOWED row that takes no test-util fails", 1, {},
          testutil_allowed={SIM: "the harness", "crates/ghost/Cargo.toml": "gone"})

    # the subject floors
    probe("a tree with no mint call at all is misuse", 2, {
        "crates/k/tests/t.rs": UNCHECKED_SRC, SIM: TOML_NORMAL}, seed=False,
        admit_allowed=set())
    probe("a tree with no unchecked call at all is misuse", 2, {
        AD: ADMIT_SRC, SIM: TOML_NORMAL}, seed=False)
    probe("a tree with no test-util reference at all is misuse", 2, {
        AD: ADMIT_SRC, "crates/k/tests/t.rs": UNCHECKED_SRC}, seed=False,
        testutil_allowed={})

    if failures:
        print(f"ingress-admission-gate --self-test: {failures} rule(s) did not behave")
        return 2
    print("ingress-admission-gate --self-test: every rule bites, and none cries wolf")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()
    rc = self_test()
    if rc:
        return rc
    print()
    return check()


if __name__ == "__main__":
    sys.exit(main())
