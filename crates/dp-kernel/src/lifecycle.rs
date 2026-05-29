//! `lifecycle` — Rust mirror of `contracts/lifecycle/` (cycles 7 + 18).
//!
//! This module mirrors the Go `contracts/lifecycle/` package so Rust
//! services receive the same enum semantics + drain orchestration without
//! a network round-trip to a Go shim.
//!
//! ### What's here
//!
//! - [`ServiceMode`] — the cycle-7 system-wide mode enum (Full | Limited
//!   | Essentials | ReadOnly | Offline). Integer values + wire strings
//!   MUST match `contracts/lifecycle/service_mode.go` exactly so a
//!   `mode_shift` Redis control message round-trips losslessly.
//! - [`PresenceState`] — cycle-18 / SR11-D3 session-scoped liveness enum
//!   (6 variants). Distinct from [`ServiceMode`] (system) and from
//!   GoneState (entity existence).
//! - [`drain`] — cycle-18 / L4.G ordered shutdown orchestrator.
//!   Identical hook order to Go `Drain`: StopAccepting → WaitInFlight
//!   → FlushOutbox → CloseBreakers → CloseResources.
//!
//! ### Parity rules
//!
//! - Cycle-7 `service_mode.go` + `mode_propagation.go` remain SSOT for
//!   the wire format. The Rust enum stores the same integer values
//!   (`Full=0, Limited=1, Essentials=2, ReadOnly=3, Offline=4`).
//! - Adding a new variant to either enum is a Go-AND-Rust change in the
//!   same PR; the cycle-18 verify script asserts variant count parity.
//! - We do NOT mirror the Redis `mode_propagation` wire bytes here —
//!   that lives in services' transport layer (each language has its
//!   own Redis client). The wire FORMAT contract is in the Go file.

use std::future::Future;
use std::time::{Duration, Instant};

use thiserror::Error;

// ────────────────────────────────────────────────────────────────────────
// ServiceMode (cycle 7) — Rust mirror.
// ────────────────────────────────────────────────────────────────────────

/// System-wide service mode. Integer values match Go `ServiceMode`.
///
/// Mode semantics (SR06-D5 + L1.J §8):
///
/// - `Full`: normal operation. Reads + writes online.
/// - `Limited`: a non-critical dep is degraded. Writes buffered if meta
///   is down; reads serve stale cache for sensitive paths.
/// - `Essentials`: critical dep degraded — accept only essential write
///   paths (auth, session heartbeats); reject feature writes.
/// - `ReadOnly`: no writes accepted; reads from cache + replicas only.
/// - `Offline`: no traffic accepted; gateway returns 503.
#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum ServiceMode {
    /// Normal operation.
    Full = 0,
    /// Non-critical dep degraded.
    Limited = 1,
    /// Critical dep degraded; feature writes rejected.
    Essentials = 2,
    /// No writes; reads from cache.
    ReadOnly = 3,
    /// No traffic; gateway returns 503.
    Offline = 4,
}

impl ServiceMode {
    /// Canonical lowercase wire string. MUST match Go `ServiceMode.String`.
    pub fn as_str(self) -> &'static str {
        match self {
            ServiceMode::Full => "full",
            ServiceMode::Limited => "limited",
            ServiceMode::Essentials => "essentials",
            ServiceMode::ReadOnly => "read_only",
            ServiceMode::Offline => "offline",
        }
    }

    /// `m.is_at_least(other)` — "is m at least as degraded as other?".
    /// Mirrors Go `GreaterOrEqual`. The common admission-check primitive.
    pub fn is_at_least(self, other: ServiceMode) -> bool {
        self >= other
    }

    /// True for modes that accept new write traffic. ReadOnly + Offline
    /// reject; everything else accepts.
    pub fn accepts_writes(self) -> bool {
        self < ServiceMode::ReadOnly
    }

    /// True for modes that allow background workers (rollup, archive,
    /// retention sweeper). At Essentials and worse, background jobs MUST
    /// pause to preserve critical-path latency budget.
    pub fn accepts_background_jobs(self) -> bool {
        self <= ServiceMode::Limited
    }

    /// True only at Full. Admin commands requiring a fresh ack (close
    /// confirmations, retire-shard ops) MUST be deferred until Full returns.
    pub fn accepts_fresh_ack_required(self) -> bool {
        matches!(self, ServiceMode::Full)
    }

    /// Canonical ordered slice — exposed so tests + the Go parity check
    /// can assert exhaustiveness. SR06-D5 fixes at 5 entries.
    pub fn all() -> [ServiceMode; 5] {
        [
            ServiceMode::Full,
            ServiceMode::Limited,
            ServiceMode::Essentials,
            ServiceMode::ReadOnly,
            ServiceMode::Offline,
        ]
    }
}

/// Parse error for [`ServiceMode::parse`]. Mirrors Go `ErrInvalidServiceMode`.
#[derive(Debug, Error)]
#[error("lifecycle: invalid service mode {0:?}")]
pub struct InvalidServiceMode(pub String);

impl ServiceMode {
    /// Decode the wire form. Tolerant of `readonly` alias (matches Go).
    pub fn parse(s: &str) -> Result<Self, InvalidServiceMode> {
        match s.trim().to_ascii_lowercase().as_str() {
            "full" => Ok(ServiceMode::Full),
            "limited" => Ok(ServiceMode::Limited),
            "essentials" => Ok(ServiceMode::Essentials),
            "read_only" | "readonly" => Ok(ServiceMode::ReadOnly),
            "offline" => Ok(ServiceMode::Offline),
            _ => Err(InvalidServiceMode(s.to_string())),
        }
    }
}

// ────────────────────────────────────────────────────────────────────────
// PresenceState (cycle 18 / SR11-D3).
// ────────────────────────────────────────────────────────────────────────

/// Session-scoped per-participant liveness state. SR11-D3.
///
/// Distinct from [`ServiceMode`] (system-wide health). Distinct from
/// GoneState (entity existence). PresenceState answers "is this user
/// reachable right now?" for the multi-stream UX + turn arbitration.
///
/// The 6 variants are FIXED per SR11-D3; adding one is a Go-AND-Rust
/// change in the same PR + a SQL CHECK migration.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PresenceState {
    /// WS connected; input within idle threshold.
    Active,
    /// WS connected; no input for 60s+.
    Idle,
    /// WS connected; drafting state (input field has content).
    Typing,
    /// One of their turns in llm_processing or streaming.
    WaitingAi,
    /// WS dropped < 5min; we hold their seat.
    DisconnectedBrief,
    /// WS dropped 5–30min; seat at risk.
    DisconnectedGhost,
}

impl PresenceState {
    /// Canonical wire string. MUST match Go `PresenceState` const values.
    pub fn as_str(self) -> &'static str {
        match self {
            PresenceState::Active => "active",
            PresenceState::Idle => "idle",
            PresenceState::Typing => "typing",
            PresenceState::WaitingAi => "waiting_ai",
            PresenceState::DisconnectedBrief => "disconnected_brief",
            PresenceState::DisconnectedGhost => "disconnected_ghost",
        }
    }

    /// True iff the participant has a live WS connection.
    pub fn is_connected(self) -> bool {
        matches!(
            self,
            PresenceState::Active
                | PresenceState::Idle
                | PresenceState::Typing
                | PresenceState::WaitingAi
        )
    }

    /// Inverse of [`Self::is_connected`].
    pub fn is_disconnected(self) -> bool {
        !self.is_connected()
    }

    /// Canonical ordered slice — exposed for SR11-D3 exhaustiveness pins.
    pub fn all() -> [PresenceState; 6] {
        [
            PresenceState::Active,
            PresenceState::Idle,
            PresenceState::Typing,
            PresenceState::WaitingAi,
            PresenceState::DisconnectedBrief,
            PresenceState::DisconnectedGhost,
        ]
    }
}

/// Parse error for [`PresenceState::parse`]. Mirrors Go `ErrInvalidPresenceState`.
#[derive(Debug, Error)]
#[error("lifecycle: invalid presence state {0:?}")]
pub struct InvalidPresenceState(pub String);

impl PresenceState {
    /// Decode the wire form. Tolerant of case + whitespace.
    pub fn parse(s: &str) -> Result<Self, InvalidPresenceState> {
        match s.trim().to_ascii_lowercase().as_str() {
            "active" => Ok(PresenceState::Active),
            "idle" => Ok(PresenceState::Idle),
            "typing" => Ok(PresenceState::Typing),
            "waiting_ai" => Ok(PresenceState::WaitingAi),
            "disconnected_brief" => Ok(PresenceState::DisconnectedBrief),
            "disconnected_ghost" => Ok(PresenceState::DisconnectedGhost),
            _ => Err(InvalidPresenceState(s.to_string())),
        }
    }
}

// ────────────────────────────────────────────────────────────────────────
// drain (cycle 18 / L4.G).
// ────────────────────────────────────────────────────────────────────────

/// Drain hook outcome. Mirrors Go `DrainResult`.
#[derive(Debug, Clone, Default)]
pub struct DrainResult {
    /// True if `stop_accepting` ran.
    pub stopped_accepting: bool,
    /// True if `wait_inflight` ran.
    pub waited_inflight: bool,
    /// True if `flush_outbox` ran.
    pub flushed_outbox: bool,
    /// True if `close_breakers` ran.
    pub closed_breakers: bool,
    /// True if `close_resources` ran.
    pub closed_resources: bool,
    /// Total wall-clock drain duration.
    pub elapsed: Duration,
    /// True iff the deadline elapsed before some hook completed.
    pub deadline_exceeded: bool,
    /// First per-step error encountered, if any.
    pub first_err: Option<String>,
}

impl DrainResult {
    /// True iff no per-step error AND no deadline exceeded.
    pub fn is_success(&self) -> bool {
        !self.deadline_exceeded && self.first_err.is_none()
    }
}

/// Drain error.
#[derive(Debug, Error)]
pub enum DrainError {
    /// Caller passed a non-positive timeout — bug.
    #[error("lifecycle: drain timeout must be > 0; got {0:?}")]
    InvalidTimeout(Duration),
}

/// Ordered shutdown orchestrator. The signature mirrors Go [`Drain`] but
/// uses tokio futures + closure traits instead of Go function-pointers.
///
/// The five-step order is FIXED:
///
/// 1. `stop_accepting` — flip /health/ready (no I/O; unbounded).
/// 2. `wait_inflight` — block until active handlers complete or deadline.
/// 3. `flush_outbox` — best-effort final drain.
/// 4. `close_breakers` — open all breakers so in-flight outbound fast-fails.
/// 5. `close_resources` — ALWAYS runs even on deadline-exceeded.
///
/// Each hook is `Option<...>`; `None` is a no-op. The shared deadline
/// covers steps 2–5 (step 1 is a flag flip).
#[allow(clippy::too_many_arguments)]
pub async fn drain<W, FO, FB, FR, WFut, FOFut>(
    timeout_dur: Duration,
    stop_accepting: Option<Box<dyn FnOnce() + Send>>,
    wait_inflight: Option<W>,
    flush_outbox: Option<FO>,
    close_breakers: Option<FB>,
    close_resources: Option<FR>,
) -> Result<DrainResult, DrainError>
where
    W: FnOnce() -> WFut + Send,
    WFut: Future<Output = Result<(), String>> + Send,
    FO: FnOnce() -> FOFut + Send,
    FOFut: Future<Output = Result<(), String>> + Send,
    FB: FnOnce() -> Result<(), String> + Send,
    FR: FnOnce() -> Result<(), String> + Send,
{
    if timeout_dur.is_zero() {
        return Err(DrainError::InvalidTimeout(timeout_dur));
    }
    let start = Instant::now();
    let mut res = DrainResult::default();

    if let Some(f) = stop_accepting {
        f();
        res.stopped_accepting = true;
    }

    // Shared deadline for steps 2–5.
    let deadline = start + timeout_dur;

    if let Some(w) = wait_inflight {
        res.waited_inflight = true;
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            res.deadline_exceeded = true;
        } else {
            match tokio::time::timeout(remaining, w()).await {
                Ok(Ok(())) => {}
                Ok(Err(e)) => {
                    if res.first_err.is_none() {
                        res.first_err = Some(format!("wait_inflight: {e}"));
                    }
                }
                Err(_) => res.deadline_exceeded = true,
            }
        }
    }

    if let Some(f) = flush_outbox {
        res.flushed_outbox = true;
        let remaining = deadline.saturating_duration_since(Instant::now());
        if remaining.is_zero() {
            res.deadline_exceeded = true;
        } else {
            match tokio::time::timeout(remaining, f()).await {
                Ok(Ok(())) => {}
                Ok(Err(e)) => {
                    if res.first_err.is_none() {
                        res.first_err = Some(format!("flush_outbox: {e}"));
                    }
                }
                Err(_) => res.deadline_exceeded = true,
            }
        }
    }

    if let Some(f) = close_breakers {
        res.closed_breakers = true;
        if let Err(e) = f() {
            if res.first_err.is_none() {
                res.first_err = Some(format!("close_breakers: {e}"));
            }
        }
    }

    // CloseResources ALWAYS runs even if the deadline was exceeded.
    if let Some(f) = close_resources {
        res.closed_resources = true;
        if let Err(e) = f() {
            if res.first_err.is_none() {
                res.first_err = Some(format!("close_resources: {e}"));
            }
        }
    }

    res.elapsed = start.elapsed();
    Ok(res)
}

/// SR06 §12AI.11 per-service-class default drain timeouts. Callers SHOULD
/// use these unless they have a documented reason otherwise.
pub mod drain_defaults {
    use std::time::Duration;

    /// V1 default for typical services.
    pub const DEFAULT: Duration = Duration::from_secs(30);
    /// `api-gateway-bff`, lightweight handlers.
    pub const STATELESS: Duration = Duration::from_secs(10);
    /// `migration-orchestrator`, `publisher`.
    pub const LONG_RUNNER: Duration = Duration::from_secs(120);
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    // ─── ServiceMode parity with Go ──────────────────────────────────

    #[test]
    fn service_mode_wire_strings_match_go() {
        // The wire strings MUST match `contracts/lifecycle/service_mode.go`.
        let expect = [
            (ServiceMode::Full, "full"),
            (ServiceMode::Limited, "limited"),
            (ServiceMode::Essentials, "essentials"),
            (ServiceMode::ReadOnly, "read_only"),
            (ServiceMode::Offline, "offline"),
        ];
        for (m, s) in expect {
            assert_eq!(m.as_str(), s);
            assert_eq!(ServiceMode::parse(s).unwrap(), m);
        }
    }

    #[test]
    fn service_mode_integer_values_match_go() {
        // Go: Full=0, Limited=1, Essentials=2, ReadOnly=3, Offline=4.
        assert_eq!(ServiceMode::Full as u8, 0);
        assert_eq!(ServiceMode::Limited as u8, 1);
        assert_eq!(ServiceMode::Essentials as u8, 2);
        assert_eq!(ServiceMode::ReadOnly as u8, 3);
        assert_eq!(ServiceMode::Offline as u8, 4);
    }

    #[test]
    fn service_mode_all_returns_5() {
        // SR06-D5 fixes at 5 entries — parity with Go AllModes.
        assert_eq!(ServiceMode::all().len(), 5);
    }

    #[test]
    fn service_mode_parse_invalid() {
        assert!(ServiceMode::parse("maintenance").is_err());
        assert!(ServiceMode::parse("").is_err());
    }

    #[test]
    fn service_mode_parse_readonly_alias() {
        assert_eq!(ServiceMode::parse("readonly").unwrap(), ServiceMode::ReadOnly);
        assert_eq!(ServiceMode::parse("READ_ONLY").unwrap(), ServiceMode::ReadOnly);
    }

    #[test]
    fn service_mode_accepts_writes() {
        assert!(ServiceMode::Full.accepts_writes());
        assert!(ServiceMode::Limited.accepts_writes());
        assert!(ServiceMode::Essentials.accepts_writes());
        assert!(!ServiceMode::ReadOnly.accepts_writes());
        assert!(!ServiceMode::Offline.accepts_writes());
    }

    // ─── PresenceState ────────────────────────────────────────────────

    #[test]
    fn presence_state_all_returns_6() {
        assert_eq!(PresenceState::all().len(), 6);
    }

    #[test]
    fn presence_state_wire_strings_round_trip() {
        for p in PresenceState::all() {
            let s = p.as_str();
            assert_eq!(PresenceState::parse(s).unwrap(), p);
        }
    }

    #[test]
    fn presence_state_is_connected() {
        let connected = [
            PresenceState::Active,
            PresenceState::Idle,
            PresenceState::Typing,
            PresenceState::WaitingAi,
        ];
        let disconnected = [
            PresenceState::DisconnectedBrief,
            PresenceState::DisconnectedGhost,
        ];
        for p in connected {
            assert!(p.is_connected(), "{p:?} should be connected");
            assert!(!p.is_disconnected());
        }
        for p in disconnected {
            assert!(p.is_disconnected(), "{p:?} should be disconnected");
            assert!(!p.is_connected());
        }
    }

    #[test]
    fn presence_state_parse_invalid() {
        assert!(PresenceState::parse("afk").is_err());
        assert!(PresenceState::parse("").is_err());
    }

    // ─── drain orchestrator ──────────────────────────────────────────

    #[tokio::test]
    async fn drain_rejects_zero_timeout() {
        let r = drain::<
            fn() -> std::future::Ready<Result<(), String>>,
            fn() -> std::future::Ready<Result<(), String>>,
            fn() -> Result<(), String>,
            fn() -> Result<(), String>,
            _, _,
        >(Duration::ZERO, None, None, None, None, None)
        .await;
        assert!(matches!(r, Err(DrainError::InvalidTimeout(_))));
    }

    #[tokio::test]
    async fn drain_hook_execution_order() {
        let order = Arc::new(Mutex::new(Vec::<&'static str>::new()));
        let o1 = order.clone();
        let o2 = order.clone();
        let o3 = order.clone();
        let o4 = order.clone();
        let o5 = order.clone();
        let r = drain(
            Duration::from_secs(1),
            Some(Box::new(move || o1.lock().unwrap().push("stop"))),
            Some(move || async move {
                o2.lock().unwrap().push("wait");
                Ok::<(), String>(())
            }),
            Some(move || async move {
                o3.lock().unwrap().push("flush");
                Ok::<(), String>(())
            }),
            Some(move || {
                o4.lock().unwrap().push("breakers");
                Ok::<(), String>(())
            }),
            Some(move || {
                o5.lock().unwrap().push("resources");
                Ok::<(), String>(())
            }),
        )
        .await
        .unwrap();
        assert!(r.is_success());
        let got = order.lock().unwrap().clone();
        assert_eq!(got, vec!["stop", "wait", "flush", "breakers", "resources"]);
    }

    #[tokio::test]
    async fn drain_close_resources_runs_even_on_deadline() {
        let closed = Arc::new(Mutex::new(false));
        let c = closed.clone();
        let r = drain(
            Duration::from_millis(10),
            None::<Box<dyn FnOnce() + Send>>,
            Some(|| async {
                tokio::time::sleep(Duration::from_millis(100)).await;
                Ok::<(), String>(())
            }),
            None::<fn() -> std::future::Ready<Result<(), String>>>,
            None::<fn() -> Result<(), String>>,
            Some(move || {
                *c.lock().unwrap() = true;
                Ok::<(), String>(())
            }),
        )
        .await
        .unwrap();
        assert!(r.deadline_exceeded);
        assert!(*closed.lock().unwrap(), "CloseResources MUST run even on deadline-exceeded");
    }
}
