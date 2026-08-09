//! `S2` — **Axis 2 is the compiler, executing on adversarial input.**
//!
//! `crates/dp` opens no connection and declares no I/O, so there is no live
//! smoke to run. Copying the command-substrate DoD's live-smoke row here would
//! produce a check that cannot fail, which is the exact defect
//! `docs/standards/non-vacuity.md` exists for. What slice 1 claims is that
//! **these violations are unrepresentable**, and the only honest execution of
//! that claim is rustc, run against code written to violate it.
//!
//! **The claim is narrower than it first read, and the narrowing is `V1-F1`.**
//! What rustc refuses is a *concrete* impl with two tiers, a fifth tier from
//! any crate, and a tier that varies at runtime. What rustc **accepts** is a
//! *generic* impl carrying one aggregate name across four tiers. That case has
//! no UI file here because there is nothing for rustc to reject — it is
//! `scripts/dp-aggregate-gate.py`'s, and pretending otherwise would put a
//! fourth case in this list that could never go red.
//!
//! Each case below MUST fail to compile. If one starts passing, the guarantee
//! it names has silently stopped holding — which is precisely the failure that
//! a green unit-test suite would never surface.
//!
//! ## The bite (`S3.3`)
//!
//! A compile-fail suite has its own vacuity trap: a file that fails to compile
//! **for the wrong reason** (a typo, a missing import) passes this test while
//! proving nothing. That is why each case is bitten — the guard is removed, the
//! case is shown to COMPILE, and the guard is restored. The evidence lives in
//! the RUN-STATE, because a bite that is not written down is a bite nobody can
//! re-run.

#[test]
fn tier_and_scope_violations_do_not_compile() {
    let t = trybuild::TestCases::new();

    // (a) DP-Ch4 — one tier and one scope per CONCRETE impl. The generic case
    // is dp-aggregate-gate's; see the header.
    t.compile_fail("tests/ui/two_tiers.rs");

    // (b) DP-A5 — the taxonomy is closed at four; the seal is what closes it.
    t.compile_fail("tests/ui/fifth_tier.rs");

    // (c) DP-A9 — tier is design-time. Split in two: the FIELD case is the
    // biteable half (S3.3), the BRANCH case is a language rule with no guard
    // to remove and is labelled unbiteable rather than given fake evidence.
    t.compile_fail("tests/ui/runtime_tier_field.rs");
    t.compile_fail("tests/ui/runtime_tier_branch.rs");

    // (d) DP-R2 — the tier table is DERIVED, so a hand-written row must not be
    // constructible. Added for V1-F5, which built one and printed it.
    t.compile_fail("tests/ui/forged_row.rs");

    // (e) DP-A12/DP-K1 — a RealityId is minted by session bind, never by a
    // feature crate. TWO escapes in one file, failing for different reasons:
    // the tuple-struct constructor (private FIELD, E0603) and new_verified
    // (pub(crate) FUNCTION, E0624). Covering only one would leave the other
    // open, and the .stderr pins both.
    t.compile_fail("tests/ui/forged_reality_id.rs");

    // (f) DP-K7 — the tier argument is CHECKED. A wrong tier does not fail,
    // it succeeds at building a key nobody reads: DP-R4's stated violation
    // mode, "the write lands at one key, the read misses elsewhere".
    t.compile_fail("tests/ui/cache_key_wrong_tier.rs");

    // (g) DP-R5 — no cross-tier mixing in a write. A T3 aggregate down the T2
    // path does not FAIL, it succeeds with a weaker durability promise than the
    // aggregate was designed for, and the loss surfaces later as a read that
    // should have been impossible.
    t.compile_fail("tests/ui/write_wrong_tier.rs");

    // (h) DP-K4/DP-A14 — scope is an ADDRESS. A channel-scoped aggregate read
    // through the reality-scoped door has no correct value for the channel it
    // needs, so the call should not be expressible rather than rejected.
    t.compile_fail("tests/ui/read_wrong_scope.rs");
}
