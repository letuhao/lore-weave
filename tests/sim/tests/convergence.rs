//! Inc-2 convergence oracle as cargo tests.

use loreweave_sim::convergence::check;

#[test]
fn real_projection_converges_across_interleavings() {
    check(false).expect("real PcProjection must converge across all interleavings");
}

#[test]
fn bite_global_order_dependent_projection_diverges() {
    // Non-vacuity: a projection that depends on global apply order MUST be
    // caught (live != replay). If this "passes" (Ok), the oracle is vacuous.
    check(true).expect("bite must fire (report divergence)");
}
