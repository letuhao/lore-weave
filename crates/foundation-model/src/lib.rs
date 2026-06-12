//! S9 — Stateright model checking of foundation protocols.
//!
//! Models (one module each): [`lifecycle`] (I9 lifecycle CAS), [`outbox`] (I13
//! outbox under crash), [`fanout`] (I7 cross-reality fan-out).
//!
//! The `spike` module below is a permanent record of the two Stateright APIs the
//! models rely on: the positive `assert_properties()` (all safety+liveness hold)
//! and the negative `discovery(name)` (a bite-test asserts a counterexample
//! EXISTS). It de-risked the dep + the liveness/discovery APIs.

pub mod fanout;
pub mod lifecycle;
pub mod outbox;

#[cfg(test)]
mod spike {
    use stateright::{Checker, Model, Property};

    struct Counter {
        ceiling: u8,
    }

    impl Model for Counter {
        type State = u8;
        type Action = ();

        fn init_states(&self) -> Vec<Self::State> {
            vec![0]
        }

        fn actions(&self, state: &Self::State, actions: &mut Vec<Self::Action>) {
            if *state < self.ceiling {
                actions.push(());
            }
        }

        fn next_state(&self, state: &Self::State, _action: Self::Action) -> Option<Self::State> {
            Some(state + 1)
        }

        fn properties(&self) -> Vec<Property<Self>> {
            vec![
                // Safety: never exceed the ceiling.
                Property::<Self>::always("bounded", |model, state| *state <= model.ceiling),
                // Liveness: every path eventually reaches the ceiling.
                Property::<Self>::eventually("reaches ceiling", |model, state| {
                    *state == model.ceiling
                }),
            ]
        }
    }

    #[test]
    fn stateright_checks_safety_and_liveness() {
        let checker = Counter { ceiling: 5 }.checker().spawn_bfs().join();
        checker.assert_properties();
    }

    /// A model that DELIBERATELY violates a safety property, to confirm the
    /// negative-assertion API the S9 bite-tests depend on (review #5): the
    /// checker must REPORT a discovery (counterexample) for the violated
    /// property, and assert_properties() must panic on it.
    struct BadCounter;
    impl Model for BadCounter {
        type State = u8;
        type Action = ();
        fn init_states(&self) -> Vec<Self::State> {
            vec![0]
        }
        fn actions(&self, state: &Self::State, actions: &mut Vec<Self::Action>) {
            if *state < 10 {
                actions.push(());
            }
        }
        fn next_state(&self, state: &Self::State, _action: Self::Action) -> Option<Self::State> {
            Some(state + 1)
        }
        fn properties(&self) -> Vec<Property<Self>> {
            // This will be violated (state reaches 10 > 3).
            vec![Property::<Self>::always("under three", |_, state| {
                *state < 3
            })]
        }
    }

    #[test]
    fn bite_test_api_reports_a_discovery() {
        let checker = BadCounter.checker().spawn_bfs().join();
        // The bite-test mechanism: a violated `always` property yields a discovery.
        assert!(
            checker.discovery("under three").is_some(),
            "expected a counterexample for the deliberately-violated property"
        );
    }
}
