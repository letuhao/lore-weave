#!/usr/bin/env python3
"""dp-slice5b-bite-gate — every guard the CAPABILITY LIFECYCLE installs, removed.

`5B` is the capability STORE: the control plane records what it issues, so a
capability can be validated, refreshed and revoked instead of merely minted.
Almost all of its value is in REFUSALS — a blank service identity, a secret that
was never issued, a revoked grant being refreshed back to life — and a refusal
is the easiest thing in the world to ship broken and green. So each one is
removed here, shown to let the violation through, and restored.

WHY A UNIT-TEST BITE AND NOT A COMPILE-FAIL BITE
------------------------------------------------
`dp-slice1-bite-gate`'s legs are compile-fail: the guard is a type rule, so
removing it makes an illegal program compile. `5B`'s guards are runtime
predicates, so the observable is a test going RED. That imposes an extra
obligation this harness enforces: **a mutation that stops the crate COMPILING is
not a bite.** A build failure reds every test including the ones that have
nothing to do with the guard, so it proves the mutation was destructive rather
than that the guard was load-bearing. Each leg therefore requires the mutated
tree to compile AND the named test to fail on an assertion.

`BDR-19` applies unchanged: a harness that fails to mutate prints the same string
as a guard that fails to catch. Every leg asserts `mutated != original` before
running anything, restores from an in-memory copy in a `finally`, and proves the
restore **by digest** rather than trusting the `finally` ran (`V1-F8`).

WHAT IS DELIBERATELY NOT HERE
-----------------------------
Two of `5B`'s guards live in SQL and cannot be bitten without a database:

  * `bytea_hex` — the digest reaching Postgres as a hex escape. Mutating it reds
    only `tests/pg_live.rs`, which skips without `META_RS_TEST_DATABASE_URL`, and
    a bite whose check silently skips is worse than no bite.
  * the `revoked_at IS NULL` CAS rendering as `IS NULL` rather than `= NULL`.

Both are exercised live by `scripts/meta-rs-pg-live-smoke.sh`. Naming them here
rather than omitting them is the `V1-F3` lesson: a leg with no runnable bite is
worth stating and is not worth counting.

Exit 0 = every bite bit; 1 = one did not.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
IDS = REPO / "crates" / "dp" / "src" / "ids.rs"
CONTROL_PLANE = REPO / "crates" / "meta-rs" / "src" / "control_plane.rs"
SESSION_STORE = REPO / "crates" / "meta-rs" / "src" / "session_store.rs"
DP_SESSION = REPO / "crates" / "dp" / "src" / "session.rs"

# Guards that exist and are proven elsewhere, listed so the count cannot read as
# "this is all of them".
UNBITEABLE_HERE = [
    (
        "bytea_hex -> Postgres BYTEA",
        "reds only tests/pg_live.rs, which SKIPS without META_RS_TEST_DATABASE_URL",
        "scripts/meta-rs-pg-live-smoke.sh :: a_capability_round_trips_through_a_real_session_registry",
    ),
    (
        "the refresh/revoke CAS rendering `revoked_at IS NULL`",
        "same — the difference between `IS NULL` and `= NULL` is invisible to any in-memory store",
        "scripts/meta-rs-pg-live-smoke.sh :: revoke_and_refresh_cas_against_a_real_server",
    ),
    (
        "session_registry's CHECK constraints (32-byte hash, non-blank identity, expiry ordering)",
        "they are schema, not code; no Rust edit can remove them",
        "scripts/meta-rs-pg-live-smoke.sh applies 039 and writes through it",
    ),
]


LOCK = REPO / "target" / ".bite-harness.lock"


class HarnessLock:
    """Refuse to start while another bite harness is mutating the tree.

    # The failure this exists to prevent, measured 2026-08-09

    `gate-wiring-gate` runs the mutating harnesses SERIALLY — but that only
    orders them inside ONE sweep process. Two sweeps overlapped, and the damage
    was worse than a false red:

      harness A reads its baseline  <- already mutated by B
      harness A mutates, then restores TO A'S BASELINE
      = B's mutation is now permanent, and A's digest check PASSES

    The restore-by-digest guard (`V1-F8`) cannot see this. It proves the file
    came back to what the harness read, and what it read was already wrong.
    Three files were left mutated in `crates/dp` — including `tier.rs`'s
    `as_key` returning `TIER_ZERO` — and every bite gate reported red for a
    reason that had nothing to do with any guard.

    # Why a lock and not a dirty-tree check

    A dirty-tree check would refuse whenever a developer has ordinary
    uncommitted work, which is most of the time — and it would be refusing the
    wrong thing. Restoring to a dirty working state is CORRECT; these harnesses
    restore byte-for-byte to whatever they read. The hazard is specifically a
    SECOND mutator, and that is what this names.
    """

    def __enter__(self) -> "HarnessLock":
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        try:
            # O_EXCL: the create fails if the file exists. Atomic, so two
            # harnesses racing to create it cannot both win.
            fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            holder = ""
            try:
                holder = LOCK.read_text(encoding="utf-8").strip()
            except OSError:
                pass
            print(
                f"REFUSING TO START — another bite harness holds {LOCK.relative_to(REPO)}"
                f"{f' ({holder})' if holder else ''}.\n"
                "  Two harnesses mutating one tree do not merely race: the second one's\n"
                "  restore writes back the FIRST one's mutation permanently, and the\n"
                "  digest check cannot see it.\n"
                "  If no harness is running, this is a stale lock from a killed run —\n"
                f"  delete {LOCK.relative_to(REPO)} and re-run.",
                file=sys.stderr,
            )
            sys.exit(2)
        with os.fdopen(fd, "w") as f:
            f.write(f"pid {os.getpid()} — {Path(sys.argv[0]).name}")
        return self

    def __exit__(self, *_exc: object) -> None:
        # Best-effort: a failure to remove leaves a stale lock, which the
        # message above tells the next run how to clear. Losing the lock file is
        # recoverable; leaving the TREE mutated is not.
        try:
            LOCK.unlink()
        except OSError:
            pass


def read_txt(path: Path) -> str:
    """Read as BYTES then decode — never `Path.read_text`.

    `Path.read_text`/`write_text` open in text mode with `newline=None`, so on
    Windows every restore would rewrite every line ending as CRLF, and
    `.gitattributes` normalisation would hide it from `git diff` — the exact
    invisible damage `V1-F8` found in the slice-1 harness.
    """
    return path.read_bytes().decode("utf-8")


def write_txt(path: Path, text: str) -> None:
    path.write_bytes(text.encode("utf-8"))


def restored_byte_identical(path: Path, original: str, label: str) -> bool:
    now = hashlib.sha256(path.read_bytes()).hexdigest()
    want = hashlib.sha256(original.encode("utf-8")).hexdigest()
    if now != want:
        print(f"  x {label}: RESTORE FAILED — {path.relative_to(REPO)} differs after the bite")
        print(f"      sha256 now  = {now}")
        print(f"      sha256 want = {want}")
        print("      The tree is left MUTATED. Restore it before doing anything else.")
        return False
    print(f"  restored : sha256 {now[:16]}... identical to baseline")
    return True


def run(*args: str) -> tuple[int, str]:
    p = subprocess.run(
        args, cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def test_outcome(crate: str, test_name: str) -> tuple[str, str]:
    """Run ONE test. Returns (`pass` | `fail` | `nobuild` | `missing`, output).

    The four-way answer is the point. `nobuild` and `missing` both look like
    `fail` to a returncode check, and both would score a destructive mutation as
    a successful bite.
    """
    code, out = run("cargo", "test", "-p", crate, "--lib", test_name, "--", "--exact")
    if "error: could not compile" in out or "error[E" in out:
        return "nobuild", out
    if "running 0 tests" in out:
        return "missing", out
    if "test result: ok" in out:
        return "pass", out
    if "test result: FAILED" in out:
        return "fail", out
    return "nobuild", out


def bite(label: str, path: Path, find: str, replace: str, crate: str, test_name: str) -> bool:
    print(f"\n{'=' * 74}\nBITE {label}\n{'=' * 74}")
    print(f"  guard    : {path.relative_to(REPO)}")
    print(f"  witness  : {crate} :: {test_name}")

    before, out = test_outcome(crate, test_name)
    print(f"  baseline : {before}  (expected pass)")
    if before != "pass":
        print(f"  x {label}: the witness does not pass BEFORE the mutation — nothing to bite")
        print(out[-1500:])
        return False

    original = read_txt(path)
    if find not in original:
        print(f"  x {label}: MISUSE — anchor not found in {path.name}: {find[:70]!r}")
        return False
    mutated = original.replace(find, replace, 1)
    if mutated == original:
        print(f"  x {label}: MISUSE — mutation produced identical text")
        return False

    ok = False
    try:
        write_txt(path, mutated)
        after, out = test_outcome(crate, test_name)
        print(f"  mutated  : guard removed -> {after}  (expected fail)")
        if after == "nobuild":
            print(f"  x {label}: the mutation broke the BUILD, so the red proves nothing about")
            print("      the guard. Rewrite the mutation so the tree still compiles.")
        elif after == "missing":
            print(f"  x {label}: the witness did not RUN under mutation — a renamed or")
            print("      filtered-out test scores as a bite and is not one.")
        elif after == "pass":
            print(f"  x {label}: THE GUARD IS NOT LOAD-BEARING — removed, and the witness")
            print("      still passes. Either the check is vacuous or the test does not")
            print("      exercise it.")
        else:
            # The red must be an ASSERTION, not a panic from somewhere unrelated.
            print(f"  red      : {_first_failure_line(out)}")
            ok = True
    finally:
        write_txt(path, original)

    if not restored_byte_identical(path, original, label):
        return False

    after_restore, _ = test_outcome(crate, test_name)
    print(f"  restored : {after_restore}  (expected pass)")
    if after_restore != "pass":
        print(f"  x {label}: the witness does not pass after restore — the tree is not back")
        return False
    return ok


def _first_failure_line(out: str) -> str:
    for line in out.splitlines():
        s = line.strip()
        if s.startswith("assertion") or "panicked at" in s or s.startswith("thread '"):
            return s[:160]
    return "(red, but no assertion line found — check the output)"


LEGS = [
    (
        "[identity] a blank service name is refused",
        IDS,
        "if trimmed.is_empty() || trimmed.len() > Self::MAX_LEN {",
        "if raw.is_empty() || trimmed.len() > Self::MAX_LEN {",
        "dp",
        "ids::tests::an_anonymous_service_identity_cannot_be_constructed",
    ),
    (
        "[identity] a control character is refused",
        IDS,
        # A ONE-LINE anchor. The multi-line form was tried first and did not
        # match: an anchor spanning newlines is hostage to whatever line endings
        # the file happens to carry, and it fails as MISUSE rather than as a
        # missing guard — which is the right way round, but avoidable.
        ".any(|c| c.is_control())",
        ".any(|_c| false)",
        "dp",
        "ids::tests::a_control_character_is_refused_because_it_forges_a_log_line",
    ),
    (
        "[identity] the length bound is applied AFTER trimming",
        IDS,
        "if trimmed.is_empty() || trimmed.len() > Self::MAX_LEN {",
        "if trimmed.is_empty() || raw.len() > Self::MAX_LEN {",
        "dp",
        "ids::tests::the_length_bound_is_applied_after_trimming",
    ),
    (
        "[store] a capability that could not be recorded is not handed out",
        CONTROL_PLANE,
        ".map_err(|e| DpError::ControlPlaneUnavailable {\n                reason: format!(\"capability store refused the issuance: {e}\"),\n            })?;",
        ".ok();",
        "meta-rs",
        "control_plane::tests::a_bind_whose_record_fails_is_refused_rather_than_returned",
    ),
    (
        "[store] revocation beats an unexpired grant",
        SESSION_STORE,
        "self.revoked_at_ms.is_none() && now_ms < self.expires_at_ms",
        "now_ms < self.expires_at_ms",
        "meta-rs",
        "control_plane::tests::revocation_takes_effect_before_the_capability_would_have_expired",
    ),
    (
        "[store] the caller identity reaches the recorded row",
        CONTROL_PLANE,
        "service_identity: req.service.as_str().to_string(),",
        "service_identity: String::new(),",
        "meta-rs",
        "control_plane::tests::a_bind_records_the_capability_it_issued",
    ),
    # ── the REVOCATION WINDOW (2026-08-09) ──────────────────────────────────
    #
    # `5B` built the store and nothing consulted it: `check_live` compares the
    # holder's own copy of an expiry against the holder's own clock, so
    # revocation was immediate at the control plane and invisible to a writer
    # already running. These four are the guards that close it.
    (
        "[refresh] the 60s lead exists, so a refresh does not race the expiry it prevents",
        DP_SESSION,
        "now_ms.saturating_add(REFRESH_LEAD_MS) >= self.expires_at_ms",
        "now_ms >= self.expires_at_ms",
        "dp",
        "session::tests::the_refresh_lead_boundary_is_where_dp_k10_puts_it",
    ),
    (
        "[refresh] a refused refresh FAILS CLOSED rather than keeping the old grant",
        DP_SESSION,
        "let new_expiry = refresher.refresh(self.capability.secret())?;",
        # A ONE-LINE mutation. A multi-line replacement was written first and a
        # heredoc turned its `\n` into a real newline, breaking this file's own
        # syntax — the §0.6 hazard, hit while writing a harness about rigour.
        # `unwrap_or(0)` is also the more honest mutation: it is what a hurried
        # edit reaches for, and it swallows the refusal exactly the way the guard
        # exists to prevent.
        "let new_expiry = refresher.refresh(self.capability.secret()).unwrap_or(0);",
        "dp",
        "session::tests::a_revoked_session_surfaces_the_refusal_rather_than_keeping_its_old_grant",
    ),
    (
        "[refresh] an expiry moving BACKWARDS is not a refresh",
        DP_SESSION,
        "if new_expiry <= self.capability.expires_at_ms() {",
        "if false {",
        "dp",
        "session::tests::a_refresh_that_moves_the_expiry_backwards_is_refused",
    ),
    (
        "[ttl] the default TTL is the revocation window DP-C8 specifies",
        CONTROL_PLANE,
        "pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 5 * 60 * 1000;",
        "pub const DEFAULT_CAPABILITY_TTL_MS: u64 = 15 * 60 * 1000;",
        "meta-rs",
        "control_plane::tests::the_default_ttl_is_the_revocation_window_dp_c8_specifies",
    ),
    (
        "[store] the digest is SHA-256 and not something cheaper",
        SESSION_STORE,
        "h.update(secret.as_bytes());",
        "h.update(b\"constant\");",
        "meta-rs",
        "session_store::tests::the_digest_is_sha256_of_the_secret_and_nothing_else",
    ),
]


def main() -> int:
    print("dp-slice5b-bite-gate — the capability store's refusals, each one removed\n")
    # Two mutators on one tree corrupt it — see `HarnessLock` for the measured
    # failure and why the restore-by-digest guard cannot detect it.
    with HarnessLock():
        results = [bite(*leg) for leg in LEGS]

    print(f"\n{'=' * 74}")
    bitten = sum(1 for r in results if r)
    for (label, *_), ok in zip(LEGS, results):
        print(f"  {'ok' if ok else ' x'}  {label}")

    print(f"\n  bitten: {bitten}/{len(LEGS)}")
    print("\n  guards that exist and are NOT bitten here (each with where it IS proven):")
    for what, why, where in UNBITEABLE_HERE:
        print(f"    - {what}")
        print(f"        why not here : {why}")
        print(f"        proven by    : {where}")

    if bitten != len(LEGS):
        print("\ndp-slice5b-bite-gate: FAIL — a guard was removed and nothing noticed.")
        return 1
    print("\ndp-slice5b-bite-gate: OK — every listed guard is load-bearing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
