//! S9 Model #2 — outbox → publisher → consumer under crash (I13).
//!
//! Verifies the transactional-outbox guarantees: a committed state-change is
//! never lost (it was enqueued in the SAME tx, so a crash can't split them), and
//! an idempotent consumer never applies an event twice despite at-least-once
//! redelivery after a crash.
//!
//! ## Non-vacuity (review #1/#2 — the model must be ABLE to fail)
//!
//! The dual-write failure is EXPRESSIBLE: in the non-atomic variant the state
//! write and the outbox-enqueue are SEPARATE steps with an in-flight `pending`
//! marker; a crash drops the in-flight enqueue (the app committed state, crashed
//! before enqueue, and does NOT retry on recovery) → the event is permanently in
//! `state` but never `enqueued` → lost. The same-tx guarantee (the atomic
//! `Write`) is the mechanism that prevents it, NOT an action-set restriction.
//!
//! ## Fairness (review #4)
//!
//! Liveness `eventually` is false under unbounded crashes, so crashes are bounded
//! by a finite `crashes_left` budget — the fairness assumption that crashes don't
//! recur forever. The no-loss predicate is `state == ALL && all applied` (false at
//! init, so non-vacuous — not the trivially-true "empty covers empty").
//!
//! ## Bounds (D-S9-MODEL-SCOPE): N events, a 1-crash budget; protocol-altitude.

use stateright::{Model, Property};

/// Number of distinct events (bit indices 0..N). W4.4 (D-S9-MODEL-SCOPE) raised it
/// 2→3 to explore deeper outbox-drain interleavings (exhaustive BFS).
const N: usize = 3;
/// All-events bitmask.
const ALL: u8 = (1 << N) - 1;
/// Finite crash budget (fairness — crashes don't recur forever). W4.4 raised it 1→2
/// so a SECOND crash can interleave (e.g. crash mid-recovery), a strictly larger
/// fault schedule than the original single-crash bound.
const CRASH_BUDGET: u8 = 2;

#[inline]
fn bit(e: usize) -> u8 {
    1 << e
}
#[inline]
fn has(set: u8, e: usize) -> bool {
    set & bit(e) != 0
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct OState {
    /// Committed state-changes (durable, monotonic).
    state: u8,
    /// Events with a durable outbox row (== `state` in the atomic model).
    enqueued: u8,
    /// Non-atomic only: state written but enqueue not yet done (in-flight; a
    /// crash drops it — the dual-write loss window).
    pending: u8,
    /// Delivered to the stream (VOLATILE — dropped on crash).
    published: u8,
    /// Per-event apply COUNT, saturating at 2 (so a 2 = an observed dup).
    applied: [u8; N],
    crashes_left: u8,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum OAction {
    /// Atomic state+enqueue (same tx).
    Write(usize),
    /// Non-atomic step 1 (state only; sets the in-flight `pending`).
    WriteState(usize),
    /// Non-atomic step 2 (enqueue the in-flight write).
    Enqueue(usize),
    Publish(usize),
    Consume(usize),
    Crash,
}

pub struct OutboxModel {
    /// false = the non-atomic (dual-write) bite.
    atomic_write: bool,
    /// false = the non-idempotent-consumer bite.
    idempotent_consume: bool,
}

impl OutboxModel {
    pub fn correct() -> Self {
        Self {
            atomic_write: true,
            idempotent_consume: true,
        }
    }
    /// Bite: state and outbox written in separate steps (no same-tx) → a crash
    /// between them loses the event.
    pub fn non_atomic() -> Self {
        Self {
            atomic_write: false,
            idempotent_consume: true,
        }
    }
    /// Bite: the consumer is not idempotent → redelivery after a crash double-applies.
    pub fn non_idempotent() -> Self {
        Self {
            atomic_write: true,
            idempotent_consume: false,
        }
    }
}

impl Model for OutboxModel {
    type State = OState;
    type Action = OAction;

    fn init_states(&self) -> Vec<Self::State> {
        vec![OState {
            state: 0,
            enqueued: 0,
            pending: 0,
            published: 0,
            applied: [0; N],
            crashes_left: CRASH_BUDGET,
        }]
    }

    fn actions(&self, s: &Self::State, actions: &mut Vec<Self::Action>) {
        for e in 0..N {
            if self.atomic_write {
                if !has(s.state, e) {
                    actions.push(OAction::Write(e));
                }
            } else {
                if !has(s.state, e) {
                    actions.push(OAction::WriteState(e));
                }
                if has(s.pending, e) && !has(s.enqueued, e) {
                    actions.push(OAction::Enqueue(e));
                }
            }
            if has(s.enqueued, e) && !has(s.published, e) {
                actions.push(OAction::Publish(e));
            }
            if has(s.published, e) {
                // Gate consume so it only fires when it changes state (avoids
                // infinite no-op self-loops): idempotent → only if not yet applied;
                // non-idempotent → up to the dup-detection cap of 2.
                let applied = s.applied[e];
                if (self.idempotent_consume && applied == 0)
                    || (!self.idempotent_consume && applied < 2)
                {
                    actions.push(OAction::Consume(e));
                }
            }
        }
        if s.crashes_left > 0 {
            actions.push(OAction::Crash);
        }
    }

    fn next_state(&self, s: &Self::State, action: Self::Action) -> Option<Self::State> {
        let mut ns = s.clone();
        match action {
            OAction::Write(e) => {
                ns.state |= bit(e);
                ns.enqueued |= bit(e); // same tx — atomic
            }
            OAction::WriteState(e) => {
                ns.state |= bit(e);
                ns.pending |= bit(e); // in-flight enqueue intent
            }
            OAction::Enqueue(e) => {
                ns.enqueued |= bit(e);
                ns.pending &= !bit(e);
            }
            OAction::Publish(e) => {
                ns.published |= bit(e);
            }
            OAction::Consume(e) => {
                if self.idempotent_consume {
                    ns.applied[e] = 1;
                } else {
                    ns.applied[e] = (ns.applied[e] + 1).min(2);
                }
            }
            OAction::Crash => {
                ns.published = 0; // volatile stream lost
                ns.pending = 0; // in-flight (non-committed) enqueue intent abandoned
                ns.crashes_left -= 1;
            }
        }
        Some(ns)
    }

    fn properties(&self) -> Vec<Property<Self>> {
        vec![
            // Safety: state and its outbox row are written atomically (same tx) —
            // every reachable state has them equal. INSTANTANEOUS (distinct from
            // the eventual no-loss below): the non-atomic bite splits the writes
            // (WriteState before Enqueue) and reaches state != enqueued
            // immediately, even without a crash.
            Property::<Self>::always("state and outbox written atomically", |_m, s| {
                s.state == s.enqueued
            }),
            // Safety: an event is never applied more than once (idempotent
            // consumer absorbs redelivery). The non-idempotent bite reaches a
            // count of 2.
            Property::<Self>::always("no event is applied more than once", |_m, s| {
                s.applied.iter().all(|&c| c <= 1)
            }),
            // Liveness (with finite-crash fairness): every committed state-change
            // is eventually delivered+applied. Non-vacuous: false at init (state
            // empty != ALL). The non-atomic bite reaches state==ALL with a
            // permanently-unenqueued event → never applied → violated.
            Property::<Self>::eventually("all committed events are eventually applied", |_m, s| {
                s.state == ALL && (0..N).all(|e| s.applied[e] >= 1)
            }),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use stateright::Checker;

    #[test]
    fn outbox_holds_atomicity_no_dup_and_no_loss() {
        let checker = OutboxModel::correct().checker().spawn_bfs().join();
        checker.assert_properties();
        assert!(
            checker.unique_state_count() > 30,
            "outbox state space too small ({}); model may be degenerate",
            checker.unique_state_count()
        );
    }

    #[test]
    fn bite_non_atomic_write_breaks_atomicity_and_loses_an_event() {
        let checker = OutboxModel::non_atomic().checker().spawn_bfs().join();
        // Immediate: the split write reaches state != enqueued.
        assert!(
            checker
                .discovery("state and outbox written atomically")
                .is_some(),
            "dual-write must reach a state where state != outbox (broken atomicity)"
        );
        // Eventual: a crash in the split window permanently loses the event.
        assert!(
            checker
                .discovery("all committed events are eventually applied")
                .is_some(),
            "dual-write + crash should permanently lose a committed event"
        );
    }

    #[test]
    fn bite_non_idempotent_consumer_double_applies() {
        let checker = OutboxModel::non_idempotent().checker().spawn_bfs().join();
        assert!(
            checker
                .discovery("no event is applied more than once")
                .is_some(),
            "a non-idempotent consumer should double-apply under crash redelivery"
        );
    }
}
