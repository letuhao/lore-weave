#!/usr/bin/env python3
"""dp-df1a-bite-gate — the guards `DF1a` puts on the CHANNEL write path.

`DF1a` gave the write surface the half it never had. `04b §10` specifies *"two
forms per primitive: one for `RealityScoped`, one for `ChannelScoped`"*; the
read side shipped both and the write side shipped one, so `WriteRequest` had
seven fields and none of them was a channel. A channel-scoped write therefore
could not be expressed — and, worse, did not FAIL: `write_at_tier` bounded
`Tier` and not `Scope`, so the aggregate went down the reality path and produced
an event with `channel_id = NULL`, which `0014_channel_ordering.up.sql` defines
as a legitimate reality-scoped event that no channel subscriber reads.

The guards below are what make that unrepresentable now. Each looks like a small
conditional and none of them is: every one of them is the difference between a
write landing on its channel and a write landing nowhere anyone is listening.

MACHINERY IMPORTED FROM `dp-slice5b-bite-gate`, for the reason 5c and 5d both
give: the read/restore/digest parts are already solved there, and a fourth copy
would be a fourth thing to drift.

WHAT IS NOT BITEABLE HERE, AND WHERE EACH IS PROVEN INSTEAD
------------------------------------------------------------
* the two WRITE scope bounds (`t2_write` refusing a channel-scoped aggregate,
  `t2_write_channel` refusing a reality-scoped one) — those are type errors, so
  removing them changes what COMPILES, not what a test asserts.
  `crates/dp/tests/ui/write_wrong_scope.rs` and
  `channel_write_wrong_scope.rs` pin both directions via trybuild, and their
  bite is `dp-slice1-bite-gate`'s compile-fail shape. Bitten by hand at DF1a
  with the red pasted into the run-state: *"Expected test case to fail to
  compile, but it succeeded."*
* `DP-Ch14` cross-node routing — `route_to_writer` is NOT BUILT, so there is no
  guard to remove. `KernelChannelWriteBackend`'s wrong-channel refusal (leg 3)
  is the thing standing in its place, and that IS bitten.

A NOTE ON WHY `write_txt` AND NOT `shutil.copy2`
------------------------------------------------------------
The first version of this harness restored with `shutil.copy2`, which preserves
mtime. The restored file therefore looked OLDER than the artifact built from the
mutant, cargo skipped the rebuild, and step 5 re-ran the MUTANT binary while the
sha256 check happily reported BYTE-EXACT. Four arms scored "did not return to
green" and one scored a false baseline failure. A verification that is silently
wrong is worse than one that fails.

`dp-slice5b-bite-gate.write_txt` uses `path.write_bytes`, which stamps a fresh
mtime, so importing it is not only DRY — it is the fix.

Requires `LOREWEAVE_TEST_PG_URL`; SKIPS (exit 0, loudly) when unset, because the
witnesses are PG-gated and a harness that scored them green with no database
would be the vacuity this file exists to refuse.

Exit 0 = every bite bit (or a stated skip); 1 = one did not.
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_5b():
    path = REPO / "scripts" / "dp-slice5b-bite-gate.py"
    if not path.exists():
        print(f"dp-df1a-bite-gate: MISUSE — {path} is missing; this harness reuses its "
              "read/restore/verdict machinery", file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("dp_slice5b_bite_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_5b()

WRITE = REPO / "crates" / "dp" / "src" / "write.rs"
CHAN = REPO / "crates" / "dp-kernel" / "src" / "dp_channel.rs"
SUITE = "integration_dp_channel"


def outcome(test_name: str) -> tuple[str, str]:
    """Run ONE test of the dp-kernel channel suite."""
    p = subprocess.run(
        ["cargo", "test", "-p", "dp-kernel", "--test", SUITE, test_name, "--", "--exact"],
        cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (p.stdout or "") + (p.stderr or "")
    if "error: could not compile" in out or "error[E" in out:
        return "nobuild", out
    if "running 0 tests" in out:
        return "missing", out
    # The suite SKIPS when the DSN is unset, and a skip prints `ok`. The caller
    # guarantees the DSN is set before any leg runs, so this is unambiguous.
    if "test result: ok" in out:
        return "pass", out
    if "test result: FAILED" in out:
        return "fail", out
    return "nobuild", out


def bite(label: str, path: Path, find: str, replace: str, test_name: str, marker: str) -> bool:
    """Six steps. A red that does not name `marker` is a WRONG-REASON red.

    The marker check is the part `V1-F3` and `BDR-50`/`BDR-56` are about: a red
    for an unrelated reason is the failure mode that looks most like success.
    Two of this harness's five legs red for a DIFFERENT assertion than the one
    aimed at (the mutant reaches the pool instead of the guard), and one is
    caught by `move_to_channel`'s own cycle check rather than its witness's
    assertion — each marker below is the message that ACTUALLY appears, verified
    by running it, not the one that seemed likely.
    """
    print(f"\n{'=' * 74}\nBITE {label}\n{'=' * 74}")
    print(f"  guard    : {path.relative_to(REPO)}")
    print(f"  witness  : dp-kernel :: {SUITE} :: {test_name}")

    before, out = outcome(test_name)
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
        after, out = outcome(test_name)
        print(f"  mutated  : guard removed -> {after}  (expected fail)")
        if after == "nobuild":
            print(f"  x {label}: the mutation broke the BUILD — the red proves nothing")
        elif after == "missing":
            print(f"  x {label}: the witness did not RUN under mutation")
        elif after == "pass":
            print(f"  x {label}: THE GUARD IS NOT LOAD-BEARING — removed, witness still passes")
        elif marker not in out:
            print(f"  x {label}: WRONG-REASON red — it does not name {marker!r}")
            print(f"      {B._first_failure_line(out)}")
        else:
            print(f"  red      : {B._first_failure_line(out)}")
            print(f"  names    : {marker!r}")
            ok = True
    finally:
        B.write_txt(path, original)

    if not B.restored_byte_identical(path, original, label):
        return False

    after_restore, _ = outcome(test_name)
    print(f"  restored : {after_restore}  (expected pass)")
    if after_restore != "pass":
        print(f"  x {label}: the witness does not pass after restore — the tree is not back")
        return False
    return ok


LEGS = [
    (
        "[dp] the session's channel actually TRAVELS into WriteRequest",
        WRITE,
        "        channel: Some(channel),",
        "        channel: None,",
        "a_channel_write_through_the_sdk_lands_on_the_channel",
        "reached the CHANNEL backend",
    ),
    (
        "[kernel] the channel backend refuses a request carrying NO channel",
        CHAN,
        "        let Some(channel) = req.channel else {",
        "        let Some(channel) = req.channel.or(Some(self.writer.lease().channel_id)) else {",
        "the_channel_backend_refuses_a_request_with_no_channel",
        # The mutant still Errs (the lazy pool cannot connect), so `expect_err`
        # succeeds and the red is the VARIANT assertion under it.
        "refused by naming the missing address",
    ),
    (
        "[kernel] a write for ANOTHER channel is refused, not re-addressed",
        CHAN,
        "        if channel != held {",
        "        if false && channel != held {",
        "the_channel_backend_refuses_another_channels_write",
        "the refusal names BOTH channels",
    ),
    (
        "[kernel] the tree refuses a DISSOLVED channel",
        CHAN,
        "        if dissolved_at.is_some() {",
        "        if false && dissolved_at.is_some() {",
        "the_tree_refuses_a_dissolved_channel",
        "must refuse",
    ),
    (
        "[kernel] ancestors EXCLUDE the channel itself",
        CHAN,
        "            ancestors: rows[..rows.len() - 1].iter().map(|&(id, _, _)| id).collect(),",
        "            ancestors: rows.iter().map(|&(id, _, _)| id).collect(),",
        "a_channel_write_through_the_sdk_lands_on_the_channel",
        # NOT the witness's own ancestor assertion: `move_to_channel`'s cycle
        # check fires first. A stronger guard than the one this leg aimed at,
        # recorded rather than papered over.
        "appears in its own ancestor chain",
    ),
]


def self_test() -> int:
    """Every leg has a live anchor, a non-empty mutation and a real witness.

    Cheap and static on purpose: the expensive proof is running the harness.
    What this catches is the rot that makes the harness silently do nothing —
    an anchor that drifted, a mutation that is a no-op, a witness that was
    renamed. Each of those turns a leg green-by-vacancy.
    """
    problems: list[str] = []
    suite = REPO / "crates" / "dp-kernel" / "tests" / f"{SUITE}.rs"
    if not suite.exists():
        problems.append(f"the witness suite {suite.name} is gone")
    suite_src = B.read_txt(suite) if suite.exists() else ""

    seen: set[tuple[str, str]] = set()
    for label, path, find, replace, test_name, marker in LEGS:
        if not path.exists():
            problems.append(f"{label}: {path.name} is gone")
            continue
        src = B.read_txt(path)
        n = src.count(find)
        if n != 1:
            problems.append(f"{label}: anchor occurs {n}x (want exactly 1): {find[:60]!r}")
        if find == replace or not replace.strip():
            problems.append(f"{label}: the mutation is a no-op")
        if f"fn {test_name}(" not in suite_src:
            problems.append(f"{label}: witness `{test_name}` is not in {SUITE}.rs")
        if not marker.strip():
            problems.append(f"{label}: no expected-red marker — a red would be unverifiable")
        key = (str(path), find)
        if key in seen:
            problems.append(f"{label}: duplicate anchor — two legs bite the same line")
        seen.add(key)

    if not LEGS:
        problems.append("LEGS is empty; delete this harness rather than passing on nothing")

    if problems:
        print(f"dp-df1a-bite-gate: SELFTEST FAIL — {len(problems)} problem(s)")
        for p in problems:
            print(f"  - {p}")
        return 1
    print(f"dp-df1a-bite-gate: SELFTEST PASS — {len(LEGS)} leg(s), each with exactly one live "
          f"anchor, a non-empty mutation, a witness that exists in {SUITE}.rs, and an "
          f"expected-red marker")
    return 0


def main() -> int:
    if "--self-test" in sys.argv or "--selftest" in sys.argv:
        return self_test()

    print("dp-df1a-bite-gate — the CHANNEL write path's guards, each one removed\n")

    if not os.environ.get("LOREWEAVE_TEST_PG_URL"):
        print("dp-df1a-bite-gate: SKIP — LOREWEAVE_TEST_PG_URL is unset.\n"
              "  Every witness here is PG-gated and SKIPS without it, and a skip prints `ok`.\n"
              "  Scoring those as bitten would be a harness that cannot fail — refusing\n"
              "  instead. Run `--self-test` for the static arms, which need no database.")
        return 0

    # The lock lives in the 5b harness this one already imports. Two mutators on
    # one tree corrupt it — see HarnessLock for the measured failure.
    with B.HarnessLock():
        results = [bite(*leg) for leg in LEGS]

    print(f"\n{'=' * 74}")
    bitten = sum(1 for r in results if r)
    for (label, *_), ok in zip(LEGS, results):
        print(f"  {'ok' if ok else ' x'}  {label}")
    print(f"\n  bitten: {bitten}/{len(LEGS)}")

    if bitten != len(LEGS):
        print("\ndp-df1a-bite-gate: FAIL — a guard was removed and nothing noticed.")
        return 1
    print("\ndp-df1a-bite-gate: OK — every listed guard is load-bearing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
