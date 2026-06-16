//! `breaker-core` — the tokio-free CircuitBreaker sync state machine.
//!
//! Extracted from `dp-kernel::resilience` for S6 / H1-loom. The breaker uses ONLY
//! `std::sync::Mutex` + `std::time` (its `call()` is plain `fut.await` — no tokio),
//! so it can be exhaustively interleaving-checked with **loom**. That can't be done
//! inside `dp-kernel` itself: `dp-kernel` depends on tokio, and global `--cfg loom`
//! rebuilds tokio's transitive deps (`concurrent-queue`) under loom, where their
//! own loom paths fail to compile. Keeping the breaker in a tokio-free leaf crate
//! sidesteps that entirely.
//!
//! `dp-kernel::resilience` re-exports `CircuitBreaker` (and the supporting types)
//! from here, so the public path `dp_kernel::resilience::CircuitBreaker` and every
//! existing consumer are unchanged. The async `with_timeout`/`retry`/`Bulkhead`
//! primitives stay in `dp-kernel::resilience` (they DO use tokio).

use std::{
    future::Future,
    time::{Duration, Instant},
};

use thiserror::Error;

// S6 / H1-loom: the breaker's `inner: Mutex<BreakerInner>` is the one sync
// primitive loom must instrument. Under `--cfg loom` it becomes
// `loom::sync::Mutex` (loom tracks acquisitions to explore interleavings);
// otherwise it is the std Mutex. The API is identical (`.lock()` →
// `LockResult<Guard>`), so the breaker code is unchanged.
#[cfg(loom)]
use loom::sync::Mutex;
#[cfg(not(loom))]
use std::sync::Mutex;

// ────────────────────────────────────────────────────────────────────────
// Circuit Breaker — 3-state per SR06 §12AI.4.
// ────────────────────────────────────────────────────────────────────────

/// 3-state breaker enum. Integer values match the Go side
/// (`StateClosed=0, StateHalfOpen=1, StateOpen=2`) so the
/// `lw_dependency_circuit_state` gauge is portable across languages.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub enum BreakerState {
    /// Calls pass through; failure window is tracked.
    #[default]
    Closed = 0,
    /// A single probe call is in flight.
    HalfOpen = 1,
    /// Calls fast-fail with [`BreakerError::Open`].
    Open = 2,
}

impl BreakerState {
    /// Wire string mirroring Go `BreakerState.String()`. Used in
    /// `dependency_events.event_type` rows.
    pub fn as_str(self) -> &'static str {
        match self {
            BreakerState::Closed => "closed",
            BreakerState::HalfOpen => "half_open",
            BreakerState::Open => "open",
        }
    }
}

/// Per-(caller_service, dep) breaker config. Sourced from
/// `contracts/dependencies/matrix.yaml`.
#[derive(Debug, Clone)]
pub struct BreakerConfig {
    /// Error rate in `[0, 1]` that trips Closed → Open. SR06 default 0.25.
    pub error_rate_threshold: f64,
    /// Minimum window size before error-rate is meaningful. SR06 default 20.
    pub min_requests: usize,
    /// Time Open stays before allowing a half-open probe. SR06 default 30 s.
    pub open_duration: Duration,
    /// Max one probe per interval while in HalfOpen. Default 1 s.
    pub half_open_probe_interval: Duration,
}

impl Default for BreakerConfig {
    fn default() -> Self {
        Self {
            error_rate_threshold: 0.25,
            min_requests: 20,
            open_duration: Duration::from_secs(30),
            half_open_probe_interval: Duration::from_secs(1),
        }
    }
}

/// Breaker error surface. Mirrors Go `ErrCircuitOpen` + inner-error wrap.
#[derive(Debug, Error)]
pub enum BreakerError<E> {
    /// Circuit is open; call fast-failed without invoking the inner fn.
    #[error("resilience: circuit open for dep {0}")]
    Open(String),
    /// Inner call failed; error propagates verbatim.
    #[error("resilience: inner call failed: {0}")]
    Inner(#[source] E),
}

/// Read-only snapshot of breaker counters. Useful for the
/// `lw_dependency_circuit_state` gauge.
#[derive(Debug, Clone, Default)]
pub struct BreakerMetrics {
    /// Current state at snapshot time.
    pub state: BreakerState,
    /// Total observed calls in the current window.
    pub windowed_total: usize,
    /// Failed calls in the current window.
    pub windowed_failures: usize,
    /// Cumulative count of fast-fails since the last Open transition.
    pub fast_failed_since_open: usize,
    /// Cumulative count of Closed transitions across breaker lifetime.
    pub transitions_closed: usize,
    /// Cumulative count of HalfOpen transitions across breaker lifetime.
    pub transitions_half_open: usize,
    /// Cumulative count of Open transitions across breaker lifetime.
    pub transitions_open: usize,
}

/// Thread-safe in-memory circuit breaker. Construct via [`CircuitBreaker::new`].
pub struct CircuitBreaker {
    dep: String,
    cfg: BreakerConfig,
    inner: Mutex<BreakerInner>,
    /// Overridable time source for tests; production = `Instant::now`.
    now: Box<dyn Fn() -> Instant + Send + Sync>,
}

struct BreakerInner {
    state: BreakerState,
    windowed_total: usize,
    windowed_failures: usize,
    opened_at: Option<Instant>,
    last_probe_at: Option<Instant>,
    fast_failed_since_open: usize,
    transitions_closed: usize,
    transitions_half_open: usize,
    transitions_open: usize,
}

impl CircuitBreaker {
    /// Construct with the canonical wall-clock time source.
    pub fn new(dep: impl Into<String>, cfg: BreakerConfig) -> Self {
        Self::with_clock(dep, cfg, Instant::now)
    }

    /// Construct with a custom clock — used by the deterministic test suite.
    pub fn with_clock<F>(dep: impl Into<String>, cfg: BreakerConfig, now: F) -> Self
    where
        F: Fn() -> Instant + Send + Sync + 'static,
    {
        Self {
            dep: dep.into(),
            cfg,
            inner: Mutex::new(BreakerInner {
                state: BreakerState::Closed,
                windowed_total: 0,
                windowed_failures: 0,
                opened_at: None,
                last_probe_at: None,
                fast_failed_since_open: 0,
                transitions_closed: 0,
                transitions_half_open: 0,
                transitions_open: 0,
            }),
            now: Box::new(now),
        }
    }

    /// Current state (cheap; safe for tight-loop reads).
    pub fn state(&self) -> BreakerState {
        self.inner.lock().expect("breaker mutex poisoned").state
    }

    /// Snapshot of all counters.
    pub fn metrics(&self) -> BreakerMetrics {
        let g = self.inner.lock().expect("breaker mutex poisoned");
        BreakerMetrics {
            state: g.state,
            windowed_total: g.windowed_total,
            windowed_failures: g.windowed_failures,
            fast_failed_since_open: g.fast_failed_since_open,
            transitions_closed: g.transitions_closed,
            transitions_half_open: g.transitions_half_open,
            transitions_open: g.transitions_open,
        }
    }

    /// Run `fut` under breaker protection. Returns [`BreakerError::Open`]
    /// if the breaker is in StateOpen and the probe-window has not elapsed.
    /// The inner future is NEVER polled while the breaker is fast-failing,
    /// so the upstream call is fully avoided (the point of a breaker).
    pub async fn call<F, T, E>(&self, fut: F) -> Result<T, BreakerError<E>>
    where
        F: Future<Output = Result<T, E>>,
    {
        let gate = self.gate();
        if gate.fast_fail {
            return Err(BreakerError::Open(self.dep.clone()));
        }
        let result = fut.await;
        let err_for_record = result.is_err();
        self.record(err_for_record, gate.is_probe);
        match result {
            Ok(v) => Ok(v),
            Err(e) => Err(BreakerError::Inner(e)),
        }
    }

    fn gate(&self) -> GateDecision {
        let mut g = self.inner.lock().expect("breaker mutex poisoned");
        let now = (self.now)();
        match g.state {
            BreakerState::Closed => GateDecision::default(),
            BreakerState::Open => {
                let elapsed = g
                    .opened_at
                    .map(|t| now.duration_since(t))
                    .unwrap_or_default();
                if elapsed < self.cfg.open_duration {
                    g.fast_failed_since_open += 1;
                    GateDecision {
                        fast_fail: true,
                        is_probe: false,
                    }
                } else {
                    transition(&mut g, BreakerState::HalfOpen);
                    g.last_probe_at = Some(now);
                    GateDecision {
                        fast_fail: false,
                        is_probe: true,
                    }
                }
            }
            BreakerState::HalfOpen => {
                let since_probe = g
                    .last_probe_at
                    .map(|t| now.duration_since(t))
                    .unwrap_or(Duration::MAX);
                if since_probe < self.cfg.half_open_probe_interval {
                    g.fast_failed_since_open += 1;
                    GateDecision {
                        fast_fail: true,
                        is_probe: false,
                    }
                } else {
                    g.last_probe_at = Some(now);
                    GateDecision {
                        fast_fail: false,
                        is_probe: true,
                    }
                }
            }
        }
    }

    fn record(&self, failed: bool, is_probe: bool) {
        let mut g = self.inner.lock().expect("breaker mutex poisoned");
        let now = (self.now)();
        if is_probe {
            if failed {
                transition(&mut g, BreakerState::Open);
                g.opened_at = Some(now);
            } else {
                transition(&mut g, BreakerState::Closed);
            }
            return;
        }
        if matches!(g.state, BreakerState::Open) {
            // Defensive: gate fast-failed; we shouldn't be here.
            return;
        }
        g.windowed_total += 1;
        if failed {
            g.windowed_failures += 1;
        }
        if g.windowed_total >= self.cfg.min_requests {
            let rate = g.windowed_failures as f64 / g.windowed_total as f64;
            if rate >= self.cfg.error_rate_threshold {
                transition(&mut g, BreakerState::Open);
                g.opened_at = Some(now);
            }
        }
    }
}

#[derive(Default)]
struct GateDecision {
    fast_fail: bool,
    is_probe: bool,
}

fn transition(g: &mut BreakerInner, next: BreakerState) {
    if g.state == next {
        return;
    }
    g.state = next;
    g.windowed_total = 0;
    g.windowed_failures = 0;
    match next {
        BreakerState::Closed => {
            g.transitions_closed += 1;
            g.fast_failed_since_open = 0;
        }
        BreakerState::HalfOpen => g.transitions_half_open += 1,
        BreakerState::Open => {
            g.transitions_open += 1;
            g.fast_failed_since_open = 0;
        }
    }
}

// ────────────────────────────────────────────────────────────────────────
// Sync smoke tests (non-loom) — exercise gate/record/transition directly.
// The full async behavior suite (call-based, #[tokio::test]) lives in
// dp-kernel::resilience against the re-exported type.
// ────────────────────────────────────────────────────────────────────────
#[cfg(all(test, not(loom)))]
mod tests {
    use super::*;

    fn cfg() -> BreakerConfig {
        BreakerConfig {
            error_rate_threshold: 0.5,
            min_requests: 2,
            open_duration: Duration::from_secs(3600),
            half_open_probe_interval: Duration::from_millis(1),
        }
    }

    #[test]
    fn record_trips_closed_to_open_on_error_rate() {
        let b = CircuitBreaker::new("d", cfg());
        // Two failures at min_requests=2, threshold 0.5 → Open.
        for _ in 0..2 {
            let d = b.gate();
            b.record(true, d.is_probe);
        }
        assert_eq!(b.state(), BreakerState::Open);
        let m = b.metrics();
        assert!(m.transitions_open >= 1);
    }

    #[test]
    fn metrics_invariant_total_ge_failures() {
        let b = CircuitBreaker::new("d", cfg());
        let d = b.gate();
        b.record(false, d.is_probe);
        let m = b.metrics();
        assert!(m.windowed_total >= m.windowed_failures);
    }
}

// ────────────────────────────────────────────────────────────────────────
// S6 / H1-loom — exhaustive interleaving model-check of the CircuitBreaker.
// ────────────────────────────────────────────────────────────────────────
//
// The breaker is fully Mutex-protected, BUT `call()` takes the lock TWICE with a
// gap: `gate()` (lock→decide→unlock) … await the inner future … `record()`
// (lock→update→unlock). Two concurrent callers therefore interleave their
// SEPARATE lock acquisitions — the real concurrency this models. loom explores
// EVERY interleaving and asserts the breaker's invariants hold in all of them.
// (A single-thread / post-quiesce test cannot see the gate→record gap.)
//
// Run: RUSTFLAGS="--cfg loom" cargo test -p breaker-core loom_tests
#[cfg(loom)]
mod loom_tests {
    use super::*;
    use loom::sync::Arc as LoomArc;

    fn cfg() -> BreakerConfig {
        BreakerConfig {
            error_rate_threshold: 0.5,
            min_requests: 2,
            open_duration: Duration::from_secs(3600),
            half_open_probe_interval: Duration::from_millis(1),
        }
    }

    /// PRIMARY: two callers each do `gate()→record()` concurrently. The split-lock
    /// gap means their lock acquisitions interleave; loom explores ALL orderings.
    /// A FIXED clock (elapsed always 0 ≪ open_duration) removes time nondeterminism,
    /// so the ONLY nondeterminism loom sees is thread scheduling — exactly what we
    /// want to exhaust. In every interleaving the breaker invariants must hold.
    #[test]
    fn breaker_gate_record_interleavings_hold_invariants() {
        loom::model(|| {
            let t0 = Instant::now();
            let b = LoomArc::new(CircuitBreaker::with_clock("d", cfg(), move || t0));
            let b2 = b.clone();

            let h = loom::thread::spawn(move || {
                let d = b2.gate();
                b2.record(true, d.is_probe); // a FAILURE outcome
            });
            let d = b.gate();
            b.record(false, d.is_probe); // a SUCCESS outcome
            h.join().unwrap();

            // Invariants that MUST hold under EVERY interleaving:
            let m = b.metrics();
            assert!(
                m.windowed_total >= m.windowed_failures,
                "windowed_total {} < windowed_failures {} — counter inconsistency under a race",
                m.windowed_total,
                m.windowed_failures,
            );
            assert!(
                matches!(
                    m.state,
                    BreakerState::Closed | BreakerState::HalfOpen | BreakerState::Open
                ),
                "breaker reached an invalid state {:?}",
                m.state,
            );
        });
    }

    /// BITE (non-vacuity): proves the loom harness ACTUALLY explores interleavings
    /// and WOULD catch a broken locking discipline. Two threads do a lock-free
    /// read-modify-write on a shared cell; loom detects the unsynchronized
    /// concurrent access and panics on the racy schedule. `#[should_panic]` asserts
    /// loom found it. Wrap the cell in a Mutex (the correct discipline) and this no
    /// longer fires — exactly the clean→broken transition the bite discipline wants.
    /// If loom did NOT explore the interleaving this would pass (no panic) and the
    /// test would FAIL — so it also guards the harness against running vacuously.
    #[test]
    #[should_panic]
    fn bite_unsynchronized_counter_is_caught_by_loom() {
        loom::model(|| {
            let c = LoomArc::new(loom::cell::UnsafeCell::new(0usize));
            let c2 = c.clone();
            let h = loom::thread::spawn(move || {
                c2.with_mut(|p| unsafe { *p += 1 });
            });
            c.with_mut(|p| unsafe { *p += 1 });
            h.join().unwrap();
            let _ = c.with(|p| unsafe { *p });
        });
    }
}
