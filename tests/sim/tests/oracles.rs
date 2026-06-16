//! Inc-3 + Inc-4 oracles as cargo tests (clean must pass, bite must fire).

use loreweave_sim::{atomicity, cas};

#[test]
fn atomicity_all_or_none_holds() {
    atomicity::check(false).expect("append-batch atomicity must hold across interleavings");
}

#[test]
fn atomicity_bite_torn_batch_is_caught() {
    atomicity::check(true).expect("torn-batch bite must fire");
}

#[test]
fn cas_serializes_concurrent_appends() {
    cas::check(false).expect("CAS must serialize racing appends to a clean 1..=K stream");
}

#[test]
fn cas_bite_lost_update_is_caught() {
    cas::check(true).expect("CAS-disabled lost-update bite must fire");
}
