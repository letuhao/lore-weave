//! Test/chaos harness for `sim-core` (S1a slice): the [`TestDomain`] toy
//! domain the property tests and bench drive.

use std::collections::BTreeMap;

use sim_core::{
    DetRng, Domain, EntityId, Precondition, PreconditionKind, QueuedInput, Violation,
};

/// Toy domain: per-entity counters (clamped by rules) + one spendable
/// resource ("qi") + a seeded roll to exercise replay-exact randomness.
pub struct TestDomain;

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TestPayload {
    /// S1b chaos: panics inside `apply` — the poison pill.
    Panic,
    /// Increment `id`'s counter by `by`, clamped to `rules.max_counter`.
    Inc { id: EntityId, by: i64 },
    /// Spend `amount` qi (guard with `Precondition::ResourceAtLeast`).
    Spend { id: EntityId, amount: i64 },
    /// Roll a seeded value — the replay-determinism probe.
    Roll { id: EntityId },
    Noop,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TestEvent {
    Inced { id: EntityId, new: i64 },
    Spent { id: EntityId, left: i64 },
    Rolled { id: EntityId, value: u64 },
}

/// Single resource kind.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Qi;

#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct TestState {
    pub counters: BTreeMap<EntityId, i64>,
    pub qi: BTreeMap<EntityId, i64>,
}

/// RLS-A12 rules slice — immutable, passed by reference, never in State.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TestRules {
    pub max_counter: i64,
}

impl Domain for TestDomain {
    type Payload = TestPayload;
    type State = TestState;
    type Event = TestEvent;
    type ResKind = Qi;
    type Rules = TestRules;
    /// `Spent` leaves the island (a stand-in for loot→inventory etc.).
    type External = TestEvent;

    fn check(
        state: &Self::State,
        _rules: &Self::Rules,
        p: &Precondition<Self>,
    ) -> Result<(), Violation> {
        match p {
            Precondition::ResourceAtLeast { id, kind: _, amount } => {
                if state.qi.get(id).copied().unwrap_or(0) >= *amount {
                    Ok(())
                } else {
                    Err(Violation {
                        kind: PreconditionKind::ResourceAtLeast,
                        entity: Some(*id),
                    })
                }
            }
            // Structural variants never reach the domain (island handles them).
            _ => Ok(()),
        }
    }

    fn apply(
        state: &mut Self::State,
        rules: &Self::Rules,
        input: &QueuedInput<Self>,
        rng: &mut DetRng,
    ) -> Vec<Self::Event> {
        match &input.payload {
            TestPayload::Panic => panic!("TestDomain poison pill (chaos harness)"),
            TestPayload::Inc { id, by } => {
                let c = state.counters.entry(*id).or_insert(0);
                *c = (*c + by).min(rules.max_counter);
                vec![TestEvent::Inced { id: *id, new: *c }]
            }
            TestPayload::Spend { id, amount } => {
                // Precondition-guarded; saturate anyway — apply must be total.
                let q = state.qi.entry(*id).or_insert(0);
                *q = q.saturating_sub(*amount);
                vec![TestEvent::Spent { id: *id, left: *q }]
            }
            TestPayload::Roll { id } => vec![TestEvent::Rolled {
                id: *id,
                value: rng.next_u64(),
            }],
            TestPayload::Noop => vec![],
        }
    }

    fn externals(events: &[Self::Event]) -> Vec<Self::External> {
        events
            .iter()
            .filter(|e| matches!(e, TestEvent::Spent { .. }))
            .cloned()
            .collect()
    }
}

/// Convenience input constructor (Seq is stamped at admission; the value here
/// is a placeholder the ingress overwrites).
pub fn input(
    input_id: u128,
    payload: TestPayload,
    preconditions: Vec<Precondition<TestDomain>>,
    on_invalid: sim_core::Fallback<TestDomain>,
) -> QueuedInput<TestDomain> {
    QueuedInput {
        seq: sim_core::Seq(u64::MAX),
        input_id: sim_core::InputId(input_id),
        class: sim_core::Class::B,
        source: sim_core::Producer::PlayerInput,
        payload,
        preconditions,
        on_invalid,
        admitted_gen: sim_core::Gen(u32::MAX), // stamped at admission
        deadline: None,
    }
}

/// `input()` with an SL-A4 deadline.
pub fn input_deadline(
    input_id: u128,
    payload: TestPayload,
    deadline: sim_core::Tick,
    on_invalid: sim_core::Fallback<TestDomain>,
) -> QueuedInput<TestDomain> {
    let mut q = input(input_id, payload, vec![], on_invalid);
    q.deadline = Some(deadline);
    q
}
