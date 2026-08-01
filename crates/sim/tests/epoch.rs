//! `Q0b B2a` — `RLS-D8` / `RLS-I1`, the ruleset epoch switch inside an island.
//!
//! ## Why this file defines its own domain
//!
//! `TestDomain::rules_digest` answers `RulesetDigest::UNPINNED` for every
//! `TestRules` — which is the honest answer for a harness domain whose rules
//! are a struct a test invented. But it means *"the digest changed after the
//! switch"* is **unfalsifiable** under `TestDomain`: the value is the same 32
//! zero bytes before and after, so the assertion passes for an
//! `activate_epoch` that does nothing at all. That is `NV-2` — the subject
//! cannot vary — and it is the exact shape `QTY-A12`'s `size_of` assertion had.
//!
//! `EpochDomain` below derives its digest from its rules, so a swap that failed
//! to swap is visible.

use std::sync::Arc;

use sim_core::{
    Admitted, Class, DiscardReason, EntityId, EpochSwitchRefused, Gen, InputId, Island, IslandId,
    Lane, Outcome, Precondition, Producer, QueuedInput, RulesetDigest, RulesetEpoch, SeenWindow,
    Seq, StepStatus, Violation,
};

// ───────────────────────── a domain whose digest VARIES ─────────────────────────

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EpochRules {
    /// The only thing that varies, and the digest is a function of it.
    pub tag: u8,
}

#[derive(Debug, Default, Clone)]
pub struct EpochState {
    /// Every applied input records the `tag` of the rules it ran under. This is
    /// what makes "no item straddles the switch" checkable rather than asserted.
    pub applied_under: Vec<u8>,
}

/// `Ok` records the tag it ran under; `Panic` is the poison pill, so the
/// poisoned arm below is reached through the island's real containment
/// machinery rather than a test-only setter that could outlive it.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Tag {
    Ok,
    Panic,
}

pub struct EpochDomain;

impl sim_core::Domain for EpochDomain {
    type Payload = Tag;
    type State = EpochState;
    type Event = ();
    type ResKind = ();
    type Rules = EpochRules;
    type External = ();
    type Portable = ();

    fn check(
        _state: &Self::State,
        _rules: &Self::Rules,
        _p: &Precondition<Self>,
    ) -> Result<(), Violation> {
        Ok(())
    }

    fn apply(
        state: &mut Self::State,
        rules: &Self::Rules,
        input: &QueuedInput<Self>,
        _rng: &mut sim_core::DetRng,
    ) -> Vec<Self::Event> {
        if matches!(input.payload, Tag::Panic) {
            panic!("poison pill");
        }
        state.applied_under.push(rules.tag);
        Vec::new()
    }

    /// Derived from the rules, so a failed swap is a failed assertion. The
    /// whole point of this domain.
    fn rules_digest(rules: &Self::Rules) -> RulesetDigest {
        let mut b = [0u8; 32];
        b[0] = rules.tag;
        RulesetDigest(b)
    }

    fn externals(_events: &[Self::Event]) -> Vec<Self::External> {
        Vec::new()
    }
    fn extract(_state: &mut Self::State, _id: EntityId) {}
    fn install(_state: &mut Self::State, _id: EntityId, _p: Self::Portable) {}
}

fn island(tag: u8) -> Island<EpochDomain> {
    Island::new(
        IslandId(1),
        7,
        RulesetEpoch(1),
        Arc::new(EpochRules { tag }),
        SeenWindow::Unbounded,
        EpochState::default(),
    )
}

fn rules(tag: u8) -> Arc<EpochRules> {
    Arc::new(EpochRules { tag })
}

/// An input with no preconditions. `Admitted::unchecked` is the `test-util`
/// bypass — its absence in a service build is what makes an admission bypass a
/// compile error (IAS-D3).
fn input(id: u128) -> Admitted<EpochDomain> {
    payload_input(id, Tag::Ok)
}

fn payload_input(id: u128, payload: Tag) -> Admitted<EpochDomain> {
    Admitted::unchecked(QueuedInput {
        input_id: InputId(id),
        seq: Seq(0),
        class: Class::A,
        source: Producer::PlayerInput,
        payload,
        preconditions: Vec::new(),
        on_invalid: sim_core::Fallback::Drop,
        deadline: None,
        admitted_gen: Gen(0),
    })
}

// ────────────────────────────── the happy path ──────────────────────────────

#[test]
fn a_switch_swaps_the_rules_the_digest_and_the_epoch_together() {
    let mut isl = island(1);
    assert_eq!(isl.epoch, RulesetEpoch(1), "doc 16 §12 — creation assigns epoch 1");
    assert_eq!(isl.digest, EpochDomain_digest(1));

    let d = isl.activate_epoch(RulesetEpoch(2), rules(9)).expect("monotonic");
    assert_eq!(d, EpochDomain_digest(9), "the returned digest is DERIVED from the new rules");
    assert_eq!(isl.digest, EpochDomain_digest(9));
    assert_eq!(isl.epoch, RulesetEpoch(2));

    // …and the rules are actually in use, not merely stored. Without this the
    // test would pass for a swap that updated the two public fields and left
    // the Arc alone — which is the realistic half-implementation.
    isl.submit(Lane::Live, input(1));
    assert!(matches!(isl.step(), StepStatus::Processed(_)));
    assert_eq!(
        state_tags(&isl),
        vec![9],
        "the input applied under the OLD rules — the Arc was not swapped"
    );
}

/// **`RLS-D8` atomicity, made observable.** Items admitted before the switch
/// were validated against rules that no longer apply, so they must not be
/// applied under the new ones. Today they discard as `Superseded`.
#[test]
fn items_admitted_before_the_switch_do_not_apply_under_the_new_rules() {
    let mut isl = island(1);
    isl.submit(Lane::Live, input(1));
    isl.submit(Lane::Live, input(2));

    isl.activate_epoch(RulesetEpoch(2), rules(9)).expect("switch");

    // Both queued items pop and discard; neither reaches `apply`.
    for _ in 0..2 {
        assert!(matches!(isl.step(), StepStatus::Processed(_)));
    }
    assert!(
        state_tags(&isl).is_empty(),
        "an item admitted under epoch 1 was APPLIED under epoch 2's rules — it was \
         never validated against them (RLS-D8 atomicity)"
    );
    assert!(
        isl.outcomes()
            .iter()
            .all(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Superseded })),
        "the discard must be RECORDED, not silent"
    );

    // …and a re-submission after the switch runs under the new rules. Without
    // this the test above is satisfied by an island that simply stopped working.
    isl.submit(Lane::Live, input(3));
    assert!(matches!(isl.step(), StepStatus::Processed(_)));
    assert_eq!(state_tags(&isl), vec![9]);
}

// ───────────────────────────────── refusals ─────────────────────────────────

#[test]
fn a_backwards_epoch_is_refused_and_changes_nothing() {
    let mut isl = island(1);
    isl.activate_epoch(RulesetEpoch(5), rules(5)).expect("forward");

    for offered in [1u32, 4, 5] {
        let err = isl
            .activate_epoch(RulesetEpoch(offered), rules(99))
            .expect_err("not strictly greater than 5");
        assert!(
            matches!(err, EpochSwitchRefused::NotMonotonic { current, offered: o }
                     if current == RulesetEpoch(5) && o == RulesetEpoch(offered)),
            "{err}"
        );
    }

    // NOTHING moved — not the digest, not the epoch. A partially applied
    // switch is the one outcome worse than either answer.
    assert_eq!(isl.epoch, RulesetEpoch(5));
    assert_eq!(isl.digest, EpochDomain_digest(5));
    assert!(format!("{}", EpochSwitchRefused::NotMonotonic {
        current: RulesetEpoch(5),
        offered: RulesetEpoch(5)
    })
    .contains("RLS-I1"));
}

/// Equality is refused **on purpose**, and this test exists because "harmless"
/// is the argument for accepting it. At-least-once delivery makes a duplicate
/// switch normal; a silent `Ok` would hide a real double-activation carrying
/// DIFFERENT bytes behind the common case.
#[test]
fn a_duplicate_switch_at_the_same_epoch_is_refused_even_with_different_rules() {
    let mut isl = island(1);
    isl.activate_epoch(RulesetEpoch(2), rules(2)).expect("first");
    let err = isl
        .activate_epoch(RulesetEpoch(2), rules(77))
        .expect_err("same epoch, different bytes — the dangerous case");
    assert!(matches!(err, EpochSwitchRefused::NotMonotonic { .. }), "{err}");
    assert_eq!(isl.digest, EpochDomain_digest(2), "the second delivery must not win");
}

// ─────────────────────────── the checkpoint carry ───────────────────────────

/// **The hole this closes.** Without an `epoch` on the checkpoint, an island
/// that reached epoch 3 comes back as epoch 1 — and then a redelivered switch
/// to epoch 2 is accepted, moving it onto rules its committed outcomes were not
/// produced under. A monotonic counter that does not survive the operation that
/// rebuilds it is not monotonic.
#[test]
fn the_epoch_survives_a_checkpoint_restore_round_trip() {
    let mut isl = island(1);
    isl.activate_epoch(RulesetEpoch(2), rules(2)).expect("2");
    isl.activate_epoch(RulesetEpoch(3), rules(3)).expect("3");

    let cp = isl.checkpoint().expect("not poisoned");
    assert_eq!(cp.epoch, RulesetEpoch(3));

    let restored = Island::<EpochDomain>::restore(cp, rules(3)).expect("digests agree");
    assert_eq!(restored.epoch, RulesetEpoch(3), "the restore reset the epoch");

    let mut restored = restored;
    let err = restored
        .activate_epoch(RulesetEpoch(2), rules(2))
        .expect_err("a redelivered epoch-2 switch must not be accepted after a restore");
    assert!(matches!(err, EpochSwitchRefused::NotMonotonic { .. }), "{err}");
}

// ───────────────────────────── the poisoned arm ─────────────────────────────

#[test]
fn a_poisoned_island_refuses_a_switch_rather_than_being_repaired_by_one() {
    let mut isl = island(1);
    poison(&mut isl);
    assert!(isl.is_poisoned());

    let err = isl.activate_epoch(RulesetEpoch(2), rules(2)).expect_err("SC-A8");
    assert!(matches!(err, EpochSwitchRefused::Poisoned), "{err}");
    assert_eq!(isl.epoch, RulesetEpoch(1), "a poisoned island must not move");
    assert!(isl.is_poisoned(), "the switch un-poisoned the island");
}

// ───────────────────────────────── helpers ─────────────────────────────────

#[allow(non_snake_case)]
fn EpochDomain_digest(tag: u8) -> RulesetDigest {
    <EpochDomain as sim_core::Domain>::rules_digest(&EpochRules { tag })
}

fn state_tags(isl: &Island<EpochDomain>) -> Vec<u8> {
    isl.state().applied_under.clone()
}

/// Poison through the island's OWN machinery — a panicking `apply` — not a
/// test setter. If containment stops poisoning, this helper stops working and
/// the test below fails, which is the point.
fn poison(isl: &mut Island<EpochDomain>) {
    isl.submit(Lane::Live, payload_input(999, Tag::Panic));
    assert!(matches!(isl.step(), StepStatus::Processed(_)));
}

/// **`RLS-D8`'s "never inside a step", observed rather than asserted.**
///
/// This arm is unreachable from a host: `step` holds `&mut self`, so no caller
/// can be inside one. The reachable violation is an edit to `island.rs` that
/// calls `activate_epoch` from within `step` — and a guard nothing can redden
/// is a guard a refactor deletes without consequence. `set_in_step_for_test`
/// exists only so this test can exist.
#[test]
fn a_switch_from_inside_a_step_is_refused_and_changes_nothing() {
    let mut isl = island(1);
    isl.set_in_step_for_test(true);

    let err = isl
        .activate_epoch(RulesetEpoch(2), rules(9))
        .expect_err("RLS-D8: the Arc is applied BETWEEN steps");
    assert!(matches!(err, EpochSwitchRefused::MidStep), "{err}");
    assert!(format!("{err}").contains("INSIDE step()"), "{err}");
    assert_eq!(isl.epoch, RulesetEpoch(1));
    assert_eq!(isl.digest, EpochDomain_digest(1));

    // …and the flag is not sticky: once the step is over, the same switch is
    // accepted. Without this, a guard that latched on forever would pass the
    // assertions above while silently refusing every real switch — failing
    // toward "the feature never works", which is the failure that looks like
    // the feature simply not being wired.
    isl.set_in_step_for_test(false);
    assert!(isl.activate_epoch(RulesetEpoch(2), rules(9)).is_ok());
}

/// The flag must be cleared by `step` itself on EVERY exit — including the
/// idle one, which returns before any work.
#[test]
fn step_clears_the_mid_step_flag_even_when_it_finds_nothing_to_do() {
    let mut isl = island(1);
    assert_eq!(isl.step(), StepStatus::Idle);
    assert!(
        isl.activate_epoch(RulesetEpoch(2), rules(9)).is_ok(),
        "an idle step left the mid-step flag set, so no switch can ever happen again"
    );
}

// ══════════ B2b — RLS-A14: the switch as an ORDERED ingress item ══════════

/// **The thing `B2a` could not do.** With the switch out-of-band, everything
/// already queued had to be superseded, because nothing marked where the
/// boundary was. As an ordered item the boundary IS its position: items ahead
/// of it run under the old rules and items behind it under the new — and the
/// second half is only safe because admission stamps `Seq` and nothing else,
/// so every precondition is re-validated at STEP time.
#[test]
fn an_ordered_switch_splits_the_queue_instead_of_superseding_it() {
    let mut isl = island(1);
    isl.submit(Lane::Live, input(1));
    isl.submit(Lane::Live, input(2));
    isl.submit_epoch_switch(RulesetEpoch(2), rules(9));
    isl.submit(Lane::Live, input(3));
    isl.submit(Lane::Live, input(4));

    for _ in 0..5 {
        assert!(matches!(isl.step(), StepStatus::Processed(_)));
    }

    assert_eq!(
        state_tags(&isl),
        vec![1, 1, 9, 9],
        "two items should have run under epoch 1's rules and two under epoch 2's — \
         a queue-wide supersede would give [], and applying the switch too early \
         or too late would shift the boundary"
    );
    assert_eq!(isl.epoch, RulesetEpoch(2));
    assert_eq!(isl.digest, EpochDomain_digest(9));
}

/// The switch is a step's ENTIRE work, so `RLS-D8`'s *"between two steps"*
/// still holds: no `D::apply` runs on the step that performs it.
#[test]
fn the_switch_consumes_exactly_one_step_and_applies_nothing() {
    let mut isl = island(1);
    isl.submit_epoch_switch(RulesetEpoch(2), rules(9));

    assert!(matches!(isl.step(), StepStatus::Processed(_)));
    assert!(state_tags(&isl).is_empty(), "the switch step ran a domain apply");
    assert_eq!(isl.epoch, RulesetEpoch(2));
    assert_eq!(isl.step(), StepStatus::Idle, "the switch was not consumed");

    // Recorded, not silent — every item's fate is (CS-D5).
    assert!(
        isl.outcomes()
            .iter()
            .any(|(_, o)| matches!(o, Outcome::Applied { events } if events.is_empty())),
        "the switch produced no recorded outcome"
    );
}

/// **The ordered path does NOT bump the island generation**, and that is the
/// whole improvement. If it did, the two items behind the switch would discard
/// as `Superseded` and the test above would read `[1, 1]`.
#[test]
fn the_ordered_path_does_not_supersede_work_queued_behind_it() {
    let mut isl = island(1);
    isl.submit_epoch_switch(RulesetEpoch(2), rules(9));
    isl.submit(Lane::Live, input(1));

    assert!(matches!(isl.step(), StepStatus::Processed(_))); // the switch
    assert!(matches!(isl.step(), StepStatus::Processed(_))); // the input
    assert_eq!(state_tags(&isl), vec![9], "the input behind the switch was superseded");
    assert!(
        !isl.outcomes()
            .iter()
            .any(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Superseded })),
        "the ordered path bumped the island generation — the bump belongs only to the          out-of-band activate_epoch, which has no position in the queue"
    );
}

/// A redelivered switch is refused by `RLS-I1` monotonicity, not by the
/// seen-set — a control item has no `InputId`, and monotonicity is strictly
/// stronger than a key that expires out of a TTL window.
#[test]
fn a_redelivered_ordered_switch_is_refused_by_its_epoch_not_by_the_seen_set() {
    let mut isl = island(1);
    isl.submit_epoch_switch(RulesetEpoch(2), rules(9));
    isl.submit_epoch_switch(RulesetEpoch(2), rules(77)); // duplicate, different bytes
    isl.submit(Lane::Live, input(1));

    for _ in 0..3 {
        assert!(matches!(isl.step(), StepStatus::Processed(_)));
    }
    assert_eq!(isl.epoch, RulesetEpoch(2));
    assert_eq!(
        isl.digest,
        EpochDomain_digest(9),
        "the SECOND delivery won — a duplicate switch overwrote the first"
    );
    assert_eq!(state_tags(&isl), vec![9]);
}

/// A switch stamped in a generation that has since been invalidated must not
/// apply. An island that was dissolved and rebuilt is not the island the
/// switch was aimed at.
#[test]
fn a_switch_from_a_superseded_generation_is_discarded() {
    let mut isl = island(1);
    isl.submit_epoch_switch(RulesetEpoch(2), rules(9));
    isl.bump_island_gen();

    assert!(matches!(isl.step(), StepStatus::Processed(_)));
    assert_eq!(isl.epoch, RulesetEpoch(1), "a stale-generation switch applied");
    assert_eq!(isl.digest, EpochDomain_digest(1));
    assert!(isl
        .outcomes()
        .iter()
        .any(|(_, o)| matches!(o, Outcome::Discarded { reason: DiscardReason::Superseded })));
}

/// The kernel half of the same finding: an island built for a reality already
/// past epoch 1 must START there, or `RLS-I1` is computed against the wrong
/// number and an intermediate replayed switch is accepted.
#[test]
fn an_island_starts_at_the_epoch_it_is_given_not_at_one() {
    let mut isl = Island::<EpochDomain>::new(
        IslandId(1),
        7,
        RulesetEpoch(5),
        rules(5),
        SeenWindow::Unbounded,
        EpochState::default(),
    );
    assert_eq!(isl.epoch, RulesetEpoch(5));

    // The switch a stale redelivery would carry. Accepted only by an island
    // that wrongly believes it is at epoch 1.
    let err = isl
        .activate_epoch(RulesetEpoch(3), rules(3))
        .expect_err("epoch 3 is BEHIND the reality's epoch 5");
    assert!(matches!(err, EpochSwitchRefused::NotMonotonic { .. }), "{err}");
    assert_eq!(isl.digest, EpochDomain_digest(5), "the island moved backwards");
}
