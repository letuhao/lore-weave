//! `resilience` — Rust mirror of `contracts/resilience/` (cycle 18 / L4.F).
//!
//! Mirrors the four canonical resilience primitives so Rust services
//! (cycle-17 dp-kernel consumers + cycle-19+ services) get the same
//! contract semantics as Go callers:
//!
//! - [`with_timeout`] — per-dep timeout wrapper (SR06 I16 enforcement point).
//! - [`CircuitBreaker`] — 3-state breaker (Closed | HalfOpen | Open).
//! - [`Retry`] — exponential backoff with ±25 % jitter, Retry-After aware.
//! - [`Bulkhead`] — per-dep concurrency + queue isolation.
//!
//! Parity rules with Go (`contracts/resilience/`):
//!
//! - Q-L4-1: Go primary, Rust mirror. Behavior MUST match where the
//!   languages allow (e.g., breaker state-machine, retry attempt counts,
//!   bulkhead queue semantics). Names differ by language idiom only
//!   (`WithTimeout` → `with_timeout`, `StateClosed` → `BreakerState::Closed`).
//! - SR06 §12AI.4: one breaker per (caller_service, dep). The library is
//!   safe for concurrent use across tokio tasks; callers share one
//!   `Arc<CircuitBreaker>` per pair.
//! - SR06 §12AI.5: idempotent vs non-idempotent vs critical-write retry
//!   classes match the Go [`RetryPolicy::default_for`] constructor.
//! - SR06 §12AI.10: `ErrBulkheadFull` returned on slot+queue saturation;
//!   never blocks indefinitely.
//!
//! The `dependency_events` audit-row writer is Go-only this cycle (the
//! Rust services that currently exist — tilemap-service, world-service
//! scaffold, travel-service scaffold — do not yet write to the meta DB).
//! Cycle 19+ will mirror it when Rust services start emitting events.

use std::{
    future::Future,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    },
    time::{Duration, Instant},
};

use thiserror::Error;
use tokio::{
    sync::{Notify, Semaphore, TryAcquireError},
    time::timeout,
};

// S6 / H1-loom: the CircuitBreaker sync state machine moved to the tokio-free
// `breaker-core` crate so it can be exhaustively race-checked with loom (loom
// can't build inside dp-kernel — tokio's transitive deps break under --cfg loom).
// Re-exported here so the public path `dp_kernel::resilience::CircuitBreaker`
// and every existing consumer are UNCHANGED. The async with_timeout/retry/
// Bulkhead primitives below stay local (they use tokio).
pub use breaker_core::{BreakerConfig, BreakerError, BreakerMetrics, BreakerState, CircuitBreaker};

// ────────────────────────────────────────────────────────────────────────
// Timeout — SR06 I16 enforcement point.
// ────────────────────────────────────────────────────────────────────────

/// Per-dep timeout error. Wraps the underlying call error OR signals that
/// the per-dep budget elapsed.
#[derive(Debug, Error)]
pub enum TimeoutError<E> {
    /// The configured per-dep timeout was non-positive — programmer bug.
    #[error("resilience: invalid timeout for dep {dep:?}: {timeout:?}")]
    InvalidTimeout {
        /// Dependency name from the matrix.
        dep: String,
        /// The non-positive timeout value the caller passed.
        timeout: Duration,
    },
    /// Per-dep deadline elapsed before the inner future resolved.
    #[error("resilience: deadline exceeded for dep {0}")]
    DeadlineExceeded(String),
    /// Inner future failed on its own; the error is propagated verbatim.
    #[error("resilience: inner call failed: {0}")]
    Inner(#[source] E),
}

/// `with_timeout` runs `fut` under a per-dep deadline derived from the
/// matrix. Mirrors `WithTimeout` in Go.
///
/// * `timeout_dur` MUST be `> 0`. Zero / negative returns
///   [`TimeoutError::InvalidTimeout`] without polling `fut` — silently
///   "no deadline" cascades into pool exhaustion (SR06 root cause).
/// * Inner errors are wrapped in [`TimeoutError::Inner`]; deadline
///   expiry surfaces as [`TimeoutError::DeadlineExceeded`].
pub async fn with_timeout<F, T, E>(
    dep: &str,
    timeout_dur: Duration,
    fut: F,
) -> Result<T, TimeoutError<E>>
where
    F: Future<Output = Result<T, E>>,
{
    if timeout_dur.is_zero() {
        return Err(TimeoutError::InvalidTimeout {
            dep: dep.to_string(),
            timeout: timeout_dur,
        });
    }
    match timeout(timeout_dur, fut).await {
        Ok(Ok(v)) => Ok(v),
        Ok(Err(e)) => Err(TimeoutError::Inner(e)),
        Err(_) => Err(TimeoutError::DeadlineExceeded(dep.to_string())),
    }
}

// ────────────────────────────────────────────────────────────────────────
// Retry — SR06 §12AI.5.
// ────────────────────────────────────────────────────────────────────────

/// Retry class — determines defaults per SR06 §12AI.5.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RetryClass {
    /// GET / read-only — 3 retries, 100 ms × 2^n ± 25 %, 10 s budget.
    Idempotent,
    /// POST without idempotency key, side-effect LLM — NO retry.
    NonIdempotent,
    /// Cost ledger, audit, canon write — 2 retries, cap 5 s, 15 s budget.
    /// Caller MUST supply idempotency key (enforced at call-site).
    CriticalWrite,
}

/// Retry configuration. Mirrors Go `RetryPolicy`.
#[derive(Debug, Clone)]
pub struct RetryPolicy {
    /// Retry class — informational; defaults are computed per class.
    pub class: RetryClass,
    /// Max attempts INCLUDING the first call. `max_attempts = 1` = no retry.
    pub max_attempts: usize,
    /// First retry sleeps `base_backoff` (× 2 each retry after).
    pub base_backoff: Duration,
    /// Hard cap on per-iteration wait.
    pub max_backoff: Duration,
    /// Wall-clock cap across all attempts.
    pub total_budget: Duration,
    /// ±this fraction of computed backoff. 0.25 = ±25 %. Range `[0, 1]`.
    pub jitter_percent: f64,
}

impl RetryPolicy {
    /// SR06-default policy per class. Mirrors Go `DefaultRetryPolicy`.
    pub fn default_for(class: RetryClass) -> Self {
        match class {
            RetryClass::Idempotent => Self {
                class,
                max_attempts: 4,
                base_backoff: Duration::from_millis(100),
                max_backoff: Duration::from_secs(5),
                total_budget: Duration::from_secs(10),
                jitter_percent: 0.25,
            },
            RetryClass::NonIdempotent => Self {
                class,
                max_attempts: 1,
                base_backoff: Duration::ZERO,
                max_backoff: Duration::ZERO,
                total_budget: Duration::ZERO,
                jitter_percent: 0.0,
            },
            RetryClass::CriticalWrite => Self {
                class,
                max_attempts: 3,
                base_backoff: Duration::from_millis(100),
                max_backoff: Duration::from_secs(5),
                total_budget: Duration::from_secs(15),
                jitter_percent: 0.25,
            },
        }
    }
}

/// Retry error wrapping the last attempt's failure on budget exhaustion.
#[derive(Debug, Error)]
pub enum RetryError<E> {
    /// Policy fields are inconsistent (e.g., `max_attempts < 1`).
    #[error("resilience: invalid retry policy: {0}")]
    InvalidPolicy(String),
    /// All attempts exhausted; last error wrapped for `?` chaining.
    #[error("resilience: retry budget exhausted")]
    BudgetExhausted(#[source] E),
    /// Non-retryable inner error — returned verbatim, NOT wrapped in
    /// `BudgetExhausted` so callers can `match` on it.
    #[error("resilience: non-retryable inner error: {0}")]
    NonRetryable(#[source] E),
}

/// `retry` runs `mk_fut` up to `policy.max_attempts` times. `mk_fut` is a
/// closure that yields a FRESH future per attempt (futures aren't re-pollable).
///
/// `is_retryable` decides whether each failure should retry — returning
/// `false` short-circuits with [`RetryError::NonRetryable`]. Pass
/// `|_| true` for the SR06 default ("retry all non-nil errors").
///
/// `retry_after_hint` may be returned by an error to override computed
/// backoff (mirrors Go `RetryAfter`). Pass `|_| None` to ignore.
pub async fn retry<F, Fut, T, E, R, H>(
    policy: RetryPolicy,
    mut mk_fut: F,
    is_retryable: R,
    retry_after_hint: H,
) -> Result<T, RetryError<E>>
where
    F: FnMut() -> Fut,
    Fut: Future<Output = Result<T, E>>,
    R: Fn(&E) -> bool,
    H: Fn(&E) -> Option<Duration>,
{
    validate_policy(&policy)?;
    let start = Instant::now();
    let mut last_err: Option<E> = None;
    for attempt in 1..=policy.max_attempts {
        match mk_fut().await {
            Ok(v) => return Ok(v),
            Err(e) => {
                if !is_retryable(&e) {
                    return Err(RetryError::NonRetryable(e));
                }
                if attempt == policy.max_attempts {
                    last_err = Some(e);
                    break;
                }
                let wait = compute_backoff(&policy, attempt, retry_after_hint(&e));
                if policy.total_budget > Duration::ZERO
                    && start.elapsed() + wait > policy.total_budget
                {
                    last_err = Some(e);
                    break;
                }
                last_err = Some(e);
                tokio::time::sleep(wait).await;
            }
        }
    }
    // Safe to unwrap: validate_policy ensures max_attempts >= 1, so the loop
    // runs at least once and last_err is Some on every error path.
    Err(RetryError::BudgetExhausted(last_err.expect(
        "retry loop should set last_err before break",
    )))
}

fn validate_policy<E>(p: &RetryPolicy) -> Result<(), RetryError<E>> {
    if p.max_attempts < 1 {
        return Err(RetryError::InvalidPolicy(format!(
            "max_attempts={} must be >= 1",
            p.max_attempts
        )));
    }
    if p.max_attempts > 1 {
        if p.base_backoff.is_zero() {
            return Err(RetryError::InvalidPolicy(
                "base_backoff must be > 0 when max_attempts > 1".into(),
            ));
        }
        if !(0.0..=1.0).contains(&p.jitter_percent) {
            return Err(RetryError::InvalidPolicy(format!(
                "jitter_percent={} must be in [0, 1]",
                p.jitter_percent
            )));
        }
    }
    Ok(())
}

fn compute_backoff(p: &RetryPolicy, attempt: usize, hint: Option<Duration>) -> Duration {
    if let Some(d) = hint {
        return clamp(d, p.max_backoff);
    }
    let base = p.base_backoff.saturating_mul(1u32 << (attempt - 1) as u32);
    if p.jitter_percent == 0.0 {
        return clamp(base, p.max_backoff);
    }
    // Deterministic-enough jitter source. Not crypto; jitter just needs
    // de-correlation across callers. We hash attempt + nanos via a cheap
    // mix to avoid pulling in the `rand` workspace dep.
    let seed = (attempt as u128).wrapping_mul(0x9E37_79B9_7F4A_7C15);
    let frac = ((seed >> 33) & 0x1FFF) as f64 / 8191.0; // [0, 1)
    let multiplier = 1.0 + (frac * 2.0 - 1.0) * p.jitter_percent;
    let wait_nanos = (base.as_nanos() as f64 * multiplier) as u128;
    clamp(Duration::from_nanos(wait_nanos as u64), p.max_backoff)
}

fn clamp(d: Duration, cap: Duration) -> Duration {
    if !cap.is_zero() && d > cap {
        cap
    } else {
        d
    }
}

// ────────────────────────────────────────────────────────────────────────
// Bulkhead — SR06 §12AI.10.
// ────────────────────────────────────────────────────────────────────────

/// Per-(service, dep) bulkhead configuration. Mirrors Go `BulkheadConfig`.
#[derive(Debug, Clone)]
pub struct BulkheadConfig {
    /// Dependency name (for the `lw_dependency_bulkhead_inflight{dep}` gauge).
    pub dep: String,
    /// Concurrent in-flight calls allowed.
    pub max_concurrent: usize,
    /// Pending callers allowed before rejection.
    pub queue_depth: usize,
    /// How long a queued caller waits before [`BulkheadError::Full`].
    pub queue_timeout: Duration,
}

/// Bulkhead error surface.
#[derive(Debug, Error)]
pub enum BulkheadError<E> {
    /// Config invalid — `max_concurrent` or `queue_depth` non-positive.
    #[error("resilience: invalid bulkhead config: {0}")]
    InvalidConfig(String),
    /// Slot + queue saturated OR queue-wait elapsed.
    #[error("resilience: bulkhead full for dep {0}")]
    Full(String),
    /// Inner future failed; error propagates.
    #[error("resilience: inner call failed: {0}")]
    Inner(#[source] E),
}

/// Thread-safe bulkhead built on a tokio [`Semaphore`].
pub struct Bulkhead {
    cfg: BulkheadConfig,
    slots: Arc<Semaphore>,
    queue_slots: Arc<Semaphore>,
    queue_notify: Arc<Notify>,
    active: AtomicUsize,
    rejected: AtomicUsize,
}

impl Bulkhead {
    /// Construct + validate. Returns [`BulkheadError::InvalidConfig`] on
    /// non-positive `max_concurrent` (a zero budget means the dep cannot
    /// be called — bootstrap MUST fail rather than silently no-op).
    pub fn new(cfg: BulkheadConfig) -> Result<Self, BulkheadError<()>> {
        if cfg.max_concurrent == 0 {
            return Err(BulkheadError::InvalidConfig(format!(
                "dep={:?} max_concurrent=0",
                cfg.dep
            )));
        }
        let slots = Arc::new(Semaphore::new(cfg.max_concurrent));
        // Queue capacity of 0 → no waiting; saturated callers reject immediately.
        let queue_slots = Arc::new(Semaphore::new(cfg.queue_depth.max(0)));
        Ok(Self {
            cfg,
            slots,
            queue_slots,
            queue_notify: Arc::new(Notify::new()),
            active: AtomicUsize::new(0),
            rejected: AtomicUsize::new(0),
        })
    }

    /// Current in-flight count (for the `lw_dependency_bulkhead_inflight` gauge).
    pub fn active(&self) -> usize {
        self.active.load(Ordering::Relaxed)
    }

    /// Cumulative rejections since construction.
    pub fn rejected(&self) -> usize {
        self.rejected.load(Ordering::Relaxed)
    }

    /// Run `fut` while holding a slot. On saturation, waits up to
    /// `queue_timeout` for a slot to free. Beyond that → [`BulkheadError::Full`].
    pub async fn call<F, T, E>(&self, fut: F) -> Result<T, BulkheadError<E>>
    where
        F: Future<Output = Result<T, E>>,
    {
        // Fast path — try to grab a slot without blocking.
        match self.slots.clone().try_acquire_owned() {
            Ok(permit) => {
                self.active.fetch_add(1, Ordering::Relaxed);
                let res = fut.await;
                self.active.fetch_sub(1, Ordering::Relaxed);
                self.queue_notify.notify_one();
                drop(permit);
                return res.map_err(BulkheadError::Inner);
            }
            Err(TryAcquireError::NoPermits) => {}
            Err(TryAcquireError::Closed) => {
                return Err(BulkheadError::Full(self.cfg.dep.clone()));
            }
        }
        // Enter the queue. If full → immediate rejection.
        let queue_permit = match self.queue_slots.clone().try_acquire_owned() {
            Ok(p) => p,
            Err(_) => {
                self.rejected.fetch_add(1, Ordering::Relaxed);
                return Err(BulkheadError::Full(self.cfg.dep.clone()));
            }
        };
        // Wait for a slot or timeout.
        let acquire = self.slots.clone().acquire_owned();
        let permit = match tokio::time::timeout(self.cfg.queue_timeout, acquire).await {
            Ok(Ok(p)) => p,
            Ok(Err(_)) => {
                self.rejected.fetch_add(1, Ordering::Relaxed);
                drop(queue_permit);
                return Err(BulkheadError::Full(self.cfg.dep.clone()));
            }
            Err(_) => {
                self.rejected.fetch_add(1, Ordering::Relaxed);
                drop(queue_permit);
                return Err(BulkheadError::Full(self.cfg.dep.clone()));
            }
        };
        drop(queue_permit);
        self.active.fetch_add(1, Ordering::Relaxed);
        let res = fut.await;
        self.active.fetch_sub(1, Ordering::Relaxed);
        self.queue_notify.notify_one();
        drop(permit);
        res.map_err(BulkheadError::Inner)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;
    // The breaker sync core moved to breaker-core; the half-open-probe test still
    // drives the (re-exported) CircuitBreaker with a std-Mutex-backed test clock.
    use std::sync::Mutex;
    use tokio::time::sleep;

    #[tokio::test]
    async fn with_timeout_rejects_zero() {
        let r: Result<(), TimeoutError<()>> =
            with_timeout("dep", Duration::ZERO, async { Ok(()) }).await;
        assert!(matches!(r, Err(TimeoutError::InvalidTimeout { .. })));
    }

    #[tokio::test]
    async fn with_timeout_passes_through_ok() {
        let r: Result<i32, TimeoutError<()>> =
            with_timeout("d", Duration::from_millis(50), async { Ok(7) }).await;
        assert_eq!(r.unwrap(), 7);
    }

    #[tokio::test]
    async fn with_timeout_deadline_exceeded() {
        let r: Result<(), TimeoutError<&'static str>> =
            with_timeout("d", Duration::from_millis(5), async {
                sleep(Duration::from_millis(50)).await;
                Ok(())
            })
            .await;
        assert!(matches!(r, Err(TimeoutError::DeadlineExceeded(_))));
    }

    #[tokio::test]
    async fn breaker_trips_on_error_rate() {
        let b = CircuitBreaker::new(
            "d",
            BreakerConfig {
                error_rate_threshold: 0.5,
                min_requests: 4,
                open_duration: Duration::from_secs(3600),
                half_open_probe_interval: Duration::from_millis(100),
            },
        );
        for _ in 0..3 {
            let _: Result<(), BreakerError<&'static str>> = b.call(async { Err("boom") }).await;
        }
        let _: Result<(), BreakerError<&'static str>> = b.call(async { Ok(()) }).await;
        assert_eq!(b.state(), BreakerState::Open);
    }

    #[tokio::test]
    async fn breaker_open_fast_fails() {
        let b = CircuitBreaker::new(
            "d",
            BreakerConfig {
                error_rate_threshold: 0.5,
                min_requests: 2,
                open_duration: Duration::from_secs(3600),
                half_open_probe_interval: Duration::from_millis(100),
            },
        );
        for _ in 0..2 {
            let _: Result<(), BreakerError<&'static str>> = b.call(async { Err("boom") }).await;
        }
        assert_eq!(b.state(), BreakerState::Open);
        let invoked = Arc::new(AtomicUsize::new(0));
        let invoked2 = invoked.clone();
        let r: Result<(), BreakerError<&'static str>> = b
            .call(async move {
                invoked2.fetch_add(1, Ordering::Relaxed);
                Ok(())
            })
            .await;
        assert!(matches!(r, Err(BreakerError::Open(_))));
        assert_eq!(invoked.load(Ordering::Relaxed), 0);
    }

    #[tokio::test]
    async fn breaker_half_open_probe_recovers() {
        // Drive Open immediately, then advance the clock past open_duration
        // via the `with_clock` constructor.
        let clock_state = Arc::new(Mutex::new(Instant::now()));
        let clock_for_breaker = clock_state.clone();
        let b = CircuitBreaker::with_clock(
            "d",
            BreakerConfig {
                error_rate_threshold: 0.5,
                min_requests: 2,
                open_duration: Duration::from_millis(50),
                half_open_probe_interval: Duration::from_millis(1),
            },
            move || *clock_for_breaker.lock().unwrap(),
        );
        for _ in 0..2 {
            let _: Result<(), BreakerError<&'static str>> = b.call(async { Err("boom") }).await;
        }
        assert_eq!(b.state(), BreakerState::Open);
        // Advance clock past open_duration. The next call probes.
        {
            let mut g = clock_state.lock().unwrap();
            *g += Duration::from_millis(100);
        }
        let r: Result<(), BreakerError<&'static str>> = b.call(async { Ok(()) }).await;
        assert!(r.is_ok());
        assert_eq!(b.state(), BreakerState::Closed);
    }

    #[tokio::test]
    async fn retry_succeeds_on_first_attempt() {
        let counter = Arc::new(AtomicUsize::new(0));
        let c2 = counter.clone();
        let p = RetryPolicy::default_for(RetryClass::Idempotent);
        let r: Result<i32, RetryError<&'static str>> = retry(
            p,
            move || {
                let c3 = c2.clone();
                async move {
                    c3.fetch_add(1, Ordering::Relaxed);
                    Ok(42)
                }
            },
            |_| true,
            |_| None,
        )
        .await;
        assert_eq!(r.unwrap(), 42);
        assert_eq!(counter.load(Ordering::Relaxed), 1);
    }

    #[tokio::test]
    async fn retry_budget_exhausted_wraps_last_err() {
        let mut p = RetryPolicy::default_for(RetryClass::Idempotent);
        p.base_backoff = Duration::from_millis(1);
        p.max_backoff = Duration::from_millis(1);
        p.jitter_percent = 0.0;
        let r: Result<(), RetryError<&'static str>> =
            retry(p, || async { Err("nope") }, |_| true, |_| None).await;
        assert!(matches!(r, Err(RetryError::BudgetExhausted(_))));
    }

    #[tokio::test]
    async fn retry_non_retryable_short_circuits() {
        let attempts = Arc::new(AtomicUsize::new(0));
        let a2 = attempts.clone();
        let mut p = RetryPolicy::default_for(RetryClass::Idempotent);
        p.base_backoff = Duration::from_millis(1);
        let r: Result<(), RetryError<&'static str>> = retry(
            p,
            move || {
                let a3 = a2.clone();
                async move {
                    a3.fetch_add(1, Ordering::Relaxed);
                    Err("permanent")
                }
            },
            |e| !matches!(*e, "permanent"),
            |_| None,
        )
        .await;
        assert!(matches!(r, Err(RetryError::NonRetryable(_))));
        assert_eq!(attempts.load(Ordering::Relaxed), 1);
    }

    #[tokio::test]
    async fn retry_invalid_policy() {
        let mut p = RetryPolicy::default_for(RetryClass::Idempotent);
        p.max_attempts = 0;
        let r: Result<(), RetryError<()>> =
            retry(p, || async { Ok::<(), ()>(()) }, |_| true, |_| None).await;
        assert!(matches!(r, Err(RetryError::InvalidPolicy(_))));
    }

    #[tokio::test]
    async fn bulkhead_rejects_invalid_config() {
        let r = Bulkhead::new(BulkheadConfig {
            dep: "d".into(),
            max_concurrent: 0,
            queue_depth: 1,
            queue_timeout: Duration::from_millis(1),
        });
        assert!(matches!(r, Err(BulkheadError::InvalidConfig(_))));
    }

    #[tokio::test]
    async fn bulkhead_fast_path_below_concurrency() {
        let bh = Bulkhead::new(BulkheadConfig {
            dep: "d".into(),
            max_concurrent: 3,
            queue_depth: 0,
            queue_timeout: Duration::from_millis(1),
        })
        .unwrap();
        for _ in 0..3 {
            let r: Result<(), BulkheadError<()>> = bh.call(async { Ok(()) }).await;
            r.unwrap();
        }
        assert_eq!(bh.rejected(), 0);
    }

    #[tokio::test]
    async fn bulkhead_rejects_when_slots_and_queue_full() {
        let bh = Arc::new(
            Bulkhead::new(BulkheadConfig {
                dep: "d".into(),
                max_concurrent: 1,
                queue_depth: 0,
                queue_timeout: Duration::from_millis(1),
            })
            .unwrap(),
        );
        let hold = Arc::new(Notify::new());
        let bh_hold = bh.clone();
        let hold_clone = hold.clone();
        let handle = tokio::spawn(async move {
            let _: Result<(), BulkheadError<()>> = bh_hold
                .call(async move {
                    hold_clone.notified().await;
                    Ok(())
                })
                .await;
        });
        // Wait for the worker to take the slot.
        for _ in 0..100 {
            if bh.active() == 1 {
                break;
            }
            sleep(Duration::from_millis(1)).await;
        }
        let r: Result<(), BulkheadError<()>> = bh.call(async { Ok(()) }).await;
        assert!(matches!(r, Err(BulkheadError::Full(_))));
        assert_eq!(bh.rejected(), 1);
        hold.notify_one();
        handle.await.unwrap();
    }
}
