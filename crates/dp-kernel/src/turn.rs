//! Cycle 20 / L4.K — `turn` Rust mirror of `contracts/turn/` (Go).
//!
//! ## Send-safety guarantee
//!
//! [`TurnContext`] is NOT `Sync` for mutable access — it's wrapped in a
//! `Mutex` so concurrent `advance` calls serialize, but the type intentionally
//! does NOT implement `Send` for shared MUTABLE references across `.await`
//! boundaries. This is a deliberate deadlock-prevention measure: holding a
//! TurnContext lock across an `.await` is the classic async-Rust deadlock
//! pattern. The Go side relies on a runtime mutex; we get compile-time help.
//!
//! ## Q-L4-1 parity
//!
//! Wire format matches the Go struct field-for-field (snake_case JSON tags).

use serde::{Deserialize, Serialize};
use std::sync::Mutex;
use std::sync::atomic::{AtomicI64, Ordering};

/// TurnContextVersion = 1 for V1 wire format.
pub const TURN_CONTEXT_VERSION: u32 = 1;

/// TurnState — 8-variant SR11 vocabulary. Wire format = snake_case.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TurnState {
    /// Accepted, queued.
    Pending,
    /// Preflight (auth, quota, capacity).
    Validating,
    /// Selecting downstream service / model.
    Routing,
    /// LLM call / projection write in flight.
    Executing,
    /// Partial response visible to user.
    Streaming,
    /// Terminal success.
    Completed,
    /// Terminal failure.
    Failed,
    /// User-initiated abort or upstream timeout.
    Cancelled,
}

impl TurnState {
    /// Canonical snake_case string.
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Pending => "pending",
            Self::Validating => "validating",
            Self::Routing => "routing",
            Self::Executing => "executing",
            Self::Streaming => "streaming",
            Self::Completed => "completed",
            Self::Failed => "failed",
            Self::Cancelled => "cancelled",
        }
    }

    /// All 8 states (deterministic order; matches Go `AllTurnStates`).
    pub fn all() -> &'static [TurnState] {
        &[
            Self::Pending,
            Self::Validating,
            Self::Routing,
            Self::Executing,
            Self::Streaming,
            Self::Completed,
            Self::Failed,
            Self::Cancelled,
        ]
    }

    /// True iff the state ends the turn.
    pub fn is_terminal(&self) -> bool {
        matches!(self, Self::Completed | Self::Failed | Self::Cancelled)
    }
}

/// Transition errors.
#[derive(Debug, thiserror::Error)]
pub enum TransitionError {
    /// (from, to) not in the allowed graph.
    #[error("turn: invalid transition {from:?} -> {to:?}")]
    Invalid {
        /// State the turn was in.
        from: TurnState,
        /// State the caller requested.
        to: TurnState,
    },
    /// Cannot transition from a terminal state.
    #[error("turn: terminal state {0:?} has no outgoing transitions")]
    Terminal(TurnState),
}

/// Returns Ok(()) if `from -> to` is allowed.
pub fn assert_transition(from: TurnState, to: TurnState) -> Result<(), TransitionError> {
    if from.is_terminal() {
        return Err(TransitionError::Terminal(from));
    }
    let ok = match (from, to) {
        (TurnState::Pending, TurnState::Validating | TurnState::Cancelled) => true,
        (TurnState::Validating, TurnState::Routing | TurnState::Failed | TurnState::Cancelled) => true,
        (TurnState::Routing, TurnState::Executing | TurnState::Failed | TurnState::Cancelled) => true,
        (TurnState::Executing, TurnState::Streaming | TurnState::Completed | TurnState::Failed | TurnState::Cancelled) => true,
        (TurnState::Streaming, TurnState::Completed | TurnState::Failed | TurnState::Cancelled) => true,
        _ => false,
    };
    if ok {
        Ok(())
    } else {
        Err(TransitionError::Invalid { from, to })
    }
}

/// Versioned cross-service envelope.
///
/// `state` is wrapped in a [`Mutex`] so concurrent threads can call
/// [`TurnContext::advance`] safely. Holding the lock across `.await` is a
/// classic deadlock pattern, so callers SHOULD only Advance from sync code
/// paths (or release before awaiting).
///
/// Serialization deliberately omits the mutex-guarded state field — the
/// wire-format `state` field is rendered manually via [`TurnContext::to_wire`]
/// so the JSON includes a snapshot of the state at serialization time.
#[derive(Debug, Serialize, Deserialize)]
pub struct TurnContext {
    /// Wire format version. V1 = 1.
    pub envelope_version: u32,
    /// Turn UUID (string).
    pub turn_id: String,
    /// Session UUID.
    pub session_id: String,
    /// Reality UUID.
    pub reality_id: String,
    /// Actor (user or service id).
    pub actor_id: String,
    /// Wall clock at turn admission (unix nanos).
    pub started_at_nanos: i64,
    /// Current state (guarded by mutex). Skipped in serde derive; use
    /// [`TurnContext::to_wire`] for a serializable snapshot.
    #[serde(skip, default = "default_pending_state")]
    state: Mutex<TurnState>,
}

fn default_pending_state() -> Mutex<TurnState> {
    Mutex::new(TurnState::Pending)
}

/// Serializable snapshot of a [`TurnContext`] — call [`TurnContext::to_wire`]
/// to obtain one. Distinct from `TurnContext` because the wire form has no
/// mutex (the state is a snapshot taken at serialization time).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct TurnContextWire {
    /// Wire format version.
    pub envelope_version: u32,
    /// Turn UUID.
    pub turn_id: String,
    /// Session UUID.
    pub session_id: String,
    /// Reality UUID.
    pub reality_id: String,
    /// Actor id.
    pub actor_id: String,
    /// Wall clock at turn admission (unix nanos).
    pub started_at_nanos: i64,
    /// Snapshot of state at serialization time.
    pub state: TurnState,
}

impl TurnContext {
    /// Construct a fresh context in `Pending`.
    pub fn new(
        turn_id: impl Into<String>,
        session_id: impl Into<String>,
        reality_id: impl Into<String>,
        actor_id: impl Into<String>,
        started_at_nanos: i64,
    ) -> Self {
        Self {
            envelope_version: TURN_CONTEXT_VERSION,
            turn_id: turn_id.into(),
            session_id: session_id.into(),
            reality_id: reality_id.into(),
            actor_id: actor_id.into(),
            started_at_nanos,
            state: Mutex::new(TurnState::Pending),
        }
    }

    /// Snapshot the current state.
    pub fn state(&self) -> TurnState {
        *self.state.lock().unwrap()
    }

    /// Transition to `to`. Returns [`TransitionError`] on illegal transition.
    pub fn advance(&self, to: TurnState) -> Result<(), TransitionError> {
        let mut g = self.state.lock().unwrap();
        assert_transition(*g, to)?;
        *g = to;
        Ok(())
    }

    /// Force the state to `s` without checking the transition graph. ONLY
    /// for replay/recovery code that loads a checkpoint.
    pub fn force_state(&self, s: TurnState) {
        *self.state.lock().unwrap() = s;
    }

    /// Snapshot to a serializable wire form (state captured at call time).
    pub fn to_wire(&self) -> TurnContextWire {
        TurnContextWire {
            envelope_version: self.envelope_version,
            turn_id: self.turn_id.clone(),
            session_id: self.session_id.clone(),
            reality_id: self.reality_id.clone(),
            actor_id: self.actor_id.clone(),
            started_at_nanos: self.started_at_nanos,
            state: self.state(),
        }
    }
}

// ── In-flight tracker (cycle-18 lifecycle integration) ───────────────────

/// Counts active (non-terminal) turns. `End` decrements after `Start`.
/// Concurrent-safe via atomic.
#[derive(Debug, Default)]
pub struct TurnInFlightTracker {
    inflight: AtomicI64,
}

impl TurnInFlightTracker {
    /// Construct.
    pub fn new() -> Self {
        Self::default()
    }

    /// Record a new turn; returns a guard that decrements on drop.
    pub fn start(&self) -> TurnGuard<'_> {
        self.inflight.fetch_add(1, Ordering::SeqCst);
        TurnGuard { tracker: self }
    }

    /// Current count.
    pub fn in_flight(&self) -> i64 {
        self.inflight.load(Ordering::SeqCst)
    }
}

/// RAII guard returned by [`TurnInFlightTracker::start`]. Decrements on drop.
pub struct TurnGuard<'a> {
    tracker: &'a TurnInFlightTracker,
}

impl Drop for TurnGuard<'_> {
    fn drop(&mut self) {
        let v = self.tracker.inflight.fetch_sub(1, Ordering::SeqCst);
        debug_assert!(v >= 1, "TurnGuard dropped without matching Start");
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parity_state_strings_match_go() {
        let want = ["pending", "validating", "routing", "executing", "streaming", "completed", "failed", "cancelled"];
        for (s, w) in TurnState::all().iter().zip(want.iter()) {
            assert_eq!(&s.as_str(), w);
        }
    }

    #[test]
    fn assert_transition_happy_paths() {
        let happy = [
            (TurnState::Pending, TurnState::Validating),
            (TurnState::Validating, TurnState::Routing),
            (TurnState::Routing, TurnState::Executing),
            (TurnState::Executing, TurnState::Streaming),
            (TurnState::Streaming, TurnState::Completed),
            (TurnState::Executing, TurnState::Completed),
            (TurnState::Pending, TurnState::Cancelled),
        ];
        for (from, to) in happy {
            assert!(assert_transition(from, to).is_ok(), "{from:?} -> {to:?}");
        }
    }

    #[test]
    fn assert_transition_rejects_backwards() {
        let err = assert_transition(TurnState::Executing, TurnState::Routing).unwrap_err();
        assert!(matches!(err, TransitionError::Invalid { .. }));
    }

    #[test]
    fn assert_transition_rejects_from_terminal() {
        for t in [TurnState::Completed, TurnState::Failed, TurnState::Cancelled] {
            let err = assert_transition(t, TurnState::Pending).unwrap_err();
            assert!(matches!(err, TransitionError::Terminal(_)));
        }
    }

    #[test]
    fn context_default_pending() {
        let c = TurnContext::new("t", "s", "r", "u", 0);
        assert_eq!(c.state(), TurnState::Pending);
        assert_eq!(c.envelope_version, TURN_CONTEXT_VERSION);
    }

    #[test]
    fn context_advance_full_happy_path() {
        let c = TurnContext::new("t", "s", "r", "u", 0);
        for to in [
            TurnState::Validating,
            TurnState::Routing,
            TurnState::Executing,
            TurnState::Streaming,
            TurnState::Completed,
        ] {
            c.advance(to).expect("advance");
        }
        assert_eq!(c.state(), TurnState::Completed);
    }

    #[test]
    fn context_rejects_invalid_transition() {
        let c = TurnContext::new("t", "s", "r", "u", 0);
        let err = c.advance(TurnState::Completed).unwrap_err();
        assert!(matches!(err, TransitionError::Invalid { .. }));
    }

    #[test]
    fn force_state_bypasses_graph() {
        let c = TurnContext::new("t", "s", "r", "u", 0);
        c.force_state(TurnState::Executing);
        assert_eq!(c.state(), TurnState::Executing);
    }

    #[test]
    fn tracker_start_drop_decrements() {
        let t = TurnInFlightTracker::new();
        assert_eq!(t.in_flight(), 0);
        let g = t.start();
        assert_eq!(t.in_flight(), 1);
        drop(g);
        assert_eq!(t.in_flight(), 0);
    }

    #[test]
    fn tracker_handles_many_starts() {
        let t = TurnInFlightTracker::new();
        let guards: Vec<_> = (0..10).map(|_| t.start()).collect();
        assert_eq!(t.in_flight(), 10);
        drop(guards);
        assert_eq!(t.in_flight(), 0);
    }
}
