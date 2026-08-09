#!/usr/bin/env python3
"""dp-slice5c-bite-gate — the guards `5C` puts on the gRPC surface, each removed.

`5C` is a transport, and a transport's guards are the easiest in the repo to
ship broken and green: a status code is still a status code when it is the wrong
one, and a validation skipped on the wire is invisible to every in-process test.
So each is removed here and shown to leak.

THE MACHINERY IS `dp-slice5b-bite-gate`'s, IMPORTED RATHER THAN COPIED
----------------------------------------------------------------------
That harness already solved the parts that are easy to get wrong — reading and
restoring as BYTES so a Windows restore does not silently rewrite every line
ending (`V1-F8`), proving the restore by digest instead of trusting the
`finally`, and the four-way `pass`/`fail`/`nobuild`/`missing` verdict that stops
a mutation which merely broke the build from scoring as a bite. Copying it would
mean two copies drifting; a second file named `-gate` that re-implemented it
badly would be worse than no second file.

`importlib` because the module name has dashes and cannot be `import`ed.

WHAT THIS FILE ADDS OVER 5B's
------------------------------
Its witnesses are INTEGRATION tests (`tests/surface.rs`), not lib tests, so the
runner is `cargo test -p dp-control-plane --test surface`. Every one of them
binds a real TCP port and speaks real gRPC — a guard that only holds in-process
is not a guard on a transport.

Exit 0 = every bite bit; 1 = one did not.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_5b():
    """Import the sibling harness by path, since its name has dashes."""
    path = REPO / "scripts" / "dp-slice5b-bite-gate.py"
    if not path.exists():
        print(f"dp-slice5c-bite-gate: MISUSE — {path} is missing; this harness reuses its "
              "read/restore/verdict machinery", file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("dp_slice5b_bite_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_5b()

SERVER = REPO / "crates" / "dp-control-plane" / "src" / "server.rs"
LIB = REPO / "crates" / "dp-control-plane" / "src" / "lib.rs"


def surface_outcome(test_name: str) -> tuple[str, str]:
    """Run ONE integration test in `tests/surface.rs`. Same four-way verdict."""
    p = subprocess.run(
        ["cargo", "test", "-p", "dp-control-plane", "--test", "surface", test_name,
         "--", "--exact"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    if "error: could not compile" in out or "error[E" in out:
        return "nobuild", out
    if "running 0 tests" in out:
        return "missing", out
    if "test result: ok" in out:
        return "pass", out
    if "test result: FAILED" in out:
        return "fail", out
    return "nobuild", out


def bite(label: str, path: Path, find: str, replace: str, test_name: str) -> bool:
    print(f"\n{'=' * 74}\nBITE {label}\n{'=' * 74}")
    print(f"  guard    : {path.relative_to(REPO)}")
    print(f"  witness  : dp-control-plane :: surface::{test_name}")

    before, out = surface_outcome(test_name)
    print(f"  baseline : {before}  (expected pass)")
    if before != "pass":
        print(f"  x {label}: the witness does not pass BEFORE the mutation")
        print(out[-1500:])
        return False

    original = B.read_txt(path)
    if find not in original:
        print(f"  x {label}: MISUSE — anchor not found in {path.name}: {find[:70]!r}")
        return False
    mutated = original.replace(find, replace, 1)
    if mutated == original:
        print(f"  x {label}: MISUSE — mutation produced identical text")
        return False

    ok = False
    try:
        B.write_txt(path, mutated)
        after, out = surface_outcome(test_name)
        print(f"  mutated  : guard removed -> {after}  (expected fail)")
        if after == "nobuild":
            print(f"  x {label}: the mutation broke the BUILD — the red proves nothing")
        elif after == "missing":
            print(f"  x {label}: the witness did not RUN under mutation")
        elif after == "pass":
            print(f"  x {label}: THE GUARD IS NOT LOAD-BEARING — removed, witness still passes")
        else:
            print(f"  red      : {B._first_failure_line(out)}")
            ok = True
    finally:
        B.write_txt(path, original)

    if not B.restored_byte_identical(path, original, label):
        return False

    after_restore, _ = surface_outcome(test_name)
    print(f"  restored : {after_restore}  (expected pass)")
    if after_restore != "pass":
        print(f"  x {label}: the witness does not pass after restore — the tree is not back")
        return False
    return ok


LEGS = [
    (
        "[wire] the server validates service_identity rather than trusting the field",
        SERVER,
        'let service = dp::ServiceIdentity::new(req.service_identity.clone()).ok_or_else(|| {',
        'let service = dp::ServiceIdentity::new(req.service_identity.clone())\n            .or_else(|| dp::ServiceIdentity::new("anonymous"))\n            .ok_or_else(|| {',
        "the_wire_refuses_a_service_identity_the_library_would_refuse",
    ),
    (
        "[wire] a rejected capability does not reveal WHICH kind of wrong it was",
        SERVER,
        'Status::unauthenticated("capability is not valid")',
        "Status::unauthenticated(format!(\"capability is not valid: {}\", e))",
        "a_forged_capability_is_refused_without_saying_which_kind_of_wrong_it_is",
    ),
    (
        "[surface] UNIMPLEMENTED_METHODS matches what the server actually refuses",
        LIB,
        '    ("GetNpcNode", "npc_binding (DP-C2) has no migration in this repo"),',
        "",
        "every_unimplemented_method_says_so_and_no_other_does",
    ),
    (
        "[surface] an UNIMPLEMENTED method names the state that is missing",
        SERVER,
        'Some(why) => Status::unimplemented(format!("{method}: {why}")),',
        "Some(_) => Status::unimplemented(String::new()),",
        "every_unimplemented_method_says_so_and_no_other_does",
    ),
    (
        "[wire] an absent reality is NOT_FOUND to resolve, not an empty row",
        SERVER,
        # NOT `.unwrap_or_default()` — that was tried first and did not COMPILE
        # (`RealityRouting` has no `Default`), so the harness refused to score
        # it, which is the four-way verdict doing its job. The guard under test
        # is the CHOICE of status code, so the mutation changes the code and
        # leaves the shape alone.
        'Status::not_found(format!("no such reality: {reality}"))',
        'Status::internal(format!("no such reality: {reality}"))',
        "an_absent_reality_is_a_plain_answer_to_verify_and_not_found_to_resolve",
    ),
    (
        "[wire] the deploy cohort survives the widening rather than being defaulted",
        SERVER,
        "deploy_cohort: u32::from(routing.deploy_cohort),",
        "deploy_cohort: 0,",
        "resolve_reality_carries_the_registry_row_across_the_wire",
    ),
    (
        "[wire] an unbound session answers `assigned = false`, not an empty node name",
        SERVER,
        "None => pb::NodeAssignment { node_id: String::new(), assigned: false },",
        "None => pb::NodeAssignment { node_id: String::new(), assigned: true },",
        "a_session_binds_over_the_wire_and_the_client_is_a_real_control_plane",
    ),
]


def main() -> int:
    print("dp-slice5c-bite-gate — the gRPC surface's guards, each one removed\n")
    results = [bite(*leg) for leg in LEGS]

    print(f"\n{'=' * 74}")
    bitten = sum(1 for r in results if r)
    for (label, *_), ok in zip(LEGS, results):
        print(f"  {'ok' if ok else ' x'}  {label}")
    print(f"\n  bitten: {bitten}/{len(LEGS)}")

    if bitten != len(LEGS):
        print("\ndp-slice5c-bite-gate: FAIL — a guard was removed and nothing noticed.")
        return 1
    print("\ndp-slice5c-bite-gate: OK — every listed guard is load-bearing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
