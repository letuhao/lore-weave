#!/usr/bin/env python3
"""dp-slice1-bite-gate — `S3.3`, the bite matrix for `crates/dp`.

**RENAMED from `dp-slice1-bite.py` (`G5`).** `gate-wiring-gate`'s scope is a
FILENAME predicate — `*-gate` / `*-lint` — so under the old name this file was
not merely unwired, it was **not reportable as unwired**: 23 legs, the entire
`S3.3` evidence that every guard in this slice is real, ran nowhere and nothing
could say so. A completeness pass found it. One `git mv` puts it inside
`gates.yml --run-all` and the wiring gate on the same day, which is the cheapest
mechanism available and therefore the right one.


A guarantee nobody tried to break is a claim. Every mechanism slice 1 installs is
therefore **removed, shown to let the violation through, and restored.**

WHAT CHANGED AFTER `V1-F3`, AND WHY THE SCORE WAS THE FINDING
--------------------------------------------------------------
The first version of this file printed **`PASS 3/3`**. A cold-start refuter
measured it and only **two** of the three were bites:

* Leg (a) claimed to prove exclusivity by compiling `tests/ui/_bite_shape.rs` as
  a control. That file **did not reference `dp` at all**, so it would have
  compiled with the crate deleted — and its counterpart `two_tiers.rs` fails on
  **`E0201`**, a Rust language rule provable with `trait Anything { type T; }`.
  The leg established *"E0201 exists"*. `_bite_shape.rs` has been deleted rather
  than left in place with a caveat: a control that controls for nothing is not
  evidence, and the argument it was standing in for (that `DP-Ch4`'s
  macro-checked shape is bypassable by hand-writing the impl) is made in prose in
  `compile_fail.rs`, where it belongs.
* Meanwhile `runtime_tier_branch.rs` **labelled itself unbiteable** and leg (a)
  got a substitute instead of the same disclosure. The inconsistency was the
  finding, not the missing bite.

So this file now reports **bitten** and **unbiteable-and-named** separately, and
`3/3` is gone. A leg with no removable guard is worth stating; it is not worth
counting.

THE THREE KINDS OF BITE HERE
----------------------------
  compile-fail  remove the mechanism from `crates/dp`, show the `tests/ui/` case
                now COMPILES, restore
  oracle        edit ONE SIDE of a spec/code pair, show `spec_oracle` goes RED
                **naming both sides**, restore. This is the `V.2` claim: a
                parser disagreeing with a `const` is the drift alarm that did
                not exist while `FLOW-2` was accumulating.
  gate          introduce the violation `dp-aggregate-gate` exists for, show it
                reds, remove it

`BDR-19` is why every mutation is verified before its check runs: a harness that
fails to mutate prints the SAME string as a guard that fails to catch, and the
wrong one of those is a finding about the guard. Every step asserts
`mutated != original`, restores from an in-memory copy in a `finally`, and then
**proves the restore by digest** rather than trusting that the `finally` ran
(`V1-F8`).

**`mutated != original` is necessary and NOT sufficient — `BDR-30`.** This
harness's own first run proved it: the `DP-S5` leg's anchor changed
`"| T2 writes"` to `"| T2 writes "`, one added space. The bytes differed, so the
assertion passed; the parse was identical, because `table_cells` trims labels.
The oracle stayed green and was RIGHT to. A mutation must change what the
document **says**, not merely what it contains — and the only reason that is
written here rather than mis-scored as a gate failure is that the harness
reported the leg red and the anchor was re-read.

Exit 0 = every bite bit; 1 = one did not.
"""
from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DP = REPO / "crates" / "dp"
TIER = DP / "src" / "tier.rs"
AGGREGATE = DP / "src" / "aggregate.rs"
DOCS = REPO / "docs" / "03_planning" / "LLM_MMO_RPG" / "06_data_plane"


def read_txt(path: Path) -> str:
    """Read as BYTES then decode — never `Path.read_text`.

    `V1-F8`'s digest check found this on its first run and it is not cosmetic:
    `Path.read_text`/`write_text` open in text mode with `newline=None`, so on
    Windows every restore rewrote every line ending as CRLF. The harness was
    silently re-punctuating LOCKED design documents on every run — and `git
    diff` showed NOTHING, because `.gitattributes` normalises to LF on read. The
    damage was invisible to exactly the tool a reviewer would check with, which
    is why the digest compares BYTES rather than asking git.
    """
    return path.read_bytes().decode("utf-8")


def write_txt(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def restored_byte_identical(path: Path, original: str, label: str) -> bool:
    """`V1-F8` — prove the restore, do not assume it.

    Every mutation below is undone in a `finally` from a copy held in **process
    memory**. That is the only copy: the mutated files are `crates/dp/src/*.rs`
    and LOCKED design documents, so a crash between write and restore leaves the
    tree wrong with nothing to diff against — and the first version of this
    harness ran against files git did not yet track, so `git checkout` would not
    have helped either. The digest is cheap and it turns "the `finally` ran" into
    "the bytes are back".
    """
    now = hashlib.sha256(path.read_bytes()).hexdigest()
    want = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if now != want:
        print(f"  x {label}: RESTORE FAILED — {path.relative_to(REPO)} differs after the bite")
        print(f"      sha256 now  = {now}")
        print(f"      sha256 want = {want}")
        print("      The tree is left MUTATED. Restore it before doing anything else.")
        return False
    print(f"  restored : sha256 {now[:16]}… identical to baseline")
    return True


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ─────────────────────────────────────────────────────────────────────────────
# compile-fail bites
# ─────────────────────────────────────────────────────────────────────────────
def _rlib() -> str:
    deps = REPO / "target" / "debug" / "deps"
    cands = sorted(deps.glob("libdp-*.rlib"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not cands:
        print("dp-slice1-bite-gate: MISUSE — no libdp-*.rlib; run `cargo build -p dp` first",
              file=sys.stderr)
        sys.exit(2)
    return str(cands[0])


def compiles(ui_file: str) -> tuple[bool, str]:
    """Ask rustc directly whether one UI case builds against the real crate."""
    code, out = run("cargo", "build", "-p", "dp", "--message-format=short")
    if code != 0:
        return False, "crate itself does not build:\n" + out[-2000:]
    code, out = run("rustc", "--edition", "2021", "--crate-type", "bin",
                    "--extern", f"dp={_rlib()}",
                    "-L", str(REPO / "target" / "debug" / "deps"),
                    "-o", str(REPO / "target" / "dp_bite_probe"),
                    str(DP / "tests" / "ui" / ui_file))
    return code == 0, out


def bite_compile_fail(label: str, path: Path, ui_file: str, find: str, replace: str) -> bool:
    print(f"\n{'=' * 74}\nBITE [compile-fail] {label}\n{'=' * 74}")

    before_ok, _ = compiles(ui_file)
    print(f"  baseline : tests/ui/{ui_file} compiles? {before_ok}  (expected False)")
    if before_ok:
        print(f"  x {label}: the UI case ALREADY compiles — the guard is absent, not merely weak")
        return False

    original = read_txt(path)
    if find not in original:
        print(f"  x {label}: MISUSE — anchor not found in {path.name}: {find[:60]!r}")
        return False
    mutated = original.replace(find, replace, 1)
    assert mutated != original, "mutation produced identical text"

    try:
        write_txt(path, mutated)
        after_ok, out = compiles(ui_file)
        print(f"  mutated  : guard removed -> compiles? {after_ok}  (expected True)")
        if not after_ok:
            # `V1-F7`: these are two DIFFERENT findings and the first version
            # printed the same sentence for both. If the mutation broke the
            # CRATE, nothing has been learned about the guard — that is a
            # defect in this harness, and saying "the guard is weak" would send
            # the reader to the wrong file.
            if out.startswith("crate itself does not build"):
                print(f"  x {label}: HARNESS MISUSE — the mutation broke `dp` itself, so the UI")
                print("    case could not be compiled against it. Nothing is proven about the")
                print("    guard. Fix the mutation, not the crate. rustc said:")
            else:
                print("  x the UI case still fails WITH THE GUARD REMOVED — it was failing for")
                print("    some other reason, so it never tested this guarantee. rustc said:")
            print("    " + "\n    ".join(out.strip().splitlines()[:8]))
            return False
    finally:
        write_txt(path, original)

    if not restored_byte_identical(path, original, label):
        return False
    restored_ok, _ = compiles(ui_file)
    print(f"  restored : compiles? {restored_ok}  (expected False)")
    if restored_ok:
        print(f"  x {label}: restore failed — {path.name} is left mutated!")
        return False

    print(f"  + {label}: the guard BITES — removing it makes the violation legal")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# oracle bites — the V.2 claim, one side at a time
# ─────────────────────────────────────────────────────────────────────────────
def oracle_green() -> tuple[bool, str]:
    code, out = run("cargo", "test", "-p", "dp", "--test", "spec_oracle")
    return code == 0, out


def bite_oracle(label: str, doc: str, find: str, replace: str, must_name: tuple[str, ...]) -> bool:
    """Edit ONE side and require the oracle to red, naming BOTH sides."""
    print(f"\n{'=' * 74}\nBITE [oracle] {label}\n{'=' * 74}")
    path = DOCS / doc

    ok, _ = oracle_green()
    print(f"  baseline : spec_oracle green? {ok}  (expected True)")
    if not ok:
        print(f"  x {label}: the oracle is already red — nothing can be concluded from a flip")
        return False

    original = read_txt(path)
    if find not in original:
        print(f"  x {label}: MISUSE — anchor not found in {doc}: {find[:70]!r}")
        return False
    mutated = original.replace(find, replace, 1)
    assert mutated != original, "mutation produced identical text"

    try:
        write_txt(path, mutated)
        ok_after, out = oracle_green()
        print(f"  mutated  : {doc} edited on ONE side -> green? {ok_after}  (expected False)")
        if ok_after:
            print(f"  x {label}: the document and the code now DISAGREE and the oracle said "
                  f"nothing. That is FLOW-2, alive.")
            return False
        missing = [n for n in must_name if n not in out]
        if missing:
            print(f"  x {label}: it reddened but its message does not name {missing} — a drift "
                  f"alarm that does not say WHICH TWO THINGS disagree sends the reader hunting")
            return False
        print(f"  ...       and the failure names both sides: {', '.join(must_name)}")
    finally:
        write_txt(path, original)

    if not restored_byte_identical(path, original, label):
        return False
    ok_restored, _ = oracle_green()
    print(f"  restored : green? {ok_restored}  (expected True)")
    if not ok_restored:
        print(f"  x {label}: restore failed — {doc} is left mutated!")
        return False

    print(f"  + {label}: the oracle BITES — a one-sided edit cannot pass")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# gate bite
# ─────────────────────────────────────────────────────────────────────────────
def bite_gate() -> bool:
    label = "dp-aggregate-gate / V1-F1"
    print(f"\n{'=' * 74}\nBITE [gate] {label}\n{'=' * 74}")
    probe = DP / "tests" / "_bite_v1f1.rs"
    gate = str(REPO / "scripts" / "dp-aggregate-gate.py")

    code, _ = run(sys.executable, gate)
    print(f"  baseline : gate exit={code}  (expected 0)")
    if code != 0:
        print(f"  x {label}: the gate is already red")
        return False

    write_txt(
        probe,
        "//! Transient bite probe — written and removed by scripts/dp-slice1-bite-gate.py.\n"
        "use core::marker::PhantomData;\n"
        "use dp::{DpAggregate, Scope, Tier};\n"
        "pub struct PlayerWallet<T: Tier, S: Scope>(PhantomData<(T, S)>);\n"
        "impl<T: Tier, S: Scope> DpAggregate for PlayerWallet<T, S> {\n"
        "    type Tier = T;\n"
        "    type Scope = S;\n"
        "    type Id = u64;\n"
        "    const TYPE_NAME: &'static str = \"player_wallet\";\n"
        "}\n",
    )
    try:
        code_after, out = run(sys.executable, gate)
        print(f"  mutated  : the V1-F1 generic escape added -> gate exit={code_after}  (expected 1)")
        if code_after != 1:
            print(f"  x {label}: the gate accepted the exact break it was written for")
            return False
        # And the contrast that IS the finding: rustc is perfectly happy with it.
        rc, _ = run("cargo", "build", "-p", "dp", "--tests", "--message-format=short")
        print(f"  ...       and `cargo build -p dp --tests` exit={rc} — rustc ACCEPTS it, which "
              f"is why\n            this is a gate and not a type")
        if rc != 0:
            print("  x the probe did not compile, so it is not the case V1-F1 describes")
            return False
        # R6, not R1/R2. The rule that catches the generic escape changed when
        # the gate was rewritten after round 2: `R1` asks "is this token a
        # tier?", which a renamed parameter passes; `R6` asks "does the
        # right-hand side name something this impl BINDS?", which is the actual
        # property. Pinning the rule id is what makes this a bite for the RIGHT
        # reason rather than a check on the exit code.
        if "R6" not in out:
            print("  x the gate reddened without naming R6 — right answer, wrong rule")
            return False
    finally:
        probe.unlink(missing_ok=True)

    code_restored, _ = run(sys.executable, gate)
    print(f"  restored : gate exit={code_restored}  (expected 0)")
    if code_restored != 0:
        print(f"  x {label}: restore failed")
        return False
    print(f"  + {label}: the gate BITES — and rustc does not")
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Leg (c)'s mutation names the tier seal THREE times — once as the anchor, once
# in the injected `impl`, once re-emitting the anchor. Spelling it out three
# times is how it went stale: the trait was `sealed::Sealed` until the `V1-F13`
# split, and the stale spelling still MATCHED because it is a prefix of
# `sealed::SealedTier`. The mutation then injected an impl of a trait that no
# longer exists, breaking `dp` — and only `V1-F7`'s misuse branch stopped that
# being scored as a weak guard. Written once, used three times, it cannot drift
# against itself.
TIER_SEAL_ANCHOR = "pub trait Tier: sealed::SealedTier"
RUNTIME_TIER_MUTATION = (
    "impl sealed::SealedTier for TierLevel {}\n"
    "impl Tier for TierLevel {\n"
    "    const LEVEL: TierLevel = TierLevel::T2;\n"
    "    const COHERENCY: Coherency = Coherency::Snapshot;\n"
    "    const CACHE_TTL: Option<Duration> = None;\n"
    "    const WRITE_ACK_P99: Duration = Duration::from_millis(1);\n"
    "    const SUSTAINED_WRITES_PER_S: Option<u32> = None;\n"
    "    const SURVIVES_STORE_OUTAGE: bool = true;\n"
    "}\n"
) + TIER_SEAL_ANCHOR

def cargo_green() -> tuple[bool, str]:
    code, out = run("cargo", "test", "-p", "dp")
    return code == 0, out


def bite_source(label: str, path: Path, edits: list[tuple[str, str]],
                must_name: tuple[str, ...] = ()) -> bool:
    """Mutate `crates/dp` source and require `cargo test -p dp` to RED.

    Added after `V.1` round 2, which found four MAJOR holes that every existing
    leg was blind to (`V2-F3`..`F6`) — because every existing leg mutated a
    DOCUMENT or a GATE, and these live in the crate. The bite matrix was honest
    about what it ran and silent about what it never touched, which is `V2-N10`.
    """
    print(f"\n{'=' * 74}\nBITE [source] {label}\n{'=' * 74}")

    ok, _ = cargo_green()
    print(f"  baseline : cargo test -p dp green? {ok}  (expected True)")
    if not ok:
        print(f"  x {label}: the suite is already red — a flip proves nothing")
        return False

    original = read_txt(path)
    # A LIST of edits, because one coherent change is not always one anchor:
    # adding a `TierLevel` variant without its `as_key` arm is `E0004`, so the
    # crate never builds and the mutation never reaches the check it is aimed
    # at. A mutation must be the change an AUTHOR would make, not the smallest
    # textual one.
    mutated = original
    for find, replace in edits:
        if find not in mutated:
            print(f"  x {label}: MISUSE — anchor not found in {path.name}: {find[:70]!r}")
            return False
        mutated = mutated.replace(find, replace, 1)
    assert mutated != original, "mutation produced identical text"

    try:
        write_txt(path, mutated)
        ok_after, out = cargo_green()
        print(f"  mutated  : {path.name} changed -> green? {ok_after}  (expected False)")
        if ok_after:
            print(f"  x {label}: the crate now says something different and 21 tests agreed with")
            print("    it anyway. That is the hole this leg was written for.")
            return False
        missing = [n for n in must_name if n not in out]
        if missing:
            print(f"  x {label}: it reddened but the message does not name {missing}")
            return False
        if must_name:
            print(f"  ...       and the failure names: {', '.join(must_name)}")
    finally:
        write_txt(path, original)

    if not restored_byte_identical(path, original, label):
        return False
    ok_restored, _ = cargo_green()
    print(f"  restored : green? {ok_restored}  (expected True)")
    if not ok_restored:
        print(f"  x {label}: restore failed")
        return False
    print(f"  + {label}: the check BITES")
    return True


def bite_gate_probe(label: str, probe_rel: str, src: str, want_rules: tuple[str, ...]) -> bool:
    """Plant a round-2 reproduction in the tree; the gate must red naming its rule.

    These are the refuter's own files, kept verbatim. A gate hardened against a
    break it no longer has a copy of is one refactor from having the break back.
    """
    print(f"\n{'=' * 74}\nBITE [gate-probe] {label}\n{'=' * 74}")
    gate = str(REPO / "scripts" / "dp-aggregate-gate.py")
    probe = REPO / probe_rel

    code, _ = run(sys.executable, gate)
    if code != 0:
        print(f"  x {label}: the gate is already red")
        return False

    probe.parent.mkdir(parents=True, exist_ok=True)
    write_txt(probe, src)
    try:
        code_after, out = run(sys.executable, gate)
        # Match the rule id by SHAPE. The enumerated version read `[:2]`, so
        # `R10` arrived as `R1` and `R11` was invisible entirely — the rule the
        # `V4-F7` legs below were added to cover could not have been detected by
        # the code that scores them.
        rules = sorted({ln.split()[0] for ln in out.splitlines()
                        if re.match(r"R\d+\s", ln.strip())})
        print(f"  planted  : gate exit={code_after} rules={rules}  (expected 1)")
        if code_after != 1:
            print(f"  x {label}: the gate ACCEPTED a break it is written against")
            return False
        missing = [r for r in want_rules if r not in rules]
        if missing:
            print(f"  x {label}: reddened, but not by {missing} — right answer, wrong reason")
            return False
    finally:
        probe.unlink(missing_ok=True)
        for d in (probe.parent, probe.parent.parent):
            try:
                d.rmdir()
            except OSError:
                break

    code_restored, _ = run(sys.executable, gate)
    print(f"  restored : gate exit={code_restored}  (expected 0)")
    if code_restored != 0:
        print(f"  x {label}: restore failed")
        return False
    print(f"  + {label}: the gate BITES, by {', '.join(want_rules)}")
    return True


UNBITEABLE = [
    ("tests/ui/two_tiers.rs",
     "fails on E0201 — 'duplicate definitions for `Tier`' — which is a Rust language rule, not a "
     "mechanism crates/dp installs. It is a REGRESSION PIN for the shape, and it is not evidence "
     "that anything in this crate is load-bearing. V1-F3."),
    ("tests/ui/runtime_tier_branch.rs",
     "fails because two distinct types cannot be the arms of one `if`. There is no guard to "
     "remove, so there is nothing to bite; the FIELD case next to it is the biteable half."),
]


def main() -> int:
    run("cargo", "build", "-p", "dp")
    results: list[bool] = []

    # ── compile-fail ─────────────────────────────────────────────────────────
    results.append(bite_compile_fail(
        "(b) closed set / DP-A5 — the seal is one word", TIER, "fifth_tier.rs",
        "pub(crate) mod sealed {", "pub mod sealed {",
    ))
    results.append(bite_compile_fail(
        "(c) design-time only / DP-A9 — TierLevel must not be a Tier", TIER,
        "runtime_tier_field.rs",
        TIER_SEAL_ANCHOR,
        RUNTIME_TIER_MUTATION,
    ))
    results.append(bite_compile_fail(
        "(d) derived rows / DP-R2 — privacy is what makes tier_row the only constructor",
        AGGREGATE, "forged_row.rs",
        # All SEVEN fields, not just the first. With one field made public the
        # literal still fails on the other six, and the leg scores a miss for a
        # reason that has nothing to do with the guarantee — which is exactly the
        # wrong-reason failure this whole harness exists to detect, arriving from
        # inside the harness. `BDR-30`.
        "    type_name: &'static str,\n    tier: TierLevel,\n    scope: ScopeKind,\n"
        "    coherency: Coherency,\n    cache_ttl: Option<Duration>,\n"
        "    write_ack_p99: Duration,\n    survives_store_outage: bool,",
        "    pub type_name: &'static str,\n    pub tier: TierLevel,\n    pub scope: ScopeKind,\n"
        "    pub coherency: Coherency,\n    pub cache_ttl: Option<Duration>,\n"
        "    pub write_ack_p99: Duration,\n    pub survives_store_outage: bool,",
    ))

    # ── oracle: one bite per parsed source ───────────────────────────────────
    for label, doc, find, replace, names in [
        ("DP-S3 write-ack budget", "08_scale_and_slos.md",
         "| DP-T2 | <5 ms ack", "| DP-T2 | <7 ms ack", ("08_scale_and_slos.md", "tier.rs")),
        ("DP-X7 cache TTL", "06_cache_coherency.md",
         "| T2 | 5 min |", "| T2 | 7 min |", ("06_cache_coherency.md", "tier.rs")),
        # NOT `"| T2 writes" -> "| T2 writes "`. That was the first anchor here and
        # it changed BYTES without changing MEANING — `table_cells` trims labels, so
        # the parse was identical and the oracle was right to stay green. `BDR-19`
        # says verify the mutation APPLIED; this is its sharper form: verify the
        # mutation SAYS SOMETHING DIFFERENT. The harness caught it, which is the
        # only reason it is written down here instead of being scored as a gate
        # failure. `BDR-30`.
        ("DP-S5 sustained writes", "08_scale_and_slos.md",
         "| T2 writes | 500 / s", "| T2 writes | 700 / s",
         ("08_scale_and_slos.md", "tier.rs")),
        ("03 tier matrix — the closed SET (V1-F2)", "03_tier_taxonomy.md",
         "| **DP-T3** | Durable-sync", "| **DP-T4** | Durable-sync",
         ("03_tier_taxonomy.md", "tier.rs")),
        ("DP-X1 coherency model (V1-F4b)", "06_cache_coherency.md",
         "| **T1** | Snapshot coherency", "| **T1** | Snapshot-ish coherency",
         ("06_cache_coherency.md", "tier.rs")),
        ("REC-102c degraded-mode partition (V1-F4c)", "07_failure_and_recovery.md",
         "| **T3** | **REJECT", "| **T3** | **BUFFER",
         ("07_failure_and_recovery.md", "tier.rs")),
        # `G3` — the two documents that carry the RULES rather than the numbers,
        # and which nothing opened until a completeness pass counted: 22 of 26.
        ("DP-A5 the closed set, in the invariant the seal cites (G3)", "02_invariants.md",
         "- **DP-T3 Durable-sync**", "- **DP-T9 Durable-sync**",
         ("02_invariants.md", "tier.rs")),
        ("DP-Ch5 the cache-key scope marker (G3)", "12_channel_primitives.md",
         "Reality-scoped:   dp:{reality_id}:r:", "Reality-scoped:   dp:{reality_id}:R:",
         ("12_channel_primitives.md",)),
        # `G10` — the first DOC-to-DOC leg. Every other one edits a document and
        # requires the CODE to notice; this pair edits one of two copies of the
        # same figures inside the LOCKED corpus and requires the OTHER COPY to
        # notice. `DP-F7` Bucket 1's header says "Enforces DP-S5 ceilings" and
        # then restates the numbers instead of referring to them. Both sides are
        # bitten, because a cross-check that only fires from one direction leaves
        # the other free to drift.
        ("G10 DP-F7's copy of the ceilings, edited alone", "07_failure_and_recovery.md",
         "| T2 writes | 500/s", "| T2 writes | 700/s",
         ("07_failure_and_recovery.md", "08_scale_and_slos.md")),
        ("G10 DP-S5's copy of the ceilings, edited alone", "08_scale_and_slos.md",
         "| T2 writes | 500 / s | 2 000 / s |", "| T2 writes | 700 / s | 2 000 / s |",
         ("07_failure_and_recovery.md", "08_scale_and_slos.md")),
    ]:
        results.append(bite_oracle(label, doc, find, replace, names))

    # ── source: the four MAJOR holes round 2 found in the crate itself ──────
    for label, path, edits, names in [
        ("V2-F3 DP-S3's unit — a two-quantity cell with its units swapped",
         DOCS / "08_scale_and_slos.md",
         [("| DP-T2 | <5 ms ack, ≤1 s to projection",
           "| DP-T2 | <5 s ack, ≤1 ms to projection")],
         ("not milliseconds",)),
        ("V2-F3 DP-S5's denominator — per-second becomes per-minute",
         DOCS / "08_scale_and_slos.md",
         [("| T2 writes | 500 / s", "| T2 writes | 500 / min")],
         ("PER-SECOND",)),
        ("V2-F4 a hand-written tier past the macro",
         TIER,
         # The derives are load-bearing: `Tier: Copy + Debug`, so without them the
         # mutation fails to COMPILE and never reaches the check it is aimed at —
         # `V1-F7`'s "the mutation broke the crate" case, from a brand-new leg on
         # its first run.
         [("declare_tier!(\n    T3,",
           "#[derive(Debug, Clone, Copy)]\npub(crate) struct T1p5;\n"
           "impl sealed::SealedTier for T1p5 {}\n"
           "impl Tier for T1p5 {\n"
           "    const LEVEL: TierLevel = TierLevel::T2;\n"
           "    const COHERENCY: Coherency = Coherency::Snapshot;\n"
           "    const CACHE_TTL: Option<Duration> = None;\n"
           "    const WRITE_ACK_P99: Duration = Duration::from_millis(7);\n"
           "    const SUSTAINED_WRITES_PER_S: Option<u32> = Some(1_500);\n"
           "    const SURVIVES_STORE_OUTAGE: bool = true;\n}\n"
           "declare_tier!(\n    T3,")],
         ("outside `declare_tier!`",)),
        # TWO edits, and that is the finding: a variant ALONE is `E0004` —
        # `as_key`'s match is exhaustive, so rustc refuses the crate before any
        # test runs. Stronger than the check, and it means the naive one-anchor
        # mutation never reaches its subject. With the arm supplied, which is
        # what an author adding a tier would write, `s3_4_counts` is what reds.
        ("V2-F5 a fifth TierLevel variant with no tier behind it",
         TIER,
         [("pub enum TierLevel {\n    T0,", "pub enum TierLevel {\n    T4,\n    T0,"),
          ('            Self::T0 => "t0",',
           '            Self::T4 => "t4",\n            Self::T0 => "t0",')],
         ("declare_tier!",)),
        ("V2-F6 rename half the cache-key tokens",
         TIER,
         [('Self::T0 => "t0",\n            Self::T1 => "t1",',
           'Self::T0 => "TIER_ZERO",\n            Self::T1 => "TIER_ONE",')],
         ()),
    ]:
        results.append(bite_source(label, path, edits, names))

    # ── gate ─────────────────────────────────────────────────────────────────
    results.append(bite_gate())

    # ── gate: round 2's own reproductions, kept verbatim ─────────────────────
    P = "crates/dp/tests/_r2_probe.rs"
    for label, rel_path, src, want in [
        ("R2-1 a generic parameter NAMED T2", P,
         "use dp::{DpAggregate, Scope, Tier};\nuse core::marker::PhantomData;\n"
         "pub struct PlayerWallet<T2, RealityScope>(PhantomData<(T2, RealityScope)>);\n"
         "impl<T2: Tier, RealityScope: Scope> DpAggregate for PlayerWallet<T2, RealityScope> {\n"
         "    type Tier = T2; type Scope = RealityScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r2_wallet\";\n}\n", ("R6", "R7")),
        ("R2-2 an associated-type projection", P,
         "use dp::{DpAggregate, Scope, Tier};\n"
         "pub trait Pick { type T2: Tier; type RealityScope: Scope; }\n"
         "impl<A: Tier, B: Scope> DpAggregate for Wallet<A, B> {\n"
         "    type Tier = <Self as Pick>::T2; type Scope = <Self as Pick>::RealityScope;\n"
         "    type Id = u64; const TYPE_NAME: &'static str = \"r2_proj\";\n}\n", ("R6",)),
        ("R2-3 a char literal that blanks the impl", P,
         "use dp::{DpAggregate, Scope, Tier};\npub const QUOTE: char = '\"';\n"
         "pub const OPEN: &str = \"/*\";\n"
         "impl<A: Tier, B: Scope> DpAggregate for Ledger<A, B> {\n"
         "    type Tier = A; type Scope = B; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r2_ledger\";\n}\npub const CLOSE: &str = \"*/\";\n",
         ("R6",)),
        ("R2-4 an odd brace inside a doc string", P,
         "use dp::{DpAggregate, Scope, Tier};\n"
         "impl<A: Tier, B: Scope> DpAggregate for Evil<A, B> {\n"
         "    #[doc = \"the cache key opens with a brace: dp:{\"]\n"
         "    type Tier = A; type Scope = B; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r2_evil\";\n}\n", ("R6",)),
        ("R2-5 src/tests/ui/ is NOT a trybuild fixture", "crates/dp/src/tests/ui/mod.rs",
         "use dp::{DpAggregate, Scope, Tier};\n"
         "impl<A: Tier, B: Scope> DpAggregate for Sneak<A, B> {\n"
         "    type Tier = A; type Scope = B; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r2_sneak\";\n}\n", ("R6",)),
        ("R2-6 aliasing a tier name", P,
         "use dp::{DpAggregate, Scope, Tier};\nuse dp::T3 as T2;\n"
         "impl DpAggregate for AliasWallet {\n"
         "    type Tier = T2; type Scope = dp::RealityScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r2_alias\";\n}\n", ("R8",)),
        ("R2-7 a unicode escape defeating TYPE_NAME uniqueness", P,
         "use dp::DpAggregate;\n"
         "impl DpAggregate for Fast { type Tier = dp::T0; type Scope = dp::RealityScope;\n"
         "    type Id = u64; const TYPE_NAME: &'static str = \"r2dup\"; }\n"
         "impl DpAggregate for Safe { type Tier = dp::T3; type Scope = dp::RealityScope;\n"
         "    type Id = u64; const TYPE_NAME: &'static str = \"r2du\\u{70}\"; }\n", ("R4",)),
        # ── `V4-F7`: the legs asserted `R4`/`R6`/`R7`/`R8`/`R10` and NOTHING
        # ELSE. Deleting `R9` and `R11` from the contract left BOTH scorers at
        # their top score — `PASS — 25 bite(s) bit` and `SELF-TEST PASS`. The
        # number measured LEGS, not COVERAGE, which is `V2-F1`'s defect wearing
        # the harness's own uniform. One probe per uncovered rule.
        #
        # These probes name types that do not exist, and one of them does not
        # parse at all. That is safe and deliberate: `cargo test --test
        # aggregate_contract` builds ONLY that target, and the contract reads
        # every other file from DISK rather than compiling it. A probe that had
        # to compile could not exercise `R1` or `R9` at all.
        ("V4-F7 R1 — a concrete NON-tier as the tier", P,
         "use dp::DpAggregate;\npub struct R1Probe;\n"
         "impl DpAggregate for R1Probe {\n"
         "    type Tier = MyCustomTier; type Scope = dp::RealityScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r4_r1\";\n}\n", ("R1",)),
        ("V4-F7 R2 — a concrete NON-scope as the scope", P,
         "use dp::DpAggregate;\npub struct R2Probe;\n"
         "impl DpAggregate for R2Probe {\n"
         "    type Tier = dp::T0; type Scope = ZoneScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"r4_r2\";\n}\n", ("R2",)),
        ("V4-F7 R3 — a computed TYPE_NAME", P,
         "use dp::DpAggregate;\npub struct R3Probe;\n"
         "impl DpAggregate for R3Probe {\n"
         "    type Tier = dp::T0; type Scope = dp::RealityScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = NAMES[0];\n}\n", ("R3",)),
        ("V4-F7 R9 — a subject file that does not parse", P,
         "use dp::DpAggregate;\nimpl DpAggregate for Broken {\n"
         "    type Tier = dp::T0\n    this is not rust\n", ("R9",)),
        ("V4-F7 R11 — a TYPE_NAME that is not snake_case", P,
         "use dp::DpAggregate;\npub struct R11Probe;\n"
         "impl DpAggregate for R11Probe {\n"
         "    type Tier = dp::T0; type Scope = dp::RealityScope; type Id = u64;\n"
         "    const TYPE_NAME: &'static str = \"PlayerWallet\";\n}\n", ("R11",)),
        ("R2-8 one macro body, N invocations", P,
         "use dp::DpAggregate;\nmacro_rules! agg { ($ty:ident) => {\n    pub struct $ty;\n"
         "    impl DpAggregate for $ty {\n"
         "        type Tier = dp::T2; type Scope = dp::RealityScope; type Id = u64;\n"
         "        const TYPE_NAME: &'static str = \"r2_macro\";\n    }\n}; }\n"
         "agg!(WalletA);\nagg!(WalletB);\n", ("R10",)),
    ]:
        results.append(bite_gate_probe(label, rel_path, src, want))

    print(f"\n{'=' * 74}")
    print("UNBITEABLE, and named rather than given a substitute (V1-F3):")
    for f, why in UNBITEABLE:
        print(f"  - {f}\n      {why}")

    print(f"\n{'=' * 74}")
    if all(results):
        print(f"dp-slice1-bite-gate: PASS — {len(results)} bite(s) bit, {len(UNBITEABLE)} leg(s) "
              f"stated as unbiteable.")
        print("Each mechanism was shown BREAKABLE by removing it, which is the only evidence")
        print("that the mechanism is what holds the claim.")
        return 0
    print(f"dp-slice1-bite-gate: FAIL — {sum(results)}/{len(results)} bites bit.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
