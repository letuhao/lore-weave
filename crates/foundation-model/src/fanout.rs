//! S9 Model #3 — cross-reality fan-out (I7).
//!
//! An `xreality.*` event emitted in one reality is dispatched by the meta-worker
//! to the SUBSCRIBED realities — and ONLY those. Verifies no leak (a non-
//! subscriber never receives it) and that full coverage is achievable (no miss).
//!
//! ## Non-vacuity (review #1 — the model must be ABLE to leak)
//!
//! The dispatch action ranges over the WHOLE reality universe — `DispatchTo(r)`
//! is generated for EVERY undelivered reality, including non-subscribers. The
//! subscription check lives in `next_state` (the mechanism under test): in the
//! correct model a dispatch to a non-subscriber is a no-op (the guard rejects);
//! in the bite the guard is removed, so the same action delivers to a non-
//! subscriber → leak. The guard, not an action-set restriction, holds no-leak.
//!
//! ## Liveness (cycle-robust)
//!
//! No-miss is "full coverage is REACHABLE" — `sometimes(delivered == subscribers)`
//! — not `eventually`, because a lazy dispatcher (only ever issuing no-op
//! non-subscriber dispatches) is a legal behavior that never completes; the
//! protocol does not FORCE coverage. Mirrors the lifecycle's `sometimes(dropped)`.
//!
//! ## Bounds (D-S9-MODEL-SCOPE): a fixed reality universe; the subscriber set is
//! hand-specified (D-S9-FANOUT-SUBSCRIBER-SOURCE), not loaded from the real
//! `book_reality_subscription` semantics.

use stateright::{Model, Property};

/// Reality universe size (bit indices 0..R).
const R: usize = 4;
/// Realities subscribed to the xreality topic (0,1,2 subscribe; 3 does NOT).
const SUBSCRIBERS: u8 = 0b0111;
/// Non-subscriber realities within 0..R (the leak surface).
const NON_SUBSCRIBERS: u8 = ((1 << R) - 1) & !SUBSCRIBERS;

#[inline]
fn bit(r: usize) -> u8 {
    1 << r
}
#[inline]
fn has(set: u8, r: usize) -> bool {
    set & bit(r) != 0
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct FState {
    emitted: bool,
    /// Realities that received the event (bitset).
    delivered: u8,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum FAction {
    Emit,
    /// Meta-worker considers dispatching to reality `r` (any reality — the
    /// subscription check is applied on apply).
    DispatchTo(usize),
}

pub struct FanoutModel {
    /// false = the bite (the subscription guard is removed → leaks).
    honor_subscription: bool,
}

impl FanoutModel {
    pub fn correct() -> Self {
        Self {
            honor_subscription: true,
        }
    }
    /// Bite: the dispatch guard admits non-subscribers.
    pub fn leaky() -> Self {
        Self {
            honor_subscription: false,
        }
    }
}

impl Model for FanoutModel {
    type State = FState;
    type Action = FAction;

    fn init_states(&self) -> Vec<Self::State> {
        vec![FState {
            emitted: false,
            delivered: 0,
        }]
    }

    fn actions(&self, s: &Self::State, actions: &mut Vec<Self::Action>) {
        if !s.emitted {
            actions.push(FAction::Emit);
            return;
        }
        // Range over the WHOLE universe — the meta-worker COULD address any
        // reality; the subscription check (in next_state) is what bounds it.
        for r in 0..R {
            if !has(s.delivered, r) {
                actions.push(FAction::DispatchTo(r));
            }
        }
    }

    fn next_state(&self, s: &Self::State, action: Self::Action) -> Option<Self::State> {
        let mut ns = s.clone();
        match action {
            FAction::Emit => ns.emitted = true,
            FAction::DispatchTo(r) => {
                // The mechanism: deliver iff the reality is subscribed. The bite
                // removes the check, so a non-subscriber gets delivered → leak.
                let admitted = !self.honor_subscription || has(SUBSCRIBERS, r);
                if admitted {
                    ns.delivered |= bit(r);
                }
                // else: no-op (guard rejected the non-subscriber).
            }
        }
        Some(ns)
    }

    fn properties(&self) -> Vec<Property<Self>> {
        vec![
            // Safety: the event never reaches a non-subscriber. Non-vacuous — the
            // model explores DispatchTo(non-subscriber); only the guard blocks it.
            Property::<Self>::always("no leak (delivered ⊆ subscribers)", |_m, s| {
                s.delivered & NON_SUBSCRIBERS == 0
            }),
            // Liveness (cycle-robust): full coverage of subscribers is reachable.
            Property::<Self>::sometimes("no miss (all subscribers reachable)", |_m, s| {
                s.delivered == SUBSCRIBERS
            }),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use stateright::Checker;

    #[test]
    fn fanout_no_leak_and_full_coverage_reachable() {
        let checker = FanoutModel::correct().checker().spawn_bfs().join();
        checker.assert_properties();
        // Coverage sanity: the model explored the reality universe, not a toy.
        assert!(
            checker.unique_state_count() > 5,
            "fanout state space too small ({}); model may be degenerate",
            checker.unique_state_count()
        );
    }

    #[test]
    fn bite_leaky_dispatch_reaches_a_non_subscriber() {
        let checker = FanoutModel::leaky().checker().spawn_bfs().join();
        assert!(
            checker
                .discovery("no leak (delivered ⊆ subscribers)")
                .is_some(),
            "a dispatch guard that admits non-subscribers should leak"
        );
    }
}
