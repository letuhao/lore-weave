#!/usr/bin/env python3
"""dp-slice5d-bite-gate — the guards `5D` puts on channel identity, each removed.

`5D` is an ADOPTION: `dp-kernel` had a `ChannelId`, a writer lease and a
`channels` table before `crates/dp` existed, and this slice moved the identity
into the contract crate and gave it a producer. Its guards are the ones that
decide whether a channel-scoped call addresses the channel the session is
actually in — the cross-channel leak `DP-A14`'s scope choice exists to prevent.

Every one of them looks like a small conditional and none of them is.

MACHINERY IMPORTED FROM `dp-slice5b-bite-gate`, for the reason 5c gives: the
read/restore/digest parts are already solved there, and a third copy would be a
third thing to drift.

WHAT IS NOT BITEABLE HERE, AND WHERE EACH IS PROVEN INSTEAD
------------------------------------------------------------
* the two SCOPE bounds (`read_projection_reality` refusing a channel-scoped
  aggregate, `read_projection_channel` refusing a reality-scoped one) — those
  are type errors, so removing them changes what COMPILES, not what a test
  asserts. `tests/ui/read_wrong_scope.rs` and
  `tests/ui/channel_read_wrong_scope.rs` pin both directions via trybuild, and
  `dp-slice1-bite-gate`'s compile-fail legs are the harness shaped for that.
* the `ChannelId::unverified` ratchet — `scripts/channel-id-adoption-gate.py`
  carries its own `--selftest` proving each arm reds on synthetic counts, which
  is stronger than a bite on the live tree (a bite there would have to edit a
  baseline, and the baseline is the thing under test).
* **`DP-K2`'s "a channel change returns a NEW context"** — there is no guard to
  remove. `move_to_channel` is `&self -> Self`; Rust's own type system is what
  makes mutating the original inexpressible, so the only "mutation" available is
  a signature change, which does not compile. A leg was written for it, scored
  `THE GUARD IS NOT LOAD-BEARING`, and the harness was right in the letter and
  wrong in the spirit — the mutation was a no-op statement that changed nothing.
  Recorded here rather than deleted quietly: `dp-slice1-bite-gate` learned the
  same lesson as `V1-F3`, that a leg with no removable guard is worth STATING
  and is not worth counting. `session::tests::the_original_context_is_untouched_because_dp_k2_says_so`
  still runs; it just cannot fail by removal.

Exit 0 = every bite bit; 1 = one did not.
"""
from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _load_5b():
    path = REPO / "scripts" / "dp-slice5b-bite-gate.py"
    if not path.exists():
        print(f"dp-slice5d-bite-gate: MISUSE — {path} is missing; this harness reuses its "
              "read/restore/verdict machinery", file=sys.stderr)
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("dp_slice5b_bite_gate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


B = _load_5b()

SESSION = REPO / "crates" / "dp" / "src" / "session.rs"
CACHE = REPO / "crates" / "dp" / "src" / "cache.rs"
READ = REPO / "crates" / "dp" / "src" / "read.rs"


def outcome(target: str, test_name: str) -> tuple[str, str]:
    """Run ONE test. `target` is `--lib` or `--test <name>`."""
    args = ["cargo", "test", "-p", "dp"]
    args += (["--lib"] if target == "lib" else ["--test", target])
    args += [test_name, "--", "--exact"]
    p = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace"
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


def bite(label: str, path: Path, find: str, replace: str, target: str, test_name: str) -> bool:
    print(f"\n{'=' * 74}\nBITE {label}\n{'=' * 74}")
    print(f"  guard    : {path.relative_to(REPO)}")
    print(f"  witness  : dp :: {target} :: {test_name}")

    before, out = outcome(target, test_name)
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
        after, out = outcome(target, test_name)
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

    after_restore, _ = outcome(target, test_name)
    print(f"  restored : {after_restore}  (expected pass)")
    if after_restore != "pass":
        print(f"  x {label}: the witness does not pass after restore — the tree is not back")
        return False
    return ok


LEGS = [
    (
        "[channel] a tree naming a DIFFERENT channel than was asked for is refused",
        SESSION,
        "if resolved.channel != raw_channel {",
        "if false {",
        "lib",
        "session::tests::a_tree_naming_a_different_channel_is_refused",
    ),
    (
        "[channel] a channel that is its own ancestor is refused",
        SESSION,
        "if resolved.ancestors.contains(&resolved.channel) {",
        "if false {",
        "lib",
        "session::tests::a_channel_that_is_its_own_ancestor_is_refused",
    ),
    (
        "[channel] moving channels checks the capability first (DP-K2)",
        SESSION,
        "self.check_live(now_ms)?;\n        let resolved = tree.resolve",
        "let resolved = tree.resolve",
        "lib",
        "session::tests::an_expired_session_cannot_move_into_a_channel",
    ),
    (
        "[cache] the CHANNEL is in the key, so two channels do not collide",
        CACHE,
        "channel = channel,",
        # An EMPTY segment, not a reordering: the key keeps its shape and loses
        # its channel, which is exactly the collision the guard prevents. The
        # first attempt used a `{channel:.0}` precision spec, which std's
        # integer `Display` ignores — the channel still printed, the keys still
        # differed, and the leg scored the guard as vacuous when the MUTATION
        # was the thing that did nothing.
        'channel = "",',
        "lib",
        "cache::tests::two_channels_do_not_share_a_key_for_the_same_aggregate_id",
    ),
    (
        "[cache] a session with no channel gets NO key rather than an invented one",
        CACHE,
        "let channel = ctx.current_channel_id()?;",
        # Channel 0 is the invented default this guard exists to refuse, and it
        # is what a hurried edit would actually reach for. The first attempt
        # named a type that does not exist, which broke the build — and a build
        # failure reds every test while proving nothing about the guard.
        "let channel = ctx.current_channel_id().unwrap_or(crate::ids::ChannelId::unverified(0));",
        "lib",
        "cache::tests::a_session_with_no_channel_gets_no_channel_key",
    ),
    (
        "[read] a reality-scoped session never reaches the store on the channel path",
        READ,
        "if ctx.current_channel_id().is_none() {",
        "if false {",
        "lib",
        "read::tests::a_reality_scoped_session_cannot_read_a_channel_scoped_aggregate",
    ),
    (
        # THE SHRINK RULE ITSELF. Three registers were DELETED in this slice on
        # the grounds that their rows had outlived their reason, and "we deleted
        # the check because it passed" is exactly the move that needs evidence
        # rather than assertion. This puts a row back for something that IS now
        # built and shows the surviving register's shrink arm refuse it — the
        # same arm shape all four registers carried.
        "[oracle] a DEFERRED row that outlived its reason still reds",
        READ,
        '    ("wait_for", "DP-Ch38 CausalityToken, also deferred by DpError"),',
        '    ("read_projection_channel", "already built — this row is the bite"),\n'
        '    ("wait_for", "DP-Ch38 CausalityToken, also deferred by DpError"),',
        "spec_oracle",
        "the_channel_scoped_key_shape_is_the_one_dp_k7_specifies",
    ),
    (
        "[oracle] the channel key's SEGMENT ORDER is the one DP-K7 specifies",
        CACHE,
        '"dp:{reality}:{scope}:{channel}:{tier}:{typ}:{id}"',
        '"dp:{reality}:{scope}:{tier}:{typ}:{channel}:{id}"',
        "spec_oracle",
        "the_channel_scoped_key_shape_is_the_one_dp_k7_specifies",
    ),
]


def main() -> int:
    print("dp-slice5d-bite-gate — the channel-identity guards, each one removed\n")
    results = [bite(*leg) for leg in LEGS]

    print(f"\n{'=' * 74}")
    bitten = sum(1 for r in results if r)
    for (label, *_), ok in zip(LEGS, results):
        print(f"  {'ok' if ok else ' x'}  {label}")
    print(f"\n  bitten: {bitten}/{len(LEGS)}")

    if bitten != len(LEGS):
        print("\ndp-slice5d-bite-gate: FAIL — a guard was removed and nothing noticed.")
        return 1
    print("\ndp-slice5d-bite-gate: OK — every listed guard is load-bearing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
