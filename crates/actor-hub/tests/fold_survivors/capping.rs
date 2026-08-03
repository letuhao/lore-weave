//! **What a `Capped` record SAYS** — the half of the survivor register about
//! the events substrate §7 requires when a value is clamped: which site bit,
//! what the fold wanted, what it emitted, and in what order the records arrive.
//!
//! Split out of `fold_survivors.rs` when `file-ceiling-gate` fired at 433 lines
//! against a 400 ceiling — the second time, because an append-only register that
//! gains a test per proven survivor only ever gets longer.
//!
//! Same test BINARY, reached by `#[path]` from the root file: a bare `mod` there
//! resolves to a SIBLING `tests/<name>.rs` and silently compiles it twice, which
//! the registry split measured as 22 tests where 13 were expected. Addressed as
//! `capping::<name>`.

use super::{deriv, fixture, p, q};
use actor_hub::*;
use ruleset_core::ModifierOp;

/// **`Accumulator.wanted` carries the EXACT pre-clamp total, not its sign.**
///
/// The only assertions on this field were `< 0` and `> 0`, so replacing it with
/// the emitted value was green — and this is the field whose module doc records
/// a review finding it understating the truth by a factor of ~6 000.
#[test]
fn the_accumulator_record_carries_the_exact_wanted_total() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    // `Percent` is PER-MILLE: the factor is `max(0, 1000 + Sum pct)/1000`, so
    // `Percent(1000)` doubles. The i64 accumulator holds 2 × i32::MAX and the
    // emit clamps to i32::MAX; `wanted` must be the former.
    let boost = ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(1_000),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let out = fold(a, &s, &r, &[boost], &[]);

    let want = (i32::MAX as i64) * 2;
    assert_eq!(out.value(q(0)), Some(i32::MAX));
    let cap = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::Emit)
        .expect("an emit that clamped produced no record");
    assert_eq!(
        cap.wanted, want,
        "`wanted` must be the value the fold actually computed, not the one it emitted"
    );
    assert_eq!(cap.emitted, i32::MAX);
}

/// **`pre_emit` is the value BEFORE the emit clamp**, which is the only thing
/// that distinguishes it from `value`. Every existing case had the two equal, so
/// assigning `value` to it was green.
#[test]
fn pre_emit_differs_from_value_when_the_emit_clamps() {
    let (r, a, mut s) = fixture();
    s[0] = i32::MAX;
    let boost = ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(1_000),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let out = fold(a, &s, &r, &[boost], &[]);

    let ex = out.explain(q(0)).expect("no explanation for a folded quantity");
    assert_eq!(ex.value, i32::MAX, "the emitted value is clamped");
    assert_eq!(
        ex.pre_emit,
        (i32::MAX as i64) * 2,
        "`pre_emit` must show what the clamp removed; equal to `value` it explains nothing"
    );
}

/// **A bound whose FLOOR bites is a `DerivedBound` cap.**
///
/// The only bound case in the suite had the ceiling bite, so a mutation that
/// reported nothing when the floor raised a value was green. Both directions of
/// `clamp` are the author's declaration working, and substrate §7 wants an event
/// for either.
#[test]
fn a_bound_whose_floor_bites_is_reported() {
    let (r, a, mut s) = fixture();
    s[2] = -5_000;
    let floored = DerivationRow {
        bound: Some(ContributionBound { min: 0, max: 100 }),
        ..deriv(3, 2, 20)
    };
    let out = fold(a, &s, &r, &[], &[floored]);

    assert_eq!(out.value(q(3)), Some(1), "the floor must have raised -5 000 000 to 0");
    let cap = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::DerivedBound)
        .expect("the floor bit and said nothing");
    // The factor is applied BEFORE the divisor, so the raw amount is
    // -5 000 × 1 000 / 1. `wanted` is that -- the value the row asked for --
    // and `emitted` is what the floor allowed.
    assert_eq!(cap.wanted, -5_000_000);
    assert_eq!(cap.emitted, 0);
}

/// **Both `Capped` records for one quantity, in the order the fold writes them.**
///
/// `emit` deliberately produces the accumulator record before the emit record,
/// and `FoldReport.capped` is public output — but nothing asserted the sequence,
/// so pushing them the other way round was green. The two records describe
/// different sites of the same number; which one a reader meets first is the
/// difference between *"the accumulation overflowed and was then clamped"* and
/// *"the value was clamped, and separately the accumulator says it overflowed."*
#[test]
fn the_accumulator_record_precedes_the_emit_record_for_one_quantity() {
    let (r, a, mut s) = fixture();
    // Saturate the accumulator downward, so BOTH records fire for `hp`.
    s[q(0).index()] = i32::MIN;
    let flat = |v: i32| ModifierRow {
        target: q(0),
        op: ModifierOp::Flat(v),
        source: p(0),
        fold_layer: FoldLayer(10),
    };
    let pct = ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(i32::MAX),
        source: p(0),
        fold_layer: FoldLayer(10),
    };

    let out = fold(a, &s, &r, &[flat(i32::MIN), flat(i32::MIN), pct], &[]);
    let sites: Vec<CapSite> = out
        .capped
        .iter()
        .filter(|c| c.quantity == q(0))
        .map(|c| c.site)
        .collect();

    assert_eq!(
        sites,
        vec![CapSite::Accumulator, CapSite::Emit],
        "both records must fire, accumulator first — got {sites:?}"
    );
}

/// **The ACCUMULATOR record's `wanted` — the twin nothing pinned.**
///
/// `the_accumulator_record_carries_the_exact_wanted_total` reads
/// `c.site == CapSite::Emit`, and the mutation row that claims to cover the
/// accumulator half mutates the **Emit** push: its label says `Accumulator` and
/// its anchor says `CapSite::Emit`. Everywhere else in the suite the
/// accumulator's `wanted` is asserted only by SIGN, so replacing it with the
/// emitted value survived all 300 tests.
///
/// `report.rs` documents this exact field: *on `CapSite::Accumulator` the true
/// value exceeded `i64` and this is the saturated bound, not the number the
/// author asked for — which is exactly why the site is recorded rather than the
/// number alone*. Reporting the emitted value there understates by ~4.3 × 10⁹
/// and makes the two sites indistinguishable, which is the whole reason the
/// site exists.
#[test]
fn the_accumulator_record_carries_the_saturated_total_not_the_emitted_value() {
    let (r, a, mut s) = fixture();
    // Saturate the i64 accumulator upward, so BOTH records fire for `hp`.
    s[q(0).index()] = i32::MAX;
    let huge = |v: i32| ModifierRow {
        target: q(0),
        op: ModifierOp::Percent(v),
        source: p(0),
        fold_layer: FoldLayer(10),
    };

    let out = fold(a, &s, &r, &[huge(i32::MAX), huge(i32::MAX)], &[]);
    let acc = out
        .capped
        .iter()
        .find(|c| c.site == CapSite::Accumulator)
        .expect("a saturating accumulator produced no record");

    assert_eq!(
        acc.emitted,
        i32::MAX,
        "the emitted value is the clamped one"
    );
    assert_eq!(
        acc.wanted,
        i64::MAX / 1_000,
        "`wanted` on an Accumulator record is the SATURATED total, not the emitted value"
    );
    assert_ne!(
        acc.wanted, acc.emitted as i64,
        "the two fields must differ here, or this case cannot see the mutation"
    );
}
