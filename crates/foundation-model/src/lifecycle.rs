//! S9 Model #1 — lifecycle CAS (I9).
//!
//! Model-checks `AttemptStateTransition`'s state-machine + compare-and-swap
//! semantics against the REAL `contracts/meta/transitions.yaml` graph (embedded
//! via `include_bytes!`, so a graph edit recompiles + re-checks this model — no
//! drift from production).
//!
//! ## The CAS race, modeled honestly
//!
//! A single-action model checker makes each action atomic, so a read-modify-
//! write race is modeled as TWO steps with the read result carried in state:
//!   - `Intend(to)`  — an actor reads the current `status` and intends `→to`
//!                     (enqueues `Attempt { from: status, to }`).
//!   - `Commit(i)`   — applies pending attempt `i`: iff `status == attempt.from`
//!                     (the CAS), advance; else the attempt is dropped (lost race).
//!
//! `last_transition` records the ACTUAL hop a commit applied — `(status_at_commit,
//! to)` — which is what makes a CAS violation OBSERVABLE: with broken CAS, the
//! status jumps along a hop computed from a STALE read, and that hop is illegal in
//! the graph. The safety property "every applied hop is a legal edge" fires.
//!
//! ## Non-vacuity
//!
//! The action set CAN reach a violation — the `enforce_cas` flag (false in the
//! bite-test) removes the CAS check, and Stateright finds an interleaving where
//! two attempts from the same state both commit, producing an illegal hop. The
//! CAS check (not an action-set restriction) is what holds the invariant.
//!
//! ## Liveness (cycle-robust)
//!
//! The real graph is CYCLIC (`active↔migrating`, `pending_close↔active`), so the
//! protocol does NOT force termination — "always eventually dropped" would be a
//! FALSE claim (an infinite legal loop is allowed). The honest liveness is that
//! completion is REACHABLE / not deadlocked: `sometimes(status == dropped)`.
//!
//! ## Bounds (design-altitude — D-S9-MODEL-SCOPE)
//!
//! Bounded to `PENDING_CAP` concurrent attempts + a total `BUDGET` of reads to
//! keep the space finite. Verifies the PROTOCOL, not the impl's real SQL/locking
//! (that's H1-loom).

use meta_rs::transitions::{ResourceGraph, TransitionGraph};
use stateright::{Model, Property};

const TRANSITIONS_YAML: &[u8] = include_bytes!("../../../contracts/meta/transitions.yaml");

/// Max concurrent in-flight attempts (racers). MUST be >= 2: the broken-CAS bite
/// only produces an illegal hop via the RACE (a lone attempt commits legally even
/// without CAS, since `status == from` holds naturally). With CAP=1 there is no
/// race and the bite would stop firing.
const PENDING_CAP: usize = 2;
/// Total reads allowed across a run (bounds the otherwise-cyclic-infinite space).
const BUDGET: u8 = 10;

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub struct LState {
    status: String,
    /// In-flight attempts: each `(from, to)` is "an actor observed status==from
    /// and intends →to".
    pending: Vec<(String, String)>,
    /// The actual hop the last commit applied: `(status_at_commit, to)`.
    last_transition: Option<(String, String)>,
    /// Remaining reads (bounds the model).
    budget: u8,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
pub enum LAction {
    Intend(String),
    Commit(usize),
}

pub struct LifecycleModel {
    graph: ResourceGraph,
    /// false = the bite variant (commit skips the CAS check).
    enforce_cas: bool,
}

impl LifecycleModel {
    fn reality() -> ResourceGraph {
        let g = TransitionGraph::parse(TRANSITIONS_YAML).expect("parse transitions.yaml");
        g.resources
            .get("reality")
            .expect("reality resource")
            .clone()
    }

    pub fn correct() -> Self {
        Self {
            graph: Self::reality(),
            enforce_cas: true,
        }
    }

    /// The bite variant: commit ignores `status == from` (no CAS).
    pub fn broken_cas() -> Self {
        Self {
            graph: Self::reality(),
            enforce_cas: false,
        }
    }

    /// Sorted legal targets from `from` (deterministic action order).
    fn legal_targets(&self, from: &str) -> Vec<String> {
        let mut out: Vec<String> = match self.graph.transitions.get(from) {
            Some(tos) => tos
                .iter()
                .filter(|to| self.graph.allows(from, to).0)
                .cloned()
                .collect(),
            None => vec![],
        };
        out.sort();
        out
    }
}

impl Model for LifecycleModel {
    type State = LState;
    type Action = LAction;

    fn init_states(&self) -> Vec<Self::State> {
        let mut starts: Vec<String> = self.graph.initial_states.iter().cloned().collect();
        starts.sort();
        starts
            .into_iter()
            .map(|s| LState {
                status: s,
                pending: vec![],
                last_transition: None,
                budget: BUDGET,
            })
            .collect()
    }

    fn actions(&self, state: &Self::State, actions: &mut Vec<Self::Action>) {
        if state.budget > 0 && state.pending.len() < PENDING_CAP {
            for to in self.legal_targets(&state.status) {
                actions.push(LAction::Intend(to));
            }
        }
        for i in 0..state.pending.len() {
            actions.push(LAction::Commit(i));
        }
    }

    fn next_state(&self, state: &Self::State, action: Self::Action) -> Option<Self::State> {
        let mut ns = state.clone();
        match action {
            LAction::Intend(to) => {
                ns.pending.push((state.status.clone(), to));
                ns.budget -= 1;
            }
            LAction::Commit(i) => {
                let (from, to) = ns.pending.remove(i);
                let cas_ok = !self.enforce_cas || state.status == from;
                if cas_ok {
                    // Record the ACTUAL hop (status-before → to). With correct CAS
                    // status==from, so this is the legal edge that was enqueued;
                    // with broken CAS it may be an illegal hop from a stale read.
                    ns.last_transition = Some((state.status.clone(), to.clone()));
                    ns.status = to;
                }
                // else: CAS lost → attempt dropped, no state change.
            }
        }
        Some(ns)
    }

    fn properties(&self) -> Vec<Property<Self>> {
        vec![
            Property::<Self>::always("status is a valid graph node", |m, s| {
                m.graph.states.contains(&s.status)
            }),
            // The CAS safety: every hop the system actually took is a legal edge.
            // Broken CAS produces a hop from a stale read → illegal → fires.
            Property::<Self>::always("every applied hop is a legal edge", |m, s| {
                match &s.last_transition {
                    None => true,
                    Some((from, to)) => m.graph.allows(from, to).0,
                }
            }),
            // Liveness (cycle-robust): completion is reachable / not deadlocked.
            Property::<Self>::sometimes("reaches terminal (dropped)", |_m, s| {
                s.status == "dropped"
            }),
        ]
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use stateright::Checker; // join()/assert_properties()/discovery() live here

    #[test]
    fn lifecycle_cas_holds_safety_and_completion_reachable() {
        let checker = LifecycleModel::correct().checker().spawn_bfs().join();
        checker.assert_properties();
        // Coverage sanity: non-trivial state space (D-S9-MODEL-SCOPE — not a toy).
        assert!(
            checker.unique_state_count() > 1_000,
            "state space too small ({}); model may be degenerate",
            checker.unique_state_count()
        );
    }

    #[test]
    fn bite_broken_cas_violates_legal_hop() {
        let checker = LifecycleModel::broken_cas().checker().spawn_bfs().join();
        // The bite: removing the CAS check MUST be caught by the legal-hop safety.
        assert!(
            checker
                .discovery("every applied hop is a legal edge")
                .is_some(),
            "broken CAS should have produced an illegal hop counterexample"
        );
    }
}
